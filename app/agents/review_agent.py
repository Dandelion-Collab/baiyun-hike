"""复核 Agent：有模型时逐条判定；未配置时放行，且不算降级。"""

from __future__ import annotations

import json

from app.agents.base import Agent, IssuesMsg
from app.models import Issue

REVIEW_SYSTEM = (
    "你是行程体检复核员。判断这条结论是否有明确依据，"
    '只返回 JSON：{"is_valid": true} 或 {"is_valid": false}。'
)


def _parse_verdict(raw: str) -> bool:
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return "false" not in str(raw).lower()
    return bool(data.get("is_valid", True))


class ReviewAgent(Agent):
    name = "review"

    def run(self, msg: IssuesMsg) -> IssuesMsg:
        if self.llm_call is None:
            return IssuesMsg(issues=msg.issues, degraded=False)

        kept: list[Issue] = []
        for issue in msg.issues:
            if self._judge(issue):
                kept.append(issue)
        return IssuesMsg(issues=kept, degraded=False)

    def _judge(self, issue: Issue) -> bool:
        user = f"结论：{issue.rule} / {issue.item} / {issue.evidence}"
        return _parse_verdict(self.llm_call(REVIEW_SYSTEM, user))