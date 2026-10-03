"""
Organ 41 — Scanner Organ (Continuous UI DOM/UIA Tree Mapping & Vision Parsing)

Responsibility: Exclusively responsible for continuous UI DOM/UIA tree mapping and vision parsing.
Feeds a standardized JSON state to the active agent.
Maintains a live visual buffer that feeds the latest frame to the engine.
If the UI changes drastically (e.g., a popup appears), flags an interrupt to the active task.

Architecture:
  - Continuous polling loop (adaptive FPS based on screen dynamics)
  - Fast capture chain: dxcam (DXGI Desktop Duplication) -> mss -> PIL
    ImageGrab, with cv2 JPEG encoding when available (~6x faster grabs)
  - Single-pass UIA tree walk (elements + raw tree from one traversal)
  - Vision model integration for element recognition
  - Change detection via hash comparison (orjson when available)
  - Event emission to CNS on significant changes
"""

import asyncio
import hashlib
import json
import logging
import os
import sys
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

try:
    from core_organs.organ_02_cns_single_file import EventEnvelope
except ImportError:
    try:
        from organ_02_cns_single_file import EventEnvelope
    except ImportError:
        @dataclass
        class EventEnvelope:
            topic: str
            source_organ: str
            payload: dict[str, Any]
            event_id: str = ""
            timestamp_ms: int = 0
            priority: int = 5
            correlation_id: Optional[str] = None

logger = logging.getLogger("hojaiga.organ41.scanner")

try:
    import orjson as _orjson
except ImportError:
    _orjson = None


def _stable_json_bytes(obj: Any) -> bytes:
    """Deterministic JSON -> bytes for hashing (orjson fast path when present)."""
    if _orjson is not None:
        try:
            return _orjson.dumps(obj, option=_orjson.OPT_SORT_KEYS)
        except Exception:
            pass
    return json.dumps(obj, sort_keys=True).encode("utf-8")


def _is_control_visible(control) -> bool:
    """Version-robust visibility check for uiautomation controls.

    uiautomation v2 exposes ``IsOffscreen`` (visible == not offscreen) and has
    no ``IsVisible`` attribute; some other versions expose ``IsVisible``. This
    helper supports both APIs so the scanner works across package versions.
    """
    try:
        v = getattr(control, "IsVisible", None)
        if v is not None:
            return bool(v() if callable(v) else v)
    except Exception:
        pass
    try:
        return not control.IsOffscreen
    except Exception:
        return True


class ScreenState(Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"
    CHANGED = "changed"


@dataclass
class UIElement:
    """Standardized UI element representation."""
    control_id: str
    class_name: str
    text: str
    bounds: Tuple[int, int, int, int]  # (left, top, right, bottom)
    is_visible: bool
    is_enabled: bool
    control_type: str
    parent_id: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "control_id": self.control_id,
            "class_name": self.class_name,
            "text": self.text,
            "bounds": self.bounds,
            "is_visible": self.is_visible,
            "is_enabled": self.is_enabled,
            "control_type": self.control_type,
            "parent_id": self.parent_id,
            "confidence": self.confidence,
        }


@dataclass
class ScreenSnapshot:
    """Complete screen state at a point in time."""
    timestamp: float
    hash: str
    state: ScreenState
    elements: List[UIElement] = field(default_factory=list)
    active_window: Optional[Dict[str, Any]] = None
    vision_data: Optional[str] = None  # base64 screenshot
    raw_uia_tree: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "hash": self.hash,
            "state": self.state.value,
            "elements": [e.to_dict() for e in self.elements],
            "active_window": self.active_window,
            "vision_data": self.vision_data,
            "raw_uia_tree": self.raw_uia_tree,
        }


class ContinuousVisionBuffer:
    """Maintains a rolling buffer of recent screen states for change detection."""

    def __init__(self, max_size: int = 10):
        self._buffer: List[ScreenSnapshot] = []
        self._lock = threading.Lock()
        self._max_size = max_size

    def add(self, snapshot: ScreenSnapshot):
        with self._lock:
            self._buffer.append(snapshot)
            if len(self._buffer) > self._max_size:
                self._buffer.pop(0)

    def get_latest(self) -> Optional[ScreenSnapshot]:
        with self._lock:
            return self._buffer[-1] if self._buffer else None

    def get_previous(self) -> Optional[ScreenSnapshot]:
        with self._lock:
            return self._buffer[-2] if len(self._buffer) >= 2 else None

    def detect_change(self, current_hash: str) -> bool:
        """Check if the current hash differs from the previous snapshot."""
        with self._lock:
            if len(self._buffer) < 2:
                return True
            return self._buffer[-2].hash != current_hash


class ScannerOrgan:
    """
    Continuous UI DOM/UIA Tree Mapping & Vision Parsing Organ.

    Features:
    - Adaptive polling (0.5-5 FPS based on screen dynamics)
    - UIA tree extraction with hierarchical caching
    - Vision model integration for element recognition
    - Change detection via hash comparison
    - Event emission to CNS on significant changes
    """

    def __init__(self, cns_publisher=None, vision_model_url: str = "http://127.0.0.1:11434"):
        self.cns = cns_publisher
        self.vision_model_url = vision_model_url
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._buffer = ContinuousVisionBuffer(max_size=10)
        self._visual_cursor = None  # Will be set externally for visual feedback

        # Adaptive polling parameters
        self.min_fps = 0.5
        self.max_fps = 5.0
        self.current_fps = 0.5
        self.static_threshold = 3  # consecutive static frames before dropping FPS

        # Change detection
        self._static_counter = 0
        self._last_significant_change = 0.0

        # UIA extraction
        try:
            import uiautomation as auto
            auto.SetGlobalSearchTimeout(1.0)
            self._uia = auto
        except ImportError:
            self._uia = None
            logger.warning("[Scanner] uiautomation not available - UIA extraction disabled")

        # Vision capture
        try:
            from PIL import ImageGrab
            self._image_grab = ImageGrab
        except ImportError:
            self._image_grab = None
            logger.warning("[Scanner] PIL ImageGrab not available - vision capture disabled")

        # ---- Fast capture / encode backends (all optional, degrade gracefully) ----
        # Capture priority: dxcam (DXGI Desktop Duplication) > mss > PIL ImageGrab.
        # Encoding priority: cv2.imencode > PIL save.
        try:
            import dxcam
            self._dxcam = dxcam
        except ImportError:
            self._dxcam = None
        try:
            import mss as mss_module
            self._mss = mss_module
        except ImportError:
            self._mss = None
        try:
            import cv2
            self._cv2 = cv2
        except ImportError:
            self._cv2 = None

        # Capture handles are not thread-safe; keep one set per thread.
        self._tls = threading.local()
        self._last_frame = None  # last raw frame (numpy BGR array or PIL Image)

        # Capture / encode tuning (environment-overridable)
        self._jpeg_quality = int(os.environ.get("HOJAIGA_SCAN_JPEG_QUALITY", "85"))
        # Vision frames are downscaled to at most this width before encoding
        # (0 = keep full resolution). Smaller frames encode much faster and
        # are still more than enough for VLM context.
        self._vision_max_width = int(os.environ.get("HOJAIGA_SCAN_VISION_WIDTH", "1280"))
        # UIA frame walk knobs
        self._element_max_depth = int(os.environ.get("HOJAIGA_SCAN_ELEMENT_DEPTH", "8"))
        self._max_nodes = int(os.environ.get("HOJAIGA_SCAN_MAX_NODES", "3000"))
        # Time budget for one frame walk in milliseconds (0 = unlimited). Rich
        # trees cost ~1ms per UIA property read; the budget keeps the
        # continuous loop responsive while still collecting a stable prefix
        # of the tree (walk order is deterministic).
        self._walk_budget_ms = int(os.environ.get("HOJAIGA_SCAN_WALK_BUDGET_MS", "400"))

    def set_visual_cursor(self, visual_cursor):
        """Set visual cursor instance for feedback during scanning."""
        self._visual_cursor = visual_cursor

    def start(self):
        """Start continuous scanning loop."""
        if self._running:
            logger.warning("[Scanner] Already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._thread.start()
        logger.info("[Scanner] Started continuous scanning")

    def stop(self):
        """Stop continuous scanning loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("[Scanner] Stopped continuous scanning")

    def _scan_loop(self):
        """Main scanning loop with adaptive FPS."""
        # uiautomation drives COM/UIA; COM must be initialized on THIS thread.
        if self._uia:
            try:
                self._uia.InitializeUIAutomationInCurrentThread()
            except Exception:
                pass

        while self._running:
            loop_start = time.time()

            try:
                # Show cursor as buffering while scanning
                if self._visual_cursor:
                    self._visual_cursor.set_buffering(True)
                
                snapshot = self._capture_snapshot()
                if snapshot:
                    self._buffer.add(snapshot)

                    # Detect significant changes
                    prev = self._buffer.get_previous()
                    if prev and snapshot.hash != prev.hash:
                        self._on_significant_change(snapshot, prev)
                        self._static_counter = 0
                        self.current_fps = self.max_fps
                    else:
                        self._static_counter += 1
                        if self._static_counter >= self.static_threshold:
                            self.current_fps = self.min_fps

            except Exception as e:
                logger.error(f"[Scanner] Scan loop error: {e}")

            # Adaptive sleep
            elapsed = time.time() - loop_start
            target_interval = 1.0 / self.current_fps
            sleep_time = max(0, target_interval - elapsed)
            time.sleep(sleep_time)

        if self._uia:
            try:
                self._uia.UninitializeUIAutomationInCurrentThread()
            except Exception:
                pass

        # Release per-thread capture handles.
        cam = getattr(self._tls, "dxcam_cam", None)
        if cam is not None:
            for closer in ("stop", "release"):
                fn = getattr(cam, closer, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
        sct = getattr(self._tls, "mss_sct", None)
        if sct is not None:
            try:
                sct.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Fast screen capture (dxcam -> mss -> PIL) and JPEG encoding (cv2 -> PIL)
    # ------------------------------------------------------------------ #
    def _grab_screen_frame(self):
        """Return the latest screen frame using the fastest available backend.

        Returns a numpy BGR array when dxcam/mss works, a PIL Image from the
        ImageGrab fallback, or the last known frame when all else fails.
        """
        # 1) dxcam -- DXGI Desktop Duplication, ~6x faster than ImageGrab.
        if self._dxcam is not None:
            try:
                cam = getattr(self._tls, "dxcam_cam", None)
                if cam is None:
                    kwargs = {"output_idx": 0, "output_color": "BGR"}
                    if self._cv2 is None:
                        # dxcam's default cv2 processor needs opencv; use the
                        # numpy processor when cv2 is unavailable.
                        kwargs["processor_backend"] = "numpy"
                    cam = self._dxcam.create(**kwargs)
                    self._tls.dxcam_cam = cam
                    self._tls.dxcam_misses = 0
                # new_frame_only=False: fall back to the last duplicated frame
                # when the screen is idle (identical pixels -> nothing to redo).
                frame = cam.grab(new_frame_only=False)
                if frame is not None:
                    self._tls.dxcam_misses = 0
                    self._last_frame = frame
                    return frame
                self._tls.dxcam_misses = getattr(self._tls, "dxcam_misses", 0) + 1
                if self._tls.dxcam_misses >= 10:
                    logger.warning("[Scanner] dxcam produced no frames; disabling it for this run")
                    self._dxcam = None
            except Exception as e:
                logger.warning(f"[Scanner] dxcam capture failed ({e}); falling back")
                self._dxcam = None

        # 2) mss -- GDI based, faster and more robust than PIL ImageGrab.
        if self._mss is not None:
            try:
                sct = getattr(self._tls, "mss_sct", None)
                if sct is None:
                    sct = self._mss.MSS()
                    self._tls.mss_sct = sct
                monitors = sct.monitors
                mon = monitors[1] if len(monitors) > 1 else monitors[0]
                raw = sct.grab(mon)
                from PIL import Image
                frame = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                self._last_frame = frame
                return frame
            except Exception as e:
                logger.warning(f"[Scanner] mss capture failed ({e}); falling back to ImageGrab")
                self._mss = None

        # 3) PIL ImageGrab -- universal fallback.
        if self._image_grab:
            try:
                frame = self._image_grab.grab()
                self._last_frame = frame
                return frame
            except Exception as e:
                logger.debug(f"[Scanner] Vision capture failed: {e}")
        return self._last_frame

    def _encode_vision_frame(self, frame) -> Optional[str]:
        """JPEG-encode a frame to base64 (cv2 fast path, PIL otherwise)."""
        try:
            import base64
            if frame is None:
                return None
            if hasattr(frame, "shape"):  # numpy array (dxcam delivers BGR)
                if self._cv2 is not None:
                    img = frame
                    if self._vision_max_width and img.shape[1] > self._vision_max_width:
                        scale = self._vision_max_width / float(img.shape[1])
                        img = self._cv2.resize(
                            img,
                            (self._vision_max_width, max(1, int(img.shape[0] * scale))),
                            interpolation=self._cv2.INTER_AREA,
                        )
                    ok, buf = self._cv2.imencode(
                        ".jpg", img,
                        [int(self._cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality],
                    )
                    if not ok:
                        return None
                    return base64.b64encode(buf.tobytes()).decode("utf-8")
                from PIL import Image
                frame = Image.fromarray(frame[..., ::-1])  # BGR -> RGB
            # PIL image path
            import io
            from PIL import Image
            img = frame
            if self._vision_max_width and img.width > self._vision_max_width:
                scale = self._vision_max_width / float(img.width)
                img = img.resize(
                    (self._vision_max_width, max(1, int(img.height * scale))),
                    Image.LANCZOS,
                )
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=self._jpeg_quality)
            return base64.b64encode(out.getvalue()).decode("utf-8")
        except Exception as e:
            logger.debug(f"[Scanner] Vision encode failed: {e}")
            return None

    def _capture_snapshot(self) -> Optional[ScreenSnapshot]:
        """Capture complete screen state including UIA tree and vision data.

        Order matters for performance: pixels are fetched first via the fast
        capture chain, but JPEG/base64 encoding happens only AFTER change
        detection so static screens reuse the previous frame's encoding.
        """
        timestamp = time.time()

        # Grab raw pixels (no encode yet)
        frame = self._grab_screen_frame()

        # Extract UIA tree via a single shared walk
        elements = []
        raw_uia_tree = None
        active_window = None

        if self._uia:
            try:
                active = self._uia.GetForegroundControl()
                if active:
                    active_window = {
                        "title": active.Name,
                        "class_name": active.ClassName,
                        "handle": active.NativeWindowHandle,
                        "bounds": (
                            active.BoundingRectangle.left,
                            active.BoundingRectangle.top,
                            active.BoundingRectangle.right,
                            active.BoundingRectangle.bottom,
                        ),
                    }
                    nodes = self._collect_uia_frame(active, self._element_max_depth, self._max_nodes)
                    elements = self._nodes_to_elements(nodes)
                    raw_uia_tree = self._nodes_to_tree(nodes)

            except Exception as e:
                logger.debug(f"[Scanner] UIA extraction failed: {e}")

        # Compute hash
        hash_input = _stable_json_bytes(
            {"elements": [e.to_dict() for e in elements], "active_window": active_window}
        )
        state_hash = hashlib.sha256(hash_input).hexdigest()[:16]

        # Determine state
        prev = self._buffer.get_latest()
        if prev and state_hash == prev.hash:
            state = ScreenState.STATIC
        elif prev and self._buffer.detect_change(state_hash):
            state = ScreenState.CHANGED
        else:
            state = ScreenState.DYNAMIC

        # Lazy vision encode: fresh encoding only when the frame changed (or
        # no previous vision exists); static frames reuse the previous base64.
        vision_b64 = None
        if frame is not None:
            if state == ScreenState.STATIC and prev and prev.vision_data:
                vision_b64 = prev.vision_data
            else:
                vision_b64 = self._encode_vision_frame(frame)

        return ScreenSnapshot(
            timestamp=timestamp,
            hash=state_hash,
            state=state,
            elements=elements,
            active_window=active_window,
            vision_data=vision_b64,
            raw_uia_tree=raw_uia_tree,
        )

    # ------------------------------------------------------------------ #
    # Single-pass UIA frame walk (elements + raw tree share one traversal)
    # ------------------------------------------------------------------ #
    def _collect_uia_frame(self, root, max_depth: int, max_nodes: int) -> List[Dict[str, Any]]:
        """Walk the UIA tree ONCE and materialise plain dicts for every node.

        Both the flat element list and the nested raw tree are derived from
        this traversal, halving the cross-process COM chatter that the old
        two-walk implementation (extract + build) incurred every frame. The
        walk stops early when the configured time budget is exhausted so the
        continuous loop stays responsive on very rich trees.
        """
        nodes: List[Dict[str, Any]] = []
        budget_s = self._walk_budget_ms / 1000.0 if self._walk_budget_ms else 0.0
        started = time.time()
        stack: List[Tuple[Any, int, int]] = [(root, 0, -1)]
        while stack and len(nodes) < max_nodes:
            if budget_s and (time.time() - started) > budget_s:
                break
            control, depth, parent_idx = stack.pop()
            try:
                rect = control.BoundingRectangle
                name = control.Name or ""
                cls = control.ClassName or ""
                ctype = control.ControlTypeName or "Unknown"
                node = {
                    # Structural id: stable across frames (unlike id()), built
                    # without extra COM calls (NativeWindowHandle is omitted).
                    "control_id": f"{ctype}|{cls}|{name}|{rect.left},{rect.top},{rect.right},{rect.bottom}",
                    "name": name,
                    "class_name": cls,
                    "control_type": ctype,
                    "bounds": (rect.left, rect.top, rect.right, rect.bottom),
                    "is_visible": _is_control_visible(control),
                    "is_enabled": control.IsEnabled,
                    "depth": depth,
                    "parent_idx": parent_idx,
                    "child_idxs": [],
                }
            except Exception:
                continue
            idx = len(nodes)
            nodes.append(node)
            if parent_idx >= 0:
                nodes[parent_idx]["child_idxs"].append(idx)
            if depth >= max_depth:
                continue
            try:
                children = control.GetChildren()
            except Exception:
                children = []
            for child in reversed(children):
                try:
                    if _is_control_visible(child):
                        stack.append((child, depth + 1, idx))
                except Exception:
                    continue
        return nodes

    def _nodes_to_elements(self, nodes: List[Dict[str, Any]]) -> List[UIElement]:
        """Derive the flat UIElement list from a _collect_uia_frame() result."""
        elements: List[UIElement] = []
        for n in nodes:
            try:
                elements.append(UIElement(
                    control_id=n["control_id"],
                    class_name=n["class_name"],
                    text=n["name"],
                    bounds=n["bounds"],
                    is_visible=n["is_visible"],
                    is_enabled=n["is_enabled"],
                    control_type=n["control_type"],
                ))
            except Exception:
                continue
        return elements

    def _nodes_to_tree(self, nodes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Derive the nested raw tree from a _collect_uia_frame() result."""
        if not nodes:
            return None

        def build(idx: int) -> Dict[str, Any]:
            n = nodes[idx]
            return {
                "name": n["name"],
                "class_name": n["class_name"],
                "control_type": n["control_type"],
                "is_visible": n["is_visible"],
                "is_enabled": n["is_enabled"],
                "bounds": n["bounds"],
                "children": [build(c) for c in n["child_idxs"]],
            }

        return build(0)

    def _extract_uia_elements(self, control, depth: int = 0, max_depth: int = 8) -> List[UIElement]:
        """Extract UI elements from UIA control tree.

        Kept for API compatibility; _capture_snapshot() now uses the
        single-pass _collect_uia_frame() path instead.
        """
        if depth > max_depth:
            return []

        elements = []
        try:
            element = UIElement(
                control_id=str(control.NativeWindowHandle or id(control)),
                class_name=control.ClassName or "",
                text=control.Name or "",
                bounds=(
                    control.BoundingRectangle.left,
                    control.BoundingRectangle.top,
                    control.BoundingRectangle.right,
                    control.BoundingRectangle.bottom,
                ),
                is_visible=_is_control_visible(control),
                is_enabled=control.IsEnabled,
                control_type=control.ControlTypeName or "Unknown",
            )
            elements.append(element)

            # Recursively extract children
            for child in control.GetChildren():
                if _is_control_visible(child):
                    elements.extend(self._extract_uia_elements(child, depth + 1, max_depth))

        except Exception as e:
            logger.debug(f"[Scanner] UIA element extraction error: {e}")

        return elements

    def _build_uia_tree(self, control, depth: int = 0, max_depth: int = 8) -> Dict[str, Any]:
        """Build hierarchical UIA tree for debugging/analysis."""
        if depth > max_depth:
            return {"depth_limit": True}

        try:
            tree = {
                "name": control.Name or "",
                "class_name": control.ClassName or "",
                "control_type": control.ControlTypeName or "",
                "is_visible": _is_control_visible(control),
                "is_enabled": control.IsEnabled,
                "bounds": (
                    control.BoundingRectangle.left,
                    control.BoundingRectangle.top,
                    control.BoundingRectangle.right,
                    control.BoundingRectangle.bottom,
                ),
                "children": [],
            }

            for child in control.GetChildren():
                if _is_control_visible(child):
                    tree["children"].append(self._build_uia_tree(child, depth + 1, max_depth))

            return tree

        except Exception as e:
            return {"error": str(e)}

    def _on_significant_change(self, current: ScreenSnapshot, previous: ScreenSnapshot):
        """Handle significant screen changes by emitting CNS events."""
        now = time.time()
        self._last_significant_change = now

        if self.cns:
            try:
                event = EventEnvelope(
                    topic="screen.change_detected",
                    source_organ="organ_41_scanner",
                    payload={
                        "current_hash": current.hash,
                        "previous_hash": previous.hash,
                        "timestamp": current.timestamp,
                        "active_window": current.active_window,
                        "change_type": self._classify_change(current, previous),
                    },
                    event_id=f"scan_{int(now * 1000)}",
                    timestamp_ms=int(now * 1000),
                    priority=7,  # High priority for UI changes
                )
                self.cns.publish(event)
                logger.info(f"[Scanner] Significant change detected: {current.hash}")
            except Exception as e:
                logger.error(f"[Scanner] Failed to emit CNS event: {e}")

    def _classify_change(self, current: ScreenSnapshot, previous: ScreenSnapshot) -> str:
        """Classify the type of change (popup, navigation, modal, etc.)."""
        # Simple heuristic: check for new windows or modal-like elements
        if not previous.active_window or not current.active_window:
            return "unknown"

        # Check if active window changed
        if current.active_window.get("title") != previous.active_window.get("title"):
            return "window_switch"

        # Check for new modal-like elements (centered dialogs, overlays)
        current_elements = {e.control_id: e for e in current.elements}
        previous_elements = {e.control_id: e for e in previous.elements}

        new_elements = set(current_elements.keys()) - set(previous_elements.keys())
        if new_elements:
            # Check if any new element is centered (likely a modal/popup)
            screen_w = 1920  # Default, should use actual screen dimensions
            screen_h = 1080
            center_x, center_y = screen_w // 2, screen_h // 2

            for elem_id in new_elements:
                elem = current_elements[elem_id]
                bounds = elem.bounds
                elem_center_x = (bounds[0] + bounds[2]) // 2
                elem_center_y = (bounds[1] + bounds[3]) // 2

                # If element is centered and has significant size
                if (
                    abs(elem_center_x - center_x) < 200
                    and abs(elem_center_y - center_y) < 200
                    and (bounds[2] - bounds[0]) > 300
                    and (bounds[3] - bounds[1]) > 200
                ):
                    return "modal_or_popup"

        return "content_update"

    def get_current_state(self) -> Optional[Dict[str, Any]]:
        """Get the current screen state as standardized JSON."""
        snapshot = self._buffer.get_latest()
        if snapshot:
            return snapshot.to_dict()
        return None

    def find_element_by_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Find UI element by text content."""
        snapshot = self._buffer.get_latest()
        if not snapshot:
            return None

        text_lower = text.lower()
        for elem in snapshot.elements:
            if text_lower in elem.text.lower():
                return elem.to_dict()
        return None

    def find_element_by_type(self, control_type: str) -> List[Dict[str, Any]]:
        """Find all UI elements of a specific type."""
        snapshot = self._buffer.get_latest()
        if not snapshot:
            return []

        return [e.to_dict() for e in snapshot.elements if e.control_type.lower() == control_type.lower()]
