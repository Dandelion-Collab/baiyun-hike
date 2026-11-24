"""路线示意图测试：SVG 结构、颜色、叉号、画布边界与标签避让。"""

from __future__ import annotations

import re

from app.graph import load_graph
from app.mapview import render_route_svg
from app.router import find_route

NODES = {
    "A": {"id": "A", "name": "起点站", "lat": 23.1800, "lng": 113.2900},
    "B": {"id": "B", "name": "中段站", "lat": 23.1900, "lng": 113.3000},
    "C": {"id": "C", "name": "终点站", "lat": 23.1700, "lng": 113.3100},
}
EDGES = [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}]


def _svg(path=None, reachable=True, blocked_at=None):
    return render_route_svg(
        NODES,
        path or ["A", "B", "C"],
        EDGES,
        reachable=reachable,
        blocked_at=blocked_at,
    )


def _label_rects(svg: str) -> list[tuple[float, float, float, float, str]]:
    rects = []
    pattern = r'<text x="([\d.]+)" y="([\d.]+)" font-size="12"[^>]*text-anchor="(\w+)"[^>]*>([^<]+)</text>'
    for match in re.finditer(pattern, svg):
        x, y, anchor, label = float(match.group(1)), float(match.group(2)), match.group(3), match.group(4)
        width = len(label) * 12
        if anchor == "start":
            left = x
        elif anchor == "end":
            left = x - width
        else:
            left = x - width / 2
        rects.append((left, y - 12, width, 15, label))
    return rects


def _intersects(a, b) -> bool:
    return (
        a[0] < b[0] + b[2]
        and a[0] + a[2] > b[0]
        and a[1] < b[1] + b[3]
        and a[1] + a[3] > b[1]
    )


def test_svg_envelope_and_viewbox() -> None:
    svg = _svg()

    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert "viewBox" in svg


def test_all_path_names_rendered() -> None:
    svg = _svg()

    for name in ("起点站", "中段站", "终点站"):
        assert name in svg


def test_start_and_end_colors_differ() -> None:
    svg = _svg()

    assert "#2ea043" in svg
    assert "#d1242f" in svg


def test_unreachable_has_cross_and_note() -> None:
    svg = _svg(path=["A", "B"], reachable=False, blocked_at="21:30 关闭，无法继续")

    assert "blocked-cross" in svg
    assert "21:30 关闭" in svg


def test_all_circles_inside_canvas() -> None:
    svg = _svg()
    coords = re.findall(r'<circle[^>]*cx="([\d.]+)"[^>]*cy="([\d.]+)"', svg)

    assert coords
    for cx, cy in coords:
        assert 0 <= float(cx) <= 760
        assert 0 <= float(cy) <= 460


def test_svg_is_responsive_and_760x460() -> None:
    svg = _svg()

    assert 'viewBox="0 0 760 460"' in svg
    assert 'width="100%"' in svg
    assert 'height="100%"' in svg


def test_legend_present() -> None:
    svg = _svg()

    for word in ("起点", "终点", "路线", "其他路段", "卡点"):
        assert word in svg


def test_real_map_labels_do_not_overlap() -> None:
    graph = load_graph()
    route = find_route(graph, "N01", "N10", "19:00")
    svg = render_route_svg(graph.nodes, route.path, graph.edges, reachable=True)

    rects = _label_rects(svg)
    assert len(rects) >= 10

    overlaps = [
        (a[4], b[4])
        for index, a in enumerate(rects)
        for b in rects[index + 1:]
        if _intersects(a, b)
    ]
    assert overlaps == []

def test_blocked_node_id_anchors_cross() -> None:
    svg = render_route_svg(
        NODES, [], EDGES, reachable=False, blocked_at="进不去", blocked_node_id="A"
    )

    circles = re.findall(r'<circle[^>]*cx="([\d.]+)"[^>]*cy="([\d.]+)"', svg)
    ax, ay = float(circles[0][0]), float(circles[0][1])

    cross = re.search(r'<g id="blocked-cross".*?</g>', svg, re.S)
    assert cross
    lines = re.findall(
        r'<line x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)"',
        cross.group(0),
    )
    assert len(lines) == 2
    bx = (float(lines[0][0]) + float(lines[0][2])) / 2
    by = (float(lines[0][1]) + float(lines[0][3])) / 2

    assert abs(bx - ax) < 0.2
    assert abs(by - ay) < 0.2


def test_blocked_note_wraps_to_at_most_three_lines() -> None:
    long_text = "停止入园缓冲 30 分钟，" * 10

    svg = render_route_svg(NODES, [], EDGES, reachable=False, blocked_at=long_text)

    note = re.search(r'<g id="blocked-note">(.*?)</g>', svg, re.S)
    assert note
    lines = re.findall(r"<text [^>]*>([^<]+)</text>", note.group(1))
    assert 1 <= len(lines) <= 3
    assert lines[-1].endswith("…")