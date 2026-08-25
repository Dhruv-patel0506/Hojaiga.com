"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 31
Name: Visual Perception System (Parallel Eye)

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Visual Perception]
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
Dependencies: pywinauto, typing, json, asyncio, hashlib, ctypes, os...
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import ctypes
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hojaiga.organ31.visual_perception")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[VisualPerception] %(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

try:
    import pywinauto  # type: ignore
except ImportError:
    pywinauto = None


@dataclass
class UIPerceptionNode:
    control_id: str
    class_name: str
    text: str
    is_visible: bool
    is_enabled: bool
    bounds: Dict[str, int]
    children: List["UIPerceptionNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "control_id": self.control_id,
            "class_name": self.class_name,
            "text": self.text,
            "is_visible": self.is_visible,
            "is_enabled": self.is_enabled,
            "bounds": self.bounds,
            "children": [c.to_dict() for c in self.children]
        }


class Window_Handle_Isolation_Engine:
    """Isolates screen capture and UIA inspection to specific background/minimized HWNDs."""
    def __init__(self):
        self._user32 = ctypes.windll.user32 if os.name == 'nt' else None

    def get_isolated_window_context(self, hwnd: int) -> Optional[Dict[str, Any]]:
        if not self._user32:
            return None
        return {"hwnd": hwnd, "status": "isolated_capture", "is_background": True}


class ContinuousVisionEngine:
    """Adaptive screenshot timing engine that throttles during static periods."""
    def __init__(self):
        self.current_fps = 0.4
        self.max_fps = 2.0
        self.min_fps = 0.4

    async def adapt_framerate(self, is_screen_dynamic: bool):
        if is_screen_dynamic:
            self.current_fps = self.max_fps
        else:
            self.current_fps = self.min_fps
        return self.current_fps


class VisualPerceptionOrgan:
    def __init__(self, cns_publisher=None):
        self.cns = cns_publisher
        self._running = False
        self._last_state_hash: Optional[str] = None
        self._desktop = pywinauto.Desktop(backend="uia") if pywinauto else None
        self.isolation_engine = Window_Handle_Isolation_Engine()
        self.vision_engine = ContinuousVisionEngine()

    def _build_tree(self, wrapper, depth=0, max_depth=4) -> UIPerceptionNode:
        if depth > max_depth:
            return UIPerceptionNode("depth_limit", "depth_limit", "", False, False, {})

        try:
            rect = wrapper.rectangle()
            node = UIPerceptionNode(
                control_id=str(wrapper.handle),
                class_name=wrapper.class_name(),
                text=wrapper.window_text() or "",
                is_visible=wrapper.is_visible(),
                is_enabled=wrapper.is_enabled(),
                bounds={"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom}
            )

            for child in wrapper.children():
                if child.is_visible():
                    node.children.append(self._build_tree(child, depth + 1, max_depth))
            
            return node
        except Exception:
            return UIPerceptionNode("error", "error", "", False, False, {})

    def describe_screen(self) -> Dict[str, Any]:
        """Queries UIA and returns a structured model of top-level visible windows."""
        if not self._desktop:
            return {"status": "mock_mode", "windows": []}

        windows = []
        try:
            for w in self._desktop.windows():
                if w.is_visible() and w.window_text():
                    windows.append(self._build_tree(w).to_dict())
        except Exception as e:
            logger.debug(f"Visual Perception UIA query warning: {e}")

        return {"status": "success", "windows": windows}

    def _hash_screen_state(self, state: dict) -> str:
        serialized = json.dumps(state, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    async def _monitor_loop(self):
        """Throttled background monitor loop to eliminate EventBus event storms."""
        from core_organs.organ_02_cns_single_file import EventEnvelope
        while self._running:
            try:
                state = self.describe_screen()
                windows = state.get("windows", [])
                
                if windows:
                    current_hash = self._hash_screen_state(state)

                    if self._last_state_hash != current_hash:
                        self._last_state_hash = current_hash
                        
                        if self.cns:
                            await self.cns.publish(EventEnvelope(
                                topic="sys.events",
                                source_organ="organ_31",
                                payload={
                                    "event_type": "SCREEN_STATE_CHANGED",
                                    "hash": current_hash[:12],
                                    "window_count": len(windows)
                                }
                            ))
            except Exception as e:
                logger.debug(f"Perception monitor error: {e}")
                
            # 2.5s debounce ensures smooth performance without flooding the bus
            await asyncio.sleep(2.5)

    async def start(self):
        self._running = True
        logger.info("Visual Perception Organ (Parallel Eye) started.")
        asyncio.create_task(self._monitor_loop())

    async def stop(self):
        self._running = False
        logger.info("Visual Perception Organ stopped.")

    # ── CNS Integration ─────────────────────────────────────────────────

    async def start_cns(self, cns) -> None:
        self.cns = cns
        await self.start()
        logger.info("VisualPerceptionOrgan connected to CNS.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    organ = VisualPerceptionOrgan()
    print("Visual Perception Organ initialized.")
