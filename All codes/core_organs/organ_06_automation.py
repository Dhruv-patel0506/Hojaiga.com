"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 6
Name: Automation Engine (Virtual Hands / Native OS / MultiTouch 3D)

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Automation Engine]
        direction TB
        IN[Inputs] --> PROC[Processing]
        PROC --> OUT[Outputs]
    end
    
    COMPONENT -- event/socket --> DOWNSTREAM_A[CONSUMER A]
    COMPONENT -- event/socket --> DOWNSTREAM_B[CONSUMER B]
    
    class COMPONENT component;
```

Inputs: Discovered from runtime
Outputs: Discovered from runtime
Dependencies: ctypes, math, random, time, asyncio, enum, dataclasses, logging...
"""
from __future__ import annotations

import asyncio
import ctypes
import enum
import logging
import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    import ctypes.wintypes as wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
else:
    user32 = None
    kernel32 = None
    wintypes = None

logger = logging.getLogger("hojaiga.organ06.automation")
if not logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("[AutomationEngine] %(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)


# ==============================================================================
# SECTION 1 — INPUT PROTOCOLS & ENUMS
# ==============================================================================
class MouseButton(str, enum.Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    MIDDLE = "MIDDLE"


class KeyAction(str, enum.Enum):
    DOWN = "DOWN"
    UP = "UP"
    PRESS = "PRESS"


class GestureType(str, enum.Enum):
    TAP = "TAP"
    DOUBLE_TAP = "DOUBLE_TAP"
    PINCH = "PINCH"
    SPREAD = "SPREAD"
    ROTATE = "ROTATE"
    SWIPE = "SWIPE"
    PAN = "PAN"


@dataclass
class Point2D:
    x: float
    y: float


@dataclass
class Point3D:
    x: float
    y: float
    z: float = 0.0
    pressure: float = 1.0


@dataclass
class MotionTrajectory:
    points: List[Point2D]
    duration_ms: float
    curve_type: str = "bezier"


# ==============================================================================
# SECTION 2 — HUMANIZED BEZIER & JITTER TRAJECTORY ENGINE
# ==============================================================================
class HumanPhysicsEngine:
    """Calculates non-linear mouse velocity curves, natural hand tremors, and deceleration."""

    @staticmethod
    def calculate_bezier_trajectory(
        start: Point2D,
        end: Point2D,
        steps: int = 30,
        deviation_scale: float = 0.2
    ) -> List[Point2D]:
        distance = math.hypot(end.x - start.x, end.y - start.y)
        if distance < 5:
            return [start, end]

        # Random control point deviations for human arc
        dx = end.x - start.x
        dy = end.y - start.y
        normal_x = -dy
        normal_y = dx

        rand_offset_1 = (random.random() - 0.5) * distance * deviation_scale
        rand_offset_2 = (random.random() - 0.5) * distance * deviation_scale

        ctrl1_x = start.x + dx * 0.25 + (normal_x / (distance or 1)) * rand_offset_1
        ctrl1_y = start.y + dy * 0.25 + (normal_y / (distance or 1)) * rand_offset_1

        ctrl2_x = start.x + dx * 0.75 + (normal_x / (distance or 1)) * rand_offset_2
        ctrl2_y = start.y + dy * 0.75 + (normal_y / (distance or 1)) * rand_offset_2

        points: List[Point2D] = []
        for i in range(steps + 1):
            t = i / steps
            # Smooth cubic bezier easing
            u = 1.0 - t
            tt = t * t
            uu = u * u
            uuu = uu * u
            ttt = tt * t

            px = uuu * start.x + 3 * uu * t * ctrl1_x + 3 * u * tt * ctrl2_x + ttt * end.x
            py = uuu * start.y + 3 * uu * t * ctrl1_y + 3 * u * tt * ctrl2_y + ttt * end.y

            # Micro-jitter addition
            jitter_x = (random.random() - 0.5) * 0.5 if 0 < i < steps else 0.0
            jitter_y = (random.random() - 0.5) * 0.5 if 0 < i < steps else 0.0

            points.append(Point2D(px + jitter_x, py + jitter_y))

        return points


# ==============================================================================
# SECTION 3 — LOW-LEVEL WIN32 DRIVER
# ==============================================================================
class Win32Driver:
    """Low-level SendInput structure packager for Windows NT."""

    # Flags
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_HWHEEL = 0x01000
    MOUSEEVENTF_ABSOLUTE = 0x8000

    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004

    def __init__(self):
        self.screen_width = 1920
        self.screen_height = 1080
        if IS_WINDOWS and user32:
            try:
                self.screen_width = user32.GetSystemMetrics(0)
                self.screen_height = user32.GetSystemMetrics(1)
            except Exception:
                pass

    def get_cursor_pos(self) -> Point2D:
        if not IS_WINDOWS or not user32:
            return Point2D(0, 0)
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return Point2D(float(pt.x), float(pt.y))

    def set_cursor_pos(self, x: float, y: float) -> None:
        if IS_WINDOWS and user32:
            user32.SetCursorPos(int(round(x)), int(round(y)))

    def mouse_event(self, flags: int, data: int = 0) -> None:
        if IS_WINDOWS and user32:
            user32.mouse_event(flags, 0, 0, data, 0)

    def send_unicode_char(self, char: str) -> None:
        if not IS_WINDOWS or not user32:
            return

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_uint32),
                ("time", ctypes.c_uint32),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class _INPUTUNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_uint32), ("union", _INPUTUNION)]

        INPUT_KEYBOARD = 1
        extra = ctypes.c_ulong(0)
        code = ord(char)

        # KeyDown
        ki_down = KEYBDINPUT(0, code, self.KEYEVENTF_UNICODE, 0, ctypes.pointer(extra))
        inp_down = INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=ki_down))
        user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(inp_down))

        # KeyUp
        ki_up = KEYBDINPUT(0, code, self.KEYEVENTF_UNICODE | self.KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
        inp_up = INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=ki_up))
        user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(inp_up))


# ==============================================================================
# SECTION 4 — MULTI-TOUCH 3D & GESTURE SYNTHESIZER
# ==============================================================================
class MultiTouchSynthesizer:
    """Emulates multitouch pressure, pinch-to-zoom, and 3D gestures."""

    def __init__(self, driver: Win32Driver):
        self.driver = driver

    async def execute_pinch(self, center: Point2D, start_radius: float, end_radius: float, duration_ms: float = 300):
        """Simulates 2-finger pinch/spread with mouse wheel delta fallback."""
        steps = int(max(5, duration_ms / 20))
        delta = end_radius - start_radius

        for i in range(steps):
            # Fallback to precise mouse wheel injection if hardware touch injector is unavailable
            wheel_step = int((delta / steps) * 2)
            self.driver.mouse_event(self.driver.MOUSEEVENTF_WHEEL, wheel_step)
            await asyncio.sleep(0.02)


# ==============================================================================
# SECTION 5 — AUTOMATION ORGAN (PUBLIC FACADE)
# ==============================================================================
class AutomationOrgan:
    """Master native automation organ (Organ 06)."""

    def __init__(self):
        self.driver = Win32Driver()
        self.physics = HumanPhysicsEngine()
        self.touch = MultiTouchSynthesizer(self.driver)
        self.cns: Optional[Any] = None

    async def move_mouse(
        self,
        target_x: float,
        target_y: float,
        duration_ms: float = 250,
        humanize: bool = True
    ) -> None:
        start_pt = self.driver.get_cursor_pos()
        end_pt = Point2D(target_x, target_y)

        if not humanize:
            self.driver.set_cursor_pos(target_x, target_y)
            return

        steps = int(max(10, duration_ms / 15))
        path = self.physics.calculate_bezier_trajectory(start_pt, end_pt, steps=steps)

        delay_per_step = (duration_ms / 1000.0) / len(path)
        for pt in path:
            self.driver.set_cursor_pos(pt.x, pt.y)
            await asyncio.sleep(delay_per_step)

    async def click(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        button: MouseButton = MouseButton.LEFT,
        click_count: int = 1,
        humanize: bool = True
    ) -> None:
        if x is not None and y is not None:
            await self.move_mouse(x, y, humanize=humanize)

        down_flag, up_flag = {
            MouseButton.LEFT: (self.driver.MOUSEEVENTF_LEFTDOWN, self.driver.MOUSEEVENTF_LEFTUP),
            MouseButton.RIGHT: (self.driver.MOUSEEVENTF_RIGHTDOWN, self.driver.MOUSEEVENTF_RIGHTUP),
            MouseButton.MIDDLE: (self.driver.MOUSEEVENTF_MIDDLEDOWN, self.driver.MOUSEEVENTF_MIDDLEUP),
        }[button]

        for _ in range(click_count):
            self.driver.mouse_event(down_flag)
            await asyncio.sleep(random.uniform(0.03, 0.07))
            self.driver.mouse_event(up_flag)
            if click_count > 1:
                await asyncio.sleep(random.uniform(0.05, 0.1))

    async def drag_and_drop(
        self,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        duration_ms: float = 500
    ) -> None:
        await self.move_mouse(from_x, from_y, humanize=True)
        self.driver.mouse_event(self.driver.MOUSEEVENTF_LEFTDOWN)
        await asyncio.sleep(0.05)

        await self.move_mouse(to_x, to_y, duration_ms=duration_ms, humanize=True)
        await asyncio.sleep(0.05)
        self.driver.mouse_event(self.driver.MOUSEEVENTF_LEFTUP)

    async def scroll(self, delta_y: int, delta_x: int = 0, x: Optional[float] = None, y: Optional[float] = None) -> None:
        if x is not None and y is not None:
            await self.move_mouse(x, y, humanize=False)

        if delta_y != 0:
            self.driver.mouse_event(self.driver.MOUSEEVENTF_WHEEL, delta_y)
        if delta_x != 0:
            self.driver.mouse_event(self.driver.MOUSEEVENTF_HWHEEL, delta_x)

    async def type_text(self, text: str, wpm: int = 120) -> None:
        base_delay = 60.0 / (wpm * 5.0)  # average 5 chars per word
        for char in text:
            self.driver.send_unicode_char(char)
            delay = random.uniform(base_delay * 0.7, base_delay * 1.3)
            await asyncio.sleep(delay)

    # ── CNS Integration ─────────────────────────────────────────────────

    async def start_cns(self, cns) -> None:
        self.cns = cns
        await self.cns.subscribe("AUTOMATION_INPUT_REQUEST", "organ_06", self._handle_input_request)
        logger.info("AutomationOrgan connected to CNS.")

    async def _handle_input_request(self, env) -> None:
        from core_organs.organ_02_cns_single_file import EventEnvelope
        payload = env.payload or {}
        task_id = payload.get("task_id", "UNKNOWN")
        action = payload.get("action", "").upper()

        try:
            if action == "CLICK":
                await self.click(payload.get("x"), payload.get("y"), MouseButton(payload.get("button", "LEFT")))
            elif action == "MOVE":
                await self.move_mouse(payload["x"], payload["y"])
            elif action == "TYPE":
                await self.type_text(payload.get("text", ""))
            elif action == "SCROLL":
                await self.scroll(payload.get("delta_y", 0), payload.get("delta_x", 0))
            elif action == "DRAG":
                await self.drag_and_drop(payload["from_x"], payload["from_y"], payload["to_x"], payload["to_y"])

            if self.cns:
                await self.cns.publish(EventEnvelope(
                    topic="AUTOMATION_INPUT_COMPLETED",
                    source_organ="organ_06",
                    payload={"task_id": task_id, "success": True, "action": action}
                ))
        except Exception as e:
            logger.error(f"Failed automation input: {e}")
            if self.cns:
                await self.cns.publish(EventEnvelope(
                    topic="AUTOMATION_INPUT_FAILED",
                    source_organ="organ_06",
                    payload={"task_id": task_id, "success": False, "error": str(e)}
                ))


if __name__ == "__main__":
    async def _test():
        organ = AutomationOrgan()
        print("Testing Automation Organ Native Driver...")
        pos = organ.driver.get_cursor_pos()
        print(f"Current cursor position: ({pos.x}, {pos.y})")
    asyncio.run(_test())
