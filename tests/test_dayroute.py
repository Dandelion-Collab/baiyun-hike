"""plan_day：分段连线的真实路径、回退与调用边界。"""

from __future__ import annotations

import app.dayroute as dayroute
from app.amap import AmapError, AmapRoute

NEAR_A = ("甲", (113.300000, 23.170000))
NEAR_B = ("乙", (113.300000, 23.175000))
FAR_A = ("南门", (113.300000, 23.160000))
FAR_B = ("白云山北", (113.300000, 23.250000))


def _route() -> AmapRoute:
    return AmapRoute(
        distance_m=640,
        duration_min=9,
        steps=[],
        polyline=[(113.300000, 23.170000), (113.300000, 23.172000), (113.300000, 23.175000)],
    )


def _boom(*args, **kwargs):
    raise AssertionError("该场景不应调用 walking_route")


def test_real_path_uses_amap_distance_and_minutes(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_walking(origin: str, dest: str) -> AmapRoute:
        calls.append((origin, dest))
        return _route()

    monkeypatch.setattr(dayroute, "walking_route", fake_walking)

    legs = dayroute.plan_day([NEAR_A, NEAR_B], True)

    assert calls == [("113.300000,23.170000", "113.300000,23.175000")]
    leg = legs[0]
    assert leg.index == 0
    assert leg.real_path is True
    assert leg.mode == "walk"
    assert leg.straight_m == 556
    assert leg.distance_m == 640
    assert leg.minutes == 9
    assert leg.polyline == _route().polyline
    assert leg.note == ""


def test_amap_error_falls_back_to_straight_line(monkeypatch) -> None:
    def fail_walking(*args, **kwargs):
        raise AmapError("高德请求失败：URLError")

    monkeypatch.setattr(dayroute, "walking_route", fail_walking)

    legs = dayroute.plan_day([NEAR_A, NEAR_B], True)

    leg = legs[0]
    assert leg.real_path is False
    assert leg.note == "直线估算"
    assert leg.straight_m == 556
    assert leg.distance_m == 556
    assert leg.minutes == 7
    assert leg.polyline == [NEAR_A[1], NEAR_B[1]]


def test_ten_km_leg_never_calls_walking_route(monkeypatch) -> None:
    monkeypatch.setattr(dayroute, "walking_route", _boom)

    legs = dayroute.plan_day([FAR_A, FAR_B], True)

    assert legs[0].straight_m > dayroute.AMAP_WALK_MAX_M
    assert legs[0].real_path is False
    assert legs[0].note == "直线估算"


def test_empty_input_returns_empty_list() -> None:
    assert dayroute.plan_day([], True) == []
    assert dayroute.plan_day([NEAR_A], True) == []


def test_four_points_give_three_legs_in_order(monkeypatch) -> None:
    monkeypatch.setattr(dayroute, "walking_route", _boom)
    points = [
        ("A", (113.300000, 23.170000)),
        ("B", (113.300000, 23.175000)),
        ("C", (113.305000, 23.175000)),
        ("D", (113.305000, 23.180000)),
    ]

    legs = dayroute.plan_day(points, False)

    assert [leg.index for leg in legs] == [0, 1, 2]
    assert [(leg.from_name, leg.to_name) for leg in legs] == [
        ("A", "B"),
        ("B", "C"),
        ("C", "D"),
    ]
    assert legs[0].to_name == legs[1].from_name
    assert legs[0].polyline[-1] == points[1][1]
    assert legs[1].polyline[0] == points[1][1]


def test_missing_key_never_calls_walking_route(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_walking(origin: str, dest: str) -> AmapRoute:
        calls.append((origin, dest))
        return _route()

    monkeypatch.setattr(dayroute, "walking_route", fake_walking)

    legs = dayroute.plan_day([NEAR_A, NEAR_B], False)

    assert calls == []
    assert all(leg.real_path is False and leg.note == "直线估算" for leg in legs)