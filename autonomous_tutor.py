"""
AI Teaching Assistant & Autonomous Whiteboard Tutor (Architecture v4 - Upgraded)
================================================================================
Key Capabilities:
  1. Strict Prompt-Answer Isolation & Anti-Looping State Machine:
     - USER_DIRECTIVE Mode: Fulfills user input directly with custom lines/derivations,
       stopping without generic quiz loops ("What is a romantic wingman vibe?").
     - AUTONOMOUS_LECTURE Mode: Socratic check-ins reserved for passive screen observation.
  2. Fixed In-Situ Screen Anchoring (Normalized & Pixel Support):
     - Translates [0.0 - 1.0] normalized or raw pixel coordinates into exact on-screen boxes.
     - Pulsating In-Situ beacons over video/diagrams, connected to whiteboard cards via organic dashed Béziers.
  3. Restored Specialized Diagram Layouts:
     - free_body: Coordinate axes, mass body, force vector arrows (N, mg, F), and equilibrium equations.
     - derivation: Step-by-step ladder cards connected by downward flow arrows and Q.E.D. summary.
     - petal_hub & mind_map: Organic flower and scalloped cloud clusters with radiating branches.
  4. Two-Way Hands-Free Voice (STT & TTS Lockstep):
     - Background VoiceInputListener (SpeechRecognition) captures spoken questions hands-free.
     - Clause-level TTS streaming moves the micro-stylus in exact lockstep with natural spoken phrases.
  5. Note Center Canvas Export & Navigation:
     - Ctrl + S: Exports the entire infinite canvas to a high-resolution PNG image.
     - PageUp / PageDown: Virtual camera jumps smoothly between past lesson clusters.
     - Alt + Drag: Infinite canvas panning | Alt + Scroll: Zoom (0.4x - 3.0x).
  6. Universal OS Media Control with Active Window Fallback:
     - Sends VK_MEDIA_PLAY_PAUSE with a targeted 'k' / Space fallback for YouTube, Chrome, Edge, VLC.
  7. Multi-Zone Spatial Segmentation (SpatialScreenSegmenter):
     - Recognizes split-screens (YouTube on Left, IDE on Right), keeping the video zone 100% clear.
"""

import sys
import os
import time
import math
import json
import random
import base64
import queue
import threading
import argparse
import re
import enum
from io import BytesIO
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

# Ensure UTF-8 stdout encoding on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# GUI Framework
try:
    from PyQt5.QtCore import Qt, QTimer, QPointF, QRect, QRectF, pyqtSignal, QObject
    from PyQt5.QtGui import (
        QPainter, QPen, QColor, QFont, QBrush, QPainterPath, 
        QPolygonF, QFontMetrics, QLinearGradient, QImage
    )
    from PyQt5.QtWidgets import QApplication, QWidget, QDesktopWidget
except ImportError as e:
    print(f"Error: Missing PyQt5. Run: pip install PyQt5\n{e}")
    sys.exit(1)

# Screen & OS Automation
from PIL import Image, ImageGrab
try:
    import mss
    import requests
except ImportError as e:
    print(f"Error: Missing dependency. Run: pip install mss requests Pillow\n{e}")
    sys.exit(1)

# Optional Local TTS Engine
try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

# Optional Hands-Free STT Engine
try:
    import speech_recognition as sr
    HAS_STT = True
except ImportError:
    HAS_STT = False

# Windows API Bindings
if sys.platform == "win32":
    import ctypes
    try:
        import win32gui
        import win32process
        import win32con
    except ImportError:
        pass


# =====================================================================
# CLI ARGUMENT PARSING & CONFIGURATION
# =====================================================================
parser = argparse.ArgumentParser(description="AI Teaching Assistant - Organic Sketchnote Whiteboard Tutor v4")
parser.add_argument("--7b", action="store_true", help="Use Qwen2.5-VL-7B Deep Analysis on port 8081")
parser.add_argument("--3b", action="store_true", help="Use qwen2.5vl:3b Fast Reflex on port 11434")
parser.add_argument("--task", "--teach", type=str, default="", help="Specific topic or goal for the assistant")
parser.add_argument("--pause-media", action="store_true", default=False, help="Enable automatic OS media pause/resume during whiteboarding")
parser.add_argument("--voice", action="store_true", default=True, help="Enable offline neural TTS narration synchronized with stylus")
parser.add_argument("--no-voice", action="store_true", default=False, help="Disable local speech synthesis narration")
parser.add_argument("--listen", action="store_true", default=True, help="Enable background hands-free speech recognition (STT)")
parser.add_argument("--no-listen", action="store_true", default=False, help="Disable background speech recognition")
parser.add_argument("--cursor", type=str, default="hybrid", choices=["hybrid", "stylus", "avatar"],
                    help="Virtual cursor style: 'hybrid' (morphs stylus/avatar), 'stylus' (8px needle), 'avatar' (glowing orb)")
cli_args, _ = parser.parse_known_args()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
LLAMA_SERVER_7B_URL = os.getenv("HOJAIGA_VISION_PRECISION_ENDPOINT", "http://localhost:8081") + "/v1/chat/completions"

USE_7B = getattr(cli_args, "7b", False) or (os.getenv("AI_TEACHER_MODEL", "").lower() in ["7b", "precision", "qwen7b"])
ACTIVE_BACKEND = "7b" if USE_7B else "3b"

if USE_7B:
    MODEL_DISPLAY_NAME = "Qwen2.5-VL-7B (Port 8081)"
    AI_THINKING_INTERVAL_SEC = 9
    VISION_MAX_RES = (768, 768)
else:
    MODEL_DISPLAY_NAME = "qwen2.5vl:3b (Port 11434)"
    AI_THINKING_INTERVAL_SEC = 6
    VISION_MAX_RES = (1024, 1024)

INITIAL_TASK = cli_args.task or os.getenv("AI_TEACHER_TASK", "")
VOICE_ENABLED = (not cli_args.no_voice) and (cli_args.voice or HAS_PYTTSX3)
LISTEN_ENABLED = (not cli_args.no_listen) and (cli_args.listen or HAS_STT)
AUTO_PAUSE_MEDIA = cli_args.pause_media
CURSOR_STYLE = cli_args.cursor.lower()
UPDATE_INTERVAL_MS = 16


# =====================================================================
# DYNAMIC COLOR THEME PALETTES
# =====================================================================
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
        "formula_border": QColor(52, 211, 153),
        "plaque_bg": QColor(15, 23, 42, 220),
        "arrow": QColor(56, 189, 248)
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
        "formula_border": QColor(244, 63, 94),
        "plaque_bg": QColor(32, 12, 24, 220),
        "arrow": QColor(244, 63, 94)
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
        "formula_border": QColor(34, 197, 94),
        "plaque_bg": QColor(6, 24, 12, 225),
        "arrow": QColor(34, 197, 94)
    }
}

def auto_detect_theme(task: str) -> str:
    t = task.lower()
    if any(k in t for k in ["pickup", "love", "romantic", "crush", "date", "flirt", "anissha", "anisha", "heart", "wingman", "kolkata", "sweet", "sweets"]):
        return "romantic"
    if any(k in t for k in ["hack", "cyber", "terminal", "exploit", "reverse", "kernel", "bash", "memory", "script"]):
        return "hacker"
    return "studious"


# =====================================================================
# THREAD-SAFE SIGNAL BRIDGE
# =====================================================================
class TutorBridge(QObject):
    trigger_void = pyqtSignal()
    dispatch_sketchnote = pyqtSignal(dict)
    set_theme = pyqtSignal(str)
    update_status = pyqtSignal(str)
    pause_media_signal = pyqtSignal()
    resume_media_signal = pyqtSignal()
    voice_query_received = pyqtSignal(str)


# =====================================================================
# UNIVERSAL OS APP & MEDIA CONTROL WITH ACTIVE WINDOW FALLBACK
# =====================================================================
class UniversalAppController:
    """Controls OS media playback, YouTube, VLC, and desktop video players without mouse hijacking."""
    
    @staticmethod
    def send_media_key(vk_code: int):
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
                time.sleep(0.04)
                ctypes.windll.user32.keybd_event(vk_code, 0, 0x0002, 0)
            except Exception as e:
                print(f"[MediaController Error] {e}")

    @classmethod
    def pause_media(cls):
        """Toggles media playback with global media key, falling back to window-targeted 'k' / Space."""
        cls.send_media_key(0xB3)  # VK_MEDIA_PLAY_PAUSE
        
        # In case Chrome/Edge/YouTube does not bind global media key, send virtual 'k' to active player
        if sys.platform == "win32":
            try:
                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    title = win32gui.GetWindowText(hwnd).lower()
                    if any(b in title for b in ["chrome", "edge", "youtube", "vlc", "player", "media"]):
                        # Virtual key code for 'k' is 0x4B
                        ctypes.windll.user32.keybd_event(0x4B, 0, 0, 0)
                        time.sleep(0.03)
                        ctypes.windll.user32.keybd_event(0x4B, 0, 0x0002, 0)
            except Exception:
                pass

    @classmethod
    def resume_media(cls):
        cls.send_media_key(0xB3)
        if sys.platform == "win32":
            try:
                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    title = win32gui.GetWindowText(hwnd).lower()
                    if any(b in title for b in ["chrome", "edge", "youtube", "vlc", "player", "media"]):
                        ctypes.windll.user32.keybd_event(0x4B, 0, 0, 0)
                        time.sleep(0.03)
                        ctypes.windll.user32.keybd_event(0x4B, 0, 0x0002, 0)
            except Exception:
                pass

    @classmethod
    def scrub(cls, seconds: int = 5):
        """Scrubs forward (seconds > 0) or backward (seconds < 0)."""
        vk = 0x27 if seconds > 0 else 0x25
        count = max(1, abs(seconds) // 5)
        for _ in range(count):
            cls.send_media_key(vk)
            time.sleep(0.03)

    @classmethod
    def modulate_speed(cls, faster: bool = True):
        """Shift + '.' (>) or Shift + ',' (<)."""
        if sys.platform == "win32":
            try:
                VK_SHIFT = 0x10
                VK_PERIOD = 0xBE
                VK_COMMA = 0xBC
                vk = VK_PERIOD if faster else VK_COMMA
                ctypes.windll.user32.keybd_event(VK_SHIFT, 0, 0, 0)
                time.sleep(0.02)
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                time.sleep(0.03)
                ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0)
                ctypes.windll.user32.keybd_event(VK_SHIFT, 0, 0x0002, 0)
            except Exception:
                pass


# =====================================================================
# MULTI-ZONE SPLIT-SCREEN SPATIAL SEGMENTATION
# =====================================================================
class SpatialScreenSegmenter:
    """Detects multi-zone split-screen arrangements (e.g., YouTube on Left, IDE on Right)."""
    
    def __init__(self, screen_w: int, screen_h: int):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.content_zone: QRectF = QRectF(0, 0, screen_w / 2.0, screen_h)
        self.whiteboard_zone: QRectF = QRectF(screen_w / 2.0, 0, screen_w / 2.0, screen_h)
        self.split_orientation: str = "VERTICAL_SPLIT"

    def analyze_layout(self) -> Dict[str, Any]:
        if sys.platform != "win32":
            return {"split": "VERTICAL_SPLIT", "whiteboard_rect": self.whiteboard_zone}

        try:
            windows = []
            def enum_cb(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    rect = win32gui.GetWindowRect(hwnd)
                    w = rect[2] - rect[0]
                    h = rect[3] - rect[1]
                    title = win32gui.GetWindowText(hwnd)
                    if w > 300 and h > 200 and title:
                        windows.append((title, rect, w, h))
                return True
            win32gui.EnumWindows(enum_cb, None)

            has_left_media = False
            has_right_media = False
            mid_x = self.screen_w / 2.0

            for title, rect, w, h in windows[:10]:
                cx = (rect[0] + rect[2]) / 2.0
                t_low = title.lower()
                if any(m in t_low for m in ["youtube", "video", "media", "vlc", "chrome", "edge", "player"]):
                    if cx < mid_x:
                        has_left_media = True
                    else:
                        has_right_media = True

            if has_left_media and not has_right_media:
                self.content_zone = QRectF(0, 0, mid_x, self.screen_h)
                self.whiteboard_zone = QRectF(mid_x + 40, 60, mid_x - 80, self.screen_h - 120)
                self.split_orientation = "VERTICAL_SPLIT"
            elif has_right_media and not has_left_media:
                self.content_zone = QRectF(mid_x, 0, mid_x, self.screen_h)
                self.whiteboard_zone = QRectF(40, 60, mid_x - 80, self.screen_h - 120)
                self.split_orientation = "VERTICAL_SPLIT"
            else:
                self.content_zone = QRectF(0, 0, mid_x, self.screen_h)
                self.whiteboard_zone = QRectF(mid_x + 40, 60, mid_x - 80, self.screen_h - 120)
        except Exception:
            pass

        return {
            "orientation": self.split_orientation,
            "content_zone": self.content_zone,
            "whiteboard_zone": self.whiteboard_zone
        }


# =====================================================================
# PROCEDURAL ORGANIC DOODLE ENGINE (AdvancedDoodleEngine)
# =====================================================================
class AdvancedDoodleEngine:
    """Vector primitives for authentic human sketchnotes, mind-maps, ribbons, and glyphs."""

    @staticmethod
    def scalloped_cloud(cx: float, cy: float, rx: float, ry: float, scallops: int = 12) -> QPainterPath:
        path = QPainterPath()
        angle_step = (2 * math.pi) / scallops
        points = []
        for i in range(scallops):
            theta = i * angle_step
            r_curr_x = rx + random.uniform(-2.0, 2.0)
            r_curr_y = ry + random.uniform(-2.0, 2.0)
            points.append((cx + r_curr_x * math.cos(theta), cy + r_curr_y * math.sin(theta)))

        path.moveTo(points[0][0], points[0][1])
        for i in range(scallops):
            p_end = points[(i + 1) % scallops]
            mid_angle = (i + 0.5) * angle_step
            ctrl_dist_x = rx * 1.25 + random.uniform(-3, 3)
            ctrl_dist_y = ry * 1.25 + random.uniform(-3, 3)
            cx_pt = cx + ctrl_dist_x * math.cos(mid_angle)
            cy_pt = cy + ctrl_dist_y * math.sin(mid_angle)
            path.quadTo(cx_pt, cy_pt, p_end[0], p_end[1])
        path.closeSubpath()
        return path

    @staticmethod
    def petal_hub(cx: float, cy: float, r_core: float = 38.0, r_petal: float = 24.0, petals: int = 6) -> QPainterPath:
        """Multi-petal circular flower node matching reference image_fb113b.png."""
        path = QPainterPath()
        path.addEllipse(QPointF(cx, cy), r_core, r_core)
        for i in range(petals):
            theta = i * (2 * math.pi / petals)
            pcx = cx + (r_core + r_petal * 0.75) * math.cos(theta)
            pcy = cy + (r_core + r_petal * 0.75) * math.sin(theta)
            petal_elem = QPainterPath()
            petal_elem.addEllipse(QPointF(pcx, pcy), r_petal, r_petal * 0.8)
            path = path.united(petal_elem)
        return path

    @staticmethod
    def ribbon_banner(x: float, y: float, w: float, h: float) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(x, y)
        path.quadTo(x + w / 2, y - 4, x + w, y)
        path.lineTo(x + w, y + h)
        path.quadTo(x + w / 2, y + h + 4, x, y + h)
        path.closeSubpath()

        # Folded ribbon tails
        tail_w = 16.0
        path.moveTo(x, y + 4)
        path.lineTo(x - tail_w, y - 5)
        path.lineTo(x - tail_w + 5, y + h / 2)
        path.lineTo(x - tail_w, y + h + 7)
        path.lineTo(x, y + h - 4)

        path.moveTo(x + w, y + 4)
        path.lineTo(x + w + tail_w, y - 5)
        path.lineTo(x + w + tail_w - 5, y + h / 2)
        path.lineTo(x + w + tail_w, y + h + 7)
        path.lineTo(x + w, y + h - 4)
        return path

    @staticmethod
    def organic_branch(p_start: Tuple[float, float], p_end: Tuple[float, float]) -> QPainterPath:
        path = QPainterPath()
        sx, sy = p_start
        ex, ey = p_end
        dx = ex - sx
        dy = ey - sy

        path.moveTo(sx, sy)
        ctrl1_x = sx + dx * 0.55 + random.uniform(-5, 5)
        ctrl1_y = sy + dy * 0.15
        ctrl2_x = sx + dx * 0.45
        ctrl2_y = sy + dy * 0.85 + random.uniform(-5, 5)
        path.cubicTo(ctrl1_x, ctrl1_y, ctrl2_x, ctrl2_y, ex, ey)
        return path

    @staticmethod
    def jittered_line(p0: Tuple[float, float], p1: Tuple[float, float]) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(p0[0] + random.uniform(-1, 1), p0[1] + random.uniform(-1, 1))
        mid_x = (p0[0] + p1[0]) / 2.0 + random.uniform(-2, 2)
        mid_y = (p0[1] + p1[1]) / 2.0 + random.uniform(-2, 2)
        path.quadTo(mid_x, mid_y, p1[0], p1[1])
        return path

    @staticmethod
    def sunburst_rays(cx: float, cy: float, r_in: float, r_out: float, count: int = 10) -> QPainterPath:
        path = QPainterPath()
        for i in range(count):
            theta = i * (2 * math.pi / count) + random.uniform(-0.08, 0.08)
            sx = cx + r_in * math.cos(theta)
            sy = cy + r_in * math.sin(theta)
            ex = cx + (r_out + random.uniform(-3, 3)) * math.cos(theta)
            ey = cy + (r_out + random.uniform(-3, 3)) * math.sin(theta)
            path.moveTo(sx, sy)
            path.lineTo(ex, ey)
        return path

    @staticmethod
    def hand_drawn_box(x: float, y: float, w: float, h: float) -> QPainterPath:
        path = QPainterPath()
        j = 2.0
        path.moveTo(x - j, y + random.uniform(-j, j))
        path.lineTo(x + w + j, y + random.uniform(-j, j))
        path.lineTo(x + w + random.uniform(-j, j), y + h + j)
        path.lineTo(x - j, y + h + random.uniform(-j, j))
        path.lineTo(x + random.uniform(-j, j), y - j)
        return path

    @staticmethod
    def free_body_arrow(origin: Tuple[float, float], vector: Tuple[float, float]) -> Tuple[QPainterPath, Tuple[float, float]]:
        path = QPainterPath()
        ox, oy = origin
        vx, vy = vector
        ex, ey = ox + vx, oy + vy

        path.moveTo(ox, oy)
        path.lineTo(ex, ey)

        angle = math.atan2(vy, vx)
        arrow_len = 12.0
        p1 = (ex - arrow_len * math.cos(angle - math.pi / 7), ey - arrow_len * math.sin(angle - math.pi / 7))
        p2 = (ex - arrow_len * math.cos(angle + math.pi / 7), ey - arrow_len * math.sin(angle + math.pi / 7))
        path.lineTo(p1[0], p1[1])
        path.moveTo(ex, ey)
        path.lineTo(p2[0], p2[1])

        label_pos = (ex + 10 * math.cos(angle), ey + 10 * math.sin(angle))
        return path, label_pos

    @staticmethod
    def stick_figure_presenter(x: float, y: float, pointing_to: Tuple[float, float]) -> QPainterPath:
        path = QPainterPath()
        head_r = 9.0
        path.addEllipse(QPointF(x, y - 36.0), head_r, head_r)
        path.moveTo(x, y - 27.0)
        path.lineTo(x, y - 8.0)
        path.moveTo(x, y - 8.0)
        path.lineTo(x - 9.0, y + 16.0)
        path.moveTo(x, y - 8.0)
        path.lineTo(x + 9.0, y + 16.0)
        path.moveTo(x, y - 22.0)
        path.lineTo(x - 10.0, y - 14.0)
        path.lineTo(x - 6.0, y - 8.0)
        px, py = pointing_to
        angle = math.atan2(py - (y - 20.0), px - x)
        arm_len = 24.0
        ax = x + arm_len * math.cos(angle)
        ay = (y - 20.0) + arm_len * math.sin(angle)
        path.moveTo(x, y - 20.0)
        path.lineTo(ax, ay)
        return path

    @staticmethod
    def lightbulb(x: float, y: float, size: float = 30.0) -> QPainterPath:
        path = QPainterPath()
        r = size * 0.4
        path.addEllipse(QPointF(x, y - r * 0.5), r, r)
        path.moveTo(x - r * 0.4, y + r * 0.5)
        path.lineTo(x + r * 0.4, y + r * 0.5)
        path.lineTo(x + r * 0.25, y + r * 0.85)
        path.lineTo(x - r * 0.25, y + r * 0.85)
        path.closeSubpath()
        for theta in [-0.6, -0.3, 0.0, 0.3, 0.6]:
            rx1 = x + (r + 4) * math.sin(theta)
            ry1 = (y - r * 0.5) - (r + 4) * math.cos(theta)
            rx2 = x + (r + 10) * math.sin(theta)
            ry2 = (y - r * 0.5) - (r + 10) * math.cos(theta)
            path.moveTo(rx1, ry1)
            path.lineTo(rx2, ry2)
        return path

    @staticmethod
    def lightning_bolt(x: float, y: float, size: float = 26.0) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(x, y - size * 0.5)
        path.lineTo(x - size * 0.25, y)
        path.lineTo(x, y)
        path.lineTo(x - size * 0.1, y + size * 0.5)
        path.lineTo(x + size * 0.25, y - size * 0.05)
        path.lineTo(x + size * 0.05, y - size * 0.05)
        path.closeSubpath()
        return path

    @staticmethod
    def hand_drawn_star(cx: float, cy: float, size: float = 14.0) -> QPainterPath:
        path = QPainterPath()
        points = []
        for i in range(10):
            r = size if i % 2 == 0 else size * 0.45
            r += random.uniform(-0.8, 0.8)
            theta = i * math.pi / 5.0 - math.pi / 2.0
            points.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))
        path.moveTo(points[0][0], points[0][1])
        for pt in points[1:]:
            path.lineTo(pt[0], pt[1])
        path.closeSubpath()
        return path

    @staticmethod
    def squiggly_underline(x: float, y: float, w: float, amplitude: float = 2.5) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(x, y)
        step = 8.0
        cur_x = x
        sign = 1
        while cur_x < x + w:
            next_x = min(x + w, cur_x + step)
            path.quadTo(cur_x + step / 2.0, y + (amplitude * sign), next_x, y)
            cur_x = next_x
            sign *= -1
        return path

DoodleEngine = AdvancedDoodleEngine


# =====================================================================
# ZERO-OVERWRITE RADIAL OCCUPANCY MANAGER
# =====================================================================
class OccupancyManager:
    def __init__(self):
        self.boxes: List[Tuple[float, float, float, float]] = []

    def get_open_rect(self, w: float, h: float, origin: Tuple[float, float], bounds: Optional[QRectF] = None) -> Tuple[float, float]:
        ox, oy = origin
        if bounds:
            ox = max(bounds.x() + 20.0, min(bounds.right() - w - 20.0, ox))
            oy = max(bounds.y() + 20.0, min(bounds.bottom() - h - 20.0, oy))

        if not self._collides(ox, oy, w, h):
            self.boxes.append((ox, oy, w, h))
            return ox, oy

        radius = 80.0
        angle = 0.0
        while radius < 8000.0:
            tx = ox + radius * math.cos(angle)
            ty = oy + radius * math.sin(angle)
            if bounds:
                tx = max(bounds.x() + 20.0, min(bounds.right() - w - 20.0, tx))
                ty = max(bounds.y() + 20.0, min(bounds.bottom() - h - 20.0, ty))
            else:
                tx = max(80.0, tx)

            if ty >= oy - 50:
                if not self._collides(tx, ty, w, h):
                    self.boxes.append((tx, ty, w, h))
                    return tx, ty
            angle += 0.35
            radius += 18.0

        fallback = (ox + w + 80.0, oy)
        self.boxes.append((fallback[0], fallback[1], w, h))
        return fallback

    def _collides(self, x: float, y: float, w: float, h: float) -> bool:
        pad = 40.0
        for bx, by, bw, bh in self.boxes:
            if not (x + w + pad < bx or x > bx + bw + pad or y + h + pad < by or y > by + bh + pad):
                return True
        return False


# =====================================================================
# CLAUSE-LEVEL STREAMING VOICE NARRATOR (TTS)
# =====================================================================
class VoiceNarrator(QObject):
    clause_started = pyqtSignal(int, str)
    clause_finished = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.speech_queue = queue.Queue()
        self.is_speaking = False
        self.engine = None
        if HAS_PYTTSX3 and VOICE_ENABLED:
            threading.Thread(target=self._worker, daemon=True).start()

    def speak_clauses(self, clauses: List[str]):
        if not (HAS_PYTTSX3 and VOICE_ENABLED):
            return
        for i, clause in enumerate(clauses):
            c_clean = clause.strip()
            if c_clean:
                self.speech_queue.put((i, c_clean))

    def _worker(self):
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 165)
            self.engine.setProperty('volume', 0.95)
            while True:
                idx, phrase = self.speech_queue.get()
                if phrase:
                    self.is_speaking = True
                    self.clause_started.emit(idx, phrase)
                    self.engine.say(phrase)
                    self.engine.runAndWait()
                    self.is_speaking = False
                    self.clause_finished.emit(idx)
        except Exception:
            pass


# =====================================================================
# TWO-WAY HANDS-FREE VOICE INPUT LISTENER (STT)
# =====================================================================
class VoiceInputListener(QObject):
    """Background microphone listener enabling hands-free questions without switching windows."""
    voice_query_received = pyqtSignal(str)

    def __init__(self, bridge: TutorBridge):
        super().__init__()
        self.bridge = bridge
        self.recognizer = None
        self.microphone = None
        if HAS_STT and LISTEN_ENABLED:
            try:
                self.recognizer = sr.Recognizer()
                self.recognizer.energy_threshold = 280
                self.recognizer.dynamic_energy_threshold = True
                self.recognizer.pause_threshold = 0.8
                self.microphone = sr.Microphone()
                threading.Thread(target=self._listen_loop, daemon=True).start()
            except Exception as e:
                print(f"[Voice Listener Notice] Speech input disabled: {e}")

    def _listen_loop(self):
        if not self.microphone:
            return
        with self.microphone as source:
            try:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.8)
            except Exception:
                pass
            print("[Voice Listener] Microphone ready (hands-free active). Speak your question anytime.")
            while True:
                try:
                    audio = self.recognizer.listen(source, timeout=4, phrase_time_limit=10)
                    try:
                        text = self.recognizer.recognize_google(audio)
                        if text and len(text.strip()) > 3:
                            print(f"\n[Voice Listener] Captured Spoken Query: \"{text}\"")
                            self.voice_query_received.emit(text.strip())
                    except Exception:
                        pass
                except Exception:
                    time.sleep(0.5)


# =====================================================================
# INTELLIGENCE ENGINE & PROMPT-ANSWER ISOLATION
# =====================================================================
class TeachingMode(enum.Enum):
    USER_DIRECTIVE = "USER_DIRECTIVE"
    AUTONOMOUS_LECTURE = "AUTONOMOUS_LECTURE"


class DualIntelligenceSystem:
    def __init__(self, bridge: TutorBridge):
        self.bridge = bridge
        self.task_goal = INITIAL_TASK or "Auto-Scanning screen"
        self.theme = auto_detect_theme(self.task_goal)
        self.is_teaching = False
        self.mode = TeachingMode.USER_DIRECTIVE if INITIAL_TASK else TeachingMode.AUTONOMOUS_LECTURE
        self.past_phrases_log: List[str] = []
        self.fifo_concept_queue: List[str] = []

        threading.Thread(target=self._crawler_loop, daemon=True).start()

    def set_goal(self, new_goal: str):
        self.task_goal = new_goal.strip()
        self.theme = auto_detect_theme(self.task_goal)
        self.bridge.set_theme.emit(self.theme)
        if self.task_goal and self.task_goal != "Auto-Scanning screen":
            self.mode = TeachingMode.USER_DIRECTIVE
        else:
            self.mode = TeachingMode.AUTONOMOUS_LECTURE
        self.is_teaching = False

    def _grab_screen(self) -> Optional[Image.Image]:
        try:
            sct_cls = getattr(mss, "MSS", getattr(mss, "mss", None))
            with sct_cls() as sct:
                mon = sct.monitors[1]
                s_img = sct.grab(mon)
                img = Image.frombytes("RGB", s_img.size, s_img.bgra, "raw", "BGRX")
                img.thumbnail(VISION_MAX_RES)
                return img
        except Exception:
            return ImageGrab.grab()

    def _encode_image(self, img: Image.Image) -> str:
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _build_prompt(self) -> str:
        history_clause = ""
        if self.past_phrases_log:
            recent = " | ".join(self.past_phrases_log[-4:])
            history_clause = f"\nALREADY TAUGHT (DO NOT REPEAT WORDS, ANALOGIES, OR QUESTIONS): [{recent}]"

        if self.mode == TeachingMode.USER_DIRECTIVE:
            return f"""You are a human live-tutor whiteboarding an organic sketchnote.
CURRENT USER DIRECTIVE: "{self.task_goal}"
ACTIVE VIBE: "{self.theme.upper()}"
{history_clause}

CRITICAL RULES FOR USER DIRECTIVE:
1. Address the CURRENT USER DIRECTIVE directly and specifically.
2. DO NOT ask Socratic questions, do NOT quiz the user (e.g. DO NOT ask "What is a romantic wingman vibe?").
3. If the user asks for a pickup line, story, sweet comment, or joke, output clever, tailored, witty lines for that exact persona/city!
4. If the user asks for math/physics/derivation, choose "free_body" or "derivation" and output real relations.
5. Choose an expressive visual diagram: "mind_map", "petal_hub", "free_body", "derivation", or "cloud_hub".

Return ONLY RAW JSON:
{{
  "title": "Short Core Banner Heading",
  "central_hub": "Key Anchor Concept",
  "diagram_style": "mind_map", // options: mind_map, petal_hub, free_body, derivation, cloud_hub
  "branches": [
    {{"label": "Direct Answer Branch", "detail": "Specific punchline, insight, or formula"}},
    {{"label": "Supporting Insight", "detail": "Nuanced context or sweet metaphor"}}
  ],
  "equations_or_punchlines": [">> Core Formula or Witty Line"],
  "screen_anchors": [], // optional: [{{"label": "Target Element", "box": [0.1, 0.2, 0.3, 0.2]}}]
  "glyphs": ["lightbulb", "star"], // options: lightbulb, lightning_bolt, star, stick_figure
  "narration_clauses": [
    "Core concept introduction sentence.",
    "Supporting punchline or mathematical breakdown."
  ],
  "queued_next_topic": "Next logical step in sequence"
}}
"""
        else:
            return f"""You are a live human tutor observing an on-screen lecture or application.
ACTIVE TOPIC: Auto-Scanning Screen
ACTIVE VIBE: "{self.theme.upper()}"
{history_clause}

Synthesize an organic sketchnote lesson from the screen. Socratic guidance is permitted.

Return ONLY RAW JSON:
{{
  "title": "Short Core Banner Heading",
  "central_hub": "Key Anchor Concept",
  "diagram_style": "mind_map",
  "branches": [
    {{"label": "Observation", "detail": "Key takeaway or question"}},
    {{"label": "Supporting Insight", "detail": "Supporting detail"}}
  ],
  "equations_or_punchlines": [">> Core Formula or Key Insight"],
  "screen_anchors": [],
  "glyphs": ["lightbulb"],
  "narration_clauses": ["Observing screen content.", "Here is the key takeaway."],
  "queued_next_topic": "Next topic"
}}
"""

    def _crawler_loop(self):
        while True:
            try:
                if not self.is_teaching and self.task_goal == "Auto-Scanning screen" and self.fifo_concept_queue:
                    next_q = self.fifo_concept_queue.pop(0)
                    print(f"[Concept FIFO] Silently advancing to queued concept: '{next_q}'")
                    self.task_goal = next_q
                    self.mode = TeachingMode.AUTONOMOUS_LECTURE

                if not self.is_teaching:
                    img = self._grab_screen()
                    if img:
                        b64_data = self._encode_image(img)
                        prompt = self._build_prompt()
                        self.bridge.update_status.emit(f"Synthesizing ({MODEL_DISPLAY_NAME})...")

                        raw_json = "{}"
                        if ACTIVE_BACKEND == "7b":
                            payload = {
                                "messages": [
                                    {"role": "system", "content": prompt},
                                    {
                                        "role": "user",
                                        "content": [
                                            {"type": "text", "text": "Synthesize whiteboard lesson."},
                                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}}
                                        ]
                                    }
                                ],
                                "response_format": {"type": "json_object"},
                                "temperature": 0.8,
                                "top_p": 0.9,
                                "max_tokens": 520
                            }
                            resp = requests.post(LLAMA_SERVER_7B_URL, json=payload, timeout=90)
                            if resp.status_code == 200:
                                raw_json = resp.json()["choices"][0]["message"]["content"]
                        else:
                            payload = {
                                "model": "qwen2.5vl:3b",
                                "prompt": prompt,
                                "images": [b64_data],
                                "stream": False,
                                "format": "json",
                                "options": {"temperature": 0.8, "top_p": 0.9}
                            }
                            resp = requests.post(OLLAMA_URL, json=payload, timeout=40)
                            if resp.status_code == 200:
                                raw_json = resp.json().get("response", "{}")

                        match = re.search(r'\{.*\}', raw_json, re.DOTALL)
                        if match:
                            data = json.loads(match.group(0))
                            if data.get("branches") or data.get("title") or data.get("central_hub"):
                                self.is_teaching = True
                                self.bridge.trigger_void.emit()
                                if AUTO_PAUSE_MEDIA:
                                    self.bridge.pause_media_signal.emit()
                                self.bridge.dispatch_sketchnote.emit(data)

                                title = data.get("title", "")
                                self.past_phrases_log.append(title)
                                if len(self.past_phrases_log) > 6:
                                    self.past_phrases_log.pop(0)

                                queued = data.get("queued_next_topic")
                                if queued and queued not in self.fifo_concept_queue:
                                    self.fifo_concept_queue.append(queued)

                                if self.mode == TeachingMode.USER_DIRECTIVE:
                                    self.mode = TeachingMode.AUTONOMOUS_LECTURE
                                    self.task_goal = "Auto-Scanning screen"

            except Exception as e:
                self.bridge.update_status.emit(f"AI: {str(e)[:24]}")

            time.sleep(AI_THINKING_INTERVAL_SEC)


# =====================================================================
# DATA STRUCTURES FOR IN-SITU SCREEN ANCHORS
# =====================================================================
@dataclass
class ScreenAnchorItem:
    sx: float
    sy: float
    sw: float
    sh: float
    wx: float
    wy: float
    label: str
    color: QColor
    created_at: float


# =====================================================================
# MASTER OVERLAY WITH REAL-TIME SKETCHNOTING & TTS/STT
# =====================================================================
class SketchnoteTutorOverlay(QWidget):
    def __init__(self, initial_task=""):
        super().__init__()
        self.bridge = TutorBridge()
        self.bridge.trigger_void.connect(self.activate_void)
        self.bridge.dispatch_sketchnote.connect(self.on_sketchnote_received)
        self.bridge.set_theme.connect(self.apply_theme)
        self.bridge.update_status.connect(self.apply_status)
        self.bridge.pause_media_signal.connect(UniversalAppController.pause_media)
        self.bridge.resume_media_signal.connect(UniversalAppController.resume_media)

        self.current_user_task = initial_task
        self.theme_name = auto_detect_theme(initial_task)
        self.theme = THEMES[self.theme_name]
        self.ai_status = "Ready"

        desktop = QDesktopWidget().geometry()
        self.w, self.h = desktop.width(), desktop.height()

        self.segmenter = SpatialScreenSegmenter(self.w, self.h)

        # Infinite Canvas & Camera
        self.cam_x = 0.0
        self.cam_y = 0.0
        self.target_cam_x = 0.0
        self.target_cam_y = 0.0
        self.cam_zoom = 1.0

        # Physical User Mouse Navigation
        self.user_navigating = False
        self.last_mouse_pos = QPointF(0, 0)

        # Micro-Stylus
        self.cursor_style = CURSOR_STYLE
        self.stylus_x = 350.0
        self.stylus_y = 250.0
        self.target_stylus_x = 350.0
        self.target_stylus_y = 250.0

        # Bezel Companion Mascot
        self.mascot_x = 75.0
        self.mascot_y = 110.0
        self.mascot_target_x = 75.0
        self.mascot_target_y = 110.0
        self.mascot_eye_blink = 0.0
        self.mascot_mood = "OBSERVING"

        # Void Dotted Screen Fade State
        self.void_alpha = 0.0
        self.void_fade_dir = 0

        # Canvas Geometries
        self.occupancy = OccupancyManager()
        self.vector_paths: List[Dict[str, Any]] = []
        self.text_entities: List[Dict[str, Any]] = []
        self.frosted_plaques: List[QRectF] = []
        self.screen_anchors: List[ScreenAnchorItem] = []

        # Clause-Level Audio Narration (TTS)
        self.narrator = VoiceNarrator()
        self.narrator.clause_started.connect(self._on_clause_started)
        self.narrator.clause_finished.connect(self._on_clause_finished)
        self.current_speaking_clause = -1

        # Two-Way Hands-Free Voice Listener (STT)
        self.voice_listener = VoiceInputListener(self.bridge)
        self.voice_listener.voice_query_received.connect(self.set_user_task)

        self._init_window_flags()

        self.physics_timer = QTimer(self)
        self.physics_timer.timeout.connect(self._update_physics)
        self.physics_timer.start(UPDATE_INTERVAL_MS)

        self.ai = DualIntelligenceSystem(self.bridge)

    def _init_window_flags(self):
        self.setGeometry(0, 0, self.w, self.h)
        self.setWindowTitle("AI TEACHING ASSISTANT - ORGANIC SKETCHNOTE TUTOR v4")

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self._apply_os_clickthrough(True)
        self.showFullScreen()

    def _apply_os_clickthrough(self, transparent: bool):
        if sys.platform == "win32":
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if transparent:
                style |= (0x00000020 | 0x00080000)
            else:
                style &= ~0x00000020
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

    def keyPressEvent(self, event):
        # ALT: Engage physical mouse navigation
        if event.key() == Qt.Key_Alt:
            self.user_navigating = True
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self._apply_os_clickthrough(False)

        # Ctrl+S: Export entire infinite canvas to high-res image ("Note Center")
        elif event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_S:
            self.export_note_center()

        # PageUp / PageDown: Jump virtual camera between past whiteboard lessons
        elif event.key() == Qt.Key_PageDown:
            self.jump_lesson(forward=True)
        elif event.key() == Qt.Key_PageUp:
            self.jump_lesson(forward=False)

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Alt:
            self.user_navigating = False
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._apply_os_clickthrough(True)
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self.last_mouse_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.user_navigating or event.buttons() & Qt.MiddleButton:
            delta = event.pos() - self.last_mouse_pos
            self.cam_x -= delta.x() / self.cam_zoom
            self.cam_y -= delta.y() / self.cam_zoom
            self.target_cam_x = self.cam_x
            self.target_cam_y = self.cam_y
            self.last_mouse_pos = event.pos()
            self.update()
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        if self.user_navigating:
            factor = 1.1 if event.angleDelta().y() > 0 else 0.9
            self.cam_zoom = max(0.4, min(3.0, self.cam_zoom * factor))
            self.update()
        super().wheelEvent(event)

    def activate_void(self):
        self.void_alpha = 0.01
        self.void_fade_dir = 1

    def apply_theme(self, theme_key: str):
        if theme_key in THEMES and theme_key != self.theme_name:
            self.theme_name = theme_key
            self.theme = THEMES[theme_key]
            self.update()

    def apply_status(self, status: str):
        self.ai_status = status

    def set_user_task(self, task: str):
        self.current_user_task = task.strip()
        new_theme = auto_detect_theme(self.current_user_task)
        self.apply_theme(new_theme)
        print(f"\n[AI Focus Updated] Now resolving: \"{self.current_user_task}\" ({self.theme['name']})")
        self.ai.set_goal(self.current_user_task)

    def _on_clause_started(self, clause_idx: int, phrase: str):
        self.current_speaking_clause = clause_idx
        self.mascot_mood = "TEACHING"

    def _on_clause_finished(self, clause_idx: int):
        if self.current_speaking_clause == clause_idx:
            self.current_speaking_clause = -1

    # -----------------------------------------------------------------------
    # SPECIALIZED DIAGRAM ROUTING & FIXED ANCHOR NORMALIZATION
    # -----------------------------------------------------------------------
    def on_sketchnote_received(self, data: dict):
        """Builds mind-map hubs, petal nodes, free-body axes, derivations, and in-situ anchors."""
        layout = self.segmenter.analyze_layout()
        whiteboard_bounds = layout["whiteboard_zone"]

        cluster_w, cluster_h = 580.0, 440.0
        target_origin = (whiteboard_bounds.x() + 40.0, whiteboard_bounds.y() + 40.0)
        wx, wy = self.occupancy.get_open_rect(cluster_w, cluster_h, target_origin, bounds=whiteboard_bounds)

        self.target_cam_x = wx - 60.0
        self.target_cam_y = wy - 40.0
        self.frosted_plaques.append(QRectF(wx, wy, cluster_w, cluster_h))

        th = self.theme
        self.mascot_target_x = 75.0
        self.mascot_target_y = 130.0
        self.mascot_mood = "TEACHING"

        title = data.get("title", "Concept Discovery").upper()
        hub_text = data.get("central_hub", title)
        diagram_style = str(data.get("diagram_style", "mind_map")).lower()
        branches = data.get("branches", [])
        eqs = data.get("equations_or_punchlines", [])

        # 1. Header Ribbon Banner
        banner_path = AdvancedDoodleEngine.ribbon_banner(wx + 40.0, wy + 20.0, cluster_w - 80.0, 36.0)
        self.vector_paths.append({"path": banner_path, "color": th["hub_border"], "fill": th["hub_bg"], "width": 2.0})
        self.text_entities.append({
            "text": title, "current_len": 0, "x": wx + 60.0, "y": wy + 44.0,
            "color": th["text_main"], "font": QFont("Segoe UI", 11, QFont.Bold), "clause_idx": 0
        })

        # 2. Specialized Diagram Routing
        if diagram_style == "free_body":
            # Coordinate Axes & Force Vectors
            ox, oy = wx + cluster_w / 2.0, wy + 160.0
            axis_x = DoodleEngine.jittered_line((ox - 80.0, oy), (ox + 80.0, oy))
            axis_y = DoodleEngine.jittered_line((ox, oy + 70.0), (ox, oy - 70.0))
            self.vector_paths.append({"path": axis_x, "color": th["text_sub"], "fill": None, "width": 1.5})
            self.vector_paths.append({"path": axis_y, "color": th["text_sub"], "fill": None, "width": 1.5})

            # Center mass block
            body = AdvancedDoodleEngine.hand_drawn_box(ox - 24.0, oy - 24.0, 48.0, 48.0)
            self.vector_paths.append({"path": body, "color": th["hub_border"], "fill": th["node_bg"], "width": 2.0})

            # Force arrows
            f_up, p_up = AdvancedDoodleEngine.free_body_arrow((ox, oy - 24.0), (0.0, -55.0))
            f_dn, p_dn = AdvancedDoodleEngine.free_body_arrow((ox, oy + 24.0), (0.0, 55.0))
            f_rt, p_rt = AdvancedDoodleEngine.free_body_arrow((ox + 24.0, oy), (65.0, -25.0))
            self.vector_paths.append({"path": f_up, "color": th["accent"], "fill": None, "width": 2.0})
            self.vector_paths.append({"path": f_dn, "color": th["accent"], "fill": None, "width": 2.0})
            self.vector_paths.append({"path": f_rt, "color": th["arrow"], "fill": None, "width": 2.2})

            self.text_entities.append({"text": "N (Normal)", "current_len": 0, "x": p_up[0] - 25, "y": p_up[1] - 4, "color": th["accent"], "font": QFont("Consolas", 9, QFont.Bold), "clause_idx": 0})
            self.text_entities.append({"text": "mg (Gravity)", "current_len": 0, "x": p_dn[0] - 28, "y": p_dn[1] + 14, "color": th["accent"], "font": QFont("Consolas", 9, QFont.Bold), "clause_idx": 0})

        elif diagram_style == "derivation":
            # Step-by-Step Derivation Ladder
            cur_y = wy + 80.0
            for i, b in enumerate(branches[:3]):
                step_box = AdvancedDoodleEngine.hand_drawn_box(wx + 40.0, cur_y, cluster_w - 80.0, 36.0)
                self.vector_paths.append({"path": step_box, "color": th["node_border"], "fill": th["node_bg"], "width": 1.5})
                self.text_entities.append({
                    "text": f"[{b.get('label', f'Step {i+1}')}] {b.get('detail', '')}",
                    "current_len": 0, "x": wx + 54.0, "y": cur_y + 24.0,
                    "color": th["text_main"], "font": QFont("Consolas", 10, QFont.Bold), "clause_idx": i + 1
                })
                if i < len(branches[:3]) - 1:
                    arr, _ = AdvancedDoodleEngine.free_body_arrow((wx + cluster_w / 2.0, cur_y + 36.0), (0.0, 20.0))
                    self.vector_paths.append({"path": arr, "color": th["accent"], "fill": None, "width": 1.8})
                cur_y += 58.0

        else:
            # Default Mind Map & Petal Cluster
            hub_cx = wx + cluster_w / 2.0
            hub_cy = wy + 124.0

            if diagram_style == "petal_hub":
                hub_path = AdvancedDoodleEngine.petal_hub(hub_cx, hub_cy, r_core=42.0, r_petal=26.0, petals=6)
            else:
                hub_path = AdvancedDoodleEngine.scalloped_cloud(hub_cx, hub_cy, 90.0, 42.0, scallops=12)

            self.vector_paths.append({"path": hub_path, "color": th["hub_border"], "fill": th["hub_bg"], "width": 2.0})

            # Sunburst rays
            rays_path = AdvancedDoodleEngine.sunburst_rays(hub_cx, hub_cy, 98.0, 115.0, count=10)
            self.vector_paths.append({"path": rays_path, "color": th["accent"], "fill": None, "width": 1.5})

            self.text_entities.append({
                "text": hub_text, "current_len": 0, "x": hub_cx - (len(hub_text) * 4.2),
                "y": hub_cy + 5.0, "color": th["accent"], "font": QFont("Segoe UI", 10, QFont.Bold), "clause_idx": 0
            })

            # Radiating branches
            branch_targets = [(wx + 40.0, wy + 240.0), (wx + cluster_w - 240.0, wy + 240.0)]
            for i, branch_data in enumerate(branches[:2]):
                tx, ty = branch_targets[i]
                b_path = AdvancedDoodleEngine.organic_branch((hub_cx, hub_cy + 42.0), (tx + 70.0, ty))
                self.vector_paths.append({"path": b_path, "color": th["branch"], "fill": None, "width": 2.5})

                node_box = AdvancedDoodleEngine.hand_drawn_box(tx, ty, 200.0, 75.0)
                self.vector_paths.append({"path": node_box, "color": th["node_border"], "fill": th["node_bg"], "width": 1.5})

                self.text_entities.append({
                    "text": f"• {branch_data.get('label', 'Point')}", "current_len": 0,
                    "x": tx + 14.0, "y": ty + 24.0, "color": th["text_main"], "font": QFont("Segoe UI", 9, QFont.Bold), "clause_idx": i + 1
                })
                self.text_entities.append({
                    "text": branch_data.get('detail', '')[:32] + ("..." if len(branch_data.get('detail', '')) > 32 else ""),
                    "current_len": 0, "x": tx + 14.0, "y": ty + 46.0, "color": th["text_sub"], "font": QFont("Segoe UI", 8, QFont.Normal), "clause_idx": i + 1
                })

        # 3. Bottom Formula / Punchline Box
        if eqs:
            eq_box = AdvancedDoodleEngine.hand_drawn_box(wx + 60.0, wy + cluster_h - 56.0, cluster_w - 120.0, 34.0)
            self.vector_paths.append({"path": eq_box, "color": th["formula_border"], "fill": th["node_bg"], "width": 1.5})
            self.text_entities.append({
                "text": eqs[0], "current_len": 0, "x": wx + 80.0, "y": wy + cluster_h - 34.0,
                "color": th["badge_text"], "font": QFont("Consolas", 10, QFont.Bold), "clause_idx": len(branches) + 1
            })

        # 4. Graphic Facilitation Glyphs
        glyphs = data.get("glyphs", ["lightbulb", "stick_figure"])
        if "stick_figure" in glyphs or len(branches) > 0:
            stick_path = AdvancedDoodleEngine.stick_figure_presenter(wx + cluster_w - 20.0, wy + cluster_h - 40.0, (wx + cluster_w / 2.0, wy + cluster_h - 40.0))
            self.vector_paths.append({"path": stick_path, "color": th["accent"], "fill": None, "width": 1.8})

        if "lightbulb" in glyphs:
            bulb_path = AdvancedDoodleEngine.lightbulb(wx + 25.0, wy + 32.0, size=24.0)
            self.vector_paths.append({"path": bulb_path, "color": th["accent"], "fill": None, "width": 1.5})

        if "lightning_bolt" in glyphs:
            bolt_path = AdvancedDoodleEngine.lightning_bolt(wx + cluster_w - 30.0, wy + 32.0, size=22.0)
            self.vector_paths.append({"path": bolt_path, "color": th["accent"], "fill": th["accent"], "width": 1.2})

        # 5. In-Situ Screen Anchors (Fixed Normalized vs Raw Pixel Scaling)
        for anchor in data.get("screen_anchors", []):
            box = anchor.get("box", [0.1, 0.1, 0.15, 0.08])
            sx = float(box[0]) * self.w if box[0] <= 1.0 else float(box[0])
            sy = float(box[1]) * self.h if box[1] <= 1.0 else float(box[1])
            sw = float(box[2]) * self.w if box[2] <= 1.0 else float(box[2])
            sh = float(box[3]) * self.h if box[3] <= 1.0 else float(box[3])

            self.screen_anchors.append(ScreenAnchorItem(
                sx=sx, sy=sy, sw=sw, sh=sh,
                wx=wx + 40.0, wy=wy + 40.0,
                label=anchor.get("label", "ACTIVE TARGET"),
                color=th["accent"],
                created_at=time.time()
            ))

        # 6. Lockstep Vocal Narration
        clauses = data.get("narration_clauses", [])
        if not clauses:
            clauses = [f"{title}. {hub_text}."]
            for b in branches:
                clauses.append(f"{b.get('label', '')}. {b.get('detail', '')}.")
            if eqs:
                clauses.append(f"Result: {eqs[0]}")
        self.narrator.speak_clauses(clauses)

        print(f"\n[Autonomous Canvas] Plotted Sketchnote '{title}' ({diagram_style.upper()}) at ({wx:.0f}, {wy:.0f})")

    # -----------------------------------------------------------------------
    # NOTE CENTER EXPORT & PAGE JUMP NAVIGATION
    # -----------------------------------------------------------------------
    def export_note_center(self):
        """Captures and saves all accumulated sketchnotes into a timestamped PNG file."""
        if not self.frosted_plaques:
            print("[Note Center] Canvas is currently empty. No plaques to export.")
            return

        min_x = min(p.x() for p in self.frosted_plaques) - 40
        min_y = min(p.y() for p in self.frosted_plaques) - 40
        max_x = max(p.right() for p in self.frosted_plaques) + 40
        max_y = max(p.bottom() for p in self.frosted_plaques) + 40
        export_w = max(100, int(max_x - min_x))
        export_h = max(100, int(max_y - min_y))

        img = QImage(export_w, export_h, QImage.Format_ARGB32)
        img.fill(QColor(10, 15, 26, 255))

        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(-min_x, -min_y)

        th = self.theme
        for plaque in self.frosted_plaques:
            p.setBrush(QBrush(QColor(15, 23, 42, 240)))
            p.setPen(QPen(th["hub_border"], 1.5))
            p.drawRoundedRect(plaque, 14, 14)

        for vp in self.vector_paths:
            p.setBrush(QBrush(vp["fill"]) if vp.get("fill") else Qt.NoBrush)
            p.setPen(QPen(vp["color"], vp["width"], Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(vp["path"])

        for te in self.text_entities:
            p.setFont(te["font"])
            p.setPen(te["color"])
            p.drawText(QPointF(te["x"], te["y"]), te["text"])

        p.end()

        filename = f"sketchnote_export_{int(time.time())}.png"
        img.save(filename)
        print(f"\n[Note Center] Exported whiteboard snapshot to: {os.path.abspath(filename)}")

    def jump_lesson(self, forward: bool = True):
        """Pans camera to adjacent lesson plaques."""
        if not self.frosted_plaques:
            return
        cur_center_x = self.cam_x + self.w / 2.0
        sorted_plaques = sorted(self.frosted_plaques, key=lambda p: p.x())
        idx = 0
        for i, pl in enumerate(sorted_plaques):
            if abs(pl.center().x() - cur_center_x) < 400:
                idx = i
                break

        target_idx = min(len(sorted_plaques) - 1, idx + 1) if forward else max(0, idx - 1)
        target_p = sorted_plaques[target_idx]
        self.target_cam_x = target_p.x() - 60.0
        self.target_cam_y = target_p.y() - 40.0
        print(f"[Canvas Navigation] Panned to Whiteboard Plaque #{target_idx + 1}")

    def _update_physics(self):
        self.cam_x += (self.target_cam_x - self.cam_x) * 0.07
        self.cam_y += (self.target_cam_y - self.cam_y) * 0.07

        self.stylus_x += (self.target_stylus_x - self.stylus_x) * 0.14
        self.stylus_y += (self.target_stylus_y - self.stylus_y) * 0.14

        self.mascot_x += (self.mascot_target_x - self.mascot_x) * 0.08
        self.mascot_y += (self.mascot_target_y - self.mascot_y) * 0.08
        self.mascot_eye_blink = (self.mascot_eye_blink + 0.04) % (math.pi * 2)

        writing = False
        for t in self.text_entities:
            is_allowed_to_type = (
                self.current_speaking_clause == -1 or 
                t.get("clause_idx", 0) <= self.current_speaking_clause or
                not VOICE_ENABLED
            )
            if is_allowed_to_type and t["current_len"] < len(t["text"]):
                advance = 2 if self.current_speaking_clause != -1 else 1
                t["current_len"] = min(len(t["text"]), t["current_len"] + advance)
                self.target_stylus_x = t["x"] + (t["current_len"] * 7.5)
                self.target_stylus_y = t["y"]
                writing = True
                break

        if not writing and self.mascot_mood == "TEACHING":
            self.mascot_mood = "OBSERVING"

        if self.void_fade_dir == 1:
            self.void_alpha += 0.02
            if self.void_alpha >= 0.35:
                self.void_fade_dir = -1
        elif self.void_fade_dir == -1:
            self.void_alpha -= 0.015
            if self.void_alpha <= 0.0:
                self.void_alpha = 0.0
                self.void_fade_dir = 0
                self.ai.is_teaching = False
                if AUTO_PAUSE_MEDIA:
                    self.bridge.resume_media_signal.emit()

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        if self.void_alpha > 0.005:
            self._render_transient_grid(painter)

        painter.save()
        painter.translate(-self.cam_x * self.cam_zoom, -self.cam_y * self.cam_zoom)
        painter.scale(self.cam_zoom, self.cam_zoom)

        th = self.theme

        # Frosted Glass Card Backings
        for plaque in self.frosted_plaques:
            painter.setBrush(QBrush(QColor(15, 23, 42, 215)))
            painter.setPen(QPen(QColor(th["branch"].red(), th["branch"].green(), th["branch"].blue(), 90), 1.5))
            painter.drawRoundedRect(plaque, 14, 14)

        # Dual-Plane Connectors
        for anchor in self.screen_anchors:
            aw_x = anchor.sx / self.cam_zoom + self.cam_x
            aw_y = anchor.sy / self.cam_zoom + self.cam_y
            branch = AdvancedDoodleEngine.organic_branch((aw_x, aw_y), (anchor.wx, anchor.wy))
            painter.setPen(QPen(anchor.color, 1.5, Qt.DashLine))
            painter.drawPath(branch)

        # Vector Sketchnote Strokes & Shapes
        for vp in self.vector_paths:
            painter.setBrush(QBrush(vp["fill"]) if vp.get("fill") else Qt.NoBrush)
            painter.setPen(QPen(vp["color"], vp["width"], Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(vp["path"])

        # Progressive Text
        for te in self.text_entities:
            painter.setFont(te["font"])
            painter.setPen(te["color"])
            painter.drawText(QPointF(te["x"], te["y"]), te["text"][:te["current_len"]])

        painter.restore()

        # In-Situ Screen Anchors
        now = time.time()
        for anchor in self.screen_anchors:
            pulse = math.sin(now * 4.0) * 3.0
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(anchor.color, 2.0, Qt.SolidLine))
            painter.drawRoundedRect(QRectF(anchor.sx - pulse, anchor.sy - pulse, anchor.sw + pulse * 2, anchor.sh + pulse * 2), 6, 6)
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.setPen(anchor.color)
            painter.drawText(QPointF(anchor.sx, anchor.sy - 6.0), f"⚡ {anchor.label}")

        self._render_stylus(painter)
        self._render_mascot(painter)
        self._render_hud(painter)

        painter.end()

    def _render_transient_grid(self, painter: QPainter):
        alpha = int(255 * self.void_alpha)
        bg = self.theme["void_bg"]
        painter.fillRect(self.rect(), QColor(bg.red(), bg.green(), bg.blue(), int(alpha * 0.8)))
        dots = self.theme["grid_dots"]
        pen = QPen(QColor(dots.red(), dots.green(), dots.blue(), alpha))
        pen.setWidth(2)
        painter.setPen(pen)
        step = 42
        for x in range(20, self.w, step):
            for y in range(20, self.h, step):
                painter.drawPoint(x, y)

    def _render_stylus(self, painter: QPainter):
        sx = (self.stylus_x - self.cam_x) * self.cam_zoom
        sy = (self.stylus_y - self.cam_y) * self.cam_zoom
        c = self.theme["stylus"]
        painter.setPen(QPen(QColor(c.red(), c.green(), c.blue(), 180), 1))
        painter.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), 220)))
        poly = QPolygonF([
            QPointF(sx, sy),
            QPointF(sx + 5.0, sy + 9.0),
            QPointF(sx + 2.0, sy + 9.0)
        ])
        painter.drawPolygon(poly)

    def _render_mascot(self, painter: QPainter):
        mx, my = self.mascot_x, self.mascot_y
        bob = math.sin(time.time() * 3.5) * 4.0
        th = self.theme

        painter.setPen(QPen(th["mascot_border"], 1.5))
        painter.setBrush(QBrush(th["mascot_pod"]))
        painter.drawRoundedRect(QRectF(mx - 18, my - 18 + bob, 36, 36), 12, 12)

        eye_open = abs(math.cos(self.mascot_eye_blink)) > 0.12
        painter.setBrush(QBrush(th["mascot_eye"]))
        painter.setPen(Qt.NoPen)
        if eye_open:
            painter.drawEllipse(QPointF(mx - 6, my - 2 + bob), 2.5, 3.5)
            painter.drawEllipse(QPointF(mx + 6, my - 2 + bob), 2.5, 3.5)
        else:
            painter.setPen(QPen(th["mascot_eye"], 1.5))
            painter.drawLine(int(mx - 8), int(my - 2 + bob), int(mx - 4), int(my - 2 + bob))
            painter.drawLine(int(mx + 4), int(my - 2 + bob), int(mx + 8), int(my - 2 + bob))

        if self.mascot_mood == "TEACHING":
            sx = (self.stylus_x - self.cam_x) * self.cam_zoom
            sy = (self.stylus_y - self.cam_y) * self.cam_zoom
            painter.setPen(QPen(th["mascot_eye"], 1, Qt.DashLine))
            painter.drawLine(int(mx), int(my + bob), int(sx), int(sy))

    def _render_hud(self, painter: QPainter):
        task_label = f"Goal: \"{self.current_user_task}\"" if self.current_user_task else "Goal: Auto-Scanning"
        nav_str = "[ALT+DRAG to Pan/Zoom] [Ctrl+S Export] [PgUp/PgDn Jump]" if not self.user_navigating else "[PANNING ACTIVE]"
        voice_tag = " [Voice Mic/TTS Sync]" if (HAS_PYTTSX3 and VOICE_ENABLED) else ""
        hud_text = f" AI TUTOR [{self.theme['badge_tag']}]  |  {task_label}  |  {nav_str}{voice_tag}  |  Core: {self.ai_status} "

        font = QFont("Consolas", 9, QFont.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(hud_text)
        h_val = fm.height()

        painter.setBrush(QBrush(QColor(10, 15, 30, 220)))
        painter.setPen(QPen(self.theme["hub_border"], 1.2))
        painter.drawRoundedRect(QRectF(16, self.h - h_val - 20, tw + 20, h_val + 8), 6, 6)

        painter.setPen(QColor(241, 245, 249, 235))
        painter.drawText(26, self.h - 16, hud_text)


# Compatibility Aliases
AITeachingOverlay = SketchnoteTutorOverlay
AutonomousTutorOverlay = SketchnoteTutorOverlay


# =====================================================================
# TERMINAL INPUT LOOP
# =====================================================================
def terminal_input_loop(overlay: SketchnoteTutorOverlay):
    time.sleep(1.0)
    print("\n" + "=" * 65)
    print("INTERACTIVE SKETCHNOTE TUTOR CONSOLE (Architecture v4)")
    print("Type any prompt, goal, or question and press Enter:")
    print("  * 'comment about Kolkata sweets'        -> Romantic Wingman Sketchnote")
    print("  * 'derive pythagorean theorem'          -> Mathematical Derivation Ladder")
    print("  * 'free body diagram of sliding block'  -> Physics Force Vectors & Axes")
    print("Or speak naturally into your microphone (Hands-Free STT active).")
    print("Shortcuts:")
    print("  * Hold ALT + Drag to Pan | ALT + Scroll to Zoom")
    print("  * Ctrl + S: Export Whiteboard to High-Resolution PNG")
    print("  * PageUp / PageDown: Jump between Past Whiteboards")
    print("=" * 65 + "\n")

    while True:
        try:
            goal = input("Enter teaching goal > ").strip()
            if goal:
                overlay.set_user_task(goal)
        except (EOFError, KeyboardInterrupt):
            break


# =====================================================================
# MAIN BOOTSTRAPPER
# =====================================================================
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps)

    print("=" * 65)
    print(" AI TEACHING ASSISTANT - ORGANIC SKETCHNOTE TUTOR v4 ")
    print("=" * 65)
    print(f"Target Vision Model     : {MODEL_DISPLAY_NAME}")
    print(f"Active Theme            : {auto_detect_theme(INITIAL_TASK).upper()}")
    print("Canvas Mode             : Organic Sketchnote (Petals, Derivations, Vectors)")
    print("Mouse Navigation        : Hold ALT + Drag to Pan | Scroll to Zoom")
    print("Note Center Export      : Press Ctrl + S to save PNG snapshot")
    print("Whiteboard Jump         : PageUp / PageDown to traverse lesson clusters")
    print(f"Voice Synthesis (TTS)   : {'ENABLED (Clause Lockstep)' if (HAS_PYTTSX3 and VOICE_ENABLED) else 'DISABLED'}")
    print(f"Hands-Free Voice (STT)  : {'ENABLED (SpeechRecognition)' if (HAS_STT and LISTEN_ENABLED) else 'DISABLED'}")
    print(f"OS Media Auto-Pause     : {'ENABLED (--pause-media)' if AUTO_PAUSE_MEDIA else 'DISABLED'}")
    print("Multi-Zone Layout       : ACTIVE (SpatialScreenSegmenter)")
    print("Press Ctrl+C in terminal to exit.")
    print("=" * 65)

    overlay = SketchnoteTutorOverlay(initial_task=INITIAL_TASK)
    threading.Thread(target=terminal_input_loop, args=(overlay,), daemon=True).start()

    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sig_timer = QTimer()
    sig_timer.timeout.connect(lambda: None)
    sig_timer.start(500)

    sys.exit(app.exec_())
