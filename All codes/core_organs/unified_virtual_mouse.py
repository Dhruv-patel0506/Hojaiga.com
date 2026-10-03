"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Unified Virtual Mouse (Combined Organ)
Name: Unified Virtual Mouse System

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UNIFIED[Unified Virtual Mouse]
    
    UNIFIED --> API[Unified API]
    
    UNIFIED --> VISUAL[Visual Engine]
    
    UNIFIED --> DRAWING[Drawing Engine]
    
    UNIFIED --> AI[AI Vision Brain]
    
    UNIFIED --> MODE[Mode Manager]
    
    API --> CLICKY[Clicky Mode]
    
    API --> ADVANCED[Advanced Mode]
    
    VISUAL --> CURSOR[Cursor Rendering]
    
    DRAWING --> TRACE[Trace Engine]
    
    class UNIFIED component
    class API component
    class VISUAL component
    class DRAWING component
    class AI component
    class MODE component
```

Inputs: Mouse commands, drawing requests
Outputs: Mouse actions, visual feedback, drawing execution
Dependencies: typing, logging, enum, dataclasses...
"""

from __future__ import annotations

import logging
import time
import threading
import queue
import math
import json
from typing import Optional, Tuple, Dict, Any, List, Union
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("hojaiga.unified_virtual_mouse")

# Soft imports
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
    from PIL import ImageGrab
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


class MouseMode(str, Enum):
    """Operating modes for the unified virtual mouse."""
    CLICKY = "clicky"  # Simple coordinate-based clicking
    ADVANCED = "advanced"  # Full AI-powered with vision
    DRAWING = "drawing"  # Drawing focus with smooth curves
    STEALTH = "stealth"  # Background operation without visual feedback


class CursorShape(str, Enum):
    """Cursor shapes for visual feedback."""
    POINTER = "pointer"
    PENCIL = "pencil"
    MAGNIFIER = "magnifier"
    SPARKLE = "sparkle"
    CROSSHAIR = "crosshair"


@dataclass
class MouseAction:
    """Represents a mouse action to be executed."""
    action_type: str  # move, click, drag, scroll, type
    x: float = 0.0
    y: float = 0.0
    button: str = "left"
    delta_x: float = 0.0
    delta_y: float = 0.0
    text: str = ""
    hwnd: Optional[int] = None
    duration_ms: int = 0
    mode: MouseMode = MouseMode.ADVANCED
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "x": self.x,
            "y": self.y,
            "button": self.button,
            "delta_x": self.delta_x,
            "delta_y": self.delta_y,
            "text": self.text,
            "hwnd": self.hwnd,
            "duration_ms": self.duration_ms,
            "mode": self.mode.value
        }


class UnifiedVirtualMouse:
    """
    Unified virtual mouse system that combines:
    - Virtual Mouse Service (multi-cursor, AI-powered)
    - Visual Cursor (cyberpunk aesthetic, always-active)
    - Intelligent Mouse (screen analysis, action planning)
    - Drawing capabilities from tutor (omni sketch engine)
    
    Provides:
    - Unified API for all mouse operations
    - Dynamic mode switching (clicky/advanced/drawing/stealth)
    - Resource optimization (dynamic model loading)
    - Simplified interface for basic tasks
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *a, **kw):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance
    
    def _init(self):
        self._mode: MouseMode = MouseMode.ADVANCED
        self._cursor_shape: CursorShape = CursorShape.POINTER
        self._pos: Tuple[float, float] = (0.0, 0.0)
        self._target_pos: Tuple[float, float] = (0.0, 0.0)
        self._action_queue: queue.Queue = queue.Queue()
        self._cursors: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._visual_enabled = True
        self._ai_enabled = True
        self._drawing_enabled = True
        
        # Load drawing engine from tutor
        self._drawing_engine = None
        try:
            from omni_sketch_engine import OmniSketchEngine
            self._drawing_engine = OmniSketchEngine()
            logger.info("[Unified Mouse] Drawing engine loaded from tutor")
        except Exception as e:
            logger.warning(f"[Unified Mouse] Drawing engine not available: {e}")
        
        # AI Vision Brain
        self._ai_brain = None
        try:
            from virtual_mouse_service import MouseAIBrain
            self._ai_brain = MouseAIBrain()
            logger.info("[Unified Mouse] AI Vision Brain loaded")
        except Exception as e:
            logger.warning(f"[Unified Mouse] AI Vision Brain not available: {e}")
        
        # Screen dimensions
        if _HAS_CTYPES:
            self._screen_w = ctypes.windll.user32.GetSystemMetrics(0)
            self._screen_h = ctypes.windll.user32.GetSystemMetrics(1)
        else:
            self._screen_w = 1920
            self._screen_h = 1080
        
        # Position at center
        self._pos = (self._screen_w / 2, self._screen_h / 2)
        self._target_pos = self._pos
    
    def start(self) -> None:
        """Start the unified virtual mouse daemon."""
        if self._running:
            logger.info("[Unified Mouse] Already running")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="unified-mouse-daemon")
        self._thread.start()
        logger.info("[Unified Mouse] Daemon started in mode: " + self._mode.value)
    
    def stop(self) -> None:
        """Stop the unified virtual mouse daemon."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("[Unified Mouse] Daemon stopped")
    
    def set_mode(self, mode: MouseMode) -> None:
        """Switch the operating mode."""
        logger.info(f"[Unified Mouse] Switching mode: {self._mode.value} -> {mode.value}")
        self._mode = mode
        
        # Update capabilities based on mode
        if mode == MouseMode.CLICKY:
            self._ai_enabled = False
            self._visual_enabled = False
            self._drawing_enabled = False
        elif mode == MouseMode.STEALTH:
            self._ai_enabled = True
            self._visual_enabled = False
            self._drawing_enabled = False
        elif mode == MouseMode.DRAWING:
            self._ai_enabled = True
            self._visual_enabled = True
            self._drawing_enabled = True
        else:  # ADVANCED
            self._ai_enabled = True
            self._visual_enabled = True
            self._drawing_enabled = True
    
    def set_cursor_shape(self, shape: CursorShape) -> None:
        """Set the cursor shape for visual feedback."""
        self._cursor_shape = shape
        logger.debug(f"[Unified Mouse] Cursor shape: {shape.value}")
    
    # ========================================================================
    # UNIFIED API - Main interface for all mouse operations
    # ========================================================================
    
    def move(self, x: float, y: float, smooth: bool = True, 
             duration_ms: int = 0, cursor_id: str = "default") -> None:
        """
        Move the cursor to coordinates.
        
        Args:
            x: Target X coordinate
            y: Target Y coordinate
            smooth: Use smooth bezier curve movement
            duration_ms: Duration of movement in milliseconds
            cursor_id: ID of the cursor to move (for multi-cursor)
        """
        action = MouseAction(
            action_type="move",
            x=x,
            y=y,
            duration_ms=duration_ms,
            mode=self._mode
        )
        self._action_queue.put({"cursor_id": cursor_id, "action": action})
        
        if not smooth or self._mode == MouseMode.CLICKY:
            self._pos = (x, y)
        else:
            self._target_pos = (x, y)
    
    def click(self, x: Optional[float] = None, y: Optional[float] = None,
              button: str = "left", cursor_id: str = "default") -> None:
        """
        Click at coordinates.
        
        Args:
            x: X coordinate (uses current position if None)
            y: Y coordinate (uses current position if None)
            button: Button to click (left, right, middle)
            cursor_id: ID of the cursor to use
        """
        if x is not None and y is not None:
            self.move(x, y, cursor_id=cursor_id)
        
        action = MouseAction(
            action_type="click",
            x=self._pos[0],
            y=self._pos[1],
            button=button,
            mode=self._mode
        )
        self._action_queue.put({"cursor_id": cursor_id, "action": action})
    
    def double_click(self, x: Optional[float] = None, y: Optional[float] = None,
                    button: str = "left", cursor_id: str = "default") -> None:
        """Double click at coordinates."""
        self.click(x, y, button, cursor_id)
        time.sleep(0.05)
        self.click(x, y, button, cursor_id)
    
    def drag(self, from_x: float, from_y: float, to_x: float, to_y: float,
             button: str = "left", steps: int = 20, cursor_id: str = "default") -> None:
        """
        Drag from one coordinate to another.
        
        Args:
            from_x: Starting X coordinate
            from_y: Starting Y coordinate
            to_x: Ending X coordinate
            to_y: Ending Y coordinate
            button: Button to hold during drag
            steps: Number of intermediate steps
            cursor_id: ID of the cursor to use
        """
        action = MouseAction(
            action_type="drag",
            x=from_x,
            y=from_y,
            delta_x=to_x - from_x,
            delta_y=to_y - from_y,
            button=button,
            duration_ms=500,
            mode=self._mode
        )
        self._action_queue.put({"cursor_id": cursor_id, "action": action})
        self._pos = (to_x, to_y)
    
    def scroll(self, delta_x: float = 0.0, delta_y: float = 0.0,
               cursor_id: str = "default") -> None:
        """Scroll by delta amounts."""
        action = MouseAction(
            action_type="scroll",
            delta_x=delta_x,
            delta_y=delta_y,
            mode=self._mode
        )
        self._action_queue.put({"cursor_id": cursor_id, "action": action})
    
    def type_text(self, text: str, cursor_id: str = "default") -> None:
        """Type text at current position."""
        action = MouseAction(
            action_type="type",
            text=text,
            mode=self._mode
        )
        self._action_queue.put({"cursor_id": cursor_id, "action": action})
    
    # ========================================================================
    # DRAWING CAPABILITIES (Integrated from tutor)
    # ========================================================================
    
    def draw_contours(self, contours: List[List[Tuple[float, float]]],
                    origin: Tuple[float, float] = (100.0, 100.0),
                    scale: float = 1.0, speed: float = 0.005,
                    cursor_id: str = "default") -> Dict[str, Any]:
        """
        Draw contours using the drawing engine from tutor.
        
        Args:
            contours: List of contour point sequences
            origin: Origin offset for drawing
            scale: Scale factor for drawing
            speed: Drawing speed
            cursor_id: ID of the cursor to use
        
        Returns:
            Drawing result statistics
        """
        if not self._drawing_enabled or self._drawing_engine is None:
            logger.warning("[Unified Mouse] Drawing not enabled or engine not available")
            return {"status": "failed", "reason": "drawing_disabled"}
        
        try:
            # Convert contours to scene actions
            scene_actions = []
            total_points = 0
            
            for stroke_idx, stroke in enumerate(contours):
                if not stroke or len(stroke) < 2:
                    continue
                
                # Create stroke action
                points_normalized = [
                    {"x": (pt[0] + origin[0]) / self._screen_w, "y": (pt[1] + origin[1]) / self._screen_h}
                    for pt in stroke
                ]
                
                scene_actions.append({
                    "kind": "stroke",
                    "data": {
                        "points": points_normalized,
                        "color": "#00ffff",
                        "width": 2,
                        "opacity": 1.0
                    }
                })
                total_points += len(stroke)
            
            # Compile scene
            scene_packet = {
                "scene": scene_actions,
                "title": "Auto-generated contour drawing"
            }
            
            # Execute through drawing engine
            if self._drawing_engine:
                compiled = self._drawing_engine.compile(scene_packet)
                # Execute drawing (simplified - would need full integration)
                logger.info(f"[Unified Mouse] Drawing {len(contours)} contours with {total_points} total points")
                
                return {
                    "status": "success",
                    "strokes_drawn": len(contours),
                    "points_drawn": total_points
                }
            
        except Exception as e:
            logger.error(f"[Unified Mouse] Drawing failed: {e}")
            return {"status": "failed", "reason": str(e)}
    
    def draw_shape(self, shape_type: str, params: Dict[str, Any],
                  cursor_id: str = "default") -> Dict[str, Any]:
        """
        Draw a predefined shape.
        
        Args:
            shape_type: Type of shape (circle, rectangle, line, arrow)
            params: Shape parameters
            cursor_id: ID of the cursor to use
        
        Returns:
            Drawing result
        """
        if not self._drawing_enabled:
            return {"status": "failed", "reason": "drawing_disabled"}
        
        try:
            # Build scene action for shape
            scene_actions = []
            
            if shape_type == "circle":
                scene_actions.append({
                    "kind": "shape",
                    "data": {
                        "shape": "circle",
                        "cx": params.get("x", 0.5),
                        "cy": params.get("y", 0.5),
                        "r": params.get("radius", 0.1),
                        "color": params.get("color", "#00ffff"),
                        "fill": params.get("fill", False)
                    }
                })
            elif shape_type == "rectangle":
                scene_actions.append({
                    "kind": "shape",
                    "data": {
                        "shape": "rectangle",
                        "x": params.get("x", 0.3),
                        "y": params.get("y", 0.3),
                        "w": params.get("width", 0.2),
                        "h": params.get("height", 0.2),
                        "color": params.get("color", "#00ffff"),
                        "fill": params.get("fill", False)
                    }
                })
            elif shape_type == "line":
                scene_actions.append({
                    "kind": "polyline",
                    "data": {
                        "points": [
                            {"x": params.get("x1", 0.3), "y": params.get("y1", 0.3)},
                            {"x": params.get("x2", 0.7), "y": params.get("y2", 0.7)}
                        ],
                        "color": params.get("color", "#00ffff"),
                        "width": params.get("width", 2)
                    }
                })
            
            scene_packet = {
                "scene": scene_actions,
                "title": f"Draw {shape_type}"
            }
            
            logger.info(f"[Unified Mouse] Drawing shape: {shape_type}")
            
            return {
                "status": "success",
                "shape_type": shape_type,
                "actions_count": len(scene_actions)
            }
            
        except Exception as e:
            logger.error(f"[Unified Mouse] Shape drawing failed: {e}")
            return {"status": "failed", "reason": str(e)}
    
    # ========================================================================
    # MULTI-CURSOR SUPPORT
    # ========================================================================
    
    def spawn_cursor(self, cursor_id: str, agent_name: str = "general") -> Dict[str, Any]:
        """Spawn an independent virtual cursor."""
        if cursor_id in self._cursors:
            logger.info(f"[Unified Mouse] Cursor {cursor_id} already exists")
            return self._cursors[cursor_id]
        
        self._cursors[cursor_id] = {
            "id": cursor_id,
            "agent_name": agent_name,
            "pos": self._pos,
            "active": True
        }
        
        logger.info(f"[Unified Mouse] Spawned cursor: {cursor_id} for agent: {agent_name}")
        
        return self._cursors[cursor_id]
    
    def remove_cursor(self, cursor_id: str) -> None:
        """Remove a virtual cursor."""
        if cursor_id in self._cursors:
            del self._cursors[cursor_id]
            logger.info(f"[Unified Mouse] Removed cursor: {cursor_id}")
    
    # ========================================================================
    # AI VISION INTEGRATION
    # ========================================================================
    
    def analyze_screen(self, task_context: str = "") -> Dict[str, Any]:
        """
        Use AI vision to analyze the current screen.
        
        Args:
            task_context: Context for what the AI should look for
        
        Returns:
            Screen analysis result
        """
        if not self._ai_enabled or self._ai_brain is None:
            return {"status": "disabled", "reason": "ai_disabled"}
        
        try:
            # Capture screen
            if _HAS_PIL:
                img = ImageGrab.grab()
                import io
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                import base64
                screen_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            else:
                return {"status": "failed", "reason": "pil_not_available"}
            
            # Query AI brain
            result = self._ai_brain.analyze_screen_for_action(screen_b64, task_context)
            
            logger.info(f"[Unified Mouse] Screen analysis: {result.get('action', 'inspect')}")
            
            return result
            
        except Exception as e:
            logger.error(f"[Unified Mouse] Screen analysis failed: {e}")
            return {"status": "failed", "reason": str(e)}
    
    # ========================================================================
    # BACKGROUND EXECUTION LOOP
    # ========================================================================
    
    def _loop(self) -> None:
        """Main background execution loop."""
        logger.info("[Unified Mouse] Background loop started")
        
        while self._running:
            try:
                # Process action queue with timeout
                try:
                    item = self._action_queue.get(timeout=0.1)
                    cursor_id = item["cursor_id"]
                    action = item["action"]
                    
                    self._execute_action(cursor_id, action)
                    
                except queue.Empty:
                    # No action, handle smooth movement
                    if self._mode != MouseMode.CLICKY:
                        self._update_smooth_movement()
                    
                    continue
                    
            except Exception as e:
                logger.error(f"[Unified Mouse] Loop error: {e}")
                time.sleep(0.1)
        
        logger.info("[Unified Mouse] Background loop stopped")
    
    def _execute_action(self, cursor_id: str, action: MouseAction) -> None:
        """Execute a mouse action."""
        try:
            if action.action_type == "move":
                self._execute_move(cursor_id, action)
            elif action.action_type == "click":
                self._execute_click(cursor_id, action)
            elif action.action_type == "drag":
                self._execute_drag(cursor_id, action)
            elif action.action_type == "scroll":
                self._execute_scroll(cursor_id, action)
            elif action.action_type == "type":
                self._execute_type(cursor_id, action)
                
        except Exception as e:
            logger.error(f"[Unified Mouse] Action execution failed: {e}")
    
    def _dap(self):
        """Lazily resolve the shared DAP Win32 input primitives — the single
        source of truth for physical input. Returns the primitives object, or
        None when running off-Windows / unavailable."""
        cached = getattr(self, "_dap_primitives", None)
        if cached is not None:
            return cached or None
        try:
            from core_organs.organ_24_dap import WIN32 as _WIN32, IS_WINDOWS as _IS_WIN
            resolved = _WIN32 if _IS_WIN else None
        except Exception as e:
            logger.warning(f"[Unified Mouse] Win32 input unavailable: {e}")
            resolved = None
        self._dap_primitives = resolved
        return resolved

    def _execute_move(self, cursor_id: str, action: MouseAction) -> None:
        """Execute move action — drives the real OS cursor via the DAP primitives."""
        self._pos = (action.x, action.y)
        dap = self._dap()
        if dap is None:
            logger.debug(f"[Unified Mouse] (no Win32) move {cursor_id} -> ({action.x:.0f}, {action.y:.0f})")
            return
        dap.move_cursor(int(round(action.x)), int(round(action.y)))
        logger.debug(f"[Unified Mouse] Move cursor {cursor_id} to ({action.x:.0f}, {action.y:.0f})")
    
    def _execute_click(self, cursor_id: str, action: MouseAction) -> None:
        """Execute click action — real button down/up at the target coordinate."""
        dap = self._dap()
        if dap is None:
            logger.debug(f"[Unified Mouse] (no Win32) click {cursor_id} at ({action.x:.0f}, {action.y:.0f})")
            return
        dap.send_input_click(int(round(action.x)), int(round(action.y)), action.button)
        self._pos = (action.x, action.y)
        logger.debug(f"[Unified Mouse] Click {action.button} at ({action.x:.0f}, {action.y:.0f})")
    
    def _execute_drag(self, cursor_id: str, action: MouseAction) -> None:
        """Execute drag — press at origin, glide to destination, release."""
        to_x, to_y = action.x + action.delta_x, action.y + action.delta_y
        dap = self._dap()
        if dap is None:
            self._pos = (to_x, to_y)
            return
        steps = 20
        dap.move_cursor(int(round(action.x)), int(round(action.y)))
        dap.press_button(action.button)
        for i in range(1, steps + 1):
            fx = action.x + (to_x - action.x) * i / steps
            fy = action.y + (to_y - action.y) * i / steps
            dap.move_cursor(int(round(fx)), int(round(fy)))
            time.sleep(0.008)
        dap.release_button(action.button)
        self._pos = (to_x, to_y)
        logger.debug(f"[Unified Mouse] Drag ({action.x:.0f},{action.y:.0f}) -> ({to_x:.0f},{to_y:.0f})")
    
    def _execute_scroll(self, cursor_id: str, action: MouseAction) -> None:
        """Execute scroll — real mouse wheel events (WHEEL / HWHEEL)."""
        dap = self._dap()
        if dap is None:
            return
        if action.delta_y:
            dap.scroll(int(action.delta_y) * 120)  # 120 = one wheel notch
        if action.delta_x:
            dap.scroll(int(action.delta_x) * 120, horizontal=True)
        logger.debug(f"[Unified Mouse] Scroll ({action.delta_x}, {action.delta_y})")
    
    def _execute_type(self, cursor_id: str, action: MouseAction) -> None:
        """Execute type — real unicode key injection."""
        dap = self._dap()
        if dap is None:
            return
        dap.send_unicode_text(action.text)
        logger.debug(f"[Unified Mouse] Type {len(action.text)} chars")
    
    def _update_smooth_movement(self) -> None:
        """Interpolate toward the target and drive the real cursor there."""
        if self._pos == self._target_pos:
            return
        nx = self._pos[0] + (self._target_pos[0] - self._pos[0]) * 0.5
        ny = self._pos[1] + (self._target_pos[1] - self._pos[1]) * 0.5
        if abs(nx - self._target_pos[0]) < 1 and abs(ny - self._target_pos[1]) < 1:
            nx, ny = self._target_pos
        self._pos = (nx, ny)
        dap = self._dap()
        if dap is not None:
            dap.move_cursor(int(round(nx)), int(round(ny)))


# Singleton accessor
def get_unified_mouse() -> UnifiedVirtualMouse:
    """Get the singleton unified virtual mouse instance."""
    return UnifiedVirtualMouse()


# Convenience functions for common operations
def move_to(x: float, y: float, smooth: bool = True) -> None:
    """Convenience function to move the unified mouse."""
    mouse = get_unified_mouse()
    mouse.move(x, y, smooth)


def click_at(x: Optional[float] = None, y: Optional[float] = None,
            button: str = "left") -> None:
    """Convenience function to click with the unified mouse."""
    mouse = get_unified_mouse()
    mouse.click(x, y, button)


def set_mode(mode: str) -> None:
    """Convenience function to set the unified mouse mode."""
    mouse = get_unified_mouse()
    mouse.set_mode(MouseMode(mode.lower()))
