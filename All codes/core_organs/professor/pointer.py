"""
professor.pointer -- THE VIRTUAL MOUSE: every thing a physical mouse does (move, hover, click, double / right / middle click, press-and-hold, drag, drag-select, lasso, drag-and-drop, flick,
wheel in both axes, with Shift / Ctrl / Alt held) delivered to an application the run launched, WITHOUT using, moving or blocking the person's mouse or keyboard.

A gesture is first COMPILED into an event script (professor.pointer.Ev: move / down / up / wheel, with times, positions, buttons, modifiers) that does not depend on any delivery route.
The script is then delivered by the first ROUTE this application accepts. Routes are tried in an order that is LEARNED per application (data/professor/app_traits.json, key 'pointer')
and every route that works is remembered, every route that does not is remembered with the reason:

  native   the application's own input / object-model interface (adapters that offer .pointer_events(script): a Chromium DevTools adapter, an editor's scripting bridge) - no OS input at all
  posted   window messages posted to the exact child window under the point (classic Win32 / WinForms / Tk / Qt / Java ... toolkits that take their input from the message queue)
  shim     posted messages + an IN-PROCESS agent (professor.inproc, Frida) that answers the polling calls the application makes - GetCursorPos / GetAsyncKeyState / GetKeyState / GetMessagePos -
           with the VIRTUAL pointer's state, and swallows SetCursorPos / ClipCursor, so the person's own cursor never leaks into the application and the application can never move it.
           Measured: WPF (ignores posted messages) and Blender (GHOST / OpenGL, ignores them) accept the same posted messages once this agent answers their polling. Owned instances only.
  uia      a plain wheel done through the scrollable control's UI Automation ScrollPattern (applications that reject a posted wheel)
  touch    a SYNTHETIC touch contact (professor.pointer_inject) on the owned window brought on screen as a GHOST (near-zero opacity, never activated, on top, away from the person's cursor,
           person idle) for the length of the gesture. Only for applications that read the Windows pointer stack themselves (WinUI / UWP / Chromium ...): a toolkit that promotes touch to mouse
           input MOVES the person's cursor, which is measured on every use and forbids this route for that application for good.
  none     the gesture is reported as undeliverable WITH the reason of every route tried.

Rules that are enforced here, not trusted to callers: nothing is sent unless the Effector allows input (a window the Professor launched or the person authorised); the in-process agent is attached
only to a process the Professor launched (fx.owned); the person's cursor is sampled during every delivery and, if a route moved it, it is put back at once and that route is closed for the
application; every verb is a script, so adding a gesture is adding a compiler function, not a route.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import math
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import config as CFG

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK = 0x200, 0x201, 0x202, 0x203
WM_RBUTTONDOWN, WM_RBUTTONUP, WM_RBUTTONDBLCLK, WM_MBUTTONDOWN, WM_MBUTTONUP, WM_MBUTTONDBLCLK = 0x204, 0x205, 0x206, 0x207, 0x208, 0x209
WM_MOUSEWHEEL, WM_XBUTTONDOWN, WM_XBUTTONUP, WM_MOUSEHWHEEL = 0x20A, 0x20B, 0x20C, 0x20E
MK_LBUTTON, MK_RBUTTON, MK_SHIFT, MK_CONTROL, MK_MBUTTON, MK_XBUTTON1, MK_XBUTTON2 = 0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40
CS_DBLCLKS, GCL_STYLE = 0x8, -26
BUTTON_BIT = {"left": 1, "right": 2, "middle": 4, "x1": 8, "x2": 16}                           # the agent's button mask
BUTTON_MK = {"left": MK_LBUTTON, "right": MK_RBUTTON, "middle": MK_MBUTTON, "x1": MK_XBUTTON1, "x2": MK_XBUTTON2}
BUTTON_MSG = {"left": (WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK), "right": (WM_RBUTTONDOWN, WM_RBUTTONUP, WM_RBUTTONDBLCLK),
              "middle": (WM_MBUTTONDOWN, WM_MBUTTONUP, WM_MBUTTONDBLCLK), "x1": (WM_XBUTTONDOWN, WM_XBUTTONUP, WM_XBUTTONDOWN), "x2": (WM_XBUTTONDOWN, WM_XBUTTONUP, WM_XBUTTONDOWN)}
MOD_BIT = {"shift": 1, "ctrl": 2, "alt": 4, "win": 8}
TRAITS_KEY = "pointer"
ROUTES = ("native", "posted", "shim", "uia", "touch")

_u = ctypes.WinDLL("user32", use_last_error=True)
_u.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_u.PostMessageW.restype = wt.BOOL
_u.ScreenToClient.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
_u.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
_u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
_u.IsWindow.argtypes = [wt.HWND]
_u.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
_u.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
_u.GetClassLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
_u.GetClassLongPtrW.restype = ctypes.c_size_t
_u.WindowFromPoint.argtypes = [wt.POINT]
_u.WindowFromPoint.restype = wt.HWND
_u.GetAncestor.argtypes = [wt.HWND, wt.UINT]
_u.GetAncestor.restype = wt.HWND
_u.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
_u.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
_u.GetWindowLongW.restype = ctypes.c_long
_u.SetWindowLongW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_long]
_u.SetLayeredWindowAttributes.argtypes = [wt.HWND, wt.COLORREF, ctypes.c_ubyte, wt.DWORD]
_u.GetLayeredWindowAttributes.argtypes = [wt.HWND, ctypes.POINTER(wt.COLORREF), ctypes.POINTER(ctypes.c_ubyte), ctypes.POINTER(wt.DWORD)]
_u.GetForegroundWindow.restype = wt.HWND
_u.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
_u.EnumChildWindows.argtypes = [wt.HWND, ctypes.c_void_p, wt.LPARAM]
_u.IsIconic.argtypes = [wt.HWND]
_u.GetSystemMetrics.argtypes = [ctypes.c_int]
HWND_TOPMOST, HWND_NOTOPMOST = wt.HWND(-1), wt.HWND(-2)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x4, 0x10, 0x40
GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT = -20, 0x80000, 0x08000000, 0x80, 0x20
LWA_ALPHA = 0x2


# ------------------------------------------------------------------------------------------------------------- traits (shared file with professor.gestures)
def _traits_path() -> str:
    return os.path.join(CFG.DATA_DIR, "app_traits.json")


def load_traits(app_key: str) -> Dict[str, Any]:
    """What was learned about how this application takes pointer input: {route: 'ok' | 'delivered' | 'ignored' | 'moves_cursor' | 'unavailable' | 'ghost_fails'}. Facts recorded by the first
    measurements (professor.gestures: posted_pointer, touch_moves_cursor) count as well unless a newer measurement says otherwise."""
    try:
        with open(_traits_path(), encoding="utf-8") as fh:
            app = json.load(fh).get(app_key, {}) or {}
    except Exception:
        return {}
    t = dict(app.get(TRAITS_KEY, {}) or {})
    if "posted" not in t and app.get("posted_pointer") is not None:
        t["posted"] = "ok" if app["posted_pointer"] else "ignored"
    if "touch" not in t and app.get("touch_moves_cursor") is not None:
        t["touch"] = "moves_cursor" if app["touch_moves_cursor"] else "ok"
    return t


def save_trait(app_key: str, route: str, value: Any) -> None:
    if not app_key:
        return
    d: Dict[str, Any] = {}
    try:
        with open(_traits_path(), encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        pass
    d.setdefault(app_key, {}).setdefault(TRAITS_KEY, {})[route] = value
    os.makedirs(os.path.dirname(_traits_path()), exist_ok=True)
    tmp = _traits_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, _traits_path())


# ------------------------------------------------------------------------------------------------------------- the event script
@dataclass
class Ev:
    kind: str                                       # move | down | up | wheel | hwheel
    x: float = 0.0
    y: float = 0.0
    button: str = ""
    mods: Tuple[str, ...] = ()
    delta: int = 0                                  # wheel: 120 per notch (positive = away from the user / up / right)
    dt: float = 0.0                                 # seconds to wait BEFORE this event
    dbl: bool = False                               # the second press of a double click (sent as the double-click message when the window class asks for one)


Script = List[Ev]


def glide(p0: Tuple[float, float], p1: Tuple[float, float], step_px: float = 9.0, ease: bool = True) -> List[Tuple[float, float]]:
    """Points from p0 to p1 about `step_px` apart; with `ease` they bunch up near both ends (a hand accelerates and brakes)."""
    d = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    n = max(2, int(d / max(1.0, step_px)))
    out = []
    for i in range(1, n + 1):
        t = i / n
        if ease:
            t = t * t * (3 - 2 * t)
        out.append((p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t))
    return out


def s_move(x: float, y: float, mods: Sequence[str] = ()) -> Script:
    return [Ev("move", x, y, mods=tuple(mods))]


def s_hover(x: float, y: float, dwell: float = 0.35, mods: Sequence[str] = ()) -> Script:
    """Arrive, then rest: tooltips and hover highlights need a still pointer for a moment (two moves 1 px apart, then the dwell)."""
    return [Ev("move", x - 1, y, mods=tuple(mods)), Ev("move", x, y, dt=0.02, mods=tuple(mods)), Ev("move", x, y, dt=dwell, mods=tuple(mods))]


def s_click(x: float, y: float, button: str = "left", count: int = 1, mods: Sequence[str] = (), hold: float = 0.05) -> Script:
    m = tuple(mods)
    sc: Script = [Ev("move", x - 1, y, mods=m), Ev("move", x, y, dt=0.02, mods=m)]
    for i in range(max(1, count)):
        sc.append(Ev("down", x, y, button, m, dt=0.04 if i == 0 else 0.05, dbl=(i % 2 == 1)))
        sc.append(Ev("up", x, y, button, m, dt=hold))
    return sc


def s_hold(x: float, y: float, secs: float = 0.8, button: str = "left", mods: Sequence[str] = ()) -> Script:
    m = tuple(mods)
    return [Ev("move", x - 1, y, mods=m), Ev("move", x, y, dt=0.02, mods=m), Ev("down", x, y, button, m, dt=0.04), Ev("up", x, y, button, m, dt=secs)]


def s_drag(points: Sequence[Tuple[float, float]], button: str = "left", mods: Sequence[str] = (), duration: float = 0.5, press_dwell: float = 0.06, end_dwell: float = 0.05) -> Script:
    """Press at the first point, follow the others in `duration` seconds, release at the last. A path (stroke, lasso, curve) or two points (a straight drag / marquee)."""
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) == 2:
        pts = [pts[0]] + glide(pts[0], pts[1])
    m = tuple(mods)
    sc: Script = [Ev("move", pts[0][0], pts[0][1], mods=m), Ev("down", pts[0][0], pts[0][1], button, m, dt=press_dwell)]
    per = max(0.0, duration) / max(1, len(pts) - 1)
    for x, y in pts[1:]:
        sc.append(Ev("move", x, y, button, m, dt=per))
    sc.append(Ev("up", pts[-1][0], pts[-1][1], button, m, dt=end_dwell))
    return sc


def s_drag_select(p0: Tuple[float, float], p1: Tuple[float, float], mods: Sequence[str] = (), duration: float = 0.5) -> Script:
    """A marquee / rubber band: left button down at one corner, straight to the opposite corner, up."""
    return s_drag([p0, p1], "left", mods, duration)


def s_flick(x: float, y: float, direction: str = "right", distance: float = 240.0, ms: float = 90.0, button: str = "left") -> Script:
    """A quick swipe: short, fast, released while still moving (scroll inertia, swipe-to-dismiss, page flips)."""
    dx, dy = {"right": (1, 0), "left": (-1, 0), "up": (0, -1), "down": (0, 1)}.get(direction, (1, 0))
    pts = [(x + dx * distance * (i / 8.0) ** 1.4, y + dy * distance * (i / 8.0) ** 1.4) for i in range(9)]
    return s_drag(pts, button, (), ms / 1000.0, press_dwell=0.02, end_dwell=0.0)


def s_drop(src: Tuple[float, float], dst: Tuple[float, float], hover: float = 0.35, button: str = "left", mods: Sequence[str] = ()) -> Script:
    """Drag-and-drop: press on the source, move past the drag threshold, glide to the target, stay over it (drag-over feedback is delivered while the pointer rests), release."""
    m = tuple(mods)
    first = (src[0] + 9 * (1 if dst[0] >= src[0] else -1), src[1] + 4 * (1 if dst[1] >= src[1] else -1))
    sc: Script = [Ev("move", src[0], src[1], mods=m), Ev("down", src[0], src[1], button, m, dt=0.06), Ev("move", first[0], first[1], button, m, dt=0.08)]
    for x, y in glide(first, dst):
        sc.append(Ev("move", x, y, button, m, dt=0.016))
    sc.append(Ev("move", dst[0], dst[1], button, m, dt=hover))
    sc.append(Ev("up", dst[0], dst[1], button, m, dt=0.05))
    return sc


def s_wheel(x: float, y: float, clicks: float = 1.0, horizontal: bool = False, mods: Sequence[str] = ()) -> Script:
    """`clicks` notches (positive = up / right, negative = down / left), one notch at a time like a real wheel."""
    m = tuple(mods)
    n = max(1, int(abs(clicks)))
    sgn = 1 if clicks >= 0 else -1
    sc: Script = [Ev("move", x, y, mods=m)]
    for i in range(n):
        sc.append(Ev("hwheel" if horizontal else "wheel", x, y, mods=m, delta=120 * sgn, dt=0.04))
    return sc


def script_points(script: Script) -> List[Tuple[float, float]]:
    return [(e.x, e.y) for e in script if e.kind in ("move", "down", "up", "wheel", "hwheel")]


def script_bbox(script: Script, pad: int = 12) -> Tuple[int, int, int, int]:
    pts = script_points(script)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return int(min(xs)) - pad, int(min(ys)) - pad, int(max(xs)) + pad, int(max(ys)) + pad


def script_buttons(script: Script) -> set:
    return {e.button for e in script if e.kind in ("down", "up") and e.button}


def script_duration(script: Script) -> float:
    return sum(e.dt for e in script)


# ------------------------------------------------------------------------------------------------------------- helpers
def _lp(x: int, y: int) -> int:
    return ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)


def cursor_pos() -> Tuple[int, int]:
    p = wt.POINT()
    _u.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def window_rect(hwnd: int) -> Tuple[int, int, int, int]:
    r = wt.RECT()
    _u.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def window_pid(hwnd: int) -> int:
    p = wt.DWORD()
    _u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    return int(p.value)


def _child_at(top: int, sx: int, sy: int) -> int:
    try:
        from core_organs import headless_input as hin
        return int(hin.child_at(top, int(sx), int(sy)) or top)
    except Exception:
        return top


def _mods_mask(mods: Sequence[str]) -> int:
    v = 0
    for m in mods:
        v |= MOD_BIT.get(m, 0)
    return v


def _mk(mods: Sequence[str]) -> int:
    return (MK_SHIFT if "shift" in mods else 0) | (MK_CONTROL if "ctrl" in mods else 0)


class _LII(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


def idle_ms() -> int:
    """Milliseconds since the last REAL input event (keyboard / mouse / touch / pen) reached the desktop."""
    lii = _LII(ctypes.sizeof(_LII), 0)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    return int((ctypes.windll.kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF)


class CursorWatch:
    """Samples the PERSON'S cursor (GetCursorPos) every ~3 ms while a route delivers: proves the route did not move it. `moved_to_script` says the movement ended on a point of the script."""
    def __init__(self):
        self.start = cursor_pos()
        self.t0 = time.time()
        self.last = self.start
        self.max_dev = 0
        self._stop = False
        self._t = threading.Thread(target=self._run, daemon=True, name="cursor-watch")

    def _run(self) -> None:
        while not self._stop:
            self.last = cursor_pos()
            self.max_dev = max(self.max_dev, abs(self.last[0] - self.start[0]) + abs(self.last[1] - self.start[1]))
            time.sleep(0.003)

    def __enter__(self) -> "CursorWatch":
        self._t.start()
        return self

    def __exit__(self, *a: Any) -> None:
        self._stop = True
        self._t.join(1.0)
        self.last = cursor_pos()
        self.max_dev = max(self.max_dev, abs(self.last[0] - self.start[0]) + abs(self.last[1] - self.start[1]))

    @property
    def moved(self) -> bool:
        return self.max_dev > 0

    @property
    def real_input_seen(self) -> bool:
        """True when real input reached the desktop during the watch: movement then may be the person's own and is not blamed on the route. (Synthetic touch / pen injection counts as input too,
        so for those routes the cursor's END position decides - see VirtualPointer.perform.)"""
        return idle_ms() < (time.time() - self.t0) * 1000 + 50


def pixels(hwnd: int, rect: Tuple[int, int, int, int]) -> Any:
    """The window's picture (PrintWindow, works parked) cropped to a SCREEN rectangle, grayscale; None when it cannot be taken."""
    try:
        import numpy as np
        from . import capture as CAP
        fr = CAP.grab_window(hwnd, isolated=True)
        if fr is None:
            return None
        ox, oy = fr.origin
        l, t, r, b = rect
        img = fr.image.convert("L").crop((max(0, l - ox), max(0, t - oy), max(1, r - ox), max(1, b - oy)))
        return np.asarray(img, dtype=np.int16)
    except Exception:
        return None


def changed(a: Any, b: Any) -> float:
    if a is None or b is None or a.shape != b.shape:
        return -1.0
    import numpy as np
    return float((np.abs(a - b) > 24).mean())


# ------------------------------------------------------------------------------------------------------------- the in-process agent (Frida)
class InprocAgent:
    """The polling shim inside the run's OWN application process (professor/inproc/agent.js). Lazy: a missing frida only means this route is unavailable."""
    AGENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inproc", "agent.js")

    def __init__(self, pid: int):
        self.pid = pid
        self.sess: Any = None
        self.script: Any = None
        self.on = False
        self.why = ""
        self.hooked: List[str] = []

    @staticmethod
    def available() -> Tuple[bool, str]:
        try:
            import frida  # noqa: F401
            return True, ""
        except Exception as exc:
            return False, f"frida is not installed ({type(exc).__name__}); pip install frida (wxWindows licence 3.1, local, no telemetry)"

    def attach(self) -> bool:
        ok, why = self.available()
        if not ok:
            self.why = why
            return False
        try:
            import frida
            with open(self.AGENT, encoding="utf-8") as fh:
                src = fh.read()
            self.sess = frida.attach(self.pid)
            self.script = self.sess.create_script(src)
            self.script.load()
            st = self.script.exports_sync.state()
            self.hooked = list(st.get("hooked", []))
            if not self.hooked:
                return False
            try:
                self.script.exports_sync.kb(True)                                          # the keyboard too is virtual from now on: the person's own Shift / Ctrl never reaches this process
            except Exception:
                pass
            if not self._guard_holds():
                self.why = "the cursor guard does not hold in this process (SetCursorPos still reached the desktop): not used"
                self.detach()
                return False
            return True
        except Exception as exc:
            self.why = f"could not attach to pid {self.pid}: {type(exc).__name__}: {str(exc)[:120]}"
            self.detach()
            return False

    def _guard_holds(self) -> bool:
        """The agent swallows an application's own SetCursorPos. Proved before the agent is used: the process is asked to move the cursor; the agent must answer the call itself (it never reaches the desktop)."""
        if "SetCursorPos" not in self.hooked:
            return False                                                                   # no hook, no test: calling it would reach the desktop
        try:
            self.script.exports_sync.selftest(7, 9)
            st = self.script.exports_sync.state().get("s", {})
        except Exception:
            return False
        return (st.get("x"), st.get("y")) == (7, 9)                                       # the call was answered by the agent (it records the position it was asked for) - it never reached the desktop

    @property
    def attached(self) -> bool:
        return self.script is not None

    def set(self, x: float, y: float, buttons: int, mods: int, scale: float = 1.0, hwnd: int = 0) -> None:
        if self.script is not None:
            self.script.exports_sync.set(True, int(round(x * scale)), int(round(y * scale)), int(buttons), int(mods), hex(int(hwnd)))
            self.on = True

    def release(self) -> None:
        """Stop answering polls with the virtual state (the swallowing of SetCursorPos / ClipCursor stays)."""
        if self.script is not None and self.on:
            try:
                self.script.exports_sync.set(False, 0, 0, 0, 0)
            except Exception:
                pass
            self.on = False

    def polls(self) -> int:
        try:
            return int(sum(self.script.exports_sync.state().get("calls", {}).values()))
        except Exception:
            return 0

    def quiet(self, min_s: float = 0.1, max_s: float = 1.5) -> None:
        """Wait until the application stopped polling (it has drained the messages that were posted): the virtual state must stay in place until then."""
        t0 = time.time()
        last = self.polls()
        stable = time.time()
        while time.time() - t0 < max_s:
            time.sleep(0.04)
            cur = self.polls()
            if cur != last:
                last, stable = cur, time.time()
            elif time.time() - stable >= min_s:
                return

    def detach(self, timeout: float = 6.0) -> None:
        """Unhook and leave. Bounded: a target whose threads are inside a hook can make Frida wait; the worker is abandoned (daemon) rather than blocking the run."""
        sc, sess = self.script, self.sess
        self.script, self.sess, self.on = None, None, False

        def work() -> None:
            try:
                if sc is not None:
                    try:
                        sc.exports_sync.set(False, 0, 0, 0, 0)
                    except Exception:
                        pass
                    sc.unload()
            except Exception:
                pass
            try:
                if sess is not None:
                    sess.detach()
            except Exception:
                pass

        th = threading.Thread(target=work, daemon=True, name="inproc-detach")
        th.start()
        th.join(timeout)


# ------------------------------------------------------------------------------------------------------------- routes
@dataclass
class Delivery:
    ok: bool
    note: str = ""
    moved_cursor: bool = False


def dpi_scale(hwnd: int) -> float:
    """Physical -> the receiving process's own pixels (<1 for a DPI-virtualised, non-aware window); 1.0 when both agree. Posted client coordinates need no conversion (Windows scales them)."""
    try:
        from core_organs.atlas.gestures import dpi_ratio
        return float(dpi_ratio(hwnd))
    except Exception:
        return 1.0


class PostedRoute:
    """Window messages posted to the child window under each point; with an agent attached the application's polling calls see the same virtual pointer."""
    def __init__(self, top: int, agent: Optional[InprocAgent] = None):
        self.top, self.agent = top, agent
        self.held: int = 0
        self._buttons: int = 0
        self.capture: int = 0
        self.last: Tuple[float, float] = (0.0, 0.0)
        self.scale = dpi_scale(top) if agent is not None else 1.0

    def _client(self, h: int, sx: float, sy: float) -> Tuple[int, int]:
        pt = wt.POINT(int(round(sx)), int(round(sy)))
        _u.ScreenToClient(h, ctypes.byref(pt))
        return pt.x, pt.y

    def _target(self, sx: float, sy: float) -> int:
        return self.capture if self.capture and _u.IsWindow(self.capture) else _child_at(self.top, int(sx), int(sy))

    def deliver(self, script: Script) -> Delivery:
        from core_organs.atlas.gestures import key_state                                     # modifiers for toolkits that poll the keyboard table of the receiving thread
        if not _u.IsWindow(self.top):
            return Delivery(False, "window gone")
        mods_all = {m for e in script for m in e.mods}
        ok = True
        n = 0
        class_dbl: Dict[int, bool] = {}
        ctx = key_state(self.top, [m for m in mods_all if m in ("shift", "ctrl", "alt")]) if (self.agent is None or not self.agent.attached) else _Null()
        with ctx:
            t_next = time.perf_counter()
            for e in script:
                if e.dt > 0:
                    t_next += e.dt
                    wait = t_next - time.perf_counter()
                    if wait > 0:
                        time.sleep(wait)
                else:
                    t_next = max(t_next, time.perf_counter())
                mk = _mk(e.mods) | self.held
                bit = BUTTON_BIT.get(e.button, 0)
                if e.kind == "down":
                    self.held |= BUTTON_MK.get(e.button, 0)
                    mk |= BUTTON_MK.get(e.button, 0)
                    self._buttons |= bit
                elif e.kind == "up":
                    self.held &= ~BUTTON_MK.get(e.button, 0)
                    mk &= ~BUTTON_MK.get(e.button, 0)
                h = self._target(e.x, e.y)
                if self.agent is not None and self.agent.attached:
                    if e.kind == "up":
                        self._buttons &= ~bit
                    self.agent.set(e.x, e.y, self._buttons, _mods_mask(e.mods), self.scale, _child_at(self.top, int(e.x), int(e.y)))
                cx, cy = self._client(h, e.x, e.y)
                if e.kind == "move":
                    ok &= bool(_u.PostMessageW(h, WM_MOUSEMOVE, mk, _lp(cx, cy)))
                elif e.kind == "down":
                    if not self.capture:
                        self.capture = h
                    dn, _up, dbl = BUTTON_MSG[e.button]
                    msg = dn
                    if e.dbl:
                        if h not in class_dbl:
                            class_dbl[h] = bool(_u.GetClassLongPtrW(h, GCL_STYLE) & CS_DBLCLKS)
                        msg = dbl if class_dbl[h] else dn
                    wp = mk | (((0x0001 if e.button == "x1" else 0x0002) << 16) if e.button in ("x1", "x2") else 0)
                    ok &= bool(_u.PostMessageW(h, msg, wp, _lp(cx, cy)))
                elif e.kind == "up":
                    _dn, up, _d = BUTTON_MSG[e.button]
                    wp = mk | (((0x0001 if e.button == "x1" else 0x0002) << 16) if e.button in ("x1", "x2") else 0)
                    ok &= bool(_u.PostMessageW(h, up, wp, _lp(cx, cy)))
                    if not self.held:
                        self.capture = 0
                elif e.kind in ("wheel", "hwheel"):
                    wp = (((int(e.delta) & 0xFFFF) << 16) | mk) & 0xFFFFFFFF
                    ok &= bool(_u.PostMessageW(h, WM_MOUSEWHEEL if e.kind == "wheel" else WM_MOUSEHWHEEL, wp, _lp(int(e.x), int(e.y))))
                n += 1
                self.last = (e.x, e.y)
            if self.agent is not None and self.agent.attached:
                self.agent.quiet(0.1, 1.5)                                                  # the application drains the queue while the virtual state is still answering
            else:
                time.sleep(0.06)
        return Delivery(ok, f"posted {n} messages" + (" + in-process pointer state" if (self.agent is not None and self.agent.attached) else ""))


class _Null:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *a: Any) -> None:
        return None


POINTER_AWARE_RX = None


def pointer_aware(hwnd: int) -> Tuple[bool, str]:
    """Does this window's toolkit read the Windows POINTER stack itself (so that a synthetic touch contact is NOT turned into mouse input that moves the person's cursor)? Decided by the window
    classes of the window and its children - the XAML / WinUI / UWP families do by design (measured: Paint). Anything else (classic Win32, WinForms, WPF, GHOST / OpenGL ...) was measured to
    promote touch to mouse and move the cursor, so touch is not even tried there unless the caller explicitly allows a measurement (probe_touch)."""
    global POINTER_AWARE_RX
    import re
    if not hwnd:
        return False, "no window"
    if POINTER_AWARE_RX is None:
        POINTER_AWARE_RX = re.compile(r"WinUIDesktopWin32WindowClass|Microsoft\.UI\.|Windows\.UI\.|DesktopChildSiteBridge|ApplicationFrame|XamlHost|InputSite|CoreWindow|Xaml", re.I)
    names: List[str] = []
    buf = ctypes.create_unicode_buffer(256)

    def cls(h: int) -> str:
        _u.GetClassNameW(h, buf, 256)
        return buf.value

    try:
        names.append(cls(hwnd))
        proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

        def cb(h: int, _l: int) -> bool:
            if len(names) < 300:
                names.append(cls(h))
            return True
        _u.EnumChildWindows(hwnd, proto(cb), 0)
    except Exception:
        pass
    hit = next((n for n in names if POINTER_AWARE_RX.search(n)), "")
    return bool(hit), (f"window class '{hit}' reads the pointer stack" if hit else "no pointer-aware window class (classic toolkits turn touch into mouse input)")


class GhostWindow:
    """The owned window brought on screen so that a pointer contact can hit it, and hidden in plain sight: near-zero opacity, never activated, on top, away from the person's cursor.
    Restored (position, z-order, opacity, styles) when the context ends. `offset` is how far the window moved (screen coordinates of the script are shifted by it)."""
    def __init__(self, hwnd: int, alpha: int = 2):
        self.hwnd, self.alpha = hwnd, alpha
        self.offset = (0, 0)
        self.ok = False
        self.why = ""
        self._saved: Dict[str, Any] = {}

    def __enter__(self) -> "GhostWindow":
        h = self.hwnd
        l, t, r, b = window_rect(h)
        w, hh = r - l, b - t
        cx, cy = cursor_pos()
        sw, sh = _u.GetSystemMetrics(0), _u.GetSystemMetrics(1)
        if w >= sw or hh >= sh:
            w, hh = min(w, sw - 40), min(hh, sh - 40)
        gx = 20 if cx > sw // 2 else max(20, sw - w - 20)                                 # the side of the screen the person's cursor is NOT on
        gy = max(20, min(60, sh - hh - 20))
        self._saved = {"rect": (l, t), "ex": _u.GetWindowLongW(h, GWL_EXSTYLE), "fg": _u.GetForegroundWindow()}
        a, key, flags = ctypes.c_ubyte(), wt.COLORREF(), wt.DWORD()
        self._saved["layered"] = bool(_u.GetLayeredWindowAttributes(h, ctypes.byref(key), ctypes.byref(a), ctypes.byref(flags)))
        self._saved["alpha"] = a.value if self._saved["layered"] else 255
        _u.SetWindowLongW(h, GWL_EXSTYLE, self._saved["ex"] | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        if not _u.SetLayeredWindowAttributes(h, 0, self.alpha, LWA_ALPHA):
            self.why = f"the window cannot be made transparent (error {ctypes.get_last_error()}): it would be visible to the person"
            _u.SetWindowLongW(h, GWL_EXSTYLE, self._saved["ex"])
            return self
        _u.SetWindowPos(h, HWND_TOPMOST, gx, gy, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        time.sleep(0.25)
        nl, nt, _nr, _nb = window_rect(h)
        self.offset = (nl - l, nt - t)
        self.ok = abs(nl - gx) <= 2 or (nl, nt) != (l, t)
        if not self.ok:
            self.why = "the window did not move on screen"
        return self

    def __exit__(self, *a: Any) -> None:
        h = self.hwnd
        if not _u.IsWindow(h):
            return
        l, t = self._saved.get("rect", (0, 0))
        _u.SetWindowPos(h, HWND_NOTOPMOST, l, t, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
        for _ in range(3):                                                                   # an application may answer the move with its own (DPI) re-layout: put it back until it stays
            time.sleep(0.15)
            if _u.IsIconic(h):
                break
            cl, ct, _r, _b = window_rect(h)
            if abs(cl - l) <= 2 and abs(ct - t) <= 2:
                break
            _u.SetWindowPos(h, HWND_NOTOPMOST, l, t, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
        if self._saved.get("layered") and self._saved.get("alpha", 255) < 255:
            _u.SetLayeredWindowAttributes(h, 0, self._saved["alpha"], LWA_ALPHA)
        else:
            _u.SetLayeredWindowAttributes(h, 0, 255, LWA_ALPHA)
        _u.SetWindowLongW(h, GWL_EXSTYLE, self._saved.get("ex", 0))
        fg0 = self._saved.get("fg")
        if fg0 and _u.GetForegroundWindow() != fg0 and _u.IsWindow(fg0) and not _u.IsIconic(fg0):
            try:
                from core_organs import headless_input as hin
                hin._hand_back_focus(int(fg0))
            except Exception:
                pass


class TouchRoute:
    """Synthetic touch on the ghost window. Left button only (tap, press-and-hold, drag, flick, marquee, drop): a touch contact has no other buttons or wheel."""
    NEED = "touch has one button and no wheel"

    def __init__(self, top: int, visible_ok: bool = False, guard: Optional[Callable[[Sequence[Tuple[float, float]], Tuple[int, int]], Tuple[bool, str]]] = None):
        self.top, self.visible_ok, self.guard = top, visible_ok, guard

    @staticmethod
    def supports(script: Script) -> Tuple[bool, str]:
        for e in script:
            if e.kind in ("wheel", "hwheel"):
                return False, "touch has no wheel"
            if e.button and e.button != "left":
                return False, "touch has only the primary button"
            if e.mods:
                return False, "touch carries no modifier keys"
        return True, ""

    def deliver(self, script: Script) -> Delivery:
        from .pointer_inject import PointerInjector
        sup, why = self.supports(script)
        if not sup:
            return Delivery(False, why)
        user_busy = False
        try:
            from core_organs.background_window import user_idle_ms
            user_busy = user_idle_ms() < 1200
        except Exception:
            pass
        if user_busy and not self.visible_ok:
            return Delivery(False, "the person is using the mouse / keyboard right now: a ghost window would be in their way")
        with GhostWindow(self.top) as gw:
            if not gw.ok:
                return Delivery(False, gw.why or "no ghost window")
            ox, oy = gw.offset
            self.last_offset = gw.offset
            top_ok = True
            first = script_points(script)[0]
            hit = _u.GetAncestor(_u.WindowFromPoint(wt.POINT(int(first[0] + ox), int(first[1] + oy))), 2)
            top_ok = (hit == self.top)
            if not top_ok:
                return Delivery(False, "another window is on top of the target at the gesture's start")
            if self.guard is not None:
                g_ok, g_why = self.guard(script_points(script), gw.offset)                 # the caller knows the surface: every point on the canvas, none over a link / button / another window
                if not g_ok:
                    return Delivery(False, "refused: " + g_why)
            ok_all = True
            with PointerInjector("touch") as pi:
                if not any(e.kind == "down" for e in script):
                    return Delivery(False, "touch needs a press")
                down = False
                t_next = time.perf_counter()
                for e in script:
                    t_next += e.dt
                    w = t_next - time.perf_counter()
                    if w > 0:
                        time.sleep(w)
                    x, y = int(round(e.x + ox)), int(round(e.y + oy))
                    if e.kind == "down":
                        ok_all &= pi.frame(x, y, "down")
                        down = True
                    elif e.kind == "move" and down:
                        ok_all &= pi.frame(x, y, "move")
                    elif e.kind == "up" and down:
                        ok_all &= pi.frame(x, y, "up")
                        down = False
                if down:
                    pi.frame(int(round(script_points(script)[-1][0] + ox)), int(round(script_points(script)[-1][1] + oy)), "up")
            time.sleep(0.15)
        return Delivery(ok_all, "synthetic touch on a ghost window")


class UiaScrollRoute:
    """The wheel, for an application that rejects a posted one: the scrollable control under the point is scrolled through its UI Automation ScrollPattern (no pointer, no focus). Wheel scripts only."""
    def __init__(self, top: int):
        self.top = top

    @staticmethod
    def supports(script: Script) -> bool:
        return bool(script) and all(e.kind in ("move", "wheel", "hwheel") for e in script) and any(e.kind in ("wheel", "hwheel") for e in script) and not any(e.mods for e in script)

    def deliver(self, script: Script) -> Delivery:
        if not self.supports(script):
            return Delivery(False, "only a plain wheel can be done through a scroll pattern")
        out: Dict[str, Any] = {}

        def work() -> None:
            try:
                from core_organs import fast_uia
                from .effectors import pattern_of
                nodes = fast_uia.snapshot(self.top, timeout_ms=3000) or []
                x, y = next((e.x, e.y) for e in script if e.kind in ("wheel", "hwheel"))
                cands = [n for n in nodes if "scroll" in (n.pats or []) and not n.offscreen and n.rect[0] <= x <= n.rect[2] and n.rect[1] <= y <= n.rect[3]]
                if not cands:
                    out["why"] = "no scrollable control under the point"
                    return
                node = min(cands, key=lambda n: (n.rect[2] - n.rect[0]) * (n.rect[3] - n.rect[1]))
                pat = pattern_of(node.ctrl, "Scroll")
                if pat is None:
                    out["why"] = "the control exposes no scroll pattern"
                    return
                NO, SMALL_DEC, SMALL_INC = 2, 1, 4
                n_done = 0
                for e in script:
                    if e.kind not in ("wheel", "hwheel"):
                        continue
                    for _ in range(3):                                                       # one notch = three lines
                        if e.kind == "wheel":
                            pat.Scroll(NO, SMALL_DEC if e.delta > 0 else SMALL_INC)
                        else:
                            pat.Scroll(SMALL_INC if e.delta > 0 else SMALL_DEC, NO)
                    n_done += 1
                out["ok"] = f"scrolled '{node.name or node.ctype}' {n_done} notch(es) through its scroll pattern"
            except Exception as exc:
                out["why"] = f"UIA error {type(exc).__name__}: {str(exc)[:80]}"

        th = threading.Thread(target=work, daemon=True, name="uia-scroll")
        th.start()
        th.join(4.0)
        if "ok" in out:
            return Delivery(True, out["ok"])
        return Delivery(False, out.get("why", "UI Automation did not answer in time"))


class NativeRoute:
    """The application's own pointer interface: an adapter with .pointer_events(script) -> (ok, note) (CDP Input.dispatchMouseEvent, an editor's scripting bridge, ...)."""
    def __init__(self, adapter: Any):
        self.adapter = adapter

    def deliver(self, script: Script) -> Delivery:
        try:
            ok, note = self.adapter.pointer_events(script)
        except Exception as exc:
            return Delivery(False, f"native pointer interface failed: {type(exc).__name__}: {str(exc)[:100]}")
        return Delivery(bool(ok), str(note))


# ------------------------------------------------------------------------------------------------------------- the pointer
@dataclass
class PointerResult:
    ok: bool
    route: str = ""
    note: str = ""
    changed: float = -1.0
    verified: Optional[bool] = None                 # True / False when an effect was checked, None when there was nothing to check it against
    moved_cursor: bool = False
    tried: List[str] = field(default_factory=list)

    @property
    def why(self) -> str:
        return self.note if self.ok else ("no route delivered the gesture: " + "; ".join(self.tried))


class VirtualPointer:
    def __init__(self, hwnd: int, app_key: str = "", fx: Any = None, overlay: Any = None, native: Any = None, visible_ok: bool = False, allow_shim: bool = True,
                 allow_touch: bool = True, log: Callable[[str], None] = lambda s: None, pid: int = 0, only: Sequence[str] = (), probe_touch: bool = False,
                 touch_guard: Optional[Callable[[Sequence[Tuple[float, float]], Tuple[int, int]], Tuple[bool, str]]] = None):
        self.hwnd, self.app_key, self.fx, self.overlay, self.native = hwnd, app_key, fx, overlay, native
        self.visible_ok, self.allow_shim, self.allow_touch, self.log, self.touch_guard = visible_ok, allow_shim, allow_touch, log, touch_guard
        self.pid = pid or window_pid(hwnd)
        self.probe_touch = probe_touch
        self.only = tuple(only)                                                              # tests / diagnostics: restrict the ladder to these routes (and ignore what was learned)
        self.traits = load_traits(app_key)
        self.agent: Optional[InprocAgent] = None
        self.pos: Tuple[float, float] = (0.0, 0.0)
        self.history: List[Dict[str, Any]] = []
        self._contrast: Dict[str, int] = {}
        self._demoted: set = set()

    # ---- gate
    def allowed(self) -> Tuple[bool, str]:
        if self.fx is not None and not self.fx.allowed:
            return False, "refused: " + self.fx.why_not()
        if not _u.IsWindow(self.hwnd):
            return False, "the window is gone"
        return True, ""

    def _owned(self) -> bool:
        return bool(self.fx is not None and getattr(self.fx, "owned", False))

    # ---- route bookkeeping
    def _mark(self, route: str, value: Any) -> None:
        self.traits[route] = value
        save_trait(self.app_key, route, value)

    def order(self, script: Script) -> List[str]:
        """Routes in the order they are tried: those measured to work first (cheapest first), unknown ones after, those measured NOT to work (or forbidden) never."""
        if self.only:
            return [r for r in self.only if r != "native" or self.native is not None]
        t = self.traits
        cand: List[str] = []
        if self.native is not None and hasattr(self.native, "pointer_events") and t.get("native") != "ignored":
            cand.append("native")
        if t.get("shim") == "ok" and t.get("posted") in ("ignored", None):
            cand += ["shim"]                                                                    # the shim is needed here: do not spend a posted attempt that is known to be ignored
        elif t.get("posted") != "ignored":
            cand.append("posted")
        if "shim" not in cand and self.allow_shim and self._owned() and t.get("shim") not in ("unavailable", "ignored"):
            cand.append("shim")
        cand.sort(key=lambda r: r in self._demoted)
        if UiaScrollRoute.supports(script) and t.get("uia") not in ("ignored",):
            cand.append("uia")
        if self.allow_touch and t.get("touch") not in ("moves_cursor", "ignored", "ghost_fails") and "touch" not in cand:
            if t.get("touch") == "ok" or self.probe_touch or pointer_aware(self.hwnd)[0]:
                cand.append("touch")
        return cand

    # ---- delivery
    def _glide(self, script: Script) -> None:
        if self.overlay is None:
            return
        try:
            pts = script_points(script)
            self.overlay.glide(pts[:: max(1, len(pts) // 40)], [10.0] * len(pts[:: max(1, len(pts) // 40)]))
        except Exception:
            pass

    def _route_obj(self, name: str) -> Tuple[Any, str]:
        if name == "native":
            return NativeRoute(self.native), ""
        if name == "posted":
            return PostedRoute(self.hwnd, None), ""
        if name == "shim":
            if self.agent is None:
                ag = InprocAgent(self.pid)
                if not ag.attach():
                    self._mark("shim", "unavailable")
                    return None, ag.why or "the in-process agent could not be attached"
                self.agent = ag
            return PostedRoute(self.hwnd, self.agent), ""
        if name == "touch":
            return TouchRoute(self.hwnd, self.visible_ok, self.touch_guard), ""
        if name == "uia":
            return UiaScrollRoute(self.hwnd), ""
        return None, "unknown route"

    def perform(self, script: Script, kind: str = "", verify: Optional[Callable[[], Optional[bool]]] = None, surface: Optional[Tuple[int, int, int, int]] = None,
                effect_expected: bool = True) -> PointerResult:
        """Deliver `script` by the first route that works. `verify()` (True / False / None=cannot tell) is checked after each delivery; without it the surface's pixels are compared (for gestures that
        are expected to change something). A route whose delivery had no effect is passed over and the next one is tried. WHAT IS LEARNED: a route is recorded as ignored by this application only
        by CONTRAST - a later route produced the effect the earlier one did not, twice - never because a gesture changed nothing (the state of the application may be why)."""
        ok, why = self.allowed()
        if not ok:
            return PointerResult(False, note=why, tried=[why])
        res = PointerResult(False)
        if not script:
            res.note = "empty gesture"
            return res
        surf = surface or script_bbox(script)
        silent: List[str] = []                                                             # routes that delivered without any effect
        for name in self.order(script):
            route, rwhy = self._route_obj(name)
            if route is None:
                res.tried.append(f"{name}: {rwhy}")
                continue
            before = pixels(self.hwnd, surf) if (verify is None and effect_expected) else None
            self._glide(script)
            with CursorWatch() as cw:
                try:
                    d = route.deliver(script)
                except Exception as exc:
                    d = Delivery(False, f"{type(exc).__name__}: {str(exc)[:100]}")
            if cw.moved and name == "touch":
                ends_on_gesture = any(abs(cw.last[0] - (x + getattr(route, "last_offset", (0, 0))[0])) + abs(cw.last[1] - (y + getattr(route, "last_offset", (0, 0))[1])) <= 8 for x, y in script_points(script))
                if ends_on_gesture or not cw.real_input_seen:
                    try:
                        _u.SetCursorPos(cw.start[0], cw.start[1])                              # give the person their cursor back at once, and never use this route again here
                    except Exception:
                        pass
                    self._mark("touch", "moves_cursor")
                    res.moved_cursor = True
                    res.tried.append(f"touch: delivered but it moved the person's cursor ({cw.max_dev} px): put back, route closed for this application")
                    continue
            elif cw.moved and not cw.real_input_seen:
                res.moved_cursor = True
                res.tried.append(f"{name}: WARNING the person's cursor moved ({cw.max_dev} px) with no real input: something other than this route moved it")
            if not d.ok:
                res.tried.append(f"{name}: {d.note}")
                if name == "touch" and ("transparent" in d.note or "did not move" in d.note):
                    self._mark("touch", "ghost_fails")
                continue
            verdict: Optional[bool] = None
            ch = -1.0
            if verify is not None:
                try:
                    verdict = verify()
                except Exception:
                    verdict = None
            elif effect_expected:
                time.sleep(0.35)
                after = pixels(self.hwnd, surf)
                ch = changed(before, after)
                verdict = None if ch < 0 else (ch > 0.0003)
                self._debug_pair(name, kind, before, after, ch)
            res.changed = ch
            res.tried.append(f"{name}: {d.note}" + (f", {ch:.4f} of the surface changed" if ch >= 0 else "") + (f", effect check: {verdict}" if verify is not None else ""))
            if verdict is False:
                silent.append(name)
                continue
            for early in silent:                                                            # the contrast: these delivered, this one made it happen
                self._contrast[early] = self._contrast.get(early, 0) + 1
                if self._contrast[early] >= 2 and self.traits.get(early) != "ok":
                    self._mark(early, "ignored")
            self._mark(name, "ok" if verdict else self.traits.get(name, "delivered"))
            res.ok, res.route, res.note, res.verified = True, name, d.note, verdict
            self.pos = script_points(script)[-1]
            self.history.append({"kind": kind, "route": name, "t": time.time(), "verified": verdict})
            if self.agent is not None and name != "shim":
                self.agent.release()
            return res
        res.note = "no route this application accepts could perform the gesture" if res.tried else "no route is open for this gesture: " + self.why_no_route(script)
        if not res.tried:
            res.tried.append(res.note)
        return res

    def why_no_route(self, script: Script) -> str:
        t = self.traits
        bits = [f"{r}: {t[r]}" for r in ("posted", "shim", "touch", "uia", "native") if t.get(r) in ("ignored", "unavailable", "moves_cursor", "ghost_fails")]
        if not self._owned():
            bits.append("the in-process agent is only used in a window the Professor launched")
        if self.allow_touch and "touch" not in self.order(script):
            bits.append("touch needs a pointer-aware toolkit")
        return "; ".join(bits) or "none applies"

    def _debug_pair(self, route: str, kind: str, before: Any, after: Any, ch: float) -> None:
        d = os.environ.get("HOJAIGA_POINTER_DEBUG", "")
        if not d or before is None or after is None:
            return
        try:
            from PIL import Image
            import numpy as np
            os.makedirs(d, exist_ok=True)
            stamp = f"{int(time.time())}_{self.app_key}_{kind}_{route}_{ch:.4f}"
            Image.fromarray(np.clip(before, 0, 255).astype("uint8")).save(os.path.join(d, stamp + "_before.png"))
            Image.fromarray(np.clip(after, 0, 255).astype("uint8")).save(os.path.join(d, stamp + "_after.png"))
        except Exception:
            pass

    def note_ineffective(self) -> None:
        """The caller saw no effect of the LAST delivery: that route is tried LAST for the rest of this session (nothing is persisted from a single observation)."""
        if self.history:
            self._demoted.add(self.history[-1]["route"])

    # ---- verbs (each compiles a script and performs it)
    def move(self, x: float, y: float, mods: Sequence[str] = ()) -> PointerResult:
        return self.perform(s_move(x, y, mods), "move", effect_expected=False)

    def hover(self, x: float, y: float, dwell: float = 0.35, mods: Sequence[str] = (), verify: Optional[Callable[[], Optional[bool]]] = None) -> PointerResult:
        return self.perform(s_hover(x, y, dwell, mods), "hover", verify, effect_expected=verify is not None)

    def click(self, x: float, y: float, button: str = "left", count: int = 1, mods: Sequence[str] = (), verify: Optional[Callable[[], Optional[bool]]] = None) -> PointerResult:
        return self.perform(s_click(x, y, button, count, mods), f"click-{button}x{count}", verify, effect_expected=verify is not None)

    def double_click(self, x: float, y: float, mods: Sequence[str] = (), verify: Optional[Callable[[], Optional[bool]]] = None) -> PointerResult:
        return self.click(x, y, "left", 2, mods, verify)

    def right_click(self, x: float, y: float, mods: Sequence[str] = (), verify: Optional[Callable[[], Optional[bool]]] = None) -> PointerResult:
        return self.click(x, y, "right", 1, mods, verify)

    def middle_click(self, x: float, y: float, mods: Sequence[str] = (), verify: Optional[Callable[[], Optional[bool]]] = None) -> PointerResult:
        return self.click(x, y, "middle", 1, mods, verify)

    def hold(self, x: float, y: float, secs: float = 0.8, button: str = "left", mods: Sequence[str] = (), verify: Optional[Callable[[], Optional[bool]]] = None) -> PointerResult:
        return self.perform(s_hold(x, y, secs, button, mods), "hold", verify, effect_expected=verify is not None)

    def drag(self, p0: Tuple[float, float], p1: Tuple[float, float], button: str = "left", mods: Sequence[str] = (), path: Optional[Sequence[Tuple[float, float]]] = None,
             duration: float = 0.5, verify: Optional[Callable[[], Optional[bool]]] = None, surface: Optional[Tuple[int, int, int, int]] = None) -> PointerResult:
        return self.perform(s_drag(path if path else [p0, p1], button, mods, duration), f"drag-{button}", verify, surface)

    def stroke(self, points: Sequence[Tuple[float, float]], duration: float = 0.6, verify: Optional[Callable[[], Optional[bool]]] = None) -> PointerResult:
        return self.perform(s_drag(points, "left", (), duration), "stroke", verify)

    def drag_select(self, p0: Tuple[float, float], p1: Tuple[float, float], mods: Sequence[str] = (), verify: Optional[Callable[[], Optional[bool]]] = None) -> PointerResult:
        return self.perform(s_drag_select(p0, p1, mods), "drag-select", verify)

    def lasso(self, points: Sequence[Tuple[float, float]], mods: Sequence[str] = (), verify: Optional[Callable[[], Optional[bool]]] = None) -> PointerResult:
        pts = list(points) + [points[0]]
        return self.perform(s_drag(pts, "left", mods, 0.7), "lasso", verify)

    def flick(self, x: float, y: float, direction: str = "right", distance: float = 240.0, ms: float = 90.0, verify: Optional[Callable[[], Optional[bool]]] = None) -> PointerResult:
        return self.perform(s_flick(x, y, direction, distance, ms), f"flick-{direction}", verify)

    def drag_drop(self, src: Tuple[float, float], dst: Tuple[float, float], mods: Sequence[str] = (), verify: Optional[Callable[[], Optional[bool]]] = None) -> PointerResult:
        return self.perform(s_drop(src, dst, mods=mods), "drag-drop", verify)

    def wheel(self, x: float, y: float, clicks: float = 1.0, horizontal: bool = False, mods: Sequence[str] = (), verify: Optional[Callable[[], Optional[bool]]] = None) -> PointerResult:
        return self.perform(s_wheel(x, y, clicks, horizontal, mods), "wheel-h" if horizontal else "wheel", verify, effect_expected=verify is not None)

    def close(self) -> None:
        if self.agent is not None:
            self.agent.detach()
            self.agent = None
