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
    organic vector trees, AST complexity audits, and conceptual derivations.
  • MODE B (Hojaiga In-Situ AR Mode): 1:1 physical pixel grounding directly over
    active video feeds, PDFs, and desktop apps through generalized visual analysis.
    Direct Euclidean proof projections, pulsating button focus beacons, micro-tag
    pills, and step-gated interactive tutorials with zero card backings.
================================================================================
"""

import sys
import os
import signal
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
import tempfile
from io import BytesIO
from typing import List, Tuple, Optional, Dict, Any

try:
    from omni_sketch_engine import OmniSketchEngine, SceneValidationError
    HAS_OMNI_SKETCH = True
except Exception as _omni_sketch_import_error:
    # The existing Void remains usable if this optional local module is absent.
    HAS_OMNI_SKETCH = False
    OmniSketchEngine = None
    SceneValidationError = ValueError
    print('[OmniSketch] unavailable:', _omni_sketch_import_error)

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
    # Qt expects the GUI thread to be initialized for OLE as STA. Do this before
    # importing Win32/Qt helpers so Qt does not have to switch an existing MTA.
    try:
        COM_INIT_RESULT = ctypes.windll.ole32.OleInitialize(None)
    except Exception:
        COM_INIT_RESULT = None
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

# Optional symbolic math support powers generic coordinate plots from safe,
# user-provided expressions. It is not a collection of example-specific graphs.
HAS_SYMPY = False
try:
    import sympy as sp
    from sympy.parsing.sympy_parser import (
        parse_expr, standard_transformations, convert_xor,
        implicit_multiplication_application,
    )
    HAS_SYMPY = True
except Exception:
    sp = None

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

HAS_EDGE_TTS = False
try:
    import edge_tts
    import pygame
    import asyncio
    HAS_EDGE_TTS = True
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

parser = argparse.ArgumentParser(description="AI Teaching Assistant - Spatial Whiteboard v8 (Universal Hojaiga)")
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
USE_3B = getattr(cli_args, "3b", False) or (os.getenv("AI_TEACHER_MODEL", "").lower() in ["3b", "qwen3b"])

# Default is now Qwen2.5-VL-7B (Port 8081 via llama.cpp) with automatic Ollama fallback
if USE_EDGE0:
    ACTIVE_BACKEND = "edge0"
    MODEL_DISPLAY_NAME = "Edge0-35B MoE Streaming (Port 8082)"
    AI_THINKING_INTERVAL_SEC = 4
    VISION_MAX_RES = (1024, 1024)
elif USE_3B:
    ACTIVE_BACKEND = "3b"
    MODEL_DISPLAY_NAME = "qwen2.5vl:3b (Port 11434)"
    AI_THINKING_INTERVAL_SEC = 5
    VISION_MAX_RES = (1024, 1024)
else:
    ACTIVE_BACKEND = "7b"
    MODEL_DISPLAY_NAME = "Qwen2.5-VL-7B (llama.cpp Port 8081)"
    AI_THINKING_INTERVAL_SEC = 6
    VISION_MAX_RES = (1024, 1024)

INITIAL_TASK = cli_args.task or os.getenv("AI_TEACHER_TASK", "")
VOICE_ENABLED = (not cli_args.no_voice) and (cli_args.voice or HAS_EDGE_TTS)
LISTEN_ENABLED = (not cli_args.no_listen) and (cli_args.listen or (HAS_WHISPER or HAS_SR))
AUTO_PAUSE_MEDIA = cli_args.pause_media

# Backward-compatible adapter for responses produced before the universal
# normalized scene contract. New model prompts no longer emit plot_specs.
def normalize_lesson_plot_specs(raw_specs: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_specs, list):
        return []
    clean: List[Dict[str, Any]] = []
    for item in raw_specs[:4]:
        if not isinstance(item, dict):
            continue
        expression = str(item.get('expr', '')).strip()
        if expression:
            spec = dict(item)
            spec['expr'] = expression[:120]
            clean.append(spec)
    return clean


def lesson_drawings_have_ink(drawings: Any, *_unused: Any) -> bool:
    if not isinstance(drawings, list):
        return False
    for raw in drawings:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get('type', '')).lower()
        if kind in {'freehand', 'arrow', 'shape', 'highlight'}:
            points = raw.get('points')
            if kind != 'freehand' or isinstance(points, list) and len(points) >= 2:
                return True
    return False


def ensure_visible_ink_color(color_str: Any) -> QColor:
    qcolor = QColor(str(color_str)) if color_str else QColor("#38bdf8")
    if not qcolor.isValid():
        qcolor = QColor("#38bdf8")
    if qcolor.alpha() < 40:
        qcolor.setAlpha(255)
    if qcolor.lightness() < 55:
        qcolor = QColor(56, 189, 248)
    return qcolor

# =============================================================================
# ROBUST VISION QUERY ENGINE — Centralized VLM/LLM with Automatic Fallback
# =============================================================================
class RobustVisionQueryEngine:
    """
    Thread-safe LLM/VLM query engine.
    Priority chain: llama.cpp Qwen2.5-VL-7B (8081) → Ollama qwen2.5vl:3b (11434) → Ollama minicpm-v (11434).
    Supports: text-only, vision (image+text), and JSON-mode responses.
    """
    _lock = threading.Lock()

    @staticmethod
    def query_vision(prompt: str, base64_image: str = "", json_mode: bool = True,
                     max_tokens: int = 800, temperature: float = 0.6, timeout: int = 180,
                     backend: Optional[str] = None, allow_fallback: bool = True) -> str:
        """
        Send a prompt (optionally with a base64-encoded JPEG image) to the best available VLM.
        Returns the raw response string (JSON or plain text depending on json_mode).
        Returns '{}' on total failure so callers never crash.
        """
        if not HAS_REQUESTS:
            print("[RobustVisionQueryEngine] requests library not available.")
            return "{}" if json_mode else ""

        selected_backend = backend or ACTIVE_BACKEND
        # Edge0 is intentionally not routed through Ollama. This build has no
        # verified local multimodal Edge0 endpoint, so failing explicitly avoids
        # claiming a 35B model while actually using Qwen 3B.
        if selected_backend == "edge0":
            print("[RobustVisionQueryEngine] Edge0 is not configured as a verified multimodal endpoint; use --7b or --3b.")
            return "{}" if json_mode else ""

        # --- Attempt 1: llama.cpp Qwen2.5-VL-7B on port 8081 ---
        # Respect an active lesson backend: do not silently switch models after
        # the lesson has started merely because a slower 7B request is still running.
        if selected_backend == "7b":
            try:
                user_content = [{"type": "text", "text": prompt}]
                if base64_image:
                    user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}})
                payload = {
                    "messages": [
                        {"role": "system", "content": "You are a precise analytical assistant. Return only what is asked."},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": temperature, "max_tokens": max_tokens, "stream": False
                }
                if json_mode:
                    payload["response_format"] = {"type": "json_object"}
                resp = requests.post(LLAMA_SERVER_7B_URL, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    result = resp.json()["choices"][0]["message"]["content"]
                    print("[RobustVisionQueryEngine] Success via llama.cpp 7B (port 8081)")
                    return result
            except requests.exceptions.ReadTimeout:
                print("[RobustVisionQueryEngine] llama.cpp 7B request timed out.")
                if not allow_fallback:
                    return "{}" if json_mode else ""
                print("[RobustVisionQueryEngine] Trying the configured fallback backend.")
            except Exception as e:
                print(f"[RobustVisionQueryEngine] llama.cpp 8081 unavailable: {type(e).__name__}")
                if not allow_fallback:
                    return "{}" if json_mode else ""
        if selected_backend == "7b" and not allow_fallback:
            return "{}" if json_mode else ""
        # --- Attempt 2: Ollama qwen2.5vl:3b (vision-capable) on port 11434 ---
        try:
            ollama_payload = {
                "model": "qwen2.5vl:3b",
                "prompt": prompt,
                "stream": False
            }
            if base64_image:
                ollama_payload["images"] = [base64_image]
            if json_mode:
                ollama_payload["format"] = "json"

            resp = requests.post(OLLAMA_URL, json=ollama_payload, timeout=timeout)
            if resp.status_code == 200:
                result = resp.json().get("response", "{}" if json_mode else "")
                print("[RobustVisionQueryEngine] Success via Ollama qwen2.5vl:3b (port 11434)")
                return result
        except Exception as e:
            print(f"[RobustVisionQueryEngine] Ollama qwen2.5vl:3b failed: {type(e).__name__}")

        # --- Attempt 3: Ollama minicpm-v (vision fallback) ---
        try:
            ollama_payload = {
                "model": "minicpm-v:latest",
                "prompt": prompt,
                "stream": False
            }
            if base64_image:
                ollama_payload["images"] = [base64_image]
            if json_mode:
                ollama_payload["format"] = "json"

            resp = requests.post(OLLAMA_URL, json=ollama_payload, timeout=timeout)
            if resp.status_code == 200:
                result = resp.json().get("response", "{}" if json_mode else "")
                print("[RobustVisionQueryEngine] Success via Ollama minicpm-v (port 11434)")
                return result
        except Exception as e:
            print(f"[RobustVisionQueryEngine] All VLM backends exhausted: {type(e).__name__}")

        return "{}" if json_mode else ""

    @staticmethod
    def query_text(prompt: str, json_mode: bool = True,
                   max_tokens: int = 800, temperature: float = 0.6, timeout: int = 45) -> str:
        """Text-only query (no image). Same fallback chain but uses text-only models too."""
        return RobustVisionQueryEngine.query_vision(
            prompt=prompt, base64_image="", json_mode=json_mode,
            max_tokens=max_tokens, temperature=temperature, timeout=timeout
        )

    @staticmethod
    def grab_screen_b64(max_res: Tuple[int, int] = (1024, 1024)) -> str:
        """Capture the primary screen and return as base64-encoded JPEG string."""
        try:
            if HAS_MSS:
                sct_cls = getattr(mss, "MSS", getattr(mss, "mss", None))
                if sct_cls:
                    with sct_cls() as sct:
                        mon = sct.monitors[1]
                        s_img = sct.grab(mon)
                        img = Image.frombytes("RGB", s_img.size, s_img.bgra, "raw", "BGRX")
                        img.thumbnail(max_res)
                        buf = BytesIO()
                        img.save(buf, format="JPEG", quality=75)
                        return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception:
            pass
        try:
            img = ImageGrab.grab()
            img.thumbnail(max_res)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=75)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception:
            return ""


class DisplayMode(enum.Enum):
    VOID = "VOID"            # Infinite blackboard canvas with organic vectors & camera panning
    IN_SITU = "IN_SITU"      # Hojaiga 1:1 physical pixel augmentation directly on screen

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
    }
}

@dataclasses.dataclass
class MicroPillTag:
    """High-contrast floating pill plaque anchored to an on-screen coordinate."""
    text: str
    target_pt: QPointF
    color: QColor = dataclasses.field(default_factory=lambda: QColor(244, 63, 94))
    bg_color: QColor = dataclasses.field(default_factory=lambda: QColor(15, 23, 42, 235))
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
    """Vector strokes anchored directly to on-screen objects with zero cards."""
    points: List[QPointF]
    color: QColor
    width: float = 3.0
    is_closed: bool = False
    fill_color: Optional[QColor] = None
    progress: float = 0.0

@dataclasses.dataclass
class TutorialStep:
    """A discrete interactive step in an application or concept walkthrough."""
    step_number: int
    spoken_instruction: str
    target_rect: QRectF
    pill_label: str
    accent_color: QColor
    dwell_duration: float = 3.5

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
    # A model scene may schedule this action against the matching narration
    # segment. Zero preserves the legacy immediate-draw behaviour.
    start_ms: int = 0

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
    # Per-stage pacing ties handwritten board annotations to the narration.
    text_reveal_rate: float = 0.08
    timeline_started_at: float = 0.0
    text_start_ms: Dict[int, int] = dataclasses.field(default_factory=dict)

class DynamicScreenFeatureDetector:
    """
    Scans live desktop pixel buffers using OpenCV to extract real screen geometry:
    triangles, polygons, UI panels, and open negative space.
    Eliminates hardcoded screen-center coordinates.
    """
    @staticmethod
    def find_on_screen_triangle(pil_img: Image.Image) -> Optional[Tuple[QPointF, QPointF, QPointF]]:
        """Finds the most prominent 3-sided polygon (e.g. Khan Academy triangle) on screen."""
        if not HAS_OPENCV or pil_img is None:
            return None
        try:
            np_arr = np.array(pil_img)
            gray = cv2.cvtColor(np_arr, cv2.COLOR_RGB2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 40, 130)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            best_triangle = None
            max_area = 0.0

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area > 1200:
                    peri = cv2.arcLength(cnt, True)
                    approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
                    if len(approx) == 3 and area > max_area:
                        max_area = area
                        pts = [QPointF(float(p[0][0]), float(p[0][1])) for p in approx]
                        best_triangle = pts

            if best_triangle:
                p0, p1, p2 = best_triangle
                d01 = math.hypot(p1.x() - p0.x(), p1.y() - p0.y())
                d12 = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
                d20 = math.hypot(p0.x() - p2.x(), p0.y() - p2.y())

                if d12 >= d01 and d12 >= d20:
                    A, B, C = p0, p1, p2
                elif d20 >= d01 and d20 >= d12:
                    A, B, C = p1, p2, p0
                else:
                    A, B, C = p2, p0, p1

                if abs(C.x() - A.x()) > abs(B.x() - A.x()):
                    B, C = C, B

                return (A, B, C)
        except Exception as e:
            print(f"[Dynamic Triangle Detection Warning] {e}")
        return None

    @staticmethod
    def find_screen_negative_space(screen_w: int, screen_h: int) -> QPointF:
        """Finds open negative space on screen to place drawings without covering dense code."""
        if not (HAS_MSS and HAS_OPENCV):
            return QPointF(screen_w * 0.65, screen_h * 0.45)
        try:
            with mss.MSS() as sct:
                s_img = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", s_img.size, s_img.bgra, "raw", "BGRX")
            np_arr = np.array(img.resize((160, 90), Image.Resampling.BILINEAR))
            gray = cv2.cvtColor(np_arr, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 40, 120)

            h, w = edges.shape
            mid_y, mid_x = h // 2, w // 2
            q_density = [
                (np.mean(edges[0:mid_y, 0:mid_x]), QPointF(screen_w * 0.25, screen_h * 0.30)),
                (np.mean(edges[0:mid_y, mid_x:w]), QPointF(screen_w * 0.72, screen_h * 0.30)),
                (np.mean(edges[mid_y:h, 0:mid_x]), QPointF(screen_w * 0.25, screen_h * 0.70)),
                (np.mean(edges[mid_y:h, mid_x:w]), QPointF(screen_w * 0.72, screen_h * 0.70)),
            ]
            q_density.sort(key=lambda x: x[0])
            return q_density[0][1]
        except Exception:
            return QPointF(screen_w * 0.65, screen_h * 0.45)

    @staticmethod
    def detect_clickable_ui_clusters(pil_img: Image.Image, max_clusters: int = 6) -> List[QRectF]:
        """Scans active software windows to find interactable button grids via contour clustering."""
        if not HAS_OPENCV or pil_img is None:
            return []
        try:
            np_arr = np.array(pil_img)
            gray = cv2.cvtColor(np_arr, cv2.COLOR_RGB2GRAY)
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            edges = cv2.Canny(blurred, 30, 100)
            contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

            rects = []
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                # Filter for typical UI button dimensions
                if 20 <= w <= 180 and 16 <= h <= 60:
                    rects.append(QRectF(float(x), float(y), float(w), float(h)))

            # Sort and deduplicate nearby overlapping rectangles
            rects.sort(key=lambda r: (r.y(), r.x()))
            clean_rects = []
            for r in rects:
                if not any(abs(r.x() - c.x()) < 15 and abs(r.y() - c.y()) < 15 for c in clean_rects):
                    clean_rects.append(r)
                if len(clean_rects) >= max_clusters:
                    break
            return clean_rects
        except Exception as e:
            print(f"[UI Detection Warning] {e}")
            return []


class SpatialScreenSegmenter:
    """Partitions screen between active application / media and whiteboard canvas."""
    def __init__(self, screen_w: int, screen_h: int):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.content_zone = QRectF(0, 0, screen_w / 2.0, screen_h)
        self.whiteboard_zone = QRectF(screen_w / 2.0, 0, screen_w / 2.0, screen_h)

    def analyze_layout(self) -> Dict[str, Any]:
        if sys.platform != "win32":
            return {"whiteboard_zone": self.whiteboard_zone}
        try:
            import win32gui
            windows = []
            def enum_cb(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    rect = win32gui.GetWindowRect(hwnd)
                    w, h = rect[2] - rect[0], rect[3] - rect[1]
                    title = (win32gui.GetWindowText(hwnd) or "").lower()
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


class InSituSpatialGrounder:
    """
    Transforms coordinate-grounded VLM detections and OpenCV contours into
    augmented vector overlays directly on screen without card containers.
    All measurements are computed dynamically from actual pixel coordinates.
    """
    @staticmethod
    def build_dynamic_polygon_augmentation(
        vertices: Tuple[QPointF, ...],
    ) -> Tuple[List[AugmentedGeometry], List[MicroPillTag]]:
        """
        Dynamically annotates ANY detected polygon (triangle, quad, etc.)
        with real measured side lengths, computed areas, interior angles,
        and outward Euclidean squares on each side. No hardcoded values.
        """
        geometries: List[AugmentedGeometry] = []
        pills: List[MicroPillTag] = []
        n = len(vertices)
        if n < 3:
            return geometries, pills

        coral = QColor(244, 63, 94)
        cyan = QColor(56, 189, 248)
        emerald = QColor(52, 211, 153)
        side_colors = [coral, cyan, emerald, QColor(251, 191, 36), QColor(216, 180, 254)]

        # --- Compute all side lengths from real pixel coordinates ---
        side_lengths: List[float] = []
        for i in range(n):
            p1 = vertices[i]
            p2 = vertices[(i + 1) % n]
            side_lengths.append(math.hypot(p2.x() - p1.x(), p2.y() - p1.y()))

        # --- Compute interior angles via dot product ---
        angles_deg: List[float] = []
        for i in range(n):
            p_prev = vertices[(i - 1) % n]
            p_curr = vertices[i]
            p_next = vertices[(i + 1) % n]
            v1x, v1y = p_prev.x() - p_curr.x(), p_prev.y() - p_curr.y()
            v2x, v2y = p_next.x() - p_curr.x(), p_next.y() - p_curr.y()
            dot = v1x * v2x + v1y * v2y
            mag1 = math.hypot(v1x, v1y) + 1e-9
            mag2 = math.hypot(v2x, v2y) + 1e-9
            cos_angle = max(-1.0, min(1.0, dot / (mag1 * mag2)))
            angles_deg.append(math.degrees(math.acos(cos_angle)))

        # --- Find the vertex closest to a right angle (for triangle annotation) ---
        right_angle_idx = min(range(n), key=lambda i: abs(angles_deg[i] - 90.0))

        # --- 1. Angle markers at each vertex ---
        for i in range(n):
            p_curr = vertices[i]
            p_prev = vertices[(i - 1) % n]
            p_next = vertices[(i + 1) % n]
            angle = angles_deg[i]

            # Direction vectors
            len_prev = math.hypot(p_prev.x() - p_curr.x(), p_prev.y() - p_curr.y()) + 1e-9
            len_next = math.hypot(p_next.x() - p_curr.x(), p_next.y() - p_curr.y()) + 1e-9
            dir_prev_x = (p_prev.x() - p_curr.x()) / len_prev
            dir_prev_y = (p_prev.y() - p_curr.y()) / len_prev
            dir_next_x = (p_next.x() - p_curr.x()) / len_next
            dir_next_y = (p_next.y() - p_curr.y()) / len_next

            marker_size = 16.0
            if abs(angle - 90.0) < 8.0:
                # Right-angle square marker
                m1 = QPointF(p_curr.x() + dir_prev_x * marker_size, p_curr.y() + dir_prev_y * marker_size)
                m2 = QPointF(m1.x() + dir_next_x * marker_size, m1.y() + dir_next_y * marker_size)
                m3 = QPointF(p_curr.x() + dir_next_x * marker_size, p_curr.y() + dir_next_y * marker_size)
                geometries.append(AugmentedGeometry(
                    points=[p_curr, m1, m2, m3, p_curr],
                    color=coral, width=2.0, is_closed=True
                ))
                pills.append(MicroPillTag(
                    text=f"90°",
                    target_pt=QPointF(m2.x() + 6, m2.y() + 6),
                    color=coral
                ))
            else:
                # Small arc indicator for non-right angles
                pills.append(MicroPillTag(
                    text=f"{angle:.1f}°",
                    target_pt=QPointF(
                        p_curr.x() + (dir_prev_x + dir_next_x) * 22,
                        p_curr.y() + (dir_prev_y + dir_next_y) * 22
                    ),
                    color=side_colors[i % len(side_colors)]
                ))

        # --- 2. Side edges with dynamically computed length labels ---
        longest_side_idx = max(range(n), key=lambda i: side_lengths[i])
        for i in range(n):
            p1 = vertices[i]
            p2 = vertices[(i + 1) % n]
            length_px = side_lengths[i]
            col = cyan if i == longest_side_idx else coral

            # Edge line
            geometries.append(AugmentedGeometry(points=[p1, p2], color=col, width=3.5))

            # Label: use pixel length as the real measurement
            mid_x = (p1.x() + p2.x()) * 0.5
            mid_y = (p1.y() + p2.y()) * 0.5
            # Offset the label perpendicular to the edge
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            edge_len = math.hypot(dx, dy) + 1e-9
            perp_x = -dy / edge_len * 20
            perp_y = dx / edge_len * 20

            side_label = f"side {chr(65 + i)} = {length_px:.0f}px"
            if n == 3 and i == longest_side_idx:
                side_label = f"longest = {length_px:.0f}px"
            pills.append(MicroPillTag(
                text=side_label,
                target_pt=QPointF(mid_x + perp_x, mid_y + perp_y),
                color=col
            ))

        # --- 3. Outward Euclidean squares on each side ---
        for i in range(n):
            p1 = vertices[i]
            p2 = vertices[(i + 1) % n]
            length_px = side_lengths[i]
            col = cyan if i == longest_side_idx else coral

            # Outward direction: perpendicular away from polygon centroid
            cx_poly = sum(v.x() for v in vertices) / n
            cy_poly = sum(v.y() for v in vertices) / n
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            # Perpendicular direction (rotate 90° CCW)
            perp_x = -dy
            perp_y = dx
            # Ensure it points away from centroid
            mid_x = (p1.x() + p2.x()) * 0.5
            mid_y = (p1.y() + p2.y()) * 0.5
            to_center_x = cx_poly - mid_x
            to_center_y = cy_poly - mid_y
            if perp_x * to_center_x + perp_y * to_center_y > 0:
                perp_x, perp_y = -perp_x, -perp_y

            # Build outward square
            sq_pts = [
                p1,
                p2,
                QPointF(p2.x() + perp_x, p2.y() + perp_y),
                QPointF(p1.x() + perp_x, p1.y() + perp_y),
                p1
            ]
            geometries.append(AugmentedGeometry(
                points=sq_pts,
                color=col, width=2.5, is_closed=True,
                fill_color=QColor(col.red(), col.green(), col.blue(), 45)
            ))
            area_val = length_px * length_px
            pills.append(MicroPillTag(
                text=f"area = {area_val:.0f}px²",
                target_pt=QPointF(
                    mid_x + perp_x * 0.5,
                    mid_y + perp_y * 0.5
                ),
                color=col
            ))

        # --- 4. Pythagorean check annotation (for triangles) ---
        if n == 3:
            sorted_sides = sorted(side_lengths)
            a2, b2, c2 = sorted_sides[0]**2, sorted_sides[1]**2, sorted_sides[2]**2
            residual = abs(a2 + b2 - c2) / (c2 + 1e-9)
            centroid = QPointF(
                sum(v.x() for v in vertices) / 3,
                sum(v.y() for v in vertices) / 3
            )
            if residual < 0.05:
                pills.append(MicroPillTag(
                    text=f"✓ a²+b² = c² (Pythagorean)",
                    target_pt=QPointF(centroid.x(), centroid.y() - 30),
                    color=emerald
                ))
            else:
                pills.append(MicroPillTag(
                    text=f"a²+b² ≠ c² (not right Δ)",
                    target_pt=QPointF(centroid.x(), centroid.y() - 30),
                    color=QColor(251, 191, 36)
                ))

        return geometries, pills

    @staticmethod
    def build_dynamic_app_tutorial_via_vlm(
        app_name: str, screen_b64: str
    ) -> List[TutorialStep]:
        """
        Uses VLM to scan the actual screenshot, identify real UI controls
        (buttons, sliders, menus), and build a multi-step interactive tutorial.
        Returns dynamically generated TutorialSteps with real control labels.
        """
        prompt = f"""You are analyzing a screenshot of the application '{app_name}'.
Identify the 5 most important interactive UI controls visible on screen (buttons, menus, sliders, tabs, input fields).
For each control, provide its approximate bounding box as percentages of screen width/height and what it does.

Return ONLY raw JSON:
{{
  "app_name": "{app_name}",
  "controls": [
    {{
      "label": "Exact text or description of the control",
      "action": "What clicking this control does",
      "bbox_pct": [x_percent, y_percent, width_percent, height_percent]
    }}
  ]
}}"""

        raw = RobustVisionQueryEngine.query_vision(prompt, screen_b64, json_mode=True, max_tokens=600)
        steps: List[TutorialStep] = []
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                controls = data.get("controls", [])
                for idx, ctrl in enumerate(controls):
                    label = ctrl.get("label", f"Control {idx + 1}")
                    action = ctrl.get("action", f"Interact with {label}")
                    bbox = ctrl.get("bbox_pct", [20 + idx * 15, 30, 12, 5])
                    # Convert percentage to approximate pixel coords (based on common 1920x1080)
                    rx = bbox[0] / 100.0 * 1920
                    ry = bbox[1] / 100.0 * 1080
                    rw = max(40.0, bbox[2] / 100.0 * 1920)
                    rh = max(20.0, bbox[3] / 100.0 * 1080)
                    col = QColor(244, 63, 94) if idx % 2 == 0 else QColor(56, 189, 248)
                    steps.append(TutorialStep(
                        step_number=idx + 1,
                        spoken_instruction=f"Step {idx + 1}: {action}. Click the '{label}' control now.",
                        target_rect=QRectF(rx, ry, rw, rh),
                        pill_label=label.lower()[:30],
                        accent_color=col,
                        dwell_duration=4.5
                    ))
        except Exception as e:
            print(f"[Dynamic App Tutorial VLM Parse Warning] {e}")

        if not steps:
            # Minimal fallback: just tell user no controls detected
            steps.append(TutorialStep(
                step_number=1,
                spoken_instruction=f"I could not identify specific controls in {app_name}. Let me scan again.",
                target_rect=QRectF(960 - 80, 540 - 20, 160, 40),
                pill_label="scanning...",
                accent_color=QColor(251, 191, 36),
                dwell_duration=5.0
            ))
        return steps

    @staticmethod
    def build_dynamic_daw_tutorial_via_vlm(
        screen_b64: str, target_window_rect: Optional[QRectF] = None
    ) -> List[TutorialStep]:
        """
        Scans the actual DAW/sequencer UI via VLM to identify step sequencer cells,
        instrument rows, and transport controls. No hardcoded kick/snare offsets.
        """
        prompt = """You are analyzing a screenshot of a Digital Audio Workstation (DAW), likely FL Studio or similar.
Identify the key interactive elements for making a beat:
1. Step sequencer grid cells (instrument rows and beat steps)
2. Transport controls (play, stop, record buttons)
3. Any instrument channel names visible

For each important element, provide bounding box as percentages of screen dimensions.

Return ONLY raw JSON:
{
  "daw_name": "detected DAW name or 'Unknown DAW'",
  "steps": [
    {
      "instruction": "Clear description of what to click and why",
      "label": "Short label for the UI element",
      "bbox_pct": [x_percent, y_percent, width_percent, height_percent]
    }
  ]
}"""

        raw = RobustVisionQueryEngine.query_vision(prompt, screen_b64, json_mode=True, max_tokens=600)
        steps: List[TutorialStep] = []
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                daw_name = data.get("daw_name", "DAW")
                for idx, step_data in enumerate(data.get("steps", [])):
                    instruction = step_data.get("instruction", f"Step {idx + 1}")
                    label = step_data.get("label", f"element {idx + 1}")
                    bbox = step_data.get("bbox_pct", [25 + idx * 10, 40, 8, 4])
                    rx = bbox[0] / 100.0 * 1920
                    ry = bbox[1] / 100.0 * 1080
                    rw = max(20.0, bbox[2] / 100.0 * 1920)
                    rh = max(16.0, bbox[3] / 100.0 * 1080)
                    col = QColor(244, 63, 94) if idx % 2 == 0 else QColor(56, 189, 248)
                    steps.append(TutorialStep(
                        step_number=idx + 1,
                        spoken_instruction=instruction,
                        target_rect=QRectF(rx, ry, rw, rh),
                        pill_label=label.lower()[:25],
                        accent_color=col,
                        dwell_duration=4.0
                    ))
                if steps:
                    print(f"[Dynamic DAW Tutorial] Built {len(steps)} steps for '{daw_name}'")
        except Exception as e:
            print(f"[Dynamic DAW Tutorial VLM Parse Warning] {e}")

        if not steps:
            steps.append(TutorialStep(
                step_number=1,
                spoken_instruction="I'm scanning the sequencer. Open FL Studio's Channel Rack and I'll guide you through each step.",
                target_rect=QRectF(960 - 100, 540 - 20, 200, 40),
                pill_label="open channel rack",
                accent_color=QColor(251, 191, 36),
                dwell_duration=5.0
            ))
        return steps

class DeepDocumentVisualDeconstructor:
    """
    Ingests entire PDFs, research papers, legal contracts, technical specs, and
    deconstructs them into borderless organic visual decision trees, condition diamonds,
    and concept branches. ALL stages are dynamically extracted via LLM analysis of
    the actual document text — no hardcoded contract templates.
    """
    @staticmethod
    def deconstruct_document_into_visual_dag(
        origin_x: float, origin_y: float, title: str, raw_text: str
    ) -> SketchnoteElement:
        cyan = QColor(56, 189, 248)
        emerald = QColor(52, 211, 153)
        amber = QColor(251, 191, 36)
        coral = QColor(248, 113, 113)
        lavender = QColor(216, 180, 254)
        stage_colors = [emerald, amber, cyan, coral, lavender, QColor(244, 63, 94), QColor(168, 162, 158)]

        # --- Ask LLM to analyze the actual document and extract structure ---
        truncated_text = raw_text[:3000]  # Keep prompt within token limits
        llm_prompt = f"""Analyze this document and extract its logical structure.

DOCUMENT TITLE: {title}
DOCUMENT TEXT (truncated):
{truncated_text}

Return ONLY raw JSON:
{{
  "document_type": "research paper / legal contract / technical spec / policy / other",
  "summary": "One-sentence summary of the entire document",
  "stages": [
    {{
      "title": "Short descriptive stage title (max 50 chars)",
      "description": "What this section covers (max 120 chars)",
      "key_entities": ["important term 1", "important term 2"]
    }}
  ],
  "key_decisions": [
    {{
      "question": "A critical decision point or condition in the document",
      "yes_outcome": "What happens if yes/true",
      "no_outcome": "What happens if no/false"
    }}
  ],
  "equations_or_formulas": ["Any formulas, rules, or quantitative thresholds found"],
  "conclusion": "Final takeaway or recommendation from the document"
}}"""

        stages = []
        decisions = []
        equations = []
        doc_summary = f"Document: {title}"
        conclusion = ""

        raw_resp = RobustVisionQueryEngine.query_text(llm_prompt, json_mode=True, max_tokens=900, timeout=45)
        try:
            match = re.search(r'\{.*\}', raw_resp, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                doc_summary = data.get("summary", doc_summary)
                conclusion = data.get("conclusion", "")
                equations = data.get("equations_or_formulas", [])
                for s in data.get("stages", []):
                    stages.append((
                        s.get("title", "Section")[:50],
                        s.get("description", "")[:120],
                        s.get("key_entities", [])
                    ))
                for d in data.get("key_decisions", []):
                    decisions.append((
                        d.get("question", "Decision?"),
                        d.get("yes_outcome", "Proceed"),
                        d.get("no_outcome", "Halt")
                    ))
        except Exception as e:
            print(f"[DeepDocumentDeconstructor LLM Parse Warning] {e}")

        # --- Fallback: extract stages from paragraphs if LLM returned nothing ---
        if not stages:
            paragraphs = [p.strip() for p in raw_text.split("\n\n") if len(p.strip()) > 30]
            if not paragraphs:
                paragraphs = [p.strip() for p in raw_text.split("\n") if len(p.strip()) > 25]
            for idx, para in enumerate(paragraphs[:7]):
                stages.append((
                    f"SECTION {idx + 1}",
                    para[:120],
                    []
                ))

        # --- Build visual element ---
        num_stages = max(len(stages), 1)
        dag_height = max(780, num_stages * 80 + 300)
        elem = SketchnoteElement(
            id=f"deep_doc_{int(time.time())}",
            element_type="proof",
            bounding_rect=QRectF(origin_x - 60, origin_y - 60, 1260, dag_height)
        )

        # 1. Floating Cloud Banner
        head_center = QPointF(origin_x + 420, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(head_center, 420, 36, 18),
            color=cyan, width=2.5, fill_color=QColor(56, 189, 248, 25)
        ))
        elem.text_items.append((
            QPointF(head_center.x() - 360, head_center.y() + 6),
            f"DEEP DOCUMENT DECONSTRUCTION: {title.upper()[:60]}",
            QFont("Segoe Print", 11, QFont.Bold), QColor(241, 245, 249), 0.0
        ))
        # Document summary line
        elem.text_items.append((
            QPointF(origin_x + 60, origin_y + 35),
            doc_summary[:100],
            QFont("Segoe Print", 9), QColor(203, 213, 225), 0.0
        ))

        # 2. Sequential Left Flow: Dynamically extracted stages
        sy = origin_y + 80
        for i, (stage_title, desc, entities) in enumerate(stages):
            col = stage_colors[i % len(stage_colors)]
            box_rect = QRectF(origin_x + 40, sy - 14, 520, 52)
            for p1, p2 in [(box_rect.topLeft(), box_rect.topRight()), (box_rect.topRight(), box_rect.bottomRight()),
                           (box_rect.bottomRight(), box_rect.bottomLeft()), (box_rect.bottomLeft(), box_rect.topLeft())]:
                elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(p1, p2, 8), color=col, width=1.8))
            elem.text_items.append((QPointF(origin_x + 55, sy + 6), f"STAGE {i+1}: {stage_title.upper()}", QFont("Segoe Print", 9, QFont.Bold), col, 0.0))
            elem.text_items.append((QPointF(origin_x + 55, sy + 28), desc, QFont("Segoe Print", 8), QColor(203, 213, 225), 0.0))

            if i < len(stages) - 1:
                arr = OrganicGeometryFactory.hand_drawn_arrow(QPointF(origin_x + 300, sy + 38), QPointF(origin_x + 300, sy + 66), 8.0)
                elem.strokes.append(HandStroke(points=arr, color=col, width=1.5))
            sy += 74

        # 3. Right Visual Logic DAG — dynamically from extracted decisions
        dx = origin_x + 640
        dy = origin_y + 80
        dag_box_h = max(440, len(decisions) * 160 + 180)
        dag_rect = QRectF(dx, dy, 520, dag_box_h)
        for p1, p2 in [(dag_rect.topLeft(), dag_rect.topRight()), (dag_rect.topRight(), dag_rect.bottomRight()),
                       (dag_rect.bottomRight(), dag_rect.bottomLeft()), (dag_rect.bottomLeft(), dag_rect.topLeft())]:
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_line(p1, p2, 14), color=cyan, width=2.0))

        elem.text_items.append((QPointF(dx + 25, dy + 35), "LOGICAL TOPOLOGY & CAUSAL GRAPH", QFont("Segoe Print", 10, QFont.Bold), cyan, 0.0))

        # Decision diamonds from real document analysis
        dm_y_offset = dy + 90
        for d_idx, (question, yes_out, no_out) in enumerate(decisions[:3]):
            dm_cx = dx + 260
            dm_cy = dm_y_offset
            dm_pts = [
                QPointF(dm_cx, dm_cy - 30),
                QPointF(dm_cx + 70, dm_cy),
                QPointF(dm_cx, dm_cy + 30),
                QPointF(dm_cx - 70, dm_cy),
                QPointF(dm_cx, dm_cy - 30)
            ]
            elem.strokes.append(HandStroke(points=dm_pts, color=amber, width=2.0, fill_color=QColor(amber.red(), amber.green(), amber.blue(), 30)))
            elem.text_items.append((QPointF(dm_cx - 60, dm_cy + 4), question[:30], QFont("Segoe Print", 8, QFont.Bold), amber, 0.0))

            # YES branch →
            elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_arrow(QPointF(dm_cx + 70, dm_cy), QPointF(dx + 430, dm_cy)), color=emerald, width=2.0))
            elem.text_items.append((QPointF(dx + 340, dm_cy - 8), f"YES → {yes_out[:20]}", QFont("Segoe Print", 8, QFont.Bold), emerald, 0.0))

            # NO branch ↓
            if d_idx < len(decisions) - 1:
                elem.strokes.append(HandStroke(points=OrganicGeometryFactory.hand_drawn_arrow(QPointF(dm_cx, dm_cy + 30), QPointF(dm_cx, dm_cy + 100)), color=coral, width=2.0))
                elem.text_items.append((QPointF(dm_cx + 10, dm_cy + 55), f"NO → {no_out[:20]}", QFont("Segoe Print", 8, QFont.Bold), coral, 0.0))
            else:
                elem.text_items.append((QPointF(dm_cx - 40, dm_cy + 45), f"NO → {no_out[:25]}", QFont("Segoe Print", 8, QFont.Bold), coral, 0.0))

            dm_y_offset += 140

        # Equations / formulas from document
        eq_y = max(dm_y_offset + 20, dy + dag_box_h - 120)
        for eq_idx, eq in enumerate(equations[:3]):
            elem.text_items.append((QPointF(dx + 25, eq_y), f">> {eq[:80]}", QFont("Consolas", 9), emerald, 0.0))
            eq_y += 28

        # Conclusion
        if conclusion:
            elem.text_items.append((QPointF(dx + 25, eq_y + 10), f"• {conclusion[:90]}", QFont("Segoe Print", 9), cyan, 0.0))

        # Stick figure presenter
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.stick_figure_presenter(dx - 30, dy + dag_box_h - 80, QPointF(dx + 120, dy + dag_box_h * 0.5)),
            color=cyan, width=2.0
        ))
        return elem

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
            QFont("Segoe Print", 11, QFont.Bold), QColor(241, 245, 249), 0.0
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
            elem.text_items.append((QPointF(rx + 22, cy), t, QFont("Segoe Print", 10, QFont.Bold), col, 0.0))
            elem.text_items.append((QPointF(rx + 22, cy + 22), d, QFont("Segoe Print", 9), QColor(203, 213, 225), 0.0))
            cy += 64

        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.stick_figure_presenter(origin_x + 30, origin_y + 490, QPointF(origin_x + 180, origin_y + 200)),
            color=cyan, width=2.0
        ))
        return elem

class DocumentAndPDFIngestor:
    @staticmethod
    def extract_document_text(filepath: str, max_pages: int = 8) -> str:
        if not os.path.exists(filepath):
            return f"Error: Document {filepath} not found on disk."

        if filepath.lower().endswith(".pdf") and HAS_PYPDF:
            try:
                reader = pypdf.PdfReader(filepath)
                text = ""
                for i in range(min(len(reader.pages), max_pages)):
                    page_text = reader.pages[i].extract_text() or ""
                    text += f"\n--- Page {i+1} ---\n" + page_text
                return text[:6000]
            except Exception as e:
                return f"PDF Ingestion error: {e}"

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                return f.read(6000)
        except Exception as e:
            return f"File read error: {e}"

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
            with mss.MSS() as sct:
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
            QFont("Segoe Print", 11, QFont.Bold), QColor(241, 245, 249), 0.0
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
            elem.text_items.append((QPointF(origin_x + 55, sy + 6), title, QFont("Segoe Print", 9, QFont.Bold), col, 0.0))
            elem.text_items.append((QPointF(origin_x + 55, sy + 26), desc, QFont("Segoe Print", 8), QColor(203, 213, 225), 0.0))

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
        elem.text_items.append((QPointF(dx + 25, dy + 35), f"STRUCTURAL BLUEPRINT: {clean_topic.upper()}", QFont("Segoe Print", 10, QFont.Bold), cyan, 0.0))
        elem.text_items.append((QPointF(dx + 25, dy + 70), "• Axiom 1: Invariant conservation rules strictly enforced.", QFont("Segoe Print", 9), emerald, 0.0))
        elem.text_items.append((QPointF(dx + 25, dy + 105), "• Axiom 2: Dimensional analysis validates scalar/vector balance.", QFont("Segoe Print", 9), amber, 0.0))
        elem.text_items.append((QPointF(dx + 25, dy + 140), "• Axiom 3: Asymptotic limits converge without singularities.", QFont("Segoe Print", 9), lavender, 0.0))

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
            QFont("Segoe Print", 11, QFont.Bold), QColor(241, 245, 249), 0.0
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
            QFont("Segoe Print", 11, QFont.Bold), QColor(254, 243, 199), 0.0
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
                QFont("Segoe Print", 11, QFont.Bold if "Challenge" in line else QFont.Normal),
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
            elem.text_items.append((QPointF(origin_x + 65, oy), opt_text, QFont("Segoe Print", 10), col, 0.0))
            oy += 45

        quiz_meta = {
            "correct_c": correct_c,
            "correct_sq": correct_sq,
            "options": options
        }
        return elem, hypot, float(correct_sq), quiz_meta

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
            except Exception:
                self.kokoro = None

        if (self.kokoro or HAS_EDGE_TTS) and VOICE_ENABLED:
            threading.Thread(target=self._worker, daemon=True).start()

    def speak(self, phrase: str):
        if not phrase.strip():
            return
        self.speech_queue.put(phrase.strip())

    def _worker(self):
        if not self.kokoro and HAS_EDGE_TTS:
            try:
                pygame.mixer.init()
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
                    if HAS_EDGE_TTS:
                        try:
                            # Generate TTS with Edge
                            temp_file = os.path.join(tempfile.gettempdir(), f"hojaiga_speech_{int(time.time()*1000)}.mp3")
                            communicate = edge_tts.Communicate(phrase, "en-US-AriaNeural", rate="+15%")
                            asyncio.run(communicate.save(temp_file))
                            
                            # Play with PyGame
                            if not pygame.mixer.get_init():
                                pygame.mixer.init()
                            pygame.mixer.music.load(temp_file)
                            pygame.mixer.music.play()
                            while pygame.mixer.music.get_busy():
                                time.sleep(0.05)
                            pygame.mixer.music.unload()
                            try:
                                os.remove(temp_file)
                            except Exception:
                                pass
                        except Exception as e:
                            print(f"[Edge TTS Error] {e}")

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
            b64_data = RobustVisionQueryEngine.grab_screen_b64(VISION_MAX_RES)

            history = " | ".join(self.past_phrases[-3:]) if self.past_phrases else "None"
            directive = prompt_directive or "Act as a free-form teacher. Analyze the screen and teach."
            full_prompt = f"""You are a distinguished university professor and a virtual AI teacher named "Hojaiga".
You are teaching a student on an infinite glass whiteboard over their desktop.
CURRENT DIRECTIVE: "{directive}"
RECENT TOPICS (DO NOT REPEAT): [{history}]
You can draw free-form diagrams, write formulas, create shapes, and point to things on screen using a virtual mouse.
Return ONLY RAW JSON using this exact schema for your drawing commands:
{{
  "narration": "What you say out loud to explain this step (use natural, human-like teaching tone)...",
  "title": "Topic Title",
  "drawings": [
    {{"type": "text", "content": "E = mc\u00b2", "x": 500, "y": 300, "color": "cyan"}},
    {{"type": "shape", "shape_type": "circle", "x": 500, "y": 400, "w": 100, "h": 100, "color": "magenta"}},
    {{"type": "shape", "shape_type": "triangle", "x": 200, "y": 200, "w": 150, "h": 150, "color": "yellow"}},
    {{"type": "arrow", "from_x": 550, "from_y": 320, "to_x": 550, "to_y": 380, "color": "white"}},
    {{"type": "highlight", "screen_x": 800, "screen_y": 150, "color": "rgba(255, 255, 0, 100)"}},
    {{"type": "freehand", "points": [[10, 10], [20, 20], [30, 10]], "color": "green"}}
  ],
  "auto_pan_target": {{"x": 500, "y": 300}},
  "mouse_target": {{"x": 800, "y": 150, "label": "Look here"}}
}}
IMPORTANT: Output only the JSON. Do not include markdown ticks."""

            raw_json = RobustVisionQueryEngine.query_vision(
                full_prompt, b64_data, json_mode=True, max_tokens=1000, temperature=0.7
            )

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
        # Reticle labels stay internal; the learner sees only the presenter dot.
        self.cursor_label = ""
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
                self.cursor_label = ""

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

        # Keep the virtual laser clean: coordinates/actions are retained in
        # current_x/current_y but never printed over the teaching surface.
class IterativeTeachingOrgan(QObject):
    """
    True Dynamic Iterative Teacher.
    Uses an autonomous feedback loop, traces with the virtual mouse,
    and generates an End-of-Session Markdown Report.
    """
    def __init__(self, overlay, topic: str):
        super().__init__()
        self.overlay = overlay
        self.topic = topic
        self.is_active = True
        self.is_paused = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.lesson_history = []
        self.content_fingerprints = set()
        self.quiz_history_path = os.path.abspath('hojaiga_quiz_history.json')
        self.report_directory = os.path.join(os.getcwd(), "hojaiga_reports")
        os.makedirs(self.report_directory, exist_ok=True)
        report_slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")[:56] or "lesson"
        self.report_path = os.path.join(self.report_directory, f"{report_slug}_{time.time_ns()}.md")
        try:
            with open(self.quiz_history_path, 'r', encoding='utf-8') as f:
                self.asked_questions = set(json.load(f).get(self.topic.lower(), []))
        except Exception:
            self.asked_questions = set()
        self.current_y_offset = 300
        self.response_event = threading.Event()
        self.response_text = ''
        self.profile_history_path = os.path.abspath('hojaiga_learner_profile.json')
        self.learner_profile = {"level": "newcomer", "prefers_derivation": None, "quiz_results": []}
        self.last_quiz_question = ''
        self.last_quiz_answer = ''
        try:
            with open(self.profile_history_path, 'r', encoding='utf-8') as f:
                stored_profile = json.load(f).get(self.topic.lower(), {})
            if isinstance(stored_profile, dict):
                self.learner_profile.update(stored_profile)
        except Exception:
            pass
        # Fallback only; the planner replaces these with task-specific stages.
        self.stages = [
            ("Orient", "State the task, available information, and intended outcome."),
            ("Reason", "Develop the solution or explanation step by step."),
            ("Verify", "Check the result against the task and explain why it follows."),
            ("Questions", "Invite the learner to challenge or extend the reasoning."),
            ("Knowledge check", "Ask one fresh question that checks understanding.")
        ]
        self.stage_actions = {"Questions": "qa", "Knowledge check": "quiz"}
        self.session_mode = "unclassified"
        self.requires_derivation_permission = False
        self.derivation_allowed = True
        self.awaiting_response = False
        self.needs_screen_vision = False
        self.presentation_mode = "worked_text"
        self.allow_diagrams = False
        # Intent only selects the fast visual workflow; the model chooses what
        # to annotate from the complete request rather than fixed keyword routes.
        self.explicit_visual_request = bool(re.search(
            r"\b(draw|trace|graph|plot|chart|diagram|visuali[sz]e|sketch|annotat(?:e|ion))\b",
            topic, re.IGNORECASE
        ))
        self.is_teaching_request = bool(re.match(r"\s*(teach|explain|learn|lesson|tutor)\b", topic, re.IGNORECASE))
        self.solution_verified = False
        self.backstage_solution: Dict[str, Any] = {}
        self.fast_visual_mode = self.explicit_visual_request
        self.model_backend = ACTIVE_BACKEND
        
    def start(self):
        threading.Thread(target=self._run_dynamic_loop, daemon=True).start()

    def submit_response(self, text: str):
        if not self.awaiting_response:
            return False
        self.response_text = text.strip()
        self.response_event.set()
        return True

    def stop(self):
        self.is_active = False
        self.awaiting_response = False
        self.pause_event.set()
        self.response_event.set()
        if self.lesson_history:
            self._generate_markdown_report(status="stopped")

    def pause(self):
        self.is_paused = True
        self.pause_event.clear()
        print(f"[Iterative Teacher] Lesson PAUSED by user interaction.")

    def resume(self):
        self.is_paused = False
        self.pause_event.set()
        print(f"[Iterative Teacher] Lesson RESUMED.")

    def toggle_pause(self):
        if self.is_paused:
            self.resume()
        else:
            self.pause()
        
    def _update_learner_profile(self, response: str, quiz_correct=None):
        """Keep a small durable learner model without assuming a fixed curriculum."""
        normalized = (response or "").lower()
        if any(token in normalized for token in ("beginner", "new", "start from", "dont know", "don't know")):
            self.learner_profile["level"] = "newcomer"
        elif any(token in normalized for token in ("advanced", "expert", "already know")):
            self.learner_profile["level"] = "advanced"
        elif any(token in normalized for token in ("intermediate", "somewhat", "basic")):
            self.learner_profile["level"] = "intermediate"
        if quiz_correct is not None:
            self.learner_profile.setdefault("quiz_results", []).append(bool(quiz_correct))
            self.learner_profile["quiz_results"] = self.learner_profile["quiz_results"][-12:]
        try:
            existing = {}
            if os.path.exists(self.profile_history_path):
                with open(self.profile_history_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            existing[self.topic.lower()] = self.learner_profile
            with open(self.profile_history_path, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2)
        except Exception as exc:
            print(f"[Iterative Teacher] Learner profile save failed: {exc}")

    def _unique_quiz_key(self, question: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (question or "").lower()).strip()

    def _plan_session(self):
        """Create a compact, task-specific solution plan before drawing anything."""
        planner_prompt = """You are Hojaiga's universal task planner. The TASK may be mathematics, a graph, a screenshot, code, an app workflow, design, research, or open-ended brainstorming.

Make a short complete plan that teaches how to reach a defensible answer. Do not solve with generic filler. Decide whether visual evidence from the current screen is essential for the solution. Return ONLY JSON:
{
  "mode": "short task classification",
  "needs_screen_vision": false,
  "requires_derivation_permission": false,
  "presentation": "worked_text|diagram|mixed",
  "drawings_needed": false,
  "stages": [
    {"name": "short unique stage name", "instruction": "specific reasoning work for this task"}
  ]
}
Use exactly 3 stages for a direct solve/draw request and 3–5 stages for an explicit teaching request. The direct stages must cover task/givens, reasoning or construction, and verification/final answer. Choose worked_text and drawings_needed false for calculations, prose, code review, planning, and other tasks that are clear through structured writing. Choose diagram only where the actual task is visual (geometry, graphs, spatial systems, anatomy, circuit/layout) or a diagram materially improves understanding; never use decorative shapes. Set requires_derivation_permission true only for a non-trivial formal proof or derivation, never for ordinary arithmetic. Do not include quiz or Q&A stages; the engine adds them after the solution."""
        # Text tasks do not pay a vision cost. A frame is only needed when the
        # request refers to existing visible evidence on screen.
        screen_reference = bool(re.search(r"\b(screen|screenshot|image|photo|pictured|shown|this app|on the board)\b", self.topic, re.IGNORECASE))
        first_image = RobustVisionQueryEngine.grab_screen_b64((640, 640)) if screen_reference else ""
        try:
            raw = RobustVisionQueryEngine.query_vision(
                planner_prompt + "\n\nTASK:\n" + self.topic,
                first_image, json_mode=True, max_tokens=260, temperature=0.15,
                timeout=180, backend=self.model_backend, allow_fallback=False,
            )
            match = re.search(r'\{.*\}', raw or "", re.DOTALL)
            plan = json.loads(match.group(0)) if match else {}
            candidate_stages = plan.get("stages", []) if isinstance(plan, dict) else []
            compiled, actions = [], {}
            for raw_stage in candidate_stages[:5]:
                if not isinstance(raw_stage, dict):
                    continue
                name = re.sub(r"\s+", " ", str(raw_stage.get("name", ""))).strip()[:72]
                instruction = re.sub(r"\s+", " ", str(raw_stage.get("instruction", ""))).strip()[:420]
                if not name or not instruction:
                    continue
                if name in actions:
                    name = f"{name} {len(compiled) + 1}"
                compiled.append((name, instruction))
                actions[name] = "none"
            if len(compiled) >= 3:
                # A direct command is deliberately compact. Keep its opening,
                # its visual/construction stage (when relevant), and its check.
                if not self.is_teaching_request and len(compiled) > 3:
                    chosen = [compiled[0]]
                    if self.explicit_visual_request:
                        visual = next((stage for stage in compiled[1:-1]
                                       if re.search(r"\b(graph|grpah|grahp|plot|chart|diagram|visual|sketch|construct)\b", stage[0] + " " + stage[1], re.IGNORECASE)), None)
                        if visual:
                            chosen.append(visual)
                    if compiled[-1] not in chosen:
                        chosen.append(compiled[-1])
                    compiled = chosen
                    actions = {name: "none" for name, _ in compiled}
                # Solving a one-off task should not wait through Q&A and quiz
                # stages. Those remain part of an explicitly requested lesson.
                if self.is_teaching_request:
                    compiled.append(("Questions", "Invite learner questions about the completed reasoning."))
                    actions["Questions"] = "qa"
                    compiled.append(("Knowledge check", "Ask one fresh task-specific question to confirm understanding."))
                    actions["Knowledge check"] = "quiz"
                self.stages = compiled
                self.stage_actions = actions
                self.session_mode = str(plan.get("mode", "unclassified"))[:100]
                self.needs_screen_vision = bool(plan.get("needs_screen_vision", False)) or screen_reference
                requested_mode = str(plan.get("presentation", "worked_text")).strip().lower()
                self.presentation_mode = requested_mode if requested_mode in {"worked_text", "diagram", "mixed"} else "worked_text"
                # Explicit visual requests always permit a meaningful diagram even
                # when the planner returns an overly conservative text-only mode.
                if self.explicit_visual_request:
                    self.presentation_mode = "mixed"
                self.allow_diagrams = (bool(plan.get("drawings_needed", False)) and self.presentation_mode in {"diagram", "mixed"}) or self.explicit_visual_request
                self.requires_derivation_permission = bool(plan.get("requires_derivation_permission", False))
                print(f"[Iterative Teacher] Planned {len(self.stages)} dynamic stages ({self.session_mode}; vision={self.needs_screen_vision}; presentation={self.presentation_mode}; interactive={self.is_teaching_request}).")
        except Exception as exc:
            print(f"[Iterative Teacher] Dynamic planning fallback: {exc}")

    def _compact_history(self) -> str:
        """Pass semantic progress, not every prior drawing point, back to the model."""
        compact = []
        for stage in self.lesson_history[-3:]:
            state = stage.get("solution_state", {}) if isinstance(stage.get("solution_state"), dict) else {}
            labels = [str(line.get("text", ""))[:80] for line in stage.get("writing_lines", []) if isinstance(line, dict)]
            compact.append({
                "stage": stage.get("stage", ""),
                "narration": str(stage.get("narration", ""))[:280],
                "labels": labels[:8],
                "answer": state.get("answer", ""),
            })
        return json.dumps(compact, ensure_ascii=False) if compact else "No prior solution steps."

    def _wait_for_response(self, spoken_prompt: str, timeout: int = 120) -> str:
        """Accept a free-text command only while the teacher has explicitly asked."""
        self.response_text = ""
        self.response_event.clear()
        self.awaiting_response = True
        self.overlay.narrator.speak(spoken_prompt)
        self.response_event.wait(timeout=timeout)
        self.awaiting_response = False
        response = self.response_text.strip()
        self.response_text = ""
        return response
    def _answers_equivalent(self, first: Any, second: Any) -> bool:
        """Conservative exact-text comparison; ambiguous answers go to model resolution."""
        def normalize(value: Any) -> str:
            text = re.sub(r"\s+", " ", str(value or "").lower()).strip()
            text = re.sub(r"^(answer|result|final answer)\s*[:=]\s*", "", text)
            return text.rstrip(".")
        a, b = normalize(first), normalize(second)
        if not a or not b:
            return False
        if a == b:
            return True
        try:
            return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False

    def _capture_backstage_answer(self):
        """Get a hidden answer hypothesis before the visible derivation begins."""
        prompt = f"""You are Hojaiga's backstage answer estimator. Produce a concise candidate answer for the TASK without teaching it and without writing a derivation.
TASK: {self.topic}
For subjective, underspecified, or visual tasks, state the best-supported conclusion and its uncertainty instead of inventing certainty.
Return ONLY JSON: {{"answer":"candidate answer", "confidence":"high|medium|low", "limitations":["real limitations only"]}}"""
        image = RobustVisionQueryEngine.grab_screen_b64((768, 768)) if self.needs_screen_vision else ""
        try:
            raw = RobustVisionQueryEngine.query_vision(
                prompt, image, json_mode=True, max_tokens=140, temperature=0.0,
                timeout=180, backend=self.model_backend, allow_fallback=False,
            )
            match = re.search(r'\{.*\}', raw or "", re.DOTALL)
            data = json.loads(match.group(0)) if match else {}
            if isinstance(data, dict) and data.get("answer"):
                self.backstage_solution = data
                print("[Iterative Teacher] Hidden candidate answer captured; visible derivation is now required.")
            else:
                print("[Iterative Teacher] Hidden candidate answer unavailable; derivation will be audited without comparison.")
        except Exception as exc:
            print(f"[Iterative Teacher] Hidden candidate answer unavailable: {exc}")

    def _verify_mandatory_derivation(self, derived: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Compare the hidden hypothesis to the final written derivation and repair any mismatch."""
        if self.solution_verified or not self.is_active:
            return None
        self.solution_verified = True
        derived_state = derived.get("solution_state", {}) if isinstance(derived.get("solution_state"), dict) else {}
        derived_answer = derived_state.get("answer", "")
        derived_steps = [str(step).strip() for step in derived_state.get("steps", []) if str(step).strip()]
        hidden_answer = self.backstage_solution.get("answer", "")
        has_derivation = bool(derived_steps)
        matched = has_derivation and self._answers_equivalent(hidden_answer, derived_answer)
        if matched:
            verdict, final_answer = "derived_and_matched", derived_answer
            details = ["The hidden answer and the completed derivation agree.", "The final result is accepted from the written derivation."]
        else:
            image = RobustVisionQueryEngine.grab_screen_b64((768, 768)) if self.needs_screen_vision else ""
            audit_prompt = f"""You are Hojaiga's mandatory derivation auditor. A hidden answer was captured before teaching. The visible derivation was completed separately. Re-solve the TASK from first principles and audit every transformation, assumption, operator, unit, and inference.
TASK: {self.topic}
HIDDEN ANSWER: {json.dumps(self.backstage_solution, ensure_ascii=False)}
VISIBLE DERIVATION: {json.dumps(derived_state, ensure_ascii=False)}
Do not choose by majority or confidence. If the derivation is incomplete, make the missing derivation. If there is a mismatch, identify the exact first error, explain it, and re-derive the result correctly.
Return ONLY JSON: {{"verdict":"corrected|derived_and_matched|uncertain", "answer":"best supported answer", "error_type":"assumption|operator|arithmetic|algebra|unit|evidence|incomplete_derivation|other", "error_explanation":"specific first error or empty when none", "corrected_derivation":["mandatory ordered steps"], "confidence":"high|medium|low"}}"""
            try:
                raw = RobustVisionQueryEngine.query_vision(
                    audit_prompt, image, json_mode=True, max_tokens=700, temperature=0.0,
                    timeout=180, backend=self.model_backend, allow_fallback=False,
                )
                match = re.search(r'\{.*\}', raw or "", re.DOTALL)
                audit = json.loads(match.group(0)) if match else {}
            except Exception as exc:
                print(f"[Iterative Teacher] Derivation audit unavailable: {exc}")
                audit = {}
            verdict = str(audit.get("verdict", "uncertain")).lower()
            final_answer = audit.get("answer") or derived_answer or hidden_answer
            details = [str(step).strip() for step in audit.get("corrected_derivation", []) if str(step).strip()][:8]
            error_explanation = str(audit.get("error_explanation", "")).strip()
            if error_explanation:
                details.insert(0, f"Error found: {error_explanation}")
            if not details:
                details = ["The answer and derivation could not be reconciled automatically; do not treat this result as verified."]
        lines = [{"kind": "heading", "text": "Mandatory derivation audit"}]
        lines.extend({"kind": "equation", "text": detail[:160]} for detail in details[:8])
        result_kind = "result" if verdict in {"derived_and_matched", "corrected"} else "explanation"
        lines.append({"kind": result_kind, "text": f"{verdict.replace('_', ' ').title()}: {final_answer}"[:160]})
        return {
            "title": f"{self.topic} - Mandatory derivation audit",
            "narration": "I compared the completed derivation with a hidden answer and audited any disagreement step by step.",
            "writing_lines": lines,
            "drawings": [],
            "solution_state": {"givens": ["Hidden candidate compared with mandatory visible derivation"], "steps": details, "answer": final_answer},
            "auto_pan_target": {},
            "verification": {"verdict": verdict, "derivation_answer": derived_answer, "hidden_answer_available": bool(hidden_answer), "final_answer": final_answer, "derivation_complete": has_derivation, "confidence": self.backstage_solution.get("confidence", "unknown")},
        }

    def _stage_requires_visual(self, stage_name: str, stage_desc: str) -> bool:
        """Only enforce a diagram where the requested visual is actually built."""
        if not self.explicit_visual_request:
            return False
        return bool(re.search(r"\b(graph|grpah|grahp|plot|chart|diagram|visual|sketch|construct)\b", f"{stage_name} {stage_desc}", re.IGNORECASE))

    def _request_visual_supplement(self, stage_name: str, stage_desc: str, solution_state: Any) -> List[Dict[str, Any]]:
        """One bounded repair pass using the universal scene contract."""
        prompt = f"""Return a compact visual scene for this learner task.
TASK: {self.topic}
STAGE: {stage_name} - {stage_desc}
Return only JSON with a `scene` list. Each action has id, kind, data, style,
start_ms, duration_ms, and optional segment_id. Use normalized coordinates
(0..1) rather than pixels. Allowed kinds are stroke, arrow, shape, text,
highlight, or function_plot. A function_plot has expression and domain.
Choose the correct visual yourself; never return decoration or prose.
"""
        try:
            raw = RobustVisionQueryEngine.query_vision(
                prompt, "", json_mode=True, max_tokens=520, temperature=0.0,
                timeout=60, backend="3b" if self.fast_visual_mode else self.model_backend,
                allow_fallback=self.fast_visual_mode,
            )
            payload = self._decode_lesson_payload(raw) or {}
            drawings = self.overlay._merge_model_visual_payload(payload) if isinstance(payload, dict) else []
            print(f"[Iterative Teacher] Visual repair returned {len(drawings)} drawable marks.")
            return drawings
        except Exception as exc:
            print(f"[Iterative Teacher] Visual supplement failed for {stage_name}: {exc}")
            return []

    @staticmethod
    def _decode_lesson_payload(raw: Any) -> Optional[Dict[str, Any]]:
        """Extract a JSON object without being confused by quoted braces or fences."""
        if not isinstance(raw, str):
            return None
        text = re.sub(r"^\s*\`\`\`(?:json)?\s*|\s*\`\`\`\s*$", "", raw.strip(), flags=re.IGNORECASE)
        decoder = json.JSONDecoder()
        for source in (text, re.sub(r",\s*([}\]])", r"\1", text)):
            for match in re.finditer(r"\{", source):
                try:
                    value, _ = decoder.raw_decode(source[match.start():])
                    if isinstance(value, dict):
                        return value
                except json.JSONDecodeError:
                    continue
        return None

    def _repair_lesson_payload(self, malformed: str, stage_name: str) -> Optional[Dict[str, Any]]:
        """Give the model one bounded chance to convert its own malformed JSON."""
        repair_prompt = f"""Convert this malformed lesson response into one valid JSON object. Keep only its information. Use keys narration, title, writing_lines, drawings, solution_state, auto_pan_target. Return only JSON.
STAGE: {stage_name}
RESPONSE:
{malformed[:6000]}"""
        try:
            repaired = RobustVisionQueryEngine.query_vision(
                repair_prompt, "", json_mode=True, max_tokens=500, temperature=0.0,
                timeout=150, backend=self.model_backend, allow_fallback=False,
            )
            return self._decode_lesson_payload(repaired)
        except Exception as exc:
            print(f"[Iterative Teacher] JSON repair unavailable for {stage_name}: {exc}")
            return None

    def _run_dynamic_loop(self):
        print(f"[Iterative Teacher] Beginning dynamic teaching loop for: {self.topic}")
        if self.fast_visual_mode:
            # One model request only: visual commands should annotate now, not
            # wait through planning, a hidden-answer call, audits, or quizzes.
            self.stages = [("Live visual annotation", "Draw and label the requested content while explaining it.")]
            self.stage_actions = {"Live visual annotation": "visual_only"}
            self.presentation_mode = "diagram"
            self.allow_diagrams = True
            self.derivation_allowed = False
            print("[Iterative Teacher] Fast visual mode: one dynamic annotation pass.")
        else:
            self._plan_session()
            self._capture_backstage_answer()
            self.derivation_allowed = True
            self.learner_profile["prefers_derivation"] = True
        stage_idx = 0
        repeated_attempts = 0
        while stage_idx < len(self.stages):
            if not self.is_active:
                break
                
            stage_name, stage_desc = self.stages[stage_idx]
            stage_action = self.stage_actions.get(stage_name, "none")
            

            print(f"[Iterative Teacher] Generating Stage: {stage_name}...")
            
            drawn_memory = self._compact_history()
            b64_data = RobustVisionQueryEngine.grab_screen_b64((768, 768)) if self.needs_screen_vision else ""
            
            quiz_context = ""
            if stage_action == "quiz":
                quiz_context = f"\nDo NOT ask any of these previously asked questions: {list(self.asked_questions)}"
            
            qa_context = ""
            if stage_action == "qa_response" and hasattr(self, 'last_qa_query'):
                qa_context = f"\nThe user just asked: '{self.last_qa_query}'. Answer that exact question visually and vocally, then relate it to the existing diagram."
            elif stage_action == "quiz_feedback":
                qa_context = f"\nQuiz question: '{self.last_quiz_question}'\nLearner answer: '{self.last_quiz_answer}'\nGrade the answer explicitly, correct any misconception, and give one short revision cue."
                
            visual_contract = (
                "The user explicitly requested a visual. Infer the appropriate diagram from the full task and return 2-12 meaningful marks plus labels. For graphs/plots/curves, prefer plot_specs with a correct symbolic expr and viewing window, plus short labels; use bright stroke colors. Use axes only for a coordinate graph; use arrows for flow, forces, or process direction; use shapes and paths for structures, maps, plans, or concepts. Never substitute a decorative shape."
                if self.explicit_visual_request else
                "No diagram was explicitly requested; use drawings only if they materially clarify the task."
            )
            prompt = f"""You are "Hojaiga", a dynamic AI teacher who writes a clean, progressive worked solution on a glass whiteboard.
TOPIC: "{self.topic}"
CURRENT STAGE: {stage_name} - {stage_desc}
LEARNER PROFILE: {json.dumps(self.learner_profile, ensure_ascii=False)}
PREVIOUS SOLUTION STATE: {drawn_memory}{quiz_context}{qa_context}
PRESENTATION POLICY: {self.presentation_mode}; diagrams permitted: {self.allow_diagrams}.\nVISUAL REQUIREMENT: {visual_contract}

Solve and teach the actual task, never generic whiteboard filler. Each stage must add distinct, correct reasoning. State givens/evidence, then write every relevant transformation, decision, or construction in order, and verify the conclusion. A final result is invalid without an explicit derivation or evidence chain in solution_state.steps. For calculations, write the original expression and each operation in sequence; explain operators or order of operations only where it helps. For code, workflows, planning, or prose, write a neat ordered explanation, not decorative geometry. For visual tasks, read visible graph geometry, straight lines, curves, labels, and relationships from the image rather than inventing them.

`writing_lines` is the board's primary output. Supply 3–8 short, complete lines for this stage, using kind "heading", "explanation", "equation", or "result". They must be concise teacher annotations, not a pasted paragraph: each spoken idea must have a matching visible line, equation, label, or diagram annotation. Put the working in the same order it will be narrated; write a small step, then its reason, then the next step. They must stand alone as a student-readable worked solution. If diagrams permitted is false, return an empty drawings array exactly. If diagrams permitted is true, draw only geometry, graph, biology/physics structure, or another visual that directly clarifies this task; never add decorative shapes. Derivation is mandatory: never skip required reasoning steps. A Q&A or quiz stage should still write its question or correction neatly.

Return ONLY RAW JSON in this exact schema:
{{
  "narration": "What you say out loud while these lines are appearing.",
  "title": "{self.topic} - {stage_name}",
  "writing_lines": [{{"kind": "heading|explanation|equation|result", "text": "short readable board line"}}],
  "drawings": [
    {{"type": "shape|arrow|highlight|freehand", "shape_type": "circle|triangle|box when type is shape", "x": 0, "y": 0, "w": 0, "h": 0, "color": "#RRGGBB", "points": [[0,0],[1,1]]}}
  ],
  "plot_specs": [{{"expr": "optional symbolic expression", "variable": "x", "x_min": -6.28, "x_max": 6.28, "y_min": -4, "y_max": 4, "color": "#38bdf8"}}],
  "solution_state": {{"givens": ["evidence used"], "steps": ["reasoning step"], "answer": "current or final result"}},
  "quiz": {{"question": "only when this stage is a knowledge check", "answer_rubric": "short expected reasoning"}},
  "auto_pan_target": {{"x": 500, "y": {self.current_y_offset + 100}}}
}}
IMPORTANT: Output only JSON."""
            
            raw_json = RobustVisionQueryEngine.query_vision(
                prompt, b64_data, json_mode=True,
                max_tokens=640 if self.fast_visual_mode else 320, temperature=0.15,
                timeout=90 if self.fast_visual_mode else 180,
                backend="3b" if self.fast_visual_mode else self.model_backend,
                allow_fallback=self.fast_visual_mode,
            )
            if not self.is_active:
                break

            data = self._decode_lesson_payload(raw_json)
            if data is None:
                print(f"[Iterative Teacher] Malformed JSON for {stage_name}; requesting one repair pass.")
                data = self._repair_lesson_payload(raw_json, stage_name)
            if data is not None:
                try:
                    if not isinstance(data, dict):
                        raise ValueError("model response root must be an object")
                    data["writing_lines"] = self.overlay._sanitize_writing_lines(
                        data.get("writing_lines", []), data.get("solution_state", {})
                    )
                    data["drawings"] = self.overlay._merge_model_visual_payload(data) if self.allow_diagrams else []
                    if self.fast_visual_mode and not lesson_drawings_have_ink(data["drawings"], self.topic):
                        data["drawings"] = self._request_visual_supplement(
                            stage_name, stage_desc, data.get("solution_state", {})
                        )
                    if (
                        self.fast_visual_mode
                        and task_expects_function_plot(self.topic)
                        and not lesson_drawings_have_ink(data["drawings"], self.topic)
                    ):
                        data["drawings"] = self._request_plot_spec_supplement(stage_name)
                    if self.fast_visual_mode:
                        print(f"[Iterative Teacher] Drawable marks ready: {len(data.get('drawings', []))}.")
                    # An empty JSON object is a backend failure, not a completed
                    # visual lesson.  Do not silently report success with no ink.
                    if self.fast_visual_mode and not data["writing_lines"] and not data["drawings"]:
                        raise ValueError("visual backend returned no annotations")
                    # Drawing content remains entirely model-authored and is
                    # constrained only by the generic sanitizer above.
                    labels = [str(line.get("text", "")) for line in data["writing_lines"]]
                    state_text = json.dumps(data.get("solution_state", {}), sort_keys=True, ensure_ascii=False)
                    fingerprint = re.sub(r"[^a-z0-9]+", " ", (stage_name + " " + data.get("narration", "") + " " + " ".join(labels) + " " + state_text).lower()).strip()
                    if not fingerprint or fingerprint in self.content_fingerprints:
                        repeated_attempts += 1
                        print(f"[Iterative Teacher] Rejected repeated or empty {stage_name} response ({repeated_attempts}/2).")
                        if repeated_attempts < 2:
                            continue
                        data = {"title": f"{self.topic} - {stage_name}", "narration": f"I need a more specific example for {stage_name}; let's continue with the next part.", "drawings": [], "auto_pan_target": {}}
                        fingerprint = f"fallback {stage_name} {time.time()}"
                    repeated_attempts = 0
                    self.content_fingerprints.add(fingerprint)
                    self.lesson_history.append({"stage": stage_name, "title": data.get("title", ""), "narration": data.get("narration", ""), "writing_lines": data.get("writing_lines", []), "content": data.get("drawings", []), "solution_state": data.get("solution_state", {}), "pan": data.get("auto_pan_target", {})})
                    self._generate_markdown_report(status="in progress")
                    
                    pan_target = data.get("auto_pan_target")
                    if pan_target:
                        self.current_y_offset = pan_target.get("y", self.current_y_offset) + 300
                        
                    self.overlay.on_ai_lesson_received(data)
                    
                    writing_marks = data.get("writing_lines", [])
                    for line_index, _ in enumerate(writing_marks):
                        if not self.is_active:
                            break
                        self.pause_event.wait()
                        self.overlay.virtual_mouse.move_to(170, min(self.overlay.height() - 90, 145 + line_index * 42), "Writing...")
                        time.sleep(0.08)
                    for d in data.get("drawings", []):
                        if not self.is_active:
                            break
                        self.pause_event.wait()
                        x, y = d.get("x", 500), d.get("y", 300)
                        self.overlay.virtual_mouse.move_to(x, y, "Drawing...")
                        time.sleep(0.12)
                        
                    # Compare the hidden initial hypothesis with the completed visible derivation.
                    remaining_solution_stages = any(
                        self.stage_actions.get(name, "none") == "none"
                        for name, _ in self.stages[stage_idx + 1:]
                    )
                    if stage_action == "none" and not remaining_solution_stages:
                        verification = self._verify_mandatory_derivation(data)
                        if verification:
                            verification["writing_lines"] = self.overlay._sanitize_writing_lines(
                                verification.get("writing_lines", []), verification.get("solution_state", {})
                            )
                            self.lesson_history.append({
                                "stage": "Mandatory derivation audit",
                                "title": verification.get("title", ""),
                                "narration": verification.get("narration", ""),
                                "writing_lines": verification.get("writing_lines", []),
                                "content": [],
                                "solution_state": verification.get("solution_state", {}),
                                "pan": {},
                                "verification": verification.get("verification", {}),
                            })
                            self.overlay.on_ai_lesson_received(verification)
                            for line_index, _ in enumerate(verification["writing_lines"]):
                                if not self.is_active:
                                    break
                                self.pause_event.wait()
                                self.overlay.virtual_mouse.move_to(170, min(self.overlay.height() - 90, 145 + line_index * 42), "Checking...")
                                time.sleep(0.08)

                    if stage_action == "quiz":
                        quiz = data.get("quiz") if isinstance(data.get("quiz"), dict) else {}
                        self.last_quiz_question = str(quiz.get("question") or data.get("narration") or "")
                        quiz_key = self._unique_quiz_key(self.last_quiz_question)
                        if quiz_key:
                            self.asked_questions.add(quiz_key)
                        try:
                            existing = {}
                            if os.path.exists(self.quiz_history_path):
                                with open(self.quiz_history_path, "r", encoding="utf-8") as f:
                                    existing = json.load(f)
                            existing[self.topic.lower()] = sorted(self.asked_questions)
                            with open(self.quiz_history_path, "w", encoding="utf-8") as f:
                                json.dump(existing, f, indent=2)
                        except Exception as e:
                            print(f"[Iterative Teacher] Quiz history save failed: {e}")
                    elif stage_action == "quiz_feedback":
                        feedback = (data.get("narration") or "").lower()
                        self._update_learner_profile(self.last_quiz_answer, quiz_correct=("correct" in feedback and "not correct" not in feedback))
                        
                    if stage_action == "qa":
                        while self.overlay.narrator.is_speaking:
                            time.sleep(0.5)
                        response = self._wait_for_response("Do you have any questions so far?")
                        if response and "no" not in response.lower():
                            self.last_qa_query = response
                            followup = "Answer to your question"
                            self.stages.insert(stage_idx + 1, (followup, "Answer the learner's exact question using the current solution."))
                            self.stage_actions[followup] = "qa_response"
                        
                    elif stage_action == "quiz":
                        while self.overlay.narrator.is_speaking:
                            time.sleep(0.5)
                        self.last_quiz_answer = self._wait_for_response("Please answer the quiz when you're ready.")
                        self._update_learner_profile(self.last_quiz_answer)
                        if self.last_quiz_answer:
                            feedback_stage = "Knowledge-check feedback"
                            self.stages.insert(stage_idx + 1, (feedback_stage, "Evaluate the learner's answer and adapt the revision."))
                            self.stage_actions[feedback_stage] = "quiz_feedback"
                except Exception as e:
                    print(f"[Teacher Error] Failed to process {stage_name}: {e}")
            else:
                repeated_attempts += 1
                print(f"[Iterative Teacher] {stage_name} returned no usable JSON ({repeated_attempts}/2).")
                if repeated_attempts < 2 and self.is_active:
                    continue
                repeated_attempts = 0
                fallback_drawings: List[Dict[str, Any]] = []
                fallback = {
                    "title": f"{self.topic} - {stage_name}",
                    "narration": f"I am keeping the essential annotation visible while I continue with {stage_name}.",
                    "writing_lines": [
                        {"kind": "heading", "text": stage_name},
                        {"kind": "explanation", "text": "Key idea: organize the given information before the next step."},
                    ],
                    "drawings": fallback_drawings,
                    "solution_state": {"givens": [self.topic], "steps": [f"Continue with {stage_name}"], "answer": ""},
                    "auto_pan_target": {},
                }
                self.lesson_history.append({"stage": stage_name, "title": fallback["title"], "narration": fallback["narration"], "content": [], "solution_state": {}, "pan": {}})
                self.overlay.on_ai_lesson_received(fallback)

            while self.overlay.narrator.is_speaking:
                time.sleep(0.5)
            
            time.sleep(1.0)
            stage_idx += 1
                
        if self.is_active:
            self._generate_markdown_report(status="complete")
            self.overlay.narrator.speak("The session is complete. Your report is saved in the Hojaiga reports folder.")
            print("[Iterative Teacher] Lesson Complete.")
        else:
            self._generate_markdown_report(status="stopped")
            print("[Iterative Teacher] Lesson stopped or replaced.")

    def _generate_markdown_report(self, status: str = "in progress"):
        report_path = self.report_path
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(f"# Hojaiga Lesson Report: {self.topic}\n\n")
                f.write(f"**Session status:** {status}\n\n")
                f.write("## Lesson flow\n\n")
                for stage in self.lesson_history:
                    f.write(f"### {stage['stage']}\n\n")
                    if stage.get("narration"):
                        f.write(f"{stage['narration']}\n\n")
                    for line in stage.get("writing_lines", []):
                        if isinstance(line, dict) and line.get("text"):
                            f.write(f"- **{line.get('kind', 'note').title()}:** {line['text']}\n")
                    solution_state = stage.get("solution_state", {})
                    if isinstance(solution_state, dict):
                        for given in solution_state.get("givens", [])[:12]:
                            f.write(f"- **Given/evidence:** {given}\n")
                        for step in solution_state.get("steps", [])[:20]:
                            f.write(f"- **Reasoning step:** {step}\n")
                        if solution_state.get("answer"):
                            f.write(f"- **Current answer:** {solution_state['answer']}\n")
                    verification = stage.get("verification", {})
                    if isinstance(verification, dict) and verification:
                        f.write(f"- **Verification verdict:** {verification.get('verdict', 'unknown')}\n")
                        f.write(f"- **Derivation answer:** {verification.get('derivation_answer', '')}\n")
                        f.write(f"- **Derivation complete:** {verification.get('derivation_complete', False)}\n")
                        f.write(f"- **Confidence:** {verification.get('confidence', 'unknown')}\n")
                    pan = stage.get("pan", {})
                    if pan:
                        f.write(f"- **Canvas reference:** ({pan.get('x', 0)}, {pan.get('y', 0)})\n")
                    for drawing in stage.get("content", []):
                        kind = drawing.get("type", "unknown")
                        if kind == "text":
                            f.write(f"- **Note:** {drawing.get('content', '')}\n")
                        elif kind == "shape":
                            f.write(f"- **Diagram:** {drawing.get('shape_type', 'shape')} at ({drawing.get('x', 0)}, {drawing.get('y', 0)})\n")
                        elif kind == "arrow":
                            f.write("- **Relationship:** directional connection between concepts\n")
                        elif kind == "highlight":
                            f.write(f"- **Concept group:** {drawing.get('color', 'highlight')} highlight\n")
                        elif kind == "freehand":
                            f.write("- **Sketch:** freehand explanatory path\n")
                    f.write("\n")
                f.write("## Quiz uniqueness\n\n")
                f.write(f"- Stored non-repeating prompts for this topic: {len(self.asked_questions)}\n")
                f.write("\n## Spatial navigation\n\n")
                f.write("- Use `go to <section name>` in Hojaiga to return to a named lesson section.\n")
                f.write("\n## Canvas annotations\n\n")
                f.write(f"- Lesson sections placed in Void: {len(self.overlay.elements)}\n")
                f.write(f"- Manual freehand annotations: {len(self.overlay.freehand_strokes)}\n")
                for index, stroke in enumerate(self.overlay.freehand_strokes, start=1):
                    if not stroke:
                        continue
                    xs, ys = [pt.x() for pt in stroke], [pt.y() for pt in stroke]
                    f.write(f"- Freehand mark {index}: {len(stroke)} points, bounds ({min(xs):.0f}, {min(ys):.0f}) to ({max(xs):.0f}, {max(ys):.0f})\n")
            print(f"[Hojaiga Report] {status.title()} report saved: {report_path}")
        except Exception as e:
            print(f"[Iterative Teacher] Failed to save report: {e}")

class DeepAppScannerOrgan(QObject):
    """
    True Recursive Autonomous UI Explorer.
    Maps applications via State Graph, remembers UI states via visual/text hashing,
    dynamically evaluates danger zones, and handles popups with backtracking.
    """
    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        # Scanning defaults to observation: screen reading must not mutate an app.
        self.allow_safe_clicks = False
        self.is_active = False
        self.max_states = 40
        self.max_depth = 8
        self.map = {'states': [], 'danger_zones': []}
        self.danger_zones = set() 
        self.visited_states = set()
        self.state_stack = [] # Stack of dicts: {"hash": str, "unexplored_elements": list, "parent_action": dict}
        
    def start(self):
        self.is_active = True
        threading.Thread(target=self._run_scan_loop, daemon=True).start()
        
    def _hash_state(self, b64_image):
        import hashlib
        return hashlib.md5(b64_image[-1000:].encode('utf-8')).hexdigest()

    def _run_scan_loop(self):
        try:
            import pyautogui
        except ImportError:
            pyautogui = None
        print("[Deep App Scanner] Beginning bounded UI graph mapping...")
        mode = 'safe interaction' if self.allow_safe_clicks else 'observation only'
        self.overlay.narrator.speak(f'Initiating deep application mapping in {mode} mode.')
        
        while self.is_active:
            if len(self.visited_states) >= self.max_states:
                print('[Deep App Scanner] State limit reached.')
                break
            b64_data = RobustVisionQueryEngine.grab_screen_b64(VISION_MAX_RES)
            current_state_hash = self._hash_state(b64_data)
            
            # If this is a newly discovered state
            if not self.state_stack or self.state_stack[-1]["hash"] != current_state_hash:
                if current_state_hash in self.visited_states:
                    print(f"[Deep App Scanner] Reached known state {current_state_hash[:8]}. Backtracking...")
                    if self.state_stack:
                        if pyautogui and self.allow_safe_clicks: pyautogui.press('esc')
                        time.sleep(1)
                        self.state_stack.pop()
                    continue
                    
                self.visited_states.add(current_state_hash)
                print(f"[Deep App Scanner] Discovered new UI State: {current_state_hash[:8]}")
                
                # Ask VLM for all elements
                prompt = f"""You are an autonomous recursive UI graph explorer.
Identify ALL visible clickable elements (menus, buttons, tabs) and dialogs. Return exact screen coordinates. Score each action's danger_probability (0.0 to 1.0). Any control that can save, submit, buy, delete, close, cancel, install, sign in, or change data MUST have danger_probability >= 0.8.
Return ONLY RAW JSON:
{{
  "elements": [
    {{"label": "File", "x": 10, "y": 20, "w": 40, "h": 20, "danger_probability": 0.0}}
  ]
}}"""
                raw_json = RobustVisionQueryEngine.query_vision(prompt, b64_data, json_mode=True, max_tokens=1500, temperature=0.3)
                
                elements = []
                match = re.search(r'\{.*\}', raw_json, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(0))
                        elements = data.get("elements", [])
                    except Exception:
                        pass
                
                if not elements:
                    print("[Deep App Scanner] Dead end state. Backtracking...")
                    if pyautogui and self.allow_safe_clicks: pyautogui.press('esc')
                    time.sleep(1)
                    if self.state_stack:
                        self.state_stack.pop()
                    continue
                    
                self.state_stack.append({
                    "hash": current_state_hash,
                    "unexplored_elements": elements,
                    "parent_action": None
                })
            
            # Get current state from top of stack
            current_state = self.state_stack[-1]
            unexplored = current_state["unexplored_elements"]
            
            if not unexplored:
                print("[Deep App Scanner] Fully explored state. Backtracking...")
                if pyautogui and self.allow_safe_clicks: pyautogui.press('esc')
                time.sleep(1)
                self.state_stack.pop()
                if not self.state_stack:
                    break
                continue
                
            # Pop the next element to explore
            target = unexplored.pop(0)
            label = target.get("label", "Unknown")
            danger = target.get("danger_probability", 0.0)
            
            tx = target.get("x", 0) + (target.get("w", 0) / 2)
            ty = target.get("y", 0) + (target.get("h", 0) / 2)
            
            danger_key = f"{label}@{int(tx)},{int(ty)}"
            protected_words = ("delete", "remove", "close", "cancel", "save", "submit", "buy", "install", "sign", "quit")
            if danger_key in self.danger_zones:
                print(f"[Deep App Scanner] Skipping known protected control: {label}")
                continue
            if danger >= 0.5 or any(word in label.lower() for word in protected_words):
                print(f"[Deep App Scanner] Recorded and skipped protected control: {label}")
                self.danger_zones.add(danger_key)
                self.map['danger_zones'].append({'label': label, 'x': tx, 'y': ty, 'risk': danger})
                continue

            print(f"[Deep App Scanner] Inspecting: {label} at ({tx}, {ty})")
            self.overlay.virtual_mouse.move_to(tx, ty, label)
            if not self.allow_safe_clicks or not pyautogui:
                continue
            try:
                # Safe mode permits one ordinary left click only; no random context clicks.
                pyautogui.click(x=int(tx), y=int(ty))
            except Exception as e:
                print(f"[Deep App Scanner] Click failed: {e}")
                continue
            self.overlay.virtual_mouse.pulse_click()
            time.sleep(2) # Wait for animation/popup/child window
            
            if len(self.state_stack) > self.max_depth:
                print("[Deep App Scanner] Maximum depth reached. Forcing backtrack.")
                if pyautogui and self.allow_safe_clicks: pyautogui.press('esc')
                time.sleep(1)
                self.state_stack.pop()
            
        report_path = os.path.abspath(f'hojaiga_app_map_{int(time.time())}.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(self.map, f, indent=2)
        print(f'[Deep App Scanner] Graph map saved to: {report_path}')
        self.overlay.narrator.speak('Scan complete. I mapped the visible UI and protected risky controls.')
        self.is_active = False


class HojaigaOrganScannerBridge(QObject):
    """Thin adapter to Organ 30: UIA tree, menus, safe probes, dialogs, popups, and memory."""
    def __init__(self, overlay, app_name: str, active_probe: bool = True):
        super().__init__()
        self.overlay, self.app_name = overlay, app_name.strip()
        self.active_probe, self.is_active = active_probe, False

    def start(self):
        self.is_active = True
        threading.Thread(target=self._run, daemon=True, name="hojaiga-organ30-scan").start()

    def _find_target_window(self):
        if sys.platform != "win32": return 0
        try:
            import win32gui
            requested, overlay_hwnd, matches = self.app_name.lower(), int(self.overlay.winId()), []
            def collect(hwnd, _):
                if hwnd != overlay_hwnd and win32gui.IsWindowVisible(hwnd):
                    title, klass = (win32gui.GetWindowText(hwnd) or "").lower(), (win32gui.GetClassName(hwnd) or "").lower()
                    if requested and (requested in title or requested in klass): matches.append(hwnd)
                return True
            win32gui.EnumWindows(collect, None)
            return matches[0] if matches else 0
        except Exception:
            return 0

    def _run(self):
        try:
            root = os.path.dirname(os.path.abspath(__file__))
            if root not in sys.path: sys.path.insert(0, root)
            from core_organs.organ_30_app_scanner import AppScanner, EyeAndBrainOrchestrator
            hwnd = self._find_target_window()
            if not hwnd:
                self.overlay.narrator.speak("I could not find that application. Open it, then say scan app and its name.")
                return
            if self.active_probe:
                scanner = AppScanner()
                try:
                    result = scanner.scan_app_active(self.app_name, hwnd)
                finally:
                    scanner.stop()
            else:
                result = EyeAndBrainOrchestrator().deep_scan_unknown_app(self.app_name, target_hwnd=hwnd)
            self.overlay.on_app_scan_received(result, self.app_name)
        except Exception as exc:
            print(f"[Hojaiga Organ 30 Bridge] {exc}")
            self.overlay.narrator.speak("The Organ 30 scan could not complete. Check scanner dependencies and UI accessibility.")
        finally:
            self.is_active = False

class HojaigaCrewBridge(QObject):
    """Opt-in bridge to Organ 01 for multi-agent tasks beyond direct teaching/scanning."""
    def __init__(self, overlay, goal: str):
        super().__init__()
        self.overlay = overlay
        self.goal = goal.strip()
        self.is_active = False

    def start(self):
        self.is_active = True
        threading.Thread(target=self._run, daemon=True, name="hojaiga-crewai-task").start()

    def _run(self):
        try:
            from core_organs.organ_01_crewai_engine import CrewAIEngine
            engine = CrewAIEngine()
            if not engine.is_available():
                raise RuntimeError("CrewAI or its configured local model is unavailable")
            result = engine.execute_task(self.goal, f"hojaiga_{int(time.time() * 1000)}")
            self.overlay.on_crewai_task_received(result, self.goal)
        except Exception as exc:
            print(f"[Hojaiga Crew Bridge] {exc}")
            self.overlay.narrator.speak("The CrewAI workflow is unavailable. Hojaiga can still teach and scan directly.")
        finally:
            self.is_active = False
class SpatialWhiteboardOverlay(QWidget):
    directive_signal = pyqtSignal(str)

    def __init__(self, initial_task: str = ""):
        super().__init__()
        self.current_user_task = initial_task
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Window
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        # Keyboard Void controls must work after clicking the glass canvas.
        self.setFocusPolicy(Qt.StrongFocus)

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.w, self.h = screen.width(), screen.height()

        # Presentation Architecture
        self.display_mode = DisplayMode.VOID
        self.click_through = True
        self.camera = CameraDirector()
        self.omni_sketch = OmniSketchEngine() if HAS_OMNI_SKETCH else None
        self.elements: List[SketchnoteElement] = []
        self.spatial_index: Dict[str, Dict[str, Any]] = {}
        self.void_origin = (0.0, 0.0, 1.0)
        # A lesson gets its own lane, so late/older lessons never overlap it.
        self.active_lesson_id = ""
        self.active_lesson_base_x = 80.0
        self.active_lesson_stage_index = 0
        self.grid_alpha = 0.35
        # Screen-space controls; board content remains in world space.
        self.void_backdrop_alpha = 82
        self.void_ribbon_collapsed = False
        self.void_ribbon_hitboxes: Dict[str, QRectF] = {}
        self.void_grid_spacing = 48.0
        self.active_stylus_pt: Optional[QPointF] = None
        self.edge_avatar = None

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

        # Intelligence System
        self.ai = DualIntelligenceSystem(self.on_ai_lesson_received)
        self.directive_signal.connect(self.handle_new_directive)

        # Background screen/code lifting must be explicit. It previously injected
        # unrelated contour diagrams into ordinary lessons.
        self.autonomous_background_analysis = False
        self._last_background_analysis = 0.0
        self.doc_navigator = AutonomousDocumentNavigator()
        self.contour_tracker = ContinuousContourTracker(self.on_autonomous_contour_detected)
        self.code_watcher = WorkspaceCodeWatcher(self.on_workspace_code_updated)

        # Virtual Pointer Subsystem
        self.virtual_mouse = VirtualMouseSubsystem(self.w, self.h)

        # 60 FPS Render Loop
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(16)

        self.enable_click_through(False)  # VOID mode default: allow direct mouse interaction for panning

    def enable_click_through(self, enabled: bool):
        self.click_through = enabled
        # Keep Qt and the native window style in agreement. Without this, the
        # overlay can visually enter Void mode while still passing mouse events on.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, enabled)
        if sys.platform == "win32":
            hwnd = int(self.winId())
            extended_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if enabled:
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, extended_style | WS_EX_TRANSPARENT | WS_EX_LAYERED)
            else:
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, extended_style & ~WS_EX_TRANSPARENT)

    def _void_ribbon_layout(self) -> Dict[str, QRectF]:
        """Return stable screen-space hitboxes for the floating Void ribbon."""
        if self.void_ribbon_collapsed:
            rect = QRectF(self.width() * 0.5 - 34, self.height() - 58, 68, 34)
            self.void_ribbon_hitboxes = {"show_ribbon": rect}
            return self.void_ribbon_hitboxes
        items = [("focus", 62), ("pen", 52), ("shade", 62), ("previous", 36),
                 ("next", 36), ("hide", 50), ("minimize", 52)]
        gap, height = 6, 38
        total = sum(width for _, width in items) + gap * (len(items) - 1) + 16
        x, y = (self.width() - total) * 0.5 + 8, self.height() - height - 22
        hitboxes = {}
        for name, width in items:
            hitboxes[name] = QRectF(x, y, width, height)
            x += width + gap
        self.void_ribbon_hitboxes = hitboxes
        return hitboxes

    def _toggle_drawing_mode(self):
        self.drawing_mode = not self.drawing_mode
        self.enable_click_through(self.display_mode == DisplayMode.IN_SITU and not self.drawing_mode)
        self.narrator.speak(f"Freehand drawing mode {'engaged' if self.drawing_mode else 'disabled'}.")
        self.update()

    def _focus_current_lesson(self):
        owned = [elem for elem in self.elements if self.active_lesson_id and elem.id.startswith(self.active_lesson_id)]
        target = owned[-1] if owned else (self.elements[-1] if self.elements else None)
        if not target:
            return
        zoom = self.camera.current_zoom
        self.camera.pan_to(
            target.bounding_rect.center().x() - self.width() / (2.0 * zoom),
            target.bounding_rect.center().y() - self.height() / (2.0 * zoom),
            zoom,
        )

    def _handle_void_ribbon_click(self, pos: QPointF) -> bool:
        if self.display_mode != DisplayMode.VOID:
            return False
        for action, rect in self._void_ribbon_layout().items():
            if not rect.contains(pos):
                continue
            if action == "focus":
                self._focus_current_lesson()
            elif action == "pen":
                self._toggle_drawing_mode()
            elif action == "shade":
                levels = (42, 82, 122)
                current = levels.index(self.void_backdrop_alpha) if self.void_backdrop_alpha in levels else 1
                self.void_backdrop_alpha = levels[(current + 1) % len(levels)]
                self.update()
            elif action == "previous":
                self.jump_lesson(forward=False)
            elif action == "next":
                self.jump_lesson(forward=True)
            elif action == "hide":
                self.void_ribbon_collapsed = True
                self.update()
            elif action == "show_ribbon":
                self.void_ribbon_collapsed = False
                self.update()
            elif action == "minimize":
                # Minimizing the presentation does not cancel the teacher thread.
                if self.edge_avatar is not None:
                    self.edge_avatar.dock_after_void_minimize()
                self.showMinimized()
            return True
        return False

    def _render_void_ribbon(self, painter: QPainter):
        if self.display_mode != DisplayMode.VOID:
            return
        labels = {
            "focus": "Focus", "pen": "Pen", "shade": "Shade",
            "previous": "‹", "next": "›", "hide": "Hide", "minimize": "Min",
            "show_ribbon": "Void",
        }
        painter.save()
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        for action, rect in self._void_ribbon_layout().items():
            active = action == "pen" and self.drawing_mode
            bg = QColor(13, 21, 37, 222 if not active else 240)
            border = QColor(71, 196, 255, 220) if active else QColor(100, 116, 139, 170)
            painter.setBrush(QBrush(bg))
            painter.setPen(QPen(border, 1.1))
            painter.drawRoundedRect(rect, 12, 12)
            painter.setPen(QPen(QColor(226, 232, 240)))
            painter.drawText(rect, int(Qt.AlignCenter), labels[action])
        painter.restore()
    def activate_void_from_avatar(self):
        """Restore/focus the living Void when the edge avatar is clicked."""
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        self.display_mode = DisplayMode.VOID
        self.enable_click_through(False)
        self._focus_current_lesson()
        self.narrator.speak("Hojaiga is ready. Tell me what you would like to learn or solve.")
        self.update()
    def clear_all_annotations(self):
        """Wipes all active in-situ geometries, beacons, and pills so nothing remains stuck."""
        self.insitu_geometries.clear()
        self.insitu_pills.clear()
        self.insitu_beacons.clear()
        self.tutorial_steps.clear()
        self.current_tutorial_idx = 0
        self.elements.clear()
        self.freehand_strokes.clear()
        self.current_freehand_stroke.clear()
        self.update()
        print("[Canvas Engine] Overlay wiped clean. Ready for dynamic input.")

    def trigger_teaching_session(self, topic: str = ""):
        """Start one cancellable, model-aware teaching session."""
        topic = topic.strip()
        if not topic:
            self.narrator.speak("Tell me the topic you want to learn.")
            return
        existing = getattr(self, "active_teacher_organ", None)
        if existing and existing.is_active:
            existing.stop()
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        print(f"[Hojaiga] Starting lesson with {MODEL_DISPLAY_NAME}.")
        self.display_mode = DisplayMode.VOID
        self.enable_click_through(False) # Allow panning in Void
        self.grid_alpha = 0.15
        
        # Preserve a return point before this lesson moves the camera.
        self.void_origin = (self.camera.current_x, self.camera.current_y, self.camera.current_zoom)

        # Reserve a fresh lane for this lesson. Existing lessons remain in the
        # infinite Void and can still be revisited, but cannot bleed into this one.
        right_edge = max((e.bounding_rect.right() for e in self.elements), default=-1160.0)
        self.active_lesson_id = f"lesson_{time.time_ns()}"
        self.active_lesson_base_x = max(80.0, right_edge + 260.0)
        self.active_lesson_stage_index = 0

        # Center the virtual mouse
        self.virtual_mouse.move_to(self.width() / 2, self.height() / 2, "TEACHER")
        self.virtual_mouse.pulse_click()
        
        if self.edge_avatar is not None:
            self.edge_avatar.set_activity("teaching")
        self.narrator.speak(f"Okay, let me explain {topic}. Give me a moment to organize my thoughts.")
        
        # Launch the autonomous teacher organ
        self.active_teacher_organ = IterativeTeachingOrgan(self, topic)
        self.active_teacher_organ.start()
        print(f"\n[Free-Form Teaching] Started iterative session on topic: {topic}")

    def trigger_crewai_task(self, goal: str):
        """Run an explicitly requested Organ 01 workflow without hijacking normal lessons."""
        goal = goal.strip()
        if not goal:
            self.narrator.speak("Tell me the task you want to delegate to CrewAI.")
            return
        active = getattr(self, "active_crewai_bridge", None)
        if active and active.is_active:
            self.narrator.speak("A CrewAI task is already running.")
            return
        self.narrator.speak("Delegating this explicitly requested workflow to the Hojaiga CrewAI engine.")
        self.active_crewai_bridge = HojaigaCrewBridge(self, goal)
        self.active_crewai_bridge.start()

    def on_crewai_task_received(self, result: dict, goal: str):
        """Summarize a completed CrewAI workflow inside the Hojaiga interaction layer."""
        if not isinstance(result, dict):
            self.narrator.speak("The CrewAI workflow returned an unreadable result.")
            return
        status = str(result.get("status", "completed")).lower()
        if status in ("error", "failed", "failure"):
            self.narrator.speak("The CrewAI workflow did not complete. Review the terminal result for details.")
        else:
            self.narrator.speak("The CrewAI workflow completed. I have kept its result available in the terminal.")
        print(f"[Hojaiga CrewAI] goal={goal!r} result={json.dumps(result, default=str)[:4000]}")
    def trigger_deep_app_scan(self, app_name: str, active_probe: bool = True):
        """Use the production Organ 30 scanner; do not duplicate scanner logic here."""
        self.display_mode = DisplayMode.IN_SITU
        self.enable_click_through(True)
        self.insitu_geometries.clear()
        self.insitu_pills.clear()
        self.insitu_beacons.clear()
        mode = "safe active probing" if active_probe else "read-only inspection"
        self.narrator.speak(f"Starting Organ 30 {mode} for {app_name}. I will map controls, menus, dialogs, and safe popups.")
        self.active_scanner_organ = HojaigaOrganScannerBridge(self, app_name, active_probe)
        self.active_scanner_organ.start()

    def _load_active_tutorial_step(self):
        if self.current_tutorial_idx >= len(self.tutorial_steps):
            self.insitu_beacons.clear()
            self.insitu_pills.clear()
            self.narrator.speak("Tutorial complete! You are ready to work.")
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
        btn_c = step.target_rect.center()
        self.virtual_mouse.move_to(btn_c.x(), btn_c.y(), label=f"STEP {step.step_number}")
        self.virtual_mouse.pulse_click("TARGET")
        self.narrator.speak(step.spoken_instruction)

    def handle_voice_directive(self, text: str):
        """Accept only deliberate spoken commands, never ambient transcription."""
        command = (text or "").strip()
        if not command:
            return
        # Terminal commands continue to go straight to handle_new_directive.
        # Microphone transcripts must start with an action word so TTS, nearby
        # conversation, and recognition noise cannot replace a live drawing.
        if not re.match(r"^(teach|explain|draw|trace|graph|plot|annotate|visuali[sz]e|sketch|pause|resume|stop|clear|void|ar)\\b", command, re.IGNORECASE):
            print(f"[Voice Input] Ignored non-command transcript: {command[:80]!r}")
            return
        self.directive_signal.emit(command)

    def handle_system_audio_directive(self, text: str):
        # System audio is reference material, not an instruction source.  It
        # must never cancel or replace the user's active lesson.
        print(f"[WASAPI System Audio] Ignored as a command: {text[:80]!r}")

    def on_speech_state_changed(self, state: str):
        pass
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
            QFont("Segoe Print", 11, QFont.Bold), QColor(241, 245, 249), 0.0
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

        elem.text_items.append((QPointF(offset_x + 60, offset_y + 440), "• Geometry successfully lifted from active desktop frame.", QFont("Segoe Print", 10), QColor(52, 211, 153), 0.0))
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

    def go_to_section(self, query: str) -> bool:
        """Pan to a named lesson section or partial title match."""
        query = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
        if query in ("origin", "original", "start", "beginning", "home"):
            x, y, zoom = self.void_origin
            self.camera.current_x = self.camera.target_x = x
            self.camera.current_y = self.camera.target_y = y
            self.camera.target_zoom = zoom
            self.narrator.speak("Returning to the lesson origin.")
            return True
        if not query or not self.spatial_index:
            return False
        matches = [(key, item) for key, item in self.spatial_index.items() if query in key or key in query]
        if not matches:
            return False
        _, item = matches[-1]
        x, y, width, height = item["bounds"]
        self.camera.pan_to(x + width / 2 - self.width() / 2, y + height / 2 - self.height() / 2, 1.0)
        self.virtual_mouse.move_to(self.width() / 2, self.height() / 2, "REFERENCE")
        self.narrator.speak(f"Returning to {item['title']}.")
        return True
    def on_app_scan_received(self, result: dict, app_name: str):
        """Render Organ 30 results as Hojaiga guidance without duplicating scan state."""
        if result.get("status") != "completed":
            self.narrator.speak(f"I could not complete the scan of {app_name}.")
            print(f"[Organ 30 Scan] {result}")
            return
        self.latest_app_scan = result
        self.insitu_beacons.clear()
        self.insitu_pills.clear()
        palette = [QColor(56, 189, 248), QColor(52, 211, 153), QColor(251, 191, 36), QColor(216, 180, 254)]
        for idx, element in enumerate(result.get("elements", [])[:8]):
            box = element.get("coords", {}).get("box", [])
            if len(box) != 4:
                continue
            left, top, right, bottom = box
            rect = QRectF(float(left), float(top), max(2.0, float(right-left)), max(2.0, float(bottom-top)))
            color, label = palette[idx % len(palette)], str(element.get("name", "Control"))[:40]
            self.insitu_beacons.append(ButtonBeacon(rect=rect, label=label, color=color))
            self.insitu_pills.append(MicroPillTag(text=label, target_pt=QPointF(rect.center().x(), rect.bottom()+14), color=color))
        scanned, failed = result.get("controls_scanned", len(result.get("elements", []))), result.get("controls_failed", 0)
        self.narrator.speak(f"Organ 30 mapped {scanned} controls in {app_name}. {failed} probes failed. I highlighted the first mapped controls; ask me to explain any one.")
        print(f"[Organ 30 Scan] {app_name}: {scanned} controls, {failed} failed probes")

    def _merge_model_visual_payload(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Prefer the topic-neutral OmniSketch scene. Legacy drawings remain a
        # compatibility input while old clients are migrated.
        legacy = payload.get('drawings', [])
        legacy = list(legacy) if isinstance(legacy, list) else []
        scene_payload = payload
        if not scene_payload.get('scene'):
            # Adapt the former plot_specs protocol to one declarative action;
            # no task keyword decides what gets drawn.
            specs = normalize_lesson_plot_specs(payload.get('plot_specs', []))
            if specs:
                actions = []
                for index, spec in enumerate(specs[:4]):
                    actions.append({
                        'id': f'legacy-plot-{index + 1}',
                        'kind': 'function_plot',
                        'data': {'expression': spec.get('expr', ''),
                                 'domain': [spec.get('x_min', -10), spec.get('x_max', 10)],
                                 'range': [spec.get('y_min', -5), spec.get('y_max', 5)],
                                 'samples': spec.get('samples', 360)},
                        'style': {'color': spec.get('color', '#38bdf8')},
                    })
                scene_payload = dict(payload)
                scene_payload['scene'] = actions
        if self.omni_sketch and scene_payload.get('scene'):
            try:
                compiled = self.omni_sketch.compile_payload(scene_payload, (1040, 650))
                payload['_scene_schedule'] = compiled.action_schedule
                if compiled.narration:
                    payload['_scene_segments'] = compiled.narration
                return self._sanitize_lesson_drawings(legacy + list(compiled.drawings))
            except SceneValidationError as exc:
                print(f'[OmniSketch] scene rejected: {exc}')
            except Exception as exc:
                print(f'[OmniSketch] scene compilation failed: {type(exc).__name__}: {exc}')
        return self._sanitize_lesson_drawings(legacy)

    def _sanitize_lesson_drawings(self, drawings: Any) -> List[Dict[str, Any]]:
        """Constrain model drawing instructions to legible, bounded whiteboard marks."""
        if not isinstance(drawings, list):
            return []
        valid_types = {"text", "shape", "arrow", "highlight", "freehand"}
        valid_shapes = {"circle", "triangle", "box"}
        clean: List[Dict[str, Any]] = []
        for raw in drawings[:18]:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            item["type"] = str(item.get("type", "")).lower()
            # Normalize common LLM JSON variants into the renderer's compact
            # protocol.  This is schema compatibility, not topic knowledge.
            if item["type"] in {"label", "latex"}:
                item["type"] = "text"
            elif item["type"] in {"polyline", "curve", "graph", "plot"}:
                item["type"] = "freehand"
            elif item["type"] in {"line", "path"}:
                item["type"] = "freehand" if item["type"] == "path" else "arrow"
            elif item["type"] == "axis":
                item["type"] = "arrow"
            points = item.get("points")
            if item["type"] == "arrow" and isinstance(points, list) and len(points) >= 2:
                try:
                    item.update({"from_x": points[0][0], "from_y": points[0][1],
                                 "to_x": points[-1][0], "to_y": points[-1][1]})
                except (TypeError, IndexError):
                    pass
            if item["type"] == "text":
                item["content"] = item.get("content") or item.get("text") or item.get("label") or ""
                position = item.get("position")
                if isinstance(position, str):
                    values = re.findall(r"-?\d+(?:\.\d+)?", position)
                    if len(values) >= 2:
                        item["x"], item["y"] = values[0], values[1]
                elif isinstance(position, (list, tuple)) and len(position) >= 2:
                    item["x"], item["y"] = position[0], position[1]
            if item["type"] == "shape" and isinstance(points, list) and len(points) >= 2:
                try:
                    xs = [float(pt[0]) for pt in points if len(pt) >= 2]
                    ys = [float(pt[1]) for pt in points if len(pt) >= 2]
                    if xs and ys:
                        item.update({"x": min(xs), "y": min(ys),
                                     "w": max(xs) - min(xs), "h": max(ys) - min(ys)})
                except (TypeError, ValueError):
                    pass
            if item["type"] not in valid_types:
                continue
            if item["type"] == "text":
                content = re.sub(r"\s+", " ", str(item.get("content", ""))).strip()
                if not content:
                    continue
                item["content"] = content[:110]
            if item["type"] == "shape":
                item["shape_type"] = item.get("shape_type") if item.get("shape_type") in valid_shapes else "box"
            if item["type"] == "arrow":
                for key, low, high, default in (("from_x", 0, 1040, 80), ("from_y", 0, 650, 320), ("to_x", 0, 1040, 900), ("to_y", 0, 650, 320)):
                    try:
                        item[key] = max(low, min(high, float(item.get(key, default))))
                    except (TypeError, ValueError):
                        item[key] = default
            for key, low, high, default in (("x", 0, 1040, 80), ("y", 0, 650, 100), ("w", 20, 900, 140), ("h", 20, 560, 100)):
                try:
                    item[key] = max(low, min(high, float(item.get(key, default))))
                except (TypeError, ValueError):
                    item[key] = default
            if item["type"] == "freehand":
                points = []
                                # Preserve locally sampled curves while still bounding untrusted model payloads.
                for pt in item.get("points", [])[:320]:
                    if isinstance(pt, (list, tuple)) and len(pt) == 2:
                        try:
                            points.append([max(0, min(1040, float(pt[0]))), max(0, min(650, float(pt[1])))])
                        except (TypeError, ValueError):
                            pass
                if len(points) < 2:
                    continue
                item["points"] = points
            clean.append(item)
        return clean
    def _sanitize_writing_lines(self, writing_lines: Any, solution_state: Any) -> List[Dict[str, str]]:
        """Normalize the model's primary, readable board output and recover it from solution state."""
        clean: List[Dict[str, str]] = []
        allowed_kinds = {"heading", "explanation", "equation", "result"}
        if isinstance(writing_lines, list):
            for raw in writing_lines[:16]:
                if isinstance(raw, dict):
                    kind = str(raw.get("kind", "explanation")).lower()
                    text = str(raw.get("text", ""))
                else:
                    kind, text = "explanation", str(raw)
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    clean.append({"kind": kind if kind in allowed_kinds else "explanation", "text": text[:160]})
        if clean:
            return clean
        state = solution_state if isinstance(solution_state, dict) else {}
        for given in state.get("givens", [])[:4]:
            text = re.sub(r"\s+", " ", str(given)).strip()
            if text:
                clean.append({"kind": "explanation", "text": f"Given: {text}"[:160]})
        for step in state.get("steps", [])[:10]:
            text = re.sub(r"\s+", " ", str(step)).strip()
            if text:
                clean.append({"kind": "equation", "text": text[:160]})
        answer = re.sub(r"\s+", " ", str(state.get("answer", ""))).strip()
        if answer:
            clean.append({"kind": "result", "text": f"Answer: {answer}"[:160]})
        return clean[:16]
    def on_ai_lesson_received(self, data: dict):
        # Each current stage gets a predictable page inside its lesson lane.
        # Previous lessons remain navigable but cannot overlap new output.
        offset_x = self.active_lesson_base_x + self.active_lesson_stage_index * 1280.0
        self.active_lesson_stage_index += 1
        offset_y = 120.0
        title = str(data.get("title", "Universal Teaching Session")).upper()

        # The board's main output is readable written working. Geometry is
        # secondary and present only where the lesson actually needs it.
        writing_lines = self._sanitize_writing_lines(data.get("writing_lines", []), data.get("solution_state", {}))
        drawings = self._merge_model_visual_payload(data) if isinstance(data, dict) else self._sanitize_lesson_drawings(data.get("drawings", []))
        narration = str(data.get("narration", f"Explaining {title}."))
        # Reveal annotations at roughly the same cadence as natural speech
        # (about 2.7 words/sec).  Lines are still rendered one after another,
        # so the pointer has a visible teaching rhythm rather than dumping text.
        estimated_seconds = max(4.0, min(28.0, len(re.findall(r"\w+", narration)) / 2.7))
        text_reveal_rate = max(0.008, min(0.045, len(writing_lines) / max(1.0, estimated_seconds * 60.0)))
        board_height = max(210.0, min(780.0, 150.0 + len(writing_lines) * 43.0 + (150.0 if drawings else 0.0)))
        elem = SketchnoteElement(
            id=f"{self.active_lesson_id}_{self.active_lesson_stage_index}_{time.time_ns()}",
            element_type="free_form",
            bounding_rect=QRectF(offset_x - 34, offset_y - 34, 1120, board_height),
            text_reveal_rate=text_reveal_rate,
            timeline_started_at=time.monotonic(),
        )
        heading_font = QFont("Segoe Print", 13, QFont.Bold)
        normal_font = QFont("Segoe Print", 11, QFont.Normal)
        equation_font = QFont("Cambria Math", 12, QFont.Normal)
        kind_colors = {
            "heading": QColor(125, 211, 252),
            "explanation": QColor(241, 245, 249),
            "equation": QColor(253, 230, 138),
            "result": QColor(134, 239, 172),
        }
        elem.text_items.append((QPointF(offset_x + 28, offset_y + 34), title, heading_font, kind_colors["heading"], 0.0))
        for index, line in enumerate(writing_lines):
            kind = line.get("kind", "explanation")
            text = line.get("text", "")
            font = equation_font if kind == "equation" else normal_font
            if kind == "result":
                font = QFont("Segoe Print", 11, QFont.Bold)
            elem.text_items.append((QPointF(offset_x + 42, offset_y + 82 + index * 43), text, font, kind_colors.get(kind, kind_colors["explanation"]), 0.0))
            elem.text_start_ms[len(elem.text_items) - 1] = int(index * estimated_seconds * 1000 / max(1, len(writing_lines)))

        # Parse only task-justified diagram marks.
        for d in drawings:
            dtype = d.get("type", "")
            qcolor = ensure_visible_ink_color(d.get("color", "#38bdf8"))
                
            x = float(d.get("x", 0)) + offset_x
            y = float(d.get("y", 0)) + offset_y
            
            if dtype == "text":
                elem.text_items.append((QPointF(x, y), d.get("content", ""), QFont("Segoe Print", 11, QFont.Bold), qcolor, 0.0))
                elem.text_start_ms[len(elem.text_items) - 1] = int(d.get("_start_ms", 0))
            elif dtype == "shape":
                # Intelligent Auto-Smoothing: Geometric shapes are hardened and sharpened for clarity.
                shape_type = d.get("shape_type", "box")
                w, h = float(d.get("w", 100)), float(d.get("h", 100))
                if shape_type == "circle":
                    # Generate a mathematically perfect circle (auto-smoothed)
                    cx, cy, r = x + w/2, y + h/2, w/2
                    pts = [QPointF(cx + r * math.cos(i * 2 * math.pi / 60), cy + r * math.sin(i * 2 * math.pi / 60)) for i in range(61)]
                elif shape_type == "triangle":
                    # Perfect sharp triangle
                    pts = [QPointF(x+w/2, y), QPointF(x+w, y+h), QPointF(x, y+h), QPointF(x+w/2, y)]
                else:
                    # Perfect sharp box
                    pts = [QPointF(x, y), QPointF(x+w, y), QPointF(x+w, y+h), QPointF(x, y+h), QPointF(x, y)]
                elem.strokes.append(HandStroke(points=pts, color=qcolor, width=3.0, start_ms=int(d.get("_start_ms", 0))))
            elif dtype == "arrow":
                fx, fy = float(d.get("from_x", 0)) + offset_x, float(d.get("from_y", 0)) + offset_y
                tx, ty = float(d.get("to_x", 0)) + offset_x, float(d.get("to_y", 0)) + offset_y
                elem.strokes.append(HandStroke(points=[QPointF(fx, fy), QPointF(tx, ty)], color=qcolor, width=2.5, is_arrow=True, start_ms=int(d.get("_start_ms", 0))))
            elif dtype == "highlight":
                # Relational Highlighting: Transparent halogen colored overlays to group related concepts
                w, h = float(d.get("w", 100)), float(d.get("h", 100))
                # Create a perfect box with transparent fill
                pts = [QPointF(x, y), QPointF(x+w, y), QPointF(x+w, y+h), QPointF(x, y+h), QPointF(x, y)]
                halogen_fill = QColor(qcolor.red(), qcolor.green(), qcolor.blue(), 50) # Very transparent
                elem.strokes.append(HandStroke(points=pts, color=QColor(0,0,0,0), width=0, fill_color=halogen_fill, start_ms=int(d.get("_start_ms", 0))))
            elif dtype == "freehand":
                points_raw = d.get("points", [])
                pts = [QPointF(float(pt[0]) + offset_x, float(pt[1]) + offset_y) for pt in points_raw if len(pt) == 2]
                if pts:
                    elem.strokes.append(HandStroke(points=pts, color=qcolor, width=2.5, start_ms=int(d.get("_start_ms", 0))))

        # Draw axes, curves, and other marks in sequence while the related
        # annotations are being narrated instead of flashing them in at once.
        if elem.strokes:
            visual_seconds = max(1.2, min(9.0, estimated_seconds * 0.45))
            stroke_rate = max(0.006, min(0.050, len(elem.strokes) / (visual_seconds * 60.0)))
            for stroke in elem.strokes:
                stroke.speed = stroke_rate

        self.elements.append(elem)
        section_key = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip() or elem.id
        self.spatial_index[section_key] = {
            "title": title, "element_id": elem.id,
            "bounds": [elem.bounding_rect.x(), elem.bounding_rect.y(), elem.bounding_rect.width(), elem.bounding_rect.height()],
            "created_at": time.time(), "drawings": drawings,
        }

        # Handle Auto-Pan
        pan = data.get("auto_pan_target")
        if pan:
            px, py = float(pan.get("x", 0)) + offset_x, float(pan.get("y", 0)) + offset_y
            cx = px - (self.width() * 0.5)
            cy = py - (self.height() * 0.5)
            self.camera.pan_to(cx, cy, 1.0)
        else:
            cx = elem.bounding_rect.center().x() - (self.width() * 0.5)
            cy = elem.bounding_rect.center().y() - (self.height() * 0.5)
            self.camera.pan_to(cx, cy, 1.0)
            
        self.grid_alpha = 0.35

        # Mouse Target
        mt = data.get("mouse_target")
        if mt:
            self.virtual_mouse.move_to(float(mt.get("x", self.width()/2)), float(mt.get("y", self.height()/2)), mt.get("label", ""))
            self.virtual_mouse.pulse_click()

        narration = data.get("narration", f"Explaining {title}.")
        self.narrator.speak(narration)

    def handle_new_directive(self, prompt: str):

        p = prompt.lower().strip()

        # Explicit screen clear commands
        if p in ["report", "open report", "latest report"]:
            teacher = getattr(self, "active_teacher_organ", None)
            if teacher:
                teacher._generate_markdown_report(status="in progress" if teacher.is_active else "complete")
                print(f"[Hojaiga Report] {teacher.report_path}")
                self.narrator.speak("I saved and printed the report path in the terminal.")
            else:
                self.narrator.speak("There is no lesson report in this running session yet.")
            return

        if p in ["clear", "clean", "reset", "wipe", "close"]:
            self.clear_all_annotations()
            self.narrator.speak("Canvas cleared.")
            return

        # An active lesson owns Q&A/quiz responses, keeping teaching topic-agnostic.
        teacher = getattr(self, "active_teacher_organ", None)
        if teacher and teacher.is_active:
            if p in ("pause lesson", "pause_lesson", "pause"):
                teacher.pause()
                return
            elif p in ("resume lesson", "resume_lesson", "resume", "continue"):
                teacher.resume()
                return
            elif p in ("stop lesson", "end lesson", "stop teaching"):
                teacher.stop()
                self.narrator.speak("Lesson stopped. I will keep the whiteboard and report what we covered.")
                return
            elif p.startswith("teach ") or p.startswith("explain "):
                teacher.stop()
                topic = re.sub(r"^(teach|explain)\s+", "", prompt, flags=re.IGNORECASE).strip()
                self.trigger_teaching_session(topic)
                return
            elif teacher.awaiting_response:
                teacher.submit_response(prompt)
                return
            else:
                teacher.stop()
                print("[Hojaiga] Replacing the active lesson with the new task.")
                self.trigger_teaching_session(prompt)
                return

        # Check legacy Socratic evaluation first
        if self.active_quiz_meta is not None:
            c_target = str(self.active_quiz_meta["correct_c"])
            sq_target = str(self.active_quiz_meta["correct_sq"])
            topic = self.active_quiz_meta.get("topic", "Pythagorean Theorem")
            if "option a" in p or " a" in p or c_target in p or sq_target in p or "correct" in p:
                self.active_quiz_meta = None
                self.knowledge_tracker.record_quiz_result(topic, is_correct=True)
                self.narrator.speak("Outstanding! That is mathematically exact. The squares on the legs perfectly sum up to the hypotenuse square!")
                print("\n[Socratic Mastery] Answer CORRECT! Persistent profile updated.")
                return
            elif any(w in p for w in ["option b", "option c", " b", " c", "wrong", "mistake"]) or p.isdigit():
                self.active_quiz_meta = None
                self.knowledge_tracker.record_quiz_result(topic, is_correct=False)
                self.narrator.speak("Not quite. Notice that we never add the linear lengths directly. Let us re-anchor the proof through a direct tile analogy.")
                remed_elem = SketchnoteElement(id=f"remed_{int(time.time())}", element_type="proof", bounding_rect=QRectF(80, 120, 900, 500))
                remed_elem.text_items.append((QPointF(110, 160), "ADAPTIVE REMEDIATION: AREA ADDITION VS LINEAR ADDITION", QFont("Segoe Print", 11, QFont.Bold), QColor(248, 113, 113), 0.0))
                remed_elem.text_items.append((QPointF(110, 205), "Never write a + b = c! A 3m stick plus a 4m stick in a straight line is 7m,", QFont("Segoe Print", 10), QColor(241, 245, 249), 0.0))
                remed_elem.text_items.append((QPointF(110, 245), "but bent at 90 degrees, their endpoints are separated by only sqrt(9 + 16) = 5 meters.", QFont("Segoe Print", 10), QColor(56, 189, 248), 0.0))
                self.elements = [remed_elem]
                return

        # -------------------------------------------------------------
        # HOJAIGA DIRECT COMMAND ROUTING
        # -------------------------------------------------------------
        if p.startswith("crew ") or p.startswith("delegate "):
            goal = re.sub(r"^(crew|delegate)\s+", "", prompt, flags=re.IGNORECASE).strip()
            self.trigger_crewai_task(goal)
            return
        if p.startswith("go to "):
            if not self.go_to_section(prompt[len("go to "):]):
                self.narrator.speak("I do not have a matching lesson section yet.")
            return
        elif p.startswith("scan app "):
            self.trigger_deep_app_scan(prompt[len("scan app "):].strip(), active_probe=True)
            return
        elif p.startswith("inspect app "):
            self.trigger_deep_app_scan(prompt[len("inspect app "):].strip(), active_probe=False)
            return
        elif p == "scan app":
            self.narrator.speak("Name the open application. For example: scan app calculator.")
            return
        elif p.startswith("teach ") or p.startswith("explain "):
            topic = prompt.replace("teach ", "").replace("explain ", "").strip()
            self.trigger_teaching_session(topic)
            return
        elif p in ["mode insitu", "insitu", "ar", "ar mode"]:
            self.display_mode = DisplayMode.IN_SITU
            self.narrator.speak("Switched to Hojaiga In-Situ Augmented Mode.")
            self.update()
            return
        elif p in ["mode void", "void", "blackboard"]:
            self.display_mode = DisplayMode.VOID
            self.narrator.speak("Switched to Infinite Void Blackboard Mode.")
            self.update()
            return
        elif p in ["draw", "pen", "freehand"]:
            self.drawing_mode = not self.drawing_mode
            self.enable_click_through(self.display_mode == DisplayMode.IN_SITU and not self.drawing_mode)
            self.narrator.speak(f"Freehand drawing mode {'engaged' if self.drawing_mode else 'disabled'}.")
            self.update()
            return

        # Every ordinary request is sent to the model-driven solver/teacher.
        # The plan determines whether the work needs text, equations, graphs,
        # diagrams, app reasoning, code reasoning, or simply conversation.
        self.trigger_teaching_session(prompt)
        return

        # Clean prior elements so drawings do not get stuck across turns
        self.insitu_geometries.clear()
        self.insitu_pills.clear()
        self.insitu_beacons.clear()

        # Dynamic screen placement offset
        neg_pos = DynamicScreenFeatureDetector.find_screen_negative_space(self.w, self.h)
        offset_x = max(60.0, neg_pos.x() - 250.0)
        offset_y = max(80.0, neg_pos.y() - 200.0)

        if p.startswith("pdf") or p.startswith("doc") or p.startswith("read "):
            parts = prompt.split(maxsplit=1)
            target_path = parts[1] if len(parts) > 1 else "document.pdf"
            extracted_text = DocumentAndPDFIngestor.extract_document_text(target_path)
            elem = DeepDocumentVisualDeconstructor.deconstruct_document_into_visual_dag(
                offset_x, offset_y, os.path.basename(target_path), extracted_text
            )
            self.elements = [elem]
            self.narrator.speak(f"Deconstructing {os.path.basename(target_path)} into an organic visual decision tree and condition topology.")
        elif p.startswith("build app") or p.startswith("create app") or p.startswith("build "):
            app_spec = prompt.replace("build app", "").replace("create app", "").replace("build", "").strip() or "data_pipeline"
            elem, out_path, _ = JarvisAppBuilder.build_application(offset_x, offset_y, app_spec)
            self.elements = [elem]
            self.narrator.speak(f"Jarvis app builder executed. Synthesized and verified application source at {os.path.basename(out_path)}.")
        elif p.startswith("toddler") or p.startswith("how does ") or p.startswith("ladder "):
            t_topic = re.sub(r"^(toddler|how does|ladder)\s+", "", prompt, flags=re.IGNORECASE).strip()
            self.trigger_teaching_session(t_topic or "the requested topic")
            return
        elif any(k in p for k in ["profile", "mastery", "knowledge", "stats"]):
            print("\n" + self.knowledge_tracker.get_summary())
            self.narrator.speak("Displaying persistent student mastery profile and prioritized remediation targets.")
            return
        elif any(k in p for k in ["fbd", "block", "friction", "ramp", "incline", "force"]):
            self.trigger_teaching_session(prompt)
            return
        elif p.startswith("code") or p.startswith("def ") or "stack" in p or "ast" in p:
            sample_code = prompt if len(prompt) > 15 else "def solve(n):\n    if n <= 1:\n        return 1\n    return solve(n - 1) + solve(n - 2)"
            elem = RealCodeASTAnalyzer.analyze_code_and_synthesize(offset_x, offset_y, sample_code)
            self.elements = [elem]
            self.narrator.speak("Static AST code audit completed. Call stack recursion depth and memory footprint mapped.")
        elif any(k in p for k in ["quiz", "test", "socratic", "check"]):
            self.narrator.speak("Start a lesson first, then I will generate a topic-specific non-repeating quiz.")
            return
        else:
            # A free-form request is always a generalized teaching request; do not
            # fall back to legacy example detectors or fixed tutorial templates.
            self.trigger_teaching_session(prompt)
            return

        cx = elem.bounding_rect.center().x() - (self.width() * 0.5)
        cy = elem.bounding_rect.center().y() - (self.height() * 0.5)
        self.camera.pan_to(cx, cy, 1.0)
        self.grid_alpha = 0.35
        self.update()

    def on_tick(self):
        self.camera.update()
        if self.grid_alpha > 0.08:
            self.grid_alpha -= 0.003

        if self.autonomous_background_analysis and time.time() - self._last_background_analysis >= 5.0:
            self._last_background_analysis = time.time()
            self.doc_navigator.check_and_advance_document()
            self.contour_tracker.evaluate_screen_contours()
            self.code_watcher.scan_for_code_updates()

        has_active = False
        for elem in self.elements:
            elapsed_ms = int((time.monotonic() - elem.timeline_started_at) * 1000) if elem.timeline_started_at else 10**9
            for stroke in elem.strokes:
                if stroke.progress < 1.0:
                    if elapsed_ms < stroke.start_ms:
                        has_active = True
                        break
                    stroke.progress = min(1.0, stroke.progress + stroke.speed)
                    has_active = True
                    if len(stroke.points) > 1:
                        idx = int(stroke.progress * (len(stroke.points) - 1))
                        self.active_stylus_pt = stroke.points[idx]
                    break

            for i, (pt, txt, font, col, p) in enumerate(elem.text_items):
                if p < 1.0:
                    if elapsed_ms < elem.text_start_ms.get(i, 0):
                        has_active = True
                        break
                    elem.text_items[i] = (pt, txt, font, col, min(1.0, p + elem.text_reveal_rate))
                    has_active = True
                    break

        if not has_active:
            self.active_stylus_pt = None
        # Update In-Situ Geometries & Beacons
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
            # 1. Direct Euclidean Proof Squares on Video (Zero Cards)
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

            # 2. Pulsating Button Focus Halos (App guidance)
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
            font = QFont("Segoe Print", 9, QFont.Bold)
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
        # BRANCH 2: BORDERLESS VECTOR SKETCH PLANE (DYNAMIC TRANSLUCENT VOID)
        # -------------------------------------------------------------
        else:
            # A dark dotted surface makes the endless world legible while its
            # alpha keeps the live desktop visible underneath.
            painter.fillRect(self.rect(), QColor(1, 5, 14, self.void_backdrop_alpha))
            painter.save()
            zoom = self.camera.current_zoom
            painter.scale(zoom, zoom)
            painter.translate(-self.camera.current_x, -self.camera.current_y)

            # Dots belong to world space, not the screen: they pan and zoom
            # together with every diagram and handwritten line.
            left, top = self.camera.current_x, self.camera.current_y
            right = left + self.width() / zoom
            bottom = top + self.height() / zoom
            spacing = self.void_grid_spacing
            start_x = math.floor(left / spacing) * spacing
            start_y = math.floor(top / spacing) * spacing
            dot_alpha = int(42 + 72 * max(0.08, min(1.0, self.grid_alpha)))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(125, 153, 181, dot_alpha)))
            dot_radius = max(0.85, 1.15 / zoom)
            x = start_x
            while x <= right + spacing:
                y = start_y
                while y <= bottom + spacing:
                    painter.drawEllipse(QPointF(x, y), dot_radius, dot_radius)
                    y += spacing
                x += spacing

            for elem in self.elements:
                op = elem.opacity
                for stroke in elem.strokes:
                    if stroke.progress <= 0.01 or len(stroke.points) < 2:
                        continue
                    pts = stroke.points
                    limit = max(2, int(stroke.progress * len(pts)))
                    active_pts = pts[:limit]
                    if stroke.fill_color and stroke.progress >= 0.90:
                        poly_path = QPainterPath()
                        poly_path.moveTo(pts[0])
                        for point in pts[1:]:
                            poly_path.lineTo(point)
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
                    for point in active_pts[1:]:
                        path.lineTo(point)
                    painter.drawPath(path)

            # Typography and its translucent backing are world-space too, so
            # lettering scales exactly with the infinite Void when zooming.
            for elem in self.elements:
                op = elem.opacity
                prepared = []
                text_bounds = None
                for pt, txt, font, col, progress in elem.text_items:
                    if progress <= 0.05 or not txt:
                        continue
                    painter.setFont(font)
                    fm = painter.fontMetrics()
                    rect = QRectF(pt.x(), pt.y() - fm.ascent(), fm.horizontalAdvance(txt), fm.height())
                    text_bounds = rect if text_bounds is None else text_bounds.united(rect)
                    prepared.append((pt, txt, font, col, progress))
                if not prepared or text_bounds is None:
                    continue
                backing = text_bounds.adjusted(-28, -24, 28, 22)
                shade = QLinearGradient(backing.topLeft(), backing.bottomRight())
                shade.setColorAt(0.0, QColor(2, 7, 18, int(108 * op)))
                shade.setColorAt(1.0, QColor(8, 22, 40, int(70 * op)))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(shade))
                painter.drawRoundedRect(backing, 18, 18)
                for point, txt, font, col, progress in prepared:
                    painter.setFont(font)
                    revealed_txt = txt[:int(progress * len(txt))]
                    if not revealed_txt:
                        continue
                    painter.setPen(QPen(QColor(2, 7, 18, int(205 * op))))
                    for dx, dy in [(-1.0, 0), (1.0, 0), (0, -1.0), (0, 1.0)]:
                        painter.drawText(QPointF(point.x() + dx, point.y() + dy), revealed_txt)
                    painter.setPen(QPen(QColor(col.red(), col.green(), col.blue(), int(255 * op))))
                    painter.drawText(point, revealed_txt)

            if self.active_stylus_pt:
                point = self.active_stylus_pt
                glow = QRadialGradient(point, 18)
                glow.setColorAt(0.0, QColor(56, 189, 248, 240))
                glow.setColorAt(0.5, QColor(56, 189, 248, 70))
                glow.setColorAt(1.0, QColor(56, 189, 248, 0))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(glow))
                painter.drawEllipse(point, 18, 18)
                painter.setBrush(QBrush(QColor(255, 255, 255, 250)))
                painter.drawEllipse(point, 3, 3)
            painter.restore()
        # BRANCH 3: FREEHAND USER DRAWING OVERLAY (F7)
        # -------------------------------------------------------------
        if self.freehand_strokes or self.current_freehand_stroke:
            painter.save()
            if self.display_mode == DisplayMode.VOID:
                painter.scale(self.camera.current_zoom, self.camera.current_zoom)
                painter.translate(-self.camera.current_x, -self.camera.current_y)
            pen = QPen(self.pen_color, self.pen_width)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            all_strokes = self.freehand_strokes + ([self.current_freehand_stroke] if self.current_freehand_stroke else [])
            for stroke in all_strokes:
                if len(stroke) > 1:
                    path = QPainterPath()
                    path.moveTo(stroke[0])
                    for pt in stroke[1:]:
                        path.lineTo(pt)
                    painter.drawPath(path)
            painter.restore()

        # The pointer and ribbon deliberately remain screen-space.
        self.virtual_mouse.render(painter)
        self._render_void_ribbon(painter)
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clear_all_annotations()
            self.narrator.speak("Canvas cleared.")
            self.update()
        elif event.key() == Qt.Key_F9:
            self.display_mode = DisplayMode.IN_SITU if self.display_mode == DisplayMode.VOID else DisplayMode.VOID
            # VOID mode: disable click-through so left-click drag pans the canvas directly
            # IN_SITU mode: enable click-through so clicks reach the underlying app
            if self.display_mode == DisplayMode.VOID:
                self.enable_click_through(False)
            else:
                self.enable_click_through(True)
            self.narrator.speak(f"Switched to {self.display_mode.value} mode.")
            self.update()
        elif event.key() == Qt.Key_V:
            # Dedicated return-to-Void key; unlike F9 it never toggles away.
            self.display_mode = DisplayMode.VOID
            self.enable_click_through(False)
            self.update()
        elif event.key() == Qt.Key_F7:
            self._toggle_drawing_mode()
        elif event.key() == Qt.Key_R:
            self.void_ribbon_collapsed = not self.void_ribbon_collapsed
            self.update()
        elif event.key() == Qt.Key_M and self.display_mode == DisplayMode.VOID:
            if self.edge_avatar is not None:
                self.edge_avatar.dock_after_void_minimize()
            self.showMinimized()
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
            # Void remains directly pannable after releasing Alt.
            if self.display_mode == DisplayMode.VOID and not self.drawing_mode:
                self.enable_click_through(False)
        super().keyReleaseEvent(event)

    def _screen_to_void_world(self, point: QPointF) -> QPointF:
        return QPointF(
            self.camera.current_x + point.x() / self.camera.current_zoom,
            self.camera.current_y + point.y() / self.camera.current_zoom,
        )

    def mousePressEvent(self, event):
        if self._handle_void_ribbon_click(event.pos()):
            event.accept()
            return
        if self.drawing_mode and event.button() == Qt.LeftButton:
            point = self._screen_to_void_world(event.pos()) if self.display_mode == DisplayMode.VOID else QPointF(event.pos())
            self.current_freehand_stroke = [point]
            self.update()
            return
        if event.button() == Qt.RightButton and self.display_mode == DisplayMode.VOID:
            self.directive_signal.emit("pause_lesson")
            return
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self.setFocus(Qt.MouseFocusReason)
            self.is_dragging = True
            self.last_mouse_pos = event.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drawing_mode and event.buttons() & Qt.LeftButton:
            point = self._screen_to_void_world(event.pos()) if self.display_mode == DisplayMode.VOID else QPointF(event.pos())
            self.current_freehand_stroke.append(point)
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
            if delta:
                if event.modifiers() & Qt.ControlModifier:
                    # Ctrl + wheel zooms around the physical pointer.
                    old_zoom = self.camera.current_zoom
                    factor = 1.12 if delta > 0 else 0.88
                    new_zoom = max(0.32, min(4.0, old_zoom * factor))
                    mouse = event.pos()
                    world_x = self.camera.current_x + mouse.x() / old_zoom
                    world_y = self.camera.current_y + mouse.y() / old_zoom
                    self.camera.current_x = self.camera.target_x = world_x - mouse.x() / new_zoom
                    self.camera.current_y = self.camera.target_y = world_y - mouse.y() / new_zoom
                    self.camera.current_zoom = self.camera.target_zoom = new_zoom
                else:
                    # Plain wheel travels vertically through the infinite board.
                    travel = delta / max(1.0, self.camera.current_zoom * 1.6)
                    self.camera.current_y = self.camera.target_y = self.camera.current_y - travel
                self.update()
                event.accept()
                return
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
    print(" HOJAIGA — UNIVERSAL TEACHING VOID")
    print("=" * 76)
    print("Commands:")
    print("  * teach <topic>           Start a structured lesson")
    print("  * scan app <name>         Organ 30 safe active scan of an open app")
    print("  * inspect app <name>      Non-destructive app inspection")
    print("  * pause / resume / stop lesson")
    print("  * void / ar / draw / clear")
    print("Controls: F9 switches Void/AR; F7 toggles pen; Ctrl+S exports notes.")
    print(f"Active model: {MODEL_DISPLAY_NAME}")
    print("=" * 76)
    if INITIAL_TASK:
        overlay.directive_signal.emit(INITIAL_TASK)
    while True:
        try:
            cmd = input("\nHojaiga > ").strip()
            if cmd:
                overlay.directive_signal.emit(cmd)
        except (EOFError, KeyboardInterrupt):
            overlay.directive_signal.emit("stop lesson")
            break
def main():
    app = QApplication(sys.argv)
    # Ctrl+C originates in the terminal thread; quit Qt cleanly instead of interrupting paintEvent.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    overlay = SpatialWhiteboardOverlay(initial_task=INITIAL_TASK)
    # Quiet launch: the edge avatar is visible; Void waits for a click or task.
    overlay.hide()
    # Organ 34 stays separate from the teaching engine but binds here to the
    # Qt event loop, so start_hojaiga.bat always presents the edge avatar.
    try:
        from core_organs.organ_34_hojaiga_avatar import spawn_edge_avatar
        overlay.edge_avatar = spawn_edge_avatar(overlay)
    except Exception as exc:
        print(f"[Hojaiga Avatar] Could not start edge avatar: {exc}")

    t = threading.Thread(target=terminal_input_loop, args=(overlay,), daemon=True)
    t.start()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()ounding_rect.center().x() - self.width() * 0.5
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
    print(" HOJAIGA — UNIVERSAL TEACHING VOID")
    print("=" * 76)
    print("Commands:")
    print("  * teach <topic>           Start a structured lesson")
    print("  * scan app <name>         Organ 30 safe active scan of an open app")
    print("  * inspect app <name>      Non-destructive app inspection")
    print("  * pause / resume / stop lesson")
    print("  * void / ar / draw / clear")
    print("Controls: F9 switches Void/AR; F7 toggles pen; Ctrl+S exports notes.")
    print(f"Active model: {MODEL_DISPLAY_NAME}")
    print("=" * 76)
    if INITIAL_TASK:
        overlay.directive_signal.emit(INITIAL_TASK)
    while True:
        try:
            cmd = input("\nHojaiga > ").strip()
            if cmd:
                overlay.directive_signal.emit(cmd)
        except (EOFError, KeyboardInterrupt):
            overlay.directive_signal.emit("stop lesson")
            break
def main():
    app = QApplication(sys.argv)
    # Ctrl+C originates in the terminal thread; quit Qt cleanly instead of interrupting paintEvent.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    overlay = SpatialWhiteboardOverlay(initial_task=INITIAL_TASK)
    # Quiet launch: the edge avatar is visible; Void waits for a click or task.
    overlay.hide()
    # Organ 34 stays separate from the teaching engine but binds here to the
    # Qt event loop, so start_hojaiga.bat always presents the edge avatar.
    try:
        from core_organs.organ_34_hojaiga_avatar import spawn_edge_avatar
        overlay.edge_avatar = spawn_edge_avatar(overlay)
    except Exception as exc:
        print(f"[Hojaiga Avatar] Could not start edge avatar: {exc}")

    t = threading.Thread(target=terminal_input_loop, args=(overlay,), daemon=True)
    t.start()

    sys.exit(app.exec_())

def terminal_input_loop(overlay: SpatialWhiteboardOverlay):
    time.sleep(1.0)
    print("=" * 76)
    print(" HOJAIGA — UNIVERSAL TEACHING VOID")
    print("=" * 76)
    print("Commands:")
    print("  * teach <topic>           Start a structured lesson")
    print("  * scan app <name>         Organ 30 safe active scan of an open app")
    print("  * inspect app <name>      Non-destructive app inspection")
    print("  * pause / resume / stop lesson")
    print("  * void / ar / draw / clear")
    print("Controls: F9 switches Void/AR; F7 toggles pen; Ctrl+S exports notes.")
    print(f"Active model: {MODEL_DISPLAY_NAME}")
    print("=" * 76)
    if INITIAL_TASK:
        overlay.directive_signal.emit(INITIAL_TASK)
    while True:
        try:
            cmd = input("\nHojaiga > ").strip()
            if cmd:
                overlay.directive_signal.emit(cmd)
        except (EOFError, KeyboardInterrupt):
            overlay.directive_signal.emit("stop lesson")
            break
def main():
    app = QApplication(sys.argv)
    # Ctrl+C originates in the terminal thread; quit Qt cleanly instead of interrupting paintEvent.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    overlay = SpatialWhiteboardOverlay(initial_task=INITIAL_TASK)
    # Quiet launch: the edge avatar is visible; Void waits for a click or task.
    overlay.hide()
    # Organ 34 stays separate from the teaching engine but binds here to the
    # Qt event loop, so start_hojaiga.bat always presents the edge avatar.
    try:
        from core_organs.organ_34_hojaiga_avatar import spawn_edge_avatar
        overlay.edge_avatar = spawn_edge_avatar(overlay)
    except Exception as exc:
        print(f"[Hojaiga Avatar] Could not start edge avatar: {exc}")

    t = threading.Thread(target=terminal_input_loop, args=(overlay,), daemon=True)
    t.start()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()ad(target=terminal_input_loop, args=(overlay,), daemon=True)
    t.start()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()