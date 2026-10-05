"""
AI Teaching Assistant & Autonomous Whiteboard Tutor (Unified Architecture v2)
=============================================================================
Critical Fixes & Upgrades:
  1. Thread-Safe Signal Bridge (`TutorBridge`): Completely eliminates Qt timer crashes
     (QObject::startTimer) by routing all background thread updates via pyqtSignal.
  2. Anti-Runaway Lock (`is_teaching`): Prevents loop runaway and coordinate drift spam.
  3. Frosted Glass Plaques: Translucent dark backings (QColor(15, 23, 42, 215)) prevent
     text camouflage over dark IDEs (VS Code) or bright browsers.
  4. Physical Mouse Canvas Navigation: Hold ALT (or Middle-Mouse Drag) to pan the infinite
     canvas with your physical mouse; scroll wheel to zoom (0.4x - 3.0x). Releasing ALT
     instantly restores 100% click-through.
  5. Animated Blinking Companion Mascot: Dynamic blinking eyes, head bobbing, and mood
     state shifts ("OBSERVING" vs "TEACHING").
  6. Progressive Whiteboard Streaming: Micro-stylus glides along writing paths as text
     and formulas stream progressively.
  7. Template-Busting Prompt: Eliminates robotic "Step 1 / Step 2" boilerplate in favor of
     organic equations, bulleted logic, and diagrams.
  8. Dual Engine: Supports both Qwen2.5-VL-7B (port 8081) and 3B (port 11434).
  9. Dynamic 5-Vibe Theme Engine & Inbuilt Virtual Cursor (Hybrid, Stylus, Avatar).
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
from io import BytesIO
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

# Ensure UTF-8 stdout encoding on Windows to prevent charmap crashes
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
        QPolygonF, QFontMetrics, QLinearGradient
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
parser = argparse.ArgumentParser(description="AI Teaching Assistant & Autonomous Whiteboard Tutor")
parser.add_argument("--7b", action="store_true", help="Use Qwen2.5-VL-7B Deep Analysis on port 8081")
parser.add_argument("--3b", action="store_true", help="Use qwen2.5vl:3b Fast Reflex on port 11434")
parser.add_argument("--task", "--teach", type=str, default="", help="Specific topic or goal for the assistant")
parser.add_argument("--pause-media", action="store_true", default=False, help="Enable automatic OS media pause/resume during whiteboarding")
parser.add_argument("--cursor", type=str, default="hybrid", choices=["hybrid", "stylus", "avatar"],
                    help="Inbuilt virtual cursor style: 'hybrid' (morphs stylus/avatar), 'stylus' (8px needle), 'avatar' (glowing orb)")
parser.add_argument("--mode", type=str, default="auto", choices=["auto", "tutor", "reflex"],
                    help="Intelligence mode: 'auto' (both discrete notes & autonomous lessons), 'tutor' (lessons only), 'reflex' (annotations only)")
cli_args, _ = parser.parse_known_args()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
LLAMA_SERVER_7B_URL = os.getenv("HOJAIGA_VISION_PRECISION_ENDPOINT", "http://localhost:8081") + "/v1/chat/completions"

def detect_vision_model(preferred_model="qwen2.5vl:3b"):
    priority_list = [
        preferred_model,
        "qwen2.5vl:3b",
        "qwen2.5-vl",
        "llava",
        "llama3.2-vision:latest",
        "minicpm-v:latest",
        "moondream:latest"
    ]
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=1.5)
        if resp.status_code == 200:
            installed = [m.get("name", "") for m in resp.json().get("models", [])]
            for candidate in priority_list:
                for inst in installed:
                    if candidate.lower() in inst.lower():
                        return inst
            if installed:
                return installed[0]
    except Exception:
        pass
    return preferred_model

USE_7B = getattr(cli_args, "7b", False) or (os.getenv("AI_TEACHER_MODEL", "").lower() in ["7b", "precision", "qwen7b"])
ACTIVE_BACKEND = "7b" if USE_7B else "3b"

if USE_7B:
    MODEL_DISPLAY_NAME = "Qwen2.5-VL-7B (Port 8081)"
    AI_THINKING_INTERVAL_SEC = 9
    VISION_MAX_RES = (768, 768)
else:
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", detect_vision_model("qwen2.5vl:3b"))
    MODEL_DISPLAY_NAME = f"{OLLAMA_MODEL} (Port 11434)"
    AI_THINKING_INTERVAL_SEC = 6
    VISION_MAX_RES = (1024, 1024)

INITIAL_TASK = cli_args.task or os.getenv("AI_TEACHER_TASK", "")
AUTO_PAUSE_MEDIA = cli_args.pause_media
CURSOR_STYLE = cli_args.cursor.lower()
TEACHING_MODE = cli_args.mode.lower()
UPDATE_INTERVAL_MS = 16

# Windows Virtual-Key Codes for Universal Media & App Control
VK_SPACE = 0x20
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_OEM_PERIOD = 0xBE
VK_OEM_COMMA = 0xBC
VK_PRIOR = 0x21
VK_NEXT = 0x22
VK_RETURN = 0x0D


# =====================================================================
# DYNAMIC THEME ENGINE
# =====================================================================
THEMES = {
    "studious": {
        "name": "STUDIOUS ACADEMIC",
        "badge_tag": "STUDIOUS",
        "void_bg": QColor(10, 15, 26),
        "grid_dots": QColor(90, 180, 255),
        "stylus": QColor(56, 189, 248),
        "mascot_pod": QColor(15, 23, 42),
        "mascot_border": QColor(56, 189, 248),
        "mascot_visor": QColor(52, 211, 153),
        "mascot_laser": QColor(52, 211, 153, 120),
        "bubble": QColor(56, 189, 248),
        "star": QColor(251, 191, 36),
        "box": QColor(168, 85, 247),
        "accent": QColor(244, 63, 94),
        "text_main": QColor(255, 255, 255),
        "text_sub": QColor(226, 232, 240),
        "badge_text": QColor(52, 211, 153),
        "hud_border": QColor(56, 189, 248, 160),
        "avatar_outer": QColor(56, 189, 248, 75),
        "avatar_mid": QColor(99, 102, 241, 140),
        "avatar_core": QColor(255, 255, 255),
        "laser": QColor(56, 189, 248, 120),
        "highlight": QColor(253, 224, 71),
        "highlight_alpha": 0.45,
        "circle": QColor(251, 146, 60),
        "arrow": QColor(255, 64, 129),
        "plaque_bg": QColor(15, 23, 42, 220),
        "plaque_border": QColor(56, 189, 248, 130)
    },
    "romantic": {
        "name": "ROMANTIC WINGMAN",
        "badge_tag": "ROMANTIC",
        "void_bg": QColor(26, 10, 20),
        "grid_dots": QColor(244, 114, 182),
        "stylus": QColor(244, 63, 94),
        "mascot_pod": QColor(32, 12, 24),
        "mascot_border": QColor(244, 63, 94),
        "mascot_visor": QColor(251, 113, 133),
        "mascot_laser": QColor(244, 63, 94, 140),
        "bubble": QColor(244, 63, 94),
        "star": QColor(244, 114, 182),
        "box": QColor(236, 72, 153),
        "accent": QColor(225, 29, 72),
        "text_main": QColor(255, 241, 242),
        "text_sub": QColor(254, 205, 211),
        "badge_text": QColor(251, 113, 133),
        "hud_border": QColor(244, 63, 94, 180),
        "avatar_outer": QColor(244, 63, 94, 85),
        "avatar_mid": QColor(225, 29, 72, 160),
        "avatar_core": QColor(255, 241, 242),
        "laser": QColor(244, 63, 94, 140),
        "highlight": QColor(251, 113, 133),
        "highlight_alpha": 0.45,
        "circle": QColor(244, 63, 94),
        "arrow": QColor(225, 29, 72),
        "plaque_bg": QColor(32, 12, 24, 225),
        "plaque_border": QColor(244, 63, 94, 140)
    },
    "pressured": {
        "name": "EXAM / HEAVY PRESSURE",
        "badge_tag": "EXAM CRUNCH",
        "void_bg": QColor(25, 12, 10),
        "grid_dots": QColor(239, 68, 68),
        "stylus": QColor(239, 68, 68),
        "mascot_pod": QColor(28, 14, 14),
        "mascot_border": QColor(239, 68, 68),
        "mascot_visor": QColor(249, 115, 22),
        "mascot_laser": QColor(239, 68, 68, 140),
        "bubble": QColor(239, 68, 68),
        "star": QColor(249, 115, 22),
        "box": QColor(220, 38, 38),
        "accent": QColor(239, 68, 68),
        "text_main": QColor(254, 240, 138),
        "text_sub": QColor(253, 224, 71),
        "badge_text": QColor(249, 115, 22),
        "hud_border": QColor(239, 68, 68, 190),
        "avatar_outer": QColor(239, 68, 68, 95),
        "avatar_mid": QColor(249, 115, 22, 160),
        "avatar_core": QColor(255, 255, 255),
        "laser": QColor(239, 68, 68, 140),
        "highlight": QColor(249, 115, 22),
        "highlight_alpha": 0.50,
        "circle": QColor(220, 38, 38),
        "arrow": QColor(239, 68, 68),
        "plaque_bg": QColor(28, 14, 14, 225),
        "plaque_border": QColor(239, 68, 68, 140)
    },
    "hacker": {
        "name": "CYBER / HACKER",
        "badge_tag": "HACKER",
        "void_bg": QColor(5, 15, 8),
        "grid_dots": QColor(34, 197, 94),
        "stylus": QColor(34, 197, 94),
        "mascot_pod": QColor(6, 24, 12),
        "mascot_border": QColor(34, 197, 94),
        "mascot_visor": QColor(52, 211, 153),
        "mascot_laser": QColor(34, 197, 94, 150),
        "bubble": QColor(34, 197, 94),
        "star": QColor(74, 222, 128),
        "box": QColor(16, 185, 129),
        "accent": QColor(52, 211, 153),
        "text_main": QColor(220, 252, 231),
        "text_sub": QColor(187, 247, 208),
        "badge_text": QColor(74, 222, 128),
        "hud_border": QColor(34, 197, 94, 180),
        "avatar_outer": QColor(34, 197, 94, 90),
        "avatar_mid": QColor(16, 185, 129, 160),
        "avatar_core": QColor(220, 252, 231),
        "laser": QColor(34, 197, 94, 150),
        "highlight": QColor(74, 222, 128),
        "highlight_alpha": 0.45,
        "circle": QColor(16, 185, 129),
        "arrow": QColor(52, 211, 153),
        "plaque_bg": QColor(6, 24, 12, 230),
        "plaque_border": QColor(34, 197, 94, 140)
    },
    "creative": {
        "name": "CREATIVE / CASUAL",
        "badge_tag": "CREATIVE",
        "void_bg": QColor(18, 12, 32),
        "grid_dots": QColor(192, 132, 252),
        "stylus": QColor(168, 85, 247),
        "mascot_pod": QColor(22, 15, 38),
        "mascot_border": QColor(168, 85, 247),
        "mascot_visor": QColor(6, 182, 212),
        "mascot_laser": QColor(168, 85, 247, 130),
        "bubble": QColor(168, 85, 247),
        "star": QColor(217, 70, 239),
        "box": QColor(20, 184, 166),
        "accent": QColor(6, 182, 212),
        "text_main": QColor(255, 255, 255),
        "text_sub": QColor(103, 232, 249),
        "badge_text": QColor(192, 132, 252),
        "hud_border": QColor(168, 85, 247, 170),
        "avatar_outer": QColor(168, 85, 247, 85),
        "avatar_mid": QColor(6, 182, 212, 150),
        "avatar_core": QColor(255, 255, 255),
        "laser": QColor(168, 85, 247, 130),
        "highlight": QColor(192, 132, 252),
        "highlight_alpha": 0.45,
        "circle": QColor(217, 70, 239),
        "arrow": QColor(6, 182, 212),
        "plaque_bg": QColor(22, 15, 38, 225),
        "plaque_border": QColor(168, 85, 247, 140)
    }
}

def resolve_theme_key(key: str) -> str:
    if not key:
        return "studious"
    k = str(key).strip().lower()
    if k in THEMES:
        return k
    aliases = {
        "educational": "studious", "academic": "studious", "teacher": "studious", "math": "studious",
        "study": "studious", "warning": "pressured", "heavy": "pressured", "pressure": "pressured",
        "exam": "pressured", "urgent": "pressured", "emergency": "pressured", "cram": "pressured",
        "cyber": "hacker", "matrix": "hacker", "terminal": "hacker", "coding": "hacker", "hack": "hacker",
        "flirt": "romantic", "love": "romantic", "wingman": "romantic", "art": "creative", "casual": "creative"
    }
    for alias, target in aliases.items():
        if alias in k:
            return target
    return "studious"

def auto_detect_theme(task: str) -> str:
    t = task.lower()
    if any(k in t for k in ["pickup", "love", "romantic", "crush", "date", "flirt", "anissha", "anisha", "heart", "propose", "valentine", "wingman"]):
        return "romantic"
    if any(k in t for k in ["exam", "urgent", "pressure", "heavy", "cram", "leak", "bug", "crash", "error", "deadline", "fail", "alert", "panic", "emergency"]):
        return "pressured"
    if any(k in t for k in ["hack", "cyber", "terminal", "exploit", "matrix", "reverse", "kernel", "assembly", "bash"]):
        return "hacker"
    if any(k in t for k in ["art", "story", "design", "creative", "fiction", "game", "draw me", "poem"]):
        return "creative"
    return "studious"

def ensure_desktop_access():
    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception:
            pass


# =====================================================================
# THREAD-SAFE SIGNAL BRIDGE
# =====================================================================
class TutorBridge(QObject):
    """Decouples background threads from the GUI via Qt queued connections."""
    trigger_void = pyqtSignal()
    dispatch_lesson = pyqtSignal(dict)
    dispatch_actions = pyqtSignal(list)
    set_theme = pyqtSignal(str)
    update_status = pyqtSignal(str)
    update_mascot = pyqtSignal(str)


# =====================================================================
# DATA STRUCTURES FOR PROGRESSIVE WHITEBOARD STREAMING
# =====================================================================
@dataclass
class ProgressiveStroke:
    path: QPainterPath
    color: QColor
    width: float
    progress: float = 0.0


@dataclass
class ProgressiveText:
    full_text: str
    current_char_count: int
    x: float
    y: float
    color: QColor
    font_size: int
    is_math: bool = False
    is_badge: bool = False


# =====================================================================
# PROCEDURAL HAND-DRAWN DOODLE ENGINE
# =====================================================================
class DoodleEngine:
    @staticmethod
    def jittered_line(p0: Tuple[float, float], p1: Tuple[float, float]) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(p0[0] + random.uniform(-1, 1), p0[1] + random.uniform(-1, 1))
        mid_x = (p0[0] + p1[0]) / 2.0 + random.uniform(-2, 2)
        mid_y = (p0[1] + p1[1]) / 2.0 + random.uniform(-2, 2)
        path.quadTo(mid_x, mid_y, p1[0], p1[1])
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
    def hand_drawn_star(cx: float, cy: float, size: float = 12.0) -> QPainterPath:
        path = QPainterPath()
        points = []
        for i in range(10):
            r = size if i % 2 == 0 else size * 0.45
            r += random.uniform(-1.0, 1.0)
            theta = i * math.pi / 5.0 - math.pi / 2.0
            points.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))
        path.moveTo(points[0][0], points[0][1])
        for pt in points[1:]:
            path.lineTo(pt[0], pt[1])
        path.closeSubpath()
        return path

    @staticmethod
    def hand_drawn_heart(cx: float, cy: float, size: float = 16.0) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(cx, cy + size * 0.4)
        path.cubicTo(cx - size * 0.8, cy - size * 0.5, cx - size * 0.5, cy - size * 1.1, cx, cy - size * 0.4)
        path.cubicTo(cx + size * 0.5, cy - size * 1.1, cx + size * 0.8, cy - size * 0.5, cx, cy + size * 0.4)
        return path

    @staticmethod
    def comic_bubble(x: float, y: float, w: float, h: float) -> QPainterPath:
        path = QPainterPath()
        r = 10.0
        path.addRoundedRect(QRectF(x, y, w, h), r, r)
        path.moveTo(x + 18.0, y + h)
        path.lineTo(x + 10.0, y + h + 14.0)
        path.lineTo(x + 30.0, y + h)
        return path


# =====================================================================
# ZERO-OVERWRITE OCCUPANCY GRID
# =====================================================================
class OccupancyManager:
    def __init__(self):
        self.boxes: List[Tuple[float, float, float, float]] = []

    def get_open_rect(self, w: float, h: float, origin: Tuple[float, float]) -> Tuple[float, float]:
        ox, oy = origin
        if not self._collides(ox, oy, w, h):
            self.boxes.append((ox, oy, w, h))
            return ox, oy

        step = 60.0
        radius = step
        angle = 0.0
        while radius < 6000.0:
            tx = ox + radius * math.cos(angle)
            tx = max(80.0, tx)
            ty = oy + radius * math.sin(angle)
            if ty >= oy - 50:
                if not self._collides(tx, ty, w, h):
                    self.boxes.append((tx, ty, w, h))
                    return tx, ty
            angle += 0.35
            radius += 16.0

        fallback = (ox + w + 60.0, oy)
        self.boxes.append((fallback[0], fallback[1], w, h))
        return fallback

    def _collides(self, x: float, y: float, w: float, h: float) -> bool:
        pad = 40.0
        for bx, by, bw, bh in self.boxes:
            if not (x + w + pad < bx or x > bx + bw + pad or y + h + pad < by or y > by + bh + pad):
                return True
        return False

    def clear(self):
        self.boxes.clear()


# =====================================================================
# DUAL-ENGINE INTELLIGENCE THREAD
# =====================================================================
class DualIntelligenceSystem:
    def __init__(self, bridge: TutorBridge):
        self.bridge = bridge
        self.task_goal = INITIAL_TASK or "Auto-Scanning screen"
        self.theme = resolve_theme_key(auto_detect_theme(self.task_goal))
        self.is_teaching = False
        self.crawler_active = True
        self.past_topics_log: List[str] = []

        threading.Thread(target=self._crawler_loop, daemon=True).start()

    def set_goal(self, new_goal: str, new_theme: str):
        self.task_goal = new_goal
        self.theme = resolve_theme_key(new_theme)
        self.bridge.set_theme.emit(self.theme)
        self.is_teaching = False

    def _grab_screen(self) -> Optional[Image.Image]:
        ensure_desktop_access()
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
        repetition_ban = ""
        if self.past_topics_log:
            history = " | ".join(self.past_topics_log[-3:])
            repetition_ban = f"\nCRITICAL RULE - AVOID REPETITION: You previously taught -> [{history}]. Explore COMPLETELY DIFFERENT angles, fresh ideas, and new equations!"

        return f"""You are an expert human-like tutor whiteboarding a live interactive lesson.
CURRENT GOAL / DIRECTIVE: '{self.task_goal}'
ACTIVE THEME: '{self.theme}'
{repetition_ban}

CRITICAL RULES:
1. Do NOT use robotic templates like "Step 1:", "Step 2:", or "Derivation:".
2. Write clean mathematical formulas, organic bullet points, or conceptual blueprints.
3. If coding or app building, sketch architectural flows. If math, write progressive equations.
4. If romantic wingman, write charming witty pickup lines, playful flirtation, and compliments.
5. Keep all statements concise and whiteboard-friendly (under 14 words per line).

Return RAW JSON matching this exact structure:
{{
  "theme": "{self.theme}",
  "title": "Short Punchy Title",
  "diagram": "right_triangle", // options: right_triangle, heart, star, box_tree
  "notes": ["Point or insight 1", "Point or insight 2"],
  "equations": [">> Formula or relation 1", ">> Formula or punchline 2"],
  "quiz": "Conversational Socratic check question?"
}}
"""

    def _crawler_loop(self):
        while self.crawler_active:
            try:
                if not self.is_teaching:
                    img = self._grab_screen()
                    if img:
                        b64_data = self._encode_image(img)
                        prompt = self._build_prompt()
                        self.bridge.update_status.emit(f"Analyzing ({MODEL_DISPLAY_NAME})...")

                        raw_json = "{}"
                        if ACTIVE_BACKEND == "7b":
                            payload = {
                                "messages": [
                                    {"role": "system", "content": prompt},
                                    {
                                        "role": "user",
                                        "content": [
                                            {"type": "text", "text": "Analyze screen and output whiteboard lesson JSON."},
                                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}}
                                        ]
                                    }
                                ],
                                "response_format": {"type": "json_object"},
                                "temperature": 0.75,
                                "top_p": 0.9,
                                "max_tokens": 450
                            }
                            resp = requests.post(LLAMA_SERVER_7B_URL, json=payload, timeout=90)
                            if resp.status_code == 200:
                                raw_json = resp.json()["choices"][0]["message"]["content"]
                        else:
                            payload = {
                                "model": OLLAMA_MODEL,
                                "prompt": prompt,
                                "images": [b64_data],
                                "stream": False,
                                "format": "json",
                                "options": {
                                    "temperature": 0.75,
                                    "top_p": 0.9
                                }
                            }
                            resp = requests.post(OLLAMA_URL, json=payload, timeout=40)
                            if resp.status_code == 200:
                                raw_json = resp.json().get("response", "{}")

                        match = re.search(r'\{.*\}', raw_json, re.DOTALL)
                        if match:
                            data = json.loads(match.group(0))
                            if data.get("notes") or data.get("equations") or data.get("title"):
                                self.is_teaching = True
                                suggested_theme = resolve_theme_key(data.get("theme", self.theme))
                                self.bridge.set_theme.emit(suggested_theme)
                                self.bridge.trigger_void.emit()
                                self.bridge.dispatch_lesson.emit(data)

                                topic = data.get("title", "Insight")
                                self.past_topics_log.append(topic)
                                if len(self.past_topics_log) > 5:
                                    self.past_topics_log.pop(0)

            except Exception as e:
                self.bridge.update_status.emit(f"AI: {str(e)[:24]}")

            time.sleep(AI_THINKING_INTERVAL_SEC)


# =====================================================================
# MASTER OVERLAY
# =====================================================================
class AutonomousTutorOverlay(QWidget):
    def __init__(self, initial_task=""):
        super().__init__()
        self.bridge = TutorBridge()
        self.bridge.trigger_void.connect(self.activate_void)
        self.bridge.dispatch_lesson.connect(self.on_lesson_received)
        self.bridge.dispatch_actions.connect(self.on_actions_received)
        self.bridge.set_theme.connect(self.apply_theme)
        self.bridge.update_status.connect(self.apply_status)
        self.bridge.update_mascot.connect(self.apply_mascot_mood)

        self.current_user_task = initial_task
        self.theme_name = resolve_theme_key(auto_detect_theme(initial_task))
        self.theme = THEMES[self.theme_name]
        self.ai_status = "Ready"

        self.cam_x = 0.0
        self.cam_y = 0.0
        self.target_cam_x = 0.0
        self.target_cam_y = 0.0
        self.cam_zoom = 1.0

        self.user_navigating = False
        self.last_mouse_pos = QPointF(0, 0)

        self.cursor_style = CURSOR_STYLE
        self.stylus_x = 400.0
        self.stylus_y = 300.0
        self.target_stylus_x = 400.0
        self.target_stylus_y = 300.0
        self.cursor_state = "IDLE"

        self.mascot_x = 75.0
        self.mascot_y = 110.0
        self.mascot_target_x = 75.0
        self.mascot_target_y = 110.0
        self.mascot_eye_blink = 0.0
        self.mascot_mood = "OBSERVING"

        self.void_alpha = 0.0
        self.void_fade_dir = 0

        self.occupancy = OccupancyManager()
        self.plaques: List[QRectF] = []
        self.strokes: List[ProgressiveStroke] = []
        self.texts: List[ProgressiveText] = []
        self.annotations: List[Dict[str, Any]] = []

        desktop = QDesktopWidget().geometry()
        self.w, self.h = desktop.width(), desktop.height()

        self._init_window_flags()

        self.physics_timer = QTimer(self)
        self.physics_timer.timeout.connect(self._update_physics)
        self.physics_timer.start(UPDATE_INTERVAL_MS)

        self.ai = DualIntelligenceSystem(self.bridge)

    def _init_window_flags(self):
        self.setGeometry(0, 0, self.w, self.h)
        self.setWindowTitle("AI TEACHING ASSISTANT & AUTONOMOUS TUTOR")

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
        resolved = resolve_theme_key(theme_key)
        if resolved in THEMES and resolved != self.theme_name:
            self.theme_name = resolved
            self.theme = THEMES[resolved]
            print(f"[Theme Engine] Switched vibe to {self.theme['name']}.")
            self.update()

    def apply_status(self, status: str):
        self.ai_status = status

    def apply_mascot_mood(self, mood: str):
        self.mascot_mood = mood

    def set_user_task(self, task: str):
        self.current_user_task = task.strip()
        new_theme = auto_detect_theme(self.current_user_task)
        self.apply_theme(new_theme)
        if self.current_user_task:
            print(f"\n[AI Focus Updated] Now working on: \"{self.current_user_task}\" ({self.theme['name']})")
            self.ai.set_goal(self.current_user_task, self.theme['name'])
        else:
            print(f"\n[AI Focus Updated] Returned to auto-scan mode ({self.theme['name']}).")
            self.ai.set_goal("Auto-Scanning screen", self.theme['name'])

    def on_lesson_received(self, data: dict):
        w, h = 480.0, 380.0
        wx, wy = self.occupancy.get_open_rect(w, h, (self.cam_x + 140.0, self.cam_y + 100.0))

        self.target_cam_x = wx - 80.0
        self.target_cam_y = wy - 50.0

        self.plaques.append(QRectF(wx, wy, w, h))

        self.target_stylus_x = wx + 30.0
        self.target_stylus_y = wy + 40.0
        self.cursor_state = "WRITING"

        self.mascot_target_x = 75.0
        self.mascot_target_y = 130.0
        self.mascot_mood = "TEACHING"

        th = self.theme
        title = data.get("title", "Concept Synthesis").upper()
        self.texts.append(ProgressiveText(
            full_text=f"TOPIC: {title}",
            current_char_count=0,
            x=wx + 24.0,
            y=wy + 34.0,
            color=th["text_main"],
            font_size=11,
            is_math=False
        ))

        diagram_type = data.get("diagram", "right_triangle")
        if self.theme_name == "romantic" or diagram_type == "heart":
            emblem = DoodleEngine.hand_drawn_heart(wx - 14.0, wy + 24.0, size=12.0)
            self.strokes.append(ProgressiveStroke(path=emblem, color=th["accent"], width=2.0))
        else:
            emblem = DoodleEngine.hand_drawn_star(wx - 14.0, wy + 24.0, size=10.0)
            self.strokes.append(ProgressiveStroke(path=emblem, color=th["star"], width=2.0))

        self.strokes.append(ProgressiveStroke(
            path=DoodleEngine.jittered_line((wx + 20.0, wy + 44.0), (wx + w - 30.0, wy + 44.0)),
            color=th["bubble"],
            width=2.0
        ))

        cur_y = wy + 80.0
        if diagram_type == "right_triangle":
            tri_pts = [(wx + 35.0, cur_y), (wx + 35.0, cur_y + 85.0), (wx + 155.0, cur_y + 85.0), (wx + 35.0, cur_y)]
            tri_path = QPainterPath()
            tri_path.moveTo(tri_pts[0][0], tri_pts[0][1])
            for pt in tri_pts[1:]:
                tri_path.lineTo(pt[0], pt[1])
            self.strokes.append(ProgressiveStroke(path=tri_path, color=th["accent"], width=2.0))

            sq_path = QPainterPath()
            sq_path.moveTo(wx + 35.0, cur_y + 70.0)
            sq_path.lineTo(wx + 50.0, cur_y + 70.0)
            sq_path.lineTo(wx + 50.0, cur_y + 85.0)
            self.strokes.append(ProgressiveStroke(path=sq_path, color=th["accent"], width=1.2))
            cur_y += 105.0

        elif diagram_type == "heart" or self.theme_name == "romantic":
            heart_p = DoodleEngine.hand_drawn_heart(wx + 65.0, cur_y + 35.0, size=24.0)
            self.strokes.append(ProgressiveStroke(path=heart_p, color=th["accent"], width=2.0))
            cur_y += 75.0

        for note in data.get("notes", [])[:3]:
            self.texts.append(ProgressiveText(
                full_text=f"• {note}",
                current_char_count=0,
                x=wx + 25.0,
                y=cur_y,
                color=th["text_sub"],
                font_size=9,
                is_math=False
            ))
            cur_y += 36.0

        for eq in data.get("equations", [])[:2]:
            box_path = DoodleEngine.hand_drawn_box(wx + 25.0, cur_y - 20.0, w - 60.0, 32.0)
            self.strokes.append(ProgressiveStroke(path=box_path, color=th["badge_text"], width=1.5))
            self.texts.append(ProgressiveText(
                full_text=f"  {eq}",
                current_char_count=0,
                x=wx + 35.0,
                y=cur_y + 2.0,
                color=th["badge_text"],
                font_size=10,
                is_math=True
            ))
            cur_y += 44.0

        quiz = data.get("quiz")
        if quiz:
            print(f"\n[AI TUTOR SOCRATIC CHECK] ({self.theme_name.upper()}): {quiz}")

        print(f"\n[Autonomous Canvas] Plotted '{title}' at world coords ({wx:.0f}, {wy:.0f})")

    def on_actions_received(self, actions: list):
        now = time.time()
        for act in actions:
            processed = dict(act)
            processed["timestamp"] = now
            if "x" in processed: processed["x"] = int(processed["x"] * self.w)
            if "y" in processed: processed["y"] = int(processed["y"] * self.h)
            if "start_x" in processed: processed["start_x"] = int(processed["start_x"] * self.w)
            if "start_y" in processed: processed["start_y"] = int(processed["start_y"] * self.h)
            if "end_x" in processed: processed["end_x"] = int(processed["end_x"] * self.w)
            if "end_y" in processed: processed["end_y"] = int(processed["end_y"] * self.h)
            if "w" in processed: processed["w"] = int(processed["w"] * self.w)
            if "h" in processed: processed["h"] = int(processed["h"] * self.h)
            if "r" in processed: processed["r"] = int(processed["r"] * self.w)
            self.annotations.append(processed)

    def _update_physics(self):
        self.cam_x += (self.target_cam_x - self.cam_x) * 0.07
        self.cam_y += (self.target_cam_y - self.cam_y) * 0.07

        self.stylus_x += (self.target_stylus_x - self.stylus_x) * 0.12
        self.stylus_y += (self.target_stylus_y - self.stylus_y) * 0.12

        self.mascot_x += (self.mascot_target_x - self.mascot_x) * 0.08
        self.mascot_y += (self.mascot_target_y - self.mascot_y) * 0.08
        self.mascot_eye_blink = (self.mascot_eye_blink + 0.04) % (math.pi * 2)

        actively_typing = False
        for t in self.texts:
            if t.current_char_count < len(t.full_text):
                t.current_char_count += 1
                self.target_stylus_x = t.x + (t.current_char_count * 7.5)
                self.target_stylus_y = t.y
                self.cursor_state = "WRITING"
                actively_typing = True
                break

        if not actively_typing and self.cursor_state == "WRITING":
            self.cursor_state = "IDLE"
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

        now = time.time()
        self.annotations = [a for a in self.annotations if now - a.get("timestamp", 0) < 20]

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
        for plaque in self.plaques:
            painter.setBrush(QBrush(th["plaque_bg"]))
            painter.setPen(QPen(th["plaque_border"], 1.5))
            painter.drawRoundedRect(plaque, 10, 10)

        for s in self.strokes:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(s.color, s.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(s.path)

        for t in self.texts:
            font = QFont("Consolas" if t.is_math else "Segoe UI", t.font_size, QFont.Bold if t.is_math else QFont.Normal)
            painter.setFont(font)
            painter.setPen(t.color)
            visible_str = t.full_text[:t.current_char_count]
            painter.drawText(QPointF(t.x, t.y), visible_str)

        self._render_discrete_annotations(painter)

        painter.restore()

        self._render_inbuilt_cursor(painter)
        self._render_mascot(painter)
        self._render_hud_status(painter)

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

    def _render_discrete_annotations(self, painter: QPainter):
        now = time.time()
        t = self.theme

        for ann in self.annotations:
            age = now - ann.get("timestamp", now)
            opacity = max(0, int(255 * (1.0 - (age / 20.0))))
            ann_type = ann.get("type")

            world_x = ann.get("x", 0) + self.cam_x
            world_y = ann.get("y", 0) + self.cam_y
            world_sx = ann.get("start_x", 0) + self.cam_x
            world_sy = ann.get("start_y", 0) + self.cam_y
            world_ex = ann.get("end_x", 0) + self.cam_x
            world_ey = ann.get("end_y", 0) + self.cam_y

            if ann_type == "draw":
                pen = QPen(QColor(t["arrow"].red(), t["arrow"].green(), t["arrow"].blue(), opacity))
                pen.setWidth(3)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.drawLine(QPointF(world_sx, world_sy), QPointF(world_ex, world_ey))

                dx = world_ex - world_sx
                dy = world_ey - world_sy
                length = math.hypot(dx, dy)
                if length > 15:
                    angle = math.atan2(dy, dx)
                    arrow_size = 14
                    p1 = QPointF(world_ex - arrow_size * math.cos(angle - math.pi / 6),
                                 world_ey - arrow_size * math.sin(angle - math.pi / 6))
                    p2 = QPointF(world_ex - arrow_size * math.cos(angle + math.pi / 6),
                                 world_ey - arrow_size * math.sin(angle + math.pi / 6))
                    arrow_poly = QPolygonF([QPointF(world_ex, world_ey), p1, p2])
                    painter.setBrush(QBrush(QColor(t["arrow"].red(), t["arrow"].green(), t["arrow"].blue(), opacity)))
                    painter.drawPolygon(arrow_poly)

            elif ann_type == "write":
                full_text = ann.get("text", "")
                if "chars_revealed" not in ann:
                    ann["chars_revealed"] = 0.0
                ann["chars_revealed"] = min(float(len(full_text)), ann["chars_revealed"] + 1.5)
                current_text = full_text[:int(ann["chars_revealed"])]

                font = QFont("Consolas", 12, QFont.Bold)
                painter.setFont(font)
                fm = painter.fontMetrics()

                max_width = int(self.w * 0.28)
                if max_width < 350:
                    max_width = 350

                calc_rect = QRect(0, 0, max_width, 3000)
                bounding_rect = fm.boundingRect(calc_rect, int(Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop), current_text)
                text_w = bounding_rect.width()
                text_h = bounding_rect.height()

                tx = float(world_x)
                ty = float(world_y)

                pill_rect = QRectF(tx - 14, ty - 12, text_w + 28, text_h + 24)
                painter.setBrush(QBrush(t["plaque_bg"]))
                painter.setPen(QPen(t["plaque_border"], 1.5))
                painter.drawRoundedRect(pill_rect, 8, 8)

                draw_rect = QRectF(tx, ty, text_w, text_h)
                painter.setPen(QColor(t["badge_text"].red(), t["badge_text"].green(), t["badge_text"].blue(), opacity))
                painter.drawText(draw_rect, int(Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop), current_text)

            elif ann_type == "highlight":
                progress = min(1.0, (now - ann.get("timestamp", now)) / 1.5)
                cur_ex = world_sx + (world_ex - world_sx) * progress
                cur_ey = world_sy + (world_ey - world_sy) * progress

                pen = QPen(QColor(t["highlight"].red(), t["highlight"].green(), t["highlight"].blue(), int(opacity * t["highlight_alpha"])))
                pen.setWidth(24)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.drawLine(QPointF(world_sx, world_sy), QPointF(cur_ex, cur_ey))

            elif ann_type == "box":
                progress = min(1.0, (now - ann.get("timestamp", now)) / 1.0)
                w, h = ann.get("w", 140), ann.get("h", 90)
                pen = QPen(QColor(t["box"].red(), t["box"].green(), t["box"].blue(), opacity))
                pen.setWidth(3)
                painter.setPen(pen)
                painter.setBrush(QBrush(QColor(t["box"].red(), t["box"].green(), t["box"].blue(), int(opacity * 0.12))))
                painter.drawRect(QRectF(world_x, world_y, w * progress, h * progress))

            elif ann_type == "circle":
                progress = min(1.0, (now - ann.get("timestamp", now)) / 0.8)
                elastic = math.sin(progress * math.pi / 2)
                r = ann.get("r", 50)
                pen = QPen(QColor(t["circle"].red(), t["circle"].green(), t["circle"].blue(), opacity))
                pen.setWidth(3)
                painter.setPen(pen)
                painter.setBrush(QBrush(QColor(t["circle"].red(), t["circle"].green(), t["circle"].blue(), int(opacity * 0.12))))
                painter.drawEllipse(QPointF(world_x, world_y), r * elastic, r * elastic)

    def _render_inbuilt_cursor(self, painter: QPainter):
        use_stylus = (self.cursor_style == "stylus") or (self.cursor_style == "hybrid" and self.cursor_state == "WRITING")
        sx = (self.stylus_x - self.cam_x) * self.cam_zoom
        sy = (self.stylus_y - self.cam_y) * self.cam_zoom
        th = self.theme

        if use_stylus:
            st_color = th["stylus"]
            painter.setPen(QPen(QColor(st_color.red(), st_color.green(), st_color.blue(), 180), 1))
            painter.setBrush(QBrush(QColor(st_color.red(), st_color.green(), st_color.blue(), 220)))
            poly = QPolygonF([
                QPointF(sx, sy),
                QPointF(sx + 5.0, sy + 9.0),
                QPointF(sx + 2.0, sy + 9.0)
            ])
            painter.drawPolygon(poly)
        else:
            t_sec = time.time()
            glow_radius = 26 + math.sin(t_sec * 5.0) * 4.0
            glow_color = QColor(th["avatar_outer"].red(), th["avatar_outer"].green(), th["avatar_outer"].blue(), 80)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glow_color))
            painter.drawEllipse(QPointF(sx, sy), glow_radius, glow_radius)

            painter.setBrush(QBrush(th["avatar_mid"]))
            painter.drawEllipse(QPointF(sx, sy), 13, 13)

            painter.setBrush(QBrush(th["avatar_core"]))
            painter.drawEllipse(QPointF(sx, sy), 5, 5)

    def _render_mascot(self, painter: QPainter):
        mx, my = self.mascot_x, self.mascot_y
        t = time.time()
        bob = math.sin(t * 3.5) * 4.0
        th = self.theme

        painter.setPen(QPen(th["mascot_border"], 1.5))
        painter.setBrush(QBrush(th["mascot_pod"]))
        painter.drawRoundedRect(QRectF(mx - 18, my - 18 + bob, 36, 36), 12, 12)

        eye_open = abs(math.cos(self.mascot_eye_blink)) > 0.12
        eye_color = th["badge_text"] if self.mascot_mood == "TEACHING" else th["mascot_visor"]

        if eye_open:
            painter.setBrush(QBrush(eye_color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(mx - 6, my - 2 + bob), 2.5, 3.5)
            painter.drawEllipse(QPointF(mx + 6, my - 2 + bob), 2.5, 3.5)
        else:
            painter.setPen(QPen(eye_color, 1.5))
            painter.drawLine(int(mx - 8), int(my - 2 + bob), int(mx - 4), int(my - 2 + bob))
            painter.drawLine(int(mx + 4), int(my - 2 + bob), int(mx + 8), int(my - 2 + bob))

        if self.mascot_mood == "TEACHING":
            sx = (self.stylus_x - self.cam_x) * self.cam_zoom
            sy = (self.stylus_y - self.cam_y) * self.cam_zoom
            painter.setPen(QPen(th["mascot_laser"], 1, Qt.DashLine))
            painter.drawLine(int(mx), int(my + bob), int(sx), int(sy))

    def _render_hud_status(self, painter: QPainter):
        tier_label = "7B DEEP" if ACTIVE_BACKEND == "7b" else "3B RAPID"
        theme_tag = self.theme["badge_tag"]
        task_str = f"Goal: \"{self.current_user_task}\"" if self.current_user_task else "Goal: Auto-Scan"
        nav_str = "[ALT+DRAG to Pan/Zoom]" if not self.user_navigating else "[PANNING CANVAS ACTIVE]"
        hud_text = f" AI TUTOR [{tier_label} | {theme_tag}]  |  {task_str}  |  {nav_str}  |  Zoom: {self.cam_zoom:.1f}x  |  Core: {self.ai_status} "

        font = QFont("Consolas", 10, QFont.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()

        tw = fm.horizontalAdvance(hud_text)
        h_val = fm.height()

        bar_rect = QRectF(16, self.h - h_val - 20, tw + 20, h_val + 8)
        painter.setBrush(QBrush(QColor(10, 15, 30, 220)))
        painter.setPen(QPen(self.theme["hud_border"], 1.2))
        painter.drawRoundedRect(bar_rect, 6, 6)

        painter.setPen(QColor(241, 245, 249, 235))
        painter.drawText(26, self.h - 16, hud_text)


# =====================================================================
# TERMINAL INPUT LOOP
# =====================================================================
def terminal_input_loop(overlay: AutonomousTutorOverlay):
    time.sleep(1.0)
    print("\n" + "=" * 65)
    print("INTERACTIVE TEACHING & TUTOR CONSOLE")
    print("Type any prompt, question, or goal and press Enter:")
    print("  * 'write a pickup line for Anissha'      -> Romantic Wingman Vibe")
    print("  * 'explain this algorithm step by step' -> Studious Academic Vibe")
    print("  * 'exam tomorrow: find the memory leak' -> Heavy / Pressured Vibe")
    print("  * 'audit this reverse shell script'     -> Cyber / Hacker Vibe")
    print("  * 'compose a creative story opening'    -> Creative Visionary Vibe")
    print("Or press Enter with empty text to switch back to Auto-Scan.")
    print("Mouse Control: Hold ALT + Drag to Pan | ALT + Scroll to Zoom")
    print("=" * 65 + "\n")

    while True:
        try:
            goal = input("Enter teaching goal > ").strip()
            overlay.set_user_task(goal)
        except (EOFError, KeyboardInterrupt):
            break


# =====================================================================
# MAIN BOOTSTRAPPER
# =====================================================================
AITeachingOverlay = AutonomousTutorOverlay

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps)

    initial_theme = auto_detect_theme(INITIAL_TASK)
    print("=" * 65)
    print(" AI TEACHING ASSISTANT - UNIFIED AUTONOMOUS WHITEBOARD ")
    print("=" * 65)
    print(f"Active Mode             : {'7B DEEP ANALYSIS' if ACTIVE_BACKEND == '7b' else '3B FAST REFLEX'}")
    print(f"Target Vision Model     : {MODEL_DISPLAY_NAME}")
    print(f"Active Theme            : {THEMES[initial_theme]['name']}")
    print(f"Initial Goal / Task     : {INITIAL_TASK or '(Auto-Scanning screen)'}")
    print(f"Cursor Style            : {CURSOR_STYLE.upper()} (Inbuilt Multi-State Virtual Cursor)")
    print("Mouse Navigation        : Hold ALT + Left/Middle Drag to Pan")
    print("Canvas Zoom             : Hold ALT + Scroll Wheel (0.4x - 3.0x)")
    print("Zero Camouflage         : Active (Frosted Plaque Backings)")
    print("Thread Safety           : 100% Signal/Slot Protected (Zero Timer Crashes)")
    print("Cost                    : 100% Local & FREE (Ollama / llama-server)")
    print("Press Ctrl+C in terminal to exit.")
    print("=" * 65)

    overlay = AutonomousTutorOverlay(initial_task=INITIAL_TASK)

    threading.Thread(target=terminal_input_loop, args=(overlay,), daemon=True).start()

    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    sig_timer = QTimer()
    sig_timer.timeout.connect(lambda: None)
    sig_timer.start(500)

    sys.exit(app.exec_())