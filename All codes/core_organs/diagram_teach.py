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
    if (mid[0] - cx) * n[0] + (mid[1] - cy) * n[1] < 0:
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



# ---------------------------------------------------------------------------------------------------------------------------------------------- geometry scenes
# A model is bad at coordinates and good at naming things. For a geometric concept it writes a SCENE (what exists and how the pieces relate: a right triangle with legs 3 and 4, a square on each side); this compiler
# computes every vertex exactly, so right angles are right, squares are square, and a shape built on a side lies outside and shares that side.
SCENE_TYPES = ("right_triangle", "triangle", "rectangle", "square", "regular_polygon", "circle", "square_on", "triangle_on", "segment", "arrow_between", "stack", "flow", "cycle")


def _poly_area(pts: Sequence[Tuple[float, float]]) -> float:
    return abs(sum(pts[k][0] * pts[(k + 1) % len(pts)][1] - pts[(k + 1) % len(pts)][0] * pts[k][1] for k in range(len(pts)))) / 2.0


def _sides_of(obj: Dict[str, Any]) -> Dict[str, Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Named sides of a compiled polygon: 'side0'.. in order, plus for a right triangle 'leg_a' (the horizontal leg), 'leg_b' (the vertical one) and 'hypotenuse'."""
    pts = obj["points"]
    out = {f"side{k}": (pts[k], pts[(k + 1) % len(pts)]) for k in range(len(pts))}
    if obj.get("type") == "right_triangle":
        out.update({"leg_a": (pts[0], pts[1]), "leg_b": (pts[0], pts[2]), "hypotenuse": (pts[1], pts[2])})
    return out


def _layout(kind: str, items: Sequence[str]) -> List[Dict[str, Any]]:
    """Exact positions for the idea-shaped diagrams, in a 0-100 canvas. Labels sit BESIDE their shapes (the overlay puts a pill to the right of a shape), so shapes are spaced to leave that room.
      stack  layers one above the other (the first at the bottom), each a wide bar;     flow   steps top to bottom, each a box, an arrow from one to the next;
      cycle  nodes on a circle, each a small round node, an arrow from one to the next (and from the last back to the first)."""
    import math
    n = len(items)
    parts: List[Dict[str, Any]] = []
    if kind in ("stack", "flow"):
        h, gap, w, x0 = 8.0, (1.0 if kind == "stack" else 6.0), 30.0, 12.0
        total = n * h + (n - 1) * gap
        y_top = 50 - total / 2
        for k in range(n):
            y = y_top + (n - 1 - k) * (h + gap) if kind == "stack" else y_top + k * (h + gap)
            parts.append({"kind": "polygon", "points": [(x0, y), (x0 + w, y), (x0 + w, y + h), (x0, y + h)], "label": items[k], "item": k})
            if kind == "flow" and k < n - 1:
                parts.append({"kind": "arrow", "points": [(x0 + w / 2, y + h), (x0 + w / 2, y + h + gap)], "label": "", "item": k, "repeat": True})
        return parts
    R, r = 30.0, 4.5
    pts = [(46 + R * math.cos(-math.pi / 2 + 2 * math.pi * k / n), 50 + R * math.sin(-math.pi / 2 + 2 * math.pi * k / n)) for k in range(n)]
    for k, (cx, cy) in enumerate(pts):
        parts.append({"kind": "polygon", "points": [(cx + r * math.cos(2 * math.pi * j / 20), cy + r * math.sin(2 * math.pi * j / 20)) for j in range(20)], "label": items[k], "item": k})
        nx, ny = pts[(k + 1) % n]
        d = math.hypot(nx - cx, ny - cy) or 1.0
        ux, uy = (nx - cx) / d, (ny - cy) / d
        parts.append({"kind": "arrow", "points": [(cx + ux * (r + 1), cy + uy * (r + 1)), (nx - ux * (r + 1.5), ny - uy * (r + 1.5))], "label": "", "item": k, "repeat": True})
    return parts


def compile_scene(scene: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    """scene = {"objects": [{"id", "type", ...}], "steps": [{"show": [ids], "say": "..."}]} -> (parts for to_screen, problems). Parts are in canvas units, scaled so the whole figure fits 10..90."""
    import math
    probs: List[str] = []
    if not isinstance(scene, dict) or not isinstance(scene.get("objects"), list):
        return [], ["no 'objects' list"]
    built: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for i, o in enumerate(scene["objects"][:14], 1):
        if not isinstance(o, dict):
            continue
        oid = str(o.get("id") or f"o{i}")
        typ = str(o.get("type", "")).lower().strip()
        if typ not in SCENE_TYPES:
            probs.append(f"object {oid}: type must be one of {', '.join(SCENE_TYPES)}")
            continue
        label = str(o.get("label", ""))[:28]
        try:
            if typ == "right_triangle":
                a, b = (float(x) for x in (o.get("legs") or [3, 4])[:2])
                pts = [(0.0, 0.0), (a, 0.0), (0.0, -b)]                     # right angle at the origin, y grows downward on screen
            elif typ == "triangle":
                a, b, c = (float(x) for x in (o.get("sides") or [3, 4, 5])[:3])
                if a + b <= c or a + c <= b or b + c <= a:
                    probs.append(f"object {oid}: sides {a}, {b}, {c} do not make a triangle")
                    continue
                x = (a * a + c * c - b * b) / (2 * a)
                pts = [(0.0, 0.0), (a, 0.0), (x, -math.sqrt(max(c * c - x * x, 0.0)))]
            elif typ == "rectangle":
                w, h = float(o.get("w", 4)), float(o.get("h", 2))
                pts = [(0.0, 0.0), (w, 0.0), (w, -h), (0.0, -h)]
            elif typ == "square":
                w = float(o.get("side", 3))
                pts = [(0.0, 0.0), (w, 0.0), (w, -w), (0.0, -w)]
            elif typ == "regular_polygon":
                n, w = int(o.get("n", 6)), float(o.get("side", 2))
                r = w / (2 * math.sin(math.pi / n))
                pts = [(r * math.cos(2 * math.pi * k / n), -r * math.sin(2 * math.pi * k / n)) for k in range(n)]
            elif typ == "circle":
                r = float(o.get("r", 2))
                pts = [(r * math.cos(2 * math.pi * k / 48), -r * math.sin(2 * math.pi * k / 48)) for k in range(48)]
            elif typ in ("square_on", "triangle_on"):
                base = built.get(str(o.get("of")))
                if base is None or base["kind"] != "polygon" or len(base["points"]) < 3:
                    probs.append(f"object {oid}: 'of' must name an EARLIER polygon (got {o.get('of')!r})")
                    continue
                sides = _sides_of(base)
                sname = str(o.get("side", "side0"))
                if sname not in sides:
                    probs.append(f"object {oid}: side {sname!r} is not one of {', '.join(sides)}")
                    continue
                (ax, ay), (bx, by) = sides[sname]
                cx = sum(q[0] for q in base["points"]) / len(base["points"])
                cy = sum(q[1] for q in base["points"]) / len(base["points"])
                dx, dy = bx - ax, by - ay
                nx, ny = -dy, dx
                mx, my = (ax + bx) / 2, (ay + by) / 2
                if (mx - cx) * nx + (my - cy) * ny < 0:
                    nx, ny = dy, -dx                                       # the normal that points away from the base shape
                if typ == "square_on":
                    pts = [(ax, ay), (bx, by), (bx + nx, by + ny), (ax + nx, ay + ny)]
                else:
                    h = math.sqrt(3) / 2.0
                    pts = [(ax, ay), (bx, by), (mx + nx * h, my + ny * h)]
            elif typ in ("stack", "flow", "cycle"):
                items = [str(x)[:22] for x in (o.get("layers") or o.get("steps") or o.get("nodes") or [])][:8]
                if len(items) < 2:
                    probs.append(f"object {oid}: {typ} needs at least 2 items (layers / steps / nodes)")
                    continue
                says_i = [str(x)[:160] for x in (o.get("says") or [])]
                made = _layout(typ, items)
                for k, part in enumerate(made):
                    pid = f"{oid}.{k}"
                    built[pid] = {"id": pid, "type": typ, "kind": part["kind"], "points": part["points"], "label": part["label"], "say_ix": part.get("item"), "layout": True}
                    order.append(pid)
                    if part.get("item") is not None and part["item"] < len(says_i):
                        built[pid]["say"] = says_i[part["item"]] if not part.get("repeat") else ""
                continue
            elif typ in ("segment", "arrow_between"):
                a_ref, b_ref = str(o.get("from", "")), str(o.get("to", ""))
                pa, pb = _point_ref(built, a_ref), _point_ref(built, b_ref)
                if pa is None or pb is None:
                    probs.append(f"object {oid}: 'from'/'to' must be 'id.sideN' midpoints or 'id.vertexN' of earlier shapes")
                    continue
                built[oid] = {"id": oid, "type": typ, "kind": "line" if typ == "segment" else "arrow", "points": [pa, pb], "label": label}
                order.append(oid)
                continue
        except Exception as exc:
            probs.append(f"object {oid}: {type(exc).__name__}: {str(exc)[:60]}")
            continue
        placed = [(float(x) + (float(o.get("at", [0, 0])[0]) if isinstance(o.get("at"), list) else 0.0), float(y) + (float(o.get("at", [0, 0])[1]) if isinstance(o.get("at"), list) else 0.0)) for x, y in pts]
        built[oid] = {"id": oid, "type": typ, "kind": "curve" if typ == "circle" else "polygon", "points": placed if typ != "circle" else placed + [placed[0]], "label": label}
        if typ == "circle":
            built[oid]["kind"] = "polygon"
        order.append(oid)
    if not built:
        return [], probs or ["empty scene"]
    # one uniform scale + shift for the whole figure (right angles and equal sides survive)
    xs = [x for b in built.values() for x, _y in b["points"]]
    ys = [y for b in built.values() for _x, y in b["points"]]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    k = min(80.0 / w if w else 1e9, 80.0 / h if h else 1e9)
    ox, oy = 10 + (80 - w * k) / 2 - min(xs) * k, 10 + (80 - h * k) / 2 - min(ys) * k
    for b in built.values():
        b["points"] = [(x * k + ox, y * k + oy) for x, y in b["points"]]
    # the order things appear in: the steps' 'show' lists, else the objects' own order
    says: Dict[str, str] = {}
    seq: List[str] = []
    for st in scene.get("steps", []) if isinstance(scene.get("steps"), list) else []:
        if not isinstance(st, dict):
            continue
        for oid in (st.get("show") or []) if isinstance(st.get("show"), list) else []:
            oid = str(oid)
            if oid in built and oid not in seq:
                seq.append(oid)
                says[oid] = str(st.get("say", ""))[:160]
    for oid in order:
        if oid not in seq:
            seq.append(oid)
    parts = []
    for oid in seq:
        b = built[oid]
        parts.append({"kind": b["kind"], "points": b["points"], "label": b["label"], "say": says.get(oid, b.get("say", "")), "built": b["type"] in ("square_on", "triangle_on") or bool(b.get("layout"))})
    return parts, probs


def _point_ref(built: Dict[str, Dict[str, Any]], ref: str) -> Optional[Tuple[float, float]]:
    m = re.match(r"^(\w+)\.(side|vertex|leg_a|leg_b|hypotenuse)(\d*)$", ref.strip())
    if not m or m.group(1) not in built or len(built[m.group(1)]["points"]) < 2:
        return None
    b = built[m.group(1)]
    pts = b["points"]
    if m.group(2) == "vertex":
        return tuple(pts[int(m.group(3) or 0) % len(pts)])
    sides = _sides_of(b)
    key = m.group(2) + m.group(3) if m.group(2) == "side" else m.group(2)
    if key not in sides:
        return None
    (ax, ay), (bx, by) = sides[key]
    return ((ax + bx) / 2, (ay + by) / 2)


SCENE_EXAMPLE = {"mode": "geometry", "title": "the area of a rectangle and the square on its side", "objects": [
    {"id": "r", "type": "rectangle", "w": 6, "h": 3, "label": "rectangle"},
    {"id": "s", "type": "square_on", "of": "r", "side": "side1", "label": "square"},
    {"id": "w", "type": "arrow_between", "from": "r.side0", "to": "r.side2", "label": "height"}],
    "steps": [{"show": ["r"], "say": "Here is the rectangle."}, {"show": ["s"], "say": "A square can be built on its short side; it lies outside the rectangle."}, {"show": ["w"], "say": "The height runs between the long sides."}]}


def scene_prompt(request: str, problems: Sequence[str] = ()) -> str:
    import json
    lines = [f'Request: "{request}"', "",
             "Decide how to draw it. Reply with a SCENE: the objects that exist and how they relate (a geometric figure, or an idea made of layers / steps / a loop). Do NOT write coordinates: the drawing program computes them.",
             "For an idea made of LAYERS, STEPS or a LOOP use: stack {layers:[names, bottom first], says:[one sentence each]} | flow {steps:[names in order], says:[...]} | cycle {nodes:[names in order], says:[...]} - the program lays them out and draws the arrows. "
             "Object types for geometric figures: right_triangle {legs:[a,b]} | triangle {sides:[a,b,c]} | rectangle {w,h} | square {side} | regular_polygon {n,side} | circle {r} | square_on {of: earlier object id, side} | triangle_on {of, side} | segment {from,to} | arrow_between {from,to}.",
             "Side names of a right_triangle: leg_a, leg_b, hypotenuse. Any polygon: side0, side1, side2 ... A square_on / triangle_on is built OUTSIDE its base shape on the side you name. Points for segment / arrow_between are 'id.sideN' (the middle of that side) or 'id.vertexN'.",
             "Each object has an id, a type, a label of at most 3 words. steps: the order they appear, each {show: [ids], say: ONE short sentence spoken while it is drawn}. Objects must be defined BEFORE anything that refers to them.",
             "Use freeform ONLY when none of the types fit: reply {\"mode\": \"freeform\"} and nothing else.",
             "Reply with JSON only. Example of a scene (a different topic):", json.dumps(SCENE_EXAMPLE)]
    if problems:
        lines += ["", "Your previous scene had these problems, fix them:"] + ["- " + p for p in problems]
    return "\n".join(lines)


def is_geometric(brain: Any, request: str) -> bool:
    """Is the idea mainly the shapes, sizes, angles, areas or construction of geometric figures? A cheap yes/no question; 'no' (or no answer) sends the request to the free-form planner."""
    try:
        q = (f'Request: "{request}" | Is explaining this mainly about geometric figures - triangles, squares, rectangles, circles, polygons, their sides, angles or areas? '
             'A process, a cycle, a flow, a list, a system or a layered idea is NOT. Reply JSON {"geometric": true or false}')
        obj, _m = brain.json(q, "You classify requests. JSON only.", max_tokens=30, temperature=0.0)
        return isinstance(obj, dict) and obj.get("geometric") is True
    except Exception:
        return False


LAYOUT_EXAMPLE = {"mode": "layout", "title": "how a seed becomes a plant", "objects": [
    {"id": "g", "type": "cycle", "nodes": ["Seed", "Sprout", "Plant", "Flower"], "says": ["A seed lies in the soil.", "Water wakes it and a sprout appears.", "The sprout grows into a plant.", "The flower makes new seeds."]}]}
LAYOUT_EXAMPLE2 = {"mode": "layout", "title": "the layers of a cake", "objects": [
    {"id": "c", "type": "stack", "layers": ["Plate", "Sponge", "Cream", "Icing"], "says": ["Start with the plate.", "The sponge goes on it.", "Cream is spread on the sponge.", "Icing covers the top."]}]}


def layout_prompt(request: str, problems: Sequence[str] = ()) -> str:
    import json
    lines = [f'Request: "{request}"', "",
             "Explain it with a simple diagram of NAMED PARTS. Reply with a SCENE using exactly ONE object of one of these types - the drawing program lays it out and draws the arrows, so NEVER write coordinates:",
             "  stack {layers: [names, the BOTTOM one first], says: [one short sentence per layer]}   - an idea made of layers / parts built on each other",
             "  flow  {steps: [names in order], says: [...]}                                          - a sequence of steps",
             "  cycle {nodes: [names in order], says: [...]}                                           - something that loops back to its start",
             "Between 3 and 7 items, each name at most 3 words, says as long as the list. Choose the type that fits the idea. Reply JSON only; two examples (other topics):", json.dumps(LAYOUT_EXAMPLE), json.dumps(LAYOUT_EXAMPLE2)]
    if problems:
        lines += ["", "Your previous scene had these problems, fix them:"] + ["- " + x for x in problems]
    return " ".join(lines) if False else "\n".join(lines)



def plan_scene(brain: Any, request: str, tries: int = 3, family: str = "geometry") -> Dict[str, Any]:
    """{'mode': 'geometry'|'freeform', 'parts', 'problems', 'seconds'}: the scene route for geometric concepts (exact by construction), 'freeform' when the model says it is not geometry or fails to produce a usable scene."""
    probs: List[str] = []
    secs = 0.0
    for k in range(tries):
        obj, meta = brain.json((layout_prompt if family == "layout" else scene_prompt)(request, probs), "You teach by drawing exact, clean diagrams. JSON only.", max_tokens=900, temperature=min(0.2 + 0.1 * k, 0.5))
        secs += float(meta.get("seconds") or 0.0)
        if isinstance(obj, dict) and str(obj.get("mode", "")).lower() == "freeform" and family != "layout":
            return {"mode": "freeform", "parts": [], "problems": [], "seconds": round(secs, 1)}
        parts, probs = compile_scene(obj)
        if parts and not probs:
            return {"mode": "geometry", "parts": parts, "problems": [], "seconds": round(secs, 1), "title": (obj or {}).get("title", ""), "scene": obj}
    return {"mode": "freeform", "parts": [], "problems": probs, "seconds": round(secs, 1)}


def plan_diagram(brain: Any, request: str, tries: int = 5, scene_first: bool = True) -> Dict[str, Any]:
    """Ask the CPU brain for a diagram plan; ask again with the problems named when it is not usable."""
    sc = {"mode": "freeform"}
    if scene_first:
        family = "geometry" if is_geometric(brain, request) else "layout"          # a figure of shapes gets the geometry types; an idea of layers / steps / a loop gets stack / flow / cycle
        sc = plan_scene(brain, request, family=family)
        if sc["mode"] != "geometry" and family == "geometry":                    # the geometry route did not hold: try the layout one before giving up on scenes
            sc = plan_scene(brain, request, family="layout")
    if sc["mode"] == "geometry":
        return {"parts": sc["parts"], "problems": [], "seconds": sc["seconds"], "title": sc.get("title", ""), "mode": "geometry", "scene": sc.get("scene")}
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



def clear_region(image: Any, aspect: float = 1.25, frac: float = 0.62, avoid: Sequence[Tuple[float, float, float, float]] = ()) -> Tuple[float, float, float, float]:
    """The part of a picture with the least going on (lowest edge density over a sliding window): where a drawing disturbs the least. Falls back to the centre. Returns (x1, y1, x2, y2) in the picture's pixels."""
    try:
        import cv2
        import numpy as np
        g = np.asarray(image.convert("L"))
        H, W = g.shape
        e = cv2.Canny(g, 60, 150).astype(np.float32) / 255.0
        ii = cv2.integral(e)
        h = int(min(H * frac, W * frac / aspect))
        w = int(h * aspect)
        best, pos = 1e9, ((W - w) // 2, (H - h) // 2)
        step = max(16, min(H, W) // 24)
        for y in range(0, H - h + 1, step):
            for x in range(0, W - w + 1, step):
                dens = (ii[y + h, x + w] - ii[y, x + w] - ii[y + h, x] + ii[y, x]) / float(w * h)
                dens += 0.002 * (abs(x + w / 2 - W / 2) / W + abs(y + h / 2 - H / 2) / H)           # a slight pull to the middle
                for ax0, ay0, ax1, ay1 in avoid:                                                          # never over what the person is being pointed at
                    ox, oy = max(0.0, min(x + w, ax1) - max(x, ax0)), max(0.0, min(y + h, ay1) - max(y, ay0))
                    dens += 5.0 * (ox * oy) / float(w * h)
                if dens < best:
                    best, pos = dens, (x, y)
        return (float(pos[0]), float(pos[1]), float(pos[0] + w), float(pos[1] + h))
    except Exception:
        W, H = image.size
        return (W * 0.19, H * 0.19, W * 0.81, H * 0.81)



def plan_on_screen(brain: Any, request: str, image: Any, look: Optional[Dict[str, Any]] = None, avoid: Sequence[Tuple[float, float, float, float]] = ()) -> Dict[str, Any]:
    """Draw a concept FOR THIS SCREEN. `look` is what the vision model said about the live picture (vision_ground.look_at): if a diagram of the concept is already on screen, the answer is to POINT at it (annotate mode,
    its box); otherwise a figure is planned (exact geometry for a geometric concept, free-form otherwise) and placed in the quietest part of the screen on an opaque card, so it is legible over a video or a busy page."""
    look = look or {}
    W, H = image.size
    if look.get("diagram_visible") and look.get("bbox"):
        x0, y0, x1, y1 = (look["bbox"][0] * W, look["bbox"][1] * H, look["bbox"][2] * W, look["bbox"][3] * H)
        return {"mode": "annotate", "look": look, "box": (x0, y0, x1, y1), "parts": [], "card": None}
    plan = plan_diagram(brain, request)
    if not plan["parts"]:
        return {"mode": "none", "look": look, "parts": [], "card": None, "plan": plan}
    region = clear_region(image, avoid=avoid)
    pad = 16.0
    card = [(region[0] - pad, region[1] - pad), (region[2] + pad, region[1] - pad), (region[2] + pad, region[3] + pad), (region[0] - pad, region[3] + pad)]
    parts = to_screen(plan["parts"], (region[0] + 6, region[1] + 6, region[2] - 6, region[3] - 6))
    return {"mode": "draw", "look": look, "region": region, "card": card, "parts": parts, "plan": plan}


def to_screen(parts: Sequence[Dict[str, Any]], region: Tuple[float, float, float, float]) -> List[Dict[str, Any]]:
    """Canvas units -> screen pixels inside `region` (x1, y1, x2, y2): equal scale on both axes, centred."""
    x1, y1, x2, y2 = region
    side = min(x2 - x1, y2 - y1)
    ox, oy = x1 + (x2 - x1 - side) / 2.0, y1 + (y2 - y1 - side) / 2.0
    k = side / 100.0
    return [dict(p, points=[(ox + x * k, oy + y * k) for x, y in p["points"]]) for p in parts]
