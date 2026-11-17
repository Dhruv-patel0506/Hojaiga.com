"""
professor.capture -- seeing the screen: monitors, DPI, screen/window capture, coordinate mapping, change detection.

Capture is READ-ONLY and focus-neutral: it never raises, restores or activates a window (feedback_invisible_scanning).
  * screen / on-screen window  -> mss BitBlt of exactly the pixels the user sees (what the Professor should talk about)
  * minimized / parked / hidden window -> PrintWindow(PW_RENDERFULLCONTENT) from the window's own surface
Everything is PHYSICAL pixels in virtual-desktop space, the same space UIA bounding rectangles and the overlay use.
A private ctypes.WinDLL is used (other modules rewrite windll argtypes; see atlas notes, measured fact 7).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import hashlib
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from .schema import Box

IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    _g32 = ctypes.WinDLL("gdi32", use_last_error=True)
    _dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
    try:
        _shcore = ctypes.WinDLL("shcore", use_last_error=True)
    except OSError:                                              # pragma: no cover
        _shcore = None
    _H = ctypes.c_void_p
    _u32.GetWindowRect.argtypes = [_H, ctypes.POINTER(wt.RECT)]
    _u32.GetWindowDC.argtypes = [_H]
    _u32.GetWindowDC.restype = _H
    _u32.ReleaseDC.argtypes = [_H, _H]
    _u32.PrintWindow.argtypes = [_H, _H, wt.UINT]
    _u32.IsIconic.argtypes = [_H]
    _u32.IsWindowVisible.argtypes = [_H]
    _u32.GetForegroundWindow.restype = _H
    _u32.GetWindowTextW.argtypes = [_H, wt.LPWSTR, ctypes.c_int]
    _u32.GetClassNameW.argtypes = [_H, wt.LPWSTR, ctypes.c_int]
    _u32.GetWindowThreadProcessId.argtypes = [_H, ctypes.POINTER(wt.DWORD)]
    _u32.GetAncestor.argtypes = [_H, wt.UINT]
    _u32.GetAncestor.restype = _H
    _u32.GetWindow.argtypes = [_H, wt.UINT]
    _u32.GetWindow.restype = _H
    _u32.GetTopWindow.argtypes = [_H]
    _u32.GetTopWindow.restype = _H
    _u32.SetWindowDisplayAffinity.argtypes = [_H, wt.DWORD]
    _u32.GetDpiForWindow.argtypes = [_H]
    _u32.GetDpiForWindow.restype = wt.UINT
    _g32.CreateCompatibleDC.argtypes = [_H]
    _g32.CreateCompatibleDC.restype = _H
    _g32.CreateCompatibleBitmap.argtypes = [_H, ctypes.c_int, ctypes.c_int]
    _g32.CreateCompatibleBitmap.restype = _H
    _g32.SelectObject.argtypes = [_H, _H]
    _g32.SelectObject.restype = _H
    _g32.DeleteObject.argtypes = [_H]
    _g32.DeleteDC.argtypes = [_H]
    _g32.GetDIBits.argtypes = [_H, _H, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]

_DPI_DONE = False


def ensure_dpi_awareness() -> bool:
    """Per-monitor-v2 DPI awareness for THIS process, once. Without it every coordinate is a logical (scaled-down) pixel and the overlay lands off target."""
    global _DPI_DONE
    if _DPI_DONE or not IS_WINDOWS:
        return True
    ok = False
    try:
        ok = bool(ctypes.WinDLL("user32").SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)))
    except Exception:
        ok = False
    if not ok:
        try:
            ok = _shcore is not None and _shcore.SetProcessDpiAwareness(2) in (0, -2147024891)       # S_OK / E_ACCESSDENIED (already set)
        except Exception:
            ok = False
    if not ok:
        try:
            ctypes.WinDLL("user32").SetProcessDPIAware()
        except Exception:
            pass
    _DPI_DONE = True
    return True


ensure_dpi_awareness()


# ------------------------------------------------------------------------------------------------------------ monitors
@dataclass
class Monitor:
    index: int
    box: Box
    primary: bool = False
    dpi: int = 96

    @property
    def scale(self) -> float:
        return self.dpi / 96.0

    def to_dict(self) -> Dict[str, Any]:
        return {"index": self.index, "box": self.box.to_list(), "primary": self.primary, "dpi": self.dpi}


def monitors() -> List[Monitor]:
    """All monitors, primary first as index 1 (matching the 'screen 2' wording a person would use), left-to-right after that."""
    out: List[Monitor] = []
    if not IS_WINDOWS:
        return out

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]

    found: List[Tuple[int, Box, bool, int]] = []
    PROC = ctypes.WINFUNCTYPE(ctypes.c_int, _H, _H, ctypes.POINTER(wt.RECT), wt.LPARAM)

    def cb(hmon, _hdc, _rect, _lp):
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if _u32.GetMonitorInfoW(_H(hmon), ctypes.byref(mi)):
            r = mi.rcMonitor
            dx, dy = ctypes.c_uint(96), ctypes.c_uint(96)
            try:
                if _shcore is not None:
                    _shcore.GetDpiForMonitor(_H(hmon), 0, ctypes.byref(dx), ctypes.byref(dy))
            except Exception:
                pass
            found.append((hmon, Box(r.left, r.top, r.right, r.bottom), bool(mi.dwFlags & 1), int(dx.value or 96)))
        return 1

    try:
        _u32.GetMonitorInfoW.argtypes = [_H, ctypes.c_void_p]
        _u32.EnumDisplayMonitors.argtypes = [_H, ctypes.c_void_p, PROC, wt.LPARAM]
        _u32.EnumDisplayMonitors(None, None, PROC(cb), 0)
    except Exception:
        pass
    found.sort(key=lambda t: (not t[2], t[1].x1, t[1].y1))
    for i, (_h, box, prim, dpi) in enumerate(found, 1):
        out.append(Monitor(i, box, prim, dpi))
    if not out:
        vs = virtual_screen()
        out.append(Monitor(1, vs, True, 96))
    return out


def virtual_screen() -> Box:
    if not IS_WINDOWS:
        return Box(0, 0, 1920, 1080)
    gm = _u32.GetSystemMetrics
    x, y, w, h = gm(76), gm(77), gm(78), gm(79)
    if w <= 0 or h <= 0:
        return Box(0, 0, gm(0), gm(1))
    return Box(x, y, x + w, y + h)


def monitor_at(x: float, y: float) -> Monitor:
    ms = monitors()
    for m in ms:
        if m.box.contains_point(x, y):
            return m
    return ms[0]


# --------------------------------------------------------------------------------------------------------------- Frame
@dataclass
class Frame:
    """A captured picture plus the facts needed to map it back to the screen."""
    image: Image.Image
    origin: Tuple[int, int] = (0, 0)          # screen position of image pixel (0,0)
    kind: str = "screen"                      # screen | window | image
    hwnd: int = 0
    monitor: int = 0
    dpi_scale: float = 1.0
    via: str = ""
    taken_at: float = field(default_factory=time.time)

    @property
    def size(self) -> Tuple[int, int]:
        return self.image.size

    def screen_box(self) -> Box:
        return Box(self.origin[0], self.origin[1], self.origin[0] + self.image.width, self.origin[1] + self.image.height)

    def to_screen(self, b: Box) -> Box:
        return b.shift(self.origin[0], self.origin[1])

    def to_image(self, b: Box) -> Box:
        return b.shift(-self.origin[0], -self.origin[1])

    def crop(self, screen_box: Box) -> Image.Image:
        """Crop by SCREEN coordinates (clipped to the picture)."""
        ib = self.to_image(screen_box).clip(self.image.width, self.image.height)
        if not ib.valid:
            return Image.new("RGB", (1, 1))
        return self.image.crop(ib.ituple())

    def hash(self) -> str:
        return frame_hash(self.image)


def frame_from_image(img: Image.Image, origin: Tuple[int, int] = (0, 0), dpi_scale: float = 1.0) -> Frame:
    return Frame(img.convert("RGB"), origin=origin, kind="image", dpi_scale=dpi_scale, via="provided")


def _mss_grab(left: int, top: int, width: int, height: int) -> Optional[Image.Image]:
    try:
        import mss
        with mss.mss() as sct:
            shot = sct.grab({"left": int(left), "top": int(top), "width": int(width), "height": int(height)})
            return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except Exception:
        return None


def grab_box(box: Box) -> Optional[Frame]:
    """The pixels of a screen rectangle (clipped to the desktop)."""
    vs = virtual_screen()
    b = box.clip(vs.x2, vs.y2, vs.x1, vs.y1)
    if not b.valid:
        return None
    img = _mss_grab(int(b.x1), int(b.y1), int(b.w), int(b.h))
    if img is None:
        return None
    m = monitor_at(b.cx, b.cy)
    return Frame(img, origin=(int(b.x1), int(b.y1)), kind="screen", monitor=m.index, dpi_scale=m.scale, via="mss")


def grab_screen(monitor_index: Optional[int] = None) -> Optional[Frame]:
    """One monitor (1 = primary) or, with None, the whole virtual desktop."""
    if monitor_index is None:
        return grab_box(virtual_screen())
    ms = monitors()
    if not (1 <= monitor_index <= len(ms)):
        return None
    return grab_box(ms[monitor_index - 1].box)


def grab_all_monitors() -> List[Frame]:
    out = []
    for m in monitors():
        f = grab_box(m.box)
        if f is not None:
            f.monitor = m.index
            out.append(f)
    return out


# ---------------------------------------------------------------------------------------------------------- windows
@dataclass
class WindowInfo:
    hwnd: int
    title: str = ""
    cls: str = ""
    pid: int = 0
    process: str = ""
    box: Box = Box(0, 0, 0, 0)
    visible: bool = False
    minimized: bool = False
    dpi_scale: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {"hwnd": self.hwnd, "title": self.title, "cls": self.cls, "pid": self.pid, "process": self.process, "box": self.box.to_list(),
                "visible": self.visible, "minimized": self.minimized, "dpi_scale": self.dpi_scale}


def _text(fn, hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    try:
        fn(_H(hwnd), buf, 512)
    except Exception:
        return ""
    return buf.value


def window_box(hwnd: int) -> Box:
    """Visible frame rectangle (DWM extended bounds exclude the invisible resize shadow), falling back to GetWindowRect."""
    if not IS_WINDOWS:
        return Box(0, 0, 0, 0)
    r = wt.RECT()
    try:
        if _dwm.DwmGetWindowAttribute(_H(hwnd), 9, ctypes.byref(r), ctypes.sizeof(r)) == 0 and r.right > r.left:
            return Box(r.left, r.top, r.right, r.bottom)
    except Exception:
        pass
    if _u32.GetWindowRect(_H(hwnd), ctypes.byref(r)):
        return Box(r.left, r.top, r.right, r.bottom)
    return Box(0, 0, 0, 0)


def process_name(pid: int) -> str:
    try:
        import psutil
        return psutil.Process(pid).name()
    except Exception:
        return ""


def window_info(hwnd: int) -> WindowInfo:
    if not IS_WINDOWS or not hwnd:
        return WindowInfo(hwnd)
    pid = wt.DWORD(0)
    _u32.GetWindowThreadProcessId(_H(hwnd), ctypes.byref(pid))
    dpi = 96
    try:
        dpi = int(_u32.GetDpiForWindow(_H(hwnd)) or 96)
    except Exception:
        pass
    return WindowInfo(hwnd=hwnd, title=_text(_u32.GetWindowTextW, hwnd), cls=_text(_u32.GetClassNameW, hwnd), pid=int(pid.value),
                      process=process_name(int(pid.value)), box=window_box(hwnd), visible=bool(_u32.IsWindowVisible(_H(hwnd))),
                      minimized=bool(_u32.IsIconic(_H(hwnd))), dpi_scale=dpi / 96.0)


def foreground_hwnd() -> int:
    if not IS_WINDOWS:
        return 0
    h = _u32.GetForegroundWindow()
    return int(h or 0)


_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland"}
_TERMINAL_PROCS = {"windowsterminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "conhost.exe", "openconsole.exe", "code.exe", "claude.exe"}


def list_top_windows(visible_only: bool = True) -> List[WindowInfo]:
    """Top-level windows in z-order (front first), skipping shell chrome, tool windows and zero-size ones."""
    out: List[WindowInfo] = []
    if not IS_WINDOWS:
        return out
    h = _u32.GetTopWindow(None)
    guard = 0
    while h and guard < 2000:
        guard += 1
        hw = int(h)
        try:
            info = window_info(hw)
            ex = _u32.GetWindowLongW(_H(hw), -20) if hasattr(_u32, "GetWindowLongW") else 0
            tool = bool(ex & 0x80)                                                    # WS_EX_TOOLWINDOW
            if (info.visible or not visible_only) and info.title and info.cls not in _SHELL_CLASSES and not tool and info.box.w > 80 and info.box.h > 60:
                out.append(info)
        except Exception:
            pass
        h = _u32.GetWindow(h, 2)                                                       # GW_HWNDNEXT
    return out


def pick_target_window(title_hint: str = "", exclude_pids: Sequence[int] = (), allow_terminals: bool = False) -> Optional[WindowInfo]:
    """The window the user is working in: title match if given, else the foreground window, else the front-most real application window.
    Terminals/editors that merely HOST this command (and our own overlay) are skipped unless allow_terminals."""
    skip = set(exclude_pids) | {os.getpid()}
    wins = list_top_windows()
    if title_hint:
        t = title_hint.lower()
        for w in wins:
            if t in w.title.lower() or t in w.process.lower():
                return w
        return None
    fg = foreground_hwnd()
    for w in wins:
        if w.hwnd == fg and w.pid not in skip and (allow_terminals or w.process.lower() not in _TERMINAL_PROCS):
            return w
    for w in wins:
        if w.pid in skip or (not allow_terminals and w.process.lower() in _TERMINAL_PROCS) or w.minimized:
            continue
        return w
    return None


def _printwindow(hwnd: int) -> Optional[Image.Image]:
    """Render a window from its own surface (works while minimized/off-screen). Every GDI handle is released in `finally`."""
    if not IS_WINDOWS:
        return None
    r = wt.RECT()
    if not _u32.GetWindowRect(_H(hwnd), ctypes.byref(r)):
        return None
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0 or w > 16000 or h > 16000:
        return None

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                    ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]

    hdc = mem = bmp = old = None
    try:
        hdc = _u32.GetWindowDC(_H(hwnd))
        if not hdc:
            return None
        mem = _g32.CreateCompatibleDC(hdc)
        bmp = _g32.CreateCompatibleBitmap(hdc, w, h)
        if not mem or not bmp:
            return None
        old = _g32.SelectObject(mem, bmp)
        if not _u32.PrintWindow(_H(hwnd), mem, 2):
            return None
        bi = BIH()
        bi.biSize, bi.biWidth, bi.biHeight, bi.biPlanes, bi.biBitCount = ctypes.sizeof(BIH), w, -h, 1, 32
        buf = (ctypes.c_ubyte * (w * h * 4))()
        if not _g32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0):
            return None
        return Image.frombuffer("RGB", (w, h), bytes(buf), "raw", "BGRX", 0, 1)
    except Exception:
        return None
    finally:
        try:
            if old:
                _g32.SelectObject(mem, old)
            if bmp:
                _g32.DeleteObject(bmp)
            if mem:
                _g32.DeleteDC(mem)
            if hdc:
                _u32.ReleaseDC(_H(hwnd), hdc)
        except Exception:
            pass


def wgc_grab(hwnd: int, timeout: float = 4.0) -> Optional[Image.Image]:
    """Windows.Graphics.Capture of ONE window (optional rung, package `windows-capture`): the compositor's own picture of the window, correct for GPU-drawn
    (OpenGL / DirectX / Electron) windows that PrintWindow paints black, and unaffected by other windows lying on top of it. Never activates anything.
    None when the package is missing, the window gives no frame (minimised windows are not composed) or the wait runs out."""
    try:
        from windows_capture import WindowsCapture
    except Exception:
        return None
    import threading
    got: Dict[str, Any] = {}
    done = threading.Event()
    try:
        cap = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=int(hwnd))
    except Exception:
        return None

    @cap.event
    def on_frame_arrived(frame, control):                       # noqa: ANN001 - callback signature fixed by the package
        try:
            buf = np.array(frame.frame_buffer[:, :, :3][:, :, ::-1])           # BGRA -> RGB, copied: the native buffer is only valid inside the callback
            got["img"] = Image.fromarray(buf)
        finally:
            done.set()
            try:
                control.stop()
            except Exception:
                pass

    @cap.event
    def on_closed():                                            # noqa: ANN202
        done.set()

    try:
        ctl = cap.start_free_threaded()
    except Exception:
        return None
    done.wait(timeout)
    try:
        ctl.stop()
    except Exception:
        pass
    return got.get("img")


def _is_blank(img: Image.Image) -> bool:
    a = np.asarray(img.convert("L").resize((64, 64)))
    return float(a.std()) < 2.0


def grab_window(hwnd: int, isolated: bool = False) -> Optional[Frame]:
    """A window's pixels. Default: what the user SEES in that window's rectangle (so pop-ups and overlapping panels are part of the lesson).
    isolated=True (or the window is minimized): the window's own surface via PrintWindow, so nothing in front of it intrudes."""
    info = window_info(hwnd)
    if info.box.w <= 0:
        return None
    if isolated or info.minimized or not info.visible or info.box.overlap_frac(virtual_screen()) < 0.5:        # parked off-screen = not on a monitor: its own surface, never a screen grab
        # Background-capture ladder (nothing here activates, raises or restores the window). The order depends on where the window is, because MEASURED:
        #   * on a real screen but covered by other windows -> Windows.Graphics.Capture first: the compositor's current picture, exact frame bounds, right for
        #     GPU-drawn windows;  PrintWindow second.
        #   * parked off-screen / hidden -> PrintWindow(PW_RENDERFULLCONTENT) FIRST: it makes the application repaint, while WGC would hand back the compositor's
        #     stale picture with every child control still black (seen on the parked fixture).  WGC is the fallback for GPU windows PrintWindow paints black.
        on_screen = info.box.overlap_frac(virtual_screen()) > 0.5 and not info.minimized
        r = wt.RECT()
        _u32.GetWindowRect(_H(hwnd), ctypes.byref(r))
        mon_dpi = monitor_at(info.box.cx, info.box.cy).dpi
        win_dpi = info.dpi_scale * 96.0

        def via_wgc():
            wg = wgc_grab(hwnd) if not info.minimized else None
            if wg is None or _is_blank(wg):
                return None
            return Frame(wg, origin=(int(info.box.x1), int(info.box.y1)), kind="window", hwnd=hwnd, dpi_scale=info.dpi_scale if info.dpi_scale > 1.0 else mon_dpi / 96.0, via="wgc")

        def via_printwindow():
            img = _printwindow(hwnd)
            if img is None or _is_blank(img):
                return None
            # A window that is NOT DPI-aware paints in logical pixels into the top-left of a physical-size bitmap (measured: the 125% display paints the UI at 80%
            # size), while accessibility rectangles and the overlay are physical. Scale the painted part back up so every later coordinate agrees.
            ratio = mon_dpi / win_dpi if win_dpi < mon_dpi - 1 else 1.0
            if ratio > 1.01:
                w, h = img.size
                img = img.crop((0, 0, int(round(w / ratio)), int(round(h / ratio)))).resize((w, h), Image.LANCZOS)
            return Frame(img, origin=(int(r.left), int(r.top)), kind="window", hwnd=hwnd, dpi_scale=(mon_dpi / 96.0 if ratio > 1.01 else info.dpi_scale),
                         via="printwindow" + (f"@x{ratio:.2f}" if ratio > 1.01 else ""))

        for fn in ((via_wgc, via_printwindow) if on_screen else (via_printwindow, via_wgc)):
            fr = fn()
            if fr is not None:
                return fr
        return None
    f = grab_box(info.box)
    if f is None:
        return None
    f.kind, f.hwnd, f.dpi_scale = "window", hwnd, info.dpi_scale
    return f


def grab_composite(hwnd: int, pops: Sequence[int]) -> Optional[Frame]:
    """The window PLUS its open pop-ups / dialogs, each rendered from its own surface (so it works for windows parked off-screen) and placed where it sits relative to the window: the picture
    a person would see. A pop-up that cannot be rendered (blank) is left out."""
    main = grab_window(hwnd, isolated=True)
    if main is None:
        return None
    if not pops:
        return main
    wb = window_info(hwnd).box
    parts: List[Tuple[Image.Image, Box]] = [(main.image, wb)]
    boxes = [wb]
    for p in pops:
        try:
            pb = window_info(p).box
            if not pb.valid or pb.w < 8 or pb.h < 8:
                continue
            im = _printwindow(p)
            if im is None or _is_blank(im):
                continue
            parts.append((im, pb))
            boxes.append(pb)
        except Exception:
            continue
    if len(parts) == 1:
        return main
    x1, y1 = min(b.x1 for b in boxes), min(b.y1 for b in boxes)
    x2, y2 = max(b.x2 for b in boxes), max(b.y2 for b in boxes)
    if (x2 - x1) > 6000 or (y2 - y1) > 6000:
        return main
    canvas = Image.new("RGB", (int(x2 - x1), int(y2 - y1)), (24, 24, 24))
    for im, b in parts:
        canvas.paste(im, (int(b.x1 - x1), int(b.y1 - y1)))
    return Frame(canvas, origin=(int(x1), int(y1)), kind="window", hwnd=hwnd, dpi_scale=main.dpi_scale, via=(main.via or "window") + f"+{len(parts) - 1}popups")


def exclude_from_capture(hwnd: int) -> bool:
    """WDA_EXCLUDEFROMCAPTURE (0x11): the overlay is shown to the user but never appears in screenshots, so the vision model never sees its own pointer."""
    if not IS_WINDOWS:
        return False
    try:
        return bool(_u32.SetWindowDisplayAffinity(_H(hwnd), 0x11))
    except Exception:
        return False


# ---------------------------------------------------------------------------------------------------------- input state
def cursor_pos() -> Tuple[int, int]:
    pt = wt.POINT()
    try:
        _u32.GetCursorPos(ctypes.byref(pt))
    except Exception:
        return (0, 0)
    return (pt.x, pt.y)


def mouse_down(button: int = 1) -> bool:
    """True while the physical mouse button is held (1 = left, 2 = right). A passive poll: nothing is injected, no hook installed."""
    try:
        return bool(_u32.GetAsyncKeyState(button) & 0x8000)
    except Exception:
        return False


def key_down(vk: int) -> bool:
    try:
        return bool(_u32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False


# -------------------------------------------------------------------------------------------------- hashing + change
def frame_hash(img: Image.Image, size: int = 16) -> str:
    """64-bit-ish difference hash of the whole picture as hex (cheap identity check between two looks)."""
    g = np.asarray(img.convert("L").resize((size + 1, size), Image.BILINEAR), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return hex(int("".join("1" if b else "0" for b in bits), 2))[2:].zfill(size * size // 4)


def hash_distance(a: str, b: str) -> int:
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except Exception:
        return 9999


def block_signature(img: Image.Image, cell: int = 32) -> np.ndarray:
    """Mean grey per cell x cell block -> a small matrix; the basis of region-level change detection."""
    g = np.asarray(img.convert("L"), dtype=np.float32)
    h, w = g.shape
    gh, gw = max(1, h // cell), max(1, w // cell)
    g = g[: gh * cell, : gw * cell]
    return g.reshape(gh, cell, gw, cell).mean(axis=(1, 3))


def changed_boxes(prev: Image.Image, cur: Image.Image, cell: int = 32, thresh: float = 6.0, pad: int = 0) -> List[Box]:
    """Rectangles (picture pixels) where `cur` differs from `prev`: block-wise mean difference > thresh, 4-connected blocks merged. Sizes must match."""
    if prev.size != cur.size:
        return [Box(0, 0, cur.width, cur.height)]
    a, b = block_signature(prev, cell), block_signature(cur, cell)
    mask = np.abs(a - b) > thresh
    if not mask.any():
        return []
    try:
        import cv2
        n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
        boxes = []
        for i in range(1, n):
            x, y, w, h = stats[i, 0], stats[i, 1], stats[i, 2], stats[i, 3]
            boxes.append(Box(x * cell - pad, y * cell - pad, (x + w) * cell + pad, (y + h) * cell + pad).clip(cur.width, cur.height))
        return boxes
    except Exception:
        ys, xs = np.nonzero(mask)
        return [Box(xs.min() * cell, ys.min() * cell, (xs.max() + 1) * cell, (ys.max() + 1) * cell).clip(cur.width, cur.height)]


def changed_fraction(prev: Image.Image, cur: Image.Image, cell: int = 32, thresh: float = 6.0) -> float:
    if prev.size != cur.size:
        return 1.0
    a, b = block_signature(prev, cell), block_signature(cur, cell)
    return float((np.abs(a - b) > thresh).mean())


def sha(data: bytes, n: int = 12) -> str:
    return hashlib.sha1(data).hexdigest()[:n]
