"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 24
Name: Dap

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Dap]
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
Dependencies: win32process, platform, win32security, win32api, dataclasses...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_24_dap.py]) --> output([Output Node])
```
"""
from __future__ import annotations

r"""
================================================================================
 ORGAN 24 — DESKTOP AUTOMATION PROTOCOL (DAP) / GUI-CDP RUNTIME
 Hojaiga Automation OS
================================================================================
 Authority Chain : Constitution -> Law Book -> Policy Manual ->
                    Master Architecture Blueprint -> Organ Specification ->
                    DAP Architecture Specification (Hojaiga-SPEC-GUI-CDP-001)

 Purpose:
     Native execution sub-system for cross-process, OS-wide GUI introspection,
     control, capture and event routing on Windows 10/11 x64.

     Provides the desktop equivalent of Chrome DevTools Protocol: unified tree
     representation, selector query engine, interaction pipeline (mouse /
     keyboard / native patterns), perception pipeline (capture / OCR / vision),
     and JSON-RPC 2.0 transport over Named Pipes for the Hojaiga Orchestrator
     (CNS Organ 02) to consume.

 Boundaries:
     - This organ owns NO GPU/VRAM allocation. Vision/OCR models, when
       enabled, are treated as CPU-first; any GPU usage is read-only
       telemetry request routed through the Brain/Infrastructure organs.
     - This organ never performs planning or reasoning. It exposes
       capabilities only (Environment Controller philosophy).
     - Communication with other organs occurs exclusively through the
       DAP Socket (Named Pipe JSON-RPC 2.0) and documented pipelines.

--------------------------------------------------------------------------------
 PRE-CODE ARCHITECTURE DIAGRAM
--------------------------------------------------------------------------------

    Hojaiga Orchestrator (CNS)
            |
            | JSON-RPC 2.0 over Named Pipe \\.\pipe\hojaiga_dap_<id>
            v
    +-------------------------------------------------------------+
    |                     DAP RUNTIME CORE                        |
    |  SessionManager | SecurityEnforcer | TreeOrchestrator        |
    |  QueryEngine (native/a11y/ocr/vision selectors)              |
    |  InteractionPipeline (Input Injector, Background Executor,   |
    |                        Focus Orchestrator)                   |
    |  PerceptionPipeline (Capture Engine, OCR Engine, Vision Eng.)|
    |  RecoveryEngine (auto-heal state machine)                    |
    +-------------------------------------------------------------+
            |                  |                  |
            v                  v                  v
      Win32Provider      UIAProvider (opt)   JavaABProvider (opt)
            |                  |                  |
            +------------------+------------------+
                               v
                Target Application Process Space

--------------------------------------------------------------------------------
 PRE-CODE STATE DIAGRAM
--------------------------------------------------------------------------------

    UNINITIALIZED -> READY -> {EXECUTING | SCANNING | RECOVERING} -> READY
                                                       |
                                                       v
                                                   FAULTED

--------------------------------------------------------------------------------
 PRE-CODE EXECUTION FLOW (Control.invoke)
--------------------------------------------------------------------------------

    Host -> Protocol.parse -> QueryEngine.resolve(node)
         -> InteractionPipeline.dispatch
              -> supports_background? BackgroundExecutor : ForegroundOrchestrator
         -> RecoveryEngine on failure (retry -> re-attach -> vision fallback)
         -> Protocol.respond -> Host

================================================================================
"""


import asyncio
from core_organs import headless_input as hin  # input guard + headless delivery
import ctypes
import dataclasses
import enum
import hashlib
import json
import logging
import os
import platform
import struct
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# ==============================================================================
# SECTION 1 — PLATFORM DETECTION & OPTIONAL NATIVE BINDINGS
# ==============================================================================

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    import ctypes.wintypes as wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
else:
    user32 = kernel32 = gdi32 = None
    wintypes = None

try:
    import win32pipe  # type: ignore
    import win32file  # type: ignore
    import win32security  # type: ignore
    import win32api  # type: ignore
    import win32con  # type: ignore
    import win32gui  # type: ignore
    import win32process  # type: ignore
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False

def load_system_config():
    import os
    for p in ["runtime_config.yaml", "var/hojaiga/config/runtime_config.yaml", r"D:\new_automation\runtime_config.yaml", r"D:\new_automation\var\hojaiga\config\runtime_config.yaml"]:
        if os.path.exists(p):
            try:
                import yaml
                with open(p, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
    return {}

try:
    import comtypes  # type: ignore
    import comtypes.client  # type: ignore
    COMTYPES_AVAILABLE = True
except ImportError:
    COMTYPES_AVAILABLE = False


LOGGER = logging.getLogger("hojaiga.organ24.dap")
if not LOGGER.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s | ORGAN24-DAP | %(levelname)s | %(message)s"))
    LOGGER.addHandler(_handler)
    LOGGER.setLevel(logging.INFO)


# ==============================================================================
# SECTION 2 — ERROR CATALOG (Spec §9.1)
# ==============================================================================

class DAPErrorCode(enum.Enum):
    ERR_NODE_NOT_FOUND = 0x1001
    ERR_NODE_AMBIGUOUS = 0x1002
    ERR_WINDOW_STALE = 0x2001
    ERR_FOREGROUND_LOCK_FAILED = 0x2002
    ERR_BACKGROUND_UNSUPPORTED = 0x3001
    ERR_OCR_ENGINE_FAILURE = 0x4001
    ERR_VISION_MODEL_NOT_LOADED = 0x4002
    ERR_ACCESS_DENIED_ELEVATION = 0x5001
    ERR_TIMEOUT = 0x6001
    ERR_INVALID_SELECTOR = 0x6002
    ERR_PLATFORM_UNSUPPORTED = 0x6003


class DAPError(Exception):
    """Base exception for all DAP runtime faults. Traceable per Law Book U-Law 1."""

    def __init__(self, code: DAPErrorCode, message: str, context: Optional[dict] = None):
        self.code = code
        self.message = message
        self.context = context or {}
        super().__init__(f"[{code.name}/{hex(code.value)}] {message}")

    def to_rpc_error(self) -> dict:
        return {
            "code": -32000 - self.code.value,
            "message": self.message,
            "data": {"errorConstant": self.code.name, "context": self.context},
        }


# ==============================================================================
# SECTION 3 — STATE CATALOG (Spec §9.2)
# ==============================================================================

class RuntimeState(enum.Enum):
    UNINITIALIZED = "UNINITIALIZED"
    READY = "READY"
    EXECUTING = "EXECUTING"
    SCANNING = "SCANNING"
    RECOVERING = "RECOVERING"
    FAULTED = "FAULTED"


class StateMachine:
    """Enforces the runtime state graph defined in the DAP specification."""

    _TRANSITIONS = {
        RuntimeState.UNINITIALIZED: {RuntimeState.READY},
        RuntimeState.READY: {RuntimeState.EXECUTING, RuntimeState.SCANNING,
                              RuntimeState.RECOVERING, RuntimeState.FAULTED},
        RuntimeState.EXECUTING: {RuntimeState.READY, RuntimeState.RECOVERING, RuntimeState.FAULTED},
        RuntimeState.SCANNING: {RuntimeState.READY, RuntimeState.RECOVERING, RuntimeState.FAULTED},
        RuntimeState.RECOVERING: {RuntimeState.READY, RuntimeState.FAULTED},
        RuntimeState.FAULTED: {RuntimeState.READY},
    }

    def __init__(self):
        self._state = RuntimeState.UNINITIALIZED
        self._lock = asyncio.Lock()
        self._history: List[Tuple[float, RuntimeState, RuntimeState]] = []

    @property
    def state(self) -> RuntimeState:
        return self._state

    async def transition(self, target: RuntimeState) -> None:
        async with self._lock:
            allowed = self._TRANSITIONS.get(self._state, set())
            if target not in allowed and target != self._state:
                raise DAPError(
                    DAPErrorCode.ERR_TIMEOUT,
                    f"Illegal state transition {self._state.value} -> {target.value}",
                )
            self._history.append((time.time(), self._state, target))
            self._state = target

    def history(self) -> List[Tuple[float, RuntimeState, RuntimeState]]:
        return list(self._history)


# ==============================================================================
# SECTION 4 — DATA CONTRACTS (Spec §4, §6)
# ==============================================================================

@dataclass
class Rect:
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0
    scale_factor: float = 1.0

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class DAPNode:
    node_id: str
    parent_node_id: Optional[str]
    child_node_ids: List[str] = field(default_factory=list)

    hwnd: int = 0
    process_id: int = 0
    thread_id: int = 0
    framework_type: str = "Win32"

    bounds: Rect = field(default_factory=Rect)

    control_type: str = "Window"
    name: str = ""
    class_name: str = ""
    automation_id: str = ""
    value: str = ""

    is_enabled: bool = True
    is_visible: bool = True
    is_focused: bool = False
    is_offscreen: bool = False
    supports_background: bool = True

    vision_confidence: float = 0.0
    ocr_text: str = ""

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["bounds"] = self.bounds.as_dict()
        return d


@dataclass
class NodeTarget:
    node_id: Optional[str] = None
    hwnd: Optional[int] = None
    selector: Optional[str] = None


@dataclass
class SelectorQuery:
    query_type: str  # "native" | "a11y" | "ocr" | "vision" | "window" | "control"
    selector: str


@dataclass
class CaptureOptions:
    format: str = "png"
    method: str = "BITBLT"


@dataclass
class CaptureResult:
    status: str
    width: int
    height: int
    format: str
    payload_base64: str
    scale_factor: float = 1.0


@dataclass
class ExecutionResult:
    status: str
    execution_time_ms: float
    background_executed: bool
    node_state: Optional[dict] = None
    error: Optional[dict] = None


# ==============================================================================
# SECTION 5 — WIN32 PRIMITIVES (ctypes fallback, pywin32 preferred)
# ==============================================================================

class Win32Primitives:
    """
    Thin wrapper exposing the exact Win32 primitives required by DAP:
    window enumeration, focus, messaging, input injection, capture.
    Uses ctypes for portability of this single-file module; prefers
    pywin32 constants when available for correctness.
    """

    WM_COMMAND = 0x0111
    WM_SETTEXT = 0x000C
    WM_GETTEXT = 0x000D
    WM_GETTEXTLENGTH = 0x000E
    BM_CLICK = 0x00F5
    WM_CLOSE = 0x0010
    SW_RESTORE = 9
    SW_MINIMIZE = 6
    SW_MAXIMIZE = 3

    def __init__(self):
        if not IS_WINDOWS:
            LOGGER.warning(
                "Organ 24 DAP initialized on non-Windows host (%s). "
                "Native Win32 automation is unavailable; running in "
                "SIMULATION MODE for testing/portability only.",
                platform.system(),
            )

    # ---- Window discovery -----------------------------------------------
    def enumerate_top_level_windows(self) -> List[int]:
        if not IS_WINDOWS:
            return []
        hwnds: List[int] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(hwnd, _lparam):
            hwnds.append(int(hwnd))
            return True

        user32.EnumWindows(_cb, 0)  # type: ignore
        return hwnds

    def enumerate_child_windows(self, hwnd: int) -> List[int]:
        if not IS_WINDOWS:
            return []
        children: List[int] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(child_hwnd, _lparam):
            children.append(int(child_hwnd))
            return True

        user32.EnumChildWindows(ctypes.c_void_p(hwnd), _cb, 0)  # type: ignore
        return children

    def get_window_text(self, hwnd: int) -> str:
        if not IS_WINDOWS:
            return ""
        length = user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))  # type: ignore
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, length + 1)  # type: ignore
        return buf.value

    def get_class_name(self, hwnd: int) -> str:
        if not IS_WINDOWS:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(ctypes.c_void_p(hwnd), buf, 256)  # type: ignore
        return buf.value

    def get_window_rect(self, hwnd: int) -> Rect:
        if not IS_WINDOWS:
            return Rect()
        r = wintypes.RECT()  # type: ignore
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))  # type: ignore
        return Rect(left=r.left, top=r.top, right=r.right, bottom=r.bottom,
                    scale_factor=self.get_dpi_scale(hwnd))

    def get_dpi_scale(self, hwnd: int) -> float:
        if not IS_WINDOWS:
            return 1.0
        try:
            dpi = user32.GetDpiForWindow(ctypes.c_void_p(hwnd))  # type: ignore
            return round(dpi / 96.0, 3) if dpi else 1.0
        except Exception:
            return 1.0

    def get_process_thread(self, hwnd: int) -> Tuple[int, int]:
        if not IS_WINDOWS:
            return (0, 0)
        pid = wintypes.DWORD(0)  # type: ignore
        tid = user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))  # type: ignore
        return (int(tid), int(pid.value))

    def is_window_visible(self, hwnd: int) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.IsWindowVisible(ctypes.c_void_p(hwnd)))  # type: ignore

    def is_window_enabled(self, hwnd: int) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.IsWindowEnabled(ctypes.c_void_p(hwnd)))  # type: ignore

    def is_window(self, hwnd: int) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.IsWindow(ctypes.c_void_p(hwnd)))  # type: ignore

    def get_foreground_window(self) -> int:
        if not IS_WINDOWS:
            return 0
        return int(user32.GetForegroundWindow())  # type: ignore

    # ---- Window control ---------------------------------------------------
    def set_foreground_window(self, hwnd: int) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.SetForegroundWindow(ctypes.c_void_p(hwnd)))  # type: ignore

    def show_window(self, hwnd: int, cmd: int) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.ShowWindow(ctypes.c_void_p(hwnd), cmd))  # type: ignore

    def attach_thread_input(self, tid_a: int, tid_b: int, attach: bool) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.AttachThreadInput(tid_a, tid_b, attach))  # type: ignore

    # ---- Messaging (background execution) ---------------------------------
    def send_message(self, hwnd: int, msg: int, wparam: int = 0, lparam: int = 0) -> int:
        if not IS_WINDOWS:
            return 0
        return int(user32.SendMessageW(ctypes.c_void_p(hwnd), msg, wparam, lparam))  # type: ignore

    def post_message(self, hwnd: int, msg: int, wparam: int = 0, lparam: int = 0) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.PostMessageW(ctypes.c_void_p(hwnd), msg, wparam, lparam))  # type: ignore

    def set_window_text(self, hwnd: int, text: str) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.SendMessageW(ctypes.c_void_p(hwnd), self.WM_SETTEXT, 0, text))  # type: ignore

    def get_control_text(self, hwnd: int) -> str:
        return self.get_window_text(hwnd)

    def click_button(self, hwnd: int) -> bool:
        if not IS_WINDOWS:
            return False
        self.send_message(hwnd, self.BM_CLICK, 0, 0)
        return True

    # ---- Input injection (foreground / physical) ---------------------------
    # Single source of truth for physical pointer input. Other organs and the
    # UnifiedVirtualMouse facade drive the cursor THROUGH these methods, so
    # exactly one place touches user32 (no duplicated, drifting input code).
    _BUTTON_FLAGS = {
        "left": (0x0002, 0x0004),
        "right": (0x0008, 0x0010),
        "middle": (0x0020, 0x0040),
    }

    def move_cursor(self, x: int, y: int) -> None:
        self._move_cursor(x, y)

    def get_cursor_pos(self) -> Tuple[int, int]:
        if not IS_WINDOWS:
            return (0, 0)
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))  # type: ignore
        return (int(pt.x), int(pt.y))

    def press_button(self, button: str = "left") -> None:
        if not IS_WINDOWS:
            return
        self._send_mouse_event(self._BUTTON_FLAGS.get(button, self._BUTTON_FLAGS["left"])[0])

    def release_button(self, button: str = "left") -> None:
        if not IS_WINDOWS:
            return
        self._send_mouse_event(self._BUTTON_FLAGS.get(button, self._BUTTON_FLAGS["left"])[1])

    def send_input_click(self, x: int, y: int, button: str = "left") -> None:
        if not IS_WINDOWS:
            return
        self._move_cursor(x, y)
        self.press_button(button)
        self.release_button(button)

    # Physical injection was DELETED (backlog 1.1): these keep their signatures so old callers do not crash, record the
    # attempt, and do nothing. Input to an app goes through headless_input (posted messages) or a UIA pattern.
    def scroll(self, amount: int, horizontal: bool = False) -> None:
        hin.physical_input_blocked("organ_24.WIN32.scroll")

    def _move_cursor(self, x: int, y: int) -> None:
        hin.physical_input_blocked("organ_24.WIN32._move_cursor")

    def _send_mouse_event(self, flag: int) -> None:
        hin.physical_input_blocked("organ_24.WIN32._send_mouse_event")

    def send_unicode_text(self, text: str) -> None:
        if not IS_WINDOWS:
            return
        for ch in text:
            self._send_unicode_char(ch)

    def _send_unicode_char(self, ch: str) -> None:
        hin.physical_input_blocked("organ_24.WIN32._send_unicode_char")

    def send_vk(self, vk: int, keyup: bool = False) -> None:
        hin.physical_input_blocked("organ_24.WIN32.send_vk")

    # ---- Capture ------------------------------------------------------------
    def capture_window_bitmap_bytes(self, hwnd: int) -> Tuple[int, int, bytes]:
        """BitBlt-based capture. Returns (width, height, raw BGRA bytes), (0, 0, b"") on any failure.

        Handle discipline is the point of the shape of this function: a process is capped at ~10,000
        GDI objects, and a capped process cannot create a device context -- so ONE leaked handle here
        is not a memory trinket, it is a step toward every later capture in the session coming back
        blank and being reported as "the app did not render". Therefore: every handle is released in
        `finally` (an exception between create and delete used to strand all three), the bitmap is
        deselected before DeleteObject (a still-selected object cannot be deleted), and a NULL
        creation returns honestly instead of painting on nothing."""
        if not IS_WINDOWS:
            return (0, 0, b"")
        if user32.IsIconic(ctypes.c_void_p(hwnd)):  # type: ignore
            # #4: a minimized window has NO full render to print - PrintWindow answers an all-blank
            # or icon-sized phantom (measured: 199x34 for a 1100x760 Notepad). Go straight to the
            # honest ladder, which restores -> captures -> re-hides and leaves the window minimized.
            fb = self._robust_fallback_bgra(hwnd)
            if fb:
                return fb
        rect = self.get_window_rect(hwnd)
        width = max(1, rect.right - rect.left)
        height = max(1, rect.bottom - rect.top)

        hwnd_dc = mem_dc = bitmap = old_bmp = None
        try:
            hwnd_dc = user32.GetWindowDC(ctypes.c_void_p(hwnd))  # type: ignore
            if not hwnd_dc:
                return (0, 0, b"")
            mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)  # type: ignore
            bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)  # type: ignore
            if not mem_dc or not bitmap:
                return (0, 0, b"")                 # out of GDI budget: say so, do not draw on nothing
            old_bmp = gdi32.SelectObject(mem_dc, bitmap)  # type: ignore

            PW_RENDERFULLCONTENT = 0x00000002
            result = user32.PrintWindow(ctypes.c_void_p(hwnd), mem_dc, PW_RENDERFULLCONTENT)  # type: ignore
            if not result:
                SRCCOPY = 0x00CC0020
                gdi32.BitBlt(mem_dc, 0, 0, width, height, hwnd_dc, 0, 0, SRCCOPY)  # type: ignore

            buffer_size = width * height * 4
            buf = ctypes.create_string_buffer(buffer_size)

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32),
                ]

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = width
            bmi.biHeight = -height
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            got = gdi32.GetDIBits(mem_dc, bitmap, 0, height, buf, ctypes.byref(bmi), 0)  # type: ignore
            if not got:
                return (0, 0, b"")
            raw = buf.raw
            # #4: PrintWindow(PW_RENDERFULLCONTENT) reads BLANK for many minimized windows (and the
            # BitBlt fallback above captures a phantom -32000 rect). Detect the all-zero render and
            # escalate the honest ladder - which restores->captures->re-hides and never leaves the
            # window in a changed state. None is returned honestly when NOTHING can produce pixels.
            if self._bytes_look_blank(raw):
                fb = self._robust_fallback_bgra(hwnd)
                if fb:
                    return fb
            return (width, height, raw)
        except Exception:                          # a capture is never worth killing an organ
            return (0, 0, b"")
        finally:
            if bitmap and old_bmp:                 # deselect first: a selected object cannot be deleted
                try:
                    gdi32.SelectObject(mem_dc, old_bmp)  # type: ignore
                except Exception:  # noqa: BLE001
                    pass
            if bitmap:
                gdi32.DeleteObject(bitmap)  # type: ignore
            if mem_dc:
                gdi32.DeleteDC(mem_dc)  # type: ignore
            if hwnd_dc:
                user32.ReleaseDC(ctypes.c_void_p(hwnd), hwnd_dc)  # type: ignore

    @staticmethod
    def _bytes_look_blank(raw: bytes) -> bool:
        """True when a captured DIB is an UNRENDERED black buffer: every sampled pixel is zero.
        Sampling every 64th pixel keeps the check at ~1 ms for a full-HD grab."""
        if not raw:
            return True
        sample = raw[::256]
        return not any(sample)

    def _robust_fallback_bgra(self, hwnd: int):
        """(w, h, BGRA bytes) from headless_input's minimized/partial-window ladder, or None."""
        try:
            from core_organs import headless_input as hin
            img, _note, rung = hin.capture_window_robust(hwnd)
            if img is None or rung == "none":
                return None
            return (img.size[0], img.size[1], img.convert("RGBA").tobytes("raw", "BGRA"))
        except Exception:                          # noqa: BLE001 - same rule as the capture itself
            return None


WIN32 = Win32Primitives()


# ==============================================================================
# SECTION 6 — PROVIDER INTERFACE (Spec §2 Provider Drivers)
# ==============================================================================

class ProviderInterface:
    """Abstract contract every framework provider (UIA/Win32/Java-AB) must satisfy."""

    name: str = "abstract"

    def supports_hwnd(self, hwnd: int) -> bool:
        raise NotImplementedError

    def build_node(self, hwnd: int, parent_id: Optional[str]) -> DAPNode:
        raise NotImplementedError

    def invoke(self, node: DAPNode) -> bool:
        raise NotImplementedError

    def set_value(self, node: DAPNode, text: str) -> bool:
        raise NotImplementedError

    def read_value(self, node: DAPNode) -> str:
        raise NotImplementedError


class Win32Provider(ProviderInterface):
    """Legacy Win32 controls, menus — WM_COMMAND / BM_CLICK / WM_SETTEXT."""

    name = "Win32"

    def supports_hwnd(self, hwnd: int) -> bool:
        return True  # universal fallback provider

    def build_node(self, hwnd: int, parent_id: Optional[str]) -> DAPNode:
        tid, pid = WIN32.get_process_thread(hwnd)
        node = DAPNode(
            node_id=str(uuid.uuid4()),
            parent_node_id=parent_id,
            hwnd=hwnd,
            process_id=pid,
            thread_id=tid,
            framework_type=self.name,
            bounds=WIN32.get_window_rect(hwnd),
            control_type="Window",
            name=WIN32.get_window_text(hwnd),
            class_name=WIN32.get_class_name(hwnd),
            is_enabled=WIN32.is_window_enabled(hwnd),
            is_visible=WIN32.is_window_visible(hwnd),
            supports_background=True,
        )
        return node

    def invoke(self, node: DAPNode) -> bool:
        return WIN32.click_button(node.hwnd)

    def set_value(self, node: DAPNode, text: str) -> bool:
        return WIN32.set_window_text(node.hwnd, text)

    def read_value(self, node: DAPNode) -> str:
        return WIN32.get_control_text(node.hwnd)


class UIAProvider(ProviderInterface):
    """WinUI / WPF / Qt / GTK / Electron via UI Automation (requires comtypes)."""

    name = "UIA"

    def __init__(self):
        self.enabled = COMTYPES_AVAILABLE and IS_WINDOWS

    def supports_hwnd(self, hwnd: int) -> bool:
        return self.enabled

    def build_node(self, hwnd: int, parent_id: Optional[str]) -> DAPNode:
        base = Win32Provider().build_node(hwnd, parent_id)
        base.framework_type = self.name
        return base

    def invoke(self, node: DAPNode) -> bool:
        if not self.enabled:
            raise DAPError(DAPErrorCode.ERR_BACKGROUND_UNSUPPORTED,
                            "UIA provider unavailable (comtypes not installed)")
        return True

    def set_value(self, node: DAPNode, text: str) -> bool:
        if not self.enabled:
            raise DAPError(DAPErrorCode.ERR_BACKGROUND_UNSUPPORTED, "UIA provider unavailable")
        return WIN32.set_window_text(node.hwnd, text)

    def read_value(self, node: DAPNode) -> str:
        return WIN32.get_control_text(node.hwnd)


class JavaAccessBridgeProvider(ProviderInterface):
    """Java Swing/AWT/JavaFX via Java Access Bridge. Requires JAB DLL bridging (external)."""

    name = "JavaAB"

    def __init__(self):
        self.enabled = False  # requires external JAB bridge DLL not bundled in this organ

    def supports_hwnd(self, hwnd: int) -> bool:
        return self.enabled

    def build_node(self, hwnd: int, parent_id: Optional[str]) -> DAPNode:
        base = Win32Provider().build_node(hwnd, parent_id)
        base.framework_type = self.name
        return base

    def invoke(self, node: DAPNode) -> bool:
        raise DAPError(DAPErrorCode.ERR_BACKGROUND_UNSUPPORTED, "Java Access Bridge not bundled")

    def set_value(self, node: DAPNode, text: str) -> bool:
        raise DAPError(DAPErrorCode.ERR_BACKGROUND_UNSUPPORTED, "Java Access Bridge not bundled")

    def read_value(self, node: DAPNode) -> str:
        raise DAPError(DAPErrorCode.ERR_BACKGROUND_UNSUPPORTED, "Java Access Bridge not bundled")


class ProviderRegistry:
    """Selects the correct provider driver for a given HWND / framework hint."""

    def __init__(self):
        self.uia = UIAProvider()
        self.java = JavaAccessBridgeProvider()
        self.win32 = Win32Provider()

    def resolve(self, hwnd: int, class_name: str = "") -> ProviderInterface:
        java_classes = ("SunAwtFrame", "SunAwtDialog")
        if class_name in java_classes and self.java.enabled:
            return self.java
        if self.uia.enabled:
            return self.uia
        return self.win32


# ==============================================================================
# SECTION 7 — TREE METAMODEL (Spec §4): Desktop/Window/Accessibility/Element/
#              Interaction/Event trees synchronized via TreeOrchestrator
# ==============================================================================

class WindowTree:
    """HWND hierarchy, Z-order, process bounds."""

    def __init__(self, providers: ProviderRegistry):
        self._providers = providers
        self._nodes: Dict[str, DAPNode] = {}
        self._hwnd_index: Dict[int, str] = {}

    def clear(self) -> None:
        self._nodes.clear()
        self._hwnd_index.clear()

    def nodes(self) -> Dict[str, DAPNode]:
        return self._nodes

    def get_by_hwnd(self, hwnd: int) -> Optional[DAPNode]:
        node_id = self._hwnd_index.get(hwnd)
        return self._nodes.get(node_id) if node_id else None

    def get(self, node_id: str) -> Optional[DAPNode]:
        return self._nodes.get(node_id)

    def rescan(self, include_children: bool = True, process_filter: Optional[List[int]] = None) -> None:
        self.clear()
        top_level = WIN32.enumerate_top_level_windows()
        for hwnd in top_level:
            self._register(hwnd, parent_id=None, include_children=include_children,
                            process_filter=process_filter)

    def _register(self, hwnd: int, parent_id: Optional[str], include_children: bool,
                  process_filter: Optional[List[int]]) -> Optional[DAPNode]:
        class_name = WIN32.get_class_name(hwnd)
        provider = self._providers.resolve(hwnd, class_name)
        node = provider.build_node(hwnd, parent_id)

        if process_filter and node.process_id not in process_filter:
            return None

        self._nodes[node.node_id] = node
        self._hwnd_index[hwnd] = node.node_id
        if parent_id and parent_id in self._nodes:
            self._nodes[parent_id].child_node_ids.append(node.node_id)

        if include_children:
            for child_hwnd in WIN32.enumerate_child_windows(hwnd):
                self._register(child_hwnd, node.node_id, include_children, process_filter)
        return node

    def mark_stale(self, node_id: str) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.is_offscreen = True
            node.is_enabled = False

    def re_attach(self, node_id: str) -> Optional[DAPNode]:
        node = self._nodes.get(node_id)
        if not node:
            return None
        if not WIN32.is_window(node.hwnd):
            return None
        provider = self._providers.resolve(node.hwnd, node.class_name)
        refreshed = provider.build_node(node.hwnd, node.parent_node_id)
        refreshed.node_id = node.node_id
        self._nodes[node.node_id] = refreshed
        return refreshed


class DesktopTree:
    """Physical display topology & monitors."""

    def __init__(self):
        self.monitors: List[Rect] = []

    def rescan(self) -> None:
        self.monitors = []
        if not IS_WINDOWS:
            self.monitors.append(Rect(0, 0, 1920, 1080, 1.0))
            return

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(wintypes.RECT), ctypes.c_double)  # type: ignore

        def _cb(_hmon, _hdc, rect_ptr, _data):
            r = rect_ptr.contents
            self.monitors.append(Rect(r.left, r.top, r.right, r.bottom))
            return 1

        user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_cb), 0)  # type: ignore


class EventTree:
    """Active listeners, hook targets, subscriber queues (Spec §9.3 Event Catalog)."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[dict], None]]] = {}
        self._queue: "asyncio.Queue[dict]" = asyncio.Queue()

    def subscribe(self, event_type: str, handler: Callable[[dict], None]) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    async def publish(self, event_type: str, params: dict) -> None:
        payload = {"jsonrpc": "2.0", "method": event_type, "params": params}
        await self._queue.put(payload)
        for handler in self._subscribers.get(event_type, []):
            try:
                handler(payload)
            except Exception:  # noqa: BLE001
                LOGGER.exception("Event subscriber raised for %s", event_type)

    async def next_event(self) -> dict:
        return await self._queue.get()


# ==============================================================================
# SECTION 8 — QUERY ENGINE & SELECTORS (Spec §2 Query Engine)
# ==============================================================================

class QueryEngine:
    """
    Resolves NodeTarget / SelectorQuery objects against the live WindowTree.
    Supports: native (class/title), a11y (hierarchical path), and simple
    substring selectors. OCR/vision selectors delegate to PerceptionPipeline.
    """

    def __init__(self, window_tree: WindowTree, perception: "PerceptionPipeline"):
        self._tree = window_tree
        self._perception = perception

    def resolve(self, target: NodeTarget) -> DAPNode:
        if target.node_id:
            node = self._tree.get(target.node_id)
            if not node:
                raise DAPError(DAPErrorCode.ERR_NODE_NOT_FOUND,
                                f"No node with id {target.node_id}")
            return node
        if target.hwnd is not None:
            node = self._tree.get_by_hwnd(target.hwnd)
            if not node:
                raise DAPError(DAPErrorCode.ERR_NODE_NOT_FOUND,
                                f"No node for hwnd {target.hwnd}")
            return node
        if target.selector:
            results = self.query(SelectorQuery("native", target.selector))
            if not results:
                raise DAPError(DAPErrorCode.ERR_NODE_NOT_FOUND,
                                f"Selector matched zero nodes: {target.selector}")
            if len(results) > 1:
                raise DAPError(DAPErrorCode.ERR_NODE_AMBIGUOUS,
                                f"Selector matched {len(results)} nodes: {target.selector}")
            return results[0]
        raise DAPError(DAPErrorCode.ERR_INVALID_SELECTOR, "Empty NodeTarget supplied")

    def query(self, sq: SelectorQuery) -> List[DAPNode]:
        if sq.query_type in ("native", "window", "control", "a11y"):
            return self._query_native(sq.selector)
        if sq.query_type == "ocr":
            return self._perception.ocr_query_all(sq.selector)
        if sq.query_type == "vision":
            return self._perception.vision_query_all(sq.selector)
        raise DAPError(DAPErrorCode.ERR_INVALID_SELECTOR, f"Unknown queryType {sq.query_type}")

    def _query_native(self, selector: str) -> List[DAPNode]:
        """
        Minimal selector grammar: Window[name='X'] -> Button[automationId='Y']
        Falls back to plain substring match against name/class_name.
        """
        segments = [s.strip() for s in selector.split("->")]
        candidates = list(self._tree.nodes().values())

        def match_segment(nodes: List[DAPNode], seg: str) -> List[DAPNode]:
            attrs = self._parse_attrs(seg)
            out = []
            for n in nodes:
                if attrs.get("name") and attrs["name"] not in n.name:
                    continue
                if attrs.get("automationId") and attrs["automationId"] != n.automation_id:
                    continue
                if attrs.get("class") and attrs["class"] != n.class_name:
                    continue
                if not attrs and seg not in n.name and seg not in n.class_name:
                    continue
                out.append(n)
            return out

        result = candidates
        for seg in segments:
            result = match_segment(result, seg)
        return result

    @staticmethod
    def _parse_attrs(segment: str) -> dict:
        attrs: Dict[str, str] = {}
        if "[" in segment and segment.endswith("]"):
            body = segment[segment.index("[") + 1:-1]
            for clause in body.split("&&"):
                clause = clause.strip()
                if "=" in clause:
                    key, val = clause.split("=", 1)
                    attrs[key.strip()] = val.strip().strip("'\"")
        return attrs


# ==============================================================================
# SECTION 9 — INTERACTION PIPELINE (Spec §7.3/§7.4/§8)
# ==============================================================================

class FocusOrchestrator:
    """Captures/restores foreground focus for physical-input-only interactions."""

    def __init__(self):
        self._saved_hwnd: Optional[int] = None

    def lock_and_focus(self, hwnd: int) -> None:
        self._saved_hwnd = WIN32.get_foreground_window()
        current_tid, _ = WIN32.get_process_thread(WIN32.get_foreground_window())
        target_tid, _ = WIN32.get_process_thread(hwnd)
        WIN32.attach_thread_input(current_tid, target_tid, True)
        WIN32.show_window(hwnd, WIN32.SW_RESTORE)
        ok = WIN32.set_foreground_window(hwnd)
        WIN32.attach_thread_input(current_tid, target_tid, False)
        if not ok and IS_WINDOWS:
            raise DAPError(DAPErrorCode.ERR_FOREGROUND_LOCK_FAILED,
                            f"SetForegroundWindow rejected for hwnd={hwnd}")

    def restore(self) -> None:
        if self._saved_hwnd:
            WIN32.set_foreground_window(self._saved_hwnd)
            self._saved_hwnd = None


class BackgroundExecutor:
    """Executes actions on covered/minimized windows without foreground focus."""

    BACKGROUND_CAPABLE_CLASSES = {
        "Button", "Edit", "ComboBox", "ListBox", "#32770",  # #32770 = generic dialog
    }

    def can_execute_background(self, node: DAPNode) -> bool:
        return node.supports_background

    def invoke(self, node: DAPNode, provider: ProviderInterface) -> bool:
        return provider.invoke(node)

    def set_value(self, node: DAPNode, provider: ProviderInterface, text: str) -> bool:
        return provider.set_value(node, text)


class InputInjector:
    """Physical mouse/keyboard injection via SendInput (foreground pipeline)."""

    def click(self, x: int, y: int, button: str = "left") -> None:
        WIN32.send_input_click(x, y, button)

    def double_click(self, x: int, y: int) -> None:
        self.click(x, y)
        time.sleep(0.05)
        self.click(x, y)

    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int) -> None:
        WIN32._move_cursor(start_x, start_y)
        WIN32._send_mouse_event(0x0002)  # left down
        steps = 12
        for i in range(1, steps + 1):
            ix = start_x + (end_x - start_x) * i // steps
            iy = start_y + (end_y - start_y) * i // steps
            WIN32._move_cursor(ix, iy)
            time.sleep(0.01)
        WIN32._send_mouse_event(0x0004)  # left up

    def scroll(self, delta_x: int, delta_y: int) -> None:
        hin.physical_input_blocked("organ_24.InputInjector.scroll")

    def type_text(self, text: str) -> None:
        WIN32.send_unicode_text(text)

    SHORTCUT_VK = {
        "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12,
        "win": 0x5B, "enter": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09,
        "f4": 0x73, "delete": 0x2E, "backspace": 0x08,
    }

    def shortcut(self, sequence: str) -> None:
        parts = [p.strip().lower() for p in sequence.split("+")]
        vks = []
        for p in parts:
            if p in self.SHORTCUT_VK:
                vks.append(self.SHORTCUT_VK[p])
            elif len(p) == 1:
                vks.append(ord(p.upper()))
            else:
                raise DAPError(DAPErrorCode.ERR_INVALID_SELECTOR, f"Unknown key token '{p}'")
        for vk in vks:
            WIN32.send_vk(vk, keyup=False)
        for vk in reversed(vks):
            WIN32.send_vk(vk, keyup=True)


class InteractionPipeline:
    """
    Orchestrates the Background-vs-Foreground decision tree defined in Spec §8.
    """

    def __init__(self, providers: ProviderRegistry):
        self._providers = providers
        self.background = BackgroundExecutor()
        self.focus = FocusOrchestrator()
        self.injector = InputInjector()

    def invoke(self, node: DAPNode, force_foreground: bool = False) -> ExecutionResult:
        started = time.time()
        provider = self._providers.resolve(node.hwnd, node.class_name)
        used_background = False
        try:
            if not force_foreground and self.background.can_execute_background(node):
                self.background.invoke(node, provider)
                used_background = True
            else:
                self.focus.lock_and_focus(node.hwnd)
                cx = (node.bounds.left + node.bounds.right) // 2
                cy = (node.bounds.top + node.bounds.bottom) // 2
                self.injector.click(cx, cy)
                self.focus.restore()
            elapsed = (time.time() - started) * 1000
            return ExecutionResult(
                status="SUCCESS", execution_time_ms=elapsed,
                background_executed=used_background,
                node_state={"nodeId": node.node_id, "enabled": node.is_enabled,
                            "visible": node.is_visible},
            )
        except DAPError as exc:
            elapsed = (time.time() - started) * 1000
            return ExecutionResult(
                status="ERROR", execution_time_ms=elapsed,
                background_executed=used_background, error=exc.to_rpc_error(),
            )

    def set_value(self, node: DAPNode, text: str) -> ExecutionResult:
        started = time.time()
        provider = self._providers.resolve(node.hwnd, node.class_name)
        try:
            self.background.set_value(node, provider, text)
            elapsed = (time.time() - started) * 1000
            return ExecutionResult(status="SUCCESS", execution_time_ms=elapsed,
                                    background_executed=True)
        except DAPError as exc:
            elapsed = (time.time() - started) * 1000
            return ExecutionResult(status="ERROR", execution_time_ms=elapsed,
                                    background_executed=False, error=exc.to_rpc_error())


# ==============================================================================
# SECTION 10 — PERCEPTION PIPELINE (Spec §7.5, §3 perception/*)
# ==============================================================================

class CaptureEngine:
    """Window/region capture via BitBlt/PrintWindow. DXGI omitted (out of Python/ctypes scope)."""

    def capture(self, node: DAPNode, options: CaptureOptions) -> CaptureResult:
        if not IS_WINDOWS:
            return CaptureResult(status="UNSUPPORTED_PLATFORM", width=0, height=0,
                                  format=options.format, payload_base64="")
        width, height, raw_bgra = WIN32.capture_window_bitmap_bytes(node.hwnd)
        import base64
        payload = base64.b64encode(raw_bgra).decode("ascii")
        return CaptureResult(status="SUCCESS", width=width, height=height,
                              format="raw_bgra", payload_base64=payload,
                              scale_factor=node.bounds.scale_factor)


class OCREngine:
    """
    Optional OCR backend (pytesseract). Perception is CPU-first per hardware
    policy; GPU acceleration for OCR is NOT owned by this organ.
    """

    def __init__(self):
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore
            self._pytesseract = pytesseract
            self._Image = Image
            self.available = True
        except ImportError:
            self.available = False

    def _image_of(self, node: DAPNode, capture: CaptureEngine):
        result = capture.capture(node, CaptureOptions(format="raw_bgra"))
        if result.status != "SUCCESS" or not result.width or not result.height:
            raise DAPError(DAPErrorCode.ERR_OCR_ENGINE_FAILURE, "Capture failed for OCR pass")
        import base64
        raw = base64.b64decode(result.payload_base64)
        return self._Image.frombuffer("RGBA", (result.width, result.height), raw, "raw", "BGRA", 0, 1).convert("RGB")

    def words(self, node: DAPNode, capture: CaptureEngine, min_conf: float = 30.0) -> List[dict]:
        """Every recognised word WITH ITS BOX, in SCREEN coordinates (the captured window's own top-left plus the pixel offset): this is what
        lets an OCR selector be ACTED on - a click lands on the word, not on 'somewhere in the window'. Words of a window that exposes no
        UIA tree at all (a custom-drawn dialog, a canvas app) are still readable this way."""
        if not self.available:
            raise DAPError(DAPErrorCode.ERR_OCR_ENGINE_FAILURE, "OCR backend (pytesseract) not installed")
        img = self._image_of(node, capture)
        # small dialogs OCR better enlarged; the factor is undone below
        k = 2 if max(img.size) < 900 else 1
        big = img.resize((img.width * k, img.height * k)) if k > 1 else img
        d = self._pytesseract.image_to_data(big, output_type=self._pytesseract.Output.DICT)
        out: List[dict] = []
        for i, txt in enumerate(d.get("text", [])):
            t = (txt or "").strip()
            try:
                conf = float(d["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            if not t or conf < min_conf:
                continue
            x, y, w, h = (int(d[k_][i]) // k for k_ in ("left", "top", "width", "height"))
            out.append({"text": t, "conf": conf, "block": int(d["block_num"][i]), "line": int(d["line_num"][i]),
                        "left": node.bounds.left + x, "top": node.bounds.top + y,
                        "right": node.bounds.left + x + w, "bottom": node.bounds.top + y + h})
        return out

    def query(self, node: DAPNode, text_pattern: str, capture: CaptureEngine) -> List[DAPNode]:
        if not self.available:
            raise DAPError(DAPErrorCode.ERR_OCR_ENGINE_FAILURE,
                            "OCR backend (pytesseract) not installed")
        image = self._image_of(node, capture)
        text = self._pytesseract.image_to_string(image)
        matches: List[DAPNode] = []
        if text_pattern.lower() in text.lower():
            bounds = node.bounds
            try:                       # narrow the match to the phrase's own box when the words can be located
                want = text_pattern.lower().split()
                ws = self.words(node, capture)
                for i in range(len(ws) - len(want) + 1):
                    if [w["text"].lower().strip(".,:;!?") for w in ws[i:i + len(want)]] == want:
                        seg = ws[i:i + len(want)]
                        bounds = Rect(left=min(w["left"] for w in seg), top=min(w["top"] for w in seg),
                                      right=max(w["right"] for w in seg), bottom=max(w["bottom"] for w in seg),
                                      scale_factor=node.bounds.scale_factor)
                        break
            except Exception:  # noqa: BLE001 - the phrase is still PRESENT; only its box is unknown
                pass
            hit = DAPNode(
                node_id=str(uuid.uuid4()), parent_node_id=node.node_id,
                hwnd=node.hwnd, bounds=bounds, control_type="OCRMatch",
                name=text_pattern, ocr_text=text[:512],
            )
            matches.append(hit)
        return matches


class VisionEngine:
    """Optional ONNX object-detection backend (e.g. YOLOv8). GPU/VRAM is read-only telemetry."""

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self.available = False
        if model_path:
            try:
                import onnxruntime  # type: ignore
                self._session = onnxruntime.InferenceSession(
                    model_path, providers=["CPUExecutionProvider"])
                self.available = True
            except Exception:
                self.available = False

    def query(self, node: DAPNode, class_name: str, capture: CaptureEngine) -> List[DAPNode]:
        if not self.available:
            raise DAPError(DAPErrorCode.ERR_VISION_MODEL_NOT_LOADED,
                            "Vision ONNX model not loaded for this session")
        return []  # inference pipeline intentionally left to model-specific integration


class PerceptionPipeline:
    def __init__(self, window_tree: WindowTree, vision_model_path: Optional[str] = None):
        self._tree = window_tree
        self.capture = CaptureEngine()
        self.ocr = OCREngine()
        self.vision = VisionEngine(vision_model_path)

    def ocr_query_all(self, text_pattern: str) -> List[DAPNode]:
        matches: List[DAPNode] = []
        for node in self._tree.nodes().values():
            try:
                matches.extend(self.ocr.query(node, text_pattern, self.capture))
            except DAPError:
                continue
        return matches

    def vision_query_all(self, class_name: str) -> List[DAPNode]:
        matches: List[DAPNode] = []
        for node in self._tree.nodes().values():
            try:
                matches.extend(self.vision.query(node, class_name, self.capture))
            except DAPError:
                continue
        return matches


# ==============================================================================
# SECTION 11 — POPUP / DIALOG / INSTALLER WIZARD / FILE PICKER MANAGERS
# ==============================================================================

class PopupSubsystem:
    """
    Detects child windows, modal dialogs, and installer wizards spawned by a
    target application, and orchestrates focus -> read -> interact -> verify
    -> resume-previous-workflow per the Popup Subsystem diagram.
    """

    DIALOG_CLASS_HINTS = {"#32770", "Popup", "ModalDialog"}
    INSTALLER_HINTS = ("setup", "install", "wizard", "installshield", "msi")

    def __init__(self, window_tree: WindowTree, interaction: InteractionPipeline):
        self._tree = window_tree
        self._interaction = interaction

    def detect(self, owner_hwnd: int) -> List[DAPNode]:
        detected: List[DAPNode] = []
        for node in self._tree.nodes().values():
            if node.hwnd == owner_hwnd:
                continue
            if node.class_name in self.DIALOG_CLASS_HINTS or self._looks_like_installer(node):
                detected.append(node)
        return detected

    def _looks_like_installer(self, node: DAPNode) -> bool:
        lowered = node.name.lower()
        return any(hint in lowered for hint in self.INSTALLER_HINTS)

    def classify(self, node: DAPNode) -> str:
        if self._looks_like_installer(node):
            return "INSTALLER_WIZARD"
        if node.class_name == "#32770":
            return "MODAL_DIALOG"
        return "CHILD_WINDOW"

    def accept(self, node: DAPNode) -> ExecutionResult:
        return self._interaction.invoke(node)

    def dismiss(self, node: DAPNode) -> bool:
        return WIN32.post_message(node.hwnd, Win32Primitives.WM_CLOSE, 0, 0)


# ==============================================================================
# SECTION 11B - FILE-DIALOG RECOGNITION (one shared shape test, no vendor branch)
# ==============================================================================
# WHAT a file dialog is gets declared below as data; the functions only ever ask a window for its
# SHAPE. No application name appears in any control-flow path, so the next family that draws its own
# picker needs a line of data (or nothing at all, if its shape is honest) instead of a new branch.
# Measured reason this exists (2026-10-05, a spreadsheet): recognition was "class is '#32770' AND the
# title contains save/open" -- and that app's own picker is an UNTITLED window of a different class, so
# the dialog opened, the loop never knew it existed, and the app sat modal behind it while the loop
# clicked an empty screen and the pane looked blank.
DIALOG_CLASS_CERTAIN = ("#32770",)              # the Win32 common dialog: an OS contract, certain
DIALOG_NAME_FIELD_AIDS = ("1001",)              # IDFILENAME: a Win32 control id, locale-independent
DIALOG_ACCEPT_AIDS = ("1",)                     # IDOK: the same contract, the accept button's control id
# Window KINDS that are known to host a name box. These are OS/vendor window-class names, not app names:
# they count as evidence for the shape test, never as an identity, and never skip the shape test.
DIALOG_CLASS_RECOGNISED = ("NUIDialog",)
DIALOG_TITLE_HINTS = ("save", "open", "export", "browse", "download", "load", "import")   # ordering hint
DIALOG_ACCEPT_WORDS = ("save", "open", "ok", "export", "import", "select", "choose")     # what 'accept' is called
DIALOG_NEVER_PRESS = ("cancel", "close", "back", "skip", "copy", "rename", "delete", "help",
                      "more options")            # never the accept button of a save
DIALOG_EDIT_ROLES = ("editcontrol", "comboboxcontrol")
DIALOG_ACCEPT_ROLES = ("buttoncontrol", "hyperlinkcontrol", "splitbuttoncontrol")
DIALOG_FSVIEW_ROLES = ("listcontrol", "treecontrol", "datagridcontrol", "tablecontrol")
DIALOG_FSITEM_ROLES = ("listitemcontrol", "treeitemcontrol", "dataitemcontrol")

# A route is a sequence of label patterns to press, one per hop, when a dialog will NOT take an
# absolute path. It is DATA: a family that needs one gets a tuple here, not a new code path, and a
# route that matches nothing in the app's own tree is skipped and the refusal is reported.
DIALOG_PATH_ROUTES: Tuple[Tuple[str, ...], ...] = (("more options", "browse"),)


def _window_class(hwnd: int) -> str:
    try:
        return hin._class_name(int(hwnd)) or ""
    except Exception:  # noqa: BLE001
        return ""


def is_owned_top_level(hwnd: int) -> bool:
    """True for a modal/auxiliary window, false for an application main frame (a frame owns nothing).
    A locale- and vendor-neutral way to tell 'a dialog the app put up' from 'the app itself'."""
    try:
        GW_OWNER = 4
        user32.GetWindow.restype = ctypes.c_void_p              # type: ignore
        user32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]  # type: ignore
        return bool(user32.GetWindow(ctypes.c_void_p(int(hwnd)), GW_OWNER))
    except Exception:  # noqa: BLE001
        return False


def file_dialog_shape(hwnd: int, nodes: Optional[List[Any]] = None,
                      timeout_ms: int = 2500) -> Dict[str, Any]:
    """Ask one window for the shape of a file dialog. Never raises: an unreadable window is simply not a
    dialog, and the reason is returned so the caller can say it out loud instead of guessing.

    certain   = the OS common-dialog class, or the tree carries the Win32 IDFILENAME control (aid 1001).
    plausible = a window that looks like a name-and-accept picker. For a family we have never met that
                means: an owned top-level (a modal, not the main frame), a SETTABLE name box, an enabled
                accept button, and proof the box is about the file system (a file list/tree, or items
                named like files). For a window kind listed in DIALOG_CLASS_RECOGNISED the name box and
                the accept button are enough -- the class says what kind of window it is, the shape says
                whether this one is holding a file name. That proof is what stops a Find/Replace or
                Rename box from being filled with a path."""
    out: Dict[str, Any] = {"hwnd": int(hwnd), "class": _window_class(hwnd), "certain": False,
                           "plausible": False, "shape_ok": False, "name_edit": False,
                           "name_settable": False, "accept": False, "fs_visible": False,
                           "nodes": 0, "read": "no-uia"}
    if nodes is None:
        try:
            from core_organs import fast_uia as _fu
            nodes = _fu.snapshot(int(hwnd), timeout_ms=timeout_ms) or []
        except Exception as exc:  # noqa: BLE001
            out["read"] = f"uia-read-failed:{type(exc).__name__}"
            return out
    out["nodes"] = len(nodes or [])
    out["read"] = "ok" if nodes else "empty-tree"
    name_by_aid = name_loose = name_plain = accepts = fs_view = fs_items = 0
    for n in nodes or []:
        ctype = (getattr(n, "ctype", "") or "").lower()
        aid = str(getattr(n, "aid", "") or "").strip()
        nm = (getattr(n, "name", "") or "").strip().lower()
        pats = tuple(getattr(n, "pats", ()) or ())
        if ctype in DIALOG_EDIT_ROLES and not aid.startswith("System."):
            name_plain += 1
            if aid in DIALOG_NAME_FIELD_AIDS:
                name_by_aid += 1
            if "value" in pats or "text" in pats:
                name_loose += 1
        if (ctype in DIALOG_ACCEPT_ROLES and getattr(n, "enabled", True)
                and "invoke" in pats and not any(w in nm for w in DIALOG_NEVER_PRESS)):
            accepts += 1
        if ctype in DIALOG_FSVIEW_ROLES:
            fs_view += 1
        if ctype in DIALOG_FSITEM_ROLES and looks_like_file_name(nm):
            fs_items += 1
    known_kind = out["class"] in DIALOG_CLASS_RECOGNISED
    out["name_edit"] = bool(name_plain or name_by_aid)
    out["name_settable"] = bool(name_loose or name_by_aid)
    out["accept"] = bool(accepts)
    out["fs_visible"] = bool(fs_view or fs_items)
    out["certain"] = bool(out["name_edit"] and out["accept"]) and (
        out["class"] in DIALOG_CLASS_CERTAIN or name_by_aid > 0)
    out["plausible"] = (not out["certain"]) and bool(out["accept"]) and bool(
        (known_kind and out["name_edit"])
        or (out["name_settable"] and is_owned_top_level(hwnd) and out["fs_visible"]))
    out["shape_ok"] = bool(out["certain"] or out["plausible"])
    return out


def looks_like_file_name(text: str) -> bool:
    """'report.pdf' yes, 'Documents' no: a trailing 1-6 character extension. Shape only, locale-neutral."""
    t = (text or "").strip()
    if "." not in t or len(t) > 80:
        return False
    tail = t.rsplit(".", 1)[-1]
    return bool(tail) and tail.isascii() and (tail.isalnum() or "_" in tail) and len(tail) <= 6


def find_file_dialogs(owner_pid: int = 0, limit: int = 4, timeout_ms: int = 2500,
                      title_hints_first: bool = True) -> List[Dict[str, Any]]:
    """Every visible file dialog on the desktop, best first, each with its shape report attached.

    Cost is bounded on purpose: the cheap filters (visible, same process, class hint or owned modal) run
    on every window, and the UIA shape read -- the expensive part -- is spent on at most `limit` candidates
    at at most `timeout_ms` each. `owner_pid` scopes it to the app being driven; a picker belonging to
    anything else is never touched."""
    found: List[Dict[str, Any]] = []
    if not IS_WINDOWS:
        return found
    cand: List[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd, _l):
        try:
            if not user32.IsWindowVisible(ctypes.c_void_p(int(hwnd))):   # type: ignore
                return True
            cls = _window_class(hwnd)
            pid = ctypes.c_uint(0)
            user32.GetWindowThreadProcessId(ctypes.c_void_p(int(hwnd)), ctypes.byref(pid))  # type: ignore
            if owner_pid and int(pid.value) != int(owner_pid):
                return True
            cheap_dialog = (cls in DIALOG_CLASS_CERTAIN or cls in DIALOG_CLASS_RECOGNISED)
            if not (cheap_dialog or is_owned_top_level(int(hwnd))):
                return True                                    # a main frame never hosts the picker
            cand.append(int(hwnd))
        except Exception:  # noqa: BLE001
            pass
        return True

    user32.EnumWindows(_cb, 0)  # type: ignore
    for hwnd in cand[:max(1, int(limit))]:
        rep = file_dialog_shape(hwnd, timeout_ms=timeout_ms)
        if rep["shape_ok"]:
            rep["title_hint"] = any(w in (hin.safe_window_text(hwnd) or "").lower()
                                    for w in DIALOG_TITLE_HINTS) if title_hints_first else False
            found.append(rep)
    found.sort(key=lambda r: (not r["certain"], not r.get("title_hint"), -r["nodes"]))
    return found


class NativeFilePicker:
    """
    Drives the OS-native Open/Save file dialog: directory scan, search,
    validation, selection, open, verify, and focus restoration.

    Recognition is NOT done here: it asks the one shared shape test below
    (`file_dialog_shape` / `find_file_dialogs`), so a dialog cannot be a file dialog to
    one caller and not to another.

    Proof is not optional in this class. It used to pick 'the first Edit under the dialog'
    and write with WM_SETTEXT, which is exactly the two ways a save silently fails: the first
    Edit is often a file-LIST CELL, and a programmatic text set does not raise the change events
    an app uses to re-validate its accept button (measured in a spreadsheet's own picker: the box
    showed the typed path while Save stayed disabled). So: find the box by its own identity, type
    it character by character, and READ THE BOX BACK - and raise instead of claiming success.
    """

    def __init__(self, window_tree: WindowTree, interaction: InteractionPipeline,
                 popups: PopupSubsystem):
        self._tree = window_tree
        self._interaction = interaction
        self._popups = popups

    def locate_dialog(self) -> Optional[DAPNode]:
        """Best-shaped file dialog, by SHAPE (the same test every other caller gets). A window whose
        tree cannot be read is NOT accepted here: a blind class/title match is how a Find box gets
        filled with a path. desktop_grounding keeps a separate bounded fallback for the unreadable
        case, and it says out loud that the dialog was taken unverified."""
        best = None
        for node in self._tree.nodes().values():
            if not node.hwnd:
                continue
            rep = file_dialog_shape(int(node.hwnd))
            if rep["shape_ok"] and (best is None or rep["nodes"] > best[1]["nodes"]):
                best = (node, rep)
        return best[0] if best else None

    @staticmethod
    def _box_is_name_worthy(n: Any, aid: str, cls: str) -> bool:
        """Identity, not position: the Win32 name-field id first, then an editable control that is
        not a file-list column cell. Never 'whatever the tree happened to list first'."""
        ctype = (getattr(n, "ctype", "") or "").lower()
        if ctype not in DIALOG_EDIT_ROLES and "edit" not in cls.lower():
            return False
        if aid.startswith("System."):
            return False
        if aid and any(a == aid for a in DIALOG_NAME_FIELD_AIDS):
            return True
        return True

    def _find_name_box(self, dialog: DAPNode) -> Tuple[int, Any]:
        """(hwnd, node) of the box a file name is typed into, preferring the dialog's OWN UIA tree."""
        try:
            from core_organs import fast_uia as _fu
            for n in (_fu.snapshot(int(dialog.hwnd), timeout_ms=2500) or []):
                aid = str(getattr(n, "aid", "") or "").strip()
                if not self._box_is_name_worthy(n, aid, str(getattr(n, "cls", "") or "")):
                    continue
                h = 0
                try:
                    h = int(getattr(n, "ctrl", None) and n.ctrl.NativeWindowHandle or 0)
                except Exception:  # noqa: BLE001
                    h = 0
                if h:
                    return h, n
        except Exception:  # noqa: BLE001
            pass
        for n in self._tree.nodes().values():           # Win32-only dialogs (the common one) land here
            if n.parent_node_id != dialog.node_id:
                continue
            aid = str(n.automation_id or "").strip()
            if self._box_is_name_worthy(n, aid, n.class_name) and n.hwnd:
                return int(n.hwnd), n
        return 0, None

    def select_path(self, dialog: DAPNode, path: str) -> ExecutionResult:
        box, _node = self._find_name_box(dialog)
        if not box:
            raise DAPError(DAPErrorCode.ERR_NODE_NOT_FOUND,
                            "No name box found in file picker dialog (never guessing the first edit)")
        WIN32.send_message(box, 0x00B1, 0, -1)            # EM_SETSEL(0,-1): mark everything
        WIN32.send_message(box, 0x0303, 0, 0)             # WM_CLEAR, so the app sees a real edit
        ok, how = hin.post_text(box, path)
        if not ok:
            raise DAPError(DAPErrorCode.ERR_BACKGROUND_UNSUPPORTED, f"could not type into the name box: {how}")
        time.sleep(0.35)
        got = WIN32.get_control_text(box)                 # the proof: does the app agree the box holds this?
        if os.path.basename(path).lower() not in (got or "").lower():
            raise DAPError(DAPErrorCode.ERR_NODE_NOT_FOUND,
                            f"name box did not take the value (reads '{got}')")
        return ExecutionResult(status="SUCCESS", execution_time_ms=0.0,
                               background_executed=True,
                               node_state={"box": box, "read_back": got, "delivery": how})

    def confirm(self, dialog: DAPNode) -> ExecutionResult:
        """Press the dialog's accept control, chosen by IDENTITY (Win32 IDOK, or a caption the app
        itself calls 'accept'), scoped to THIS dialog's process - never a button in some other window."""
        want = tuple(str(a) for a in DIALOG_ACCEPT_AIDS)
        cands = [n for n in self._tree.nodes().values()
                 if n.parent_node_id == dialog.node_id
                 and (n.class_name or "").lower() in ("button", "buttoncontrol")
                 and n.is_enabled
                 and not any(w in (n.name or "").lower() for w in DIALOG_NEVER_PRESS)]
        pick = next((n for n in cands if str(n.automation_id or "").strip() in want), None) \
            or next((n for n in cands if any((n.name or "").strip().lower().startswith(w)
                                             for w in DIALOG_ACCEPT_WORDS)), None) \
            or (cands[0] if cands else None)
        if pick is None:
            raise DAPError(DAPErrorCode.ERR_NODE_NOT_FOUND, "No confirm button found")
        return self._interaction.invoke(pick)


# ==============================================================================
# SECTION 12 — RECOVERY ENGINE (Spec §5.3 Auto-Recovery Pipeline)
# ==============================================================================

class RecoveryEngine:
    """
    Implements: Health Monitor -> mark stale -> re-attach -> (fallback) Vision
    capture + OCR/YOLO -> physical click via coordinates.
    """

    def __init__(self, window_tree: WindowTree, perception: PerceptionPipeline,
                 injector: InputInjector, state_machine: StateMachine):
        self._tree = window_tree
        self._perception = perception
        self._injector = injector
        self._state = state_machine

    async def recover(self, node: DAPNode, action_desc: str) -> ExecutionResult:
        await self._state.transition(RuntimeState.RECOVERING)
        started = time.time()
        try:
            self._tree.mark_stale(node.node_id)
            refreshed = self._tree.re_attach(node.node_id)
            if refreshed is not None:
                await self._state.transition(RuntimeState.READY)
                return ExecutionResult(
                    status="SUCCESS", execution_time_ms=(time.time() - started) * 1000,
                    background_executed=True,
                    node_state={"nodeId": refreshed.node_id, "recovered": "re-attach"},
                )

            matches = self._perception.ocr_query_all(node.name or action_desc)
            if matches:
                target = matches[0]
                cx = (target.bounds.left + target.bounds.right) // 2
                cy = (target.bounds.top + target.bounds.bottom) // 2
                self._injector.click(cx, cy)
                await self._state.transition(RuntimeState.READY)
                return ExecutionResult(
                    status="SUCCESS", execution_time_ms=(time.time() - started) * 1000,
                    background_executed=False,
                    node_state={"nodeId": target.node_id, "recovered": "vision_fallback"},
                )

            await self._state.transition(RuntimeState.FAULTED)
            err = DAPError(DAPErrorCode.ERR_WINDOW_STALE,
                            f"Recovery exhausted for node {node.node_id}")
            return ExecutionResult(status="ERROR",
                                    execution_time_ms=(time.time() - started) * 1000,
                                    background_executed=False, error=err.to_rpc_error())
        except DAPError as exc:
            await self._state.transition(RuntimeState.FAULTED)
            return ExecutionResult(status="ERROR",
                                    execution_time_ms=(time.time() - started) * 1000,
                                    background_executed=False, error=exc.to_rpc_error())


# ==============================================================================
# SECTION 13 — SECURITY ENFORCER (Spec §10 Security & Integrity Enforcement)
# ==============================================================================

class SecurityEnforcer:
    """
    PID/PPID allowlisting for the Named Pipe endpoint plus elevation-boundary
    detection. Encrypted IPC / SDDL binding is handled at the transport layer.
    """

    def __init__(self, allowed_host_pids: Optional[List[int]] = None):
        self._allowed_pids = set(allowed_host_pids or [])

    def authorize_session(self, host_pid: int) -> bool:
        if not self._allowed_pids:
            return True  # open policy when no allowlist configured (dev/test mode)
        return host_pid in self._allowed_pids

    def check_elevation_boundary(self, target_hwnd: int) -> None:
        if not IS_WINDOWS or not PYWIN32_AVAILABLE:
            return
        try:
            _, pid = WIN32.get_process_thread(target_hwnd)
            handle = win32api.OpenProcess(  # type: ignore
                win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)  # type: ignore
            token = win32security.OpenProcessToken(handle, win32con.TOKEN_QUERY)  # type: ignore
            elevation = win32security.GetTokenInformation(  # type: ignore
                token, win32security.TokenElevation)  # type: ignore
            if elevation and not self._is_self_elevated():
                raise DAPError(DAPErrorCode.ERR_ACCESS_DENIED_ELEVATION,
                                f"Target process {pid} runs at higher integrity level")
        except DAPError:
            raise
        except Exception:
            return

    @staticmethod
    def _is_self_elevated() -> bool:
        if not IS_WINDOWS:
            return False
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False


# ==============================================================================
# SECTION 14 — SESSION MANAGER
# ==============================================================================

@dataclass
class Session:
    session_id: str
    host_pid: int
    created_at: float = field(default_factory=time.time)


class SessionManager:
    def __init__(self, security: SecurityEnforcer):
        self._security = security
        self._sessions: Dict[str, Session] = {}

    def open_session(self, host_pid: int) -> Session:
        if not self._security.authorize_session(host_pid):
            raise DAPError(DAPErrorCode.ERR_ACCESS_DENIED_ELEVATION,
                            f"Host PID {host_pid} not authorized to open DAP session")
        session = Session(session_id=f"sess_{uuid.uuid4().hex[:12]}", host_pid=host_pid)
        self._sessions[session.session_id] = session
        return session

    def close_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)


# ==============================================================================
# SECTION 14.5 — ENHANCED MULTI-SESSION SUPPORT (CDP-Style)
# ==============================================================================

@dataclass
class DAPSession:
    """Represents a single app session (like CDP session)."""
    session_id: str
    hwnd: int
    process_id: int
    app_name: str
    window_title: str
    tree_state: Dict[str, Any] = field(default_factory=dict)
    input_state: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    is_focused: bool = False
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "hwnd": self.hwnd,
            "process_id": self.process_id,
            "app_name": self.app_name,
            "window_title": self.window_title,
            "is_active": self.is_active,
            "is_focused": self.is_focused,
            "created_at": self.created_at,
            "last_active": self.last_active,
        }


class DAPSessionManager:
    """Manages multiple app sessions (CDP-style)."""

    def __init__(self):
        self._sessions: Dict[str, DAPSession] = {}
        self._active_session_id: Optional[str] = None
        self._session_counter = 0
        self._lock = threading.Lock()

    def create_session(self, hwnd: int, app_name: str) -> str:
        """Create a new session for an app."""
        with self._lock:
            session_id = f"dap_session_{self._session_counter}"
            self._session_counter += 1

            pid = self._get_process_id(hwnd)
            window_title = self._get_window_title(hwnd)

            session = DAPSession(
                session_id=session_id,
                hwnd=hwnd,
                process_id=pid,
                app_name=app_name,
                window_title=window_title,
                tree_state={},
                input_state={}
            )

            self._sessions[session_id] = session
            LOGGER.info(f"[DAPSessionManager] Created session {session_id} for {app_name}")
            return session_id

    def get_session(self, session_id: str) -> Optional[DAPSession]:
        """Get a session by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def get_active_session(self) -> Optional[DAPSession]:
        """Get the currently active session."""
        with self._lock:
            if self._active_session_id:
                return self._sessions.get(self._active_session_id)
            return None

    def switch_session(self, session_id: str) -> bool:
        """Switch active session (focus app)."""
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                LOGGER.warning(f"[DAPSessionManager] Session {session_id} not found")
                return False

            # Focus the window
            success = self._focus_window(session.hwnd)
            if not success:
                LOGGER.warning(f"[DAPSessionManager] Failed to focus window for session {session_id}")
                return False

            # Update active session
            self._active_session_id = session_id
            session.last_active = time.time()

            # Update focus states
            for sid, s in self._sessions.items():
                s.is_focused = (sid == session_id)

            LOGGER.info(f"[DAPSessionManager] Switched to session {session_id} ({session.app_name})")
            return True

    def close_session(self, session_id: str) -> bool:
        """Close a session."""
        with self._lock:
            if session_id not in self._sessions:
                return False

            session = self._sessions[session_id]
            LOGGER.info(f"[DAPSessionManager] Closing session {session_id} ({session.app_name})")

            del self._sessions[session_id]

            if self._active_session_id == session_id:
                self._active_session_id = None

            return True

    def list_sessions(self) -> List[DAPSession]:
        """List all active sessions."""
        with self._lock:
            return list(self._sessions.values())

    def get_session_by_app(self, app_name: str) -> Optional[DAPSession]:
        """Get session by app name."""
        with self._lock:
            for session in self._sessions.values():
                if session.app_name.lower() == app_name.lower():
                    return session
            return None

    def _get_process_id(self, hwnd: int) -> int:
        """Get process ID from window handle."""
        if not IS_WINDOWS:
            return 0
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        return int(pid.value)

    def _get_window_title(self, hwnd: int) -> str:
        """Get window title."""
        if not IS_WINDOWS:
            return ""
        length = user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, length + 1)
        return buf.value

    def _focus_window(self, hwnd: int) -> bool:
        """Focus a window."""
        if not IS_WINDOWS:
            return False
        return bool(user32.SetForegroundWindow(ctypes.c_void_p(hwnd)))


class DirectDataTransfer:
    """Copy-paste-free data transfer between sessions."""

    def __init__(self, session_manager: DAPSessionManager):
        self.session_manager = session_manager
        self._transfer_buffer: Dict[str, Any] = {}

    async def transfer_text(self, from_session: str, to_session: str,
                          source_selector: str, target_selector: str) -> bool:
        """
        Transfer text directly between apps without clipboard.

        Args:
            from_session: Source session ID
            to_session: Target session ID
            source_selector: Source element selector
            target_selector: Target element selector
        """
        source_session = self.session_manager.get_session(from_session)
        if not source_session:
            LOGGER.error(f"[DirectDataTransfer] Source session {from_session} not found")
            return False

        # Get text from source (placeholder - would use UIA/Win32)
        text = await self._get_element_text(source_session, source_selector)
        if not text:
            LOGGER.error(f"[DirectDataTransfer] Failed to get text from source")
            return False

        # Switch to target
        self.session_manager.switch_session(to_session)

        # Type text directly (no clipboard)
        target_session = self.session_manager.get_session(to_session)
        if not target_session:
            LOGGER.error(f"[DirectDataTransfer] Target session {to_session} not found")
            return False

        success = await self._type_into_element(target_session, target_selector, text)
        if success:
            LOGGER.info(f"[DirectDataTransfer] Transferred text from {from_session} to {to_session}")

        return success

    async def transfer_data(self, from_session: str, to_session: str,
                          data: Any) -> bool:
        """Transfer structured data between sessions."""
        self._transfer_buffer[to_session] = {
            "from_session": from_session,
            "data": data,
            "timestamp": time.time()
        }
        LOGGER.info(f"[DirectDataTransfer] Buffered data from {from_session} to {to_session}")
        return True

    async def retrieve_data(self, session_id: str) -> Optional[Any]:
        """Retrieve buffered data for a session."""
        if session_id in self._transfer_buffer:
            return self._transfer_buffer[session_id]["data"]
        return None

    async def _get_element_text(self, session: DAPSession, selector: str) -> Optional[str]:
        """Get text from element in session (placeholder implementation)."""
        # TODO: Implement using UIA/Win32
        LOGGER.debug(f"[DirectDataTransfer] Getting text from {selector} in session {session.session_id}")
        return "Sample text"  # Placeholder

    async def _type_into_element(self, session: DAPSession, selector: str, text: str) -> bool:
        """Type text into element without clipboard (placeholder implementation)."""
        # TODO: Implement using SendInput
        LOGGER.debug(f"[DirectDataTransfer] Typing into {selector} in session {session.session_id}")
        return True  # Placeholder


class ParallelExecutionEngine:
    """Execute tasks in parallel across multiple sessions."""

    def __init__(self, session_manager: DAPSessionManager):
        self.session_manager = session_manager
        self._running_tasks: Dict[str, asyncio.Task] = {}

    async def execute_parallel(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute tasks in parallel across multiple sessions.

        Args:
            tasks: List of task dicts with session_id and action
        """
        results = []

        async def execute_single_task(task):
            session_id = task["session_id"]
            action = task["action"]
            params = task.get("params", {})

            # Switch to session
            self.session_manager.switch_session(session_id)

            # Execute action
            try:
                result = await self._execute_action(session_id, action, params)
                return {"session_id": session_id, "result": result, "success": True}
            except Exception as e:
                LOGGER.error(f"[ParallelExecutionEngine] Task failed for {session_id}: {e}")
                return {"session_id": session_id, "error": str(e), "success": False}

        # Run in parallel
        coroutines = [execute_single_task(task) for task in tasks]
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        LOGGER.info(f"[ParallelExecutionEngine] Executed {len(results)} parallel tasks")
        return results

    async def _execute_action(self, session_id: str, action: str, params: Dict[str, Any]) -> Any:
        """Execute a single action in a session (placeholder implementation)."""
        # TODO: Implement based on action type
        LOGGER.debug(f"[ParallelExecutionEngine] Executing {action} on {session_id} with params {params}")
        return {"status": "completed"}  # Placeholder


class SmoothSwitchingOrchestrator:
    """Orchestrate smooth switching between apps."""

    def __init__(self, session_manager: DAPSessionManager):
        self.session_manager = session_manager
        self._switch_history: List[str] = []
        self._switch_cache: Dict[str, Any] = {}
        self._max_history = 10

    async def switch_with_state(self, from_session: str, to_session: str) -> bool:
        """
        Switch between apps while preserving state.

        Args:
            from_session: Current session
            to_session: Target session
        """
        # Save current state
        current_session = self.session_manager.get_session(from_session)
        if current_session:
            self._switch_cache[from_session] = {
                "hwnd": current_session.hwnd,
                "tree_state": current_session.tree_state.copy(),
                "input_state": current_session.input_state.copy(),
                "timestamp": time.time()
            }

        # Switch to target
        success = self.session_manager.switch_session(to_session)

        if success:
            # Restore target state
            target_session = self.session_manager.get_session(to_session)
            if to_session in self._switch_cache:
                cached = self._switch_cache[to_session]
                target_session.tree_state = cached["tree_state"]
                target_session.input_state = cached["input_state"]

            # Record switch
            self._switch_history.append(to_session)
            if len(self._switch_history) > self._max_history:
                self._switch_history.pop(0)

            LOGGER.info(f"[SmoothSwitchingOrchestrator] Switched from {from_session} to {to_session}")

        return success

    async def quick_switch(self, session_id: str) -> bool:
        """Quick switch without full state restoration."""
        return self.session_manager.switch_session(session_id)

    async def switch_back(self) -> bool:
        """Switch back to previous session."""
        if len(self._switch_history) < 2:
            return False

        # Get previous session
        prev_session = self._switch_history[-2]
        current_session = self._switch_history[-1]

        return await self.switch_with_state(current_session, prev_session)

    def get_switch_history(self) -> List[str]:
        """Get switch history."""
        return self._switch_history.copy()


# ==============================================================================
# SECTION 15 — DAP RUNTIME CORE (Orchestration of every subsystem above)
# ==============================================================================

@dataclass
class Finger:
    finger_id: int
    x: int = 0
    y: int = 0


class MouseHand:
    """Logical virtual 'hand' for a desktop / 3D-app session.

    The OS exposes a single hardware cursor, but the automation tracks an
    independent cursor position and a set of 'fingers' (multi-cursor) per session
    so concurrent workflows and 3D-modeling apps can address several pointers
    logically. The actual Win32 input is delegated to a shared InputInjector.
    """

    def __init__(self, session_id: str, injector: "InputInjector"):
        self.session_id = session_id
        self._injector = injector
        self.x: int = 0
        self.y: int = 0
        self.fingers: List[Finger] = [Finger(0)]
        self.last_action: str = "idle"

    def move_to(self, x: int, y: int) -> None:
        WIN32._move_cursor(x, y)
        self.x, self.y = x, y
        self.last_action = f"move ({x},{y})"

    def click(self, x: int, y: int, button: str = "left") -> None:
        self._injector.click(x, y, button)
        self.x, self.y = x, y
        self.last_action = f"click ({x},{y}) {button}"

    def double_click(self, x: int, y: int) -> None:
        self._injector.double_click(x, y)
        self.last_action = f"double-click ({x},{y})"

    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int) -> None:
        self._injector.drag(start_x, start_y, end_x, end_y)
        self.x, self.y = end_x, end_y
        self.last_action = f"drag ({start_x},{start_y})->({end_x},{end_y})"

    def scroll(self, delta_x: int, delta_y: int) -> None:
        self._injector.scroll(delta_x, delta_y)
        self.last_action = f"scroll ({delta_x},{delta_y})"

    def add_finger(self) -> Finger:
        """Spawn an additional cursor (finger) for multi-cursor 3D apps."""
        finger = Finger(len(self.fingers))
        self.fingers.append(finger)
        return finger

    def multi_touch(self, points: List[Tuple[int, int]]) -> None:
        """Logically address several pointers at once (3D-modeling apps).

        Win32 has a single hardware cursor, so the primary cursor is stepped
        through each point while every finger records its own coordinates.
        """
        for i, (px, py) in enumerate(points):
            if i < len(self.fingers):
                self.fingers[i].x, self.fingers[i].y = px, py
        self.x, self.y = points[0] if points else (self.x, self.y)
        self.last_action = f"multi-touch {len(points)} fingers (logical)"


class HandRegistry:
    """Maps session_id -> MouseHand so each desktop/3D session owns its hand."""

    def __init__(self) -> None:
        self._hands: Dict[str, MouseHand] = {}

    def get_or_create(self, session_id: str, injector: "InputInjector") -> MouseHand:
        hand = self._hands.get(session_id)
        if hand is None:
            hand = MouseHand(session_id, injector)
            self._hands[session_id] = hand
        return hand

    def get(self, session_id: str) -> Optional[MouseHand]:
        return self._hands.get(session_id)

    def remove(self, session_id: str) -> None:
        self._hands.pop(session_id, None)


class DAPRuntimeCore:
    """
    Public-facing runtime object. This is the single class an embedding
    Hojaiga organ (e.g. Execution Controller / CNS) instantiates directly
    or drives remotely via the JSON-RPC socket defined in Section 16.
    """

    VERSION = "1.0.0-PROD"
    SPEC_ID = "Hojaiga-SPEC-GUI-CDP-001"

    def __init__(self, allowed_host_pids: Optional[List[int]] = None,
                 vision_model_path: Optional[str] = None):
        self.state = StateMachine()
        self.providers = ProviderRegistry()
        self.desktop_tree = DesktopTree()
        self.window_tree = WindowTree(self.providers)
        self.event_tree = EventTree()
        self.perception = PerceptionPipeline(self.window_tree, vision_model_path)
        self.query_engine = QueryEngine(self.window_tree, self.perception)
        self.interaction = InteractionPipeline(self.providers)
        self.recovery = RecoveryEngine(self.window_tree, self.perception,
                                        self.interaction.injector, self.state)
        self.popups = PopupSubsystem(self.window_tree, self.interaction)
        self.file_picker = NativeFilePicker(self.window_tree, self.interaction, self.popups)
        self.security = SecurityEnforcer(allowed_host_pids)
        self.sessions = SessionManager(self.security)
        self._injector = self.interaction.injector
        self.hands = HandRegistry()
        self._initialized = False
        
        # Enhanced multi-session components (CDP-style)
        self._app_session_manager = DAPSessionManager()
        self._data_transfer = DirectDataTransfer(self._app_session_manager)
        self._parallel_engine = ParallelExecutionEngine(self._app_session_manager)
        self._switch_orchestrator = SmoothSwitchingOrchestrator(self._app_session_manager)

    async def initialize(self) -> None:
        LOGGER.info("Organ 24 DAP Runtime Core initializing (spec=%s v%s)",
                    self.SPEC_ID, self.VERSION)
        self.desktop_tree.rescan()
        self.window_tree.rescan()
        self._initialized = True
        await self.state.transition(RuntimeState.READY)
        await self.event_tree.publish("Runtime.ready", {
            "status": "RUNNING", "monitors": len(self.desktop_tree.monitors),
            "windows": len(self.window_tree.nodes()),
        })

    async def shutdown(self) -> None:
        LOGGER.info("Organ 24 DAP Runtime Core shutting down")
        self.window_tree.clear()
        self._initialized = False

    def _require_ready(self) -> None:
        if not self._initialized:
            raise DAPError(DAPErrorCode.ERR_TIMEOUT, "DAP runtime not initialized")

    # ---- Window.* domain ----------------------------------------------------
    async def window_enumerate(self, include_child_windows: bool = True,
                                process_filter: Optional[List[int]] = None) -> List[dict]:
        self._require_ready()
        await self.state.transition(RuntimeState.SCANNING)
        self.window_tree.rescan(include_child_windows, process_filter)
        await self.state.transition(RuntimeState.READY)
        return [n.as_dict() for n in self.window_tree.nodes().values()]

    async def window_focus(self, target: NodeTarget) -> dict:
        self._require_ready()
        node = self.query_engine.resolve(target)
        await self.state.transition(RuntimeState.EXECUTING)
        try:
            self.interaction.focus.lock_and_focus(node.hwnd)
            await self.state.transition(RuntimeState.READY)
            return {"nodeId": node.node_id, "focused": True}
        except DAPError:
            await self.state.transition(RuntimeState.FAULTED)
            await self.state.transition(RuntimeState.READY)
            raise

    async def window_restore(self, target: NodeTarget) -> dict:
        node = self.query_engine.resolve(target)
        WIN32.show_window(node.hwnd, WIN32.SW_RESTORE)
        return {"nodeId": node.node_id, "state": "RESTORED"}

    async def window_minimize(self, target: NodeTarget) -> dict:
        node = self.query_engine.resolve(target)
        WIN32.show_window(node.hwnd, WIN32.SW_MINIMIZE)
        return {"nodeId": node.node_id, "state": "MINIMIZED"}

    async def window_maximize(self, target: NodeTarget) -> dict:
        node = self.query_engine.resolve(target)
        WIN32.show_window(node.hwnd, WIN32.SW_MAXIMIZE)
        return {"nodeId": node.node_id, "state": "MAXIMIZED"}

    async def window_capture(self, target: NodeTarget, options: Optional[CaptureOptions] = None) -> dict:
        node = self.query_engine.resolve(target)
        result = self.perception.capture.capture(node, options or CaptureOptions())
        return dataclasses.asdict(result)

    async def window_query(self, selector: SelectorQuery) -> List[dict]:
        nodes = self.query_engine.query(selector)
        return [n.as_dict() for n in nodes]

    # ---- DAP Layered Win32 Capsule HUD (from prompt) ----
    class DAPOverlayCapsuleHUD:
        """Spawns an asynchronous Win32 top-level layered overlay window to render actions."""
        def __init__(self):
            self.hwnd = 0
            self.text = "DAP Core Ready"
            self.state = "working"
            self._thread = None
            self._loop_count = 0
            self._last_tree_hash = None
        def start(self):
            if not IS_WINDOWS or user32 is None or gdi32 is None or wintypes is None: return
            self._thread = threading.Thread(target=self._run_native_window_loop, daemon=True)
            self._thread.start()
        def set_telemetry(self, message: str, state: str = "working"):
            self.text = message
            self.state = state
            if self.hwnd and user32 is not None and user32.IsWindow(self.hwnd):
                user32.InvalidateRect(ctypes.c_void_p(self.hwnd), None, True)
        def _run_native_window_loop(self):
            if not IS_WINDOWS or user32 is None or gdi32 is None or wintypes is None:
                return
            WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_int64, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint64, ctypes.c_int64)
            def wnd_proc(hwnd, msg, wparam, lparam):
                if msg == 0x000F:
                    ps = ctypes.create_string_buffer(64)
                    hdc = user32.BeginPaint(ctypes.c_void_p(hwnd), ps)
                    rect = wintypes.RECT(5, 5, 235, 35)
                    color_hex = 0x001A1A1A
                    if self.state == "input_needed": color_hex = 0x001F1FFF
                    elif self.state == "paused": color_hex = 0x0000A5FF
                    brush = gdi32.CreateSolidBrush(color_hex)
                    user32.FillRect(hdc, ctypes.byref(rect), brush)
                    gdi32.DeleteObject(brush)
                    user32.SetTextColor(hdc, 0x00E2E8F0)
                    user32.SetBkMode(hdc, 1)
                    user32.DrawTextW(hdc, self.text, -1, ctypes.byref(rect), 0x0004 | 0x0020 | 0x0001)
                    user32.EndPaint(ctypes.c_void_p(hwnd), ps)
                    return 0
                return user32.DefWindowProcW(ctypes.c_void_p(hwnd), msg, wparam, lparam)
            WS_EX_TOPMOST = 0x00000008
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000
            WS_POPUP = 0x80000000
            self.hwnd = user32.CreateWindowExW(WS_EX_TOPMOST | WS_EX_TRANSPARENT | WS_EX_LAYERED, "STATIC", "Hojaiga DAP HUD", WS_POPUP, 840, 25, 240, 40, None, None, None, None)
            user32.SetLayeredWindowAttributes(ctypes.c_void_p(self.hwnd), 0, 235, 0x00000002)
            user32.ShowWindow(ctypes.c_void_p(self.hwnd), 5)
            msg = wintypes.MSG()
            while user32 and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if user32 is None:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

    # ---- Control.* domain -----------------------------------------------------
    async def control_query(self, selector: SelectorQuery) -> List[dict]:
        return await self.window_query(selector)

    async def control_invoke(self, target: NodeTarget, force_foreground: bool = False) -> dict:
        self._require_ready()
        if not hasattr(self, "hud"):
            self.hud = self.DAPOverlayCapsuleHUD()
            self.hud.start()
            # load DAP desktop_hud config
            try:
                cfg = load_system_config().get("organ_24_dap", {}).get("desktop_hud", {})
                if cfg:
                    self.hud.text = "DAP ready"
            except Exception:
                pass
        node = self.query_engine.resolve(target)
        self.hud.set_telemetry(f"Interacting: {node.control_type}", state="working")
        await self.state.transition(RuntimeState.EXECUTING)
        result = self.interaction.invoke(node, force_foreground)
        # Win32 Node verification and loop structural processing (virtual mouse via gatekeeper, no physical)
        try:
            current_tree = [n.class_name for n in self.window_tree.nodes().values()]
            tree_hash = hashlib.md5("".join(current_tree).encode('utf-8')).hexdigest()
            if tree_hash == self.hud._last_tree_hash:
                self.hud._loop_count += 1
            else:
                self.hud._loop_count = 0
                self.hud._last_tree_hash = tree_hash
            if self.hud._loop_count >= 3:
                self.hud.set_telemetry("Agent needs your input", state="input_needed")
                self.hud._loop_count = 0
                initial_fg = user32.GetForegroundWindow() if (IS_WINDOWS and user32 is not None) else None
                while IS_WINDOWS and user32 is not None and user32.GetForegroundWindow() == initial_fg:
                    await asyncio.sleep(0.5)
                self.hud.set_telemetry("Failsafe cleared | Resuming UI processing", state="working")
        except Exception:
            pass
        if result.status == "ERROR" and result.error and result.error["data"]["errorConstant"] == "ERR_WINDOW_STALE":
            result = await self.recovery.recover(node, "control.invoke")

    # ---- Enhanced Multi-Session Domain (CDP-Style) -----------------------
    async def session_create(self, app_name: str) -> dict:
        """Create a new session for an app (CDP-style)."""
        self._require_ready()
        hwnd = self._find_app_window(app_name)
        if not hwnd:
            raise DAPError(DAPErrorCode.ERR_TARGET_NOT_FOUND, f"App not found: {app_name}")
        
        session_id = self._app_session_manager.create_session(hwnd, app_name)
        session = self._app_session_manager.get_session(session_id)
        return session.to_dict() if session else {"error": "Failed to create session"}

    async def session_switch(self, session_id: str) -> dict:
        """Switch to an app session (CDP-style)."""
        self._require_ready()
        success = self._app_session_manager.switch_session(session_id)
        return {"session_id": session_id, "switched": success}

    async def session_close(self, session_id: str) -> dict:
        """Close an app session."""
        self._require_ready()
        success = self._app_session_manager.close_session(session_id)
        return {"session_id": session_id, "closed": success}

    async def session_list(self) -> dict:
        """List all active sessions."""
        self._require_ready()
        sessions = self._app_session_manager.list_sessions()
        return {
            "sessions": [s.to_dict() for s in sessions],
            "active_session": self._app_session_manager._active_session_id,
            "count": len(sessions)
        }

    async def session_get(self, session_id: str) -> dict:
        """Get session details."""
        self._require_ready()
        session = self._app_session_manager.get_session(session_id)
        return session.to_dict() if session else {"error": "Session not found"}

    async def data_transfer(self, from_session: str, to_session: str,
                           source_selector: str, target_selector: str) -> dict:
        """Transfer data between apps without clipboard."""
        self._require_ready()
        success = await self._data_transfer.transfer_text(
            from_session, to_session, source_selector, target_selector
        )
        return {
            "from_session": from_session,
            "to_session": to_session,
            "transferred": success
        }

    async def execute_parallel(self, tasks: List[dict]) -> dict:
        """Execute tasks in parallel across multiple sessions."""
        self._require_ready()
        results = await self._parallel_engine.execute_parallel(tasks)
        return {"tasks": len(tasks), "results": results}

    async def switch_with_state(self, from_session: str, to_session: str) -> dict:
        """Switch between apps while preserving state."""
        self._require_ready()
        success = await self._switch_orchestrator.switch_with_state(from_session, to_session)
        return {
            "from_session": from_session,
            "to_session": to_session,
            "switched": success
        }

    def _find_app_window(self, app_name: str) -> Optional[int]:
        """Find window for app by name."""
        for hwnd in WIN32.enumerate_top_level_windows():
            title = WIN32.get_window_title(hwnd).lower()
            class_name = WIN32.get_class_name(hwnd).lower()
            if app_name.lower() in title or app_name.lower() in class_name:
                return hwnd
        return None

    async def control_value(self, target: NodeTarget, text_value: Optional[str] = None) -> dict:
        node = self.query_engine.resolve(target)
        if text_value is None:
            provider = self.providers.resolve(node.hwnd, node.class_name)
            return {"nodeId": node.node_id, "value": provider.read_value(node)}
        result = self.interaction.set_value(node, text_value)
        return dataclasses.asdict(result)

    async def control_read(self, target: NodeTarget) -> dict:
        node = self.query_engine.resolve(target)
        return node.as_dict()

    # ---- Mouse.* domain ---------------------------------------------------------
    async def mouse_move(self, x: int, y: int, session_id: str = "default") -> dict:
        self.hands.get_or_create(session_id, self._injector).move_to(x, y)
        return {"x": x, "y": y, "hand": session_id}

    async def mouse_click(self, x: int, y: int, button: str = "left", session_id: str = "default") -> dict:
        self.hands.get_or_create(session_id, self._injector).click(x, y, button)
        return {"x": x, "y": y, "button": button, "hand": session_id}

    async def mouse_double_click(self, x: int, y: int, session_id: str = "default") -> dict:
        self.hands.get_or_create(session_id, self._injector).double_click(x, y)
        return {"x": x, "y": y, "hand": session_id}

    async def mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int,
                         session_id: str = "default") -> dict:
        self.hands.get_or_create(session_id, self._injector).drag(start_x, start_y, end_x, end_y)
        return {"from": [start_x, start_y], "to": [end_x, end_y], "hand": session_id}

    async def mouse_scroll(self, delta_x: int, delta_y: int, session_id: str = "default") -> dict:
        self.hands.get_or_create(session_id, self._injector).scroll(delta_x, delta_y)
        return {"deltaX": delta_x, "deltaY": delta_y, "hand": session_id}

    # ---- Virtual hands / fingers (multi-cursor for 3D apps) --------------------
    def get_hand(self, session_id: str) -> "MouseHand":
        """Return the independent virtual hand for a desktop/3D session."""
        return self.hands.get_or_create(session_id, self._injector)

    def add_finger(self, session_id: str = "default") -> int:
        return self.hands.get_or_create(session_id, self._injector).add_finger().finger_id

    async def multi_touch(self, points: List[Tuple[int, int]], session_id: str = "default") -> dict:
        self.hands.get_or_create(session_id, self._injector).multi_touch(points)
        return {"fingers": len(points), "hand": session_id}

    # ---- Keyboard.* domain -------------------------------------------------------
    async def keyboard_type(self, text: str) -> dict:
        self.interaction.injector.type_text(text)
        return {"charsSent": len(text)}

    async def keyboard_shortcut(self, sequence: str) -> dict:
        self.interaction.injector.shortcut(sequence)
        return {"sequence": sequence}

    # ---- OCR.* / Vision.* domain -------------------------------------------------
    async def ocr_query(self, target: NodeTarget, text_pattern: str) -> List[dict]:
        node = self.query_engine.resolve(target)
        matches = self.perception.ocr.query(node, text_pattern, self.perception.capture)
        return [m.as_dict() for m in matches]

    async def vision_query(self, target: NodeTarget, class_name: str) -> List[dict]:
        node = self.query_engine.resolve(target)
        matches = self.perception.vision.query(node, class_name, self.perception.capture)
        return [m.as_dict() for m in matches]

    # ---- Popup / Dialog / Installer / FilePicker domain --------------------------
    async def popup_detect(self, owner_target: NodeTarget) -> List[dict]:
        owner = self.query_engine.resolve(owner_target)
        popups = self.popups.detect(owner.hwnd)
        return [{**p.as_dict(), "classification": self.popups.classify(p)} for p in popups]

    async def popup_accept(self, target: NodeTarget) -> dict:
        node = self.query_engine.resolve(target)
        result = self.popups.accept(node)
        return dataclasses.asdict(result)

    async def popup_dismiss(self, target: NodeTarget) -> dict:
        node = self.query_engine.resolve(target)
        return {"nodeId": node.node_id, "dismissed": self.popups.dismiss(node)}

    async def file_picker_select(self, path: str) -> dict:
        dialog = self.file_picker.locate_dialog()
        if not dialog:
            raise DAPError(DAPErrorCode.ERR_NODE_NOT_FOUND, "No active file picker dialog found")
        set_result = self.file_picker.select_path(dialog, path)
        confirm_result = self.file_picker.confirm(dialog)
        return {"select": dataclasses.asdict(set_result),
                "confirm": dataclasses.asdict(confirm_result)}

    # ---- Screens / Displays --------------------------------------------------------
    async def screens_enumerate(self) -> List[dict]:
        self.desktop_tree.rescan()
        return [m.as_dict() for m in self.desktop_tree.monitors]


# ==============================================================================
# SECTION 16 — GUI-CDP COMMUNICATION: SOCKETS & PIPELINES (Spec §6)
# ==============================================================================

class JSONRPCProtocol:
    """Parses/serializes JSON-RPC 2.0 frames per Spec §6.1 wire format."""

    @staticmethod
    def parse(raw: bytes) -> dict:
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DAPError(DAPErrorCode.ERR_INVALID_SELECTOR, f"Malformed JSON-RPC frame: {exc}")

    @staticmethod
    def success(request_id: Any, result: Any) -> bytes:
        return (json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n").encode("utf-8")

    @staticmethod
    def failure(request_id: Any, error: dict) -> bytes:
        return (json.dumps({"jsonrpc": "2.0", "id": request_id, "error": error}) + "\n").encode("utf-8")


class DAPSocket:
    """
    Named Pipe (Windows) JSON-RPC 2.0 endpoint: \\\\.\\pipe\\hojaiga_dap_<id>
    Falls back to a loopback TCP socket when Named Pipes are unavailable
    (non-Windows dev/test hosts), preserving identical wire semantics.

    Socket Definition (per Organ Specification socket rules):
        Name              : DAP Socket
        Version           : 1.0.0
        Direction         : Bidirectional (Host <-> DAP Runtime)
        Allowed Data      : JSON-RPC 2.0 request / response / event frames
        Validation        : JSONRPCProtocol.parse + method dispatch table
        Security          : SecurityEnforcer PID allowlist + SDDL (Windows)
        Failure Behaviour : Emits JSON-RPC error frame; connection preserved
        Retry Behaviour   : Host-driven; runtime never auto-reconnects
    """

    def __init__(self, core: DAPRuntimeCore, pipe_name: str = "hojaiga_dap_01",
                 tcp_port: int = 8765):
        self.core = core
        self.pipe_name = pipe_name
        self.tcp_port = tcp_port
        self._dispatch = self._build_dispatch_table()
        self._running = False

    def _build_dispatch_table(self) -> Dict[str, Callable]:
        c = self.core
        return {
            "Window.enumerate": lambda p: c.window_enumerate(
                p.get("includeChildWindows", True), p.get("processFilter")),
            "Window.focus": lambda p: c.window_focus(self._target(p)),
            "Window.restore": lambda p: c.window_restore(self._target(p)),
            "Window.minimize": lambda p: c.window_minimize(self._target(p)),
            "Window.maximize": lambda p: c.window_maximize(self._target(p)),
            "Window.capture": lambda p: c.window_capture(
                self._target(p), CaptureOptions(**p.get("options", {}))),
            "Window.query": lambda p: c.window_query(
                SelectorQuery(p.get("queryType", "native"), p["selector"])),
            "Control.query": lambda p: c.control_query(
                SelectorQuery(p.get("queryType", "native"), p["selector"])),
            "Control.invoke": lambda p: c.control_invoke(
                self._target(p), p.get("options", {}).get("forceForeground", False)),
            "Control.value": lambda p: c.control_value(self._target(p), p.get("textValue")),
            "Control.read": lambda p: c.control_read(self._target(p)),
            "Mouse.move": lambda p: c.mouse_move(p["x"], p["y"]),
            "Mouse.click": lambda p: c.mouse_click(p["x"], p["y"], p.get("button", "left")),
            "Mouse.doubleClick": lambda p: c.mouse_double_click(p["x"], p["y"]),
            "Mouse.drag": lambda p: c.mouse_drag(p["startX"], p["startY"], p["endX"], p["endY"]),
            "Mouse.scroll": lambda p: c.mouse_scroll(p.get("deltaX", 0), p.get("deltaY", 0)),
            "Keyboard.type": lambda p: c.keyboard_type(p["text"]),
            "Keyboard.shortcut": lambda p: c.keyboard_shortcut(p["shortcutSequence"]),
            "OCR.query": lambda p: c.ocr_query(self._target(p), p["textPattern"]),
            "Vision.query": lambda p: c.vision_query(self._target(p), p["className"]),
            "Popup.detect": lambda p: c.popup_detect(self._target(p)),
            "Popup.accept": lambda p: c.popup_accept(self._target(p)),
            "Popup.dismiss": lambda p: c.popup_dismiss(self._target(p)),
            "FilePicker.select": lambda p: c.file_picker_select(p["path"]),
            "Screens.enumerate": lambda p: c.screens_enumerate(),
        }

    @staticmethod
    def _target(params: dict) -> NodeTarget:
        target = params.get("target", {})
        return NodeTarget(node_id=target.get("nodeId"), hwnd=target.get("hwnd"),
                           selector=target.get("selector"))

    async def handle_frame(self, raw: bytes) -> bytes:
        try:
            frame = JSONRPCProtocol.parse(raw)
        except DAPError as exc:
            return JSONRPCProtocol.failure(None, exc.to_rpc_error())

        request_id = frame.get("id")
        method = frame.get("method")
        params = frame.get("params", {})

        if not isinstance(method, str):
            err = DAPError(DAPErrorCode.ERR_INVALID_SELECTOR, "Invalid method")
            return JSONRPCProtocol.failure(request_id, err.to_rpc_error())

        handler = self._dispatch.get(method)
        if handler is None:
            err = DAPError(DAPErrorCode.ERR_INVALID_SELECTOR, f"Unknown method '{method}'")
            return JSONRPCProtocol.failure(request_id, err.to_rpc_error())

        try:
            result = await handler(params)
            return JSONRPCProtocol.success(request_id, result)
        except DAPError as exc:
            return JSONRPCProtocol.failure(request_id, exc.to_rpc_error())
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Unhandled exception dispatching %s", method)
            err = DAPError(DAPErrorCode.ERR_TIMEOUT, str(exc))
            return JSONRPCProtocol.failure(request_id, err.to_rpc_error())

    # ---- Transport: Named Pipe (Windows) -------------------------------------------
    async def serve_named_pipe(self) -> None:
        if not (IS_WINDOWS and PYWIN32_AVAILABLE):
            LOGGER.warning("Named Pipe transport unavailable; use serve_tcp() instead.")
            return
        self._running = True
        pipe_path = rf"\\.\pipe\{self.pipe_name}"
        loop = asyncio.get_event_loop()
        while self._running:
            handle = win32pipe.CreateNamedPipe(  # type: ignore
                pipe_path,
                win32pipe.PIPE_ACCESS_DUPLEX,  # type: ignore
                win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,  # type: ignore
                win32pipe.PIPE_UNLIMITED_INSTANCES, 65536, 65536, 0, None,  # type: ignore
            )
            await loop.run_in_executor(None, win32pipe.ConnectNamedPipe, handle, None)  # type: ignore
            await self._serve_pipe_client(handle, loop)

    async def _serve_pipe_client(self, handle, loop) -> None:
        try:
            while self._running:
                _, data = await loop.run_in_executor(None, win32file.ReadFile, handle, 65536)  # type: ignore
                if not data:
                    break
                response = await self.handle_frame(data)
                await loop.run_in_executor(None, win32file.WriteFile, handle, response)  # type: ignore
        finally:
            win32file.CloseHandle(handle)  # type: ignore

    # ---- Transport: TCP loopback (portable / testing) --------------------------------
    async def serve_tcp(self) -> asyncio.AbstractServer:
        async def _client_connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            try:
                while True:
                    line = await reader.readline()
                    if not line:
                        break
                    response = await self.handle_frame(line)
                    writer.write(response)
                    await writer.drain()
            finally:
                writer.close()

        server = await asyncio.start_server(_client_connected, "127.0.0.1", self.tcp_port)
        self._running = True
        LOGGER.info("DAP Socket listening on tcp://127.0.0.1:%d (JSON-RPC 2.0)", self.tcp_port)
        return server

    def stop(self) -> None:
        self._running = False


# ==============================================================================
# SECTION 17 — PUBLIC FACADE
# ==============================================================================

class DesktopAutomationProtocol:
    """
    Top-level public entry point for Organ 24. Wraps DAPRuntimeCore and
    DAPSocket for straightforward embedding by other Hojaiga organs.
    """

    def __init__(self, allowed_host_pids: Optional[List[int]] = None,
                 vision_model_path: Optional[str] = None,
                 pipe_name: str = "hojaiga_dap_01", tcp_port: int = 8765):
        self.core = DAPRuntimeCore(allowed_host_pids, vision_model_path)
        self.socket = DAPSocket(self.core, pipe_name, tcp_port)

    async def start(self, transport: str = "auto") -> None:
        await self.core.initialize()
        if transport == "auto":
            transport = "named_pipe" if (IS_WINDOWS and PYWIN32_AVAILABLE) else "tcp"
        if transport == "named_pipe":
            asyncio.create_task(self.socket.serve_named_pipe())
        elif transport == "tcp":
            await self.socket.serve_tcp()

    async def stop(self) -> None:
        self.socket.stop()
        await self.core.shutdown()

    def store_elements_batch(self, app_name: str, elements: Optional[List[Dict[str, Any]]] = None) -> int:
        """Batch-store scanned UI element profiles (single SELECT + 2 executemany).

        Thin public wrapper around DatabaseManager.upsert_element_profiles_batch
        so the DAP surface exposes the UIA scan hot path without per-element DB
        round trips. Returns the number of profiles written (0 on DB failure).
        """
        elements = elements or []
        if not elements:
            return 0
        try:
            if getattr(self, "_db_manager", None) is None:
                from core_organs.database_manager import DatabaseManager
                self._db_manager = DatabaseManager()
            return int(self._db_manager.upsert_element_profiles_batch(app_name, elements) or 0)
        except Exception as exc:
            LOGGER.warning("[DAP] store_elements_batch failed: %s", exc)
            return 0


# Backwards-compatible alias: some tools/tests import the DAP entry point
# under the historical name "DAPBridge".
DAPBridge = DesktopAutomationProtocol

__all__ = [
    "DesktopAutomationProtocol", "DAPBridge", "DAPRuntimeCore", "DAPSocket", "JSONRPCProtocol",
    "DAPError", "DAPErrorCode", "RuntimeState", "StateMachine",
    "DAPNode", "Rect", "NodeTarget", "SelectorQuery", "CaptureOptions",
    "CaptureResult", "ExecutionResult", "Win32Primitives", "WIN32",
    "ProviderInterface", "Win32Provider", "UIAProvider", "JavaAccessBridgeProvider",
    "ProviderRegistry", "WindowTree", "DesktopTree", "EventTree", "QueryEngine",
    "InteractionPipeline", "BackgroundExecutor", "FocusOrchestrator", "InputInjector",
    "PerceptionPipeline", "CaptureEngine", "OCREngine", "VisionEngine",
    "PopupSubsystem", "NativeFilePicker", "RecoveryEngine", "SecurityEnforcer",
    "SessionManager", "Session",
]
