"""
professor.pointer_inject -- A REAL POINTER THAT IS NOT THE PERSON'S MOUSE: synthetic pen / touch input for strokes, drags and viewport gestures.

Measured 2026-10-10: a WinUI 3 application (Paint) ignores every POSTED mouse message (drag, middle-drag, wheel, right-drag: 0 pixels changed). Such toolkits read pointer input only
from Windows' input stack. Moving the person's own mouse (SendInput) is not allowed. Windows offers a third way: a SYNTHETIC POINTER DEVICE (InjectSyntheticPointerInput, Windows 10
1809+) - its own pen or touch contact, separate from the mouse; the system cursor is not moved by touch contacts.

  PointerInjector(kind='touch'|'pen')   .stroke(points, ms_per_point)  down -> moves -> up along a path (the virtual cursor overlay draws the same path)
                                        .tap(x, y)
The contact lands on whatever window is at that SCREEN point, so the target must be visible there: callers (professor.gestures) bring the run's OWNED window on screen without
activating it, check that it is the window under every point of the path, and refuse otherwise. Never used on a window the run did not launch.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time
from typing import List, Sequence, Tuple

PT_POINTER, PT_TOUCH, PT_PEN, PT_MOUSE = 1, 2, 3, 4
POINTER_FEEDBACK_DEFAULT, POINTER_FEEDBACK_INDIRECT, POINTER_FEEDBACK_NONE = 1, 2, 3
POINTER_FLAG_NONE, POINTER_FLAG_NEW, POINTER_FLAG_INRANGE, POINTER_FLAG_INCONTACT = 0x0, 0x1, 0x2, 0x4
POINTER_FLAG_FIRSTBUTTON, POINTER_FLAG_PRIMARY, POINTER_FLAG_DOWN, POINTER_FLAG_UPDATE, POINTER_FLAG_UP = 0x10, 0x2000, 0x10000, 0x20000, 0x40000
TOUCH_MASK_CONTACTAREA, TOUCH_MASK_ORIENTATION, TOUCH_MASK_PRESSURE = 0x1, 0x2, 0x4
PEN_MASK_PRESSURE = 0x1


class POINTER_INFO(ctypes.Structure):
    _fields_ = [("pointerType", wt.DWORD), ("pointerId", wt.UINT), ("frameId", wt.UINT), ("pointerFlags", wt.DWORD), ("sourceDevice", wt.HANDLE), ("hwndTarget", wt.HWND),
                ("ptPixelLocation", wt.POINT), ("ptHimetricLocation", wt.POINT), ("ptPixelLocationRaw", wt.POINT), ("ptHimetricLocationRaw", wt.POINT), ("dwTime", wt.DWORD),
                ("historyCount", wt.UINT), ("InputData", ctypes.c_int32), ("dwKeyStates", wt.DWORD), ("PerformanceCount", ctypes.c_uint64), ("ButtonChangeType", ctypes.c_int)]


class POINTER_TOUCH_INFO(ctypes.Structure):
    _fields_ = [("pointerInfo", POINTER_INFO), ("touchFlags", wt.DWORD), ("touchMask", wt.DWORD), ("rcContact", wt.RECT), ("rcContactRaw", wt.RECT), ("orientation", wt.UINT),
                ("pressure", wt.UINT)]


class POINTER_PEN_INFO(ctypes.Structure):
    _fields_ = [("pointerInfo", POINTER_INFO), ("penFlags", wt.DWORD), ("penMask", wt.DWORD), ("pressure", wt.UINT), ("rotation", wt.UINT), ("tiltX", ctypes.c_int32), ("tiltY", ctypes.c_int32)]


class _U(ctypes.Union):
    _fields_ = [("touchInfo", POINTER_TOUCH_INFO), ("penInfo", POINTER_PEN_INFO)]


class POINTER_TYPE_INFO(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


_u = ctypes.windll.user32
_u.CreateSyntheticPointerDevice.restype = wt.HANDLE
_u.CreateSyntheticPointerDevice.argtypes = [wt.DWORD, wt.ULONG, wt.DWORD]
_u.InjectSyntheticPointerInput.argtypes = [wt.HANDLE, ctypes.POINTER(POINTER_TYPE_INFO), wt.UINT]
_u.InjectSyntheticPointerInput.restype = wt.BOOL
_u.DestroySyntheticPointerDevice.argtypes = [wt.HANDLE]


class PointerInjector:
    def __init__(self, kind: str = "touch"):
        self.kind = kind
        self.ptype = PT_TOUCH if kind == "touch" else PT_PEN
        self.dev = _u.CreateSyntheticPointerDevice(self.ptype, 1, POINTER_FEEDBACK_NONE)
        if not self.dev:
            raise OSError(f"CreateSyntheticPointerDevice failed ({ctypes.get_last_error()})")

    def close(self) -> None:
        if self.dev:
            _u.DestroySyntheticPointerDevice(self.dev)
            self.dev = None

    def __enter__(self) -> "PointerInjector":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _frame(self, x: int, y: int, flags: int) -> bool:
        info = POINTER_TYPE_INFO()
        info.type = self.ptype
        if self.ptype == PT_TOUCH:
            t = info.touchInfo
            pi = t.pointerInfo
            t.touchFlags = 0
            t.touchMask = TOUCH_MASK_CONTACTAREA | TOUCH_MASK_PRESSURE
            t.rcContact = wt.RECT(x - 2, y - 2, x + 2, y + 2)
            t.pressure = 512 if flags & POINTER_FLAG_INCONTACT else 0
        else:
            t = info.penInfo
            pi = t.pointerInfo
            t.penMask = PEN_MASK_PRESSURE
            t.pressure = 512 if flags & POINTER_FLAG_INCONTACT else 0
        pi.pointerType = self.ptype
        pi.pointerId = 0
        pi.pointerFlags = flags
        pi.ptPixelLocation = wt.POINT(int(x), int(y))
        return bool(_u.InjectSyntheticPointerInput(self.dev, ctypes.byref(info), 1))

    def frame(self, x: int, y: int, phase: str) -> bool:
        """One contact frame, for callers that pace their own gesture: phase 'down' | 'move' | 'up'."""
        down = POINTER_FLAG_DOWN | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT | POINTER_FLAG_PRIMARY | POINTER_FLAG_NEW | (POINTER_FLAG_FIRSTBUTTON if self.ptype == PT_PEN else 0)
        move = POINTER_FLAG_UPDATE | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT | POINTER_FLAG_PRIMARY | (POINTER_FLAG_FIRSTBUTTON if self.ptype == PT_PEN else 0)
        flags = {"down": down, "move": move, "up": POINTER_FLAG_UP | POINTER_FLAG_PRIMARY}[phase]
        return self._frame(int(x), int(y), flags)

    def stroke(self, points: Sequence[Tuple[float, float]], ms_per_point: float = 12.0) -> Tuple[bool, str]:
        pts = [(int(round(x)), int(round(y))) for x, y in points]
        if len(pts) < 2:
            return False, "a stroke needs two points"
        down = POINTER_FLAG_DOWN | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT | POINTER_FLAG_PRIMARY | POINTER_FLAG_NEW | (POINTER_FLAG_FIRSTBUTTON if self.ptype == PT_PEN else 0)
        move = POINTER_FLAG_UPDATE | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT | POINTER_FLAG_PRIMARY | (POINTER_FLAG_FIRSTBUTTON if self.ptype == PT_PEN else 0)
        ok = self._frame(*pts[0], down)
        for x, y in pts[1:]:
            time.sleep(ms_per_point / 1000.0)
            ok &= self._frame(x, y, move)
        time.sleep(ms_per_point / 1000.0)
        ok &= self._frame(*pts[-1], POINTER_FLAG_UP | POINTER_FLAG_PRIMARY)
        return ok, f"synthetic {self.kind} stroke, {len(pts)} points" + ("" if ok else f" (error {ctypes.get_last_error()})")

    def tap(self, x: float, y: float) -> Tuple[bool, str]:
        return self.stroke([(x, y), (x + 1, y)], 20.0)
