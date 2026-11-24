"""解析模块测试：行程、日期、时刻、意图与 demo 整包解析。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.exceptions import ParseError
from app.parser import parse_intent, parse_itinerary

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_parse_standard_single_line_multiple_stops() -> None:
    itinerary = parse_itinerary("上午广州塔，中午陶陶居吃饭，下午沙面岛")

    assert [item.name for item in itinerary.items] == ["广州塔", "陶陶居", "沙面岛"]
    assert [item.period for item in itinerary.items] == ["morning", "noon", "afternoon"]
    assert itinerary.date == "2026-11-23"


def test_parse_only_date_returns_empty_items() -> None:
    itinerary = parse_itinerary("第一天")

    assert itinerary.items == []
    assert itinerary.date == "2026-11-23"


def test_parse_vague_period_keeps_duration_none() -> None:
    itinerary = parse_itinerary("下午 广州塔")

    assert len(itinerary.items) == 1
    assert itinerary.items[0].name == "广州塔"
    assert itinerary.items[0].period == "afternoon"
    assert itinerary.items[0].duration_min is None
    assert itinerary.items[0].time is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("上午 大概两小时 广州塔", 120),
        ("上午 广州塔，1.5 小时", 90),
        ("上午 广州塔 半天", 240),
        ("上午 广州塔 90 分钟", 90),
        ("上午 广州塔 半小时", 30),
    ],
)
def test_parse_approx_duration(text: str, expected: int) -> None:
    itinerary = parse_itinerary(text)

    assert itinerary.items[0].duration_min == expected


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_parse_empty_input_raises(text: str) -> None:
    with pytest.raises(ParseError):
        parse_itinerary(text)


def test_parse_unlisted_place_is_kept() -> None:
    itinerary = parse_itinerary("上午 火星基地 2 小时")

    assert itinerary.items[0].name == "火星基地"
    assert itinerary.items[0].duration_min == 120


def test_parse_multiline_input() -> None:
    text = "上午 广州塔，1.5 小时\n中午 陶陶居，1 小时\n晚上 珠江夜游天字码头，1.5 小时"
    itinerary = parse_itinerary(text)

    assert len(itinerary.items) == 3
    assert [item.period for item in itinerary.items] == ["morning", "noon", "evening"]


def test_parse_multi_day_switch() -> None:
    text = "第一天 上午 广州塔\n第二天 下午 沙面岛\n第三天 晚上 太古仓"
    itinerary = parse_itinerary(text)

    dates = [item.date for item in itinerary.items]
    assert dates == ["2026-11-23", "2026-11-24", "2026-11-25"]


def test_parse_unrecognizable_input_raises() -> None:
    with pytest.raises(ParseError):
        parse_itinerary("12345")


def test_parse_intent_normal() -> None:
    intent = parse_intent("今晚 10 点想夜爬白云山，一个人，体力一般")

    assert intent.when == "22:00"
    assert intent.party_size == 1
    assert intent.stamina == "medium"
    assert intent.target == "摩星岭"
    assert intent.alone is True


def test_parse_intent_missing_party_size_defaults_to_one() -> None:
    intent = parse_intent("今晚 10 点夜爬白云山")

    assert intent.party_size == 1
    assert intent.alone is None
    assert intent.stamina is None


def test_parse_intent_stamina_high_and_company() -> None:
    intent = parse_intent("晚上 9 点和朋友去摩星岭，体力很好")

    assert intent.when == "21:00"
    assert intent.stamina == "high"
    assert intent.target == "摩星岭"
    assert intent.alone is False


def test_parse_intent_clock_format() -> None:
    intent = parse_intent("23:30 夜爬白云山")

    assert intent.when == "23:30"


@pytest.mark.parametrize("text", ["今晚 25 点去白云山", "今晚 10:75 去白云山"])
def test_parse_intent_invalid_time_raises(text: str) -> None:
    with pytest.raises(ParseError):
        parse_intent(text)


def test_parse_today_resolves_to_base_date() -> None:
    itinerary = parse_itinerary("今天 上午 广州塔")

    assert itinerary.items[0].date == "2026-11-23"


def test_parse_tomorrow_resolves_to_next_day() -> None:
    itinerary = parse_itinerary("明天 上午 广州塔")

    assert itinerary.items[0].date == "2026-11-24"


def test_parse_this_week_wednesday() -> None:
    itinerary = parse_itinerary("周三 上午 广州塔")

    assert itinerary.items[0].date == "2026-11-25"


def test_parse_next_week_wednesday() -> None:
    itinerary = parse_itinerary("下周三 上午 广州塔")

    assert itinerary.items[0].date == "2026-12-02"


def test_parse_absolute_month_day() -> None:
    itinerary = parse_itinerary("12月2日 上午 广州塔")

    assert itinerary.items[0].date == "2026-12-02"


def test_parse_dash_date() -> None:
    itinerary = parse_itinerary("12-02 上午 广州塔")

    assert itinerary.items[0].date == "2026-12-02"


def test_parse_no_date_falls_back_to_base() -> None:
    itinerary = parse_itinerary("上午 广州塔")

    assert itinerary.items[0].date == "2026-11-23"


def test_parse_explicit_clock_into_time() -> None:
    itinerary = parse_itinerary("上午 9:00 广州塔，1.5 小时\n下午 17:10 沙面岛")

    assert itinerary.items[0].time == "09:00"
    assert itinerary.items[0].period == "morning"
    assert itinerary.items[1].time == "17:10"


def test_parse_evening_point_time_is_24h() -> None:
    itinerary = parse_itinerary("晚上 9 点半 珠江夜游天字码头")

    assert itinerary.items[0].time == "21:30"


def test_parse_demo_itinerary_has_three_days_and_enough_stops() -> None:
    text = (DATA_DIR / "demo_itinerary.txt").read_text(encoding="utf-8")
    itinerary = parse_itinerary(text)

    days = {item.date for item in itinerary.items}
    assert days == {"2026-11-23", "2026-11-24", "2026-11-25"}
    assert len(itinerary.items) >= 14
    for item in itinerary.items:
        assert item.time is None or re.fullmatch(r"\d{2}:\d{2}", item.time)

def test_parse_evening_midnight_marks_cross_day_as_none() -> None:
    itinerary = parse_itinerary("晚上12:00 到太古仓")

    assert itinerary.items[0].time is None

def test_parse_transport_mode_taxi() -> None:
    itinerary = parse_itinerary("上午 打车去白云山")

    item = itinerary.items[0]
    assert item.name == "白云山"
    assert item.transport_mode == "taxi"


def test_parse_transport_mode_metro() -> None:
    itinerary = parse_itinerary("晚上 坐地铁到体育西")

    item = itinerary.items[0]
    assert item.name == "体育西"
    assert item.transport_mode == "metro"