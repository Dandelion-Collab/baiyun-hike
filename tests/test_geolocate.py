"""坐标换算测试：WGS84→GCJ02、最近山门与半径口径。"""

from __future__ import annotations

import math

from app import geolocate, route_amap


def _distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * geolocate.EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def test_wgs84_to_gcj02_tiananmen_offset() -> None:
    lat, lng = geolocate.wgs84_to_gcj02(39.9087, 116.3975)

    moved = _distance_m(39.9087, 116.3975, lat, lng)

    assert 300 <= moved <= 700


def test_wgs84_to_gcj02_outside_china_identity() -> None:
    lat, lng = geolocate.wgs84_to_gcj02(35.6762, 139.6503)

    assert _distance_m(35.6762, 139.6503, lat, lng) < 1


def test_distance_to_nearest_gate_south_gate() -> None:
    # 南门节点是 GCJ-02（23.159042,113.296288），这里给对应的 WGS84 输入。
    name, km, at_gate = geolocate.distance_to_nearest_gate(23.161679, 113.290926)

    assert "南门" in name
    assert km < 0.05
    assert at_gate is True


def test_distance_to_nearest_gate_beijing_road() -> None:
    name, km, at_gate = geolocate.distance_to_nearest_gate(23.1291, 113.2644)

    assert "南门" in name
    assert 3 <= km <= 8
    assert at_gate is False


def test_distance_to_nearest_gate_gcj02_direct_south_gate() -> None:
    # 南门节点本身就是 GCJ-02；直传时不应再做转换。
    name, km, at_gate = geolocate.distance_to_nearest_gate(
        23.159042, 113.296288, coord_system="gcj02"
    )

    assert "南门" in name
    assert km < 0.05
    assert at_gate is True


def test_distance_to_nearest_gate_wgs84_same_point_south_gate() -> None:
    # 同一地理位置的 WGS84 坐标，转换后也应落在南门门口。
    name, km, at_gate = geolocate.distance_to_nearest_gate(
        23.161679, 113.290926, coord_system="wgs84"
    )

    assert "南门" in name
    assert km < 0.05
    assert at_gate is True


def test_distance_to_nearest_gate_rejects_unknown_coord_system() -> None:
    try:
        geolocate.distance_to_nearest_gate(23.1, 113.2, coord_system="bd09")
    except ValueError:
        return
    raise AssertionError("未知坐标系应当抛 ValueError")


def test_distance_to_nearest_gate_radius_threshold() -> None:
    name, km, at_gate = geolocate.distance_to_nearest_gate(23.1291, 113.2644, 120)
    assert name == "白云山南门"
    assert at_gate is False

    _, _, wide = geolocate.distance_to_nearest_gate(23.1291, 113.2644, 10_000)
    assert wide is True


def test_gate_radius_matches_route_amap() -> None:
    assert geolocate.DEFAULT_GATE_RADIUS_M == route_amap.ORIGIN_GATE_RADIUS_M