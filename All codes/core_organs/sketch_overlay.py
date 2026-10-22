"""
sketch_overlay -- the live-teacher marks on top of the screen: curved arrows from a trigger to where the result will appear, drag gestures drawn over the canvas, and glowing loops around a whole cluster
of controls (a keypad, a colour palette, a chat list) BEFORE the single control is shown.

Drawing is done by tutor_overlay (the red vector layer): a layered window with WS_EX_TRANSPARENT (clicks pass through to the program underneath), WS_EX_NOACTIVATE (never takes focus), WS_EX_TOPMOST, drawn with
per-pixel alpha - so an animation never blocks a click the person or the agent makes and never steals the keyboard. `click_through()` checks those flags on the real window style.

    cluster_controls(controls)        -> [{members, box, n}]     controls that sit together, are alike in size and form a grid / row / column (found from geometry, no app knowledge)
    enclosure(box, pad, radius)       -> points                  a rounded loop around a region (closed outline, many points = smooth)
    bezier(p0, p1, bend)              -> points                  a curved path (quadratic Bezier, bowed to one side)
    motion_arrow(src, dst, bend)      -> points                  from the edge of the source region to the edge of the target region, stopping short of the target so it never covers it
    Sketcher(overlay).loop / .arrow / .drag / .group_then_focus / .clear
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core_organs import tutor_overlay as TO
from core_organs.professor import overlay as OV
from core_organs.professor.schema import Box

WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOPMOST, WS_EX_NOACTIVATE = 0x00080000, 0x00000020, 0x00000008, 0x08000000


def click_through(ex_style: int = OV._EX) -> Dict[str, bool]:
    """The window-style bits that make the overlay harmless: a click goes THROUGH it, it never becomes the active window, it stays on top."""
    return {"layered": bool(ex_style & WS_EX_LAYERED), "click_through": bool(ex_style & WS_EX_TRANSPARENT), "never_activates": bool(ex_style & WS_EX_NOACTIVATE), "topmost": bool(ex_style & WS_EX_TOPMOST)}


def _pt(p: Any) -> Tuple[float, float]:
    if hasattr(p, "x1"):
        return ((p.x1 + p.x2) / 2.0, (p.y1 + p.y2) / 2.0)
    if hasattr(p, "__len__") and len(p) >= 4:
        return (p[0] + p[2] / 2.0, p[1] + p[3] / 2.0)
    return (float(p[0]), float(p[1]))


def _box(b: Any) -> Box:
    if hasattr(b, "x1"):
        return b
    x, y, w, h = b[:4]
    return Box(float(x), float(y), float(x + w), float(y + h))


def bezier(p0: Tuple[float, float], p1: Tuple[float, float], bend: float = 0.25, n: int = 28) -> List[Tuple[float, float]]:
    """A curve from p0 to p1 bowed to one side by `bend` x the distance (0 = straight)."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    mid = ((p0[0] + p1[0]) / 2 - dy * bend, (p0[1] + p1[1]) / 2 + dx * bend)
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * mid[0] + t * t * p1[0], (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * mid[1] + t * t * p1[1]) for t in [i / (n - 1) for i in range(n)]]


def _edge_towards(b: Box, target: Tuple[float, float], gap: float = 6.0) -> Tuple[float, float]:
    """The point on the border of box b in the direction of `target`, pushed out by `gap`."""
    cx, cy = (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2
    dx, dy = target[0] - cx, target[1] - cy
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return (cx, cy)
    hw, hh = max((b.x2 - b.x1) / 2, 1e-6), max((b.y2 - b.y1) / 2, 1e-6)
    t = min(hw / abs(dx) if dx else 1e9, hh / abs(dy) if dy else 1e9)
    ex, ey = cx + dx * t, cy + dy * t
    d = math.hypot(dx, dy)
    return (ex + dx / d * gap, ey + dy / d * gap)


def motion_arrow(src: Any, dst: Any, bend: float = 0.22, gap: float = 8.0) -> List[Tuple[float, float]]:
    """From the source region's edge to the target region's edge (stopping `gap` short, so the head points AT it without covering it)."""
    sb, db = _box(src), _box(dst)
    a = _edge_towards(sb, _pt(db), gap)
    b = _edge_towards(db, _pt(sb), gap)
    return bezier(a, b, bend)


def enclosure(box: Any, pad: float = 10.0, radius: float = 18.0, per_corner: int = 7) -> List[Tuple[float, float]]:
    """A rounded loop around a region: a closed outline with smooth corners (the points of its four arcs)."""
    b = _box(box)
    x1, y1, x2, y2 = b.x1 - pad, b.y1 - pad, b.x2 + pad, b.y2 + pad
    r = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    pts: List[Tuple[float, float]] = []
    for cx, cy, a0 in ((x2 - r, y1 + r, -90), (x2 - r, y2 - r, 0), (x1 + r, y2 - r, 90), (x1 + r, y1 + r, 180)):
        for i in range(per_corner + 1):
            a = math.radians(a0 + 90 * i / per_corner)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def cluster_controls(controls: Sequence[Dict[str, Any]], min_members: int = 4, gap_factor: float = 1.1, size_ratio: float = 1.8) -> List[Dict[str, Any]]:
    """Controls that belong together: neighbours (gap below `gap_factor` x their own size), alike in size (within `size_ratio`), joined transitively. A cluster needs `min_members` and must look like a grid,
    row or column (its members fill at least a third of their bounding box). Found from geometry only: a keypad, a palette, a toolbar group, a list of chat rows."""
    items = [c for c in controls if c.get("box") and c["box"][2] >= 6 and c["box"][3] >= 6]
    n = len(items)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(n):
        xi, yi, wi, hi = items[i]["box"]
        for j in range(i + 1, n):
            xj, yj, wj, hj = items[j]["box"]
            if max(wi / wj, wj / wi) > size_ratio or max(hi / hj, hj / hi) > size_ratio:
                continue
            gx = max(0.0, max(xi, xj) - min(xi + wi, xj + wj))
            gy = max(0.0, max(yi, yj) - min(yi + hi, yj + hj))
            ref = max(min(wi, wj), min(hi, hj))
            if gx <= gap_factor * ref and gy <= gap_factor * ref and (gx == 0 or gy == 0 or min(gx, gy) <= 0.5 * ref):
                parent[find(i)] = find(j)
    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out: List[Dict[str, Any]] = []
    for idx in groups.values():
        if len(idx) < min_members:
            continue
        mem = [items[i] for i in idx]
        x1 = min(m["box"][0] for m in mem)
        y1 = min(m["box"][1] for m in mem)
        x2 = max(m["box"][0] + m["box"][2] for m in mem)
        y2 = max(m["box"][1] + m["box"][3] for m in mem)
        fill = sum(m["box"][2] * m["box"][3] for m in mem) / max((x2 - x1) * (y2 - y1), 1)
        if fill < 0.33:
            continue
        out.append({"members": mem, "n": len(mem), "box": Box(float(x1), float(y1), float(x2), float(y2)), "fill": round(fill, 2),
                    "typical": (statistics.median(m["box"][2] for m in mem), statistics.median(m["box"][3] for m in mem))})
    return sorted(out, key=lambda c: -c["n"])


class Sketcher:
    """Draws on any overlay with .shape/.box/.badge/.wipe (the real RedOverlay or the recording twin)."""

    def __init__(self, overlay: Any) -> None:
        self.ov = overlay

    def loop(self, region: Any, label: str = "", pad: float = 10.0) -> List[Tuple[float, float]]:
        pts = enclosure(region, pad)
        self.ov.shape("polygon", pts, pill=label, seconds=0.8)
        return pts

    def arrow(self, src: Any, dst: Any, label: str = "", bend: float = 0.22) -> List[Tuple[float, float]]:
        pts = motion_arrow(src, dst, bend)
        self.ov.shape("arrow", pts, pill=label, seconds=0.9)
        return pts

    def drag(self, points: Sequence[Tuple[float, float]], label: str = "") -> List[Tuple[float, float]]:
        """A drag gesture: the path the hand will take, smoothed, with a head at the end."""
        pts = TO.smooth(list(points), 3) if len(points) >= 3 else list(points)
        self.ov.shape("arrow", pts, pill=label, seconds=max(0.9, min(2.5, TO.path_length(pts) / 600.0)))
        return pts

    def group_then_focus(self, controls: Sequence[Dict[str, Any]], target: Any, label: str = "", trigger: Optional[Any] = None) -> Dict[str, Any]:
        """The teaching order: the loop around the cluster the target belongs to (the whole keypad), then the single box, then - if a trigger is named - the arrow from the trigger to the target."""
        tb = _box(target)
        tc = _pt(tb)
        home = next((c for c in cluster_controls(controls) if c["box"].x1 <= tc[0] <= c["box"].x2 and c["box"].y1 <= tc[1] <= c["box"].y2), None)
        done: Dict[str, Any] = {"cluster": home["n"] if home else 0}
        if home:
            self.loop(home["box"], f"{label or 'this group'} ({home['n']} controls)")
        self.ov.box(tb, pill=label, pointer=False)
        if trigger is not None:
            self.arrow(trigger, tb, "")
            done["arrow"] = True
        return done

    def clear(self) -> None:
        self.ov.wipe()
