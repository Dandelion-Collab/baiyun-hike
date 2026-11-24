"""图的加载与双向邻接表。"""

from __future__ import annotations

import pytest

from app.graph import load_graph


def test_adjacency_is_bidirectional() -> None:
    graph = load_graph()

    forward = [edge for edge in graph.neighbors("N01") if edge["to"] == "N06"]
    backward = [edge for edge in graph.neighbors("N06") if edge["to"] == "N01"]

    assert forward
    assert backward
    assert forward[0]["walk_min"] == backward[0]["walk_min"]
    assert forward[0]["passable_windows"] == backward[0]["passable_windows"]


def test_neighbors_unknown_id_raises_key_error() -> None:
    graph = load_graph()

    with pytest.raises(KeyError):
        graph.neighbors("N99")


def test_node_unknown_id_raises_key_error() -> None:
    graph = load_graph()

    with pytest.raises(KeyError):
        graph.node("N99")


def test_nodes_keep_night_access_column() -> None:
    graph = load_graph()

    assert graph.node("N01")["night_access"] == "open"
    assert graph.node("N01")["open_windows"] == "00:00-24:00"
    assert graph.node("N09")["open_windows"] == "00:00-24:00"