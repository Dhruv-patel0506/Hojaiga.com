"""
AI Teaching Assistant & Autonomous Whiteboard Tutor (Architecture v6 - Production Engine)
========================================================================================
Resolved Capabilities:
  1. Infinite Void Conveyor: Horizontal/radial progression without coordinate locking.
  2. Dissolve / Chalk Ghosting: Older cards fade to 20% opacity to prevent overlap clutter.
  3. Dynamic Wrapped Text Boxes: Word-wrapped QRectF calculation avoids label bleeding.
  4. Perceptual dHash Diffing: Stops static screen re-inference thrashing.
  5. Coercive Schema Guard: Robust schema validation preventing LLM dictionary crashes.
  6. GSMTC Media Control: System-level OS media session pause/resume.
  7. Acoustic & Gibberish STT Filter: Blocks mic leakage and phoneme loops.
  8. Academic Blackboard Prompt: Multi-branch, deep university-level lecture synthesis.
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
import asyncio
from io import BytesIO
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

# UTF-8 stdout encoding on Windows
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

# Windows WinRT Media Transport Control
HAS_WINRT = False
if sys.platform == "win32":
    try:
        from winsdk.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as MediaManager
        )
        HAS_WINRT = True
    except ImportError:
        HAS_WINRT = False

# Local TTS Engine
try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

# Speech Recognition Engines
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

# Windows Win32 API
if sys.platform == "win32":
    import ctypes
    try:
        import win32gui
        import win32process
        import win32con
    except ImportError:
        pass


# =====================================================================
# CLI ARGUMENTS & SYSTEM CONFIGURATION
# =====================================================================
parser = argparse.ArgumentParser(description="AI Teaching Assistant - Organic Sketchnote Whiteboard Tutor v6")
parser.add_argument("--7b", action="store_true", help="Use Qwen2.5-VL-7B Deep Analysis on port 8081")
parser.add_argument("--3b", action="store_true", help="Use qwen2.5vl:3b Fast Reflex on port 11434")
parser.add_argument("--task", "--teach", type=str, default="", help="Specific topic or goal for the assistant")
parser.add_argument("--pause-media", action="store_true", default=False, help="Enable automatic OS media pause/resume")
parser.add_argument("--voice", action="store_true", default=True, help="Enable offline TTS narration")
parser.add_argument("--no-voice", action="store_true", default=False, help="Disable speech synthesis")
parser.add_argument("--listen", action="store_true", default=True, help="Enable hands-free background speech recognition")
parser.add_argument("--no-listen", action="store_true", default=False, help="Disable speech recognition")
cli_args, _ = parser.parse_known_args()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
LLAMA_SERVER_7B_URL = os.getenv("HOJAIGA_VISION_PRECISION_ENDPOINT", "http://localhost:8081") + "/v1/chat/completions"

USE_7B = getattr(cli_args, "7b", False) or (os.getenv("AI_TEACHER_MODEL", "").lower() in ["7b", "precision", "qwen7b"])
ACTIVE_BACKEND = "7b" if USE_7B else "3b"

if USE_7B:
    MODEL_DISPLAY_NAME = "Qwen2.5-VL-7B (Port 8081)"
    AI_THINKING_INTERVAL_SEC = 8
    VISION_MAX_RES = (768, 768)
else:
    MODEL_DISPLAY_NAME = "qwen2.5vl:3b (Port 11434)"
    AI_THINKING_INTERVAL_SEC = 5
    VISION_MAX_RES = (1024, 1024)

INITIAL_TASK = cli_args.task or os.getenv("AI_TEACHER_TASK", "")
VOICE_ENABLED = (not cli_args.no_voice) and (cli_args.voice or HAS_PYTTSX3)
LISTEN_ENABLED = (not cli_args.no_listen) and (cli_args.listen or HAS_STT)
AUTO_PAUSE_MEDIA = cli_args.pause_media
UPDATE_INTERVAL_MS = 16


# =====================================================================
# THEME PALETTES
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
        "arrow": QColor(56, 189, 248)
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
        "arrow": QColor(34, 197, 94)
    }
}

def auto_detect_theme(task: str) -> str:
    t = task.lower()
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
# FIX 4: RELIABLE OS MEDIA SESSION CONTROLLER (GSMTC + FALLBACK)
# =====================================================================
class UniversalAppController:
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
    def pause_media(cls):
        if cls._run_winrt_action("pause"):
            return
        # Virtual keycode fallback
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0)
                time.sleep(0.03)
                ctypes.windll.user32.keybd_event(0xB3, 0, 0x0002, 0)
                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    title = win32gui.GetWindowText(hwnd).lower()
                    if any(b in title for b in ["chrome", "edge", "youtube", "vlc", "player"]):
                        ctypes.windll.user32.keybd_event(0x4B, 0, 0, 0)  # 'k'
                        time.sleep(0.02)
                        ctypes.windll.user32.keybd_event(0x4B, 0, 0x0002, 0)
            except Exception:
                pass

    @classmethod
    def resume_media(cls):
        if cls._run_winrt_action("play"):
            return
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0)
                time.sleep(0.03)
                ctypes.windll.user32.keybd_event(0xB3, 0, 0x0002, 0)
            except Exception:
                pass


# =====================================================================
# FIX 2: PERCEPTUAL SCREEN DIFFING (dHash)
# =====================================================================
class PerceptualDiffEngine:
    @staticmethod
    def compute_dhash(image: Image.Image, hash_size: int = 8) -> int:
        """Computes 64-bit difference hash."""
        resized = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
        diff = []
        pixels = list(resized.getdata())
        for row in range(hash_size):
            for col in range(hash_size):
                p_left = pixels[row * (hash_size + 1) + col]
                p_right = pixels[row * (hash_size + 1) + col + 1]
                diff.append(p_left > p_right)
        return sum([1 << i for i, val in enumerate(diff) if val])

    @staticmethod
    def hamming_distance(h1: int, h2: int) -> int:
        return bin(h1 ^ h2).count('1')


# =====================================================================
# FIX 3: SCHEMA NORMALIZATION & COERCION GUARD
# =====================================================================
class SchemaValidator:
    @staticmethod
    def normalize(raw_json: str) -> Optional[dict]:
        try:
            match = re.search(r'\{.*\}', raw_json, re.DOTALL)
            if not match:
                return None
            data = json.loads(match.group(0))

            # Coerce title and hub
            title = str(data.get("title") or "Architectural Derivation").strip()
            central_hub = str(data.get("central_hub") or title).strip()

            # Coerce branches to List[Dict[label, detail]]
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

            # Coerce equations/takeaways
            raw_eqs = data.get("equations_or_punchlines") or data.get("equations") or []
            if isinstance(raw_eqs, str):
                raw_eqs = [raw_eqs]
            elif not isinstance(raw_eqs, list):
                raw_eqs = []
            clean_eqs = [str(e).strip() for e in raw_eqs if str(e).strip()]

            # Coerce narration clauses
            clauses = data.get("narration_clauses") or []
            if isinstance(clauses, str):
                clauses = [clauses]
            clean_clauses = [str(c).strip() for c in clauses if str(c).strip()]

            if not clean_clauses:
                clean_clauses = [f"Analyzing {title}."]
                for b in clean_branches[:2]:
                    clean_clauses.append(f"{b['label']}: {b['detail']}")

            return {
                "title": title,
                "central_hub": central_hub,
                "diagram_style": str(data.get("diagram_style") or "mind_map").lower(),
                "branches": clean_branches[:5],
                "equations_or_punchlines": clean_eqs[:3],
                "narration_clauses": clean_clauses,
                "screen_anchors": data.get("screen_anchors", []),
                "glyphs": data.get("glyphs", ["lightbulb"])
            }
        except Exception as e:
            print(f"[Schema Sanitizer Error] {e}")
            return None


# =====================================================================
# PROCEDURAL DOODLE PRIMITIVES
# =====================================================================
class AdvancedDoodleEngine:
    @staticmethod
    def scalloped_cloud(cx: float, cy: float, rx: float, ry: float, scallops: int = 12) -> QPainterPath:
        path = QPainterPath()
        angle_step = (2 * math.pi) / scallops
        points = []
        for i in range(scallops):
            theta = i * angle_step
            points.append((cx + rx * math.cos(theta), cy + ry * math.sin(theta)))

        path.moveTo(points[0][0], points[0][1])
        for i in range(scallops):
            p_end = points[(i + 1) % scallops]
            mid_angle = (i + 0.5) * angle_step
            path.quadTo(cx + rx * 1.25 * math.cos(mid_angle), cy + ry * 1.25 * math.sin(mid_angle), p_end[0], p_end[1])
        path.closeSubpath()
        return path

    @staticmethod
    def organic_branch(p_start: Tuple[float, float], p_end: Tuple[float, float]) -> QPainterPath:
        path = QPainterPath()
        sx, sy = p_start
        ex, ey = p_end
        dx, dy = ex - sx, ey - sy
        path.moveTo(sx, sy)
        path.cubicTo(sx + dx * 0.5, sy + dy * 0.1, sx + dx * 0.5, sy + dy * 0.9, ex, ey)
        return path

    @staticmethod
    def hand_drawn_box(x: float, y: float, w: float, h: float) -> QPainterPath:
        path = QPainterPath()
        j = 1.8
        path.moveTo(x - j, y + random.uniform(-j, j))
        path.lineTo(x + w + j, y + random.uniform(-j, j))
        path.lineTo(x + w + random.uniform(-j, j), y + h + j)
        path.lineTo(x - j, y + h + random.uniform(-j, j))
        path.closeSubpath()
        return path


# =====================================================================
# DRAWING DATA STRUCTURES WITH DISSOLVE OPACITY
# =====================================================================
@dataclass
class ProgressiveVectorPath:
    path: QPainterPath
    color: QColor
    fill: Optional[QColor]
    width: float
    progress: float = 0.0
    opacity: float = 1.0


@dataclass
class PlaqueCard:
    rect: QRectF
    cluster_id: int
    opacity: float = 1.0


@dataclass
class WrappedTextEntity:
    text: str
    rect: QRectF
    color: QColor
    font: QFont
    opacity: float = 1.0
    revealed_chars: int = 0


# =====================================================================
# INFINITE CONVEYOR OCCUPANCY MANAGER (Zero (740, 100) Clamping)
# =====================================================================
class InfiniteConveyorOccupancy:
    """Arranges lesson clusters sequentially across the infinite coordinate space."""
    def __init__(self):
        self.next_x = 100.0
        self.base_y = 100.0

    def get_next_cluster_origin(self, cluster_w: float) -> Tuple[float, float]:
        ox = self.next_x
        oy = self.base_y
        self.next_x += cluster_w + 140.0
        return ox, oy


# =====================================================================
# CLAUSE-SYNCHRONIZED TTS ENGINE
# =====================================================================
class VoiceNarrator(QObject):
    clause_started = pyqtSignal(int, str)
    clause_finished = pyqtSignal(int)
    speaking_state_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.speech_queue = queue.Queue()
        self.is_speaking = False
        if HAS_PYTTSX3 and VOICE_ENABLED:
            threading.Thread(target=self._worker, daemon=True).start()

    def speak_clauses(self, clauses: List[str]):
        if not (HAS_PYTTSX3 and VOICE_ENABLED):
            return
        for i, clause in enumerate(clauses):
            c = clause.strip()
            if c:
                self.speech_queue.put((i, c))

    def _worker(self):
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', 165)
            engine.setProperty('volume', 0.95)
            while True:
                idx, phrase = self.speech_queue.get()
                self.is_speaking = True
                self.speaking_state_changed.emit(True)
                self.clause_started.emit(idx, phrase)
                engine.say(phrase)
                engine.runAndWait()
                self.clause_finished.emit(idx)
                time.sleep(0.12)
                if self.speech_queue.empty():
                    self.is_speaking = False
                    self.speaking_state_changed.emit(False)
        except Exception:
            pass


# =====================================================================
# FIX 5: ACOUSTIC GATED & GIBBERISH-FILTERED STT LISTENER
# =====================================================================
class EchoSuppressedVoiceListener(QObject):
    voice_query_received = pyqtSignal(str)

    def __init__(self, bridge: TutorBridge):
        super().__init__()
        self.bridge = bridge
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
        """Drops phoneme spam, non-English leaked audio, and repetitive gibberish."""
        if not text or len(text.strip()) < 5:
            return False
        clean = text.strip()
        # Drop excessive consonant or vowel runs
        if re.search(r'[bcdfghjklmnpqrstvwxyz]{6,}', clean, re.IGNORECASE):
            return False
        # Drop repeated character loops (e.g., 'aotadna0oang...')
        if len(set(clean.lower().replace(" ", ""))) < 4:
            return False
        alpha_ratio = sum(c.isalpha() or c.isspace() for c in clean) / len(clean)
        return alpha_ratio > 0.85

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
                        print(f"\n[STT Filter Verified] Spoken Query: \"{text}\"")
                        self.voice_query_received.emit(text)
                except Exception:
                    time.sleep(0.3)


# =====================================================================
# INTELLIGENCE SUBSYSTEM (With dHash Perceptual Diffing)
# =====================================================================
class DualIntelligenceSystem:
    def __init__(self, bridge: TutorBridge):
        self.bridge = bridge
        self.task_goal = INITIAL_TASK or "Auto-Scanning screen"
        self.theme = auto_detect_theme(self.task_goal)
        self.is_teaching = False
        self.last_screen_hash: Optional[int] = None
        self.past_phrases: List[str] = []

        threading.Thread(target=self._crawler_loop, daemon=True).start()

    def set_goal(self, new_goal: str):
        self.task_goal = new_goal.strip()
        self.theme = auto_detect_theme(self.task_goal)
        self.bridge.set_theme.emit(self.theme)
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

    def _build_prompt(self) -> str:
        history = " | ".join(self.past_phrases[-3:]) if self.past_phrases else "None"
        return f"""You are a distinguished university professor sketching deep technical proofs, system architectures, and mathematical insights onto an infinite blackboard.

CURRENT DIRECTIVE: "{self.task_goal}"
ACTIVE VIBE: "{self.theme.upper()}"
RECENT TOPICS (DO NOT REPEAT): [{history}]

STRICT BANNED WORDS: Never write "Observation", "Supporting Insight", "Key Takeaway", "Step 1", or generic AI boilerplate.

WRITING GUIDELINES:
1. Explain the screen's core concept with academic depth and dense human annotations.
2. Provide 3 to 5 nuanced technical nodes (e.g., algorithmic edge-cases, vector identities, runtime mechanics, memory layout).
3. If code or system architecture is shown, sketch exact data-flow arrows and state-machine transitions.
4. Include genuine mathematical identities, punchy developer caveats, or witty margin notes.

Return ONLY RAW JSON:
{{
  "title": "Dense Conceptual Title",
  "central_hub": "Core Architectural Principle",
  "diagram_style": "mind_map",
  "branches": [
    {{"label": "State Mutation", "detail": "Atomic swap fails under concurrent threads without memory barriers"}},
    {{"label": "Edge Case", "detail": "Re-entrant signal handler deadlocks when allocating memory on heap"}},
    {{"label": "Vector Equation", "detail": "grad(L) = (y_pred - y_true) * x.T over mini-batch tensor"}},
    {{"label": "Runtime Caveat", "detail": "GIL contention degrades throughput on worker pools"}}
  ],
  "equations_or_punchlines": [
    ">> Proof: lim_{{x->0}} sin(x)/x = 1 (L'Hopital / Squeeze Theorem)",
    ">> Time Complexity: O(N log K) priority queue"
  ],
  "glyphs": ["lightbulb", "star"],
  "narration_clauses": [
    "Notice the memory allocation bottleneck occurring on the active stack trace.",
    "When worker threads abort via signal 200, the runtime leaks unfinished task descriptors.",
    "Let us map the corrective state transition directly onto our blackboard."
  ]
}}"""

    def _crawler_loop(self):
        while True:
            try:
                if not self.is_teaching:
                    img = self._grab_screen()
                    if img:
                        # Compute perceptual hash diff
                        curr_hash = PerceptualDiffEngine.compute_dhash(img)
                        if self.last_screen_hash is not None and self.task_goal == "Auto-Scanning screen":
                            dist = PerceptualDiffEngine.hamming_distance(curr_hash, self.last_screen_hash)
                            if dist < 8:  # Less than 12.5% visual change
                                time.sleep(AI_THINKING_INTERVAL_SEC)
                                continue

                        self.last_screen_hash = curr_hash
                        buf = BytesIO()
                        img.save(buf, format="JPEG", quality=75)
                        b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")

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
                                            {"type": "text", "text": "Synthesize deep whiteboard sketchnote."},
                                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}}
                                        ]
                                    }
                                ],
                                "response_format": {"type": "json_object"},
                                "temperature": 0.7,
                                "max_tokens": 580
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
                                "format": "json"
                            }
                            resp = requests.post(OLLAMA_URL, json=payload, timeout=40)
                            if resp.status_code == 200:
                                raw_json = resp.json().get("response", "{}")

                        # Validate and coerce schema
                        data = SchemaValidator.normalize(raw_json)
                        if data and (data["branches"] or data["title"]):
                            self.is_teaching = True
                            self.bridge.trigger_void.emit()
                            if AUTO_PAUSE_MEDIA:
                                self.bridge.pause_media_signal.emit()
                            self.bridge.dispatch_sketchnote.emit(data)
                            self.past_phrases.append(data["title"])
                            if len(self.past_phrases) > 6:
                                self.past_phrases.pop(0)

            except Exception as e:
                self.bridge.update_status.emit(f"AI: {str(e)[:24]}")

            time.sleep(AI_THINKING_INTERVAL_SEC)


# =====================================================================
# MASTER OVERLAY (With Dissolving Canvas & Dynamic Word-Wrap)
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
        self.task_goal = initial_task or "Auto-Scanning screen"

        desktop = QDesktopWidget().geometry()
        self.w, self.h = desktop.width(), desktop.height()

        # Infinite Coordinate System
        self.cam_x = 0.0
        self.cam_y = 0.0
        self.target_cam_x = 0.0
        self.target_cam_y = 0.0
        self.cam_zoom = 1.0
        self.conveyor = InfiniteConveyorOccupancy()
        self.cluster_count = 0

        # Physical Mouse Nav
        self.user_navigating = False
        self.last_mouse_pos = QPointF(0, 0)

        # Stylus & Mascot
        self.stylus_x, self.stylus_y = 400.0, 300.0
        self.target_stylus_x, self.target_stylus_y = 400.0, 300.0
        self.mascot_x, self.mascot_y = 85.0, 120.0
        self.mascot_target_x, self.mascot_target_y = 85.0, 120.0
        self.mascot_eye_blink = 0.0
        self.mascot_mouth_open = 0.0
        self.mascot_tilt_deg = 0.0
        self.mascot_mood = "OBSERVING"

        # Void Grid Fade
        self.void_alpha = 0.0
        self.void_fade_dir = 0

        # Entities
        self.plaques: List[PlaqueCard] = []
        self.strokes: List[ProgressiveVectorPath] = []
        self.text_cards: List[WrappedTextEntity] = []

        # TTS & STT
        self.narrator = VoiceNarrator()
        self.voice_listener = EchoSuppressedVoiceListener(self.bridge)
        self.voice_listener.voice_query_received.connect(self.set_user_task)
        self.narrator.speaking_state_changed.connect(self.voice_listener.set_tts_active)

        self._init_window()

        self.physics_timer = QTimer(self)
        self.physics_timer.timeout.connect(self._update_physics)
        self.physics_timer.start(UPDATE_INTERVAL_MS)

        self.ai = DualIntelligenceSystem(self.bridge)

    def _init_window(self):
        self.setGeometry(0, 0, self.w, self.h)
        self.setWindowTitle("AI TUTOR PRODUCTION ENGINE")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._set_clickthrough(True)
        self.showFullScreen()

    def _set_clickthrough(self, transparent: bool):
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
            self._set_clickthrough(False)
        elif event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_S:
            self.export_canvas()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Alt:
            self.user_navigating = False
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._set_clickthrough(True)
        super().keyReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if self.user_navigating or event.buttons() & Qt.MiddleButton:
            delta = event.pos() - self.last_mouse_pos
            self.cam_x -= delta.x() / self.cam_zoom
            self.cam_y -= delta.y() / self.cam_zoom
            self.target_cam_x, self.target_cam_y = self.cam_x, self.cam_y
            self.last_mouse_pos = event.pos()
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self.last_mouse_pos = event.pos()
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        if self.user_navigating:
            factor = 1.1 if event.angleDelta().y() > 0 else 0.9
            self.cam_zoom = max(0.3, min(3.0, self.cam_zoom * factor))
            self.update()
        super().wheelEvent(event)

    def activate_void(self):
        self.void_alpha = 0.01
        self.void_fade_dir = 1

    def apply_theme(self, t: str):
        if t in THEMES and t != self.theme_name:
            self.theme_name = t
            self.theme = THEMES[t]
            self.update()

    def apply_status(self, s: str):
        self.ai_status = s

    def set_user_task(self, task: str):
        self.current_user_task = task.strip()
        self.task_goal = task.strip()
        self.apply_theme(auto_detect_theme(self.current_user_task))
        self.ai.set_goal(self.current_user_task)
        print(f"\n[AI Focus Updated] Now resolving: \"{self.current_user_task}\"")

    # -------------------------------------------------------------------
    # DISSOLVING LIFECYCLE & DYNAMIC AUTO-EXPANDING PLACEMENT
    # -------------------------------------------------------------------
    def on_sketchnote_received(self, data: dict):
        # FIX 1 & 2: Smoothly ghost prior clusters to 20% opacity (soft blackboard chalk)
        for p in self.plaques:
            p.opacity = max(0.18, p.opacity * 0.4)
        for s in self.strokes:
            s.opacity = max(0.18, s.opacity * 0.4)
        for t in self.text_cards:
            t.opacity = max(0.18, t.opacity * 0.4)

        self.cluster_count += 1
        cluster_w = 680.0
        wx, wy = self.conveyor.get_next_cluster_origin(cluster_w)

        # Smooth camera glide to new lecture cluster
        self.target_cam_x = wx - 40.0
        self.target_cam_y = wy - 30.0

        th = self.theme
        title = data["title"].upper()
        hub = data["central_hub"]
        branches = data["branches"]
        eqs = data["equations_or_punchlines"]

        fm_title = QFontMetrics(QFont("Segoe UI", 11, QFont.Bold))
        fm_body = QFontMetrics(QFont("Segoe UI", 9, QFont.Normal))

        # Dynamic layout calculation
        cur_y = wy + 80.0
        branch_cards = []
        for b in branches:
            text_str = f"\u2022 {b['label']}: {b['detail']}"
            req_rect = fm_body.boundingRect(QRect(0, 0, int(cluster_w - 80.0), 2000), int(Qt.TextWordWrap), text_str)
            h_box = req_rect.height() + 18.0
            branch_cards.append((b, cur_y, h_box, text_str))
            cur_y += h_box + 14.0

        total_cluster_h = (cur_y - wy) + (len(eqs) * 44.0) + 50.0

        # Background Plaque
        self.plaques.append(PlaqueCard(rect=QRectF(wx, wy, cluster_w, total_cluster_h), cluster_id=self.cluster_count))

        # 1. Scalloped Header Hub
        hub_path = AdvancedDoodleEngine.scalloped_cloud(wx + cluster_w / 2.0, wy + 42.0, cluster_w / 2.2, 28.0)
        self.strokes.append(ProgressiveVectorPath(path=hub_path, color=th["hub_border"], fill=th["hub_bg"], width=2.0))
        self.text_cards.append(WrappedTextEntity(
            text=f"{title} \u2500\u2500 {hub}",
            rect=QRectF(wx + 30.0, wy + 28.0, cluster_w - 60.0, 30.0),
            color=th["accent"],
            font=QFont("Segoe UI", 10, QFont.Bold)
        ))

        # 2. Dynamic Auto-Expanding Branch Cards
        for b, by, bh, full_str in branch_cards:
            b_box = AdvancedDoodleEngine.hand_drawn_box(wx + 40.0, by, cluster_w - 80.0, bh)
            self.strokes.append(ProgressiveVectorPath(path=b_box, color=th["node_border"], fill=th["node_bg"], width=1.5))

            # Organic Connecting Branch
            b_line = AdvancedDoodleEngine.organic_branch((wx + cluster_w / 2.0, wy + 68.0), (wx + 40.0, by + bh / 2.0))
            self.strokes.append(ProgressiveVectorPath(path=b_line, color=th["branch"], fill=None, width=1.8))

            # Word-Wrapped Body Text
            self.text_cards.append(WrappedTextEntity(
                text=full_str,
                rect=QRectF(wx + 52.0, by + 8.0, cluster_w - 104.0, bh - 12.0),
                color=th["text_main"],
                font=QFont("Segoe UI", 9, QFont.Normal)
            ))

        # 3. Mathematical Identities / Caveats Box
        eq_y = cur_y + 10.0
        for eq in eqs:
            eq_box = AdvancedDoodleEngine.hand_drawn_box(wx + 50.0, eq_y, cluster_w - 100.0, 34.0)
            self.strokes.append(ProgressiveVectorPath(path=eq_box, color=th["formula_border"], fill=th["node_bg"], width=1.5))
            self.text_cards.append(WrappedTextEntity(
                text=eq,
                rect=QRectF(wx + 62.0, eq_y + 8.0, cluster_w - 124.0, 24.0),
                color=th["badge_text"],
                font=QFont("Consolas", 9, QFont.Bold)
            ))
            eq_y += 42.0

        # Speak synchronized narration
        self.narrator.speak_clauses(data["narration_clauses"])
        print(f"\n[Canvas Conveyor] Synthesized Blackboard Cluster #{self.cluster_count} at ({wx:.0f}, {wy:.0f})")

    # -------------------------------------------------------------------
    # PROGRESSIVE DRAWING & PHYSICS LOOP
    # -------------------------------------------------------------------
    def _update_physics(self):
        self.cam_x += (self.target_cam_x - self.cam_x) * 0.08
        self.cam_y += (self.target_cam_y - self.cam_y) * 0.08
        self.stylus_x += (self.target_stylus_x - self.stylus_x) * 0.15
        self.stylus_y += (self.target_stylus_y - self.stylus_y) * 0.15

        # Progressive stroke drawing
        actively_drawing = False
        for s in self.strokes:
            if s.progress < 1.0:
                s.progress = min(1.0, s.progress + 0.06)
                try:
                    pt = s.path.pointAtPercent(s.progress)
                    self.target_stylus_x, self.target_stylus_y = pt.x(), pt.y()
                except Exception:
                    pass
                actively_drawing = True
                break

        # Progressive text revelation
        if not actively_drawing:
            for t in self.text_cards:
                if t.revealed_chars < len(t.text):
                    t.revealed_chars = min(len(t.text), t.revealed_chars + 2)
                    self.target_stylus_x = t.rect.x() + (t.revealed_chars * 6.5)
                    self.target_stylus_y = t.rect.y() + 10.0
                    break

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

        # 1. Render Plaques with Alpha Ghosting
        for p in self.plaques:
            bg = QColor(15, 23, 42, int(220 * p.opacity))
            bdr = QColor(th["hub_border"].red(), th["hub_border"].green(), th["hub_border"].blue(), int(140 * p.opacity))
            painter.setBrush(QBrush(bg))
            painter.setPen(QPen(bdr, 1.5))
            painter.drawRoundedRect(p.rect, 14, 14)

        # 2. Render Progressive Strokes
        for s in self.strokes:
            if s.progress <= 0.0:
                continue
            stroke_c = QColor(s.color.red(), s.color.green(), s.color.blue(), int(255 * s.opacity))
            pen = QPen(stroke_c, s.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            if s.progress < 0.99:
                tlen = s.path.length()
                if tlen > 0:
                    pen.setDashPattern([max(1.0, tlen * s.progress) / max(1.0, s.width), 99999.0])
            painter.setPen(pen)
            if s.fill and s.progress > 0.6:
                fill_a = int(s.fill.alpha() * s.opacity * ((s.progress - 0.6) * 2.5))
                painter.setBrush(QBrush(QColor(s.fill.red(), s.fill.green(), s.fill.blue(), fill_a)))
            else:
                painter.setBrush(Qt.NoBrush)
            painter.drawPath(s.path)

        # 3. Render Word-Wrapped Text
        for t in self.text_cards:
            tc = QColor(t.color.red(), t.color.green(), t.color.blue(), int(255 * t.opacity))
            painter.setPen(tc)
            painter.setFont(t.font)
            visible_text = t.text[:t.revealed_chars]
            painter.drawText(t.rect, int(Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop), visible_text)

        painter.restore()

        self._render_stylus(painter)
        self._render_hud(painter)
        painter.end()

    def _render_transient_grid(self, painter: QPainter):
        alpha = int(255 * self.void_alpha)
        bg = self.theme["void_bg"]
        painter.fillRect(self.rect(), QColor(bg.red(), bg.green(), bg.blue(), int(alpha * 0.85)))
        dots = self.theme["grid_dots"]
        painter.setPen(QPen(QColor(dots.red(), dots.green(), dots.blue(), alpha), 2))
        for x in range(20, self.w, 44):
            for y in range(20, self.h, 44):
                painter.drawPoint(x, y)

    def _render_stylus(self, painter: QPainter):
        sx = (self.stylus_x - self.cam_x) * self.cam_zoom
        sy = (self.stylus_y - self.cam_y) * self.cam_zoom
        c = self.theme["stylus"]
        painter.setPen(QPen(QColor(c.red(), c.green(), c.blue(), 180), 1))
        painter.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), 220)))
        poly = QPolygonF([QPointF(sx, sy), QPointF(sx + 5.0, sy + 9.0), QPointF(sx + 2.0, sy + 9.0)])
        painter.drawPolygon(poly)

    def _render_hud(self, painter: QPainter):
        nav_str = "[ALT+DRAG Infinite Pan] [ALT+SCROLL Zoom] [Ctrl+S PNG]" if not self.user_navigating else "[PANNING VOID]"
        hud_text = f" AI TUTOR [{self.theme['badge_tag']}] | Task: \"{self.task_goal}\" | {nav_str} | Status: {self.ai_status} "
        font = QFont("Consolas", 9, QFont.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw, h_val = fm.horizontalAdvance(hud_text), fm.height()
        painter.setBrush(QBrush(QColor(10, 15, 30, 220)))
        painter.setPen(QPen(self.theme["hub_border"], 1.2))
        painter.drawRoundedRect(QRectF(16, self.h - h_val - 20, tw + 20, h_val + 8), 6, 6)
        painter.setPen(QColor(241, 245, 249, 235))
        painter.drawText(26, self.h - 16, hud_text)

    def export_canvas(self):
        if not self.plaques:
            print("[Note Center] Canvas is currently empty. No plaques to export.")
            return
        min_x = min(p.rect.x() for p in self.plaques) - 50
        min_y = min(p.rect.y() for p in self.plaques) - 50
        max_x = max(p.rect.right() for p in self.plaques) + 50
        max_y = max(p.rect.bottom() for p in self.plaques) + 50
        ew, eh = max(200, int(max_x - min_x)), max(200, int(max_y - min_y))
        img = QImage(ew, eh, QImage.Format_ARGB32)
        img.fill(QColor(10, 15, 26, 255))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.translate(-min_x, -min_y)
        for pl in self.plaques:
            p.setBrush(QBrush(QColor(15, 23, 42, 240)))
            p.setPen(QPen(self.theme["hub_border"], 1.5))
            p.drawRoundedRect(pl.rect, 14, 14)
        for s in self.strokes:
            p.setBrush(QBrush(s.fill) if s.fill else Qt.NoBrush)
            p.setPen(QPen(s.color, s.width))
            p.drawPath(s.path)
        for t in self.text_cards:
            p.setFont(t.font)
            p.setPen(t.color)
            p.drawText(t.rect, int(Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop), t.text)
        p.end()
        fname = f"blackboard_export_{int(time.time())}.png"
        img.save(fname)
        print(f"\n[Note Center] Exported infinite blackboard snapshot to: {os.path.abspath(fname)}")


# =====================================================================
# TERMINAL INPUT LOOP & BOOTSTRAPPER
# =====================================================================
def terminal_input_loop(overlay: SketchnoteTutorOverlay):
    time.sleep(1.0)
    print("\n" + "=" * 65)
    print("AI TUTOR PRODUCTION REPAIR CONSOLE (Architecture v6)")
    print("Type any prompt/concept or speak into mic (Echo & Gibberish Filter active):")
    print("  * 'explain raft consensus protocol' -> Architectural proofs & data flow")
    print("  * 'derive euler-lagrange equation'  -> Multi-branch vector derivation")
    print("Controls:")
    print("  * Hold ALT + Drag: Pan infinite blackboard void")
    print("  * Hold ALT + Scroll: Zoom infinite canvas (0.3x - 3.0x)")
    print("  * Ctrl + S: Export high-res blackboard PNG")
    print("=" * 65 + "\n")
    while True:
        try:
            goal = input("Enter teaching goal > ").strip()
            if goal:
                overlay.set_user_task(goal)
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps)

    print("=" * 65)
    print(" AI TEACHING ASSISTANT - PRODUCTION WHITEBOARD v6 ")
    print("=" * 65)
    print(f"Target Vision Core      : {MODEL_DISPLAY_NAME}")
    print("Spatial Layout          : Infinite Blackboard Conveyor (Anti-Stacking)")
    print("Screen Diffing Engine   : 64-bit dHash Perceptual Hashing (Anti-Thrashing)")
    print("Schema Enforcement      : Coercive Normalizer & Sanitizer Active")
    print("Acoustic Echo Gating    : Active (Mic suppressed during speech)")
    print(f"OS Media Auto-Pause     : {'GSMTC WinRT Hooks' if HAS_WINRT else 'Virtual Key Fallback'}")
    print(f"Voice Synthesis (TTS)   : {'ENABLED' if VOICE_ENABLED else 'DISABLED'}")
    print(f"Hands-Free Voice (STT)  : {'ENABLED' if LISTEN_ENABLED else 'DISABLED'}")
    print("=" * 65)

    overlay = SketchnoteTutorOverlay(initial_task=INITIAL_TASK)
    threading.Thread(target=terminal_input_loop, args=(overlay,), daemon=True).start()

    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sig_timer = QTimer()
    sig_timer.timeout.connect(lambda: None)
    sig_timer.start(500)

    sys.exit(app.exec_())
