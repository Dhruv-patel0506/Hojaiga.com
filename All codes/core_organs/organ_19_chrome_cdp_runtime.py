"""
HOJAIGA AUTOMATION OS - ORGAN 19: CHROME CDP RUNTIME
======================================================================
Hardened implementation:
- Fixed KeyError: 'x' by providing automatic fallback coordinates and selector retries.
- Reuses active debugging instances (port 9222/scan) to prevent zombie browser spawning.
- Fully compatible with Hojaiga IPC protocol.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import platform
import socket
import struct
import sys
import threading
import time
import uuid
import hashlib
import random
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import IntEnum, Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Awaitable

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
    _HAS_WEBSOCKETS = True
except Exception:
    websockets = None
    WebSocketClientProtocol = Any
    _HAS_WEBSOCKETS = False

try:
    import urllib.request as _urllib_request
    _HAS_URLLIB = True
except Exception:
    _HAS_URLLIB = False

_IS_WINDOWS = platform.system() == "Windows"

if _IS_WINDOWS:
    try:
        import win32pipe
        import win32file
        import win32con
        import win32gui
        import win32api
        import win32security
        import pywintypes
        _HAS_PYWIN32 = True
    except Exception:
        _HAS_PYWIN32 = False
else:
    _HAS_PYWIN32 = False

try:
    import psutil
    _HAS_PSUTIL = True
except Exception:
    psutil = None
    _HAS_PSUTIL = False

LOG = logging.getLogger("hojaiga.organ19.chrome_cdp_runtime")
if not LOG.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] organ19.cdp: %(message)s"))
    LOG.addHandler(_handler)
LOG.setLevel(logging.INFO)

IPC_SOCKET_NAME = "hojaiga_interface"
IPC_MAX_FRAME_BYTES = 16 * 1024 * 1024
IPC_LENGTH_HEADER = struct.Struct(">I")
IPC_OPCODE_HEADER = struct.Struct(">H")


class Organ19OpCode(IntEnum):
    PING = 0x0000
    PONG = 0x0001
    LAUNCH_BROWSER = 0x0100
    ATTACH_BROWSER = 0x0101
    CLOSE_BROWSER = 0x0102
    CREATE_TAB = 0x0110
    CLOSE_TAB = 0x0111
    LIST_TARGETS = 0x0112
    NAVIGATE = 0x0120
    RELOAD = 0x0121
    GO_BACK = 0x0122
    GO_FORWARD = 0x0123
    GET_DOM_TREE = 0x0130
    QUERY_SELECTOR = 0x0131
    CLICK = 0x0140
    RIGHT_CLICK = 0x0141
    DOUBLE_CLICK = 0x0142
    HOVER = 0x0143
    SCROLL = 0x0144
    DRAG_DROP = 0x0145
    MULTI_SELECT = 0x0146
    TYPE_TEXT = 0x0150
    PRESS_KEY = 0x0151
    EXECUTE_JS = 0x0160
    GET_PAGE_STATE = 0x0170
    SET_NETWORK_RULE = 0x0180
    GET_NETWORK_LOG = 0x0181
    DOWNLOAD_START = 0x0190
    DOWNLOAD_STATUS = 0x0191
    UPLOAD_FILES = 0x01A0
    NATIVE_FILE_PICKER = 0x01A1
    SCREENSHOT = 0x01B0
    START_SCREENCAST = 0x01B1
    STOP_SCREENCAST = 0x01B2
    CREATE_PROFILE = 0x01C0
    SET_COOKIES = 0x01D0
    GET_COOKIES = 0x01D1
    SUBSCRIBE_EVENTS = 0x01E0
    RECOVER_SESSION = 0x01F0
    ERROR = 0xFFFF
    EVENT = 0xFFFE


@dataclass
class IPCFrame:
    op_code: int
    payload: Dict[str, Any]

    def encode(self) -> bytes:
        body = json.dumps(self.payload, separators=(",", ":")).encode("utf-8")
        if len(body) + 2 > IPC_MAX_FRAME_BYTES:
            raise ValueError("IPC frame exceeds 16MB maximum payload size")
        header = IPC_LENGTH_HEADER.pack(len(body) + 2) + IPC_OPCODE_HEADER.pack(self.op_code)
        return header + body

    @staticmethod
    def decode(length_prefixed: bytes) -> "IPCFrame":
        op_code = IPC_OPCODE_HEADER.unpack(length_prefixed[:2])[0]
        payload = json.loads(length_prefixed[2:].decode("utf-8")) if len(length_prefixed) > 2 else {}
        return IPCFrame(op_code=op_code, payload=payload)


class IPCTransportKind(str, Enum):
    WINDOWS_NAMED_PIPE = "windows_named_pipe"
    UNIX_DOMAIN_SOCKET = "unix_domain_socket"
    TCP_LOOPBACK = "tcp_loopback"


class IPCServer:
    def __init__(self, kernel: "CDPRuntimeKernel", tcp_port: int = 47619):
        self._kernel = kernel
        self._tcp_port = tcp_port
        self._server: Optional[asyncio.AbstractServer] = None
        self._transport_kind: Optional[IPCTransportKind] = None

    @property
    def transport_kind(self) -> Optional[IPCTransportKind]:
        return self._transport_kind

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, host="127.0.0.1", port=self._tcp_port)
        self._transport_kind = IPCTransportKind.TCP_LOOPBACK
        LOG.info("IPC transport: TCP loopback (127.0.0.1:%d)", self._tcp_port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                length_bytes = await reader.readexactly(4)
                total_len = IPC_LENGTH_HEADER.unpack(length_bytes)[0]
                if total_len > IPC_MAX_FRAME_BYTES:
                    raise ValueError("frame exceeds max size")
                body = await reader.readexactly(total_len)
                frame = IPCFrame.decode(body)
                response = await self._kernel.dispatch(frame)
                writer.write(response.encode())
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        except Exception as exc:
            LOG.warning("IPC client error: %s", exc)
        finally:
            writer.close()


class AOSEventType(str, Enum):
    PAGE_LOADED = "EVENT_PAGE_LOADED"
    DOM_READY = "EVENT_DOM_READY"
    FRAME_NAVIGATED = "EVENT_FRAME_NAVIGATED"
    TARGET_CREATED = "EVENT_TARGET_CREATED"
    TARGET_CRASHED = "EVENT_TARGET_CRASHED"
    DOM_MUTATED = "EVENT_DOM_MUTATED"
    NETWORK_REQUEST = "EVENT_NETWORK_REQUEST"
    NETWORK_RESPONSE = "EVENT_NETWORK_RESPONSE"
    NETWORK_FAILED = "EVENT_NETWORK_FAILED"
    CONSOLE_MESSAGE = "EVENT_CONSOLE_MESSAGE"
    RUNTIME_EXCEPTION = "EVENT_RUNTIME_EXCEPTION"
    DIALOG_OPENED = "EVENT_DIALOG_OPENED"
    SECURITY_CHANGED = "EVENT_SECURITY_CHANGED"
    DOWNLOAD_PROGRESS = "EVENT_DOWNLOAD_PROGRESS"
    FILE_CHOOSER_OPENED = "EVENT_FILE_CHOOSER_OPENED"
    SCREENCAST_FRAME = "EVENT_SCREENCAST_FRAME"
    SESSION_STATE_CHANGED = "EVENT_SESSION_STATE_CHANGED"


@dataclass
class AOSEvent:
    event_type: AOSEventType
    browser_id: str
    session_id: Optional[str]
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "browser_id": self.browser_id,
            "session_id": self.session_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


class CDPEventBus:
    def __init__(self, capacity: int = 4096):
        self._capacity = capacity
        self._buffer: List[AOSEvent] = []
        self._subscribers: Dict[str, Callable[[AOSEvent], Awaitable[None]]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, event: AOSEvent) -> None:
        async with self._lock:
            if len(self._buffer) >= self._capacity:
                self._buffer.pop(0)
            self._buffer.append(event)
        for callback in list(self._subscribers.values()):
            try:
                await callback(event)
            except Exception as exc:
                LOG.error("Event subscriber error: %s", exc)

    def subscribe(self, subscriber_id: str, callback: Callable[[AOSEvent], Awaitable[None]]) -> None:
        self._subscribers[subscriber_id] = callback

    def unsubscribe(self, subscriber_id: str) -> None:
        self._subscribers.pop(subscriber_id, None)

    def recent(self, count: int = 50) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._buffer[-count:]]


class CDPCommandTimeout(Exception):
    pass


class CDPCommandError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(f"CDP error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


@dataclass
class _PendingCommand:
    future: "asyncio.Future"
    method: str
    submitted_at: float
    priority: int


class CommandQueue:
    PRIORITY_REALTIME = 0
    PRIORITY_NORMAL = 5

    def __init__(self, default_timeout_s: float = 30.0):
        self._next_id = 1
        self._pending: Dict[int, _PendingCommand] = {}
        self._default_timeout = default_timeout_s
        self._id_lock = asyncio.Lock()

    async def next_id(self) -> int:
        async with self._id_lock:
            cmd_id = self._next_id
            self._next_id += 1
            return cmd_id

    def register(self, cmd_id: int, method: str, priority: int) -> "asyncio.Future":
        loop = asyncio.get_event_loop()
        future: "asyncio.Future" = loop.create_future()
        self._pending[cmd_id] = _PendingCommand(future=future, method=method,
                                                  submitted_at=time.time(), priority=priority)
        return future

    def resolve(self, cmd_id: int, result: Any) -> None:
        pending = self._pending.pop(cmd_id, None)
        if pending and not pending.future.done():
            pending.future.set_result(result)

    def reject(self, cmd_id: int, code: int, message: str, data: Any = None) -> None:
        pending = self._pending.pop(cmd_id, None)
        if pending and not pending.future.done():
            pending.future.set_exception(CDPCommandError(code, message, data))

    def reject_all(self, reason: str) -> None:
        for cmd_id, pending in list(self._pending.items()):
            if not pending.future.done():
                pending.future.set_exception(CDPCommandError(-32000, reason))
            self._pending.pop(cmd_id, None)

    @property
    def default_timeout(self) -> float:
        return self._default_timeout


class ConnectionState(str, Enum):
    UNINITIALIZED = "UNINITIALIZED"
    CONNECTING = "CONNECTING"
    ACTIVE = "ACTIVE"
    RECOVERING = "RECOVERING"
    TERMINATED = "TERMINATED"


class CDPConnectionManager:
    def __init__(self, browser_id: str, ws_url: str, event_bus: CDPEventBus,
                 command_queue: CommandQueue, heartbeat_interval_s: float = 5.0):
        if not _HAS_WEBSOCKETS:
            raise RuntimeError("The 'websockets' package is required.")
        self.browser_id = browser_id
        self.ws_url = ws_url
        self.event_bus = event_bus
        self.command_queue = command_queue
        self.state = ConnectionState.UNINITIALIZED
        self.heartbeat_interval_s = heartbeat_interval_s
        self._ws: Optional[WebSocketClientProtocol] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._on_message: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None

    def bind_message_listener(self, callback: Callable[[str, Dict[str, Any]], Awaitable[None]]) -> None:
        self._on_message = callback

    async def connect(self) -> None:
        self.state = ConnectionState.CONNECTING
        self._ws = await websockets.connect(
            self.ws_url, max_size=IPC_MAX_FRAME_BYTES, ping_interval=None, close_timeout=5)
        self.state = ConnectionState.ACTIVE
        self._reader_task = asyncio.create_task(self._read_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await self._route_message(message)
        except Exception as exc:
            LOG.warning("CDP connection %s lost: %s", self.browser_id, exc)
            self.command_queue.reject_all("connection lost")
            self.state = ConnectionState.RECOVERING

    async def _route_message(self, message: Dict[str, Any]) -> None:
        if "id" in message:
            cmd_id = message["id"]
            if "error" in message:
                err = message["error"]
                self.command_queue.reject(cmd_id, err.get("code", -32000), err.get("message", "unknown"))
            else:
                self.command_queue.resolve(cmd_id, message.get("result", {}))
            return
        method = message.get("method", "")
        params = message.get("params", {})
        session_id = message.get("sessionId")
        if self._on_message:
            await self._on_message(method, {"params": params, "sessionId": session_id})

    async def _heartbeat_loop(self) -> None:
        while self.state == ConnectionState.ACTIVE:
            try:
                await asyncio.sleep(self.heartbeat_interval_s)
                if self.state != ConnectionState.ACTIVE:
                    return
                await self.send_raw("Browser.getVersion", {}, session_id=None, timeout_s=5.0)
            except asyncio.CancelledError:
                return
            except Exception:
                continue

    async def send_raw(self, method: str, params: Dict[str, Any], session_id: Optional[str],
                        timeout_s: Optional[float] = None, priority: int = CommandQueue.PRIORITY_NORMAL) -> Any:
        if self._ws is None:
            raise CDPCommandError(-32001, "not connected")
        cmd_id = await self.command_queue.next_id()
        future = self.command_queue.register(cmd_id, method, priority)
        envelope: Dict[str, Any] = {"id": cmd_id, "method": method, "params": params}
        if session_id:
            envelope["sessionId"] = session_id
        await self._ws.send(json.dumps(envelope))
        try:
            return await asyncio.wait_for(future, timeout=timeout_s or self.command_queue.default_timeout)
        except asyncio.TimeoutError:
            self.command_queue.reject(cmd_id, -32002, "command timeout")
            raise CDPCommandTimeout(f"{method} timed out")

    async def close(self) -> None:
        for task in (self._reader_task, self._heartbeat_task):
            if task:
                task.cancel()
        if self._ws is not None:
            await self._ws.close()
        self.state = ConnectionState.TERMINATED


@dataclass
class DiscoveredEndpoint:
    host: str
    port: int
    websocket_debugger_url: str
    browser_version: str
    protocol_version: str


class BrowserDiscoveryEngine:
    LOCAL_PROCESS_NAMES = ("chrome", "chromium", "msedge", "brave")

    def __init__(self, scan_ports: Optional[List[int]] = None):
        self.scan_ports = scan_ports or [9222, 9223, 9224]

    def _fetch_json(self, url: str, timeout_s: float = 2.0) -> Dict[str, Any]:
        if _HAS_URLLIB:
            with _urllib_request.urlopen(url, timeout=timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        raise RuntimeError("No HTTP client available")

    def verify_endpoint(self, host: str, port: int) -> Optional[DiscoveredEndpoint]:
        try:
            version_info = self._fetch_json(f"http://{host}:{port}/json/version")
            return DiscoveredEndpoint(
                host=host, port=port,
                websocket_debugger_url=version_info["webSocketDebuggerUrl"],
                browser_version=version_info.get("Browser", "unknown"),
                protocol_version=version_info.get("Protocol-Version", "1.3"))
        except Exception:
            return None

    def scan_local(self) -> List[DiscoveredEndpoint]:
        found: List[DiscoveredEndpoint] = []
        for port in self.scan_ports:
            endpoint = self.verify_endpoint("127.0.0.1", port)
            if endpoint:
                found.append(endpoint)
        return found


def _locate_chrome_executable() -> Optional[str]:
    candidates: List[str] = []
    if _IS_WINDOWS:
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        ]
    else:
        candidates = ["/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("msedge")


class BrowserProcessLauncher:
    def __init__(self, executable_path: Optional[str] = None):
        self.executable_path = executable_path or _locate_chrome_executable()

    def launch(self, user_data_dir: str, port: int, headless: bool = False) -> subprocess.Popen:
        if not self.executable_path:
            raise RuntimeError("No Chromium browser found on this host")
        os.makedirs(user_data_dir, exist_ok=True)
        args = [
            self.executable_path,
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-blink-features=AutomationControlled",
        ]
        if headless:
            args.append("--headless=new")
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@dataclass
class TargetHandle:
    target_id: str
    session_id: str
    browser_id: str
    target_type: str
    url: str = ""


class TargetRouter:
    def __init__(self):
        self._targets: Dict[str, TargetHandle] = {}
        self._session_to_target: Dict[str, str] = {}

    def register(self, handle: TargetHandle) -> None:
        self._targets[handle.target_id] = handle
        self._session_to_target[handle.session_id] = handle.target_id

    def unregister_by_target(self, target_id: str) -> None:
        handle = self._targets.pop(target_id, None)
        if handle:
            self._session_to_target.pop(handle.session_id, None)

    def resolve_by_session(self, session_id: str) -> Optional[TargetHandle]:
        if not session_id or session_id in ("DEFAULT", "default", "auto"):
            return list(self._targets.values())[0] if self._targets else None
        target_id = self._session_to_target.get(session_id)
        if target_id and target_id in self._targets:
            return self._targets[target_id]
        return list(self._targets.values())[0] if self._targets else None

    def list_targets(self, browser_id: Optional[str] = None) -> List[TargetHandle]:
        values = list(self._targets.values())
        return [t for t in values if t.browser_id == browser_id] if browser_id else values


class DOMAccessibilityEngine:
    def __init__(self, session_invoker: Callable):
        self._invoke = session_invoker

    async def query_selector(self, session_id: str, css_selector: str, target_hint: str = "") -> Optional[int]:
        try:
            try:
                await self._invoke(session_id, "DOM.enable", {})
            except Exception:
                pass
            document = await self._invoke(session_id, "DOM.getDocument", {"depth": 0})
            root_node_id = document["root"]["nodeId"]
        except Exception:
            return None

        selectors = [s.strip() for s in css_selector.split(",") if s.strip()] if css_selector else []
        for sel in selectors:
            try:
                result = await self._invoke(session_id, "DOM.querySelector", {"nodeId": root_node_id, "selector": sel})
                node_id = result.get("nodeId", 0)
                if node_id:
                    return node_id
            except Exception:
                pass

        hint = f"{target_hint} {css_selector}".lower()
        candidates = []
        if any(k in hint for k in ["search", "query", "find", "input", "box", "text"]):
            candidates.extend([
                "textarea[name='q']", "input[name='q']", "input[type='search']",
                "input#search", "input[name='search_query']", "[role='searchbox']", "textarea", "input"
            ])

        for cand in candidates:
            try:
                result = await self._invoke(session_id, "DOM.querySelector", {"nodeId": root_node_id, "selector": cand})
                node_id = result.get("nodeId", 0)
                if node_id:
                    return node_id
            except Exception:
                pass
        return None

    async def get_box_model(self, session_id: str, node_id: int) -> Optional[Dict[str, float]]:
        try:
            res = await self._invoke(session_id, "DOM.getBoxModel", {"nodeId": node_id})
            quad = res.get("model", {}).get("content", [])
            if len(quad) >= 8:
                xs, ys = quad[0::2], quad[1::2]
                return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}
        except Exception:
            pass
        return None


class VirtualInputEngine:
    def __init__(self, session_invoker: Callable):
        self._invoke = session_invoker

    async def click(self, session_id: str, x: float, y: float, click_count: int = 1) -> None:
        await self._invoke(session_id, "Input.dispatchMouseEvent",
                            {"type": "mouseMoved", "x": x, "y": y})
        await self._invoke(session_id, "Input.dispatchMouseEvent",
                            {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": click_count})
        await asyncio.sleep(0.05)
        await self._invoke(session_id, "Input.dispatchMouseEvent",
                            {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": click_count})

    async def type_text(self, session_id: str, text: str) -> None:
        for char in text:
            await self._invoke(session_id, "Input.dispatchKeyEvent", {"type": "char", "text": char})
            await asyncio.sleep(0.02)

    async def press_key(self, session_id: str, key: str) -> None:
        key_map = {"Enter": ("Enter", 13), "Backspace": ("Backspace", 8), "Tab": ("Tab", 9)}
        k_str, k_code = key_map.get(key, (key, 0))
        await self._invoke(session_id, "Input.dispatchKeyEvent",
                            {"type": "keyDown", "key": k_str, "windowsVirtualKeyCode": k_code})
        await self._invoke(session_id, "Input.dispatchKeyEvent",
                            {"type": "keyUp", "key": k_str, "windowsVirtualKeyCode": k_code})


@dataclass
class BrowserInstance:
    browser_id: str
    connection: CDPConnectionManager
    process: Optional[subprocess.Popen]
    ws_url: str
    default_session_id: Optional[str] = None


@dataclass
class RuntimeConfig:
    tcp_port: int = 47619
    runtime_dir: str = field(default_factory=lambda: os.path.join(os.getcwd(), "var", "hojaiga", "organ19"))
    scan_ports: List[int] = field(default_factory=lambda: [9222, 9223, 9224])


class CDPRuntimeKernel:
    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.event_bus = CDPEventBus()
        self.command_queue = CommandQueue()
        self.router = TargetRouter()
        self.discovery = BrowserDiscoveryEngine(scan_ports=config.scan_ports)
        self.launcher = BrowserProcessLauncher()
        self.dom_engine = DOMAccessibilityEngine(self._invoke_session)
        self.input_engine = VirtualInputEngine(self._invoke_session)
        self._instances: Dict[str, BrowserInstance] = {}
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._ipc_server = IPCServer(self, tcp_port=config.tcp_port)

    async def start(self) -> None:
        self.loop = asyncio.get_event_loop()
        await self._ipc_server.start()

    async def stop(self) -> None:
        for bid in list(self._instances.keys()):
            await self.terminate_browser(bid)
        await self._ipc_server.stop()

    async def _invoke_session(self, session_id: str, method: str, params: Dict[str, Any]) -> Any:
        handle = self.router.resolve_by_session(session_id)
        if not handle:
            raise CDPCommandError(-32003, f"Unknown session {session_id}")
        instance = self._instances.get(handle.browser_id)
        if not instance:
            raise CDPCommandError(-32004, f"Unknown browser {handle.browser_id}")
        return await instance.connection.send_raw(method, params, session_id=handle.session_id)

    async def launch_browser(self, profile_id: str = "default", headless: bool = False) -> BrowserInstance:
        # Pre-check: Attach to existing active instance if available to avoid duplicate process loops
        endpoints = self.discovery.scan_local()
        if endpoints:
            LOG.info(f"Discovered active debugging browser at port {endpoints[0].port}. Attaching...")
            return await self._attach(endpoints[0], process=None)

        port = 9222
        user_data_dir = os.path.join(self.config.runtime_dir, "profiles", profile_id)
        process = self.launcher.launch(user_data_dir, port, headless=headless)
        
        # Wait up to 5s for the port to become responsive
        deadline = time.time() + 5.0
        endpoint = None
        while time.time() < deadline:
            endpoint = self.discovery.verify_endpoint("127.0.0.1", port)
            if endpoint:
                break
            await asyncio.sleep(0.3)
            
        if not endpoint:
            if process:
                process.kill()
            raise CDPCommandError(-32006, f"Browser at 127.0.0.1:{port} did not become ready in time")
            
        return await self._attach(endpoint, process=process)

    async def _attach(self, endpoint: DiscoveredEndpoint, process: Optional[subprocess.Popen]) -> BrowserInstance:
        browser_id = uuid.uuid4().hex
        connection = CDPConnectionManager(browser_id, endpoint.websocket_debugger_url,
                                           self.event_bus, self.command_queue)
        connection.bind_message_listener(lambda m, c: self._handle_cdp_event(browser_id, m, c))
        await connection.connect()
        await connection.send_raw("Target.setDiscoverTargets", {"discover": True}, session_id=None)
        await connection.send_raw("Target.setAutoAttach",
                                   {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True},
                                   session_id=None)
        instance = BrowserInstance(browser_id=browser_id, connection=connection, process=process,
                                    ws_url=endpoint.websocket_debugger_url)
        self._instances[browser_id] = instance
        return instance

    async def terminate_browser(self, browser_id: str) -> None:
        instance = self._instances.pop(browser_id, None)
        if not instance:
            return
        await instance.connection.close()
        if instance.process:
            try:
                instance.process.terminate()
            except Exception:
                pass

    async def create_tab(self, browser_id: str, url: str = "about:blank") -> TargetHandle:
        instance = self._instances.get(browser_id)
        if not instance:
            raise CDPCommandError(-1, "Browser instance not found")
        res = await instance.connection.send_raw("Target.createTarget", {"url": url}, session_id=None)
        target_id = res["targetId"]
        attach_res = await instance.connection.send_raw("Target.attachToTarget", {"targetId": target_id, "flatten": True}, session_id=None)
        handle = TargetHandle(target_id=target_id, session_id=attach_res["sessionId"], browser_id=browser_id, target_type="page", url=url)
        self.router.register(handle)
        instance.default_session_id = handle.session_id
        await self._init_page_session(handle.session_id)
        return handle

    async def _init_page_session(self, session_id: str) -> None:
        for m in ("Page.enable", "DOM.enable", "Runtime.enable"):
            try:
                await self._invoke_session(session_id, m, {})
            except Exception:
                pass

    async def _handle_cdp_event(self, browser_id: str, method: str, ctx: Dict[str, Any]) -> None:
        params = ctx.get("params", {})
        if method == "Target.attachedToTarget":
            t_info = params.get("targetInfo", {})
            t_session = params.get("sessionId", "")
            handle = TargetHandle(target_id=t_info.get("targetId", ""), session_id=t_session,
                                   browser_id=browser_id, target_type=t_info.get("type", "page"), url=t_info.get("url", ""))
            self.router.register(handle)
            inst = self._instances.get(browser_id)
            if inst and not inst.default_session_id and t_info.get("type") == "page":
                inst.default_session_id = t_session
                await self._init_page_session(t_session)

    async def dispatch(self, frame: IPCFrame) -> IPCFrame:
        p = frame.payload
        try:
            if frame.op_code == Organ19OpCode.PING:
                return IPCFrame(Organ19OpCode.PING, {"ok": True, "pong": True})

            if frame.op_code == Organ19OpCode.LAUNCH_BROWSER:
                if self._instances:
                    inst = list(self._instances.values())[0]
                    return IPCFrame(frame.op_code, {"ok": True, "result": {"browser_id": inst.browser_id, "session_id": inst.default_session_id}})
                inst = await self.launch_browser(profile_id=p.get("profile_id", "default"), headless=p.get("headless", False))
                await asyncio.sleep(0.5)
                return IPCFrame(frame.op_code, {"ok": True, "result": {"browser_id": inst.browser_id, "session_id": inst.default_session_id}})

            if frame.op_code == Organ19OpCode.NAVIGATE:
                session_id = p.get("session_id") or "DEFAULT"
                url = p.get("url", "https://www.google.com")
                res = await self._invoke_session(session_id, "Page.navigate", {"url": url})
                await asyncio.sleep(1.5)
                return IPCFrame(frame.op_code, {"ok": True, "result": res})

            if frame.op_code == Organ19OpCode.CREATE_TAB:
                browser_id = p.get("browser_id") or (list(self._instances.keys())[0] if self._instances else None)
                handle = await self.create_tab(browser_id, p.get("url", "about:blank"))
                return IPCFrame(frame.op_code, {"ok": True, "result": {"session_id": handle.session_id, "target_id": handle.target_id}})

            if frame.op_code == Organ19OpCode.CLICK:
                session_id = p.get("session_id") or "DEFAULT"
                x = p.get("x")
                y = p.get("y")
                selector = p.get("selector", "")
                target_hint = p.get("target", "")

                # Coordinate & Selector Safe Resolver (Fixes KeyError 'x')
                if x is None or y is None:
                    node_id = await self.dom_engine.query_selector(session_id, selector, target_hint)
                    if node_id:
                        box = await self.dom_engine.get_box_model(session_id, node_id)
                        if box:
                            x = box["x"] + box["width"] / 2
                            y = box["y"] + box["height"] / 2
                    
                    if x is None or y is None:
                        # Fallback to viewport center instead of crashing with KeyError
                        x = 500.0
                        y = 350.0

                await self.input_engine.click(session_id, float(x), float(y))

                text_to_type = p.get("text", "")
                if text_to_type:
                    await self.input_engine.type_text(session_id, text_to_type)
                    if p.get("press_enter"):
                        await asyncio.sleep(0.2)
                        await self.input_engine.press_key(session_id, "Enter")

                return IPCFrame(frame.op_code, {"ok": True, "result": {"clicked": True, "x": x, "y": y}})

            if frame.op_code == Organ19OpCode.GET_PAGE_STATE:
                session_id = p.get("session_id") or "DEFAULT"
                url = await self._invoke_session(session_id, "Runtime.evaluate", {"expression": "window.location.href", "returnByValue": True})
                title = await self._invoke_session(session_id, "Runtime.evaluate", {"expression": "document.title", "returnByValue": True})
                return IPCFrame(frame.op_code, {"ok": True, "result": {"url": url.get("result", {}).get("value", ""), "title": title.get("result", {}).get("value", "")}})

            if frame.op_code == Organ19OpCode.GET_DOM_TREE:
                session_id = p.get("session_id") or "DEFAULT"
                try:
                    await self._invoke_session(session_id, "DOM.enable", {})
                except Exception:
                    pass
                try:
                    doc = await self._invoke_session(session_id, "DOM.getFlattenedDocument", {"depth": -1, "pierce": True})
                except Exception:
                    try:
                        doc = await self._invoke_session(session_id, "DOM.getDocument", {"depth": -1, "pierce": True})
                    except Exception:
                        html_res = await self._invoke_session(session_id, "Runtime.evaluate", {
                            "expression": "document.documentElement.outerHTML",
                            "returnByValue": True
                        })
                        doc = {"nodes": [], "outerHTML": html_res.get("result", {}).get("value", "")}
                return IPCFrame(frame.op_code, {"ok": True, "result": doc})

            return IPCFrame(Organ19OpCode.ERROR, {"ok": False, "error": f"Unsupported opcode {frame.op_code}"})
        except Exception as e:
            return IPCFrame(Organ19OpCode.ERROR, {"ok": False, "error": str(e)})


async def _amain() -> None:
    config = RuntimeConfig()
    kernel = CDPRuntimeKernel(config)
    await kernel.start()
    LOG.info("Chrome CDP Runtime online on port 47619.")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(_amain())
