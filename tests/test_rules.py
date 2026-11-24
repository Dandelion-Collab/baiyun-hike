"""锁住 D5 常量与模型契约，防止后续修改静默改口径。"""

from __future__ import annotations

from app import rules
from app.models import Issue, Leg, RouteResult

D5_CONSTANTS = {
    "ENTRY_CUTOFF_MIN": 30,
    "MIN_TRANSFER_MIN": 5,
    "MAX_DAY_MIN": 600,
    "TIME_SHORT_RATIO": 0.6,
    "MAX_LEG_KM": 5.0,
    "MIN_LEG_MIN": 20,
    "VERIFY_TTL_MONTHS": 12,
}


def test_d5_constants_match_decisions() -> None:
    for name, expected in D5_CONSTANTS.items():
        assert getattr(rules, name) == expected, f"{name} 与 docs/decisions.md D5 不一致"


def test_d10_constants_match_decisions() -> None:
    assert rules.WALK_SPEED_M_PER_MIN == 80
    assert rules.TIME_TIGHT_RATIO == 0.85


def test_night_start_constant() -> None:
    assert rules.NIGHT_START_MIN == 21 * 60


def test_route_result_contract_is_complete() -> None:
    expected = {
        "reachable", "path", "legs", "total_min", "depart_at", "arrive_at",
        "reason", "fallback", "partial", "blocked_at", "warnings",
        "unverified", "degraded",
    }
    assert set(RouteResult.model_fields) == expected


def test_issue_contract_requires_evidence() -> None:
    assert set(Issue.model_fields) == {"level", "rule", "item", "evidence", "suggest"}


def test_leg_keeps_from_to_alias() -> None:
    leg = Leg.model_validate(
        {"from": "N01", "to": "N06", "walk_min": 12, "distance_m": 600}
    )
    assert leg.from_node == "N01"
    assert leg.model_dump(by_alias=True)["from"] == "N01"
    assert leg.model_dump(by_alias=True)["to"] == "N06"