"""坐标换算：WGS84→GCJ02、最近山门（山门坐标为 GCJ-02）。"""

from __future__ import annotations

import math

from app.gates import load_gates

A = 6378245.0
EE = 0.00669342162296594323
EARTH_RADIUS_M = 6371000.0
DEFAULT_GATE_RADIUS_M = 120.0
DEFAULT_COORD_SYSTEM = "wgs84"
COORD_SYSTEMS = ("wgs84", "gcj02")


def _out_of_china(lat: float, lng: float) -> bool:
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)


def _transform_lat(x: float, y: float) -> float:
    ret = (
        -100.0
        + 2.0 * x
        + 3.0 * y
        + 0.2 * y * y
        + 0.1 * x * y
        + 0.2 * math.sqrt(abs(x))
    )
    ret += (
        20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)
    ) * 2.0 / 3.0
    ret += (
        20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)
    ) * 2.0 / 3.0
    ret += (
        160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)
    ) * 2.0 / 3.0
    return ret


def _transform_lng(x: float, y: float) -> float:
    ret = (
        300.0
        + x
        + 2.0 * y
        + 0.1 * x * x
        + 0.1 * x * y
        + 0.1 * math.sqrt(abs(x))
    )
    ret += (
        20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)
    ) * 2.0 / 3.0
    ret += (
        20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)
    ) * 2.0 / 3.0
    ret += (
        150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)
    ) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lat: float, lng: float) -> tuple[float, float]:
    """WGS84 转 GCJ02；境外坐标原样返回。"""

    if _out_of_china(lat, lng):
        return lat, lng

    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (A / sqrtmagic * math.cos(radlat) * math.pi)
    return lat + dlat, lng + dlng


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a))) / 1000.0


def distance_to_nearest_gate(
    lat: float,
    lng: float,
    radius_m: float = DEFAULT_GATE_RADIUS_M,
    coord_system: str = DEFAULT_COORD_SYSTEM,
) -> tuple[str, float, bool]:
    """返回（最近山门名称, 公里, 是否在 radius_m 内）。

    coord_system：入参坐标系。"wgs84"（默认）先转 GCJ-02 再比较；
    "gcj02" 直接与 GCJ-02 山门坐标比较。山门坐标是 GCJ-02。
    """

    if coord_system not in COORD_SYSTEMS:
        raise ValueError(
            f"coord_system 只能是 {COORD_SYSTEMS}，收到 {coord_system!r}"
        )

    gates = load_gates()
    if not gates:
        return "", float("inf"), False

    if coord_system == "wgs84":
        gcj_lat, gcj_lng = wgs84_to_gcj02(lat, lng)
    else:
        gcj_lat, gcj_lng = lat, lng
    best = min(
        gates,
        key=lambda gate: _haversine_km(
            gcj_lat, gcj_lng, float(gate["lat"]), float(gate["lng"])
        ),
    )
    km = _haversine_km(
        gcj_lat, gcj_lng, float(best["lat"]), float(best["lng"])
    )
    return str(best["name"]), km, km <= radius_m / 1000.0

def amap_origin(
    lat: float, lng: float, coord_system: str = DEFAULT_COORD_SYSTEM
) -> str:
    """返回高德接口需要的 "lng,lat" 字符串。

    "wgs84" 先转 GCJ-02；"gcj02" 原样输出。格式化到 6 位小数（约 0.1 米）。
    """

    if coord_system not in COORD_SYSTEMS:
        raise ValueError(
            f"coord_system 只能是 {COORD_SYSTEMS}，收到 {coord_system!r}"
        )

    if coord_system == "wgs84":
        lat, lng = wgs84_to_gcj02(lat, lng)
    return f"{lng:.6f},{lat:.6f}"