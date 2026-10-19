"""
diagram_teach -- explain a concept by DRAWING it on the screen, over whatever the person is already looking at, synchronised with the voice.

No drawing program is opened. The brain (brain_planner, CPU) writes a small diagram plan in a 0-100 canvas: a few parts, each a shape (polygon / line / arrow / curve), a short label and ONE sentence to say. The plan is
checked (inside the canvas, enough points, not too many parts), mapped onto a region of the real screen with equal scale on both axes (a square stays square), and played part by part through the red overlay
(tutor_overlay): the stroke draws itself while the sentence is spoken, the label appears beside it.

    plan_diagram(brain, "explain the pythagorean theorem")   ->  parts in canvas units
    to_screen(parts, region)                                 ->  the same parts in screen pixels
    MicroTutor.explain(request)                              ->  draws + speaks it over the live screen
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

KINDS = ("polygon", "line", "arrow", "curve")
ASK_RX = re.compile(r"\b(draw|diagram|visuali[sz]e|illustrate|sketch|show me (?:visually|with a (?:drawing|picture|diagram))|on my screen|annotate)\b", re.I)


def is_diagram_request(text: str) -> bool:
    """A request to see something DRAWN (not a request to operate a control)."""
    return bool(ASK_RX.search(text or ""))


EXAMPLE = {"title": "area of a rectangle, and a square on its short side", "parts": [
    {"kind": "polygon", "points": [[20, 30], [70, 30], [70, 60], [20, 60]], "label": "rectangle", "say": "This is the rectangle."},
    {"kind": "arrow", "points": [[20, 68], [70, 68]], "label": "width", "say": "Measure its width along the bottom."},
    {"kind": "arrow", "points": [[78, 60], [78, 30]], "label": "height", "say": "And its height up the side."},
    {"kind": "polygon", "build": {"shape": "square", "on_part": 1, "side": 3}, "label": "square", "say": "A square can be built on the short left side; it is drawn for you outside the rectangle."},
    {"kind": "curve", "points": [[30, 40], [45, 50], [60, 40]], "label": "width times height", "say": "The area is the width multiplied by the height."}]}


def diagram_prompt(request: str, problems: Sequence[str] = ()) -> str:
    import json
    lines = [f'Request: "{request}"', "", "Explain it by drawing a diagram. Use a canvas of 100 x 100 units, origin at the top-left, y grows downward. Keep every point between 8 and 92.",
             "A plan has 3 to 8 parts, in the order you will explain them. Each part: kind (polygon = closed outline | line | arrow | curve), points as [x, y] pairs (polygon 3+, line / arrow 2+, curve 3+), "
             "a label of at most 3 words, and ONE short sentence to say while it is drawn.",
             "Use real proportions (a right angle must really be a right angle; a square must have equal sides). A shape built on a side of another shape shares that side's two end points and lies OUTSIDE it. "
             "Label a part with what it IS (triangle, square, circle); a triangle polygon has exactly 3 points, a square 4. To put a square or an equilateral triangle ON a side of an earlier polygon do NOT compute points: write "
             '{"kind": "polygon", "build": {"shape": "square", "on_part": 1, "side": 0}, "label": "square a", "say": "..."} (on_part = the number of the earlier part, side = 0 for its first edge, 1 for its second ...); '
             "it is built for you outside that polygon. Do not draw text: labels are added for you.",
             "Reply with JSON only, in this format (a different topic):", json.dumps(EXAMPLE)]
    if problems:
        lines += ["", "Your previous plan had these problems, fix them:"] + ["- " + p for p in problems]
    return "\n".join(lines)


def construct(build: Dict[str, Any], parts: Sequence[Dict[str, Any]]) -> Optional[List[Tuple[float, float]]]:
    """A shape built ON a side of an earlier polygon, computed (not guessed by the model): {"shape": "square" | "triangle", "on_part": <1-based part>, "side": <0-based side>}. The new shape shares that side's two end
    points and lies OUTSIDE the polygon (equilateral triangle for 'triangle')."""
    import math
    try:
        base = parts[int(build["on_part"]) - 1]
        pts = [tuple(q) for q in base["points"]]
        pts = pts[:-1] if len(pts) > 3 and pts[0] == pts[-1] else pts
        k = int(build.get("side", 0)) % len(pts)
        a, b = pts[k], pts[(k + 1) % len(pts)]
    except Exception:
        return None
    if base.get("kind") != "polygon":
        return None
    cx, cy = sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts)
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = (-dy, dx)
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    if (mid[0] + n[0] - cx) ** 2 + (mid[1] + n[1] - cy) ** 2 < (mid[0] - cx) ** 2 + (mid[1] - cy) ** 2:
        n = (dy, -dx)                                                     # the normal that points away from the polygon's centre
    shape = str(build.get("shape", "square")).lower()
    if shape == "square":
        return [a, b, (b[0] + n[0], b[1] + n[1]), (a[0] + n[0], a[1] + n[1])]
    if shape == "triangle":
        h = math.sqrt(3) / 2.0
        return [a, b, (mid[0] + n[0] * h, mid[1] + n[1] * h)]
    return None


def fit_canvas(parts: List[Dict[str, Any]], lo: float = 10.0, hi: float = 90.0) -> List[Dict[str, Any]]:
    """Constructed shapes can leave the 0-100 canvas: one uniform scale + shift brings the whole drawing inside it (proportions, right angles and equal sides are kept)."""
    xs = [x for p in parts for x, _y in p["points"]]
    ys = [y for p in parts for _x, y in p["points"]]
    if not xs:
        return parts
    if min(xs) >= 2 and max(xs) <= 98 and min(ys) >= 2 and max(ys) <= 98:
        return parts
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    k = min((hi - lo) / w if w else 1e9, (hi - lo) / h if h else 1e9)
    ox, oy = lo + ((hi - lo) - w * k) / 2 - min(xs) * k, lo + ((hi - lo) - h * k) / 2 - min(ys) * k
    return [dict(p, points=[(x * k + ox, y * k + oy) for x, y in p["points"]]) for p in parts]


def snap_shapes(parts: List[Dict[str, Any]]) -> List[str]:
    """Make a part BE the shape its label names, by arithmetic: a 'triangle' with 4+ corners keeps the 3 corners that span the largest area; a 'square' with 4 corners becomes a true square (same centre, side = sqrt(area),
    turned like its first edge). Returns what was changed."""
    import itertools
    import math
    notes: List[str] = []
    for i, p in enumerate(parts, 1):
        if p["kind"] != "polygon" or p.get("built"):
            continue
        label = p["label"].lower()
        pts = [tuple(q) for q in p["points"]]
        pts = pts[:-1] if len(pts) > 3 and pts[0] == pts[-1] else pts
        if re.search(r"\btriangles?\b", label) and len(pts) > 3:
            best = max(itertools.combinations(pts, 3), key=lambda t: abs((t[1][0] - t[0][0]) * (t[2][1] - t[0][1]) - (t[2][0] - t[0][0]) * (t[1][1] - t[0][1])))
            p["points"] = [tuple(q) for q in best]
            notes.append(f"part {i}: '{p['label']}' had {len(pts)} corners, kept the 3 that span the most area")
        elif re.search(r"\bsquares?\b", label) and len(pts) == 4:
            cx, cy = sum(q[0] for q in pts) / 4, sum(q[1] for q in pts) / 4
            area = abs(sum(pts[k][0] * pts[(k + 1) % 4][1] - pts[(k + 1) % 4][0] * pts[k][1] for k in range(4))) / 2.0
            side = math.sqrt(area)
            ang = math.atan2(pts[1][1] - pts[0][1], pts[1][0] - pts[0][0])
            h = side / 2.0
            p["points"] = [(cx + math.cos(ang) * dx - math.sin(ang) * dy, cy + math.sin(ang) * dx + math.cos(ang) * dy) for dx, dy in ((-h, -h), (h, -h), (h, h), (-h, h))]
            sides = [math.dist(pts[k], pts[(k + 1) % 4]) for k in range(4)]
            if max(sides) > 1.12 * min(sides):
                notes.append(f"part {i}: '{p['label']}' had sides {', '.join(str(round(x)) for x in sides)}, made a true square")
    return notes


def validate(obj: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    probs: List[str] = []
    parts: List[Dict[str, Any]] = []
    if not isinstance(obj, dict) or not isinstance(obj.get("parts"), list):
        return [], ["no 'parts' list"]
    for i, p in enumerate(obj["parts"][:10]):
        if not isinstance(p, dict):
            continue
        kind = str(p.get("kind", "")).lower()
        if kind not in KINDS:
            probs.append(f"part {i + 1}: kind must be one of {', '.join(KINDS)}")
            continue
        try:
            if isinstance(p.get("build"), dict) and kind == "polygon":
                pts = construct(p["build"], parts) or []
                if not pts:
                    probs.append(f"part {i + 1}: build needs {{shape: square|triangle, on_part: an EARLIER polygon (1-based), side: 0-based side}}")
                    continue
            else:
                pts = [(float(a), float(b)) for a, b in p.get("points", [])]
        except Exception:
            probs.append(f"part {i + 1}: points must be [x, y] pairs")
            continue
        need = {"polygon": 3, "line": 2, "arrow": 2, "curve": 3}[kind]
        if len(pts) < need:
            probs.append(f"part {i + 1}: a {kind} needs at least {need} points")
            continue
        built = isinstance(p.get("build"), dict)
        if not built and any(not (2 <= x <= 98 and 2 <= y <= 98) for x, y in pts):
            probs.append(f"part {i + 1}: keep the points between 8 and 92")
            continue
        parts.append({"kind": kind, "points": pts, "label": str(p.get("label", ""))[:28], "say": str(p.get("say", ""))[:160], "built": built})
    if len(parts) < 2:
        probs.append("at least 2 usable parts are needed")
    snap_shapes(parts)
    return fit_canvas(parts), probs


SHAPE_WORDS = {"triangle": 3, "square": 4, "rectangle": 4, "quadrilateral": 4, "pentagon": 5, "hexagon": 6}


def _angle(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]) -> float:
    """Angle at b (degrees)."""
    import math
    v1, v2 = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
    n = math.hypot(*v1) * math.hypot(*v2)
    if n == 0:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / n))))


def geometry_problems(parts: Sequence[Dict[str, Any]]) -> List[str]:
    """A critic for drawn geometry, read from the plan's own words: a part whose label / sentence names a shape must BE that shape (a triangle has 3 corners, a square 4 equal sides and right angles, a rectangle 4 right angles,
    'right triangle' has a 90 degree corner), two outlines must not sit on top of each other, and nothing may be a sliver. The planner is told what is wrong and draws again."""
    import math
    probs: List[str] = []
    polys = []
    for i, p in enumerate(parts, 1):
        words = (p["label"] + " " + p["say"]).lower()
        pts = [tuple(q) for q in p["points"]]
        if p["kind"] != "polygon":
            continue
        pts = pts[:-1] if len(pts) > 3 and pts[0] == pts[-1] else pts
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        area = abs(sum(pts[k][0] * pts[(k + 1) % len(pts)][1] - pts[(k + 1) % len(pts)][0] * pts[k][1] for k in range(len(pts)))) / 2.0
        if area < 25:
            probs.append(f"part {i}: the outline is a sliver (area {area:.0f}); make it clearly visible")
        polys.append((i, min(xs), min(ys), max(xs), max(ys), area))
        label = p["label"].lower()
        for w, n in SHAPE_WORDS.items():                                   # the LABEL says what the part is; the sentence may talk about other shapes
            if not p.get("built") and re.search(r"\b" + w + r"s?\b", label) and len(pts) != n:
                probs.append(f"part {i} is labelled a {w} but has {len(pts)} corners; a {w} has {n}")
                break
        if not p.get("built") and len(pts) == 4 and re.search(r"\bsquare\b", label):
            sides = [math.dist(pts[k], pts[(k + 1) % 4]) for k in range(4)]
            if max(sides) > 1.12 * min(sides):
                probs.append(f"part {i} is a square but its sides are {', '.join(str(round(x)) for x in sides)}; they must be equal")
        if not p.get("built") and len(pts) == 3 and re.search(r"\bright\b", label):
            if not any(abs(_angle(pts[(k - 1) % 3], pts[k], pts[(k + 1) % 3]) - 90) <= 7 for k in range(3)):
                probs.append(f"part {i} is a right triangle but no corner is 90 degrees")
    import numpy as np
    import cv2

    def mask(pts: Sequence[Tuple[float, float]]) -> Any:
        m = np.zeros((200, 200), np.uint8)
        cv2.fillPoly(m, [np.array([(int(x * 2), int(y * 2)) for x, y in pts], np.int32)], 1)
        return m
    shapes = [(i, mask([tuple(q) for q in p["points"]])) for i, p in enumerate(parts, 1) if p["kind"] == "polygon"]
    for a in range(len(shapes)):
        for b in range(a + 1, len(shapes)):
            (i, ma), (j, mb) = shapes[a], shapes[b]
            inter = int((ma & mb).sum())
            small = max(1, min(int(ma.sum()), int(mb.sum())))
            if inter > 0.3 * small:
                probs.append(f"parts {i} and {j} overlap ({100 * inter // small}% of the smaller); place the second beside or outside the first (a shape built on a side shares that side and lies outside)")
    return probs


def plan_diagram(brain: Any, request: str, tries: int = 5) -> Dict[str, Any]:
    """Ask the CPU brain for a diagram plan; ask again with the problems named when it is not usable."""
    probs: List[str] = []
    best: List[Dict[str, Any]] = []
    best_probs = 10 ** 6
    best_list: List[str] = []
    secs = 0.0
    for k in range(tries):
        obj, meta = brain.json(diagram_prompt(request, probs), "You teach by drawing clear, correct diagrams. JSON only.", max_tokens=900, temperature=min(0.25 + 0.12 * k, 0.7))      # a stuck plan is re-drawn a little more freely each time
        secs += float(meta.get("seconds") or 0.0)
        parts, probs = validate(obj)
        probs = probs + (geometry_problems(parts) if parts else [])
        if parts and (not best or len(probs) <= best_probs):
            best, best_probs, best_list = parts, len(probs), list(probs)
        if not probs:
            break
    if best and best_list and all(" overlap (" in x for x in best_list):             # last resort: when every remaining problem is an outline lying on another, the LATER outline is dropped (its sentence goes with it)
        drop = set()
        for x in best_list:
            m = re.match(r"parts (\d+) and (\d+) overlap", x)
            if m:
                drop.add(int(m.group(2)))
        kept = [pt for k, pt in enumerate(best, 1) if k not in drop or pt.get("built")]
        if len(kept) >= 3 and not geometry_problems(kept):
            best, best_list = kept, []
    return {"parts": best, "problems": best_list if best else probs, "seconds": round(secs, 1), "title": (obj or {}).get("title", "") if isinstance(obj, dict) else ""}


def to_screen(parts: Sequence[Dict[str, Any]], region: Tuple[float, float, float, float]) -> List[Dict[str, Any]]:
    """Canvas units -> screen pixels inside `region` (x1, y1, x2, y2): equal scale on both axes, centred."""
    x1, y1, x2, y2 = region
    side = min(x2 - x1, y2 - y1)
    ox, oy = x1 + (x2 - x1 - side) / 2.0, y1 + (y2 - y1 - side) / 2.0
    k = side / 100.0
    return [dict(p, points=[(ox + x * k, oy + y * k) for x, y in p["points"]]) for p in parts]
