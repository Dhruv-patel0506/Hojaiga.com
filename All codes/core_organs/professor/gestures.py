"""
professor.gestures -- POINTER GESTURES (draw, drag, select by dragging, click / double / right click, drop, flick, scroll, orbit / pan / zoom a viewport) for a guide step, through the VIRTUAL mouse.

The person's own mouse is never moved. The delivery is professor.pointer.VirtualPointer: a gesture is compiled to an event script and delivered by the first route this application accepts,
routes being tried in an order that is LEARNED per application (data/professor/app_traits.json, key 'pointer'):
  0 scripting    the application's own scripting / object model performs the gesture's RESULT (orbit the view, add a primitive) - no pointer at all (adapters that offer .gesture(kind, ...))
  1 native       an adapter's own pointer interface (.pointer_events)
  2 posted       mouse messages posted to the child window under the point (classic toolkits)
  3 shim         the same messages + an in-process agent answering the application's polling of the cursor / buttons / modifiers with the virtual pointer (WPF, Blender, OLE drag-and-drop ...)
  4 touch        a synthetic touch contact on the owned window shown as a near-invisible GHOST for the length of the gesture - only where measured NOT to move the person's cursor, and only along a
                 path whose every point lies on the target surface (never across a link, a button, a splash screen)
  5 none         blocked WITH the reason of every route tried
The virtual cursor (overlay) glides along the same path whichever route delivers it. Every gesture is verified: by the application's own state when its scripting bridge can tell
(selection, view), else by pixels inside the target surface. Nothing here names an application: routes are chosen by measurement, surfaces by what the tree / the vision scan says is a canvas.
"""

from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes as wt
import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import config as CFG
from . import pointer as PT

TRAITS_PATH = os.path.join(CFG.DATA_DIR, "app_traits.json")
SURFACE_ROLES = {"pane", "custom", "image", "document", "group", "window"}
_u = ctypes.windll.user32


# ------------------------------------------------------------------------------------------------------------- traits
def load_traits(app_key: str) -> Dict[str, Any]:
    try:
        with open(TRAITS_PATH, encoding="utf-8") as fh:
            return json.load(fh).get(app_key, {})
    except Exception:
        return {}


def save_trait(app_key: str, key: str, value: Any) -> None:
    d: Dict[str, Any] = {}
    try:
        with open(TRAITS_PATH, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        pass
    d.setdefault(app_key, {})[key] = value
    os.makedirs(os.path.dirname(TRAITS_PATH), exist_ok=True)
    with open(TRAITS_PATH, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1, ensure_ascii=False)


def kind_of(text: str) -> str:
    """What a guide sentence's gesture is FOR, from its words: orbit / pan / zoom a view, draw a stroke, select an area, drag and drop, flick, scroll, click variants, hover, or a plain drag."""
    import re
    t = (text or "").lower()
    if re.search(r"\b(orbit|rotate the view|turn the view|tumble|look around)\b", t):
        return "orbit"
    if re.search(r"\bdrag[- ]and[- ]drop\b", t):
        return "drop"
    if re.search(r"\b(zoom|scroll (?:in|out)|dolly)\b", t):
        return "zoom"
    if re.search(r"\b(pan|move the view|scroll the view)\b", t):
        return "pan"
    if re.search(r"\bscroll\b", t):
        return "scroll"
    if re.search(r"\b(swipe|flick)\b", t):
        return "flick"
    if re.search(r"\b(draw|paint|sketch|stroke|scribble|brush|ink|write by hand)\b", t):
        return "stroke"
    if re.search(r"\b(select|lasso|marquee|around the area|rubber ?band)\b", t):
        return "select_area"
    if re.search(r"\bdouble[- ]?click\b", t):
        return "double_click"
    if re.search(r"\b(right[- ]?click|context menu)\b", t):
        return "right_click"
    if re.search(r"\b(hover|point at|rest the pointer|mouse over)\b", t):
        return "hover"
    return "drag"


def gesture_route(app_key: str) -> str:
    """The route a gesture can take in this application, from what was MEASURED: '' when none is known to work."""
    t = load_traits(app_key)
    if t.get("scripting"):
        return "the application's own scripting engine"
    p = t.get("pointer", {}) or {}
    if p.get("shim") == "ok":
        return "posted pointer messages with the in-process pointer agent"
    if p.get("posted") in ("ok", "delivered") or t.get("posted_pointer") is True:
        return "posted pointer messages"
    if p.get("touch") == "ok" or t.get("touch_moves_cursor") is False:
        return "synthetic touch on the visible owned window (teaching / visible mode)"
    return ""


# ------------------------------------------------------------------------------------------------------------- paths
@dataclass
class Gesture:
    kind: str                                   # stroke | drag | select_area | orbit | pan | zoom | tap
    points: List[Tuple[float, float]]           # screen coordinates
    surface: Tuple[int, int, int, int]          # the target surface's rectangle (screen)
    why: str = ""                               # the guide's words


def path_for(kind: str, surface: Tuple[int, int, int, int], n: int = 32) -> List[Tuple[float, float]]:
    """A path INSIDE the surface (a 15% margin) that does what the gesture needs: a visible wave for a stroke, a diagonal for a drag / area selection, a horizontal sweep for orbit / pan."""
    l, t, r, b = surface
    w, h = r - l, b - t
    x0, x1 = l + 0.3 * w, l + 0.7 * w
    yc = t + 0.55 * h
    if kind == "stroke":
        return [(x0 + (x1 - x0) * i / (n - 1), yc + 0.06 * h * math.sin(i / 4.0)) for i in range(n)]
    if kind in ("drag", "select_area"):
        return [(x0 + (x1 - x0) * i / (n - 1), t + 0.35 * h + 0.3 * h * i / (n - 1)) for i in range(n)]
    if kind in ("orbit", "pan"):
        return [(x0 + (x1 - x0) * i / (n - 1), yc) for i in range(n)]
    if kind == "drop":
        return [(l + 0.25 * w, t + 0.5 * h), (l + 0.75 * w, t + 0.5 * h)]
    if kind == "flick":
        return [(l + 0.35 * w, t + 0.5 * h), (l + 0.65 * w, t + 0.5 * h)]
    return [(l + w / 2, t + h / 2)]


# ------------------------------------------------------------------------------------------------------------- drawings
# A 'draw' step used to end as DELEGATED (nothing drawn, reported done). A drawing is now a list of strokes in a 0..100 box: plain geometry for the
# shapes geometry names, the model's sketch for anything else ('a house', 'a smiley'), scaled into the canvas keeping its proportions.
SKETCH_SYSTEM = ("You draw with a pen. Plan a simple line drawing of the thing asked as strokes in a 0..100 box (x right, y down), each stroke a list of "
                 "[x, y] points the pen passes through without lifting; use enough points for curves; at most 12 strokes. Reply JSON only: {\"strokes\": [[[x, y], ...], ...]}.")


def shape_strokes(what: str) -> List[List[Tuple[float, float]]]:
    """Strokes for the shapes geometry names; [] for anything else."""
    import re
    t = (what or "").lower()
    ring = lambda rx, ry, n=48: [(50 + rx * math.cos(2 * math.pi * i / n), 50 + ry * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]
    if re.search(r"\b(circle|round|ring|dot)\b", t):
        return [ring(40, 40)]
    if re.search(r"\b(ellipse|oval)\b", t):
        return [ring(45, 28)]
    if re.search(r"\bsquare\b", t):
        return [[(10, 10), (90, 10), (90, 90), (10, 90), (10, 10)]]
    if re.search(r"\b(rectangle|box)\b", t):
        return [[(5, 25), (95, 25), (95, 75), (5, 75), (5, 25)]]
    if re.search(r"\btriangle\b", t):
        return [[(50, 8), (92, 88), (8, 88), (50, 8)]]
    if re.search(r"\bstar\b", t):
        pts = [(50 + (42 if i % 2 == 0 else 17) * math.sin(math.pi * i / 5), 52 - (42 if i % 2 == 0 else 17) * math.cos(math.pi * i / 5)) for i in range(11)]
        return [pts]
    if re.search(r"\b(line|stroke)\b", t) and not re.search(r"\b(drawing|sketch|of)\b", t):
        return [[(10, 50), (90, 50)]]
    if re.search(r"\b(wave|zigzag|squiggle)\b", t):
        return [[(5 + 90 * i / 31, 50 + 20 * math.sin(i / 2.5)) for i in range(32)]]
    return []


QUICKDRAW_DIR = os.environ.get("HOJAIGA_QUICKDRAW", r"D:\new_automation\data\inbox\6_1_quickdraw")


def quickdraw_strokes(what: str, folder: str = "", pick: int = -1, scan: int = 400) -> List[List[Tuple[float, float]]]:
    """A real human sketch of the thing named (Google Quick, Draw!, CC BY 4.0, simplified strokes in a 0..255 box): the category whose name is in the request (the longest
    such name wins: 'light bulb' over 'bulb'), one of the first `scan` drawings the game recognised, scaled to 0..100 keeping its proportions. [] when no category matches."""
    import random
    import re
    folder = folder or QUICKDRAW_DIR
    if not os.path.isdir(folder):
        return []
    text = " " + re.sub(r"[^a-z ]+", " ", (what or "").lower()) + " "
    cats = sorted((f[:-7] for f in os.listdir(folder) if f.endswith(".ndjson")), key=len, reverse=True)
    cat = next((c for c in cats if f" {c.replace('_', ' ')} " in text or f" {c.replace('_', ' ')}s " in text), "")
    if not cat:
        return []
    rows = []
    with open(os.path.join(folder, cat + ".ndjson"), encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i >= scan:
                break
            with contextlib.suppress(Exception):
                d = json.loads(line)
                if d.get("recognized") and d.get("drawing"):
                    rows.append(d["drawing"])
    if not rows:
        return []
    drawing = rows[pick % len(rows)] if pick >= 0 else random.choice(rows)
    xs = [x for st in drawing for x in st[0]]
    ys = [y for st in drawing for y in st[1]]
    side = max(max(xs) - min(xs), max(ys) - min(ys), 1)
    return [[(100.0 * (x - min(xs)) / side, 100.0 * (y - min(ys)) / side) for x, y in zip(st[0], st[1])] for st in drawing if len(st[0]) >= 2]


def sketch_strokes(what: str, ask: Optional[Callable[[str, str], Optional[str]]] = None) -> List[List[Tuple[float, float]]]:
    """Geometry first; then a real human sketch of the named thing (Quick, Draw!); otherwise the model's line drawing (validated: numbers inside the box, at least two points a stroke)."""
    s = shape_strokes(what) or quickdraw_strokes(what)
    if s:
        return s
    import re
    if ask is None:
        from core_organs.mind import app_qa as QA
        ask = lambda system, prompt: QA.ask_llm(prompt, system, timeout=120, max_tokens=1500)
    raw = ask(SKETCH_SYSTEM, f"Draw: {what}\nJSON:") or ""
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        return []
    out = []
    for st in (d.get("strokes") or [])[:12]:
        pts = [(min(100.0, max(0.0, float(p[0]))), min(100.0, max(0.0, float(p[1])))) for p in st if isinstance(p, (list, tuple)) and len(p) >= 2
               and all(isinstance(v, (int, float)) for v in p[:2])]
        if len(pts) >= 2:
            out.append(pts)
    return out


def fit_strokes(strokes: Sequence[Sequence[Tuple[float, float]]], surface: Tuple[int, int, int, int], margin: float = 0.18) -> List[List[Tuple[float, float]]]:
    """0..100 strokes into the middle of the surface, same scale on both axes (a circle stays a circle), with a margin."""
    l, t, r, b = surface
    side = min(r - l, b - t) * (1 - 2 * margin)
    ox, oy = (l + r) / 2 - side / 2, (t + b) / 2 - side / 2
    return [[(ox + side * x / 100.0, oy + side * y / 100.0) for x, y in st] for st in strokes]


ACTIONABLE_ROLES = ("button", "hyperlink", "menuitem", "listitem", "edit", "combobox", "checkbox", "radiobutton", "tabitem", "splitbutton", "slider", "spinner", "treeitem", "scrollbar", "menu", "toolbar", "text")


def free_rect(nodes: Sequence[Any], window_rect: Tuple[int, int, int, int], cols: int = 48, rows: int = 32) -> Optional[Tuple[int, int, int, int]]:
    """The largest rectangle of the window that no actionable control covers - where a canvas / viewport is when the tree does not name it (a drawing area is often not a node of its own, only
    the empty space between the toolbars). A grid of cells is marked busy where a control's rectangle covers the cell's centre; the biggest block of free cells is returned (one cell of margin)."""
    l, t, r, b = window_rect
    w, h = r - l, b - t
    if w <= 0 or h <= 0:
        return None
    cw, ch = w / cols, h / rows
    busy = [[False] * cols for _ in range(rows)]
    ctl = [n for n in nodes if n.role in ACTIONABLE_ROLES and not n.offscreen and n.rect[2] > n.rect[0] and n.rect[3] > n.rect[1] and (n.rect[2] - n.rect[0]) * (n.rect[3] - n.rect[1]) < 0.5 * w * h]
    for j in range(rows):
        cy = t + (j + 0.5) * ch
        for i in range(cols):
            cx = l + (i + 0.5) * cw
            if any(n.rect[0] <= cx <= n.rect[2] and n.rect[1] <= cy <= n.rect[3] for n in ctl):
                busy[j][i] = True
    heights = [0] * cols
    best, best_rect = 0, None
    for j in range(rows):
        for i in range(cols):
            heights[i] = 0 if busy[j][i] else heights[i] + 1
        stack: List[Tuple[int, int]] = []                                        # (first column of the bar, its height)
        for i in range(cols + 1):
            cur = heights[i] if i < cols else 0
            start = i
            while stack and stack[-1][1] >= cur:
                s0, hh = stack.pop()
                if hh * (i - s0) > best:
                    best, best_rect = hh * (i - s0), (s0, j - hh + 1, i, j + 1)
                start = s0
            stack.append((start, cur))
    if not best_rect or best < 0.08 * cols * rows:
        return None
    c0, r0, c1, r1 = best_rect
    return (int(l + (c0 + 1) * cw), int(t + (r0 + 1) * ch), int(l + (c1 - 1) * cw), int(t + (r1 - 1) * ch))


def surface_of(nodes: Sequence[Any], window_rect: Tuple[int, int, int, int]) -> Tuple[Optional[Tuple[int, int, int, int]], str]:
    """The canvas / viewport: the largest surface-like node with no actionable controls inside it (a document, an image, a custom drawing area) when it is a real part of the window; else the
    largest block of the window that no control covers; else the window's central area."""
    l, t, r, b = window_rect
    win_area = max(1, (r - l) * (b - t))
    best, area = None, 0
    for n in nodes:
        if n.role not in SURFACE_ROLES or n.offscreen or n.rect[2] <= n.rect[0]:
            continue
        a = (n.rect[2] - n.rect[0]) * (n.rect[3] - n.rect[1])
        inner = [m for m in nodes if m is not n and m.role in ("button", "hyperlink", "menuitem", "listitem", "edit", "combobox", "checkbox") and not m.offscreen
                 and n.rect[0] <= (m.rect[0] + m.rect[2]) / 2 <= n.rect[2] and n.rect[1] <= (m.rect[1] + m.rect[3]) / 2 <= n.rect[3]]
        if a > area and not inner:
            best, area = tuple(n.rect), a
    if best is not None and area >= 0.12 * win_area:
        return best, "the largest surface of the tree with no controls inside it"
    fr = free_rect(nodes, window_rect)
    if fr is not None:
        return fr, "the largest part of the window no control covers"
    if best is not None:
        return best, "the largest surface of the tree with no controls inside it (small)"
    return (l + (r - l) // 5, t + (b - t) // 4, r - (r - l) // 5, b - (b - t) // 6), "the window's central area (no canvas node in the tree)"


def path_is_clear(points: Sequence[Tuple[float, float]], owned_hwnd: int, nodes: Sequence[Any], surface: Tuple[int, int, int, int], offset: Tuple[int, int] = (0, 0)) -> Tuple[bool, str]:
    """Every point of the path: inside the surface, on the run's OWN window (nothing else on top there; `offset` = how far a ghost window was moved on screen), and not on an actionable control (a link / button / list item)."""
    l, t, r, b = surface
    ctl = [n for n in nodes if n.role in ("button", "hyperlink", "menuitem", "listitem", "checkbox", "tabitem", "splitbutton") and not n.offscreen and n.rect[2] > n.rect[0]]
    for x, y in points:
        if not (l <= x <= r and t <= y <= b):
            return False, f"the path leaves the surface at ({int(x)}, {int(y)})"
        top = _u.GetAncestor(_u.WindowFromPoint(wt.POINT(int(x + offset[0]), int(y + offset[1]))), 2)
        if top != owned_hwnd:
            return False, f"another window is on top at ({int(x)}, {int(y)})"
        hit = next((n for n in ctl if n.rect[0] <= x <= n.rect[2] and n.rect[1] <= y <= n.rect[3]), None)
        if hit is not None:
            return False, f"the path crosses the control '{hit.name[:40]}' ({hit.role}) - a pointer there could activate it"
    return True, ""


# ------------------------------------------------------------------------------------------------------------- delivery
@dataclass
class GestureResult:
    ok: bool
    route: str = ""
    why: str = ""
    changed: float = 0.0
    tried: List[str] = field(default_factory=list)


_pixels = PT.pixels                                                                    # kept for callers / tests that used the old names
_changed = PT.changed


class GestureDriver:
    def __init__(self, app_key: str, hwnd: int, fx: Any, nodes_fn: Callable[[], List[Any]], overlay: Any = None, scripting: Any = None, visible_ok: bool = False,
                 log: Callable[[str], None] = lambda s: None, native: Any = None):
        self.app_key, self.hwnd, self.fx, self.nodes_fn = app_key, hwnd, fx, nodes_fn
        self.overlay, self.scripting, self.visible_ok, self.log, self.native = overlay, scripting, visible_ok, log, native
        self.vp: Optional[PT.VirtualPointer] = None
        self._surface: Tuple[int, int, int, int] = (0, 0, 0, 0)
        self._nodes: List[Any] = []

    # ---- the virtual mouse of this application (one per driver; it keeps the learned order and the in-process agent)
    def pointer(self) -> PT.VirtualPointer:
        if self.vp is None:
            self.vp = PT.VirtualPointer(self.hwnd, self.app_key, self.fx, overlay=self.overlay, native=self.native, visible_ok=self.visible_ok, log=self.log, touch_guard=self._touch_guard)
        return self.vp

    def _touch_guard(self, pts: Sequence[Tuple[float, float]], offset: Tuple[int, int]) -> Tuple[bool, str]:
        return path_is_clear(pts, self.hwnd, self._nodes, self._surface, offset)

    def _scripted_verify(self) -> Optional[Callable[[], Optional[bool]]]:
        """When the application's scripting bridge can report its own state (selection, view, ...), a gesture is checked against THAT, not only against pixels."""
        sc = self.scripting
        if sc is None or not hasattr(sc, "digest"):
            return None
        before = sc.digest()
        if before is None:
            return None

        def check() -> Optional[bool]:
            end = time.time() + 1.2                                                    # the application applies queued input on its own schedule: ask until it shows a change or time is up
            after = sc.digest()
            while after is not None and after == before and time.time() < end:
                time.sleep(0.15)
                after = sc.digest()
            return None if after is None else after != before
        return check

    def draw(self, what: str, ask: Optional[Callable[[str, str], Optional[str]]] = None, strokes: Optional[Sequence[Sequence[Tuple[float, float]]]] = None) -> GestureResult:
        """Draw `what` on the canvas: every stroke through the virtual mouse, then the surface's pixels must have changed (the picture itself is judged later)."""
        if not self.fx.allowed:
            return GestureResult(False, why="refused: " + self.fx.why_not())
        plan = list(strokes) if strokes is not None else sketch_strokes(what, ask)
        if not plan:
            return GestureResult(False, why=f"no drawing could be planned for '{what[:60]}'")
        nodes = self.nodes_fn()
        r = wt.RECT()
        _u.GetWindowRect(self.hwnd, ctypes.byref(r))
        surface, how_s = surface_of(nodes, (r.left, r.top, r.right, r.bottom))
        self._nodes, self._surface = nodes, surface
        vp = self.pointer()
        before = _pixels(self.hwnd, surface)
        routes, tried = [], []
        for st in fit_strokes(plan, surface):
            pr = vp.stroke(st, duration=max(0.4, min(2.0, len(st) * 0.03)))
            routes.append(pr.route)
            tried += list(getattr(pr, "tried", []) or [])[:2]
            if not pr.ok:
                return GestureResult(False, pr.route, f"stroke {len(routes)} of {len(plan)} was not delivered: {pr.why}", 0.0, tried)
        time.sleep(0.4)
        ch = _changed(before, _pixels(self.hwnd, surface))
        ok = ch > 0.002
        return GestureResult(ok, routes[-1] if routes else "", f"{len(plan)} stroke(s) on the {how_s} surface; {ch:.3%} of it changed", ch, tried)

    def perform(self, kind: str, why: str = "") -> GestureResult:
        if not self.fx.allowed:
            return GestureResult(False, why="refused: " + self.fx.why_not())
        res = GestureResult(False)
        nodes = self.nodes_fn()
        r = wt.RECT()
        _u.GetWindowRect(self.hwnd, ctypes.byref(r))
        surface, how_s = surface_of(nodes, (r.left, r.top, r.right, r.bottom))
        self._nodes, self._surface = nodes, surface
        pts = path_for(kind, surface)
        # 0 scripting: the RESULT of the gesture through the application's own object model
        if self.scripting is not None and hasattr(self.scripting, "gesture") and kind in ("orbit", "pan", "zoom"):
            ok, note = self.scripting.gesture(kind, why)
            res.tried.append(f"scripting -> {note}")
            if ok:
                if self.overlay is not None:
                    try:
                        self.overlay.glide(list(pts), [12.0] * len(pts))
                    except Exception:
                        pass
                return GestureResult(True, "scripting", note, 0.0, res.tried)
        # the virtual mouse: native > posted > posted + in-process pointer state > synthetic touch on a ghost window (the order is learned per application)
        vp = self.pointer()
        verify = self._scripted_verify()
        p0, p1 = (pts[0], pts[-1])
        cx, cy = (surface[0] + surface[2]) / 2, (surface[1] + surface[3]) / 2
        if kind == "orbit":
            pr = vp.drag(p0, p1, "middle", verify=verify, surface=surface)
        elif kind == "pan":
            pr = vp.drag(p0, p1, "middle", ("shift",), verify=verify, surface=surface)
        elif kind == "zoom":
            pr = vp.wheel(cx, cy, 3, verify=verify)
        elif kind == "scroll":
            pr = vp.wheel(cx, cy, -3, verify=verify)
        elif kind == "stroke":
            pr = vp.stroke(pts, verify=verify)
        elif kind == "select_area":
            pr = vp.drag_select(p0, p1, verify=verify)
        elif kind == "drop":
            pr = vp.drag_drop(p0, p1, verify=verify)
        elif kind == "flick":
            pr = vp.flick(p0[0], p0[1], "right", max(80.0, p1[0] - p0[0]), verify=verify)
        elif kind == "double_click":
            pr = vp.double_click(cx, cy, verify=verify)
        elif kind == "right_click":
            pr = vp.right_click(cx, cy, verify=verify)
        elif kind == "hover":
            pr = vp.hover(cx, cy, verify=verify)
        else:
            pr = vp.drag(p0, p1, "left", verify=verify, surface=surface)
        res.tried += pr.tried
        if pr.ok:
            return GestureResult(True, pr.route, pr.note + f" on {how_s}", max(0.0, pr.changed), res.tried)
        res.why = "no route this application accepts could perform the gesture: " + "; ".join(res.tried)
        return res
