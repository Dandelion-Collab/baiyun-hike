"""自然语言解析：行程文本 → Itinerary，意图文本 → Intent。

口径：
- 相对日期以 rules.BASE_DATE（2026-11-23，周一）为基准：
  今天 / 明天 / 后天按自然日顺延；“周三”取本周三，“下周三”取下一自然周三；
  “12月2日”“12-02”按 2026 年解析；无日期信息时沿用基准日或上一行的日期。
- “第 N 天”优先于同行的星期词。
- 上午 / 中午 / 下午 / 晚上 → morning / noon / afternoon / evening。
- 显式时刻（9:00、17:10、9 点半）解析进 time，识别不到填 None，不猜；
  中午 / 下午 / 晚上且小时小于 12 时补 12 小时。
- 时长支持“1.5 小时”“大概两小时”“半天”“90 分钟”；识别不到填 None。
- 不查 POI 表，未收录地点原样保留；category 留空，由体检阶段按 POI 表填充。
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.exceptions import ParseError
from app.graph import load_graph
from app.models import Intent, Itinerary, ItineraryItem
from app.rules import BASE_DATE

DAY_RE = re.compile(r"第([一二两三四五六七八九十\d]+)天")
RELATIVE_DATE_RE = re.compile(r"(大后天|后天|明天|今天)")
WEEKDAY_RE = re.compile(r"(下|本)?(?:周|星期|礼拜)([一二三四五六日天])")
FULL_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
MONTH_DAY_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")
DASH_DATE_RE = re.compile(r"(?<![\d-])(\d{1,2})-(\d{1,2})(?![\d-])")
ALL_DATE_TOKENS_RE = re.compile(
    r"大后天|后天|明天|今天|"
    r"第[一二两三四五六七八九十\d]+天|"
    r"\d{4}-\d{1,2}-\d{1,2}|"
    r"\d{1,2}月\d{1,2}日|"
    r"(?:下|本)?(?:周|星期|礼拜)[一二三四五六日天]|"
    r"(?<![\d-])\d{1,2}-\d{1,2}(?![\d-])"
)
CLOCK_RE = re.compile(r"(\d{1,2})\s*[:：]\s*(\d{2})")
POINT_TIME_RE = re.compile(r"(\d{1,2})\s*点(半)?")
DURATION_RE = re.compile(
    r"(?:留|停留|游览|大概|大约|约)?\s*"
    r"(\d+(?:\.\d+)?|[一二两三四五六七八九十]+|半)\s*(?:个)?\s*(小时|钟头|分钟|分)"
)
HALF_DAY_RE = re.compile(r"半天")
PAREN_RE = re.compile(r"[（(][^）)]*[）)]")
PUNCT_RE = re.compile(r"[，,；;。、：:\s]+")

PERIOD_WORDS = {
    "上午": "morning",
    "早上": "morning",
    "早晨": "morning",
    "清晨": "morning",
    "中午": "noon",
    "正午": "noon",
    "下午": "afternoon",
    "午后": "afternoon",
    "晚上": "evening",
    "傍晚": "evening",
    "夜里": "evening",
    "夜间": "evening",
}
PERIOD_SPLIT_RE = re.compile("(" + "|".join(PERIOD_WORDS) + ")")

WEEKDAY_INDEX = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
RELATIVE_OFFSET = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}

CN_NUM = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "半": 0.5,
}

ACTION_WORDS = tuple(
    sorted(
        (
            "结束参观", "结束游览", "吃饭", "用餐", "逛街", "看展",
            "打卡", "参观", "游览", "游玩", "散步", "逛",
        ),
        key=len,
        reverse=True,
    )
)


def _day_number(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return CN_NUM.get(token) if token in CN_NUM else None


def _safe_date(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ParseError(f"非法日期：{year}-{month}-{day}") from exc


def _strip_date_tokens(line: str) -> str:
    return ALL_DATE_TOKENS_RE.sub(" ", line)


def _resolve_date(line: str) -> tuple[date | None, str]:
    day_match = DAY_RE.search(line)
    if day_match:
        number = _day_number(day_match.group(1))
        if number is None or number < 1:
            raise ParseError(f"无法识别的天数：{day_match.group(0)}")
        return BASE_DATE + timedelta(days=number - 1), _strip_date_tokens(line)

    relative = RELATIVE_DATE_RE.search(line)
    if relative:
        offset = RELATIVE_OFFSET[relative.group(1)]
        return BASE_DATE + timedelta(days=offset), _strip_date_tokens(line)

    weekday = WEEKDAY_RE.search(line)
    if weekday:
        target = BASE_DATE + timedelta(days=WEEKDAY_INDEX[weekday.group(2)])
        if weekday.group(1) == "下":
            target += timedelta(days=7)
        return target, _strip_date_tokens(line)

    full = FULL_DATE_RE.search(line)
    if full:
        resolved = _safe_date(int(full.group(1)), int(full.group(2)), int(full.group(3)))
        return resolved, _strip_date_tokens(line)

    month_day = MONTH_DAY_RE.search(line)
    if month_day:
        resolved = _safe_date(2026, int(month_day.group(1)), int(month_day.group(2)))
        return resolved, _strip_date_tokens(line)

    dash = DASH_DATE_RE.search(line)
    if dash:
        resolved = _safe_date(2026, int(dash.group(1)), int(dash.group(2)))
        return resolved, _strip_date_tokens(line)

    return None, line


def _duration_minutes(match: re.Match[str]) -> int:
    value, unit = match.group(1), match.group(2)
    if value == "半":
        amount = 0.5
    elif value.replace(".", "", 1).isdigit():
        amount = float(value)
    else:
        amount = CN_NUM[value]
    minutes = amount * 60 if unit in ("小时", "钟头") else amount
    return int(round(minutes))


def _extract_duration(text: str) -> tuple[int | None, str]:
    half = HALF_DAY_RE.search(text)
    if half:
        return 240, text[: half.start()] + " " + text[half.end():]
    match = DURATION_RE.search(text)
    if not match:
        return None, text
    return _duration_minutes(match), text[: match.start()] + " " + text[match.end():]


def _format_time(hour: int, minute: int, period: str | None) -> str | None:
    if hour > 23 or minute > 59:
        return None
    # “晚上 12:00”指次日 00:00；按 D2 不支持跨日，填 None 而不是 12:00。
    if period == "evening" and hour == 12:
        return None
    if hour < 12 and period in ("noon", "afternoon", "evening"):
        hour += 12
    return f"{hour:02d}:{minute:02d}"


def _extract_time(text: str, period: str | None) -> tuple[str | None, str]:
    clock = CLOCK_RE.search(text)
    if clock:
        hour, minute = int(clock.group(1)), int(clock.group(2))
        remaining = text[: clock.start()] + " " + text[clock.end():]
        return _format_time(hour, minute, period), remaining

    point = POINT_TIME_RE.search(text)
    if point:
        hour = int(point.group(1))
        minute = 30 if point.group(2) else 0
        remaining = text[: point.start()] + " " + text[point.end():]
        return _format_time(hour, minute, period), remaining

    return None, text


def _clean_name(text: str) -> str:
    text = PAREN_RE.sub(" ", text)
    text = PUNCT_RE.sub(" ", text).strip()
    for word in ACTION_WORDS:
        if text.startswith(word):
            text = text[len(word):].strip()
        if text.endswith(word):
            text = text[: -len(word)].strip()
    return text.strip(" -—·、，,；;。.")


def _usable_name(name: str) -> bool:
    return len(name) >= 2 and bool(re.search(r"[\u4e00-\u9fffA-Za-z]", name))


def _segments(line: str) -> list[tuple[str | None, str]]:
    parts = PERIOD_SPLIT_RE.split(line)
    if len(parts) == 1:
        return [(None, parts[0])]
    segments: list[tuple[str | None, str]] = []
    head = parts[0].strip()
    if head:
        segments.append((None, head))
    for index in range(1, len(parts), 2):
        period = PERIOD_WORDS[parts[index]]
        body = parts[index + 1] if index + 1 < len(parts) else ""
        segments.append((period, body))
    return segments


def _parse_line(line: str, current_date: date) -> tuple[list[ItineraryItem], date, bool]:
    date_seen = False
    resolved, line = _resolve_date(line)
    if resolved is not None:
        current_date = resolved
        date_seen = True

    items: list[ItineraryItem] = []
    for period, body in _segments(line):
        if not body.strip():
            continue
        duration, body = _extract_duration(body)
        time_text, body = _extract_time(body, period)
        name = _clean_name(body)
        if not _usable_name(name):
            continue
        items.append(
            ItineraryItem(
                name=name,
                period=period,
                time=time_text,
                duration_min=duration,
                date=current_date.isoformat(),
            )
        )
    return items, current_date, date_seen


def parse_itinerary(text: str) -> Itinerary:
    """把自然语言行程解析成 Itinerary；完全无法识别时抛 ParseError。"""

    if not text or not text.strip():
        raise ParseError("行程文本为空")

    current_date = BASE_DATE
    first_date: date | None = None
    date_seen = False
    items: list[ItineraryItem] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line_items, current_date, line_date_seen = _parse_line(line, current_date)
        if line_date_seen and first_date is None:
            first_date = current_date
        date_seen = date_seen or line_date_seen
        items.extend(line_items)

    if not items and not date_seen:
        raise ParseError("未能从文本中识别出任何行程站点")

    items = [_attach_transport(item) for item in items]
    return Itinerary(date=(first_date or BASE_DATE).isoformat(), items=items)


def _attach_transport(item: ItineraryItem) -> ItineraryItem:
    """把站名里的交通方式归一成字段；识别不到时原样返回。"""

    mode, clean_name = split_transport(item.name)
    if mode is None or not clean_name or clean_name == item.name:
        return item
    return item.model_copy(update={"name": clean_name, "transport_mode": mode})


def _parse_when(text: str) -> str:
    clock = CLOCK_RE.search(text)
    if clock:
        hour, minute = int(clock.group(1)), int(clock.group(2))
        if hour > 23 or minute > 59:
            raise ParseError(f"非法时间：{clock.group(0)}")
        return f"{hour:02d}:{minute:02d}"

    point = POINT_TIME_RE.search(text)
    if point:
        hour = int(point.group(1))
        if hour > 23:
            raise ParseError(f"非法时间：{point.group(0)}")
        if hour < 12 and any(word in text for word in ("晚", "夜")):
            hour += 12
        elif hour < 12 and any(word in text for word in ("下午", "午后", "傍晚")):
            hour += 12

        minute = 30 if point.group(2) else 0
        return f"{hour:02d}:{minute:02d}"

    if "点" in text:
        raise ParseError("时间表述无法识别，请给出 HH:MM 或“N 点”")
    raise ParseError("未识别到出发时间")


def _parse_target(text: str) -> str:
    best_position: int | None = None
    best_name: str | None = None
    for node in load_graph().nodes.values():
        name = node["name"]
        if name.endswith("门"):
            continue
        position = text.find(name)
        if position >= 0 and (best_position is None or position < best_position):
            best_position, best_name = position, name
    return best_name or "摩星岭"


def _parse_party_size(text: str) -> int | None:
    if re.search(r"(两个人|俩人|二人|2\s*个人)", text):
        return 2
    if re.search(r"(一个人|独自|单人|自己一个人|自己)", text):
        return 1
    if re.search(r"(我们|几个人|结伴|朋友|一起|多人|团队)", text):
        return None
    return 1


def _parse_stamina(text: str) -> str | None:
    if re.search(r"(体力\s*(很|非常|特别)?\s*(好|强|不错|棒)|很强|很好|体力好)", text):
        return "high"
    if re.search(r"(体力\s*(较弱|偏弱|弱|差)|较弱|偏弱|体力差|一般偏弱)", text):
        return "low"
    if re.search(r"(体力\s*一般|一般)", text):
        return "medium"
    return None


def _parse_alone(text: str) -> bool | None:
    if re.search(r"(一个人|独自|单人|自己一个人|自己)", text):
        return True
    if re.search(r"(我们|一起|结伴|朋友|多人|团队)", text):
        return False
    return None


def parse_intent(text: str) -> Intent:
    """把自然语言意图解析成 Intent；时间缺失或非法时抛 ParseError。"""

    if not text or not text.strip():
        raise ParseError("意图文本为空")

    return Intent(
        when=_parse_when(text),
        party_size=_parse_party_size(text),
        stamina=_parse_stamina(text),
        target=_parse_target(text),
        alone=_parse_alone(text),
    )

TRANSPORT_PATTERNS = (
    ("taxi", re.compile(r"(打车|滴滴|出租车|的士|打的)")),
    ("metro", re.compile(r"(坐地铁|乘地铁|地铁(?!站)|轨道交通)")),
    ("bike", re.compile(r"(骑行|骑车|单车|自行车)")),
    ("walk", re.compile(r"(步行(?!街)|走路|徒步)")),
)


def split_transport(text: str) -> tuple[str | None, str]:
    """识别地名里的交通方式，返回 (mode, 去掉方式词后的地名)。

    mode 取 walk / bike / metro / taxi；识别不到返回 (None, 原文)。
    """

    for mode, pattern in TRANSPORT_PATTERNS:
        if pattern.search(text):
            cleaned = pattern.sub(" ", text).strip()
            cleaned = re.sub(r"^[去到往]\s*", "", cleaned).strip()
            return mode, cleaned or text
    return None, text