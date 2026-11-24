"""可通行性判定的边界用例。"""

from __future__ import annotations

import pytest

from app.graph import load_graph
from app.passability import (
    edge_passable,
    explain_why_closed,
    is_open,
    node_enterable,
    parse_windows,
)


def _edge(windows: str) -> dict[str, str]:
    return {"from": "A", "to": "B", "passable_windows": windows}


def _node(
    windows: str, *, kind: str = "junction", night_access: str = "open"
) -> dict[str, str]:
    return {
        "id": "X",
        "type": kind,
        "open_windows": windows,
        "night_access": night_access,
    }


def test_edge_closed_at_exact_end() -> None:
    assert edge_passable(_edge("06:00-21:30"), 21 * 60 + 30, 21 * 60 + 42) is False


def test_edge_requires_full_coverage() -> None:
    assert edge_passable(_edge("06:00-21:30"), 21 * 60 + 29, 21 * 60 + 45) is False


def test_edge_passable_inside_window() -> None:
    assert edge_passable(_edge("06:00-21:30"), 20 * 60, 20 * 60 + 20) is True


def test_is_open_is_half_open() -> None:
    node = _node("06:00-22:00")

    assert is_open(node, 22 * 60) is False
    assert is_open(node, 22 * 60 - 1) is True


def test_all_day_window_is_open_any_time() -> None:
    node = _node("00:00-24:00")

    assert is_open(node, 0) is True
    assert is_open(node, 23 * 60 + 59) is True


def test_multi_window_across_lunch_break() -> None:
    node = _node("06:00-12:00;14:00-18:00")

    assert is_open(node, 13 * 60) is False
    assert is_open(node, 14 * 60 + 30) is True


def test_invalid_window_format_raises() -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_windows("6点-22点")

    assert "6点-22点" in str(excinfo.value)


def test_gate_rejects_entry_after_close() -> None:
    graph = load_graph()

    assert node_enterable(graph.node("N03"), 22 * 60) is False
    assert node_enterable(graph.node("N03"), 21 * 60 + 30) is True


def test_gate_accepts_entry_at_cutoff_boundary() -> None:
    graph = load_graph()

    assert node_enterable(graph.node("N02"), 22 * 60) is True
    assert node_enterable(graph.node("N02"), 23 * 60 + 29) is True
    assert node_enterable(graph.node("N02"), 23 * 60 + 31) is False


def test_junction_ignores_entry_cutoff() -> None:
    graph = load_graph()

    assert node_enterable(graph.node("N07"), 22 * 60 + 35) is True


def test_explain_contains_closing_time_and_trip_times() -> None:
    message = explain_why_closed(_edge("06:00-21:30"), 21 * 60 + 29, 21 * 60 + 45)

    assert "21:30" in message
    assert "21:29" in message
    assert "21:45" in message


def test_parse_windows_accepts_24_00() -> None:
    assert parse_windows("06:00-24:00") == [(360, 1440)]