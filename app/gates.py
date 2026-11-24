"""门禁点：从白云山节点里筛出山门，并判断一条路线是否经过某门。"""

from __future__ import annotations

import math

from app.graph import load_graph

EARTH_RADIUS_M = 6371000.0
DEFAULT_RADIUS_M = 60


def _distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def load_gates() -> list[dict]:
    """读取图数据里的山门节点，字段与 graph 节点一致。"""

    graph = load_graph()
    return [dict(node) for node in graph.nodes.values() if node.get("type") == "gate"]


def gates_near(
    points: list[tuple[float, float]], radius_m: float = DEFAULT_RADIUS_M
) -> list[dict]:
    """polyline 点列（lng, lat）里任一点落在门的 radius 内，即视为经过；按门去重。"""

    if not points:
        return []

    hits: list[dict] = []
    for gate in load_gates():
        gate_lat = float(gate["lat"])
        gate_lng = float(gate["lng"])
        for lng, lat in points:
            if _distance_m(gate_lat, gate_lng, float(lat), float(lng)) <= radius_m:
                hits.append(gate)
                break
    return hits