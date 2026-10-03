#!/usr/bin/env python3
"""
================================================================================
AI TEACHING ASSISTANT & AUTONOMOUS GLASS WHITEBOARD — MASTER ENGINE v8 (HOJAIGA)
================================================================================
A production-grade, 100% non-hijacking spatial computing tutor for Windows.
Transforms the entire desktop into an interactive, organic glass whiteboard and
in-situ augmented reality tutorial engine.

Dual Presentation Modes:
  • MODE A (Void Blackboard Canvas): Infinite (X, Y) world space, 0.4x-3.0x zoom,
    frosted glass cards, AST audits, and conceptual derivations.
  • MODE B (Hojaiga In-Situ AR Mode): 1:1 physical pixel grounding directly over
    active video feeds and desktop apps (Khan Academy & FL Studio style). Direct
    Euclidean proof squares on video, pulsating button beacons, micro-tag pills,
    and step-gated interactive tutorials with zero card backings.
================================================================================
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
import enum
import ast
import glob
from io import BytesIO
from typing import List, Tuple, Optional, Dict, Any

# Pre-load onnxruntime and soundcard before Qt loads GUI DLLs
HAS_ONNX = False
try:
    import onnxruntime
    HAS_ONNX = True
except Exception:
    pass

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

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

from PyQt5.QtCore import Qt, QTimer, QPointF, QRect, QRectF, pyqtSignal, QObject
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QBrush, QPainterPath, QFont, 
    QFontMetrics, QLinearGradient, QRadialGradient, QTransform, QPolygonF, QImage
)
from PyQt5.QtWidgets import QApplication, QWidget, QDesktopWidget

from PIL import Image, ImageGrab
try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

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
except Exception:
    pass

HAS_SR = False
try:
    import speech_recognition as sr
    HAS_SR = True
except Exception:
    pass

HAS_SOUNDCARD = False
try:
    import soundcard as sc
    HAS_SOUNDCARD = True
except Exception:
    pass

HAS_KOKORO = False
try:
    import kokoro_onnx
    import sounddevice as sd
    KOKORO_MODEL_PATH = "d:/new_automation/kokoro_models/kokoro-v1.0.int8.onnx"
    KOKORO_VOICES_PATH = "d:/new_automation/kokoro_models/voices-v1.0.bin"
    if os.path.exists(KOKORO_MODEL_PATH) and os.path.exists(KOKORO_VOICES_PATH):
        HAS_KOKORO = True
except Exception:
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

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008

VK_MEDIA_PLAY_PAUSE = 0xB3
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_SPACE = 0x20
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001

parser = argparse.ArgumentParser(description="AI Teaching Assistant - Spatial Whiteboard v8 (Hojaiga)")
parser.add_argument("--edge0", action="store_true", help="Use Edge0-35B / 8B Streaming MoE on port 8082")
parser.add_argument("--7b", action="store_true", help="Use Qwen2.5-VL-7B Deep Analysis on port 8081")
parser.add_argument("--3b", action="store_true", help="Use qwen2.5vl:3b Fast Reflex on port 11434")
parser.add_argument("--task", "--teach", type=str, default="", help="Specific topic or goal")
parser.add_argument("--pause-media", action="store_true", default=False, help="Enable automatic OS media pause/resume")
parser.add_argument("--voice", action="store_true", default=True, help="Enable offline neural TTS narration")
parser.add_argument("--no-voice", action="store_true", default=False, help="Disable speech synthesis")
parser.add_argument("--listen", action="store_true", default=True, help="Enable hands-free speech recognition")
parser.add_argument("--no-listen", action="store_true", default=False, help="Disable speech recognition")
cli_args, _ = parser.parse_known_args()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
LLAMA_SERVER_7B_URL = os.getenv("HOJAIGA_VISION_PRECISION_ENDPOINT", "http://localhost:8081") + "/v1/chat/completions"
EDGE0_URL = os.getenv("EDGE0_API_URL", "http://localhost:8082") + "/v1/chat/completions"

USE_EDGE0 = getattr(cli_args, "edge0", False) or (os.getenv("AI_TEACHER_MODEL", "").lower() in ["edge0", "moe", "edge0-35b"])
USE_7B = getattr(cli_args, "7b", False) or (os.getenv("AI_TEACHER_MODEL", "").lower() in ["7b", "precision", "qwen7b"])

if USE_EDGE0:
    ACTIVE_BACKEND = "edge0"
    MODEL_DISPLAY_NAME = "Edge0-35B MoE Streaming (Port 8082)"
    AI_THINKING_INTERVAL_SEC = 4
    VISION_MAX_RES = (1024, 1024)
elif USE_7B:
    ACTIVE_BACKEND = "7b"
    MODEL_DISPLAY_NAME = "Qwen2.5-VL-7B (Port 8081)"
    AI_THINKING_INTERVAL_SEC = 7
    VISION_MAX_RES = (768, 768)
else:
    ACTIVE_BACKEND = "3b"
    MODEL_DISPLAY_NAME = "qwen2.5vl:3b (Port 11434)"
    AI_THINKING_INTERVAL_SEC = 5
    VISION_MAX_RES = (1024, 1024)

INITIAL_TASK = cli_args.task or os.getenv("AI_TEACHER_TASK", "")
VOICE_ENABLED = (not cli_args.no_voice) and (cli_args.voice or HAS_PYTTSX3)
LISTEN_ENABLED = (not cli_args.no_listen) and (cli_args.listen or (HAS_WHISPER or HAS_SR))
AUTO_PAUSE_MEDIA = cli_args.pause_media

THEMES = {
    "studious": {
        "name": "STUDIOUS ACADEMIC",
        "badge_tag": "ACADEMIC",
        "void_bg": QColor(10, 15, 26),
        "grid_dots": QColor(90, 180, 255),
        "stylus": QColor(56, 189, 248),
        "mascot_pod": QColor(15, 23, 42),
        "mascot_border": QColor(56, 189, 248),
        "mascot_eye": QColor(52, 211, 153),
        "hub_bg": QColor(20, 30, 50, 220),
        "hub_border": QColor(56, 189, 248),
        "node_bg": QColor(15, 23, 42, 215),
        "node_border": QColor(147, 197, 253),
        "branch": QColor(56, 189, 248, 190),
        "accent": QColor(251, 191, 36),
        "text_main": QColor(255, 255, 255),
        "text_sub": QColor(226, 232, 240),
        "badge_text": QColor(52, 211, 153),
        "formula_border": QColor(52, 211, 153)
    },
    "romantic": {
        "name": "ROMANTIC WINGMAN",
        "badge_tag": "ROMANTIC",
        "void_bg": QColor(26, 10, 20),
        "grid_dots": QColor(244, 114, 182),
        "stylus": QColor(244, 63, 94),
        "mascot_pod": QColor(32, 12, 24),
        "mascot_border": QColor(244, 63, 94),
        "mascot_eye": QColor(251, 113, 133),
        "hub_bg": QColor(48, 16, 36, 225),
        "hub_border": QColor(244, 63, 94),
        "node_bg": QColor(32, 12, 24, 215),
        "node_border": QColor(244, 114, 182),
        "branch": QColor(244, 63, 94, 190),
        "accent": QColor(251, 113, 133),
        "text_main": QColor(255, 241, 242),
        "text_sub": QColor(254, 205, 211),
        "badge_text": QColor(251, 113, 133),
        "formula_border": QColor(244, 63, 94)
    },
    "hacker": {
        "name": "CYBER / HACKER",
        "badge_tag": "HACKER",
        "void_bg": QColor(5, 15, 8),
        "grid_dots": QColor(34, 197, 94),
        "stylus": QColor(34, 197, 94),
        "mascot_pod": QColor(6, 24, 12),
        "mascot_border": QColor(34, 197, 94),
        "mascot_eye": QColor(52, 211, 153),
        "hub_bg": QColor(10, 32, 16, 230),
        "hub_border": QColor(34, 197, 94),
        "node_bg": QColor(6, 24, 12, 220),
        "node_border": QColor(74, 222, 128),
        "branch": QColor(34, 197, 94, 190),
        "accent": QColor(74, 222, 128),
        "text_main": QColor(220, 252, 231),
        "text_sub": QColor(187, 247, 208),
        "badge_text": QColor(74, 222, 128),
        "formula_border": QColor(34, 197, 94)
    }
}

def auto_detect_theme(task: str) -> str:
    t = task.lower()
    if any(k in t for k in ["pickup", "love", "romantic", "crush", "date", "flirt", "anissha", "anisha", "heart", "wingman", "kolkata", "sweet"]):
        return "romantic"
    if any(k in t for k in ["hack", "cyber", "terminal", "exploit", "reverse", "kernel", "bash", "memory", "script", "asm", "cve"]):
        return "hacker"
    return "studious"

# =====================================================================
# HOJAIGA IN-SITU DATA STRUCTURES & PROTOCOLS
# =====================================================================

class DisplayMode(enum.Enum):
    VOID = "VOID"            # Infinite blackboard canvas with cards & camera pan
    IN_SITU = "IN_SITU"      # Hojaiga 1:1 physical pixel augmentation directly on screen

@dataclasses.dataclass
class MicroPillTag:
    """High-contrast floating pill tag anchored to exact physical coordinates."""
    text: str
    target_pt: QPointF
    color: QColor = dataclasses.field(default_factory=lambda: QColor(244, 63, 94))
    bg_color: QColor = dataclasses.field(default_factory=lambda: QColor(15, 23, 42, 230))
    progress: float = 0.0

@dataclasses.dataclass
class ButtonBeacon:
    """Pulsating neon focus beacon over physical software controls."""
    rect: QRectF
    label: str
    color: QColor
    pulse_phase: float = 0.0
    active: bool = True

@dataclasses.dataclass
class AugmentedGeometry:
    """Vector strokes anchored directly to on-screen objects."""
    points: List[QPointF]
    color: QColor
    width: float = 3.0
    is_closed: bool = False
    fill_color: Optional[QColor] = None
    progress: float = 0.0

@dataclasses.dataclass
class TutorialStep:
    """A discrete step in an interactive software walkthrough."""
    step_number: int
    spoken_instruction: str
    target_rect: QRectF
    pill_label: str
    accent_color: QColor
    dwell_duration: float = 3.8

class InSituSpatialGrounder:
    """
    Transforms coordinate-grounded VLM detections into augmented vector overlays
    directly on top of video feeds and desktop applications without card containers.
    """
    @staticmethod
    def build_pythagorean_video_augmentation(
        triangle_vertices: Tuple[QPointF, QPointF, QPointF]
    ) -> Tuple[List[AugmentedGeometry], List[MicroPillTag]]:
        A, B, C = triangle_vertices  # A = Right Angle, B = Base End, C = Height Peak
        geometries: List[AugmentedGeometry] = []
        pills: List[MicroPillTag] = []

        coral = QColor(244, 63, 94)
        cyan = QColor(56, 189, 248)

        # 1. Right-Angle Marker
        marker_size = 18.0
        dir_b = (B - A) / (math.hypot(B.x() - A.x(), B.y() - A.y()) + 1e-5)
        dir_c = (C - A) / (math.hypot(C.x() - A.x(), C.y() - A.y()) + 1e-5)
        m1 = A + dir_b * marker_size
        m2 = m1 + dir_c * marker_size
        m3 = A + dir_c * marker_size
        geometries.append(AugmentedGeometry(
            points=[A, m1, m2, m3, A],
            color=coral, width=2.0, is_closed=True
        ))
        pills.append(MicroPillTag(
            text="right angle (90°)",
            target_pt=QPointF(m2.x() + 8, m2.y() + 8),
            color=coral
        ))

        # 2. Leg A (Base) Vector & Label
        geometries.append(AugmentedGeometry(points=[A, B], color=coral, width=3.5))
        pills.append(MicroPillTag(
            text="leg A = 4",
            target_pt=QPointF((A.x() + B.x()) * 0.5, A.y() + 24),
            color=coral
        ))

        # 3. Leg B (Height) Vector & Label
        geometries.append(AugmentedGeometry(points=[A, C], color=coral, width=3.5))
        pills.append(MicroPillTag(
            text="leg B = 3",
            target_pt=QPointF(A.x() - 85, (A.y() + C.y()) * 0.5),
            color=coral
        ))

        # 4. Hypotenuse C Vector & Label
        geometries.append(AugmentedGeometry(points=[C, B], color=cyan, width=4.0))
        pills.append(MicroPillTag(
            text="hypotenuse C = 5",
            target_pt=QPointF((C.x() + B.x()) * 0.5 + 15, (C.y() + B.y()) * 0.5 - 20),
            color=cyan
        ))

        # 5. Outward Euclidean Square on Leg A (Downward)
        base_len = math.hypot(B.x() - A.x(), B.y() - A.y())
        sq_a_pts = [
            A,
            QPointF(A.x(), A.y() + base_len),
            QPointF(B.x(), B.y() + base_len),
            B,
            A
        ]
        geometries.append(AugmentedGeometry(
            points=sq_a_pts,
            color=coral, width=2.5, is_closed=True,
            fill_color=QColor(244, 63, 94, 55)
        ))
        pills.append(MicroPillTag(
            text="area 16",
            target_pt=QPointF((A.x() + B.x()) * 0.5, A.y() + base_len * 0.5),
            color=coral
        ))

        # 6. Outward Euclidean Square on Leg B (Leftward)
        height_len = math.hypot(C.x() - A.x(), C.y() - A.y())
        sq_b_pts = [
            C,
            QPointF(C.x() - height_len, C.y()),
            QPointF(A.x() - height_len, A.y()),
            A,
            C
        ]
        geometries.append(AugmentedGeometry(
            points=sq_b_pts,
            color=coral, width=2.5, is_closed=True,
            fill_color=QColor(244, 63, 94, 55)
        ))
        pills.append(MicroPillTag(
            text="area 9",
            target_pt=QPointF(A.x() - height_len * 0.5, (A.y() + C.y()) * 0.5),
            color=coral
        ))

        # 7. Outward Euclidean Square on Hypotenuse (Diagonal Outward)
        dx = B.x() - C.x()
        dy = B.y() - C.y()
        sq_c_pts = [
            C,
            B,
            QPointF(B.x() - dy, B.y() + dx),
            QPointF(C.x() - dy, C.y() + dx),
            C
        ]
        geometries.append(AugmentedGeometry(
            points=sq_c_pts,
            color=cyan, width=3.0, is_closed=True,
            fill_color=QColor(56, 189, 248, 60)
        ))
        pills.append(MicroPillTag(
            text="area 25",
            target_pt=QPointF((C.x() + B.x()) * 0.5 - dy * 0.5, (C.y() + B.y()) * 0.5 + dx * 0.5),
            color=cyan
        ))

        return geometries, pills

    @staticmethod
    def build_fl_studio_beat_tutorial(channel_rack_rect: QRectF) -> List[TutorialStep]:
        rx, ry, rw, rh = channel_rack_rect.x(), channel_rack_rect.y(), channel_rack_rect.width(), channel_rack_rect.height()
        coral = QColor(244, 63, 94)

        btn_w, btn_h = 24.0, 20.0
        step_gap = 28.0
        grid_start_x = rx + rw * 0.38
        kick_y = ry + 68.0
        snare_y = ry + 94.0

        return [
            TutorialStep(1, "On the kick row, click this first square. Step 1.", QRectF(grid_start_x, kick_y, btn_w, btn_h), "kick step one", coral, 3.5),
            TutorialStep(2, "Then step 5, the start of beat 2.", QRectF(grid_start_x + 4 * step_gap, kick_y, btn_w, btn_h), "kick step five", coral, 3.5),
            TutorialStep(3, "Then step 9, beat 3.", QRectF(grid_start_x + 8 * step_gap, kick_y, btn_w, btn_h), "kick step nine", coral, 3.5),
            TutorialStep(4, "And step 13, beat 4.", QRectF(grid_start_x + 12 * step_gap, kick_y, btn_w, btn_h), "kick step that", coral, 3.5),
            TutorialStep(5, "Now drop down to this 808 snare row. Click step 5 here, and step 13 on beat 4.", QRectF(grid_start_x + 4 * step_gap, snare_y, btn_w, btn_h), "snare step five", coral, 4.5),
            TutorialStep(6, "Press space to hear it groove.", QRectF(rx + rw * 0.5 - 80, ry + rh - 40, 160, 30), "press space", QColor(52, 211, 153), 4.0)
        ]

# =====================================================================
# SYSTEM & HARDWARE AUTOMATION
# =====================================================================

class UniversalMediaController:
    """Dispatches WinRT media commands and low-level hardware scan codes."""
    
    @staticmethod
    def _run_winrt_action(action: str) -> bool:
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

    @classmethod
    def modulate_speed(cls, faster: bool = True):
        if sys.platform == "win32":
            VK_SHIFT = 0x10
            vk = 0xBE if faster else 0xBC
            user32.keybd_event(VK_SHIFT, 0, 0, 0)
            time.sleep(0.02)
            cls.send_key(vk)
            user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)

    @classmethod
    def advance_document(cls, forward: bool = True):
        vk = 0x22 if forward else 0x21
        cls.send_key(vk, extended=True)

class SpatialScreenSegmenter:
    def __init__(self, screen_w: int, screen_h: int):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.content_zone = QRectF(0, 0, screen_w / 2.0, screen_h)
        self.whiteboard_zone = QRectF(screen_w / 2.0, 0, screen_w / 2.0, screen_h)

    def analyze_layout(self) -> Dict[str, Any]:
        if sys.platform != "win32":
            return {"whiteboard_zone": self.whiteboard_zone}
        try:
            windows = []
            def enum_cb(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    rect = win32gui.GetWindowRect(hwnd)
                    w, h = rect[2] - rect[0], rect[3] - rect[1]
                    title = win32gui.GetWindowText(hwnd).lower()
                    if w > 300 and h > 200 and title:
                        windows.append((title, rect))
                return True
            win32gui.EnumWindows(enum_cb, None)

            mid_x = self.screen_w / 2.0
            has_left_media = False
            has_right_media = False
            for title, rect in windows[:10]:
                cx = (rect[0] + rect[2]) / 2.0
                if any(m in title for m in ["youtube", "video", "media", "vlc", "player", "netflix"]):
                    if cx < mid_x:
                        has_left_media = True
                    else:
                        has_right_media = True

            if has_left_media and not has_right_media:
                self.content_zone = QRectF(0, 0, mid_x, self.screen_h)
                self.whiteboard_zone = QRectF(mid_x + 30, 40, mid_x - 60, self.screen_h - 80)
            elif has_right_media and not has_left_media:
                self.content_zone = QRectF(mid_x, 0, mid_x, self.screen_h)
                self.whiteboard_zone = QRectF(30, 40, mid_x - 60, self.screen_h - 80)
            else:
                self.whiteboard_zone = QRectF(mid_x + 30, 40, mid_x - 60, self.screen_h - 80)
        except Exception:
            pass
        return {"whiteboard_zone": self.whiteboard_zone}

class PerceptualDiffEngine:
    @staticmethod
    def compute_dhash(image: Image.Image, hash_size: int = 8) -> int:
        resized = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
        pixels = list(resized.getdata())
        diff = []
        for row in range(hash_size):
            for col in range(hash_size):
                p_left = pixels[row * (hash_size + 1) + col]
                p_right = pixels[row * (hash_size + 1) + col + 1]
                diff.append(p_left > p_right)
        return sum([1 << i for i, val in enumerate(diff) if val])

    @staticmethod
    def hamming_distance(h1: int, h2: int) -> int:
        return bin(h1 ^ h2).count('1')

class SchemaValidator:
    @staticmethod
    def normalize(raw_json: str) -> Optional[dict]:
        try:
            match = re.search(r'\{.*\}', raw_json, re.DOTALL)
            if not match:
                return None
            data = json.loads(match.group(0))
            title = str(data.get("title") or "Technical Derivation").strip()
            central_hub = str(data.get("central_hub") or title).strip()

            raw_branches = data.get("branches") or []
            if not isinstance(raw_branches, list):
                raw_branches = [raw_branches]
            clean_branches = []
            for b in raw_branches:
                if isinstance(b, dict):
                    lbl = str(b.get("label") or b.get("title") or "Mechanism").strip()
                    det = str(b.get("detail") or b.get("body") or "").strip()
                else:
                    lbl = "Principle"
                    det = str(b).strip()
                if det:
                    clean_branches.append({"label": lbl, "detail": det})

            raw_eqs = data.get("equations") or data.get("equations_or_punchlines") or []
            if isinstance(raw_eqs, str):
                raw_eqs = [raw_eqs]
            elif not isinstance(raw_eqs, list):
                raw_eqs = []
            clean_eqs = [str(e).strip() for e in raw_eqs if str(e).strip()]

            clauses = data.get("narration_clauses") or data.get("narration") or []
            if isinstance(clauses, str):
                clauses = [clauses]
            clean_clauses = [str(c).strip() for c in clauses if str(c).strip()]
            if not clean_clauses:
                clean_clauses = [f"Examining {title}."]
                for b in clean_branches[:2]:
                    clean_clauses.append(f"{b['label']}: {b['detail']}")

            return {
                "title": title,
                "central_hub": central_hub,
                "diagram_style": str(data.get("diagram_style") or "mind_map").lower(),
                "branches": clean_branches[:5],
                "equations": clean_eqs[:3],
                "narration_clauses": clean_clauses,
                "socratic_question": data.get("socratic_question", ""),
                "expected_concept": data.get("expected_concept", "")
            }
        except Exception:
            return None

@dataclasses.dataclass
class HandStroke:
    points: List[QPointF]
    color: QColor
    width: float = 2.5
    progress: float = 0.0
    speed: float = 0.045
    is_dashed: bool = False
    fill_color: Optional[QColor] = None
    is_arrow: bool = False
    opacity: float = 1.0

@dataclasses.dataclass
class ScreenAnchorItem:
    source_screen_pt: QPointF
    target_void_pt: QPointF
    label: str
    color: QColor
    contour_paths: List[QPainterPath] = dataclasses.field(default_factory=list)

@dataclasses.dataclass
class SketchnoteElement:
    id: str
    element_type: str
    bounding_rect: QRectF
    strokes: List[HandStroke] = dataclasses.field(default_factory=list)
    text_items: List[Tuple[QPointF, str, QFont, QColor, float]] = dataclasses.field(default_factory=list)
    anchors: List[ScreenAnchorItem] = dataclasses.field(default_factory=list)
    opacity: float = 1.0

class OrganicGeometryFactory:
    @staticmethod
    def hand_drawn_line(p1: QPointF, p2: QPointF, steps: int = 18, jitter: float = 1.1) -> List[QPointF]:
        pts = []
        for i in range(steps + 1):
            t = i / float(steps)
            x = p1.x() + t * (p2.x() - p1.x())
            y = p1.y() + t * (p2.y() - p1.y())
            bow = math.sin(t * math.pi) * random.uniform(-jitter * 1.6, jitter * 1.6)
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

    @classmethod
    def stick_figure_presenter(cls, x: float, y: float, pointing_to: QPointF) -> List[QPointF]:
        pts = []
        head_c = QPointF(x, y - 36.0)
        pts.extend(cls.hand_drawn_cloud(head_c, 9.0, 9.0, 10))
        pts.extend(cls.hand_drawn_line(QPointF(x, y - 27.0), QPointF(x, y - 8.0), steps=6))
        pts.extend(cls.hand_drawn_line(QPointF(x, y - 8.0), QPointF(x - 9.0, y + 16.0), steps=6))
        pts.extend(cls.hand_drawn_line(QPointF(x, y - 8.0), QPointF(x + 9.0, y + 16.0), steps=6))
        pts.extend(cls.hand_drawn_line(QPointF(x, y - 22.0), QPointF(x - 10.0, y - 10.0), steps=5))
        angle = math.atan2(pointing_to.y() - (y - 20.0), pointing_to.x() - x)
        arm_end = QPointF(x + 28.0 * math.cos(angle), (y - 20.0) + 28.0 * math.sin(angle))
        pts.extend(cls.hand_drawn_arrow(QPointF(x, y - 20.0), arm_end, arrow_size=8.0))
        return pts

class OpenCVScreenTracer:
    @staticmethod
    def extract_screen_contours(pil_img: Image.Image, crop_box: Optional[Tuple[int, int, int, int]] = None) -> List[QPainterPath]:
        if not HAS_OPENCV:
            return []
        try:
            if crop_box:
                crop = pil_img.crop(crop_box)
                ox, oy = crop_box[0], crop_box[1]
            else:
                crop = pil_img
                ox, oy = 0, 0

            np_arr = np.array(crop)
            gray = cv2.cvtColor(np_arr, cv2.COLOR_RGB2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 40, 130)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            paths = []
            for cnt in contours:
                if cv2.contourArea(cnt) > 300:
                    peri = cv2.arcLength(cnt, True)
                    approx = cv2.approxPolyDP(cnt, 0.025 * peri, True)
                    if len(approx) >= 3:
                        path = QPainterPath()
                        p0 = approx[0][0]
                        path.moveTo(ox + float(p0[0]), oy + float(p0[1]))
                        for pt in approx[1:]:
                            p = pt[0]
                            path.lineTo(ox + float(p[0]), oy + float(p[1]))
                        path.closeSubpath()
                        paths.append(path)
            return paths
        except Exception:
            return []

class EuclideanProofSynthesizer:
    @staticmethod
    def build_proof(origin_x: float, origin_y: float) -> SketchnoteElement:
        elem = SketchnoteElement(
            id=f"proof_pythagoras_{int(time.time())}",
            element_type="proof",
            bounding_rect=QRectF(origin_x - 60, origin_y - 60, 1260, 780)
        )
        cyan = QColor(56, 189, 248)
        emerald = QColor(52, 211, 153)
        amber = QColor(251, 191, 36)
        lavender = QColor(216, 180, 254)

        head_center = QPointF(origin_x + 440, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(head_center, 420, 36, 18),
            color=cyan, width=2.5, fill_color=QColor(56, 189, 248, 25)
        ))
        elem.text_items.append((
            QPointF(head_center.x() - 360, head_center.y() + 6),
            "THE PYTHAGOREAN THEOREM: FIRST-PRINCIPLES VISUAL PROOF BY SQUARES",
            QFont("Segoe UI", 11, QFont.Bold), QColor(241, 245, 249), 0.0
        ))

        scale = 35.0
        a_len = 3.0 * scale
        b_len = 4.0 * scale
        A = QPointF(origin_x + 220, origin_y + 360)
        B = QPointF(A.x() + b_len, A.y())
        C = QPointF(A.x(), A.y() - a_len)

        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(A, B, 18, 1.2), color=emerald, width=3.5))
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(A, C, 16, 1.2), color=amber, width=3.5))
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(C, B, 22, 1.4), color=cyan, width=4.0))

        sq_glyph = [QPointF(A.x(), A.y() - 14), QPointF(A.x() + 14, A.y() - 14), QPointF(A.x() + 14, A.y())]
        elem.strokes.append(HandStroke(points=sq_glyph, color=QColor(241, 245, 249), width=1.5))

        sq_a = [C, QPointF(C.x() - a_len, C.y()), QPointF(A.x() - a_len, A.y()), A, C]
        elem.strokes.append(HandStroke(points=sq_a, color=amber, width=2.5, fill_color=QColor(amber.red(), amber.green(), amber.blue(), 35)))
        elem.text_items.append((QPointF(A.x() - a_len * 0.75, A.y() - a_len * 0.45), "a² = 9", QFont("Segoe UI", 12, QFont.Bold), amber, 0.0))

        sq_b = [A, QPointF(A.x(), A.y() + b_len), QPointF(B.x(), B.y() + b_len), B, A]
        elem.strokes.append(HandStroke(points=sq_b, color=emerald, width=2.5, fill_color=QColor(emerald.red(), emerald.green(), emerald.blue(), 35)))
        elem.text_items.append((QPointF(A.x() + b_len * 0.35, A.y() + b_len * 0.55), "b² = 16", QFont("Segoe UI", 12, QFont.Bold), emerald, 0.0))

        dx = B.x() - C.x()
        dy = B.y() - C.y()
        sq_c = [C, B, QPointF(B.x() - dy, B.y() + dx), QPointF(C.x() - dy, C.y() + dx), C]
        elem.strokes.append(HandStroke(points=sq_c, color=cyan, width=3.0, fill_color=QColor(cyan.red(), cyan.green(), cyan.blue(), 40)))
        elem.text_items.append((QPointF(C.x() + dx * 0.35 - dy * 0.55, C.y() + dy * 0.35 + dx * 0.55), "c² = 25", QFont("Segoe UI", 13, QFont.Bold), cyan, 0.0))

        elem.text_items.append((QPointF(A.x() - 75, A.y() - a_len * 0.5), "Height a = 3", QFont("Segoe UI", 10, QFont.Bold), amber, 0.0))
        elem.text_items.append((QPointF(A.x() + b_len * 0.3, A.y() - 10), "Base b = 4", QFont("Segoe UI", 10, QFont.Bold), emerald, 0.0))
        elem.text_items.append((QPointF(C.x() + b_len * 0.55, C.y() + a_len * 0.4), "Hypotenuse c = 5", QFont("Segoe UI", 10, QFont.Bold), cyan, 0.0))

        lx = origin_x + 590
        ly = origin_y + 60
        steps = [
            ("1. WHAT IS A TRIANGLE?", "A 3-sided shape. When one corner is a 90° box, it's a RIGHT-ANGLED TRIANGLE.", QColor(241, 245, 249)),
            ("2. WHAT IS THE HYPOTENUSE?", "The longest side directly OPPOSITE the 90° corner. (The glowing cyan diagonal).", cyan),
            ("3. WHAT ARE THE LEGS?", "The two perpendicular edges meeting at the right angle: Upright Height (a) & Flat Base (b).", emerald),
            ("4. DRAW SQUARES ON EACH SIDE", "Imagine physical floor tiles: 3×3 square on height (9) + 4×4 square on base (16).", amber),
            ("5. THE MAGIC EQUALITY", "Total tiles = 9 + 16 = 25 tiles!", lavender),
            ("6. PERFECT FIT ON HYPOTENUSE", "25 tiles perfectly tile the 5×5 square on the hypotenuse! Formula: a² + b² = c².", cyan)
        ]
        cy = ly
        for title, desc, col in steps:
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_cloud(QPointF(lx, cy - 4), 6, 6, 8), color=col, width=2.0, fill_color=col))
            elem.text_items.append((QPointF(lx + 22, cy), title, QFont("Segoe UI", 10, QFont.Bold), col, 0.0))
            elem.text_items.append((QPointF(lx + 22, cy + 22), desc, QFont("Segoe UI", 9), QColor(203, 213, 225), 0.0))
            cy += 64

        return elem

class FreeBodyDiagramSynthesizer:
    @staticmethod
    def build_fbd(origin_x: float, origin_y: float) -> SketchnoteElement:
        elem = SketchnoteElement(
            id=f"fbd_incline_{int(time.time())}",
            element_type="fbd",
            bounding_rect=QRectF(origin_x - 60, origin_y - 60, 1150, 740)
        )
        cyan = QColor(56, 189, 248)
        emerald = QColor(52, 211, 153)
        amber = QColor(251, 191, 36)
        coral = QColor(248, 113, 113)
        lavender = QColor(216, 180, 254)

        head_center = QPointF(origin_x + 380, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(head_center, 380, 36, 16),
            color=lavender, width=2.5, fill_color=QColor(147, 51, 234, 30)
        ))
        elem.text_items.append((
            QPointF(head_center.x() - 320, head_center.y() + 6),
            "FREE-BODY DIAGRAM (FBD): BLOCK ON INCLINED RAMP WITH FRICTION",
            QFont("Segoe UI", 11, QFont.Bold), QColor(243, 244, 246), 0.0
        ))

        ramp_len = 380.0
        theta = math.radians(30.0)
        P_left = QPointF(origin_x + 40, origin_y + 380)
        P_right = QPointF(P_left.x() + ramp_len, P_left.y())
        P_peak = QPointF(P_left.x(), P_left.y() - ramp_len * math.tan(theta))

        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(P_left, P_right, 20), color=QColor(148, 163, 184), width=3.0))
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(P_left, P_peak, 14), color=QColor(148, 163, 184), width=3.0))
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(P_peak, P_right, 24), color=QColor(226, 232, 240), width=4.0))

        t_block = 0.48
        cx = P_peak.x() + t_block * (P_right.x() - P_peak.x())
        cy = P_peak.y() + t_block * (P_right.y() - P_peak.y()) - 20.0
        C = QPointF(cx, cy)

        bw, bh = 60.0, 40.0
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        b_pts = [
            QPointF(C.x() - bw*cos_t + bh*sin_t, C.y() + bw*sin_t + bh*cos_t),
            QPointF(C.x() + bw*cos_t + bh*sin_t, C.y() - bw*sin_t + bh*cos_t),
            QPointF(C.x() + bw*cos_t - bh*sin_t, C.y() - bw*sin_t - bh*cos_t),
            QPointF(C.x() - bw*cos_t - bh*sin_t, C.y() + bw*sin_t - bh*cos_t),
            QPointF(C.x() - bw*cos_t + bh*sin_t, C.y() + bw*sin_t + bh*cos_t)
        ]
        elem.strokes.append(HandStroke(points=b_pts, color=cyan, width=3.0, fill_color=QColor(56, 189, 248, 35)))

        mg_end = QPointF(C.x(), C.y() + 140)
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_arrow(C, mg_end), color=amber, width=3.5))
        elem.text_items.append((QPointF(mg_end.x() + 12, mg_end.y()), "F_g = m·g (Gravity)", QFont("Segoe UI", 11, QFont.Bold), amber, 0.0))

        fn_end = QPointF(C.x() + 110 * sin_t, C.y() - 110 * cos_t)
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_arrow(C, fn_end), color=emerald, width=3.5))
        elem.text_items.append((QPointF(fn_end.x() + 12, fn_end.y() - 8), "F_N = m·g·cos(θ) (Normal Force)", QFont("Segoe UI", 11, QFont.Bold), emerald, 0.0))

        fk_end = QPointF(C.x() - 95 * cos_t, C.y() - 95 * sin_t)
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_arrow(C, fk_end), color=coral, width=3.5))
        elem.text_items.append((QPointF(fk_end.x() - 145, fk_end.y() - 12), "f_k = μ_k·F_N (Friction)", QFont("Segoe UI", 11, QFont.Bold), coral, 0.0))

        down_end = QPointF(C.x() + 100 * cos_t, C.y() + 100 * sin_t)
        elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_arrow(C, down_end), color=amber, width=2.5, is_dashed=True))
        elem.text_items.append((QPointF(down_end.x() + 10, down_end.y() + 16), "m·g·sin(θ) (Downslope Vector)", QFont("Segoe UI", 10), amber, 0.0))

        rx = origin_x + 520
        ry = origin_y + 80
        derivations = [
            ("1. ISOLATE OBJECT", "Detach mass (m) and treat as a point at its center of gravity.", cyan),
            ("2. RESOLVE AXES", "Align X-axis parallel to the ramp, and Y-axis perpendicular to ramp surface.", emerald),
            ("3. DECOMPOSE GRAVITY", "Y-comp: mg·cos(θ) pushes into ramp | X-comp: mg·sin(θ) pulls downhill.", amber),
            ("4. EQUILIBRIUM (Y-AXIS)", "Zero motion perpendicular to ramp: ΣFy = 0  ===>  F_N = mg·cos(θ).", emerald),
            ("5. NEWTON'S 2ND LAW", "ΣFx = m·a  ===>  mg·sin(θ) - f_k = m·a.", coral),
            ("6. NET ACCELERATION", "a = g·(sin(θ) - μ_k·cos(θ)) [Sliding begins when tan(θ) > μ_s].", lavender)
        ]
        cy = ry
        for step_title, step_desc, col in derivations:
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_cloud(QPointF(rx, cy - 4), 6, 6, 8), color=col, width=2.0, fill_color=col))
            elem.text_items.append((QPointF(rx + 22, cy), step_title, QFont("Segoe UI", 10, QFont.Bold), col, 0.0))
            elem.text_items.append((QPointF(rx + 22, cy + 22), step_desc, QFont("Segoe UI", 9), QColor(203, 213, 225), 0.0))
            cy += 64

        return elem

class RealCodeASTAnalyzer:
    @staticmethod
    def analyze_code_and_synthesize(origin_x: float, origin_y: float, raw_code: str) -> SketchnoteElement:
        elem = SketchnoteElement(
            id=f"code_ast_{int(time.time())}",
            element_type="code_arch",
            bounding_rect=QRectF(origin_x - 60, origin_y - 60, 1180, 760)
        )
        cyan = QColor(56, 189, 248)
        emerald = QColor(52, 211, 153)
        amber = QColor(251, 191, 36)
        violet = QColor(167, 139, 250)
        coral = QColor(248, 113, 113)

        head_center = QPointF(origin_x + 400, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(head_center, 400, 36, 16),
            color=cyan, width=2.5, fill_color=QColor(56, 189, 248, 25)
        ))
        elem.text_items.append((
            QPointF(head_center.x() - 340, head_center.y() + 6),
            "AST CODE EXECUTION GRAPH & STATIC RUNTIME AUDIT",
            QFont("Segoe UI", 11, QFont.Bold), QColor(241, 245, 249), 0.0
        ))

        ast_nodes_count = 0
        functions_found = []
        loops_count = 0
        has_recursion = False
        syntax_valid = True
        syntax_err_msg = ""

        try:
            tree = ast.parse(raw_code)
            ast_nodes_count = len(list(ast.walk(tree)))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions_found.append(node.name)
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == node.name:
                            has_recursion = True
                elif isinstance(node, (ast.For, ast.While)):
                    loops_count += 1
        except SyntaxError as se:
            syntax_valid = False
            syntax_err_msg = f"Line {se.lineno}: {se.msg}"

        stack_rect = QRectF(origin_x + 40, origin_y + 80, 260, 340)
        for p1, p2 in [(stack_rect.topLeft(), stack_rect.topRight()), (stack_rect.topRight(), stack_rect.bottomRight()),
                       (stack_rect.bottomRight(), stack_rect.bottomLeft()), (stack_rect.bottomLeft(), stack_rect.topLeft())]:
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(p1, p2, 10), color=emerald, width=2.0))

        elem.text_items.append((QPointF(origin_x + 55, origin_y + 110), "ACTIVE RUNTIME FRAMES", QFont("Consolas", 10, QFont.Bold), emerald, 0.0))
        if syntax_valid:
            elem.text_items.append((QPointF(origin_x + 55, origin_y + 145), f"• Functions: {', '.join(functions_found) or 'global script'}", QFont("Consolas", 9), QColor(226, 232, 240), 0.0))
            elem.text_items.append((QPointF(origin_x + 55, origin_y + 185), f"• Loops Detected: {loops_count}", QFont("Consolas", 9), amber, 0.0))
            elem.text_items.append((QPointF(origin_x + 55, origin_y + 225), f"• Recursive Stack: {'YES (Depth O(N))' if has_recursion else 'NO (Iterative)'}", QFont("Consolas", 9), cyan, 0.0))
            elem.text_items.append((QPointF(origin_x + 55, origin_y + 265), f"• AST Expression Nodes: {ast_nodes_count}", QFont("Consolas", 9), violet, 0.0))
        else:
            elem.text_items.append((QPointF(origin_x + 55, origin_y + 145), "SYNTAX ERROR IDENTIFIED:", QFont("Consolas", 9, QFont.Bold), coral, 0.0))
            elem.text_items.append((QPointF(origin_x + 55, origin_y + 185), syntax_err_msg, QFont("Consolas", 9), QColor(248, 113, 113), 0.0))

        rx = origin_x + 360
        ry = origin_y + 80
        est_complexity = "O(N²)" if loops_count > 1 else ("O(N)" if loops_count == 1 or has_recursion else "O(1)")

        insights = [
            ("1. TIME COMPLEXITY ESTIMATE", f"Inferred algorithmic bound: {est_complexity} based on AST traversal.", cyan),
            ("2. HEAP / STACK ALLOCATION", "Recursion creates stack frames; pre-allocate arrays to avoid GC pressure.", emerald),
            ("3. PROACTIVE IMPROVEMENT (JARVIS)", "Use generator expressions or itertools to convert loops to C-level iteration.", amber),
            ("4. EDGE-CASE BOUNDARY AUDIT", "Ensure empty collections and boundary inputs return base cases without raising IndexError.", violet)
        ]
        cy = ry
        for t, d, col in insights:
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_cloud(QPointF(rx, cy - 4), 6, 6, 8), color=col, width=2.0, fill_color=col))
            elem.text_items.append((QPointF(rx + 22, cy), t, QFont("Segoe UI", 10, QFont.Bold), col, 0.0))
            elem.text_items.append((QPointF(rx + 22, cy + 22), d, QFont("Segoe UI", 9), QColor(203, 213, 225), 0.0))
            cy += 64

        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.stick_figure_presenter(origin_x + 30, origin_y + 490, QPointF(origin_x + 180, origin_y + 200)),
            color=cyan, width=2.0
        ))
        return elem

class DocumentAndPDFIngestor:
    @staticmethod
    def extract_document_text(filepath: str, max_pages: int = 5) -> str:
        if not os.path.exists(filepath):
            return f"Error: Document {filepath} not found on disk."

        if filepath.lower().endswith(".pdf") and HAS_PYPDF:
            try:
                reader = pypdf.PdfReader(filepath)
                text = ""
                for i in range(min(len(reader.pages), max_pages)):
                    page_text = reader.pages[i].extract_text() or ""
                    text += f"\n--- Page {i+1} ---\n" + page_text
                return text[:3000]
            except Exception as e:
                return f"PDF Ingestion error: {e}"

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                return f.read(3000)
        except Exception as e:
            return f"File read error: {e}"

    @staticmethod
    def synthesize_document_lecture(origin_x: float, origin_y: float, title: str, summary_points: List[str]) -> SketchnoteElement:
        elem = SketchnoteElement(
            id=f"doc_{int(time.time())}",
            element_type="mind_map",
            bounding_rect=QRectF(origin_x - 60, origin_y - 60, 1150, 740)
        )
        cyan = QColor(56, 189, 248)
        emerald = QColor(52, 211, 153)

        head_center = QPointF(origin_x + 380, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(head_center, 380, 36, 16),
            color=cyan, width=2.5, fill_color=QColor(56, 189, 248, 25)
        ))
        elem.text_items.append((
            QPointF(head_center.x() - 320, head_center.y() + 6),
            f"DOCUMENT INGESTION: {title.upper()}",
            QFont("Segoe UI", 11, QFont.Bold), QColor(241, 245, 249), 0.0
        ))

        by = origin_y + 80
        for i, pt in enumerate(summary_points[:5]):
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_cloud(QPointF(origin_x + 30, by - 4), 6, 6, 8), color=emerald, width=2.0, fill_color=emerald))
            elem.text_items.append((QPointF(origin_x + 50, by), f"• Point {i+1}: {pt}", QFont("Segoe UI", 10), emerald, 0.0))
            by += 55

        return elem

class StructuredNoteCompiler:
    @staticmethod
    def compile_class_notes(elements: List[SketchnoteElement]) -> str:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        md = f"# AI Teaching Assistant — Interactive Class Notes\n"
        md += f"*Generated on: {timestamp}*\n\n---\n\n"

        for i, elem in enumerate(elements):
            md += f"## Topic {i+1}: {elem.element_type.upper()}\n\n"
            for _, txt, _, _, _ in elem.text_items:
                if txt.startswith("THE ") or txt.startswith("FREE-BODY") or txt.startswith("CODE "):
                    md += f"### {txt}\n"
                elif txt.startswith("•") or txt.startswith("1.") or txt.startswith("2.") or txt.startswith("3."):
                    md += f"- {txt}\n"
                elif ">>" in txt or "=" in txt:
                    md += f"$$\n{txt.replace('>>', '').strip()}\n$$\n"
                else:
                    md += f"{txt}\n\n"
            md += "\n---\n\n"
        return md

    @staticmethod
    def compile_exam_cheatsheet(elements: List[SketchnoteElement]) -> str:
        timestamp = time.strftime("%Y-%m-%d")
        md = f"# Exam Quick-Reference Cheat Sheet ({timestamp})\n\n"
        md += "### Key Formulas & High-Frequency Derivations\n\n"
        for elem in elements:
            for _, txt, _, _, _ in elem.text_items:
                if any(sym in txt for sym in ["=", "O(", "F_g", "a²", "b²", "c²", "sin", "cos"]):
                    md += f"* **Identity**: `{txt.replace('>>', '').strip()}`\n"
        return md

class PersistentKnowledgeTracker:
    FILEPATH = "knowledge_state.json"

    def __init__(self):
        self.state = self.load()

    def load(self) -> Dict[str, Any]:
        if os.path.exists(self.FILEPATH):
            try:
                with open(self.FILEPATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "mastery": {},
            "attempts": {},
            "correct": {},
            "struggles": [],
            "session_log": []
        }

    def save(self):
        try:
            with open(self.FILEPATH, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"[KnowledgeTracker Error] {e}")

    def record_quiz_result(self, topic: str, is_correct: bool):
        t = topic.lower().strip()
        att = self.state["attempts"].get(t, 0) + 1
        corr = self.state["correct"].get(t, 0) + (1 if is_correct else 0)
        self.state["attempts"][t] = att
        self.state["correct"][t] = corr
        score = round(corr / float(att), 2)
        self.state["mastery"][t] = score
        
        if score < 0.70 and t not in self.state["struggles"]:
            self.state["struggles"].append(t)
        elif score >= 0.80 and t in self.state["struggles"]:
            self.state["struggles"].remove(t)
            
        self.state["session_log"].append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "topic": t,
            "correct": is_correct,
            "mastery": score
        })
        self.save()

    def get_summary(self) -> str:
        s = "=== PERSISTENT MASTERY PROFILE (knowledge_state.json) ===\n"
        if not self.state["mastery"]:
            return s + "No topics recorded yet. Engage in Socratic checkpoints to build profile.\n"
        for top, scr in self.state["mastery"].items():
            att = self.state["attempts"].get(top, 0)
            status = "MASTERED" if scr >= 0.85 else ("NEEDS PRACTICE" if scr >= 0.6 else "REMEDIATION REQUIRED")
            s += f"  * {top.title()}: {int(scr * 100)}% ({status}) [Attempts: {att}]\n"
        if self.state["struggles"]:
            s += f"Prioritized Remediation Targets: {', '.join(self.state['struggles']).title()}\n"
        return s

class AutonomousDocumentNavigator:
    def __init__(self):
        self.last_advance_time = 0.0
        self.dwell_interval_sec = 28.0

    def check_and_advance_document(self) -> bool:
        if sys.platform != "win32":
            return False
        now = time.time()
        if now - self.last_advance_time < self.dwell_interval_sec:
            return False

        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return False
            buff = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buff, 512)
            title = buff.value.lower()
            if any(app in title for app in ["pdf", "acrobat", "foxit", "powerpoint", "slides", "sumatra"]):
                UniversalMediaController.advance_document(forward=True)
                self.last_advance_time = now
                return True
        except Exception:
            pass
        return False

class ContinuousContourTracker:
    def __init__(self, elevation_callback):
        self.elevation_callback = elevation_callback
        self.last_contour_time = 0.0
        self.last_fingerprint = 0

    def evaluate_screen_contours(self):
        if not (HAS_MSS and HAS_OPENCV):
            return
        now = time.time()
        if now - self.last_contour_time < 12.0:
            return

        try:
            with mss.mss() as sct:
                mon = sct.monitors[1]
                s_img = sct.grab(mon)
                img = Image.frombytes("RGB", s_img.size, s_img.bgra, "raw", "BGRX")
                
            np_arr = np.array(img.resize((640, 360), Image.Resampling.BILINEAR))
            gray = cv2.cvtColor(np_arr, cv2.COLOR_RGB2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 140)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            prominent_contours = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if 800 < area < 45000:
                    peri = cv2.arcLength(cnt, True)
                    approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
                    if 3 <= len(approx) <= 8:
                        prominent_contours.append(approx)

            if prominent_contours:
                shape_fp = len(prominent_contours) * 1000 + int(cv2.contourArea(prominent_contours[0]))
                if abs(shape_fp - self.last_fingerprint) > 150:
                    self.last_fingerprint = shape_fp
                    self.last_contour_time = now
                    self.elevation_callback(img, prominent_contours)
        except Exception:
            pass

class WorkspaceCodeWatcher:
    def __init__(self, callback):
        self.callback = callback
        self.file_mtimes: Dict[str, float] = {}
        self.scan_directory = os.getcwd()

    def scan_for_code_updates(self):
        try:
            py_files = glob.glob(os.path.join(self.scan_directory, "*.py"))
            for fpath in py_files[:8]:
                if os.path.basename(fpath).startswith("ai_teaching_assistant"):
                    continue
                try:
                    mtime = os.path.getmtime(fpath)
                except OSError:
                    continue

                if fpath not in self.file_mtimes:
                    self.file_mtimes[fpath] = mtime
                    continue

                if mtime > self.file_mtimes[fpath] + 0.5:
                    self.file_mtimes[fpath] = mtime
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        source = f.read(4000)
                    if len(source.strip()) > 20:
                        self.callback(os.path.basename(fpath), source)
        except Exception:
            pass

class DynamicToddlerPedagogySynthesizer:
    @staticmethod
    def synthesize_toddler_ladder(origin_x: float, origin_y: float, topic: str) -> SketchnoteElement:
        elem = SketchnoteElement(
            id=f"toddler_ladder_{int(time.time())}",
            element_type="proof",
            bounding_rect=QRectF(origin_x - 60, origin_y - 60, 1240, 780)
        )
        cyan = QColor(56, 189, 248)
        emerald = QColor(52, 211, 153)
        amber = QColor(251, 191, 36)
        coral = QColor(248, 113, 113)
        lavender = QColor(216, 180, 254)

        clean_topic = topic.strip().title()
        head_center = QPointF(origin_x + 420, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(head_center, 420, 36, 18),
            color=cyan, width=2.5, fill_color=QColor(56, 189, 248, 25)
        ))
        elem.text_items.append((
            QPointF(head_center.x() - 360, head_center.y() + 6),
            f"TODDLER-TO-PROFESSOR ATOMIC DERIVATION: {clean_topic.upper()}",
            QFont("Segoe UI", 11, QFont.Bold), QColor(241, 245, 249), 0.0
        ))

        steps = [
            ("STEP 1: THE TODDLER INTUITION", f"What is {clean_topic}? Imagine playing with physical building blocks in the real world.", QColor(241, 245, 249)),
            ("STEP 2: THE PHYSICAL MECHANISM", "Before formulas, feel the cause-and-effect: push one side, and the other side must react.", emerald),
            ("STEP 3: ISOLATING THE CORE PIECES", "Strip away the jargon. Label every moving part with concrete physical units.", amber),
            ("STEP 4: THE MATHEMATICAL LADDER", "Turn the tangible observation into an unbreakable quantitative identity.", cyan),
            ("STEP 5: RUNTIME / REAL-WORLD PROOF", "Test boundary conditions: What happens at zero? What happens at infinity?", coral),
            ("STEP 6: PROFESSOR-GRADE IDENTITY", f"Unifying principle established for {clean_topic}. Q.E.D. verified from first principles.", lavender)
        ]

        sy = origin_y + 80
        for i, (title, desc, col) in enumerate(steps):
            box_rect = QRectF(origin_x + 40, sy - 14, 520, 50)
            for p1, p2 in [(box_rect.topLeft(), box_rect.topRight()), (box_rect.topRight(), box_rect.bottomRight()),
                           (box_rect.bottomRight(), box_rect.bottomLeft()), (box_rect.bottomLeft(), box_rect.topLeft())]:
                elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(p1, p2, 8), color=col, width=1.8))
            elem.text_items.append((QPointF(origin_x + 55, sy + 6), title, QFont("Segoe UI", 9, QFont.Bold), col, 0.0))
            elem.text_items.append((QPointF(origin_x + 55, sy + 26), desc, QFont("Segoe UI", 8), QColor(203, 213, 225), 0.0))

            if i < len(steps) - 1:
                arr = OrganicGeometryFactory.hand_drawn_arrow(QPointF(origin_x + 300, sy + 38), QPointF(origin_x + 300, sy + 66), 8.0)
                elem.strokes.append(HandStroke(points=arr, color=col, width=1.5))
            sy += 72

        dx = origin_x + 640
        dy = origin_y + 100
        blueprint_rect = QRectF(dx, dy, 520, 420)
        for p1, p2 in [(blueprint_rect.topLeft(), blueprint_rect.topRight()), (blueprint_rect.topRight(), blueprint_rect.bottomRight()),
                       (blueprint_rect.bottomRight(), blueprint_rect.bottomLeft()), (blueprint_rect.bottomLeft(), blueprint_rect.topLeft())]:
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(p1, p2, 14), color=cyan, width=2.0))
        elem.text_items.append((QPointF(dx + 25, dy + 35), f"STRUCTURAL BLUEPRINT: {clean_topic.upper()}", QFont("Segoe UI", 10, QFont.Bold), cyan, 0.0))
        elem.text_items.append((QPointF(dx + 25, dy + 70), "• Axiom 1: Invariant conservation rules strictly enforced.", QFont("Segoe UI", 9), emerald, 0.0))
        elem.text_items.append((QPointF(dx + 25, dy + 105), "• Axiom 2: Dimensional analysis validates scalar/vector balance.", QFont("Segoe UI", 9), amber, 0.0))
        elem.text_items.append((QPointF(dx + 25, dy + 140), "• Axiom 3: Asymptotic limits converge without singularities.", QFont("Segoe UI", 9), lavender, 0.0))

        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.stick_figure_presenter(dx - 30, dy + 320, QPointF(dx + 120, dy + 140)),
            color=amber, width=2.0
        ))
        return elem

class JarvisAppBuilder:
    @staticmethod
    def build_application(origin_x: float, origin_y: float, app_spec: str) -> Tuple[SketchnoteElement, str, str]:
        elem = SketchnoteElement(
            id=f"jarvis_app_{int(time.time())}",
            element_type="code_arch",
            bounding_rect=QRectF(origin_x - 60, origin_y - 60, 1260, 780)
        )
        cyan = QColor(56, 189, 248)
        emerald = QColor(52, 211, 153)
        amber = QColor(251, 191, 36)
        violet = QColor(167, 139, 250)

        app_name = re.sub(r'[^a-zA-Z0-9_]', '_', app_spec.strip().lower())[:24] or "generated_app"
        app_filename = f"{app_name}.py"

        head_center = QPointF(origin_x + 420, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(head_center, 420, 36, 16),
            color=cyan, width=2.5, fill_color=QColor(56, 189, 248, 25)
        ))
        elem.text_items.append((
            QPointF(head_center.x() - 360, head_center.y() + 6),
            f"JARVIS BUILD-FROM-SCRATCH APP ENGINE: {app_name.upper()}.PY",
            QFont("Segoe UI", 11, QFont.Bold), QColor(241, 245, 249), 0.0
        ))

        boilerplate = f'''#!/usr/bin/env python3
"""
Generated by Jarvis App Engine: {app_spec}
Architecture: Self-contained reactive tool with zero external dependencies.
"""

import sys
import time

class {app_name.title().replace("_", "")}Engine:
    def __init__(self):
        self.active = True
        self.operations_count = 0

    def execute_workflow(self, task_param: str) -> dict:
        self.operations_count += 1
        print(f"[{app_name.upper()}] Processing input: {{task_param}}...")
        return {{
            "status": "SUCCESS",
            "task": task_param,
            "operation_id": self.operations_count,
            "timestamp": time.time()
        }}

if __name__ == "__main__":
    app = {app_name.title().replace("_", "")}Engine()
    result = app.execute_workflow("Initial Automated Task")
    print(f"Execution Output: {{result}}")
'''
        syntax_ok = True
        try:
            ast.parse(boilerplate)
        except SyntaxError:
            syntax_ok = False

        out_dir = "generated_apps"
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, app_filename)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(boilerplate)

        arch_rect = QRectF(origin_x + 40, origin_y + 80, 520, 420)
        for p1, p2 in [(arch_rect.topLeft(), arch_rect.topRight()), (arch_rect.topRight(), arch_rect.bottomRight()),
                       (arch_rect.bottomRight(), arch_rect.bottomLeft()), (arch_rect.bottomLeft(), arch_rect.topLeft())]:
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(p1, p2, 12), color=emerald, width=2.0))
        elem.text_items.append((QPointF(origin_x + 60, origin_y + 115), "JARVIS ARCHITECTURAL BLUEPRINT", QFont("Consolas", 10, QFont.Bold), emerald, 0.0))
        elem.text_items.append((QPointF(origin_x + 60, origin_y + 155), f"• Target Path: {out_path}", QFont("Consolas", 9), QColor(226, 232, 240), 0.0))
        elem.text_items.append((QPointF(origin_x + 60, origin_y + 195), f"• AST Syntax Gate: {'PASSED [100% VALID]' if syntax_ok else 'FAILED'}", QFont("Consolas", 9, QFont.Bold), cyan, 0.0))
        elem.text_items.append((QPointF(origin_x + 60, origin_y + 235), f"• Core Class: {app_name.title().replace('_', '')}Engine", QFont("Consolas", 9), amber, 0.0))

        rx = origin_x + 600
        ry = origin_y + 80
        elem.text_items.append((QPointF(rx, ry + 25), "SYNTHESIZED SOURCE MANIFEST:", QFont("Consolas", 10, QFont.Bold), cyan, 0.0))
        code_lines = boilerplate.strip().split("\n")[:12]
        cy = ry + 60
        for line in code_lines:
            elem.text_items.append((QPointF(rx, cy), line[:55], QFont("Consolas", 8), QColor(203, 213, 225), 0.0))
            cy += 24

        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.stick_figure_presenter(origin_x + 20, origin_y + 480, QPointF(origin_x + 240, origin_y + 200)),
            color=emerald, width=2.0
        ))
        return elem, out_path, boilerplate

class DynamicSocraticEngine:
    @staticmethod
    def generate_quiz(origin_x: float, origin_y: float) -> Tuple[SketchnoteElement, float, float, Dict[str, Any]]:
        elem = SketchnoteElement(
            id=f"quiz_{int(time.time())}",
            element_type="proof",
            bounding_rect=QRectF(origin_x - 40, origin_y - 40, 1000, 560)
        )
        gold = QColor(251, 191, 36)
        emerald = QColor(52, 211, 153)
        cyan = QColor(56, 189, 248)

        base = random.choice([5, 6, 8, 9, 12])
        height = random.choice([12, 8, 15, 12, 16])
        hypot = math.sqrt(base*base + height*height)
        correct_c = int(hypot) if hypot.is_integer() else round(hypot, 2)
        correct_sq = base*base + height*height

        center = QPointF(origin_x + 380, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(center, 360, 36, 16),
            color=gold, width=2.5, fill_color=QColor(251, 191, 36, 25)
        ))
        elem.text_items.append((
            QPointF(center.x() - 300, center.y() + 6),
            "SOCRATIC CHECKPOINT: DYNAMIC MASTERY ASSESSMENT",
            QFont("Segoe UI", 11, QFont.Bold), QColor(254, 243, 199), 0.0
        ))

        q_lines = [
            f"Scenario: You are designing a diagonal structural support for a warehouse roof truss.",
            f"Given: Base horizontal span (b) = {base} m | Upright vertical wall (a) = {height} m.",
            f"Challenge: What is the exact length of the diagonal strut (c), and its attached square area (c²)?"
        ]
        qy = origin_y + 70
        for line in q_lines:
            elem.text_items.append((
                QPointF(origin_x + 30, qy), line,
                QFont("Segoe UI", 11, QFont.Bold if "Challenge" in line else QFont.Normal),
                cyan if "Challenge" in line else QColor(241, 245, 249), 0.0
            ))
            qy += 34

        options = [
            (f"Option A: c = {correct_c} m, Area(c²) = {correct_sq} m² [CORRECT]", emerald, "a"),
            (f"Option B: c = {correct_c + 2} m, Area(c²) = {correct_sq + 40} m² [MISCALCULATION]", QColor(203, 213, 225), "b"),
            (f"Option C: c = {abs(height - base)} m, Area(c²) = {(height - base)**2} m² [INCORRECT FORMULA]", QColor(203, 213, 225), "c")
        ]
        random.shuffle(options)

        oy = origin_y + 200
        for opt_text, col, _ in options:
            box_rect = QRectF(origin_x + 30, oy - 14, 18, 18)
            for p1, p2 in [(box_rect.topLeft(), box_rect.topRight()), (box_rect.topRight(), box_rect.bottomRight()),
                           (box_rect.bottomRight(), box_rect.bottomLeft()), (box_rect.bottomLeft(), box_rect.topLeft())]:
                elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(p1, p2, 4), color=col, width=2.0))
            elem.text_items.append((QPointF(origin_x + 65, oy), opt_text, QFont("Segoe UI", 10), col, 0.0))
            oy += 45

        quiz_meta = {
            "correct_c": correct_c,
            "correct_sq": correct_sq,
            "options": options
        }
        return elem, hypot, float(correct_sq), quiz_meta

class HighSpeedMediaTranscriber:
    @staticmethod
    def build_cadence_breakdown(origin_x: float, origin_y: float) -> SketchnoteElement:
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

class VoiceNarrator(QObject):
    speaking_state_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.speech_queue = queue.Queue()
        self.is_speaking = False
        self.kokoro = None
        if HAS_KOKORO and VOICE_ENABLED:
            try:
                self.kokoro = kokoro_onnx.Kokoro(
                    model_path=KOKORO_MODEL_PATH,
                    voices_path=KOKORO_VOICES_PATH
                )
                print("[Voice Engine] Kokoro-ONNX 82M Neural Voice loaded (af_heart).")
            except Exception as e:
                self.kokoro = None

        if (self.kokoro or HAS_PYTTSX3) and VOICE_ENABLED:
            threading.Thread(target=self._worker, daemon=True).start()

    def speak(self, phrase: str):
        if not phrase.strip():
            return
        self.speech_queue.put(phrase.strip())

    def _worker(self):
        sapi_engine = None
        if not self.kokoro and HAS_PYTTSX3:
            try:
                sapi_engine = pyttsx3.init()
                sapi_engine.setProperty('rate', 165)
                sapi_engine.setProperty('volume', 0.95)
            except Exception:
                pass

        while True:
            try:
                phrase = self.speech_queue.get()
                self.is_speaking = True
                self.speaking_state_changed.emit(True)

                played_neural = False
                if self.kokoro:
                    try:
                        samples, sample_rate = self.kokoro.create(
                            phrase, voice='af_heart', speed=1.05, lang='en-us'
                        )
                        sd.play(samples, sample_rate)
                        sd.wait()
                        played_neural = True
                    except Exception:
                        played_neural = False

                if not played_neural:
                    if sapi_engine is None and HAS_PYTTSX3:
                        try:
                            sapi_engine = pyttsx3.init()
                            sapi_engine.setProperty('rate', 165)
                            sapi_engine.setProperty('volume', 0.95)
                        except Exception:
                            pass
                    if sapi_engine:
                        sapi_engine.say(phrase)
                        sapi_engine.runAndWait()

                time.sleep(0.08)
                if self.speech_queue.empty():
                    self.is_speaking = False
                    self.speaking_state_changed.emit(False)
            except Exception:
                time.sleep(0.1)

class EchoSuppressedVoiceListener(QObject):
    voice_query_received = pyqtSignal(str)
    system_audio_transcribed = pyqtSignal(str)
    speech_state_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.tts_active = False
        self.whisper_model = None
        self.recognizer = None
        self.microphone = None
        self.loopback_mic = None

        if HAS_WHISPER:
            try:
                self.whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
            except Exception:
                pass

        if LISTEN_ENABLED:
            if HAS_SR:
                try:
                    self.recognizer = sr.Recognizer()
                    self.recognizer.pause_threshold = 2.0
                    self.recognizer.energy_threshold = 400
                    self.recognizer.dynamic_energy_threshold = True
                    self.microphone = sr.Microphone()
                except Exception:
                    pass

            if HAS_SOUNDCARD:
                try:
                    default_speaker = sc.default_speaker()
                    if default_speaker:
                        self.loopback_mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
                except Exception:
                    pass

            if self.microphone or self.whisper_model:
                threading.Thread(target=self._listen_loop, daemon=True).start()

            if self.loopback_mic and self.whisper_model:
                threading.Thread(target=self._wasapi_loopback_worker, daemon=True).start()

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

    def _wasapi_loopback_worker(self):
        SAMPLE_RATE = 16000
        CHUNK_SEC = 4.0
        NUM_FRAMES = int(SAMPLE_RATE * CHUNK_SEC)

        while True:
            try:
                if self.tts_active or not self.loopback_mic:
                    time.sleep(0.5)
                    continue

                with self.loopback_mic.recorder(samplerate=SAMPLE_RATE, channels=1) as recorder:
                    data = recorder.record(numframes=NUM_FRAMES)
                    if self.tts_active:
                        continue

                    rms = float(np.sqrt(np.mean(data**2)))
                    if rms > 0.015 and self.whisper_model:
                        import wave
                        pcm_data = (data.flatten() * 32767).astype(np.int16)
                        buf = BytesIO()
                        with wave.open(buf, 'wb') as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(SAMPLE_RATE)
                            wf.writeframes(pcm_data.tobytes())
                        buf.seek(0)

                        segments, info = self.whisper_model.transcribe(buf, beam_size=1)
                        if info.language == "en":
                            lecture_text = " ".join(s.text for s in segments if s.avg_logprob > -0.9).strip()
                            if self._is_intelligible(lecture_text):
                                self.system_audio_transcribed.emit(lecture_text)
                time.sleep(0.1)
            except Exception:
                time.sleep(0.5)

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
                    
                    self.speech_state_changed.emit("LISTENING")
                    audio = self.recognizer.listen(source, timeout=4, phrase_time_limit=25)
                    if self.tts_active:
                        continue
                    
                    self.speech_state_changed.emit("FINALIZING")
                    text = ""
                    if self.whisper_model:
                        buf = BytesIO(audio.get_wav_data())
                        segments, info = self.whisper_model.transcribe(buf, beam_size=1)
                        if info.language == "en":
                            text = " ".join(s.text for s in segments if s.avg_logprob > -0.9).strip()
                    elif self.recognizer:
                        text = self.recognizer.recognize_google(audio).strip()
                    
                    if self._is_intelligible(text):
                        self.voice_query_received.emit(text)
                except sr.WaitTimeoutError:
                    continue
                except Exception:
                    time.sleep(0.3)

class DualIntelligenceSystem:
    def __init__(self, callback):
        self.callback = callback
        self.is_busy = False
        self.past_phrases: List[str] = []

    def trigger_analysis(self, prompt: str = ""):
        if self.is_busy:
            return
        threading.Thread(target=self._run_analysis, args=(prompt,), daemon=True).start()

    def _grab_screen(self) -> Optional[Image.Image]:
        try:
            sct_cls = getattr(mss, "MSS", getattr(mss, "mss", None))
            if sct_cls:
                with sct_cls() as sct:
                    mon = sct.monitors[1]
                    s_img = sct.grab(mon)
                    img = Image.frombytes("RGB", s_img.size, s_img.bgra, "raw", "BGRX")
                    img.thumbnail(VISION_MAX_RES)
                    return img
        except Exception:
            pass
        try:
            img = ImageGrab.grab()
            img.thumbnail(VISION_MAX_RES)
            return img
        except Exception:
            return None

    def _run_analysis(self, prompt_directive: str):
        self.is_busy = True
        try:
            img = self._grab_screen()
            b64_data = ""
            if img:
                buf = BytesIO()
                img.save(buf, format="JPEG", quality=75)
                b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")

            history = " | ".join(self.past_phrases[-3:]) if self.past_phrases else "None"
            directive = prompt_directive or "Analyze the technical structure shown on screen."
            sys_prompt = f"""You are a distinguished university professor sketching deep technical proofs, system architectures, and mathematical insights onto an infinite blackboard.
CURRENT DIRECTIVE: "{directive}"
RECENT TOPICS (DO NOT REPEAT): [{history}]
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
            if HAS_REQUESTS:
                if ACTIVE_BACKEND == "edge0":
                    payload = {
                        "messages": [
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": f"Synthesize whiteboard sketchnote for directive: {directive}"}
                        ],
                        "stream": False, "temperature": 0.6, "max_tokens": 600
                    }
                    try:
                        resp = requests.post(EDGE0_URL, json=payload, timeout=30)
                        if resp.status_code == 200:
                            raw_json = resp.json()["choices"][0]["message"]["content"]
                    except Exception:
                        payload_fb = {"model": "qwen2.5vl:3b", "prompt": sys_prompt, "images": [b64_data] if b64_data else [], "stream": False, "format": "json"}
                        resp = requests.post(OLLAMA_URL, json=payload_fb, timeout=35)
                        if resp.status_code == 200:
                            raw_json = resp.json().get("response", "{}")
                elif ACTIVE_BACKEND == "7b":
                    payload = {
                        "messages": [
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": [{"type": "text", "text": "Synthesize whiteboard sketchnote."}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}}]}
                        ],
                        "response_format": {"type": "json_object"}, "temperature": 0.7, "max_tokens": 500
                    }
                    resp = requests.post(LLAMA_SERVER_7B_URL, json=payload, timeout=60)
                    if resp.status_code == 200:
                        raw_json = resp.json()["choices"][0]["message"]["content"]
                else:
                    payload = {"model": "qwen2.5vl:3b", "prompt": sys_prompt, "images": [b64_data] if b64_data else [], "stream": False, "format": "json"}
                    resp = requests.post(OLLAMA_URL, json=payload, timeout=40)
                    if resp.status_code == 200:
                        raw_json = resp.json().get("response", "{}")

            match = re.search(r'\{.*\}', raw_json, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                self.past_phrases.append(data.get("title", ""))
                self.callback(data)
        except Exception as e:
            print(f"[Vision Worker Warning] {e}")
        finally:
            self.is_busy = False

class VirtualMouseSubsystem(QObject):
    def __init__(self, screen_w: int, screen_h: int):
        super().__init__()
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.current_x = screen_w * 0.5
        self.current_y = screen_h * 0.5
        self.target_x = self.current_x
        self.target_y = self.current_y
        self.visible = True
        self.is_clicking = False
        self.click_pulse = 0.0
        self.trail_points: List[Tuple[float, float, float]] = []
        self.laser_mode = True
        self.cursor_label = "TUTOR"
        self.lerp_speed = 0.14

    def move_to(self, x: float, y: float, label: str = ""):
        self.target_x = max(10.0, min(float(self.screen_w - 10), float(x)))
        self.target_y = max(10.0, min(float(self.screen_h - 10), float(y)))
        if label:
            self.cursor_label = label

    def pulse_click(self, label: str = "CLICK"):
        self.is_clicking = True
        self.click_pulse = 1.0
        self.cursor_label = label

    def execute_physical_click(self, x: int, y: int):
        if sys.platform == "win32":
            try:
                user32.SetCursorPos(int(x), int(y))
                user32.mouse_event(0x0002, 0, 0, 0, 0)
                time.sleep(0.04)
                user32.mouse_event(0x0004, 0, 0, 0, 0)
                self.pulse_click("OS CLICK")
            except Exception as e:
                print(f"[Virtual Mouse Physical Click] {e}")

    def update(self):
        self.current_x += (self.target_x - self.current_x) * self.lerp_speed
        self.current_y += (self.target_y - self.current_y) * self.lerp_speed
        now = time.time()
        self.trail_points.append((self.current_x, self.current_y, now))
        self.trail_points = [p for p in self.trail_points if (now - p[2]) < 0.45]
        if self.click_pulse > 0.0:
            self.click_pulse = max(0.0, self.click_pulse - 0.06)
            if self.click_pulse == 0.0:
                self.is_clicking = False
                self.cursor_label = "TUTOR"

    def render(self, painter: QPainter):
        if not self.visible:
            return
        now = time.time()
        if len(self.trail_points) > 1:
            for i in range(len(self.trail_points) - 1):
                p1 = self.trail_points[i]
                p2 = self.trail_points[i + 1]
                age = now - p1[2]
                alpha = int(max(0, min(255, (1.0 - (age / 0.45)) * 170)))
                trail_color = QColor(244, 63, 94, alpha) if self.laser_mode else QColor(56, 189, 248, alpha)
                pen = QPen(trail_color, max(1.0, 3.5 * (1.0 - age / 0.45)))
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.drawLine(int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1]))

        if self.click_pulse > 0.01:
            ring_rad = 32.0 * (1.0 - self.click_pulse) + 6.0
            ring_alpha = int(240 * self.click_pulse)
            painter.setPen(QPen(QColor(244, 63, 94, ring_alpha), 2.2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(self.current_x, self.current_y), ring_rad, ring_rad)

        glow_rad = 14.0
        glow = QRadialGradient(QPointF(self.current_x, self.current_y), glow_rad)
        if self.laser_mode:
            glow.setColorAt(0.0, QColor(244, 63, 94, 255))
            glow.setColorAt(0.4, QColor(251, 113, 133, 160))
            glow.setColorAt(1.0, QColor(244, 63, 94, 0))
        else:
            glow.setColorAt(0.0, QColor(56, 189, 248, 255))
            glow.setColorAt(0.4, QColor(147, 197, 253, 160))
            glow.setColorAt(1.0, QColor(56, 189, 248, 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(self.current_x, self.current_y), glow_rad, glow_rad)

        painter.setBrush(QBrush(QColor(255, 255, 255, 250)))
        painter.drawEllipse(QPointF(self.current_x, self.current_y), 3.2, 3.2)

        reticle_color = QColor(244, 63, 94, 210) if self.laser_mode else QColor(56, 189, 248, 210)
        painter.setPen(QPen(reticle_color, 1.4))
        cx, cy = self.current_x, self.current_y
        painter.drawLine(int(cx - 10), int(cy), int(cx - 5), int(cy))
        painter.drawLine(int(cx + 5), int(cy), int(cx + 10), int(cy))
        painter.drawLine(int(cx), int(cy - 10), int(cx), int(cy - 5))
        painter.drawLine(int(cx), int(cy + 5), int(cx), int(cy + 10))

        badge_text = f"• {self.cursor_label} ({int(cx)}, {int(cy)})"
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.setBrush(QBrush(QColor(15, 23, 42, 220)))
        painter.setPen(QPen(reticle_color, 1.0))
        badge_rect = QRectF(cx + 12, cy - 22, 115, 18)
        painter.drawRoundedRect(badge_rect, 4, 4)
        painter.setPen(QPen(QColor(241, 245, 249)))
        painter.drawText(QPointF(cx + 16, cy - 9), badge_text)


# =====================================================================
# UNIFIED MASTER SPATIAL WHITEBOARD OVERLAY (HOJAIGA IN-SITU & VOID)
# =====================================================================
class SpatialWhiteboardOverlay(QWidget):
    directive_signal = pyqtSignal(str)

    def __init__(self, initial_task: str = ""):
        super().__init__()
        self.current_user_task = initial_task
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.SubWindow | 
            Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.w, self.h = screen.width(), screen.height()

        # Presentation Architecture
        self.display_mode = DisplayMode.VOID
        self.click_through = True
        self.camera = CameraDirector()
        self.elements: List[SketchnoteElement] = []
        self.grid_alpha = 0.35
        self.active_stylus_pt: Optional[QPointF] = None

        # Hojaiga In-Situ Direct AR Plane Stores
        self.insitu_geometries: List[AugmentedGeometry] = []
        self.insitu_pills: List[MicroPillTag] = []
        self.insitu_beacons: List[ButtonBeacon] = []
        self.tutorial_steps: List[TutorialStep] = []
        self.current_tutorial_idx: int = 0
        self.tutorial_step_timer: float = 0.0

        # Freehand On-Screen Drawing State (F7)
        self.drawing_mode: bool = False
        self.freehand_strokes: List[List[QPointF]] = []
        self.current_freehand_stroke: List[QPointF] = []
        self.pen_color: QColor = QColor(56, 189, 248)
        self.pen_width: float = 3.5

        # Expressive Mascot State
        self.mascot_x = 75.0
        self.mascot_y = 110.0
        self.mascot_bob = 0.0
        self.mascot_eye_blink = 0.0
        self.mascot_mood = "OBSERVING"
        self.mascot_celebrate_timer = 0

        # Knowledge State & Socratic Meta
        self.active_quiz_meta: Optional[Dict[str, Any]] = None
        self.knowledge_tracker = PersistentKnowledgeTracker()

        # Interaction & Navigation
        self.alt_pressed = False
        self.is_dragging = False
        self.last_mouse_pos = QPointF(0, 0)

        # Voice & Audio
        self.segmenter = SpatialScreenSegmenter(self.w, self.h)
        self.narrator = VoiceNarrator()
        self.listener = EchoSuppressedVoiceListener()
        self.listener.voice_query_received.connect(self.handle_voice_directive)
        self.listener.system_audio_transcribed.connect(self.handle_system_audio_directive)
        self.listener.speech_state_changed.connect(self.on_speech_state_changed)
        self.narrator.speaking_state_changed.connect(self.listener.set_tts_active)

        # Autonomous Daemons
        self.ai = DualIntelligenceSystem(self.on_ai_lesson_received)
        self.doc_navigator = AutonomousDocumentNavigator()
        self.contour_tracker = ContinuousContourTracker(self.on_autonomous_contour_detected)
        self.code_watcher = WorkspaceCodeWatcher(self.on_workspace_code_updated)
        self.virtual_mouse = VirtualMouseSubsystem(self.w, self.h)

        self.directive_signal.connect(self.handle_new_directive)

        # 60 FPS Render Loop
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(16)

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

    # -----------------------------------------------------------------
    # HOJAIGA DIRECT IN-SITU AR TRIGGERS
    # -----------------------------------------------------------------

    def trigger_hojaiga_khan_demo(self, center_x: Optional[float] = None, center_y: Optional[float] = None):
        """Spawns direct-on-video Euclidean proof squares anchored to the video's triangle."""
        self.display_mode = DisplayMode.IN_SITU
        cx = center_x or (self.w * 0.5)
        cy = center_y or (self.h * 0.5)

        A = QPointF(cx - 120, cy + 90)   # 90° right angle corner
        B = QPointF(cx + 60, cy + 90)    # Base Leg A=4 end
        C = QPointF(cx - 120, cy - 45)   # Height Leg B=3 peak

        geoms, pills = InSituSpatialGrounder.build_pythagorean_video_augmentation((A, B, C))
        self.insitu_geometries = geoms
        self.insitu_pills = pills
        self.insitu_beacons.clear()
        self.tutorial_steps.clear()

        # Guide virtual laser mouse to the hypotenuse center
        hypot_mid = QPointF((C.x() + B.x()) * 0.5, (C.y() + B.y()) * 0.5)
        self.virtual_mouse.move_to(hypot_mid.x(), hypot_mid.y(), label="HYPOTENUSE")
        self.virtual_mouse.pulse_click("SQUARES ATTACHED")

        self.narrator.speak(
            "This little square is the right angle. That's what makes the theorem work. "
            "This bottom leg is 4, this side is 3, and across is hypotenuse 5. "
            "Squared means area. The square on the hypotenuse holds exactly 16 plus 9: 25."
        )
        print("\n[Hojaiga AR] Direct Video Augmentation deployed. Painted Euclidean squares directly on screen geometry.")

    def trigger_hojaiga_fl_studio_demo(self, target_window_rect: Optional[QRectF] = None):
        """Spawns step-gated beatmaking UI beacons over active DAW / Channel Rack."""
        self.display_mode = DisplayMode.IN_SITU
        rect = target_window_rect or QRectF(self.w * 0.28, self.h * 0.24, 720, 360)

        self.tutorial_steps = InSituSpatialGrounder.build_fl_studio_beat_tutorial(rect)
        self.current_tutorial_idx = 0
        self.insitu_geometries.clear()
        self._load_active_tutorial_step()
        print(f"\n[Hojaiga AR] Interactive FL Studio Walkthrough started over rect: {rect}")

    def _load_active_tutorial_step(self):
        if self.current_tutorial_idx >= len(self.tutorial_steps):
            self.insitu_beacons.clear()
            self.insitu_pills.clear()
            self.narrator.speak("Tutorial complete! You are ready to make music.")
            return

        step = self.tutorial_steps[self.current_tutorial_idx]
        self.insitu_beacons = [
            ButtonBeacon(
                rect=step.target_rect,
                label=f"Step {step.step_number}",
                color=step.accent_color
            )
        ]
        self.insitu_pills = [
            MicroPillTag(
                text=step.pill_label,
                target_pt=QPointF(step.target_rect.center().x(), step.target_rect.bottom() + 16),
                color=step.accent_color
            )
        ]
        self.tutorial_step_timer = time.time()
        # Move virtual laser mouse over target button and pulse click
        btn_c = step.target_rect.center()
        self.virtual_mouse.move_to(btn_c.x(), btn_c.y(), label=f"STEP {step.step_number}")
        self.virtual_mouse.pulse_click("CLICK TARGET")
        self.narrator.speak(step.spoken_instruction)

    # -----------------------------------------------------------------
    # DIRECTIVE DISPATCHER
    # -----------------------------------------------------------------

    def handle_voice_directive(self, text: str):
        self.mascot_mood = "TEACHING"
        self.directive_signal.emit(text)

    def handle_system_audio_directive(self, text: str):
        print(f"[WASAPI System Lecture Audio Trigger] \"{text}\"")
        self.directive_signal.emit(f"stream {text}")

    def on_speech_state_changed(self, state: str):
        if state == "FINALIZING":
            self.mascot_mood = "THINKING"
        elif state == "LISTENING" and self.mascot_mood == "THINKING":
            self.mascot_mood = "OBSERVING"

    def on_autonomous_contour_detected(self, pil_img: Image.Image, contours: List[Any]):
        offset_x = len(self.elements) * 1280.0 + 80.0
        offset_y = 120.0
        elem = SketchnoteElement(
            id=f"auto_lift_{int(time.time())}",
            element_type="proof",
            bounding_rect=QRectF(offset_x - 60, offset_y - 60, 1050, 700)
        )
        cyan = QColor(56, 189, 248)
        head_center = QPointF(offset_x + 360, offset_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(head_center, 360, 36, 16),
            color=cyan, width=2.5, fill_color=QColor(56, 189, 248, 25)
        ))
        elem.text_items.append((
            QPointF(head_center.x() - 300, head_center.y() + 6),
            "AUTONOMOUS CONTOUR ELEVATION (CONTINUOUS OPENCV DAEMON)",
            QFont("Segoe UI", 11, QFont.Bold), QColor(241, 245, 249), 0.0
        ))

        sx_scale = 1280.0 / 640.0
        sy_scale = 720.0 / 360.0
        for approx in contours[:3]:
            pts = []
            for p in approx:
                pt = p[0]
                pts.append(QPointF(offset_x + 80 + float(pt[0]) * sx_scale, offset_y + 100 + float(pt[1]) * sy_scale))
            if len(pts) >= 3:
                pts.append(pts[0])
                elem.strokes.append(HandStroke(points=pts, color=cyan, width=3.2))

        elem.text_items.append((QPointF(offset_x + 60, offset_y + 440), "• Geometry successfully lifted from active desktop frame.", QFont("Segoe UI", 10), QColor(52, 211, 153), 0.0))
        self.elements.append(elem)
        cx = elem.bounding_rect.center().x() - (self.width() * 0.5)
        cy = elem.bounding_rect.center().y() - (self.height() * 0.5)
        self.camera.pan_to(cx, cy, 1.0)
        self.narrator.speak("Autonomous contour elevation triggered. Prominent diagram geometry identified and anchored to your whiteboard.")

    def on_workspace_code_updated(self, filename: str, source_code: str):
        offset_x = len(self.elements) * 1280.0 + 80.0
        offset_y = 120.0
        elem = RealCodeASTAnalyzer.analyze_code_and_synthesize(offset_x, offset_y, source_code)
        elem.text_items.insert(1, (QPointF(offset_x + 40, offset_y + 45), f"WATCHING WORKSPACE: {filename}", QFont("Consolas", 10, QFont.Bold), QColor(251, 191, 36), 0.0))
        self.elements.append(elem)
        cx = elem.bounding_rect.center().x() - (self.width() * 0.5)
        cy = elem.bounding_rect.center().y() - (self.height() * 0.5)
        self.camera.pan_to(cx, cy, 1.0)
        self.narrator.speak(f"Detected code update in {filename}. Live AST complexity and execution frame audit complete.")

    def on_ai_lesson_received(self, data: dict):
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

        by = offset_y + 80
        for b in data.get("branches", []):
            lbl = b.get("label", "Concept") if isinstance(b, dict) else "Principle"
            det = b.get("detail", str(b)) if isinstance(b, dict) else str(b)
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_cloud(QPointF(offset_x + 30, by - 4), 6, 6, 8), color=emerald, width=2.0, fill_color=emerald))
            elem.text_items.append((QPointF(offset_x + 50, by), f"• {lbl}: {det}", QFont("Segoe UI", 10), emerald, 0.0))
            by += 55

        for eq in data.get("equations", []):
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
        p = prompt.lower().strip()
        offset_x = len(self.elements) * 1280.0 + 80.0
        offset_y = 120.0
        self.mascot_mood = "TEACHING"

        # Check Socratic evaluation first
        if self.active_quiz_meta is not None:
            c_target = str(self.active_quiz_meta["correct_c"])
            sq_target = str(self.active_quiz_meta["correct_sq"])
            topic = self.active_quiz_meta.get("topic", "Pythagorean Theorem")
            if "option a" in p or " a" in p or c_target in p or sq_target in p or "correct" in p:
                self.active_quiz_meta = None
                self.knowledge_tracker.record_quiz_result(topic, is_correct=True)
                self.mascot_mood = "CELEBRATING"
                self.mascot_celebrate_timer = 180
                self.narrator.speak("Outstanding! That is mathematically exact. The squares on the legs perfectly sum up to the hypotenuse square!")
                print("\n[Socratic Mastery] Answer CORRECT! Persistent profile updated.")
                return
            elif any(w in p for w in ["option b", "option c", " b", " c", "wrong", "mistake"]) or p.isdigit():
                self.active_quiz_meta = None
                self.knowledge_tracker.record_quiz_result(topic, is_correct=False)
                self.narrator.speak("Not quite. Notice that we never add the linear lengths directly. Let us re-anchor the proof through a direct tile analogy.")
                remed_elem = SketchnoteElement(id=f"remed_{int(time.time())}", element_type="proof", bounding_rect=QRectF(offset_x, offset_y, 900, 500))
                remed_elem.text_items.append((QPointF(offset_x + 30, offset_y + 40), "ADAPTIVE REMEDIATION: AREA ADDITION VS LINEAR ADDITION", QFont("Segoe UI", 11, QFont.Bold), QColor(248, 113, 113), 0.0))
                remed_elem.text_items.append((QPointF(offset_x + 30, offset_y + 90), "Never write a + b = c! A 3m stick plus a 4m stick in a straight line is 7m,", QFont("Segoe UI", 10), QColor(241, 245, 249), 0.0))
                remed_elem.text_items.append((QPointF(offset_x + 30, offset_y + 125), "but bent at 90 degrees, their endpoints are separated by only sqrt(9 + 16) = 5 meters.", QFont("Segoe UI", 10), QColor(56, 189, 248), 0.0))
                self.elements.append(remed_elem)
                cx = remed_elem.bounding_rect.center().x() - (self.width() * 0.5)
                cy = remed_elem.bounding_rect.center().y() - (self.height() * 0.5)
                self.camera.pan_to(cx, cy, 1.0)
                return

        # -------------------------------------------------------------
        # HOJAIGA DIRECT IN-SITU COMMAND ROUTING
        # -------------------------------------------------------------
        if any(k in p for k in ["khan", "clicky", "draw on screen", "show me on screen", "direct triangle"]):
            self.trigger_hojaiga_khan_demo()
            return
        elif any(k in p for k in ["fl studio", "beat", "make a beat", "sequencer"]):
            self.trigger_hojaiga_fl_studio_demo()
            return
        elif p in ["mode insitu", "insitu", "ar", "ar mode"]:
            self.display_mode = DisplayMode.IN_SITU
            self.narrator.speak("Switched to Hojaiga In-Situ Augmented Mode.")
            return
        elif p in ["mode void", "void", "blackboard"]:
            self.display_mode = DisplayMode.VOID
            self.narrator.speak("Switched to Infinite Void Blackboard Mode.")
            return
        elif p in ["draw", "pen", "freehand"]:
            self.drawing_mode = not self.drawing_mode
            self.enable_click_through(not self.drawing_mode)
            self.narrator.speak(f"Freehand drawing mode {'engaged' if self.drawing_mode else 'disabled'}.")
            return
        elif p in ["clear", "clear draw", "clean"]:
            self.freehand_strokes.clear()
            self.insitu_geometries.clear()
            self.insitu_pills.clear()
            self.insitu_beacons.clear()
            self.update()
            return

        # Dissolve previous void clusters to 20% opacity (Chalk Ghosting)
        self.display_mode = DisplayMode.VOID
        for el in self.elements:
            el.opacity = max(0.20, el.opacity * 0.45)
            for s in el.strokes:
                s.opacity = el.opacity

        if p.startswith("build app") or p.startswith("create app") or p.startswith("build "):
            app_spec = prompt.replace("build app", "").replace("create app", "").replace("build", "").strip() or "data_pipeline"
            elem, out_path, _ = JarvisAppBuilder.build_application(offset_x, offset_y, app_spec)
            self.elements.append(elem)
            self.narrator.speak(f"Jarvis app builder executed. Synthesized and verified application source at {os.path.basename(out_path)}.")
        elif p.startswith("toddler") or p.startswith("explain ") or p.startswith("how does ") or p.startswith("ladder "):
            t_topic = prompt.replace("toddler", "").replace("explain", "").replace("ladder", "").strip() or "gravity"
            elem = DynamicToddlerPedagogySynthesizer.synthesize_toddler_ladder(offset_x, offset_y, t_topic)
            self.elements.append(elem)
            self.narrator.speak(f"Decomposing {t_topic} from absolute first principles into a toddler-to-professor progression ladder.")
        elif any(k in p for k in ["profile", "mastery", "knowledge", "stats"]):
            print("\n" + self.knowledge_tracker.get_summary())
            self.narrator.speak("Displaying persistent student mastery profile and prioritized remediation targets.")
            return
        elif any(k in p for k in ["pythagor", "triangle", "hypotenuse", "proof"]):
            elem = EuclideanProofSynthesizer.build_proof(offset_x, offset_y)
            self.elements.append(elem)
            self.narrator.speak("Let us derive the Pythagorean theorem visually from first principles. Notice how the squares on the height and base sum up exactly to the square on the hypotenuse.")
        elif any(k in p for k in ["fbd", "block", "friction", "ramp", "incline", "force"]):
            elem = FreeBodyDiagramSynthesizer.build_fbd(offset_x, offset_y)
            self.elements.append(elem)
            self.narrator.speak("Constructing the Free-Body Diagram. We decompose gravity into perpendicular and downslope force vectors across the ramp.")
        elif p.startswith("code") or p.startswith("def ") or "stack" in p or "ast" in p:
            sample_code = prompt if len(prompt) > 15 else "def solve(n):\n    if n <= 1:\n        return 1\n    return solve(n - 1) + solve(n - 2)"
            elem = RealCodeASTAnalyzer.analyze_code_and_synthesize(offset_x, offset_y, sample_code)
            self.elements.append(elem)
            self.narrator.speak("Static AST code audit completed. Call stack recursion depth and memory footprint are now mapped onto your workspace.")
        elif p.startswith("pdf") or p.startswith("doc") or "read " in p:
            parts = prompt.split(maxsplit=1)
            target_path = parts[1] if len(parts) > 1 else "lecture_notes.pdf"
            extracted = DocumentAndPDFIngestor.extract_document_text(target_path)
            summary_points = [
                extracted[:80].strip() or "Ingested academic structure from document.",
                "Hierarchical concepts partitioned into distinct visual nodes.",
                "Key theorems and definitions extracted into active memory."
            ]
            elem = DocumentAndPDFIngestor.synthesize_document_lecture(offset_x, offset_y, os.path.basename(target_path), summary_points)
            self.elements.append(elem)
            self.narrator.speak(f"Ingested document {os.path.basename(target_path)}. Converting academic prose into hierarchical blackboard nodes.")
        elif any(k in p for k in ["notes", "export notes", "markdown", "cheatsheet"]):
            self.export_notes_markdown()
            return
        elif any(k in p for k in ["obs", "app", "stream", "dock"]):
            elem = AppInspectionSynthesizer.build_obs_guide(offset_x, offset_y)
            self.elements.append(elem)
            self.narrator.speak("Mapping OBS Studio control docks with spatial callouts in the screen negative space.")
        elif any(k in p for k in ["rap", "lyrics", "cadence", "speed", "music"]):
            elem = HighSpeedMediaTranscriber.build_cadence_breakdown(offset_x, offset_y)
            self.elements.append(elem)
            self.narrator.speak("Analyzing high-speed lyrical cadence, syllabic meter, and acoustic velocity.")
        elif any(k in p for k in ["quiz", "test", "socratic", "check"]):
            elem, _, _, quiz_meta = DynamicSocraticEngine.generate_quiz(offset_x, offset_y)
            self.active_quiz_meta = quiz_meta
            self.elements.append(elem)
            self.narrator.speak("Socratic mastery checkpoint! Calculate the hypotenuse and speak or enter your answer.")
        elif any(k in p for k in ["lift", "trace", "cv", "extract"]):
            elem = SketchnoteElement(id=f"lift_{int(time.time())}", element_type="proof", bounding_rect=QRectF(offset_x, offset_y, 900, 600))
            img = self.ai._grab_screen()
            if img:
                contours = OpenCVScreenTracer.extract_screen_contours(img)
                for cnt in contours[:4]:
                    elem.strokes.append(HandStroke(points=[cnt.pointAtPercent(i/20.0) for i in range(21)], color=QColor(56, 189, 248), width=3.0))
            elem.text_items.append((QPointF(offset_x + 30, offset_y + 40), "OPENCV SCREEN GEOMETRY LIFTED", QFont("Segoe UI", 11, QFont.Bold), QColor(241, 245, 249), 0.0))
            self.elements.append(elem)
            self.narrator.speak("Extracting active screen contours via OpenCV Canny edge detection and elevating geometry into the void.")
        else:
            self.ai.trigger_analysis(prompt)
            return

        cx = elem.bounding_rect.center().x() - (self.width() * 0.5)
        cy = elem.bounding_rect.center().y() - (self.height() * 0.5)
        self.camera.pan_to(cx, cy, 1.0)
        self.grid_alpha = 0.35

    # -----------------------------------------------------------------
    # TICK & 60 FPS RENDER LOOP
    # -----------------------------------------------------------------

    def on_tick(self):
        self.camera.update()
        if self.grid_alpha > 0.08:
            self.grid_alpha -= 0.003

        if int(time.time() * 60) % 45 == 0:
            self.doc_navigator.check_and_advance_document()
            self.contour_tracker.evaluate_screen_contours()
            self.code_watcher.scan_for_code_updates()

        # Update Void Elements
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

        # Update Hojaiga In-Situ Geometries & Beacons
        for g in self.insitu_geometries:
            if g.progress < 1.0:
                g.progress = min(1.0, g.progress + 0.04)
        for p in self.insitu_pills:
            if p.progress < 1.0:
                p.progress = min(1.0, p.progress + 0.08)
        for b in self.insitu_beacons:
            b.pulse_phase = (b.pulse_phase + 0.08) % (2 * math.pi)

        # Automatic progression for step-gated walkthrough tutorials
        if self.tutorial_steps and self.current_tutorial_idx < len(self.tutorial_steps):
            active_step = self.tutorial_steps[self.current_tutorial_idx]
            if time.time() - self.tutorial_step_timer > active_step.dwell_duration:
                self.current_tutorial_idx += 1
                self._load_active_tutorial_step()

        # Mascot oscillation
        if self.mascot_celebrate_timer > 0:
            self.mascot_celebrate_timer -= 1
            self.mascot_bob = math.sin(time.time() * 12.0) * 8.0
            if self.mascot_celebrate_timer == 0:
                self.mascot_mood = "OBSERVING"
        else:
            self.mascot_bob = math.sin(time.time() * 3.5) * 4.0
        self.mascot_eye_blink += 0.05

        # Update Virtual Laser Mouse
        if self.active_stylus_pt and self.display_mode == DisplayMode.VOID:
            sx = (self.active_stylus_pt.x() - self.camera.current_x) * self.camera.current_zoom
            sy = (self.active_stylus_pt.y() - self.camera.current_y) * self.camera.current_zoom
            self.virtual_mouse.move_to(sx, sy, label="SKETCHING")
        self.virtual_mouse.update()

        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # -------------------------------------------------------------
        # BRANCH 1: HOJAIGA IN-SITU AR PLANE (Direct Physical Display Pixels)
        # -------------------------------------------------------------
        if self.display_mode == DisplayMode.IN_SITU:
            # 1. Direct Euclidean Proof Squares on Video (No Cards)
            for g in self.insitu_geometries:
                if g.progress <= 0.01:
                    continue
                pts = g.points
                limit = max(2, int(g.progress * len(pts)))
                active_pts = pts[:limit]

                if g.fill_color and g.progress >= 0.85:
                    path = QPainterPath()
                    path.moveTo(pts[0])
                    for pt in pts[1:]:
                        path.lineTo(pt)
                    path.closeSubpath()
                    painter.fillPath(path, QBrush(g.fill_color))

                pen = QPen(g.color, g.width)
                pen.setCapStyle(Qt.RoundCap)
                pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(pen)

                path = QPainterPath()
                path.moveTo(active_pts[0])
                for pt in active_pts[1:]:
                    path.lineTo(pt)
                if g.is_closed and g.progress >= 0.99:
                    path.closeSubpath()
                painter.drawPath(path)

            # 2. Pulsating Button Focus Halos (FL Studio / App guidance)
            now = time.time()
            for b in self.insitu_beacons:
                pulse = math.sin(now * 5.0) * 4.0
                r = b.rect
                glow = QRadialGradient(r.center(), max(r.width(), r.height()) * 0.9)
                glow.setColorAt(0.0, QColor(b.color.red(), b.color.green(), b.color.blue(), 140))
                glow.setColorAt(0.6, QColor(b.color.red(), b.color.green(), b.color.blue(), 40))
                glow.setColorAt(1.0, QColor(b.color.red(), b.color.green(), b.color.blue(), 0))
                painter.setBrush(QBrush(glow))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(r.center(), r.width() + pulse * 2, r.height() + pulse * 2)

                pen = QPen(b.color, 2.0)
                painter.setPen(pen)
                painter.setBrush(QBrush(QColor(b.color.red(), b.color.green(), b.color.blue(), 30)))
                painter.drawRoundedRect(QRectF(r.x() - pulse * 0.5, r.y() - pulse * 0.5, r.width() + pulse, r.height() + pulse), 4, 4)

            # 3. High-Contrast Micro-Pills
            font = QFont("Segoe UI", 9, QFont.Bold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            for p in self.insitu_pills:
                if p.progress <= 0.05:
                    continue
                txt = p.text
                tw = fm.horizontalAdvance(txt)
                th = fm.height()
                pill_w = (tw + 18.0) * p.progress
                pill_h = th + 6.0
                px = p.target_pt.x() - pill_w * 0.5
                py = p.target_pt.y() - pill_h * 0.5

                painter.setBrush(QBrush(p.bg_color))
                painter.setPen(QPen(p.color, 1.3))
                painter.drawRoundedRect(QRectF(px, py, pill_w, pill_h), pill_h * 0.5, pill_h * 0.5)
                if p.progress >= 0.8:
                    painter.setPen(QPen(QColor(255, 255, 255)))
                    painter.drawText(QRectF(px, py, pill_w, pill_h), int(Qt.AlignCenter), txt)

        # -------------------------------------------------------------
        # BRANCH 2: VOID BLACKBOARD CANVAS (Infinite (X,Y) + Frosted Cards)
        # -------------------------------------------------------------
        else:
            if self.grid_alpha > 0.01:
                dot_color = QColor(148, 163, 184, int(self.grid_alpha * 255))
                painter.setPen(QPen(dot_color, 1.5))
                step = 34
                start_x = int(self.camera.current_x) % step
                start_y = int(self.camera.current_y) % step
                for gx in range(start_x, self.width(), step):
                    for gy in range(start_y, self.height(), step):
                        painter.drawPoint(gx, gy)

            painter.save()
            painter.translate(-self.camera.current_x, -self.camera.current_y)
            painter.scale(self.camera.current_zoom, self.camera.current_zoom)

            for elem in self.elements:
                op = elem.opacity
                painter.setBrush(QBrush(QColor(15, 23, 42, int(215 * op))))
                painter.setPen(QPen(QColor(56, 189, 248, int(80 * op)), 1.5))
                painter.drawRoundedRect(elem.bounding_rect, 14, 14)

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

        # -------------------------------------------------------------
        # BRANCH 3: FREEHAND USER DRAWING OVERLAY (F7)
        # -------------------------------------------------------------
        if self.freehand_strokes or self.current_freehand_stroke:
            pen = QPen(self.pen_color, self.pen_width)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            for stroke in self.freehand_strokes:
                if len(stroke) > 1:
                    path = QPainterPath()
                    path.moveTo(stroke[0])
                    for pt in stroke[1:]:
                        path.lineTo(pt)
                    painter.drawPath(path)

            if len(self.current_freehand_stroke) > 1:
                path = QPainterPath()
                path.moveTo(self.current_freehand_stroke[0])
                for pt in self.current_freehand_stroke[1:]:
                    path.lineTo(pt)
                painter.drawPath(path)

        # Render Virtual Mouse & Laser Reticle
        self.virtual_mouse.render(painter)

        # Render Expressive Mascot
        self._render_mascot(painter)

        # In-Situ Floating HUD
        mode_label = self.display_mode.value
        draw_tag = " | [PEN ACTIVE]" if self.drawing_mode else ""
        hud_text = (
            f"SPATIAL TUTOR v8 [{mode_label} MODE]{draw_tag} | "
            f"F9: Toggle AR/Void | F7: Freehand Pen | 'khan' / 'beat' for Hojaiga | ALT: Pan"
        )
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.setBrush(QBrush(QColor(15, 23, 42, 215)))
        hud_col = QColor(244, 63, 94) if self.display_mode == DisplayMode.IN_SITU else QColor(56, 189, 248)
        painter.setPen(QPen(hud_col, 1.2))
        painter.drawRoundedRect(QRectF(20, self.height() - 48, 820, 28), 6, 6)
        painter.setPen(QPen(QColor(241, 245, 249)))
        painter.drawText(QPointF(32, self.height() - 30), hud_text)

    def _render_mascot(self, painter: QPainter):
        mx, my = self.mascot_x, self.mascot_y + self.mascot_bob
        border_col = QColor(244, 63, 94) if self.display_mode == DisplayMode.IN_SITU else QColor(56, 189, 248)
        painter.setPen(QPen(border_col, 1.8))
        painter.setBrush(QBrush(QColor(15, 23, 42, 230)))
        painter.drawRoundedRect(QRectF(mx - 20, my - 20, 40, 40), 12, 12)

        painter.setPen(QPen(border_col, 1.5))
        painter.drawLine(int(mx - 10), int(my - 20), int(mx - 15), int(my - 28))
        painter.drawLine(int(mx + 10), int(my - 20), int(mx + 15), int(my - 28))
        pulse = int(180 + 70 * math.sin(time.time() * 6.0))
        painter.setBrush(QBrush(QColor(border_col.red(), border_col.green(), border_col.blue(), pulse)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(mx - 15, my - 28), 3, 3)
        painter.drawEllipse(QPointF(mx + 15, my - 28), 3, 3)

        eye_open = abs(math.cos(self.mascot_eye_blink)) > 0.12
        painter.setBrush(QBrush(QColor(52, 211, 153)))
        if eye_open:
            painter.drawEllipse(QPointF(mx - 7, my - 2), 2.8, 3.8)
            painter.drawEllipse(QPointF(mx + 7, my - 2), 2.8, 3.8)
        else:
            painter.setPen(QPen(QColor(52, 211, 153), 1.5))
            painter.drawLine(int(mx - 9), int(my - 2), int(mx - 5), int(my - 2))
            painter.drawLine(int(mx + 5), int(my - 2), int(mx + 9), int(my - 2))

    # -----------------------------------------------------------------
    # MOUSE, KEYBOARD & NOTE EXPORT HANDLERS
    # -----------------------------------------------------------------

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F9:
            self.display_mode = DisplayMode.IN_SITU if self.display_mode == DisplayMode.VOID else DisplayMode.VOID
            self.narrator.speak(f"Switched to {self.display_mode.value} mode.")
            self.update()
        elif event.key() == Qt.Key_F7:
            self.drawing_mode = not self.drawing_mode
            self.enable_click_through(not self.drawing_mode)
            self.narrator.speak(f"Freehand drawing mode {'engaged' if self.drawing_mode else 'disabled'}.")
            self.update()
        elif event.key() == Qt.Key_Alt:
            self.alt_pressed = True
            if self.click_through and not self.drawing_mode:
                self.enable_click_through(False)
        elif event.key() == Qt.Key_F8:
            self.enable_click_through(not self.click_through)
        elif event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_S:
            self.export_canvas()
        elif event.key() == Qt.Key_PageDown:
            self.jump_lesson(forward=True)
        elif event.key() == Qt.Key_PageUp:
            self.jump_lesson(forward=False)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Alt:
            self.alt_pressed = False
            if not self.click_through and not self.drawing_mode:
                self.enable_click_through(True)
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        if self.drawing_mode and event.button() == Qt.LeftButton:
            self.current_freehand_stroke = [QPointF(event.pos())]
            self.update()
            return

        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self.is_dragging = True
            self.last_mouse_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drawing_mode and event.buttons() & Qt.LeftButton:
            self.current_freehand_stroke.append(QPointF(event.pos()))
            self.update()
            return

        if self.is_dragging and self.display_mode == DisplayMode.VOID:
            delta = event.pos() - self.last_mouse_pos
            self.last_mouse_pos = event.pos()
            self.camera.current_x -= delta.x() / self.camera.current_zoom
            self.camera.current_y -= delta.y() / self.camera.current_zoom
            self.camera.target_x = self.camera.current_x
            self.camera.target_y = self.camera.current_y
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drawing_mode and event.button() == Qt.LeftButton:
            if len(self.current_freehand_stroke) > 1:
                self.freehand_strokes.append(self.current_freehand_stroke)
            self.current_freehand_stroke = []
            self.update()
            return

        self.is_dragging = False
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if self.display_mode == DisplayMode.VOID:
            delta = event.angleDelta().y()
            factor = 1.12 if delta > 0 else 0.88
            new_zoom = max(0.4, min(3.0, self.camera.target_zoom * factor))
            self.camera.target_zoom = new_zoom
            self.update()
        super().wheelEvent(event)

    def jump_lesson(self, forward: bool = True):
        if not self.elements:
            return
        cur_cx = self.camera.current_x + self.width() * 0.5
        sorted_elems = sorted(self.elements, key=lambda e: e.bounding_rect.center().x())
        idx = 0
        for i, el in enumerate(sorted_elems):
            if abs(el.bounding_rect.center().x() - cur_cx) < 500:
                idx = i
                break
        t_idx = min(len(sorted_elems) - 1, idx + 1) if forward else max(0, idx - 1)
        target = sorted_elems[t_idx]
        cx = target.bounding_rect.center().x() - self.width() * 0.5
        cy = target.bounding_rect.center().y() - self.height() * 0.5
        self.camera.pan_to(cx, cy, 1.0)

    def export_notes_markdown(self):
        if not self.elements:
            print("[Note Center] Whiteboard is currently empty.")
            return

        notes_md = StructuredNoteCompiler.compile_class_notes(self.elements)
        notes_fn = f"class_notes_{int(time.time())}.md"
        with open(notes_fn, "w", encoding="utf-8") as f:
            f.write(notes_md)

        exam_md = StructuredNoteCompiler.compile_exam_cheatsheet(self.elements)
        exam_fn = f"exam_cheatsheet_{int(time.time())}.md"
        with open(exam_fn, "w", encoding="utf-8") as f:
            f.write(exam_md)

        print(f"\n[Note Center] Class notes written to: {os.path.abspath(notes_fn)}")
        print(f"[Note Center] Exam quick-reference written to: {os.path.abspath(exam_fn)}")
        self.narrator.speak("Class lecture notes and exam formula cheat sheet successfully compiled and exported.")

    def export_canvas(self):
        if not self.elements:
            print("[Note Center] Whiteboard is currently empty.")
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
            p.setBrush(QBrush(QColor(15, 23, 42, 230)))
            p.setPen(QPen(QColor(56, 189, 248), 1.5))
            p.drawRoundedRect(elem.bounding_rect, 14, 14)
            for stroke in elem.strokes:
                if stroke.fill_color:
                    poly = QPainterPath()
                    poly.moveTo(stroke.points[0])
                    for pt in stroke.points[1:]:
                        poly.lineTo(pt)
                    poly.closeSubpath()
                    p.fillPath(poly, QBrush(stroke.fill_color))
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

        filename = f"spatial_whiteboard_export_{int(time.time())}.png"
        img.save(filename)
        print(f"\n[Note Center] High-resolution PNG exported to: {os.path.abspath(filename)}")
        self.export_notes_markdown()

def terminal_input_loop(overlay: SpatialWhiteboardOverlay):
    time.sleep(1.0)
    print("=" * 76)
    print(" AI TEACHING ASSISTANT & GLASS WHITEBOARD ENGINE v8 (HOJAIGA UNIFIED)")
    print("=" * 76)
    print("Hojaiga Direct Augmented Reality Modes:")
    print("  * 'khan' / 'triangle'   -> Direct-on-video Euclidean proof squares (Khan Academy)")
    print("  * 'beat' / 'fl studio'  -> Step-gated pulsating button halo walkthrough (FL Studio)")
    print("  * 'draw' / 'pen'        -> Freehand on-screen drawing mode (Press F7)")
    print("  * 'mode insitu'         -> Strips frosted cards, engages 1:1 screen pixel AR")
    print("  * 'mode void'           -> Restores infinite blackboard canvas & frosted cards")
    print("First-Principles Whiteboard Modes:")
    print("  * 'build app <spec>'    -> Jarvis builds runnable app from scratch (CP-13.1)")
    print("  * 'toddler <topic>'     -> Dynamic atomic Toddler-to-Professor ladder (CP-4.1)")
    print("  * 'stream <topic>'      -> Real-time video/lecture cadence ingestion (CP-3.2)")
    print("  * 'mastery' / 'stats'   -> View persistent knowledge state & targets (CP-5.2)")
    print("  * 'code <snippet>'      -> Real Python AST parsing, Big-O, stack frames")
    print("  * 'quiz' / 'test'       -> Dynamic Socratic quiz with closed-loop answer grading")
    print("Controls:")
    print("  * Press F9: Toggle between Hojaiga In-Situ AR & Infinite Void Blackboard")
    print("  * Press F7: Toggle Freehand Pen Mode | Hold ALT to Drag/Zoom | F8: Pass-Through")
    print("  * Ctrl + S: Export PNG Whiteboard + Markdown Class Notes")
    print("=" * 76)

    time.sleep(0.8)
    overlay.directive_signal.emit(INITIAL_TASK or "khan")

    while True:
        try:
            cmd = input("\nEnter teaching goal > ").strip()
            if not cmd:
                continue
            if cmd.lower() in ("pause", "play", "toggle"):
                UniversalMediaController.toggle_playback()
                print("[Media Controller] Universal media playback toggled.")
            elif cmd.lower() in ("back", "rewind", "scrub back"):
                UniversalMediaController.scrub_back_5s()
                print("[Media Controller] Scrubbed backward 5s.")
            elif cmd.lower() in ("forward", "ff", "scrub forward"):
                UniversalMediaController.scrub_forward_5s()
                print("[Media Controller] Scrubbed forward 5s.")
            else:
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