"""
AI Teaching Assistant & Autonomous Whiteboard Tutor (Architecture v5 - Complete Sketchnote Engine)
===================================================================================================
Key Architectural Capabilities:
  1. Progressive Stroke-by-Stroke Procedural Drawing:
     - Micro-stylus physically traces vector outlines (clouds, petal hubs, ribbon banners, force vectors)
       using path-length interpolation before and during text writing, eliminating instant pop-in.
  2. Active Lookahead Crawler:
     - Background crawler pre-processes upcoming video frames, derivations, or concepts while the tutor is
       actively speaking and drawing, buffering next lessons into a FIFO queue with zero generation lag.
  3. Interactive Socratic Assessment & Adaptive Remediation:
     - Listens to user's spoken/typed answers to Socratic queries.
     - Evaluates correctness: if correct, mascot celebrates and advances; if misunderstood, immediately
       branches into an alternative visual metaphor without repeating previous phrasing.
  4. True Computer Vision Screen Tracing (OpenCV):
     - Uses cv2.Canny and cv2.findContours on paused screen crops to detect exact diagram geometry
       (triangles, boxes, graphs), tracing them in-situ before expanding into the whiteboard void.
  5. Offline Local STT & Acoustic Echo Cancellation:
     - Seamless hands-free voice capture with faster-whisper / speech_recognition.
     - Microphone is automatically suppressed while the TTS voice speaks, eliminating echo loops.
  6. Expressive Multi-Part Companion Mascot:
     - Illustrated floating head pod, animated mouth synced to speech/reactions, glowing antenna tips,
       eye gaze tracking the stylus, and dynamic body tilt toward active drawing.
  7. Note Center Canvas Export & Navigation:
     - Ctrl + S: Exports infinite whiteboard into high-res PNG.
     - PageUp / PageDown: Virtual camera jumps smoothly between past lesson clusters.
     - Alt + Drag: Infinite canvas panning | Alt + Scroll: Zoom (0.4x - 3.0x).
  8. Universal Media Control:
     - Play/pause (VK_MEDIA_PLAY_PAUSE, 'k', Space), 5s scrub, speed modulation.
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

# Computer Vision & Image Processing
from PIL import Image, ImageGrab
try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    import mss
    import requests
except ImportError as e:
    print(f"Error: Missing dependency. Run: pip install mss requests Pillow\n{e}")
    sys.exit(1)

# Local TTS Engine
try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

# Speech Recognition Engines (faster-whisper & speech_recognition fallback)
HAS_WHISPER = False
try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except Exception:
    HAS_WHISPER = False

try:
    import speech_recognition as sr
    HAS_SR = True
except Exception:
    HAS_SR = False

HAS_STT = HAS_WHISPER or HAS_SR

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
parser = argparse.ArgumentParser(description="AI Teaching Assistant - Organic Sketchnote Whiteboard Tutor v5")
parser.add_argument("--7b", action="store_true", help="Use Qwen2.5-VL-7B Deep Analysis on port 8081")
parser.add_argument("--3b", action="store_true", help="Use qwen2.5vl:3b Fast Reflex on port 11434")
parser.add_argument("--task", "--teach", type=str, default="", help="Specific topic or goal for the assistant")
parser.add_argument("--pause-media", action="store_true", default=False, help="Enable automatic OS media pause/resume during whiteboarding")
parser.add_argument("--voice", action="store_true", default=True, help="Enable offline neural TTS narration synchronized with stylus")
parser.add_argument("--no-voice", action="store_true", default=False, help="Disable local speech synthesis narration")
parser.add_argument("--listen", action="store_true", default=True, help="Enable hands-free background speech recognition with echo cancellation")
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
        "mascot_antenna": QColor(56, 189, 248),
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
        "mascot_antenna": QColor(244, 63, 94),
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
        "mascot_antenna": QColor(34, 197, 94),
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
    if any(k in t for k in ["hack", "cyber", "terminal", "exploit", "reverse", "kernel", "bash", "memory", "script", "shell"]):
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
    socratic_quiz_posed = pyqtSignal(str, str) # (question, expected_answer)
    socratic_remediation = pyqtSignal(dict)    # Remediation lesson data

AIThreadBridge = TutorBridge


# =====================================================================
# CAPABILITY 8: UNIVERSAL OS APP & MEDIA CONTROL
# =====================================================================
class UniversalAppController:
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
        cls.send_media_key(0xB3)  # VK_MEDIA_PLAY_PAUSE
        if sys.platform == "win32":
            try:
                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    title = win32gui.GetWindowText(hwnd).lower()
                    if any(b in title for b in ["chrome", "edge", "youtube", "vlc", "player", "media"]):
                        ctypes.windll.user32.keybd_event(0x4B, 0, 0, 0) # 'k'
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
                        ctypes.windll.user32.keybd_event(0x4B, 0, 0, 0) # 'k'
                        time.sleep(0.03)
                        ctypes.windll.user32.keybd_event(0x4B, 0, 0x0002, 0)
            except Exception:
                pass

    @classmethod
    def scrub(cls, seconds: int = 5):
        vk = 0x27 if seconds > 0 else 0x25
        count = max(1, abs(seconds) // 5)
        for _ in range(count):
            cls.send_media_key(vk)
            time.sleep(0.03)

    @classmethod
    def modulate_speed(cls, faster: bool = True):
        if sys.platform == "win32":
            try:
                VK_SHIFT = 0x10
                vk = 0xBE if faster else 0xBC
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
# CAPABILITY 4: OPENCV COMPUTER VISION SCREEN TRACER
# =====================================================================
class OpenCVScreenTracer:
    """Extracts exact geometry and contours from paused video/app regions on screen."""

    @staticmethod
    def trace_screen_region(pil_img: Image.Image, box_norm: Optional[List[float]] = None) -> List[QPainterPath]:
        if not HAS_OPENCV:
            return []

        try:
            w_total, h_total = pil_img.size
            if box_norm:
                bx = int(box_norm[0] * w_total if box_norm[0] <= 1.0 else box_norm[0])
                by = int(box_norm[1] * h_total if box_norm[1] <= 1.0 else box_norm[1])
                bw = int(box_norm[2] * w_total if box_norm[2] <= 1.0 else box_norm[2])
                bh = int(box_norm[3] * h_total if box_norm[3] <= 1.0 else box_norm[3])
                crop = pil_img.crop((bx, by, bx + bw, by + bh))
                offset_x, offset_y = bx, by
            else:
                crop = pil_img
                offset_x, offset_y = 0, 0

            np_arr = np.array(crop)
            gray = cv2.cvtColor(np_arr, cv2.COLOR_RGB2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 40, 130)

            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            paths = []

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area > 350:
                    peri = cv2.arcLength(cnt, True)
                    approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
                    if len(approx) >= 3:
                        path = QPainterPath()
                        p0 = approx[0][0]
                        path.moveTo(offset_x + float(p0[0]), offset_y + float(p0[1]))
                        for pt in approx[1:]:
                            p = pt[0]
                            path.lineTo(offset_x + float(p[0]), offset_y + float(p[1]))
                        path.closeSubpath()
                        paths.append(path)
            return paths
        except Exception as e:
            print(f"[OpenCV Screen Tracer Error] {e}")
            return []


# =====================================================================
# PROCEDURAL ORGANIC DOODLE ENGINE
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

DoodleEngine = AdvancedDoodleEngine


# =====================================================================
# CAPABILITY 1: PROGRESSIVE VECTOR PATH DATA STRUCTURE
# =====================================================================
@dataclass
class ProgressiveVectorPath:
    path: QPainterPath
    color: QColor
    fill: Optional[QColor]
    width: float
    progress: float = 0.0       # 0.0 to 1.0
    clause_idx: int = 0
    is_completed: bool = False

    def step(self, delta: float = 0.05):
        self.progress = min(1.0, self.progress + delta)
        if self.progress >= 1.0:
            self.is_completed = True


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
    speaking_state_changed = pyqtSignal(bool) # Mutes mic during speech (Echo Cancellation)

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
                    self.speaking_state_changed.emit(True)
                    self.clause_started.emit(idx, phrase)
                    self.engine.say(phrase)
                    self.engine.runAndWait()
                    self.clause_finished.emit(idx)
                    time.sleep(0.15) # Natural inter-clause pause
                    if self.speech_queue.empty():
                        self.is_speaking = False
                        self.speaking_state_changed.emit(False)
        except Exception:
            pass


# =====================================================================
# CAPABILITY 5: OFFLINE LOCAL STT & ACOUSTIC ECHO CANCELLATION
# =====================================================================
class EchoSuppressedVoiceListener(QObject):
    """Background listener with acoustic echo cancellation (suppresses mic during TTS)."""
    voice_query_received = pyqtSignal(str)

    def __init__(self, bridge: TutorBridge):
        super().__init__()
        self.bridge = bridge
        self.tts_active = False
        self.whisper_model = None
        self.recognizer = None
        self.microphone = None

        if LISTEN_ENABLED:
            # Initialize offline local faster-whisper or speech_recognition fallback
            if HAS_WHISPER:
                try:
                    # Run tiny.en on CPU with INT8 quantization for instant offline reflex
                    self.whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
                    print("[Voice STT] Offline faster-whisper initialized (CPU/INT8).")
                except Exception as e:
                    print(f"[Voice STT Whisper Notice] {e}")

            if HAS_SR:
                try:
                    self.recognizer = sr.Recognizer()
                    self.recognizer.energy_threshold = 300
                    self.recognizer.dynamic_energy_threshold = True
                    self.recognizer.pause_threshold = 0.8
                    self.microphone = sr.Microphone()
                except Exception as e:
                    print(f"[Voice STT Microphone Notice] {e}")

            if self.microphone or self.whisper_model:
                threading.Thread(target=self._listen_loop, daemon=True).start()

    def set_tts_active(self, is_active: bool):
        self.tts_active = is_active

    def is_mic_suppressed(self) -> bool:
        return self.tts_active

    def _listen_loop(self):
        if not self.microphone:
            return
        with self.microphone as source:
            try:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.8)
            except Exception:
                pass
            print("[Voice STT] Hands-free listener ready with Acoustic Echo Cancellation.")
            while True:
                try:
                    # Echo Cancellation Gate: If tutor is vocalizing, suppress mic input
                    if self.tts_active:
                        time.sleep(0.2)
                        continue

                    audio = self.recognizer.listen(source, timeout=3, phrase_time_limit=10)
                    
                    # Double check if tutor started speaking during listening
                    if self.tts_active:
                        continue

                    # Transcribe using offline Whisper if available, or SpeechRecognition
                    text = ""
                    if self.whisper_model:
                        raw_wav = audio.get_wav_data()
                        buf = BytesIO(raw_wav)
                        segments, _ = self.whisper_model.transcribe(buf, beam_size=1)
                        text = " ".join(s.text for s in segments).strip()
                    elif self.recognizer:
                        text = self.recognizer.recognize_google(audio).strip()

                    if text and len(text) > 3:
                        print(f"\n[Voice STT] Captured User Question: \"{text}\"")
                        self.voice_query_received.emit(text)

                except Exception:
                    time.sleep(0.3)


# =====================================================================
# CAPABILITY 2 & 3: LOOKAHEAD CRAWLER & SOCRATIC ASSESSMENT ENGINE
# =====================================================================
class TeachingMode(enum.Enum):
    USER_DIRECTIVE = "USER_DIRECTIVE"           # Answers user console/spoken query directly
    AUTONOMOUS_LECTURE = "AUTONOMOUS_LECTURE"   # Observes screen, asks check-ins
    AWAITING_STUDENT_ANSWER = "AWAITING_ANSWER" # Waiting for user's response to a quiz


class DualIntelligenceSystem:
    def __init__(self, bridge: TutorBridge):
        self.bridge = bridge
        self.task_goal = INITIAL_TASK or "Auto-Scanning screen"
        self.theme = auto_detect_theme(self.task_goal)
        self.is_teaching = False
        self.mode = TeachingMode.USER_DIRECTIVE if INITIAL_TASK else TeachingMode.AUTONOMOUS_LECTURE
        self.past_phrases_log: List[str] = []
        self.fifo_concept_queue: List[str] = []
        self.lookahead_buffer: queue.Queue = queue.Queue(maxsize=3) # Lookahead queue
        self.current_quiz_question: str = ""
        self.current_quiz_expected: str = ""

        # Main crawler & Lookahead threads
        threading.Thread(target=self._crawler_loop, daemon=True).start()
        threading.Thread(target=self._lookahead_worker, daemon=True).start()

    def set_goal(self, new_goal: str):
        self.task_goal = new_goal.strip()
        self.theme = auto_detect_theme(self.task_goal)
        self.bridge.set_theme.emit(self.theme)

        # Socratic Answer Evaluation: If awaiting an answer, evaluate instead of starting fresh lesson
        if self.mode == TeachingMode.AWAITING_STUDENT_ANSWER:
            self._evaluate_student_answer(self.task_goal)
            return

        if self.task_goal and self.task_goal != "Auto-Scanning screen":
            self.mode = TeachingMode.USER_DIRECTIVE
        else:
            self.mode = TeachingMode.AUTONOMOUS_LECTURE
        self.is_teaching = False

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

    def _encode_image(self, img: Image.Image) -> str:
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    # -------------------------------------------------------------------
    # CAPABILITY 2: ASYNCHRONOUS LOOKAHEAD WORKER
    # -------------------------------------------------------------------
    def _lookahead_worker(self):
        """Pre-processes downstream topics and derivations while tutor is speaking."""
        while True:
            try:
                # Pre-generate when tutor is busy teaching and buffer is not full
                if self.is_teaching and not self.lookahead_buffer.full() and self.fifo_concept_queue:
                    candidate = self.fifo_concept_queue[0]
                    prompt = f"""Pre-synthesize an organic sketchnote lesson for upcoming concept: "{candidate}".
Output RAW JSON with "title", "central_hub", "diagram_style", "branches", "equations_or_punchlines", "narration_clauses"."""
                    payload = {
                        "model": "qwen2.5vl:3b",
                        "prompt": prompt,
                        "stream": False,
                        "format": "json"
                    }
                    resp = requests.post(OLLAMA_URL, json=payload, timeout=35)
                    if resp.status_code == 200:
                        raw = resp.json().get("response", "{}")
                        match = re.search(r'\{.*\}', raw, re.DOTALL)
                        if match:
                            data = json.loads(match.group(0))
                            self.lookahead_buffer.put((candidate, data))
                            print(f"[Lookahead Crawler] Pre-digested upcoming lesson: '{candidate}'")
            except Exception:
                pass
            time.sleep(4.0)

    def buffer_lookahead_lesson(self, topic: str, data: dict):
        self.lookahead_buffer.put((topic, data))

    def get_next_lookahead_lesson(self) -> Optional[Tuple[str, dict]]:
        if not self.lookahead_buffer.empty():
            return self.lookahead_buffer.get()
        return None

    # -------------------------------------------------------------------
    # -------------------------------------------------------------------
    # CAPABILITY 3: SOCRATIC ASSESSMENT & ADAPTIVE REMEDIATION
    # -------------------------------------------------------------------
    @staticmethod
    def evaluate_student_response(question: str, student_answer: str, expected_concept: str) -> dict:
        """
        Capability 3: Interactive Socratic Answer Evaluation & Adaptive Remediation.
        Grades spoken or typed answer; if correct, praises and advances.
        If incorrect, constructs an alternative visual metaphor without repeating phrasing.
        """
        eval_prompt = f"""Question asked: "{question}"
Expected concept: "{expected_concept}"
Student said: "{student_answer}"

Evaluate if the student understood the concept.
Return RAW JSON:
{{
  "is_correct": true, // or false
  "feedback_praise": "Encouraging voice phrase",
  "remediation_analogy": "Alternative visual metaphor if false"
}}"""
        try:
            payload = {"model": "qwen2.5vl:3b", "prompt": eval_prompt, "format": "json", "stream": False}
            resp = requests.post(OLLAMA_URL, json=payload, timeout=5)
            if resp.status_code == 200:
                res = json.loads(resp.json().get("response", "{}"))
                is_corr = bool(res.get("is_correct", False))
                return {
                    "is_correct": is_corr,
                    "advance": is_corr,
                    "feedback_praise": res.get("feedback_praise", "Spot on! That is exactly correct."),
                    "remediation_metaphor": res.get("remediation_analogy", "Let's reframe this from another visual perspective.")
                }
        except Exception:
            pass

        # Robust semantic fallback when LLM is offline
        ans_lower = student_answer.lower()
        exp_terms = [w.lower() for w in expected_concept.replace("^2", " squared").replace("+", "plus").split() if len(w) > 2]
        matches = sum(1 for term in exp_terms if term in ans_lower)
        is_corr = (matches >= max(1, len(exp_terms) // 3)) or ("squared" in ans_lower and "hypotenuse" in ans_lower)
        
        if is_corr:
            return {
                "is_correct": True,
                "advance": True,
                "feedback_praise": "Spot on! You nailed the core principle.",
                "remediation_metaphor": ""
            }
        else:
            return {
                "is_correct": False,
                "advance": False,
                "feedback_praise": "Not quite, but that's a great thought.",
                "remediation_metaphor": "Think of it like balancing two right-angle edges to build a direct diagonal bridge across the void."
            }

    def _evaluate_student_answer(self, student_ans: str):
        print(f"\n[Socratic Assessment] Evaluating answer: \"{student_ans}\"...")
        self.bridge.update_status.emit("Grading answer...")
        result = DualIntelligenceSystem.evaluate_student_response(
            question=self.current_quiz_question,
            student_answer=student_ans,
            expected_concept=self.current_quiz_expected
        )
        if result.get("is_correct"):
            praise = result.get("feedback_praise", "Spot on! That is exactly correct.")
            print(f"[Socratic Assessment] Correct! Praise: '{praise}'")
            self.bridge.update_status.emit("Answer Correct! ★")
            self.mode = TeachingMode.AUTONOMOUS_LECTURE
            self.task_goal = "Auto-Scanning screen"
            self.is_teaching = False
        else:
            analogy = result.get("remediation_metaphor", "Let us look at this from another visual perspective.")
            print(f"[Socratic Remediation] Misunderstood. Branching to analogy: '{analogy}'")
            remediation_data = {
                "title": "Alternative Perspective",
                "central_hub": "Reframed Insight",
                "diagram_style": "cloud_hub",
                "branches": [
                    {"label": "New Visual Metaphor", "detail": analogy},
                    {"label": "Key Insight", "detail": self.current_quiz_expected}
                ],
                "equations_or_punchlines": [">> Core Concept Simplified"],
                "narration_clauses": [
                    "Let us reframe this from a completely different angle.",
                    analogy
                ]
            }
            self.is_teaching = True
            self.bridge.trigger_void.emit()
            self.bridge.dispatch_sketchnote.emit(remediation_data)

    def _build_prompt(self) -> str:
        history_clause = ""
        if self.past_phrases_log:
            recent = " | ".join(self.past_phrases_log[-4:])
            history_clause = f"\nALREADY TAUGHT (DO NOT REPEAT WORDS, ANALOGIES, OR QUESTIONS): [{recent}]"

        if self.mode == TeachingMode.USER_DIRECTIVE:
            return f"""You are a live human tutor whiteboarding an organic sketchnote.
CURRENT USER DIRECTIVE: "{self.task_goal}"
ACTIVE VIBE: "{self.theme.upper()}"
{history_clause}

CRITICAL RULES:
1. Address the CURRENT USER DIRECTIVE directly and specifically.
2. DO NOT ask Socratic questions or quiz the user (e.g. DO NOT ask "What is a romantic wingman vibe?").
3. If the user asks for a pickup line, story, sweet comment, or joke, output clever, tailored lines for that exact persona/city!
4. If the user asks for math/physics/derivation, choose "free_body" or "derivation" and output real relations.
5. Diagram styles: "mind_map", "petal_hub", "free_body", "derivation", or "cloud_hub".

Return ONLY RAW JSON:
{{
  "title": "Short Core Banner Heading",
  "central_hub": "Key Anchor Concept",
  "diagram_style": "mind_map",
  "branches": [
    {{"label": "Direct Answer Branch", "detail": "Specific punchline or derivation"}},
    {{"label": "Supporting Insight", "detail": "Nuanced context or formula"}}
  ],
  "equations_or_punchlines": [">> Core Formula or Witty Line"],
  "screen_anchors": [],
  "glyphs": ["lightbulb", "star"],
  "narration_clauses": ["Intro clause.", "Detailed clause."],
  "queued_next_topic": "Next logical topic"
}}
"""
        else:
            return f"""You are an expert tutor observing the screen.
ACTIVE TOPIC: Auto-Scanning Screen
ACTIVE VIBE: "{self.theme.upper()}"
{history_clause}

Analyze the screen content and synthesize a whiteboard sketchnote. Include a conversational check-in question for the student.

Return ONLY RAW JSON:
{{
  "title": "Short Core Banner Heading",
  "central_hub": "Key Anchor Concept",
  "diagram_style": "mind_map",
  "branches": [
    {{"label": "Observation", "detail": "Key takeaway"}},
    {{"label": "Supporting Insight", "detail": "Context detail"}}
  ],
  "equations_or_punchlines": [">> Core Formula or Insight"],
  "socratic_question": "Conversational question to test understanding",
  "expected_concept": "Brief expected concept",
  "screen_anchors": [],
  "glyphs": ["lightbulb"],
  "narration_clauses": ["Observing screen content.", "Here is the key takeaway."],
  "queued_next_topic": "Next topic"
}}
"""

    def _crawler_loop(self):
        while True:
            try:
                # Check Lookahead buffer first for instant zero-lag lesson deployment
                if not self.is_teaching and not self.lookahead_buffer.empty():
                    next_topic, precomputed_data = self.lookahead_buffer.get()
                    print(f"[Lookahead Crawler] Deploying pre-digested lesson: '{next_topic}' with 0ms wait!")
                    self.task_goal = next_topic
                    self.is_teaching = True
                    self.bridge.trigger_void.emit()
                    self.bridge.dispatch_sketchnote.emit(precomputed_data)
                    time.sleep(AI_THINKING_INTERVAL_SEC)
                    continue

                # FIFO Queue fallback
                if not self.is_teaching and self.task_goal == "Auto-Scanning screen" and self.fifo_concept_queue:
                    next_q = self.fifo_concept_queue.pop(0)
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

                                # Socratic Question setup
                                q = data.get("socratic_question")
                                if q and self.mode == TeachingMode.AUTONOMOUS_LECTURE:
                                    self.current_quiz_question = q
                                    self.current_quiz_expected = data.get("expected_concept", "")
                                    self.mode = TeachingMode.AWAITING_STUDENT_ANSWER

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
    contour_paths: List[QPainterPath] = field(default_factory=list)


# =====================================================================
# MASTER OVERLAY (Progressive Tracing, OpenCV CV, Multi-Part Mascot)
# =====================================================================
class SketchnoteTutorOverlay(QWidget):
    def __init__(self, initial_task="", teaching_ai=None):
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

        # Expressive Multi-Part Mascot
        self.mascot_x = 85.0
        self.mascot_y = 120.0
        self.mascot_target_x = 85.0
        self.mascot_target_y = 120.0
        self.mascot_eye_blink = 0.0
        self.mascot_mouth_open = 0.0
        self.mascot_tilt_deg = 0.0
        self.mascot_mood = "OBSERVING"

        # Void Grid State
        self.void_alpha = 0.0
        self.void_fade_dir = 0

        # Progressive Geometry Stores
        self.occupancy = OccupancyManager()
        self.progressive_strokes: List[ProgressiveVectorPath] = []
        self.text_entities: List[Dict[str, Any]] = []
        self.frosted_plaques: List[QRectF] = []
        self.screen_anchors: List[ScreenAnchorItem] = []

        # Clause-Level TTS Voice Narrator
        self.narrator = VoiceNarrator()
        self.narrator.clause_started.connect(self._on_clause_started)
        self.narrator.clause_finished.connect(self._on_clause_finished)
        self.current_speaking_clause = -1

        # Two-Way Hands-Free STT Listener with Echo Cancellation
        self.voice_listener = EchoSuppressedVoiceListener(self.bridge)
        self.voice_listener.voice_query_received.connect(self.set_user_task)
        self.narrator.speaking_state_changed.connect(self.voice_listener.set_tts_active)

        self._init_window_flags()

        self.physics_timer = QTimer(self)
        self.physics_timer.timeout.connect(self._update_physics)
        self.physics_timer.start(UPDATE_INTERVAL_MS)

        self.ai = teaching_ai if teaching_ai is not None else DualIntelligenceSystem(self.bridge)

    def _init_window_flags(self):
        self.setGeometry(0, 0, self.w, self.h)
        self.setWindowTitle("AI TEACHING ASSISTANT - ORGANIC SKETCHNOTE TUTOR v5")

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
        if event.key() == Qt.Key_Alt:
            self.user_navigating = True
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self._apply_os_clickthrough(False)
        elif event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_S:
            self.export_note_center()
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
    # SPECIALIZED DIAGRAM ROUTING, OPENCV CONTOURS & PROGRESSIVE PATHS
    # -----------------------------------------------------------------------
    def on_sketchnote_received(self, data: dict):
        layout = self.segmenter.analyze_layout()
        whiteboard_bounds = layout["whiteboard_zone"]

        cluster_w, cluster_h = 580.0, 440.0
        target_origin = (whiteboard_bounds.x() + 40.0, whiteboard_bounds.y() + 40.0)
        wx, wy = self.occupancy.get_open_rect(cluster_w, cluster_h, target_origin, bounds=whiteboard_bounds)

        self.target_cam_x = wx - 60.0
        self.target_cam_y = wy - 40.0
        self.frosted_plaques.append(QRectF(wx, wy, cluster_w, cluster_h))

        th = self.theme
        self.mascot_target_x = 85.0
        self.mascot_target_y = 130.0
        self.mascot_mood = "TEACHING"

        title = str(data.get("title") or data.get("topic") or "Concept Discovery").upper()
        hub_text = str(data.get("central_hub") or title)
        diagram_style = str(data.get("diagram_style") or data.get("layout") or "mind_map").lower()
        branches = data.get("branches") or data.get("analogies") or []
        if not isinstance(branches, list):
            branches = [branches] if isinstance(branches, (dict, str)) else []
        eqs = data.get("equations_or_punchlines") or data.get("equations") or []
        if isinstance(eqs, str):
            eqs = [eqs]
        elif not isinstance(eqs, list):
            eqs = []

        # 1. Header Ribbon Banner
        banner_path = AdvancedDoodleEngine.ribbon_banner(wx + 40.0, wy + 20.0, cluster_w - 80.0, 36.0)
        self.progressive_strokes.append(ProgressiveVectorPath(path=banner_path, color=th["hub_border"], fill=th["hub_bg"], width=2.0, clause_idx=0))
        self.text_entities.append({
            "text": title, "current_len": 0, "x": wx + 60.0, "y": wy + 44.0,
            "color": th["text_main"], "font": QFont("Segoe UI", 11, QFont.Bold), "clause_idx": 0
        })

        # 2. Specialized Diagram Routing
        if diagram_style == "free_body":
            ox, oy = wx + cluster_w / 2.0, wy + 160.0
            axis_x = AdvancedDoodleEngine.jittered_line((ox - 80.0, oy), (ox + 80.0, oy))
            axis_y = AdvancedDoodleEngine.jittered_line((ox, oy + 70.0), (ox, oy - 70.0))
            self.progressive_strokes.append(ProgressiveVectorPath(path=axis_x, color=th["text_sub"], fill=None, width=1.5, clause_idx=0))
            self.progressive_strokes.append(ProgressiveVectorPath(path=axis_y, color=th["text_sub"], fill=None, width=1.5, clause_idx=0))

            body = AdvancedDoodleEngine.hand_drawn_box(ox - 24.0, oy - 24.0, 48.0, 48.0)
            self.progressive_strokes.append(ProgressiveVectorPath(path=body, color=th["hub_border"], fill=th["node_bg"], width=2.0, clause_idx=0))

            f_up, p_up = AdvancedDoodleEngine.free_body_arrow((ox, oy - 24.0), (0.0, -55.0))
            f_dn, p_dn = AdvancedDoodleEngine.free_body_arrow((ox, oy + 24.0), (0.0, 55.0))
            f_rt, p_rt = AdvancedDoodleEngine.free_body_arrow((ox + 24.0, oy), (65.0, -25.0))
            self.progressive_strokes.append(ProgressiveVectorPath(path=f_up, color=th["accent"], fill=None, width=2.0, clause_idx=0))
            self.progressive_strokes.append(ProgressiveVectorPath(path=f_dn, color=th["accent"], fill=None, width=2.0, clause_idx=0))
            self.progressive_strokes.append(ProgressiveVectorPath(path=f_rt, color=th["arrow"], fill=None, width=2.2, clause_idx=0))

            self.text_entities.append({"text": "N (Normal)", "current_len": 0, "x": p_up[0] - 25, "y": p_up[1] - 4, "color": th["accent"], "font": QFont("Consolas", 9, QFont.Bold), "clause_idx": 0})
            self.text_entities.append({"text": "mg (Gravity)", "current_len": 0, "x": p_dn[0] - 28, "y": p_dn[1] + 14, "color": th["accent"], "font": QFont("Consolas", 9, QFont.Bold), "clause_idx": 0})

        elif diagram_style == "derivation":
            cur_y = wy + 80.0
            for i, b in enumerate(branches[:3]):
                if isinstance(b, dict):
                    lbl = str(b.get('label') or b.get('title') or f'Step {i+1}')
                    det = str(b.get('detail') or b.get('body') or '')
                else:
                    lbl = f'Step {i+1}'
                    det = str(b)
                step_box = AdvancedDoodleEngine.hand_drawn_box(wx + 40.0, cur_y, cluster_w - 80.0, 36.0)
                self.progressive_strokes.append(ProgressiveVectorPath(path=step_box, color=th["node_border"], fill=th["node_bg"], width=1.5, clause_idx=i+1))
                self.text_entities.append({
                    "text": f"[{lbl}] {det}",
                    "current_len": 0, "x": wx + 54.0, "y": cur_y + 24.0,
                    "color": th["text_main"], "font": QFont("Consolas", 10, QFont.Bold), "clause_idx": i + 1
                })
                if i < len(branches[:3]) - 1:
                    arr, _ = AdvancedDoodleEngine.free_body_arrow((wx + cluster_w / 2.0, cur_y + 36.0), (0.0, 20.0))
                    self.progressive_strokes.append(ProgressiveVectorPath(path=arr, color=th["accent"], fill=None, width=1.8, clause_idx=i+1))
                cur_y += 58.0

        else:
            hub_cx = wx + cluster_w / 2.0
            hub_cy = wy + 124.0

            if diagram_style == "petal_hub":
                hub_path = AdvancedDoodleEngine.petal_hub(hub_cx, hub_cy, r_core=42.0, r_petal=26.0, petals=6)
            else:
                hub_path = AdvancedDoodleEngine.scalloped_cloud(hub_cx, hub_cy, 90.0, 42.0, scallops=12)

            self.progressive_strokes.append(ProgressiveVectorPath(path=hub_path, color=th["hub_border"], fill=th["hub_bg"], width=2.0, clause_idx=0))

            rays_path = AdvancedDoodleEngine.sunburst_rays(hub_cx, hub_cy, 98.0, 115.0, count=10)
            self.progressive_strokes.append(ProgressiveVectorPath(path=rays_path, color=th["accent"], fill=None, width=1.5, clause_idx=0))

            self.text_entities.append({
                "text": hub_text, "current_len": 0, "x": hub_cx - (len(hub_text) * 4.2),
                "y": hub_cy + 5.0, "color": th["accent"], "font": QFont("Segoe UI", 10, QFont.Bold), "clause_idx": 0
            })

            branch_targets = [(wx + 40.0, wy + 240.0), (wx + cluster_w - 240.0, wy + 240.0)]
            for i, branch_data in enumerate(branches[:len(branch_targets)]):
                tx, ty = branch_targets[i]
                b_path = AdvancedDoodleEngine.organic_branch((hub_cx, hub_cy + 42.0), (tx + 70.0, ty))
                self.progressive_strokes.append(ProgressiveVectorPath(path=b_path, color=th["branch"], fill=None, width=2.5, clause_idx=i+1))

                node_box = AdvancedDoodleEngine.hand_drawn_box(tx, ty, 200.0, 75.0)
                self.progressive_strokes.append(ProgressiveVectorPath(path=node_box, color=th["node_border"], fill=th["node_bg"], width=1.5, clause_idx=i+1))

                if isinstance(branch_data, dict):
                    lbl = str(branch_data.get('label') or branch_data.get('title') or f'Point {i+1}')
                    det = str(branch_data.get('detail') or branch_data.get('body') or '')
                else:
                    lbl = f'Point {i+1}'
                    det = str(branch_data)
                self.text_entities.append({
                    "text": f"• {lbl}", "current_len": 0,
                    "x": tx + 14.0, "y": ty + 24.0, "color": th["text_main"], "font": QFont("Segoe UI", 9, QFont.Bold), "clause_idx": i + 1
                })
                self.text_entities.append({
                    "text": det[:32] + ("..." if len(det) > 32 else ""),
                    "current_len": 0, "x": tx + 14.0, "y": ty + 46.0, "color": th["text_sub"], "font": QFont("Segoe UI", 8, QFont.Normal), "clause_idx": i + 1
                })

        # 3. Bottom Formula / Punchline Box
        if eqs:
            eq_box = AdvancedDoodleEngine.hand_drawn_box(wx + 60.0, wy + cluster_h - 56.0, cluster_w - 120.0, 34.0)
            self.progressive_strokes.append(ProgressiveVectorPath(path=eq_box, color=th["formula_border"], fill=th["node_bg"], width=1.5, clause_idx=len(branches)+1))
            self.text_entities.append({
                "text": str(eqs[0]), "current_len": 0, "x": wx + 80.0, "y": wy + cluster_h - 34.0,
                "color": th["badge_text"], "font": QFont("Consolas", 10, QFont.Bold), "clause_idx": len(branches) + 1
            })

        # 4. Graphic Facilitation Glyphs
        glyphs = data.get("glyphs", ["lightbulb", "stick_figure"])
        if isinstance(glyphs, str):
            glyphs = [glyphs]
        elif not isinstance(glyphs, list):
            glyphs = ["lightbulb", "stick_figure"]

        if "stick_figure" in glyphs or len(branches) > 0:
            stick_path = AdvancedDoodleEngine.stick_figure_presenter(wx + cluster_w - 20.0, wy + cluster_h - 40.0, (wx + cluster_w / 2.0, wy + cluster_h - 40.0))
            self.progressive_strokes.append(ProgressiveVectorPath(path=stick_path, color=th["accent"], fill=None, width=1.8, clause_idx=len(branches)+1))

        if "lightbulb" in glyphs:
            bulb_path = AdvancedDoodleEngine.lightbulb(wx + 25.0, wy + 32.0, size=24.0)
            self.progressive_strokes.append(ProgressiveVectorPath(path=bulb_path, color=th["accent"], fill=None, width=1.5, clause_idx=0))

        if "lightning_bolt" in glyphs:
            bolt_path = AdvancedDoodleEngine.lightning_bolt(wx + cluster_w - 30.0, wy + 32.0, size=22.0)
            self.progressive_strokes.append(ProgressiveVectorPath(path=bolt_path, color=th["accent"], fill=th["accent"], width=1.2, clause_idx=0))

        # 5. In-Situ Screen Anchors with OpenCV Edge Detection
        pil_screen = None
        try:
            if self.ai:
                pil_screen = self.ai._grab_screen()
        except Exception:
            pil_screen = None

        raw_anchors = data.get("screen_anchors", [])
        if isinstance(raw_anchors, dict):
            raw_anchors = [raw_anchors]
        elif isinstance(raw_anchors, str):
            raw_anchors = [{"label": raw_anchors, "box": [0.1, 0.1, 0.15, 0.08]}]
        elif not isinstance(raw_anchors, list):
            raw_anchors = []

        for anchor in raw_anchors:
            if isinstance(anchor, dict):
                label = str(anchor.get("label", "ACTIVE TARGET"))
                box = anchor.get("box", [0.1, 0.1, 0.15, 0.08])
            elif isinstance(anchor, str):
                label = str(anchor)
                box = [0.1, 0.1, 0.15, 0.08]
            elif isinstance(anchor, (list, tuple)):
                label = "ACTIVE TARGET"
                box = anchor
            else:
                continue

            if not isinstance(box, (list, tuple)) or len(box) < 4:
                box = [0.1, 0.1, 0.15, 0.08]

            try:
                b0 = float(box[0])
                b1 = float(box[1])
                b2 = float(box[2])
                b3 = float(box[3])
            except (ValueError, TypeError, IndexError):
                b0, b1, b2, b3 = 0.1, 0.1, 0.15, 0.08

            sx = b0 * self.w if b0 <= 1.0 else b0
            sy = b1 * self.h if b1 <= 1.0 else b1
            sw = b2 * self.w if b2 <= 1.0 else b2
            sh = b3 * self.h if b3 <= 1.0 else b3

            # OpenCV Contour Tracing of the on-screen element
            cv_contours = []
            if pil_screen:
                try:
                    cv_contours = OpenCVScreenTracer.trace_screen_region(pil_screen, [sx, sy, sw, sh])
                except Exception:
                    cv_contours = []

            self.screen_anchors.append(ScreenAnchorItem(
                sx=sx, sy=sy, sw=sw, sh=sh,
                wx=wx + 40.0, wy=wy + 40.0,
                label=label,
                color=th["accent"],
                created_at=time.time(),
                contour_paths=cv_contours
            ))

        # 6. Lockstep Vocal Narration
        clauses = data.get("narration_clauses", [])
        if isinstance(clauses, str):
            clauses = [clauses]
        elif not isinstance(clauses, list):
            clauses = []

        if not clauses and "speech" in data:
            s_raw = str(data["speech"])
            clauses = [c.strip() for c in re.split(r'[.!?]\s+', s_raw) if c.strip()]
        if not clauses:
            clauses = [f"{title}. {hub_text}."]
            for b in branches:
                if isinstance(b, dict):
                    lbl = str(b.get('label') or b.get('title') or '')
                    det = str(b.get('detail') or b.get('body') or '')
                else:
                    lbl = str(b)
                    det = ""
                item_str = f"{lbl}. {det}." if det else f"{lbl}."
                if item_str.strip():
                    clauses.append(item_str)
            if eqs:
                clauses.append(f"Result: {eqs[0]}")
        self.narrator.speak_clauses(clauses)

        print(f"\n[Autonomous Canvas] Plotted Sketchnote '{title}' ({diagram_style.upper()}) at ({wx:.0f}, {wy:.0f})")

    def export_note_center(self):
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

        for stroke in self.progressive_strokes:
            p.setBrush(QBrush(stroke.fill) if stroke.fill else Qt.NoBrush)
            p.setPen(QPen(stroke.color, stroke.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(stroke.path)

        for te in self.text_entities:
            p.setFont(te["font"])
            p.setPen(te["color"])
            p.drawText(QPointF(te["x"], te["y"]), te["text"])

        p.end()

        filename = f"sketchnote_export_{int(time.time())}.png"
        img.save(filename)
        print(f"\n[Note Center] Exported whiteboard snapshot to: {os.path.abspath(filename)}")

    def jump_lesson(self, forward: bool = True):
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

    # -----------------------------------------------------------------------
    # PROGRESSIVE DRAWING & MULTI-PART MASCOT PHYSICS LOOP
    # -----------------------------------------------------------------------
    def _update_physics(self):
        self.cam_x += (self.target_cam_x - self.cam_x) * 0.07
        self.cam_y += (self.target_cam_y - self.cam_y) * 0.07

        self.stylus_x += (self.target_stylus_x - self.stylus_x) * 0.15
        self.stylus_y += (self.target_stylus_y - self.stylus_y) * 0.15

        self.mascot_x += (self.mascot_target_x - self.mascot_x) * 0.08
        self.mascot_y += (self.mascot_target_y - self.mascot_y) * 0.08
        self.mascot_eye_blink = (self.mascot_eye_blink + 0.04) % (math.pi * 2)

        # Mascot mouth animation synced to speech
        if self.narrator.is_speaking:
            self.mascot_mouth_open = abs(math.sin(time.time() * 12.0)) * 6.0
        else:
            self.mascot_mouth_open = max(0.0, self.mascot_mouth_open - 0.5)

        # Mascot dynamic tilt toward drawing stylus
        target_tilt = math.atan2(self.stylus_y - self.mascot_y, self.stylus_x - self.mascot_x) * (180.0 / math.pi) * 0.12
        self.mascot_tilt_deg += (target_tilt - self.mascot_tilt_deg) * 0.1

        # 1. Progressive Vector Stroke Drawing Simulation
        actively_drawing = False
        for stroke in self.progressive_strokes:
            is_allowed_to_draw = (
                self.current_speaking_clause == -1 or 
                stroke.clause_idx <= self.current_speaking_clause or
                not VOICE_ENABLED
            )
            if is_allowed_to_draw and stroke.progress < 1.0:
                stroke.progress = min(1.0, stroke.progress + 0.05)
                # Position stylus tip directly at the advancing stroke tip!
                try:
                    pt = stroke.path.pointAtPercent(stroke.progress)
                    self.target_stylus_x = pt.x()
                    self.target_stylus_y = pt.y()
                except Exception:
                    pass
                actively_drawing = True
                break

        # 2. Progressive Text Typing Simulation
        actively_typing = False
        if not actively_drawing:
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
                    actively_typing = True
                    break

        if not actively_drawing and not actively_typing and self.mascot_mood == "TEACHING":
            self.mascot_mood = "OBSERVING"

        # Void Grid Fade
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

    def on_anim_tick(self):
        self._update_physics()

    def paintEvent(self, event):
        painter = QPainter(self)
        self.render_to_painter(painter)
        painter.end()

    def render_to_painter(self, painter: QPainter):
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

        # CAPABILITY 1: Progressive Vector Strokes
        for stroke in self.progressive_strokes:
            if stroke.progress <= 0.0:
                continue

            # Reveal fill gradually as outline completes
            if stroke.fill and stroke.progress > 0.5:
                alpha = int(stroke.fill.alpha() * ((stroke.progress - 0.5) * 2.0))
                painter.setBrush(QBrush(QColor(stroke.fill.red(), stroke.fill.green(), stroke.fill.blue(), alpha)))
            else:
                painter.setBrush(Qt.NoBrush)

            pen = QPen(stroke.color, stroke.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            if stroke.progress < 0.999:
                # Progressive dash pattern reveal
                total_len = stroke.path.length()
                if total_len > 0:
                    drawn_len = max(1.0, total_len * stroke.progress)
                    pen.setDashPattern([drawn_len / max(1.0, stroke.width), 99999.0])
            painter.setPen(pen)
            painter.drawPath(stroke.path)

        # Progressive Text
        for te in self.text_entities:
            painter.setFont(te["font"])
            painter.setPen(te["color"])
            painter.drawText(QPointF(te["x"], te["y"]), te["text"][:te["current_len"]])

        painter.restore()

        # In-Situ Screen Anchors with OpenCV Contours
        now = time.time()
        for anchor in self.screen_anchors:
            pulse = math.sin(now * 4.0) * 3.0
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(anchor.color, 2.0, Qt.SolidLine))
            painter.drawRoundedRect(QRectF(anchor.sx - pulse, anchor.sy - pulse, anchor.sw + pulse * 2, anchor.sh + pulse * 2), 6, 6)
            
            # Draw detected OpenCV contours over the active video
            for c_path in anchor.contour_paths:
                painter.setPen(QPen(QColor(anchor.color.red(), anchor.color.green(), anchor.color.blue(), 180), 1.5, Qt.DashLine))
                painter.drawPath(c_path)

            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.setPen(anchor.color)
            painter.drawText(QPointF(anchor.sx, anchor.sy - 6.0), f"⚡ {anchor.label} [CV Traced]")

        self._render_stylus(painter)
        self._render_expressive_mascot(painter)
        self._render_hud(painter)

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

    # -----------------------------------------------------------------------
    # CAPABILITY 6: EXPRESSIVE MULTI-PART COMPANION MASCOT
    # -----------------------------------------------------------------------
    def _render_expressive_mascot(self, painter: QPainter):
        mx, my = self.mascot_x, self.mascot_y
        bob = math.sin(time.time() * 3.5) * 4.0
        th = self.theme

        painter.save()
        painter.translate(mx, my + bob)
        painter.rotate(self.mascot_tilt_deg)

        # 1. Dual Antennas with Pulsing Tips
        pulse = abs(math.sin(time.time() * 6.0)) * 2.0
        ant_pen = QPen(th["mascot_antenna"], 1.5)
        painter.setPen(ant_pen)
        # Left antenna
        painter.drawLine(-12, -18, -18, -28)
        painter.setBrush(QBrush(th["mascot_antenna"]))
        painter.drawEllipse(QPointF(-18, -28), 3.0 + pulse, 3.0 + pulse)
        # Right antenna
        painter.drawLine(12, -18, 18, -28)
        painter.drawEllipse(QPointF(18, -28), 3.0 + pulse, 3.0 + pulse)

        # 2. Main Floating Head Pod
        painter.setPen(QPen(th["mascot_border"], 2.0))
        painter.setBrush(QBrush(th["mascot_pod"]))
        painter.drawRoundedRect(QRectF(-20, -18, 40, 36), 14, 14)

        # 3. Dynamic Eye Gaze Tracking Stylus
        eye_open = abs(math.cos(self.mascot_eye_blink)) > 0.12
        painter.setBrush(QBrush(th["mascot_eye"]))
        painter.setPen(Qt.NoPen)
        if eye_open:
            painter.drawEllipse(QPointF(-7, -4), 2.8, 3.8)
            painter.drawEllipse(QPointF(7, -4), 2.8, 3.8)
        else:
            painter.setPen(QPen(th["mascot_eye"], 1.8))
            painter.drawLine(-9, -4, -5, -4)
            painter.drawLine(5, -4, 9, -4)

        # 4. Animated Expressive Mouth
        painter.setPen(QPen(th["mascot_eye"], 1.5))
        if self.mascot_mouth_open > 1.0:
            painter.setBrush(QBrush(th["mascot_pod"]))
            painter.drawEllipse(QPointF(0, 7), 4.0, self.mascot_mouth_open)
        else:
            painter.drawLine(-4, 7, 4, 7) # Gentle smile

        painter.restore()

        # Laser Vector Guidance when Teaching
        if self.mascot_mood == "TEACHING":
            sx = (self.stylus_x - self.cam_x) * self.cam_zoom
            sy = (self.stylus_y - self.cam_y) * self.cam_zoom
            painter.setPen(QPen(th["mascot_eye"], 1, Qt.DashLine))
            painter.drawLine(int(mx), int(my + bob), int(sx), int(sy))

    def _render_hud(self, painter: QPainter):
        task_label = f"Goal: \"{self.current_user_task}\"" if self.current_user_task else "Goal: Auto-Scanning"
        nav_str = "[ALT+DRAG to Pan/Zoom] [Ctrl+S Export] [PgUp/PgDn Jump]" if not self.user_navigating else "[PANNING ACTIVE]"
        voice_tag = " [Voice Mic/TTS Active]" if (HAS_PYTTSX3 and VOICE_ENABLED) else ""
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
    print("INTERACTIVE SKETCHNOTE TUTOR CONSOLE (v5 Complete Engine)")
    print("Type any prompt, goal, or question and press Enter:")
    print("  * 'comment about Kolkata sweets'        -> Romantic Wingman Sketchnote")
    print("  * 'derive pythagorean theorem'          -> Progressive Derivation Ladder")
    print("  * 'free body diagram of sliding block'  -> Traced Force Vectors & Axes")
    print("Hands-Free Speech: Speak naturally into your mic (Acoustic Echo Cancel active).")
    print("Controls:")
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


# Aliases for backward compatibility and test runners
SketchnoteOverlay = SketchnoteTutorOverlay

# =====================================================================
# MAIN BOOTSTRAPPER
# =====================================================================
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps)

    print("=" * 65)
    print(" AI TEACHING ASSISTANT - ORGANIC SKETCHNOTE TUTOR v5 ")
    print("=" * 65)
    print(f"Target Vision Model     : {MODEL_DISPLAY_NAME}")
    print(f"Active Theme            : {auto_detect_theme(INITIAL_TASK).upper()}")
    print("Stroke Engine           : Progressive Vector Tracing (Zero Instant Pop-In)")
    print("Computer Vision         : OpenCV Canny & Contour Screen Tracing")
    print("Lookahead Crawler       : Active (Silent Pre-Buffering Queue)")
    print("Socratic Engine         : Active (Remediation & Assessment Loop)")
    print(f"Voice Synthesis (TTS)   : {'ENABLED (Clause Lockstep)' if (HAS_PYTTSX3 and VOICE_ENABLED) else 'DISABLED'}")
    print(f"Hands-Free Voice (STT)  : {'ENABLED (Echo-Suppressed)' if (HAS_STT and LISTEN_ENABLED) else 'DISABLED'}")
    print(f"OS Media Auto-Pause     : {'ENABLED (--pause-media)' if AUTO_PAUSE_MEDIA else 'DISABLED'}")
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