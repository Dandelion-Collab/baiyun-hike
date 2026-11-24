"""POI 表加载与查询。

只做“读 CSV + 包含匹配”，不做任何规则判定。
返回原始字符串字典，类型转换留给使用方，避免加载层替业务层做决定。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def load_poi(path: str | Path | None = None) -> list[dict[str, str]]:
    """读取 poi.csv，返回逐行字典。空字段保持空字符串，不转 NaN。"""

    csv_path = Path(path) if path is not None else DATA_DIR / "poi.csv"
    frame = pd.read_csv(
        csv_path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    return frame.to_dict(orient="records")


def find_poi(name: str, rows: list[dict[str, str]] | None = None) -> dict[str, str] | None:
    """按包含匹配找 POI：行程写法可含地点名，也可被地点名包含。"""

    pool = rows if rows is not None else load_poi()
    for row in pool:
        poi_name = row.get("name", "")
        if not poi_name:
            continue
        if poi_name in name or name in poi_name:
            return row
    return None