"""路线 Agent：包装 router.find_route，不调模型。"""

from __future__ import annotations

from app.agents.base import Agent, RouteMsg
from app.graph import load_graph
from app.models import Intent
from app.router import find_route


class RouteAgent(Agent):
    name = "route"

    def run(
        self,
        start: str,
        goal: str,
        depart_at: str,
        intent: Intent | None = None,
    ) -> RouteMsg:
        graph = load_graph()
        return RouteMsg(route=find_route(graph, start, goal, depart_at, intent))