"""
atlas.gestures -- the GESTURE ATLAS: how an application responds to the mouse, learned by doing it.

For every kind of region (a canvas/viewport, a text area, a list, a slider, a control) the prober performs a grammar of
gestures -- hover, click, right-click, double-click, hold, wheel, drag with each button, with Shift/Ctrl/Alt -- and MEASURES
the effect: a menu opened (and what is in it), a tooltip appeared (and what it says), the content panned / zoomed / rotated
(and by how much per pixel / per wheel click), a rubber band appeared, an object moved, a stroke was drawn, nothing happened.

Rules this module obeys (they come from the project's laws, not from taste):
  * HEADLESS. Input is posted to the exact child window (no physical pointer, no focus theft). The window is parked
    off-screen by background_window; pixels come from PrintWindow.
  * REVERSIBLE. Every gesture is undone (popups closed, the inverse gesture performed) and the restoration is VERIFIED by pixels.
    A gesture that cannot be undone stops further mutation and is reported -- the app is never silently left changed.
  * HONEST. A gesture the app ignored is recorded as 'no_effect' with delivered=True; one that could not be delivered is
    'undeliverable'. Nothing is claimed that a picture did not show.
  * MUTATING gestures (left click / double click / left drag / hold) only run on a PRISTINE disposable instance.
  * No per-app code: regions and gestures are chosen by control type, size and measured behaviour.
"""

from __future__ import annotations

import contextlib
import ctypes
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import common as C
from . import motion

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK = 0x200, 0x201, 0x202, 0x203
WM_RBUTTONDOWN, WM_RBUTTONUP, WM_MBUTTONDOWN, WM_MBUTTONUP = 0x204, 0x205, 0x207, 0x208
WM_MOUSEWHEEL, WM_CONTEXTMENU = 0x20A, 0x7B
MK_LBUTTON, MK_RBUTTON, MK_SHIFT, MK_CONTROL, MK_MBUTTON = 0x1, 0x2, 0x4, 0x8, 0x10
VK = {"shift": 0x10, "ctrl": 0x11, "alt": 0x12, "left": 0x01, "right": 0x02, "middle": 0x04}
BTN = {"left": (WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON), "right": (WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON),
       "middle": (WM_MBUTTONDOWN, WM_MBUTTONUP, MK_MBUTTON)}

_u32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
_k32 = ctypes.windll.kernel32 if hasattr(ctypes, "windll") else None


# --------------------------------------------------------------------------------------------------
# grammar (DATA: a new gesture or a new region kind is a table row)
# --------------------------------------------------------------------------------------------------

def _wh(img) -> Tuple[int, int]:
    """(width, height) of a PIL image or a numpy array; (0, 0) for anything else."""
    try:
        if hasattr(img, "shape"):
            return int(img.shape[1]), int(img.shape[0])
        sz = img.size
        return int(sz[0]), int(sz[1])
    except Exception:
        return 0, 0


@dataclass(frozen=True)
class Spec:
    name: str                 # hover | click | dblclick | hold | wheel | drag
    button: str = "left"
    mods: Tuple[str, ...] = ()
    mutating: bool = False
    arg: float = 0.0          # wheel clicks / drag pixels

    @property
    def label(self) -> str:
        m = "+".join(self.mods)
        core = {"hover": "hover", "click": f"click-{self.button}", "dblclick": "double-click", "hold": "hold",
                "wheel": "wheel", "drag": f"drag-{self.button}"}[self.name]
        return (m + "+" if m else "") + core


S = Spec
CANVAS_GRAMMAR: List[Spec] = [
    S("hover"), S("click", "right"), S("wheel", arg=1), S("wheel", arg=3), S("drag", "middle", arg=90), S("drag", "right", arg=90),
    S("wheel", mods=("ctrl",), arg=1), S("wheel", mods=("shift",), arg=1), S("drag", "middle", mods=("shift",), arg=90),
    S("click", "left", mutating=True), S("drag", "left", mutating=True, arg=150),
    S("hold", "left", mutating=True), S("drag", "left", mods=("shift",), mutating=True, arg=100),
    S("drag", "left", mods=("ctrl",), mutating=True, arg=100), S("drag", "left", mods=("alt",), mutating=True, arg=100),
    S("drag", "right", mods=("alt",), arg=90), S("dblclick", "left", mutating=True),
]
TEXT_GRAMMAR: List[Spec] = [S("hover"), S("click", "right"), S("wheel", arg=3), S("dblclick", "left", mutating=True),
                            S("drag", "left", mutating=True, arg=120)]
LIST_GRAMMAR: List[Spec] = [S("hover"), S("click", "right"), S("wheel", arg=2), S("dblclick", "left", mutating=True)]
SLIDER_GRAMMAR: List[Spec] = [S("hover"), S("wheel", arg=2), S("drag", "left", mutating=True, arg=40)]
CONTROL_GRAMMAR: List[Spec] = [S("hover"), S("click", "right")]
OBJECT_GRAMMAR: List[Spec] = [
    S("click", "right"), S("click", "left", mutating=True), S("drag", "left", mutating=True, arg=120), S("dblclick", "left", mutating=True),
    S("click", "left", mods=("shift",), mutating=True), S("drag", "left", mods=("shift",), mutating=True, arg=100),
    S("drag", "left", mods=("ctrl",), mutating=True, arg=100), S("drag", "left", mods=("alt",), mutating=True, arg=100), S("hold", "left", mutating=True),
]
GRAMMARS = {"canvas": CANVAS_GRAMMAR, "blind": CANVAS_GRAMMAR, "text": TEXT_GRAMMAR, "list": LIST_GRAMMAR, "tree": LIST_GRAMMAR,
            "grid": LIST_GRAMMAR, "slider": SLIDER_GRAMMAR, "control": CONTROL_GRAMMAR, "object": OBJECT_GRAMMAR}

KIND_OF_TYPE = {"DocumentControl": "text", "EditControl": "text", "ListControl": "list", "TreeControl": "tree", "DataGridControl": "grid",
                "TableControl": "grid", "SliderControl": "slider", "SpinnerControl": "slider", "ImageControl": "canvas"}
CANVAS_TYPES = {"PaneControl", "CustomControl", "ImageControl", "GroupControl"}
ACTIONABLE = {"invoke", "toggle", "expand", "select"}


@dataclass
class Region:
    id: str
    kind: str                       # canvas | blind | text | list | tree | grid | slider | control
    name: str
    rect: Tuple[int, int, int, int]  # SCREEN px (left, top, right, bottom)
    source: str = "uia"
    ctype: str = ""
    parent: Optional[str] = None                      # an object lives inside a canvas; gestures on it are analysed on the canvas
    img_box: Optional[Tuple[int, int, int, int]] = None

    @property
    def w(self) -> int:
        return self.rect[2] - self.rect[0]

    @property
    def h(self) -> int:
        return self.rect[3] - self.rect[1]

    @property
    def center(self) -> Tuple[int, int]:
        return (self.rect[0] + self.rect[2]) // 2, (self.rect[1] + self.rect[3]) // 2


@dataclass
class GestureResult:
    region: str
    region_kind: str
    gesture: str
    effect_class: str
    delivered: bool
    effective: Optional[bool]
    reversible: Optional[bool]
    detail: Dict[str, Any] = field(default_factory=dict)
    seconds: float = 0.0


# --------------------------------------------------------------------------------------------------
# headless pointer
# --------------------------------------------------------------------------------------------------

def _lp(x: int, y: int) -> int:
    return ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)


class _Pt(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def win_rect(hwnd: int) -> Tuple[int, int, int, int]:
    class R(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
    r = R()
    _u32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.l, r.t, r.r, r.b


@contextlib.contextmanager
def key_state(hwnd: int, mods: Sequence[str]):
    """Set Shift/Ctrl/Alt in the TARGET thread's keyboard-state table (attached input) for the duration; the physical keyboard is untouched."""
    vks = [VK[m] for m in mods if m in VK]
    if not vks or _u32 is None:
        yield
        return
    target_tid = _u32.GetWindowThreadProcessId(hwnd, None)
    my_tid = _k32.GetCurrentThreadId()
    attached = bool(target_tid and target_tid != my_tid and _u32.AttachThreadInput(my_tid, target_tid, True))
    saved = (ctypes.c_ubyte * 256)()
    have = bool(_u32.GetKeyboardState(saved))
    try:
        if have:
            st = (ctypes.c_ubyte * 256)()
            ctypes.memmove(st, saved, 256)
            for v in vks:
                st[v] = 0x80
                if v == 0x11:
                    st[0xA2] = 0x80
                elif v == 0x10:
                    st[0xA0] = 0x80
                elif v == 0x12:
                    st[0xA4] = 0x80
            _u32.SetKeyboardState(st)
        yield
        time.sleep(0.06)                      # the target thread drains its queue before the table is restored
    finally:
        if have:
            _u32.SetKeyboardState(saved)
        if attached:
            _u32.AttachThreadInput(my_tid, target_tid, False)


def dpi_ratio(hwnd: int) -> float:
    """logical-pixels-per-physical-pixel of the window as ITS OWN code sees them (96/120 = 0.8 at 125% scaling; 1.0 when both agree).
    A window that is not DPI-aware paints (and PrintWindow returns) LOGICAL pixels, while UIA and screen coordinates are physical:
    this ratio maps a position inside a captured picture to a screen position and back. Posted mouse coordinates need NO conversion."""
    try:
        u = ctypes.windll.user32
        aw_t = u.GetAwarenessFromDpiAwarenessContext(u.GetWindowDpiAwarenessContext(hwnd))
        aw_m = u.GetAwarenessFromDpiAwarenessContext(u.GetThreadDpiAwarenessContext())
        if aw_m == 0:
            return 1.0                                       # we are virtualised too: both live in the same logical space
        dpi_t = float(u.GetDpiForWindow(hwnd) or 96)
        dpi_m = float(u.GetDpiForSystem() or 96)
        return max(0.25, min(4.0, dpi_t / dpi_m)) if aw_t == 0 or dpi_t != dpi_m else 1.0
    except Exception:
        return 1.0


class Pointer:
    """Posts mouse messages to the exact child window under a screen point. Everything returns (delivered, note)."""

    def __init__(self, hwnd: int):
        from core_organs import headless_input as hin
        self.hin = hin
        self.top = hwnd
        self._ratio: Dict[int, float] = {}

    def ratio(self, t: int) -> float:
        r = self._ratio.get(t)
        if r is None:
            r = self._ratio[t] = dpi_ratio(t)
        return r

    def _target(self, sx: int, sy: int) -> Tuple[int, int, int]:
        t = self.hin.child_at(self.top, int(sx), int(sy))
        pt = _Pt(int(sx), int(sy))
        _u32.ScreenToClient(t, ctypes.byref(pt))
        # physical client coordinates: for a DPI-virtualised (non-aware) receiver Windows scales the posted lParam itself
        # (measured: also scaling here put a marker at 0.8x the intended position). The ratio is only for mapping PICTURES.
        return t, int(pt.x), int(pt.y)

    @staticmethod
    def _mk(mods: Sequence[str]) -> int:
        v = 0
        if "shift" in mods:
            v |= MK_SHIFT
        if "ctrl" in mods:
            v |= MK_CONTROL
        return v

    def alive(self) -> bool:
        return bool(_u32.IsWindow(self.top))

    def move(self, sx: int, sy: int, held: int = 0, mods: Sequence[str] = ()) -> bool:
        t, cx, cy = self._target(sx, sy)
        return bool(_u32.PostMessageW(t, WM_MOUSEMOVE, held | self._mk(mods), _lp(cx, cy)))

    def click(self, sx: int, sy: int, button: str = "left", clicks: int = 1, mods: Sequence[str] = (), hold_s: float = 0.03) -> Tuple[bool, str]:
        dn, up, mk = BTN[button]
        ok = True
        with key_state(self.top, mods):
            t, cx, cy = self._target(sx, sy)
            ok &= bool(_u32.PostMessageW(t, WM_MOUSEMOVE, self._mk(mods), _lp(cx, cy)))
            for i in range(clicks):
                ok &= bool(_u32.PostMessageW(t, dn, mk | self._mk(mods), _lp(cx, cy)))
                time.sleep(hold_s)
                ok &= bool(_u32.PostMessageW(t, up, self._mk(mods), _lp(cx, cy)))
                if i + 1 < clicks:
                    time.sleep(0.03)
                    if button == "left":
                        ok &= bool(_u32.PostMessageW(t, WM_LBUTTONDBLCLK, mk | self._mk(mods), _lp(cx, cy)))
                        ok &= bool(_u32.PostMessageW(t, up, self._mk(mods), _lp(cx, cy)))
                        break
        return ok, f"posted-{button}-click x{clicks}->{self.hin._class_name(t)}@({cx},{cy})"

    def context_menu(self, sx: int, sy: int) -> bool:
        """What a XAML host needs: the context-menu message itself, to the child window under the point."""
        t, _, _ = self._target(sx, sy)
        return bool(_u32.PostMessageW(t, WM_CONTEXTMENU, t, _lp(int(sx), int(sy))))

    def wheel(self, sx: int, sy: int, clicks: int, mods: Sequence[str] = ()) -> Tuple[bool, str]:
        t, _, _ = self._target(sx, sy)
        wparam = (((int(clicks) * 120) & 0xFFFF) << 16) | self._mk(mods)
        with key_state(self.top, mods):
            ok = bool(_u32.PostMessageW(t, WM_MOUSEWHEEL, wparam, _lp(int(sx), int(sy))))
            time.sleep(0.05)
        return ok, f"posted-wheel({clicks})->{self.hin._class_name(t)}"

    def drag(self, p0: Tuple[int, int], p1: Tuple[int, int], button: str = "left", mods: Sequence[str] = (), steps: int = 22,
             duration_s: float = 0.4, path: Optional[List[Tuple[int, int]]] = None, mid: Optional[Callable[[], None]] = None,
             hold_end_s: float = 0.0) -> Tuple[bool, str]:
        dn, up, mk = BTN[button]
        if path and len(path) >= 2:
            pts = [(int(x), int(y)) for x, y in path]
        else:
            n = max(2, steps)
            pts = [(int(round(p0[0] + (p1[0] - p0[0]) * i / n)), int(round(p0[1] + (p1[1] - p0[1]) * i / n))) for i in range(n + 1)]
        ok = True
        with key_state(self.top, mods):
            t, cx, cy = self._target(*pts[0])
            held = mk | self._mk(mods)

            def lp(x, y):
                pt = _Pt(int(x), int(y))
                _u32.ScreenToClient(t, ctypes.byref(pt))
                return _lp(pt.x, pt.y)
            ok &= bool(_u32.PostMessageW(t, WM_MOUSEMOVE, self._mk(mods), lp(*pts[0])))
            time.sleep(0.02)
            ok &= bool(_u32.PostMessageW(t, dn, held, lp(*pts[0])))
            slice_s = max(0.0, duration_s) / max(1, len(pts) - 1)
            half = len(pts) // 2
            for i, (x, y) in enumerate(pts[1:], start=1):
                ok &= bool(_u32.PostMessageW(t, WM_MOUSEMOVE, held, lp(x, y)))
                time.sleep(slice_s)
                if mid is not None and i == half:
                    time.sleep(0.18)           # let the target repaint its in-progress feedback
                    mid()
            if hold_end_s:
                time.sleep(hold_end_s)
            ok &= bool(_u32.PostMessageW(t, up, self._mk(mods), lp(*pts[-1])))
            time.sleep(0.05)
        return ok, f"posted-{button}-drag {len(pts)}pts->{self.hin._class_name(t)}"

    def hold(self, sx: int, sy: int, seconds: float = 0.75, button: str = "left", observe: Optional[Callable[[], None]] = None) -> Tuple[bool, str]:
        dn, up, mk = BTN[button]
        t, cx, cy = self._target(sx, sy)
        ok = bool(_u32.PostMessageW(t, WM_MOUSEMOVE, 0, _lp(cx, cy)))
        ok &= bool(_u32.PostMessageW(t, dn, mk, _lp(cx, cy)))
        time.sleep(seconds)
        if observe:
            observe()
        ok &= bool(_u32.PostMessageW(t, up, 0, _lp(cx, cy)))
        time.sleep(0.05)
        return ok, f"posted-{button}-hold {seconds:.2f}s->{self.hin._class_name(t)}"


# --------------------------------------------------------------------------------------------------
# regions
# --------------------------------------------------------------------------------------------------

def discover_regions(hwnd: int, nodes: Optional[List[Any]] = None, *, min_side: int = 48, blind_min_frac: float = 0.04) -> List[Region]:
    """Regions worth probing, from the UIA tree (by control type, size, emptiness) plus BLIND areas the tree does not cover."""
    from core_organs import fast_uia
    if nodes is None:
        nodes = fast_uia.snapshot(hwnd, timeout_ms=6000) or []
        if len(nodes) < 5:                                   # right after parking, the tree is still being built: wait (bounded), re-read
            try:
                fast_uia.wait_ready(hwnd, timeout_s=6.0)
            except Exception:
                pass
            nodes = fast_uia.snapshot(hwnd, timeout_ms=6000) or []
    wl, wt_, wr, wb = win_rect(hwnd)
    ww, wh = max(1, wr - wl), max(1, wb - wt_)
    out: List[Region] = []

    def actionable_desc(n) -> int:
        return sum(1 for d in fast_uia.descendants_of(nodes, n.idx) if (set(d.pats) & ACTIONABLE) or (d.name and d.ctype in ("ButtonControl", "MenuItemControl", "TabItemControl")))

    for n in nodes:
        l, t, r, b = n.rect
        w, h = r - l, b - t
        if n.offscreen and not (wl - 50000 < l < wr + 50000):       # a parked window reports real (off-screen) coordinates; skip only stale ones
            continue
        if w < min_side or h < min_side or w >= ww * 0.98 and h >= wh * 0.98:
            continue
        kind = KIND_OF_TYPE.get(n.ctype)
        if kind is None and n.ctype in CANVAS_TYPES and actionable_desc(n) == 0 and w * h >= 0.02 * ww * wh:
            kind = "canvas"
        if kind is None:
            continue
        if kind == "canvas" and any(o.kind == "canvas" and o.rect[0] <= l and o.rect[1] <= t and o.rect[2] >= r and o.rect[3] >= b for o in out):
            continue
        out.append(Region(id=f"{kind}:{n.aid or n.name or n.cls}:{l},{t}", kind=kind, name=n.name or n.aid or n.cls or n.ctype, rect=(l, t, r, b), ctype=n.ctype))
    # ---- blind areas: client space no leaf element covers (custom-drawn UIs)
    try:
        cell = 24
        gx, gy = max(1, ww // cell), max(1, wh // cell)
        covered = [[False] * gx for _ in range(gy)]
        for n in nodes:
            l, t, r, b = n.rect
            if r <= l or b <= t:
                continue
            if (r - l) * (b - t) >= 0.85 * ww * wh:                # the frame / a full-window container: it does not "cover" what is drawn inside it
                continue
            if n.children and n.ctype in ("WindowControl", "PaneControl", "GroupControl", "CustomControl") and not n.name:
                continue
            for cy_ in range(max(0, (t - wt_) // cell), min(gy, (b - wt_) // cell + 1)):
                for cx_ in range(max(0, (l - wl) // cell), min(gx, (r - wl) // cell + 1)):
                    covered[cy_][cx_] = True
        seen = [[False] * gx for _ in range(gy)]
        for sy in range(gy):
            for sx in range(gx):
                if covered[sy][sx] or seen[sy][sx]:
                    continue
                stack, cells = [(sx, sy)], []
                seen[sy][sx] = True
                while stack:
                    x, y = stack.pop()
                    cells.append((x, y))
                    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if 0 <= nx < gx and 0 <= ny < gy and not covered[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
                xs = [c[0] for c in cells]
                ys = [c[1] for c in cells]
                rect = (wl + min(xs) * cell, wt_ + min(ys) * cell, wl + (max(xs) + 1) * cell, wt_ + (max(ys) + 1) * cell)
                if (rect[2] - rect[0]) * (rect[3] - rect[1]) >= blind_min_frac * ww * wh and len(cells) >= 0.5 * (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1):
                    out.append(Region(id=f"blind:{rect[0]},{rect[1]}", kind="blind", name="uncovered area", rect=rect, source="geometry"))
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------------------------------
# the prober
# --------------------------------------------------------------------------------------------------

class GestureProber:
    def __init__(self, hwnd: int, app_key: str, *, store: Optional[C.AtlasStore] = None, run_id: str = "", budget_s: float = 45.0,
                 pristine: bool = False, predictor: Optional[Callable[[str, Dict[str, Any]], Optional[str]]] = None,
                 observer: Optional[Callable[[str, Dict[str, Any], str, str], None]] = None, log: Optional[Callable[[str], None]] = None,
                 evidence_dir: str = ""):
        from core_organs import headless_input as hin
        self.evidence_dir = evidence_dir
        self.hin = hin
        self.hwnd = hwnd
        self.app_key = app_key
        self.store = store or C.get_store()
        self.run_id = run_id or f"gest_{int(time.time())}"
        self.budget_s = budget_s
        self.pristine = pristine
        self.ptr = Pointer(hwnd)
        self.predictor = predictor
        self.observer = observer
        self.log = log or (lambda s: None)
        self.t0 = time.time()
        self.dirty = False                 # a VIEW change that could not be undone: stop view gestures
        self.dirty_content = False         # a CONTENT change that could not be undone: stop mutating gestures
        self.results: List[GestureResult] = []
        self._baseline_popups: List[int] = []
        self._base_wins: set = set()
        self._eff: Dict[str, Dict[str, Any]] = {}

    # ---- helpers
    def left(self) -> float:
        return self.budget_s - (time.time() - self.t0)

    def grab(self):
        img, note = self.hin.capture_window(self.hwnd)
        return img

    def popups(self) -> List[int]:
        from core_organs import organ_48_app_behavior_model as bm
        try:
            return list(bm._open_popups(self.hwnd))
        except Exception:
            return []

    def win_set(self) -> set:
        """Every visible top-level window of the app's process, whatever its class (a WinForms/MFC drop-down shares the main window's
        class, which the engine's popup helpers deliberately skip), minus the main window."""
        out = set()
        try:
            for w in self.hin.process_windows(self.hwnd, include_hidden=False):
                if w == self.hwnd or self.hin.is_cloaked(w):
                    continue
                l, t, r, b = win_rect(w)
                if r - l >= 2 and b - t >= 2:
                    out.add(int(w))
        except Exception:
            pass
        return out

    def new_popups(self) -> List[int]:
        now_ = self.win_set() | set(self.popups())
        return sorted(w for w in now_ if w not in self._base_wins and w not in self._baseline_popups)

    def wait_new(self, max_s: float) -> List[int]:
        end = time.time() + max_s
        while True:
            n = self.new_popups()
            if n or time.time() >= end:
                return n
            time.sleep(0.08)

    def popup_items(self, new: List[int]) -> Dict[str, Any]:
        from core_organs import fast_uia
        items: List[Dict[str, str]] = []
        kinds = set()
        for w in new[:4]:
            cls = ""
            try:
                cls = self.hin._class_name(w).lower()
            except Exception:
                pass
            nodes = fast_uia.snapshot(w, timeout_ms=1500) or []
            for n in nodes:
                if n.ctype in ("MenuItemControl", "ButtonControl", "ToolTipControl", "TextControl", "ListItemControl", "CheckBoxControl", "RadioButtonControl", "TabItemControl", "EditControl", "ComboBoxControl") and (n.name or n.ctype == "EditControl"):
                    items.append({"name": n.name, "type": n.ctype.replace("Control", "")})
            types = {i["type"] for i in items}
            if "tooltip" in cls or "ToolTip" in types:
                kinds.add("tooltip")
            elif "MenuItem" in types or "menu" in cls:
                kinds.add("menu")
            elif "Button" in types or "Edit" in types:
                kinds.add("dialog")
            else:
                kinds.add("popup")
        return {"kinds": sorted(kinds), "items": items[:40]}

    def close_new_popups(self) -> bool:
        """Close what the gesture opened: the engine's ladder first (Escape, then WM_CLOSE), then WM_CLOSE on any window of ours still open."""
        from core_organs import organ_63_app_mastery as m63
        try:
            m63.close_popups(self.hwnd, self._baseline_popups, timeout_s=1.5)
        except Exception:
            pass
        end = time.time() + 1.5
        while time.time() < end:
            left = self.new_popups()
            if not left:
                return True
            for w in left:
                _u32.PostMessageW(w, 0x0010, 0, 0)          # WM_CLOSE
            time.sleep(0.12)
        return not self.new_popups()

    def hung(self) -> bool:
        try:
            return bool(_u32.IsHungAppWindow(self.hwnd))
        except Exception:
            return False

    def rel(self, region: Region) -> Tuple[int, int, int, int]:
        wl, wt_, _, _ = win_rect(self.hwnd)
        return region.rect[0] - wl, region.rect[1] - wt_, region.rect[2] - wl, region.rect[3] - wt_

    @staticmethod
    def _crop(img, box):
        return motion.crop(img, box)

    def region_hwnd(self, region: Region) -> int:
        """The native child window that IS this region (same rectangle), or 0. Capturing the child directly is exact even when the
        top-level surface of a parked window is stale (measured: PrintWindow of a parked, resized window painted only its old size)."""
        try:
            cx, cy = region.center
            t = self.hin.child_at(self.hwnd, int(cx), int(cy))
            if t and t != self.hwnd:
                l, tp, r, b = win_rect(t)
                if abs(l - region.rect[0]) <= 6 and abs(tp - region.rect[1]) <= 6 and abs(r - region.rect[2]) <= 6 and abs(b - region.rect[3]) <= 6:
                    return int(t)
        except Exception:
            pass
        return 0

    def _raw_region(self, region: Region, full=None):
        import numpy as np
        h = self.region_hwnd(region)
        if h:
            img, _ = self.hin.capture_window(h)
            if img is not None:
                return np.asarray(img)
        if full is None:
            try:
                _u32.RedrawWindow(self.hwnd, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0100)   # INVALIDATE | ALLCHILDREN | UPDATENOW | (frame)
            except Exception:
                pass
            full = self.grab()
        if full is None:
            return None
        return self._crop(full, self.rel(region))

    def grab_region(self, region: Region, full=None):
        """The region's PAINTED pixels as an ndarray (RGB) or None (child window first, else a crop of the whole-window capture)."""
        raw = self._raw_region(region, full)
        info = self._eff.get(region.id)
        if raw is not None and info and info.get("pb"):
            x0, y0, x1, y1 = info["pb"]
            raw = raw[y0:y1, x0:x1]
        return raw

    def prepare(self, region: Region) -> Dict[str, Any]:
        """Per-region calibration, once: DPI ratio, the painted extent (and the physical rectangle it corresponds to), and the
        volatility mask (pixels that change on their own)."""
        info = self._eff.get(region.id)
        if info:
            return info
        h = self.region_hwnd(region)
        ratio = self.ptr.ratio(h or self.hwnd)
        raw = self._raw_region(region)
        pb = motion.painted_box(raw) if raw is not None else None
        rect = region.rect
        if pb:
            rect = (int(region.rect[0] + pb[0] / ratio), int(region.rect[1] + pb[1] / ratio), int(region.rect[0] + pb[2] / ratio), int(region.rect[1] + pb[3] / ratio))
        eff = Region(region.id, region.kind, region.name, rect, region.source, region.ctype)
        info = {"region": eff, "pb": pb, "ratio": ratio, "noise": None, "raw_size": None if raw is None else (raw.shape[1], raw.shape[0])}
        self._eff[region.id] = info
        frames = []
        for _ in range(3):
            fr = self.grab_region(region)
            if fr is not None:
                frames.append(fr)
            time.sleep(0.12)
        if len(frames) >= 2:
            try:
                info["noise"] = motion.volatility_mask(frames)
                info["noise_px"] = int(info["noise"].sum() // 255)
            except Exception:
                info["noise"] = None
        return info

    def restored(self, ref, now_img, ignore=None, effect_px: int = 0) -> Tuple[bool, Dict[str, Any]]:
        """Did an undo bring the region back? Pixel-equal, or equal up to a tiny rigid residual (<= 3 px, no scale/rotation) -- the
        backlash real controls have. Returns (restored, evidence)."""
        if ref is None or now_img is None:
            return False, {"why": "no picture"}
        g_ref, g_now = motion.to_gray(ref)[0], motion.to_gray(now_img)[0]
        st = motion.diff_stats(g_ref, g_now, ignore=ignore)
        ev: Dict[str, Any] = {"changed_px": st["changed_px"], "changed_ratio": round(st["changed_ratio"], 5)}
        if st["changed_px"] < max(30, int(4e-5 * g_ref.size)):          # the same threshold at which a gesture counts as 'no effect'
            return True, ev
        if effect_px and st["changed_px"] < 0.12 * effect_px:           # what is left is a small fraction of what the gesture did: backlash
            ev["leftover_fraction"] = round(st["changed_px"] / float(effect_px), 3)
            return True, ev
        reg = motion.register(ref, now_img)
        ev["registration"] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in reg.items() if k in ("ok", "scale", "rot_deg", "shift", "residual", "method", "explained_fraction")}
        # small RIGID leftover (backlash of a drag/zoom/rotate) is restored; a leftover OBJECT (a marker, a stroke) is not
        if (reg.get("ok") and reg.get("method") != "identity" and reg.get("explained_fraction", 0) > 0.75 and reg.get("shift", 99) <= 4.0
                and abs(math.log(max(1e-6, reg.get("scale", 1.0)))) < 0.015 and abs(reg.get("rot_deg", 0.0)) < 1.5):
            ev["backlash_px"] = round(float(reg.get("shift", 0.0)), 2)
            return True, ev
        return False, ev

    # ---- one gesture
    def perform(self, region: Region, spec: Spec, *, target: Optional[Region] = None) -> GestureResult:
        """One gesture on `region`. With `target` (an object inside the region) the pointer goes to the object but the effect is judged on the
        whole region (an object that moves leaves its own bounding box)."""
        t0 = time.time()
        info = self.prepare(region)
        eff = info["region"]
        ratio = info["ratio"]
        noise = info.get("noise")
        clear: Optional[Callable[[], None]] = None
        if target is not None and info.get("empty"):
            ex, ey = info["empty"]

            def clear():                                   # a click on empty canvas: the universal way to drop a selection
                self.ptr.click(ex, ey, "left")
                time.sleep(0.3)
            clear()
        self._baseline_popups = self.popups()
        self._base_wins = self.win_set()
        before = self.grab()
        rb = self.grab_region(region, before)
        box = self.rel(eff)
        cx, cy = (target or eff).center                    # geometry comes from the painted, physical-pixel rectangle
        kind_name = target.kind if target else region.kind
        feats = {"region_kind": kind_name, "gesture": spec.label, "ctype": region.ctype}
        predicted = self.predictor("gesture", feats) if self.predictor else None
        detail: Dict[str, Any] = {}
        delivered, note = True, ""
        drag_info: Optional[Dict[str, Any]] = None
        mid_img = {"img": None}
        inverse: Optional[Callable[[], None]] = None
        w, h = eff.w, eff.h
        margin = 14
        try:
            if spec.name == "hover":
                self.ptr.move(cx, cy, mods=spec.mods)
                time.sleep(0.2)
                self.ptr.move(cx + 2, cy + 1, mods=spec.mods)
                time.sleep(0.75)                           # tooltips wait ~0.5 s
                note = "posted-hover"
            elif spec.name == "click":
                delivered, note = self.ptr.click(cx, cy, spec.button, 1, spec.mods)
                if spec.button == "left" and clear is not None:
                    inverse = clear
                if spec.button == "right":
                    time.sleep(0.3)
                    if not self.new_popups():
                        self.ptr.context_menu(cx, cy)      # XAML hosts want the message itself
                time.sleep(0.35)
            elif spec.name == "dblclick":
                delivered, note = self.ptr.click(cx, cy, spec.button, 2, spec.mods)
                time.sleep(0.35)
                if clear is not None:
                    inverse = clear
            elif spec.name == "hold":
                snap = {}

                def _obs():
                    snap["pop"] = self.new_popups()
                    snap["img"] = self.grab()
                delivered, note = self.ptr.hold(cx, cy, 0.8, spec.button, observe=_obs)
                detail["while_held_popups"] = len(snap.get("pop", []))
                time.sleep(0.25)
                if clear is not None:
                    inverse = clear
            elif spec.name == "wheel":
                n = int(spec.arg) or 3
                delivered, note = self.ptr.wheel(cx, cy, n, spec.mods)
                time.sleep(0.35)
                inverse = lambda n=n: self.ptr.wheel(cx, cy, -n, spec.mods)
                drag_info = None
                detail["clicks"] = n
            elif spec.name == "drag":
                dist = int(spec.arg) or 90
                dx = min(dist, max(20, w // 2 - margin))
                dy = 0
                if spec.button == "left":                                        # rubber band / draw / object move: a diagonal has an area
                    dy = min(int(dist * 0.7), max(15, h // 2 - margin))
                if target is not None:                                          # start ON the object, move it towards the canvas centre
                    sgn_x = 1 if cx < eff.center[0] else -1
                    sgn_y = 1 if cy < eff.center[1] else -1
                    p0 = (cx, cy)
                    p1 = (cx + sgn_x * dx, cy + sgn_y * (dy or 0))
                else:
                    p0 = (cx - dx // 2, cy - dy // 2)
                    p1 = (cx + dx // 2, cy + dy // 2)
                rx0, ry0 = (p0[0] - eff.rect[0]) * ratio, (p0[1] - eff.rect[1]) * ratio       # coordinates inside the cropped pictures (logical px)
                rx1, ry1 = (p1[0] - eff.rect[0]) * ratio, (p1[1] - eff.rect[1]) * ratio
                mx, my = (rx0 + rx1) / 2.0, (ry0 + ry1) / 2.0
                drag_info = {"box": (min(rx0, rx1), min(ry0, ry1), max(rx0, rx1), max(ry0, ry1)),
                             "boxes": [(min(rx0, rx1), min(ry0, ry1), max(rx0, rx1), max(ry0, ry1)), (min(rx0, mx), min(ry0, my), max(rx0, mx), max(ry0, my))],
                             "vec": ((p1[0] - p0[0]) * ratio, (p1[1] - p0[1]) * ratio), "button": spec.button}

                def _mid():
                    mid_img["img"] = self.grab_region(region)
                delivered, note = self.ptr.drag(p0, p1, spec.button, spec.mods, mid=_mid)
                time.sleep(0.3)
                def inverse():
                    self.ptr.drag(p1, p0, spec.button, spec.mods)
                    if clear is not None:
                        time.sleep(0.2)
                        clear()
            else:
                delivered, note = False, f"unknown gesture {spec.name}"
        except Exception as exc:
            delivered, note = False, f"{type(exc).__name__}: {str(exc)[:100]}"
        detail["delivery"] = note
        after = self.grab()
        ra = self.grab_region(region, after)
        new_pop = self.wait_new({"click": 0.9 if spec.button == "right" else 0.2, "dblclick": 0.25, "hold": 0.0, "hover": 0.0}.get(spec.name, 0.1))
        eff_class, effective = "no_effect", False
        if not delivered:
            eff_class, effective = "undeliverable", None
        elif new_pop:
            info = self.popup_items(new_pop)
            detail.update(info)
            eff_class = {"menu": "opens_menu", "tooltip": "shows_tooltip", "dialog": "opens_dialog"}.get((info["kinds"] or ["popup"])[0], "opens_popup")
            effective = True
        elif rb is not None and ra is not None and _wh(rb)[0] > 4 and _wh(rb)[1] > 4 and _wh(ra)[0] > 4 and _wh(ra)[1] > 4:
            mid = mid_img["img"]
            try:
                d = motion.describe(rb, ra, hint=("wheel" if spec.name == "wheel" else spec.name), drag=drag_info, during=mid, ignore=noise)
            except Exception as exc:                                           # an unreadable capture is "unobserved", never a crash of the whole probe
                d = {"class": "unobserved", "confidence": 0.0, "params": {}, "evidence": f"analysis failed: {type(exc).__name__}"}
            detail["motion"] = {"class": d["class"], "confidence": round(d["confidence"], 2), "params": d["params"], "evidence": d["evidence"]}
            eff_class = d["class"]
            effective = (d["class"] != "none") if d["class"] != "unobserved" else None
            if eff_class == "none":
                eff_class = "no_effect"
            # change OUTSIDE the region (status bar, another panel) is an effect too
            try:
                if before is not None and after is not None and before.size == after.size:
                    full = motion.diff_stats(motion.to_gray(before)[0], motion.to_gray(after)[0])
                    inside = motion.diff_stats(motion.to_gray(rb)[0], motion.to_gray(ra)[0])
                    outside_px = full["changed_px"] - inside["changed_px"]
                    if outside_px > 30:
                        detail["changed_outside_region_px"] = int(outside_px)
                        if eff_class == "no_effect":
                            eff_class, effective = "changes_elsewhere", True
            except Exception:
                pass
        else:
            detail["capture"] = "unavailable"
            eff_class, effective = "unobserved", None
        # ---- undo, and PROVE it
        reversible: Optional[bool] = None
        try:
            if new_pop:
                self.close_new_popups()
                time.sleep(0.15)
                reversible = not self.new_popups()
            if effective and inverse is not None and eff_class in ("pan", "scroll", "zoom", "rotate", "nonrigid", "local_change", "translate_object",
                                                                   "rubber_band_with_selection", "shape_draw", "stroke", "changes_elsewhere"):
                inverse()
                time.sleep(0.4)
                bk = self.grab_region(region)
                if rb is not None and bk is not None:
                    reversible, rev_ev = self.restored(rb, bk, noise, int(detail.get("motion", {}).get("evidence", {}).get("changed_px", 0)))
                    detail["restore"] = rev_ev
                    if not reversible:
                        # one more honest try for apps with undo; never claim success without pixels
                        try:
                            self.hin.post_key_combo(self.hwnd, "ctrl+z" if self.pristine else "escape")
                            time.sleep(0.4)
                            reversible, rev_ev = self.restored(rb, self.grab_region(region), noise, int(detail.get("motion", {}).get("evidence", {}).get("changed_px", 0)))
                            detail["restore_after_undo"] = rev_ev
                        except Exception:
                            pass
                        if not reversible:
                            self.dirty = True
            elif effective and inverse is None and eff_class in ("local_change", "rubber_band_with_selection", "shape_draw", "stroke", "translate_object", "changes_elsewhere"):
                # a click-like gesture changed content and has no inverse: ask the app's own undo, and PROVE it with pixels
                reversible = False
                try:
                    self.hin.post_key_combo(self.hwnd, "ctrl+z" if self.pristine else "escape")
                    time.sleep(0.4)
                    ok_undo, ev_undo = self.restored(rb, self.grab_region(region), noise)
                    detail["restore_after_undo"] = ev_undo
                    reversible = ok_undo
                except Exception:
                    pass
                if not reversible:
                    self.dirty_content = True
            elif not effective:
                reversible = True
        except Exception as exc:
            detail["undo_error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
        if clear is not None:
            try:
                clear()                                        # whatever else happened, an object gesture ends with nothing selected
            except Exception:
                pass
        # ---- quantify the transfer function where it is physical
        mo = detail.get("motion", {})
        pr = mo.get("params", {})
        if spec.name == "wheel" and eff_class == "zoom" and pr.get("scale"):
            detail["zoom_factor"] = round(float(pr["scale"]), 4)
            detail["zoom_note"] = f"x{round(float(pr['scale']), 3)} for {detail.get('clicks', 1)} wheel notch(es) in one message"
        if spec.name == "drag" and eff_class == "rotate" and drag_info and abs(drag_info["vec"][0]) > 0:
            detail["deg_per_px"] = round(float(pr.get("rot_deg", 0)) / drag_info["vec"][0], 4)
        if spec.name == "drag" and eff_class == "pan" and drag_info:
            v = drag_info["vec"]
            if abs(v[0]) > 0:
                detail["pan_ratio_x"] = round(float(pr.get("dx", 0)) / v[0], 3)
        res = GestureResult(region.id if target is None else target.id, kind_name, spec.label, eff_class, bool(delivered), effective, reversible, detail, round(time.time() - t0, 2))
        if self.evidence_dir and rb is not None and ra is not None:
            try:
                import os
                os.makedirs(self.evidence_dir, exist_ok=True)
                stem = os.path.join(self.evidence_dir, f"{len(self.results):03d}_{region.kind}_{spec.label.replace('+', '_')}")
                Image = __import__("PIL.Image", fromlist=["Image"])
                Image.fromarray(rb).save(stem + "_before.png")
                Image.fromarray(ra).save(stem + "_after.png")
                if mid_img["img"] is not None:
                    Image.fromarray(mid_img["img"]).save(stem + "_during.png")
                detail["evidence_png"] = stem + "_after.png"
            except Exception:
                pass
        self.results.append(res)
        self._persist(target or region, spec, res)
        if self.observer:
            try:
                self.observer("gesture", feats, predicted or "", eff_class)
            except Exception:
                pass
        return res

    def _persist(self, region: Region, spec: Spec, res: GestureResult) -> None:
        ev = f"run={self.run_id}; {res.detail.get('delivery', '')}; conf={res.detail.get('motion', {}).get('confidence', '')}"
        effect = {k: v for k, v in res.detail.items() if k != "motion"}
        if res.detail.get("motion"):
            effect["motion"] = {k: v for k, v in res.detail["motion"].items() if k != "evidence"}
        self.store.put_gesture(self.app_key, region.name, region.kind, spec.label, "+".join(spec.mods), res.effect_class, effect,
                               reversible=res.reversible, delivered=res.delivered, effective=res.effective, evidence=ev, run_id=self.run_id)
        if res.effective and res.effect_class not in ("no_effect", "undeliverable", "unobserved"):
            stmt = (f"{spec.label} on an object -> {res.effect_class}" if region.kind == "object" else f"{spec.label} on a {region.kind} region ('{region.name}') -> {res.effect_class}")
            extras = []
            if res.detail.get("zoom_factor"):
                extras.append(f"zoom x{res.detail['zoom_factor']} for {res.detail.get('clicks', 1)} wheel notch(es)")
            if res.detail.get("deg_per_px"):
                extras.append(f"{res.detail['deg_per_px']} deg per px dragged")
            if res.detail.get("pan_ratio_x"):
                extras.append(f"pan follows the pointer {res.detail['pan_ratio_x']}:1")
            if res.detail.get("items"):
                extras.append("items: " + ", ".join(i["name"] for i in res.detail["items"][:8] if i.get("name")))
            if extras:
                stmt += " (" + "; ".join(extras) + ")"
            self.store.claim(self.app_key, "gesture.rule", stmt, trust="measured", confidence=min(0.95, 0.5 + 0.5 * float(res.detail.get("motion", {}).get("confidence", 0.8))),
                             evidence=[C.Evidence("gesture", f"{self.run_id}:{region.id}:{spec.label}", ev)], value={"region_kind": region.kind, "gesture": spec.label, "effect": res.effect_class, "detail": {k: v for k, v in res.detail.items() if k not in ("motion", "items")}}, source="atlas.gestures")

    def find_objects(self, region: Region, max_objects: int = 3) -> List[Region]:
        """Things drawn on a canvas, found by SEGMENTATION (pixels unlike the dominant background colour, thin lines removed by an opening):
        the targets for gestures that only mean something ON an object (select, move, shift-move, object menu). No knowledge of the app."""
        import numpy as np
        import cv2
        info = self.prepare(region)
        img = self.grab_region(region)
        if img is None or img.ndim != 3:
            return []
        arr = img[:, :, :3]
        q = (arr >> 4).astype(np.int32)
        key = (q[:, :, 0] << 8) | (q[:, :, 1] << 4) | q[:, :, 2]
        vals, counts = np.unique(key, return_counts=True)
        bg = int(vals[counts.argmax()])
        bgc = np.array([((bg >> 8) & 15) * 16 + 8, ((bg >> 4) & 15) * 16 + 8, (bg & 15) * 16 + 8])
        mask = (np.abs(arr.astype(np.int32) - bgc).sum(axis=2) > 90).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
        n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
        found = []
        for i in range(1, n):
            x, y, w_, h_, a = [int(v) for v in stats[i]]
            if 400 <= a <= 0.4 * mask.size:
                found.append((a, (x, y, x + w_, y + h_)))
        found.sort(reverse=True)
        ratio, eff = info["ratio"], info["region"]
        out: List[Region] = []
        for k, (a, (x0, y0, x1, y1)) in enumerate(found[:max_objects]):
            rect = (int(eff.rect[0] + x0 / ratio), int(eff.rect[1] + y0 / ratio), int(eff.rect[0] + x1 / ratio), int(eff.rect[1] + y1 / ratio))
            out.append(Region(id=f"object:{region.id}:{k}", kind="object", name="object", rect=rect, source="segmentation", parent=region.id, img_box=(x0, y0, x1, y1)))
        # an EMPTY place: the point of the canvas farthest from every object (where a click clears a selection)
        best, best_d = None, -1.0
        gx, gy = img.shape[1], img.shape[0]
        for fx in (0.08, 0.2, 0.35, 0.5, 0.65, 0.8, 0.92):
            for fy in (0.08, 0.2, 0.35, 0.5, 0.65, 0.8, 0.92):
                px, py = fx * gx, fy * gy
                d = min([max(0.0, max(b[0] - px, px - b[2], b[1] - py, py - b[3])) for _, b in found] or [1e9])
                if d > best_d:
                    best, best_d = (px, py), d
        if best is not None:
            info["empty"] = (int(eff.rect[0] + best[0] / ratio), int(eff.rect[1] + best[1] / ratio))
        return out

    def probe_objects(self, region: Region, objects: Sequence[Region], *, max_s: float = 25.0) -> List[GestureResult]:
        out: List[GestureResult] = []
        t_end = time.time() + max_s
        for obj in objects:
            for sp in OBJECT_GRAMMAR:
                if self.left() < 1.0 or time.time() > t_end:
                    return out
                if sp.mutating and not self.pristine:
                    continue
                if self.dirty_content and sp.mutating:
                    continue
                if self.dirty and sp.name == "drag":
                    continue
                if self.hung() or not self.ptr.alive():
                    return out
                out.append(self.perform(region, sp, target=obj))
        return out

    # ---- the run
    def probe_region(self, region: Region, specs: Optional[Sequence[Spec]] = None, *, max_s: float = 30.0) -> List[GestureResult]:
        specs = list(specs or GRAMMARS.get(region.kind, CONTROL_GRAMMAR))
        out: List[GestureResult] = []
        t_end = time.time() + max_s
        for sp in specs:
            if self.left() < 1.0 or time.time() > t_end:
                break
            if sp.mutating and not self.pristine:
                continue
            if self.dirty and sp.name in ("drag", "wheel"):
                continue
            if self.hung() or not self.ptr.alive():
                self.log("app stopped answering: gesture probing halted")
                break
            out.append(self.perform(region, sp))
        return out

    def run(self, regions: Optional[List[Region]] = None, nodes: Optional[List[Any]] = None) -> Dict[str, Any]:
        regs = regions if regions is not None else discover_regions(self.hwnd, nodes)
        order = {"canvas": 0, "blind": 1, "text": 2, "list": 3, "tree": 3, "grid": 3, "slider": 4, "control": 5}
        regs = sorted(regs, key=lambda r: (order.get(r.kind, 9), -(r.w * r.h)))
        per = max(6.0, self.budget_s / max(1, len(regs)))
        for r in regs:
            if self.left() < 1.5:
                break
            self.probe_region(r, max_s=min(self.left() - 0.5, per * (2.5 if r.kind in ("canvas", "blind") else 1.0)))
            if r.kind in ("canvas", "blind") and self.left() > 6.0:
                try:
                    objs = self.find_objects(r, 2)
                    if objs:
                        self.probe_objects(r, objs, max_s=min(self.left() - 0.5, per * 2.0))
                except Exception as exc:
                    self.log(f"object probing skipped: {type(exc).__name__}: {str(exc)[:80]}")
        summary: Dict[str, Any] = {"regions": [{"id": r.id, "kind": r.kind, "name": r.name, "size": [r.w, r.h]} for r in regs],
                                   "gestures": len(self.results), "effective": sum(1 for g in self.results if g.effective),
                                   "undeliverable": sum(1 for g in self.results if g.effect_class == "undeliverable"),
                                   "dirty": self.dirty, "seconds": round(time.time() - self.t0, 1),
                                   "by_effect": {}}
        for g in self.results:
            summary["by_effect"][g.effect_class] = summary["by_effect"].get(g.effect_class, 0) + 1
        return summary
