"""
canvas_teach -- the Lightboard Tutor and hybrid compositions, as geometry.

An expert at a lightboard keeps the DIAGRAM in the middle and explains around it: a title above, short labelled call-outs in columns on both sides with a clean leader from each label to the exact part it
names, numbered markers, and a step-by-step summary underneath. This module partitions a canvas the same way (dynamically, from the canvas box), places call-outs so that no label overlaps another or the
artwork and no two leaders cross, finds structural landmarks on the traced strokes by itself, draws a magnifier circle on a region with a zoom panel in a margin lane, and frames the whole.
Everything is a list of canvas_artist.Stroke (text uses the stroke font), so the same plan runs on the fake canvas in tests and on Paint live. The checks (`audit`) are explicit and measured.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from core_organs import canvas_artist as CA
from core_organs.canvas_artist import Box, Pt, Stroke


# ------------------------------------------------------------------------------------------------------------------------------------ zones
def lightboard_zones(canvas: Box, header: float = 0.10, footer: float = 0.15, lane: float = 0.22, gap: float = 14.0) -> Dict[str, Box]:
    """header / left lane / core / right lane / footer, as boxes inside `canvas` with `gap` px between them. Proportions are fractions of the canvas, so any canvas size works."""
    x0, y0, x1, y1 = canvas
    w, h = x1 - x0, y1 - y0
    hy, fy = y0 + h * header, y1 - h * footer
    lx, rx = x0 + w * lane, x1 - w * lane
    return {"header": (x0, y0, x1, hy - gap / 2),
            "left": (x0, hy + gap / 2, lx - gap / 2, fy - gap / 2),
            "core": (lx + gap / 2, hy + gap / 2, rx - gap / 2, fy - gap / 2),
            "right": (rx + gap / 2, hy + gap / 2, x1, fy - gap / 2),
            "footer": (x0, fy + gap / 2, x1, y1)}


def stroke_bbox(strokes: Sequence[Stroke]) -> Box:
    xs = [p[0] for s in strokes for p in s.points]
    ys = [p[1] for s in strokes for p in s.points]
    return min(xs), min(ys), max(xs), max(ys)


def auto_landmarks(strokes: Sequence[Stroke], n: int = 6) -> List[Pt]:
    """Structural landmarks without any hand-placed coordinates: take the longest traced strokes, represent each by its midpoint, and keep n of them that are far apart from each other (farthest-point
    sampling). The longest outlines are the parts of the figure a teacher would point at."""
    cand = sorted((s for s in strokes if s.kind == "trace"), key=lambda s: -CA.path_length(s.points))[:max(n * 6, 12)]
    mids = [s.points[len(s.points) // 2] for s in cand]
    if not mids:
        return []
    chosen = [mids[0]]
    while len(chosen) < min(n, len(mids)):
        best = max(mids, key=lambda m: min(math.dist(m, c) for c in chosen))
        chosen.append(best)
    return chosen


def rel_to_canvas(rel: Pt, stats: Dict[str, Any]) -> Pt:
    """A point given as fractions (0-1, 0-1) of the reference image -> canvas pixels, through the map the tracer used to place the image."""
    sc = stats["map"]["scale"]
    (ox, oy), (W, H) = stats["map"]["offset"], stats["map"]["size"]
    return ox + rel[0] * W * sc, oy + rel[1] * H * sc


def canvas_to_rel(pt: Pt, stats: Dict[str, Any]) -> Pt:
    """Inverse of rel_to_canvas: canvas pixels -> fractions of the reference image."""
    sc = stats["map"]["scale"]
    (ox, oy), (W, H) = stats["map"]["offset"], stats["map"]["size"]
    return (pt[0] - ox) / max(W * sc, 1e-6), (pt[1] - oy) / max(H * sc, 1e-6)


def densest_window(strokes: Sequence[Stroke], radius: float, step: float = 12.0) -> Pt:
    """Centre of the radius-sized window holding the MOST ink (sum of stroke length inside it): the finest detail of the traced art, found from the strokes alone -- where a teacher would zoom in."""
    pts = [q for s in strokes if s.kind == "trace" for q in s.points]
    if not pts:
        return (0.0, 0.0)
    arr = np.array(pts)
    x0, y0, x1, y1 = arr[:, 0].min(), arr[:, 1].min(), arr[:, 0].max(), arr[:, 1].max()
    best, bc = (float(x0), float(y0)), -1
    for cy in np.arange(y0 + radius, max(y1 - radius, y0 + radius) + 1, step):
        for cx in np.arange(x0 + radius, max(x1 - radius, x0 + radius) + 1, step):
            c = int(((np.abs(arr[:, 0] - cx) <= radius) & (np.abs(arr[:, 1] - cy) <= radius)).sum())
            if c > bc:
                best, bc = (float(cx), float(cy)), c
    return best


def load_sidecar(image_path: str) -> Dict[str, Any]:
    """Optional DATA next to a reference image: <name>.labels.json = {"title": str, "labels": [{"text": str, "at": [fx, fy]}], "steps": [str]}. It is input, not code: with none, the labels are 'Part N' placed at
    landmarks found from the traced strokes, the title is the file name, and the steps describe what was measured."""
    import json
    import os
    p = os.path.splitext(image_path)[0] + ".labels.json"
    try:
        return json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else {}
    except Exception:
        return {}


def snap_to_art(point: Pt, art: Sequence[Stroke]) -> Pt:
    """The point on the traced strokes nearest to `point`: a leader must end ON the drawing, not in the empty space beside the part it names."""
    best, bd = point, float("inf")
    for s in art:
        for q in s.points:
            d = (q[0] - point[0]) ** 2 + (q[1] - point[1]) ** 2
            if d < bd:
                best, bd = q, d
    return best


# ------------------------------------------------------------------------------------------------------------------------------------ call-outs
def _seg_intersect(a: Pt, b: Pt, c: Pt, d: Pt) -> bool:
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) - (q[1] - p[1]) * (r[0] - p[0])
    return ccw(a, c, d) * ccw(b, c, d) < 0 and ccw(a, b, c) * ccw(a, b, d) < 0


def _seg_hits_box(a: Pt, b: Pt, box: Box, shrink: float = 0.0) -> bool:
    x0, y0, x1, y1 = box[0] + shrink, box[1] + shrink, box[2] - shrink, box[3] - shrink
    if x0 <= a[0] <= x1 and y0 <= a[1] <= y1 or x0 <= b[0] <= x1 and y0 <= b[1] <= y1:
        return True
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return any(_seg_intersect(a, b, corners[i], corners[(i + 1) % 4]) for i in range(4))


@dataclass
class Callout:
    label: str
    landmark: Pt
    lane: str                       # left | right
    box: Box = (0, 0, 0, 0)
    anchor: Pt = (0, 0)             # where the leader meets the box
    number: int = 0
    height: float = 16.0
    lines: int = 1


def wrap_label(label: str, max_w: float, h: float) -> List[str]:
    """`label` on one line if it fits `max_w` at height h, else split at the space nearest the middle (a single long word is left alone)."""
    if CA.text_size(label, h)[0] <= max_w or " " not in label:
        return [label]
    words = label.split(" ")
    best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return [" ".join(words[:best]), " ".join(words[best:])]


def fit_height(labels: Sequence[str], max_w: float, hmax: float = 16.0, hmin: float = 8.0) -> Tuple[float, List[List[str]]]:
    """The largest common text height (<= hmax) at which every label, wrapped to at most two lines, fits `max_w`; returns (height, wrapped lines per label)."""
    h = hmax
    while h > hmin:
        wrapped = [wrap_label(l, max_w, h) for l in labels]
        if all(CA.text_size(ln, h)[0] <= max_w for w in wrapped for ln in w):
            return h, wrapped
        h -= 1
    return hmin, [wrap_label(l, max_w, hmin) for l in labels]


def place_callouts(zones: Dict[str, Box], labels: Sequence[str], landmarks: Sequence[Pt], height: float = 16.0, pad: float = 8.0) -> List[Callout]:
    """Assign each (label, landmark) to the lane on its side of the core, order by the landmark's y inside each lane (so the leaders fan out without crossing), and give each label an evenly spread slot
    in its lane sized to its text. Returns the call-outs with boxes and leader anchors."""
    core = zones["core"]
    cx = (core[0] + core[2]) / 2
    sides: Dict[str, List[Callout]] = {"left": [], "right": []}
    for lab, lm in zip(labels, landmarks):
        sides["left" if lm[0] < cx else "right"].append(Callout(lab, lm, "left" if lm[0] < cx else "right"))
    # keep the lanes balanced: if one side got more than the lane can hold, spill the extras (the ones nearest the centre) to the other side
    def cap(lane: str) -> int:
        z = zones[lane]
        return max(1, int((z[3] - z[1]) // (height + 2 * pad + 10)))
    for a, b in (("left", "right"), ("right", "left")):
        while len(sides[a]) > cap(a) and len(sides[b]) < cap(b):
            c = min(sides[a], key=lambda c: abs(c.landmark[0] - cx) * -1)
            sides[a].remove(c)
            c.lane = b
            sides[b].append(c)
    out: List[Callout] = []
    lane_w = min(zones["left"][2] - zones["left"][0], zones["right"][2] - zones["right"][0]) - 8 - 2 * pad
    h_common, _ = fit_height([f"9 {c.label}" for lane in sides.values() for c in lane], lane_w, height)       # the number marker is part of the text
    for lane, items in sides.items():
        z = zones[lane]
        items.sort(key=lambda c: c.landmark[1])
        n = len(items)
        for i, c in enumerate(items):
            slot_h = (z[3] - z[1]) / max(n, 1)
            lines = wrap_label(f"9 {c.label}", lane_w, h_common)
            c.height, c.lines = h_common, len(lines)
            tw = max(CA.text_size(ln, h_common)[0] for ln in lines)
            th = len(lines) * h_common + (len(lines) - 1) * 4
            bw, bh = min(tw + 2 * pad, z[2] - z[0] - 8), th + 2 * pad
            cy = z[1] + slot_h * (i + 0.5)
            x0 = z[0] + 4 if lane == "left" else z[2] - bw - 4
            c.box = (x0, cy - bh / 2, x0 + bw, cy + bh / 2)
            c.anchor = (c.box[2], cy) if lane == "left" else (c.box[0], cy)
            out.append(c)
    for k, c in enumerate(sorted(out, key=lambda c: (c.landmark[1], c.landmark[0])), 1):
        c.number = k
    return out


def callout_strokes(c: Callout, height: float = 0.0, pad: float = 8.0, number_marker: bool = True) -> List[Stroke]:
    """The label box, its text (wrapped), and the leader arrow from the box to the landmark (the arrowhead lands ON the landmark)."""
    height = height or c.height
    out = [Stroke(CA.resample(CA.rect_pts(c.box), 4.0), "rectangle", f"callout{c.number}:box", "Pencil", {"cell": c.box})]
    label = f"{c.number} {c.label}" if number_marker else c.label
    lane_w = (c.box[2] - c.box[0]) - 2 * pad + 0.5
    for k, line in enumerate(wrap_label(label, lane_w, height) if c.lines > 1 else [label]):
        out.extend(CA.text_strokes(line, (c.box[0] + pad, c.box[1] + pad + k * (height + 4)), height))
    a, b = c.anchor, c.landmark
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    tip = (b[0] - 3 * math.cos(ang), b[1] - 3 * math.sin(ang))                   # stop a hair before the landmark so the head sits beside the stroke it names
    for poly in CA.arrow(a, tip, 11.0):
        out.append(Stroke(CA.resample(poly, 4.0), "arrow", f"callout{c.number}:leader", "Pencil", {"from": a, "to": tip}))
    return out


# ------------------------------------------------------------------------------------------------------------------------------------ magnifier + zoom panel
def magnifier(landmark: Pt, radius: float, panel: Box, zoom_strokes: Sequence[Stroke]) -> List[Stroke]:
    """A circle around the region of interest, a framed zoom panel in a margin lane holding the (already re-traced, larger) detail, and two tangent-style leader lines between them."""
    circle = Stroke(CA.resample(CA.ellipse_pts((landmark[0] - radius, landmark[1] - radius, landmark[0] + radius, landmark[1] + radius)), 4.0), "ellipse", "magnifier:circle", "Pencil", {"cell": (landmark[0] - radius, landmark[1] - radius, landmark[0] + radius, landmark[1] + radius)})
    frame = Stroke(CA.resample(CA.rect_pts(panel), 4.0), "rectangle", "magnifier:panel", "Pencil", {"cell": panel})
    pc = ((panel[0] + panel[2]) / 2, (panel[1] + panel[3]) / 2)
    ang = math.atan2(pc[1] - landmark[1], pc[0] - landmark[0])
    out = [circle, frame]
    for sgn in (-1, 1):
        a = (landmark[0] + radius * math.cos(ang + sgn * 0.5 * math.pi), landmark[1] + radius * math.sin(ang + sgn * 0.5 * math.pi))
        corner = (panel[0] if landmark[0] < pc[0] else panel[2], panel[1] if sgn < 0 else panel[3])
        out.append(Stroke(CA.resample([a, corner], 4.0), "path", "magnifier:leader", "Pencil", {"from": a, "to": corner}))
    out.extend(zoom_strokes)
    return out


# ------------------------------------------------------------------------------------------------------------------------------------ the composition
def plan_lightboard(canvas: Box, art: Sequence[Stroke], title: str, labels: Sequence[Any], steps: Sequence[str], landmarks: Optional[Sequence[Pt]] = None,
                    art_zone: str = "core", frame: bool = True, stats: Optional[Dict[str, Any]] = None) -> Tuple[List[Stroke], Dict[str, Any]]:
    """A complete lightboard page around already-placed `art` strokes (they must lie in the core zone): header with title + underline, call-outs with leaders and numbered markers in both lanes, a footer with the
    numbered step summary, a frame around the core. Returns (strokes, layout) where layout holds zones / callouts for the audit."""
    zones = lightboard_zones(canvas)
    # `labels` items are either "TEXT" (the landmark is chosen automatically) or ("TEXT", (fx, fy)): where on the REFERENCE image the part is, as fractions; it is mapped to the canvas through the tracer's map
    # and snapped onto the nearest traced stroke, so the leader ends on the drawing itself.
    texts, lms = [], []
    auto = auto_landmarks(art, len(labels))
    for i, item in enumerate(labels):
        text, rel = (item, None) if isinstance(item, str) else (item[0], item[1])
        if landmarks and i < len(landmarks):
            pt = landmarks[i]
        elif rel is not None and stats is not None:
            pt = snap_to_art(rel_to_canvas(rel, stats), art)
        elif i < len(auto):
            pt = auto[i]
        else:
            continue
        texts.append(text)
        lms.append(pt)
    callouts = place_callouts(zones, texts, lms)
    strokes: List[Stroke] = []
    # header: the title centred, a rule under it
    o, h = CA.fit_text(title, CA.inset(zones["header"], 6), 26)
    ts = CA.text_strokes(title, o, h)
    for s in ts:
        s.group = "header"
    strokes += ts
    tb = stroke_bbox(ts) if ts else zones["header"]
    strokes.append(Stroke(CA.resample([(tb[0], tb[3] + 8), (tb[2], tb[3] + 8)], 4.0), "line", "header:rule", "Pencil", {"cell": (tb[0], tb[3] + 8, tb[2], tb[3] + 9)}))
    # call-outs
    for c in callouts:
        strokes += callout_strokes(c)
    # footer: one line per step, numbered, small, in two columns when there are many
    fz = CA.inset(zones["footer"], 6)
    cols = 2 if len(steps) > 3 else 1
    per = int(math.ceil(len(steps) / cols))
    colw = (fz[2] - fz[0]) / cols
    lh = min(14.0, (fz[3] - fz[1]) / max(per, 1) - 4)
    for i, st in enumerate(steps):
        cidx, r = divmod(i, per)
        txt = f"{i + 1}. {st}"
        box = (fz[0] + cidx * colw, fz[1] + r * (lh + 4), fz[0] + (cidx + 1) * colw - 8, fz[1] + r * (lh + 4) + lh)
        o2, h2 = CA.fit_text(txt, box, lh)
        ss = CA.text_strokes(txt, (box[0], o2[1]), h2)
        for s in ss:
            s.group = f"footer{i}"
        strokes += ss
    if frame:
        z = zones[art_zone]
        strokes.append(Stroke(CA.resample(CA.rect_pts(CA.inset(z, 2)), 4.0), "rectangle", "frame", "Pencil", {"cell": z}))
    return strokes, {"zones": zones, "callouts": callouts, "landmarks": lms}


def audit(layout: Dict[str, Any], art: Sequence[Stroke], strokes: Sequence[Stroke], canvas: Box, size: Tuple[int, int]) -> Dict[str, Any]:
    """The measured checks of a lightboard page: containment; call-out boxes disjoint from each other and from the artwork; no two leaders crossing; no leader passing through another call-out box; every
    leader ends on its landmark; labels fit their boxes."""
    callouts: List[Callout] = layout["callouts"]
    art_bb = stroke_bbox(art) if art else (0, 0, 0, 0)
    boxes_overlap = [(a.label, b.label) for i, a in enumerate(callouts) for b in callouts[i + 1:]
                     if not (a.box[2] + 2 <= b.box[0] or b.box[2] + 2 <= a.box[0] or a.box[3] + 2 <= b.box[1] or b.box[3] + 2 <= a.box[1])]
    box_on_art = [c.label for c in callouts if not (c.box[2] < art_bb[0] or c.box[0] > art_bb[2] or c.box[3] < art_bb[1] or c.box[1] > art_bb[3])]
    cross = []
    for i, a in enumerate(callouts):
        for b in callouts[i + 1:]:
            if _seg_intersect(a.anchor, a.landmark, b.anchor, b.landmark):
                cross.append((a.label, b.label))
    through = [(a.label, b.label) for a in callouts for b in callouts if a is not b and _seg_hits_box(a.anchor, a.landmark, b.box, 1.0)]
    ends = [c.label for c in callouts if math.dist(next(s for s in callout_strokes(c) if s.group == f"callout{c.number}:leader").meta["to"], c.landmark) > 4.5]
    return {"containment_pct": CA.containment(strokes, canvas), "callouts": len(callouts), "box_overlaps": boxes_overlap, "boxes_on_artwork": box_on_art, "leader_crossings": cross,
            "leaders_through_boxes": through, "leaders_not_on_landmark": ends, "ok": not (boxes_overlap or box_on_art or cross or through or ends) and CA.containment(strokes, canvas) == 100.0}
