"""高德 Web 服务封装：步行路径规划。

Key 只在真正发起请求时读取，缺失抛 MissingKeyError，import 本模块不会崩。
请求失败重试 1 次；结果按（起点, 终点, 策略, 出发小时）缓存 7 天。
异常信息不拼接请求 URL，避免把 Key 带进日志。
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

AMAP_URL = "https://restapi.amap.com/v3/direction/walking"
TIMEOUT_SECONDS = 3
RETRY_TIMES = 1
SECONDS_PER_MINUTE = 60
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_PATH = Path(__file__).resolve().parents[1] / "logs" / "amap_cache.json"


class MissingKeyError(RuntimeError):
    """未配置 AMAP_KEY。"""


class AmapError(RuntimeError):
    """高德接口调用失败。"""

    def __init__(self, message: str, *, status: str = "", info: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.info = info


@dataclass
class AmapRoute:
    distance_m: int
    duration_min: int
    steps: list[dict] = field(default_factory=list)
    polyline: list[tuple[float, float]] = field(default_factory=list)


def _key() -> str:
    key = os.environ.get("AMAP_KEY", "").strip()
    if not key:
        raise MissingKeyError("未配置 AMAP_KEY，请设置环境变量后重试")
    return key


def _parse_polyline(text: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for chunk in str(text).split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(",")
        if len(parts) != 2:
            continue
        try:
            lng, lat = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        points.append((lng, lat))
    return points


def _parse_route(payload: dict) -> AmapRoute:
    paths = (payload.get("route") or {}).get("paths") or []
    if not paths:
        raise AmapError(
            "高德未返回步行路径",
            status=str(payload.get("status", "")),
            info=str(payload.get("info", "")),
        )

    path = paths[0]
    steps = path.get("steps") or []
    polyline: list[tuple[float, float]] = []
    for step in steps:
        polyline.extend(_parse_polyline(str(step.get("polyline", ""))))

    distance_m = int(float(path.get("distance", 0) or 0))
    duration_sec = int(float(path.get("duration", 0) or 0))
    duration_min = max(1, round(duration_sec / SECONDS_PER_MINUTE))
    return AmapRoute(
        distance_m=distance_m,
        duration_min=duration_min,
        steps=steps,
        polyline=polyline,
    )


def _cache_key(origin: str, dest: str, strategy: int, depart_hour: str) -> str:
    return f"{origin}|{dest}|{strategy}|{depart_hour}"


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def _route_to_cache(route: AmapRoute) -> dict:
    return {
        "distance_m": route.distance_m,
        "duration_min": route.duration_min,
        "steps": route.steps,
        "polyline": [[lng, lat] for lng, lat in route.polyline],
    }


def _route_from_cache(data: dict) -> AmapRoute:
    return AmapRoute(
        distance_m=int(data.get("distance_m", 0)),
        duration_min=int(data.get("duration_min", 0)),
        steps=list(data.get("steps", [])),
        polyline=[(float(lng), float(lat)) for lng, lat in data.get("polyline", [])],
    )


def walking_route(
    origin: str,
    dest: str,
    strategy: int = 0,
    city: str = "广州",
) -> AmapRoute:
    """规划步行路线；成功返回 AmapRoute，失败抛 AmapError。"""

    key = _key()
    depart_hour = time.strftime("%Y%m%d%H")
    cache_key = _cache_key(origin, dest, strategy, depart_hour)
    cache = _load_cache()
    entry = cache.get(cache_key)
    if entry and time.time() - float(entry.get("saved_at", 0)) <= CACHE_TTL_SECONDS:
        cached = entry.get("route") or {}
        if cached:
            return _route_from_cache(cached)

    query = urllib.parse.urlencode(
        {
            "key": key,
            "origin": origin,
            "destination": dest,
            "strategy": strategy,
            "city": city,
        }
    )
    url = f"{AMAP_URL}?{query}"

    payload: dict | None = None
    last_error: Exception | None = None
    for _ in range(RETRY_TIMES + 1):
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except (OSError, ValueError) as exc:
            last_error = exc

    if payload is None:
        raise AmapError(f"高德请求失败：{type(last_error).__name__}")

    if str(payload.get("status", "")) != "1":
        raise AmapError(
            f"高德返回失败：{payload.get('info', '')}",
            status=str(payload.get("status", "")),
            info=str(payload.get("info", "")),
        )

    route = _parse_route(payload)
    cache[cache_key] = {"saved_at": time.time(), "route": _route_to_cache(route)}
    _save_cache(cache)
    return route

STATIC_URL = "https://restapi.amap.com/v3/staticmap"
STATIC_MAX_POINTS = 100


def _thin(points: list[tuple[float, float]], limit: int) -> list[tuple[float, float]]:
    if len(points) <= limit:
        return points
    step = max(1, len(points) // limit)
    thinned = points[::step]
    if thinned[-1] != points[-1]:
        thinned.append(points[-1])
    return thinned


def static_map(
    polyline: list[tuple[float, float]],
    gates: list[dict] | None = None,
    size: str = "750*460",
) -> bytes | None:
    """用高德静态图接口渲染 PNG；失败返回 None，由调用方退回离线示意图。"""

    if not polyline:
        return None

    key = _key()
    points = _thin(polyline, STATIC_MAX_POINTS)
    path = ";".join(f"{lng:.6f},{lat:.6f}" for lng, lat in points)
    params: dict[str, str] = {
        "key": key,
        "size": size,
        "scale": "2",
        "paths": f"8,0x1f6feb,1,,{path}",
    }
    if gates:
        params["markers"] = "|".join(
            f"mid,0xd1242f,{float(gate['lng']):.6f},{float(gate['lat']):.6f}"
            for gate in gates
        )

    url = f"{STATIC_URL}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            return response.read()
    except OSError:
        return None