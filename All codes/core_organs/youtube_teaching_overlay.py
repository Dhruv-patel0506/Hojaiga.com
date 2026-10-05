"""
youtube_teaching_overlay.py — YouTube Video Teaching Overlay System

Captures a YouTube video frame, extracts diagrams/shapes, traces them
on a transparent overlay ON TOP of the paused video, adds labels
and annotations, and provides a teaching explanation.

Pipeline:
  1. Open YouTube video → pause it
  2. Capture paused frame (CDP screenshot)
  3. VLM analyzes the frame → identifies shapes, labels, context
  4. Extract contours from frame → geometric primitives
  5. Draw traced shapes on transparent overlay (on top of video)
  6. Add text labels, numbers, arrows to the diagram
  7. Provide teaching explanation with transcript context

Usage:
    overlay = YouTubeTeachingOverlay()
    overlay.start("https://www.youtube.com/watch?v=...")
    # User sees paused video with traced diagram + labels + explanation
    overlay.stop()
"""

from __future__ import annotations
import threading
import time
import json
import base64
import io
import os
import logging
import tempfile
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path

logger = logging.getLogger("hojaiga.youtube_overlay")

# ── Lazy imports ──────────────────────────────────────────────
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

try:
    from PIL import ImageGrab, Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False


class YouTubeTeachingOverlay:
    """
    Full pipeline: YouTube video → pause → capture frame → analyze with VLM →
    extract shapes → trace on overlay → add labels → teach explanation.
    """

    def __init__(self):
        self._drawing_engine = None
        self._analyzer = None
        self._frame_b64: Optional[str] = None
        self._frame_path: Optional[str] = None
        self._vlm_analysis: str = ""
        self._shapes: List[Dict] = []
        self._labels: List[Dict] = []
        self._explanation: str = ""
        self._transcript: str = ""
        self._video_title: str = ""
        self._overlay_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        logger.info("[YouTubeOverlay] System initialized")

    # ═══════════════════════════════════════════════════════════
    # STEP 1: Open & Pause YouTube Video
    # ═══════════════════════════════════════════════════════════

    def open_and_pause(self, video_url: str) -> bool:
        """
        Navigate Chrome to YouTube video and pause it.
        Returns True if successful.
        """
        try:
            from core_organs.lead_extractor import (
                send_cdp_navigate, send_cdp_js, send_cdp_click_coordinates,
                ensure_organ19_running
            )

            # Ensure Chrome CDP is running
            if not ensure_organ19_running(timeout=10):
                logger.warning("[YouTubeOverlay] Organ 19 not running, attempting to start...")
                # Try launching Chrome directly
                self._launch_chrome_for_video(video_url)
                time.sleep(5)
            else:
                # Navigate to video
                logger.info("[YouTubeOverlay] Navigating to: %s", video_url)
                if not send_cdp_navigate(video_url, timeout=30):
                    logger.error("[YouTubeOverlay] Navigation failed")
                    return False

            # Wait for video to load
            logger.info("[YouTubeOverlay] Waiting for video to load...")
            time.sleep(4)

            # Pause the video using JavaScript
            pause_js = """
            (() => {
                const video = document.querySelector('video');
                if (video) {
                    video.pause();
                    return {paused: true, duration: video.duration, currentTime: video.currentTime};
                }
                return {paused: false};
            })()
            """
            result = send_cdp_js(pause_js, timeout=10)
            if isinstance(result, dict) and result.get("paused"):
                logger.info("[YouTubeOverlay] Video paused at %.1fs (duration: %.1fs)",
                           result.get("currentTime", 0), result.get("duration", 0))
            else:
                # Fallback: press Space to pause
                logger.info("[YouTubeOverlay] JS pause failed, pressing Space...")
                self._press_key_via_cdp("Space")
                time.sleep(1)

            # Get video title
            title_js = """
            (() => {
                const title = document.querySelector('h1.ytd-watch-metadata yt-formatted-string');
                return title ? title.textContent : document.title;
            })()
            """
            title_result = send_cdp_js(title_js, timeout=5)
            if isinstance(title_result, str):
                self._video_title = title_result
            elif isinstance(title_result, dict):
                self._video_title = title_result.get("value", "")
            else:
                self._video_title = str(title_result) if title_result else ""

            logger.info("[YouTubeOverlay] Video title: %s", self._video_title[:80])
            return True

        except Exception as e:
            logger.error("[YouTubeOverlay] open_and_pause failed: %s", e)
            return False

    def _launch_chrome_for_video(self, url: str):
        """Launch Chrome directly with the video URL."""
        import subprocess
        try:
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            subprocess.Popen([
                chrome_path,
                "--remote-debugging-port=0",
                "--no-first-run",
                "--no-default-browser-check",
                url
            ], cwd=os.path.dirname(chrome_path))
            logger.info("[YouTubeOverlay] Launched Chrome with URL")
        except Exception as e:
            logger.error("[YouTubeOverlay] Chrome launch failed: %s", e)

    def _press_key_via_cdp(self, key: str):
        """Press a key via CDP."""
        try:
            from core_organs.lead_extractor import send_cdp_js
            js = f"""
            (() => {{
                document.dispatchEvent(new KeyboardEvent('keydown', {{key: '{key}', code: '{key}', keyCode: 32, which: 32}}));
                document.dispatchEvent(new KeyboardEvent('keyup', {{key: '{key}', code: '{key}', keyCode: 32, which: 32}}));
            }})()
            """
            send_cdp_js(js, timeout=5)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    # STEP 2: Capture Paused Frame
    # ═══════════════════════════════════════════════════════════

    def capture_frame(self) -> Optional[str]:
        """
        Capture the current browser viewport (paused video frame).
        Returns base64-encoded JPEG image.
        """
        try:
            from core_organs.lead_extractor import send_cdp_screenshot
            logger.info("[YouTubeOverlay] Capturing video frame...")
            self._frame_b64 = send_cdp_screenshot(format="jpeg", quality=90, timeout=20)

            if self._frame_b64:
                # Save to temp file for contour extraction
                self._frame_path = os.path.join(tempfile.gettempdir(), "hojaiga_yt_frame.jpg")
                with open(self._frame_path, "wb") as f:
                    f.write(base64.b64decode(self._frame_b64))
                logger.info("[YouTubeOverlay] Frame captured: %s (%d bytes)",
                           self._frame_path, len(self._frame_b64))
                return self._frame_b64
            else:
                # Fallback: capture screen region where browser is
                logger.warning("[YouTubeOverlay] CDP screenshot failed, trying PIL capture...")
                return self._capture_screen_fallback()

        except Exception as e:
            logger.error("[YouTubeOverlay] capture_frame failed: %s", e)
            return self._capture_screen_fallback()

    def _capture_screen_fallback(self) -> Optional[str]:
        """Fallback: capture full screen with PIL."""
        if not _HAS_PIL:
            return None
        try:
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            self._frame_b64 = base64.b64encode(buf.getvalue()).decode()
            self._frame_path = os.path.join(tempfile.gettempdir(), "hojaiga_yt_frame.jpg")
            img.save(self._frame_path, "JPEG", quality=90)
            logger.info("[YouTubeOverlay] Fallback capture: %s", self._frame_path)
            return self._frame_b64
        except Exception as e:
            logger.error("[YouTubeOverlay] Fallback capture failed: %s", e)
            return None

    # ═══════════════════════════════════════════════════════════
    # STEP 3: VLM Analysis of Frame
    # ═══════════════════════════════════════════════════════════

    def analyze_frame(self, topic_hint: str = "") -> str:
        """
        Send the captured frame to VLM for analysis.
        Identifies shapes, labels, text, and context in the diagram.
        """
        if not self._frame_b64:
            logger.error("[YouTubeOverlay] No frame to analyze")
            return ""

        try:
            from core_organs.intelligent_mouse import ScreenAnalyzer
            analyzer = ScreenAnalyzer()

            prompt = (
                "You are analyzing a paused educational YouTube video frame for teaching. "
                "Provide a DETAILED analysis:\n\n"
                "1. DIAGRAM SHAPES: List every geometric shape visible (triangles, circles, "
                "rectangles, lines, arrows, curves, angles). For each shape, describe:\n"
                "   - Type (triangle, circle, line, angle, etc.)\n"
                "   - Approximate pixel coordinates of key vertices/center\n"
                "   - Color and line style\n\n"
                "2. TEXT LABELS: List every text label, number, letter visible on the diagram.\n"
                "   For each: exact text, approximate position (x, y), font size estimate.\n\n"
                "3. DIAGRAM STRUCTURE: How are the shapes connected? What does the overall\n"
                "   diagram represent? (e.g., right triangle with altitude, circle with inscribed\n"
                "   polygon, coordinate graph, etc.)\n\n"
                "4. TEACHING CONTEXT: What concept is being explained? What would a teacher\n"
                "   say about this diagram?\n\n"
                "Return as JSON:\n"
                "{\n"
                '  "shapes": [{"type": "...", "vertices": [[x,y], ...], "color": "...", "label": "..."}],\n'
                '  "labels": [{"text": "...", "position": [x, y], "size": "..."}],\n'
                '  "structure": "description of diagram layout",\n'
                '  "concept": "what concept this teaches",\n'
                '  "teaching_script": "what the teacher would explain"\n'
                "}"
            )

            if topic_hint:
                prompt += f"\n\nVideo topic context: {topic_hint}"

            self._vlm_analysis = analyzer.analyze(self._frame_b64, prompt, model="minicpm-v:latest")
            logger.info("[YouTubeOverlay] VLM analysis: %d chars", len(self._vlm_analysis))

            # Parse JSON response
            try:
                import re
                m = re.search(r"\{.*\}", self._vlm_analysis, re.DOTALL)
                if m:
                    parsed = json.loads(m.group(0))
                    self._shapes = parsed.get("shapes", [])
                    self._labels = parsed.get("labels", [])
                    logger.info("[YouTubeOverlay] Parsed %d shapes, %d labels",
                               len(self._shapes), len(self._labels))
            except (json.JSONDecodeError, Exception) as e:
                logger.warning("[YouTubeOverlay] JSON parse failed: %s", e)

            return self._vlm_analysis

        except Exception as e:
            logger.error("[YouTubeOverlay] analyze_frame failed: %s", e)
            return ""

    # ═══════════════════════════════════════════════════════════
    # STEP 4: Extract Contours from Frame
    # ═══════════════════════════════════════════════════════════

    def extract_contours(self, detail_level: str = "standard") -> List[List[Tuple[int, int]]]:
        """
        Extract geometric contours/shapes from the captured frame
        using OpenCV edge detection and contour finding.
        """
        if not self._frame_path or not os.path.exists(self._frame_path):
            logger.error("[YouTubeOverlay] No frame available for contour extraction")
            return []

        if not _HAS_CV2:
            logger.warning("[YouTubeOverlay] OpenCV not available, using VLM-parsed shapes only")
            return []

        try:
            from core_organs.virtual_mouse_service import TraceAndVisionEngine
            contours = TraceAndVisionEngine.extract_contours_from_image(
                self._frame_path, max_points=800
            )
            logger.info("[YouTubeOverlay] Extracted %d contours from frame", len(contours))

            # Classify each contour
            for i, contour in enumerate(contours):
                if len(contour) >= 3:
                    shape_info = TraceAndVisionEngine.identify_shape(contour)
                    logger.debug("[YouTubeOverlay] Contour %d: %s (confidence: %.2f)",
                                i, shape_info.get("shape"), shape_info.get("confidence", 0))

            return contours

        except Exception as e:
            logger.error("[YouTubeOverlay] extract_contours failed: %s", e)
            return []

    # ═══════════════════════════════════════════════════════════
    # STEP 5: Draw Traced Diagram on Overlay
    # ═══════════════════════════════════════════════════════════

    def trace_on_overlay(self, contours: List[List[Tuple[int, int]]],
                         color: int = 0x00FF00, width: int = 3,
                         animate: bool = True, duration: float = 15.0) -> bool:
        """
        Draw the extracted contours on a transparent overlay
        ON TOP of the paused YouTube video.
        """
        try:
            from core_organs.intelligent_mouse import DrawingEngine

            if self._drawing_engine is None:
                self._drawing_engine = DrawingEngine()

            self._drawing_engine.show()

            if animate:
                # Animate each contour being drawn
                for i, contour in enumerate(contours):
                    if self._stop_event.is_set():
                        return False
                    if len(contour) < 2:
                        continue

                    # Color-code different contours
                    contour_colors = [0x00FF00, 0xFF6600, 0x00CCFF, 0xFFFF00, 0xFF00FF, 0x00FFFF]
                    c = contour_colors[i % len(contour_colors)]

                    # Animate drawing this contour point by point
                    for j in range(len(contour) - 1):
                        if self._stop_event.is_set():
                            return False
                        self._drawing_engine.draw_line(
                            int(contour[j][0]), int(contour[j][1]),
                            int(contour[j+1][0]), int(contour[j+1][1]),
                            color=c, width=width, duration=duration
                        )
                        if animate:
                            time.sleep(0.01)  # Small delay for animation
                    logger.debug("[YouTubeOverlay] Drew contour %d (%d points)", i, len(contour))
            else:
                # Draw all contours instantly
                for i, contour in enumerate(contours):
                    if len(contour) < 2:
                        continue
                    contour_colors = [0x00FF00, 0xFF6600, 0x00CCFF, 0xFFFF00, 0xFF00FF, 0x00FFFF]
                    c = contour_colors[i % len(contour_colors)]

                    points = [(int(p[0]), int(p[1])) for p in contour]
                    if len(points) >= 3:
                        self._drawing_engine.draw_filled_shape(
                            points, fill_color=0, outline_color=c, outline_width=width,
                            duration=duration
                        )
                    else:
                        for j in range(len(points) - 1):
                            self._drawing_engine.draw_line(
                                points[j][0], points[j][1],
                                points[j+1][0], points[j+1][1],
                                color=c, width=width, duration=duration
                            )

            logger.info("[YouTubeOverlay] Drew %d contours on overlay", len(contours))
            return True

        except Exception as e:
            logger.error("[YouTubeOverlay] trace_on_overlay failed: %s", e)
            return False

    # ═══════════════════════════════════════════════════════════
    # STEP 6: Add Labels, Numbers, Arrows
    # ═══════════════════════════════════════════════════════════

    def add_labels(self, labels: Optional[List[Dict]] = None,
                   duration: float = 20.0) -> int:
        """
        Add text labels, numbers, letters to the traced diagram.
        Each label has text, position [x, y], and optional size.
        Returns count of labels drawn.
        """
        if labels is None:
            labels = self._labels

        if not labels:
            logger.info("[YouTubeOverlay] No labels to draw")
            return 0

        try:
            from core_organs.intelligent_mouse import DrawingEngine

            if self._drawing_engine is None:
                self._drawing_engine = DrawingEngine()

            self._drawing_engine.show()
            drawn = 0

            for label in labels:
                if self._stop_event.is_set():
                    break

                text = label.get("text", "")
                pos = label.get("position", [0, 0])
                size_str = label.get("size", "medium")

                if not text or len(pos) < 2:
                    continue

                x, y = int(pos[0]), int(pos[1])

                # Map size string to font size
                size_map = {"small": 12, "medium": 16, "large": 20, "xlarge": 28}
                font_size = size_map.get(size_str, 16)

                # Draw text with background highlight
                # Draw background rectangle for readability
                text_width = len(text) * (font_size // 2 + 2)
                self._drawing_engine.draw_rectangle(
                    x - 4, y - 2, x + text_width + 4, y + font_size + 4,
                    color=0x000000, fill_color=0x000000, width=1, duration=duration
                )

                # Draw text in bright color
                self._drawing_engine.draw_text(
                    x, y, text,
                    color=0xFFFFFF, font_size=font_size, duration=duration
                )

                drawn += 1
                logger.debug("[YouTubeOverlay] Drew label: '%s' at (%d, %d)", text, x, y)

            logger.info("[YouTubeOverlay] Drew %d labels on overlay", drawn)
            return drawn

        except Exception as e:
            logger.error("[YouTubeOverlay] add_labels failed: %s", e)
            return 0

    def add_own_diagram(self, diagram_type: str = "right_triangle",
                        labels: Optional[Dict[str, str]] = None,
                        offset_x: int = 0, offset_y: int = 0,
                        scale: float = 1.0, duration: float = 25.0) -> bool:
        """
        Draw OUR OWN diagram on the overlay — not just tracing from the video,
        but creating a clean, labeled version for teaching.

        diagram_type: "right_triangle", "circle", "angle", "coordinate_axes", "parallel_lines"
        labels: {"A": "vertex label", "B": "...", "side_ab": "3", "angle_alpha": "90°"}
        """
        try:
            from core_organs.intelligent_mouse import DrawingEngine

            if self._drawing_engine is None:
                self._drawing_engine = DrawingEngine()

            self._drawing_engine.show()

            if diagram_type == "right_triangle":
                return self._draw_right_triangle(
                    self._drawing_engine, labels or {},
                    offset_x, offset_y, scale, duration
                )
            elif diagram_type == "circle":
                return self._draw_circle_diagram(
                    self._drawing_engine, labels or {},
                    offset_x, offset_y, scale, duration
                )
            elif diagram_type == "angle":
                return self._draw_angle_diagram(
                    self._drawing_engine, labels or {},
                    offset_x, offset_y, scale, duration
                )
            elif diagram_type == "coordinate_axes":
                return self._draw_coordinate_axes(
                    self._drawing_engine, labels or {},
                    offset_x, offset_y, scale, duration
                )
            else:
                logger.warning("[YouTubeOverlay] Unknown diagram type: %s", diagram_type)
                return False

        except Exception as e:
            logger.error("[YouTubeOverlay] add_own_diagram failed: %s", e)
            return False

    def _draw_right_triangle(self, engine, labels: Dict[str, str],
                             ox: int, oy: int, scale: float, dur: float) -> bool:
        """Draw a labeled right triangle for Pythagoras theorem teaching."""
        # Triangle vertices (scaled and offset)
        A = (int(ox + 100 * scale), int(oy + 250 * scale))   # Right angle vertex
        B = (int(ox + 400 * scale), int(oy + 250 * scale))   # Bottom right
        C = (int(ox + 100 * scale), int(oy + 50 * scale))    # Top left

        # Draw triangle edges with different colors
        engine.draw_line(A[0], A[1], B[0], B[1], color=0x00CCFF, width=3, duration=dur)  # base
        engine.draw_line(A[0], A[1], C[0], C[1], color=0x00CCFF, width=3, duration=dur)  # height
        engine.draw_line(B[0], B[1], C[0], C[1], color=0xFF6600, width=3, duration=dur)  # hypotenuse

        # Draw right angle marker
        marker_size = int(20 * scale)
        engine.draw_line(A[0] + marker_size, A[1], A[0] + marker_size, A[1] - marker_size,
                        color=0xFFFF00, width=2, duration=dur)
        engine.draw_line(A[0] + marker_size, A[1] - marker_size, A[0], A[1] - marker_size,
                        color=0xFFFF00, width=2, duration=dur)

        # Add vertex labels
        label_a = labels.get("A", "A")
        label_b = labels.get("B", "B")
        label_c = labels.get("C", "C")
        engine.draw_text(A[0] - 30, A[1] + 10, label_a, color=0xFFFFFF, font_size=18, duration=dur)
        engine.draw_text(B[0] + 10, B[1] + 10, label_b, color=0xFFFFFF, font_size=18, duration=dur)
        engine.draw_text(C[0] - 30, C[1] - 25, label_c, color=0xFFFFFF, font_size=18, duration=dur)

        # Add side length labels
        ab_len = labels.get("ab", "a")
        ac_len = labels.get("ac", "b")
        bc_len = labels.get("bc", "c")
        engine.draw_text((A[0] + B[0]) // 2 - 10, A[1] + 15, ab_len,
                        color=0x00FF88, font_size=16, duration=dur)
        engine.draw_text(A[0] - 45, (A[1] + C[1]) // 2, ac_len,
                        color=0x00FF88, font_size=16, duration=dur)
        engine.draw_text((B[0] + C[0]) // 2 + 10, (B[1] + C[1]) // 2 - 10, bc_len,
                        color=0xFF8800, font_size=16, duration=dur)

        # Add formula if provided
        formula = labels.get("formula", "")
        if formula:
            engine.draw_text(ox + 50, oy + 300 * scale, formula,
                            color=0xFFFF00, font_size=20, duration=dur)

        logger.info("[YouTubeOverlay] Drew right triangle with labels")
        return True

    def _draw_circle_diagram(self, engine, labels: Dict[str, str],
                             ox: int, oy: int, scale: float, dur: float) -> bool:
        """Draw a labeled circle for geometry teaching."""
        cx, cy = int(ox + 200 * scale), int(oy + 200 * scale)
        r = int(120 * scale)

        # Draw circle
        engine.draw_circle(cx, cy, r, color=0x00CCFF, width=3, duration=dur)

        # Draw center point
        engine.draw_circle(cx, cy, 4, color=0xFF0000, fill_color=0xFF0000, width=1, duration=dur)

        # Center label
        center_label = labels.get("center", "O")
        engine.draw_text(cx - 20, cy + r + 15, center_label,
                        color=0xFFFFFF, font_size=16, duration=dur)

        # Radius line
        rx, ry = int(cx + r * 0.7), int(cy - r * 0.7)
        engine.draw_line(cx, cy, rx, ry, color=0xFFFF00, width=2, duration=dur)
        radius_label = labels.get("radius", "r")
        engine.draw_text((cx + rx) // 2 + 5, (cy + ry) // 2 - 15, radius_label,
                        color=0xFFFF00, font_size=14, duration=dur)

        # Diameter line
        engine.draw_line(cx - r, cy, cx + r, cy, color=0x00FF88, width=2, duration=dur)
        diam_label = labels.get("diameter", "d = 2r")
        engine.draw_text(cx - 20, cy - 15, diam_label,
                        color=0x00FF88, font_size=14, duration=dur)

        # Circumference formula
        formula = labels.get("formula", "C = 2πr")
        engine.draw_text(ox + 50, oy + 280 * scale, formula,
                        color=0xFFFF00, font_size=18, duration=dur)

        logger.info("[YouTubeOverlay] Drew circle diagram with labels")
        return True

    def _draw_angle_diagram(self, engine, labels: Dict[str, str],
                            ox: int, oy: int, scale: float, dur: float) -> bool:
        """Draw an angle with arc and label for geometry teaching."""
        # Vertex
        vx, vy = int(ox + 200 * scale), int(oy + 200 * scale)

        # Two rays
        import math
        angle_rad = math.radians(45)  # 45 degree angle
        ray_len = int(150 * scale)

        x1 = int(vx + ray_len * math.cos(0))
        y1 = int(vy)
        x2 = int(vx + ray_len * math.cos(-angle_rad))
        y2 = int(vy - ray_len * math.sin(angle_rad))

        engine.draw_line(vx, vy, x1, y1, color=0x00CCFF, width=3, duration=dur)
        engine.draw_line(vx, vy, x2, y2, color=0x00CCFF, width=3, duration=dur)

        # Draw angle arc
        arc_r = int(40 * scale)
        arc_pts = []
        for a in range(0, 46, 3):
            rad = math.radians(a)
            arc_pts.append((int(vx + arc_r * math.cos(rad)), int(vy - arc_r * math.sin(rad))))
        for i in range(len(arc_pts) - 1):
            engine.draw_line(arc_pts[i][0], arc_pts[i][1],
                           arc_pts[i+1][0], arc_pts[i+1][1],
                           color=0xFFFF00, width=2, duration=dur)

        # Angle label
        angle_label = labels.get("angle", "45°")
        engine.draw_text(vx + arc_r + 10, vy - arc_r // 2, angle_label,
                        color=0xFFFF00, font_size=16, duration=dur)

        # Vertex label
        vertex_label = labels.get("vertex", "O")
        engine.draw_text(vx - 25, vy + 10, vertex_label,
                        color=0xFFFFFF, font_size=16, duration=dur)

        # Point labels
        p1_label = labels.get("p1", "A")
        p2_label = labels.get("p2", "B")
        engine.draw_text(x1 + 10, y1 + 5, p1_label, color=0xFFFFFF, font_size=16, duration=dur)
        engine.draw_text(x2 + 10, y2 - 20, p2_label, color=0xFFFFFF, font_size=16, duration=dur)

        logger.info("[YouTubeOverlay] Drew angle diagram with labels")
        return True

    def _draw_coordinate_axes(self, engine, labels: Dict[str, str],
                              ox: int, oy: int, scale: float, dur: float) -> bool:
        """Draw X-Y coordinate axes for math teaching."""
        cx, cy = int(ox + 200 * scale), int(oy + 200 * scale)
        axis_len = int(180 * scale)

        # X axis
        engine.draw_line(cx - axis_len, cy, cx + axis_len, cy, color=0x00CCFF, width=2, duration=dur)
        engine.draw_arrow(cx + axis_len - 10, cy, cx + axis_len, cy, color=0x00CCFF, width=2, duration=dur)

        # Y axis
        engine.draw_line(cx, cy + axis_len, cx, cy - axis_len, color=0x00CCFF, width=2, duration=dur)
        engine.draw_arrow(cx, cy - axis_len + 10, cx, cy - axis_len, color=0x00CCFF, width=2, duration=dur)

        # Origin
        engine.draw_circle(cx, cy, 3, color=0xFF0000, fill_color=0xFF0000, width=1, duration=dur)
        origin_label = labels.get("origin", "O")
        engine.draw_text(cx - 25, cy + 10, origin_label, color=0xFFFFFF, font_size=14, duration=dur)

        # Axis labels
        x_label = labels.get("x", "x")
        y_label = labels.get("y", "y")
        engine.draw_text(cx + axis_len + 5, cy - 20, x_label, color=0x00FF88, font_size=16, duration=dur)
        engine.draw_text(cx + 10, cy - axis_len - 5, y_label, color=0x00FF88, font_size=16, duration=dur)

        # Tick marks
        for i in range(-4, 5):
            if i == 0:
                continue
            tick_x = cx + int(i * 40 * scale)
            engine.draw_line(tick_x, cy - 4, tick_x, cy + 4, color=0x666666, width=1, duration=dur)
            engine.draw_text(tick_x - 5, cy + 8, str(i), color=0x999999, font_size=10, duration=dur)

        for i in range(-4, 5):
            if i == 0:
                continue
            tick_y = cy - int(i * 40 * scale)
            engine.draw_line(cx - 4, tick_y, cx + 4, tick_y, color=0x666666, width=1, duration=dur)
            engine.draw_text(cx - 18, tick_y - 5, str(i), color=0x999999, font_size=10, duration=dur)

        logger.info("[YouTubeOverlay] Drew coordinate axes with labels")
        return True

    # ═══════════════════════════════════════════════════════════
    # STEP 7: Teaching Explanation
    # ═══════════════════════════════════════════════════════════

    def explain(self, transcript: str = "", topic: str = "") -> str:
        """
        Generate a teaching explanation combining:
        - VLM analysis of the frame
        - Transcript context
        - Extracted shape information
        Returns a formatted teaching explanation.
        """
        self._transcript = transcript

        try:
            from core_organs.intelligent_mouse import ScreenAnalyzer
            analyzer = ScreenAnalyzer()

            prompt = (
                "You are a world-class teacher explaining a concept from a YouTube video.\n\n"
                "CONTEXT:\n"
            )

            if topic:
                prompt += f"Video topic: {topic}\n"
            if self._video_title:
                prompt += f"Video title: {self._video_title}\n"
            if transcript:
                # Take first 500 chars of transcript for context
                prompt += f"Transcript snippet: {transcript[:500]}\n"

            prompt += (
                f"\nDIAGRAM ANALYSIS:\n{self._vlm_analysis[:1000]}\n\n"
                f"SHAPES FOUND: {len(self._shapes)} shapes\n"
                f"LABELS FOUND: {len(self._labels)} labels\n\n"

                "Provide a CLEAR, STEP-BY-STEP teaching explanation:\n"
                "1. What is the concept being taught?\n"
                "2. Walk through each part of the diagram\n"
                "3. Explain the mathematical/logical relationships\n"
                "4. Give the key formula or rule\n"
                "5. Provide a real-world example or intuition\n\n"
                "Write as if you are speaking to a student watching this video. "
                "Be engaging, clear, and thorough. Use simple language."
            )

            self._explanation = analyzer.analyze(
                self._frame_b64 or "", prompt, model="minicpm-v:latest"
            )

            if not self._explanation:
                # Fallback: generate explanation from VLM analysis alone
                self._explanation = self._generate_fallback_explanation()

            logger.info("[YouTubeOverlay] Generated explanation: %d chars", len(self._explanation))
            return self._explanation

        except Exception as e:
            logger.error("[YouTubeOverlay] explain failed: %s", e)
            return self._generate_fallback_explanation()

    def _generate_fallback_explanation(self) -> str:
        """Generate a fallback explanation from available data."""
        parts = []
        if self._video_title:
            parts.append(f"## Teaching: {self._video_title}\n")

        if self._shapes:
            parts.append("### Diagram Elements:")
            for i, shape in enumerate(self._shapes, 1):
                shape_type = shape.get("type", "unknown")
                label = shape.get("label", "")
                parts.append(f"{i}. **{shape_type}** {label}")

        if self._labels:
            parts.append("\n### Labels:")
            for label in self._labels:
                text = label.get("text", "")
                parts.append(f"- {text}")

        if self._transcript:
            parts.append(f"\n### Context from video:\n{self._transcript[:300]}...")

        return "\n".join(parts) if parts else "No explanation available."

    # ═══════════════════════════════════════════════════════════
    # STEP 8: Display Explanation on Screen
    # ═══════════════════════════════════════════════════════════

    def show_explanation_on_screen(self, explanation: str,
                                   x: int = 50, y: int = 400,
                                   duration: float = 30.0) -> bool:
        """
        Display the teaching explanation as text overlay on screen.
        Wraps long text into multiple lines.
        """
        try:
            from core_organs.intelligent_mouse import DrawingEngine

            if self._drawing_engine is None:
                self._drawing_engine = DrawingEngine()

            self._drawing_engine.show()

            # Split explanation into lines
            lines = explanation.split("\n")
            line_y = y
            max_chars_per_line = 80

            for line in lines:
                if not line.strip():
                    line_y += 15
                    continue

                # Wrap long lines
                while len(line) > max_chars_per_line:
                    split_at = line.rfind(" ", 0, max_chars_per_line)
                    if split_at == -1:
                        split_at = max_chars_per_line
                    self._drawing_engine.draw_text(
                        x, line_y, line[:split_at],
                        color=0xFFFFFF, font_size=14, duration=duration
                    )
                    line_y += 20
                    line = line[split_at:].lstrip()

                self._drawing_engine.draw_text(
                    x, line_y, line,
                    color=0xFFFFFF, font_size=14, duration=duration
                )
                line_y += 20

            logger.info("[YouTubeOverlay] Displayed explanation on screen (%d lines)", len(lines))
            return True

        except Exception as e:
            logger.error("[YouTubeOverlay] show_explanation_on_screen failed: %s", e)
            return False

    # ═══════════════════════════════════════════════════════════
    # FULL PIPELINE: One-call teaching experience
    # ═══════════════════════════════════════════════════════════

    def teach_video(self, video_url: str, topic: str = "",
                    trace_contours: bool = True,
                    draw_own_diagram: bool = True,
                    diagram_type: str = "right_triangle",
                    show_explanation: bool = True) -> Dict[str, Any]:
        """
        Complete one-call YouTube teaching pipeline.

        Args:
            video_url: YouTube video URL
            topic: Topic hint for the VLM (e.g., "Pythagoras theorem")
            trace_contours: Whether to trace shapes from the video frame
            draw_own_diagram: Whether to draw our own clean labeled diagram
            diagram_type: Type of diagram to draw (right_triangle, circle, angle, coordinate_axes)
            show_explanation: Whether to show explanation text on screen

        Returns:
            Dict with frame_path, analysis, contours, explanation, etc.
        """
        result = {
            "video_url": video_url,
            "title": "",
            "frame_path": "",
            "vlm_analysis": "",
            "shapes_count": 0,
            "labels_count": 0,
            "contours_count": 0,
            "explanation": "",
            "success": False,
        }

        try:
            # Step 1: Open & pause video
            logger.info("[YouTubeOverlay] === STARTING TEACH PIPELINE ===")
            if not self.open_and_pause(video_url):
                logger.error("[YouTubeOverlay] Failed to open/pause video")
                return result
            result["title"] = self._video_title

            # Step 2: Capture frame
            frame = self.capture_frame()
            if not frame:
                logger.error("[YouTubeOverlay] Failed to capture frame")
                return result
            result["frame_path"] = self._frame_path or ""

            # Step 3: VLM analysis
            analysis = self.analyze_frame(topic_hint=topic)
            result["vlm_analysis"] = analysis
            result["shapes_count"] = len(self._shapes)
            result["labels_count"] = len(self._labels)

            # Step 4: Extract contours (if OpenCV available)
            contours = []
            if trace_contours:
                contours = self.extract_contours()
                result["contours_count"] = len(contours)

            # Step 5: Draw traced diagram on overlay
            if trace_contours and contours:
                self.trace_on_overlay(contours, animate=True, duration=15.0)
                time.sleep(1)

            # Step 6: Add labels from VLM analysis
            if self._labels:
                self.add_labels(duration=20.0)
                time.sleep(0.5)

            # Step 7: Draw our OWN clean diagram
            if draw_own_diagram:
                # Position our diagram to the right/below the video content
                self.add_own_diagram(
                    diagram_type=diagram_type,
                    labels={"formula": "a² + b² = c²"} if diagram_type == "right_triangle" else {},
                    offset_x=800, offset_y=100, scale=0.8, duration=25.0
                )
                time.sleep(0.5)

            # Step 8: Generate and show explanation
            if show_explanation:
                explanation = self.explain(transcript="", topic=topic)
                result["explanation"] = explanation
                self.show_explanation_on_screen(explanation, x=50, y=500, duration=30.0)

            result["success"] = True
            logger.info("[YouTubeOverlay] === TEACH PIPELINE COMPLETE ===")
            return result

        except Exception as e:
            logger.error("[YouTubeOverlay] teach_video failed: %s", e)
            result["explanation"] = f"Error: {e}"
            return result

    # ═══════════════════════════════════════════════════════════
    # Cleanup
    # ═══════════════════════════════════════════════════════════

    def clear_overlay(self):
        """Clear all drawings from the overlay."""
        try:
            if self._drawing_engine:
                self._drawing_engine.clear()
            logger.info("[YouTubeOverlay] Overlay cleared")
        except Exception as e:
            logger.debug("[YouTubeOverlay] clear_overlay: %s", e)

    def stop(self):
        """Stop the teaching overlay and clean up."""
        self._stop_event.set()
        self.clear_overlay()
        try:
            if self._drawing_engine:
                self._drawing_engine.hide()
        except Exception:
            pass
        logger.info("[YouTubeOverlay] Stopped and cleaned up")

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# Module-level convenience function
# ═══════════════════════════════════════════════════════════════

def teach_youtube_video(video_url: str, topic: str = "", **kwargs) -> Dict[str, Any]:
    """
    One-call convenience function to teach from a YouTube video.

    Usage:
        from core_organs.youtube_teaching_overlay import teach_youtube_video
        result = teach_youtube_video(
            "https://www.youtube.com/watch?v=...",
            topic="Pythagoras theorem"
        )
    """
    overlay = YouTubeTeachingOverlay()
    return overlay.teach_video(video_url, topic=topic, **kwargs)
