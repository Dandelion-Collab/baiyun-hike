"""路线示意图：零依赖 SVG，离线可用，不引地图服务。"""

from __future__ import annotations

import html

MARGIN = 48
DEFAULT_WIDTH = 760
DEFAULT_HEIGHT = 460
COLOR_BG = "#ffffff"
COLOR_EDGE = "#d9d9d9"
COLOR_PATH = "#1f6feb"
COLOR_START = "#2ea043"
COLOR_END = "#d1242f"
COLOR_NODE = "#57606a"
COLOR_BLOCK = "#d1242f"
LABEL_SIZE = 12
LABEL_GAP = 8
BLOCKED_WRAP_CHARS = 26
BLOCKED_MAX_LINES = 3
BLOCKED_LEFT = 16
BLOCKED_TOP = 156
BLOCKED_LINE_HEIGHT = 16
BLOCKED_WIDTH_RATIO = 0.55

LEGEND_ITEMS = (
    ("起点", COLOR_START),
    ("终点", COLOR_END),
    ("路线", COLOR_PATH),
    ("其他路段", COLOR_EDGE),
    ("卡点", COLOR_BLOCK),
)


def _project(nodes: dict, width: int, height: int):
    lats = [float(node["lat"]) for node in nodes.values()]
    lngs = [float(node["lng"]) for node in nodes.values()]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)
    span_lat = max(max_lat - min_lat, 1e-6)
    span_lng = max(max_lng - min_lng, 1e-6)
    inner_w = max(width - 2 * MARGIN, 1)
    inner_h = max(height - 2 * MARGIN, 1)
    scale = min(inner_w / span_lng, inner_h / span_lat)
    draw_w = span_lng * scale
    draw_h = span_lat * scale
    offset_x = MARGIN + (inner_w - draw_w) / 2
    offset_y = MARGIN + (inner_h - draw_h) / 2

    def project(node_id: str) -> tuple[float, float]:
        node = nodes[node_id]
        x = offset_x + (float(node["lng"]) - min_lng) * scale
        y = offset_y + (max_lat - float(node["lat"])) * scale
        return x, y

    return project


def _text_rect(x: float, baseline: float, text_w: float, anchor: str) -> tuple[float, float, float, float]:
    top = baseline - LABEL_SIZE
    height = LABEL_SIZE * 1.25
    if anchor == "start":
        left = x
    elif anchor == "end":
        left = x - text_w
    else:
        left = x - text_w / 2
    return (left, top, text_w, height)


def _inside(rect: tuple[float, float, float, float], width: int, height: int) -> bool:
    left, top, w, h = rect
    return left >= 2 and top >= 2 and left + w <= width - 2 and top + h <= height - 2


def _overlaps(
    rect: tuple[float, float, float, float],
    occupied: list[tuple[float, float, float, float]],
    pad: float = 2,
) -> bool:
    left, top, w, h = rect
    right, bottom = left + w, top + h
    for oleft, otop, ow, oh in occupied:
        if (
            left - pad < oleft + ow
            and right + pad > oleft
            and top - pad < otop + oh
            and bottom + pad > otop
        ):
            return True
    return False


def _place_label(
    x: float,
    y: float,
    text: str,
    occupied: list[tuple[float, float, float, float]],
    width: int,
    height: int,
) -> tuple[float, float, str, tuple[float, float, float, float] | None]:
    text_w = len(text) * LABEL_SIZE
    candidates = (
        (x + LABEL_GAP, y - LABEL_GAP, "start"),
        (x + LABEL_GAP, y + LABEL_SIZE * 2, "start"),
        (x - LABEL_GAP, y - LABEL_GAP, "end"),
        (x - LABEL_GAP, y + LABEL_SIZE * 2, "end"),
    )
    for tx, ty, anchor in candidates:
        rect = _text_rect(tx, ty, text_w, anchor)
        if _inside(rect, width, height) and not _overlaps(rect, occupied):
            return tx, ty, anchor, None

    for offset in (LABEL_SIZE * 2, LABEL_SIZE * 3, LABEL_SIZE * 4):
        tx, ty, anchor = x, y + offset, "middle"
        rect = _text_rect(tx, ty, text_w, anchor)
        if _inside(rect, width, height) and not _overlaps(rect, occupied):
            return tx, ty, anchor, (x, y + 5, x, y + offset - LABEL_SIZE)

    tx, ty, anchor = x, y + LABEL_SIZE * 2, "middle"
    return tx, ty, anchor, (x, y + 5, x, y + LABEL_SIZE + 5)


def _wrap_note(text: str, limit: int) -> list[str]:
    if not text:
        return []
    lines = [text[index:index + limit] for index in range(0, len(text), limit)]
    if len(lines) > BLOCKED_MAX_LINES:
        lines = lines[:BLOCKED_MAX_LINES]
        lines[-1] = lines[-1][: limit - 1] + "…"
    return lines


def _legend() -> list[str]:
    parts = ['<g id="legend">']
    parts.append(
        f'<rect x="16" y="16" width="148" height="124" rx="8" '
        f'fill="{COLOR_BG}" stroke="#d0d7de" opacity="0.95"/>'
    )
    for index, (label, color) in enumerate(LEGEND_ITEMS):
        row_y = 36 + index * 22
        parts.append(
            f'<line x1="28" y1="{row_y - 4}" x2="48" y2="{row_y - 4}" '
            f'stroke="{color}" stroke-width="4" stroke-linecap="round"/>'
        )
        parts.append(f'<text x="56" y="{row_y}" font-size="12" fill="#24292f">{label}</text>')
    parts.append("</g>")
    return parts


def render_route_svg(
    nodes: dict,
    path: list[str],
    edges: list[dict],
    *,
    reachable: bool,
    blocked_at: str | None = None,
    blocked_node_id: str | None = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> str:
    """把节点与路径画成一张合法 SVG；等比投影居中，纬度翻转（北在上）。"""

    project = _project(nodes, width, height)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" height="100%" preserveAspectRatio="xMidYMid meet" role="img">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{COLOR_BG}"/>',
    ]

    for edge in edges:
        start, end = str(edge["from"]), str(edge["to"])
        if start not in nodes or end not in nodes:
            continue
        x1, y1 = project(start)
        x2, y2 = project(end)
        parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{COLOR_EDGE}" stroke-width="2"/>'
        )

    if len(path) >= 2:
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in (project(node_id) for node_id in path))
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{COLOR_PATH}" '
            f'stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
        )

    positions = {node_id: project(node_id) for node_id in nodes}
    occupied: list[tuple[float, float, float, float]] = [(16.0, 16.0, 148.0, 124.0)]
    for x, y in positions.values():
        occupied.append((x - 8, y - 8, 16, 16))

    note_lines: list[str] = []
    if not reachable and blocked_at:
        limit = min(BLOCKED_WRAP_CHARS, int(width * BLOCKED_WIDTH_RATIO) // LABEL_SIZE)
        note_lines = _wrap_note(f"无法继续：{blocked_at}", limit)
        note_h = len(note_lines) * BLOCKED_LINE_HEIGHT + 10
        occupied.append(
            (BLOCKED_LEFT - 4, BLOCKED_TOP - 14, width * BLOCKED_WIDTH_RATIO, note_h)
        )

    start_id = path[0] if path else None
    end_id = path[-1] if path else None
    for node_id, node in nodes.items():
        x, y = positions[node_id]
        if node_id == start_id:
            fill = COLOR_START
        elif node_id == end_id:
            fill = COLOR_END
        else:
            fill = COLOR_NODE
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{fill}"/>')

        name = str(node.get("name", node_id))
        tx, ty, anchor, leader = _place_label(x, y, name, occupied, width, height)
        occupied.append(_text_rect(tx, ty, len(name) * LABEL_SIZE, anchor))
        if leader:
            parts.append(
                f'<line x1="{leader[0]:.1f}" y1="{leader[1]:.1f}" '
                f'x2="{leader[2]:.1f}" y2="{leader[3]:.1f}" '
                f'stroke="{COLOR_NODE}" stroke-width="1"/>'
            )
        parts.append(
            f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="{LABEL_SIZE}" '
            f'font-family="system-ui, -apple-system, Segoe UI, Microsoft YaHei, sans-serif" '
            f'text-anchor="{anchor}" fill="#24292f">{html.escape(name)}</text>'
        )

    if not reachable and blocked_at and note_lines:
        if blocked_node_id and blocked_node_id in positions:
            bx, by = positions[blocked_node_id]
        elif path:
            bx, by = positions[path[-1]]
        else:
            bx, by = width / 2, height / 2

        parts.append(
            f'<g id="blocked-cross" stroke="{COLOR_BLOCK}" stroke-width="4" stroke-linecap="round">'
        )
        parts.append(f'<line x1="{bx - 9:.1f}" y1="{by - 9:.1f}" x2="{bx + 9:.1f}" y2="{by + 9:.1f}"/>')
        parts.append(f'<line x1="{bx - 9:.1f}" y1="{by + 9:.1f}" x2="{bx + 9:.1f}" y2="{by - 9:.1f}"/>')
        parts.append("</g>")

        note_h = len(note_lines) * BLOCKED_LINE_HEIGHT + 10
        parts.append(
            f'<rect x="{BLOCKED_LEFT - 4}" y="{BLOCKED_TOP - 14}" '
            f'width="{width * BLOCKED_WIDTH_RATIO:.1f}" height="{note_h}" '
            f'fill="{COLOR_BG}" opacity="0.92" rx="4"/>'
        )
        parts.append('<g id="blocked-note">')
        for index, line in enumerate(note_lines):
            parts.append(
                f'<text x="{BLOCKED_LEFT}" y="{BLOCKED_TOP + index * BLOCKED_LINE_HEIGHT}" '
                f'font-size="12" fill="{COLOR_BLOCK}">{html.escape(line)}</text>'
            )
        parts.append("</g>")

    parts.extend(_legend())
    parts.append("</svg>")
    return "\n".join(parts)