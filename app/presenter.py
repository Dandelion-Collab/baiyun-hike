"""展示层纯函数：把 Issue / RouteResult 翻译成人话。

这里不依赖任何界面框架，也不读文件，方便单测。
"""

from __future__ import annotations

from app.models import Issue, RouteResult

LEVEL_TITLES = {
    "error": "必须改",
    "warn": "建议调整",
    "info": "仅供参考",
}

RULE_TITLES = {
    "time_short": "时间不够",
    "time_tight": "时间安排偏紧",
    "closed_day": "当天闭馆",
    "transport_impossible": "交通衔接不了",
    "overload": "当天强度过大",
    "unverified": "地点未收录",
    "night_closed": "夜间已关闭",
    "entry_only_out": "夜间只出不进",
    "no_lighting": "夜间无照明",
}


def group_issues(issues: list[Issue]) -> dict[str, list[Issue]]:
    """按严重程度分组，组内保持输入顺序。"""

    groups: dict[str, list[Issue]] = {"error": [], "warn": [], "info": []}
    for issue in issues:
        groups[issue.level].append(issue)
    return groups


def summarize(issues: list[Issue]) -> str:
    """一句话概括，例如“共 10 条：3 条必须改，7 条建议调整”。"""

    if not issues:
        return "共 0 条，未发现问题"

    groups = group_issues(issues)
    parts: list[str] = []
    if groups["error"]:
        parts.append(f"{len(groups['error'])} 条必须改")
    if groups["warn"]:
        parts.append(f"{len(groups['warn'])} 条建议调整")
    if groups["info"]:
        parts.append(f"{len(groups['info'])} 条仅供参考")
    return f"共 {len(issues)} 条：" + "，".join(parts)


def format_issue(issue: Issue) -> dict[str, str]:
    """单条问题的人话视图；标题带地点名。"""

    prefix = RULE_TITLES.get(issue.rule, "需要留意")
    return {
        "title": f"{prefix}：{issue.item}",
        "detail": issue.evidence,
        "suggest": issue.suggest or "",
    }


def _label(node_id: str, names: dict[str, str] | None) -> str:
    if names and node_id in names:
        return names[node_id]
    return node_id


def format_route(
    route: RouteResult, names: dict[str, str] | None = None
) -> dict[str, object]:
    """路线的视图：可达给标题与分段，不可达给三段式提示。"""

    if route.reachable:
        legs = [
            f"{_label(leg.from_node, names)} → {_label(leg.to_node, names)}，"
            f"步行 {leg.walk_min} 分钟"
            for leg in route.legs
        ]
        headline = f"全程约 {route.total_min} 分钟，{route.arrive_at} 到达"
        notice = [f"注意：{warning}" for warning in route.warnings]
        return {"headline": headline, "legs": legs, "notice": notice}

    fallback = route.fallback
    farthest_path = fallback.farthest_path if fallback else []
    if farthest_path:
        farthest = " → ".join(_label(node_id, names) for node_id in farthest_path)
    else:
        farthest = "还没进入景区，没有可达点"
    blocked = route.blocked_at or route.reason or "当前时间窗内无法继续前进"
    suggestions = fallback.suggestions if fallback else []
    suggestion_text = "；".join(suggestions) if suggestions else "改时间、改入口或改目标后再试"

    return {
        "headline": "这条路线走不通",
        "legs": [],
        "notice": [
            f"最远可到：{farthest}",
            f"卡在哪：{blocked}",
            f"建议：{suggestion_text}",
        ],
    }