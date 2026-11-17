"""
professor.pointer_course -- THE DOT COURSE: the virtual cursor picks a dot up on one side of the screen and puts it next to the other dot on the opposite side.

A running, measurable test of the pointer agent END TO END (not an application test): the Professor creates its OWN small canvas window (it owns it, so posting it mouse messages is allowed by
the input law; the physical mouse is never touched), draws one dot near the left edge and another near the right edge, and drags the first next to the second with the SAME gesture compiler and
route ladder every application drag uses (press -> past the drag threshold -> glide -> rest over the target -> release). Success is MEASURED twice: by the canvas itself (where its dot ended up)
and by pixels (the picture before and after the drag differs where it should).

Why it matters for training:
  * every glide is a MEASURED movement (distance, target width, actual seconds) -> it feeds the motor-timing model (professor.ml.motor), which so far only had the textbook prior;
  * the press / move / release TIMING of s_drop is rehearsed against a target that always answers, so route problems show up as course failures, not as app mysteries;
  * the result is written next to the model: data/professor/pointer_course/<time>.json with pictures.

Runs standalone (python -m core_organs.professor.pointer_course) and as a phase of an AppRun (HOJAIGA_POINTER_COURSE=1)."""
from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes as wt
import json
import math
import os
import random
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from . import config as CFG
from . import pointer as PT

LRESULT, WNDPROC = ctypes.c_ssize_t, ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p)
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK = 0x200, 0x201, 0x202, 0x203
WM_NCHITTEST, WM_MOUSEACTIVATE, WM_PAINT, WM_CLOSE, WM_DESTROY, WM_QUIT = 0x84, 0x21, 0xF, 0x10, 0x2, 0x12
WM_VALIDATE_RECT = 0x13
MA_NOACTIVATE, HTCLIENT = 3, 1
WS_POPUP, WS_VISIBLE = 0x80000000, 0x10000000
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x80, 0x08000000, 0x00000008
CS_HREDRAW, CS_VREDRAW = 0x0001, 0x0002
CW_USEDEFAULT = -2147483648


class _MSG(ctypes.Structure):
    _fields_ = [("hwnd", wt.HWND), ("message", ctypes.c_uint), ("wParam", wt.WPARAM),
                ("lParam", wt.LPARAM), ("pt", wt.POINT), ("time", ctypes.c_uint)]


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


_u = ctypes.WinDLL("user32", use_last_error=True)
_g = ctypes.WinDLL("gdi32", use_last_error=True)
_k = ctypes.WinDLL("kernel32", use_last_error=True)
_u.DefWindowProcW.restype = ctypes.c_ssize_t
_u.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
_u.CreateWindowExW.restype = wt.HWND
_u.CreateWindowExW.argtypes = [ctypes.c_uint, wt.LPCWSTR, wt.LPCWSTR, ctypes.c_uint,
                               ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                               wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
_u.RegisterClassW.argtypes = [ctypes.c_void_p]
_u.LoadCursorW.restype = wt.HICON
_u.LoadCursorW.argtypes = [wt.HINSTANCE, wt.LPCWSTR]
_k.GetModuleHandleW.restype = wt.HINSTANCE
_k.GetModuleHandleW.argtypes = [wt.LPCWSTR]
_u.SetLayeredWindowAttributes.argtypes = [wt.HWND, wt.COLORREF, ctypes.c_ubyte, ctypes.c_uint]
# EVERY call the WndProc / message loop makes is fully typed and resolved HERE, at import, on the main thread. Two measured reasons: (1) a first lazy `dll.name` lookup from inside the WndProc
# (during DispatchMessage, on the canvas thread, while the main thread loads another DLL - psutil / PIL plugins import lazily) hits the Windows loader re-entrantly and crashed the process
# (access violation in ctypes.__getattr__); (2) an UNtyped call converts Python ints to C ints: HWND/HDC values beyond 2^31 come back TRUNCATED, and a truncated handle handed to GDI corrupts
# memory (measured: intermittent access violations during garbage collection while the course window painted). Types everywhere; nothing is looked up first from a callback.
for _n, _rt, _at in (
    ("SetCapture", wt.BOOL, [wt.HWND]), ("ReleaseCapture", wt.BOOL, []), ("InvalidateRect", wt.BOOL, [wt.HWND, ctypes.c_void_p, wt.BOOL]),
    ("BeginPaint", wt.HDC, [wt.HWND, ctypes.c_void_p]), ("EndPaint", wt.BOOL, [wt.HWND, ctypes.c_void_p]),
    ("FillRect", ctypes.c_int, [wt.HDC, ctypes.POINTER(wt.RECT), ctypes.c_void_p]),
    ("GetMessageW", ctypes.c_int, [ctypes.c_void_p, wt.HWND, ctypes.c_uint, ctypes.c_uint]),
    ("TranslateMessage", ctypes.c_int, [ctypes.c_void_p]), ("DispatchMessageW", ctypes.c_ssize_t, [ctypes.c_void_p]),
    ("PostQuitMessage", None, [ctypes.c_int]), ("IsWindow", wt.BOOL, [wt.HWND]), ("DestroyWindow", wt.BOOL, [wt.HWND]),
    ("GetSystemMetrics", ctypes.c_int, [ctypes.c_int]), ("SetWindowTextW", wt.BOOL, [wt.HWND, wt.LPCWSTR])):
    _f = getattr(_u, _n); _f.restype = _rt; _f.argtypes = _at
_u.PostMessageW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
_u.PostMessageW.restype = wt.BOOL
_u.ValidateRect.argtypes = [wt.HWND, ctypes.c_void_p]
_u.ValidateRect.restype = wt.BOOL
for _n, _rt, _at in (
    ("CreateSolidBrush", ctypes.c_void_p, [wt.COLORREF]), ("CreatePen", ctypes.c_void_p, [ctypes.c_int, ctypes.c_int, wt.COLORREF]),
    ("SelectObject", ctypes.c_void_p, [wt.HDC, ctypes.c_void_p]), ("Ellipse", ctypes.c_int, [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]),
    ("DeleteObject", ctypes.c_int, [ctypes.c_void_p])):
    _f = getattr(_g, _n); _f.restype = _rt; _f.argtypes = _at

COLORS = {"A": (0x2E, 0x6E, 0xF0), "B": (0x28, 0xA8, 0x50)}             # the moving dot is blue, the waiting dot green (BGR)
DOT_R = 14                                                              # dot radius, px

_CANVASES: Dict[int, Any] = {}                                          # hwnd -> the canvas that answers for it (the window class is registered ONCE for the process; see _ensure_class)
_PROC: Optional[Any] = None
_CLASS_LOCK = threading.Lock()
ERROR_CLASS_ALREADY_EXISTS = 180


def _dispatch(h: Any, msg: int, w: Any, lp: Any) -> int:
    c = _CANVASES.get(int(h) if h else 0)
    if c is None:                                                       # a message to a window whose canvas already stopped
        return int(_u.DefWindowProcW(h, msg, w, 0 if lp is None else int(lp)))
    return c._wndproc(h, msg, w, lp)


def _ensure_class() -> Tuple[bool, str]:
    """Register the course window class ONCE per process and keep the callback for the life of the process (a class whose WNDPROC thunk is freed is a crash waiting at exit or in a later round)."""
    global _PROC
    with _CLASS_LOCK:
        if _PROC is not None:
            return True, ""
        hinst = _k.GetModuleHandleW(None)
        proc = WNDPROC(_dispatch)
        cls = _WNDCLASSW()
        cls.style = CS_HREDRAW | CS_VREDRAW
        cls.lpfnWndProc = proc
        cls.hInstance = hinst
        cls.hCursor = _u.LoadCursorW(0, ctypes.cast(32512, wt.LPCWSTR))
        cls.hbrBackground = 0
        cls.lpszClassName = "HojaigaDotsCanvas"
        atom = _u.RegisterClassW(ctypes.byref(cls))
        err = ctypes.get_last_error()
        if not atom and err != ERROR_CLASS_ALREADY_EXISTS:
            return False, f"RegisterClassW failed (win32 error {err})"
        _PROC = proc                                                    # kept forever: the class points at it for the life of the process
        return True, ""


class DotsCanvas:
    """The Professor's own course window: a thin strip across the top of the screen with two dots. It answers the posted mouse messages with its OWN message loop (thread), grabs a dot on
    a press that lands on it, carries it while the button is held, drops it on release. Nothing here touches the physical mouse; the window never activates."""

    def __init__(self, width: int = 0, height: int = 140, a_pos: Optional[Tuple[int, int]] = None, b_pos: Optional[Tuple[int, int]] = None):
        sw = _u.GetSystemMetrics(0)
        self.width = width or (sw - 40)
        self.height = height
        self.x = 20
        self.y = 60
        self.a = list(a_pos or (70, self.height // 2))
        self.b = list(b_pos or (self.width - 70, self.height // 2))
        self.grab: Optional[str] = None
        self.pressed = 0
        self.released = 0
        self.t_grab = 0.0                                             # when a press took hold of a dot (canvas clock: the travel timing is measured HERE, not from the caller's wall)
        self.t_move0 = 0.0                                            # first move that carried the dot
        self.t_up = 0.0                                               # release that dropped it
        self._lk = threading.Lock()
        self.hwnd = 0
        self.fail_why = ""
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.alive = True

    # ---- geometry (screen coordinates of the dots: the strip is a plain popup, client == window)
    def dot_screen(self, key: str) -> Tuple[float, float]:
        with self._lk:
            x, y = (self.a if key == "A" else self.b)
            return (self.x + x, self.y + y)

    def distance_to(self, key: str, pt: Tuple[float, float]) -> float:
        dx, dy = self.dot_screen(key)
        return math.hypot(dx - pt[0], dy - pt[1])

    def travel_seconds(self) -> float:
        """The dot's own movement time: first carried moment -> release (0.0 when no grab->drop happened). This is what a Fitts observation needs, not the caller's wall time."""
        with self._lk:
            if not (self.t_grab and self.t_up):
                return 0.0
            t0 = self.t_move0 or (self.t_grab + 0.12)
            return max(0.0, self.t_up - t0)

    # ---- message loop
    def start(self) -> "DotsCanvas":
        self._thread = threading.Thread(target=self._main, daemon=True)
        self._thread.start()
        self._ready.wait(5.0)
        return self

    def _wndproc(self, h: int, msg: int, w: Any, lp: Any) -> int:
        raw = 0 if lp is None else int(lp)                                   # ctypes hands 0-valued pointer args over as None
        xy = raw & 0xFFFFFFFF                                                # message coordinates live in the low 16+16 bits
        x, y = ctypes.c_short(xy & 0xFFFF).value, ctypes.c_short((xy >> 16) & 0xFFFF).value
        if msg == WM_LBUTTONDOWN or msg == WM_LBUTTONDBLCLK:
            with self._lk:
                for key, (cx, cy) in (("A", (self.a[0], self.a[1])), ("B", (self.b[0], self.b[1]))):
                    if (cx - x) ** 2 + (cy - y) ** 2 <= (DOT_R + 8) ** 2:
                        self.grab = key
                        self.t_grab, self.t_move0, self.t_up = time.time(), 0.0, 0.0
                        break
                self.pressed += 1
            _u.SetCapture(h)
            return 0
        if msg == WM_MOUSEMOVE:
            with self._lk:
                if self.grab:
                    if not self.t_move0:
                        self.t_move0 = time.time()
                    gx, gy = (self.a if self.grab == "A" else self.b)
                    gx = max(DOT_R, min(self.width - DOT_R, x))
                    gy = max(DOT_R, min(self.height - DOT_R, y))
                    if self.grab == "A":
                        self.a = [gx, gy]
                    else:
                        self.b = [gx, gy]
                    _u.InvalidateRect(h, None, True)
            return 0
        if msg == WM_LBUTTONUP:
            with self._lk:
                if self.grab:
                    self.t_up = time.time()
                self.grab = None
                self.released += 1
            _u.ReleaseCapture()
            return 0
        if msg == WM_PAINT:
            # PAINTSTRUCT on x64 is 8+8+32+4+4+20 = ~132 bytes (hwnd,hdc,rgnUpdate RECT,fErase,rcRestore,cRestore). A too-small buffer
            # is the measured access-violation source: BeginPaint wrote straight past its end and corrupted the heap (crashes reproduced
            # ~40% with this handler active, 0/6 with it off). Size it honestly and guard a failed BeginPaint.
            ps = ctypes.create_string_buffer(192)
            hdc = _u.BeginPaint(h, ps)
            if not hdc:
                return 0
            try:
                rect = wt.RECT(0, 0, self.width, self.height)
                brush = _g.CreateSolidBrush(0x00F5F5F5)
                _u.FillRect(hdc, ctypes.byref(rect), brush)
                _g.DeleteObject(brush)
                for key in ("A", "B"):
                    with self._lk:
                        cx, cy = (self.a if key == "A" else self.b)
                    col = COLORS[key][0] | (COLORS[key][1] << 8) | (COLORS[key][2] << 16)
                    pen = _g.CreatePen(0, 2, col)
                    b2 = _g.CreateSolidBrush(col)
                    _g.SelectObject(hdc, pen)
                    _g.SelectObject(hdc, b2)
                    _g.Ellipse(hdc, cx - DOT_R, cy - DOT_R, cx + DOT_R + 1, cy + DOT_R + 1)
                    _g.DeleteObject(pen)
                    _g.DeleteObject(b2)
            finally:
                _u.EndPaint(h, ps)
            return 0
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        if msg == WM_NCHITTEST:
            return HTCLIENT
        if msg == WM_DESTROY:
            _u.PostQuitMessage(0)
            return 0
        return _u.DefWindowProcW(h, msg, w, raw)

    def _main(self) -> None:
        try:
            self._build_window()
        except Exception as exc:
            self.fail_why = f"the course window crashed while starting: {type(exc).__name__}: {str(exc)[:140]}"
            self.hwnd = 0
            self._ready.set()

    def _build_window(self) -> None:
        ok, why = _ensure_class()
        if not ok:
            self.fail_why = why
            self._ready.set()
            return
        hwnd = _u.CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                                  "HojaigaDotsCanvas", "Hojaiga pointer course", WS_POPUP | WS_VISIBLE,
                                  self.x, self.y, self.width, self.height, 0, 0, _k.GetModuleHandleW(None), 0)
        err_win = ctypes.get_last_error()
        if not hwnd:
            self.fail_why = f"the course window could not be created (create err {err_win or _k.GetLastError()}, w={self.width} h={self.height})"
            self._ready.set()
            return
        self.hwnd = int(hwnd)
        _CANVASES[self.hwnd] = self
        self._ready.set()
        msg = _MSG()
        while self.alive:
            r = _u.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if r in (0, -1):
                break
            _u.TranslateMessage(ctypes.byref(msg))
            _u.DispatchMessageW(ctypes.byref(msg))
        with contextlib.suppress(Exception):
            _u.DestroyWindow(hwnd)
        _CANVASES.pop(int(hwnd), None)

    def stop(self) -> None:
        self.alive = False
        if self.hwnd and _u.IsWindow(self.hwnd):
            _u.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        if self._thread:
            self._thread.join(3.0)


class _Fx:
    """The course window belongs to the Professor: input is allowed, the window is owned."""
    allowed = True
    owned = True

    @staticmethod
    def why_not() -> str:
        return ""


def _observe_motion(learner: Any, model: Any, distance: float, width: float, seconds: float) -> None:
    try:
        if learner is not None and hasattr(learner, "observe_motion"):
            learner.observe_motion(distance, width, seconds)
        elif model is not None:
            model.observe(distance, width, seconds)
    except Exception:
        pass


def run_course(learner: Any = None, rounds: int = 3, tol_px: float = 34.0, save_evidence: bool = True, log: Any = print) -> Dict[str, Any]:
    """Drag a dot from one side of the screen to the other, `rounds` times (sides alternate, positions randomised). Every drag goes through the pointer agent's gesture compiler and route ladder,
    exactly as an application drag would; the canvas answers with facts: where the dot ended, and a picture."""
    out_dir = os.path.join(CFG.DATA_DIR, "pointer_course")
    np, Image = None, None                                                  # imported up front on the main thread, before any canvas thread exists (a lazy PIL import inside a GC while a WndProc runs crashed the process at exit - measured)
    if save_evidence:
        with contextlib.suppress(Exception):
            import numpy as np
            from PIL import Image
    motor = None
    if learner is None:
        from .ml.motor import MotorModel
        motor = MotorModel(os.path.join(CFG.DATA_DIR, "ml", "motor.json"))
    rep: Dict[str, Any] = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "rounds": [], "reached": 0, "routed": {}}
    for i in range(max(1, rounds)):
        rnd: Dict[str, Any] = {"round": i + 1}
        ay = random.randint(DOT_R + 6, 140 - DOT_R - 6)
        by = random.randint(DOT_R + 6, 140 - DOT_R - 6)
        canvas = DotsCanvas(a_pos=(70, ay), b_pos=((_u.GetSystemMetrics(0) - 40) - 70, by))
        canvas.start()
        if not canvas.hwnd:
            rep["rounds"].append({"round": i + 1, "ok": False, "why": canvas.fail_why or "the course window did not start"})
            break
        mover = "A" if i % 2 == 0 else "B"
        other = "B" if mover == "A" else "A"
        src = canvas.dot_screen(mover)
        dst_xy = canvas.dot_screen(other)
        target = (dst_xy[0] + (DOT_R * 2 + 8) * (1 if src[0] > dst_xy[0] else -1), dst_xy[1])      # put it NEXT TO the waiting dot, side by side

        def reached(canvas=canvas, mover=mover, target=target) -> bool:
            deadline = time.time() + 2.0                                                          # the canvas drains its posted queue a moment after the release
            while time.time() < deadline:
                if canvas.distance_to(mover, target) <= tol_px:
                    return True
                time.sleep(0.1)
            return canvas.distance_to(mover, target) <= tol_px

        before = PT.pixels(canvas.hwnd, (canvas.x, canvas.y, canvas.x + canvas.width, canvas.y + canvas.height))
        vp = PT.VirtualPointer(canvas.hwnd, "pointer_course", _Fx(), only=["posted"], allow_touch=False)
        t0 = time.time()
        res = vp.drag_drop(src, target, verify=reached, target_width=2 * DOT_R)   # the dot's own width: the compiler times the glide by Fitts's law on THIS target
        wall = time.time() - t0
        ended = canvas.dot_screen(mover)
        err = canvas.distance_to(mover, target)
        dist = math.hypot(target[0] - src[0], target[1] - src[1])
        travel = 0.0
        _deadline = time.time() + 0.6                                                 # the release is processed by the canvas a moment after the verify sees the dot in place: wait for its own timing
        while time.time() < _deadline:
            travel = canvas.travel_seconds()
            if travel:
                break
            time.sleep(0.05)
        if travel > 0:
            _observe_motion(learner, motor, dist, 2 * DOT_R, travel)                   # the Fitts observation is the DOT's measured movement time, never the caller's wall
        rnd.update({"ok": bool(res.ok and err <= tol_px), "mover": mover, "from": [round(s, 1) for s in src], "to": [round(t, 1) for t in target],
                    "dot_ended_at": [round(e, 1) for e in ended], "error_px": round(err, 1), "distance_px": round(dist, 1),
                    "travel_seconds": round(travel, 3), "travel_measured": travel > 0,
                    "seconds": round(wall, 2), "route": res.route, "verified": res.verified, "press_up": [canvas.pressed, canvas.released],
                    "tried": res.tried[:4]})
        vp.close() if hasattr(vp, "close") else None
        after = PT.pixels(canvas.hwnd, (canvas.x, canvas.y, canvas.x + canvas.width, canvas.y + canvas.height)) if (save_evidence and before is not None) else None
        canvas.stop()                                                        # the canvas thread is gone BEFORE any PIL/numpy work: a lazy import + GC on the main thread while a WndProc answers re-entrantly crashed the process at exit (measured)
        if save_evidence and before is not None and Image is not None:
            try:
                os.makedirs(out_dir, exist_ok=True)
                tag = os.path.join(out_dir, f"{time.strftime('%Y%m%d_%H%M%S')}_r{i + 1}")
                Image.fromarray(np.clip(before, 0, 255).astype("uint8")).save(tag + "_before.png")
                if after is not None:
                    Image.fromarray(np.clip(after, 0, 255).astype("uint8")).save(tag + "_after.png")
                    rnd["picture_changed_fraction"] = round(PT.changed(before, after), 4)   # the drag visibly MOVED something (measured, not assumed)
            except Exception as exc:
                rnd["picture_note"] = f"{type(exc).__name__}: {str(exc)[:60]}"
        rep["rounds"].append(rnd)
        rep["reached"] += 1 if rnd["ok"] else 0
        rep["routed"][res.route or "none"] = rep["routed"].get(res.route or "none", 0) + 1
        log(f"round {i + 1}: dot {mover} dragged {'REACHED' if rnd['ok'] else 'MISSED'} its place ({rnd['error_px']} px off, route '{res.route}', {rnd['seconds']}s)")
    rep["passed"] = rep["reached"] == len(rep["rounds"]) and len(rep["rounds"]) > 0
    msum = None
    try:
        if learner is not None and getattr(learner, "motor", None) is not None:
            msum = learner.motor.summary()
        elif motor is not None:
            msum = motor.summary()
    except Exception:
        pass
    if msum is not None:
        rep["motor"] = msum
        try:
            if motor is not None:
                motor.save()
            elif learner is not None and hasattr(learner, "save"):
                learner.save()
        except Exception:
            pass
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, f"{time.strftime('%Y%m%d_%H%M%S')}.json"), "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=1, ensure_ascii=False)
    except Exception:
        pass
    return rep


if __name__ == "__main__":
    import sys
    r = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    out = run_course(rounds=r, log=lambda s: print(s, flush=True))
    print(json.dumps({k: v for k, v in out.items() if k != "rounds"}, indent=1))
