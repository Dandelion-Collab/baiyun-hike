"""高德封装测试：无 Key、响应解析与缓存。"""

from __future__ import annotations

import json

import pytest

import app.amap as amap

PAYLOAD = {
    "status": "1",
    "route": {
        "paths": [
            {
                "distance": "1234.0",
                "duration": "900",
                "steps": [{"polyline": "113.2900,23.1800;113.3000,23.1900"}],
            }
        ]
    },
}


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_missing_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("AMAP_KEY", raising=False)

    with pytest.raises(amap.MissingKeyError):
        amap.walking_route("113.29,23.18", "113.30,23.19")


def test_parse_walking_response(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AMAP_KEY", "test-key")
    monkeypatch.setattr(amap, "CACHE_PATH", tmp_path / "cache.json")

    def fake_urlopen(url, timeout=0):
        return _FakeResponse(PAYLOAD)

    monkeypatch.setattr(amap.urllib.request, "urlopen", fake_urlopen)

    route = amap.walking_route("113.29,23.18", "113.30,23.19")

    assert route.distance_m == 1234
    assert route.duration_min == 15
    assert len(route.polyline) == 2
    assert route.polyline[0] == (113.29, 23.18)


def test_cache_hits_only_once(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AMAP_KEY", "test-key")
    monkeypatch.setattr(amap, "CACHE_PATH", tmp_path / "cache.json")
    calls = []

    def fake_urlopen(url, timeout=0):
        calls.append(url)
        return _FakeResponse(PAYLOAD)

    monkeypatch.setattr(amap.urllib.request, "urlopen", fake_urlopen)

    first = amap.walking_route("113.29,23.18", "113.30,23.19")
    second = amap.walking_route("113.29,23.18", "113.30,23.19")

    assert len(calls) == 1
    assert first.distance_m == second.distance_m == 1234