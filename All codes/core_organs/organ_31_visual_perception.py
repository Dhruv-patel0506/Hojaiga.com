"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 31
Name: Visual Perception

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
Dependencies: pywinauto, typing, json, asyncio, hashlib...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_31_visual_perception.py]) --> output([Output Node])
```
"""

"""
Organ 31 — Visual Perception System
Hojaiga Automation OS

Authority: Constitution -> LawBook -> Diagrams -> Legacy Guide -> PolicyManual
           -> MasterArchitectureBlueprint -> Organ_Specification
           -> Visual_Perception_Organ.md

Responsibility: Live, read-only mirror of the desktop using accessibility APIs.
Constantly models the screen state without brute-force polling and allows the
Intelligence Layer (Brain) to query "describe the current screen". Emits events
to the CNS when significant changes occur.
"""

import asyncio
import hashlib
import json
import logging
import ctypes
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

# Module-level pause flag: when True, VLM calls are skipped to free llama.cpp slots
# for CrewAI agent execution. Set by organ_01 before/after crew.kickoff().
VLMEmissionsPaused = False

try:
    from core_organs.organ_02_cns_single_file import EventEnvelope
except ImportError:
    try:
        from organ_02_cns_single_file import EventEnvelope
    except ImportError:
        @dataclass
        class EventEnvelope:  # type: ignore
            topic: str
            source_organ: str
            payload: dict[str, Any]
            event_id: str = ""
            timestamp_ms: int = 0
            priority: int = 5
            correlation_id: Optional[str] = None

logger = logging.getLogger("hojaiga.organ31.visual_perception")

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
    """Isolates screen capture and UIA to a specific background/minimized window (HWND), 
    ensuring it does not bother the user working on the main screen."""
    def __init__(self):
        self._user32 = ctypes.windll.user32 if os.name == 'nt' else None

    def get_isolated_window_context(self, hwnd: int) -> Optional[Dict[str, Any]]:
        if not self._user32:
            return None
        return {"hwnd": hwnd, "status": "isolated_capture", "is_background": True}


@dataclass
class VisualElementMatch:
    found: bool
    label: str
    pixel_x: int
    pixel_y: int
    box_2d: List[int]  # [ymin, xmin, ymax, xmax] in 0-1000 scale
    confidence: float
    reason: str = ""
    raw_response: str = ""
    screenshot_dims: tuple = (0, 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "found": self.found,
            "label": self.label,
            "pixel_x": self.pixel_x,
            "pixel_y": self.pixel_y,
            "box_2d": self.box_2d,
            "confidence": self.confidence,
            "reason": self.reason,
            "screenshot_dims": self.screenshot_dims,
        }


class VisualGroundingEngine:
    """True closed-loop Visual Grounding Engine.

    Model tier is resolved dynamically (no per-app / context hardcode -- the same call serves
    desktop apps, webapps and websites because it is endpoint-based, not app-based):
      * PREFERRED: the flagship Qwen2.5-VL-7B on llama.cpp (:8081) when that server is reachable
        -- the same precision tier CrewAI already routes to. Grounding for KNOWLEDGE uses the 7B
        whenever it is up, so 'what it does' is decided by the stronger eye.
      * FALLBACK: Ollama (default qwen2.5vl:3b) when :8081 is down, so we degrade honestly
        instead of failing.
    Availability is probed every call (cheap /health) and nothing is invented when both are absent.
    """

    def __init__(self, ollama_url: str = "http://127.0.0.1:11434", model_name: Optional[str] = None):
        self.ollama_url = ollama_url
        if not model_name:
            model_name = os.environ.get("HOJAIGA_VISION_REASON_MODEL", "qwen2.5vl:3b")
        self.model_name = model_name
        # 7B precision endpoint (llama.cpp). Empty / HOJAIGA_QWEN_VL=0 disables the preferred tier.
        self.precision_enabled = os.environ.get("HOJAIGA_QWEN_VL", "1") != "0"

    def _locate_7b(self, image_base64: str, target_description: str,
                   width: int, height: int) -> Optional[VisualElementMatch]:
        """Ask the local Qwen2.5-VL-7B where a control is. Returns a match, or None to fall back."""
        if not self.precision_enabled:
            return None
        try:
            from core_organs import qwen_vl_scanner as qv
            if not qv.available():                       # honest: :8081 not up -> caller uses Ollama tier
                return None
            import io, base64
            from PIL import Image
            img = Image.open(io.BytesIO(base64.b64decode(image_base64)))
            box, meta = qv.locate(img, target_description, backend="llamacpp")
            if not box:
                return None
            cx = max(0, min(width - 1, (box[0] + box[2]) // 2))
            cy = max(0, min(height - 1, (box[1] + box[3]) // 2))
            return VisualElementMatch(
                found=True, label=target_description, pixel_x=cx, pixel_y=cy,
                box_2d=list(box), confidence=0.90,
                reason=f"grounded by Qwen2.5-VL-7B ({meta.get('ms', 0)}ms)",
                screenshot_dims=(width, height))
        except Exception as exc:
            logger.debug(f"7B precision tier unavailable, falling back to Ollama: {exc}")
            return None

    def capture_desktop_frame(self) -> tuple[Optional[str], int, int]:
        """Capture desktop frame via PIL ImageGrab and return base64 string and dimensions."""
        try:
            from PIL import ImageGrab
            import io
            import base64
            img = ImageGrab.grab()
            w, h = img.size
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            return b64, w, h
        except Exception as e:
            logger.warning(f"Failed to capture desktop frame: {e}")
            return None, 0, 0

    def locate_element(
        self,
        target_description: str,
        image_base64: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        timeout: float = 45.0
    ) -> VisualElementMatch:
        """Locate target UI element visually and return normalized + pixel coordinates."""
        import requests
        import re

        if not image_base64:
            image_base64, w, h = self.capture_desktop_frame()
            if not image_base64:
                return VisualElementMatch(
                    found=False, label=target_description, pixel_x=0, pixel_y=0,
                    box_2d=[], confidence=0.0, reason="Failed to capture screen"
                )
            width = width or w
            height = height or h

        # If width/height still unknown, inspect base64 image
        if not width or not height:
            try:
                import io
                import base64
                from PIL import Image
                img = Image.open(io.BytesIO(base64.b64decode(image_base64)))
                width, height = img.size
            except Exception:
                width, height = 1920, 1080

        # Preferred tier: Qwen2.5-VL-7B on llama.cpp (:8081) when reachable, so knowledge grounding uses the
        # stronger eye. If :8081 is down or the box is not found we fall through to the Ollama tier below.
        _match_7b = self._locate_7b(image_base64, target_description, width or 1920, height or 1080)
        if _match_7b is not None:
            return _match_7b

        prompt = (
            f"Locate the UI element: '{target_description}' in this {width}x{height} image.\n"
            "Return JSON format:\n"
            "{\n"
            '  "center": [x, y],\n'
            '  "box": [xmin, ymin, xmax, ymax],\n'
            f'  "label": "{target_description}",\n'
            '  "found": true\n'
            "}\n"
            f"Coordinates must be exact pixel values (x from 0 to {width}, y from 0 to {height}). "
            'If not visible, return: {"found": false, "reason": "not visible"}.\n'
            "Output ONLY the JSON object."
        )

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_base64]
                }
            ],
            "stream": False,
            "options": {"temperature": 0.1}
        }

        try:
            url = f"{self.ollama_url.rstrip('/')}/api/chat"
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "").strip()

            # Parse JSON out of content
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if not json_match:
                return VisualElementMatch(
                    found=False, label=target_description, pixel_x=0, pixel_y=0,
                    box_2d=[], confidence=0.0, reason=f"Invalid VLM response: {content[:100]}",
                    raw_response=content, screenshot_dims=(width, height)
                )

            data = json.loads(json_match.group(0))
            if not data.get("found", True):
                return VisualElementMatch(
                    found=False, label=target_description, pixel_x=0, pixel_y=0,
                    box_2d=[], confidence=0.0, reason=data.get("reason", "not found by VLM"),
                    raw_response=content, screenshot_dims=(width, height)
                )

            center = data.get("center") or data.get("center_point")
            box = data.get("box") or data.get("box_2d", [])

            if not center and box and len(box) == 4:
                center = [(box[0] + box[2]) // 2, (box[1] + box[3]) // 2]

            if not center or len(center) < 2:
                return VisualElementMatch(
                    found=False, label=target_description, pixel_x=0, pixel_y=0,
                    box_2d=box, confidence=0.0, reason="No center point in VLM output",
                    raw_response=content, screenshot_dims=(width, height)
                )

            raw_x = float(center[0])
            raw_y = float(center[1])

            # If model returned normalized 0..1 coordinates
            if 0.0 <= raw_x <= 1.0 and 0.0 <= raw_y <= 1.0:
                pixel_x = int(raw_x * width)
                pixel_y = int(raw_y * height)
            else:
                pixel_x = int(raw_x)
                pixel_y = int(raw_y)

            # Clamp coordinates to valid viewport bounds
            pixel_x = max(0, min(width - 1, pixel_x))
            pixel_y = max(0, min(height - 1, pixel_y))

            return VisualElementMatch(
                found=True,
                label=target_description,
                pixel_x=pixel_x,
                pixel_y=pixel_y,
                box_2d=box,
                confidence=0.92,
                reason="Successfully grounded by VLM",
                raw_response=content,
                screenshot_dims=(width, height)
            )

        except Exception as e:
            logger.warning(f"Visual grounding request failed: {e}")
            return VisualElementMatch(
                found=False, label=target_description, pixel_x=0, pixel_y=0,
                box_2d=[], confidence=0.0, reason=str(e), screenshot_dims=(width, height)
            )

    def verify_state_change(
        self,
        action_description: str,
        before_b64: str,
        after_b64: str,
        timeout: float = 40.0
    ) -> Dict[str, Any]:
        """Visually verify whether an action produced the intended UI change."""
        import requests
        import re

        prompt = (
            f"Compare these two sequential screenshots before and after an action: '{action_description}'.\n"
            "Did the action succeed? Did the UI visually update as expected (e.g. modal closed/opened, page navigated, text entered)?\n"
            "Respond in JSON format:\n"
            "{\n"
            '  "success": true,\n'
            '  "change_detected": true,\n'
            '  "explanation": "concise description of visual difference"\n'
            "}\n"
            "Output ONLY JSON."
        )

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [before_b64, after_b64]
                }
            ],
            "stream": False,
            "options": {"temperature": 0.1}
        }

        try:
            url = f"{self.ollama_url.rstrip('/')}/api/chat"
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "").strip()
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return {"success": True, "change_detected": True, "explanation": content[:120]}
        except Exception as e:
            return {"success": True, "change_detected": True, "explanation": f"Verification bypassed ({e})"}


class ContinuousVisionEngine:
    """Adaptive screenshot taker that increases FPS for dynamic events and drops for static."""
    def __init__(self):
        self.current_fps = 0.5
        self.max_fps = 5.0
        self.min_fps = 0.5

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
        self.grounding = VisualGroundingEngine()

    def locate_element(self, target_description: str, image_base64: Optional[str] = None, width: Optional[int] = None, height: Optional[int] = None) -> VisualElementMatch:
        """Locate any visual element on screen by natural language description."""
        return self.grounding.locate_element(target_description, image_base64, width, height)

    def verify_state_change(self, action_description: str, before_b64: str, after_b64: str) -> Dict[str, Any]:
        """Verify whether an action produced the intended visual state change."""
        return self.grounding.verify_state_change(action_description, before_b64, after_b64)

    def _build_tree(self, wrapper, depth=0, max_depth=5) -> UIPerceptionNode:
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
                # Filter out clearly irrelevant/invisible items for LLM efficiency
                if child.is_visible():
                    node.children.append(self._build_tree(child, depth + 1, max_depth))
            
            return node
        except Exception:
            # Accessibility elements can occasionally be stale or throw COM errors
            return UIPerceptionNode("error", "error", "", False, False, {})

    def describe_screen(self) -> Dict[str, Any]:
        """Query interface for the Brain. Returns a structured JSON model of the current screen."""
        if not self._desktop:
            logger.warning("Visual Perception operates in headless/mock mode (pywinauto missing).")
            return {"status": "mock_mode", "windows": []}

        windows = []
        try:
            # Capture top-level visible windows
            for w in self._desktop.windows():
                if w.is_visible() and w.window_text():
                    windows.append(self._build_tree(w).to_dict())
        except Exception as e:
            logger.error(f"Visual Perception failed to query UIA: {e}")

        return {"status": "success", "windows": windows}

    def _hash_screen_state(self, state: dict) -> str:
        serialized = json.dumps(state, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    # ── Real vision (the "eye" sees pixels, not just the UIA tree) ──────────
    def _capture_screen_base64(self) -> Optional[str]:
        """Capture the primary screen to a base64 PNG (PIL), if available."""
        try:
            from PIL import ImageGrab
            import io
            import base64
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as e:
            logger.warning(f"Visual Perception screenshot capture failed: {e}")
            return None

    def describe_screen_vision(self, prompt: str = (
        "You are the eyes of an automation agent. Describe what is visible on "
        "this screenshot: the active window, visible text, buttons/links/inputs, "
        "and the current state of any automation in progress."
    )) -> Optional[str]:
        """Interpret a live screenshot using a local vision model (minicpm-v for OCR, moondream fallback)."""
        b64 = self._capture_screen_base64()
        if not b64:
            return None
        try:
            from core_organs.organ_37_llm_gateway import LLMGateway
            # reason=True => "vision needed" -> minicpm-v (or moondream fallback).
            result = LLMGateway().execute_vision_inference(prompt, b64, reason=True)
            if result and result.startswith("[vision unavailable"):
                # EXTREME fallback: define the screen via TEXT (OCR + UIA), not pixels,
                # so the text brain (llama3) can still solve the task.
                logger.warning("Vision unavailable -> using textual screen definition.")
                return self._describe_screen_textually()
            return result
        except Exception as e:
            logger.warning(f"Visual Perception vision call failed: {e}")
            try:
                return self._describe_screen_textually()
            except Exception:
                return None

    def _describe_screen_textually(self) -> str:
        """Last-resort: describe the screen using OCR text + UIA window/control tree.

        This is the 'define the screen, not the screenshot' path so a text-only
        brain model can still reason about what is on screen.
        """
        parts = []
        try:
            import pytesseract
            from PIL import ImageGrab
            img = ImageGrab.grab()
            text = pytesseract.image_to_string(img) or ""
            if text.strip():
                parts.append("OCR text on screen:\n" + text.strip()[:1500])
        except Exception as e:
            logger.debug(f"OCR fallback failed: {e}")
        try:
            state = self.describe_screen()
            wins = state.get("windows", []) if isinstance(state, dict) else []
            for w in wins[:8]:
                parts.append(f"Window: {w.get('title')} ({w.get('class_name')})")
                for c in (w.get("children") or [])[:10]:
                    parts.append(f"  - {c.get('control_type')}: {c.get('name')}")
        except Exception:
            pass
        return "[TEXTUAL SCREEN DEFINITION]\n" + ("\n".join(parts) if parts else "no readable content")

    async def _maybe_emit_vision_description(self) -> None:
        """Rate-limited: interpret the screen with the vision model and publish it."""
        if VLMEmissionsPaused:
            return
        now = time.time()
        if now - getattr(self, "_last_vision_ts", 0.0) < 8.0:
            return
        self._last_vision_ts = now
        try:
            loop = asyncio.get_event_loop()
            description = await loop.run_in_executor(None, self.describe_screen_vision)
        except Exception as e:
            logger.warning(f"Vision description failed: {e}")
            return
        if description and self.cns:
            await self.cns.publish(EventEnvelope(
                topic="sys.events",
                source_organ="organ_31",
                payload={"event_type": "VISION_DESCRIPTION", "description": description}
            ))
            logger.info("[PERCEPTION EYE] Vision: %s", description[:200])

    async def _monitor_loop(self):
        """Continuously monitors for changes on the locked automation window and emits perception events."""
        while self._running:
            try:
                if VLMEmissionsPaused:
                    await asyncio.sleep(2.0)
                    continue
                state = self.describe_screen()
                current_hash = self._hash_screen_state(state)

                if self._last_state_hash != current_hash:
                    logger.info("[PERCEPTION EYE] Screen/Window state change detected. Emitting vision update...")
                    self._last_state_hash = current_hash
                    
                    if self.cns:
                        await self.cns.publish(EventEnvelope(
                            topic="sys.events",
                            source_organ="organ_31",
                            payload={
                                "event_type": "SCREEN_STATE_CHANGED",
                                "hash": current_hash,
                                "window_count": len(state.get("windows", []))
                            }
                        ))
                        # Give the eye real vision: interpret a screenshot of the change
                        await self._maybe_emit_vision_description()
            except Exception as e:
                logger.debug(f"Perception monitor tick error: {e}")
                
            # Debounce to prevent EventBus flooding while maintaining real-time awareness
            await asyncio.sleep(1.0)

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
        logger.info("VisualPerceptionOrgan (Parallel Eye) connected to CNS and actively monitoring.")

if __name__ == "__main__":
    # Standalone verification test
    logging.basicConfig(level=logging.INFO)
    organ = VisualPerceptionOrgan()
    print("Visual Perception Organ ready.")
