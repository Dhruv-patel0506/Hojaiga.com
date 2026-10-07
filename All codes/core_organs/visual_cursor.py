"""
visual_cursor.py — Clicky-Style Visual Cursor Engine for Hojaiga Automation.

Features:
- Independent Virtual Operation: 100% decoupled from physical mouse (NEVER steals OS cursor).
- Blue Arrow Design: Single bright blue arrow-pointer cursor (white outline).
- Circular Motion Animation: Rotates in circular motion when buffering/processing.
- Single Color: Bright blue (0x00E8731A) for high visibility.
- Magnetic Rest State: Sticks to the physical mouse when idle, detaches to act, re-attaches when idle again.
- Dynamic State Badges: Real-time floating status indicators (⚡ ACTIVE, 🚀 MOVING, ✏️ DRAWING, 🎯 CLICK).
- Bezier-Arc Flight: Natural curved trajectory with luminous trailing dots.
- Expanding Click Ripples: Radiant wave ripples on interactions.
- Background Window Message Dispatch: Direct PostMessageW(hwnd, WM_LBUTTONDOWN/MOVE/UP) via ScreenToClient.
- Layered click-through, non-activating topmost window (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE).
"""

import os
import sys
import threading
import time
import math
import logging
from typing import Optional, Tuple, List, Dict, Any

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

logger = logging.getLogger("hojaiga.visual_cursor")

try:
    import ctypes
    import ctypes.wintypes
    from ctypes import wintypes
    _HAS_CTYPES = True
except ImportError:
    _HAS_CTYPES = False

try:
    import win32gui
    import win32con
    import win32api
    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False

if _HAS_CTYPES:
    try:
        ctypes.windll.user32.DisableProcessWindowsGhosting()
    except Exception:
        pass

    class _WNDCLASSEX(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint),
            ("style", ctypes.c_uint),
            ("lpfnWndProc", ctypes.c_void_p),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", ctypes.c_void_p),
            ("hIcon", ctypes.c_void_p),
            ("hCursor", ctypes.c_void_p),
            ("hbrBackground", ctypes.c_void_p),
            ("lpszMenuName", ctypes.c_wchar_p),
            ("lpszClassName", ctypes.c_wchar_p),
            ("hIconSm", ctypes.c_void_p),
        ]
    _WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_void_p, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)

    class _PAINTSTRUCT(ctypes.Structure):
        _fields_ = [
            ("hdc", wintypes.HWND),
            ("fErase", wintypes.BOOL),
            ("rcPaint", wintypes.RECT),
            ("fRestore", wintypes.BOOL),
            ("fIncUpdate", wintypes.BOOL),
            ("rgbReserved", ctypes.c_byte * 32),
        ]

    class _BLENDFUNCTION(ctypes.Structure):
        _fields_ = [
            ("BlendOp", ctypes.c_byte),
            ("BlendFlags", ctypes.c_byte),
            ("SourceConstantAlpha", ctypes.c_byte),
            ("AlphaFormat", ctypes.c_byte),
        ]

    def _ensure_interactive_desktop():
        """Ensures calling thread is attached to the active interactive input desktop."""
        try:
            from core_organs import headless_input as _hin
            if _hin.on_input_desktop():
                return  # already on the interactive desktop: do not touch window station/desktop
            user32 = ctypes.windll.user32
            hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x0002 | 0x0100 | 0x0200)
            if hwinsta:
                user32.SetProcessWindowStation(hwinsta)
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
            if not hdesk:
                hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception:
            pass

    _ensure_interactive_desktop()

    try:
        ctypes.windll.gdi32.SelectObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        ctypes.windll.gdi32.SelectObject.restype = wintypes.HANDLE
        ctypes.windll.gdi32.CreateCompatibleDC.argtypes = [wintypes.HANDLE]
        ctypes.windll.gdi32.CreateCompatibleDC.restype = wintypes.HANDLE
        ctypes.windll.gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_int]
        ctypes.windll.gdi32.CreateCompatibleBitmap.restype = wintypes.HANDLE
        ctypes.windll.gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
        ctypes.windll.gdi32.DeleteObject.restype = wintypes.BOOL
        ctypes.windll.gdi32.DeleteDC.argtypes = [wintypes.HANDLE]
        ctypes.windll.gdi32.DeleteDC.restype = wintypes.BOOL
        ctypes.windll.gdi32.PatBlt.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        ctypes.windll.gdi32.Ellipse.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        ctypes.windll.gdi32.Polygon.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_int]
        ctypes.windll.gdi32.Polygon.restype = wintypes.BOOL

        # Critical user32 64-bit handle signatures (prevents OverflowError on ReleaseDC and handles)
        ctypes.windll.user32.GetDC.argtypes = [wintypes.HWND]
        ctypes.windll.user32.GetDC.restype = wintypes.HDC
        ctypes.windll.user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        ctypes.windll.user32.ReleaseDC.restype = ctypes.c_int
        ctypes.windll.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        ctypes.windll.user32.ShowWindow.restype = wintypes.BOOL
        ctypes.windll.user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
        ctypes.windll.user32.ShowWindowAsync.restype = wintypes.BOOL
        ctypes.windll.user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        ctypes.windll.user32.SetWindowPos.restype = wintypes.BOOL
        ctypes.windll.user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        ctypes.windll.user32.SetForegroundWindow.restype = wintypes.BOOL
        ctypes.windll.user32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
        ctypes.windll.user32.PostMessageW.restype = wintypes.BOOL
        ctypes.windll.user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.c_void_p]
        ctypes.windll.user32.ScreenToClient.restype = wintypes.BOOL
        ctypes.windll.user32.GetCursorPos.argtypes = [ctypes.c_void_p]
        ctypes.windll.user32.GetCursorPos.restype = wintypes.BOOL

        # 64-bit handle prototypes for the remaining GDI calls used by _render_frame.
        # Without these ctypes treats handles as C int and raises OverflowError, so the
        # overlay silently never painted a single frame.
        ctypes.windll.gdi32.CreateDIBSection.argtypes = [
            wintypes.HDC, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p,
            wintypes.HANDLE, wintypes.DWORD]
        ctypes.windll.gdi32.CreateDIBSection.restype = wintypes.HANDLE
        ctypes.windll.gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
        ctypes.windll.gdi32.CreateSolidBrush.restype = wintypes.HANDLE
        ctypes.windll.gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.COLORREF]
        ctypes.windll.gdi32.CreatePen.restype = wintypes.HANDLE
        ctypes.windll.user32.CreateWindowExW.restype = wintypes.HWND
        ctypes.windll.user32.DestroyWindow.argtypes = [wintypes.HWND]

        ctypes.windll.user32.UpdateLayeredWindow.argtypes = [
            wintypes.HWND, wintypes.HDC,
            ctypes.c_void_p, ctypes.c_void_p,
            wintypes.HDC, ctypes.c_void_p,
            wintypes.COLORREF, ctypes.c_void_p,
            wintypes.DWORD
        ]
        ctypes.windll.user32.UpdateLayeredWindow.restype = wintypes.BOOL
    except Exception:
        pass

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                    ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]
        _fields_ = [("type", ctypes.c_ulong), ("_input", _INPUT)]

def _bezier_point(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    """Cubic bezier interpolation at parameter t."""
    u = 1.0 - t
    return (u**3 * p0 + 3 * u**2 * t * p1 + 3 * u * t**2 * p2 + t**3 * p3)


def _bezier_derivative(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    """Derivative of cubic bezier (for speed control)."""
    u = 1.0 - t
    return (3 * u**2 * (p1 - p0) + 6 * u * t * (p2 - p1) + 3 * t**2 * (p3 - p2))


# ═══════════════════════════════════════════════════════════════════════════
# CURSOR SHAPES ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class CursorShape:
    """Simple flat triangle cursor (Clicky-style) with rotation animation for buffering."""

    # Simple right-pointing isosceles triangle (Clicky-style). Halved to ~27px wide x
    # 30px tall (was ~54x60): at the old size the sprite read as a large block rather than a
    # pointer and obscured the very target it sat on. The tip stays at the origin (0,0), so the
    # drawn point remains exactly on the logical cursor hotspot and click/interact accuracy is
    # unchanged (actuation is headless post_click, never driven by the sprite's pixels).
    TRIANGLE_VERTICES = [(-27.0, -15.0), (-27.0, 15.0), (0.0, 0.0)]
    COLOR = 0x00E8731A  # Bright blue (BGR format: B=E8,G=73,R=1A)
    OUTLINE_COLOR = 0x00FFFFFF  # Legacy (kept for compatibility; no longer stroked)

    def __init__(self):
        self._rotation_angle = 0.0  # Rotation angle in degrees
        self._is_buffering = False  # Buffering state
        self._rotation_speed = 180.0  # Degrees per second when buffering
        self._name = "pointer"      # logical mode label ('pointer' / 'pencil'); the sprite itself stays the blue arrow

    # VisualCursor.set_shape and the drag/draw routines call these. They did not exist, so every drag and every
    # draw_shape raised AttributeError before it delivered a single point (another reason drawing was dead).
    def set_shape(self, name: str, animate: bool = True) -> None:
        self._name = str(name or "pointer")

    def get_shape(self) -> str:
        return self._name

    def set_buffering(self, buffering: bool):
        """Set buffering state - enables rotation animation."""
        self._is_buffering = buffering

    def tick_rotation(self, dt: float = 0.016):
        """Update rotation based on buffering state."""
        if self._is_buffering:
            self._rotation_angle = (self._rotation_angle + self._rotation_speed * dt) % 360.0
        else:
            # Smoothly return to 0 degrees
            if abs(self._rotation_angle) > 1.0:
                self._rotation_angle *= 0.9
            else:
                self._rotation_angle = 0.0

    def get_rotation(self) -> float:
        return self._rotation_angle

    def is_buffering(self) -> bool:
        return self._is_buffering


# ═══════════════════════════════════════════════════════════════════════════
# PER-AGENT CURSOR SPRITE (the cursor "duplicates" for temporary agents)
# ═══════════════════════════════════════════════════════════════════════════

# Distinct, high-visibility arrow colours (BGR) so simultaneous agents are
# instantly tellable apart. The primary blue arrow is intentionally omitted.
AGENT_PALETTE: List[int] = [
    0x0016CC84,  # emerald
    0x000B9EF5,  # amber
    0x005E3BF4,  # rose
    0x00EED322,  # cyan
    0x00EF46D9,  # fuchsia
    0x002F6FE4,  # sky
    0x0081B910,  # lime-teal
    0x00C832C8,  # magenta
]


class CursorSprite:
    """An independent, colour-coded cursor owned by ONE temporary agent.

    It lives inside the single overlay surface (no extra window) but keeps its
    own position, bezier flight, trail, ripples, label and lifecycle, so many
    agents can each 'have' a cursor that moves on its own lane without fighting
    over the one physical pointer. Rendering reuses VisualCursor's GDI helpers."""

    _MISSPEED = 26.0

    def __init__(self, owner: "VisualCursor", sid: str, name: str, color: int,
                 ttl: Optional[float] = None):
        self._vc = owner
        self.id = sid
        self.name = name
        self.color = color
        screen_w = ctypes.windll.user32.GetSystemMetrics(0) if _HAS_CTYPES else 1920
        screen_h = ctypes.windll.user32.GetSystemMetrics(1) if _HAS_CTYPES else 1080
        self._x: float = float(screen_w // 2)
        self._y: float = float(screen_h // 2)
        self._target_x: float = self._x
        self._target_y: float = self._y
        self._visible = True
        self._flying = False
        self._fly_p0 = (self._x, self._y)
        self._fly_p1 = (self._x, self._y)
        self._fly_p2 = (self._x, self._y)
        self._fly_p3 = (self._x, self._y)
        self._fly_start = time.time()
        self._fly_dur = 0.5
        self._label = ""
        self._state = "ACTIVE"
        self._trail: List[Tuple[float, float, float]] = []
        self._ripples: List[Tuple[float, float, float, Any]] = []
        self._born = time.time()
        self._last_action = time.time()
        self._ttl = ttl  # seconds of idle before auto-retire (None = manual)

    # ---- agent-driven actions ----
    def fly_to(self, x: float, y: float, label: str = "", duration: float = 0.5):
        self._visible = True
        start_x, start_y = self._x, self._y
        mid_x, mid_y = (start_x + x) / 2, (start_y + y) / 2
        dist = math.hypot(x - start_x, y - start_y)
        arc = min(dist * 0.35, 120)
        self._fly_p0 = (start_x, start_y)
        self._fly_p1 = (start_x + (mid_x - start_x) * 0.3, mid_y - arc)
        self._fly_p2 = (mid_x + (x - mid_x) * 0.3, mid_y - arc * 0.5)
        self._fly_p3 = (x, y)
        self._fly_start = time.time()
        self._fly_dur = max(0.05, duration)
        self._label = label
        self._flying = True
        self._state = "MOVING"
        self._target_x, self._target_y = x, y
        self._last_action = time.time()

    def move_to(self, x: float, y: float):
        self._visible = True
        self._flying = False
        self._target_x, self._target_y = x, y
        self._last_action = time.time()

    def set_label(self, label: str, state: str = ""):
        self._label = label or ""
        if state:
            self._state = state.upper()

    def click(self, x: Optional[float] = None, y: Optional[float] = None):
        cx = x if x is not None else self._x
        cy = y if y is not None else self._y
        self._ripples.append((cx, cy, time.time(), self.color))
        self._last_action = time.time()
        return self

    @property
    def center(self) -> Tuple[int, int]:
        return (int(self._x), int(self._y))

    def info(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "color": self.color,
                "pos": self.center, "state": self._state,
                "ttl": self._ttl, "age": round(time.time() - self._born, 2)}

    # ---- per-frame advance (called by the animation loop) ----
    def tick(self, now: float) -> bool:
        """Advance one frame. Returns True when this sprite should be retired."""
        if self._flying:
            t = min(1.0, (now - self._fly_start) / self._fly_dur)
            self._x = _bezier_point(t, self._fly_p0[0], self._fly_p1[0],
                                    self._fly_p2[0], self._fly_p3[0])
            self._y = _bezier_point(t, self._fly_p0[1], self._fly_p1[1],
                                    self._fly_p2[1], self._fly_p3[1])
            self._trail.append((self._x, self._y, now))
            if t >= 1.0:
                self._flying = False
                self._x, self._y = self._fly_p3
                self._state = "ACTIVE"
        else:
            dx, dy = self._target_x - self._x, self._target_y - self._y
            dist = math.hypot(dx, dy)
            if dist > 1.0:
                step = min(self._MISSPEED, dist)
                self._x += (dx / dist) * step
                self._y += (dy / dist) * step
                self._trail.append((self._x, self._y, now))
        if self._ttl is not None and (now - self._last_action) >= self._ttl:
            return True  # idle past TTL -> auto-retire
        return False

    # ---- rendering (drawn into the shared overlay DIB) ----
    def draw(self, vc: "VisualCursor", hdc_mem, now: float):
        if not self._visible:
            return
        self._trail = vc._draw_trail_points(hdc_mem, now, self._trail, self.color)
        cx, cy = int(self._x), int(self._y)
        vc._draw_neon_triangle(hdc_mem, cx, cy, now, color=self.color, rotation=0.0)
        self._ripples = vc._draw_ripple_set(hdc_mem, now, self._ripples, self.color)
        text = f"{self.name}" if not self._label else f"{self.name} \u00b7 {self._label}"
        vc._draw_badge(hdc_mem, cx + 18, cy - 20, text, border_color=self.color)


# ═══════════════════════════════════════════════════════════════════════════
# VISUAL CURSOR MAIN OVERLAY
# ═══════════════════════════════════════════════════════════════════════════

class VisualCursor:
    """Transparent overlay window with active living virtual cursor.
    NEVER steals physical mouse. Runs actively on desktop."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *a, **kw):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self._hwnd: int = 0
        self._visible = False

        screen_w = ctypes.windll.user32.GetSystemMetrics(0) if _HAS_CTYPES else 1920
        screen_h = ctypes.windll.user32.GetSystemMetrics(1) if _HAS_CTYPES else 1080

        # Position default: center of screen so it is actively ready
        self._x: float = float(screen_w // 2)
        self._y: float = float(screen_h // 2)
        self._target_x: float = self._x
        self._target_y: float = self._y

        self._click_animations: list = []
        self._trail_points: List[Tuple[float, float, float]] = []
        self._cursor_size: int = 24
        self._ripple_max_radius: int = 48
        self._ripple_duration: float = 0.5
        self._move_speed: float = 22.0
        self._animating = False
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Shape engine
        self.shape = CursorShape()
        self._active_state = "ACTIVE"  # "ACTIVE", "MOVING", "DRAWING", "CLICKING"
        self._show_state_badge = True
        self._hfont_badge: int = 0     # the badge font, created once on the render thread

        # Magnetic rest state: virtual cursor rides on the physical mouse when idle,
        # detaches the moment the agent acts, and snaps back once idle again.
        self._magnet_enabled = True
        self._attached = True
        self._last_action_ts: float = 0.0
        self._reattach_delay: float = 0.7  # seconds of idle before re-attaching

        # Bezier flight state
        self._flying = False
        self._fly_start_time: float = 0.0
        self._fly_duration: float = 0.5
        self._fly_p0 = (self._x, self._y)
        self._fly_p1 = (self._x, self._y)
        self._fly_p2 = (self._x, self._y)
        self._fly_p3 = (self._x, self._y)
        self._fly_label: str = ""

        # Permanent presence: transient is False by default so cursor stays active
        self._transient = False
        self._transient_hide_time: float = 0.0
        self._transient_delay: float = 1.5

        # Single-color palette (bright blue arrow)
        self._color_cursor = CursorShape.COLOR  # Bright blue (BGR)
        self._color_trail = 0x00E8731A          # Blue trail
        self._color_ripple = 0x00E8731A         # Blue ripple
        self._color_label_bg = 0x001A1624       # Deep charcoal
        self._color_label_text = 0x00FFFFFF     # White text

        # GDI objects
        self._brush_cursor = None
        self._pen_trail = None
        self._pen_ripple = None

        # ── Multi-cursor registry (per temporary agent) ──────────────────
        # The single blue arrow above stays the PRIMARY/physical-magnet cursor.
        # Each spawned agent gets its own independently-animated, colour-coded
        # CursorSprite drawn into the SAME overlay surface, so parallel agents
        # each visibly 'own' a cursor without fighting over one pointer.
        self._sprites: Dict[str, "CursorSprite"] = {}
        self._sprite_lock = threading.Lock()
        self._palette_i = 0

    def _create_window(self):
        """Create transparent, click-through, always-on-top overlay window."""
        if not _HAS_CTYPES or not _HAS_WIN32:
            logger.warning("[VisualCursor] Missing ctypes or pywin32 — overlay disabled")
            return

        _ensure_interactive_desktop()
        hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)

        wc = _WNDCLASSEX()
        wc.cbSize = ctypes.sizeof(wc)
        wc.style = win32con.CS_HREDRAW | win32con.CS_VREDRAW
        self._wnd_proc_ref = _WNDPROC(self._wnd_proc)
        wc.lpfnWndProc = ctypes.cast(self._wnd_proc_ref, ctypes.c_void_p)
        wc.hInstance = hInstance
        wc.hCursor = ctypes.windll.user32.LoadCursorW(0, win32con.IDC_ARROW)
        wc.lpszClassName = "HojaigaVisualCursor"
        wc.hbrBackground = 0
        wc.hIcon = 0
        wc.hIconSm = 0
        wc.cbWndExtra = 0
        wc.cbClsExtra = 0
        wc.menuName = None

        try:
            ctypes.windll.user32.RegisterClassExW(ctypes.byref(wc))
        except Exception:
            pass

        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)

        ex_style = (
            win32con.WS_EX_LAYERED |
            win32con.WS_EX_TRANSPARENT |
            win32con.WS_EX_TOPMOST |
            win32con.WS_EX_NOACTIVATE
        )

        self._hwnd = ctypes.windll.user32.CreateWindowExW(
            ex_style,
            "HojaigaVisualCursor",
            "Hojaiga Active Virtual Mouse",
            win32con.WS_POPUP,
            0, 0, screen_w, screen_h,
            0, 0, hInstance, None
        )

        if not self._hwnd:
            logger.error("[VisualCursor] CreateWindowExW failed")
            return

        # NOTE: Do NOT call SetLayeredWindowAttributes here!
        # It is mutually exclusive with UpdateLayeredWindow.
        # We use UpdateLayeredWindow with per-pixel alpha in _render_frame.

        # GDI objects
        self._brush_cursor = ctypes.windll.gdi32.CreateSolidBrush(self._color_cursor)
        self._pen_trail = ctypes.windll.gdi32.CreatePen(0, 3, self._color_trail)
        self._pen_ripple = ctypes.windll.gdi32.CreatePen(0, 2, self._color_ripple)

        logger.info("[VisualCursor] Active overlay created hwnd=%d", self._hwnd)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_PAINT:
            self._render_frame()
            return 0
        try:
            return ctypes.windll.user32.DefWindowProcW(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(msg),
                ctypes.c_size_t(wparam),
                ctypes.c_size_t(lparam)
            )
        except Exception:
            return 0

    def _render_frame(self):
        """Render active living cursor frame via UpdateLayeredWindow at 60fps.
        Uses a 32-bit ARGB DIB section for proper per-pixel alpha transparency.
        Renders a small region around the cursor for performance."""
        if not self._hwnd or not _HAS_CTYPES:
            return

        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)
        if screen_w <= 0 or screen_h <= 0:
            return

        hdc_screen = None
        hdc_mem = None
        hbmp = None

        try:
            hdc_screen = ctypes.windll.user32.GetDC(0)
            if not hdc_screen:
                return

            hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc_screen)

            # Create 32-bit ARGB DIB section for per-pixel alpha
            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32),
                ]
            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = screen_w
            bmi.biHeight = -screen_h  # top-down
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0  # BI_RGB

            ppvBits = ctypes.c_void_p()
            hbmp = ctypes.windll.gdi32.CreateDIBSection(
                hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(ppvBits), None, 0
            )
            if not hbmp:
                return

            ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)

            # Clear to fully transparent (all bytes = 0)
            ctypes.windll.gdi32.PatBlt(hdc_mem, 0, 0, screen_w, screen_h, win32con.BLACKNESS)

            now = time.time()

            # 1. Glowing Trail (Electric Cyan fading particles)
            self._draw_trail(hdc_mem, now)

            # 2. Render Active Living Cursor (single triangle with rotation)
            if self._visible:
                cx, cy = int(self._x), int(self._y)
                self._draw_neon_triangle(hdc_mem, cx, cy, now)

                # 3. Dynamic Active State Badge
                if self._show_state_badge:
                    badge_text = ""
                    if self._flying:
                        badge_text = f">> {self._fly_label or 'MOVING'}"
                    elif self._active_state == "DRAWING":
                        badge_text = "DRAWING"
                    elif self._active_state == "CLICKING":
                        badge_text = "CLICK"
                    elif self._active_state == "ACTIVE":
                        badge_text = "ACTIVE"
                    else:
                        badge_text = self._active_state

                    if badge_text:
                        self._draw_badge(hdc_mem, cx + 18, cy - 20, badge_text)

            # 4. Click Ripples
            self._draw_ripples(hdc_mem, now)

            # 4b. Per-agent cursors (multi-cursor): each temporary agent's own
            # colour-coded arrow + name badge, rendered on this same surface.
            with self._sprite_lock:
                sprites = list(self._sprites.values())
            for spr in sprites:
                spr.draw(self, hdc_mem, now)

            # 5. Stamp alpha=255 onto all non-black pixels in the DIB
            # GDI draws with alpha=0, so UpdateLayeredWindow with AC_SRC_ALPHA
            # would make everything invisible. We fix by setting alpha=255 on
            # pixels that have any color. Use numpy for speed if available.
            if ppvBits.value:
                pixel_count = screen_w * screen_h
                try:
                    import numpy as np
                    arr = np.ctypeslib.as_array(
                        ctypes.cast(ppvBits, ctypes.POINTER(ctypes.c_uint32 * pixel_count)).contents
                    )
                    # Where any of BGR channels is non-zero, set alpha byte
                    mask = (arr & 0x00FFFFFF) != 0
                    arr[mask] |= 0xFF000000
                except ImportError:
                    # Fallback: scan only the hot region(s) around every cursor
                    # (primary + each agent sprite) so we still light up sprites
                    # even without numpy. Keep it bounded for speed.
                    arr_type = ctypes.c_uint32 * pixel_count
                    pixels = ctypes.cast(ppvBits, ctypes.POINTER(arr_type)).contents
                    centers = [(int(self._x), int(self._y))]
                    centers += [(int(s._x), int(s._y)) for s in sprites]
                    for (ccx, ccy) in centers:
                        y_min = max(0, ccy - 150)
                        y_max = min(screen_h, ccy + 150)
                        x_min = max(0, ccx - 150)
                        x_max = min(screen_w, ccx + 150)
                        for row in range(y_min, y_max):
                            base = row * screen_w
                            for col in range(x_min, x_max):
                                idx = base + col
                                v = pixels[idx]
                                if v & 0x00FFFFFF:
                                    pixels[idx] = v | 0xFF000000

            # Update layered window with per-pixel alpha
            sz = wintypes.SIZE(screen_w, screen_h)
            pt_src = wintypes.POINT(0, 0)
            # AC_SRC_OVER=0, Flags=0, SourceConstantAlpha=255, AlphaFormat=AC_SRC_ALPHA=1
            blend = _BLENDFUNCTION(0, 0, 255, 1)
            _ulw_ok = ctypes.windll.user32.UpdateLayeredWindow(
                self._hwnd, hdc_screen, None,
                ctypes.byref(sz),
                hdc_mem,
                ctypes.byref(pt_src),
                0, ctypes.byref(blend), 0x00000002  # ULW_ALPHA
            )
            if not _ulw_ok:
                logger.debug("[VisualCursor] UpdateLayeredWindow failed err=%d", ctypes.GetLastError())
        except Exception as e:
            logger.debug(f"[VisualCursor] _render_frame error: {e}")
        finally:
            if hbmp:
                try: ctypes.windll.gdi32.DeleteObject(hbmp)
                except Exception: pass
            if hdc_mem:
                try: ctypes.windll.gdi32.DeleteDC(hdc_mem)
                except Exception: pass
            if hdc_screen:
                try: ctypes.windll.user32.ReleaseDC(0, hdc_screen)
                except Exception: pass

    def _draw_neon_triangle(self, hdc_mem, cx: int, cy: int, now: float,
                            color: Optional[int] = None, rotation: Optional[float] = None):
        """Render single-color arrow-pointer triangle. `color`/`rotation` default
        to the primary cursor's blue arrow + live buffering rotation, so per-agent
        sprites can reuse this exact renderer with their own color."""
        # Update rotation (primary keeps animating; sprites pass an explicit value)
        if rotation is None:
            self.shape.tick_rotation(0.016)
            rotation = self.shape.get_rotation()
        fill = CursorShape.COLOR if color is None else color

        # Base triangle vertices (Clicky-style simple triangle)
        base_vertices = CursorShape.TRIANGLE_VERTICES

        # Apply rotation if buffering
        if rotation != 0:
            rad = math.radians(rotation)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            rotated_vertices = []
            for vx, vy in base_vertices:
                # Rotate around origin (0,0) - the cursor tip
                rx = vx * cos_a - vy * sin_a
                ry = vx * sin_a + vy * cos_a
                rotated_vertices.append((rx, ry))
            vertices = rotated_vertices
        else:
            vertices = base_vertices

        # Draw triangle with single color
        pts = (POINT * (len(vertices) + 1))()
        for i, (vx, vy) in enumerate(vertices):
            pts[i] = POINT(cx + int(vx), cy + int(vy))
        pts[len(vertices)] = pts[0]  # Close the triangle

        # Flat single-color fill, no neon outline (Clicky look): the pen matches
        # the brush so GDI's default 1px stroke never draws a white edge.
        brush = ctypes.windll.gdi32.CreateSolidBrush(fill)
        pen = ctypes.windll.gdi32.CreatePen(0, 1, fill)
        old_brush = ctypes.windll.gdi32.SelectObject(hdc_mem, brush)
        old_pen = ctypes.windll.gdi32.SelectObject(hdc_mem, pen)

        ctypes.windll.gdi32.Polygon(hdc_mem, ctypes.byref(pts), len(vertices))

        # Cleanup
        ctypes.windll.gdi32.SelectObject(hdc_mem, old_brush)
        ctypes.windll.gdi32.SelectObject(hdc_mem, old_pen)
        ctypes.windll.gdi32.DeleteObject(brush)
        ctypes.windll.gdi32.DeleteObject(pen)

    def _badge_font(self):
        """One font handle for the life of the overlay, created on first use (and deleted by
        destroy()). Measured reason this is not a micro-optimisation: the badge used to create a
        font per frame AND ask user32 for GetTextExtentPoint32W -- an entry point of GDI32, so the
        call raised AttributeError, the local `except Exception: pass` swallowed it, and the frame's
        font handle was stranded. 4,154 live fonts later the process walked past the ~10,000
        per-process GDI cap, after which no device context can be created and EVERY PrintWindow
        capture in the session comes back blank and reads as "the app did not render"."""
        if not _HAS_CTYPES:
            return 0
        cached = getattr(self, "_hfont_badge", 0)
        if cached:
            return cached
        self._hfont_badge = ctypes.windll.gdi32.CreateFontW(
            12, 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 0, 0, "Segoe UI")
        return self._hfont_badge or 0

    def _draw_badge(self, hdc_mem, x: int, y: int, text: str,
                    border_color: int = 0x00FFFF00):
        """Render sleek cyberpunk rounded pill badge showing active state.

        Three rules this function used to break, and now cannot: measure text with the GDI32
        entry point (not user32), deselect an object before deleting it (a still-selected object
        cannot be deleted), and release every object in `finally` -- an error is logged, never
        swallowed, because a hidden error here costs the whole session its eyes."""
        try:
            import ctypes.wintypes as wt
            g32 = ctypes.windll.gdi32
            u32 = ctypes.windll.user32
            hfont = self._badge_font()
            if not hfont:
                return
            old_font = g32.SelectObject(hdc_mem, hfont)
            pen_b = brush_b = None
            old_p = old_br = None
            try:
                # GetTextExtentPoint32W lives in gdi32; typed here because the windll loaders are
                # thread-local and this runs on the animation thread, not the importing one.
                g32.GetTextExtentPoint32W.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                                      ctypes.c_int, ctypes.c_void_p]
                g32.GetTextExtentPoint32W.restype = ctypes.c_int
                size = wt.SIZE()
                if not g32.GetTextExtentPoint32W(hdc_mem, text, len(text), ctypes.byref(size)):
                    size.cx, size.cy = 90, 16          # a failed measurement must not lose the badge

                pad_x = 7
                pad_y = 3
                rect_left = x
                rect_top = y
                rect_right = x + size.cx + pad_x * 2
                rect_bottom = y + size.cy + pad_y * 2

                pen_b = g32.CreatePen(0, 1, border_color)      # tinted border
                brush_b = g32.CreateSolidBrush(0x001A1624)  # Cyber dark
                old_p = g32.SelectObject(hdc_mem, pen_b)
                old_br = g32.SelectObject(hdc_mem, brush_b)

                u32.RoundRect(hdc_mem, rect_left, rect_top, rect_right, rect_bottom, 10, 10)

                g32.SetBkMode(hdc_mem, 1)  # Transparent
                g32.SetTextColor(hdc_mem, 0x00FFFFFF)
                u32.TextOutW(hdc_mem, rect_left + pad_x, rect_top + pad_y, text, len(text))
            finally:
                # Restore every slot we touched (SelectObject returns the object of that TYPE that
                # was in the slot, so old_p is the old pen and old_br the old brush), then delete
                # what this call created -- nothing can be deleted while it is still selected. The
                # font is the shared cached one and is never deleted here (destroy() does that).
                if old_br is not None:
                    g32.SelectObject(hdc_mem, old_br)
                if old_p is not None:
                    g32.SelectObject(hdc_mem, old_p)
                if old_font is not None:
                    g32.SelectObject(hdc_mem, old_font)
                if brush_b:
                    g32.DeleteObject(brush_b)
                if pen_b:
                    g32.DeleteObject(pen_b)
        except Exception as e:
            logger.debug("[VisualCursor] badge draw failed: %s", e)

    def _draw_trail(self, hdc_mem, now: float):
        """Draw bright blue glowing trail dots along the primary movement path."""
        self._trail_points = self._draw_trail_points(hdc_mem, now, self._trail_points,
                                                     self._color_trail)

    def _draw_trail_points(self, hdc_mem, now: float, points: List[Tuple[float, float, float]],
                           color: int) -> List[Tuple[float, float, float]]:
        """Shared trail renderer: draw + prune the given points, return survivors."""
        if not points:
            return points
        cutoff = now - 0.35
        alive = [(x, y, t) for (x, y, t) in points if t > cutoff]
        for tx, ty, tt in alive:
            age = now - tt
            alpha = max(0.0, 1.0 - (age / 0.35))
            radius = max(1, int(5 * alpha))
            intensity = int(255 * alpha)
            # Tint the dot by the supplied base color's brightness.
            b = (color >> 16) & 0xFF
            g = (color >> 8) & 0xFF
            r = color & 0xFF
            dot = ((b * intensity // 255) << 16) | ((g * intensity // 255) << 8) | (r * intensity // 255)
            pen = ctypes.windll.gdi32.CreatePen(0, 1, dot)
            old_pen = ctypes.windll.gdi32.SelectObject(hdc_mem, pen)
            ctypes.windll.gdi32.Ellipse(hdc_mem, int(tx) - radius, int(ty) - radius,
                                        int(tx) + radius, int(ty) + radius)
            ctypes.windll.gdi32.SelectObject(hdc_mem, old_pen)
            ctypes.windll.gdi32.DeleteObject(pen)
        return alive

    def _draw_ripples(self, hdc_mem, now: float):
        """Draw expanding click ripple waves for the primary cursor."""
        self._click_animations = self._draw_ripple_set(hdc_mem, now, self._click_animations,
                                                       self._color_ripple)

    def _draw_ripple_set(self, hdc_mem, now: float,
                         anims: List[Tuple[float, float, float, Any]],
                         color: int) -> List[Tuple[float, float, float, Any]]:
        """Shared ripple renderer: draw + prune, return still-active animations."""
        active: List[Tuple[float, float, float, Any]] = []
        for (ax, ay, start_t, c) in anims:
            elapsed = now - start_t
            if elapsed < self._ripple_duration:
                progress = elapsed / self._ripple_duration
                radius = int(self._ripple_max_radius * progress)
                alpha = 1.0 - progress
                if radius > 0:
                    intensity = int(255 * alpha)
                    b = (color >> 16) & 0xFF
                    g = (color >> 8) & 0xFF
                    r = color & 0xFF
                    col = ((b * intensity // 255) << 16) | ((g * intensity // 255) << 8) | (r * intensity // 255)
                    pen = ctypes.windll.gdi32.CreatePen(0, 2, col)
                    old_pen = ctypes.windll.gdi32.SelectObject(hdc_mem, pen)
                    ctypes.windll.gdi32.SelectObject(hdc_mem, 0)
                    ctypes.windll.gdi32.Ellipse(hdc_mem, int(ax) - radius, int(ay) - radius,
                                                int(ax) + radius, int(ay) + radius)
                    ctypes.windll.gdi32.SelectObject(hdc_mem, old_pen)
                    ctypes.windll.gdi32.DeleteObject(pen)
                active.append((ax, ay, start_t, c))
        return active

    def _anim_loop(self):
        """Animation loop — window creation, message pump, bezier flight, shape morphing, trail recording, 60fps refresh."""
        _ensure_interactive_desktop()
        if not self._hwnd:
            self._create_window()
        if self._hwnd and _HAS_CTYPES:
            ctypes.windll.user32.ShowWindow(self._hwnd, win32con.SW_SHOW)

        while self._running:
            # 1. Pump Windows message queue on background thread to stay 100% responsive
            if _HAS_CTYPES and _HAS_WIN32:
                try:
                    msg = wintypes.MSG()
                    while ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, win32con.PM_REMOVE):
                        ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                        ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
                except Exception:
                    pass

            now = time.time()
            if hasattr(self, "shape") and hasattr(self.shape, "tick_morph"):
                try:
                    self.shape.tick_morph(0.016)
                except AttributeError:
                    pass  # Skip if method doesn't exist

            # Handle bezier-arc flight
            if self._flying:
                elapsed = now - self._fly_start_time
                t = min(1.0, elapsed / self._fly_duration)

                # Cubic bezier interpolation
                self._x = _bezier_point(t, self._fly_p0[0], self._fly_p1[0],
                                       self._fly_p2[0], self._fly_p3[0])
                self._y = _bezier_point(t, self._fly_p0[1], self._fly_p1[1],
                                       self._fly_p2[1], self._fly_p3[1])

                self._trail_points.append((self._x, self._y, now))

                if t >= 1.0:
                    self._flying = False
                    self._x = self._fly_p3[0]
                    self._y = self._fly_p3[1]
                    if self._active_state == "MOVING":
                        self._active_state = "ACTIVE"
            else:
                if self._magnet_enabled and self._attached:
                    # REST STATE: virtual cursor rides on top of the physical mouse.
                    px, py = self._get_physical_cursor()
                    self._x = float(px)
                    self._y = float(py)
                    self._target_x = self._x
                    self._target_y = self._y
                else:
                    # DETACHED: glide to the last commanded target, then re-attach
                    # to the physical mouse once the agent has been idle a moment.
                    dx = self._target_x - self._x
                    dy = self._target_y - self._y
                    dist = math.hypot(dx, dy)
                    if dist > 1.0:
                        step = min(self._move_speed, dist)
                        self._x += (dx / dist) * step
                        self._y += (dy / dist) * step
                        self._trail_points.append((self._x, self._y, now))
                    if (self._magnet_enabled
                            and not self._flying
                            and self._active_state in ("ACTIVE", "IDLE", "")
                            and (now - self._last_action_ts) >= self._reattach_delay):
                        self._attached = True

            # Handle transient auto-hide only if explicitly configured
            if self._transient and self._transient_hide_time > 0:
                if now > self._transient_hide_time:
                    self._visible = False
                    self._transient = False
                    self._transient_hide_time = 0

            # Advance every agent cursor (flight/glide/trail/ripple/auto-retire).
            with self._sprite_lock:
                sprite_items = list(self._sprites.items())
            expired = []
            for sid, spr in sprite_items:
                if spr.tick(now):
                    expired.append(sid)
            if expired:
                with self._sprite_lock:
                    for sid in expired:
                        self._sprites.pop(sid, None)

            # Direct render via UpdateLayeredWindow at 60fps (no cross-thread message blocking)
            try:
                self._render_frame()
            except Exception:
                pass

            time.sleep(0.016)

    def show(self):
        """Show the cursor overlay and start active animation loop."""
        self._visible = True
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._anim_loop, daemon=True, name="VisualCursorThread")
            self._thread.start()
        elif self._hwnd and _HAS_CTYPES:
            ctypes.windll.user32.ShowWindow(self._hwnd, win32con.SW_SHOW)
        logger.info("[VisualCursor] Overlay active on desktop")

    def hide(self):
        """Hide the cursor overlay."""
        self._visible = False
        if self._hwnd:
            ctypes.windll.user32.ShowWindow(self._hwnd, win32con.SW_HIDE)
        self._running = False
        logger.info("[VisualCursor] Overlay hidden")

    # ── Multi-cursor API (one visible cursor per temporary agent) ──────────
    def spawn_cursor(self, agent_id: Optional[str] = None, agent_name: str = "",
                     color: Optional[int] = None, ttl: Optional[float] = None) -> "CursorSprite":
        """Duplicate the cursor for a new (temporary) agent: a fresh, independent,
        colour-coded arrow that animates on its own lane. Idempotent per agent_id."""
        sid = agent_id or f"agent_{int(time.time()*1000)}_{len(self._sprites)}"
        with self._sprite_lock:
            existing = self._sprites.get(sid)
        if existing is not None:
            if agent_name:
                existing.name = agent_name
            return existing
        if color is None:
            color = AGENT_PALETTE[self._palette_i % len(AGENT_PALETTE)]
            self._palette_i += 1
        spr = CursorSprite(self, sid, agent_name or sid, color, ttl=ttl)
        with self._sprite_lock:
            self._sprites[sid] = spr
        # Make sure the overlay + animation loop are running so the new cursor
        # is visible even if nothing called show() yet.
        if not self._running:
            try:
                self.show()
            except Exception:
                pass
        return spr

    def agent_cursor(self, agent_id: str, agent_name: str = "") -> "CursorSprite":
        """Get-or-create the dedicated cursor for an agent id."""
        with self._sprite_lock:
            spr = self._sprites.get(agent_id)
        if spr is None:
            spr = self.spawn_cursor(agent_id, agent_name)
        elif agent_name:
            spr.name = agent_name
        return spr

    def remove_cursor(self, agent_id: str) -> bool:
        """Retire one agent cursor (called when a temporary agent finishes)."""
        with self._sprite_lock:
            return self._sprites.pop(agent_id, None) is not None

    def list_cursors(self) -> List[Dict[str, Any]]:
        with self._sprite_lock:
            return [s.info() for s in self._sprites.values()]

    def set_active_state(self, state: str):
        """Set active state label (e.g. 'ACTIVE', 'MOVING', 'DRAWING', 'CLICKING')."""
        self._active_state = state.strip().upper()

    def set_buffering(self, buffering: bool):
        """Set buffering state - enables rotation animation on triangle."""
        if hasattr(self, "shape"):
            self.shape.set_buffering(buffering)

    def set_shape(self, shape_name: str, animate: bool = True):
        """Morph cursor shape (e.g. 'pointer', 'pencil', 'magnifier', 'sparkle')."""
        if hasattr(self, "shape"):
            self.shape.set_shape(shape_name, animate=animate)

    def set_transient(self, enabled: bool, delay: float = 1.5):
        """Enable/disable transient mode."""
        self._transient = enabled
        self._transient_delay = delay

    def fly_to(self, x: float, y: float, label: str = "", duration: float = 0.5):
        """Fly cursor to (x, y) using curved bezier-arc flight. NEVER touches physical mouse."""
        self._detach()
        start_x, start_y = self._x, self._y
        mid_x = (start_x + x) / 2
        mid_y = (start_y + y) / 2
        dist = math.hypot(x - start_x, y - start_y)
        arc_height = min(dist * 0.35, 120)

        self._fly_p0 = (start_x, start_y)
        self._fly_p1 = (start_x + (mid_x - start_x) * 0.3, mid_y - arc_height)
        self._fly_p2 = (mid_x + (x - mid_x) * 0.3, mid_y - arc_height * 0.5)
        self._fly_p3 = (x, y)

        self._fly_start_time = time.time()
        self._fly_duration = duration
        self._fly_label = label
        self._flying = True
        self._active_state = "MOVING"
        self._target_x = x
        self._target_y = y

    def move_to(self, x: float, y: float, animate: bool = True):
        """Move cursor position without touching physical mouse."""
        self._detach()
        self._target_x = x
        self._target_y = y
        if not animate:
            self._x = x
            self._y = y

    def click_at(self, x: float, y: float, color: int = 0x00FF8800, hwnd: Optional[int] = None):
        """Fly to (x, y), trigger the expanding ripple, and click the window under that point with POSTED window
        messages (headless_input.post_click). The physical pointer is never moved; if no target window can be
        resolved the click is refused and recorded in ``self.last_click``."""
        self.show()
        self._active_state = "CLICKING"
        self.fly_to(x, y, label="Click", duration=0.35)

        def _on_click_finish():
            self._click_animations.append((x, y, time.time(), color))
            try:
                from core_organs import headless_input as hin
                target = self._stroke_target(hwnd, x, y)
                if target:
                    ok, note = hin.post_click(target, int(x), int(y))
                else:
                    ok, note = False, "UNDELIVERABLE: no target window resolved (refused; no physical-input fallback)"
                self.last_click = {"delivered": ok, "note": note}
            except Exception as exc:
                self.last_click = {"delivered": False, "note": f"click failed: {exc}"}
            time.sleep(0.2)
            self._active_state = "ACTIVE"

        threading.Timer(self._fly_duration + 0.05, _on_click_finish).start()

    def right_click_at(self, x: float, y: float, hwnd: Optional[int] = None):
        """Show a right-click ripple (red/magenta)."""
        self.click_at(x, y, color=0x000000FF, hwnd=hwnd)

    def set_state(self, state: str):
        """Set active badge state (e.g. 'ACTIVE', 'DRAWING', 'MOVING', 'IDLE')."""
        self._active_state = state.upper().strip()

    def set_active_state(self, state: str):
        """Set active badge state."""
        self._active_state = state.upper().strip()

    def set_position(self, x: float, y: float):
        """Instantly set virtual cursor position."""
        self._detach()
        self._x = x
        self._y = y
        self._target_x = x
        self._target_y = y

    def _send_input_mouse(self, x: float, y: float, flags: int):
        """REMOVED. This used to inject hardware mouse events (mouse_event + SendInput), which the product forbids:
        input goes through headless_input only (post_click / post_drag). Kept as a no-op so an old caller cannot
        reach the physical pointer; it logs instead."""
        logger.warning("[VisualCursor] _send_input_mouse is retired (headless_input only); ignored")

    def _get_physical_cursor(self) -> Tuple[int, int]:
        if not _HAS_CTYPES:
            return (0, 0)
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return (pt.x, pt.y)

    def enable_magnet(self, enabled: bool, reattach_delay: float = 0.7):
        """Enable/disable the magnetic rest state (stick to the physical mouse)."""
        self._magnet_enabled = enabled
        if reattach_delay is not None:
            self._reattach_delay = max(0.0, float(reattach_delay))
        if not enabled:
            self._attached = False

    def _detach(self):
        """Break the magnetic rest state so the virtual cursor can act independently.
        Called at the start of every commanded move/click/drag/draw."""
        self._attached = False
        self._last_action_ts = time.time()

    def _stroke_target(self, hwnd: Optional[int], x: float, y: float) -> int:
        """Window that receives a stroke: the caller's hwnd, else the top-level window under the point (a
        read-only lookup that skips this overlay). 0 = unresolvable -> the stroke is REFUSED, never sent to the
        physical pointer."""
        if hwnd:
            return int(hwnd)
        if not (_HAS_WIN32 and _HAS_CTYPES):
            return 0
        try:
            h = win32gui.WindowFromPoint((int(x), int(y)))
            if h == self._hwnd:
                h = win32gui.GetWindow(h, win32con.GW_HWNDNEXT)
            return int(ctypes.windll.user32.GetAncestor(h, 2) or h) if h else 0
        except Exception:
            return 0

    def _post_stroke(self, target_h: int, pts: List[Tuple[int, int]], duration_s: float) -> Dict[str, Any]:
        """Deliver ONE stroke as posted window messages (headless_input.post_drag) while the visible sprite follows
        the same points, then report whether pixels actually changed. Never touches the physical pointer."""
        from core_organs import headless_input as hin

        def _follow(x: int, y: int):
            self.set_position(float(x), float(y))
            self._trail_points.append((float(x), float(y), time.time()))
        if not target_h:
            return {"delivered": False, "effective": None, "changed_pixels": -1,
                    "note": "UNDELIVERABLE: no target window resolved for the stroke (refused; no physical-input fallback)"}
        before, _w = hin.capture_window(target_h)
        ok, note = hin.post_drag(target_h, pts[0][0], pts[0][1], pts[-1][0], pts[-1][1],
                                 path=pts if len(pts) > 2 else None, duration_s=duration_s, on_point=_follow)
        time.sleep(0.3)
        after, _w2 = hin.capture_window(target_h)
        n, bbox = hin.changed_pixels(before, after)
        effective = None if n < 0 else (n > 0)
        if ok and effective is False:
            note = "delivered but INEFFECTIVE: the window did not react to posted mouse input (no pixel changed)"
        return {"delivered": ok, "effective": effective, "changed_pixels": n, "bbox": bbox, "note": note}

    def drag_to(self, start_x: float, start_y: float, end_x: float, end_y: float,
                steps: int = 30, label: str = "Drag", physical: bool = False, hwnd: Optional[int] = None):
        """Virtual drag from (start_x, start_y) to (end_x, end_y) with a real-time glowing trail. The stroke is
        delivered as POSTED window messages to the target window (headless_input.post_drag): the physical mouse is
        never used (the `physical` flag is accepted for old callers and ignored). The outcome - delivered AND
        effective (pixels changed) - is left in ``self.last_stroke``."""
        self.show()
        self._active_state = "DRAWING"
        if hasattr(self, "shape"):
            self.shape.set_shape("pencil")
        self.fly_to(start_x, start_y, label=label, duration=0.25)
        time.sleep(0.28)
        try:
            target_h = self._stroke_target(hwnd, start_x, start_y)
            self.last_stroke = self._post_stroke(target_h, [(int(start_x), int(start_y)), (int(end_x), int(end_y))],
                                                 max(0.2, steps * 0.015))
        finally:
            self._active_state = "ACTIVE"
            if hasattr(self, "shape"):
                self.shape.set_shape("pointer")

    def _resolve_drawing_strokes(self, shape_or_concept: Any, cx: float, cy: float,
                                 width: float = 150.0, height: float = 150.0,
                                 steps: int = 50) -> List[List[Tuple[float, float]]]:
        """Dynamically generates ordered strokes and coordinates for ANY shape, complex figure, or image.
        Supports:
        - Arbitrary regular polygons (nonagon=9, octagon=8, heptagon=7, hexagon=6, pentagon=5, triangle=3, decagon=10, dodecagon=12, polygon:N)
        - Geometric shapes (circle, oval, star, heart, diamond, spiral)
        - Complex multi-stroke figures (human IRL with environment & background, house, tree, flower, car, landscape)
        - Image vectorization: file path to PNG/JPG/BMP converts contours into ordered coordinate strokes
        - Explicit raw strokes / coordinate lists
        """
        import os, json

        # 1. If explicitly passed a list of strokes
        if isinstance(shape_or_concept, list):
            if len(shape_or_concept) > 0:
                if isinstance(shape_or_concept[0], (list, tuple)) and len(shape_or_concept[0]) > 0:
                    if isinstance(shape_or_concept[0][0], (int, float)):
                        # Single stroke of points [(x,y), ...]
                        return [shape_or_concept]
                    elif isinstance(shape_or_concept[0][0], (list, tuple)):
                        # List of strokes [[(x,y), ...], ...]
                        return shape_or_concept

        shape_str = str(shape_or_concept).strip()

        # 2. Check if JSON string of strokes
        if shape_str.startswith("[") and shape_str.endswith("]"):
            try:
                parsed = json.loads(shape_str)
                if isinstance(parsed, list):
                    return self._resolve_drawing_strokes(parsed, cx, cy, width, height, steps)
            except Exception:
                pass

        # 3. Check if image file path exists
        if os.path.isfile(shape_str) and any(shape_str.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".ico")):
            try:
                import cv2
                import numpy as np
                print(f"[VisualCursor] Tracing highly detailed reference image: {shape_str}")
                
                # Load image
                img = cv2.imread(shape_str, cv2.IMREAD_GRAYSCALE)
                if img is None: raise ValueError("Failed to load image with cv2")
                
                # Resize for manageable tracing (too large = millions of strokes)
                max_dim = 250
                h, w = img.shape
                scale = min(max_dim/w, max_dim/h)
                if scale < 1.0:
                    img = cv2.resize(img, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
                h, w = img.shape
                
                # Edge detection
                blurred = cv2.GaussianBlur(img, (5, 5), 0)
                edges = cv2.Canny(blurred, 50, 150)
                
                # Dilate slightly to connect broken lines
                kernel = np.ones((2,2), np.uint8)
                edges = cv2.dilate(edges, kernel, iterations=1)
                
                # Find contours hierarchically (Outer first, then inner)
                contours, hierarchy = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                
                img_strokes = []
                if contours and hierarchy is not None:
                    # Hierarchy format: [Next, Previous, First_Child, Parent]
                    # We want to sort contours by tree depth (parents first, children later)
                    hierarchy = hierarchy[0]
                    depths = {}
                    def get_depth(idx):
                        if idx in depths: return depths[idx]
                        parent = hierarchy[idx][3]
                        if parent == -1: 
                            depths[idx] = 0
                        else:
                            depths[idx] = get_depth(parent) + 1
                        return depths[idx]
                        
                    # Calculate depths
                    for i in range(len(contours)):
                        get_depth(i)
                        
                    # Sort contours by depth (0 = outermost, higher = deeper inside)
                    sorted_contours = sorted(range(len(contours)), key=lambda x: depths[x])
                    
                    # Convert to normalized strokes
                    start_x = cx - (width / 2.0)
                    start_y = cy - (height / 2.0)
                    
                    for idx in sorted_contours:
                        cnt = contours[idx]
                        # Filter out tiny noise contours
                        if cv2.contourArea(cnt) < 5 and cv2.arcLength(cnt, True) < 10:
                            continue
                            
                        # Smooth and reduce points for drawing speed using Douglas-Peucker
                        epsilon = 0.005 * cv2.arcLength(cnt, True)
                        approx = cv2.approxPolyDP(cnt, epsilon, True)
                        
                        stroke = []
                        for pt in approx:
                            px, py = pt[0]
                            # Normalize 0..1
                            nx = px / float(w)
                            ny = py / float(h)
                            # Scale to user bounds
                            sx = start_x + (nx * width)
                            sy = start_y + (ny * height)
                            stroke.append((sx, sy))
                            
                        # Ensure closed contours close
                        if len(stroke) > 2:
                            stroke.append(stroke[0])
                            
                        if len(stroke) > 1:
                            img_strokes.append(stroke)
                            
                print(f"[VisualCursor] Extracted {len(img_strokes)} hierarchical contour strokes (Outer to Inner).")
                if img_strokes:
                    return img_strokes
            except Exception as e:
                print(f"[VisualCursor] Image tracing failed: {e}")

        # 4. Parametric and Complex Figures
        shape_clean = shape_str.lower()
        strokes: List[List[Tuple[float, float]]] = []

        polygon_sides = {
            "triangle": 3, "trigon": 3,
            "square": 4, "rectangle": 4, "box": 4,
            "pentagon": 5,
            "hexagon": 6,
            "heptagon": 7, "septagon": 7,
            "octagon": 8,
            "nonagon": 9, "enneagon": 9,
            "decagon": 10,
            "hendecagon": 11, "undecagon": 11,
            "dodecagon": 12,
            "tridecagon": 13, "triskaidecagon": 13,
            "tetradecagon": 14,
            "pentadecagon": 15,
            "hexadecagon": 16,
            "heptadecagon": 17,
            "octadecagon": 18,
            "enneadecagon": 19,
            "icosagon": 20
        }

        # Check for dynamic N-gon (e.g. "polygon:9", "ngon:14", "9-gon", "10-gon")
        if any(shape_clean.startswith(p) for p in ("polygon:", "ngon:", "poly:")):
            try:
                n_val = int(shape_clean.split(":")[1].strip())
                if n_val >= 3:
                    polygon_sides[shape_clean] = n_val
            except Exception:
                pass
        elif "-gon" in shape_clean:
            try:
                prefix = shape_clean.split("-gon")[0].strip()
                n_val = int(prefix)
                if n_val >= 3:
                    polygon_sides[shape_clean] = n_val
            except Exception:
                pass

        if shape_clean in polygon_sides and shape_clean not in ("rectangle", "square", "box", "squre", "parallelogram", "trapezium", "trapezoid"):
            n = polygon_sides[shape_clean]
            rx = width / 2.0
            ry = height / 2.0
            corners = []
            for i in range(n):
                angle = (2.0 * math.pi * i / float(n)) - (math.pi / 2.0)
                corners.append((cx + rx * math.cos(angle), cy + ry * math.sin(angle)))
            corners.append(corners[0]) # close
            stroke = []
            sub = max(4, steps // n)
            for k in range(len(corners) - 1):
                c1, c2 = corners[k], corners[k + 1]
                for s in range(sub):
                    t = s / float(sub)
                    stroke.append((c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t))
            stroke.append(corners[-1])
            strokes.append(stroke)

        elif shape_clean in ("rectangle", "rect", "rectange"):
            # Oblong rectangle: enforce distinct width != height if passed square dimensions
            w_val = float(width)
            h_val = float(height)
            if abs(w_val - h_val) < 10:
                w_val = width * 1.45
                h_val = height * 0.80
            hx = w_val / 2.0
            hy = h_val / 2.0
            corners = [
                (cx - hx, cy - hy),
                (cx + hx, cy - hy),
                (cx + hx, cy + hy),
                (cx - hx, cy + hy),
                (cx - hx, cy - hy),
            ]
            stroke = []
            sub = max(4, steps // 4)
            for k in range(len(corners) - 1):
                c1, c2 = corners[k], corners[k + 1]
                for s in range(sub):
                    t = s / float(sub)
                    stroke.append((c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t))
            stroke.append(corners[-1])
            strokes.append(stroke)

        elif shape_clean in ("square", "box", "squre"):
            # Equilateral square: strictly 1:1 aspect ratio
            side = min(float(width), float(height))
            hx = side / 2.0
            hy = side / 2.0
            corners = [
                (cx - hx, cy - hy),
                (cx + hx, cy - hy),
                (cx + hx, cy + hy),
                (cx - hx, cy + hy),
                (cx - hx, cy - hy),
            ]
            stroke = []
            sub = max(4, steps // 4)
            for k in range(len(corners) - 1):
                c1, c2 = corners[k], corners[k + 1]
                for s in range(sub):
                    t = s / float(sub)
                    stroke.append((c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t))
            stroke.append(corners[-1])
            strokes.append(stroke)

        elif shape_clean in ("parallelogram", "rhomboid"):
            # Parallelogram: opposite sides parallel and slanted
            w_val = float(width)
            h_val = float(height)
            if abs(w_val - h_val) < 10:
                w_val = width * 1.45
                h_val = height * 0.80
            hx = w_val / 2.0
            hy = h_val / 2.0
            slant = w_val * 0.25
            corners = [
                (cx - hx + slant / 2.0, cy - hy),      # Top-left
                (cx + hx + slant / 2.0, cy - hy),      # Top-right
                (cx + hx - slant / 2.0, cy + hy),      # Bottom-right
                (cx - hx - slant / 2.0, cy + hy),      # Bottom-left
                (cx - hx + slant / 2.0, cy - hy),      # Close back to Top-left
            ]
            stroke = []
            sub = max(4, steps // 4)
            for k in range(len(corners) - 1):
                c1, c2 = corners[k], corners[k + 1]
                for s in range(sub):
                    t = s / float(sub)
                    stroke.append((c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t))
            stroke.append(corners[-1])
            strokes.append(stroke)

        elif shape_clean in ("trapezium", "trapezoid", "trapez"):
            # Trapezium (Isosceles Trapezoid): top side parallel to bottom, slanted non-parallel sides
            w_val = float(width)
            h_val = float(height)
            if abs(w_val - h_val) < 10:
                w_val = width * 1.45
                h_val = height * 0.80
            w_top = w_val * 0.55
            w_bot = w_val
            hy = h_val / 2.0
            h_top = w_top / 2.0
            h_bot = w_bot / 2.0
            corners = [
                (cx - h_top, cy - hy),      # Top-left
                (cx + h_top, cy - hy),      # Top-right
                (cx + h_bot, cy + hy),      # Bottom-right
                (cx - h_bot, cy + hy),      # Bottom-left
                (cx - h_top, cy - hy),      # Close back to Top-left
            ]
            stroke = []
            sub = max(4, steps // 4)
            for k in range(len(corners) - 1):
                c1, c2 = corners[k], corners[k + 1]
                for s in range(sub):
                    t = s / float(sub)
                    stroke.append((c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t))
            stroke.append(corners[-1])
            strokes.append(stroke)

        elif shape_clean in ("oval", "ellipse"):
            # Elliptical oval: distinct horizontal major axis
            rx_val = float(width) / 2.0
            ry_val = float(height) / 2.0
            if abs(rx_val - ry_val) < 10:
                rx_val = width * 0.65
                ry_val = height * 0.38
            stroke = []
            for i in range(steps + 1):
                angle = 2.0 * math.pi * (i / float(steps))
                stroke.append((cx + rx_val * math.cos(angle), cy + ry_val * math.sin(angle)))
            strokes.append(stroke)

        elif shape_clean in ("circle", "round", "circl"):
            # Equidistant circle
            r_val = min(float(width), float(height)) / 2.0
            stroke = []
            for i in range(steps + 1):
                angle = 2.0 * math.pi * (i / float(steps))
                stroke.append((cx + r_val * math.cos(angle), cy + r_val * math.sin(angle)))
            strokes.append(stroke)

        elif "star" in shape_clean:
            pts_count = 5
            if any(shape_clean.startswith(p) for p in ("star:", "points:")):
                try:
                    pts_count = int(shape_clean.split(":")[1].strip())
                except Exception:
                    pass
            rx, ry = width / 2.0, height / 2.0
            inner_rx, inner_ry = rx * 0.4, ry * 0.4
            corners = []
            total_pts = pts_count * 2
            for i in range(total_pts):
                angle = (2.0 * math.pi * i / float(total_pts)) - (math.pi / 2.0)
                curr_rx = rx if i % 2 == 0 else inner_rx
                curr_ry = ry if i % 2 == 0 else inner_ry
                corners.append((cx + curr_rx * math.cos(angle), cy + curr_ry * math.sin(angle)))
            corners.append(corners[0])
            stroke = []
            sub = max(4, steps // total_pts)
            for k in range(len(corners) - 1):
                c1, c2 = corners[k], corners[k + 1]
                for s in range(sub):
                    t = s / float(sub)
                    stroke.append((c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t))
            stroke.append(corners[-1])
            strokes.append(stroke)

        elif "heart" in shape_clean:
            stroke = []
            scale_x, scale_y = width / 34.0, height / 34.0
            for i in range(steps + 1):
                t = 2.0 * math.pi * (i / float(steps))
                x_val = 16.0 * (math.sin(t) ** 3)
                y_val = -(13.0 * math.cos(t) - 5.0 * math.cos(2*t) - 2.0 * math.cos(3*t) - math.cos(4*t))
                stroke.append((cx + x_val * scale_x, cy + y_val * scale_y))
            strokes.append(stroke)

        else:
            # =========================================================
            # DYNAMIC LLM-POWERED DRAWING ENGINE (Ollama / Qwen2.5)
            # Decides between generating simple JSON coordinates OR 
            # generating a complex reference image via Pollinations to trace.
            # =========================================================
            try:
                import requests
                import json
                print(f"[VisualCursor] Planning dynamic drawing strategy for: '{shape_str}'...")
                
                prompt = f'''You are a master robotic artist. User requested drawing: "{shape_str}"

TASK:
Decide whether to draw this using simple geometric coordinates, OR by generating a highly detailed reference image to trace.
- If it's a simple shape, icon, or basic teaching diagram (e.g. parallelogram, stick figure): Output a JSON with a "strokes" array (array of [x,y] coordinates from 0.0 to 1.0).
- If it's a complex scene, detailed object, or realistic drawing (e.g. village in a valley, futuristic spaceship): Output a JSON with a "pollinations_prompt" string containing a highly detailed, comma-separated prompt for an image generator (must include "white background, clean line art or flat illustration style" so it can be easily traced).

RULES:
1. Output ONLY valid JSON.
2. Either provide "strokes" OR "pollinations_prompt", not both.

Example 1: {{"strokes": [[[0.2, 0.2], [0.8, 0.2]], [[0.5, 0.5], [0.5, 0.9]]]}}
Example 2: {{"pollinations_prompt": "a highly detailed futuristic spaceship, white background, clean line art, professional, sharp, 8k"}}
'''
                data = {'model': 'qwen2.5:3b', 'prompt': prompt, 'stream': False, 'format': 'json'}
                res = requests.post('http://127.0.0.1:11434/api/generate', json=data, timeout=30)
                res_data = res.json()
                response_text = res_data.get('response', '{}').strip()
                
                parsed = json.loads(response_text)
                
                if "pollinations_prompt" in parsed and parsed["pollinations_prompt"]:
                    poly_prompt = parsed["pollinations_prompt"]
                    print(f"[VisualCursor] LLM decided to generate an image to trace. Prompt: {poly_prompt}")
                    try:
                        import sys
                        sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__))))
                        from core_organs.image_generator import generate_image
                        img_path = generate_image(poly_prompt, width=400, height=400)
                        if img_path and os.path.exists(img_path):
                            print(f"[VisualCursor] Generated reference image. Switching to Trace Mode...")
                            # Recursive call to use the OpenCV tracing logic!
                            return self._resolve_drawing_strokes(img_path, cx, cy, width, height, steps)
                        else:
                            raise ValueError("Image generation returned empty path.")
                    except Exception as e:
                        print(f"[VisualCursor] Image generation failed: {e}")
                        raise e
                else:
                    llm_strokes = parsed.get("strokes", [])
                    if not llm_strokes or not isinstance(llm_strokes, list):
                        raise ValueError("No strokes or pollinations_prompt returned by LLM.")
                    
                    print(f"[VisualCursor] LLM successfully generated {len(llm_strokes)} simple geometric strokes!")
                    
                    # Scale coordinates to requested dimensions
                    start_x = cx - (width / 2.0)
                    start_y = cy - (height / 2.0)
                    
                    for s in llm_strokes:
                        if not isinstance(s, list): continue
                        scaled_stroke = []
                        for pt in s:
                            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                                px = start_x + (float(pt[0]) * width)
                                py = start_y + (float(pt[1]) * height)
                                scaled_stroke.append((px, py))
                        if len(scaled_stroke) > 1:
                            strokes.append(scaled_stroke)
                            
            except Exception as e:
                print(f"[VisualCursor] LLM dynamic drawing failed: {e}. Falling back to default line.")
                strokes.append([(cx - width / 2.0, cy - height / 2.0), (cx + width / 2.0, cy + height / 2.0)])

        return strokes

    def draw_shape(self, shape: Any, cx: float, cy: float, width: float = 150.0, height: float = 150.0,
                   steps: int = 50, label: str = "Drawing...", physical: bool = False, hwnd: Optional[int] = None):
        """Draws ANY parametric shape, multi-stroke figure (e.g. human IRL with background, house),
        or vectorized image coordinates, as POSTED window messages to the target window (headless_input.post_drag
        over a sampled point list): the physical mouse is never touched (`physical` is ignored). The visible
        sprite follows every point. ``self.last_stroke`` reports delivered / effective (pixels changed) honestly."""
        self.show()
        self._active_state = "DRAWING"
        old_shape = self.shape.get_shape() if hasattr(self, "shape") else "pointer"
        if hasattr(self, "shape"):
            self.shape.set_shape("pencil")
        self.last_stroke = {"delivered": False, "effective": None, "changed_pixels": -1, "note": "nothing drawn"}

        strokes = self._resolve_drawing_strokes(shape, cx, cy, width, height, steps)
        if not strokes:
            self._active_state = "ACTIVE"
            if hasattr(self, "shape"): self.shape.set_shape(old_shape)
            return

        target_h = self._stroke_target(hwnd, cx, cy)
        from core_organs import headless_input as hin
        total_strokes = len(strokes)
        before_all, _why = hin.capture_window(target_h) if target_h else (None, "no-target")
        delivered, notes = True, []
        try:
            for s_idx, stroke in enumerate(strokes):
                if not stroke:
                    continue
                sx, sy = stroke[0]
                # Pen-up flight of the visible sprite to the stroke origin
                flight_label = f"Draw {shape} ({s_idx + 1}/{total_strokes})" if total_strokes > 1 else f"Draw {shape}"
                self.fly_to(sx, sy, label=flight_label, duration=0.20)
                time.sleep(0.22)
                pts = [(int(round(p[0])), int(round(p[1]))) for p in stroke]
                if not target_h:
                    delivered = False
                    notes.append("UNDELIVERABLE: no target window resolved (refused; no physical-input fallback)")
                    break
                ok, note = hin.post_drag(target_h, pts[0][0], pts[0][1], pts[-1][0], pts[-1][1],
                                         path=pts if len(pts) > 2 else None,
                                         duration_s=max(0.15, len(pts) * 0.012),
                                         on_point=lambda x, y: (self.set_position(float(x), float(y)),
                                                                self._trail_points.append((float(x), float(y), time.time()))))
                delivered = delivered and ok
                notes.append(note)

                # (No second overlay: IntelligentMouse's "Hojaiga Drawing" is a full-screen window created on whatever
                #  thread draws first and nobody pumps its messages, so any other thread's GetWindowText/EnumWindows sweep
                #  of this process blocks on it - measured as a hang. The sprite's own glowing trail already shows the stroke.)
            time.sleep(0.3)
            after_all, _why2 = hin.capture_window(target_h) if target_h else (None, "no-target")
            n, bbox = hin.changed_pixels(before_all, after_all)
            effective = None if n < 0 else (n > 0)
            summary = notes[0] if notes else "no stroke"
            if delivered and effective is False:
                summary = "delivered but INEFFECTIVE: the window did not react to posted mouse input (no pixel changed)"
            self.last_stroke = {"delivered": delivered, "effective": effective, "changed_pixels": n, "bbox": bbox,
                                "note": summary, "strokes": total_strokes}
        finally:
            self._active_state = "ACTIVE"
            if hasattr(self, "shape"):
                self.shape.set_shape(old_shape)

    def get_position(self) -> Tuple[float, float]:
        """Get current virtual cursor position."""
        return (self._x, self._y)

    def destroy(self):
        """Destroy the overlay window and free GDI resources."""
        self.hide()
        if self._hwnd:
            ctypes.windll.user32.DestroyWindow(self._hwnd)
            self._hwnd = 0
        if getattr(self, "_hfont_badge", 0):        # the badge's one cached font (see _badge_font)
            ctypes.windll.gdi32.DeleteObject(self._hfont_badge)
            self._hfont_badge = 0
        for brush in [self._brush_cursor, self._brush_center]:
            if brush:
                ctypes.windll.gdi32.DeleteObject(brush)
        for pen in [self._pen_cursor, self._pen_trail, self._pen_ripple]:
            if pen:
                ctypes.windll.gdi32.DeleteObject(pen)
        VisualCursor._instance = None


# ─── Convenience functions ───

_default_cursor: Optional[VisualCursor] = None

def get_cursor() -> VisualCursor:
    global _default_cursor
    if _default_cursor is None:
        _default_cursor = VisualCursor()
    return _default_cursor


def for_agent(agent_id: str, agent_name: str = "", ttl: Optional[float] = None) -> "CursorSprite":
    """Get (or duplicate) a dedicated, colour-coded cursor for a temporary agent.
    Parallel agents each get their own visible cursor on one overlay surface."""
    c = get_cursor()
    spr = c.agent_cursor(agent_id, agent_name)
    if ttl is not None:
        spr._ttl = ttl
    return spr


def release_agent(agent_id: str) -> bool:
    """Retire a temporary agent's cursor when that agent finishes."""
    return get_cursor().remove_cursor(agent_id)

def show_cursor():
    get_cursor().show()

def hide_cursor():
    get_cursor().hide()

def click_visual(x: float, y: float, hwnd: Optional[int] = None):
    c = get_cursor()
    c.show()
    c.click_at(x, y, hwnd=hwnd)
    return c

def fly_visual(x: float, y: float, label: str = ""):
    c = get_cursor()
    c.show()
    c.fly_to(x, y, label=label)
    return c

def drag_visual(start_x: float, start_y: float, end_x: float, end_y: float,
                steps: int = 30, label: str = "Drag", physical: bool = False, hwnd: Optional[int] = None):
    c = get_cursor()
    c.drag_to(start_x, start_y, end_x, end_y, steps=steps, label=label, physical=physical, hwnd=hwnd)
    return c

def draw_shape_visual(shape: str, cx: float, cy: float, width: float = 150.0, height: float = 150.0,
                      steps: int = 50, label: str = "Drawing...", physical: bool = False, hwnd: Optional[int] = None):
    c = get_cursor()
    c.draw_shape(shape, cx, cy, width=width, height=height, steps=steps, label=label, physical=physical, hwnd=hwnd)
    return c

def move_visual(x: float, y: float, animate: bool = True):
    c = get_cursor()
    c.show()
    c.move_to(x, y, animate=animate)
    return c
