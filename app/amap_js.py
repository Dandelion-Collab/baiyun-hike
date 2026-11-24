"""高德 JS API 交互地图：纯函数返回 HTML；缺 Key 返回 None。

图层用 AMap.plugin 异步加载，整段初始化包 try/catch，并用 window.onerror 兜底，
避免任一图层构造失败导致整页白屏。
"""

from __future__ import annotations

import json
import os
import urllib.parse

DEFAULT_HEIGHT = 460
FALLBACK_TEXT = "地图加载失败，已切换静态图"


def build_map_html(
    *,
    center: tuple[float, float],
    zoom: int,
    paths: list[dict],
    markers: list[dict],
    height: int = DEFAULT_HEIGHT,
) -> str | None:
    key = os.environ.get("AMAP_JS_KEY", "").strip()
    security = os.environ.get("AMAP_SECURITY_CODE", "").strip()
    if not key or not security:
        return None

    path_payload = [
        {
            "points": [[float(lng), float(lat)] for lng, lat in path.get("points", [])],
            "color": str(path.get("color", "#1f6feb")),
            "weight": int(path.get("weight", 5)),
            "dashed": bool(path.get("dashed", False)),
        }
        for path in paths
    ]
    marker_payload = [
        {
            "lnglat": [float(marker["lnglat"][0]), float(marker["lnglat"][1])],
            "title": str(marker.get("title", "")),
            "color": str(marker.get("color", "#57606a")),
        }
        for marker in markers
    ]

    key_param = urllib.parse.quote(key, safe="")
    security_js = json.dumps(security).replace("</", "<\\/")
    center_js = json.dumps([float(center[0]), float(center[1])])
    paths_js = json.dumps(path_payload, ensure_ascii=False).replace("</", "<\\/")
    markers_js = json.dumps(marker_payload, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
html, body, #map {{ height: 100%; margin: 0; }}
#fallback {{ display: none; padding: 24px; font-family: system-ui, sans-serif; color: #d1242f; }}
</style>
<script>window._AMapSecurityConfig = {{securityJsCode: {security_js}}};</script>
<script>
window.onerror = function () {{
  var box = document.getElementById("fallback");
  if (box) {{
    box.style.display = "block";
    box.textContent = "{FALLBACK_TEXT}";
  }}
  return false;
}};
</script>
</head>
<body>
<div id="map" style="width:100%;height:{int(height)}px"></div>
<div id="fallback">{FALLBACK_TEXT}</div>
<script src="https://webapi.amap.com/maps?v=2.0&key={key_param}"></script>
<script>
function showFallback() {{
  var box = document.getElementById("fallback");
  if (box) {{
    box.style.display = "block";
    box.textContent = "{FALLBACK_TEXT}";
  }}
}}
try {{
  var map = new AMap.Map("map", {{
    center: {center_js},
    zoom: {int(zoom)}
  }});
  AMap.plugin(["AMap.TileLayer.Satellite", "AMap.TileLayer.RoadNet"], function () {{
    try {{
      map.add([new AMap.TileLayer.Satellite(), new AMap.TileLayer.RoadNet()]);
    }} catch (layerError) {{
      showFallback();
    }}
    var paths = {paths_js};
    paths.forEach(function (item) {{
      var line = new AMap.Polyline({{
        path: item.points,
        strokeColor: item.color,
        strokeWeight: item.weight,
        strokeStyle: item.dashed ? "dashed" : "solid"
      }});
      line.setMap(map);
    }});
    var markers = {markers_js};
    markers.forEach(function (item) {{
      var marker = new AMap.Marker({{
        position: item.lnglat,
        title: item.title,
        content: '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + item.color + ';"></span>',
        label: {{ content: item.title, direction: "top" }}
      }});
      marker.setMap(map);
    }});

  }});
}} catch (error) {{
  showFallback();
}}
</script>
</body>
</html>
"""