"""
try_app_pointer -- the Hojaiga VIRTUAL CURSOR over a real browser window.

During the on-screen web exploration the pointer you see is the Professor's overlay cursor (a click-through layer above every window: it never takes focus, never moves your real mouse, never
shows up in screenshots). For each control the explorer is about to use, this module works out WHERE that control is on the physical screen and glides the cursor there.

    where is the page content?   the browser window's content area is found through the operating system (the 'Chrome_RenderWidgetHostHWND' child of the browser window): its top-left corner in
                                 physical pixels. If that cannot be found, the window geometry reported by the page itself is used instead.
    where is the control?        content corner + (control position in the page - how far the page is scrolled + half the control's size) x the display scale (device pixel ratio).
    what does the click?         Playwright, over the browser's own debugging channel: the page receives a real click event, your physical mouse does not move.
"""
from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes as wt
import time
from typing import Any, Dict, Optional, Tuple

_u = ctypes.windll.user32


def _class(h: int) -> str:
    b = ctypes.create_unicode_buffer(256)
    _u.GetClassNameW(h, b, 256)
    return b.value


def _title(h: int) -> str:
    n = _u.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 2)
    _u.GetWindowTextW(h, b, n + 1)
    return b.value


def find_content_origin(title_hint: str = "") -> Optional[Tuple[int, int, int, int, int]]:
    """(left, top, width, height, hwnd) of the content area of the browser window whose title contains `title_hint`, in physical pixels; None if no such window."""
    tops = []
    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def on_top(h, _):
        if _u.IsWindowVisible(h) and _class(h) == "Chrome_WidgetWin_1":
            tops.append(h)
        return True
    _u.EnumWindows(EnumProc(on_top), 0)
    best = None
    for h in tops:
        t = _title(h)
        if not t or (title_hint and title_hint.lower()[:30] not in t.lower() and "chromium" not in t.lower() and "chrome for testing" not in t.lower()):
            continue
        kids = []

        def on_child(c, _):
            if _class(c) == "Chrome_RenderWidgetHostHWND":
                kids.append(c)
            return True
        _u.EnumChildWindows(h, EnumProc(on_child), 0)
        for c in kids:
            r = wt.RECT()
            _u.GetWindowRect(c, ctypes.byref(r))
            if r.right - r.left > 200 and r.bottom - r.top > 200:
                cand = (r.left, r.top, r.right - r.left, r.bottom - r.top, h)
                if best is None or (title_hint and title_hint.lower()[:30] in t.lower()):
                    best = cand
    return best


class ScreenPointer:
    def __init__(self) -> None:
        self.ov: Any = None
        self.ok = False
        self.err = ""
        self.last_origin: Optional[Tuple[int, int]] = None
        self.method = ""

    def start(self) -> bool:
        with contextlib.suppress(Exception):
            ctypes.windll.shcore.SetProcessDpiAwareness(2)                       # physical pixels, like the overlay
        try:
            from core_organs.professor.overlay import Overlay
            self.ov = Overlay()
            self.ok = bool(self.ov.start())
            self.err = "" if self.ok else str(self.ov.error)
        except Exception as e:
            self.err = f"{type(e).__name__}: {str(e)[:100]}"
        return self.ok

    def stop(self) -> None:
        with contextlib.suppress(Exception):
            if self.ov is not None:
                self.ov.release_cursor()
                self.ov.stop()

    def origin(self, page: Any) -> Optional[Tuple[float, float, float]]:
        """(content left, content top, scale) in physical pixels."""
        info = page.evaluate("() => [scrollX, scrollY, devicePixelRatio, screenX, screenY, outerWidth - innerWidth, outerHeight - innerHeight, innerWidth]")
        sx, sy, dpr, wx, wy, dw, dh, iw = info
        found = None
        with contextlib.suppress(Exception):
            found = find_content_origin(page.title())
        if found:
            # the page's devicePixelRatio is what the BROWSER believes (an emulated viewport pins it to 1); the pixels on the screen are what the operating system draws: the content area's real
            # width in physical pixels divided by the page's width in CSS pixels is the scale that matters for where things are on screen
            self.method = "window"
            return float(found[0]), float(found[1]), float(found[2]) / max(1.0, float(iw))
        self.method = "page geometry"                                           # the window's own report: left border ~ half the width difference, top = what is left of the height difference
        os_scale = 1.0
        with contextlib.suppress(Exception):
            os_scale = _u.GetDpiForSystem() / 96.0
        border = max(0.0, dw / 2.0)
        return (wx + border) * os_scale, (wy + max(0.0, dh - border)) * os_scale, os_scale

    def move(self, page: Any, c: Dict[str, Any], dwell: float = 0.05) -> bool:
        if not self.ok:
            return False
        try:
            sx, sy = page.evaluate("() => [scrollX, scrollY]")
            ox, oy, dpr = self.origin(page)
            x = ox + (c["x"] - sx + c["w"] / 2.0) * dpr
            y = oy + (c["y"] - sy + c["h"] / 2.0) * dpr
            self.last_origin = (int(ox), int(oy))
            dur = self.ov.glide([(x, y)])
            time.sleep(min(float(dur), 1.4) + dwell)
            return True
        except Exception as e:
            self.err = f"{type(e).__name__}: {str(e)[:100]}"
            return False
