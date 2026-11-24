"""可通行性判定。

口径见 docs/night_rules.md 与 docs/decisions.md D1 / D3 / D9。
时间统一用当天分钟数 int，24:00 记为 1440。
"""

from __future__ import annotations

import re

from app.rules import ENTRY_CUTOFF_MIN

WINDOW_RE = re.compile(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})")
DAY_END = 24 * 60


def _to_minutes(hour: int, minute: int) -> int:
    if hour > 24 or minute > 59 or (hour == 24 and minute != 0):
        raise ValueError(f"非法时刻：{hour:02d}:{minute:02d}")
    return hour * 60 + minute


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_windows(text: str) -> list[tuple[int, int]]:
    """把 `06:00-12:00;14:00-18:00` 解析为当天分钟数区间 [(360, 720), ...]。

    24:00 视为 1440；格式非法、起点晚于终点、或时刻越界都抛 ValueError。
    """

    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"非法时间窗：{text!r}")

    windows: list[tuple[int, int]] = []
    for chunk in text.split(";"):
        match = WINDOW_RE.fullmatch(chunk.strip())
        if not match:
            raise ValueError(f"非法时间窗：{text!r}")
        start = _to_minutes(int(match.group(1)), int(match.group(2)))
        end = _to_minutes(int(match.group(3)), int(match.group(4)))
        if start >= DAY_END or end <= start:
            raise ValueError(f"非法时间窗：{text!r}")
        windows.append((start, end))
    return windows


def is_open(node: dict[str, str], t: int) -> bool:
    """时刻 t 是否落在节点任一窗口 [start, end) 内；t == end 视为关闭。"""

    return any(start <= t < end for start, end in parse_windows(node["open_windows"]))


def node_enterable(node: dict[str, str], t: int) -> bool:
    """节点在 t 是否可进。

    gate 除窗口外还要满足 t <= end - ENTRY_CUTOFF_MIN（闭端）；
    junction / summit 只看窗口。gate_only_out 的“只出不进”由 gate 的
    窗口 + cutoff 表达：窗口外一律不可进，不额外按 NIGHT_START_MIN 判，
    否则会与 D8“21:00 南门可进”冲突。
    """

    windows = parse_windows(node["open_windows"])
    if node.get("type") == "gate":
        return any(start <= t <= end - ENTRY_CUTOFF_MIN for start, end in windows)
    return any(start <= t < end for start, end in windows)


def edge_passable(edge: dict[str, str], t1: int, t2: int) -> bool:
    """整段覆盖：必须存在窗口使 start <= t1 且 t2 < end（见 D1）。"""

    return any(
        start <= t1 and t2 < end
        for start, end in parse_windows(edge["passable_windows"])
    )


def explain_why_closed(x: dict[str, str], t1: int, t2: int) -> str:
    """把不可通行翻译成人话，必须带具体时刻与窗口边界。"""

    raw = x.get("passable_windows") or x.get("open_windows")
    windows = parse_windows(raw)
    closing = min((end for start, end in windows if end >= t1), default=windows[-1][1])
    label = "该路段" if "passable_windows" in x else "该地点"
    return f"{label} {_fmt(closing)} 关闭，你 {_fmt(t1)} 出发 {_fmt(t2)} 到达"