"""多 Agent 编排：手写串行链路，一步一消息，失败重试两次后降级。

- run_check：解析 → 体检 → 复核
- run_route：意图 → 路线 → 安全提示
- degraded 只表示“本该执行的步骤失败了”；未配置模型不算降级。
- 任何一步重试两次仍失败即降级；夜间降级必须拒答，不许给路线。
"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field

from app.agents.base import (
    Agent,
    IssuesMsg,
    LLMCall,
    RouteMsg,
    log_call,
    summarize,
)
from app.agents.intent_agent import IntentAgent
from app.agents.parse_agent import ParseAgent
from app.agents.policy_agent import PolicyAgent
from app.agents.review_agent import ReviewAgent
from app.agents.route_agent import RouteAgent
from app.agents.safety_agent import SafetyAgent
from app.models import Issue, RouteResult
from app.rules import NIGHT_START_MIN

MAX_ATTEMPTS = 3


class CheckOutcome(BaseModel):
    issues: list[Issue] = Field(default_factory=list)
    degraded: bool = False
    session_ids: dict[str, str] = Field(default_factory=dict)
    message: str | None = None


class RouteOutcome(BaseModel):
    route: RouteResult
    safety: list[str] = Field(default_factory=list)
    degraded: bool = False
    session_ids: dict[str, str] = Field(default_factory=dict)
    message: str | None = None


def _night(depart_at: str) -> bool:
    hour, minute = depart_at.split(":")
    return int(hour) * 60 + int(minute) >= NIGHT_START_MIN


def _run_with_retry(agent: Agent, *args):
    """成功返回 (结果, None)；重试耗尽返回 (None, 最后一次异常)。每次调用都写日志。"""

    last_error: Exception | None = None
    for _ in range(MAX_ATTEMPTS):
        started = time.perf_counter()
        try:
            result = agent.run(*args)
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            log_call(agent.name, agent.session_id, elapsed_ms, summarize(args), f"error: {exc}")
            last_error = exc
            continue
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log_call(agent.name, agent.session_id, elapsed_ms, summarize(args), summarize(result))
        return result, None
    return None, last_error


def run_check(text: str, llm_call: LLMCall | None = None) -> CheckOutcome:
    parse_agent = ParseAgent()
    policy_agent = PolicyAgent()
    review_agent = ReviewAgent(llm_call)
    session_ids = {
        agent.name: agent.session_id for agent in (parse_agent, policy_agent, review_agent)
    }

    parse_msg, error = _run_with_retry(parse_agent, text)
    if parse_msg is None:
        return CheckOutcome(
            degraded=True, session_ids=session_ids, message=f"行程解析失败：{error}"
        )

    issues_msg, error = _run_with_retry(policy_agent, parse_msg)
    if issues_msg is None:
        return CheckOutcome(
            degraded=True, session_ids=session_ids, message=f"体检失败：{error}"
        )

    if llm_call is None:
        log_call(
            review_agent.name,
            review_agent.session_id,
            0,
            summarize(issues_msg),
            "review skipped: no llm configured",
        )
        return CheckOutcome(
            issues=issues_msg.issues,
            degraded=False,
            session_ids=session_ids,
        )

    reviewed, error = _run_with_retry(review_agent, issues_msg)
    if reviewed is None:
        return CheckOutcome(
            issues=issues_msg.issues,
            degraded=True,
            session_ids=session_ids,
            message=f"复核失败，结论未经模型确认：{error}",
        )

    return CheckOutcome(
        issues=reviewed.issues,
        degraded=False,
        session_ids=session_ids,
    )


def run_route(
    text: str,
    from_node: str,
    to_node: str,
    depart_at: str,
    llm_call: LLMCall | None = None,
    route_agent: Agent | None = None,
) -> RouteOutcome:
    intent_agent = IntentAgent()
    route_agent = route_agent or RouteAgent()
    safety_agent = SafetyAgent(llm_call)
    session_ids = {
        route_agent.name: route_agent.session_id,
        safety_agent.name: safety_agent.session_id,
    }

    intent = None
    degraded = False
    if text and text.strip():
        intent, intent_error = _run_with_retry(intent_agent, text)
        session_ids[intent_agent.name] = intent_agent.session_id
        if intent is None:
            degraded = True

    route_msg, route_error = _run_with_retry(
        route_agent, from_node, to_node, depart_at, intent
    )
    if route_msg is None:
        degraded = True
        route = RouteResult(
            reachable=False,
            reason="路线服务暂时不可用，无法确认安全路线",
            depart_at=depart_at,
            partial=True,
            blocked_at="路线服务暂时不可用",
        )
    else:
        route = route_msg.route

    if degraded and _night(depart_at):
        route = RouteResult(
            reachable=False,
            reason="夜间降级：复核环节失败，无法确认安全性，因此不提供路线",
            depart_at=depart_at,
            partial=True,
            blocked_at="夜间降级拒答",
        )

    safety_msg = _run_with_retry(safety_agent, RouteMsg(route=route), depart_at)[0]
    safety = safety_msg.notes if safety_msg is not None else [route.reason or "安全提示生成失败"]

    return RouteOutcome(
        route=route,
        safety=safety,
        degraded=degraded or safety_msg is None,
        session_ids=session_ids,
        message=None if route_error is None else f"路线服务降级：{route_error}",
    )