"""能力 A：行程体检（R1–R6）。

判定口径：
- R1 时间不足：ratio = duration_min / POI 建议时长；
  ratio < TIME_SHORT_RATIO → error/time_short；
  TIME_SHORT_RATIO <= ratio < TIME_TIGHT_RATIO → warn/time_tight；否则不报。
- R2 闭馆日：item.date 的星期命中 POI.closed_weekday。
- R3 交通不可能：同一天相邻两站都有 time、都有坐标时，
  交通方式取 item.transport_mode，未声明则按距离默认（步行 / 骑行 / 地铁）；
  可用间隔 = next.time - (prev.time + prev.duration_min)，间隔不足即 error。
- R4 强度超载：同一天 duration_min 合计 > MAX_DAY_MIN。
- R5 未收录：POI 表查不到，level=info，evidence 固定为“未收录，未校验”。
- R6 夜间：closed 且到达 ≥ NIGHT_START_MIN；当天首站 gate_only_out 且到达 ≥ NIGHT_START_MIN；
  period=evening 且 lighting=none。

缺 time、缺坐标、跨天的站点一律跳过 R3，不猜、不误报；
缺 duration_min 时按 0 计，并在 evidence 注明“按上一站结束时刻估算”。
"""

from __future__ import annotations

import math
from datetime import date as Date

from app.models import Issue, Itinerary, ItineraryItem
from app.poi import find_poi, load_poi
from app.rules import (
    BIKE_MAX_M,
    BIKE_OVERHEAD_MIN,
    BIKE_SPEED_M_PER_MIN,
    MAX_DAY_MIN,
    METRO_BASE_MIN,
    METRO_MIN_PER_KM,
    MIN_TRANSFER_MIN,
    NIGHT_START_MIN,
    TAXI_OVERHEAD_MIN,
    TAXI_SPEED_M_PER_MIN,
    TIME_SHORT_RATIO,
    TIME_TIGHT_RATIO,
    WALK_MAX_M,
    WALK_SPEED_M_PER_MIN,
)

EARTH_RADIUS_KM = 6371.0
METERS_PER_KM = 1000
MINUTES_PER_HOUR = 60
LEVEL_ORDER = {"error": 0, "warn": 1, "info": 2}
WEEKDAY_LABELS = ("一", "二", "三", "四", "五", "六", "日")
TRANSPORT_LABELS = {"walk": "步行", "bike": "骑行", "metro": "地铁", "taxi": "打车"}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """两点的球面直线距离（公里）。"""

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def _issue(level: str, rule: str, item: str, evidence: str) -> Issue:
    if not evidence or not evidence.strip():
        raise ValueError("Issue 缺少 evidence，无依据不得输出")
    return Issue(level=level, rule=rule, item=item, evidence=evidence)


def _to_minutes(value: str | None) -> int | None:
    if not value:
        return None
    parts = value.split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if hour > 23 or minute > 59:
        return None
    return hour * MINUTES_PER_HOUR + minute


def _format_minutes(total: int) -> str:
    return f"{total // MINUTES_PER_HOUR:02d}:{total % MINUTES_PER_HOUR:02d}"


def _poi_int(poi: dict[str, str], key: str) -> int | None:
    raw = (poi.get(key) or "").strip()
    try:
        return int(raw)
    except ValueError:
        return None


def _poi_float(poi: dict[str, str], key: str) -> float | None:
    raw = (poi.get(key) or "").strip()
    try:
        return float(raw)
    except ValueError:
        return None


def _weekday(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return Date.fromisoformat(value).isoweekday()
    except ValueError:
        return None


def _default_mode(distance_m: float) -> str:
    if distance_m <= WALK_MAX_M:
        return "walk"
    if distance_m <= BIKE_MAX_M:
        return "bike"
    return "metro"


def _transport_need(mode: str, distance_m: float) -> float:
    if mode == "bike":
        return distance_m / BIKE_SPEED_M_PER_MIN + BIKE_OVERHEAD_MIN
    if mode == "metro":
        return METRO_BASE_MIN + (distance_m / METERS_PER_KM) * METRO_MIN_PER_KM
    if mode == "taxi":
        return TAXI_OVERHEAD_MIN + distance_m / TAXI_SPEED_M_PER_MIN
    return distance_m / WALK_SPEED_M_PER_MIN


def _transport_detail(mode: str) -> str:
    if mode == "bike":
        return f"（含取还车 {BIKE_OVERHEAD_MIN} 分钟）"
    if mode == "metro":
        return "（含进出站候车）"
    if mode == "taxi":
        return "（含等车）"
    return ""


def _check_item(item: ItineraryItem, poi: dict[str, str], is_first_of_day: bool) -> list[Issue]:
    issues: list[Issue] = []

    advised = _poi_int(poi, "duration_min")
    if item.duration_min is not None and advised:
        ratio = item.duration_min / advised
        if ratio < TIME_SHORT_RATIO:
            issues.append(
                _issue(
                    "error",
                    "time_short",
                    item.name,
                    f"建议 {advised} 分钟，你留了 {item.duration_min} 分钟",
                )
            )
        elif ratio < TIME_TIGHT_RATIO:
            issues.append(
                _issue(
                    "warn",
                    "time_tight",
                    item.name,
                    f"建议 {advised} 分钟，你留了 {item.duration_min} 分钟（偏紧）",
                )
            )

    weekday = _weekday(item.date)
    closed_weekday = _poi_int(poi, "closed_weekday")
    if weekday is not None and closed_weekday == weekday:
        issues.append(
            _issue(
                "error",
                "closed_day",
                item.name,
                f"{item.date}（周{WEEKDAY_LABELS[weekday - 1]}）命中闭馆日",
            )
        )

    arrival = _to_minutes(item.time)
    if arrival is not None:
        if poi.get("night_access") == "closed" and arrival >= NIGHT_START_MIN:
            issues.append(
                _issue(
                    "error",
                    "night_closed",
                    item.name,
                    f"{item.time} 到达，夜间关闭（{_format_minutes(NIGHT_START_MIN)} 起）",
                )
            )
        if (
            is_first_of_day
            and poi.get("night_access") == "gate_only_out"
            and arrival >= NIGHT_START_MIN
        ):
            issues.append(
                _issue(
                    "warn",
                    "entry_only_out",
                    item.name,
                    f"当天首站 {item.time} 到达，只出不进（{_format_minutes(NIGHT_START_MIN)} 起）",
                )
            )

    if item.period == "evening" and poi.get("lighting") == "none":
        issues.append(_issue("warn", "no_lighting", item.name, "夜间无照明"))

    return issues


def _check_transport(
    items: list[ItineraryItem], pois: list[dict[str, str] | None]
) -> list[Issue]:
    issues: list[Issue] = []
    for index in range(1, len(items)):
        prev, curr = items[index - 1], items[index]
        if prev.date != curr.date:
            continue
        prev_time, curr_time = _to_minutes(prev.time), _to_minutes(curr.time)
        if prev_time is None or curr_time is None:
            continue
        prev_poi, curr_poi = pois[index - 1], pois[index]
        if prev_poi is None or curr_poi is None:
            continue
        lat1, lng1 = _poi_float(prev_poi, "lat"), _poi_float(prev_poi, "lng")
        lat2, lng2 = _poi_float(curr_poi, "lat"), _poi_float(curr_poi, "lng")
        if None in (lat1, lng1, lat2, lng2):
            continue

        distance_m = haversine_km(lat1, lng1, lat2, lng2) * METERS_PER_KM
        mode = curr.transport_mode or _default_mode(distance_m)
        need = _transport_need(mode, distance_m)
        prev_duration = prev.duration_min or 0
        interval = curr_time - (prev_time + prev_duration)
        if interval < need:
            note = "" if prev.duration_min is not None else "（按上一站结束时刻估算）"
            issues.append(
                _issue(
                    "error",
                    "transport_impossible",
                    curr.name,
                    f"{TRANSPORT_LABELS[mode]}约 {round(need)} 分钟{_transport_detail(mode)}，"
                    f"你只有 {interval} 分钟{note}",
                )
            )
    return issues


def _check_overload(items: list[ItineraryItem]) -> list[Issue]:
    totals: dict[str | None, int] = {}
    for item in items:
        if item.duration_min is None:
            continue
        totals[item.date] = totals.get(item.date, 0) + item.duration_min
    issues: list[Issue] = []
    for day, total in totals.items():
        if total > MAX_DAY_MIN:
            issues.append(
                _issue(
                    "warn",
                    "overload",
                    day or "未标注日期",
                    f"当天合计 {total} 分钟，上限 {MAX_DAY_MIN} 分钟",
                )
            )
    return issues


def _finalize(issues: list[Issue]) -> list[Issue]:
    unique: list[Issue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        key = (issue.level, issue.rule, issue.item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return sorted(unique, key=lambda issue: LEVEL_ORDER[issue.level])


def check(
    itinerary: Itinerary, poi_rows: list[dict[str, str]] | None = None
) -> list[Issue]:
    """体检入口。poi_rows 仅用于测试注入，默认读 data/poi.csv。"""

    rows = poi_rows if poi_rows is not None else load_poi()
    items = itinerary.items
    pois = [find_poi(item.name, rows) for item in items]

    first_index: dict[str | None, int] = {}
    for index, item in enumerate(items):
        first_index.setdefault(item.date, index)

    issues: list[Issue] = []
    for index, (item, poi) in enumerate(zip(items, pois)):
        if poi is None:
            issues.append(_issue("info", "unverified", item.name, "未收录，未校验"))
            continue
        issues.extend(_check_item(item, poi, first_index.get(item.date) == index))

    issues.extend(_check_transport(items, pois))
    issues.extend(_check_overload(items))
    return _finalize(issues)