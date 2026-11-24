"""数据体检：开始写代码之前，先把数据口径校验一遍。

用法：
    python tools/preflight.py

退出码：0 全部通过；1 有 FAIL；2 文件缺失。
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

TIME_RE = re.compile(r"^(\d{2}):(\d{2})$")

POI_HEADER = [
    "name", "category", "lat", "lng", "duration_min", "open_windows", "closed_weekday",
    "fee", "night_access", "lighting", "slope", "booking", "note", "verified_at",
]
NODE_HEADER = ["id", "name", "type", "lat", "lng", "open_windows", "night_access", "note"]
EDGE_HEADER = ["from", "to", "distance_m", "walk_min", "slope", "lighting", "passable_windows", "note"]

ENUMS = {
    "category": {"sight", "food"},
    "night_access": {"open", "gate_only_out", "closed", "na"},
    "lighting": {"good", "partial", "none", "na"},
    "slope": {"flat", "mild", "steep", "na"},
    "type": {"gate", "junction", "summit", "toilet"},
    "booking": {"yes", "no"},
}

fail: list[str] = []
warn: list[str] = []
pass_count = 0


def ok(msg: str) -> None:
    global pass_count
    pass_count += 1
    print(f"  PASS  {msg}")


def bad(msg: str) -> None:
    fail.append(msg)
    print(f"  FAIL  {msg}")


def soft(msg: str) -> None:
    warn.append(msg)
    print(f"  WARN  {msg}")


def read_csv(path: Path, header: list[str]) -> list[dict] | None:
    if not path.exists():
        bad(f"缺少文件 {path.relative_to(ROOT)}")
        return None
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        actual = reader.fieldnames or []
        rows = list(reader)
    if actual != header:
        missing = [c for c in header if c not in actual]
        extra = [c for c in actual if c not in header]
        bad(f"{path.name} 表头不匹配；缺 {missing}，多 {extra}")
        return rows
    ok(f"{path.name} 表头正确（{len(rows)} 行）")
    return rows


def parse_windows(text: str, where: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    if not text:
        bad(f"{where}: 时间窗为空")
        return out
    for part in text.split(";"):
        part = part.strip()
        if "-" not in part:
            bad(f"{where}: 非法时间窗 '{part}'")
            continue
        s, e = part.split("-", 1)
        m1, m2 = TIME_RE.match(s.strip()), TIME_RE.match(e.strip())
        if not m1 or not m2:
            bad(f"{where}: 非法时刻 '{part}'")
            continue
        sh, sm = int(m1.group(1)), int(m1.group(2))
        eh, em = int(m2.group(1)), int(m2.group(2))
        if (sh, sm) == (24, 0):
            start, end = 24 * 60, 24 * 60
        else:
            start = sh * 60 + sm
            end = (24 * 60) if (eh, em) == (24, 0) else eh * 60 + em
        if start >= end:
            bad(f"{where}: 窗口结束不晚于开始 '{part}'（跨午夜请拆成两行）")
            continue
        out.append((start, end))
    return out


def check_poi() -> list[dict]:
    rows = read_csv(DATA / "poi.csv", POI_HEADER)
    if rows is None:
        return []
    seen: set[str] = set()
    for i, r in enumerate(rows, 2):
        w = f"poi.csv 第 {i} 行 {r.get('name', '?')}"
        if not r.get("name"):
            bad(f"{w}: name 为空")
        elif r["name"] in seen:
            bad(f"{w}: name 重复")
        else:
            seen.add(r["name"])
        for field in ("category", "night_access", "lighting", "slope", "booking"):
            v = (r.get(field) or "").strip()
            if v not in ENUMS[field]:
                bad(f"{w}: {field}='{v}' 不在 {sorted(ENUMS[field])}")
        try:
            lat, lng = float(r["lat"]), float(r["lng"])
            if not (22.5 <= lat <= 23.9):
                bad(f"{w}: lat={lat} 超出广州范围")
            if not (112.9 <= lng <= 114.1):
                bad(f"{w}: lng={lng} 超出广州范围")
        except (TypeError, ValueError):
            bad(f"{w}: 坐标不是数字")
        try:
            if int(r["duration_min"]) <= 0:
                bad(f"{w}: duration_min 必须为正")
        except (TypeError, ValueError):
            bad(f"{w}: duration_min 不是整数")
        cw = (r.get("closed_weekday") or "").strip()
        if cw and (not cw.isdigit() or not 1 <= int(cw) <= 7):
            bad(f"{w}: closed_weekday='{cw}' 应为 1-7")
        if not (r.get("verified_at") or "").strip():
            soft(f"{w}: verified_at 为空")
        parse_windows(r.get("open_windows", ""), w)
    return rows


def check_nodes() -> set[str]:
    rows = read_csv(DATA / "baiyun_nodes.csv", NODE_HEADER)
    if rows is None:
        return set()
    ids: set[str] = set()
    for i, r in enumerate(rows, 2):
        w = f"nodes 第 {i} 行 {r.get('id', '?')}"
        if r["id"] in ids:
            bad(f"{w}: id 重复")
        ids.add(r["id"])
        if (r.get("type") or "") not in ENUMS["type"]:
            bad(f"{w}: type='{r.get('type')}' 不合法")
        if (r.get("night_access") or "") not in ENUMS["night_access"]:
            bad(f"{w}: night_access='{r.get('night_access')}' 不合法")
        parse_windows(r.get("open_windows", ""), w)
    ok(f"nodes 共 {len(ids)} 个节点")
    return ids


def check_edges(ids: set[str]) -> None:
    rows = read_csv(DATA / "baiyun_edges.csv", EDGE_HEADER)
    if rows is None:
        return
    for i, r in enumerate(rows, 2):
        w = f"edges 第 {i} 行 {r.get('from')}->{r.get('to')}"
        for end in ("from", "to"):
            if r[end] not in ids:
                bad(f"{w}: {end}='{r[end]}' 不在 nodes 中")
        try:
            d, t = int(r["distance_m"]), int(r["walk_min"])
            if t <= 0:
                bad(f"{w}: walk_min 必须为正")
            else:
                speed = d / t
                if not (30 <= speed <= 150):
                    bad(f"{w}: 步行速度 {speed:.0f} 米/分 不合理")
        except (TypeError, ValueError):
            bad(f"{w}: distance_m / walk_min 不是整数")
        for field in ("slope", "lighting"):
            if (r.get(field) or "") not in ENUMS[field]:
                bad(f"{w}: {field}='{r.get(field)}' 不合法")
        parse_windows(r.get("passable_windows", ""), w)


def check_demo(poi_rows: list[dict]) -> None:
    path = DATA / "demo_itinerary.txt"
    if not path.exists():
        bad("缺少 demo_itinerary.txt")
        return
    text = path.read_text(encoding="utf-8")
    names = [r["name"] for r in poi_rows]
    unmatched = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("第"):
            continue
        if not any(n in line for n in names):
            unmatched.append(line)
    if unmatched:
        for line in unmatched:
            soft(f"演示行程中的地点可能未收录：{line}")
    else:
        ok("演示行程中的每一站都能在 poi.csv 中找到")


def check_genuine_flag(poi_rows: list[dict], node_rows: list[dict], edge_rows: list[dict]) -> None:
    total = len(poi_rows) + len(node_rows) + len(edge_rows)
    pending = sum(1 for r in poi_rows + node_rows + edge_rows if "待校验" in (r.get("note") or ""))
    if total and pending / total > 0.5:
        soft(f"{pending}/{total} 行标注'待校验'，建议先跑 tools/geo_fix.py 校正坐标")
    else:
        ok(f"待校验行数 {pending}/{total}")


def main() -> int:
    print("== 数据体检 ==")
    poi_rows = check_poi() or []
    ids = check_nodes()
    check_edges(ids)
    check_demo(poi_rows)

    # 重新读一次用于统计（read_csv 已被调用过，简单起见再读）
    try:
        with open(DATA / "baiyun_nodes.csv", encoding="utf-8-sig", newline="") as f:
            node_rows = list(csv.DictReader(f))
        with open(DATA / "baiyun_edges.csv", encoding="utf-8-sig", newline="") as f:
            edge_rows = list(csv.DictReader(f))
    except OSError:
        node_rows, edge_rows = [], []
    check_genuine_flag(poi_rows, node_rows, edge_rows)

    print("\n== 汇总 ==")
    print(f"  PASS {pass_count}  WARN {len(warn)}  FAIL {len(fail)}")
    if fail:
        print("\n必须修复：")
        for m in fail:
            print(f"  - {m}")
        return 1
    print("\n数据可用于开发。下一步：创建 app/ 骨架并跑首批测试。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
