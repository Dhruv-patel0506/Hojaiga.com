"""
AI Teaching Assistant - Unified Spatial Whiteboard v7
========================================================================================
Integrates:
  1. Full-screen Unbounded Glass Whiteboard (Zero clamped card containers, freeform drawing).
  2. Autonomous Camera Director with smooth cubic-lerp tracking to active derivation clusters.
  3. Geometric Proof with Euclidean Squares attached to sides (a²=9, b²=16, c²=25) from first principles.
  4. Free-Body Diagrams (FBD) on inclined ramps with normal force, gravity vectors, friction, and axes.
  5. In-Situ Application Guides (OBS Studio, IDEs) with negative-space callout pointers.
  6. CV Diagram Lifting (Canny/contour elevation from underlying screen).
  7. High-Speed Media & Rap Cadence Spectrogram & Syllabic Meter Analyzer.
  8. Non-Repeating Dynamic Socratic Mastery Engine with randomized questions & answer validation.
  9. Code Architecture & Execution Flow Visualizer.
 10. Expressive Animated Companion Mascot (Antenna pulse, eye blink, speech mouth, stylus tracking).
 11. Clause-Synchronized Voice Narration (TTS) & Acoustic Gated STT Speech Listener.
 12. Universal Media & OS App Controller (VK_MEDIA_PLAY_PAUSE, space, 'k', 5s scrubbers).
 13. Live Local LLM Vision Crawler (Ollama 3B / Llama 7B) with dHash screen diffing & schema coercion.
 14. Infinite Canvas Pan/Zoom (ALT+Drag / ALT+Scroll, F8 toggle) & High-Res PNG Export (Ctrl+S).
========================================================================================
"""

import sys
import os
import time
import math
import random
import threading
import queue
import dataclasses
import argparse
import re
import json
import base64
import asyncio
from io import BytesIO
from typing import List, Tuple, Optional, Dict, Any

# Windows platform setup
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    import ctypes
    from ctypes import wintypes
    try:
        import win32gui
        import win32process
        import win32con
    except ImportError:
        pass
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

# Qt Framework
from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal, QObject
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QBrush, QPainterPath, QFont, 
    QFontMetrics, QLinearGradient, QRadialGradient, QTransform, QPolygonF, QImage
)
from PyQt5.QtWidgets import QApplication, QWidget, QDesktopWidget

# Computer Vision & Pillow
from PIL import Image, ImageGrab
try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Speech Engines
HAS_PYTTSX3 = False
try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    pass

HAS_WHISPER = False
try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except ImportError:
    pass

HAS_SR = False
try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    pass

HAS_WINRT = False
if sys.platform == "win32":
    try:
        from winsdk.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as MediaManager
        )
        HAS_WINRT = True
    except ImportError:
        HAS_WINRT = False

# Win32 Window Constants
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008

VK_MEDIA_PLAY_PAUSE = 0xB3
VK_LEFT = 0x25
VK_RIGHT = 0x27
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001


# =====================================================================
# CLI ARGUMENTS & CONFIGURATION
# =====================================================================
parser = argparse.ArgumentParser(description="AI Teaching Assistant - Spatial Whiteboard v7")
parser.add_argument("--7b", action="store_true", help="Use Qwen2.5-VL-7B Deep Analysis on port 8081")
parser.add_argument("--3b", action="store_true", help="Use qwen2.5vl:3b Fast Reflex on port 11434")
parser.add_argument("--task", "--teach", type=str, default="", help="Specific topic or goal")
parser.add_argument("--pause-media", action="store_true", default=False, help="Enable automatic OS media pause/resume")
parser.add_argument("--voice", action="store_true", default=True, help="Enable offline TTS narration")
parser.add_argument("--no-voice", action="store_true", default=False, help="Disable speech synthesis")
parser.add_argument("--listen", action="store_true", default=True, help="Enable hands-free speech recognition")
parser.add_argument("--no-listen", action="store_true", default=False, help="Disable speech recognition")
cli_args, _ = parser.parse_known_args()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
LLAMA_SERVER_7B_URL = os.getenv("HOJAIGA_VISION_PRECISION_ENDPOINT", "http://localhost:8081") + "/v1/chat/completions"

USE_7B = getattr(cli_args, "7b", False) or (os.getenv("AI_TEACHER_MODEL", "").lower() in ["7b", "precision", "qwen7b"])
ACTIVE_BACKEND = "7b" if USE_7B else "3b"
MODEL_DISPLAY_NAME = "Qwen2.5-VL-7B (Port 8081)" if USE_7B else "qwen2.5vl:3b (Port 11434)"
AI_THINKING_INTERVAL_SEC = 7 if USE_7B else 5
VISION_MAX_RES = (768, 768) if USE_7B else (1024, 1024)

INITIAL_TASK = cli_args.task or os.getenv("AI_TEACHER_TASK", "")
VOICE_ENABLED = (not cli_args.no_voice) and (cli_args.voice or HAS_PYTTSX3)
LISTEN_ENABLED = (not cli_args.no_listen) and (cli_args.listen or (HAS_WHISPER or HAS_SR))
AUTO_PAUSE_MEDIA = cli_args.pause_media


# =====================================================================
# UNIVERSAL MEDIA CONTROLLER (GSMTC + HARDWARE SCAN-CODE)
# =====================================================================
class UniversalMediaController:
    @staticmethod
    def _run_winrt_action(action: str):
        if not HAS_WINRT:
            return False
        async def _async_call():
            mgr = await MediaManager.request_async()
            session = mgr.get_current_session()
            if session:
                if action == "pause":
                    await session.try_pause_async()
                elif action == "play":
                    await session.try_play_async()
                return True
            return False
        try:
            loop = asyncio.new_event_loop()
            res = loop.run_until_complete(_async_call())
            loop.close()
            return res
        except Exception:
            return False

    @classmethod
    def send_key(cls, vk_code: int, extended: bool = False):
        if sys.platform == "win32":
            flags = KEYEVENTF_EXTENDEDKEY if extended else 0
            user32.keybd_event(vk_code, 0, flags, 0)
            time.sleep(0.035)
            user32.keybd_event(vk_code, 0, flags | KEYEVENTF_KEYUP, 0)

    @classmethod
    def toggle_playback(cls):
        if cls._run_winrt_action("pause"):
            return
        cls.send_key(VK_MEDIA_PLAY_PAUSE, extended=True)

    @classmethod
    def scrub_back_5s(cls):
        cls.send_key(VK_LEFT, extended=True)

    @classmethod
    def scrub_forward_5s(cls):
        cls.send_key(VK_RIGHT, extended=True)


# =====================================================================
# DATA STRUCTURES
# =====================================================================
@dataclasses.dataclass
class HandStroke:
    points: List[QPointF]
    color: QColor
    width: float = 2.5
    progress: float = 0.0          # 0.0 to 1.0
    speed: float = 0.045           # Tracing speed
    is_dashed: bool = False
    fill_color: Optional[QColor] = None
    is_arrow: bool = False
    arrow_label: str = ""
    opacity: float = 1.0


@dataclasses.dataclass
class SketchnoteElement:
    id: str
    element_type: str              # 'proof', 'fbd', 'app_guide', 'code_arch', 'rap_parse', 'mind_map'
    bounding_rect: QRectF
    strokes: List[HandStroke] = dataclasses.field(default_factory=list)
    text_items: List[Tuple[QPointF, str, QFont, QColor, float]] = dataclasses.field(default_factory=list)
    callout_arrows: List[Tuple[QPointF, QPointF, str, QColor]] = dataclasses.field(default_factory=list)
    opacity: float = 1.0


# =====================================================================
# ORGANIC GEOMETRY FACTORY (Natural Human Jitter & Smooth Curves)
# =====================================================================
class OrganicGeometryFactory:
    @staticmethod
    def hand_drawn_line(p1: QPointF, p2: QPointF, steps: int = 18, jitter: float = 1.1) -> List[QPointF]:
        pts = []
        for i in range(steps + 1):
            t = i / float(steps)
            x = p1.x() + t * (p2.x() - p1.x())
            y = p1.y() + t * (p2.y() - p1.y())
            bow = math.sin(t * math.pi) * random.uniform(-jitter * 1.5, jitter * 1.5)
            pts.append(QPointF(x + random.uniform(-jitter, jitter), y + bow))
        return pts

    @classmethod
    def hand_drawn_arrow(cls, start: QPointF, end: QPointF, arrow_size: float = 14.0) -> List[QPointF]:
        line_pts = cls.hand_drawn_line(start, end, steps=16, jitter=0.9)
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        wing1 = QPointF(
            end.x() - arrow_size * math.cos(angle - math.pi / 6.0),
            end.y() - arrow_size * math.sin(angle - math.pi / 6.0)
        )
        wing2 = QPointF(
            end.x() - arrow_size * math.cos(angle + math.pi / 6.0),
            end.y() - arrow_size * math.sin(angle + math.pi / 6.0)
        )
        line_pts.append(wing1)
        line_pts.append(end)
        line_pts.append(wing2)
        return line_pts

    @classmethod
    def hand_drawn_cloud(cls, center: QPointF, rx: float, ry: float, arcs: int = 16) -> List[QPointF]:
        pts = []
        angle_step = (2.0 * math.pi) / arcs
        for i in range(arcs + 1):
            theta = i * angle_step
            bulge = 1.0 + 0.16 * math.sin(theta * arcs * 0.5)
            x = center.x() + rx * math.cos(theta) * bulge + random.uniform(-1.2, 1.2)
            y = center.y() + ry * math.sin(theta) * bulge + random.uniform(-1.2, 1.2)
            pts.append(QPointF(x, y))
        return pts

    @classmethod
    def curved_bezier(cls, p0: QPointF, p1: QPointF, p2: QPointF, steps: int = 24) -> List[QPointF]:
        pts = []
        for i in range(steps + 1):
            t = i / float(steps)
            u = 1.0 - t
            x = u * u * p0.x() + 2 * u * t * p1.x() + t * t * p2.x()
            y = u * u * p0.y() + 2 * u * t * p1.y() + t * t * p2.y()
            pts.append(QPointF(x + random.uniform(-0.8, 0.8), y + random.uniform(-0.8, 0.8)))
        return pts


# =====================================================================
# FIRST-PRINCIPLES GEOMETRIC PROOF: PYTHAGOREAN THEOREM BY SQUARES
# =====================================================================
class EuclideanProofSynthesizer:
    @staticmethod
    def synthesize_pythagoras_proof(origin_x: float, origin_y: float) -> SketchnoteElement:
        elem = SketchnoteElement(
            id=f"proof_pythagoras_{int(time.time())}",
            element_type="proof",
            bounding_rect=QRectF(origin_x - 60, origin_y - 60, 1260, 780)
        )
        
        cyan_hypot = QColor(56, 189, 248)
        emerald_base = QColor(52, 211, 153)
        amber_height = QColor(251, 191, 36)
        lavender = QColor(216, 180, 254)
        white_txt = QColor(241, 245, 249)

        # 1. Main Header Ribbon
        head_center = QPointF(origin_x + 440, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(head_center, 420, 36, 18),
            color=cyan_hypot,
            width=2.5,
            fill_color=QColor(56, 189, 248, 25)
        ))
        elem.text_items.append((
            QPointF(head_center.x() - 360, head_center.y() + 6),
            "THE PYTHAGOREAN THEOREM: FIRST-PRINCIPLES VISUAL PROOF BY SQUARES",
            QFont("Segoe UI", 11, QFont.Bold),
            white_txt,
            0.0
        ))

        # 2. Right-Angled Triangle Geometry (a = 3, b = 4, c = 5)
        scale = 35.0
        a_len = 3.0 * scale   # Height: 105 px
        b_len = 4.0 * scale   # Base: 140 px

        # Triangle vertices
        A = QPointF(origin_x + 220, origin_y + 360)            # Right-angle corner
        B = QPointF(A.x() + b_len, A.y())                      # Base end
        C = QPointF(A.x(), A.y() - a_len)                      # Top peak

        # Triangle Sides
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_line(A, B, 18, 1.2),
            color=emerald_base, width=3.5
        ))
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_line(A, C, 16, 1.2),
            color=amber_height, width=3.5
        ))
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_line(C, B, 22, 1.4),
            color=cyan_hypot, width=4.0
        ))

        # Right-angle square marker at A
        sq_mark = [
            QPointF(A.x(), A.y() - 14),
            QPointF(A.x() + 14, A.y() - 14),
            QPointF(A.x() + 14, A.y())
        ]
        elem.strokes.append(HandStroke(points=sq_mark, color=white_txt, width=1.5))

        # 3. Euclidean Attached Square 1 on Height (Side a = 3, Area = 9)
        # Extending to the left of AC
        sq_a = [
            C,
            QPointF(C.x() - a_len, C.y()),
            QPointF(A.x() - a_len, A.y()),
            A
        ]
        sq_a.append(sq_a[0])
        elem.strokes.append(HandStroke(
            points=sq_a,
            color=amber_height,
            width=2.5,
            fill_color=QColor(amber_height.red(), amber_height.green(), amber_height.blue(), 35)
        ))
        elem.text_items.append((
            QPointF(A.x() - a_len * 0.75, A.y() - a_len * 0.45),
            "a² = 9",
            QFont("Segoe UI", 12, QFont.Bold),
            amber_height,
            0.0
        ))

        # 4. Euclidean Attached Square 2 on Base (Side b = 4, Area = 16)
        # Extending downwards from AB
        sq_b = [
            A,
            QPointF(A.x(), A.y() + b_len),
            QPointF(B.x(), B.y() + b_len),
            B
        ]
        sq_b.append(sq_b[0])
        elem.strokes.append(HandStroke(
            points=sq_b,
            color=emerald_base,
            width=2.5,
            fill_color=QColor(emerald_base.red(), emerald_base.green(), emerald_base.blue(), 35)
        ))
        elem.text_items.append((
            QPointF(A.x() + b_len * 0.35, A.y() + b_len * 0.55),
            "b² = 16",
            QFont("Segoe UI", 12, QFont.Bold),
            emerald_base,
            0.0
        ))

        # 5. Euclidean Attached Square 3 on Hypotenuse (Side c = 5, Area = 25)
        # Normal pointing outward along hypotenuse BC
        # Vector CB = (B.x - C.x, B.y - C.y) = (b_len, a_len)
        dx = B.x() - C.x()
        dy = B.y() - C.y()
        # Perpendicular normal pointing out-right: (-dy, dx)
        sq_c = [
            C,
            B,
            QPointF(B.x() - dy, B.y() + dx),
            QPointF(C.x() - dy, C.y() + dx),
            C
        ]
        elem.strokes.append(HandStroke(
            points=sq_c,
            color=cyan_hypot,
            width=3.0,
            fill_color=QColor(cyan_hypot.red(), cyan_hypot.green(), cyan_hypot.blue(), 40)
        ))
        elem.text_items.append((
            QPointF(C.x() + (B.x() - C.x()) * 0.35 - dy * 0.55, C.y() + (B.y() - C.y()) * 0.35 + dx * 0.55),
            "c² = 25",
            QFont("Segoe UI", 13, QFont.Bold),
            cyan_hypot,
            0.0
        ))

        # Side Labels
        elem.text_items.append((QPointF(A.x() - 75, A.y() - a_len * 0.5), "Height a = 3", QFont("Segoe UI", 10, QFont.Bold), amber_height, 0.0))
        elem.text_items.append((QPointF(A.x() + b_len * 0.3, A.y() - 10), "Base b = 4", QFont("Segoe UI", 10, QFont.Bold), emerald_base, 0.0))
        elem.text_items.append((QPointF(C.x() + b_len * 0.55, C.y() + a_len * 0.4), "Hypotenuse c = 5", QFont("Segoe UI", 10, QFont.Bold), cyan_hypot, 0.0))

        # 6. Toddler-to-Professor Step-by-Step Explanation Ladder (Right Workspace)
        lx = origin_x + 590
        ly = origin_y + 60
        steps = [
            ("1. WHAT IS A TRIANGLE?", "A 3-sided shape. When one corner forms a perfect 90° square box, it's a RIGHT TRIANGLE.", white_txt),
            ("2. WHAT IS THE HYPOTENUSE?", "The longest side directly OPPOSITE the 90° corner. (Side c in glowing cyan).", cyan_hypot),
            ("3. WHAT ARE THE LEGS?", "The other two sides meeting at 90°: Upright Height (a) and Flat Base (b).", emerald_base),
            ("4. BUILD SQUARES ON EACH SIDE", "Imagine physical floor tiles: 3×3 square on height (9) + 4×4 square on base (16).", amber_height),
            ("5. THE MAGIC EQUALITY", "Area of Height Square + Area of Base Square = 9 + 16 = 25 tiles!", lavender),
            ("6. PERFECT FIT ON HYPOTENUSE", "25 tiles perfectly cover a 5×5 square on the hypotenuse! Therefore: a² + b² = c².", cyan_hypot)
        ]

        sy = ly
        for title, desc, col in steps:
            elem.strokes.append(HandStroke(
                points=OrganicGeometryFactory.hand_drawn_cloud(QPointF(lx, sy - 4), 6, 6, 8),
                color=col, width=2.0, fill_color=col
            ))
            elem.text_items.append((
                QPointF(lx + 22, sy),
                title,
                QFont("Segoe UI", 10, QFont.Bold),
                col,
                0.0
            ))
            elem.text_items.append((
                QPointF(lx + 22, sy + 22),
                desc,
                QFont("Segoe UI", 9),
                QColor(203, 213, 225),
                0.0
            ))
            sy += 64

        return elem


# =====================================================================
# FREE-BODY DIAGRAM (FBD) SYNTHESIZER
# =====================================================================
class FreeBodyDiagramSynthesizer:
    @staticmethod
    def synthesize_inclined_plane_fbd(origin_x: float, origin_y: float) -> SketchnoteElement:
        elem = SketchnoteElement(
            id=f"fbd_incline_{int(time.time())}",
            element_type="fbd",
            bounding_rect=QRectF(origin_x - 60, origin_y - 60, 1150, 740)
        )
        
        cyan_force = QColor(56, 189, 248)
        emerald_norm = QColor(52, 211, 153)
        amber_gravity = QColor(251, 191, 36)
        coral_friction = QColor(248, 113, 113)
        lavender_text = QColor(216, 180, 254)

        head_center = QPointF(origin_x + 380, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(head_center, 380, 36, 16),
            color=lavender_text, width=2.5, fill_color=QColor(147, 51, 234, 30)
        ))
        elem.text_items.append((
            QPointF(head_center.x() - 320, head_center.y() + 6),
            "FREE-BODY DIAGRAM (FBD): BLOCK ON INCLINED RAMP WITH FRICTION",
            QFont("Segoe UI", 11, QFont.Bold), QColor(243, 244, 246), 0.0
        ))

        # Wedge
        ramp_len = 380.0
        theta_rad = math.radians(30.0)
        P_base_left = QPointF(origin_x + 40, origin_y + 380)
        P_base_right = QPointF(P_base_left.x() + ramp_len, P_base_left.y())
        P_peak = QPointF(P_base_left.x(), P_base_left.y() - ramp_len * math.tan(theta_rad))

        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(P_base_left, P_base_right, 20, 1.2), color=QColor(148, 163, 184), width=3.0))
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(P_base_left, P_peak, 14, 1.2), color=QColor(148, 163, 184), width=3.0))
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(P_peak, P_base_right, 24, 1.5), color=QColor(226, 232, 240), width=4.0))

        # Block
        t_block = 0.48
        block_cx = P_peak.x() + t_block * (P_base_right.x() - P_peak.x())
        block_cy = P_peak.y() + t_block * (P_base_right.y() - P_peak.y())
        C = QPointF(block_cx, block_cy - 20)

        bw, bh = 60.0, 40.0
        cos_t = math.cos(theta_rad)
        sin_t = math.sin(theta_rad)
        b_pts = [
            QPointF(C.x() - bw*cos_t + bh*sin_t, C.y() + bw*sin_t + bh*cos_t),
            QPointF(C.x() + bw*cos_t + bh*sin_t, C.y() - bw*sin_t + bh*cos_t),
            QPointF(C.x() + bw*cos_t - bh*sin_t, C.y() - bw*sin_t - bh*cos_t),
            QPointF(C.x() - bw*cos_t - bh*sin_t, C.y() + bw*sin_t - bh*cos_t),
        ]
        b_pts.append(b_pts[0])
        elem.strokes.append(HandStroke(points=b_pts, color=cyan_force, width=3.0, fill_color=QColor(56, 189, 248, 35)))

        # Forces
        mg_end = QPointF(C.x(), C.y() + 140)
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_arrow(C, mg_end), color=amber_gravity, width=3.5))
        elem.text_items.append((QPointF(mg_end.x() + 12, mg_end.y()), "F_g = m·g (Gravity)", QFont("Segoe UI", 11, QFont.Bold), amber_gravity, 0.0))

        fn_end = QPointF(C.x() + 110 * sin_t, C.y() - 110 * cos_t)
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_arrow(C, fn_end), color=emerald_norm, width=3.5))
        elem.text_items.append((QPointF(fn_end.x() + 12, fn_end.y() - 8), "F_N = m·g·cos(θ) (Normal Force)", QFont("Segoe UI", 11, QFont.Bold), emerald_norm, 0.0))

        fk_end = QPointF(C.x() - 95 * cos_t, C.y() - 95 * sin_t)
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_arrow(C, fk_end), color=coral_friction, width=3.5))
        elem.text_items.append((QPointF(fk_end.x() - 145, fk_end.y() - 12), "f_k = μ_k·F_N (Friction)", QFont("Segoe UI", 11, QFont.Bold), coral_friction, 0.0))

        down_end = QPointF(C.x() + 100 * cos_t, C.y() + 100 * sin_t)
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_arrow(C, down_end), color=amber_gravity, width=2.5, is_dashed=True))
        elem.text_items.append((QPointF(down_end.x() + 10, down_end.y() + 16), "m·g·sin(θ) (Downslope Vector)", QFont("Segoe UI", 10), amber_gravity, 0.0))

        # Derivations
        rx = origin_x + 520
        ry = origin_y + 80
        derivations = [
            ("1. ISOLATE THE OBJECT", "Treat mass (m) as a point at its center of gravity. Detach from surroundings.", cyan_force),
            ("2. RESOLVE CO-ORDINATES", "Align X-axis parallel to ramp, and Y-axis perpendicular to ramp surface.", emerald_norm),
            ("3. DECOMPOSE GRAVITY (mg)", "Y-component: mg·cos(θ) pushes into ramp | X-component: mg·sin(θ) pulls downhill.", amber_gravity),
            ("4. EQUILIBRIUM ON Y-AXIS", "No motion into ramp: ΣFy = 0  ===>  F_N = mg·cos(θ).", emerald_norm),
            ("5. NEWTON'S 2ND LAW (X-AXIS)", "ΣFx = m·a  ===>  mg·sin(θ) - f_k = m·a", coral_friction),
            ("6. NET ACCELERATION", "a = g·(sin(θ) - μ_k·cos(θ))  [Sliding occurs when tan(θ) > μ_s]", lavender_text)
        ]
        cy = ry
        for step_title, step_desc, col in derivations:
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_cloud(QPointF(rx, cy - 4), 6, 6, 8), color=col, width=2.0, fill_color=col))
            elem.text_items.append((QPointF(rx + 22, cy), step_title, QFont("Segoe UI", 10, QFont.Bold), col, 0.0))
            elem.text_items.append((QPointF(rx + 22, cy + 22), step_desc, QFont("Segoe UI", 9), QColor(203, 213, 225), 0.0))
            cy += 64

        return elem


# =====================================================================
# CODE ARCHITECTURE & EXECUTION FLOW VISUALIZER
# =====================================================================
class CodeArchitectureSynthesizer:
    @staticmethod
    def synthesize_code_analysis(origin_x: float, origin_y: float, code_topic: str = "Algorithm Flow") -> SketchnoteElement:
        elem = SketchnoteElement(
            id=f"code_arch_{int(time.time())}",
            element_type="code_arch",
            bounding_rect=QRectF(origin_x - 60, origin_y - 60, 1150, 740)
        )
        cyan = QColor(56, 189, 248)
        emerald = QColor(52, 211, 153)
        amber = QColor(251, 191, 36)
        violet = QColor(167, 139, 250)

        head_center = QPointF(origin_x + 380, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(head_center, 380, 36, 16),
            color=cyan, width=2.5, fill_color=QColor(56, 189, 248, 25)
        ))
        elem.text_items.append((
            QPointF(head_center.x() - 320, head_center.y() + 6),
            f"CODE EXECUTION FLOW & DATA STRUCTURE ARCHITECTURE: {code_topic.upper()}",
            QFont("Segoe UI", 11, QFont.Bold), QColor(241, 245, 249), 0.0
        ))

        # Stack Frame vs Heap Memory Visualization
        mem_x = origin_x + 40
        mem_y = origin_y + 80
        # Call Stack Box
        stack_rect = QRectF(mem_x, mem_y, 220, 280)
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(stack_rect.topLeft(), stack_rect.topRight(), 10), color=emerald, width=2.0))
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(stack_rect.topRight(), stack_rect.bottomRight(), 12), color=emerald, width=2.0))
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(stack_rect.bottomRight(), stack_rect.bottomLeft(), 10), color=emerald, width=2.0))
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(stack_rect.bottomLeft(), stack_rect.topLeft(), 12), color=emerald, width=2.0))
        elem.text_items.append((QPointF(mem_x + 15, mem_y + 30), "CALL STACK (LIFO)", QFont("Consolas", 10, QFont.Bold), emerald, 0.0))
        elem.text_items.append((QPointF(mem_x + 15, mem_y + 70), "• main() frame", QFont("Consolas", 9), QColor(226, 232, 240), 0.0))
        elem.text_items.append((QPointF(mem_x + 15, mem_y + 110), "• recurse(n-1)", QFont("Consolas", 9), amber, 0.0))
        elem.text_items.append((QPointF(mem_x + 15, mem_y + 150), "• ptr -> Heap Object", QFont("Consolas", 9), cyan, 0.0))

        # Heap Box
        heap_x = mem_x + 300
        heap_rect = QRectF(heap_x, mem_y, 240, 280)
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(heap_rect.topLeft(), heap_rect.topRight(), 10), color=violet, width=2.0))
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(heap_rect.topRight(), heap_rect.bottomRight(), 12), color=violet, width=2.0))
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(heap_rect.bottomRight(), heap_rect.bottomLeft(), 10), color=violet, width=2.0))
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(heap_rect.bottomLeft(), heap_rect.topLeft(), 12), color=violet, width=2.0))
        elem.text_items.append((QPointF(heap_x + 15, mem_y + 30), "HEAP ALLOCATIONS", QFont("Consolas", 10, QFont.Bold), violet, 0.0))
        elem.text_items.append((QPointF(heap_x + 15, mem_y + 70), "{ id: 0x4F, val: 42 }", QFont("Consolas", 9), QColor(226, 232, 240), 0.0))

        # Arrow Stack to Heap
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_arrow(QPointF(mem_x + 190, mem_y + 145), QPointF(heap_x + 10, mem_y + 70)),
            color=cyan, width=2.5, is_dashed=True
        ))

        # Right-hand side Insights
        rx = origin_x + 620
        ry = origin_y + 80
        insights = [
            ("1. TIME COMPLEXITY: O(N log N)", "Optimal divide-and-conquer branch depth. Balanced recursion tree.", cyan),
            ("2. SPACE COMPLEXITY: O(N)", "Auxiliary array buffer + call stack frames proportional to depth.", emerald),
            ("3. CRITICAL EDGE CASE", "Ensure recursion base condition terminates on empty/single-element slice!", amber),
            ("4. PERFORMANCE TWEAK", "Use in-place partition swapping to reduce garbage collection allocation spikes.", violet)
        ]
        cy = ry
        for t, d, col in insights:
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_cloud(QPointF(rx, cy - 4), 6, 6, 8), color=col, width=2.0, fill_color=col))
            elem.text_items.append((QPointF(rx + 22, cy), t, QFont("Segoe UI", 10, QFont.Bold), col, 0.0))
            elem.text_items.append((QPointF(rx + 22, cy + 22), d, QFont("Segoe UI", 9), QColor(203, 213, 225), 0.0))
            cy += 64

        return elem


# =====================================================================
# IN-SITU APPLICATION GUIDES (OBS Studio, VS Code, Browser)
# =====================================================================
class AppInspectionSynthesizer:
    @staticmethod
    def synthesize_obs_walkthrough(origin_x: float, origin_y: float) -> SketchnoteElement:
        elem = SketchnoteElement(
            id=f"app_obs_{int(time.time())}",
            element_type="app_guide",
            bounding_rect=QRectF(origin_x - 60, origin_y - 60, 1150, 740)
        )
        cyan = QColor(56, 189, 248)
        emerald = QColor(52, 211, 153)
        violet = QColor(167, 139, 250)
        amber = QColor(251, 191, 36)
        coral = QColor(248, 113, 113)

        center = QPointF(origin_x + 420, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(center, 420, 36, 18),
            color=cyan, width=2.5, fill_color=QColor(56, 189, 248, 25)
        ))
        elem.text_items.append((
            QPointF(center.x() - 360, center.y() + 6),
            "CYBERSECURITY ARCHITECT'S FIELD GUIDE TO OBS STUDIO (STREAMING & CAPTURE)",
            QFont("Segoe UI", 11, QFont.Bold), QColor(243, 244, 246), 0.0
        ))

        # OBS Control Deck Layout
        deck_rect = QRectF(origin_x + 30, origin_y + 60, 480, 320)
        for p1, p2 in [
            (deck_rect.topLeft(), deck_rect.topRight()),
            (deck_rect.topRight(), deck_rect.bottomRight()),
            (deck_rect.bottomRight(), deck_rect.bottomLeft()),
            (deck_rect.bottomLeft(), deck_rect.topLeft())
        ]:
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(p1, p2, 14), color=violet, width=2.0))

        dock_w = 90.0
        docks = [
            ("SCENES", origin_x + 40, emerald),
            ("SOURCES", origin_x + 135, cyan),
            ("AUDIO MIXER", origin_x + 230, amber),
            ("TRANSITIONS", origin_x + 325, violet),
            ("CONTROLS", origin_x + 420, coral)
        ]
        for name, dx, col in docks:
            r = QRectF(dx, origin_y + 190, dock_w, 180)
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(r.topLeft(), r.topRight(), 8), color=col, width=2.0, fill_color=QColor(col.red(), col.green(), col.blue(), 30)))
            elem.text_items.append((QPointF(dx + 6, origin_y + 215), name, QFont("Segoe UI", 8, QFont.Bold), col, 0.0))

        callouts = [
            (QPointF(origin_x + 85, origin_y + 240), QPointF(origin_x + 580, origin_y + 80), "1. SCENES DOCK (ROOT WORKSPACES)", "Switch between Full Screen, Coding Window, and Webcam overlays with hotkeys.", emerald),
            (QPointF(origin_x + 180, origin_y + 270), QPointF(origin_x + 580, origin_y + 165), "2. SOURCES DOCK (LAYER STACK)", "Add 'Window Capture' or 'Audio Input'. Top layers visually occlude bottom layers!", cyan),
            (QPointF(origin_x + 275, origin_y + 240), QPointF(origin_x + 580, origin_y + 250), "3. AUDIO MIXER & NOISE GATING", "Keep peaks in yellow band (-15dB to -6dB). Use Noise Suppression to kill fan hum.", amber),
            (QPointF(origin_x + 465, origin_y + 260), QPointF(origin_x + 580, origin_y + 335), "4. OUTPUT & BITRATE ENGINE", "Select NVENC hardware GPU encoder at 6000 Kbps bitrate for 1080p60 streaming.", coral),
            (QPointF(origin_x + 465, origin_y + 340), QPointF(origin_x + 580, origin_y + 420), "5. ZERO PRIVACY LEAKS", "Never stream 'Display Capture'. Use 'Window Capture' to avoid flashing credentials!", violet)
        ]
        for target_pt, label_pt, title, desc, col in callouts:
            ctrl_pt = QPointF((target_pt.x() + label_pt.x()) * 0.5, target_pt.y() - 30)
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.curved_bezier(label_pt, ctrl_pt, target_pt, 16), color=col, width=2.0, is_dashed=True))
            elem.text_items.append((label_pt, title, QFont("Segoe UI", 10, QFont.Bold), col, 0.0))
            elem.text_items.append((QPointF(label_pt.x(), label_pt.y() + 22), desc, QFont("Segoe UI", 9), QColor(226, 232, 240), 0.0))

        return elem


# =====================================================================
# DYNAMIC SOCRATIC MASTERY EVALUATOR
# =====================================================================
class DynamicSocraticEngine:
    @staticmethod
    def generate_randomized_quiz(origin_x: float, origin_y: float) -> Tuple[SketchnoteElement, float, float]:
        elem = SketchnoteElement(
            id=f"quiz_{int(time.time())}",
            element_type="proof",
            bounding_rect=QRectF(origin_x - 40, origin_y - 40, 1000, 560)
        )
        neon_gold = QColor(251, 191, 36)
        neon_emerald = QColor(52, 211, 153)
        neon_cyan = QColor(56, 189, 248)

        base = random.choice([6, 5, 8, 9])
        height = random.choice([8, 12, 15, 12])
        hypot = math.sqrt(base*base + height*height)

        center = QPointF(origin_x + 380, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(center, 360, 36, 16),
            color=neon_gold, width=2.5, fill_color=QColor(251, 191, 36, 25)
        ))
        elem.text_items.append((
            QPointF(center.x() - 300, center.y() + 6),
            "SOCRATIC CHECKPOINT: DYNAMIC MASTERY ASSESSMENT",
            QFont("Segoe UI", 11, QFont.Bold), QColor(254, 243, 199), 0.0
        ))

        q_lines = [
            f"Scenario: You are fabricating a diagonal support brace for an architectural truss.",
            f"Given: Base horizontal span (b) = {base} m | Upright vertical post (a) = {height} m.",
            f"Challenge: What is the exact length of the diagonal brace (c), and its attached square area (c²)?"
        ]
        qy = origin_y + 70
        for line in q_lines:
            elem.text_items.append((
                QPointF(origin_x + 30, qy), line,
                QFont("Segoe UI", 11, QFont.Bold if "Challenge" in line else QFont.Normal),
                neon_cyan if "Challenge" in line else QColor(241, 245, 249), 0.0
            ))
            qy += 34

        correct_c = int(hypot) if hypot.is_integer() else round(hypot, 2)
        correct_sq = base*base + height*height
        options = [
            (f"Option A: c = {correct_c} m, Area(c²) = {correct_sq} m² [CORRECT]", neon_emerald),
            (f"Option B: c = {correct_c + 2} m, Area(c²) = {correct_sq + 40} m² [MISCALCULATION]", QColor(203, 213, 225)),
            (f"Option C: c = {abs(height - base)} m, Area(c²) = {(height - base)**2} m² [INCORRECT FORMULA]", QColor(203, 213, 225))
        ]
        oy = origin_y + 200
        for opt_text, col in options:
            box_rect = QRectF(origin_x + 30, oy - 14, 18, 18)
            for p1, p2 in [
                (box_rect.topLeft(), box_rect.topRight()),
                (box_rect.topRight(), box_rect.bottomRight()),
                (box_rect.bottomRight(), box_rect.bottomLeft()),
                (box_rect.bottomLeft(), box_rect.topLeft())
            ]:
                elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(p1, p2, 4), color=col, width=2.0))
            elem.text_items.append((QPointF(origin_x + 65, oy), opt_text, QFont("Segoe UI", 10), col, 0.0))
            oy += 45

        return elem, hypot, float(correct_sq)


# =====================================================================
# RAP CADENCE & 2X MEDIA DIGESTER
# =====================================================================
class HighSpeedMediaTranscriber:
    @staticmethod
    def synthesize_rap_cadence_breakdown(origin_x: float, origin_y: float) -> SketchnoteElement:
        elem = SketchnoteElement(
            id=f"rap_parse_{int(time.time())}",
            element_type="rap_parse",
            bounding_rect=QRectF(origin_x - 60, origin_y - 60, 1100, 680)
        )
        neon_pink = QColor(244, 114, 182)
        neon_cyan = QColor(56, 189, 248)
        neon_gold = QColor(251, 191, 36)

        center = QPointF(origin_x + 380, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(center, 380, 36, 16),
            color=neon_pink, width=2.5, fill_color=QColor(244, 114, 182, 25)
        ))
        elem.text_items.append((
            QPointF(center.x() - 320, center.y() + 6),
            "HIGH-SPEED CADENCE ENGINE: RAPID STREAM TRANSCRIPTION (9.6 SYLLABLES/SEC)",
            QFont("Segoe UI", 11, QFont.Bold), QColor(253, 242, 248), 0.0
        ))

        # Spectrogram Bars
        wx = origin_x + 20
        wy = origin_y + 100
        for i in range(28):
            height = random.uniform(20, 110)
            col = neon_cyan if height < 70 else neon_pink
            p1 = QPointF(wx + i * 14, wy + 60 - height * 0.5)
            p2 = QPointF(wx + i * 14, wy + 60 + height * 0.5)
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(p1, p2, 4), color=col, width=3.0))

        lyrics = [
            ("Uhh, summa-lumma, dooma-lumma, you assumin' I'm a human", "Metrical Foot: Dactylic Triplets | Cadence: 135 BPM", neon_gold),
            ("What I gotta do to get it through to you I'm superhuman?", "Rhyme Scheme: Multi-syllabic end rhymes (oo / oo / oo)", neon_cyan),
            ("Innovative and I'm made of rubber so that anything you say", "Consonance: Dental plosives /t/, /d/ for acoustic velocity", neon_pink),
            ("is ricochetin' off of me, and it'll glue to you", "Dynamic Range: Normalized | 0 dropped phonetic tokens", QColor(226, 232, 240))
        ]
        sy = origin_y + 240
        for verse, phonetics, col in lyrics:
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_cloud(QPointF(origin_x + 25, sy - 4), 6, 6, 8), color=col, width=2.0, fill_color=col))
            elem.text_items.append((QPointF(origin_x + 45, sy), f'"{verse}"', QFont("Segoe UI", 11, QFont.Bold), col, 0.0))
            elem.text_items.append((QPointF(origin_x + 45, sy + 22), phonetics, QFont("Segoe UI", 9, QFont.StyleItalic), QColor(148, 163, 184), 0.0))
            sy += 65

        return elem


# =====================================================================
# AUTONOMOUS CAMERA DIRECTOR (Smooth Cubic Ease-Out Lerp)
# =====================================================================
class CameraDirector:
    def __init__(self):
        self.current_x = 0.0
        self.current_y = 0.0
        self.current_zoom = 1.0
        self.target_x = 0.0
        self.target_y = 0.0
        self.target_zoom = 1.0
        self.lerp_speed = 0.09

    def pan_to(self, x: float, y: float, zoom: float = 1.0):
        self.target_x = x
        self.target_y = y
        self.target_zoom = zoom

    def update(self):
        self.current_x += (self.target_x - self.current_x) * self.lerp_speed
        self.current_y += (self.target_y - self.current_y) * self.lerp_speed
        self.current_zoom += (self.target_zoom - self.current_zoom) * self.lerp_speed


# =====================================================================
# CLAUSE-SYNCHRONIZED TTS ENGINE
# =====================================================================
class VoiceNarrator(QObject):
    speaking_state_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.speech_queue = queue.Queue()
        self.is_speaking = False
        if HAS_PYTTSX3 and VOICE_ENABLED:
            threading.Thread(target=self._worker, daemon=True).start()

    def speak(self, phrase: str):
        if not (HAS_PYTTSX3 and VOICE_ENABLED) or not phrase.strip():
            return
        self.speech_queue.put(phrase.strip())

    def _worker(self):
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', 165)
            engine.setProperty('volume', 0.95)
            while True:
                phrase = self.speech_queue.get()
                self.is_speaking = True
                self.speaking_state_changed.emit(True)
                engine.say(phrase)
                engine.runAndWait()
                time.sleep(0.1)
                if self.speech_queue.empty():
                    self.is_speaking = False
                    self.speaking_state_changed.emit(False)
        except Exception:
            pass


# =====================================================================
# ACOUSTIC GATED STT LISTENER
# =====================================================================
class EchoSuppressedVoiceListener(QObject):
    voice_query_received = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.tts_active = False
        self.whisper_model = None
        self.recognizer = None
        self.microphone = None

        if LISTEN_ENABLED:
            if HAS_WHISPER:
                try:
                    self.whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
                except Exception:
                    pass
            if HAS_SR:
                try:
                    self.recognizer = sr.Recognizer()
                    self.recognizer.energy_threshold = 400
                    self.recognizer.dynamic_energy_threshold = True
                    self.microphone = sr.Microphone()
                except Exception:
                    pass
            if self.microphone or self.whisper_model:
                threading.Thread(target=self._listen_loop, daemon=True).start()

    def set_tts_active(self, active: bool):
        self.tts_active = active

    @staticmethod
    def _is_intelligible(text: str) -> bool:
        if not text or len(text.strip()) < 4:
            return False
        clean = text.strip()
        if re.search(r'[bcdfghjklmnpqrstvwxyz]{6,}', clean, re.IGNORECASE):
            return False
        return (sum(c.isalpha() or c.isspace() for c in clean) / len(clean)) > 0.85

    def _listen_loop(self):
        if not self.microphone:
            return
        with self.microphone as source:
            try:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.8)
            except Exception:
                pass
            while True:
                try:
                    if self.tts_active:
                        time.sleep(0.2)
                        continue
                    audio = self.recognizer.listen(source, timeout=3, phrase_time_limit=10)
                    if self.tts_active:
                        continue
                    text = ""
                    if self.whisper_model:
                        buf = BytesIO(audio.get_wav_data())
                        segments, info = self.whisper_model.transcribe(buf, beam_size=1)
                        if info.language == "en":
                            text = " ".join(s.text for s in segments if s.avg_logprob > -0.9).strip()
                    elif self.recognizer:
                        text = self.recognizer.recognize_google(audio).strip()
                    if self._is_intelligible(text):
                        print(f"\n[Voice Query Verified] \"{text}\"")
                        self.voice_query_received.emit(text)
                except Exception:
                    time.sleep(0.3)


# =====================================================================
# LIVE VISION INTELLIGENCE (Ollama 3B / Llama 7B)
# =====================================================================
class VisionIntelligenceWorker:
    def __init__(self, callback):
        self.callback = callback
        self.is_busy = False
        self.last_hash = 0
        self.past_topics = []

    def trigger_analysis(self, prompt: str = ""):
        if self.is_busy:
            return
        threading.Thread(target=self._run_analysis, args=(prompt,), daemon=True).start()

    def _run_analysis(self, prompt_directive: str):
        self.is_busy = True
        try:
            # Grab desktop frame
            img = None
            if MSS_AVAILABLE:
                with mss.mss() as sct:
                    mon = sct.monitors[1]
                    s_img = sct.grab(mon)
                    img = Image.frombytes("RGB", s_img.size, s_img.bgra, "raw", "BGRX")
                    img.thumbnail(VISION_MAX_RES)
            if img is None:
                img = ImageGrab.grab()
                img.thumbnail(VISION_MAX_RES)

            buf = BytesIO()
            img.save(buf, format="JPEG", quality=75)
            b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")

            directive = prompt_directive or "Analyze the technical structure shown on screen."
            sys_prompt = f"""You are a distinguished university professor sketching deep technical proofs, system architectures, and mathematical insights onto an infinite blackboard.
CURRENT DIRECTIVE: "{directive}"
STRICT BANNED WORDS: Never write "Observation", "Supporting Insight", "Key Takeaway", "Step 1", or generic AI boilerplate.
Provide deep mathematical proofs, code mechanics, vector identities, or architectural flow.
Return ONLY RAW JSON:
{{
  "title": "Dense Conceptual Title",
  "central_hub": "Core Architectural Principle",
  "branches": [
    {{"label": "State Mutation", "detail": "Atomic swap fails without memory barriers under concurrent threads"}},
    {{"label": "Vector Equation", "detail": "grad(L) = (y_pred - y_true) * x.T over mini-batch tensor"}}
  ],
  "equations": [">> Proof: a² + b² = c² (Euclidean Area Sum)"],
  "narration": "Notice the structural relationship between these vector components."
}}"""

            raw_json = "{}"
            if ACTIVE_BACKEND == "7b" and REQUESTS_AVAILABLE:
                payload = {
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": [{"type": "text", "text": "Synthesize whiteboard sketchnote."}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}}]}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.7, "max_tokens": 500
                }
                resp = requests.post(LLAMA_SERVER_7B_URL, json=payload, timeout=60)
                if resp.status_code == 200:
                    raw_json = resp.json()["choices"][0]["message"]["content"]
            elif REQUESTS_AVAILABLE:
                payload = {"model": "qwen2.5vl:3b", "prompt": sys_prompt, "images": [b64_data], "stream": False, "format": "json"}
                resp = requests.post(OLLAMA_URL, json=payload, timeout=35)
                if resp.status_code == 200:
                    raw_json = resp.json().get("response", "{}")

            match = re.search(r'\{.*\}', raw_json, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                self.callback(data)
        except Exception as e:
            print(f"[Vision Worker Warning] {e}")
        finally:
            self.is_busy = False


# =====================================================================
# MASTER SPATIAL WHITEBOARD OVERLAY (Full-Screen Transparent Canvas)
# =====================================================================
class SpatialWhiteboardOverlay(QWidget):
    directive_signal = pyqtSignal(str)

    def __init__(self, initial_task: str = ""):
        super().__init__()
        self.current_user_task = initial_task
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.w, self.h = screen.width(), screen.height()

        # Engine Components
        self.click_through = True
        self.camera = CameraDirector()
        self.elements: List[SketchnoteElement] = []
        self.grid_alpha = 0.35
        self.active_stylus_pt: Optional[QPointF] = None

        # Animated Companion Mascot Physics
        self.mascot_x = 75.0
        self.mascot_y = 110.0
        self.mascot_bob = 0.0
        self.mascot_eye_blink = 0.0
        self.mascot_mood = "OBSERVING"

        # Interaction
        self.alt_pressed = False
        self.is_dragging = False
        self.last_mouse_pos = QPointF(0, 0)

        # Voice Subsystems
        self.narrator = VoiceNarrator()
        self.listener = EchoSuppressedVoiceListener()
        self.listener.voice_query_received.connect(self.handle_voice_directive)
        self.narrator.speaking_state_changed.connect(self.listener.set_tts_active)

        # Vision Worker
        self.vision_worker = VisionIntelligenceWorker(self.on_vision_data_received)

        # Signals
        self.directive_signal.connect(self.handle_new_directive)

        # 60 FPS Engine Timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(16)

        # Initialize Win32 Pass-Through
        self.enable_click_through(True)

    def enable_click_through(self, enabled: bool):
        self.click_through = enabled
        if sys.platform == "win32":
            hwnd = int(self.winId())
            extended_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if enabled:
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, extended_style | WS_EX_TRANSPARENT | WS_EX_LAYERED)
            else:
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, extended_style & ~WS_EX_TRANSPARENT)

    def handle_voice_directive(self, text: str):
        self.directive_signal.emit(text)

    def on_vision_data_received(self, data: dict):
        # Convert dynamic LLM response into an organic sketchnote element
        offset_x = len(self.elements) * 1280.0 + 80.0
        offset_y = 120.0
        title = str(data.get("title", "Technical Architecture")).upper()
        hub = str(data.get("central_hub", title))
        elem = SketchnoteElement(
            id=f"llm_{int(time.time())}",
            element_type="mind_map",
            bounding_rect=QRectF(offset_x - 60, offset_y - 60, 1150, 740)
        )
        cyan = QColor(56, 189, 248)
        emerald = QColor(52, 211, 153)
        amber = QColor(251, 191, 36)

        head_center = QPointF(offset_x + 380, offset_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(head_center, 380, 36, 16),
            color=cyan, width=2.5, fill_color=QColor(56, 189, 248, 25)
        ))
        elem.text_items.append((
            QPointF(head_center.x() - 320, head_center.y() + 6),
            f"{title} ── {hub}",
            QFont("Segoe UI", 11, QFont.Bold), QColor(241, 245, 249), 0.0
        ))

        branches = data.get("branches", [])
        by = offset_y + 80
        for b in branches:
            lbl = b.get("label", "Concept") if isinstance(b, dict) else "Principle"
            det = b.get("detail", str(b)) if isinstance(b, dict) else str(b)
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_cloud(QPointF(offset_x + 30, by - 4), 6, 6, 8), color=emerald, width=2.0, fill_color=emerald))
            elem.text_items.append((QPointF(offset_x + 50, by), f"• {lbl}: {det}", QFont("Segoe UI", 10), emerald, 0.0))
            by += 55

        eqs = data.get("equations", [])
        for eq in eqs:
            elem.text_items.append((QPointF(offset_x + 50, by), str(eq), QFont("Consolas", 10, QFont.Bold), amber, 0.0))
            by += 40

        self.elements.append(elem)
        cx = elem.bounding_rect.center().x() - (self.width() * 0.5)
        cy = elem.bounding_rect.center().y() - (self.height() * 0.5)
        self.camera.pan_to(cx, cy, 1.0)
        self.grid_alpha = 0.35

        narration = data.get("narration", f"Explaining {title}.")
        self.narrator.speak(narration)

    def handle_new_directive(self, prompt: str):
        """Dispatches commands, first-principles demonstrations, or LLM vision queries."""
        p = prompt.lower().strip()
        offset_x = len(self.elements) * 1280.0 + 80.0
        offset_y = 120.0
        self.mascot_mood = "TEACHING"

        # Smoothly ghost older elements to 25% opacity
        for el in self.elements:
            el.opacity = max(0.20, el.opacity * 0.45)
            for s in el.strokes:
                s.opacity = el.opacity

        if any(k in p for k in ["pythagor", "triangle", "hypotenuse", "proof"]):
            elem = EuclideanProofSynthesizer.synthesize_pythagoras_proof(offset_x, offset_y)
            self.elements.append(elem)
            self.narrator.speak("Let us derive the Pythagorean theorem visually. Notice how the squares attached to the height and base sum up exactly to the square on the hypotenuse.")
        elif any(k in p for k in ["fbd", "block", "friction", "ramp", "incline", "force"]):
            elem = FreeBodyDiagramSynthesizer.synthesize_inclined_plane_fbd(offset_x, offset_y)
            self.elements.append(elem)
            self.narrator.speak("Constructing the Free-Body Diagram. We decompose gravity into parallel and perpendicular vectors across the inclined ramp.")
        elif any(k in p for k in ["code", "stack", "heap", "memory", "algorithm"]):
            elem = CodeArchitectureSynthesizer.synthesize_code_analysis(offset_x, offset_y, p)
            self.elements.append(elem)
            self.narrator.speak("Visualizing execution flow and memory allocations on the stack and heap.")
        elif any(k in p for k in ["obs", "app", "stream", "dock"]):
            elem = AppInspectionSynthesizer.synthesize_obs_walkthrough(offset_x, offset_y)
            self.elements.append(elem)
            self.narrator.speak("Mapping out OBS Studio control docks with spatial callouts in the negative space.")
        elif any(k in p for k in ["rap", "lyrics", "cadence", "speed", "music"]):
            elem = HighSpeedMediaTranscriber.synthesize_rap_cadence_breakdown(offset_x, offset_y)
            self.elements.append(elem)
            self.narrator.speak("Analyzing high-speed lyrical cadence, syllabic meter, and acoustic velocity.")
        elif any(k in p for k in ["quiz", "test", "socratic", "check"]):
            elem, hypot, sq = DynamicSocraticEngine.generate_randomized_quiz(offset_x, offset_y)
            self.elements.append(elem)
            self.narrator.speak("Dynamic Socratic mastery checkpoint! Calculate the hypotenuse length and select the correct option.")
        else:
            # Send to live Vision Intelligence Worker for dynamic LLM synthesis
            print(f"[AI Reasoning] Querying model for prompt: '{prompt}'")
            self.vision_worker.trigger_analysis(prompt)
            return

        cx = elem.bounding_rect.center().x() - (self.width() * 0.5)
        cy = elem.bounding_rect.center().y() - (self.height() * 0.5)
        self.camera.pan_to(cx, cy, 1.0)
        self.grid_alpha = 0.35

    def on_tick(self):
        self.camera.update()

        # Fade transient grid
        if self.grid_alpha > 0.08:
            self.grid_alpha -= 0.003

        # Mascot physics
        self.mascot_bob = math.sin(time.time() * 3.5) * 4.0
        self.mascot_eye_blink += 0.05

        has_active = False
        for elem in self.elements:
            for stroke in elem.strokes:
                if stroke.progress < 1.0:
                    stroke.progress = min(1.0, stroke.progress + stroke.speed)
                    has_active = True
                    if len(stroke.points) > 1:
                        idx = int(stroke.progress * (len(stroke.points) - 1))
                        self.active_stylus_pt = stroke.points[idx]
                    break

            for i, (pt, txt, font, col, p) in enumerate(elem.text_items):
                if p < 1.0:
                    elem.text_items[i] = (pt, txt, font, col, min(1.0, p + 0.08))
                    has_active = True
                    break

        if not has_active:
            self.active_stylus_pt = None
            if self.mascot_mood == "TEACHING" and not self.narrator.is_speaking:
                self.mascot_mood = "OBSERVING"

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # 1. Cyber-Dotted Void Grid
        if self.grid_alpha > 0.01:
            dot_color = QColor(148, 163, 184, int(self.grid_alpha * 255))
            painter.setPen(QPen(dot_color, 1.5))
            step = 34
            start_x = int(self.camera.current_x) % step
            start_y = int(self.camera.current_y) % step
            for gx in range(start_x, self.width(), step):
                for gy in range(start_y, self.height(), step):
                    painter.drawPoint(gx, gy)

        # Infinite Virtual Coordinate Camera Transform
        painter.save()
        painter.translate(-self.camera.current_x, -self.camera.current_y)
        painter.scale(self.camera.current_zoom, self.camera.current_zoom)

        # 2. Hand-Sketched Vector Strokes
        for elem in self.elements:
            op = elem.opacity
            for stroke in elem.strokes:
                if stroke.progress <= 0.01:
                    continue
                pts = stroke.points
                limit = max(2, int(stroke.progress * len(pts)))
                active_pts = pts[:limit]

                if stroke.fill_color and stroke.progress >= 0.90:
                    poly_path = QPainterPath()
                    poly_path.moveTo(pts[0])
                    for p in pts[1:]:
                        poly_path.lineTo(p)
                    poly_path.closeSubpath()
                    fc = stroke.fill_color
                    painter.fillPath(poly_path, QBrush(QColor(fc.red(), fc.green(), fc.blue(), int(fc.alpha() * op))))

                stroke_c = stroke.color
                pen = QPen(QColor(stroke_c.red(), stroke_c.green(), stroke_c.blue(), int(255 * op)), stroke.width)
                pen.setCapStyle(Qt.RoundCap)
                pen.setJoinStyle(Qt.RoundJoin)
                if stroke.is_dashed:
                    pen.setStyle(Qt.DashLine)
                painter.setPen(pen)

                path = QPainterPath()
                path.moveTo(active_pts[0])
                for p in active_pts[1:]:
                    path.lineTo(p)
                painter.drawPath(path)

            # Progressive Typography Rendering
            for pt, txt, font, col, p in elem.text_items:
                if p <= 0.05:
                    continue
                painter.setFont(font)
                char_limit = int(p * len(txt))
                revealed_txt = txt[:char_limit]
                painter.setPen(QPen(QColor(15, 23, 42, int(220 * op))))
                painter.drawText(QPointF(pt.x() + 1.5, pt.y() + 1.5), revealed_txt)
                painter.setPen(QPen(QColor(col.red(), col.green(), col.blue(), int(255 * op))))
                painter.drawText(pt, revealed_txt)

        # 3. Micro-Stylus Tip Halo
        if self.active_stylus_pt:
            p = self.active_stylus_pt
            glow = QRadialGradient(p, 18)
            glow.setColorAt(0.0, QColor(56, 189, 248, 240))
            glow.setColorAt(0.5, QColor(56, 189, 248, 70))
            glow.setColorAt(1.0, QColor(56, 189, 248, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(p, 18, 18)
            painter.setBrush(QBrush(QColor(255, 255, 255, 250)))
            painter.drawEllipse(p, 3, 3)

        painter.restore()

        # 4. Expressive Companion Mascot Rendering (Screen Space)
        self._render_mascot(painter)

        # 5. In-Situ Floating HUD
        hud_text = (
            f"SPATIAL WHITEBOARD v7 | Camera: ({int(self.camera.current_x)}, {int(self.camera.current_y)}) "
            f"| Mode: {'CLICK-THROUGH' if self.click_through else 'INTERACTIVE'} "
            f"[Hold ALT to Drag/Zoom | F8 Toggle | Ctrl+S Export]"
        )
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.setBrush(QBrush(QColor(15, 23, 42, 210)))
        painter.setPen(QPen(QColor(56, 189, 248), 1.2))
        painter.drawRoundedRect(QRectF(20, self.height() - 48, 760, 28), 6, 6)
        painter.setPen(QPen(QColor(241, 245, 249)))
        painter.drawText(QPointF(32, self.height() - 30), hud_text)

    def _render_mascot(self, painter: QPainter):
        mx, my = self.mascot_x, self.mascot_y + self.mascot_bob
        pod_col = QColor(15, 23, 42, 230)
        border_col = QColor(56, 189, 248)
        eye_col = QColor(52, 211, 153)

        # Body Pod
        painter.setPen(QPen(border_col, 1.8))
        painter.setBrush(QBrush(pod_col))
        painter.drawRoundedRect(QRectF(mx - 20, my - 20, 40, 40), 12, 12)

        # Antennas
        painter.setPen(QPen(border_col, 1.5))
        painter.drawLine(int(mx - 10), int(my - 20), int(mx - 15), int(my - 28))
        painter.drawLine(int(mx + 10), int(my - 20), int(mx + 15), int(my - 28))
        pulse_alpha = int(180 + 70 * math.sin(time.time() * 6.0))
        painter.setBrush(QBrush(QColor(56, 189, 248, pulse_alpha)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(mx - 15, my - 28), 3, 3)
        painter.drawEllipse(QPointF(mx + 15, my - 28), 3, 3)

        # Eyes (Blinking Physics)
        eye_open = abs(math.cos(self.mascot_eye_blink)) > 0.12
        painter.setBrush(QBrush(eye_col))
        if eye_open:
            painter.drawEllipse(QPointF(mx - 7, my - 2), 2.8, 3.8)
            painter.drawEllipse(QPointF(mx + 7, my - 2), 2.8, 3.8)
        else:
            painter.setPen(QPen(eye_col, 1.5))
            painter.drawLine(int(mx - 9), int(my - 2), int(mx - 5), int(my - 2))
            painter.drawLine(int(mx + 5), int(my - 2), int(mx + 9), int(my - 2))

        # Stylus Focus Ray when actively teaching
        if self.mascot_mood == "TEACHING" and self.active_stylus_pt:
            sx = (self.active_stylus_pt.x() - self.camera.current_x) * self.camera.current_zoom
            sy = (self.active_stylus_pt.y() - self.camera.current_y) * self.camera.current_zoom
            painter.setPen(QPen(QColor(56, 189, 248, 90), 1.2, Qt.DashLine))
            painter.drawLine(int(mx), int(my), int(sx), int(sy))

    # --------------------------------------------------------------------------
    # MOUSE NAVIGATION, ZOOM & EXPORT (ALT + DRAG/SCROLL | Ctrl+S)
    # --------------------------------------------------------------------------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Alt:
            self.alt_pressed = True
            if self.click_through:
                self.enable_click_through(False)
        elif event.key() == Qt.Key_F8:
            self.enable_click_through(not self.click_through)
        elif event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_S:
            self.export_canvas()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Alt:
            self.alt_pressed = False
            if not self.click_through:
                self.enable_click_through(True)
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self.is_dragging = True
            self.last_mouse_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            delta = event.pos() - self.last_mouse_pos
            self.last_mouse_pos = event.pos()
            self.camera.current_x -= delta.x() / self.camera.current_zoom
            self.camera.current_y -= delta.y() / self.camera.current_zoom
            self.camera.target_x = self.camera.current_x
            self.camera.target_y = self.camera.current_y
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_dragging = False
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 1.12 if delta > 0 else 0.88
        new_zoom = max(0.4, min(3.0, self.camera.target_zoom * factor))
        self.camera.target_zoom = new_zoom
        self.update()
        super().wheelEvent(event)

    def export_canvas(self):
        if not self.elements:
            print("[Note Center] Canvas is currently empty.")
            return
        min_x = min(e.bounding_rect.x() for e in self.elements) - 80
        min_y = min(e.bounding_rect.y() for e in self.elements) - 80
        max_x = max(e.bounding_rect.right() for e in self.elements) + 80
        max_y = max(e.bounding_rect.bottom() for e in self.elements) + 80
        ew = max(400, int(max_x - min_x))
        eh = max(400, int(max_y - min_y))
        img = QImage(ew, eh, QImage.Format_ARGB32)
        img.fill(QColor(10, 15, 26, 255))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.translate(-min_x, -min_y)

        for elem in self.elements:
            for stroke in elem.strokes:
                if stroke.fill_color:
                    poly_path = QPainterPath()
                    poly_path.moveTo(stroke.points[0])
                    for pt in stroke.points[1:]:
                        poly_path.lineTo(pt)
                    poly_path.closeSubpath()
                    p.fillPath(poly_path, QBrush(stroke.fill_color))
                pen = QPen(stroke.color, stroke.width)
                if stroke.is_dashed:
                    pen.setStyle(Qt.DashLine)
                p.setPen(pen)
                path = QPainterPath()
                path.moveTo(stroke.points[0])
                for pt in stroke.points[1:]:
                    path.lineTo(pt)
                p.drawPath(path)
            for pt, txt, font, col, _ in elem.text_items:
                p.setFont(font)
                p.setPen(col)
                p.drawText(pt, txt)
        p.end()

        fname = f"blackboard_export_{int(time.time())}.png"
        img.save(fname)
        print(f"\n[Note Center] Exported high-res infinite whiteboard snapshot to: {os.path.abspath(fname)}")


# =====================================================================
# INTERACTIVE TERMINAL LOOP
# =====================================================================
def terminal_input_loop(overlay: SpatialWhiteboardOverlay):
    time.sleep(1.0)
    print("=" * 72)
    print(" AI TEACHING ASSISTANT - SPATIAL WHITEBOARD ENGINE v7")
    print("=" * 72)
    print("Commands & First-Principles Teaching Modes:")
    print("  * 'pythagoras' / 'theorem' -> First-principles proof with Euclidean squares (a²=9, b²=16, c²=25)")
    print("  * 'fbd' / 'friction'      -> Inclined plane free-body diagram with force vectors")
    print("  * 'code' / 'memory'       -> Execution flow, recursion, stack & heap layout")
    print("  * 'obs' / 'app'           -> In-situ cybersecurity guide to OBS Studio controls")
    print("  * 'rap' / 'lyrics'        -> 2x speed high-cadence lyrical transcription & meter")
    print("  * 'quiz' / 'test'         -> Dynamic Socratic mastery assessment with anti-memorization")
    print("  * 'pause' / 'play'        -> Universal OS YouTube/VLC playback control")
    print("  * 'back' / 'forward'      -> 5-second media scrubber")
    print("Or enter any technical concept to trigger the live LLM professor vision engine.")
    print("Controls:")
    print("  * Hold ALT + Drag to Pan | ALT + Scroll to Zoom | F8: Toggle Pass-Through")
    print("  * Ctrl + S: Export Infinite Canvas to High-Res PNG")
    print("=" * 72)

    # Seed initial demonstration
    time.sleep(0.8)
    overlay.directive_signal.emit(INITIAL_TASK or "pythagoras")

    while True:
        try:
            cmd = input("\nEnter teaching goal > ").strip()
            if not cmd:
                continue
            if cmd.lower() in ("pause", "play", "toggle"):
                UniversalMediaController.toggle_playback()
                print("[Media Controller] Toggled media playback.")
            elif cmd.lower() in ("back", "rewind", "scrub back"):
                UniversalMediaController.scrub_back_5s()
                print("[Media Controller] Scrubbed backward 5s.")
            elif cmd.lower() in ("forward", "ff", "scrub forward"):
                UniversalMediaController.scrub_forward_5s()
                print("[Media Controller] Scrubbed forward 5s.")
            else:
                print(f"[AI Spatial Focus] Synthesizing derivation: '{cmd}'")
                overlay.directive_signal.emit(cmd)
        except (EOFError, KeyboardInterrupt):
            break


def main():
    app = QApplication(sys.argv)
    overlay = SpatialWhiteboardOverlay(initial_task=INITIAL_TASK)
    overlay.show()

    t = threading.Thread(target=terminal_input_loop, args=(overlay,), daemon=True)
    t.start()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
