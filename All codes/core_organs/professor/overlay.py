"""
professor.overlay -- the transparent layer above every window where the Professor draws: the flying pointer, the pulsing outline, the speech bubble.

Properties (the contract that keeps it harmless):
  * CLICK-THROUGH  WS_EX_TRANSPARENT: every mouse event goes to the window underneath, the learner keeps working normally
  * NO FOCUS       WS_EX_NOACTIVATE + SW_SHOWNOACTIVATE: showing, moving or updating never takes the foreground (feedback_invisible_scanning)
  * NOT CAPTURED   SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE): screenshots taken for the vision model never contain the overlay itself
  * PER-PIXEL ALPHA  UpdateLayeredWindow with premultiplied BGRA: soft glows and anti-aliased edges, no colour-key fringes
  * CHEAP          one small layered window per actor (pointer, outline, bubble), each only as large as its sprite, instead of one 4K window; sprites are
                   pre-rendered, animation is moving/fading windows (position + constant alpha), 60 fps for the pointer, 30 fps for pulses
Everything the overlay shows is also expressible as plain data (`RecordingOverlay`, `overlay_render.compose_preview`), which is how it is tested without
putting a pixel on the user's screen.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import math
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from . import overlay_render as R
from . import pointing
from .capture import IS_WINDOWS, cursor_pos, exclude_from_capture, monitor_at, virtual_screen
from .schema import Box

if IS_WINDOWS:
    _u = ctypes.WinDLL("user32", use_last_error=True)
    _g = ctypes.WinDLL("gdi32", use_last_error=True)
    _k = ctypes.WinDLL("kernel32", use_last_error=True)
    _H = ctypes.c_void_p
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, _H, wt.UINT, wt.WPARAM, wt.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", _H),
                    ("hIcon", _H), ("hCursor", _H), ("hbrBackground", _H), ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                    ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte), ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

    class MSG(ctypes.Structure):
        _fields_ = [("hwnd", _H), ("message", wt.UINT), ("wParam", wt.WPARAM), ("lParam", wt.LPARAM), ("time", wt.DWORD), ("pt", wt.POINT)]

    _u.DefWindowProcW.argtypes = [_H, wt.UINT, wt.WPARAM, wt.LPARAM]
    _u.DefWindowProcW.restype = LRESULT
    _u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    _u.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, _H, _H, _H, _H]
    _u.CreateWindowExW.restype = _H
    _u.ShowWindow.argtypes = [_H, ctypes.c_int]
    _u.DestroyWindow.argtypes = [_H]
    _u.GetDC.argtypes = [_H]
    _u.GetDC.restype = _H
    _u.ReleaseDC.argtypes = [_H, _H]
    _u.SetWindowPos.argtypes = [_H, _H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
    _u.UpdateLayeredWindow.argtypes = [_H, _H, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE), _H, ctypes.POINTER(wt.POINT), wt.COLORREF,
                                       ctypes.POINTER(BLENDFUNCTION), wt.DWORD]
    _u.PeekMessageW.argtypes = [ctypes.POINTER(MSG), _H, wt.UINT, wt.UINT, wt.UINT]
    _u.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    _u.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    _g.CreateCompatibleDC.argtypes = [_H]
    _g.CreateCompatibleDC.restype = _H
    _g.CreateDIBSection.argtypes = [_H, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), _H, wt.DWORD]
    _g.CreateDIBSection.restype = _H
    _g.SelectObject.argtypes = [_H, _H]
    _g.SelectObject.restype = _H
    _g.DeleteObject.argtypes = [_H]
    _g.DeleteDC.argtypes = [_H]
    _k.GetModuleHandleW.argtypes = [wt.LPCWSTR]
    _k.GetModuleHandleW.restype = _H

_EX = 0x00080000 | 0x00000020 | 0x00000008 | 0x08000000 | 0x00000080      # LAYERED | TRANSPARENT | TOPMOST | NOACTIVATE | TOOLWINDOW
_WS_POPUP = 0x80000000
_HWND_TOPMOST = ctypes.c_void_p(-1) if IS_WINDOWS else None


# ===================================================================================================== layered window
class LayeredWindow:
    """One click-through, no-activate, per-pixel-alpha top-level window that can show a sprite anywhere on the desktop."""
    _CLASS = "HojaigaProfessorOverlay"
    _registered = False
    _wndproc = None

    @classmethod
    def register(cls) -> None:
        if cls._registered:
            return

        def proc(hwnd, msg, wparam, lparam):
            return _u.DefWindowProcW(hwnd, msg, wparam, lparam)

        cls._wndproc = WNDPROC(proc)
        wc = WNDCLASSW()
        wc.lpfnWndProc = cls._wndproc
        wc.hInstance = _k.GetModuleHandleW(None)
        wc.lpszClassName = cls._CLASS
        _u.RegisterClassW(ctypes.byref(wc))
        cls._registered = True

    def __init__(self) -> None:
        self.register()
        self.hwnd = _u.CreateWindowExW(_EX, self._CLASS, "Hojaiga Professor", _WS_POPUP, 0, 0, 1, 1, None, None, _k.GetModuleHandleW(None), None)
        if not self.hwnd:
            raise OSError("CreateWindowExW failed")
        exclude_from_capture(int(self.hwnd))
        self.memdc: Optional[int] = None
        self.hbm: Optional[int] = None
        self.old: Optional[int] = None
        self.bits = ctypes.c_void_p()
        self.size = (0, 0)
        self.visible = False
        self.pos = (0, 0)

    def _alloc(self, w: int, h: int) -> None:
        self._free()
        screen = _u.GetDC(None)
        try:
            self.memdc = _g.CreateCompatibleDC(screen)
            bmi = BITMAPINFOHEADER()
            bmi.biSize, bmi.biWidth, bmi.biHeight, bmi.biPlanes, bmi.biBitCount, bmi.biCompression = ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0
            self.hbm = _g.CreateDIBSection(screen, ctypes.byref(bmi), 0, ctypes.byref(self.bits), None, 0)
            self.old = _g.SelectObject(self.memdc, self.hbm)
        finally:
            _u.ReleaseDC(None, screen)
        self.size = (w, h)

    def _free(self) -> None:
        try:
            if self.memdc and self.old:
                _g.SelectObject(self.memdc, self.old)
            if self.hbm:
                _g.DeleteObject(self.hbm)
            if self.memdc:
                _g.DeleteDC(self.memdc)
        except Exception:
            pass
        self.memdc = self.hbm = self.old = None
        self.size = (0, 0)

    def set_bitmap(self, rgba: np.ndarray) -> None:
        """rgba: (h, w, 4) uint8, straight alpha. Converts to premultiplied BGRA inside the DIB."""
        h, w = rgba.shape[:2]
        if (w, h) != self.size or not self.hbm:
            self._alloc(w, h)
        a = rgba[..., 3:4].astype(np.uint16)
        pm = (rgba[..., :3].astype(np.uint16) * a // 255).astype(np.uint8)
        out = np.concatenate([pm[..., ::-1], rgba[..., 3:4]], axis=2)
        out = np.ascontiguousarray(out)
        ctypes.memmove(self.bits, out.ctypes.data, w * h * 4)

    def show(self, x: int, y: int, alpha: int = 255) -> None:
        if not self.hbm:
            return
        pt = wt.POINT(int(x), int(y))
        sz = wt.SIZE(self.size[0], self.size[1])
        src = wt.POINT(0, 0)
        bf = BLENDFUNCTION(0, 0, max(0, min(255, int(alpha))), 1)
        _u.UpdateLayeredWindow(self.hwnd, None, ctypes.byref(pt), ctypes.byref(sz), self.memdc, ctypes.byref(src), 0, ctypes.byref(bf), 2)
        self.pos = (int(x), int(y))
        if not self.visible:
            _u.ShowWindow(self.hwnd, 4)                      # SW_SHOWNOACTIVATE
            self.visible = True

    def hide(self) -> None:
        if self.visible:
            _u.ShowWindow(self.hwnd, 0)
            self.visible = False

    def raise_topmost(self) -> None:
        _u.SetWindowPos(self.hwnd, _HWND_TOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)         # NOSIZE | NOMOVE | NOACTIVATE

    def destroy(self) -> None:
        try:
            _u.DestroyWindow(self.hwnd)
        except Exception:
            pass
        self._free()


def _np(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGBA"))


# ===================================================================================================== actors
class Actor:
    def __init__(self) -> None:
        self.win: Optional[LayeredWindow] = None
        self.born = time.perf_counter()
        self.dying: Optional[float] = None
        self.fade_in = 0.22
        self.fade_out = 0.25

    def alpha(self, now: float) -> float:
        a = min(1.0, (now - self.born) / self.fade_in) if self.fade_in > 0 else 1.0
        if self.dying is not None:
            a = min(a, max(0.0, 1.0 - (now - self.dying) / self.fade_out))
        return a

    def kill(self, now: float) -> None:
        if self.dying is None:
            self.dying = now

    def alive(self, now: float) -> bool:
        return self.dying is None or now - self.dying < self.fade_out

    def settled(self, now: float) -> bool:
        return now - self.born >= self.fade_in

    def draw(self, now: float) -> None:                      # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    def destroy(self) -> None:
        if self.win is not None:
            self.win.destroy()
            self.win = None

    def _win(self) -> LayeredWindow:
        if self.win is None:
            self.win = LayeredWindow()
        return self.win


class HighlightActor(Actor):
    def __init__(self, box: Box, ripple: bool = False) -> None:
        super().__init__()
        self.box = box
        w, h = max(8, int(box.w)), max(8, int(box.h))
        self.frames: List[np.ndarray] = []
        self.off = (0, 0)
        for p in (0.0, 0.25, 0.5, 0.75, 1.0):
            img, self.off = R.render_highlight(w, h, p, 1.0)
            self.frames.append(_np(img))
        self.ripple = ripple
        self._last = -1

    def draw(self, now: float) -> None:
        ph = (now - self.born) * 1.15
        k = abs((ph % 2.0) - 1.0)                                            # ping-pong 0..1
        idx = int(round(k * (len(self.frames) - 1)))
        win = self._win()
        if idx != self._last or not win.visible:
            win.set_bitmap(self.frames[idx])
            self._last = idx
        win.show(int(self.box.x1 + self.off[0]), int(self.box.y1 + self.off[1]), int(255 * self.alpha(now)))


class CircleActor(HighlightActor):
    def __init__(self, x: float, y: float) -> None:
        Actor.__init__(self)
        self.box = Box(x, y, x, y)
        self.frames = []
        for p in (0.0, 0.5, 1.0):
            img, self.off = R.render_circle(22, p)
            self.frames.append(_np(img))
        self._last = -1
        self.ripple = False


class BubbleActor(Actor):
    def __init__(self, text: str, target: Box, step: Optional[int], screen: Box, hotkey: str = "") -> None:
        super().__init__()
        img, tip = R.render_bubble(text, step, 340, "up", hotkey=hotkey)
        x, y, side = R.place_bubble(target, img.size, tip, screen)
        img, tip = R.render_bubble(text, step, 340, side, tail_x=(target.cx - x) if side in ("up", "down") else None, hotkey=hotkey)
        x, y, _s = R.place_bubble(target, img.size, tip, screen)
        self.bitmap = _np(img)
        self.xy = (x, y)

    def draw(self, now: float) -> None:
        win = self._win()
        if not win.hbm:
            win.set_bitmap(self.bitmap)
        win.show(self.xy[0], self.xy[1], int(255 * self.alpha(now)))


class ArrowActor(Actor):
    def __init__(self, p0: Tuple[float, float], p1: Tuple[float, float]) -> None:
        super().__init__()
        img, self.off = R.render_arrow(p0, p1)
        self.bitmap = _np(img)

    def draw(self, now: float) -> None:
        win = self._win()
        if not win.hbm:
            win.set_bitmap(self.bitmap)
        win.show(self.off[0], self.off[1], int(255 * self.alpha(now)))


class SpotlightActor(Actor):
    def __init__(self, hole: Box) -> None:
        super().__init__()
        m = monitor_at(hole.cx, hole.cy).box
        self.origin = (int(m.x1), int(m.y1))
        self.bitmap = _np(R.render_spotlight((int(m.w), int(m.h)), hole.shift(-m.x1, -m.y1)))
        self.fade_in = 0.35

    def draw(self, now: float) -> None:
        win = self._win()
        if not win.hbm:
            win.set_bitmap(self.bitmap)
        win.show(self.origin[0], self.origin[1], int(255 * self.alpha(now)))


class CursorActor(Actor):
    """The blue pointer. Follows the physical mouse until told to fly; flies along a Bezier arc; spins while the Professor is thinking."""

    def __init__(self, start: Tuple[float, float]) -> None:
        super().__init__()
        self.fade_in = 0.2
        self.sprites: Dict[Any, Tuple[np.ndarray, Tuple[int, int]]] = {}
        for sc in (1.0, 1.15, 1.3):
            img, off = R.render_cursor(sc, 0.0, 1.0)
            self.sprites[sc] = (_np(img), off)
        self.spin: List[Tuple[np.ndarray, Tuple[int, int]]] = []
        for ang in range(0, 360, 30):
            img, off = R.render_cursor(1.0, float(ang), 0.8)
            self.spin.append((_np(img), off))
        self.pos = start
        self.flight: Optional[Tuple[Tuple[float, float], Tuple[float, float], float, float]] = None
        self.thinking = False
        self.landed_at: Optional[float] = None
        self.hold_until = 0.0
        self.route: Optional[Tuple[Any, float]] = None             # a stitched multi-target trajectory being played: (pointing.Trajectory, start time)

    def fly_route(self, traj: Any) -> None:
        self.route = (traj, time.perf_counter())
        self.flight = None
        self.landed_at = None
        self.thinking = False

    def fly_to(self, x: float, y: float) -> None:
        now = time.perf_counter()
        dur = pointing.flight_seconds(self.pos, (x, y))
        self.flight = (self.pos, (x, y), now, dur)
        self.landed_at = None
        self.thinking = False

    def flying(self) -> bool:
        return self.flight is not None or self.route is not None

    def draw(self, now: float) -> None:
        scale_idx = 1.0
        if self.route is not None:
            traj, rt0 = self.route
            rt = now - rt0
            if rt >= traj.duration:
                self.pos = traj.points[-1]
                self.route = None
                self.landed_at = now
            else:
                self.pos = traj.at(rt)
                vx, vy = traj.velocity(rt)
                scale_idx = 1.3 if (vx * vx + vy * vy) ** 0.5 > 900 else (1.15 if (vx * vx + vy * vy) ** 0.5 > 400 else 1.0)
        elif self.flight is not None:
            p0, p1, t0, dur = self.flight
            t = (now - t0) / dur
            if t >= 1.0:
                self.pos = p1
                self.flight = None
                self.landed_at = now
            else:
                self.pos = pointing.bezier_arc(p0, p1, pointing.ease_in_out(t))
                mid = math.sin(math.pi * t)
                scale_idx = 1.3 if mid > 0.75 else (1.15 if mid > 0.35 else 1.0)
        x, y = self.pos
        if self.landed_at is not None and self.flight is None and not self.thinking:
            y += 2.0 * math.sin((now - self.landed_at) * 3.2)                  # gentle idle bob on the target
        if self.thinking:
            idx = int(((now - self.born) * 540.0) % 360) // 30
            bmp, off = self.spin[idx % len(self.spin)]
        else:
            bmp, off = self.sprites[scale_idx]
        win = self._win()
        key = (id(bmp))
        if getattr(win, "_key", None) != key:
            win.set_bitmap(bmp)
            win._key = key                                                      # type: ignore[attr-defined]
        win.show(int(x + off[0]), int(y + off[1]), int(255 * self.alpha(now)))


# ===================================================================================================== the overlay
class Overlay:
    """Thread-safe façade. Every method returns immediately; drawing happens on the overlay thread."""
    kind = "layered-window"

    def __init__(self) -> None:
        self._q: "queue.Queue[Tuple[str, tuple]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self.error = ""
        self.actors: List[Actor] = []
        self.cursor: Optional[CursorActor] = None
        self._idle = threading.Event()
        self._idle.set()

    # ---- lifecycle
    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        if not IS_WINDOWS:
            self.error = "layered windows need Windows"
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="professor-overlay", daemon=True)
        self._thread.start()
        self._ready.wait(3.0)
        return not self.error

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(2.0)

    # ---- public drawing API
    def point(self, box: Box, label: str = "", step: Optional[int] = None, action: str = "look", say_bubble: bool = True, bubble_text: str = "",
              spotlight: bool = False, fly: bool = True, hotkey: str = "") -> None:
        self._idle.clear()
        self._q.put(("point", (box, label, step, action, say_bubble, bubble_text or label, spotlight, fly, hotkey)))

    def point_xy(self, x: float, y: float, label: str = "") -> None:
        self._idle.clear()
        self._q.put(("circle", (x, y, label)))

    def glide(self, points: Sequence[Tuple[float, float]], widths: Optional[Sequence[float]] = None) -> float:
        """Move the (virtual, overlay-only) pointer through several targets as ONE continuous Fitts's-law trajectory. The real mouse is never touched. Returns the planned duration (s)."""
        start = self.cursor.pos if self.cursor is not None else cursor_pos()
        traj = pointing.stitch([start] + [tuple(p) for p in points], [0.0] + list(widths or []))
        self._idle.clear()
        self._q.put(("glide", ([tuple(p) for p in points], list(widths or []))))
        return traj.duration

    def arrow(self, p0: Tuple[float, float], p1: Tuple[float, float]) -> None:
        self._q.put(("arrow", (p0, p1)))

    def thinking(self, on: bool = True) -> None:
        self._q.put(("thinking", (on,)))

    def clear(self) -> None:
        self._q.put(("clear", ()))

    def release_cursor(self) -> None:
        self._q.put(("release", ()))

    def wait_idle(self, timeout: float = 5.0) -> bool:
        return self._idle.wait(timeout)

    # ---- thread
    def _screen_for(self, box: Box) -> Box:
        try:
            return monitor_at(box.cx, box.cy).box
        except Exception:
            return virtual_screen()

    def _handle(self, cmd: str, a: tuple, now: float) -> None:
        if cmd == "point":
            box, label, step, action, say_bubble, btxt, spot, fly, hotkey = a
            for ac in self.actors:
                if not isinstance(ac, CursorActor):
                    ac.kill(now)
            if spot:
                self.actors.append(SpotlightActor(box))
            self.actors.append(HighlightActor(box, ripple=action in ("click", "double_click")))
            if say_bubble and (btxt or hotkey):
                self.actors.append(BubbleActor(btxt, box, step, self._screen_for(box), hotkey))
            if self.cursor is None:
                self.cursor = CursorActor(cursor_pos())
                self.actors.append(self.cursor)
            x, y = pointing.landing_point(box, action)
            if fly:
                self.cursor.fly_to(x, y)
            else:
                self.cursor.pos = (x, y)
        elif cmd == "glide":
            pts, ws = a
            if self.cursor is None:
                self.cursor = CursorActor(cursor_pos())
                self.actors.append(self.cursor)
            self.cursor.fly_route(pointing.stitch([self.cursor.pos] + pts, [0.0] + ws))
        elif cmd == "circle":
            x, y, label = a
            for ac in self.actors:
                if not isinstance(ac, CursorActor):
                    ac.kill(now)
            self.actors.append(CircleActor(x, y))
            if self.cursor is None:
                self.cursor = CursorActor(cursor_pos())
                self.actors.append(self.cursor)
            self.cursor.fly_to(x, y)
        elif cmd == "arrow":
            self.actors.append(ArrowActor(*a))
        elif cmd == "thinking":
            if self.cursor is None and a[0]:
                self.cursor = CursorActor(cursor_pos())
                self.actors.append(self.cursor)
            if self.cursor is not None:
                self.cursor.thinking = bool(a[0])
        elif cmd == "clear":
            for ac in self.actors:
                ac.kill(now)
            self.cursor = None
        elif cmd == "release":
            if self.cursor is not None:
                self.cursor.kill(now)
                self.cursor = None

    def _run(self) -> None:
        try:
            LayeredWindow.register()
            self._ready.set()
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self._ready.set()
            return
        msg = MSG()
        last_top = 0.0
        while not self._stop.is_set():
            t0 = time.perf_counter()
            try:
                while True:
                    cmd, a = self._q.get_nowait()
                    self._handle(cmd, a, t0)
            except queue.Empty:
                pass
            except Exception as exc:
                self.error = f"command failed: {type(exc).__name__}: {exc}"
            keep: List[Actor] = []
            for ac in self.actors:
                if not ac.alive(t0):
                    ac.destroy()
                    continue
                try:
                    ac.draw(t0)
                except Exception as exc:
                    self.error = f"draw failed: {type(exc).__name__}: {exc}"
                keep.append(ac)
            self.actors = keep
            if t0 - last_top > 1.5:
                for ac in self.actors:
                    if ac.win is not None:
                        ac.win.raise_topmost()
                last_top = t0
            while _u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                _u.TranslateMessage(ctypes.byref(msg))
                _u.DispatchMessageW(ctypes.byref(msg))
            busy = any((isinstance(ac, CursorActor) and (ac.flying() or ac.thinking)) or not ac.settled(t0) for ac in self.actors)
            if not busy and self._q.empty():
                self._idle.set()
            dt = time.perf_counter() - t0
            time.sleep(max(0.0, (1 / 60.0 if self.actors else 0.05) - dt))
        for ac in self.actors:
            ac.destroy()
        self.actors = []


# ===================================================================================================== headless twin
class RecordingOverlay:
    """Same API, draws nothing. Keeps the steady-state scene as plain commands (for tests, dry runs, previews)."""
    kind = "recording"

    def __init__(self, reason: str = "") -> None:
        self.reason = reason
        self.error = reason
        self.log: List[Tuple[str, Dict[str, Any]]] = []
        self.scene: List[Dict[str, Any]] = []
        self._thinking = False

    def start(self) -> bool:
        return True

    def stop(self) -> None:
        pass

    def point(self, box: Box, label: str = "", step: Optional[int] = None, action: str = "look", say_bubble: bool = True, bubble_text: str = "",
              spotlight: bool = False, fly: bool = True, hotkey: str = "") -> None:
        self.log.append(("point", {"box": box.to_list(), "label": label, "step": step, "action": action, "bubble": bubble_text or label, "hotkey": hotkey, "spotlight": spotlight}))
        self.scene = []
        if spotlight:
            self.scene.append({"type": "spotlight", "box": box.to_list()})
        self.scene.append({"type": "highlight", "box": box.to_list(), "pulse": 0.4})
        if say_bubble and (bubble_text or label or hotkey):
            self.scene.append({"type": "bubble", "text": bubble_text or label, "step": step, "box": box.to_list(), "hotkey": hotkey})
        x, y = pointing.landing_point(box, action)
        self.scene.append({"type": "cursor", "x": x, "y": y})

    def glide(self, points: Sequence[Tuple[float, float]], widths: Optional[Sequence[float]] = None) -> float:
        start = self._pos if getattr(self, "_pos", None) else (0.0, 0.0)
        traj = pointing.stitch([start] + [tuple(p) for p in points], [0.0] + list(widths or []))
        self.log.append(("glide", {"points": [list(p) for p in points], "widths": list(widths or []), "seconds": round(traj.duration, 3), "arrivals": [round(a, 3) for a in traj.arrival[1:]]}))
        if points:
            self._pos = tuple(points[-1])
            self.scene = [{"type": "cursor", "x": points[-1][0], "y": points[-1][1]}]
        return traj.duration

    def point_xy(self, x: float, y: float, label: str = "") -> None:
        self.log.append(("point_xy", {"x": x, "y": y, "label": label}))
        self.scene = [{"type": "circle", "x": x, "y": y, "pulse": 0.4}, {"type": "cursor", "x": x, "y": y}]

    def arrow(self, p0: Tuple[float, float], p1: Tuple[float, float]) -> None:
        self.log.append(("arrow", {"from": list(p0), "to": list(p1)}))
        self.scene.append({"type": "arrow", "from": list(p0), "to": list(p1)})

    def thinking(self, on: bool = True) -> None:
        self._thinking = on
        self.log.append(("thinking", {"on": on}))

    def clear(self) -> None:
        self.log.append(("clear", {}))
        self.scene = []

    def release_cursor(self) -> None:
        self.log.append(("release", {}))

    def wait_idle(self, timeout: float = 5.0) -> bool:
        return True

    def preview(self, background: Image.Image, origin: Tuple[int, int] = (0, 0)) -> Image.Image:
        return R.compose_preview(background, self.scene, origin)


def make_overlay(kind: str = "auto") -> Any:
    """'auto' = the real layered overlay when this machine can create one, else the recording twin (its `.error` says why)."""
    if kind == "recording":
        return RecordingOverlay("requested")
    ov = Overlay()
    if kind in ("auto", "real") and ov.start():
        return ov
    if kind == "real":
        return ov
    return RecordingOverlay(ov.error or "overlay unavailable")
