"""
professor.pointing -- where the Professor points: tags in a model's text, element ids, screen mapping, and the flight path of the pointer.

Tag forms (Clicky-compatible, plus ids):
    [POINT:#12:save button]        element 12 of the current ScreenModel      <- preferred: the box was MEASURED, nothing is guessed
    [POINT:640,48:save button]     pixel in the screenshot the model was shown
    [POINT:640,48:terminal:screen2] same, on monitor 2
    [POINT:none]                   nothing to point at
Resolution always ends in SCREEN pixels (virtual-desktop space) so the overlay, which lives in that space, never needs to know how the picture was scaled.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .schema import Box, PointCommand, ScreenModel

TAG = re.compile(r"\[POINT:\s*(none|#\d+|-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?)\s*(?::\s*([^:\]]*?))?\s*(?::\s*screen\s*(\d+))?\s*\]", re.I)


@dataclass
class PointTag:
    kind: str                       # none | id | xy
    element_id: Optional[int] = None
    x: float = 0.0
    y: float = 0.0
    label: str = ""
    screen: int = 0


def parse_tags(text: str) -> Tuple[str, List[PointTag]]:
    """(text without tags, tags in order). Tolerates spaces and any case."""
    tags: List[PointTag] = []
    for m in TAG.finditer(text or ""):
        body, label, screen = m.group(1).strip(), (m.group(2) or "").strip(), int(m.group(3) or 0)
        if body.lower() == "none":
            tags.append(PointTag("none"))
        elif body.startswith("#"):
            tags.append(PointTag("id", element_id=int(body[1:]), label=label, screen=screen))
        else:
            xs, ys = [float(v) for v in body.split(",")]
            tags.append(PointTag("xy", x=xs, y=ys, label=label, screen=screen))
    return TAG.sub("", text or "").strip(), tags


def resolve(tag: PointTag, sm: Optional[ScreenModel], picture_size: Optional[Tuple[int, int]] = None, action: str = "look") -> Optional[PointCommand]:
    """A PointCommand in screen pixels, or None. `picture_size` is the size of the picture the model saw (for xy tags; sm.size when omitted)."""
    if tag.kind == "none":
        return None
    if tag.kind == "id" and sm is not None:
        e = sm.element(tag.element_id or -1)
        if e is None:
            return None
        return PointCommand(e.bbox, tag.label or e.label, "highlight", action, e.id)
    if tag.kind == "xy" and sm is not None:
        w, h = picture_size or sm.size
        sx = sm.size[0] / w if w else 1.0
        sy = sm.size[1] / h if h else 1.0
        px, py = tag.x * sx + sm.origin[0], tag.y * sy + sm.origin[1]
        hit = None
        for e in sm.elements:                              # snap a loose pixel to the control under it: a measured box beats a guessed point
            if e.bbox.contains_point(px, py) and (hit is None or e.bbox.area < hit.bbox.area):
                hit = e
        if hit is not None:
            return PointCommand(hit.bbox, tag.label or hit.label, "highlight", action, hit.id)
        return PointCommand(Box(px - 18, py - 18, px + 18, py + 18), tag.label, "circle", action, None)
    return None


# ------------------------------------------------------------------------------------------------------ motion maths
def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def bezier_arc(p0: Tuple[float, float], p1: Tuple[float, float], t: float, bulge: float = 0.22) -> Tuple[float, float]:
    """Quadratic Bezier from p0 to p1 whose control point sits off the straight line (a thrown, curved flight like a hand moving a cursor).
    The bulge direction is always 'up and to the side' so repeated flights look consistent."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    dist = math.hypot(dx, dy)
    if dist < 1:
        return p1
    nx, ny = -dy / dist, dx / dist
    if ny > 0:
        nx, ny = -nx, -ny                                  # normal pointing upward on screen
    cx = (p0[0] + p1[0]) / 2 + nx * dist * bulge
    cy = (p0[1] + p1[1]) / 2 + ny * dist * bulge
    u = 1 - t
    return (u * u * p0[0] + 2 * u * t * cx + t * t * p1[0], u * u * p0[1] + 2 * u * t * cy + t * t * p1[1])


def flight_seconds(p0: Tuple[float, float], p1: Tuple[float, float]) -> float:
    """0.45 s for a short hop up to 1.1 s across a big monitor."""
    d = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    return max(0.45, min(1.1, 0.35 + d / 2600.0))


def landing_point(box: Box, action: str = "look") -> Tuple[float, float]:
    """Where the pointer tip lands: the middle of the control, nudged toward its left-top for large boxes so it never covers the label's centre."""
    if box.w > 220 or box.h > 90:
        return (box.x1 + min(40.0, box.w * 0.18), box.y1 + min(22.0, box.h * 0.35))
    return (box.cx, box.cy)


# ------------------------------------------------------------------------------------------------ Fitts's law + stitched trajectories
FITTS_A, FITTS_B = 0.10, 0.12                        # the textbook prior; ml.motor.MotorModel refines it from measured movements (set_fitts)


def set_fitts(a: float, b: float) -> None:
    global FITTS_A, FITTS_B
    FITTS_A, FITTS_B = float(a), float(b)


def fitts_seconds(distance: float, width: float, a: Optional[float] = None, b: Optional[float] = None) -> float:
    """Fitts's law: movement time MT = a + b * log2(D / W + 1). Far targets take longer, SMALL targets take longer (a hand slows to land on them). Clamped to a believable range."""
    a = FITTS_A if a is None else a
    b = FITTS_B if b is None else b
    w = max(4.0, float(width))
    return max(0.16, min(1.6, a + b * math.log2(max(0.0, float(distance)) / w + 1.0)))


class Trajectory:
    """One CONTINUOUS route through several targets: cubic Bezier segments joined with matching velocity (no stop-and-go between waypoints), accelerating from rest at the start and
    settling at the last target. Each segment lasts as long as Fitts's law says for its distance and the width of the target it is heading for."""

    def __init__(self, points: List[Tuple[float, float]], widths: List[float]):
        n = len(points)
        self.points = [(float(x), float(y)) for x, y in points]
        self.widths = [float(w) for w in widths] + [24.0] * max(0, n - len(widths))
        self.times: List[float] = [fitts_seconds(math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1]), self.widths[i + 1]) for i in range(n - 1)]
        self.arrival: List[float] = [0.0]
        for t in self.times:
            self.arrival.append(self.arrival[-1] + t)
        vel: List[Tuple[float, float]] = [(0.0, 0.0)] * n                      # velocity (px/s) at each waypoint: 0 at both ends, central difference between
        for i in range(1, n - 1):
            dt = self.times[i - 1] + self.times[i]
            vel[i] = ((points[i + 1][0] - points[i - 1][0]) / dt, (points[i + 1][1] - points[i - 1][1]) / dt)
        self.vel = vel
        self.segs: List[Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float]]] = []
        for i in range(n - 1):
            T = self.times[i]
            p0, p3 = self.points[i], self.points[i + 1]
            c1 = (p0[0] + vel[i][0] * T / 3.0, p0[1] + vel[i][1] * T / 3.0)
            c2 = (p3[0] - vel[i + 1][0] * T / 3.0, p3[1] - vel[i + 1][1] * T / 3.0)
            self.segs.append((p0, c1, c2, p3))

    @property
    def duration(self) -> float:
        return self.arrival[-1]

    def at(self, t: float) -> Tuple[float, float]:
        if not self.segs:
            return self.points[0] if self.points else (0.0, 0.0)
        t = max(0.0, min(self.duration, t))
        i = 0
        while i < len(self.times) - 1 and t > self.arrival[i + 1]:
            i += 1
        s = (t - self.arrival[i]) / self.times[i] if self.times[i] > 0 else 1.0
        p0, c1, c2, p3 = self.segs[i]
        u = 1.0 - s
        return (u ** 3 * p0[0] + 3 * u * u * s * c1[0] + 3 * u * s * s * c2[0] + s ** 3 * p3[0], u ** 3 * p0[1] + 3 * u * u * s * c1[1] + 3 * u * s * s * c2[1] + s ** 3 * p3[1])

    def velocity(self, t: float, h: float = 1e-3) -> Tuple[float, float]:
        a, b = self.at(max(0.0, t - h)), self.at(min(self.duration, t + h))
        dt = min(self.duration, t + h) - max(0.0, t - h)
        return ((b[0] - a[0]) / dt, (b[1] - a[1]) / dt) if dt > 0 else (0.0, 0.0)

    def length(self, steps: int = 400) -> float:
        pts = [self.at(self.duration * i / steps) for i in range(steps + 1)]
        return sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(steps))


def stitch(points: List[Tuple[float, float]], widths: Optional[List[float]] = None) -> Trajectory:
    """`points[0]` is where the pointer is now; the rest are the targets in order; `widths[i]` is the size of target i (0 for the start)."""
    return Trajectory(points, widths or [0.0] + [24.0] * (len(points) - 1))


def route_for(boxes: List[Box], start: Optional[Tuple[float, float]] = None, action: str = "click") -> Tuple[List[Tuple[float, float]], List[float]]:
    """Landing points + target widths for a list of boxes (the route a demonstration glides through)."""
    pts = [landing_point(b, action) for b in boxes]
    ws = [max(6.0, min(b.w, b.h)) for b in boxes]
    if start is not None:
        pts, ws = [start] + pts, [0.0] + ws
    return pts, ws
