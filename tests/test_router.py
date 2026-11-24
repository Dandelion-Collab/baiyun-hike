"""能力 B：带时间窗的最短路测试（新四张牌 + 边界）。"""

from __future__ import annotations

import pytest

from app.graph import load_graph
from app.passability import edge_passable, node_enterable
from app.router import find_route


def _graph():
    return load_graph()


def test_1900_n01_to_n10_is_reachable() -> None:
    result = find_route(_graph(), "N01", "N10", "19:00")

    assert result.reachable is True
    assert result.path == ["N01", "N06", "N07", "N08", "N09", "N10"]
    assert result.total_min == 113
    assert result.partial is False


def test_2000_n01_to_n10_is_reachable() -> None:
    result = find_route(_graph(), "N01", "N10", "20:00")

    assert result.reachable is True
    assert result.total_min == 113


def test_2100_n01_to_n10_is_reachable() -> None:
    result = find_route(_graph(), "N01", "N10", "21:00")

    assert result.reachable is True
    assert result.total_min == 113


def test_2200_n01_to_n10_is_reachable() -> None:
    result = find_route(_graph(), "N01", "N10", "22:00")

    assert result.reachable is True
    assert result.path == ["N01", "N06", "N07", "N08", "N09", "N10"]
    assert result.total_min == 113


def test_2230_n03_is_unreachable_and_mentions_gate() -> None:
    result = find_route(_graph(), "N03", "N10", "22:30")

    assert result.reachable is False
    assert result.reason is not None
    assert "柯子岭门" in result.reason
    assert "21:30 前可进" in result.reason
    assert "建议走 24 小时开放的南门/西门" in result.reason


def test_2330_n03_is_unreachable_without_blanket_wording() -> None:
    result = find_route(_graph(), "N03", "N10", "23:30")

    assert result.reachable is False
    assert result.reason is not None
    assert "柯子岭门" in result.reason
    assert "今晚无法上山" not in result.reason


def test_2200_n02_to_n07_is_reachable() -> None:
    result = find_route(_graph(), "N02", "N07", "22:00")

    assert result.reachable is True
    assert result.path == ["N02", "N07"]
    assert result.total_min == 41


def test_2300_n04_to_n10_is_reachable_direct() -> None:
    result = find_route(_graph(), "N04", "N10", "23:00")

    assert result.reachable is True
    assert result.path == ["N04", "N10"]
    assert result.total_min == 43


def test_same_start_and_goal() -> None:
    result = find_route(_graph(), "N01", "N01", "19:00")

    assert result.reachable is True
    assert result.path == ["N01"]
    assert result.legs == []
    assert result.total_min == 0


def test_unknown_node_id_raises_value_error() -> None:
    with pytest.raises(ValueError) as excinfo:
        find_route(_graph(), "N99", "N10", "19:00")

    assert "N99" in str(excinfo.value)


def test_repeat_request_is_stable() -> None:
    graph = _graph()

    first = find_route(graph, "N01", "N10", "22:00")
    second = find_route(graph, "N01", "N10", "22:00")

    assert first.model_dump() == second.model_dump()


def test_no_lighting_edge_produces_warning() -> None:
    result = find_route(_graph(), "N03", "N07", "19:00")

    assert result.reachable is True
    assert result.warnings
    assert any("无照明" in warning for warning in result.warnings)


def test_result_field_types() -> None:
    result = find_route(_graph(), "N01", "N10", "19:00")

    assert isinstance(result.total_min, int)
    assert result.arrive_at == "20:53"
    for leg in result.legs:
        assert isinstance(leg.walk_min, int)
        assert isinstance(leg.distance_m, int)


def test_node_lat_lng_are_float() -> None:
    node = _graph().node("N01")

    assert isinstance(node["lat"], float)
    assert isinstance(node["lng"], float)


def test_edge_distance_and_walk_min_are_int() -> None:
    edge = _graph().neighbors("N01")[0]

    assert isinstance(edge["distance_m"], int)
    assert isinstance(edge["walk_min"], int)


def test_fallback_path_is_fully_passable() -> None:
    graph = _graph()
    result = find_route(graph, "N01", "N10", "23:00")

    assert result.fallback is not None
    path = result.fallback.farthest_path
    assert path[-1] == "N06"

    t = 23 * 60
    for current, nxt in zip(path, path[1:]):
        edge = next(edge for edge in graph.neighbors(current) if edge["to"] == nxt)
        t2 = t + edge["walk_min"]
        assert edge_passable(edge, t, t2)
        assert node_enterable(graph.node(nxt), t2)
        t = t2