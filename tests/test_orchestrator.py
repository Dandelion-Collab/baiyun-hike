"""多 Agent 编排测试：复核否决、重试降级、夜间可达与日志。"""

from __future__ import annotations

from pathlib import Path

from app.agents.base import Agent
from app.orchestrator import run_check, run_route

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "logs" / "agent.log"


class _FailingAgent(Agent):
    name = "route"

    def run(self, *args, **kwargs):
        raise RuntimeError("路由服务不可用")


def _reject_all(system: str, user: str) -> str:
    return '{"is_valid": false}'


def _accept_all(system: str, user: str) -> str:
    return '{"is_valid": true}'


def _raise_all(system: str, user: str) -> str:
    raise RuntimeError("模型额度不可用")


def test_reasonable_itinerary_has_no_issues() -> None:
    text = "上午 北京路步行街，1.5 小时\n中午 银记肠粉北京路，30 分钟"

    outcome = run_check(text)

    assert outcome.issues == []
    assert outcome.degraded is False


def test_demo_unconfigured_has_ten_issues_and_not_degraded() -> None:
    text = (ROOT / "data" / "demo_itinerary.txt").read_text(encoding="utf-8")

    outcome = run_check(text)

    assert len(outcome.issues) == 10
    assert outcome.degraded is False


def test_monday_museum_reports_closed_day() -> None:
    outcome = run_check("第一天 上午 广东省博物馆")

    assert any(issue.rule == "closed_day" for issue in outcome.issues)
    assert outcome.degraded is False


def test_review_can_reject_issue() -> None:
    outcome = run_check("第一天 上午 广东省博物馆", llm_call=_reject_all)

    assert outcome.issues == []
    assert outcome.degraded is False


def test_review_accepts_issue_when_valid() -> None:
    outcome = run_check("第一天 上午 广东省博物馆", llm_call=_accept_all)

    assert any(issue.rule == "closed_day" for issue in outcome.issues)
    assert outcome.degraded is False


def test_1900_route_reaches_summit_with_safety_notes() -> None:
    outcome = run_route("今晚 19:00 夜爬白云山", "N01", "N10", "19:00")

    assert "N10" in outcome.route.path
    assert outcome.safety


def test_2200_route_is_reachable() -> None:
    outcome = run_route("今晚 22:00 夜爬白云山", "N01", "N10", "22:00")

    assert outcome.route.reachable is True
    assert "N10" in outcome.route.path
    assert outcome.route.total_min == 113
    assert outcome.degraded is False


def test_configured_llm_failure_degrades_and_night_refuses() -> None:
    check_outcome = run_check("第一天 上午 广东省博物馆", llm_call=_raise_all)
    assert check_outcome.degraded is True
    assert check_outcome.issues

    route_outcome = run_route(
        "今晚 22:00 夜爬白云山",
        "N01",
        "N10",
        "22:00",
        llm_call=_raise_all,
        route_agent=_FailingAgent(),
    )
    assert route_outcome.degraded is True
    assert route_outcome.route.reachable is False
    assert "复核环节失败" in (route_outcome.route.reason or "")


def test_same_input_is_stable() -> None:
    first = run_check("第一天 上午 广东省博物馆")
    second = run_check("第一天 上午 广东省博物馆")

    assert [issue.model_dump() for issue in first.issues] == [
        issue.model_dump() for issue in second.issues
    ]
    assert first.degraded == second.degraded


def test_agent_session_ids_are_unique() -> None:
    outcome = run_check("第一天 上午 广东省博物馆")

    values = list(outcome.session_ids.values())
    assert len(values) == len(set(values))
    assert len(values) >= 3


def test_log_contains_session_and_elapsed() -> None:
    outcome = run_check("第一天 上午 广东省博物馆")
    text = LOG_PATH.read_text(encoding="utf-8")

    assert any(session_id in text for session_id in outcome.session_ids.values())
    assert "ms" in text