"""
canvas_artist -- functional work on a drawing canvas (MS Paint), planned in pure geometry and executed through the executor's hands, with measured quality checks.

Everything that can be computed without a window is computed without one and is unit-tested against a fake painter (a numpy canvas): canvas detection from a picture, grid partition with padding, shape / curve /
connector / text planners, the contour tracer, the lightboard zone planner, k-means palette and tonal bands, and the quality metrics (containment, overlap, stroke completion, leak). `LivePainter` runs a plan
on an OWNED, parked Paint through the virtual pointer (synthetic touch: measured to draw on a parked WinUI canvas where posted mouse messages are ignored) and UI Automation (tool, colour, brush, size).

Nothing here is tied to one window size or one app layout: the canvas box is FOUND in each picture (the largest near-white block), cells are derived from it, strokes are expressed in picture pixels and mapped
to screen pixels through the capture origin.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

Pt = Tuple[float, float]
Box = Tuple[float, float, float, float]          # x0, y0, x1, y1


# ------------------------------------------------------------------------------------------------------------------------------------ canvas
def find_canvas(img: Any, white: int = 250, min_area_frac: float = 0.05) -> Box:
    """The drawing surface in a picture of the window: the bounding box of the LARGEST connected block of pure-white pixels (after a morphological opening that removes thin white fragments: swatches, icons,
    text backgrounds in a ribbon). Dynamic: no coordinates are assumed. A picture with no sizeable white block raises ValueError."""
    import cv2
    a = np.asarray(img.convert("L") if hasattr(img, "convert") else img)
    mask = (a >= white).astype(np.uint8)
    k = max(9, int(min(a.shape) * 0.03)) | 1
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
    if n <= 1:
        raise ValueError("no white canvas found in the picture")
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, area = stats[i]
    if area < min_area_frac * a.shape[0] * a.shape[1]:
        raise ValueError("no white canvas found in the picture")
    return float(x), float(y), float(x + w - 1), float(y + h - 1)


def inset(box: Box, pad: float) -> Box:
    return box[0] + pad, box[1] + pad, box[2] - pad, box[3] - pad


def grid_cells(box: Box, rows: int, cols: int, pad: float) -> List[Box]:
    """rows x cols non-overlapping cells inside `box`, each shrunk by `pad` on every side, so two neighbours are always 2*pad apart and none touches the canvas edge by less than `pad`."""
    x0, y0, x1, y1 = box
    cw, ch = (x1 - x0) / cols, (y1 - y0) / rows
    return [(x0 + c * cw + pad, y0 + r * ch + pad, x0 + (c + 1) * cw - pad, y0 + (r + 1) * ch - pad) for r in range(rows) for c in range(cols)]


# ------------------------------------------------------------------------------------------------------------------------------------ strokes
@dataclass
class Stroke:
    points: List[Pt]
    kind: str = "path"            # rectangle | ellipse | triangle | line | arrow | curve | text | trace | fill ...
    group: str = ""               # which shape / label / contour this belongs to
    tool: str = "Pencil"
    meta: Dict[str, Any] = field(default_factory=dict)


def resample(points: Sequence[Pt], step: float) -> List[Pt]:
    """Points spaced `step` px apart along the path (the pointer interpolates between samples; even spacing makes the pace even)."""
    pts = [tuple(map(float, p)) for p in points]
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    carry = 0.0
    for a, b in zip(pts, pts[1:]):
        seg = math.dist(a, b)
        if seg == 0:
            continue
        d = step - carry
        while d <= seg:
            t = d / seg
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            d += step
        carry = seg - (d - step)
    if math.dist(out[-1], pts[-1]) > 1e-6:
        out.append(pts[-1])
    return out


def path_length(points: Sequence[Pt]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def bezier(p0: Pt, p1: Pt, p2: Pt, p3: Pt, n: int = 48) -> List[Pt]:
    """A cubic Bezier sampled at n+1 points."""
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0], u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return out


def catmull_rom(points: Sequence[Pt], per_seg: int = 12) -> List[Pt]:
    """A smooth curve THROUGH the given points (free-form multi-point polylines become smooth strokes)."""
    p = [tuple(map(float, q)) for q in points]
    if len(p) < 3:
        return p
    ext = [p[0]] + p + [p[-1]]
    out: List[Pt] = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(per_seg):
            t = k / per_seg
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2 + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    out.append(p[-1])
    return out


# ------------------------------------------------------------------------------------------------------------------------------------ shapes
def rect_pts(b: Box) -> List[Pt]:
    return [(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3]), (b[0], b[1])]


def ellipse_pts(b: Box, n: int = 72) -> List[Pt]:
    cx, cy, rx, ry = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, (b[2] - b[0]) / 2, (b[3] - b[1]) / 2
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]


def triangle_pts(b: Box) -> List[Pt]:
    return [((b[0] + b[2]) / 2, b[1]), (b[2], b[3]), (b[0], b[3]), ((b[0] + b[2]) / 2, b[1])]


def line_pts(b: Box) -> List[Pt]:
    return [(b[0], b[3]), (b[2], b[1])]


SHAPES: Dict[str, Callable[[Box], List[Pt]]] = {"rectangle": rect_pts, "ellipse": ellipse_pts, "triangle": triangle_pts, "line": line_pts}


def plan_shapes(cells: Sequence[Box], kinds: Sequence[str], tool_for: Optional[Dict[str, str]] = None, step: float = 4.0) -> List[Stroke]:
    """One shape per cell, in order. Each shape's points stay inside its cell (a closed shape is the cell's inscribed outline)."""
    tool_for = tool_for or {}
    out = []
    for i, (cell, k) in enumerate(zip(cells, kinds)):
        out.append(Stroke(resample(SHAPES[k](cell), step), k, f"shape{i}", tool_for.get(k, "Pencil"), {"cell": cell}))
    return out


# ------------------------------------------------------------------------------------------------------------------------------------ text as strokes
# A small stroke font (5 wide x 7 tall grid, y down). Used where a typed label is unreliable (the Text tool's box needs focus + typing) and for labels that must be pure geometry.
_G: Dict[str, List[List[Tuple[int, int]]]] = {
    "A": [[(0, 6), (2, 0), (4, 6)], [(1, 3), (3, 3)]], "B": [[(0, 6), (0, 0), (3, 0), (4, 1), (3, 3), (0, 3)], [(3, 3), (4, 4), (4, 5), (3, 6), (0, 6)]], "C": [[(4, 1), (3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5)]],
    "D": [[(0, 0), (0, 6), (2, 6), (4, 4), (4, 2), (2, 0), (0, 0)]], "E": [[(4, 0), (0, 0), (0, 6), (4, 6)], [(0, 3), (3, 3)]], "F": [[(4, 0), (0, 0), (0, 6)], [(0, 3), (3, 3)]],
    "G": [[(4, 1), (3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 3), (2, 3)]], "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]], "I": [[(1, 0), (3, 0)], [(2, 0), (2, 6)], [(1, 6), (3, 6)]],
    "J": [[(4, 0), (4, 5), (3, 6), (1, 6), (0, 5)]], "K": [[(0, 0), (0, 6)], [(4, 0), (0, 3), (4, 6)]], "L": [[(0, 0), (0, 6), (4, 6)]], "M": [[(0, 6), (0, 0), (2, 3), (4, 0), (4, 6)]],
    "N": [[(0, 6), (0, 0), (4, 6), (4, 0)]], "O": [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)]], "P": [[(0, 6), (0, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)]],
    "Q": [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)], [(2, 4), (4, 6)]], "R": [[(0, 6), (0, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)], [(2, 3), (4, 6)]],
    "S": [[(4, 1), (3, 0), (1, 0), (0, 1), (0, 2), (1, 3), (3, 3), (4, 4), (4, 5), (3, 6), (1, 6), (0, 5)]], "T": [[(0, 0), (4, 0)], [(2, 0), (2, 6)]], "U": [[(0, 0), (0, 5), (1, 6), (3, 6), (4, 5), (4, 0)]],
    "V": [[(0, 0), (2, 6), (4, 0)]], "W": [[(0, 0), (1, 6), (2, 3), (3, 6), (4, 0)]], "X": [[(0, 0), (4, 6)], [(4, 0), (0, 6)]], "Y": [[(0, 0), (2, 3), (4, 0)], [(2, 3), (2, 6)]], "Z": [[(0, 0), (4, 0), (0, 6), (4, 6)]],
    "0": [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)], [(0, 5), (4, 1)]], "1": [[(1, 1), (2, 0), (2, 6)], [(1, 6), (3, 6)]], "2": [[(0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (0, 6), (4, 6)]],
    "3": [[(0, 0), (4, 0), (2, 3), (3, 3), (4, 4), (4, 5), (3, 6), (1, 6), (0, 5)]], "4": [[(3, 6), (3, 0), (0, 4), (4, 4)]], "5": [[(4, 0), (0, 0), (0, 3), (3, 3), (4, 4), (4, 5), (3, 6), (0, 6)]],
    "6": [[(4, 1), (3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)]], "7": [[(0, 0), (4, 0), (1, 6)]], "8": [[(1, 3), (0, 2), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (3, 3), (1, 3), (0, 4), (0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3)]],
    "9": [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0), (0, 1), (0, 2), (1, 3), (4, 3)]], "-": [[(0, 3), (4, 3)]], ".": [[(2, 5.6), (2, 6)]], ":": [[(2, 1.6), (2, 2)], [(2, 4.6), (2, 5)]], "/": [[(0, 6), (4, 0)]],
    "(": [[(3, 0), (1, 2), (1, 4), (3, 6)]], ")": [[(1, 0), (3, 2), (3, 4), (1, 6)]], "+": [[(0, 3), (4, 3)], [(2, 1), (2, 5)]], "=": [[(0, 2), (4, 2)], [(0, 4), (4, 4)]], ",": [[(2, 5), (1.5, 6.5)]], "?": [[(0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (2, 3), (2, 4)], [(2, 5.6), (2, 6)]],
}


def text_size(text: str, height: float, spacing: float = 0.35) -> Tuple[float, float]:
    """(width, height) in px of `text` drawn with the stroke font at the given cap height."""
    s = height / 6.0
    return len(text) * (4 + 4 * spacing + 1) * s - (4 * spacing + 1) * s, height


def text_strokes(text: str, origin: Pt, height: float = 18.0, spacing: float = 0.35) -> List[Stroke]:
    """`text` (upper-cased; unknown characters are skipped) as polylines with its top-left at `origin`."""
    s = height / 6.0
    adv = (4 + 4 * spacing + 1) * s
    out: List[Stroke] = []
    for i, ch in enumerate(text.upper()):
        for poly in _G.get(ch, []):
            out.append(Stroke([(origin[0] + i * adv + x * s, origin[1] + y * s) for x, y in poly], "text", f"text:{text}", "Pencil", {"char": ch}))
    return out


def fit_text(text: str, box: Box, max_height: float = 22.0) -> Tuple[Pt, float]:
    """(origin, height) so `text` fits inside `box` centred, as large as max_height allows."""
    bw, bh = box[2] - box[0], box[3] - box[1]
    h = min(max_height, bh)
    while h > 6 and text_size(text, h)[0] > bw:
        h -= 1
    w, _ = text_size(text, h)
    return (box[0] + (bw - w) / 2, box[1] + (bh - h) / 2), h


# ------------------------------------------------------------------------------------------------------------------------------------ connectors (border to border)
def border_point(b: Box, toward: Pt) -> Pt:
    """Where the ray from the box's centre to `toward` leaves the box."""
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, b[1]
    hw, hh = (b[2] - b[0]) / 2, (b[3] - b[1]) / 2
    t = min(hw / abs(dx) if dx else float("inf"), hh / abs(dy) if dy else float("inf"))
    return cx + dx * t, cy + dy * t


def arrow(a: Pt, b: Pt, head: float = 12.0, spread: float = 0.45) -> List[List[Pt]]:
    """A shaft a->b and the two barbs of its head (three polylines)."""
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    l = (b[0] - head * math.cos(ang - spread), b[1] - head * math.sin(ang - spread))
    r = (b[0] - head * math.cos(ang + spread), b[1] - head * math.sin(ang + spread))
    return [[a, b], [l, b], [r, b]]


def connector(src: Box, dst: Box, gap: float = 3.0, head: float = 12.0) -> List[Stroke]:
    """A directional arrow from the border of `src` to the border of `dst` (straight, centre to centre, clipped to both borders, `gap` px short of each)."""
    cs, cd = ((src[0] + src[2]) / 2, (src[1] + src[3]) / 2), ((dst[0] + dst[2]) / 2, (dst[1] + dst[3]) / 2)
    a, b = border_point(src, cd), border_point(dst, cs)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    a = (a[0] + gap * math.cos(ang), a[1] + gap * math.sin(ang))
    b = (b[0] - gap * math.cos(ang), b[1] - gap * math.sin(ang))
    return [Stroke(resample(p, 4.0), "arrow", "arrow", "Pencil", {"from": a, "to": b}) for p in arrow(a, b, head)]


def plan_flowchart(box: Box, labels: Sequence[str], edges: Sequence[Tuple[int, int]], cols: int = 3, pad: float = 24.0, step: float = 4.0) -> Tuple[List[Stroke], List[Box]]:
    """Boxes on a grid (reading order), a label centred in each (stroke font), arrows between the listed (from, to) pairs, border to border."""
    rows = int(math.ceil(len(labels) / cols))
    cells = grid_cells(box, rows, cols, pad)
    boxes = []
    for c in cells[:len(labels)]:                                      # shrink each cell to a box with room around it for the arrows
        w, h = c[2] - c[0], c[3] - c[1]
        boxes.append((c[0] + w * 0.12, c[1] + h * 0.22, c[2] - w * 0.12, c[3] - h * 0.22))
    strokes: List[Stroke] = []
    for i, (b, lab) in enumerate(zip(boxes, labels)):
        strokes.append(Stroke(resample(rect_pts(b), step), "rectangle", f"box{i}", "Pencil", {"cell": b}))
        o, h = fit_text(lab, inset(b, 8), 20)
        strokes.extend(text_strokes(lab, o, h))
    for a, b in edges:
        strokes.extend(connector(boxes[a], boxes[b]))
    return strokes, boxes


# ------------------------------------------------------------------------------------------------------------------------------------ free-form
def plan_curves(cells: Sequence[Box], step: float = 3.0) -> List[Stroke]:
    """One curve per cell: an S-curve (Bezier), a wave (sine), a spiral, a Lissajous, a flower, an infinity: each fills its cell without leaving it."""
    out: List[Stroke] = []

    def fit(pts: List[Pt], cell: Box) -> List[Pt]:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        sx = (cell[2] - cell[0]) / max(max(xs) - min(xs), 1e-9)
        sy = (cell[3] - cell[1]) / max(max(ys) - min(ys), 1e-9)
        s = min(sx, sy)
        ox = cell[0] + ((cell[2] - cell[0]) - (max(xs) - min(xs)) * s) / 2 - min(xs) * s
        oy = cell[1] + ((cell[3] - cell[1]) - (max(ys) - min(ys)) * s) / 2 - min(ys) * s
        return [(x * s + ox, y * s + oy) for x, y in pts]
    makers: List[Tuple[str, Callable[[], List[Pt]]]] = [
        ("bezier_s", lambda: bezier((0, 100), (60, -40), (140, 240), (200, 100), 80)),
        ("sine", lambda: [(t * 10, 40 * math.sin(t / 3.0)) for t in range(0, 61)]),
        ("spiral", lambda: [((1 + 0.12 * t) * math.cos(t / 4.0), (1 + 0.12 * t) * math.sin(t / 4.0)) for t in range(0, 140)]),
        ("lissajous", lambda: [(math.sin(3 * t / 40.0 * math.pi), math.sin(2 * t / 40.0 * math.pi)) for t in range(0, 81)]),
        ("flower", lambda: [(math.cos(5 * a) * math.cos(a), math.cos(5 * a) * math.sin(a)) for a in [i * 2 * math.pi / 160 for i in range(161)]]),
        ("infinity", lambda: [(math.cos(a) / (1 + math.sin(a) ** 2), math.sin(a) * math.cos(a) / (1 + math.sin(a) ** 2)) for a in [i * 2 * math.pi / 120 for i in range(121)]]),
    ]
    for i, cell in enumerate(cells):
        name, mk = makers[i % len(makers)]
        out.append(Stroke(resample(fit(mk(), cell), step), "curve", f"curve{i}:{name}", "Pencil", {"cell": cell, "curve": name}))
    return out


# ------------------------------------------------------------------------------------------------------------------------------------ metrics
def raster(strokes: Sequence[Stroke], size: Tuple[int, int], thickness: int = 2) -> np.ndarray:
    import cv2
    m = np.zeros((size[1], size[0]), np.uint8)
    for s in strokes:
        pts = np.array([[int(round(x)), int(round(y))] for x, y in s.points], np.int32).reshape(-1, 1, 2)
        if len(pts) >= 2:
            cv2.polylines(m, [pts], False, 255, thickness)
        elif len(pts) == 1:
            cv2.circle(m, tuple(pts[0, 0]), max(thickness // 2, 1), 255, -1)
    return m


def containment(strokes: Sequence[Stroke], box: Box) -> float:
    """% of all planned points inside `box`."""
    pts = [p for s in strokes for p in s.points]
    if not pts:
        return 100.0
    inside = sum(1 for x, y in pts if box[0] <= x <= box[2] and box[1] <= y <= box[3])
    return round(100.0 * inside / len(pts), 2)


def overlap_pairs(shapes: Dict[str, Sequence[Stroke]], size: Tuple[int, int], min_gap: int = 4) -> List[Tuple[str, str]]:
    """Pairs of groups whose rasters come within `min_gap` px of each other (0 = they touch or cross). Zero pairs = zero unintended overlap."""
    import cv2
    names = list(shapes)
    masks = {n: cv2.dilate(raster(shapes[n], size, 2), np.ones((min_gap, min_gap), np.uint8)) for n in names}
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if np.any(masks[a] & masks[b]):
                out.append((a, b))
    return out


def completion(strokes: Sequence[Stroke], observed: Any, canvas: Box, tol: int = 3, ink: int = 128) -> float:
    """% of the planned stroke pixels that really got ink within `tol` px: the plan rasterised vs the captured canvas (dark pixels = ink)."""
    import cv2
    g = np.asarray(observed.convert("L") if hasattr(observed, "convert") else observed)
    plan = raster(strokes, (g.shape[1], g.shape[0]), 1) > 0
    inked = cv2.dilate((g < ink).astype(np.uint8), np.ones((2 * tol + 1, 2 * tol + 1), np.uint8)) > 0
    x0, y0, x1, y1 = [int(v) for v in canvas]
    box = np.zeros_like(plan)
    box[y0:y1 + 1, x0:x1 + 1] = True
    p = plan & box
    return round(100.0 * float((p & inked).sum()) / max(float(p.sum()), 1.0), 2)


def leak_pixels(before: Any, after: Any, canvas: Box, thr: int = 24, margin: int = 2) -> int:
    """Pixels that changed OUTSIDE the canvas box (a stroke that escaped onto the chrome)."""
    a, b = (np.asarray(x.convert("L"), dtype=np.int16) for x in (before, after))
    d = np.abs(a - b) > thr
    x0, y0, x1, y1 = [int(v) for v in canvas]
    d[max(y0 - margin, 0):y1 + margin + 1, max(x0 - margin, 0):x1 + margin + 1] = False
    return int(d.sum())


def leak_bbox(before: Any, after: Any, canvas: Box, thr: int = 24, margin: int = 2) -> Optional[Tuple[int, int, int, int]]:
    """Where the outside-the-canvas changes are (x0, y0, x1, y1), or None: tells a stroke that escaped from a status-bar readout that changed."""
    a, b = (np.asarray(x.convert("L"), dtype=np.int16) for x in (before, after))
    d = np.abs(a - b) > thr
    x0, y0, x1, y1 = [int(v) for v in canvas]
    d[max(y0 - margin, 0):y1 + margin + 1, max(x0 - margin, 0):x1 + margin + 1] = False
    ys, xs = np.where(d)
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())) if len(xs) else None


# ------------------------------------------------------------------------------------------------------------------------------------ tracing (Stage 4)
def edge_map(gray: np.ndarray, scales: Sequence[float] = (1.0, 0.5), sigma: float = 1.0) -> np.ndarray:
    """A multi-scale edge map (uint8 0/255): bilateral denoise, then at each scale the union of an XDoG-style soft-thresholded difference of Gaussians and an auto-threshold Canny (thresholds from the median),
    brought back to full size. Fine detail comes from scale 1, structure from the coarser scales."""
    import cv2
    g = cv2.bilateralFilter(gray, 7, 40, 5)
    out = np.zeros_like(gray, np.uint8)
    for sc in scales:
        h, w = g.shape
        gs = cv2.resize(g, (max(8, int(w * sc)), max(8, int(h * sc))), interpolation=cv2.INTER_AREA) if sc != 1.0 else g
        a = cv2.GaussianBlur(gs, (0, 0), sigma).astype(np.float32)
        b = cv2.GaussianBlur(gs, (0, 0), sigma * 1.6).astype(np.float32)
        d = a - 0.98 * b                                              # XDoG: sharpened difference of Gaussians, then a soft step
        x = (d < -2.0).astype(np.uint8) * 255
        med = float(np.median(gs))
        c = cv2.Canny(gs, int(max(10, 0.66 * med)), int(min(250, 1.33 * med + 40)))
        e = cv2.bitwise_or(x, c)
        if sc != 1.0:
            e = cv2.resize(e, (w, h), interpolation=cv2.INTER_NEAREST)
        out = cv2.bitwise_or(out, e)
    return out


def trace_strokes(image_bgr: np.ndarray, target: Box, max_strokes: int = 220, min_len: float = 18.0, eps: float = 1.5, margin: float = 10.0, step: float = 3.0, colour_edges: bool = True, min_component: int = 30, coverage: float = 0.0, time_budget_s: float = 0.0, sec_per_stroke: float = 0.75) -> Tuple[List[Stroke], Dict[str, Any]]:
    """Reference image -> pen strokes inside `target` (a box, e.g. the canvas safe zone).
    edge map -> skeleton (one-pixel lines: a thick line is not traced twice, as its two sides) -> cv2.findContours with the topological hierarchy -> Douglas-Peucker simplification -> strokes sorted from the OUTER
    structural boundaries to the finest interior details (hierarchy depth, then length) -> mapped proportionally (aspect kept, centred) into the target. Stats include the reference edge map for scoring."""
    import cv2
    from skimage.morphology import skeletonize
    img = image_bgr if image_bgr.ndim == 3 else cv2.cvtColor(image_bgr, cv2.COLOR_GRAY2BGR)
    h0, w0 = img.shape[:2]
    if max(h0, w0) < 900:                                             # small references (a 435 px plate): trace on an enlarged copy so one pixel of the original is several traced pixels
        f = 900.0 / max(h0, w0)
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = edge_map(gray)
    if colour_edges:                                                  # painted / printed colour art: region boundaries live in the colour channels too, and mean-shift removes the paper / brush texture first
        smooth = cv2.pyrMeanShiftFiltering(img, 10, 22)
        lab = cv2.cvtColor(smooth, cv2.COLOR_BGR2LAB)
        for ch in (1, 2):
            edges = cv2.bitwise_or(edges, edge_map(lab[:, :, ch], scales=(0.5,)))
        edges = cv2.bitwise_or(edges, edge_map(lab[:, :, 0], scales=(0.5,)))
    n, labels, stt, _ = cv2.connectedComponentsWithStats((edges > 0).astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stt[1:, cv2.CC_STAT_AREA] >= min_component                 # specks are texture, not structure
    edges = (keep[labels] * 255).astype(np.uint8)
    skel = skeletonize(edges > 0).astype(np.uint8) * 255
    cnts, hier = cv2.findContours(skel, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    hier = hier[0] if hier is not None else np.zeros((0, 4), int)

    def depth(i: int) -> int:
        d = 0
        while hier[i][3] != -1:
            i = hier[i][3]
            d += 1
        return d
    items = []
    for i, c in enumerate(cnts):
        if len(c) < 2:
            continue
        ap = cv2.approxPolyDP(c, eps, False).reshape(-1, 2).astype(float)
        ln = float(cv2.arcLength(c, False))
        if ln < min_len or len(ap) < 2:
            continue
        items.append((depth(i), -ln, ap.tolist(), ln))
    raw_n = len(items)
    # WHICH strokes are drawn: the longest ones carry the structure (inner borderlines included), so selection is by length, NOT by depth (a depth-first cut drops every fine interior line -- measured: 300 of 793
    # contours kept, the 493 dropped were the interior detail). `coverage` (0-1) keeps strokes until that share of the total edge length is covered; `time_budget_s` caps the count by drawing time.
    by_len = sorted(items, key=lambda t: -t[3])
    cap = max_strokes if max_strokes else len(by_len)
    if time_budget_s:
        cap = min(cap, max(1, int(time_budget_s / max(sec_per_stroke, 1e-3))))
    if coverage > 0:
        total = sum(t[3] for t in by_len) or 1.0
        acc, n_keep = 0.0, 0
        for t in by_len:
            n_keep += 1
            acc += t[3]
            if acc >= coverage * total:
                break
        cap = min(cap, n_keep)
    items = by_len[:cap]
    items.sort(key=lambda t: (t[0], t[1]))                            # HOW they are drawn: outer structural boundaries first, finest interior details last
    H, W = gray.shape
    bw, bh = (target[2] - target[0]) - 2 * margin, (target[3] - target[1]) - 2 * margin
    sc = min(bw / W, bh / H)
    ox = target[0] + margin + (bw - W * sc) / 2
    oy = target[1] + margin + (bh - H * sc) / 2
    strokes = [Stroke(resample([(ox + x * sc, oy + y * sc) for x, y in pts], step), "trace", f"trace{k}", "Pencil", {"depth": d, "length": ln * sc}) for k, (d, _n, pts, ln) in enumerate(items)]
    kept_len = sum(t[3] for t in items)
    stats = {"edge_pixels": int((edges > 0).sum()), "contours_found": len(cnts), "contours_kept": raw_n, "strokes": len(strokes), "length_covered_pct": round(100.0 * kept_len / max(sum(t[3] for t in by_len), 1.0), 1), "max_depth": max((d for d, *_ in items), default=0),
             "ink_length_px": round(sum(s.meta["length"] for s in strokes)), "map": {"scale": sc, "offset": (ox, oy), "size": (W, H)}, "edges": edges, "ref_size": (W, H)}
    return strokes, stats


def trace_fidelity(drawn: Any, canvas: Box, stats: Dict[str, Any], tol: int = 4) -> Dict[str, float]:
    """How well the drawing reproduces the reference's structure: the reference edge map placed where the tracer placed it, against the ink on the canvas. recall = % of reference edge pixels that have ink within
    `tol` px; precision = % of ink pixels that are near a reference edge. (Edge-level, not photographic similarity: it measures structure.)"""
    import cv2
    g = np.asarray(drawn.convert("L") if hasattr(drawn, "convert") else drawn)
    sc, (ox, oy), (W, H) = stats["map"]["scale"], stats["map"]["offset"], stats["map"]["size"]
    ref = cv2.resize(stats["edges"], (max(1, int(W * sc)), max(1, int(H * sc))), interpolation=cv2.INTER_AREA)
    full = np.zeros_like(g)
    x0, y0 = int(round(ox)), int(round(oy))
    h, w = ref.shape
    full[y0:y0 + h, x0:x0 + w] = (ref > 40).astype(np.uint8)[:full.shape[0] - y0, :full.shape[1] - x0]
    cx0, cy0, cx1, cy1 = [int(v) for v in canvas]
    ink = (g < 128).astype(np.uint8)
    region = np.zeros_like(ink)
    region[cy0:cy1 + 1, cx0:cx1 + 1] = 1
    ink &= region
    k = np.ones((2 * tol + 1, 2 * tol + 1), np.uint8)
    near_ink = cv2.dilate(ink, k) > 0
    near_ref = cv2.dilate(full, k) > 0
    recall = float(((full > 0) & near_ink).sum()) / max(float((full > 0).sum()), 1.0)
    precision = float(((ink > 0) & near_ref).sum()) / max(float((ink > 0).sum()), 1.0)
    return {"recall_pct": round(100 * recall, 1), "precision_pct": round(100 * precision, 1)}


# ------------------------------------------------------------------------------------------------------------------------------------ painters
class FakePainter:
    """A numpy canvas that draws what it is told: the offline stand-in for LivePainter (same interface)."""

    def __init__(self, size: Tuple[int, int] = (1536, 864), canvas: Box = (190, 125, 1343, 771)):
        import cv2
        self.cv2 = cv2
        self.size, self.box = size, canvas
        self.img = np.full((size[1], size[0]), 243, np.uint8)
        x0, y0, x1, y1 = [int(v) for v in canvas]
        self.img[y0:y1 + 1, x0:x1 + 1] = 255
        self.calls: List[Tuple[str, Any]] = []
        self.tool = "Pencil"

    def grab(self):
        from PIL import Image
        return Image.fromarray(self.img).convert("RGB")

    def canvas(self) -> Box:
        return find_canvas(self.grab())

    def select(self, name: str) -> bool:
        self.calls.append(("select", name))
        self.tool = name
        return True

    def stroke(self, points: Sequence[Pt], width: int = 2) -> bool:
        self.calls.append(("stroke", len(points)))
        pts = np.array([[int(round(x)), int(round(y))] for x, y in points], np.int32).reshape(-1, 1, 2)
        if len(pts) >= 2:
            self.cv2.polylines(self.img, [pts], False, 0, width)
        return True


def execute(painter: Any, strokes: Sequence[Stroke], on_stroke: Optional[Callable[[int, Stroke], None]] = None, batch: int = 12) -> Dict[str, Any]:
    """Run a plan: select each stroke's tool when it changes, then draw. A painter with `stroke_batch(list_of_point_lists)` gets up to `batch` consecutive strokes of the same tool in ONE delivery (one ghost
    window, one idle check: measured to cut a stroke from ~2.4 s to well under a second); others get one stroke at a time. Returns counts and timing."""
    t0 = time.time()
    last_tool, drawn = None, 0
    pending: List[Tuple[int, Stroke]] = []

    def flush() -> None:
        nonlocal drawn
        if not pending:
            return
        if hasattr(painter, "stroke_batch"):
            n_ok = painter.stroke_batch([s.points for _, s in pending])
            drawn += int(n_ok)
        else:
            for _, s in pending:
                drawn += 1 if painter.stroke(s.points) else 0
        if on_stroke:
            for i, s in pending:
                on_stroke(i, s)
        pending.clear()
    for i, s in enumerate(strokes):
        if s.tool != last_tool:
            flush()
            painter.select(s.tool)
            last_tool = s.tool
        pending.append((i, s))
        if len(pending) >= batch:
            flush()
    flush()
    return {"strokes": len(strokes), "drawn": drawn, "seconds": round(time.time() - t0, 1)}


# ------------------------------------------------------------------------------------------------------------------------------------ verify and repair
def missing_strokes(strokes: Sequence[Stroke], observed: Any, canvas: Box, tol: int = 3, ink: int = 128, min_frac: float = 0.85) -> List[int]:
    """Indices of the strokes whose points did NOT get ink on the captured canvas (fewer than `min_frac` of their points within `tol` px of a dark pixel). A stroke can fail to land (a contact the app
    took for a tap, a delivery cut short because the person moved): the plan raster vs the picture finds it, per stroke, cheaply (points are sampled, not rasterised)."""
    import cv2
    g = np.asarray(observed.convert("L") if hasattr(observed, "convert") else observed)
    inked = cv2.dilate((g < ink).astype(np.uint8), np.ones((2 * tol + 1, 2 * tol + 1), np.uint8)) > 0
    H, W = inked.shape
    out = []
    for i, st in enumerate(strokes):
        pts = resample(st.points, 2.0) if len(st.points) > 1 else list(st.points)
        if not pts:
            continue
        hit = sum(1 for x, y in pts if 0 <= int(round(y)) < H and 0 <= int(round(x)) < W and inked[int(round(y)), int(round(x))])
        if hit < min_frac * len(pts):
            out.append(i)
    return out


def repair(painter: Any, strokes: Sequence[Stroke], canvas: Box, passes: int = 2, **kw: Any) -> Dict[str, Any]:
    """Look at the canvas, find the strokes that did not land, draw just those again (same tool), look again. Up to `passes` times. Returns what was found and what is still missing."""
    rep: Dict[str, Any] = {"passes": 0, "missing_first": None, "redrawn": 0, "missing_last": 0}
    for k in range(passes):
        time.sleep(0.6)
        miss = missing_strokes(strokes, painter.grab(), canvas, **kw)
        if rep["missing_first"] is None:
            rep["missing_first"] = len(miss)
        rep["missing_last"] = len(miss)
        if not miss:
            break
        rep["passes"] += 1
        sub = [strokes[i] for i in miss]
        execute(painter, sub)
        rep["redrawn"] += len(sub)
    else:
        time.sleep(0.6)
        rep["missing_last"] = len(missing_strokes(strokes, painter.grab(), canvas, **kw))
    return rep
