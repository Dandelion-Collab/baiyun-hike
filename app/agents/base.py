"""Agent 基础设施：消息模型、基类、会话号与调用日志。

模型调用做成可注入接口：默认没有实现，各 Agent 走确定性回退并标 degraded。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from app.models import Issue, Itinerary, RouteResult

LLMCall = Callable[[str, str], str]
default_llm: LLMCall | None = None

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "agent.log"


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


class ParseMsg(BaseModel):
    itinerary: Itinerary
    degraded: bool = False


class IssuesMsg(BaseModel):
    issues: list[Issue] = Field(default_factory=list)
    degraded: bool = False


class RouteMsg(BaseModel):
    route: RouteResult
    degraded: bool = False


class VerdictMsg(BaseModel):
    issue_rule: str
    issue_item: str
    is_valid: bool
    note: str = ""


class SafetyMsg(BaseModel):
    notes: list[str] = Field(default_factory=list)
    degraded: bool = False


def summarize(value: object, limit: int = 140) -> str:
    text = value if isinstance(value, str) else str(value)
    return " ".join(text.split())[:limit]


def log_call(
    agent_name: str,
    session_id: str,
    elapsed_ms: int,
    input_summary: str,
    output_summary: str,
) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = (
        f"{datetime.now().isoformat(timespec='seconds')} | {agent_name} | "
        f"{session_id} | {elapsed_ms}ms | in: {input_summary} | out: {output_summary}\n"
    )
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line)


class Agent:
    name = "agent"

    def __init__(self, llm_call: LLMCall | None = default_llm):
        self.llm_call = llm_call
        self.session_id = new_session_id()

    def run(self, *args, **kwargs):
        raise NotImplementedError("待实现：子类实现 run")