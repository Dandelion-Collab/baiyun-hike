"""高德 JS 地图测试：缺 Key、结构、坐标数组、转义与图层加载方式，全部离线。"""

from __future__ import annotations

import app.amap_js as amap_js


def _build(**overrides):
    params = {
        "center": (113.30, 23.17),
        "zoom": 14,
        "paths": [
            {
                "points": [(113.29, 23.15), (113.30, 23.16), (113.31, 23.17)],
                "color": "#1f6feb",
                "weight": 5,
                "dashed": False,
            }
        ],
        "markers": [{"lnglat": (113.29, 23.15), "title": "南门", "color": "#2ea043"}],
    }
    params.update(overrides)
    return amap_js.build_map_html(**params)


def test_missing_env_returns_none(monkeypatch) -> None:
    monkeypatch.delenv("AMAP_JS_KEY", raising=False)
    monkeypatch.delenv("AMAP_SECURITY_CODE", raising=False)

    assert _build() is None


def test_html_contains_required_scripts(monkeypatch) -> None:
    monkeypatch.setenv("AMAP_JS_KEY", "js-key")
    monkeypatch.setenv("AMAP_SECURITY_CODE", "sec-code")

    html = _build()

    assert html is not None
    assert "window._AMapSecurityConfig" in html
    assert "v=2.0&key=js-key" in html
    assert "AMap.Polyline" in html
    assert "zoom: 14" in html
    assert "setFitView" not in html


def test_points_are_json_arrays(monkeypatch) -> None:
    monkeypatch.setenv("AMAP_JS_KEY", "js-key")
    monkeypatch.setenv("AMAP_SECURITY_CODE", "sec-code")

    html = _build()

    assert html is not None
    assert "[113.29, 23.15]" in html
    assert "[113.31, 23.17]" in html


def test_security_code_is_escaped(monkeypatch) -> None:
    monkeypatch.setenv("AMAP_JS_KEY", "js-key")
    monkeypatch.setenv("AMAP_SECURITY_CODE", 'a"b')

    html = _build()

    assert html is not None
    assert 'a"b' not in html
    assert 'a\\"b' in html


def test_layers_use_plugin_and_no_3d(monkeypatch) -> None:
    monkeypatch.setenv("AMAP_JS_KEY", "js-key")
    monkeypatch.setenv("AMAP_SECURITY_CODE", "sec-code")

    html = _build()

    assert html is not None
    assert "AMap.plugin" in html
    assert 'viewMode: "3D"' not in html
    assert "amap://styles/normal" not in html


def test_has_try_catch_and_onerror(monkeypatch) -> None:
    monkeypatch.setenv("AMAP_JS_KEY", "js-key")
    monkeypatch.setenv("AMAP_SECURITY_CODE", "sec-code")

    html = _build()

    assert html is not None
    assert "try {" in html
    assert "catch" in html
    assert "window.onerror" in html
    assert "地图加载失败，已切换静态图" in html