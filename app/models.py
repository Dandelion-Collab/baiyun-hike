"""接口契约模型（pydantic v2）。

字段一次留足，让后续实现只填逻辑、不改模型：
- Issue 必带 evidence（无依据不得输出）。
- RouteResult 覆盖拒答、部分可达、降级、待校验四类状态。
- Leg 用 alias 保留对外契约里的 "from" / "to"。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Period = Literal["morning", "noon", "afternoon", "evening"]
Category = Literal["sight", "food"]
Stamina = Literal["low", "medium", "high"]
IssueLevel = Literal["error", "warn", "info"]
NightAccess = Literal["open", "gate_only_out", "closed", "na"]


class ItineraryItem(BaseModel):
    """行程中的一站。time 为 HH:MM，transport_mode 取 walk/bike/metro/taxi；
    duration_min 为分钟，识别不到都填 None，不猜。
    """

    name: str
    period: Period | None = None
    time: str | None = None
    transport_mode: str | None = None
    duration_min: int | None = None
    category: Category | None = None
    date: str | None = None


class Itinerary(BaseModel):
    """一份待体检的行程。date 形如 YYYY-MM-DD；跨天时按出发日归属。"""

    date: str | None = None
    items: list[ItineraryItem] = Field(default_factory=list)


class Issue(BaseModel):
    """一条体检结论。evidence 为空即视为无依据，不得输出。"""

    level: IssueLevel
    rule: str
    item: str
    evidence: str
    suggest: str | None = None


class Intent(BaseModel):
    """能力 B 的意图。when 用 HH:MM；target 未说明时默认摩星岭。"""

    when: str
    party_size: int | None = 1
    stamina: Stamina | None = None
    target: str = "摩星岭"
    alone: bool | None = None


class CheckRequest(BaseModel):
    """POST /check 的入参：用户贴进来的自然语言行程。"""

    text: str


class RouteRequest(BaseModel):
    """POST /route 的入参。depart_at 用 HH:MM。"""

    from_node: str
    to_node: str
    depart_at: str
    intent: Intent | None = None


class Leg(BaseModel):
    """路径中的一段。对外序列化用 "from" / "to"，内部用 from_node / to_node。"""

    model_config = ConfigDict(populate_by_name=True)

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    walk_min: int
    distance_m: int
    lighting: str | None = None
    slope: str | None = None


class Fallback(BaseModel):
    """走不通时的三段式：最远可达点 + 卡点 + 建议（至少一条）。"""

    farthest_path: list[str] = Field(default_factory=list)
    blocked_at: str | None = None
    suggestions: list[str] = Field(default_factory=list)


class RouteResult(BaseModel):
    """能力 B 的输出契约。reachable=false 时不得出现“大概能走”的路线。"""

    reachable: bool = False
    path: list[str] = Field(default_factory=list)
    legs: list[Leg] = Field(default_factory=list)
    total_min: int = 0
    depart_at: str | None = None
    arrive_at: str | None = None
    reason: str | None = None
    fallback: Fallback | None = None
    partial: bool = False
    blocked_at: str | None = None
    warnings: list[str] = Field(default_factory=list)
    unverified: bool = False
    degraded: bool = False