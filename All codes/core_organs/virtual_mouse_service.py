"""
virtual_mouse_service.py — Unified Intelligent Virtual Mouse & Multi-Cursor Engine

The complete autonomous mouse system. Works independently of physical mouse.
Can operate on minimized apps, draw on transparent overlay, think with AI, and act autonomously.

CAPABILITIES:
  - Background Operation: Click/type/scroll on MINIMIZED apps (no foreground steal)
  - Multi-Cursor: Spawn independent cursors for parallel tasks
  - Transparent Overlay: Draw shapes, lines, text, arrows on screen
  - AI Vision: See screen, understand context, find elements
  - Trace Engine: Follow paths, draw contours, annotate
  - Autonomous Execution: Single command → full task completion
  - Physical Mouse Safety: NEVER steals user's mouse or screen
  - 3D/Gaming: High-precision viewport, orbit, pan, aim

ARCHITECTURE:
  User Command → AI Brain → Action Queue → Background Dispatch → Visual Feedback
"""

from __future__ import annotations
import threading
import time
import queue
import logging
import math
import base64
import io
import json
import urllib.request
from typing import Optional, Tuple, Dict, Any, List, Union

logger = logging.getLogger("hojaiga.virtual_mouse")

# soft imports
try:
    import win32api, win32con, win32gui  # type: ignore
    _HAS_WIN32 = True
except Exception:
    _HAS_WIN32 = False

try:
    import ctypes
    _HAS_CTYPES = True
except Exception:
    _HAS_CTYPES = False

GATEKEEPER_URL = "http://127.0.0.1:11435"
GATEKEEPER_SECRET = "339680"
DEDICATED_VISION_MODEL = "minicpm-v:latest"  # 5.5GB, excellent OCR, fits in 6GB VRAM


class MouseAIBrain:
    """Dedicated AI intelligence engine wired to Gatekeeper using minicpm-v (5.5GB).
    Protects automation from 429 external rate limits and empowers mouse to make its own decisions.
    """

    def __init__(self, gatekeeper_url: str = GATEKEEPER_URL, secret: str = GATEKEEPER_SECRET, model: str = DEDICATED_VISION_MODEL):
        self.gatekeeper_url = gatekeeper_url
        self.secret = secret
        self.model = model

    def query(self, prompt: str, image_b64: Optional[str] = None, timeout: float = 30.0) -> str:
        """Direct query to the dedicated local vision/text model on Gatekeeper."""
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    **({"images": [image_b64]} if image_b64 else {})
                }
            ],
            "stream": False,
        }
        req = urllib.request.Request(
            f"{self.gatekeeper_url}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-Hojaiga-Validation": self.secret},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
                return data.get("message", {}).get("content", "")
        except Exception as e:
            logger.debug("[MouseAIBrain] gatekeeper call failed: %s", e)
            return ""

    def analyze_screen_for_action(self, image_b64: str, task_context: str) -> Dict[str, Any]:
        """Analyze viewport image and return autonomous mouse target and action suggestion."""
        prompt = (
            f"You are the autonomous virtual mouse intelligence. Task context: {task_context}. "
            "Inspect the screen, identify the primary target coordinate or UI button to interact with, "
            "and output JSON with: {'target_x': int, 'target_y': int, 'action': 'click'|'drag'|'orbit'|'aim', 'reason': str}."
        )
        response = self.query(prompt, image_b64=image_b64, timeout=30.0)
        try:
            # extract JSON
            import re
            m = re.search(r"\{.*\}", response, re.DOTALL)
            if m:
                return json.loads(m.group(0))
        except Exception:
            pass
        return {"raw_response": response, "action": "inspect"}


class VirtualCursorHandle:
    """An independent intelligent virtual cursor handle assigned to an agent/subagent, viewport, or game context."""

    def __init__(self, service: VirtualMouseService, cursor_id: str, agent_name: str = "general"):
        self._service = service
        self.cursor_id = cursor_id
        self.agent_name = agent_name
        self._pos: Tuple[float, float] = (0.0, 0.0)
        self.memory: Dict[str, Any] = {}
        self.active_goal: Optional[str] = None
        self.ai = service.ai_brain

    @property
    def position(self) -> Tuple[float, float]:
        return self._pos

    def assign_goal(self, goal: str):
        self.active_goal = goal

    def move_to(self, x: float, y: float, session_id: Optional[str] = None, hwnd: Optional[int] = None, surface: str = "auto"):
        self._pos = (float(x), float(y))
        self._service.move(x, y, session_id=session_id, hwnd=hwnd, surface=surface, cursor_id=self.cursor_id)

    def click(self, x: Optional[float] = None, y: Optional[float] = None, button: str = "left", session_id: Optional[str] = None, hwnd: Optional[int] = None, surface: str = "auto"):
        if x is not None and y is not None:
            self._pos = (float(x), float(y))
        self._service.click(self._pos[0], self._pos[1], button=button, session_id=session_id, hwnd=hwnd, surface=surface, cursor_id=self.cursor_id)
        self._report_to_ml("click", success=True, metadata={"button": button, "x": self._pos[0], "y": self._pos[1]})

    def double_click(self, x: Optional[float] = None, y: Optional[float] = None, session_id: Optional[str] = None, hwnd: Optional[int] = None, surface: str = "auto"):
        if x is not None and y is not None:
            self._pos = (float(x), float(y))
        self.click(session_id=session_id, hwnd=hwnd, surface=surface)
        time.sleep(0.05)
        self.click(session_id=session_id, hwnd=hwnd, surface=surface)

    def drag_to(self, ex: float, ey: float, button: str = "left", session_id: Optional[str] = None, hwnd: Optional[int] = None, steps: int = 20, surface: str = "auto"):
        sx, sy = self._pos
        self._service.drag(sx, sy, ex, ey, button=button, session_id=session_id, hwnd=hwnd, steps=steps, surface=surface, cursor_id=self.cursor_id)
        self._pos = (float(ex), float(ey))
        self._report_to_ml("drag", success=True, metadata={"start": (sx, sy), "end": (ex, ey), "button": button})

    # High-Performance 3D Space & Gaming (Blender, Maya, 3D CAD, FPS viewports)
    def orbit_3d(self, delta_x: float, delta_y: float, hwnd: Optional[int] = None, steps: int = 15):
        """Orbit in 3D viewport (typically MMB drag in Blender)."""
        sx, sy = self._pos
        ex, ey = sx + delta_x, sy + delta_y
        self.drag_to(ex, ey, button="middle", hwnd=hwnd, steps=steps)

    def pan_3d(self, delta_x: float, delta_y: float, hwnd: Optional[int] = None, steps: int = 15):
        """Pan in 3D viewport (typically Shift + MMB drag in Blender)."""
        self.orbit_3d(delta_x, delta_y, hwnd=hwnd, steps=steps)

    def aim_relative(self, dx: int, dy: int, click_after: bool = False, button: str = "left", hwnd: Optional[int] = None):
        """Dispatches raw relative mouse motion delta (dx, dy).
        Essential for 3D FPS camera turns and unbounded 3D manipulation where cursor is centered/locked.
        """
        self._service.relative_move(dx, dy, hwnd=hwnd, cursor_id=self.cursor_id)
        self._pos = (self._pos[0] + dx, self._pos[1] + dy)
        if click_after:
            self.click(button=button, hwnd=hwnd)

    def trace_path(self, points: List[Tuple[float, float]], hwnd: Optional[int] = None, speed: float = 0.01):
        """Follow a custom line or geometric trajectory accurately."""
        if not points:
            return
        self.move_to(points[0][0], points[0][1], hwnd=hwnd)
        for pt in points[1:]:
            self.move_to(pt[0], pt[1], hwnd=hwnd)
            time.sleep(speed)
        self._report_to_ml("trace_path", success=True, metadata={"num_points": len(points)})

    def draw_contours(self, contours: List[List[Tuple[float, float]]], origin: Tuple[float, float] = (100.0, 100.0), scale: float = 1.0, hwnd: Optional[int] = None, speed: float = 0.005):
        """Draws physical stroke contours stroke-by-stroke onto MS Paint, Photoshop, or web canvas.
        Performs genuine mouse drag (LBUTTONDOWN -> continuous MOUSEMOVE -> LBUTTONUP) for each contour stroke.
        This provides real human-like drawing/sketching without physical cursor takeover.
        """
        ox, oy = origin
        total_strokes = len(contours)
        drawn_points = 0

        for stroke_idx, stroke in enumerate(contours):
            if not stroke or len(stroke) < 2:
                continue
            # Position cursor at first point
            start_x = ox + stroke[0][0] * scale
            start_y = oy + stroke[0][1] * scale
            self.move_to(start_x, start_y, hwnd=hwnd)
            time.sleep(0.01)

            # Pen down
            self._service._q.put({
                "type": "mousePressed",
                "x": start_x,
                "y": start_y,
                "button": "left",
                "session_id": None,
                "hwnd": hwnd,
                "surface": "desktop" if hwnd else "auto",
                "cursor_id": self.cursor_id
            })

            # Draw trajectory
            for pt in stroke[1:]:
                cur_x = ox + pt[0] * scale
                cur_y = oy + pt[1] * scale
                self._pos = (cur_x, cur_y)
                self._service._q.put({
                    "type": "mouseMoved",
                    "x": cur_x,
                    "y": cur_y,
                    "button": "left",
                    "session_id": None,
                    "hwnd": hwnd,
                    "surface": "desktop" if hwnd else "auto",
                    "cursor_id": self.cursor_id
                })
                drawn_points += 1
                if speed > 0:
                    time.sleep(speed)

            # Pen up
            end_x = ox + stroke[-1][0] * scale
            end_y = oy + stroke[-1][1] * scale
            self._service._q.put({
                "type": "mouseReleased",
                "x": end_x,
                "y": end_y,
                "button": "left",
                "session_id": None,
                "hwnd": hwnd,
                "surface": "desktop" if hwnd else "auto",
                "cursor_id": self.cursor_id
            })
            time.sleep(0.02)

        self._report_to_ml("draw_contours", success=True, metadata={"strokes": total_strokes, "points": drawn_points})
        return {"strokes_drawn": total_strokes, "points": drawn_points}

    def think_and_act(self, image_b64: str, context: str = "") -> Dict[str, Any]:
        """Autonomous loop: Cursor visually inspects its viewport via its dedicated AI brain,
        determines the target coordinate, acts on it, and reports feedback.
        """
        full_context = f"{self.active_goal or ''} | {context}"
        decision = self.ai.analyze_screen_for_action(image_b64, full_context)
        act = decision.get("action")
        tx = decision.get("target_x")
        ty = decision.get("target_y")

        if tx is not None and ty is not None:
            if act == "click":
                self.move_to(tx, ty)
                self.click()
            elif act == "drag":
                self.drag_to(tx, ty)
            elif act == "orbit":
                self.orbit_3d(tx - self._pos[0], ty - self._pos[1])
        return decision

    def _report_to_ml(self, action: str, success: bool, metadata: Optional[Dict[str, Any]] = None):
        """Self-learning loop: reports action and context back to OrganML."""
        try:
            from organ_ml import ml
            ml.feed_action(
                app_name="virtual_cursor",
                element_name=f"{self.cursor_id}_{action}",
                action_type=action,
                success=success,
                visual_hint=str(metadata or {}),
                tab=self.agent_name,
                group_location=self.active_goal or "general",
            )
        except Exception:
            pass


class TraceAndVisionEngine:
    """Detects, traces, and classifies shapes, lines, or contours from screen regions."""

    @staticmethod
    def identify_shape(points: List[Tuple[float, float]]) -> Dict[str, Any]:
        """Analyze a list of 2D points to detect shape geometry, aspect ratio, and type."""
        if len(points) < 2:
            return {"shape": "point", "confidence": 0.5, "length": 0.0}

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        w = max_x - min_x
        h = max_y - min_y

        total_length = 0.0
        for i in range(len(points) - 1):
            dx = points[i+1][0] - points[i][0]
            dy = points[i+1][1] - points[i][1]
            total_length += math.hypot(dx, dy)

        # Closed loop check
        start_end_dist = math.hypot(points[-1][0] - points[0][0], points[-1][1] - points[0][1])
        is_closed = start_end_dist < max(15.0, total_length * 0.08)

        # Classify
        if not is_closed:
            direct_dist = math.hypot(points[-1][0] - points[0][0], points[-1][1] - points[0][1])
            linearity = direct_dist / max(total_length, 1e-5)
            if linearity > 0.90:
                shape = "straight_line"
            else:
                shape = "curved_line"
            confidence = 0.85
        else:
            aspect = w / max(h, 1e-5)
            if 0.85 <= aspect <= 1.15:
                shape = "circle_or_square"
                confidence = 0.80
            else:
                shape = "rectangle_or_ellipse"
                confidence = 0.75

        return {
            "shape": shape,
            "is_closed": is_closed,
            "bounds": {"x": min_x, "y": min_y, "width": w, "height": h},
            "length": round(total_length, 2),
            "confidence": confidence,
        }

    @staticmethod
    def extract_contours_from_image(image_path: str, max_points: int = 1200) -> List[List[Tuple[float, float]]]:
        """Extracts physical stroke trajectories from an image (e.g. Ganesha murti, icon, sketch)
        using edge detection (Canny) and contour approximation. Enables actual mouse drawing in MS Paint/canvas.
        """
        try:
            import cv2
            img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                return []
            # Edge detection
            edges = cv2.Canny(img, threshold1=50, threshold2=150)
            contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_TC89_KCOS)
            
            trajectories = []
            for cnt in contours:
                if len(cnt) < 3:
                    continue
                # simplify contour to preserve smooth hand drawing strokes
                epsilon = 0.005 * cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, epsilon, False)
                pts = [(float(pt[0][0]), float(pt[0][1])) for pt in approx]
                if pts:
                    trajectories.append(pts)
            return trajectories
        except Exception as e:
            logger.debug("[TraceAndVisionEngine] contour extraction error: %s", e)
            return []

    @staticmethod
    def extract_contours_from_b64(image_b64: str) -> List[List[Tuple[float, float]]]:
        """Extracts drawing trajectories directly from a base64 encoded image."""
        try:
            import cv2
            import numpy as np
            raw_bytes = base64.b64decode(image_b64)
            nparr = np.frombuffer(raw_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            if img is None:
                return []
            edges = cv2.Canny(img, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_TC89_KCOS)
            trajectories = []
            for cnt in contours:
                if len(cnt) < 3:
                    continue
                epsilon = 0.005 * cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, epsilon, False)
                pts = [(float(pt[0][0]), float(pt[0][1])) for pt in approx]
                if pts:
                    trajectories.append(pts)
            return trajectories
        except Exception as e:
            logger.debug("[TraceAndVisionEngine] b64 contour error: %s", e)
            return []

    @staticmethod
    def extract_contours_ultra_res(image_path: str, detail_level: str = "ultra", max_dim: int = 800) -> List[List[Tuple[float, float]]]:
        """High-resolution multi-scale contour extraction with CLAHE, bilateral filter,
        fused Canny/Sobel, and morphological thinning for complex photos.
        """
        try:
            from core_organs.organ_10_extended_capabilities import AutonomousPaintingEngine
            res = AutonomousPaintingEngine.extract_high_res_contours(image_path, detail_level=detail_level, max_canvas_dim=max_dim)
            all_strokes = []
            for layer in ["outer_silhouette", "interior_anatomy", "fine_textures", "shading_hatching"]:
                for stroke in res["layers"].get(layer, []):
                    all_strokes.append([(float(x), float(y)) for x, y in stroke])
            return all_strokes
        except Exception as e:
            logger.debug("[TraceAndVisionEngine] ultra res error: %s", e)
            return TraceAndVisionEngine.extract_contours_from_image(image_path)



def _flash_desktop_indicator(x: int, y: int):
    """Render a transient visible neon click ring on the desktop at (x, y) without stealing focus."""
    if not _HAS_WIN32:
        return
    def _draw():
        try:
            hdc = win32gui.GetDC(0)
            if hdc:
                pen = win32gui.CreatePen(win32con.PS_SOLID, 2, win32api.RGB(0, 255, 255))
                old_pen = win32gui.SelectObject(hdc, pen)
                brush = win32gui.GetStockObject(win32con.NULL_BRUSH)
                old_brush = win32gui.SelectObject(hdc, brush)
                for r in (8, 14, 20):
                    win32gui.Ellipse(hdc, x - r, y - r, x + r, y + r)
                    time.sleep(0.03)
                win32gui.SelectObject(hdc, old_pen)
                win32gui.SelectObject(hdc, old_brush)
                win32gui.DeleteObject(pen)
                win32gui.ReleaseDC(0, hdc)
                win32gui.InvalidateRect(0, (x - 25, y - 25, x + 25, y + 25), True)
        except Exception:
            pass
    threading.Thread(target=_draw, daemon=True).start()


class VirtualMouseService:
    """Singleton daemon — multi-cursor virtual mouse service with dedicated AI brain."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *a, **kw):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self._q: queue.Queue = queue.Queue()
        self._pos: Dict[str, Tuple[float, float]] = {}  # cursor_id or session_id -> (x,y)
        self._cursors: Dict[str, VirtualCursorHandle] = {}
        self.vision = TraceAndVisionEngine()
        self.ai_brain = MouseAIBrain()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cdp_invoker = None  # set via attach_cdp

    def spawn(self, cursor_id: str, agent_name: str = "general") -> VirtualCursorHandle:
        """Spawn or retrieve an independent virtual cursor instance for an agent/subagent."""
        with self._lock:
            if cursor_id not in self._cursors:
                self._cursors[cursor_id] = VirtualCursorHandle(self, cursor_id, agent_name)
            return self._cursors[cursor_id]

    def list_cursors(self) -> List[str]:
        return list(self._cursors.keys())

    def attach_cdp(self, invoker):
        """Wire CDP invoker for web surfaces (Input.dispatchMouseEvent)."""
        self._cdp_invoker = invoker

    def start(self):
        if self._running:
            return
        self._running = True
        try:
            from core_organs.visual_cursor import get_cursor
            get_cursor().show()
            get_cursor().set_state("ACTIVE")
        except Exception:
            pass
        self._thread = threading.Thread(target=self._loop, daemon=True, name="virtual-mouse-daemon")
        self._thread.start()
        logger.info("[VirtualMouse] daemon online — GUI + web ready with local AI Brain")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)

    def _loop(self):
        while self._running:
            try:
                job = self._q.get(timeout=0.1)
                self._execute(job)
            except queue.Empty:
                continue
            except Exception as e:
                logger.debug("mouse loop %s", e)

    def _execute(self, job: Dict[str, Any]):
        surface = job.get("surface", "auto")
        job_type = job.get("type", "")
        cursor_id = job.get("cursor_id", "default")
        session = job.get("session_id")
        hwnd = job.get("hwnd")

        # Relative delta move (used in 3D cameras and FPS games)
        if job_type == "relativeMove":
            dx = job.get("dx", 0)
            dy = job.get("dy", 0)
            if hwnd and _HAS_WIN32:
                cur_x, cur_y = self._pos.get(cursor_id, (0.0, 0.0))
                new_x, new_y = cur_x + dx, cur_y + dy
                self._pos[cursor_id] = (new_x, new_y)
                lparam = win32api.MAKELONG(int(new_x), int(new_y))
                try:
                    win32gui.SendMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
                except Exception:
                    pass
            else:
                cur_x, cur_y = self._pos.get(cursor_id, (0.0, 0.0))
                self._pos[cursor_id] = (cur_x + dx, cur_y + dy)
            return

        x, y = job["x"], job["y"]
        self._pos[cursor_id] = (x, y)

        if surface == "auto":
            surface = "web" if session and self._cdp_invoker else "desktop"

        if surface == "web" and self._cdp_invoker and session:
            # CDP virtual
            import asyncio
            btn = job.get("button", "left")
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    self._cdp_invoker(
                        session,
                        "Input.dispatchMouseEvent",
                        {
                            "type": job_type,
                            "x": x,
                            "y": y,
                            "button": btn,
                            "clickCount": job.get("clickCount", 1),
                        },
                    )
                )
            except Exception as e:
                logger.debug("cdp dispatch %s", e)
            self._pos[session] = (x, y)
        else:
            # Desktop virtual — SendMessage background (no physical cursor steal)
            if hwnd and _HAS_WIN32:
                lparam = win32api.MAKELONG(int(x), int(y))
                btn = job.get("button", "left")
                if btn == "middle":
                    down_msg = win32con.WM_MBUTTONDOWN
                    up_msg = win32con.WM_MBUTTONUP
                    wparam = win32con.MK_MBUTTON
                elif btn == "right":
                    down_msg = win32con.WM_RBUTTONDOWN
                    up_msg = win32con.WM_RBUTTONUP
                    wparam = win32con.MK_RBUTTON
                else:
                    down_msg = win32con.WM_LBUTTONDOWN
                    up_msg = win32con.WM_LBUTTONUP
                    wparam = win32con.MK_LBUTTON

                msg_map = {
                    "mouseMoved": win32con.WM_MOUSEMOVE,
                    "mousePressed": down_msg,
                    "mouseReleased": up_msg,
                }
                msg = msg_map.get(job_type, win32con.WM_MOUSEMOVE)
                pw = wparam if job_type == "mousePressed" else 0

                # Flash visual cursor indicator for automated desktop clicks
                if job_type == "mousePressed":
                    _flash_desktop_indicator(int(x), int(y))

                try:
                    win32gui.SendMessage(hwnd, msg, pw, lparam)
                except Exception:
                    pass


    # Public API
    def move(self, x: float, y: float, session_id: Optional[str] = None, hwnd: Optional[int] = None, surface: str = "auto", cursor_id: str = "default"):
        self._pos[cursor_id] = (x, y)
        self._q.put({"type": "mouseMoved", "x": x, "y": y, "session_id": session_id, "hwnd": hwnd, "surface": surface, "cursor_id": cursor_id})

    def relative_move(self, dx: int, dy: int, hwnd: Optional[int] = None, cursor_id: str = "default"):
        self._q.put({"type": "relativeMove", "dx": dx, "dy": dy, "hwnd": hwnd, "cursor_id": cursor_id})

    def click(self, x: float, y: float, button: str = "left", session_id: Optional[str] = None, hwnd: Optional[int] = None, surface: str = "auto", cursor_id: str = "default"):
        self._pos[cursor_id] = (x, y)
        self._q.put({"type": "mousePressed", "x": x, "y": y, "button": button, "clickCount": 1, "session_id": session_id, "hwnd": hwnd, "surface": surface, "cursor_id": cursor_id})
        time.sleep(0.02)
        self._q.put({"type": "mouseReleased", "x": x, "y": y, "button": button, "clickCount": 1, "session_id": session_id, "hwnd": hwnd, "surface": surface, "cursor_id": cursor_id})

    def drag(self, sx: float, sy: float, ex: float, ey: float, button: str = "left", session_id: Optional[str] = None, hwnd: Optional[int] = None, steps: int = 20, surface: str = "auto", cursor_id: str = "default"):
        self._pos[cursor_id] = (sx, sy)
        self._q.put({"type": "mousePressed", "x": sx, "y": sy, "button": button, "session_id": session_id, "hwnd": hwnd, "surface": surface, "cursor_id": cursor_id})
        for i in range(steps):
            x = sx + (ex - sx) * i / steps
            y = sy + (ey - sy) * i / steps
            self._pos[cursor_id] = (x, y)
            self._q.put({"type": "mouseMoved", "x": x, "y": y, "button": button, "session_id": session_id, "hwnd": hwnd, "surface": surface, "cursor_id": cursor_id})
            time.sleep(0.01)
        self._pos[cursor_id] = (ex, ey)
        self._q.put({"type": "mouseReleased", "x": ex, "y": ey, "button": button, "session_id": session_id, "hwnd": hwnd, "surface": surface, "cursor_id": cursor_id})

    def stretch(self, cursor1_id: str, cursor2_id: str, p1_start: Tuple[float, float], p1_end: Tuple[float, float],
                p2_start: Tuple[float, float], p2_end: Tuple[float, float], session_id: Optional[str] = None, hwnd: Optional[int] = None, steps: int = 20):
        """Stretch operation — 2 cursors moving apart simultaneously."""
        c1 = self.spawn(cursor1_id)
        c2 = self.spawn(cursor2_id)
        c1.move_to(p1_start[0], p1_start[1], session_id=session_id, hwnd=hwnd)
        c2.move_to(p2_start[0], p2_start[1], session_id=session_id, hwnd=hwnd)

        t1 = threading.Thread(target=c1.drag_to, args=(p1_end[0], p1_end[1], "left", session_id, hwnd, steps))
        t2 = threading.Thread(target=c2.drag_to, args=(p2_end[0], p2_end[1], "left", session_id, hwnd, steps))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    def narrow(self, cursor1_id: str, cursor2_id: str, p1_start: Tuple[float, float], p1_end: Tuple[float, float],
               p2_start: Tuple[float, float], p2_end: Tuple[float, float], session_id: Optional[str] = None, hwnd: Optional[int] = None, steps: int = 20):
        """Narrow operation — 2 cursors moving toward each other simultaneously."""
        self.stretch(cursor1_id, cursor2_id, p1_start, p1_end, p2_start, p2_end, session_id=session_id, hwnd=hwnd, steps=steps)

    def is_online(self) -> bool:
        return self._running and (self._thread.is_alive() if self._thread else False)

    # ══════════════════════════════════════════════════════════════
    # INTELLIGENT MOUSE: Background, Overlay, AI Vision, Autonomous
    # ══════════════════════════════════════════════════════════════

    def background_click(self, hwnd: int, x: int, y: int, button: str = "left"):
        """Click on a MINIMIZED app — no foreground steal, no cursor movement."""
        import ctypes.wintypes
        try:
            rect = win32gui.GetWindowRect(hwnd)
            client_pt = ctypes.wintypes.POINT(x, y)
            ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(client_pt))
            lparam = (client_pt.y << 16) | (client_pt.x & 0xFFFF)

            msg_map = {
                ("left", "down"): (0x0201, 0x0001),   # WM_LBUTTONDOWN
                ("left", "up"):   (0x0202, 0),         # WM_LBUTTONUP
                ("right", "down"): (0x0204, 0x0002),   # WM_RBUTTONDOWN
                ("right", "up"):   (0x0205, 0),         # WM_RBUTTONUP
            }
            down_msg, wparam = msg_map.get((button, "down"), (0x0201, 0x0001))
            up_msg, _ = msg_map.get((button, "up"), (0x0202, 0))

            win32gui.PostMessage(hwnd, down_msg, wparam, lparam)
            time.sleep(0.02)
            win32gui.PostMessage(hwnd, up_msg, 0, lparam)

            # Show visual indicator at click position
            _flash_desktop_indicator(x, y)
            logger.info("[VM] Background click on hwnd=%d at (%d,%d)", hwnd, x, y)
            return True
        except Exception as e:
            logger.debug("[VM] Background click failed: %s", e)
            return False

    def background_type(self, hwnd: int, text: str):
        """Type text into a MINIMIZED app via UIA — no foreground steal."""
        try:
            import uiautomation as auto
            ctrl = auto.ControlFromHandle(hwnd)
            if not ctrl:
                return False

            for child in ctrl.GetChildren():
                ctype = child.ControlTypeName or ""
                if ctype in ("DocumentControl", "EditControl"):
                    # Try ValuePattern first (works minimized)
                    try:
                        vp = child.GetValuePattern()
                        if vp:
                            existing = vp.Value or ""
                            vp.SetValue(existing + text)
                            logger.info("[VM] Background type via UIA: %d chars into hwnd=%d", len(text), hwnd)
                            return True
                    except Exception:
                        pass
                    # Try LegacyIAccessible
                    try:
                        li = child.GetLegacyIAccessiblePattern()
                        if li:
                            existing = li.GetValue() or ""
                            li.SetValue(existing + text)
                            return True
                    except Exception:
                        pass
            return False
        except Exception as e:
            logger.debug("[VM] Background type failed: %s", e)
            return False

    def background_key(self, hwnd: int, key: str):
        """Send keyboard shortcut to MINIMIZED app via PostMessage."""
        VK_MAP = {
            "ctrl": 0x11, "alt": 0x12, "shift": 0x10,
            "enter": 0x0D, "tab": 0x09, "escape": 0x1B,
            "backspace": 0x08, "delete": 0x2E, "space": 0x20,
            "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
        }
        for c in range(ord('A'), ord('Z') + 1):
            VK_MAP[chr(c).lower()] = c
        for d in range(0, 10):
            VK_MAP[str(d)] = 0x30 + d

        key_lower = key.lower().strip()
        parts = [p.strip() for p in key_lower.split("+")]

        def _send_vk(vk, up=False):
            msg = 0x0101 if up else 0x0100  # WM_KEYUP / WM_KEYDOWN
            win32gui.PostMessage(hwnd, msg, vk, 0)
            time.sleep(0.02)

        if len(parts) == 1:
            vk = VK_MAP.get(parts[0])
            if vk is not None:
                _send_vk(vk)
                _send_vk(vk, up=True)
                return True
        elif len(parts) == 2:
            mod_vk = VK_MAP.get(parts[0])
            key_vk = VK_MAP.get(parts[1])
            if mod_vk and key_vk:
                _send_vk(mod_vk)
                _send_vk(key_vk)
                _send_vk(key_vk, up=True)
                _send_vk(mod_vk, up=True)
                return True
        elif len(parts) == 3:
            m1_vk = VK_MAP.get(parts[0])
            m2_vk = VK_MAP.get(parts[1])
            key_vk = VK_MAP.get(parts[2])
            if all([m1_vk, m2_vk, key_vk]):
                _send_vk(m1_vk)
                _send_vk(m2_vk)
                _send_vk(key_vk)
                _send_vk(key_vk, up=True)
                _send_vk(m2_vk, up=True)
                _send_vk(m1_vk, up=True)
                return True
        return False

    def background_scroll(self, hwnd: int, delta: int = -3):
        """Scroll in a MINIMIZED app via PostMessage WM_MOUSEWHEEL."""
        WM_MOUSEWHEEL = 0x020A
        lparam = (0 << 16) | 0  # center of client area
        wparam = (delta << 16) | 0
        try:
            win32gui.PostMessage(hwnd, WM_MOUSEWHEEL, wparam, lparam)
            return True
        except Exception:
            return False

    # ─── Overlay Drawing (Transparent) ───

    def draw_on_screen(self, drawing_type: str, **kwargs):
        """Draw shapes on transparent overlay. Types: line, circle, arrow, text, rectangle, highlight, path."""
        try:
            from core_organs.visual_cursor import VisualCursor
            vc = VisualCursor()
            vc.show()

            if drawing_type == "line":
                vc.drawing.draw_line(
                    kwargs["x1"], kwargs["y1"], kwargs["x2"], kwargs["y2"],
                    color=kwargs.get("color", 0x0000FF),
                    width=kwargs.get("width", 3),
                    duration=kwargs.get("duration", 0)
                )
            elif drawing_type == "circle":
                vc.drawing.draw_circle(
                    kwargs["cx"], kwargs["cy"], kwargs.get("radius", 50),
                    color=kwargs.get("color", 0x0000FF),
                    duration=kwargs.get("duration", 0)
                )
            elif drawing_type == "arrow":
                vc.drawing.draw_arrow(
                    kwargs["x1"], kwargs["y1"], kwargs["x2"], kwargs["y2"],
                    color=kwargs.get("color", 0x0000FF),
                    duration=kwargs.get("duration", 0)
                )
            elif drawing_type == "text":
                vc.drawing.draw_text(
                    kwargs["x"], kwargs["y"], kwargs.get("text", ""),
                    color=kwargs.get("color", 0x00FFFF),
                    font_size=kwargs.get("font_size", 16),
                    duration=kwargs.get("duration", 0)
                )
            elif drawing_type == "rectangle":
                vc.drawing.draw_rectangle(
                    kwargs["x1"], kwargs["y1"], kwargs["x2"], kwargs["y2"],
                    color=kwargs.get("color", 0x0000FF),
                    fill_color=kwargs.get("fill_color", 0),
                    duration=kwargs.get("duration", 0)
                )
            elif drawing_type == "highlight":
                vc.drawing.highlight_region(
                    kwargs["x1"], kwargs["y1"], kwargs["x2"], kwargs["y2"],
                    color=kwargs.get("color", 0x0088FF),
                    duration=kwargs.get("duration", 2.0)
                )
            elif drawing_type == "path":
                vc.drawing.draw_path(
                    kwargs.get("points", []),
                    color=kwargs.get("color", 0x00FF00),
                    duration=kwargs.get("duration", 0)
                )
            elif drawing_type == "clear":
                vc.drawing.clear()
            return True
        except Exception as e:
            logger.debug("[VM] Draw failed: %s", e)
            return False

    # ─── Screen Analysis (AI Vision) ───

    def see_screen(self, hwnd: int = 0, region: tuple = None, task: str = "") -> dict:
        """Capture and analyze screen using VLM. Returns understanding + elements."""
        try:
            from PIL import ImageGrab
            import io, base64

            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                img = ImageGrab.grab(bbox=rect)
            elif region:
                img = ImageGrab.grab(bbox=region)
            else:
                img = ImageGrab.grab()

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            image_b64 = base64.b64encode(buf.getvalue()).decode()

            # Query VLM
            import urllib.request
            prompt = (
                f"Analyze this screen. Task: {task or 'general observation'}. "
                "List all interactive elements (buttons, text, links) with their approximate positions. "
                "What app is this? What state? What actions are possible?"
            )
            payload = {
                "model": "minicpm-v:latest",
                "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
                "stream": False,
            }
            req = urllib.request.Request(
                f"{GATEKEEPER_URL}/api/chat",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "X-Hojaiga-Validation": GATEKEEPER_SECRET},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
                analysis = data.get("message", {}).get("content", "")

            return {
                "analysis": analysis,
                "image_b64": image_b64,
                "hwnd": hwnd,
                "region": region,
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.debug("[VM] Screen analysis failed: %s", e)
            return {"error": str(e)}

    def find_clickable(self, hwnd: int = 0) -> list:
        """Find all clickable elements on screen with coordinates."""
        result = self.see_screen(hwnd=hwnd, task="find all clickable buttons and elements")
        analysis = result.get("analysis", "")
        # Try to parse element list from VLM response
        try:
            import re
            m = re.search(r"\[.*\]", analysis, re.DOTALL)
            if m:
                return json.loads(m.group(0))
        except Exception:
            pass
        return [{"raw_analysis": analysis}]

    # ─── Autonomous Execution ───

    def autonomous_click(self, hwnd: int, element_name: str):
        """Find element by name on screen and click it — fully autonomous."""
        result = self.see_screen(hwnd=hwnd, task=f"find the '{element_name}' button or element")
        analysis = result.get("analysis", "")
        # Parse approximate coordinates from VLM response
        try:
            import re
            # Look for coordinate patterns like "(x, y)" or "at x,y"
            coords = re.findall(r'[\(\[]?\s*(\d{2,4})\s*[,\s]\s*(\d{2,4})\s*[\)\]]?', analysis)
            if coords:
                x, y = int(coords[0][0]), int(coords[0][1])
                self.background_click(hwnd, x, y)
                return {"success": True, "x": x, "y": y, "element": element_name}
        except Exception:
            pass
        return {"success": False, "analysis": analysis}

    def autonomous_task(self, command: str) -> dict:
        """Execute a complex task autonomously from a single command string."""
        try:
            from core_organs.organ_01_brain import HojaigaBrain
            brain = HojaigaBrain()
            result = brain.compile_task(command, task_id=f"mouse_auto_{int(time.time())}")
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Teach / Explain ───

    def teach(self, question: str = "What is on screen?", hwnd: int = 0,
              annotate: bool = True) -> str:
        """Analyze screen and explain with optional annotations."""
        result = self.see_screen(hwnd=hwnd, task=question)
        analysis = result.get("analysis", "")

        if annotate and analysis:
            self.draw_on_screen("text", x=50, y=50, text=analysis[:200],
                              color=0x00FFFF, font_size=14, duration=8.0)

        return analysis

    def explain_region(self, x1: int, y1: int, x2: int, y2: int,
                      question: str = "What is this?") -> str:
        """Capture region, explain it, highlight it."""
        result = self.see_screen(region=(x1, y1, x2, y2), task=question)
        analysis = result.get("analysis", "")

        self.draw_on_screen("highlight", x1=x1, y1=y1, x2=x2, y2=y2,
                          color=0x0088FF, duration=3.0)
        self.draw_on_screen("text", x=x1, y=y1-25, text=analysis[:150],
                          color=0x00FFFF, duration=5.0)

        return analysis

    # ─── Memory / Learning ───

    def remember(self, action: str, result: Any, context: dict = None):
        """Store interaction for learning."""
        if not hasattr(self, '_memory'):
            self._memory = []
        self._memory.append({
            "action": action,
            "result": str(result)[:500],
            "context": context or {},
            "timestamp": time.time(),
        })
        # Feed to ML organ
        try:
            from core_organs.organ_ml import ml
            ml.feed_action(
                app_name="virtual_mouse",
                element_name=action,
                action_type="intelligent_action",
                success=True,
                visual_hint=str(result)[:200]
            )
        except Exception:
            pass

    def get_memory(self, last_n: int = 10) -> list:
        if not hasattr(self, '_memory'):
            self._memory = []
        return self._memory[-last_n:]


# global singleton — import anywhere, always online
virtual_mouse = VirtualMouseService()
virtual_mouse.start()
