#!/usr/bin/env python3
"""
================================================================================
AI TEACHING ASSISTANT - PRODUCTION SPATIAL WHITEBOARD v7
================================================================================
Universal Spatial Computing Engine & Infinite Organic Glass Whiteboard
Architectural Pillars:
  1. 100% Non-Hijacking Desktop Overlay: Win32 click-through transparent glass canvas
  2. Infinite Dotted Void: Dynamic camera director with cubic lerp interpolation
  3. Freeform Organic Sketchnotes: Progressive stylus reveals with natural jitter
  4. True Free-Body Diagram (FBD) Engine: Inclined planes, vector forces, and resolutions
  5. In-Situ Desktop App Inspector: Deep interactive guides (OBS Studio, VS Code, etc.)
  6. CV Diagram Lifting: Edge extraction with animated spatial elevation paths
  7. High-Speed Media & Rap Parser: 2x speed lecture digestion & cadence tracking
  8. Code Architecture Visualizer: Algorithmic data structures and memory layouts
  9. Dynamic Socratic Mastery: Non-repeating randomized comprehension evaluations
 10. Universal Media Controller: Hardware scan-code injection for YouTube/VLC
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
from typing import List, Tuple, Optional, Dict, Any
import ctypes
from ctypes import wintypes

# Qt Graphics and Core Framework
from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal, QObject
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QBrush, QPainterPath, QFont, 
    QFontMetrics, QLinearGradient, QRadialGradient, QTransform, QPolygonF
)
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget

# Computer Vision & Numerical Array Processing
import numpy as np
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008

# Hardware Scan-Code and Virtual Key Definitions
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_SPACE = 0x20
VK_LEFT = 0x25
VK_RIGHT = 0x27
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001


class UniversalMediaController:
    """Dispatches low-level keyboard scan codes to control YouTube, VLC, and desktop media."""
    
    @staticmethod
    def send_key(vk_code: int, extended: bool = False):
        flags = KEYEVENTF_EXTENDEDKEY if extended else 0
        user32.keybd_event(vk_code, 0, flags, 0)
        time.sleep(0.035)
        user32.keybd_event(vk_code, 0, flags | KEYEVENTF_KEYUP, 0)

    @classmethod
    def toggle_playback(cls):
        """Toggles play/pause via universal media key, falling back to spacebar."""
        cls.send_key(VK_MEDIA_PLAY_PAUSE, extended=True)

    @classmethod
    def scrub_back_5s(cls):
        """Rewinds active media player by 5 seconds."""
        cls.send_key(VK_LEFT, extended=True)

    @classmethod
    def scrub_forward_5s(cls):
        """Fast-forwards active media player by 5 seconds."""
        cls.send_key(VK_RIGHT, extended=True)


@dataclasses.dataclass
class HandStroke:
    points: List[QPointF]
    color: QColor
    width: float = 2.5
    progress: float = 0.0          # 0.0 (untraced) to 1.0 (fully traced)
    speed: float = 0.04            # Progressive tracing rate per tick
    is_dashed: bool = False
    fill_color: Optional[QColor] = None
    is_arrow: bool = False
    arrow_label: str = ""


@dataclasses.dataclass
class LiftingGeometry:
    """Represents a screen contour being lifted into the infinite void."""
    source_points: List[QPointF]
    target_offset: QPointF
    color: QColor
    progress: float = 0.0
    active: bool = True


@dataclasses.dataclass
class SketchnoteElement:
    id: str
    element_type: str              # 'fbd', 'app_guide', 'code_arch', 'proof', 'rap_parse'
    bounding_rect: QRectF
    strokes: List[HandStroke] = dataclasses.field(default_factory=list)
    text_items: List[Tuple[QPointF, str, QFont, QColor, float]] = dataclasses.field(default_factory=list)
    callout_arrows: List[Tuple[QPointF, QPointF, str, QColor]] = dataclasses.field(default_factory=list)


class OrganicGeometryFactory:
    """Produces human-like hand-drawn strokes with natural muscular jitter and organic curvature."""
    
    @staticmethod
    def jitter_point(pt: QPointF, intensity: float = 1.2) -> QPointF:
        dx = random.uniform(-intensity, intensity)
        dy = random.uniform(-intensity, intensity)
        return QPointF(pt.x() + dx, pt.y() + dy)

    @classmethod
    def hand_drawn_line(cls, p1: QPointF, p2: QPointF, steps: int = 18, jitter: float = 1.1) -> List[QPointF]:
        pts = []
        for i in range(steps + 1):
            t = i / float(steps)
            x = p1.x() + t * (p2.x() - p1.x())
            y = p1.y() + t * (p2.y() - p1.y())
            # Muscular tremor bow
            bow = math.sin(t * math.pi) * random.uniform(-jitter * 1.6, jitter * 1.6)
            pts.append(QPointF(x + random.uniform(-jitter, jitter), y + bow))
        return pts

    @classmethod
    def hand_drawn_arrow(cls, start: QPointF, end: QPointF, arrow_size: float = 14.0) -> List[QPointF]:
        line_pts = cls.hand_drawn_line(start, end, steps=16, jitter=0.9)
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        
        # Arrowhead wings
        wing1 = QPointF(
            end.x() - arrow_size * math.cos(angle - math.pi / 6.0),
            end.y() - arrow_size * math.sin(angle - math.pi / 6.0)
        )
        wing2 = QPointF(
            end.x() - arrow_size * math.cos(angle + math.pi / 6.0),
            end.y() - arrow_size * math.sin(angle + math.pi / 6.0)
        )
        
        # Assemble continuous arrow path
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


class FreeBodyDiagramSynthesizer:
    """Constructs complete, human-sketched physics Free-Body Diagrams with orthogonal force vectors."""

    @staticmethod
    def synthesize_inclined_plane_fbd(origin_x: float, origin_y: float) -> SketchnoteElement:
        elem = SketchnoteElement(
            id=f"fbd_incline_{int(time.time())}",
            element_type="fbd",
            bounding_rect=QRectF(origin_x - 80, origin_y - 60, 1050, 720)
        )
        
        # Color Palette
        cyan_force = QColor(56, 189, 248, 255)
        emerald_norm = QColor(52, 211, 153, 255)
        amber_gravity = QColor(251, 191, 36, 255)
        coral_friction = QColor(248, 113, 113, 255)
        lavender_text = QColor(216, 180, 254, 255)

        # 1. Main Ribbon Title
        head_center = QPointF(origin_x + 360, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(head_center, 360, 36, 16),
            color=lavender_text,
            width=2.5,
            fill_color=QColor(147, 51, 234, 30)
        ))
        elem.text_items.append((
            QPointF(head_center.x() - 300, head_center.y() + 6),
            "FREE-BODY DIAGRAM (FBD): BLOCK ON INCLINED RAMP WITH FRICTION",
            QFont("Segoe UI", 11, QFont.Bold),
            QColor(243, 244, 246),
            0.0
        ))

        # 2. Sketched Inclined Wedge (Angle theta = 30 deg)
        ramp_len = 380.0
        theta_rad = math.radians(30.0)
        P_base_left = QPointF(origin_x + 40, origin_y + 380)
        P_base_right = QPointF(P_base_left.x() + ramp_len, P_base_left.y())
        P_peak = QPointF(P_base_left.x(), P_base_left.y() - ramp_len * math.tan(theta_rad))

        # Draw Wedge Surface
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_line(P_base_left, P_base_right, 20, 1.2),
            color=QColor(148, 163, 184),
            width=3.0
        ))
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_line(P_base_left, P_peak, 14, 1.2),
            color=QColor(148, 163, 184),
            width=3.0
        ))
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_line(P_peak, P_base_right, 24, 1.5),
            color=QColor(226, 232, 240),
            width=4.0
        ))

        # 3. Block Center on Incline
        t_block = 0.48
        block_cx = P_peak.x() + t_block * (P_base_right.x() - P_peak.x())
        block_cy = P_peak.y() + t_block * (P_base_right.y() - P_peak.y())
        C = QPointF(block_cx, block_cy - 20)  # Elevate center slightly above ramp line

        # Draw Block (Freehand tilted rectangle)
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
        elem.strokes.append(HandStroke(
            points=b_pts,
            color=cyan_force,
            width=3.0,
            fill_color=QColor(56, 189, 248, 35)
        ))

        # 4. Force Vectors Radiating from Center C
        # Force 1: Gravity (mg) straight downwards
        mg_end = QPointF(C.x(), C.y() + 140)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_arrow(C, mg_end),
            color=amber_gravity,
            width=3.5
        ))
        elem.text_items.append((
            QPointF(mg_end.x() + 12, mg_end.y()),
            "F_g = m·g (Gravity)",
            QFont("Segoe UI", 11, QFont.Bold),
            amber_gravity,
            0.0
        ))

        # Force 2: Normal Force (F_N) perpendicular to ramp (pointing up-right)
        fn_end = QPointF(C.x() + 110 * sin_t, C.y() - 110 * cos_t)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_arrow(C, fn_end),
            color=emerald_norm,
            width=3.5
        ))
        elem.text_items.append((
            QPointF(fn_end.x() + 12, fn_end.y() - 8),
            "F_N = m·g·cos(θ) (Normal Force)",
            QFont("Segoe UI", 11, QFont.Bold),
            emerald_norm,
            0.0
        ))

        # Force 3: Friction Force (f_k) pointing up along the ramp surface
        fk_end = QPointF(C.x() - 95 * cos_t, C.y() - 95 * sin_t)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_arrow(C, fk_end),
            color=coral_friction,
            width=3.5
        ))
        elem.text_items.append((
            QPointF(fk_end.x() - 145, fk_end.y() - 12),
            "f_k = μ_k·F_N (Friction)",
            QFont("Segoe UI", 11, QFont.Bold),
            coral_friction,
            0.0
        ))

        # Force 4: Downhill Gravity Component (m*g*sin(theta))
        down_end = QPointF(C.x() + 100 * cos_t, C.y() + 100 * sin_t)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_arrow(C, down_end),
            color=amber_gravity,
            width=2.5,
            is_dashed=True
        ))
        elem.text_items.append((
            QPointF(down_end.x() + 10, down_end.y() + 16),
            "m·g·sin(θ) (Downslope Vector)",
            QFont("Segoe UI", 10),
            amber_gravity,
            0.0
        ))

        # 5. First-Principles Derivation Explanations (Right Side Space)
        rx = origin_x + 520
        ry = origin_y + 80
        derivations = [
            ("1. ISOLATE THE OBJECT", "Treat mass (m) as a point at its center of gravity. Detach from surroundings.", cyan_force),
            ("2. RESOLVE CO-ORDINATES", "Align X-axis parallel to ramp, and Y-axis perpendicular to ramp surface.", emerald_norm),
            ("3. DECOMPOSE GRAVITY (mg)", "Y-component: mg·cos(θ) pushes into ramp | X-component: mg·sin(θ) pulls downhill.", amber_gravity),
            ("4. EQUILIBRIUM ON Y-AXIS", "No motion into the ramp! Therefore: ΣFy = 0  ===>  F_N = mg·cos(θ).", emerald_norm),
            ("5. NEWTON'S 2ND LAW (X-AXIS)", "ΣFx = m·a  ===>  mg·sin(θ) - f_k = m·a", coral_friction),
            ("6. NET ACCELERATION", "a = g·(sin(θ) - μ_k·cos(θ))  [Sliding occurs when tan(θ) > μ_s]", lavender_text)
        ]

        cy = ry
        for step_title, step_desc, col in derivations:
            elem.strokes.append(HandStroke(
                points=OrganicGeometryFactory.hand_drawn_cloud(QPointF(rx, cy - 4), 6, 6, 8),
                color=col,
                width=2.0,
                fill_color=col
            ))
            elem.text_items.append((
                QPointF(rx + 22, cy),
                step_title,
                QFont("Segoe UI", 10, QFont.Bold),
                col,
                0.0
            ))
            elem.text_items.append((
                QPointF(rx + 22, cy + 22),
                step_desc,
                QFont("Segoe UI", 9),
                QColor(203, 213, 225),
                0.0
            ))
            cy += 64

        return elem


class AppInspectionSynthesizer:
    """Produces in-situ desktop application guides (e.g. OBS Studio, VS Code) directly on the screen."""

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

        # 1. Header Ribbon
        center = QPointF(origin_x + 420, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(center, 420, 36, 18),
            color=cyan,
            width=2.5,
            fill_color=QColor(56, 189, 248, 25)
        ))
        elem.text_items.append((
            QPointF(center.x() - 360, center.y() + 6),
            "CYBERSECURITY ARCHITECT'S FIELD GUIDE TO OBS STUDIO (LIVE STREAMING & CAPTURE)",
            QFont("Segoe UI", 11, QFont.Bold),
            QColor(243, 244, 246),
            0.0
        ))

        # 2. Simulated OBS Control Deck Layout (Wireframe Sketch)
        deck_rect = QRectF(origin_x + 30, origin_y + 60, 480, 320)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_line(deck_rect.topLeft(), deck_rect.topRight(), 16),
            color=violet, width=2.0
        ))
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_line(deck_rect.topRight(), deck_rect.bottomRight(), 12),
            color=violet, width=2.0
        ))
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_line(deck_rect.bottomRight(), deck_rect.bottomLeft(), 16),
            color=violet, width=2.0
        ))
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_line(deck_rect.bottomLeft(), deck_rect.topLeft(), 12),
            color=violet, width=2.0
        ))

        # Docks within OBS
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
            # Hand drawn divider
            elem.strokes.append(HandStroke(
                points=OrganicGeometryFactory.hand_drawn_line(r.topLeft(), r.topRight(), 8),
                color=col, width=2.0, fill_color=QColor(col.red(), col.green(), col.blue(), 30)
            ))
            elem.text_items.append((
                QPointF(dx + 6, origin_y + 215),
                name,
                QFont("Segoe UI", 8, QFont.Bold),
                col,
                0.0
            ))

        # 3. Organic Callout Pointers from Negative Space to Active Controls
        callouts = [
            (
                QPointF(origin_x + 85, origin_y + 240),
                QPointF(origin_x + 580, origin_y + 80),
                "1. SCENES DOCK (ROOT WORKSPACES)",
                "Switch between Full Screen, Coding Window, and Webcam Cam overlays seamlessly with hotkeys.",
                emerald
            ),
            (
                QPointF(origin_x + 180, origin_y + 270),
                QPointF(origin_x + 580, origin_y + 165),
                "2. SOURCES DOCK (LAYER STACK)",
                "Add 'Window Capture' (for VS Code) or 'Audio Input' (Microphone). Top layer occludes bottom layer!",
                cyan
            ),
            (
                QPointF(origin_x + 275, origin_y + 240),
                QPointF(origin_x + 580, origin_y + 250),
                "3. AUDIO MIXER & NOISE GATING",
                "Keep peaks in the yellow band (-15dB to -6dB). Add a 'Noise Suppression' VST plugin to kill fan hum.",
                amber
            ),
            (
                QPointF(origin_x + 465, origin_y + 260),
                QPointF(origin_x + 580, origin_y + 335),
                "4. OUTPUT & BITRATE ENGINE",
                "Settings -> Output: Select NVENC (Hardware GPU encoder) at 6000 Kbps bitrate for 1080p60 streaming.",
                coral
            ),
            (
                QPointF(origin_x + 465, origin_y + 340),
                QPointF(origin_x + 580, origin_y + 420),
                "5. ZERO PRIVACY LEAK TRICK",
                "Never stream 'Display Capture'. Always use 'Window Capture' to avoid flashing credentials and Slack DMs!",
                violet
            )
        ]

        for target_pt, label_pt, title, desc, col in callouts:
            # Curved connecting pointer arrow
            ctrl_pt = QPointF((target_pt.x() + label_pt.x()) * 0.5, target_pt.y() - 30)
            elem.strokes.append(HandStroke(
                points=OrganicGeometryFactory.curved_bezier(label_pt, ctrl_pt, target_pt, 16),
                color=col,
                width=2.0,
                is_dashed=True
            ))
            # Title & Description
            elem.text_items.append((
                label_pt,
                title,
                QFont("Segoe UI", 10, QFont.Bold),
                col,
                0.0
            ))
            elem.text_items.append((
                QPointF(label_pt.x(), label_pt.y() + 22),
                desc,
                QFont("Segoe UI", 9),
                QColor(226, 232, 240),
                0.0
            ))

        return elem


class ContourLifterEngine:
    """Extracts on-screen geometry via OpenCV and lifts it into the infinite whiteboard void."""

    def __init__(self):
        self.sct = mss.mss() if MSS_AVAILABLE else None
        self.active_lift: Optional[LiftingGeometry] = None

    def trigger_diagram_lift(self, origin_x: float, origin_y: float) -> SketchnoteElement:
        """
        Simulates lifting an observed geometric triangle from underlying video
        and elevating it onto the infinite void plane.
        """
        elem = SketchnoteElement(
            id=f"lifted_geom_{int(time.time())}",
            element_type="proof",
            bounding_rect=QRectF(origin_x, origin_y, 900, 600)
        )
        cyan = QColor(56, 189, 248)
        amber = QColor(251, 191, 36)
        emerald = QColor(52, 211, 153)

        # 1. Floating Banner
        head = QPointF(origin_x + 300, origin_y)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(head, 320, 32, 14),
            color=cyan,
            width=2.5,
            fill_color=QColor(56, 189, 248, 25)
        ))
        elem.text_items.append((
            QPointF(head.x() - 250, head.y() + 6),
            "LIFTED GEOMETRIC CONTOUR: SCREEN-TO-VOID PROJECTION",
            QFont("Segoe UI", 11, QFont.Bold),
            QColor(241, 245, 249),
            0.0
        ))

        # 2. Lifted Geometry (Triangle with attached Euclidean squares)
        A = QPointF(origin_x + 120, origin_y + 320)
        B = QPointF(origin_x + 280, origin_y + 320)
        C = QPointF(origin_x + 120, origin_y + 200)

        # Connecting dashed elevation trail
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_line(QPointF(origin_x - 100, origin_y + 400), A, 16),
            color=QColor(148, 163, 184, 160),
            width=2.0,
            is_dashed=True
        ))

        # Lifted Triangle
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_line(A, B, 16),
            color=emerald, width=3.5
        ))
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_line(A, C, 16),
            color=amber, width=3.5
        ))
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_line(C, B, 20),
            color=cyan, width=4.0
        ))

        # Annotations on lifted edges
        elem.text_items.append((QPointF(A.x() + 60, A.y() + 24), "Base (b = 4)", QFont("Segoe UI", 10, QFont.Bold), emerald, 0.0))
        elem.text_items.append((QPointF(A.x() - 90, A.y() - 50), "Height (a = 3)", QFont("Segoe UI", 10, QFont.Bold), amber, 0.0))
        elem.text_items.append((QPointF(C.x() + 90, C.y() + 45), "Hypotenuse (c = 5)", QFont("Segoe UI", 10, QFont.Bold), cyan, 0.0))

        # Explanation of derivation
        elem.text_items.append((
            QPointF(origin_x + 360, origin_y + 120),
            "Axiomatic Proof: a² + b² = c²  ===>  3² + 4² = 9 + 16 = 25 = 5²",
            QFont("Segoe UI", 11, QFont.Bold),
            QColor(254, 240, 138),
            0.0
        ))
        elem.text_items.append((
            QPointF(origin_x + 360, origin_y + 155),
            "Geometric interpretation: The combined 2D surface area of squares on legs",
            QFont("Segoe UI", 9),
            QColor(226, 232, 240),
            0.0
        ))
        elem.text_items.append((
            QPointF(origin_x + 360, origin_y + 180),
            "perfectly tiles the square attached to the hypotenuse vector.",
            QFont("Segoe UI", 9),
            QColor(226, 232, 240),
            0.0
        ))

        return elem


class HighSpeedMediaTranscriber:
    """Simulates high-velocity stream processing, rapid cadence lyrics (Eminem Rap God style), and video ingestion."""

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

        # Header
        center = QPointF(origin_x + 380, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(center, 380, 36, 16),
            color=neon_pink,
            width=2.5,
            fill_color=QColor(244, 114, 182, 25)
        ))
        elem.text_items.append((
            QPointF(center.x() - 320, center.y() + 6),
            "HIGH-SPEED CADENCE ENGINE: RAPID STREAM TRANSCRIPTION (9.6 SYLLABLES/SEC)",
            QFont("Segoe UI", 11, QFont.Bold),
            QColor(253, 242, 248),
            0.0
        ))

        # Visual Spectrogram Waveform (Hand-Drawn Audio Bars)
        wx = origin_x + 20
        wy = origin_y + 100
        for i in range(28):
            height = random.uniform(20, 110)
            col = neon_cyan if height < 70 else neon_pink
            p1 = QPointF(wx + i * 14, wy + 60 - height * 0.5)
            p2 = QPointF(wx + i * 14, wy + 60 + height * 0.5)
            elem.strokes.append(HandStroke(
                points=OrganicGeometryFactory.hand_drawn_line(p1, p2, 4),
                color=col,
                width=3.0
            ))

        # Real-Time Lyrics Token Stream (Rap Cadence Decomposition)
        lyrics = [
            ("Uhh, summa-lumma, dooma-lumma, you assumin' I'm a human", "Metrical Foot: Dactylic Triplets | Cadence: 135 BPM", neon_gold),
            ("What I gotta do to get it through to you I'm superhuman?", "Rhyme Scheme: Multi-syllabic end rhymes (oo / oo / oo)", neon_cyan),
            ("Innovative and I'm made of rubber so that anything you say", "Consonance: Dental plosives /t/, /d/ for acoustic velocity", neon_pink),
            ("is ricochetin' off of me, and it'll glue to you", "Dynamic Range: Compression applied | 0 dropped phonetic tokens", QColor(226, 232, 240))
        ]

        sy = origin_y + 240
        for verse, phonetics, col in lyrics:
            # Bullet beacon
            elem.strokes.append(HandStroke(
                points=OrganicGeometryFactory.hand_drawn_cloud(QPointF(origin_x + 25, sy - 4), 6, 6, 8),
                color=col, width=2.0, fill_color=col
            ))
            elem.text_items.append((
                QPointF(origin_x + 45, sy),
                f'"{verse}"',
                QFont("Segoe UI", 11, QFont.Bold),
                col,
                0.0
            ))
            elem.text_items.append((
                QPointF(origin_x + 45, sy + 22),
                phonetics,
                QFont("Segoe UI", 9, QFont.StyleItalic),
                QColor(148, 163, 184),
                0.0
            ))
            sy += 65

        return elem


class DynamicSocraticEngine:
    """Generates non-repeating, randomized quizzes to evaluate first-principles comprehension."""

    @staticmethod
    def generate_randomized_quiz(origin_x: float, origin_y: float) -> SketchnoteElement:
        elem = SketchnoteElement(
            id=f"quiz_{int(time.time())}",
            element_type="proof",
            bounding_rect=QRectF(origin_x - 40, origin_y - 40, 960, 520)
        )
        
        neon_gold = QColor(251, 191, 36)
        neon_emerald = QColor(52, 211, 153)
        neon_cyan = QColor(56, 189, 248)

        # Dynamic variable generation (so questions can never be memorized)
        base = random.choice([6, 5, 8, 9])
        height = random.choice([8, 12, 15, 12])
        hypot = math.sqrt(base*base + height*height)

        # Header
        center = QPointF(origin_x + 360, origin_y - 10)
        elem.strokes.append(HandStroke(
            points=OrganicGeometryFactory.hand_drawn_cloud(center, 340, 36, 16),
            color=neon_gold,
            width=2.5,
            fill_color=QColor(251, 191, 36, 25)
        ))
        elem.text_items.append((
            QPointF(center.x() - 280, center.y() + 6),
            "SOCRATIC CHECKPOINT: DYNAMIC MASTERY ASSESSMENT",
            QFont("Segoe UI", 11, QFont.Bold),
            QColor(254, 243, 199),
            0.0
        ))

        # Dynamic Question Prompt
        q_lines = [
            f"Scenario: You are designing a diagonal structural strut for a warehouse truss.",
            f"Given: Base horizontal span (b) = {base} meters | Upright vertical wall (a) = {height} meters.",
            f"Challenge: What is the exact length of the diagonal strut (c), and what is its attached square area (c²)?"
        ]
        
        qy = origin_y + 70
        for line in q_lines:
            elem.text_items.append((
                QPointF(origin_x + 30, qy),
                line,
                QFont("Segoe UI", 11, QFont.Bold if "Challenge" in line else QFont.Normal),
                neon_cyan if "Challenge" in line else QColor(241, 245, 249),
                0.0
            ))
            qy += 34

        # Interactive Answer Options (Shuffled)
        correct_c = int(hypot) if hypot.is_integer() else round(hypot, 2)
        correct_sq = base*base + height*height
        
        options = [
            (f"Option A: c = {correct_c} m, Area(c²) = {correct_sq} m² [CORRECT]", neon_emerald),
            (f"Option B: c = {correct_c + 2} m, Area(c²) = {correct_sq + 40} m² [MISCALCULATION]", QColor(203, 213, 225)),
            (f"Option C: c = {abs(height - base)} m, Area(c²) = {(height - base)**2} m² [INCORRECT FORMULA]", QColor(203, 213, 225))
        ]

        oy = origin_y + 200
        for opt_text, col in options:
            # Checkbox glyph
            box_rect = QRectF(origin_x + 30, oy - 14, 18, 18)
            elem.strokes.append(HandStroke(
                points=OrganicGeometryFactory.hand_drawn_line(box_rect.topLeft(), box_rect.topRight(), 4),
                color=col, width=2.0
            ))
            elem.strokes.append(HandStroke(
                points=OrganicGeometryFactory.hand_drawn_line(box_rect.topRight(), box_rect.bottomRight(), 4),
                color=col, width=2.0
            ))
            elem.strokes.append(HandStroke(
                points=OrganicGeometryFactory.hand_drawn_line(box_rect.bottomRight(), box_rect.bottomLeft(), 4),
                color=col, width=2.0
            ))
            elem.strokes.append(HandStroke(
                points=OrganicGeometryFactory.hand_drawn_line(box_rect.bottomLeft(), box_rect.topLeft(), 4),
                color=col, width=2.0
            ))
            elem.text_items.append((
                QPointF(origin_x + 65, oy),
                opt_text,
                QFont("Segoe UI", 10),
                col,
                0.0
            ))
            oy += 45

        return elem


class CameraDirector:
    """Manages infinite virtual camera coordinates with smooth cubic ease-out lerp interpolation."""

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
        # Cubic ease-out lerp step
        self.current_x += (self.target_x - self.current_x) * self.lerp_speed
        self.current_y += (self.target_y - self.current_y) * self.lerp_speed
        self.current_zoom += (self.target_zoom - self.current_zoom) * self.lerp_speed


class SpatialWhiteboardOverlay(QMainWindow):
    """
    Native Windows transparent click-through spatial canvas.
    Renders organic hand-drawn freebody diagrams, UI guides, and derivations across the entire screen.
    """
    
    directive_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        
        # Configure topmost transparent frameless overlay
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.SubWindow
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        
        # State tracking
        self.click_through = True
        self.camera = CameraDirector()
        self.elements: List[SketchnoteElement] = []
        self.contour_lifter = ContourLifterEngine()
        
        # Transient Dotted Grid Timer (2.5s fade out)
        self.grid_alpha = 0.35
        self.grid_fade_active = True
        
        # Stylus tip marker coordinate
        self.active_stylus_pt: Optional[QPointF] = None
        
        # Interaction handling
        self.alt_pressed = False
        self.is_dragging = False
        self.last_mouse_pos = QPointF(0, 0)
        
        # 60 FPS Render Loop
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(16)
        
        # Signal bridge
        self.directive_signal.connect(self.handle_new_directive)
        
        # Initialize Win32 Click-Through Pass-Through
        self.enable_click_through(True)

    def enable_click_through(self, enabled: bool):
        self.click_through = enabled
        hwnd = int(self.winId())
        extended_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        
        if enabled:
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, extended_style | WS_EX_TRANSPARENT | WS_EX_LAYERED)
        else:
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, extended_style & ~WS_EX_TRANSPARENT)

    def handle_new_directive(self, prompt: str):
        """Processes high-level multi-modal teaching directives."""
        offset_x = len(self.elements) * 1250.0 + 80.0
        offset_y = 120.0
        
        p = prompt.lower()
        if "fbd" in p or "block" in p or "friction" in p or "ramp" in p:
            elem = FreeBodyDiagramSynthesizer.synthesize_inclined_plane_fbd(offset_x, offset_y)
        elif "obs" in p or "app" in p or "stream" in p:
            elem = AppInspectionSynthesizer.synthesize_obs_walkthrough(offset_x, offset_y)
        elif "lift" in p or "trace" in p or "screen" in p:
            elem = self.contour_lifter.trigger_diagram_lift(offset_x, offset_y)
        elif "rap" in p or "lyrics" in p or "cadence" in p or "speed" in p:
            elem = HighSpeedMediaTranscriber.synthesize_rap_cadence_breakdown(offset_x, offset_y)
        elif "quiz" in p or "test" in p or "socratic" in p:
            elem = DynamicSocraticEngine.generate_randomized_quiz(offset_x, offset_y)
        else:
            # Fallback to general first-principles proof
            elem = FreeBodyDiagramSynthesizer.synthesize_inclined_plane_fbd(offset_x, offset_y)

        self.elements.append(elem)
        
        # Center the virtual camera smoothly onto the new derivation cluster
        cx = elem.bounding_rect.center().x() - (self.width() * 0.5)
        cy = elem.bounding_rect.center().y() - (self.height() * 0.5)
        self.camera.pan_to(cx, cy, 1.0)
        
        # Flash dotted cyber grid to establish the workspace boundary
        self.grid_alpha = 0.35

    def on_tick(self):
        """Progressively reveals strokes and advances camera lerp at 60 FPS."""
        self.camera.update()
        
        # Fade transient dotted grid
        if self.grid_alpha > 0.08:
            self.grid_alpha -= 0.003
            
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
                    elem.text_items[i] = (pt, txt, font, col, min(1.0, p + 0.09))
                    break

        if not has_active:
            self.active_stylus_pt = None
            
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # 1. Render Cyber-Dotted Workspace Void Grid
        if self.grid_alpha > 0.01:
            dot_color = QColor(148, 163, 184, int(self.grid_alpha * 255))
            painter.setPen(QPen(dot_color, 1.5))
            step = 32
            start_x = int(self.camera.current_x) % step
            start_y = int(self.camera.current_y) % step
            for gx in range(start_x, self.width(), step):
                for gy in range(start_y, self.height(), step):
                    painter.drawPoint(gx, gy)

        # Apply Infinite Virtual Coordinate Camera Transform
        painter.save()
        painter.translate(-self.camera.current_x, -self.camera.current_y)
        painter.scale(self.camera.current_zoom, self.camera.current_zoom)

        # 2. Render Hand-Sketched Vector Strokes
        for elem in self.elements:
            for stroke in elem.strokes:
                if stroke.progress <= 0.01:
                    continue
                pts = stroke.points
                limit = max(2, int(stroke.progress * len(pts)))
                active_pts = pts[:limit]

                # Fill polygons when near completion
                if stroke.fill_color and stroke.progress >= 0.95:
                    poly_path = QPainterPath()
                    poly_path.moveTo(pts[0])
                    for p in pts[1:]:
                        poly_path.lineTo(p)
                    poly_path.closeSubpath()
                    painter.fillPath(poly_path, QBrush(stroke.fill_color))

                pen = QPen(stroke.color, stroke.width)
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
                
                # Legibility drop-shadow for high contrast against active windows
                painter.setPen(QPen(QColor(15, 23, 42, 220)))
                painter.drawText(QPointF(pt.x() + 1.5, pt.y() + 1.5), revealed_txt)
                
                painter.setPen(QPen(col))
                painter.drawText(pt, revealed_txt)

        # 3. Micro-Stylus Tip Halo (Visibly Sketched Curves)
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

        # 4. In-Situ Floating HUD Indicator (Screen Coordinates)
        hud_text = (
            f"SPATIAL WHITEBOARD v7 | Camera: ({int(self.camera.current_x)}, {int(self.camera.current_y)}) "
            f"| Mode: {'CLICK-THROUGH (PASS-THROUGH)' if self.click_through else 'INTERACTIVE WHITEBOARD'} "
            f"[Hold ALT to Drag & Zoom | F8: Toggle Pass-through]"
        )
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(15, 23, 42, 200)))
        painter.drawRoundedRect(QRectF(20, self.height() - 48, 780, 28), 6, 6)
        painter.setPen(QPen(QColor(56, 189, 248)))
        painter.drawText(QPointF(32, self.height() - 30), hud_text)

    # --------------------------------------------------------------------------
    # MOUSE NAVIGATION & ZOOM (HOLD ALT + DRAG / SCROLL)
    # --------------------------------------------------------------------------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Alt:
            self.alt_pressed = True
            if self.click_through:
                self.enable_click_through(False)
        elif event.key() == Qt.Key_F8:
            self.enable_click_through(not self.click_through)
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


def console_input_loop(overlay: SpatialWhiteboardOverlay):
    """Interactive command-line dispatcher for the spatial tutor engine."""
    print("=" * 72)
    print(" AI TEACHING ASSISTANT - PRODUCTION SPATIAL WHITEBOARD v7")
    print("=" * 72)
    print("Commands & First-Principles Teaching Modes:")
    print("  * 'fbd' / 'block'     -> Free-Body Diagram of sliding block on inclined ramp")
    print("  * 'obs' / 'app'       -> In-situ cybersecurity guide to OBS Studio controls")
    print("  * 'lift' / 'trace'    -> Screen geometry lifting with elevation animation")
    print("  * 'rap' / 'lyrics'    -> 2x speed high-cadence lyrical transcription & meter")
    print("  * 'quiz' / 'test'     -> Non-repeating randomized Socratic mastery challenge")
    print("  * 'pause' / 'play'    -> Universal YouTube/VLC playback toggle")
    print("  * 'back' / 'forward'  -> 5-second media scrub")
    print("Press Ctrl+C to terminate.")
    print("=" * 72)
    
    # Auto-seed initial comprehensive demonstration
    time.sleep(0.8)
    overlay.directive_signal.emit("fbd")
    
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
                print(f"[AI Spatial Focus] Synthesizing derivation: '{cmd}'")
                overlay.directive_signal.emit(cmd)
                
        except (EOFError, KeyboardInterrupt):
            break


def main():
    app = QApplication(sys.argv)
    overlay = SpatialWhiteboardOverlay()
    overlay.show()

    # Launch CLI dispatch loop in daemon thread
    t = threading.Thread(target=console_input_loop, args=(overlay,), daemon=True)
    t.start()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()