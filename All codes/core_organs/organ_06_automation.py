"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 6
Name: Automation

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Automation]
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
Dependencies: enum, pathlib, __future__, typing, playwright.async_api...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_06_automation.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Hojaiga Automation OS — Organ 06: Automation
Single-file production implementation.
Complies with: Constitution, Law Book (Universal Laws 3,6,7,8; Foundational
Laws 4,5,9,11), Policy Manual, Organ Specification, Organ_06_Automation.md.

Execution only — no planning/reasoning embedded (Diagram 4, Upper Surface).
Optional deps: playwright (browser), pywin32/pyperclip (Windows desktop/clipboard).
Organ degrades gracefully if optional deps are absent.
"""


import asyncio
import json
import logging
import os
import struct
import time
import uuid
import ctypes
import math
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

LOG = logging.getLogger("hojaiga.organ06.automation")
LOG.setLevel(logging.INFO)
if not LOG.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] organ06: %(message)s"))
    LOG.addHandler(_h)

PIPE_NAME = r"\\.\pipe\hojaiga_automation" if os.name == "nt" else "/tmp/hojaiga_automation.sock"
MAX_FRAME_BYTES = 8 * 1024 * 1024
HEADER_FMT = "!IH"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

try:
    import pyperclip
    _CLIPBOARD_AVAILABLE = True
except ImportError:
    _CLIPBOARD_AVAILABLE = False

try:
    import win32gui
    import win32process
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False


# ───────────────────────────── Op Codes ─────────────────────────────

class OpCode(int, Enum):
    SUBMIT_TASK = 1
    GET_TASK_STATUS = 2
    CANCEL_TASK = 3
    GET_REPORT = 4
    ACK = 100
    ERROR = 999


# ───────────────────────────── State Enums ─────────────────────────────

class TaskState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    RETRYING = "RETRYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


class RuntimeState(str, Enum):
    IDLE = "IDLE"
    LAUNCHING = "LAUNCHING"
    READY = "READY"
    BUSY = "BUSY"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    DEGRADED = "DEGRADED"


# ───────────────────────────── Data Contracts ─────────────────────────────

@dataclass
class TaskRequest:
    capability: str              # e.g. "browser.navigate", "browser.download",
                                  # "desktop.focus_window", "clipboard.write"
    target: str                  # url / window title / file path / text
    runtime: str = "browser"     # "browser" | "desktop" | "clipboard"
    params: Dict[str, Any] = field(default_factory=dict)
    max_retries: int = 3
    timeout_s: float = 30.0
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class TaskResult:
    task_id: str
    state: TaskState
    result: Any = None
    error: Optional[str] = None
    attempts: int = 0
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


# ───────────────────────────── Retry Manager ─────────────────────────────

class RetryManager:
    """Universal Law 8: Failure Transparency and Recovery."""

    def __init__(self, base_delay_s: float = 0.5, max_delay_s: float = 8.0):
        self._base = base_delay_s
        self._max = max_delay_s

    def delay_for(self, attempt: int) -> float:
        return min(self._max, self._base * (2 ** max(0, attempt - 1)))

    async def run(self, fn: Callable[[], Any], max_retries: int,
                   task_id: str) -> TaskResult:
        started = time.time()
        last_error: Optional[str] = None
        for attempt in range(1, max_retries + 1):
            try:
                result = await fn()
                return TaskResult(
                    task_id=task_id, state=TaskState.SUCCEEDED, result=result,
                    attempts=attempt, duration_ms=(time.time() - started) * 1000,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
                LOG.warning("Task %s attempt %d failed: %s", task_id, attempt, last_error)
                if attempt < max_retries:
                    await asyncio.sleep(self.delay_for(attempt))
        return TaskResult(
            task_id=task_id, state=TaskState.FAILED, error=last_error,
            attempts=max_retries, duration_ms=(time.time() - started) * 1000,
        )


# ───────────────────────────── Browser Manager ─────────────────────────────

class BrowserManager:
    """Playwright + CDP lifecycle owner."""

    def __init__(self, headless: bool = False, downloads_dir: Optional[Path] = None):
        self.state = RuntimeState.IDLE
        self._headless = headless
        self._downloads_dir = downloads_dir or Path("./data/organ_06/downloads")
        self._downloads_dir.mkdir(parents=True, exist_ok=True)
        self._pw = None
        self._browser: Optional["Browser"] = None
        self._context: Optional["BrowserContext"] = None
        self._pages: Dict[str, "Page"] = {}

    async def launch(self) -> None:
        if not _PLAYWRIGHT_AVAILABLE:
            self.state = RuntimeState.DEGRADED
            raise RuntimeError("playwright not installed")
        self.state = RuntimeState.LAUNCHING
        self._pw = await async_playwright().start()  # type: ignore
        self._browser = await self._pw.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context(
            accept_downloads=True,
        )
        self.state = RuntimeState.READY
        LOG.info("Browser runtime launched (headless=%s)", self._headless)

    async def ensure_ready(self) -> None:
        if self.state not in (RuntimeState.READY, RuntimeState.BUSY):
            await self.launch()

    async def new_page(self, tab_id: Optional[str] = None) -> str:
        await self.ensure_ready()
        page = await self._context.new_page()  # type: ignore
        tab_id = tab_id or str(uuid.uuid4())
        self._pages[tab_id] = page
        return tab_id

    def _page(self, tab_id: Optional[str]) -> "Page":
        if tab_id and tab_id in self._pages:
            return self._pages[tab_id]
        if self._pages:
            return next(iter(self._pages.values()))
        raise RuntimeError("no active page")

    async def navigate(self, url: str, tab_id: Optional[str] = None) -> Dict[str, Any]:
        await self.ensure_ready()
        self.state = RuntimeState.BUSY
        if not tab_id or tab_id not in self._pages:
            tab_id = await self.new_page(tab_id)
        page = self._page(tab_id)
        await page.goto(url, wait_until="domcontentloaded")
        self.state = RuntimeState.READY
        return {"tab_id": tab_id, "url": page.url, "title": await page.title()}

    async def click(self, selector: str, tab_id: Optional[str] = None) -> Dict[str, Any]:
        page = self._page(tab_id)
        await page.click(selector, timeout=10_000)
        return {"clicked": selector}

    async def fill(self, selector: str, value: str, tab_id: Optional[str] = None) -> Dict[str, Any]:
        page = self._page(tab_id)
        await page.fill(selector, value, timeout=10_000)
        return {"filled": selector}

    async def download(self, trigger_selector: str, tab_id: Optional[str] = None) -> Dict[str, Any]:
        page = self._page(tab_id)
        async with page.expect_download() as dl_info:
            await page.click(trigger_selector)
        download = await dl_info.value
        dest = self._downloads_dir / download.suggested_filename
        await download.save_as(str(dest))
        return {"path": str(dest), "url": download.url}

    async def upload(self, selector: str, file_path: str, tab_id: Optional[str] = None) -> Dict[str, Any]:
        page = self._page(tab_id)
        await page.set_input_files(selector, file_path, timeout=10_000)
        return {"uploaded": file_path, "selector": selector}

    async def evaluate_js(self, script: str, tab_id: Optional[str] = None) -> Any:
        page = self._page(tab_id)
        return await page.evaluate(script)

    async def close_tab(self, tab_id: str) -> None:
        page = self._pages.pop(tab_id, None)
        if page:
            await page.close()

    async def shutdown(self) -> None:
        self.state = RuntimeState.SHUTTING_DOWN
        for page in list(self._pages.values()):
            await page.close()
        self._pages.clear()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self.state = RuntimeState.IDLE
        LOG.info("Browser runtime shut down; GPU/CPU resources released")


# ───────────────────────────── Window Manager (Desktop) ─────────────────────────────

@dataclass
class WindowInfo:
    hwnd: int
    title: str
    pid: int
    is_visible: bool


class WindowManager:
    """Main/child/popup window classification. Windows-only via pywin32;
    degrades to a no-op stub on unsupported platforms (Foundational Law 9:
    Environment Awareness)."""

    def __init__(self):
        self.available = _WIN32_AVAILABLE

    def enumerate_windows(self) -> List[WindowInfo]:
        if not self.available:
            LOG.warning("WindowManager unavailable on this platform (no pywin32)")
            return []
        results: List[WindowInfo] = []

        def _cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):  # type: ignore
                _, pid = win32process.GetWindowThreadProcessId(hwnd)  # type: ignore
                results.append(WindowInfo(
                    hwnd=hwnd, title=win32gui.GetWindowText(hwnd),  # type: ignore
                    pid=pid, is_visible=True,
                ))
            return True

        win32gui.EnumWindows(_cb, None)  # type: ignore
        return results

    def find_by_title(self, title_substr: str) -> Optional[WindowInfo]:
        for w in self.enumerate_windows():
            if title_substr.lower() in w.title.lower():
                return w
        return None

    def focus(self, hwnd: int) -> bool:
        if not self.available:
            return False
        try:
            win32gui.SetForegroundWindow(hwnd)  # type: ignore
            return True
        except Exception:  # noqa: BLE001
            LOG.exception("focus() failed for hwnd=%s", hwnd)
            return False

    def find_child_windows(self, parent_hwnd: int) -> List[WindowInfo]:
        if not self.available:
            return []
        children: List[WindowInfo] = []

        def _cb(hwnd, _):
            if win32gui.GetWindowText(hwnd):  # type: ignore
                _, pid = win32process.GetWindowThreadProcessId(hwnd)  # type: ignore
                children.append(WindowInfo(
                    hwnd=hwnd, title=win32gui.GetWindowText(hwnd),  # type: ignore
                    pid=pid, is_visible=win32gui.IsWindowVisible(hwnd),  # type: ignore
                ))
            return True

        win32gui.EnumChildWindows(parent_hwnd, _cb, None)  # type: ignore
        return children


# ───────────────────────────── GUI Manager (Desktop Runtime) ─────────────────────────────

class GUIManager:
    """Desktop session orchestration on top of WindowManager (Diagram 9:
    Windows GUI Automation)."""

    def __init__(self, window_manager: WindowManager):
        self.state = RuntimeState.IDLE
        self._wm = window_manager

    async def focus_window(self, title_substr: str) -> Dict[str, Any]:
        self.state = RuntimeState.BUSY
        win = self._wm.find_by_title(title_substr)
        if not win:
            self.state = RuntimeState.READY
            raise RuntimeError(f"window not found: {title_substr}")
        ok = self._wm.focus(win.hwnd)
        self.state = RuntimeState.READY
        return {"hwnd": win.hwnd, "title": win.title, "focused": ok}

    async def list_child_windows(self, title_substr: str) -> List[Dict[str, Any]]:
        win = self._wm.find_by_title(title_substr)
        if not win:
            raise RuntimeError(f"window not found: {title_substr}")
        return [asdict(c) for c in self._wm.find_child_windows(win.hwnd)]


# ───────────────────────────── Clipboard Manager ─────────────────────────────

class ClipboardManager:
    def __init__(self):
        self.available = _CLIPBOARD_AVAILABLE

    async def write(self, text: str) -> Dict[str, Any]:
        if not self.available:
            raise RuntimeError("clipboard backend unavailable (pyperclip missing)")
        pyperclip.copy(text)  # type: ignore
        return {"written_chars": len(text)}

    async def read(self) -> Dict[str, Any]:
        if not self.available:
            raise RuntimeError("clipboard backend unavailable (pyperclip missing)")
        return {"text": pyperclip.paste()}  # type: ignore


# ───────────────────────────── MultiTouch 3D Physics ─────────────────────────────

class MultiTouch_3D_Physics_Engine:
    """Virtual HID hooks to simulate multi-point touch events and 3D rotation."""
    
    def __init__(self):
        self._user32 = ctypes.windll.user32 if os.name == 'nt' else None

    # The hardware-event implementations (mouse_event / keybd_event) were DELETED (backlog 1.1): they moved the user's real
    # pointer and keyboard. A viewport gesture needs a TARGET window and posted messages (headless_input.post_scroll /
    # post_drag); without one there is nothing safe to do, so the honest answer is a refusal, never a guess.
    _REFUSED = {"error": "physical input removed (product law); use headless_input.post_scroll/post_drag with a target window",
                "delivered": False}

    async def scroll(self, amount: int) -> Dict[str, Any]:
        """Basic 2D scrolling: refused (no target window to post to)."""
        return dict(self._REFUSED, action="scroll", amount=amount)

    async def zoom(self, factor: float) -> Dict[str, Any]:
        """Basic Zoom (Ctrl+Scroll): refused (no target window to post to)."""
        return dict(self._REFUSED, action="zoom", factor=factor)

    async def rotate_3d_object(self, yaw: float, pitch: float, roll: float) -> Dict[str, Any]:
        """Maps 3D rotation vectors to drag offsets. Refused here; the offsets are still reported so a caller with a window
        can deliver them through headless_input.post_drag."""
        dx = int(math.sin(yaw) * 100)
        dy = int(math.sin(pitch) * 100)
        return dict(self._REFUSED, action="3d_rotate", dx=dx, dy=dy)


# ───────────────────────────── Task Engine (Orchestrator) ─────────────────────────────

class TaskEngine:
    def __init__(self, browser: BrowserManager, gui: GUIManager,
                 clipboard: ClipboardManager, retry: RetryManager, 
                 physics: MultiTouch_3D_Physics_Engine):
        self.browser = browser
        self.gui = gui
        self.clipboard = clipboard
        self.retry = retry
        self.physics = physics
        self._tasks: Dict[str, TaskResult] = {}
        self._cancelled: set[str] = set()
        self._listeners: List[Callable[[str, Dict[str, Any]], None]] = []

    def on_event(self, cb: Callable[[str, Dict[str, Any]], None]) -> None:
        self._listeners.append(cb)

    def _emit(self, name: str, payload: Dict[str, Any]) -> None:
        for cb in self._listeners:
            try:
                cb(name, payload)
            except Exception:  # noqa: BLE001
                LOG.exception("listener failed for %s", name)

    async def submit(self, req: TaskRequest) -> TaskResult:
        self._tasks[req.task_id] = TaskResult(task_id=req.task_id, state=TaskState.QUEUED)
        handler = self._route(req)

        async def _bounded():
            if req.task_id in self._cancelled:
                raise RuntimeError("task cancelled")
            return await asyncio.wait_for(handler(), timeout=req.timeout_s)

        self._tasks[req.task_id] = TaskResult(task_id=req.task_id, state=TaskState.RUNNING)
        result = await self.retry.run(_bounded, req.max_retries, req.task_id)
        if req.task_id in self._cancelled and result.state != TaskState.SUCCEEDED:
            result.state = TaskState.ESCALATED
            result.error = "cancelled_by_user"
        self._tasks[req.task_id] = result
        self._emit("EVENT_TASK_COMPLETE", asdict(result))
        return result

    def _route(self, req: TaskRequest) -> Callable[[], Any]:
        cap = req.capability

        async def browser_navigate():
            return await self.browser.navigate(req.target, req.params.get("tab_id"))

        async def browser_click():
            return await self.browser.click(req.target, req.params.get("tab_id"))

        async def browser_fill():
            return await self.browser.fill(req.target, req.params.get("value", ""),
                                            req.params.get("tab_id"))

        async def browser_download():
            return await self.browser.download(req.target, req.params.get("tab_id"))

        async def browser_upload():
            return await self.browser.upload(req.target, req.params.get("file_path", ""),
                                              req.params.get("tab_id"))

        async def browser_js():
            return await self.browser.evaluate_js(req.target, req.params.get("tab_id"))

        async def desktop_focus():
            return await self.gui.focus_window(req.target)

        async def desktop_children():
            return await self.gui.list_child_windows(req.target)

        async def clipboard_write():
            return await self.clipboard.write(req.target)

        async def clipboard_read():
            return await self.clipboard.read()

        async def physics_scroll():
            return await self.physics.scroll(req.params.get("amount", 100))

        async def physics_zoom():
            return await self.physics.zoom(req.params.get("factor", 1.0))

        async def physics_rotate():
            return await self.physics.rotate_3d_object(
                req.params.get("yaw", 0.0),
                req.params.get("pitch", 0.0),
                req.params.get("roll", 0.0)
            )

        table = {
            "browser.navigate": browser_navigate,
            "browser.click": browser_click,
            "browser.fill": browser_fill,
            "browser.download": browser_download,
            "browser.upload": browser_upload,
            "browser.evaluate_js": browser_js,
            "desktop.focus_window": desktop_focus,
            "desktop.list_children": desktop_children,
            "clipboard.write": clipboard_write,
            "clipboard.read": clipboard_read,
            "physics.scroll": physics_scroll,
            "physics.zoom": physics_zoom,
            "physics.rotate": physics_rotate,
        }
        if cap not in table:
            async def _unknown():
                raise RuntimeError(f"unknown capability: {cap}")
            return _unknown
        return table[cap]

    def status(self, task_id: str) -> Optional[TaskResult]:
        return self._tasks.get(task_id)

    def cancel(self, task_id: str) -> bool:
        self._cancelled.add(task_id)
        return True

    def report(self, since_ts: float = 0.0) -> Dict[str, Any]:
        return {
            "tasks": [asdict(t) for t in self._tasks.values() if t.timestamp >= since_ts],
            "browser_state": self.browser.state.value,
            "gui_state": self.gui.state.value,
        }

    async def shutdown(self) -> None:
        await self.browser.shutdown()


# ───────────────────────────── IPC Framing ─────────────────────────────

def encode_frame(op_code: OpCode, payload: Dict[str, Any]) -> bytes:
    body = json.dumps(payload, default=str).encode("utf-8")
    if len(body) > MAX_FRAME_BYTES:
        raise ValueError("frame exceeds max payload size")
    return struct.pack(HEADER_FMT, len(body), int(op_code)) + body


async def read_frame(reader: asyncio.StreamReader) -> Optional[tuple[OpCode, Dict[str, Any]]]:
    header = await reader.readexactly(HEADER_SIZE)
    length, op_code = struct.unpack(HEADER_FMT, header)
    if length > MAX_FRAME_BYTES:
        raise ValueError("incoming frame too large")
    body = await reader.readexactly(length)
    return OpCode(op_code), json.loads(body.decode("utf-8"))


# ───────────────────────────── IPC Server ─────────────────────────────

class AutomationIPCServer:
    def __init__(self, engine: TaskEngine, path: str = PIPE_NAME):
        self._engine = engine
        self._path = path
        self._server: Optional[asyncio.AbstractServer] = None

    async def start(self) -> None:
        if os.name == "nt":
            LOG.info("Named Pipe IPC not natively supported by asyncio on Windows; "
                     "run via TCP loopback fallback on 127.0.0.1:47060.")
            self._server = await asyncio.start_server(self._handle, "127.0.0.1", 47060)
        else:
            if os.path.exists(self._path):
                os.remove(self._path)
            self._server = await asyncio.start_unix_server(self._handle, path=self._path)
        LOG.info("Automation IPC server listening at %s", self._path)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername", "local")
        LOG.info("Client connected: %s", peer)
        try:
            while True:
                frame = await read_frame(reader)
                if frame is None:
                    break
                op_code, payload = frame
                response = await self._dispatch(op_code, payload)
                writer.write(response)
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        except Exception:
            LOG.exception("IPC handler error")
            writer.write(encode_frame(OpCode.ERROR, {"error": "internal_error"}))
            await writer.drain()
        finally:
            writer.close()

    async def _dispatch(self, op_code: OpCode, payload: Dict[str, Any]) -> bytes:
        if op_code == OpCode.SUBMIT_TASK:
            req = TaskRequest(**payload)
            result = await self._engine.submit(req)
            return encode_frame(OpCode.ACK, asdict(result))

        if op_code == OpCode.GET_TASK_STATUS:
            result = self._engine.status(payload["task_id"])
            if result is None:
                return encode_frame(OpCode.ERROR, {"error": "task_not_found"})
            return encode_frame(OpCode.ACK, asdict(result))

        if op_code == OpCode.CANCEL_TASK:
            ok = self._engine.cancel(payload["task_id"])
            return encode_frame(OpCode.ACK, {"cancelled": ok})

        if op_code == OpCode.GET_REPORT:
            return encode_frame(OpCode.ACK, self._engine.report(payload.get("since_ts", 0.0)))

        return encode_frame(OpCode.ERROR, {"error": "unknown_op_code"})

    def close(self) -> None:
        if self._server:
            self._server.close()


# ───────────────────────────── Entrypoint ─────────────────────────────

async def main() -> None:
    data_dir = Path(os.environ.get("HOJAIGA_AUTOMATION_DATA", "./data/organ_06"))
    browser = BrowserManager(headless=False, downloads_dir=data_dir / "downloads")
    window_manager = WindowManager()
    gui = GUIManager(window_manager)
    clipboard = ClipboardManager()
    retry = RetryManager()
    physics = MultiTouch_3D_Physics_Engine()
    engine = TaskEngine(browser, gui, clipboard, retry, physics)
    engine.on_event(lambda name, payload: LOG.info("EVENT %s %s", name, payload))

    server = AutomationIPCServer(engine)
    await server.start()

    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        await engine.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        LOG.info("Automation Organ shutdown requested.")
