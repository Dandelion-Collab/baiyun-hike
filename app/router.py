"""能力 B：带时间窗的最短路。

状态为（节点，到达时刻分钟），用 heapq 按累计耗时扩展；
每段边要求整段覆盖（D1），到达节点后还要通过可进入判定（D3）。
图按 D9 无向；D10 的交通方式只用于城市接驳，不参与景区内部路由。

当前数据窗口均为单段连续区间，因此用“节点最早到达时刻”剪枝；
若以后引入多窗口（午休后重开），剪枝需改成把窗口序号纳入状态。
"""

from __future__ import annotations

import heapq
import itertools
import re
from collections import deque

from app.graph import Graph
from app.models import Fallback, Intent, Leg, RouteResult
from app.passability import (
    edge_passable,
    explain_why_closed,
    node_enterable,
    parse_windows,
)
from app.rules import ENTRY_CUTOFF_MIN, NIGHT_START_MIN

TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")
UNREACHABLE_RANK = 10**9


def _to_minutes(value: str) -> int:
    match = TIME_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"非法时刻：{value!r}")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError(f"非法时刻：{value!r}")
    return hour * 60 + minute


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _require_node(graph: Graph, node_id: str) -> dict[str, object]:
    try:
        return graph.node(node_id)
    except KeyError as exc:
        raise ValueError(f"不存在的节点 id：{node_id}") from exc


def _hops_to(graph: Graph, goal: str) -> dict[str, int]:
    hops = {goal: 0}
    queue = deque([goal])
    while queue:
        node = queue.popleft()
        for edge in graph.neighbors(node):
            nxt = str(edge["to"])
            if nxt not in hops:
                hops[nxt] = hops[node] + 1
                queue.append(nxt)
    return hops


def _path_to(parent: dict[str, str], node: str) -> list[str]:
    path = [node]
    while path[-1] in parent:
        path.append(parent[path[-1]])
    path.reverse()
    return path


def _edge_between(graph: Graph, start: str, goal: str) -> dict[str, object]:
    for edge in graph.neighbors(start):
        if edge["to"] == goal:
            return edge
    raise KeyError(f"{start} 与 {goal} 之间没有边")


def _warnings_for_path(graph: Graph, path: list[str]) -> list[str]:
    warnings: list[str] = []
    for start, goal in zip(path, path[1:]):
        edge = _edge_between(graph, start, goal)
        if edge.get("lighting") == "none":
            warnings.append(
                f"{graph.node(start)['name']}→{graph.node(goal)['name']} 无照明"
            )
    return warnings


def _unverified_for_path(graph: Graph, path: list[str]) -> bool:
    for node_id in path:
        if "待校验" in str(graph.node(node_id).get("note", "")):
            return True
    for start, goal in zip(path, path[1:]):
        edge = _edge_between(graph, start, goal)
        if "待校验" in str(edge.get("note", "")):
            return True
    return False


def _entry_reason(node: dict[str, object], departure: int) -> str:
    windows = parse_windows(str(node["open_windows"]))
    start, end = windows[0]
    cutoff = end - ENTRY_CUTOFF_MIN
    return (
        f"{node['name']} {_fmt(start)}-{_fmt(end)}，{_fmt(cutoff)} 前可进"
        f"（停止入园缓冲 {ENTRY_CUTOFF_MIN} 分钟）；你 {_fmt(departure)} 到达。"
        f"建议走 24 小时开放的南门/西门"
    )


def _suggestions(graph: Graph, start_node: dict[str, object], departure: int) -> list[str]:
    windows = parse_windows(str(start_node["open_windows"]))
    cutoff = windows[0][1] - ENTRY_CUTOFF_MIN
    suggestions = [f"改为 {_fmt(cutoff)} 前从 {start_node['name']} 入园"]
    for node in graph.nodes.values():
        if node.get("type") != "gate" or node["id"] == start_node["id"]:
            continue
        if node_enterable(node, departure):
            suggestions.append(f"或改从 {node['name']} 入园")
            break
    suggestions.append("或改去离你最近的可行景点")
    return suggestions


def _diagnose(graph: Graph, node: str, t: int, hops: dict[str, int]) -> str | None:
    best_message: str | None = None
    best_rank = UNREACHABLE_RANK
    for edge in graph.neighbors(node):
        nxt = str(edge["to"])
        t2 = t + int(edge["walk_min"])
        if not edge_passable(edge, t, t2):
            message = explain_why_closed(edge, t, t2)
        elif not node_enterable(graph.node(nxt), t2):
            nxt_node = graph.node(nxt)
            message = (
                f"{nxt_node['name']} {nxt_node['open_windows']} 已关闭，"
                f"你 {_fmt(t2)} 到达"
            )
        else:
            continue
        rank = hops.get(nxt, UNREACHABLE_RANK)
        if rank < best_rank:
            best_rank, best_message = rank, message
    return best_message


def _failure(
    graph: Graph,
    start_node: dict[str, object],
    goal_node: dict[str, object],
    departure: int,
    best: dict[str, int],
    parent: dict[str, str],
    hops: dict[str, int],
    reason: str,
    farthest: list[str],
) -> RouteResult:
    block = _diagnose(graph, farthest[-1], best[farthest[-1]], hops) if farthest else None
    final_reason = block or reason
    return RouteResult(
        reachable=False,
        path=[],
        legs=[],
        total_min=0,
        depart_at=_fmt(departure),
        reason=final_reason,
        fallback=Fallback(
            farthest_path=farthest,
            blocked_at=final_reason,
            suggestions=_suggestions(graph, start_node, departure),
        ),
        partial=True,
        blocked_at=final_reason,
        unverified=_unverified_for_path(graph, farthest) if farthest else False,
    )


def find_route(
    graph: Graph,
    start: str,
    goal: str,
    depart_at: str,
    intent: Intent | None = None,
) -> RouteResult:
    """返回可行路线；不可达时给出三件套：最远可达点 / 卡点 / 建议。"""

    departure = _to_minutes(depart_at)
    start_node = _require_node(graph, start)
    goal_node = _require_node(graph, goal)

    if start == goal:
        return RouteResult(
            reachable=True,
            path=[start],
            legs=[],
            total_min=0,
            depart_at=_fmt(departure),
            arrive_at=_fmt(departure),
            warnings=[],
            unverified=_unverified_for_path(graph, [start]),
        )

    if not node_enterable(start_node, departure):
        reason = _entry_reason(start_node, departure)
        return RouteResult(
            reachable=False,
            path=[],
            legs=[],
            total_min=0,
            depart_at=_fmt(departure),
            reason=reason,
            fallback=Fallback(
                farthest_path=[],
                blocked_at=reason,
                suggestions=_suggestions(graph, start_node, departure),
            ),
            partial=True,
            blocked_at=reason,
            unverified=_unverified_for_path(graph, [start]),
        )

    best: dict[str, int] = {start: departure}
    parent: dict[str, str] = {}
    counter = itertools.count()
    heap: list[tuple[int, int, int, str]] = []
    heapq.heappush(heap, (0, next(counter), departure, start))

    while heap:
        elapsed, _, t, node = heapq.heappop(heap)
        if t > best.get(node, -1):
            continue
        if node == goal:
            path = _path_to(parent, node)
            legs: list[Leg] = []
            for current, nxt in zip(path, path[1:]):
                edge = _edge_between(graph, current, nxt)
                legs.append(
                    Leg(
                        from_node=current,
                        to_node=nxt,
                        walk_min=int(edge["walk_min"]),
                        distance_m=int(edge["distance_m"]),
                        lighting=str(edge.get("lighting") or "") or None,
                        slope=str(edge.get("slope") or "") or None,
                    )
                )
            total_min = sum(leg.walk_min for leg in legs)
            return RouteResult(
                reachable=True,
                path=path,
                legs=legs,
                total_min=total_min,
                depart_at=_fmt(departure),
                arrive_at=_fmt(departure + total_min),
                warnings=_warnings_for_path(graph, path),
                unverified=_unverified_for_path(graph, path),
            )

        for edge in graph.neighbors(node):
            nxt = str(edge["to"])
            t2 = t + int(edge["walk_min"])
            if not edge_passable(edge, t, t2):
                continue
            if not node_enterable(graph.node(nxt), t2):
                continue
            if nxt in best and t2 >= best[nxt]:
                continue
            best[nxt] = t2
            parent[nxt] = node
            heapq.heappush(heap, (elapsed + int(edge["walk_min"]), next(counter), t2, nxt))

    hops = _hops_to(graph, goal)
    candidates = [node for node in best if node != goal]
    if not candidates:
        farthest = [start]
    else:
        farthest_node = min(candidates, key=lambda node: (hops.get(node, UNREACHABLE_RANK), -best[node]))
        farthest = _path_to(parent, farthest_node)
    return _failure(
        graph,
        start_node,
        goal_node,
        departure,
        best,
        parent,
        hops,
        f"{start_node['name']} 到 {goal_node['name']} 在 {_fmt(departure)} 后无可行路线",
        farthest,
    )