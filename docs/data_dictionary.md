# 数据字典

> 三张表 + 一份演示行程。字段变更必须同步更新本文件与 `tools/preflight.py`。

## 1. `data/poi.csv`（34 个广州点）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| name | str | ✓ | 唯一名称；与演示行程中的写法要能被包含匹配 |
| category | enum | ✓ | `sight` / `food` |
| lat, lng | float | ✓ | GCJ-02 坐标，保留 6 位小数 |
| duration_min | int | ✓ | 建议停留分钟数 |
| open_windows | str | ✓ | `HH:MM-HH:MM`，多窗口用 `;`；全天写 `00:00-24:00` |
| closed_weekday | int |  | 1–7（周一=1），空表示不闭馆 |
| fee | int | ✓ | 门票/人均（元），0 表示免费 |
| night_access | enum | ✓ | `open` / `gate_only_out` / `closed` / `na` |
| lighting | enum | ✓ | `good` / `partial` / `none` / `na` |
| slope | enum | ✓ | `flat` / `mild` / `steep` / `na` |
| booking | bool | ✓ | `yes` / `no`，是否需预约 |
| note | str |  | 自由文本；含"待校验"表示数据未核实 |
| verified_at | str | ✓ | `YYYY-MM`，数据核实月份 |

## 2. `data/baiyun_nodes.csv`（白云山 10 个节点）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | str | `N01`…`N10`，被 edges 引用 |
| name | str | 展示名（南门/西门/摩星岭…） |
| type | enum | `gate` / `junction` / `summit` / `toilet` |
| lat, lng | float | GCJ-02 |
| open_windows | str | 可进入且可停留的时段 |
| night_access | enum | `open` / `gate_only_out` / `closed`（当前 10 个节点均为 `open`；`gate_only_out` 留给"只出不进"的门） |
| note | str | 含"待校验"则标 unverified |

## 3. `data/baiyun_edges.csv`（12 条边）

| 字段 | 类型 | 说明 |
|---|---|---|
| from, to | str | 必须是 nodes 中存在的 id |
| distance_m | int | 米 |
| walk_min | int | 分钟，**已含 ×1.2 安全余量** |
| slope | enum | 同 poi |
| lighting | enum | 同 poi |
| passable_windows | str | 可通行时段（半开区间） |
| note | str | 自由文本 |

## 4. `data/demo_itinerary.txt`

自然语言三天行程，用于演示与测试；每站名称应能在 `poi.csv` 中找到（包含匹配）。

## 5. 校验规则（`tools/preflight.py` 实现）

1. 表头与上表完全一致
2. 时间格式 `^\d{2}:\d{2}$`，且 `end > start`（`24:00` 视为 1440）
3. 枚举值合法
4. `closed_weekday` ∈ 1..7
5. 坐标落在广州范围：lat 22.5–23.9，lng 112.9–114.1
6. `name` 不重复
7. edges 的 `from`/`to` 必须存在于 nodes
8. 步行速度合理：`distance_m / walk_min` ∈ [30, 150] 米/分钟
9. 演示行程中的地点能被 poi.csv 包含匹配
10. 缺失/多余列直接判 FAIL
