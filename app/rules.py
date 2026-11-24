"""判定口径的数字来源。

这里的阈值常量必须与 docs/decisions.md 的 D5 / D10 / D11 表一致；
BASE_DATE 是相对日期的统一基准（2026-11-23，周一），同样只在这里定义一次。
改值先改文档，再改这里，避免代码与口径漂移。

注意：
- walk_min 在录入时已折入 ×1.2 安全余量，代码中不得再次放大。
- ENTRY_CUTOFF_MIN 对应 D3 的“停止入园缓冲”，语义是“入园”，
  因此只对 type=gate 的节点生效；junction / summit 不受该缓冲约束。
  边界取闭端：t <= end - ENTRY_CUTOFF_MIN 才可进——这是 D8 表
  “21:00 从南门进”“22:00 从西门进”两条同时成立的必要条件。
- MAX_LEG_KM 不再参与 R3，保留待用；R3 以时间需求为唯一判据。
"""

from __future__ import annotations

from datetime import date

BASE_DATE: date = date(2026, 11, 23)

ENTRY_CUTOFF_MIN: int = 30
MIN_TRANSFER_MIN: int = 5
MAX_DAY_MIN: int = 600
TIME_SHORT_RATIO: float = 0.6
TIME_TIGHT_RATIO: float = 0.85
MAX_LEG_KM: float = 5.0
MIN_LEG_MIN: int = 20
VERIFY_TTL_MONTHS: int = 12

# D11：按距离选择交通方式；文本声明优先。
WALK_MAX_M: int = 1200
BIKE_MAX_M: int = 4000
WALK_SPEED_M_PER_MIN: int = 80
BIKE_SPEED_M_PER_MIN: int = 250
BIKE_OVERHEAD_MIN: int = 5
METRO_BASE_MIN: int = 10
METRO_MIN_PER_KM: float = 2.5
TAXI_SPEED_M_PER_MIN: int = 400
TAXI_OVERHEAD_MIN: int = 10

# R6 的夜间起点：到达时刻 >= 该值才判夜间关闭 / 只出不进。
NIGHT_START_MIN: int = 21 * 60