"""把一天的行程点按顺序连成路线。

输入 points = [(名称, (lng, lat)), ...]，顺序即当天的游览顺序。
直线距离用 haversine 自己算；交通方式与耗时的默认口径复用 app.checker。
有 Web 服务 Key 且直线距离不超过 AMAP_WALK_MAX_M 时向高德要真实步行路径，
失败、超距或无 Key 一律回退起终两点直线，并标注 FALLBACK_NOTE。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.amap import AmapError, MissingKeyError, walking_route
from app.checker import _default_mode, _transport_need

EARTH_RADIUS_M = 6371000.0
AMAP_WALK_MAX_M = 2500
FALLBACK_NOTE = "直线估算"


@dataclass
class Leg:
    index: int
    from_name: str
    to_name: str
    mode: str
    straight_m: int
    distance_m: int
    minutes: int
    real_path: bool
    polyline: list[tuple[float, float]] = field(default_factory=list)
    note: str = ""


def _haversine_m(
    start: tuple[float, float], end: tuple[float, float]
) -> float:
    """两点的球面直线距离（米）。坐标顺序为 (lng, lat)。"""

    lng1, lat1 = start
    lng2, lat2 = end
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _coord(point: tuple[float, float]) -> str:
    return f"{point[0]:.6f},{point[1]:.6f}"


def _fallback_leg(
    index: int,
    from_name: str,
    to_name: str,
    start: tuple[float, float],
    end: tuple[float, float],
    straight_m: int,
    mode: str,
) -> Leg:
    return Leg(
        index=index,
        from_name=from_name,
        to_name=to_name,
        mode=mode,
        straight_m=straight_m,
        distance_m=straight_m,
        minutes=max(1, round(_transport_need(mode, straight_m))),
        real_path=False,
        polyline=[start, end],
        note=FALLBACK_NOTE,
    )


def plan_day(
    points: list[tuple[str, tuple[float, float]]], key_available: bool
) -> list[Leg]:
    """按顺序生成相邻两点之间的 Leg；少于两个点返回空列表。"""

    legs: list[Leg] = []
    for index in range(len(points) - 1):
        from_name, start_raw = points[index]
        to_name, end_raw = points[index + 1]
        start = (float(start_raw[0]), float(start_raw[1]))
        end = (float(end_raw[0]), float(end_raw[1]))

        straight_m = round(_haversine_m(start, end))
        mode = _default_mode(straight_m)

        route = None
        if key_available and straight_m <= AMAP_WALK_MAX_M:
            try:
                route = walking_route(_coord(start), _coord(end))
            except (AmapError, MissingKeyError):
                route = None

        if route is None:
            legs.append(
                _fallback_leg(
                    index, str(from_name), str(to_name), start, end, straight_m, mode
                )
            )
            continue

        legs.append(
            Leg(
                index=index,
                from_name=str(from_name),
                to_name=str(to_name),
                mode=mode,
                straight_m=straight_m,
                distance_m=int(route.distance_m),
                minutes=int(route.duration_min),
                real_path=True,
                polyline=list(route.polyline) or [start, end],
                note="",
            )
        )
    return legs