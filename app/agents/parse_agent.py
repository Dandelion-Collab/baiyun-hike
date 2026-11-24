"""解析 Agent：把自然语言行程包成 ParseMsg。"""

from __future__ import annotations

from app.agents.base import Agent, ParseMsg
from app.parser import parse_itinerary


class ParseAgent(Agent):
    name = "parse"

    def run(self, text: str) -> ParseMsg:
        return ParseMsg(itinerary=parse_itinerary(text))