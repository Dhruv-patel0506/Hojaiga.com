"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 29
Name: Popup Handler (Desktop Interaction Manager / DIM)

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Popup Handler]
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
Dependencies: numpy, pywinauto, PIL, enum, typing, asyncio, json, logging, time, uuid...
"""
from __future__ import annotations

"""
Organ 29 — Popup Handler (Desktop Interaction Manager / DIM)
Hojaiga Automation OS

Authority: Constitution -> LawBook -> Diagrams -> Legacy Guide -> PolicyManual
           -> MasterArchitectureBlueprint -> Organ_Specification
           -> Popup_Handler_Desktop_Interaction_Manager.md

Responsibility: Discover, classify, track, and resolve non-browser GUI windows
(popups, dialogs, child windows, installer wizards, native file pickers,
security prompts, modal notifications).
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Optional, List, Dict

logger = logging.getLogger("hojaiga.organ29.dim")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[DIM/PopupHandler] %(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)


# ═══════════════════════════════════════════════════════════════════════
# ENUMS / DATA CONTRACTS
# ═══════════════════════════════════════════════════════════════════════
class WindowType(str, Enum):
    MAIN_WINDOW = "main_window"
    CHILD_WINDOW = "child_window"
    MODAL_WINDOW = "modal_window"
    FLOATING_WINDOW = "floating_window"
    TOOL_WINDOW = "tool_window"
    WIZARD = "wizard"
    INSTALLER = "installer"
    MESSAGE_BOX = "message_box"
    CONFIRMATION = "confirmation"
    AUTHENTICATION = "authentication"
    UAC_PROMPT = "uac_prompt"
    SECURITY_PROMPT = "security_prompt"
    CRASH_REPORTER = "crash_reporter"
    PROGRESS_WINDOW = "progress_window"
    SPLASH_SCREEN = "splash_screen"
    NOTIFICATION = "notification"
    TOAST = "toast"
    CONTEXT_MENU = "context_menu"
    TOOLTIP = "tooltip"
    FILE_PICKER = "file_picker"
    FOLDER_PICKER = "folder_picker"
    SAVE_DIALOG = "save_dialog"
    OPEN_DIALOG = "open_dialog"
    LICENSE_AGREEMENT = "license_agreement"
    UNKNOWN = "unknown"


class WindowEvent(str, Enum):
    CREATED = "EVENT_WINDOW_CREATED"
    CLOSED = "EVENT_WINDOW_CLOSED"
    HIDDEN = "EVENT_WINDOW_HIDDEN"
    RESTORED = "EVENT_WINDOW_RESTORED"
    ACTIVATED = "EVENT_WINDOW_ACTIVATED"
    MINIMIZED = "EVENT_WINDOW_MINIMIZED"
    MAXIMIZED = "EVENT_WINDOW_MAXIMIZED"
    TITLE_CHANGED = "EVENT_TITLE_CHANGED"
    FOCUS_CHANGED = "EVENT_FOCUS_CHANGED"
    OWNER_CHANGED = "EVENT_OWNER_CHANGED"
    POPUP_CREATED = "EVENT_POPUP_CREATED"
    DIALOG_CREATED = "EVENT_DIALOG_CREATED"
    WIZARD_CREATED = "EVENT_WIZARD_CREATED"
    TOOLTIP_CREATED = "EVENT_TOOLTIP_CREATED"
    CONTEXT_MENU_OPENED = "EVENT_CONTEXT_MENU_OPENED"


class EngineLayer(int, Enum):
    ACCESSIBILITY = 1
    FRAMEWORK_NATIVE = 2
    OCR = 3
    VISION = 4
    PIXEL_GEOMETRY = 5
    HUMAN_ESCALATION = 6


SECURITY_SENSITIVE_TYPES = frozenset(
    {WindowType.UAC_PROMPT, WindowType.AUTHENTICATION, WindowType.SECURITY_PROMPT}
)

BLOCKING_MODAL_TYPES = frozenset(
    {
        WindowType.MODAL_WINDOW,
        WindowType.MESSAGE_BOX,
        WindowType.CONFIRMATION,
        WindowType.AUTHENTICATION,
        WindowType.UAC_PROMPT,
        WindowType.SECURITY_PROMPT,
        WindowType.CRASH_REPORTER,
        WindowType.LICENSE_AGREEMENT,
    }
)


@dataclass
class WindowRect:
    left: int
    top: int
    right: int
    bottom: int


@dataclass
class WindowNode:
    handle: int
    parent_handle: Optional[int]
    owner_handle: Optional[int]
    process_id: int
    title: str
    class_name: str
    win_type: WindowType
    bounds: WindowRect
    is_visible: bool = True
    has_focus: bool = False
    children: list["WindowNode"] = field(default_factory=list)

    def flatten(self) -> list["WindowNode"]:
        stack: list[WindowNode] = [self]
        out: list[WindowNode] = []
        while stack:
            node = stack.pop()
            out.append(node)
            stack.extend(node.children)
        return out


@dataclass
class FocusState:
    active_control: Optional[int] = None
    active_window: Optional[int] = None
    previous_window: Optional[int] = None
    modal_stack: list[int] = field(default_factory=list)


@dataclass
class SocketMessage:
    request_id: str
    source: str
    destination: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class SocketResponse:
    request_id: str
    status: str
    result: Any = None
    errors: Optional[str] = None
    execution_time_ms: float = 0.0


# ═══════════════════════════════════════════════════════════════════════
# SOCKET REGISTRY & PROTOCOL
# ═══════════════════════════════════════════════════════════════════════
class DIMSocket:
    def __init__(self, name: str, timeout_ms: int, retries: int, version: str = "v1.0"):
        self.name = name
        self.timeout_ms = timeout_ms
        self.retries = retries
        self.version = version
        self._handlers: list[Callable[[SocketMessage], Any]] = []

    def subscribe(self, handler: Callable[[SocketMessage], Any]) -> None:
        self._handlers.append(handler)

    async def send(self, message: SocketMessage) -> SocketResponse:
        start = time.time()
        attempt = 0
        last_error: Optional[str] = None
        while attempt <= self.retries:
            try:
                result = await asyncio.wait_for(
                    self._dispatch(message), timeout=self.timeout_ms / 1000
                )
                return SocketResponse(
                    request_id=message.request_id,
                    status="ok",
                    result=result,
                    execution_time_ms=(time.time() - start) * 1000,
                )
            except asyncio.TimeoutError:
                last_error = f"timeout after {self.timeout_ms}ms"
            except Exception as exc:
                last_error = str(exc)
            attempt += 1
        return SocketResponse(
            request_id=message.request_id,
            status="error",
            errors=last_error,
            execution_time_ms=(time.time() - start) * 1000,
        )

    async def _dispatch(self, message: SocketMessage) -> Any:
        if not self._handlers:
            raise RuntimeError(f"no handler bound for socket {self.name}")
        results = []
        for h in self._handlers:
            res = h(message)
            if asyncio.iscoroutine(res):
                res = await res
            results.append(res)
        return results[-1] if results else None


class SocketRegistry:
    def __init__(self) -> None:
        self.window_discovery = DIMSocket("window_discovery", 500, 3)
        self.popup = DIMSocket("popup", 1000, 3)
        self.dialog = DIMSocket("dialog", 1000, 3)
        self.child_window = DIMSocket("child_window", 500, 2)
        self.modal_window = DIMSocket("modal_window", 1000, 3)
        self.installer = DIMSocket("installer", 5000, 5)
        self.ocr = DIMSocket("ocr", 2000, 2)
        self.vision = DIMSocket("vision", 2000, 2)
        self.accessibility = DIMSocket("accessibility", 500, 3)
        self.focus = DIMSocket("focus", 200, 3)
        self.window_tree = DIMSocket("window_tree", 1000, 2)
        self.window_event = DIMSocket("window_event", 100, 5)
        self.desktop_interaction = DIMSocket("desktop_interaction", 1000, 3)
        self.workflow_pause = DIMSocket("workflow_pause", 200, 5)
        self.workflow_resume = DIMSocket("workflow_resume", 200, 5)
        self.security_prompt = DIMSocket("security_prompt", 5000, 1)
        self.file_picker = DIMSocket("file_picker", 2000, 3)
        self.directory_navigation = DIMSocket("directory_navigation", 1000, 3)
        self.file_search = DIMSocket("file_search", 3000, 2)
        self.file_validation = DIMSocket("file_validation", 500, 2)
        self.file_selection = DIMSocket("file_selection", 1000, 3)
        self.multi_selection = DIMSocket("multi_selection", 2000, 3)
        self.folder_selection = DIMSocket("folder_selection", 1000, 3)
        self.explorer = DIMSocket("explorer", 1000, 3)
        self.upload = DIMSocket("upload", 5000, 3)
        self.download = DIMSocket("download", 5000, 3)


# ═══════════════════════════════════════════════════════════════════════
# WINDOW BACKEND IMPLEMENTATION
# ═══════════════════════════════════════════════════════════════════════
class WindowBackend:
    def enumerate_windows(self) -> list[WindowNode]:
        raise NotImplementedError

    def set_focus(self, handle: int) -> bool:
        raise NotImplementedError

    def click(self, handle: int, x: int, y: int) -> bool:
        raise NotImplementedError

    def send_text(self, handle: int, text: str) -> bool:
        raise NotImplementedError

    def capture_bitmap(self, handle: int) -> bytes:
        raise NotImplementedError


class NullWindowBackend(WindowBackend):
    def enumerate_windows(self) -> list[WindowNode]:
        return []

    def set_focus(self, handle: int) -> bool:
        return True

    def click(self, handle: int, x: int, y: int) -> bool:
        return True

    def send_text(self, handle: int, text: str) -> bool:
        return True

    def capture_bitmap(self, handle: int) -> bytes:
        return b""


try:
    import pywinauto  # type: ignore

    class Win32WindowBackend(WindowBackend):
        def __init__(self) -> None:
            self._desktop = pywinauto.Desktop(backend="uia")

        def enumerate_windows(self) -> list[WindowNode]:
            nodes: list[WindowNode] = []
            for w in self._desktop.windows():
                try:
                    rect = w.rectangle()
                    nodes.append(
                        WindowNode(
                            handle=w.handle,
                            parent_handle=None,
                            owner_handle=None,
                            process_id=w.process_id(),
                            title=w.window_text(),
                            class_name=w.class_name(),
                            win_type=WindowType.UNKNOWN,
                            bounds=WindowRect(rect.left, rect.top, rect.right, rect.bottom),
                            is_visible=w.is_visible(),
                        )
                    )
                except Exception:
                    continue
            return nodes

        def set_focus(self, handle: int) -> bool:
            try:
                pywinauto.Application().connect(handle=handle).top_window().set_focus()
                return True
            except Exception:
                return False

        def click(self, handle: int, x: int, y: int) -> bool:
            try:
                if x > 0 and y > 0:
                    pywinauto.mouse.click(coords=(x, y))
                else:
                    win = pywinauto.Application().connect(handle=handle).top_window()
                    win.click_input()
                return True
            except Exception:
                return False

        def send_text(self, handle: int, text: str) -> bool:
            try:
                pywinauto.keyboard.send_keys(text)
                return True
            except Exception:
                return False

        def capture_bitmap(self, handle: int) -> bytes:
            return b""

    DEFAULT_BACKEND_CLS = Win32WindowBackend
except ImportError:
    DEFAULT_BACKEND_CLS = NullWindowBackend


# ═══════════════════════════════════════════════════════════════════════
# CLASSIFIER & TREE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════
_CLASS_HINTS: dict[str, WindowType] = {
    "#32770": WindowType.MESSAGE_BOX,
    "InnoClass": WindowType.WIZARD,
    "WiX_UI_Bootstrapper": WindowType.WIZARD,
    "InstallShield_Class": WindowType.WIZARD,
    "MsiDialogCloseClass": WindowType.INSTALLER,
    "ConsentUIWindow": WindowType.UAC_PROMPT,
    "CredentialUIWindow": WindowType.AUTHENTICATION,
    "tooltips_class32": WindowType.TOOLTIP,
    "#32768": WindowType.CONTEXT_MENU,
}

_TITLE_HINTS: tuple[tuple[str, WindowType], ...] = (
    ("save as", WindowType.SAVE_DIALOG),
    ("open", WindowType.OPEN_DIALOG),
    ("select folder", WindowType.FOLDER_PICKER),
    ("license agreement", WindowType.LICENSE_AGREEMENT),
    ("user account control", WindowType.UAC_PROMPT),
    ("setup", WindowType.WIZARD),
    ("install", WindowType.INSTALLER),
    ("error", WindowType.MESSAGE_BOX),
    ("warning", WindowType.MESSAGE_BOX),
    ("confirm", WindowType.CONFIRMATION),
)


class WindowClassifier:
    def classify(self, node: WindowNode) -> WindowType:
        if node.class_name in _CLASS_HINTS:
            return _CLASS_HINTS[node.class_name]
        title_lower = node.title.lower()
        for needle, wtype in _TITLE_HINTS:
            if needle in title_lower:
                return wtype
        if node.parent_handle is not None:
            return WindowType.CHILD_WINDOW
        return WindowType.MAIN_WINDOW if node.is_visible and len(node.title) > 0 else WindowType.UNKNOWN


class WindowTreeManager:
    def __init__(self) -> None:
        self._by_handle: dict[int, WindowNode] = {}
        self._roots: list[WindowNode] = []

    def rebuild(self, nodes: list[WindowNode]) -> None:
        self._by_handle = {n.handle: n for n in nodes}
        for n in self._by_handle.values():
            n.children = []
        self._roots = []
        for n in self._by_handle.values():
            parent = self._by_handle.get(n.parent_handle) if n.parent_handle is not None else None
            if parent is not None:
                parent.children.append(n)
            else:
                self._roots.append(n)

    def find(self, handle: int) -> Optional[WindowNode]:
        return self._by_handle.get(handle)

    def roots(self) -> list[WindowNode]:
        return self._roots

    def all_nodes(self) -> list[WindowNode]:
        return list(self._by_handle.values())


class FocusManager:
    def __init__(self, backend: WindowBackend) -> None:
        self._backend = backend
        self.state = FocusState()

    def capture(self, window: int, control: Optional[int] = None) -> None:
        self.state.previous_window = self.state.active_window
        self.state.active_window = window
        self.state.active_control = control

    def push_modal(self, handle: int) -> None:
        self.state.modal_stack.append(handle)

    def pop_modal(self) -> Optional[int]:
        return self.state.modal_stack.pop() if self.state.modal_stack else None

    def set_focus_explicit(self, handle: int, control: Optional[int] = None) -> bool:
        ok = self._backend.set_focus(handle)
        if ok:
            self.capture(handle, control)
        return ok

    def restore_previous(self) -> bool:
        target = self.state.previous_window
        if target is None:
            return False
        ok = self._backend.set_focus(target)
        if ok:
            self.state.active_window = target
            self.state.previous_window = None
        return ok


# ═══════════════════════════════════════════════════════════════════════
# OCR / VISION / SECURITY / INSTALLER / FILE PICKER
# ═══════════════════════════════════════════════════════════════════════
@dataclass
class OCRResult:
    text: str
    confidence: float
    boxes: list[dict[str, Any]] = field(default_factory=list)


class OCREngine:
    def __init__(self, backend: WindowBackend) -> None:
        self._backend = backend

    async def extract(self, handle: int) -> OCRResult:
        bitmap = self._backend.capture_bitmap(handle)
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore
            import io

            if not bitmap:
                return OCRResult(text="", confidence=0.0)
            image = Image.open(io.BytesIO(bitmap))
            text = pytesseract.image_to_string(image)
            return OCRResult(text=text.strip(), confidence=0.85 if text.strip() else 0.0)
        except ImportError:
            return OCRResult(text="", confidence=0.0)


@dataclass
class VisionMatch:
    found: bool
    confidence: float
    x: int = 0
    y: int = 0


class VisionEngine:
    MIN_CONFIDENCE = 0.90

    def __init__(self, backend: WindowBackend) -> None:
        self._backend = backend

    async def match_template(self, handle: int, template_path: str) -> VisionMatch:
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore

            bitmap = self._backend.capture_bitmap(handle)
            if not bitmap:
                return VisionMatch(found=False, confidence=0.0)
            screen = cv2.imdecode(np.frombuffer(bitmap, dtype=np.uint8), cv2.IMREAD_COLOR)
            template = cv2.imread(template_path, cv2.IMREAD_COLOR)
            if screen is None or template is None:
                return VisionMatch(found=False, confidence=0.0)
            result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            h, w = template.shape[:2]
            cx, cy = max_loc[0] + w // 2, max_loc[1] + h // 2
            return VisionMatch(found=max_val >= self.MIN_CONFIDENCE, confidence=max_val, x=cx, y=cy)
        except ImportError:
            return VisionMatch(found=False, confidence=0.0)


class SecurityPolicyGuard:
    def __init__(self, signed_approval_tokens: Optional[set[str]] = None) -> None:
        self._signed_tokens = signed_approval_tokens or set()

    def requires_escalation(self, win_type: WindowType) -> bool:
        return win_type in SECURITY_SENSITIVE_TYPES

    def is_approved(self, win_type: WindowType, approval_token: Optional[str]) -> bool:
        if not self.requires_escalation(win_type):
            return True
        return approval_token is not None and approval_token in self._signed_tokens


class InstallerWizardEngine:
    PAGE_ACTIONS: dict[str, str | None] = {
        "welcome": "Next",
        "license": "Accept",
        "directory": "Next",
        "options": "Next",
        "install": None,
        "progress": None,
        "finish": "Finish",
    }

    def __init__(self, backend: WindowBackend, policy: SecurityPolicyGuard) -> None:
        self._backend = backend
        self._policy = policy

    def detect_page(self, node: WindowNode) -> str:
        title = node.title.lower()
        if "license" in title or "agreement" in title:
            return "license"
        if "directory" in title or "destination" in title or "location" in title:
            return "directory"
        if "finish" in title or "complete" in title:
            return "finish"
        if "progress" in title or "installing" in title:
            return "progress"
        if "ready to install" in title or "install" in title:
            return "install"
        if "options" in title or "components" in title:
            return "options"
        return "welcome"

    async def advance(self, node: WindowNode, target_path: Optional[str] = None) -> Optional[str]:
        page = self.detect_page(node)
        action = self.PAGE_ACTIONS.get(page)
        if page == "directory" and target_path:
            self._backend.send_text(node.handle, target_path)
        if page in ("install", "progress"):
            return None
        if action:
            self._backend.click(node.handle, 0, 0)
        return action


class NativeFilePickerEngine:
    def __init__(self, backend: WindowBackend, tree: WindowTreeManager) -> None:
        self._backend = backend
        self._tree = tree
        self._directory_memory: dict[str, str] = {}

    def detect(self) -> Optional[WindowNode]:
        for node in self._tree.all_nodes():
            if node.win_type in (
                WindowType.FILE_PICKER,
                WindowType.FOLDER_PICKER,
                WindowType.SAVE_DIALOG,
                WindowType.OPEN_DIALOG,
            ):
                return node
        return None

    async def resolve(
        self,
        target_path: str,
        is_save_dialog: bool = False,
        multi_select: bool = False,
        filenames: Optional[list[str]] = None,
    ) -> bool:
        node = self.detect()
        if node is None:
            return False
        payload = target_path
        if multi_select and filenames:
            payload = " ".join(f'"{f}"' for f in filenames)
        ok = self._backend.send_text(node.handle, payload)
        if ok:
            self._directory_memory[node.class_name] = target_path
        self._backend.click(node.handle, 0, 0)
        return ok


class DeadlockGuard:
    def __init__(self, max_wait_seconds: float = 15.0, max_loop_iterations: int = 15) -> None:
        self.max_wait_seconds = max_wait_seconds
        self.max_loop_iterations = max_loop_iterations

    async def wait_until(self, predicate: Callable[[], bool], poll_interval: float = 0.3) -> bool:
        start = time.time()
        iterations = 0
        while time.time() - start < self.max_wait_seconds and iterations < self.max_loop_iterations:
            if predicate():
                return True
            await asyncio.sleep(poll_interval)
            iterations += 1
        return False


# ═══════════════════════════════════════════════════════════════════════
# DESKTOP INTERACTION MANAGER — PUBLIC FACADE & CNS HANDLERS
# ═══════════════════════════════════════════════════════════════════════
class DesktopInteractionManager:
    def __init__(
        self,
        backend: Optional[WindowBackend] = None,
        signed_approval_tokens: Optional[set[str]] = None,
    ) -> None:
        self.backend: WindowBackend = backend or DEFAULT_BACKEND_CLS()
        self.sockets = SocketRegistry()
        self.classifier = WindowClassifier()
        self.tree = WindowTreeManager()
        self.focus = FocusManager(self.backend)
        self.ocr = OCREngine(self.backend)
        self.vision = VisionEngine(self.backend)
        self.security = SecurityPolicyGuard(signed_approval_tokens)
        self.installer = InstallerWizardEngine(self.backend, self.security)
        self.nfpe = NativeFilePickerEngine(self.backend, self.tree)
        self.deadlock_guard = DeadlockGuard()
        self._bind_sockets()
        self.cns: Optional[Any] = None

    def _bind_sockets(self) -> None:
        self.sockets.window_discovery.subscribe(self._handle_discovery_request)
        self.sockets.popup.subscribe(self._handle_popup_request)
        self.sockets.window_tree.subscribe(self._handle_tree_request)
        self.sockets.focus.subscribe(self._handle_focus_request)
        self.sockets.file_picker.subscribe(self._handle_file_picker_request)
        self.sockets.installer.subscribe(self._handle_installer_request)
        self.sockets.security_prompt.subscribe(self._handle_security_request)

    def refresh(self) -> list[WindowNode]:
        nodes = self.backend.enumerate_windows()
        for n in nodes:
            n.win_type = self.classifier.classify(n)
        self.tree.rebuild(nodes)
        return nodes

    async def intercept_popup(self, node: WindowNode, approval_token: Optional[str] = None) -> bool:
        request_id = str(uuid.uuid4())
        logger.info("Popup detected: handle=%s type=%s", node.handle, node.win_type)

        text_result = await self._read_with_fallback(node)

        if self.security.requires_escalation(node.win_type):
            approved = self.security.is_approved(node.win_type, approval_token)
            if not approved:
                logger.warning("Security prompt requires operator approval: %s", node.handle)
                return False

        self.focus.push_modal(node.handle)

        if node.win_type in (WindowType.WIZARD, WindowType.INSTALLER):
            await self.installer.advance(node)
        elif node.win_type in (
            WindowType.FILE_PICKER, WindowType.FOLDER_PICKER,
            WindowType.SAVE_DIALOG, WindowType.OPEN_DIALOG,
        ):
            pass
        else:
            logger.info("Resolving modal/dialog window %s...", node.handle)
            self.backend.click(node.handle, 0, 0)

        closed = await self.deadlock_guard.wait_until(
            lambda: self.tree.find(node.handle) is None
        )
        self.focus.pop_modal()
        self.focus.restore_previous()
        return closed

    async def _read_with_fallback(self, node: WindowNode) -> dict[str, Any]:
        if node.title:
            return {"layer": EngineLayer.ACCESSIBILITY.name, "text": node.title}
        ocr_result = await self.ocr.extract(node.handle)
        if ocr_result.text:
            return {"layer": EngineLayer.OCR.name, "text": ocr_result.text}
        return {"layer": EngineLayer.HUMAN_ESCALATION.name, "text": ""}

    # ── Socket Handlers ──────────────────────────────────────────────

    async def _handle_discovery_request(self, message: SocketMessage) -> list[dict[str, Any]]:
        nodes = self.refresh()
        return [self._node_to_dict(n) for n in nodes]

    async def _handle_popup_request(self, message: SocketMessage) -> bool:
        handle = message.payload.get("handle")
        if handle is None:
            return False
        node = self.tree.find(handle)
        if node is None:
            return False
        token = message.payload.get("approval_token")
        return await self.intercept_popup(node, token)

    async def _handle_tree_request(self, message: SocketMessage) -> list[dict[str, Any]]:
        return [self._node_to_dict(n) for n in self.tree.roots()]

    async def _handle_focus_request(self, message: SocketMessage) -> bool:
        handle = message.payload.get("handle")
        return self.focus.set_focus_explicit(handle) if handle is not None else False

    async def _handle_file_picker_request(self, message: SocketMessage) -> bool:
        return await self.nfpe.resolve(
            target_path=message.payload.get("target_path", ""),
            is_save_dialog=message.payload.get("is_save_dialog", False),
            multi_select=message.payload.get("multi_select", False),
            filenames=message.payload.get("filenames"),
        )

    async def _handle_installer_request(self, message: SocketMessage) -> Optional[str]:
        handle = message.payload.get("handle")
        if handle is None:
            return None
        node = self.tree.find(handle)
        if node is None:
            return None
        return await self.installer.advance(node, message.payload.get("target_path"))

    async def _handle_security_request(self, message: SocketMessage) -> bool:
        win_type = WindowType(message.payload.get("win_type", WindowType.UNKNOWN.value))
        token = message.payload.get("approval_token")
        return self.security.is_approved(win_type, token)

    @staticmethod
    def _node_to_dict(node: WindowNode) -> dict[str, Any]:
        d = asdict(node)
        d.pop("children", None)
        return d

    # ── CNS Integration (Real Window Stack Inspection) ──────────────────

    async def start_cns(self, cns: Any) -> None:
        self.cns = cns
        await self.cns.subscribe("SCAN_COMPLETED", "organ_29_dim", self._handle_scan_for_popups)
        logger.info("DesktopInteractionManager registered to CNS EventBus.")

    async def _handle_scan_for_popups(self, env: Any) -> None:
        from core_organs.organ_02_cns_single_file import EventEnvelope
        payload = env.payload or {}
        task_id = payload.get("task_id", "UNKNOWN")

        # Refresh live desktop window stack
        nodes = self.refresh()
        blocking_popups = [n for n in nodes if n.win_type in BLOCKING_MODAL_TYPES and n.is_visible]

        all_resolved = True
        for popup in blocking_popups:
            logger.info(f"Detected blocking modal dialog '{popup.title}' ({popup.win_type.value}). Attempting resolution...")
            resolved = await self.intercept_popup(popup)
            if not resolved:
                all_resolved = False

        if self.cns:
            await self.cns.publish(EventEnvelope(
                topic="POPUP_RESOLVED",
                source_organ="organ_29",
                payload={"task_id": task_id, "resolved": all_resolved, "popups_handled": len(blocking_popups)}
            ))


if __name__ == "__main__":
    dim = DesktopInteractionManager()
    windows = dim.refresh()
    print(f"Organ 29 initialized. Found {len(windows)} active desktop windows.")
