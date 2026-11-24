"""安全提示 Agent：规则实现，不调模型。"""

from __future__ import annotations

from app.agents.base import Agent, RouteMsg, SafetyMsg
from app.graph import load_graph
from app.rules import NIGHT_START_MIN


def _minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


class SafetyAgent(Agent):
    name = "safety"

    def run(self, msg: RouteMsg, depart_at: str) -> SafetyMsg:
        graph = load_graph()

        def label(node_id: str) -> str:
            return str(graph.node(node_id)["name"])

        route = msg.route
        notes: list[str] = []

        if not route.reachable:
            notes.append(route.reason or "当前时段无法确认可行路线")

        for leg in route.legs:
            if leg.lighting == "none":
                notes.append(
                    f"{label(leg.from_node)}→{label(leg.to_node)} 无照明，夜间不建议单独通过"
                )
            if leg.slope == "steep":
                notes.append(f"{label(leg.from_node)}→{label(leg.to_node)} 坡道较陡，注意体力")

        if _minutes(depart_at) >= NIGHT_START_MIN:
            notes.append("夜间出发，请结伴并携带照明")

        if route.reachable and route.path:
            notes.append(f"如需下撤，可沿原路返回 {label(route.path[0])}")

        return SafetyMsg(notes=notes)