"""白云山图加载（无向图）。

按 D9：CSV 每条边只录一次，邻接表同时注册 from->to 与 to->from，
两个方向共享同一组 walk_min 与 passable_windows。
数值字段在加载时强制转换：distance_m / walk_min -> int，lat / lng -> float，
其余字段保持 str，避免路由层做算术时把字符串悄悄拼接。
本模块只做加载与引用完整性检查，不做任何时间判断。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.exceptions import DataError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Graph:
    """nodes 以 id 为键；adjacency 是双向邻接表，值为按当前节点定向的边 dict。"""

    nodes: dict[str, dict[str, object]]
    edges: list[dict[str, object]]
    adjacency: dict[str, list[dict[str, object]]]

    def node(self, node_id: str) -> dict[str, object]:
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise KeyError(f"不存在的节点 id：{node_id}") from exc

    def neighbors(self, node_id: str) -> list[dict[str, object]]:
        try:
            return list(self.adjacency[node_id])
        except KeyError as exc:
            raise KeyError(f"不存在的节点 id：{node_id}") from exc


def _read_rows(path: Path) -> list[dict[str, object]]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@lru_cache(maxsize=1)
def load_graph(
    nodes_path: str | Path | None = None,
    edges_path: str | Path | None = None,
) -> Graph:
    """读取图数据。重复节点 id、悬空边、数值字段非法都抛 DataError。"""

    node_file = Path(nodes_path) if nodes_path is not None else DATA_DIR / "baiyun_nodes.csv"
    edge_file = Path(edges_path) if edges_path is not None else DATA_DIR / "baiyun_edges.csv"

    nodes: dict[str, dict[str, object]] = {}
    for row in _read_rows(node_file):
        node_id = str(row.get("id", ""))
        if not node_id:
            raise DataError(f"{node_file.name} 存在空 id 的行")
        if node_id in nodes:
            raise DataError(f"{node_file.name} 节点 id 重复：{node_id}")
        try:
            row["lat"] = float(row["lat"])
            row["lng"] = float(row["lng"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DataError(f"{node_file.name} 坐标不是数字：{node_id}") from exc
        nodes[node_id] = row

    edges = _read_rows(edge_file)
    adjacency: dict[str, list[dict[str, object]]] = {node_id: [] for node_id in nodes}
    for row in edges:
        for end in ("from", "to"):
            if str(row.get(end)) not in nodes:
                raise DataError(f"{edge_file.name} 边引用了不存在的节点：{row.get(end)}")
        try:
            row["distance_m"] = int(row["distance_m"])
            row["walk_min"] = int(row["walk_min"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DataError(
                f"{edge_file.name} 距离或耗时不是整数：{row.get('from')}->{row.get('to')}"
            ) from exc
        payload = {
            key: value for key, value in row.items() if key not in ("from", "to")
        }
        source, target = str(row["from"]), str(row["to"])
        adjacency[source].append({"from": source, "to": target, **payload})
        adjacency[target].append({"from": target, "to": source, **payload})

    return Graph(nodes=nodes, edges=edges, adjacency=adjacency)