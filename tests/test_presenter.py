"""展示层纯函数测试。"""

from __future__ import annotations

import ast
from pathlib import Path

from app.models import Fallback, Issue, Leg, RouteResult
from app.presenter import format_issue, format_route, group_issues, summarize


def _issue(level: str, rule: str, item: str, *, suggest: str | None = None) -> Issue:
    return Issue(level=level, rule=rule, item=item, evidence="这是一条依据", suggest=suggest)


def test_group_issues_groups_and_keeps_order() -> None:
    issues = [
        _issue("warn", "time_tight", "广州塔"),
        _issue("error", "closed_day", "广东省博物馆"),
        _issue("warn", "overload", "2026-11-24"),
        _issue("info", "unverified", "火星基地"),
    ]

    groups = group_issues(issues)

    assert [issue.item for issue in groups["error"]] == ["广东省博物馆"]
    assert [issue.item for issue in groups["warn"]] == ["广州塔", "2026-11-24"]
    assert [issue.item for issue in groups["info"]] == ["火星基地"]


def test_summarize_counts_match() -> None:
    issues = [
        _issue("error", "closed_day", f"地点{i}") for i in range(3)
    ] + [
        _issue("warn", "time_tight", f"地点{i}") for i in range(7)
    ]

    assert summarize(issues) == "共 10 条：3 条必须改，7 条建议调整"


def test_format_issue_title_contains_place() -> None:
    view = format_issue(
        _issue("warn", "time_tight", "广州塔", suggest="至少留 120 分钟")
    )

    assert "广州塔" in view["title"]
    assert "time_tight" not in view["title"]
    assert "偏紧" in view["title"]
    assert view["detail"] == "这是一条依据"
    assert view["suggest"] == "至少留 120 分钟"


def test_format_route_reachable_headline_has_minutes() -> None:
    route = RouteResult(
        reachable=True,
        path=["N01", "N06"],
        legs=[Leg(from_node="N01", to_node="N06", walk_min=12, distance_m=600)],
        total_min=90,
        depart_at="19:00",
        arrive_at="20:30",
    )

    view = format_route(route, {"N01": "白云山南门", "N06": "能仁寺"})

    assert "90" in str(view["headline"])
    assert "20:30" in str(view["headline"])
    assert "步行 12 分钟" in str(view["legs"][0])


def test_format_route_unreachable_notice_has_three_parts() -> None:
    route = RouteResult(
        reachable=False,
        reason="该路段 21:30 关闭，你 22:15 出发 22:30 到达",
        partial=True,
        fallback=Fallback(
            farthest_path=["N01", "N09"],
            blocked_at="该路段 21:30 关闭，你 22:15 出发 22:30 到达",
            suggestions=["明早 6:00 后再来"],
        ),
    )

    view = format_route(route, {"N01": "白云山南门", "N09": "山顶广场"})

    text = "".join(view["notice"])
    assert "最远" in text
    assert "卡在" in text
    assert "建议" in text
    assert "山顶广场" in text


def test_presenter_does_not_import_streamlit() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "app" / "presenter.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert "streamlit" not in imported

    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name):
                called.add(target.id)
            elif isinstance(target, ast.Attribute):
                called.add(target.attr)

    assert "open" not in called
    assert "read_text" not in called