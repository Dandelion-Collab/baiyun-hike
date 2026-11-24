"""静态地图测试：URL 参数、抽稀与缓存，全部离线。"""

from __future__ import annotations

import urllib.parse

import app.amap_map as amap_map

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_url_center_and_zoom() -> None:
    points = [(113.296, 23.159), (113.303, 23.175)]

    url = amap_map.build_static_map_url(points, key="test-key")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)

    assert query["location"] == ["113.299500,23.167000"]
    assert query["zoom"] == ["14"]
    assert query["size"] == ["600*420"]
    assert query["scale"] == ["2"]
    assert len(query["markers"]) == 2


def test_points_are_thinned_to_limit() -> None:
    points = [(113.29 + index * 0.0001, 23.18) for index in range(50)]

    thinned = amap_map._thin(points)

    assert len(thinned) == 40
    assert thinned[0] == points[0]
    assert thinned[-1] == points[-1]


def test_cache_hits_only_once(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AMAP_KEY", "test-key")
    monkeypatch.setattr(amap_map, "CACHE_DIR", tmp_path / "staticmap")
    calls = []

    def fake_urlopen(url, timeout=0):
        calls.append(url)
        return _FakeResponse(PNG)

    monkeypatch.setattr(amap_map.urllib.request, "urlopen", fake_urlopen)

    points = [(113.296, 23.159), (113.303, 23.175)]
    first = amap_map.static_map_png(points)
    second = amap_map.static_map_png(points)

    assert first == PNG
    assert second == PNG
    assert len(calls) == 1