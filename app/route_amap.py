"""接驳走高德、景区内部走本地图。

高德只负责“城市起点 → 山门”的接驳；进山后一律用 app.router.find_route，
避免高德在白云山内部绕山外一大圈。门能否进仍以本地 open_windows 为准。
若起点本身就在某个山门 120 米内，则该门直接作为入口，接驳为 0、不调高德。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.amap import AmapError, MissingKeyError, walking_route
from app.gates import load_gates
from app.graph import load_graph
from app.passability import node_enterable, parse_windows
from app.router import find_route
from app.rules import ENTRY_CUTOFF_MIN

LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "agent.log"
MISSING_KEY_REASON = "未配置高德 Key，已切换离线方案"
ORIGIN_GATE_RADIUS_M = 120
EARTH_RADIUS_M = 6371000.0


@dataclass
class RoutePlan:
    origin: str
    dest_node: str
    depart_at: str
    reachable: bool
    total_min: int = 0
    duration_min: int = 0
    distance_m: int = 0
    legs: list[dict] = field(default_factory=list)
    segments: list[dict] = field(default_factory=list)
    polyline: list[tuple[float, float]] = field(default_factory=list)
    internal_is_estimate: bool = False
    gates_checked: list[str] = field(default_factory=list)
    reason: str = ""
    advice: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def _to_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _near_gate(origin: str) -> dict | None:
    try:
        lng_text, lat_text = str(origin).split(",")
        lng, lat = float(lng_text), float(lat_text)
    except (AttributeError, ValueError):
        return None

    best_gate: dict | None = None
    best_distance = ORIGIN_GATE_RADIUS_M + 1
    for gate in load_gates():
        distance = _distance_m(lat, lng, float(gate["lat"]), float(gate["lng"]))
        if distance <= ORIGIN_GATE_RADIUS_M and distance < best_distance:
            best_gate = gate
            best_distance = distance
    return best_gate


def _cutoff_minutes(gate: dict) -> int:
    windows = parse_windows(str(gate["open_windows"]))
    return windows[-1][1] - ENTRY_CUTOFF_MIN


def _log(origin: str, dest: str, depart_at: str, attempts: int, result: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = (
        f"{datetime.now().isoformat(timespec='seconds')} | plan | "
        f"{origin}→{dest} | {depart_at} | {attempts} | {result}\n"
    )
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line)


def _offline_advice() -> list[str]:
    return [
        "改用离线自建路线（app.router.find_route）",
        "或配置 AMAP_KEY 后再试",
    ]


def _advice() -> list[str]:
    return [
        "改早一些出发，赶在门禁停止入园前到达",
        "换一个入口再试，不同山门关闭时间不同",
        "或改去离你更近、当前时段开放的景点",
    ]


def _gate_reason(gate: dict, depart_at: str) -> str:
    cutoff = _fmt(_cutoff_minutes(gate))
    return (
        f"{gate['name']} {gate['open_windows']}，{cutoff} 前可进；"
        f"你 {depart_at} 到达。建议走 24 小时开放的南门/西门"
    )


def _segments_from(internal) -> list[dict]:
    return [
        {
            "from": str(leg.from_node),
            "to": str(leg.to_node),
            "distance_m": int(leg.distance_m),
            "walk_min": int(leg.walk_min),
            "lighting": str(leg.lighting or ""),
        }
        for leg in internal.legs
    ]


def _internal_polyline(graph, internal) -> list[tuple[float, float]]:
    return [
        (float(graph.node(node_id)["lng"]), float(graph.node(node_id)["lat"]))
        for node_id in internal.path
    ]


def arrival_times(depart_at: str, legs: list[dict], segments: list[dict]) -> list[str]:
    """逐段到达时刻：接驳（若有）+ 内部逐段，统一按“上一段到达 + 本段时长”累加。"""

    current = _to_minutes(depart_at)
    times: list[str] = []
    if legs and legs[0].get("mode") == "amap":
        current += int(legs[0]["minutes"])
        times.append(_fmt(current))
    for segment in segments:
        current += int(segment["walk_min"])
        times.append(_fmt(current))
    return times


def plan(origin: str, dest_node: str, depart_at: str, city: str = "广州") -> RoutePlan:
    """起点在门内直接本地进山；否则逐个山门尝试“高德接驳 + 本地进山”。"""

    depart_min = _to_minutes(depart_at)
    graph = load_graph()
    attempts = 0
    rejected: list[str] = []
    failures: list[tuple[int, str]] = []
    best: tuple[int, dict, object, object, list[dict]] | None = None

    start_gate = _near_gate(origin)
    if start_gate is not None:
        gate_id = str(start_gate["id"])
        if not node_enterable(start_gate, depart_min):
            reason = _gate_reason(start_gate, depart_at)
            _log(origin, dest_node, depart_at, 0, f"unreachable at gate {gate_id}")
            return RoutePlan(
                origin=origin,
                dest_node=dest_node,
                depart_at=depart_at,
                reachable=False,
                reason=reason,
                advice=_advice(),
                rejected=[reason],
            )

        internal = find_route(graph, gate_id, dest_node, depart_at)
        if not internal.reachable:
            farthest = (
                str(internal.fallback.farthest_path[-1])
                if internal.fallback and internal.fallback.farthest_path
                else gate_id
            )
            reason = f"从{start_gate['name']}进山后到不了{dest_node}，最远到{farthest}"
            _log(origin, dest_node, depart_at, 0, f"unreachable from gate {gate_id}")
            return RoutePlan(
                origin=origin,
                dest_node=dest_node,
                depart_at=depart_at,
                reachable=False,
                reason=reason,
                advice=_advice(),
                rejected=[reason],
            )

        total = internal.total_min
        legs = [
            {
                "mode": "local",
                "from": str(start_gate["name"]),
                "to": dest_node,
                "minutes": total,
                "path": list(internal.path),
            }
        ]
        _log(origin, dest_node, depart_at, 0, f"local only via gate {gate_id}")
        return RoutePlan(
            origin=origin,
            dest_node=dest_node,
            depart_at=depart_at,
            reachable=True,
            total_min=total,
            duration_min=total,
            distance_m=sum(leg.distance_m for leg in internal.legs),
            legs=legs,
            segments=_segments_from(internal),
            polyline=_internal_polyline(graph, internal),
            internal_is_estimate=True,
            gates_checked=[gate_id],
        )

    for gate in load_gates():
        gate_id = str(gate["id"])
        gate_coord = f"{float(gate['lng']):.6f},{float(gate['lat']):.6f}"
        attempts += 1
        try:
            transfer = walking_route(origin, gate_coord, city=city)
        except MissingKeyError:
            _log(origin, dest_node, depart_at, attempts, "missing key")
            return RoutePlan(
                origin=origin,
                dest_node=dest_node,
                depart_at=depart_at,
                reachable=False,
                reason=MISSING_KEY_REASON,
                rejected=[MISSING_KEY_REASON],
                advice=_offline_advice(),
            )
        except AmapError as exc:
            rejected.append(f"接驳到{gate['name']}失败：{exc}")
            continue

        arrival = depart_min + transfer.duration_min
        if not node_enterable(gate, arrival):
            gap = max(0, arrival - _cutoff_minutes(gate))
            message = f"到达{gate['name']}时已不可进（{_fmt(arrival)}）"
            rejected.append(message)
            failures.append((gap, message))
            continue

        internal = find_route(graph, gate_id, dest_node, _fmt(arrival))
        if not internal.reachable:
            farthest = (
                str(internal.fallback.farthest_path[-1])
                if internal.fallback and internal.fallback.farthest_path
                else gate_id
            )
            rejected.append(f"从{gate['name']}进山后到不了{dest_node}，最远到{farthest}")
            continue

        total = transfer.duration_min + internal.total_min
        legs = [
            {
                "mode": "amap",
                "from": "起点",
                "to": str(gate["name"]),
                "minutes": transfer.duration_min,
                "distance_m": transfer.distance_m,
            },
            {
                "mode": "local",
                "from": str(gate["name"]),
                "to": dest_node,
                "minutes": internal.total_min,
                "path": list(internal.path),
            },
        ]
        if best is None or total < best[0]:
            best = (total, gate, transfer, internal, legs)

    if best is None:
        if failures:
            gap, message = min(failures, key=lambda item: item[0])
            reason = f"{message}；最接近只差 {gap} 分钟"
        elif rejected:
            reason = rejected[0]
        else:
            reason = "当前时段没有可行方案"
        _log(origin, dest_node, depart_at, attempts, f"unreachable | {reason}")
        return RoutePlan(
            origin=origin,
            dest_node=dest_node,
            depart_at=depart_at,
            reachable=False,
            reason=reason,
            advice=_advice(),
            rejected=rejected,
        )

    total, gate, transfer, internal, legs = best
    _log(origin, dest_node, depart_at, attempts, f"reachable via gate {gate['id']}")
    return RoutePlan(
        origin=origin,
        dest_node=dest_node,
        depart_at=depart_at,
        reachable=True,
        total_min=total,
        duration_min=total,
        distance_m=transfer.distance_m + sum(leg.distance_m for leg in internal.legs),
        legs=legs,
        segments=_segments_from(internal),
        polyline=list(transfer.polyline) + _internal_polyline(graph, internal),
        internal_is_estimate=True,
        gates_checked=[str(gate["id"])],
        rejected=rejected,
    )