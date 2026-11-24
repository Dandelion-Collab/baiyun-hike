"""门禁点测试：命中半径与时间窗判定，坐标从数据实际值生成。"""

from __future__ import annotations

from app.gates import gates_near, load_gates
from app.passability import node_enterable


def _gate(gate_id: str) -> dict:
    return next(item for item in load_gates() if item["id"] == gate_id)


def _point(gate: dict) -> tuple[float, float]:
    return (float(gate["lng"]), float(gate["lat"]))


def test_gates_near_hits_south_gate() -> None:
    hits = gates_near([_point(_gate("N01"))], radius_m=60)

    assert [gate["id"] for gate in hits] == ["N01"]


def test_gates_near_hits_about_30m_away() -> None:
    gate = _gate("N01")
    nearby = (float(gate["lng"]), float(gate["lat"]) + 0.00027)

    hits = gates_near([nearby], radius_m=60)

    assert "N01" in [item["id"] for item in hits]


def test_gates_near_misses_far_points() -> None:
    gates = load_gates()
    far = (
        max(float(item["lng"]) for item in gates) + 0.1,
        max(float(item["lat"]) for item in gates) + 0.1,
    )

    assert gates_near([far], radius_m=60) == []


def test_south_gate_is_open_all_night() -> None:
    """南门按官方口径 24 小时开放，夜爬从这里进。"""

    gate = _gate("N01")

    assert node_enterable(gate, 22 * 60) is True
    assert node_enterable(gate, 2 * 60) is True


def test_kolziling_gate_cutoff_boundary() -> None:
    """非 24 小时的门：06:00-22:00，停止入园缓冲 30 分钟，闭端 21:30 仍可进。"""

    gate = _gate("N03")

    assert node_enterable(gate, 21 * 60 + 30) is True
    assert node_enterable(gate, 21 * 60 + 31) is False
    assert node_enterable(gate, 22 * 60 + 30) is False