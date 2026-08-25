"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 24
Name: Desktop Automation Protocol (DAP) / GUI-CDP Runtime

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
"""
from __future__ import annotations

import asyncio
import ctypes
import dataclasses
import enum
import json
import logging
import platform
import struct
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

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
# SECTION 1 — ERROR CATALOG
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
# SECTION 2 — STATE CATALOG
# ==============================================================================
class RuntimeState(enum.Enum):
    UNINITIALIZED = "UNINITIALIZED"
    READY = "READY"
    EXECUTING = "EXECUTING"
    SCANNING = "SCANNING"
    RECOVERING = "RECOVERING"
    FAULTED = "FAULTED"


class StateMachine:
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
# SECTION 3 — DATA CONTRACTS
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
    query_type: str
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
# SECTION 4 — WIN32 PRIMITIVES
# ==============================================================================
class Win32Primitives:
    WM_COMMAND = 0x0111
    WM_SETTEXT = 0x000C
    WM_GETTEXT = 0x000D
    WM_GETTEXTLENGTH = 0x000E
    BM_CLICK = 0x00F5
    WM_CLOSE = 0x0010
    SW_RESTORE = 9
    SW_MINIMIZE = 6
    SW_MAXIMIZE = 3

    def enumerate_top_level_windows(self) -> List[int]:
        if not IS_WINDOWS:
            return []
        hwnds: List[int] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(hwnd, _lparam):
            hwnds.append(int(hwnd))
            return True

        user32.EnumWindows(_cb, 0)
        return hwnds

    def enumerate_child_windows(self, hwnd: int) -> List[int]:
        if not IS_WINDOWS:
            return []
        children: List[int] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(child_hwnd, _lparam):
            children.append(int(child_hwnd))
            return True

        user32.EnumChildWindows(ctypes.c_void_p(hwnd), _cb, 0)
        return children

    def get_window_text(self, hwnd: int) -> str:
        if not IS_WINDOWS:
            return ""
        length = user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, length + 1)
        return buf.value

    def get_class_name(self, hwnd: int) -> str:
        if not IS_WINDOWS:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(ctypes.c_void_p(hwnd), buf, 256)
        return buf.value

    def get_window_rect(self, hwnd: int) -> Rect:
        if not IS_WINDOWS:
            return Rect()
        r = wintypes.RECT()
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
        return Rect(left=r.left, top=r.top, right=r.right, bottom=r.bottom,
                    scale_factor=self.get_dpi_scale(hwnd))

    def get_dpi_scale(self, hwnd: int) -> float:
        if not IS_WINDOWS:
            return 1.0
        try:
            dpi = user32.GetDpiForWindow(ctypes.c_void_p(hwnd))
            return round(dpi / 96.0, 3) if dpi else 1.0
        except Exception:
            return 1.0

    def get_process_thread(self, hwnd: int) -> Tuple[int, int]:
        if not IS_WINDOWS:
            return (0, 0)
        pid = wintypes.DWORD(0)
        tid = user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        return (int(tid), int(pid.value))

    def is_window_visible(self, hwnd: int) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.IsWindowVisible(ctypes.c_void_p(hwnd)))

    def is_window_enabled(self, hwnd: int) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.IsWindowEnabled(ctypes.c_void_p(hwnd)))

    def is_window(self, hwnd: int) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.IsWindow(ctypes.c_void_p(hwnd)))

    def get_foreground_window(self) -> int:
        if not IS_WINDOWS:
            return 0
        return int(user32.GetForegroundWindow())

    def set_foreground_window(self, hwnd: int) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.SetForegroundWindow(ctypes.c_void_p(hwnd)))

    def show_window(self, hwnd: int, cmd: int) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.ShowWindow(ctypes.c_void_p(hwnd), cmd))

    def attach_thread_input(self, tid_a: int, tid_b: int, attach: bool) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.AttachThreadInput(tid_a, tid_b, attach))

    def send_message(self, hwnd: int, msg: int, wparam: int = 0, lparam: int = 0) -> int:
        if not IS_WINDOWS:
            return 0
        return int(user32.SendMessageW(ctypes.c_void_p(hwnd), msg, wparam, lparam))

    def post_message(self, hwnd: int, msg: int, wparam: int = 0, lparam: int = 0) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.PostMessageW(ctypes.c_void_p(hwnd), msg, wparam, lparam))

    def set_window_text(self, hwnd: int, text: str) -> bool:
        if not IS_WINDOWS:
            return False
        return bool(user32.SendMessageW(ctypes.c_void_p(hwnd), self.WM_SETTEXT, 0, text))

    def get_control_text(self, hwnd: int) -> str:
        return self.get_window_text(hwnd)

    def click_button(self, hwnd: int) -> bool:
        if not IS_WINDOWS:
            return False
        self.send_message(hwnd, self.BM_CLICK, 0, 0)
        return True

    def send_input_click(self, x: int, y: int, button: str = "left") -> None:
        if not IS_WINDOWS:
            return
        self._move_cursor(x, y)
        down, up = {
            "left": (0x0002, 0x0004),
            "right": (0x0008, 0x0010),
            "middle": (0x0020, 0x0040),
        }[button]
        self._send_mouse_event(down)
        time.sleep(0.04)
        self._send_mouse_event(up)

    def _move_cursor(self, x: int, y: int) -> None:
        user32.SetCursorPos(int(x), int(y))

    def _send_mouse_event(self, flag: int) -> None:
        user32.mouse_event(flag, 0, 0, 0, 0)

    def send_unicode_text(self, text: str) -> None:
        if not IS_WINDOWS:
            return
        KEYEVENTF_UNICODE = 0x0004
        KEYEVENTF_KEYUP = 0x0002

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class _INPUTUNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_uint32), ("union", _INPUTUNION)]

        INPUT_KEYBOARD = 1
        extra = ctypes.c_ulong(0)

        for ch in text:
            ki_down = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE, 0, ctypes.pointer(extra))
            inp_down = INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=ki_down))
            user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(inp_down))

            ki_up = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
            inp_up = INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=ki_up))
            user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(inp_up))
            time.sleep(0.015)

    def send_vk(self, vk: int, keyup: bool = False) -> None:
        if not IS_WINDOWS:
            return
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP if keyup else 0, 0)

    def capture_window_bitmap_bytes(self, hwnd: int) -> Tuple[int, int, bytes]:
        if not IS_WINDOWS:
            return (0, 0, b"")
        rect = self.get_window_rect(hwnd)
        width = max(1, rect.right - rect.left)
        height = max(1, rect.bottom - rect.top)

        hwnd_dc = user32.GetWindowDC(ctypes.c_void_p(hwnd))
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
        gdi32.SelectObject(mem_dc, bitmap)

        PW_RENDERFULLCONTENT = 0x00000002
        result = user32.PrintWindow(ctypes.c_void_p(hwnd), mem_dc, PW_RENDERFULLCONTENT)
        if not result:
            SRCCOPY = 0x00CC0020
            gdi32.BitBlt(mem_dc, 0, 0, width, height, hwnd_dc, 0, 0, SRCCOPY)

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

        gdi32.GetDIBits(mem_dc, bitmap, 0, height, buf, ctypes.byref(bmi), 0)

        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(ctypes.c_void_p(hwnd), hwnd_dc)

        return (width, height, buf.raw)


WIN32 = Win32Primitives()


# ==============================================================================
# SECTION 5 — PROVIDERS
# ==============================================================================
class ProviderInterface:
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
    name = "Win32"

    def supports_hwnd(self, hwnd: int) -> bool:
        return True

    def build_node(self, hwnd: int, parent_id: Optional[str]) -> DAPNode:
        tid, pid = WIN32.get_process_thread(hwnd)
        return DAPNode(
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

    def invoke(self, node: DAPNode) -> bool:
        return WIN32.click_button(node.hwnd)

    def set_value(self, node: DAPNode, text: str) -> bool:
        return WIN32.set_window_text(node.hwnd, text)

    def read_value(self, node: DAPNode) -> str:
        return WIN32.get_control_text(node.hwnd)


class UIAProvider(ProviderInterface):
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
        return True

    def set_value(self, node: DAPNode, text: str) -> bool:
        return WIN32.set_window_text(node.hwnd, text)

    def read_value(self, node: DAPNode) -> str:
        return WIN32.get_control_text(node.hwnd)


class ProviderRegistry:
    def __init__(self):
        self.uia = UIAProvider()
        self.win32 = Win32Provider()

    def resolve(self, hwnd: int, class_name: str = "") -> ProviderInterface:
        if self.uia.enabled:
            return self.uia
        return self.win32


# ==============================================================================
# SECTION 6 — TREES & ORCHESTRATION
# ==============================================================================
class WindowTree:
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

    def re_attach(self, node_id: str) -> Optional[DAPNode]:
        node = self._nodes.get(node_id)
        if not node or not WIN32.is_window(node.hwnd):
            return None
        provider = self._providers.resolve(node.hwnd, node.class_name)
        refreshed = provider.build_node(node.hwnd, node.parent_node_id)
        refreshed.node_id = node.node_id
        self._nodes[node.node_id] = refreshed
        return refreshed


class DesktopTree:
    def __init__(self):
        self.monitors: List[Rect] = []

    def rescan(self) -> None:
        self.monitors = []
        if not IS_WINDOWS:
            self.monitors.append(Rect(0, 0, 1920, 1080, 1.0))
            return

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(wintypes.RECT), ctypes.c_double)

        def _cb(_hmon, _hdc, rect_ptr, _data):
            r = rect_ptr.contents
            self.monitors.append(Rect(r.left, r.top, r.right, r.bottom))
            return 1

        user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_cb), 0)


# ==============================================================================
# SECTION 7 — QUERY ENGINE
# ==============================================================================
class QueryEngine:
    def __init__(self, window_tree: WindowTree):
        self._tree = window_tree

    def resolve(self, target: NodeTarget) -> DAPNode:
        if target.node_id:
            node = self._tree.get(target.node_id)
            if not node:
                raise DAPError(DAPErrorCode.ERR_NODE_NOT_FOUND, f"No node with id {target.node_id}")
            return node
        if target.hwnd is not None:
            node = self._tree.get_by_hwnd(target.hwnd)
            if not node:
                raise DAPError(DAPErrorCode.ERR_NODE_NOT_FOUND, f"No node for hwnd {target.hwnd}")
            return node
        if target.selector:
            results = self.query(SelectorQuery("native", target.selector))
            if not results:
                raise DAPError(DAPErrorCode.ERR_NODE_NOT_FOUND, f"Selector matched zero nodes: {target.selector}")
            return results[0]
        raise DAPError(DAPErrorCode.ERR_INVALID_SELECTOR, "Empty NodeTarget supplied")

    def query(self, sq: SelectorQuery) -> List[DAPNode]:
        candidates = list(self._tree.nodes().values())
        return [n for n in candidates if sq.selector.lower() in n.name.lower() or sq.selector.lower() in n.class_name.lower()]


# ==============================================================================
# SECTION 8 — INTERACTION PIPELINE (HARDENED WITH FOCUS AND VISIBILITY GATES)
# ==============================================================================
class FocusOrchestrator:
    def __init__(self):
        self._saved_hwnd: Optional[int] = None

    def lock_and_focus(self, hwnd: int) -> None:
        self._saved_hwnd = WIN32.get_foreground_window()
        current_tid, _ = WIN32.get_process_thread(WIN32.get_foreground_window())
        target_tid, _ = WIN32.get_process_thread(hwnd)
        WIN32.attach_thread_input(current_tid, target_tid, True)
        WIN32.show_window(hwnd, WIN32.SW_RESTORE)
        WIN32.set_foreground_window(hwnd)
        WIN32.attach_thread_input(current_tid, target_tid, False)
        time.sleep(0.05)

    def restore(self) -> None:
        if self._saved_hwnd and WIN32.is_window(self._saved_hwnd):
            WIN32.set_foreground_window(self._saved_hwnd)
            self._saved_hwnd = None


class InputInjector:
    def click(self, x: int, y: int, button: str = "left") -> None:
        WIN32.send_input_click(x, y, button)

    def double_click(self, x: int, y: int) -> None:
        self.click(x, y)
        time.sleep(0.05)
        self.click(x, y)

    def type_text(self, text: str) -> None:
        WIN32.send_unicode_text(text)

    def shortcut(self, sequence: str) -> None:
        keys = [k.strip().lower() for k in sequence.split("+")]
        vks = []
        vk_map = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "enter": 0x0D, "esc": 0x1B, "tab": 0x09}
        for k in keys:
            if k in vk_map:
                vks.append(vk_map[k])
            elif len(k) == 1:
                vks.append(ord(k.upper()))
        for vk in vks:
            WIN32.send_vk(vk, keyup=False)
        for vk in reversed(vks):
            WIN32.send_vk(vk, keyup=True)


class InteractionPipeline:
    def __init__(self, providers: ProviderRegistry):
        self._providers = providers
        self.focus = FocusOrchestrator()
        self.injector = InputInjector()

    def invoke(self, node: DAPNode, force_foreground: bool = True) -> ExecutionResult:
        started = time.time()
        try:
            # Visibility & Focus Pre-Check
            if not WIN32.is_window_visible(node.hwnd):
                WIN32.show_window(node.hwnd, WIN32.SW_RESTORE)

            self.focus.lock_and_focus(node.hwnd)

            # Re-read bounding rect to account for DPI & monitor offsets
            fresh_bounds = WIN32.get_window_rect(node.hwnd)
            cx = (fresh_bounds.left + fresh_bounds.right) // 2
            cy = (fresh_bounds.top + fresh_bounds.bottom) // 2

            self.injector.click(cx, cy)
            self.focus.restore()

            elapsed = (time.time() - started) * 1000
            return ExecutionResult(status="SUCCESS", execution_time_ms=elapsed, background_executed=False,
                                   node_state=node.as_dict())
        except Exception as exc:
            elapsed = (time.time() - started) * 1000
            return ExecutionResult(status="ERROR", execution_time_ms=elapsed, background_executed=False,
                                   error={"message": str(exc)})

    def set_value(self, node: DAPNode, text: str) -> ExecutionResult:
        started = time.time()
        try:
            provider = self._providers.resolve(node.hwnd, node.class_name)
            provider.set_value(node, text)
            elapsed = (time.time() - started) * 1000
            return ExecutionResult(status="SUCCESS", execution_time_ms=elapsed, background_executed=True)
        except Exception as exc:
            elapsed = (time.time() - started) * 1000
            return ExecutionResult(status="ERROR", execution_time_ms=elapsed, background_executed=False,
                                   error={"message": str(exc)})


# ==============================================================================
# SECTION 9 — POPUPS, DIALOGS, CAPTURE
# ==============================================================================
class PopupSubsystem:
    DIALOG_CLASS_HINTS = {"#32770", "Popup", "ModalDialog"}

    def __init__(self, window_tree: WindowTree, interaction: InteractionPipeline):
        self._tree = window_tree
        self._interaction = interaction

    def detect(self, owner_hwnd: int) -> List[DAPNode]:
        return [n for n in self._tree.nodes().values() if n.hwnd != owner_hwnd and n.class_name in self.DIALOG_CLASS_HINTS]


class CaptureEngine:
    def capture(self, node: DAPNode, options: CaptureOptions) -> CaptureResult:
        if not IS_WINDOWS:
            return CaptureResult(status="UNSUPPORTED_PLATFORM", width=0, height=0, format=options.format, payload_base64="")
        width, height, raw_bgra = WIN32.capture_window_bitmap_bytes(node.hwnd)
        import base64
        payload = base64.b64encode(raw_bgra).decode("ascii")
        return CaptureResult(status="SUCCESS", width=width, height=height, format="raw_bgra", payload_base64=payload)


# ==============================================================================
# SECTION 10 — DAP RUNTIME CORE (PUBLIC FACADE)
# ==============================================================================
class DAPRuntimeCore:
    VERSION = "1.0.0-PROD"

    def __init__(self, allowed_host_pids: Optional[List[int]] = None, vision_model_path: Optional[str] = None):
        self.state = StateMachine()
        self.providers = ProviderRegistry()
        self.desktop_tree = DesktopTree()
        self.window_tree = WindowTree(self.providers)
        self.query_engine = QueryEngine(self.window_tree)
        self.interaction = InteractionPipeline(self.providers)
        self.capture = CaptureEngine()
        self.popups = PopupSubsystem(self.window_tree, self.interaction)
        self._initialized = False

    async def initialize(self) -> None:
        self.desktop_tree.rescan()
        self.window_tree.rescan()
        self._initialized = True
        await self.state.transition(RuntimeState.READY)
        LOGGER.info("Organ 24 DAP Runtime initialized.")

    async def shutdown(self) -> None:
        self.window_tree.clear()
        self._initialized = False

    async def window_enumerate(self, include_child_windows: bool = True, process_filter: Optional[List[int]] = None) -> List[dict]:
        self.window_tree.rescan(include_child_windows, process_filter)
        return [n.as_dict() for n in self.window_tree.nodes().values()]

    async def window_focus(self, target: NodeTarget) -> dict:
        node = self.query_engine.resolve(target)
        self.interaction.focus.lock_and_focus(node.hwnd)
        return {"nodeId": node.node_id, "focused": True}

    async def control_invoke(self, target: NodeTarget) -> dict:
        node = self.query_engine.resolve(target)
        res = self.interaction.invoke(node)
        return dataclasses.asdict(res)

    async def control_value(self, target: NodeTarget, text_value: Optional[str] = None) -> dict:
        node = self.query_engine.resolve(target)
        if text_value is None:
            provider = self.providers.resolve(node.hwnd, node.class_name)
            return {"nodeId": node.node_id, "value": provider.read_value(node)}
        res = self.interaction.set_value(node, text_value)
        return dataclasses.asdict(res)

    async def keyboard_type(self, text: str) -> dict:
        self.interaction.injector.type_text(text)
        return {"charsSent": len(text)}

    async def keyboard_shortcut(self, sequence: str) -> dict:
        self.interaction.injector.shortcut(sequence)
        return {"sequence": sequence}

    async def window_capture(self, target: NodeTarget, options: Optional[CaptureOptions] = None) -> dict:
        node = self.query_engine.resolve(target)
        res = self.capture.capture(node, options or CaptureOptions())
        return dataclasses.asdict(res)


class DesktopAutomationProtocol:
    def __init__(self, pipe_name: str = "hojaiga_dap_01"):
        self.core = DAPRuntimeCore()

    async def start(self) -> None:
        await self.core.initialize()

    async def stop(self) -> None:
        await self.core.shutdown()


if __name__ == "__main__":
    async def _demo():
        dap = DAPRuntimeCore()
        await dap.initialize()
        windows = await dap.window_enumerate(include_child_windows=False)
        print(f"DAP Discovered {len(windows)} active windows.")
        await dap.shutdown()

    asyncio.run(_demo())
