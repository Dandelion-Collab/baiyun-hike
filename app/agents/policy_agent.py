"""体检 Agent：包装 checker.check，不调模型。"""

from __future__ import annotations

from app.agents.base import Agent, IssuesMsg, ParseMsg
from app.checker import check


class PolicyAgent(Agent):
    name = "policy"

    def run(self, msg: ParseMsg) -> IssuesMsg:
        return IssuesMsg(issues=check(msg.itinerary))