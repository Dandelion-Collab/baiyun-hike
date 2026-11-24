"""体检引擎测试：R1–R6、交通方式选择、去重、排序与 demo 回归。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.checker import _issue, check
from app.models import Itinerary, ItineraryItem
from app.parser import parse_itinerary
from app.poi import load_poi

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _item(
    name: str,
    *,
    time: str | None = None,
    duration: int | None = None,
    period: str | None = None,
    transport_mode: str | None = None,
    date: str = "2026-11-24",
) -> ItineraryItem:
    return ItineraryItem(
        name=name,
        time=time,
        duration_min=duration,
        period=period,
        transport_mode=transport_mode,
        date=date,
    )


def _itinerary(*items: ItineraryItem) -> Itinerary:
    return Itinerary(date=items[0].date if items else None, items=list(items))


def _rules(issues) -> list[str]:
    return [issue.rule for issue in issues]


def test_r1_time_short() -> None:
    issues = check(_itinerary(_item("广州塔", duration=60)))

    assert _rules(issues) == ["time_short"]
    assert issues[0].level == "error"
    assert "120" in issues[0].evidence
    assert "60" in issues[0].evidence


def test_r1_time_tight_is_warn() -> None:
    issues = check(_itinerary(_item("广州塔", duration=90)))

    assert _rules(issues) == ["time_tight"]
    assert issues[0].level == "warn"


def test_r2_closed_day() -> None:
    issues = check(_itinerary(_item("广东省博物馆", duration=150, date="2026-11-23")))

    assert _rules(issues) == ["closed_day"]
    assert issues[0].level == "error"


def test_r3_transport_impossible() -> None:
    issues = check(
        _itinerary(
            _item("广州塔", time="09:00", duration=120, period="morning"),
            _item("黄埔古港", time="11:10", duration=90, period="morning"),
        )
    )

    assert _rules(issues) == ["transport_impossible"]
    assert issues[0].level == "error"


def test_r3_short_distance_still_impossible_by_time() -> None:
    issues = check(
        _itinerary(
            _item("陈家祠", time="17:00", duration=None),
            _item("北京路步行街", time="17:10", duration=None),
        )
    )

    assert _rules(issues) == ["transport_impossible"]
    assert "按上一站结束时刻估算" in issues[0].evidence


def test_r3_long_distance_by_time() -> None:
    issues = check(
        _itinerary(
            _item("广州塔", time="09:00", duration=90),
            _item("白云山", time="11:00", duration=180),
        )
    )

    assert "transport_impossible" in _rules(issues)


def test_r3_bike_mode_selected_for_short_distance() -> None:
    issues = check(
        _itinerary(
            _item("陈家祠", time="17:00", duration=None),
            _item("北京路步行街", time="17:10", duration=None),
        )
    )

    transport = [issue for issue in issues if issue.rule == "transport_impossible"]
    assert transport
    assert "骑行" in transport[0].evidence


def test_r3_long_metro_is_not_a_false_positive() -> None:
    issues = check(
        _itinerary(
            _item("长隆野生动物世界", time="09:30", duration=180),
            _item("华南植物园", time="14:00", duration=150),
        )
    )

    assert "transport_impossible" not in _rules(issues)


def test_r3_taxi_declared_via_transport_mode() -> None:
    issues = check(
        _itinerary(
            _item("广州塔", time="09:00", duration=120),
            _item("黄埔古港", time="11:10", duration=90, transport_mode="taxi"),
        )
    )

    transport = [issue for issue in issues if issue.rule == "transport_impossible"]
    assert transport
    assert "打车" in transport[0].evidence


def test_r3_walk_800m_is_enough() -> None:
    rows = [
        {
            "name": "测试A",
            "category": "sight",
            "lat": "23.1250",
            "lng": "113.2680",
            "duration_min": "15",
            "open_windows": "00:00-24:00",
            "closed_weekday": "",
            "fee": "0",
            "night_access": "open",
            "lighting": "good",
            "slope": "flat",
            "booking": "no",
            "note": "",
            "verified_at": "2026-11",
        },
        {
            "name": "测试B",
            "category": "sight",
            "lat": "23.1322",
            "lng": "113.2680",
            "duration_min": "30",
            "open_windows": "00:00-24:00",
            "closed_weekday": "",
            "fee": "0",
            "night_access": "open",
            "lighting": "good",
            "slope": "flat",
            "booking": "no",
            "note": "",
            "verified_at": "2026-11",
        },
    ]
    issues = check(
        _itinerary(
            _item("测试A", time="10:00", duration=15),
            _item("测试B", time="10:30", duration=30),
        ),
        poi_rows=rows,
    )

    assert issues == []


def test_r4_overload() -> None:
    issues = check(
        _itinerary(
            _item("广州塔", duration=120),
            _item("花城广场", duration=60),
            _item("广东省博物馆", duration=150),
            _item("陈家祠", duration=90),
            _item("沙面岛", duration=90),
            _item("上下九步行街", duration=90),
            _item("永庆坊", duration=90),
            _item("珠江夜游天字码头", duration=90),
        )
    )

    assert _rules(issues) == ["overload"]
    assert issues[0].level == "warn"
    assert "780" in issues[0].evidence


def test_r5_unlisted_is_info() -> None:
    issues = check(_itinerary(_item("火星基地")))

    assert len(issues) == 1
    assert issues[0].rule == "unverified"
    assert issues[0].level == "info"
    assert issues[0].evidence == "未收录，未校验"


def test_r6_night_closed() -> None:
    issues = check(_itinerary(_item("陈家祠", time="21:30", duration=90, period="evening")))

    assert _rules(issues) == ["night_closed"]
    assert issues[0].level == "error"


def test_r6_entry_only_out_on_first_stop() -> None:
    issues = check(
        _itinerary(
            _item("越秀公园", time="21:00", duration=120, period="evening"),
            _item("北京路步行街", time="23:45", duration=90, period="evening"),
        )
    )

    assert _rules(issues) == ["entry_only_out"]
    assert issues[0].level == "warn"


def test_r6_no_lighting_for_evening() -> None:
    rows = load_poi() + [
        {
            "name": "无灯步道",
            "category": "sight",
            "lat": "23.1800",
            "lng": "113.2900",
            "duration_min": "60",
            "open_windows": "00:00-24:00",
            "closed_weekday": "",
            "fee": "0",
            "night_access": "open",
            "lighting": "none",
            "slope": "flat",
            "booking": "no",
            "note": "",
            "verified_at": "2026-11",
        }
    ]
    issues = check(
        _itinerary(_item("无灯步道", duration=60, period="evening")),
        poi_rows=rows,
    )

    assert _rules(issues) == ["no_lighting"]
    assert issues[0].level == "warn"


def test_reasonable_day_returns_empty() -> None:
    issues = check(
        _itinerary(
            _item("北京路步行街", time="10:00", duration=90, period="morning"),
            _item("银记肠粉北京路", time="11:45", duration=30, period="noon"),
        )
    )

    assert issues == []


def test_missing_time_skips_transport_and_night_rules() -> None:
    issues = check(
        _itinerary(
            _item("越秀公园", duration=120),
            _item("广州塔", duration=120),
            _item("黄埔古港", duration=90),
            _item("陈家祠", duration=90),
        )
    )

    assert issues == []


def test_same_rule_not_reported_twice() -> None:
    issues = check(
        _itinerary(
            _item("广州塔", duration=60),
            _item("广州塔", duration=60),
        )
    )

    assert _rules(issues).count("time_short") == 1


def test_demo_all_issue_evidence_is_not_empty() -> None:
    text = (DATA_DIR / "demo_itinerary.txt").read_text(encoding="utf-8")
    issues = check(parse_itinerary(text))

    assert issues
    for issue in issues:
        assert issue.evidence.strip()


def test_demo_regression() -> None:
    text = (DATA_DIR / "demo_itinerary.txt").read_text(encoding="utf-8")
    issues = check(parse_itinerary(text))

    closed = [issue for issue in issues if issue.rule == "closed_day"]
    transport = [issue for issue in issues if issue.rule == "transport_impossible"]
    overload = [issue for issue in issues if issue.rule == "overload"]

    assert len(closed) == 1
    assert len(transport) >= 2
    assert any("地铁" in issue.evidence for issue in transport)
    assert any("骑行" in issue.evidence for issue in transport)
    assert len(overload) == 1
    assert not any(issue.rule == "unverified" for issue in issues)
    assert 8 <= len(issues) <= 14


def test_issue_with_empty_evidence_raises() -> None:
    with pytest.raises(ValueError):
        _issue("error", "time_short", "广州塔", "   ")