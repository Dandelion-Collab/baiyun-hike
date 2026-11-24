"""意图 Agent：规则实现，复用 parser.parse_intent。"""

from __future__ import annotations

from app.agents.base import Agent
from app.models import Intent
from app.parser import parse_intent


class IntentAgent(Agent):
    name = "intent"

    def run(self, text: str) -> Intent:
        return parse_intent(text)