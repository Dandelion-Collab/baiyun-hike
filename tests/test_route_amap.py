"""接驳走高德、内部走本地图：plan 的编排测试。"""

from __future__ import annotations

import app.route_amap as route_amap
from app.amap import AmapError, AmapRoute
from app.gates import load_gates
from app.models import Fallback, Leg, RouteResult

ORIGIN = "113.268000,23.125000"
DEST_NODE = "N10"


def _transfer(minutes: int) -> AmapRoute:
    return AmapRoute(
        distance_m=4000,
        duration_min=minutes,
        steps=[],
        polyline=[(113.268, 23.125), (113.296288, 23.159042)],
    )


def _south_coord() -> str:
    south = next(gate for gate in load_gates() if gate["id"] == "N01")
    return f"{float(south['lng']):.6f},{float(south['lat']):.6f}"


def _south_legs() -> list[Leg]:
    return [
        Leg(from_node="N01", to_node="N06", walk_min=21, distance_m=1528, lighting="good"),
        Leg(from_node="N06", to_node="N07", walk_min=48, distance_m=3421, lighting="partial"),
        Leg(from_node="N07", to_node="N08", walk_min=14, distance_m=1000, lighting="good"),
        Leg(from_node="N08", to_node="N09", walk_min=22, distance_m=1372, lighting="partial"),
        Leg(from_node="N09", to_node="N10", walk_min=8, distance_m=496, lighting="none"),
    ]


def test_origin_at_gate_skips_transfer(monkeypatch) -> None:
    def fail_walking(*args, **kwargs):
        raise AssertionError("起点在门附近时不应调用高德接驳")

    monkeypatch.setattr(route_amap, "walking_route", fail_walking)

    def fake_find_route(graph, start, goal, depart):
        return RouteResult(
            reachable=True,
            path=["N01", "N06", "N07", "N08", "N09", "N10"],
            legs=_south_legs(),
            total_min=113,
        )

    monkeypatch.setattr(route_amap, "find_route", fake_find_route)

    result = route_amap.plan(_south_coord(), DEST_NODE, "22:00")

    assert result.reachable is True
    assert result.total_min == 113
    assert len(result.legs) == 1
    assert result.legs[0]["mode"] == "local"
    assert result.gates_checked == ["N01"]



def test_arrival_times_accumulate_from_previous_leg() -> None:
    legs = [{"mode": "amap", "minutes": 66}]
    segments = [
        {"from": "N04", "to": "N10", "distance_m": 2689, "walk_min": 43, "lighting": "none"}
    ]

    times = route_amap.arrival_times("22:00", legs, segments)

    assert times == ["23:06", "23:49"]


def test_transfer_plus_local_total_and_uses_router(monkeypatch) -> None:
    monkeypatch.setattr(route_amap, "walking_route", lambda *args, **kwargs: _transfer(20))
    calls = []

    def fake_find_route(graph, start, goal, depart):
        calls.append((start, goal, depart))
        return RouteResult(
            reachable=True,
            path=["N01", "N06", "N07", "N08", "N09", "N10"],
            legs=[],
            total_min=113,
        )

    monkeypatch.setattr(route_amap, "find_route", fake_find_route)

    result = route_amap.plan(ORIGIN, DEST_NODE, "19:00")

    assert result.reachable is True
    assert calls
    assert result.total_min == 20 + 113
    assert result.legs[0]["mode"] == "amap"
    assert result.legs[0]["minutes"] == 20
    assert result.legs[1]["mode"] == "local"


def test_closed_gate_is_rejected_then_next_gate_wins(monkeypatch) -> None:
    monkeypatch.setattr(route_amap, "walking_route", lambda *args, **kwargs: _transfer(20))
    real = {str(gate["id"]): gate for gate in load_gates()}
    monkeypatch.setattr(route_amap, "load_gates", lambda: [real["N03"], real["N01"]])

    def fake_find_route(graph, start, goal, depart):
        return RouteResult(
            reachable=True, path=[start, "N07", "N08", "N09", "N10"], legs=[], total_min=30
        )

    monkeypatch.setattr(route_amap, "find_route", fake_find_route)

    result = route_amap.plan(ORIGIN, DEST_NODE, "22:30")

    assert result.reachable is True
    assert result.gates_checked == ["N01"]
    assert any("柯子岭门" in item for item in result.rejected)


def test_all_gates_blocked_returns_advice(monkeypatch) -> None:
    monkeypatch.setattr(route_amap, "walking_route", lambda *args, **kwargs: _transfer(20))

    def fake_find_route(graph, start, goal, depart):
        return RouteResult(
            reachable=False,
            path=[],
            legs=[],
            total_min=0,
            partial=True,
            fallback=Fallback(farthest_path=[start, "N07"]),
        )

    monkeypatch.setattr(route_amap, "find_route", fake_find_route)

    result = route_amap.plan(ORIGIN, DEST_NODE, "23:00")

    assert result.reachable is False
    assert len(result.advice) >= 2
    assert result.rejected


def test_missing_key_is_captured(monkeypatch) -> None:
    monkeypatch.delenv("AMAP_KEY", raising=False)
    monkeypatch.setattr(
        route_amap,
        "walking_route",
        lambda *args, **kwargs: (_ for _ in ()).throw(route_amap.MissingKeyError("no key")),
    )

    result = route_amap.plan(ORIGIN, DEST_NODE, "19:00")

    assert result.reachable is False
    assert "未配置高德 Key" in result.reason
    assert len(result.advice) >= 2