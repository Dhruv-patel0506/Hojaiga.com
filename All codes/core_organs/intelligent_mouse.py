"""
intelligent_mouse.py — Hojaiga Intelligent Mouse System

An AI-powered mouse that can:
- SEE: Capture and analyze any screen region
- DRAW: Trace lines, draw shapes, annotate on transparent overlay
- THINK: Understand context, decide best action
- ACT: Click, type, scroll, navigate, teach, explain
- LEARN: Remember patterns, improve over time
- AUTONOMOUS: Perform complex multi-step tasks from single command

Architecture:
  Screen Capture → VLM Analysis → AI Decision → Action Execution → Visual Feedback

Usage:
    mouse = IntelligentMouse()
    mouse.start()

    # Teach mode - explain what's on screen
    mouse.teach("What is happening in this video?")

    # Trace mode - follow a path
    mouse.trace_path([(100,200), (300,400), (500,600)])

    # Annotate mode - draw on screen
    mouse.annotate("circle", x=500, y=300, radius=50, color="red")

    # Autonomous mode - do complex task
    mouse.execute("open notepad, type hello, save as test.txt")
"""

from __future__ import annotations
import threading
import time
import math
import json
import logging
import base64
import io
import os
import sys
from typing import Optional, Tuple, Dict, Any, List, Callable
from enum import Enum

logger = logging.getLogger("hojaiga.intelligent_mouse")

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

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
    import win32process
    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False

if _HAS_CTYPES:
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
            ("hdc", ctypes.c_void_p),
            ("fErase", ctypes.c_int),
            ("rcPaint", wintypes.RECT),
            ("fRestore", ctypes.c_int),
            ("fIncUpdate", ctypes.c_int),
            ("rgbReserved", ctypes.c_byte * 32),
        ]

    class _BLENDFUNCTION(ctypes.Structure):
        _fields_ = [
            ("BlendOp", ctypes.c_byte),
            ("BlendFlags", ctypes.c_byte),
            ("SourceConstantAlpha", ctypes.c_byte),
            ("AlphaFormat", ctypes.c_byte),
        ]

    ctypes.windll.user32.DefWindowProcW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    ctypes.windll.user32.DefWindowProcW.restype = ctypes.c_void_p

    gdi32 = ctypes.windll.gdi32
    gdi32.MoveToEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    gdi32.MoveToEx.restype = wintypes.BOOL
    gdi32.LineTo.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.LineTo.restype = wintypes.BOOL
    gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.COLORREF]
    gdi32.CreatePen.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
    gdi32.CreateSolidBrush.restype = wintypes.HGDIOBJ
    gdi32.Polygon.argtypes = [wintypes.HDC, ctypes.c_void_p, ctypes.c_int]
    gdi32.Polygon.restype = wintypes.BOOL

try:
    from PIL import ImageGrab
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


class MouseMode(Enum):
    IDLE = "idle"
    SEEING = "seeing"
    DRAWING = "drawing"
    TRACING = "tracing"
    ANNOTATING = "annotating"
    TEACHING = "teaching"
    EXECUTING = "executing"
    FOLLOWING = "following"


class ActionPlan:
    """Structured action plan for autonomous execution."""

    def __init__(self, goal: str):
        self.goal = goal
        self.steps: List[Dict[str, Any]] = []
        self.current_step = 0
        self.context: Dict[str, Any] = {}
        self.completed = False
        self.failed = False
        self.error = ""

    def add_step(self, action: str, params: Dict[str, Any], description: str = ""):
        self.steps.append({
            "action": action,
            "params": params,
            "description": description,
            "status": "pending",
            "result": None,
        })

    def advance(self, result: Any = None):
        if self.current_step < len(self.steps):
            self.steps[self.current_step]["status"] = "completed"
            self.steps[self.current_step]["result"] = result
            self.current_step += 1
            if self.current_step >= len(self.steps):
                self.completed = True

    def fail(self, error: str):
        self.failed = True
        self.error = error
        if self.current_step < len(self.steps):
            self.steps[self.current_step]["status"] = "failed"

    @property
    def current_action(self) -> Optional[Dict[str, Any]]:
        if self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": self.steps,
            "current_step": self.current_step,
            "completed": self.completed,
            "failed": self.failed,
            "error": self.error,
        }


class ScreenAnalyzer:
    """Captures and analyzes screen content using VLM."""

    def __init__(self, gatekeeper_url: str = "http://127.0.0.1:11435",
                 secret: str = "339680"):
        self.gatekeeper_url = gatekeeper_url
        self.secret = secret

    def capture_screen(self, region: Optional[Tuple[int, int, int, int]] = None) -> Optional[str]:
        """Capture screen or region, return base64 PNG."""
        if not _HAS_PIL:
            return None
        try:
            if region:
                img = ImageGrab.grab(bbox=region)
            else:
                img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            logger.debug("[ScreenAnalyzer] Capture failed: %s", e)
            return None

    def capture_hwnd(self, hwnd: int) -> Optional[str]:
        """Capture a specific window by handle."""
        if not _HAS_PIL or not _HAS_WIN32:
            return None
        try:
            rect = win32gui.GetWindowRect(hwnd)
            if rect[2] > rect[0] and rect[3] > rect[1]:
                img = ImageGrab.grab(bbox=rect)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            logger.debug("[ScreenAnalyzer] HWND capture failed: %s", e)
        return None

    def analyze(self, image_b64: str, prompt: str, model: str = "minicpm-v:latest") -> str:
        """Send image + prompt to VLM via Gatekeeper."""
        import urllib.request
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt, "images": [image_b64]}
            ],
            "stream": False,
        }
        req = urllib.request.Request(
            f"{self.gatekeeper_url}/api/chat",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Hojaiga-Validation": self.secret
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
                return data.get("message", {}).get("content", "")
        except Exception as e:
            logger.debug("[ScreenAnalyzer] VLM query failed: %s", e)
            return ""

    def find_elements(self, image_b64: str) -> List[Dict[str, Any]]:
        """Detect clickable elements, text, and UI components in screenshot."""
        prompt = (
            "Analyze this screenshot. List ALL interactive elements you can see. "
            "For each element provide: name, type (button/text/link/icon/menu), "
            "approximate bounding box (x1,y1,x2,y2), and what it does. "
            "Return as JSON array: [{\"name\": \"...\", \"type\": \"...\", "
            "\"bbox\": [x1,y1,x2,y2], \"description\": \"...\"}]"
        )
        result = self.analyze(image_b64, prompt)
        try:
            import re
            m = re.search(r"\[.*\]", result, re.DOTALL)
            if m:
                return json.loads(m.group(0))
        except Exception:
            pass
        return []

    def understand_context(self, image_b64: str, task: str = "") -> Dict[str, Any]:
        """Deep understanding of what's on screen and what's happening."""
        prompt = (
            f"Analyze this screen in detail. Task context: {task or 'general observation'}. "
            "Provide:\n"
            "1. What application/window is active\n"
            "2. What content is visible (text, images, videos, UI elements)\n"
            "3. What state the application is in\n"
            "4. What actions are possible right now\n"
            "5. What would be the logical next step\n"
            "Return as JSON: {\"app\": \"...\", \"content\": \"...\", \"state\": \"...\", "
            "\"possible_actions\": [...], \"next_step\": \"...\"}"
        )
        result = self.analyze(image_b64, prompt)
        try:
            import re
            m = re.search(r"\{.*\}", result, re.DOTALL)
            if m:
                return json.loads(m.group(0))
        except Exception:
            pass
        return {"raw_response": result}


class DrawingEngine:
    """Transparent overlay for drawing shapes, lines, text on screen."""

    def __init__(self):
        self._hwnd: int = 0
        self._visible = False
        self._drawings: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._create_window()

    def _create_window(self):
        if not _HAS_CTYPES or not _HAS_WIN32:
            return

        hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)

        wc = _WNDCLASSEX()
        wc.cbSize = ctypes.sizeof(wc)
        wc.style = win32con.CS_HREDRAW | win32con.CS_VREDRAW
        self._wnd_proc_ref = _WNDPROC(self._wnd_proc)
        wc.lpfnWndProc = ctypes.cast(self._wnd_proc_ref, ctypes.c_void_p)
        wc.hInstance = hInstance
        wc.lpszClassName = "HojaigaDrawingOverlay"
        wc.hbrBackground = 0
        wc.hIcon = 0
        wc.hIconSm = 0
        wc.cbWndExtra = 0
        wc.cbClsExtra = 0
        wc.menuName = None
        wc.hCursor = 0

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
            "HojaigaDrawingOverlay",
            "Hojaiga Drawing",
            win32con.WS_POPUP,
            0, 0, screen_w, screen_h,
            0, 0, hInstance, None
        )

        if self._hwnd:
            ctypes.windll.user32.SetLayeredWindowAttributes(
                self._hwnd, 0x00000000, 255, win32con.LWA_COLORKEY
            )

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_PAINT:
            self._on_paint(hwnd)
            return 0
        try:
            return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        except Exception:
            return 0

    def _on_paint(self, hwnd):
        ps = _PAINTSTRUCT()
        hdc = ctypes.windll.user32.BeginPaint(hwnd, ctypes.byref(ps))

        sw = ps.rcPaint.right - ps.rcPaint.left
        sh = ps.rcPaint.bottom - ps.rcPaint.top
        if sw <= 0 or sh <= 0:
            ctypes.windll.user32.EndPaint(hwnd, ctypes.byref(ps))
            return

        hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc)
        hbmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc, sw, sh)
        ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)
        ctypes.windll.gdi32.PatBlt(hdc_mem, 0, 0, sw, sh, win32con.BLACKNESS)

        with self._lock:
            now = time.time()
            for drawing in self._drawings[:]:
                dtype = drawing.get("type")
                expires = drawing.get("expires", 0)
                if expires and now > expires:
                    self._drawings.remove(drawing)
                    continue

                color = drawing.get("color", 0x0000FF)  # BGR default blue
                pen = ctypes.windll.gdi32.CreatePen(0, drawing.get("width", 3), color)
                old_pen = ctypes.windll.gdi32.SelectObject(hdc_mem, pen)

                if dtype == "line":
                    x1, y1, x2, y2 = drawing["coords"]
                    ctypes.windll.gdi32.MoveToEx(hdc_mem, x1, y1, None)
                    ctypes.windll.gdi32.LineTo(hdc_mem, x2, y2)

                elif dtype == "circle":
                    cx, cy, r = drawing["center"], drawing["radius"]
                    brush = ctypes.windll.gdi32.CreateSolidBrush(drawing.get("fill_color", color))
                    old_brush = ctypes.windll.gdi32.SelectObject(hdc_mem, brush)
                    ctypes.windll.user32.Ellipse(hdc_mem, cx-r, cy-r, cx+r, cy+r)
                    ctypes.windll.gdi32.SelectObject(hdc_mem, old_brush)
                    ctypes.windll.gdi32.DeleteObject(brush)

                elif dtype == "rectangle":
                    x1, y1, x2, y2 = drawing["coords"]
                    brush = ctypes.windll.gdi32.CreateSolidBrush(drawing.get("fill_color", 0))
                    old_brush = ctypes.windll.gdi32.SelectObject(hdc_mem, brush)
                    ctypes.windll.user32.Rectangle(hdc_mem, x1, y1, x2, y2)
                    ctypes.windll.gdi32.SelectObject(hdc_mem, old_brush)
                    ctypes.windll.gdi32.DeleteObject(brush)

                elif dtype == "arrow":
                    x1, y1, x2, y2 = drawing["coords"]
                    ctypes.windll.gdi32.MoveToEx(hdc_mem, x1, y1, None)
                    ctypes.windll.gdi32.LineTo(hdc_mem, x2, y2)
                    # Arrowhead
                    angle = math.atan2(y2-y1, x2-x1)
                    arrow_len = 15
                    a1x = x2 - arrow_len * math.cos(angle - 0.4)
                    a1y = y2 - arrow_len * math.sin(angle - 0.4)
                    a2x = x2 - arrow_len * math.cos(angle + 0.4)
                    a2y = y2 - arrow_len * math.sin(angle + 0.4)
                    ctypes.windll.gdi32.MoveToEx(hdc_mem, x2, y2, None)
                    ctypes.windll.gdi32.LineTo(hdc_mem, int(a1x), int(a1y))
                    ctypes.windll.gdi32.MoveToEx(hdc_mem, x2, y2, None)
                    ctypes.windll.gdi32.LineTo(hdc_mem, int(a2x), int(a2y))

                elif dtype == "path":
                    points = drawing["points"]
                    if len(points) >= 2:
                        ctypes.windll.gdi32.MoveToEx(hdc_mem, int(points[0][0]), int(points[0][1]), None)
                        for px, py in points[1:]:
                            ctypes.windll.gdi32.LineTo(hdc_mem, int(px), int(py))

                elif dtype == "bezier_path":
                    points = drawing["points"]
                    if len(points) >= 2:
                        ctypes.windll.gdi32.MoveToEx(hdc_mem, int(points[0][0]), int(points[0][1]), None)
                        for px, py in points[1:]:
                            ctypes.windll.gdi32.LineTo(hdc_mem, int(px), int(py))

                elif dtype == "filled_polygon":
                    points = drawing["points"]
                    if len(points) >= 3:
                        fill = drawing.get("fill_color", 0x0088FF)
                        outline = drawing.get("outline_color", 0x000000)
                        owidth = drawing.get("outline_width", 2)
                        # Fill polygon
                        brush = ctypes.windll.gdi32.CreateSolidBrush(fill)
                        old_brush = ctypes.windll.gdi32.SelectObject(hdc_mem, brush)
                        outline_pen = ctypes.windll.gdi32.CreatePen(0, owidth, outline)
                        old_pen2 = ctypes.windll.gdi32.SelectObject(hdc_mem, outline_pen)
                        # Create point array for Polygon API
                        POINT_ARRAY = ctypes.wintypes.POINT * len(points)
                        pt_array = POINT_ARRAY(*[(int(p[0]), int(p[1])) for p in points])
                        ctypes.windll.gdi32.Polygon(hdc_mem, ctypes.byref(pt_array), len(points))
                        ctypes.windll.gdi32.SelectObject(hdc_mem, old_brush)
                        ctypes.windll.gdi32.SelectObject(hdc_mem, old_pen2)
                        ctypes.windll.gdi32.DeleteObject(brush)
                        ctypes.windll.gdi32.DeleteObject(outline_pen)

                elif dtype == "gradient_rect":
                    x1, y1, x2, y2 = drawing["coords"]
                    c1 = drawing.get("color_start", 0xFF0000)
                    c2 = drawing.get("color_end", 0x0000FF)
                    direction = drawing.get("direction", "horizontal")
                    # Approximate gradient with horizontal bands
                    steps = min(abs(y2 - y1) if direction == "vertical" else abs(x2 - x1), 50)
                    steps = max(steps, 1)
                    for i in range(steps):
                        t = i / steps
                        r = int(((c1 >> 16) & 0xFF) * (1 - t) + ((c2 >> 16) & 0xFF) * t)
                        g = int(((c1 >> 8) & 0xFF) * (1 - t) + ((c2 >> 8) & 0xFF) * t)
                        b = int((c1 & 0xFF) * (1 - t) + (c2 & 0xFF) * t)
                        band_color = (r << 16) | (g << 8) | b
                        pen = ctypes.windll.gdi32.CreatePen(0, 1, band_color)
                        old_p = ctypes.windll.gdi32.SelectObject(hdc_mem, pen)
                        if direction == "vertical":
                            yy = int(y1 + (y2 - y1) * t)
                            ctypes.windll.gdi32.MoveToEx(hdc_mem, x1, yy, None)
                            ctypes.windll.gdi32.LineTo(hdc_mem, x2, yy)
                        else:
                            xx = int(x1 + (x2 - x1) * t)
                            ctypes.windll.gdi32.MoveToEx(hdc_mem, xx, y1, None)
                            ctypes.windll.gdi32.LineTo(hdc_mem, xx, y2)
                        ctypes.windll.gdi32.SelectObject(hdc_mem, old_p)
                        ctypes.windll.gdi32.DeleteObject(pen)

                elif dtype == "dashed_line":
                    x1, y1, x2, y2 = drawing["coords"]
                    dash_len = drawing.get("dash_len", 10)
                    gap_len = drawing.get("gap_len", 6)
                    total = math.hypot(x2 - x1, y2 - y1)
                    if total < 1:
                        continue
                    dx = (x2 - x1) / total
                    dy = (y2 - y1) / total
                    pos = 0
                    drawing_dashes = True
                    while pos < total:
                        seg_len = dash_len if drawing_dashes else gap_len
                        end_pos = min(pos + seg_len, total)
                        if drawing_dashes:
                            sx = int(x1 + dx * pos)
                            sy = int(y1 + dy * pos)
                            ex = int(x1 + dx * end_pos)
                            ey = int(y1 + dy * end_pos)
                            ctypes.windll.gdi32.MoveToEx(hdc_mem, sx, sy, None)
                            ctypes.windll.gdi32.LineTo(hdc_mem, ex, ey)
                        pos = end_pos
                        drawing_dashes = not drawing_dashes

                elif dtype == "brush_stroke":
                    strokes = drawing.get("strokes", [])
                    for i in range(len(strokes) - 1):
                        x, y, w = strokes[i]
                        x2, y2, w2 = strokes[i + 1]
                        # Draw thick line segment with varying width
                        pen = ctypes.windll.gdi32.CreatePen(0, max(1, (w + w2) // 2), color)
                        old_p = ctypes.windll.gdi32.SelectObject(hdc_mem, pen)
                        ctypes.windll.gdi32.MoveToEx(hdc_mem, x, y, None)
                        ctypes.windll.gdi32.LineTo(hdc_mem, x2, y2)
                        ctypes.windll.gdi32.SelectObject(hdc_mem, old_p)
                        ctypes.windll.gdi32.DeleteObject(pen)

                elif dtype == "text":
                    x, y = drawing["position"]
                    text = drawing["text"]
                    ctypes.windll.user32.SetBkMode(hdc_mem, 1)  # TRANSPARENT
                    font_size = drawing.get("font_size", 16)
                    hfont = ctypes.windll.gdi32.CreateFontW(
                        font_size, 0, 0, 0, 400, 0, 0, 0,
                        1, 0, 0, 0, 0, "Segoe UI"
                    )
                    old_font = ctypes.windll.gdi32.SelectObject(hdc_mem, hfont)
                    ctypes.windll.user32.SetTextColor(hdc_mem, color)
                    ctypes.windll.user32.TextOutW(hdc_mem, x, y, text, len(text))
                    ctypes.windll.gdi32.SelectObject(hdc_mem, old_font)
                    ctypes.windll.gdi32.DeleteObject(hfont)

                ctypes.windll.gdi32.SelectObject(hdc_mem, old_pen)
                ctypes.windll.gdi32.DeleteObject(pen)

        blend = _BLENDFUNCTION(0, 0, 255, 0)
        ctypes.windll.user32.UpdateLayeredWindow(
            self._hwnd, 0, 0,
            ctypes.byref(wintypes.SIZE(sw, sh)),
            hdc_mem,
            ctypes.byref(wintypes.POINT(0, 0)),
            0, ctypes.byref(blend), 0x00000002
        )

        ctypes.windll.gdi32.DeleteObject(hbmp)
        ctypes.windll.gdi32.DeleteDC(hdc_mem)
        ctypes.windll.user32.EndPaint(hwnd, ctypes.byref(ps))

    def show(self):
        if self._hwnd:
            ctypes.windll.user32.ShowWindow(self._hwnd, win32con.SW_SHOW)
            self._visible = True

    def hide(self):
        if self._hwnd:
            ctypes.windll.user32.ShowWindow(self._hwnd, win32con.SW_HIDE)
            self._visible = False

    def clear(self):
        with self._lock:
            self._drawings.clear()
        self._repaint()

    def _repaint(self):
        if self._hwnd:
            ctypes.windll.user32.InvalidateRect(self._hwnd, None, 0)
            ctypes.windll.user32.UpdateWindow(self._hwnd)

    def draw_line(self, x1: int, y1: int, x2: int, y2: int,
                  color: int = 0x0000FF, width: int = 3, duration: float = 0):
        """Draw a line. duration=0 means permanent until cleared."""
        expires = time.time() + duration if duration > 0 else 0
        with self._lock:
            self._drawings.append({
                "type": "line", "coords": (x1, y1, x2, y2),
                "color": color, "width": width, "expires": expires
            })
        self._repaint()

    def draw_circle(self, cx: int, cy: int, radius: int,
                   color: int = 0x0000FF, fill_color: int = 0, width: int = 3, duration: float = 0):
        expires = time.time() + duration if duration > 0 else 0
        with self._lock:
            self._drawings.append({
                "type": "circle", "center": (cx, cy), "radius": radius,
                "color": color, "fill_color": fill_color, "width": width, "expires": expires
            })
        self._repaint()

    def draw_rectangle(self, x1: int, y1: int, x2: int, y2: int,
                      color: int = 0x0000FF, fill_color: int = 0, width: int = 3, duration: float = 0):
        expires = time.time() + duration if duration > 0 else 0
        with self._lock:
            self._drawings.append({
                "type": "rectangle", "coords": (x1, y1, x2, y2),
                "color": color, "fill_color": fill_color, "width": width, "expires": expires
            })
        self._repaint()

    def draw_arrow(self, x1: int, y1: int, x2: int, y2: int,
                  color: int = 0x0000FF, width: int = 3, duration: float = 0):
        expires = time.time() + duration if duration > 0 else 0
        with self._lock:
            self._drawings.append({
                "type": "arrow", "coords": (x1, y1, x2, y2),
                "color": color, "width": width, "expires": expires
            })
        self._repaint()

    def draw_path(self, points: List[Tuple[int, int]],
                 color: int = 0x0000FF, width: int = 3, duration: float = 0):
        expires = time.time() + duration if duration > 0 else 0
        with self._lock:
            self._drawings.append({
                "type": "path", "points": points,
                "color": color, "width": width, "expires": expires
            })
        self._repaint()

    def draw_text(self, x: int, y: int, text: str,
                 color: int = 0x00FFFF, font_size: int = 16, duration: float = 0):
        expires = time.time() + duration if duration > 0 else 0
        with self._lock:
            self._drawings.append({
                "type": "text", "position": (x, y), "text": text,
                "color": color, "font_size": font_size, "expires": expires
            })
        self._repaint()

    def highlight_region(self, x1: int, y1: int, x2: int, y2: int,
                        color: int = 0x0088FF, duration: float = 2.0):
        """Highlight a screen region with semi-transparent rectangle."""
        self.draw_rectangle(x1, y1, x2, y2, color=color,
                          fill_color=color, width=2, duration=duration)

    def trace_animation(self, points: List[Tuple[int, int]],
                       color: int = 0x00FF00, width: int = 3, speed: float = 0.02):
        """Animate a path being drawn point by point."""
        if len(points) < 2:
            return
        self.show()
        for i in range(len(points) - 1):
            self.draw_line(
                points[i][0], points[i][1],
                points[i+1][0], points[i+1][1],
                color=color, width=width, duration=5.0
            )
            time.sleep(speed)

    # ═══════════════════════════════════════════════════════════════════
    # ENHANCED DRAWING — Bezier curves, filled shapes, gradients,
    # dashed lines, brush strokes, reveal animations
    # ═══════════════════════════════════════════════════════════════════

    def draw_bezier_curve(self, control_points: List[Tuple[int, int]],
                          color: int = 0x0000FF, width: int = 3,
                          segments: int = 40, duration: float = 0):
        """Draw a smooth Bezier curve through control points using Catmull-Rom interpolation.
        control_points: at least 2 points defining the path.
        Segments controls smoothness (higher = smoother but slower)."""
        if len(control_points) < 2:
            return
        # Generate smooth points using Catmull-Rom spline
        smooth_pts = self._catmull_rom_spline(control_points, segments)
        expires = time.time() + duration if duration > 0 else 0
        with self._lock:
            self._drawings.append({
                "type": "bezier_path", "points": smooth_pts,
                "color": color, "width": width, "expires": expires
            })
        self._repaint()

    def draw_filled_shape(self, points: List[Tuple[int, int]],
                          fill_color: int = 0x0088FF, outline_color: int = 0x000000,
                          outline_width: int = 2, duration: float = 0):
        """Draw any polygon filled with solid color + outline."""
        if len(points) < 3:
            return
        expires = time.time() + duration if duration > 0 else 0
        with self._lock:
            self._drawings.append({
                "type": "filled_polygon", "points": points,
                "fill_color": fill_color, "outline_color": outline_color,
                "outline_width": outline_width, "expires": expires
            })
        self._repaint()

    def draw_gradient_rect(self, x1: int, y1: int, x2: int, y2: int,
                           color_start: int = 0xFF0000, color_end: int = 0x0000FF,
                           direction: str = "horizontal", duration: float = 0):
        """Draw a rectangle with linear gradient fill.
        direction: 'horizontal', 'vertical', or 'diagonal'."""
        expires = time.time() + duration if duration > 0 else 0
        with self._lock:
            self._drawings.append({
                "type": "gradient_rect", "coords": (x1, y1, x2, y2),
                "color_start": color_start, "color_end": color_end,
                "direction": direction, "expires": expires
            })
        self._repaint()

    def draw_dashed_line(self, x1: int, y1: int, x2: int, y2: int,
                         color: int = 0x0000FF, width: int = 2,
                         dash_len: int = 10, gap_len: int = 6, duration: float = 0):
        """Draw a dashed line with configurable dash/gap pattern."""
        expires = time.time() + duration if duration > 0 else 0
        with self._lock:
            self._drawings.append({
                "type": "dashed_line", "coords": (x1, y1, x2, y2),
                "color": color, "width": width,
                "dash_len": dash_len, "gap_len": gap_len, "expires": expires
            })
        self._repaint()

    def draw_brush_stroke(self, points: List[Tuple[int, int]],
                          color: int = 0x0000FF, base_width: int = 8,
                          brush_type: str = "round", duration: float = 0):
        """Draw a natural brush stroke with pressure simulation.
        brush_type: 'round', 'flat', 'calligraphy', 'spray'."""
        if len(points) < 2:
            return
        # Generate width-modulated points for natural look
        strokes = self._generate_brush_points(points, base_width, brush_type)
        expires = time.time() + duration if duration > 0 else 0
        with self._lock:
            self._drawings.append({
                "type": "brush_stroke", "strokes": strokes,
                "color": color, "expires": expires
            })
        self._repaint()

    def draw_reveal(self, draw_func, x: int, y: int, width: int, height: int,
                    animation_type: str = "expand", duration: float = 1.2,
                    easing: str = "ease_out_back"):
        """Animate a shape being revealed onto the screen with easing.
        Shapes start small/rough, then morph and expand into final form.
        animation_type: 'expand', 'fade_in', 'morph', 'slide_in', 'bounce_in'.
        easing: 'ease_out_back', 'ease_out_elastic', 'ease_out_bounce', 'ease_in_out'."""
        import threading as _threading
        def _animate():
            fps = 60
            frames = int(duration * fps)
            for frame in range(frames):
                t = frame / max(frames - 1, 1)
                # Apply easing
                eased_t = self._apply_easing(t, easing)
                # Calculate alpha and scale
                alpha = min(1.0, eased_t * 1.5)  # Fade in faster than scale
                scale = eased_t
                # Draw with current scale/alpha
                self._draw_reveal_frame(draw_func, x, y, width, height,
                                       scale, alpha, animation_type)
                time.sleep(1.0 / fps)
            # Final frame: full opacity, full scale
            self._draw_reveal_frame(draw_func, x, y, width, height,
                                   1.0, 1.0, animation_type)
        _threading.Thread(target=_animate, daemon=True).start()

    # ═══════════════════════════════════════════════════════════════════
    # INTERNAL HELPERS — Catmull-Rom, easing, brush generation
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _catmull_rom_spline(points: List[Tuple[int, int]], segments: int = 30) -> List[Tuple[int, int]]:
        """Generate smooth curve through points using Catmull-Rom spline interpolation."""
        if len(points) < 2:
            return points
        result = []
        # Extend with virtual points at start and end
        extended = [points[0]] + points + [points[-1]]
        for i in range(1, len(extended) - 2):
            p0 = extended[i - 1]
            p1 = extended[i]
            p2 = extended[i + 1]
            p3 = extended[i + 2]
            for t in range(segments + 1):
                t_f = t / segments
                t2 = t_f * t_f
                t3 = t2 * t_f
                x = 0.5 * ((2 * p1[0]) +
                           (-p0[0] + p2[0]) * t_f +
                           (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                           (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
                y = 0.5 * ((2 * p1[1]) +
                           (-p0[1] + p2[1]) * t_f +
                           (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                           (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
                result.append((int(x), int(y)))
        return result

    @staticmethod
    def _apply_easing(t: float, easing: str = "ease_out_back") -> float:
        """Apply easing function to parameter t (0..1)."""
        if easing == "ease_out_back":
            c1 = 1.70158
            c3 = c1 + 1
            return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)
        elif easing == "ease_out_elastic":
            c4 = (2 * math.pi) / 3
            if t == 0 or t == 1:
                return t
            return pow(2, -10 * t) * math.sin((t * 10 - 0.75) * c4) + 1
        elif easing == "ease_out_bounce":
            n1 = 7.5625
            d1 = 2.75
            if t < 1 / d1:
                return n1 * t * t
            elif t < 2 / d1:
                t -= 1.5 / d1
                return n1 * t * t + 0.75
            elif t < 2.5 / d1:
                t -= 2.25 / d1
                return n1 * t * t + 0.9375
            else:
                t -= 2.625 / d1
                return n1 * t * t + 0.984375
        elif easing == "ease_in_out":
            return 3 * t * t - 2 * t * t * t
        elif easing == "linear":
            return t
        else:
            return t

    @staticmethod
    def _generate_brush_points(points: List[Tuple[int, int]], base_width: int,
                                brush_type: str) -> List[Tuple[int, int, int]]:
        """Generate brush stroke points with variable width.
        Returns list of (x, y, width) tuples."""
        if len(points) < 2:
            return [(points[0][0], points[0][1], base_width)] if points else []
        result = []
        n = len(points)
        for i, (x, y) in enumerate(points):
            # Pressure simulation: taper at start and end
            progress = i / max(n - 1, 1)
            if brush_type == "round":
                # Bell curve pressure: thin at edges, thick in middle
                pressure = math.sin(progress * math.pi)
                w = max(1, int(base_width * (0.3 + 0.7 * pressure)))
            elif brush_type == "flat":
                w = base_width
            elif brush_type == "calligraphy":
                # Angle-based width variation
                if i < n - 1:
                    dx = points[i + 1][0] - x
                    dy = points[i + 1][1] - y
                    angle = math.atan2(dy, dx)
                    w = max(1, int(base_width * abs(math.sin(angle)) + 1))
                else:
                    w = max(1, int(base_width * 0.5))
            elif brush_type == "spray":
                import random
                w = max(1, int(base_width * (0.5 + random.random() * 0.5)))
            else:
                w = base_width
            result.append((x, y, w))
        return result

    def _draw_reveal_frame(self, draw_func, x: int, y: int, w: int, h: int,
                           scale: float, alpha: float, anim_type: str):
        """Draw one frame of a reveal animation."""
        # For now, use existing drawing methods with scale transform
        # The draw_func should accept (x, y, w, h, scale, alpha)
        try:
            draw_func(x, y, w, h, scale, alpha)
        except Exception:
            pass


class IntelligentMouse:
    """
    The fully autonomous intelligent mouse system.

    Combines screen analysis, drawing, clicking, typing, and AI decision-making
    into a single cohesive system that can see, think, draw, and act.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *a, **kw):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self.analyzer = ScreenAnalyzer()
        self.drawing = DrawingEngine()
        self.mode = MouseMode.IDLE
        self.current_plan: Optional[ActionPlan] = None
        self.memory: List[Dict[str, Any]] = []
        self.context_history: List[Dict[str, Any]] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Import virtual cursor for clicks
        try:
            from core_organs.visual_cursor import VisualCursor
            self.cursor = VisualCursor()
        except Exception:
            self.cursor = None

        logger.info("[IntelligentMouse] System initialized")

    def start(self):
        """Start the intelligent mouse system."""
        self._running = True
        self.drawing.show()
        if self.cursor:
            self.cursor.show()
        logger.info("[IntelligentMouse] System online")

    def stop(self):
        """Stop the intelligent mouse system."""
        self._running = False
        self.drawing.hide()
        if self.cursor:
            self.cursor.hide()
        logger.info("[IntelligentMouse] System offline")

    # ─── SEE: Capture and understand screen ───

    def see(self, region: Optional[Tuple[int, int, int, int]] = None,
            hwnd: int = 0, task: str = "") -> Dict[str, Any]:
        """Capture screen and understand what's happening."""
        self.mode = MouseMode.SEEING

        if hwnd:
            image_b64 = self.analyzer.capture_hwnd(hwnd)
        else:
            image_b64 = self.analyzer.capture_screen(region)

        if not image_b64:
            return {"error": "Failed to capture screen"}

        # Get deep understanding
        understanding = self.analyzer.understand_context(image_b64, task)

        # Find interactive elements
        elements = self.analyzer.find_elements(image_b64)

        result = {
            "understanding": understanding,
            "elements": elements,
            "element_count": len(elements),
            "timestamp": time.time(),
        }

        self.context_history.append(result)
        self.mode = MouseMode.IDLE
        return result

    # ─── DRAW: Transparent overlay drawing ───

    def draw_line(self, x1: int, y1: int, x2: int, y2: int,
                 color: str = "blue", width: int = 3, duration: float = 0):
        """Draw a line on the transparent overlay."""
        self.mode = MouseMode.DRAWING
        color_int = self._parse_color(color)
        self.drawing.draw_line(x1, y1, x2, y2, color=color_int, width=width, duration=duration)
        self.mode = MouseMode.IDLE

    def draw_circle(self, cx: int, cy: int, radius: int,
                   color: str = "blue", duration: float = 0):
        """Draw a circle on the transparent overlay."""
        self.mode = MouseMode.DRAWING
        color_int = self._parse_color(color)
        self.drawing.draw_circle(cx, cy, radius, color=color_int, duration=duration)
        self.mode = MouseMode.IDLE

    def draw_arrow(self, x1: int, y1: int, x2: int, y2: int,
                  color: str = "red", duration: float = 0):
        """Draw an arrow pointing from (x1,y1) to (x2,y2)."""
        self.mode = MouseMode.DRAWING
        color_int = self._parse_color(color)
        self.drawing.draw_arrow(x1, y1, x2, y2, color=color_int, duration=duration)
        self.mode = MouseMode.IDLE

    def annotate(self, text: str, x: int = 100, y: int = 100,
                color: str = "yellow", font_size: int = 18, duration: float = 5.0):
        """Draw text annotation on screen."""
        self.mode = MouseMode.ANNOTATING
        color_int = self._parse_color(color)
        self.drawing.draw_text(x, y, text, color=color_int, font_size=font_size, duration=duration)
        self.mode = MouseMode.IDLE

    def highlight(self, x1: int, y1: int, x2: int, y2: int,
                 color: str = "orange", duration: float = 2.0):
        """Highlight a region on screen."""
        self.mode = MouseMode.ANNOTATING
        color_int = self._parse_color(color)
        self.drawing.highlight_region(x1, y1, x2, y2, color=color_int, duration=duration)
        self.mode = MouseMode.IDLE

    def clear_drawings(self):
        """Clear all drawings from overlay."""
        self.drawing.clear()

    # ─── TRACE: Follow paths on screen ───

    def trace_path(self, points: List[Tuple[int, int]],
                  color: str = "green", speed: float = 0.02):
        """Trace a path on screen with animated line."""
        self.mode = MouseMode.TRACING
        color_int = self._parse_color(color)
        self.drawing.trace_animation(points, color=color_int, speed=speed)
        self.mode = MouseMode.IDLE

    def trace_from_image(self, image_path: str, origin: Tuple[int, int] = (100, 100),
                        scale: float = 1.0, color: str = "green"):
        """Extract contours from image and trace them on screen."""
        try:
            from core_organs.virtual_mouse_service import TraceAndVisionEngine
            contours = TraceAndVisionEngine.extract_contours_from_image(image_path)
            self.drawing.show()
            for contour in contours:
                scaled = [(int(origin[0] + p[0] * scale), int(origin[1] + p[1] * scale))
                         for p in contour]
                self.drawing.trace_animation(scaled, color=self._parse_color(color), speed=0.01)
        except Exception as e:
            logger.error("[IntelligentMouse] Trace from image failed: %s", e)

    # ─── TEACH: Explain and teach from screen ───

    def teach(self, question: str = "What is on screen?",
             annotate: bool = True) -> str:
        """Analyze screen and explain what's happening with optional annotations."""
        self.mode = MouseMode.TEACHING

        # Capture and analyze
        result = self.see(task=question)
        understanding = result.get("understanding", {})

        explanation = understanding.get("raw_response", "")
        if not explanation:
            explanation = json.dumps(understanding, indent=2)

        # Annotate screen if requested
        if annotate and result.get("elements"):
            self.drawing.show()
            for el in result["elements"][:5]:  # Top 5 elements
                bbox = el.get("bbox", [0, 0, 0, 0])
                if len(bbox) == 4 and all(b > 0 for b in bbox):
                    self.drawing.highlight_region(
                        bbox[0], bbox[1], bbox[2], bbox[3],
                        color=0x00FF00, duration=5.0
                    )
                    name = el.get("name", "")
                    if name:
                        self.drawing.draw_text(
                            bbox[0], bbox[1] - 20, name,
                            color=0x00FFFF, duration=5.0
                        )

        self.mode = MouseMode.IDLE
        return explanation

    def explain_region(self, x1: int, y1: int, x2: int, y2: int,
                      question: str = "What is this?") -> str:
        """Capture a specific region and explain it."""
        self.mode = MouseMode.TEACHING
        image_b64 = self.analyzer.capture_screen(region=(x1, y1, x2, y2))
        if not image_b64:
            return "Failed to capture region"

        explanation = self.analyzer.analyze(image_b64, question)

        # Highlight the region
        self.drawing.highlight_region(x1, y1, x2, y2, color=0x0088FF, duration=3.0)
        self.drawing.draw_text(x1, y1 - 25, explanation[:100], color=0x00FFFF, duration=5.0)

        self.mode = MouseMode.IDLE
        return explanation

    # ─── ACT: Perform actions autonomously ───

    def click_at(self, x: int, y: int, button: str = "left"):
        """Click at screen coordinates."""
        if self.cursor:
            self.cursor.click_at(x, y)
        # Also send the actual click
        try:
            from core_organs.organ_01_crewai_engine import _constrained_virtual_click
            _constrained_virtual_click(x, y)
        except Exception:
            pass

    def move_to(self, x: int, y: int, animate: bool = True):
        """Move cursor to position."""
        if self.cursor:
            self.cursor.move_to(x, y, animate=animate)

    def type_text(self, text: str):
        """Type text using virtual keyboard."""
        try:
            from core_organs.organ_01_crewai_engine import _last_launched_app
            hwnd = _last_launched_app.get("hwnd", 0) if _last_launched_app else 0
            if hwnd:
                import uiautomation as auto
                ctrl = auto.ControlFromHandle(hwnd)
                if ctrl:
                    # Find text area
                    for child in ctrl.GetChildren():
                        ctype = child.ControlTypeName or ""
                        if ctype in ("DocumentControl", "EditControl"):
                            vp = child.GetValuePattern()
                            if vp:
                                existing = vp.Value or ""
                                vp.SetValue(existing + text)
                                return
        except Exception:
            pass

    def press_key(self, key: str):
        """Press a keyboard key."""
        try:
            from core_organs.organ_01_crewai_engine import _last_launched_app
            hwnd = _last_launched_app.get("hwnd", 0) if _last_launched_app else 0
            if hwnd:
                ctypes.windll.user32.PostMessageW(hwnd, 0x0100, 0, 0)  # WM_KEYDOWN
        except Exception:
            pass

    # ─── AUTONOMOUS: Execute complex tasks ───

    def execute(self, command: str) -> str:
        """Execute a complex task autonomously from a single command."""
        self.mode = MouseMode.EXECUTING

        # Build action plan
        plan = ActionPlan(command)
        self.current_plan = plan

        # Analyze what needs to be done
        result = self.see(task=command)
        understanding = result.get("understanding", {})
        elements = result.get("elements", [])

        # Execute via CrewAI brain
        try:
            from core_organs.organ_01_brain import HojaigaBrain
            brain = HojaigaBrain()
            task_obj = {
                "objective": command,
                "task_id": f"mouse_{int(time.time())}"
            }
            brain_result = brain.compile_task(command, task_id=task_obj["task_id"])
            plan.advance(brain_result)
            self.mode = MouseMode.IDLE
            return json.dumps(brain_result, indent=2, default=str)
        except Exception as e:
            plan.fail(str(e))
            self.mode = MouseMode.IDLE
            return f"Execution failed: {e}"

    # ─── HELPER: Color parsing ───

    def _parse_color(self, color: str) -> int:
        """Parse color name to BGR integer for GDI."""
        colors = {
            "red": 0x0000FF,
            "green": 0x00FF00,
            "blue": 0xFF0000,
            "yellow": 0x00FFFF,
            "cyan": 0xFFFF00,
            "magenta": 0xFF00FF,
            "orange": 0x0088FF,
            "white": 0xFFFFFF,
            "black": 0x000000,
            "pink": 0x8080FF,
        }
        if isinstance(color, int):
            return color
        return colors.get(color.lower(), 0xFF0000)

    # ─── MEMORY: Learn from interactions ───

    def remember(self, action: str, result: Any, context: Dict[str, Any] = None):
        """Store an interaction in memory for learning."""
        self.memory.append({
            "action": action,
            "result": str(result)[:500],
            "context": context or {},
            "timestamp": time.time(),
        })
        # Feed to ML organ
        try:
            from core_organs.organ_ml import ml
            ml.feed_action(
                app_name="intelligent_mouse",
                element_name=action,
                action_type="mouse_action",
                success=True,
                visual_hint=str(result)[:200]
            )
        except Exception:
            pass

    def get_memory(self, last_n: int = 10) -> List[Dict[str, Any]]:
        """Get recent memory entries."""
        return self.memory[-last_n:]


# ─── Singleton access ───

_mouse: Optional[IntelligentMouse] = None

def get_mouse() -> IntelligentMouse:
    global _mouse
    if _mouse is None:
        _mouse = IntelligentMouse()
    return _mouse

def start_mouse():
    get_mouse().start()

def stop_mouse():
    get_mouse().stop()
