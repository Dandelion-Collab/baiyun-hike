"""用高德地理编码 API 自动校正 poi.csv 的经纬度。

为什么需要：poi.csv 里的坐标是人工填的近似值（note 列标了"坐标待校验"），
而距离计算对坐标很敏感——差 500 米就可能误判"交通不可能"。
这个脚本一次跑完，把坐标换成高德返回的 GCJ-02 坐标。

用法：
    set AMAP_KEY=你的Web服务Key          # Windows
    python tools/geo_fix.py data/poi.csv

可选：
    python tools/geo_fix.py data/poi.csv --dry-run   # 只打印，不写回
    python tools/geo_fix.py data/poi.csv --all       # 全部重查（默认只查标了"坐标待校验"的）

说明：
- 用的是 Web 服务 API（不是 JS API Key）
- 地址取 name 列，city 固定为广州；查不到的按失败列出，手动用坐标拾取器补
- 每次请求间隔 0.25 秒，避免触发频控
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

CITY = "广州"
API = "https://restapi.amap.com/v3/geocode/geo"
PENDING_FLAG = "坐标待校验"
SLEEP_SEC = 0.25


def geocode(key: str, address: str) -> tuple[float, float] | None:
    query = urllib.parse.urlencode({"address": address, "city": CITY, "key": key})
    url = f"{API}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # 网络/超时
        print(f"  ! 请求失败: {exc}")
        return None

    if data.get("status") != "1":
        print(f"  ! 接口报错: {data.get('info')} ({data.get('infocode')})")
        return None
    geocodes = data.get("geocodes") or []
    if not geocodes:
        return None

    lng_str, lat_str = geocodes[0]["location"].split(",")
    return float(lat_str), float(lng_str)


def main() -> int:
    parser = argparse.ArgumentParser(description="校正 POI 坐标")
    parser.add_argument("csv_path", help="poi.csv 路径")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写回文件")
    parser.add_argument("--all", action="store_true", help="全部重查，而不只是标记待校验的")
    args = parser.parse_args()

    key = os.environ.get("AMAP_KEY", "").strip()
    if not key:
        print("缺少环境变量 AMAP_KEY。先设置：set AMAP_KEY=你的Web服务Key")
        return 2

    with open(args.csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("CSV 是空的")
        return 1

    fields = list(rows[0].keys())
    ok = failed = skipped = 0

    for i, row in enumerate(rows, 1):
        name = (row.get("name") or "").strip()
        note = row.get("note") or ""
        need = args.all or PENDING_FLAG in note
        if not name or not need:
            skipped += 1
            continue

        print(f"[{i}/{len(rows)}] {name}")
        result = geocode(key, name)
        time.sleep(SLEEP_SEC)

        if result is None:
            print("  × 查不到，请用坐标拾取器手动补")
            failed += 1
            continue

        lat, lng = result
        row["lat"] = f"{lat:.6f}"
        row["lng"] = f"{lng:.6f}"
        row["note"] = note.replace(PENDING_FLAG, "").strip("；; ")
        print(f"  ✓ {lat:.6f},{lng:.6f}")
        ok += 1

    if not args.dry_run:
        with open(args.csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    print(f"\n完成：成功 {ok}，失败 {failed}，跳过 {skipped}")
    if args.dry_run:
        print("（dry-run，未写回文件）")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
