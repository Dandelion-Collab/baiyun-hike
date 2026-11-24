"""Streamlit 界面：只负责展示，判定逻辑全部在 app/ 里。"""

from __future__ import annotations

import os
from datetime import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from app.amap_js import build_map_html
from app.amap_map import static_map_png
from app.checker import TRANSPORT_LABELS, check
from app.dayroute import plan_day
from app.exceptions import ParseError
from app.gates import load_gates
from app.geolocate import COORD_SYSTEMS, amap_origin, distance_to_nearest_gate
from app.graph import load_graph
from app.mapview import render_route_svg
from app.parser import parse_itinerary
from app.poi import find_poi, load_poi
from app.presenter import format_issue, format_route, group_issues, summarize
from app.router import find_route
from app.route_amap import (
    ORIGIN_GATE_RADIUS_M,
    RoutePlan,
    arrival_times,
    plan as plan_amap,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
LEVEL_ROWS = (
    ("error", "必须改", True),
    ("warn", "建议调整", False),
    ("info", "仅供参考", False),
)
LIGHTING_LABELS = {"good": "有", "partial": "部分", "none": "无（注意安全）", "": "未知"}

WEB_KEY = os.environ.get("AMAP_KEY", "").strip()
JS_KEY = os.environ.get("AMAP_JS_KEY", "").strip()


def _to_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _fmt_minutes(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _coord(graph, node_id: str) -> str:
    node = graph.nodes[node_id]
    return f"{float(node['lng']):.6f},{float(node['lat']):.6f}"


def _origin_ready(user_origin: dict | None) -> bool:
    """定位结果是否足够支撑“我的位置”起点；缺字段时退回手动选门。"""
    if not user_origin:
        return False
    if user_origin.get("lat") is None or user_origin.get("lng") is None:
        return False
    if user_origin.get("coord_system") not in COORD_SYSTEMS:
        return False
    if not user_origin.get("gate"):
        return False
    return user_origin.get("km") is not None


def _offline_start(graph, start_id: str, user_origin: dict | None) -> str:
    """离线模式只认山门：若起点是"我的位置"，退到距离最近的那个门。"""
    if start_id != "__me__" or not user_origin:
        return start_id
    target = str(user_origin.get("gate") or "")
    for node_id, node in graph.nodes.items():
        if str(node.get("name")) == target and str(node.get("type")) == "gate":
            return node_id
    return "N01"


def _bbox(points: list[tuple[float, float]]) -> tuple[tuple[float, float], int]:
    if not points:
        return (113.303, 23.175), 16
    lngs = [float(point[0]) for point in points]
    lats = [float(point[1]) for point in points]
    span = max(max(lngs) - min(lngs), max(lats) - min(lats))
    if span < 0.01:
        zoom = 16
    elif span < 0.02:
        zoom = 15
    elif span < 0.05:
        zoom = 14
    else:
        zoom = 13
    return ((min(lngs) + max(lngs)) / 2, (min(lats) + max(lats)) / 2), zoom


def _gate_marker(gate: dict) -> dict:
    windows = str(gate["open_windows"])
    all_day = windows.startswith("00:00-24:00")
    return {
        "lnglat": (float(gate["lng"]), float(gate["lat"])),
        "title": str(gate["name"]) if all_day else f"{gate['name']} {windows}",
        "color": "#2ea043" if all_day else "#57606a",
    }


def _plan_gates(plan_result: RoutePlan) -> list[dict]:
    if not plan_result.gates_checked:
        return []
    wanted = set(plan_result.gates_checked)
    return [gate for gate in load_gates() if str(gate["id"]) in wanted]


def _render_segments(segments: list[dict], times: list[str], names: dict[str, str]) -> None:
    for segment, arrival in zip(segments, times):
        lighting = LIGHTING_LABELS.get(str(segment.get("lighting", "")), "未知")
        start = names.get(str(segment["from"]), str(segment["from"]))
        goal = names.get(str(segment["to"]), str(segment["to"]))
        st.write(
            f"{start} → {goal}　{segment['distance_m']} m　"
            f"约 {segment['walk_min']} 分钟　照明：{lighting}　→ {arrival}"
        )


def _render_day_map(itinerary) -> None:
    rows = load_poi()
    days: dict[str, list[tuple[str, tuple[float, float]]]] = {}
    for item in itinerary.items:
        poi = find_poi(item.name, rows)
        if poi is None:
            continue
        day = item.date or "未标注日期"
        days.setdefault(day, []).append(
            (str(item.name), (float(poi["lng"]), float(poi["lat"])))
        )
    if not days:
        return

    if len(days) > 1:
        day = st.selectbox("查看哪一天", list(days))
    else:
        day = next(iter(days))

    entries = days[day]
    markers = []
    for index, (name, lnglat) in enumerate(entries):
        if index == 0:
            color = "#2ea043"
        elif index == len(entries) - 1:
            color = "#d1242f"
        else:
            color = "#57606a"
        markers.append({"lnglat": lnglat, "title": name, "color": color})

    center, zoom = _bbox([lnglat for _, lnglat in entries])
    legs = []
    if len(entries) >= 2 and st.checkbox("把当天各站连成路线", key=f"day_route_{day}"):
        legs = plan_day(entries, key_available=bool(WEB_KEY))

    paths = []
    for leg in legs:
        if leg.real_path:
            paths.append(
                {"points": leg.polyline, "color": "#1f6feb", "weight": 5, "dashed": False}
            )
        else:
            paths.append(
                {"points": leg.polyline, "color": "#9aa0a6", "weight": 3, "dashed": True}
            )

    html = build_map_html(center=center, zoom=zoom, paths=paths, markers=markers)
    if html:
        st.caption(f"{day} 行程点地图（底图：高德）")
        components.html(html, height=480)

    for leg in legs:
        mode = TRANSPORT_LABELS.get(leg.mode, leg.mode)
        kind = "真实路径" if leg.real_path else "直线估算"
        st.write(
            f"{leg.from_name} → {leg.to_name}　{mode}　{leg.distance_m} m　"
            f"约 {leg.minutes} 分钟　（{kind}）"
        )


def _render_plan_text(plan_result: RoutePlan | None, names: dict[str, str]) -> None:
    if plan_result is None:
        st.info("当前没有高德规划结果。")
        return

    if plan_result.reachable:
        transfer = (
            plan_result.legs[0]
            if plan_result.legs and plan_result.legs[0].get("mode") == "amap"
            else None
        )
        transfer_min = int(transfer["minutes"]) if transfer else 0
        internal_min = sum(int(segment["walk_min"]) for segment in plan_result.segments)
        st.success(
            f"全程约 {plan_result.total_min} 分钟（接驳 {transfer_min} + 内部 {internal_min}），"
            f"{plan_result.distance_m / 1000:.1f} 公里"
        )

        times = arrival_times(plan_result.depart_at, plan_result.legs, plan_result.segments)
        if transfer:
            st.write(
                f"起点 → {transfer['to']}　{transfer['distance_m']} m　"
                f"约 {transfer_min} 分钟　（高德接驳）　→ {times[0]}"
            )
            segment_times = times[1:]
        else:
            segment_times = times
        _render_segments(plan_result.segments, segment_times, names)

        for line in plan_result.advice:
            st.info(line)
    else:
        st.error(plan_result.reason or "当前时段没有可行方案")
        for line in plan_result.advice:
            st.info(line)


def _render_offline(graph, start_id: str, goal_id: str, depart_at: str) -> None:
    route = find_route(graph, start_id, goal_id, depart_at)
    names = {node_id: str(node["name"]) for node_id, node in graph.nodes.items()}
    view = format_route(route, names)

    if route.reachable:
        route_path = route.path
        blocked_at = None
        blocked_node_id = None
    else:
        route_path = route.fallback.farthest_path if route.fallback else []
        blocked_at = route.blocked_at or route.reason
        blocked_node_id = start_id if not route_path else None

    svg = render_route_svg(
        graph.nodes,
        route_path,
        graph.edges,
        reachable=route.reachable,
        blocked_at=blocked_at,
        blocked_node_id=blocked_node_id,
    )
    components.html(svg, height=440)

    if route.reachable:
        st.success(view["headline"])
        segments = [
            {
                "from": leg.from_node,
                "to": leg.to_node,
                "distance_m": leg.distance_m,
                "walk_min": leg.walk_min,
                "lighting": leg.lighting or "",
            }
            for leg in route.legs
        ]
        times = arrival_times(depart_at, [], segments)
        _render_segments(segments, times, names)
        if view["notice"]:
            st.warning("；".join(view["notice"]))
    else:
        st.error(view["headline"])
        for line in view["notice"]:
            if line.startswith("最远"):
                st.warning(line)
            elif line.startswith("卡在"):
                st.error(line)
            else:
                st.info(line)


st.set_page_config(
    page_title="广州旅行助手 · 行程体检与白云山夜爬",
    page_icon="🥾",
    layout="wide",
)
st.title("广州旅行助手 · 行程体检与白云山夜爬")
st.caption("只做可行性检查与白云山夜爬路线提示，不生成旅游攻略。")

graph = load_graph()
node_ids = list(graph.nodes)
node_names = {node_id: str(graph.nodes[node_id]["name"]) for node_id in node_ids}

tab_check, tab_route = st.tabs(["行程体检", "白云山夜爬"])

with tab_check:
    demo_text = (DATA_DIR / "demo_itinerary.txt").read_text(encoding="utf-8")

    def _fill_demo_itinerary() -> None:
        st.session_state["itinerary_text"] = demo_text

    if "itinerary_text" not in st.session_state:
        st.session_state["itinerary_text"] = demo_text
    itinerary_text = st.text_area(
        "把排好的行程贴在这里", key="itinerary_text", height=320
    )

    demo_col, check_col = st.columns(2)
    demo_col.button("填入示例行程", on_click=_fill_demo_itinerary)
    start_check = check_col.button("开始体检", type="primary")

    if start_check:
        try:
            itinerary = parse_itinerary(itinerary_text)
        except ParseError as exc:
            st.session_state["check_error"] = str(exc)
            st.session_state.pop("check_result", None)
        else:
            st.session_state["check_error"] = None
            st.session_state["check_result"] = (itinerary, check(itinerary))

    check_error = st.session_state.get("check_error")
    if check_error:
        st.error(f"没能读懂这段行程：{check_error}。请按「上午 9:00 地点」的格式再试一次。")
    elif "check_result" in st.session_state:
        itinerary, issues = st.session_state["check_result"]
        _render_day_map(itinerary)
        if not issues:
            st.success(
                "这一天的安排没发现问题，按计划出发即可；具体开放时间与票价仍以现场公告为准。"
            )
        else:
            st.info(summarize(issues))
            groups = group_issues(issues)
            for level, title, expanded in LEVEL_ROWS:
                bucket = groups[level]
                with st.expander(f"{title}（{len(bucket)} 条）", expanded=expanded):
                    if not bucket:
                        st.caption("没有这一类的提示。")
                    for issue in bucket:
                        view = format_issue(issue)
                        st.markdown(f"**{view['title']}**")
                        st.write(view["detail"])
                        if view["suggest"]:
                            st.caption(f"建议：{view['suggest']}")

with tab_route:
    mode_slot = st.empty()
    if WEB_KEY and JS_KEY:
        default_mode = "高德交互地图"
    elif WEB_KEY:
        default_mode = "高德静态图"
    else:
        default_mode = "示意图（离线）"
    mode_slot.caption(f"规划方式：{default_mode}")

    columns = st.columns([1.1, 1.1, 1, 1.3])
    with columns[3]:
        st.caption("用当前位置作起点")
        _geo_path = Path(__file__).resolve().parent / "components" / "geolocator" / "index.html"
        if _geo_path.exists():
            components.html(_geo_path.read_text(encoding="utf-8"), height=140)
        st.caption(
            "组件定位结果是 WGS84，需复制到下方输入框并把坐标系选为 WGS84——"
            "组件是沙箱 iframe，浏览器不会把坐标自动交回页面。"
        )
        coord_options = {
            "GCJ02（高德/腾讯地图）": "gcj02",
            "WGS84（浏览器定位）": "wgs84",
        }
        coord_label = st.radio(
            "坐标系",
            list(coord_options),
            index=0,
            horizontal=True,
            key="user_coord_system",
        )
        coord_system = coord_options[coord_label]
        coord_text = st.text_input(
            "填入坐标（纬度,经度）",
            key="user_coord_text",
            placeholder="纬度,经度，例如 23.1291,113.2644",
            label_visibility="collapsed",
        )
        st.caption(
            "从高德/腾讯地图抄的坐标选 GCJ02；浏览器定位得到的坐标选 WGS84。"
        )
        if st.button("使用这个位置", key="use_user_coord"):
            raw = (coord_text or "").replace("，", ",").strip()
            parts = [part.strip() for part in raw.split(",") if part.strip()]
            if len(parts) != 2:
                st.caption("格式不对，应为「纬度,经度」，例如 23.1291,113.2644")
            else:
                try:
                    lat_u, lng_u = float(parts[0]), float(parts[1])
                except ValueError:
                    st.caption("坐标不是数字，请检查后再试。")
                else:
                    if abs(lat_u) > 90 or abs(lng_u) > 180:
                        st.caption("纬度需在 -90~90，经度在 -180~180。")
                    else:
                        gate_name, km, at_gate = distance_to_nearest_gate(
                            lat_u,
                            lng_u,
                            ORIGIN_GATE_RADIUS_M,
                            coord_system=coord_system,
                        )
                        if not gate_name or km == float("inf"):
                            st.session_state.pop("user_origin", None)
                            st.session_state["start_select"] = "N01"
                            st.caption("附近没有可用的山门数据，已退回手动选门。")
                        else:
                            st.session_state["user_origin"] = {
                                "lat": lat_u,
                                "lng": lng_u,
                                "coord_system": coord_system,
                                "gate": gate_name,
                                "km": km,
                                "at_gate": at_gate,
                            }
                            st.session_state["start_select"] = "__me__"
                            if at_gate:
                                st.caption(f"已在{gate_name}门口（免接驳）")
                            else:
                                st.caption(f"距{gate_name} {km:.1f} 公里（需接驳）")

    user_origin = st.session_state.get("user_origin")
    if user_origin and not _origin_ready(user_origin):
        st.session_state.pop("user_origin", None)
        user_origin = None
        st.caption("定位信息不完整（缺少最近山门），已退回手动选门。")
    start_options = (["__me__"] if user_origin else []) + list(node_ids)

    def _label(option: str) -> str:
        if option == "__me__":
            assert user_origin is not None
            gate = str(user_origin.get("gate") or "")
            km = user_origin.get("km")
            if not gate or km is None:
                return "我的位置（缺少山门信息，请手动选门）"
            if user_origin.get("at_gate"):
                return f"我的位置（已在{gate}门口，免接驳）"
            return f"我的位置（距{gate} {float(km):.1f} 公里，需接驳）"
        return node_names[option]

    if st.session_state.get("start_select") not in start_options:
        st.session_state["start_select"] = "N01"

    start_id = columns[0].selectbox(
        "起点",
        start_options,
        key="start_select",
        format_func=_label,
    )
    goal_id = columns[1].selectbox(
        "终点",
        node_ids,
        index=node_ids.index("N10"),
        format_func=lambda node_id: node_names[node_id],
    )
    depart_time = columns[2].time_input("出发时间", value=time(22, 0))

    if st.button("规划路线", type="primary"):
        depart_text = depart_time.strftime("%H:%M")
        plan_result: RoutePlan | None = None
        start_label = "我的位置" if start_id == "__me__" else node_names[start_id]

        if start_id == "__me__" and user_origin:
            origin = amap_origin(
                user_origin["lat"],
                user_origin["lng"],
                user_origin["coord_system"],
            )
            km = user_origin.get("km")
            if km is not None and float(km) > 50:
                st.warning(
                    f"你离白云山约 {float(km):.0f} 公里，接驳段会很长；也可以直接在左侧选一个山门。"
                )
        else:
            origin = _coord(graph, start_id)

        if WEB_KEY:
            plan_result = plan_amap(origin, goal_id, depart_text)
            html = None
            if JS_KEY:
                polyline = plan_result.polyline
                paths = (
                    [{"points": polyline, "color": "#1f6feb", "weight": 5, "dashed": False}]
                    if polyline
                    else []
                )
                markers = []
                if polyline:
                    markers.append(
                        {"lnglat": polyline[0], "title": start_label, "color": "#2ea043"}
                    )
                    markers.append(
                        {"lnglat": polyline[-1], "title": node_names[goal_id], "color": "#d1242f"}
                    )
                for gate in _plan_gates(plan_result):
                    markers.append(_gate_marker(gate))
                center, zoom = _bbox(polyline)
                html = build_map_html(
                    center=center, zoom=zoom, paths=paths, markers=markers
                )

            if html:
                mode_slot.caption("规划方式：高德交互地图")
                components.html(html, height=480)
                _render_plan_text(plan_result, node_names)
            else:
                png = static_map_png(plan_result.polyline) if plan_result.polyline else None
                if png:
                    mode_slot.caption("规划方式：高德静态图")
                    st.image(png, caption="底图：高德静态地图")
                    _render_plan_text(plan_result, node_names)
                else:
                    try:
                        mode_slot.caption("规划方式：示意图（离线）")
                        _render_offline(graph, _offline_start(graph, start_id, user_origin), goal_id, depart_text)
                    except Exception:
                        _render_plan_text(plan_result, node_names)
        else:
            try:
                _render_offline(graph, _offline_start(graph, start_id, user_origin), goal_id, depart_text)
            except Exception:
                st.warning("当前无法生成示意图，请检查数据文件后再试。")

st.divider()
st.caption(
    "地图只作路线示意；数据于 2026 年 11 月整理，门禁与开放时间以景区公告为准；"
    "本页面只做可行性检查，不构成登山安全建议，夜间出行请结伴并留意现场公告。"
)