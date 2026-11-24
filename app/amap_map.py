"""高德静态地图：真底图 + 路线 + 起终点；失败返回 None，由上层降级。"""

from __future__ import annotations

import hashlib
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

STATIC_URL = "https://restapi.amap.com/v3/staticmap"
TIMEOUT_SECONDS = 6
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_POINTS = 40
DEFAULT_SIZE = (600, 420)
DEFAULT_SCALE = 2
CACHE_DIR = Path(__file__).resolve().parents[1] / "logs" / "staticmap"
COLOR_PATH = "6,0x1f6feb,1,,:"
MARKER_START = "mid,0x2ea043,A:"
MARKER_END = "mid,0xd1242f,B:"
PNG_MAGIC = b"\x89PNG"
ZOOM_RULES = ((0.01, 15), (0.02, 14), (0.05, 13))


def _key() -> str:
    return os.environ.get("AMAP_KEY", "").strip()


def _centroid_and_zoom(points: list[tuple[float, float]]) -> tuple[tuple[float, float], int]:
    lngs = [float(point[0]) for point in points]
    lats = [float(point[1]) for point in points]
    min_lng, max_lng = min(lngs), max(lngs)
    min_lat, max_lat = min(lats), max(lats)
    span = max(max_lng - min_lng, max_lat - min_lat)
    zoom = 12
    for limit, value in ZOOM_RULES:
        if span < limit:
            zoom = value
            break
    return ((min_lng + max_lng) / 2, (min_lat + max_lat) / 2), zoom


def _thin(
    points: list[tuple[float, float]], limit: int = MAX_POINTS
) -> list[tuple[float, float]]:
    if len(points) <= limit:
        return list(points)
    step = len(points) / limit
    picked = [points[int(index * step)] for index in range(limit)]
    picked[-1] = points[-1]
    return picked


def build_static_map_url(
    points: list[tuple[float, float]],
    *,
    size: tuple[int, int] = DEFAULT_SIZE,
    scale: int = DEFAULT_SCALE,
    key: str = "",
) -> str:
    center, zoom = _centroid_and_zoom(points)
    thinned = _thin(points)
    path = ";".join(f"{float(lng):.6f},{float(lat):.6f}" for lng, lat in thinned)
    width, height = size
    query = [
        ("key", key),
        ("location", f"{center[0]:.6f},{center[1]:.6f}"),
        ("zoom", str(zoom)),
        ("size", f"{width}*{height}"),
        ("scale", str(scale)),
        ("paths", f"{COLOR_PATH}{path}"),
        ("markers", f"{MARKER_START}{float(points[0][0]):.6f},{float(points[0][1]):.6f}"),
        ("markers", f"{MARKER_END}{float(points[-1][0]):.6f},{float(points[-1][1]):.6f}"),
    ]
    return f"{STATIC_URL}?{urllib.parse.urlencode(query)}"


def _cache_file(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.png"


def static_map_png(
    points: list[tuple[float, float]],
    *,
    size: tuple[int, int] = DEFAULT_SIZE,
    scale: int = DEFAULT_SCALE,
) -> bytes | None:
    if not points:
        return None
    key = _key()
    if not key:
        return None

    url = build_static_map_url(points, size=size, scale=scale, key=key)
    cache_file = _cache_file(url)
    if cache_file.exists():
        try:
            if time.time() - cache_file.stat().st_mtime <= CACHE_TTL_SECONDS:
                return cache_file.read_bytes()
        except OSError:
            pass

    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read()
    except OSError:
        return None

    if not payload or not payload.startswith(PNG_MAGIC):
        return None

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(payload)
    except OSError:
        pass
    return payload