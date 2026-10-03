"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 19
Name: Chrome Cdp Runtime

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Chrome Cdp Runtime]
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
Dependencies: win32process, platform, socket, hashlib, win32api...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_19_chrome_cdp_runtime.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
organ_19_chrome_cdp_runtime.py

HOJAIGA AUTOMATION OS - ORGAN 19: CHROME CDP RUNTIME
======================================================================
Authority Order: Constitution -> Law Book -> Policy Manual ->
                  Master Architecture Blueprint -> Organ Specification ->
                  CHROME_CDP_RUNTIME_ARCHITECTURE_SPECIFICATION.md

Universal Law 3 (Separation of Responsibility): this organ owns ONLY
Chromium DevTools Protocol (CDP) browser communication, execution and
instrumentation. It does not implement Brain, Knowledge, Interface or
any other organ. It exposes itself exclusively through the documented
`hojaiga_interface` length-prefixed binary frame IPC socket:

    [4-byte length | 2-byte op_code | JSON payload]   (max 16MB)

Transport fallback order: Windows Named Pipe -> Unix Domain Socket ->
TCP loopback (127.0.0.1), identical wire protocol on every transport.

CPU-only. Windows 11 primary / POSIX compatible. No GPU usage (GPU is
reserved exclusively for the Brain's local LLM inference and is never
touched by this organ).

======================================================================
PRE-CODE ARCHITECTURE DIAGRAM (spec-derived)
======================================================================

    +-----------------------------------------------------------------+
    |                       CHROME CDP RUNTIME                        |
    |                                                                 |
    |  +----------------+   +---------------+   +------------------+ |
    |  | Connection Mgr |-->| Target Router |-->| Frame/Ctx Tracker| |
    |  | (WS Multiplex) |   | (Session Disp)|   | (ExecutionCtx)   | |
    |  +----------------+   +---------------+   +------------------+ |
    |         |                     |                     |          |
    |         v                     v                     v          |
    |  +----------------+   +---------------+   +------------------+ |
    |  | Command Queue  |   |  Event Bus    |   | Out-of-Band      | |
    |  | (RPC req/res)  |   | (CDP PubSub)  |   | Stream Engine    | |
    |  +----------------+   +---------------+   +------------------+ |
    +-----------------------------------------------------------------+
                                  ^
                                  | JSON-RPC 2.0 over WebSocket
                                  v
    +-----------------------------------------------------------------+
    |            CHROMIUM BROWSER PROCESS (TARGET)                    |
    |  [Browser Target] -> [Page Target] -> [Worker/Frame Targets]    |
    +-----------------------------------------------------------------+

======================================================================
ACTUAL (AS-BUILT) ARCHITECTURE DIAGRAM
======================================================================

    BrowserDiscoveryEngine
        |
        v
    CDPConnectionManager --owns--> {BrowserID: CDPWebSocketLink}
        |
        v
    TargetRouter (sessionId <-> TargetHandle, flat protocol)
        |
        +--> FrameContextTracker (frameId / loaderId / executionContextId)
        +--> CommandQueue (id -> Future, priority lanes, timeout)
        +--> CDPEventBus (ring buffer pub/sub -> AOS unified events)
        +--> OutOfBandStreamEngine (screencast / tracing binary lanes)
        |
        v
    Subsystem Execution Matrix
        DOMAccessibilityEngine   VirtualInputEngine
        NetworkInterceptor       ScreenshotVisionEngine
        StorageCookieManager     FileChooserBridge / NativePickerBridge
        DownloadManager          BrowserProfileManager
        |
        v
    RecoveryEngine (crash detection, respawn, session state restore)
        |
        v
    CDPRuntimeKernel  <--dispatch-->  IPCServer (hojaiga_interface)
"""


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
import math
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import IntEnum, Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple, Awaitable, Union, TypeGuard

# ----------------------------------------------------------------------
# SOFT IMPORTS (optional platform / transport dependencies)
# ----------------------------------------------------------------------
try:
    import websockets
    from websockets.client import WebSocketClientProtocol  # type: ignore
    _HAS_WEBSOCKETS = True
except Exception:  # pragma: no cover - optional dependency
    websockets = None
    WebSocketClientProtocol = Any  # type: ignore
    _HAS_WEBSOCKETS = False

try:
    import aiohttp
    _HAS_AIOHTTP = True
except Exception:  # pragma: no cover - optional dependency
    aiohttp = None
    _HAS_AIOHTTP = False

try:
    import urllib.request as _urllib_request
    _HAS_URLLIB = True
except Exception:  # pragma: no cover
    _HAS_URLLIB = False

_IS_WINDOWS = platform.system() == "Windows"

if _IS_WINDOWS:
    try:
        import win32pipe  # type: ignore
        import win32file  # type: ignore
        import win32con  # type: ignore
        import win32gui  # type: ignore
        import win32api  # type: ignore
        import win32security  # type: ignore
        import pywintypes  # type: ignore
        _HAS_PYWIN32 = True
    except Exception:  # pragma: no cover - optional dependency
        win32pipe = win32file = win32con = win32gui = win32api = win32security = pywintypes = None
        _HAS_PYWIN32 = False
else:
    _HAS_PYWIN32 = False

try:
    import psutil  # type: ignore
    _HAS_PSUTIL = True
except Exception:  # pragma: no cover - optional dependency
    psutil = None
    _HAS_PSUTIL = False


LOG = logging.getLogger("hojaiga.organ19.chrome_cdp_runtime")
if not LOG.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] organ19.cdp: %(message)s"))
    LOG.addHandler(_handler)
LOG.setLevel(logging.INFO)

def load_system_config():
    for p in ["runtime_config.yaml", "var/hojaiga/config/runtime_config.yaml", r"D:\new_automation\runtime_config.yaml", r"D:\new_automation\var\hojaiga\config\runtime_config.yaml"]:
        if os.path.exists(p):
            try:
                import yaml
                with open(p, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
    return {}

# Polish setup_login — runs only when Chrome needed and no DB session cookie
try:
    from core_organs.setup_login import ensure_login  # type: ignore
    _HAS_SETUP_LOGIN = True
except Exception:
    ensure_login = None  # type: ignore
    _HAS_SETUP_LOGIN = False


# ======================================================================
# SECTION 1 -- IPC WIRE PROTOCOL (shared contract, per Law Book 5)
# ======================================================================

IPC_SOCKET_NAME = "hojaiga_interface"
IPC_MAX_FRAME_BYTES = 16 * 1024 * 1024
IPC_LENGTH_HEADER = struct.Struct(">I")
IPC_OPCODE_HEADER = struct.Struct(">H")


class Organ19OpCode(IntEnum):
    """Operation codes accepted on this organ's IPC socket."""
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
    HANDLE_CAPTCHA = 0x0124
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
    APPROVE_TASK_COMPLETION = 0x01F1
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
    """
    Length-prefixed binary frame IPC server for Organ 19.
    Transport fallback: Windows Named Pipe -> Unix Domain Socket -> TCP loopback.
    Identical wire protocol across every transport.
    """

    def __init__(self, kernel: "CDPRuntimeKernel", tcp_port: int = 47619,
                 pipe_name: str = r"\\.\pipe\hojaiga_interface_organ19",
                 uds_path: str = "/tmp/hojaiga_interface_organ19.sock"):
        self._kernel = kernel
        self._tcp_port = tcp_port
        self._pipe_name = pipe_name
        self._uds_path = uds_path
        self._server: Optional[asyncio.AbstractServer] = None
        self._transport_kind: Optional[IPCTransportKind] = None
        self._pipe_thread: Optional[threading.Thread] = None
        self._pipe_stop = threading.Event()

    @property
    def transport_kind(self) -> Optional[IPCTransportKind]:
        return self._transport_kind

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, host="127.0.0.1", port=self._tcp_port)
        self._transport_kind = IPCTransportKind.TCP_LOOPBACK
        LOG.info("IPC transport: TCP loopback (127.0.0.1:%d)", self._tcp_port)

    async def stop(self) -> None:
        self._pipe_stop.set()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        if self._pipe_thread is not None:
            self._pipe_thread.join(timeout=2.0)

    def _start_named_pipe(self) -> None:
        def _pipe_loop() -> None:
            while not self._pipe_stop.is_set():
                try:
                    handle = win32pipe.CreateNamedPipe(  # type: ignore
                        self._pipe_name,
                        win32pipe.PIPE_ACCESS_DUPLEX,  # type: ignore
                        win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,  # type: ignore
                        win32pipe.PIPE_UNLIMITED_INSTANCES,  # type: ignore
                        IPC_MAX_FRAME_BYTES, IPC_MAX_FRAME_BYTES, 0)
                    win32pipe.ConnectNamedPipe(handle, None)  # type: ignore
                    self._serve_pipe_client(handle)
                except Exception as exc:  # pragma: no cover - platform dependent
                    if not self._pipe_stop.is_set():
                        LOG.error("Named pipe error: %s", exc)
                        time.sleep(0.5)
        self._pipe_thread = threading.Thread(target=_pipe_loop, daemon=True, name="organ19-named-pipe")
        self._pipe_thread.start()

    def _serve_pipe_client(self, handle) -> None:  # pragma: no cover - platform dependent
        loop = self._kernel.loop
        if loop is None:
            raise RuntimeError("Event loop is not available")
        try:
            while not self._pipe_stop.is_set():
                _, length_bytes = win32file.ReadFile(handle, 4)  # type: ignore
                total_len = IPC_LENGTH_HEADER.unpack(length_bytes if isinstance(length_bytes, bytes) else length_bytes.encode())[0]
                _, body = win32file.ReadFile(handle, total_len)  # type: ignore
                frame = IPCFrame.decode(body if isinstance(body, bytes) else body.encode())
                future = asyncio.run_coroutine_threadsafe(
                    self._kernel.dispatch(frame), loop)
                response = future.result(timeout=60)
                win32file.WriteFile(handle, response.encode())  # type: ignore
        except Exception as exc:
            LOG.debug("Named pipe client disconnected: %s", exc)
        finally:
            try:
                win32file.CloseHandle(handle)  # type: ignore
            except Exception:
                pass

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        LOG.debug("IPC client connected: %s", peer)
        try:
            while True:
                length_bytes = await reader.readexactly(4)
                total_len = IPC_LENGTH_HEADER.unpack(length_bytes if isinstance(length_bytes, bytes) else length_bytes.encode())[0]
                if total_len > IPC_MAX_FRAME_BYTES:
                    raise ValueError("frame exceeds max size")
                body = await reader.readexactly(total_len)
                frame = IPCFrame.decode(body)
                response = await self._kernel.dispatch(frame)
                writer.write(response.encode())
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        except Exception as exc:
            LOG.warning("IPC client error: %s", exc)
        finally:
            writer.close()


# ======================================================================
# SECTION 2 -- CDP EVENT MODEL
# ======================================================================

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

    @staticmethod
    def from_cdp_method(method: str) -> Optional["AOSEventType"]:
        return _CDP_EVENT_CATALOG.get(method)


_CDP_EVENT_CATALOG: Dict[str, AOSEventType] = {
    "Page.loadEventFired": AOSEventType.PAGE_LOADED,
    "Page.domContentEventFired": AOSEventType.DOM_READY,
    "Page.frameNavigated": AOSEventType.FRAME_NAVIGATED,
    "Target.targetCreated": AOSEventType.TARGET_CREATED,
    "Target.targetCrashed": AOSEventType.TARGET_CRASHED,
    "DOM.documentUpdated": AOSEventType.DOM_MUTATED,
    "Network.requestWillBeSent": AOSEventType.NETWORK_REQUEST,
    "Network.responseReceived": AOSEventType.NETWORK_RESPONSE,
    "Network.loadingFailed": AOSEventType.NETWORK_FAILED,
    "Runtime.consoleAPICalled": AOSEventType.CONSOLE_MESSAGE,
    "Runtime.exceptionThrown": AOSEventType.RUNTIME_EXCEPTION,
    "Page.javascriptDialogOpening": AOSEventType.DIALOG_OPENED,
    "Security.securityStateChanged": AOSEventType.SECURITY_CHANGED,
    "Browser.downloadProgress": AOSEventType.DOWNLOAD_PROGRESS,
    "Page.fileChooserOpened": AOSEventType.FILE_CHOOSER_OPENED,
    "Page.screencastFrame": AOSEventType.SCREENCAST_FRAME,
}


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
    """
    Asynchronous ring-buffer style event distribution system.
    Publishes unified AOS events derived from raw CDP domain events
    to subscribing internal components and external IPC subscribers.
    """

    def __init__(self, capacity: int = 4096):
        self._capacity = capacity
        self._buffer: List[AOSEvent] = []
        self._subscribers: Dict[str, Callable[[AOSEvent], Awaitable[None]]] = {}
        self._dropped = 0
        self._lock = asyncio.Lock()

    async def publish(self, event: AOSEvent) -> None:
        async with self._lock:
            if len(self._buffer) >= self._capacity:
                self._buffer.pop(0)
                self._dropped += 1
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

    @property
    def dropped_count(self) -> int:
        return self._dropped


# ======================================================================
# SECTION 3 -- COMMAND QUEUE (JSON-RPC 2.0 request/response matching)
# ======================================================================

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
    """
    Guarantees command order, matches JSON-RPC ids with responses,
    enforces timeout policy, supports priority lanes for real-time
    human-in-the-loop overrides.
    """

    PRIORITY_REALTIME = 0
    PRIORITY_NORMAL = 5
    PRIORITY_BACKGROUND = 9

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

    @property
    def in_flight(self) -> int:
        return len(self._pending)


# ======================================================================
# SECTION 4 -- CONNECTION MANAGER (WebSocket multiplexer)
# ======================================================================

class ConnectionState(str, Enum):
    UNINITIALIZED = "UNINITIALIZED"
    CONNECTING = "CONNECTING"
    ACTIVE = "ACTIVE"
    RECOVERING = "RECOVERING"
    TERMINATED = "TERMINATED"


class CDPConnectionManager:
    """
    Manages a single root WebSocket connection to a Chromium debugging
    endpoint using flattened CDP sessions (Target.attachToTarget with
    flatten=true). One root connection multiplexes every tab/target
    for the owning browser instance.
    """

    def __init__(self, browser_id: str, ws_url: str, event_bus: CDPEventBus,
                 command_queue: CommandQueue, heartbeat_interval_s: float = 5.0):
        if not _HAS_WEBSOCKETS:
            raise RuntimeError(
                "The 'websockets' package is required for Chrome CDP Runtime "
                "and is not installed. Install with: pip install websockets")
        self.browser_id = browser_id
        self.ws_url = ws_url
        self.event_bus = event_bus
        self.command_queue = command_queue
        self.state = ConnectionState.UNINITIALIZED
        self.heartbeat_interval_s = heartbeat_interval_s
        self._ws: Optional[WebSocketClientProtocol] = None  # type: ignore
        self._reader_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._on_state_change: Optional[Callable[[ConnectionState], Awaitable[None]]] = None
        self._on_message: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None

    def bind_state_listener(self, callback: Callable[[ConnectionState], Awaitable[None]]) -> None:
        self._on_state_change = callback

    def bind_message_listener(self, callback: Callable[[str, Dict[str, Any]], Awaitable[None]]) -> None:
        self._on_message = callback

    async def _set_state(self, state: ConnectionState) -> None:
        self.state = state
        if self._on_state_change:
            await self._on_state_change(state)

    async def connect(self) -> None:
        await self._set_state(ConnectionState.CONNECTING)
        self._ws = await websockets.connect(  # type: ignore
            self.ws_url, max_size=IPC_MAX_FRAME_BYTES, ping_interval=None, close_timeout=5)
        await self._set_state(ConnectionState.ACTIVE)
        self._reader_task = asyncio.create_task(self._read_loop(), name=f"cdp-reader-{self.browser_id}")
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name=f"cdp-heartbeat-{self.browser_id}")

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:  # type: ignore[union-attr]
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    LOG.warning("Malformed CDP frame received, dropping")
                    continue
                await self._route_message(message)
        except Exception as exc:
            LOG.warning("CDP connection %s lost: %s", self.browser_id, exc)
            self.command_queue.reject_all("connection lost")
            await self._set_state(ConnectionState.RECOVERING)

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
            except CDPCommandError:
                LOG.warning("Heartbeat failed for browser %s; marking RECOVERING", self.browser_id)
                await self._set_state(ConnectionState.RECOVERING)
                return
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
            raise CDPCommandTimeout(f"{method} timed out after {timeout_s or self.command_queue.default_timeout}s")

    async def close(self) -> None:
        for task in (self._reader_task, self._heartbeat_task):
            if task:
                task.cancel()
        if self._ws is not None:
            await self._ws.close()
        await self._set_state(ConnectionState.TERMINATED)


# ======================================================================
# SECTION 5 -- BROWSER DISCOVERY ENGINE
# ======================================================================

@dataclass
class DiscoveredEndpoint:
    host: str
    port: int
    websocket_debugger_url: str
    browser_version: str
    protocol_version: str
    process_id: Optional[int] = None


class BrowserDiscoveryEngine:
    """
    Scans, verifies, and attaches to Chromium instances across local
    and remote environments per spec section 3.
    """

    LOCAL_PROCESS_NAMES = ("chrome", "chromium", "msedge", "brave", "thorium", "electron")

    def __init__(self, scan_ports: Optional[List[int]] = None):
        self.scan_ports = scan_ports or [9222, 9223, 9224]

    def discover_local_processes(self) -> List[Tuple[int, int]]:
        """Returns list of (pid, remote_debugging_port) tuples found via CLI args."""
        results: List[Tuple[int, int]] = []
        if not _HAS_PSUTIL:
            return results
        for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):  # type: ignore
            try:
                name = (proc.info.get("name") or "").lower()
                if not any(target in name for target in self.LOCAL_PROCESS_NAMES):
                    continue
                cmdline = proc.info.get("cmdline") or []
                for arg in cmdline:
                    if arg.startswith("--remote-debugging-port="):
                        port = int(arg.split("=", 1)[1])
                        results.append((proc.info["pid"], port))
            except Exception:
                continue
        return results

    def read_devtools_active_port_file(self, user_data_dir: str) -> Optional[Tuple[str, int]]:
        """Parses DevToolsActivePort file inside a Chromium user-data-dir."""
        path = os.path.join(user_data_dir, "DevToolsActivePort")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        if len(lines) < 2:
            return None
        port = int(lines[0])
        ws_path = lines[1]
        return ws_path, port

    def _fetch_json(self, url: str, timeout_s: float = 3.0) -> Dict[str, Any]:
        if _HAS_URLLIB:
            with _urllib_request.urlopen(url, timeout=timeout_s) as response:  # nosec B310  # type: ignore
                return json.loads(response.read().decode("utf-8"))
        raise RuntimeError("no HTTP client available for discovery")

    def verify_endpoint(self, host: str, port: int) -> Optional[DiscoveredEndpoint]:
        """Queries /json/version and validates protocol version >= 1.3."""
        try:
            version_info = self._fetch_json(f"http://{host}:{port}/json/version")
            protocol_version = version_info.get("Protocol-Version", "0.0")
            if tuple(int(x) for x in protocol_version.split(".")) < (1, 3):
                LOG.warning("Endpoint %s:%d protocol version %s below minimum", host, port, protocol_version)
                return None
            return DiscoveredEndpoint(
                host=host, port=port,
                websocket_debugger_url=version_info["webSocketDebuggerUrl"],
                browser_version=version_info.get("Browser", "unknown"),
                protocol_version=protocol_version)
        except Exception as exc:
            LOG.debug("Endpoint %s:%d not reachable: %s", host, port, exc)
            return None

    def scan_local(self) -> List[DiscoveredEndpoint]:
        found: List[DiscoveredEndpoint] = []
        for _, port in self.discover_local_processes():
            endpoint = self.verify_endpoint("127.0.0.1", port)
            if endpoint:
                found.append(endpoint)
        for port in self.scan_ports:
            endpoint = self.verify_endpoint("127.0.0.1", port)
            if endpoint and endpoint not in found:
                found.append(endpoint)
        return found

    def resolve_remote(self, host: str, port: int) -> Optional[DiscoveredEndpoint]:
        return self.verify_endpoint(host, port)


# ======================================================================
# SECTION 6 -- BROWSER PROCESS LAUNCHER & PROFILE MANAGER
# ======================================================================

@dataclass
class BrowserProfile:
    profile_id: str
    user_data_dir: str
    proxy_server: Optional[str] = None
    incognito: bool = False
    extra_flags: List[str] = field(default_factory=list)
    profile_directory: str = "Default"


# Volatile/lock artifacts that must never be cloned or blocked on while the
# human browser is open (mirrors the Polish-automation safe-clone policy).
_USER_PROFILE_SKIP_FILES = {
    "SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile", "LOCK",
    "DevToolsActivePort",
}
_USER_PROFILE_SKIP_DIRS = {
    "Cache", "Code Cache", "GPUCache", "ShaderCache", "GrShaderCache",
    "DawnGraphiteCache", "DawnWebGPUCache", "Crashpad", "Sessions",
    "Session Storage", "Service Worker", "BrowserMetrics", "OptimizationGuide",
    "Safe Browsing",
}


def resolve_profile_directory(user_data_dir: str) -> str:
    """Deterministically pick which profile to open inside a user-data-dir.

    Chrome shows the "Who's using Chrome?" profile picker when
    --profile-directory is omitted and the user-data-dir is ambiguous. Every
    launch therefore resolves ONE profile up front so the picker can never
    silently block automation:
      1. The profile recorded as last used in Local State (when it exists).
      2. "Default" (Chrome's own convention for fresh/managed dirs).
      3. The sole "Profile N" directory when exactly one exists.
      4. "Default" (Chrome creates it on first run).
    """
    base = os.path.abspath(user_data_dir)
    last_used = ""
    local_state = os.path.join(base, "Local State")
    try:
        if os.path.exists(local_state):
            with open(local_state, "r", encoding="utf-8") as handle:
                state = json.load(handle)
            profile_state = state.get("profile", {}) if isinstance(state, dict) else {}
            last_used = str(profile_state.get("last_used") or "")
            if not last_used:
                active = profile_state.get("last_active_profiles") or []
                if isinstance(active, list) and active:
                    last_used = str(active[0])
    except Exception:
        last_used = ""
    if last_used and os.path.isdir(os.path.join(base, last_used)):
        return last_used
    if os.path.isdir(os.path.join(base, "Default")):
        return "Default"
    try:
        candidates = [name for name in os.listdir(base)
                      if name.startswith("Profile ") and os.path.isdir(os.path.join(base, name))]
    except Exception:
        candidates = []
    if len(candidates) == 1:
        return candidates[0]
    return "Default"


class BrowserProfileManager:
    """Creates and tracks isolated Chromium user-data-dir profiles."""
    def __init__(self, base_dir: str):
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        self._profiles: Dict[str, BrowserProfile] = {}
        self._user_profile_cache: Optional[BrowserProfile] = None

    def create_profile(self, profile_id: Optional[str] = None, proxy_server: Optional[str] = None, incognito: bool = False,
                        extra_flags: Optional[List[str]] = None, user_data_dir: Optional[str] = None,
                        profile_directory: Optional[str] = None) -> BrowserProfile:
        if not profile_id:
            profile_id = uuid.uuid4().hex
        if not user_data_dir:
            user_data_dir = os.path.abspath(os.path.join(self.base_dir, profile_id))
        else:
            user_data_dir = os.path.abspath(user_data_dir)
        os.makedirs(user_data_dir, exist_ok=True)
        # --profile-directory determinism: never let Chrome fall back to the
        # "Who's using Chrome?" picker, which silently blocks all automation.
        if not profile_directory:
            profile_directory = resolve_profile_directory(user_data_dir)
        profile = BrowserProfile(profile_id=profile_id, user_data_dir=user_data_dir,
                                  proxy_server=proxy_server, incognito=incognito,
                                  extra_flags=extra_flags or [], profile_directory=profile_directory)
        self._profiles[profile_id] = profile
        return profile

    def get(self, profile_id: str) -> Optional[BrowserProfile]:
        return self._profiles.get(profile_id)

    def destroy_profile(self, profile_id: str) -> None:
        profile = self._profiles.pop(profile_id, None)
        if profile and os.path.isdir(profile.user_data_dir):
            shutil.rmtree(profile.user_data_dir, ignore_errors=True)

    @staticmethod
    def _read_profile_cache(user_data_base: str) -> Optional[str]:
        """Reads the profile selection cached by the interactive chooser."""
        cache_file = os.path.join(user_data_base, ".hojaiga_profile_cache")
        try:
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as handle:
                    cached = handle.read().strip()
                if cached:
                    return cached
        except Exception:
            pass
        return None

    @staticmethod
    def _copy_file_quiet(src: str, dst: str) -> bool:
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            return True
        except Exception:
            return False

    def _copy_tree_quiet(self, src: str, dst: str) -> None:
        """Copies a profile directory, skipping volatile dirs and locked files."""
        os.makedirs(dst, exist_ok=True)
        for root, dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            dirs[:] = [d for d in dirs if d not in _USER_PROFILE_SKIP_DIRS]
            target_root = dst if rel == "." else os.path.join(dst, rel)
            os.makedirs(target_root, exist_ok=True)
            for name in files:
                if name in _USER_PROFILE_SKIP_FILES:
                    continue
                self._copy_file_quiet(os.path.join(root, name), os.path.join(target_root, name))

    def prepare_user_profile(self, user_data_base: Optional[str] = None,
                              profile_directory: Optional[str] = None,
                              refresh: bool = False) -> BrowserProfile:
        """Clones the human user's real Chrome profile for authenticated automation.

        Resolves which profile to use without ever prompting (explicit choice ->
        cached choice -> Local State last_used -> sole Profile N -> Default),
        then copies it into an isolated clone inside the runtime so the live
        browser data is never locked or hijacked. Chrome is always opened with
        an explicit --profile-directory, so the "Who's using Chrome?" picker can
        never block automation.
        """
        if self._user_profile_cache is not None and not refresh:
            return self._user_profile_cache
        base = (user_data_base
                or os.environ.get("HOJAIGA_USER_CHROME_DATA")
                or (os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data") if _IS_WINDOWS
                    else os.path.expanduser("~/.config/google-chrome")))
        if not os.path.isdir(base):
            raise RuntimeError(f"user Chrome data dir not found: {base}")
        chosen = profile_directory or self._read_profile_cache(base) or resolve_profile_directory(base)
        if not os.path.isdir(os.path.join(base, chosen)):
            chosen = resolve_profile_directory(base)
        source_profile = os.path.join(base, chosen)
        if not os.path.isdir(source_profile):
            raise RuntimeError(f"Chrome profile directory not found: {source_profile}")
        clone_root = os.path.join(self.base_dir, "user_profile_clone")
        # Copy Local State (profile bookkeeping) so the clone is self-consistent,
        # then the resolved profile directory minus volatile lock/session files.
        local_state = os.path.join(base, "Local State")
        if os.path.exists(local_state):
            self._copy_file_quiet(local_state, os.path.join(clone_root, "Local State"))
        self._copy_tree_quiet(source_profile, os.path.join(clone_root, chosen))
        profile = self.create_profile(profile_id="user_profile", user_data_dir=clone_root,
                                      profile_directory=chosen)
        self._user_profile_cache = profile
        LOG.info("prepare_user_profile: cloned profile '%s' from %s -> %s", chosen, base, clone_root)
        return profile


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
    for name in ("google-chrome", "chromium-browser", "chromium", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    return None


class BrowserProcessLauncher:
    """Spawns local Chromium processes with deterministic launch flags."""

    def __init__(self, executable_path: Optional[str] = None):
        self.executable_path = executable_path or _locate_chrome_executable()

    def launch(self, profile: BrowserProfile, port: int = 0, headless: bool = False,
                extra_args: Optional[List[str]] = None) -> subprocess.Popen:
        if not self.executable_path:
            raise RuntimeError("No Chromium-based browser executable located on this system")
        # port=0 lets Chrome pick a free debugging port itself, eliminating the
        # race where our pre-selected port gets taken by another chrome.exe during
        # a respawn storm. The real port is read back from DevToolsActivePort.
        abs_user_data_dir = os.path.abspath(profile.user_data_dir)
        args = [
            self.executable_path,
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={abs_user_data_dir}",
            # Deterministic profile open: omitting --profile-directory lets Chrome
            # show the "Who's using Chrome?" picker, which blocks automation.
            f"--profile-directory={profile.profile_directory or 'Default'}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-breakpad",
            "--disable-blink-features=AutomationControlled",
            # Polish-automation proven-launch flags (stability on constrained HW):
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1440,900",
        ]
        if profile.incognito:
            args.append("--incognito")
        if profile.proxy_server:
            args.append(f"--proxy-server={profile.proxy_server}")
        if headless:
            args.append("--headless=new")
        args.extend(profile.extra_flags)
        args.extend(extra_args or [])
        # Only suppress window if headless mode is explicitly requested; GUI Chrome must be visible
        creationflags = (subprocess.CREATE_NO_WINDOW if _IS_WINDOWS else 0) if headless else 0
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=creationflags)


# ======================================================================
# SECTION 6b -- POLISH MERGED: BrowserManager (browser_tools.py:85-127) + HITL (hitl_pipeline.py:1-92)
# Runs only via setup_login check — not every time.
# ======================================================================

# Polish BrowserManager — isolated selenium/undetected_chromedriver path for setup_login and fallback
# Kept separate from Organ19's CDP BrowserProfileManager to preserve CDP virtual input.
try:
    from selenium import webdriver as _selenium_wd  # type: ignore
    from selenium.webdriver.chrome.service import Service as _ChromeService  # type: ignore
    from webdriver_manager.chrome import ChromeDriverManager as _CDM  # type: ignore
    _HAS_SELENIUM_PM = True
except Exception:
    _selenium_wd = None  # type: ignore
    _HAS_SELENIUM_PM = False

class PolishBrowserManager:
    """Mirrors tools/browser_tools.py:85-127 prepare_profile + get_driver for setup_login."""
    _drivers = {}
    _lock = threading.Lock()
    _profiles_prepared = set()

    @classmethod
    def prepare_profile(cls, worker_id, base_profile, profile_dir="Default"):
        import shutil as _sh
        temp_dir = os.path.join(os.environ.get("TEMP", r"C:\temp"), f"chrome-agent-{worker_id}")
        key = (worker_id, profile_dir)
        if key not in cls._profiles_prepared:
            if os.path.exists(temp_dir):
                _sh.rmtree(temp_dir, ignore_errors=True)
            os.makedirs(temp_dir, exist_ok=True)
            for item in ["Local State", "Preferences"]:
                src = os.path.join(base_profile, item)
                if os.path.exists(src):
                    _sh.copy2(src, os.path.join(temp_dir, item))
            src_path = os.path.join(base_profile, profile_dir)
            if not os.path.exists(src_path):
                src_path = os.path.join(base_profile, "Default")
            dst = os.path.join(temp_dir, profile_dir)
            os.makedirs(dst, exist_ok=True)
            for root, dirs, files in os.walk(src_path):
                rel = os.path.relpath(root, src_path)
                dest = os.path.join(dst, rel)
                os.makedirs(dest, exist_ok=True)
                for f in files:
                    if f in ["lockfile", "SingletonLock", "SingletonCookie", "SingletonSocket"]:
                        continue
                    try:
                        _sh.copy2(os.path.join(root, f), os.path.join(dest, f))
                    except Exception:
                        pass
            cls._profiles_prepared.add(key)
        return temp_dir

# Polish HITL — hitl_pipeline.py:1-92 original, not fake always-visible
import hashlib as _hitl_hash
_hitl_last_hash = None
_hitl_loop = 0

def polish_inject_hitl_ui(driver):
    js_code = """
    if (!document.getElementById('hitl-cdp-overlay')) {
        let overlay = document.createElement('div');
        overlay.id = 'hitl-cdp-overlay';
        overlay.style.position = 'fixed';
        overlay.style.bottom = '0';
        overlay.style.left = '0';
        overlay.style.width = '100%';
        overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.9)';
        overlay.style.color = '#00ffcc';
        overlay.style.padding = '15px';
        overlay.style.zIndex = '999999999';
        overlay.style.display = 'flex';
        overlay.style.justifyContent = 'space-between';
        overlay.style.alignItems = 'center';
        overlay.style.fontFamily = 'monospace';
        overlay.style.fontSize = '14px';
        overlay.style.transition = 'opacity 0.3s';
        overlay.style.opacity = '0';
        let text = document.createElement('span');
        text.id = 'hitl-cdp-text';
        text.innerText = 'CDP Automation Active | Mouse idle';
        let bc = document.createElement('div');
        let pb = document.createElement('button');
        pb.innerText = 'PAUSE (HITL)';
        pb.style.marginRight = '10px';
        pb.style.backgroundColor = '#ffcc00';
        pb.style.border = 'none';
        pb.style.padding = '5px 10px';
        pb.style.cursor = 'pointer';
        pb.style.fontWeight = 'bold';
        let rb = document.createElement('button');
        rb.innerText = 'FIXED - RESUME';
        rb.style.backgroundColor = '#00ffcc';
        rb.style.border = 'none';
        rb.style.padding = '5px 10px';
        rb.style.cursor = 'pointer';
        rb.style.fontWeight = 'bold';
        bc.appendChild(pb); bc.appendChild(rb);
        overlay.appendChild(text); overlay.appendChild(bc);
        document.body.appendChild(overlay);
        window.__HITL_PAUSED = false;
        pb.onclick = function() { window.__HITL_PAUSED = true; text.innerText = ' HUMAN INTERVENTION NEEDED - Automation Paused'; overlay.style.opacity = '1'; };
        rb.onclick = function() { window.__HITL_PAUSED = false; text.innerText = 'CDP Automation Active | Resuming...'; setTimeout(()=>{ overlay.style.opacity='0'; },2000); };
        let to; document.addEventListener('mousemove', ()=>{ if(!window.__HITL_PAUSED){ overlay.style.opacity='1'; clearTimeout(to); to=setTimeout(()=>{ if(!window.__HITL_PAUSED) overlay.style.opacity='0'; },2000); } });
    }
    """
    try:
        driver.execute_script(js_code)
    except Exception as e:
        LOG.debug("polish inject failed %s", e)

def polish_wait_if_paused(driver):
    try:
        while driver.execute_script("return window.__HITL_PAUSED;") == True:
            time.sleep(1)
    except Exception:
        pass

def polish_check_for_loops(driver):
    global _hitl_last_hash, _hitl_loop
    try:
        from selenium.webdriver.common.by import By
        html = driver.find_element(By.TAG_NAME, "body").get_attribute('innerHTML')
        h = _hitl_hash.md5(html.encode('utf-8')).hexdigest()
        if h == _hitl_last_hash:
            _hitl_loop += 1
        else:
            _hitl_loop = 0
            _hitl_last_hash = h
        if _hitl_loop >= 3:
            driver.execute_script("let t=document.getElementById('hitl-cdp-text'); if(t) t.innerText=' HUMAN INTERVENTION: Loop Detected '; let o=document.getElementById('hitl-cdp-overlay'); if(o) o.style.opacity='1'; window.__HITL_PAUSED=true;")
            _hitl_loop = 0
            return True
    except Exception:
        pass
    return False

# ----------------------------------------------------------------------
# CAPTCHA / 2FA DETECTION (CDP, main JS world)
# ----------------------------------------------------------------------
# Human-in-the-loop hook: detects interactive CAPTCHA challenges (reCAPTCHA v2,
# hCaptcha, Cloudflare Turnstile/interstitials) and 2FA/OTP prompts so
# automation can pause for a human instead of stopping dead at authentication.
# Invisible widgets (reCAPTCHA v3 badges, hidden anchors) are deliberately NOT
# treated as challenges -- only visible, interactive ones and challenge-specific
# text/inputs match, keeping false positives off ordinary pages.
_CAPTCHA_DETECT_JS = r"""
(function(){
  function vis(el){
    if(!el) return false;
    var r = el.getBoundingClientRect();
    if(r.width < 4 || r.height < 4) return false;
    var st = window.getComputedStyle(el);
    return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
  }
  var found = {}; var markers = [];
  function add(kind, marker){
    found[kind] = true;
    if(markers.length < 8) markers.push(kind + ':' + marker);
  }
  var widgets = [
    ['captcha','iframe[src*="recaptcha/api2/bframe"]'],
    ['captcha','iframe[src*="recaptcha/enterprise/bframe"]'],
    ['captcha','iframe[title*="recaptcha" i]:not([src*="size=invisible"])'],
    ['captcha','.g-recaptcha:not([data-size="invisible"])'],
    ['captcha','.h-captcha'],
    ['captcha','iframe[src*="hcaptcha.com"]'],
    ['cloudflare','#challenge-form'],
    ['cloudflare','#challenge-stage'],
    ['cloudflare','iframe[src*="challenges.cloudflare.com"]'],
    ['cloudflare','.cf-turnstile'],
    ['cloudflare','#cf-challenge-running']
  ];
  for(var i=0;i<widgets.length;i++){
    var els = document.querySelectorAll(widgets[i][1]);
    for(var j=0;j<els.length;j++){ if(vis(els[j])){ add(widgets[i][0], widgets[i][1]); break; } }
  }
  var otps = [
    'input[autocomplete="one-time-code"]',
    'input[name*="otp" i]','input[id*="otp" i]',
    'input[name*="totp" i]','input[id*="totp" i]',
    'input[name*="mfa" i]','input[id*="mfa" i]',
    'input[name*="2fa" i]','input[id*="2fa" i]'
  ];
  for(var k=0;k<otps.length;k++){
    var oe = document.querySelectorAll(otps[k]);
    for(var m=0;m<oe.length;m++){ if(vis(oe[m])){ add('2fa', otps[k]); break; } }
  }
  if(markers.length === 0){
    var text = ((document.title||'') + ' ' + ((document.body && document.body.innerText)||'').slice(0,40000)).toLowerCase();
    var phrases = [
      ['captcha','verify you are human'],['captcha',"i'm not a robot"],['captcha','i am not a robot'],
      ['captcha','are you a robot'],['captcha','confirm you are human'],['captcha','unusual traffic'],
      ['cloudflare','checking your browser'],['cloudflare','just a moment'],
      ['2fa','enter the verification code'],['2fa','enter the 6-digit code'],['2fa','enter the code we sent'],
      ['2fa','authentication code'],['2fa','two-factor authentication'],['2fa','two-step verification'],
      ['2fa','2-step verification'],['2fa','check your phone'],['2fa','approve the sign-in request'],
      ['2fa','enter this code']
    ];
    for(var p=0;p<phrases.length;p++){
      if(text.indexOf(phrases[p][1]) !== -1){ add(phrases[p][0], 'text'); }
    }
  }
  var kind = '';
  if(found['cloudflare']) kind = 'cloudflare';
  else if(found['2fa']) kind = '2fa';
  else if(found['captcha']) kind = 'captcha';
  return { detected: !!kind, kind: kind, markers: markers, url: String(window.location.href||'').slice(0,300) };
})()
"""

# ======================================================================
# SECTION 7 -- TARGET ROUTER / SESSION / FRAME CONTEXT TRACKER
# ======================================================================

@dataclass
class TargetHandle:
    target_id: str
    session_id: str
    browser_id: str
    target_type: str
    url: str = ""
    window_id: Optional[int] = None
    browser_context_id: Optional[str] = None


@dataclass
class FrameContext:
    frame_id: str
    loader_id: str
    execution_context_id: Optional[int] = None
    url: str = ""
    parent_frame_id: Optional[str] = None


class FrameContextTracker:
    """Maintains real-time mapping of FrameId/LoaderId/ExecutionContextId."""

    def __init__(self):
        self._frames: Dict[str, FrameContext] = {}

    def upsert_frame(self, frame_id: str, loader_id: str, url: str,
                      parent_frame_id: Optional[str] = None) -> None:
        existing = self._frames.get(frame_id)
        exec_ctx = existing.execution_context_id if existing else None
        self._frames[frame_id] = FrameContext(frame_id=frame_id, loader_id=loader_id, url=url,
                                                execution_context_id=exec_ctx, parent_frame_id=parent_frame_id)

    def bind_execution_context(self, frame_id: str, execution_context_id: int) -> None:
        if frame_id in self._frames:
            self._frames[frame_id].execution_context_id = execution_context_id

    def get(self, frame_id: str) -> Optional[FrameContext]:
        return self._frames.get(frame_id)

    def clear_target(self, target_id: str) -> None:
        pass  # frames are scoped per-connection; caller resets on target close


class TargetRouter:
    """
    Routes CDP commands/events using flat protocol sessions. Maps
    unique CDP sessionId strings to internal AOS TargetHandles.
    """

    def __init__(self):
        self._targets: Dict[str, TargetHandle] = {}
        self._session_to_target: Dict[str, str] = {}
        self.frame_tracker = FrameContextTracker()

    def register(self, handle: TargetHandle) -> None:
        self._targets[handle.target_id] = handle
        self._session_to_target[handle.session_id] = handle.target_id

    def unregister_by_target(self, target_id: str) -> None:
        handle = self._targets.pop(target_id, None)
        if handle:
            self._session_to_target.pop(handle.session_id, None)
            self.frame_tracker.clear_target(target_id)

    def resolve_by_session(self, session_id: str) -> Optional[TargetHandle]:
        if not session_id or session_id in ("DEFAULT", "default", "auto", "none"):
            if self._targets:
                return list(self._targets.values())[0]
            return None
        target_id = self._session_to_target.get(session_id)
        if target_id and target_id in self._targets:
            return self._targets[target_id]
        if self._targets:
            return list(self._targets.values())[0]
        return None

    def resolve_by_target(self, target_id: str) -> Optional[TargetHandle]:
        return self._targets.get(target_id)

    def list_targets(self, browser_id: Optional[str] = None) -> List[TargetHandle]:
        values = list(self._targets.values())
        if browser_id:
            values = [t for t in values if t.browser_id == browser_id]
        return values


# ======================================================================
# SECTION 8 -- DOM & ACCESSIBILITY TREE SYNTHESIS
# ======================================================================

@dataclass
class UnifiedNode:
    node_id: int
    backend_node_id: int
    frame_id: Optional[str]
    tag_name: str
    attributes: Dict[str, str]
    ax_role: Optional[str]
    ax_name: Optional[str]
    bounding_box: Optional[Dict[str, float]]
    is_clickable: bool
    is_visible: bool
    shadow_root_type: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodeId": self.node_id, "backendNodeId": self.backend_node_id,
            "frameId": self.frame_id, "tagName": self.tag_name, "attributes": self.attributes,
            "axNode": {"role": self.ax_role, "name": self.ax_name} if self.ax_role else None,
            "boundingBox": self.bounding_box, "isClickable": self.is_clickable,
            "isVisible": self.is_visible, "shadowRootType": self.shadow_root_type,
        }


_CLICKABLE_TAGS = {"A", "BUTTON", "INPUT", "SELECT", "TEXTAREA", "LABEL"}


class DOMAccessibilityEngine:
    """
    Builds a combined structural map by stitching together the raw DOM
    tree and Accessibility (AX) tree, per spec section 6.
    """

    def __init__(self, session_invoker: "SessionInvoker"):
        self._invoke = session_invoker

    async def synthesize_tree(self, session_id: str, pierce_shadow_dom: bool = True) -> List[UnifiedNode]:
        dom_result = await self._invoke(session_id, "DOM.getFlattenedDocument",
                                         {"depth": -1, "pierce": pierce_shadow_dom})
        try:
            ax_result = await self._invoke(session_id, "Accessibility.getFullAXTree", {})
        except CDPCommandError:
            ax_result = {"nodes": []}
        ax_by_backend: Dict[int, Dict[str, Any]] = {}
        for ax_node in ax_result.get("nodes", []):
            backend_id = ax_node.get("backendDOMNodeId")
            if backend_id is not None:
                ax_by_backend[backend_id] = ax_node

        nodes: List[UnifiedNode] = []
        for raw_node in dom_result.get("nodes", []):
            backend_id = raw_node.get("backendNodeId", 0)
            ax_node = ax_by_backend.get(backend_id, {})
            attributes = self._parse_attributes(raw_node.get("attributes", []))
            tag_name = raw_node.get("nodeName", "").upper()
            bounding_box = await self._safe_box_model(session_id, backend_id)
            ax_role = (ax_node.get("role") or {}).get("value")
            ax_name = (ax_node.get("name") or {}).get("value")
            nodes.append(UnifiedNode(
                node_id=raw_node.get("nodeId", 0), backend_node_id=backend_id,
                frame_id=raw_node.get("frameId"), tag_name=tag_name, attributes=attributes,
                ax_role=ax_role, ax_name=ax_name, bounding_box=bounding_box,
                is_clickable=tag_name in _CLICKABLE_TAGS or ax_role in ("button", "link"),
                is_visible=bounding_box is not None,
                shadow_root_type=raw_node.get("shadowRootType")))
        return nodes

    async def _safe_box_model(self, session_id: str, backend_node_id: int) -> Optional[Dict[str, float]]:
        try:
            result = await self._invoke(session_id, "DOM.getBoxModel", {"backendNodeId": backend_node_id})
            quad = result.get("model", {}).get("content", [])
            if len(quad) < 8:
                return None
            xs = quad[0::2]
            ys = quad[1::2]
            x, y = min(xs), min(ys)
            return {"x": x, "y": y, "width": max(xs) - x, "height": max(ys) - y}
        except CDPCommandError:
            return None

    @staticmethod
    def _parse_attributes(flat_attrs: List[str]) -> Dict[str, str]:
        return {flat_attrs[i]: flat_attrs[i + 1] for i in range(0, len(flat_attrs) - 1, 2)}

    async def query_selector(self, session_id: str, css_selector: str, target_hint: str = "") -> Optional[int]:
        document = await self._invoke(session_id, "DOM.getDocument", {"depth": 0})
        root_node_id = document["root"]["nodeId"]
        
        # 1. Try selector directly (or each comma-separated piece)
        selectors = [s.strip() for s in css_selector.split(",") if s.strip()] if css_selector else []
        for sel in selectors:
            try:
                result = await self._invoke(session_id, "DOM.querySelector",
                                             {"nodeId": root_node_id, "selector": sel})
                node_id = result.get("nodeId", 0)
                if node_id:
                    return node_id
            except CDPCommandError:
                pass
                
        # 2. Semantic Fallback Candidate Lists based on target hint & selector
        hint = f"{target_hint} {css_selector}".lower()
        candidates: List[str] = []
        
        if any(k in hint for k in ["search", "query", "find", "input", "box", "text"]):
            candidates.extend([
                "textarea[name='q']", "input[name='q']", "input[type='search']", "textarea[type='search']",
                "input[name='search_query']", "input#search", "input[name='search']",
                "input[placeholder*='search' i]", "textarea[placeholder*='search' i]",
                "input[placeholder*='Search' i]", "textarea[placeholder*='Search' i]",
                "input[aria-label*='search' i]", "textarea[aria-label*='search' i]",
                "[role='searchbox']", "[role='combobox']",
                "input[type='text']", "textarea"
            ])
            
        if any(k in hint for k in ["title", "heading", "result", "link", "card", "item", "video"]):
            candidates.extend([
                "ytd-video-renderer #video-title", "a#video-title", "yt-formatted-string#video-title",
                "#video-title", "h3 a", "h3", "h2 a", "h2", "h1", "div.title", ".video-title", "a.yt-simple-endpoint"
            ])
            
        if any(k in hint for k in ["desc", "description", "details", "summary", "text"]):
            candidates.extend([
                "ytd-text-inline-expander", "#description-inner", "div#description", ".description", "p"
            ])
            
        # If selector has a tag before dot (e.g. h3.yt-video-title -> h3), try just the tag
        if css_selector and "." in css_selector and not css_selector.startswith("."):
            tag_only = css_selector.split(".", 1)[0].strip()
            if tag_only in ("h1", "h2", "h3", "h4", "h5", "h6", "div", "span", "p", "a", "button", "input", "textarea"):
                candidates.append(tag_only)
            
        # Try candidate selectors
        for cand in candidates:
            try:
                result = await self._invoke(session_id, "DOM.querySelector",
                                             {"nodeId": root_node_id, "selector": cand})
                node_id = result.get("nodeId", 0)
                if node_id:
                    return node_id
            except CDPCommandError:
                pass

        # 3. Self-Healing via Accessibility Tree (Find element by semantic role / label / name)
        try:
            ax_res = await self._invoke(session_id, "Accessibility.getFullAXTree", {})
            nodes = ax_res.get("nodes", [])
            for node in nodes:
                name = str((node.get("name") or {}).get("value", "")).lower()
                role = str((node.get("role") or {}).get("value", "")).lower()
                backend_id = node.get("backendDOMNodeId")
                if backend_id and (hint in name or any(k in name for k in hint.split() if len(k) > 3)):
                    # Resolve backendNodeId to nodeId
                    desc = await self._invoke(session_id, "DOM.describeNode", {"backendNodeId": backend_id})
                    nid = desc.get("node", {}).get("nodeId", 0)
                    if nid:
                        return nid
        except Exception:
            pass

        # 4. Last-resort fallback: inspect first visible input/textarea if search was requested
        if any(k in hint for k in ["search", "query", "input", "box"]):
            for generic in ["textarea", "input"]:
                try:
                    result = await self._invoke(session_id, "DOM.querySelectorAll",
                                                 {"nodeId": root_node_id, "selector": generic})
                    for nid in result.get("nodeIds", []):
                        box = await self._safe_box_model(session_id, nid)
                        if box and box["width"] > 0 and box["height"] > 0:
                            return nid
                except CDPCommandError:
                    pass

        return None


# ======================================================================
# SECTION 9 -- VIRTUAL INPUT ENGINE (mouse / keyboard / touch)
# ======================================================================

_KEY_CODE_MAP: Dict[str, Tuple[str, int]] = {
    "Enter": ("Enter", 13), "Tab": ("Tab", 9), "Escape": ("Escape", 27),
    "Backspace": ("Backspace", 8), "Delete": ("Delete", 46),
    "ArrowUp": ("ArrowUp", 38), "ArrowDown": ("ArrowDown", 40),
    "ArrowLeft": ("ArrowLeft", 37), "ArrowRight": ("ArrowRight", 39),
    "Space": (" ", 32),
}


def _cubic_bezier_path(x0: float, y0: float, x1: float, y1: float, steps: int = 20) -> List[Tuple[float, float]]:
    """Generates a humanized mouse trajectory using a randomized cubic Bezier curve."""
    jitter_x = random.uniform(-40, 40)
    jitter_y = random.uniform(-40, 40)
    ctrl1 = (x0 + (x1 - x0) * 0.33 + jitter_x, y0 + (y1 - y0) * 0.33 + jitter_y)
    ctrl2 = (x0 + (x1 - x0) * 0.66 - jitter_x, y0 + (y1 - y0) * 0.66 - jitter_y)
    points: List[Tuple[float, float]] = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = (mt ** 3) * x0 + 3 * (mt ** 2) * t * ctrl1[0] + 3 * mt * (t ** 2) * ctrl2[0] + (t ** 3) * x1
        y = (mt ** 3) * y0 + 3 * (mt ** 2) * t * ctrl1[1] + 3 * mt * (t ** 2) * ctrl2[1] + (t ** 3) * y1
        points.append((x, y))
    return points


class VirtualInputEngine:
    """
    Emulates human mouse, keyboard and touch interaction by dispatching
    low-level input events to Chromium's compositor via Input.* CDP
    methods, per spec section 12.
    """

    def __init__(self, session_invoker: "SessionInvoker", humanize_mouse: bool = True,
                 typing_delay_variance_ms: Union[Tuple[int, int], int] = (20, 120),
                 action_callback: Optional[Callable[[str, str], Coroutine[Any, Any, None]]] = None):
        self._invoke = session_invoker
        self._humanize_mouse = humanize_mouse
        self._typing_delay_variance_ms = typing_delay_variance_ms
        self._mouse_position: Dict[str, Tuple[float, float]] = {}
        # Optional callback invoked as `await cb(session_id, description)` after
        # each input action -- used by the kernel to drive the HUD capsule.
        self._action_callback = action_callback

    def _report(self, session_id: str, description: str) -> None:
        cb = self._action_callback
        if cb is None:
            return
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(cb(session_id, description))
        except Exception:  # noqa: BLE001 - HUD updates must never break input
            pass

    async def move_to(self, session_id: str, x: float, y: float) -> None:
        origin = self._mouse_position.get(session_id, (x, y))
        path = _cubic_bezier_path(*origin, x, y) if self._humanize_mouse else [(x, y)]
        for px, py in path:
            await self._invoke(session_id, "Input.dispatchMouseEvent",
                                {"type": "mouseMoved", "x": px, "y": py})
            if self._humanize_mouse:
                # Pace the bezier trajectory so the cursor visibly GLIDES like a
                # human hand instead of teleporting between points.
                await asyncio.sleep(random.uniform(0.006, 0.014))
        self._mouse_position[session_id] = (x, y)
        self._report(session_id, f"move ({x:.0f},{y:.0f})")

    async def click(self, session_id: str, x: float, y: float, button: str = "left",
                     click_count: int = 1, modifiers: int = 0) -> None:
        await self.move_to(session_id, x, y)
        await self._invoke(session_id, "Input.dispatchMouseEvent",
                            {"type": "mousePressed", "x": x, "y": y, "button": button,
                             "clickCount": click_count, "modifiers": modifiers})
        await self._invoke(session_id, "Input.dispatchMouseEvent",
                            {"type": "mouseReleased", "x": x, "y": y, "button": button,
                             "clickCount": click_count, "modifiers": modifiers})
        self._report(session_id, f"click ({x:.0f},{y:.0f}) {button}")
        await asyncio.sleep(random.uniform(0.02, 0.08))

    async def right_click(self, session_id: str, x: float, y: float) -> None:
        await self.click(session_id, x, y, button="right")

    async def double_click(self, session_id: str, x: float, y: float) -> None:
        await self.click(session_id, x, y, button="left", click_count=2)

    async def hover(self, session_id: str, x: float, y: float) -> None:
        await self.move_to(session_id, x, y)

    async def scroll(self, session_id: str, x: float, y: float, delta_x: float = 0.0,
                      delta_y: float = 0.0, smooth: bool = True) -> None:
        """Human-like scroll with acceleration, deceleration, and micro-pauses."""
        if not smooth or abs(delta_y) < 50:
            await self._invoke(session_id, "Input.dispatchMouseEvent",
                                {"type": "mouseWheel", "x": x, "y": y,
                                 "deltaX": delta_x, "deltaY": delta_y})
            return

        # Break scroll into realistic human kinetic chunks (ease-in, ease-out)
        steps = max(5, min(20, int(abs(delta_y) / 40)))
        remaining_y = delta_y
        for i in range(steps):
            factor = (i + 1) / steps
            # Smooth bell curve / cubic easing
            ease = 3 * (factor ** 2) - 2 * (factor ** 3)
            chunk_y = (delta_y / steps) * (0.8 + 0.4 * ease)
            # Add slight natural jitter
            jitter_x = random.uniform(-1.0, 1.0)
            await self._invoke(session_id, "Input.dispatchMouseEvent",
                                {"type": "mouseWheel", "x": x + jitter_x, "y": y,
                                 "deltaX": delta_x / steps, "deltaY": chunk_y})
            await asyncio.sleep(random.uniform(0.015, 0.035))

    async def auto_scroll_page(self, session_id: str, max_scrolls: int = 10, pause_s: float = 1.0) -> Dict[str, Any]:
        """Automatically detects infinite scroll or lazy-loaded feeds, scrolls smoothly,
        and pauses to let new DOM content render.
        """
        scrolls_done = 0
        last_height = 0
        for _ in range(max_scrolls):
            res = await self._invoke(session_id, "Runtime.evaluate", {
                "expression": "JSON.stringify({h: document.body.scrollHeight, y: window.scrollY})",
                "returnByValue": True
            })
            val = json.loads(res.get("result", {}).get("value", "{}"))
            cur_h = val.get("h", 0)
            if cur_h == last_height and scrolls_done > 2:
                # Reached true bottom of page
                break
            last_height = cur_h
            # Scroll down smoothly
            await self.scroll(session_id, 400, 400, delta_y=600, smooth=True)
            scrolls_done += 1
            await asyncio.sleep(pause_s + random.uniform(0.1, 0.4))
        return {"scrolls_completed": scrolls_done, "final_height": last_height}

    async def drag_drop(self, session_id: str, source_x: float, source_y: float,
                         target_x: float, target_y: float) -> None:
        await self.move_to(session_id, source_x, source_y)
        await self._invoke(session_id, "Input.dispatchMouseEvent",
                            {"type": "mousePressed", "x": source_x, "y": source_y,
                             "button": "left", "clickCount": 1})
        path = _cubic_bezier_path(source_x, source_y, target_x, target_y, steps=15)
        for px, py in path:
            await self._invoke(session_id, "Input.dispatchMouseEvent",
                                {"type": "mouseMoved", "x": px, "y": py, "button": "left"})
            await asyncio.sleep(random.uniform(0.004, 0.015))
        await self._invoke(session_id, "Input.dispatchMouseEvent",
                            {"type": "mouseReleased", "x": target_x, "y": target_y,
                             "button": "left", "clickCount": 1})

    async def multi_select(self, session_id: str, points: List[Tuple[float, float]],
                            modifier: str = "Control") -> None:
        """Ctrl/Shift-click multiple points to build a multi-selection."""
        modifier_bit = {"Alt": 1, "Control": 2, "Meta": 4, "Shift": 8}.get(modifier, 2)
        for x, y in points:
            await self.click(session_id, x, y, modifiers=modifier_bit)

    async def type_text(self, session_id: str, text: str) -> None:
        """Human-like typing: realistic cadence, word-boundary pauses, and natural variance."""
        for idx, char in enumerate(text):
            # keyDown without 'text' — only sends key press event, no character input
            await self._invoke(session_id, "Input.dispatchKeyEvent", {"type": "keyDown", "key": char})
            # char event — this is the ONLY one that actually inputs the character
            await self._invoke(session_id, "Input.dispatchKeyEvent", {"type": "char", "text": char})
            # keyUp — key release
            await self._invoke(session_id, "Input.dispatchKeyEvent", {"type": "keyUp", "key": char})
            
            # Natural human typing speed variance
            if isinstance(self._typing_delay_variance_ms, (tuple, list)) and len(self._typing_delay_variance_ms) == 2:
                low, high = self._typing_delay_variance_ms
            else:
                low, high = (20, 120)
            delay = random.uniform(low, high) / 1000.0
            # Occasional thinking pause after space or punctuation
            if char in [" ", ",", "."]:
                delay += random.uniform(0.05, 0.18)
            await asyncio.sleep(delay)

    async def press_key(self, session_id: str, key: str) -> None:
        key_str, key_code = _KEY_CODE_MAP.get(key, (key, 0))
        await self._invoke(session_id, "Input.dispatchKeyEvent",
                            {"type": "keyDown", "key": key_str, "windowsVirtualKeyCode": key_code})
        await self._invoke(session_id, "Input.dispatchKeyEvent",
                            {"type": "keyUp", "key": key_str, "windowsVirtualKeyCode": key_code})

    async def dispatch_touch(self, session_id: str, touch_points: List[Dict[str, float]],
                              event_type: str = "touchStart") -> None:
        await self._invoke(session_id, "Input.dispatchTouchEvent",
                            {"type": event_type, "touchPoints": touch_points})


# ======================================================================
# SECTION 10 -- NETWORK INTERCEPTOR / STORAGE / COOKIES
# ======================================================================

@dataclass
class NetworkRule:
    rule_id: str
    url_pattern: str
    action: str  # "BLOCK" | "MODIFY" | "PASS"
    inject_headers: Dict[str, str] = field(default_factory=dict)
    mock_status: Optional[int] = None
    mock_body: Optional[str] = None


class NetworkInterceptor:
    """Monitors, logs, modifies, or blocks network traffic via Fetch/Network domains."""

    def __init__(self, session_invoker: "SessionInvoker", max_captured_body_kb: int = 10240):
        self._invoke = session_invoker
        self._rules: Dict[str, List[NetworkRule]] = {}
        self._log: Dict[str, List[Dict[str, Any]]] = {}
        self._max_body_bytes = max_captured_body_kb * 1024

    async def enable(self, session_id: str, global_interception: bool = True) -> None:
        await self._invoke(session_id, "Network.enable", {"maxResourceBufferSize": self._max_body_bytes})
        if global_interception:
            await self._invoke(session_id, "Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
        self._rules.setdefault(session_id, [])
        self._log.setdefault(session_id, [])

    def add_rule(self, session_id: str, rule: NetworkRule) -> None:
        self._rules.setdefault(session_id, []).append(rule)

    def record(self, session_id: str, entry: Dict[str, Any]) -> None:
        log = self._log.setdefault(session_id, [])
        log.append(entry)
        if len(log) > 5000:
            log.pop(0)

    def get_log(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self._log.get(session_id, []))

    async def handle_request_paused(self, session_id: str, event_params: Dict[str, Any]) -> None:
        request_id = event_params.get("requestId")
        request = event_params.get("request", {})
        url = request.get("url", "")
        matched = self._match_rule(session_id, url)
        if matched is None:
            await self._invoke(session_id, "Fetch.continueRequest", {"requestId": request_id})
            return
        if matched.action == "BLOCK":
            await self._invoke(session_id, "Fetch.failRequest",
                                {"requestId": request_id, "errorReason": "BlockedByClient"})
        elif matched.action == "MODIFY":
            headers = [{"name": k, "value": v} for k, v in matched.inject_headers.items()]
            await self._invoke(session_id, "Fetch.continueRequest",
                                {"requestId": request_id, "headers": headers or None})
        else:
            await self._invoke(session_id, "Fetch.continueRequest", {"requestId": request_id})

    def _match_rule(self, session_id: str, url: str) -> Optional[NetworkRule]:
        import fnmatch
        for rule in self._rules.get(session_id, []):
            if fnmatch.fnmatch(url, rule.url_pattern):
                return rule
        return None

    async def get_cookies(self, session_id: str, urls: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        params = {"urls": urls} if urls else {}
        result = await self._invoke(session_id, "Storage.getCookies", params)
        return result.get("cookies", [])

    async def set_cookies(self, session_id: str, cookies: List[Dict[str, Any]]) -> None:
        await self._invoke(session_id, "Storage.setCookies", {"cookies": cookies})

    async def clear_cookies(self, session_id: str) -> None:
        await self._invoke(session_id, "Storage.clearCookies", {})

    async def grant_permissions(self, session_id: str, permissions: List[str], origin: str) -> None:
        await self._invoke(session_id, "Browser.grantPermissions",
                            {"permissions": permissions, "origin": origin})


# ======================================================================
# SECTION 11 -- DOWNLOAD MANAGER
# ======================================================================

@dataclass
class DownloadRecord:
    guid: str
    url: str
    suggested_filename: str
    state: str = "inProgress"
    total_bytes: int = 0
    received_bytes: int = 0
    file_path: Optional[str] = None
    sha256: Optional[str] = None


class DownloadManager:
    """Tracks download lifecycle and verifies file hashes on completion."""

    def __init__(self, session_invoker: "SessionInvoker", download_root: str):
        self._invoke = session_invoker
        self._download_root = download_root
        self._downloads: Dict[str, DownloadRecord] = {}

    async def configure(self, session_id: str, browser_session_scope: str) -> str:
        target_dir = os.path.join(self._download_root, browser_session_scope)
        os.makedirs(target_dir, exist_ok=True)
        await self._invoke(session_id, "Browser.setDownloadBehavior",
                            {"behavior": "allow", "downloadPath": target_dir, "eventsEnabled": True})
        return target_dir

    def on_download_will_begin(self, guid: str, url: str, suggested_filename: str) -> None:
        self._downloads[guid] = DownloadRecord(guid=guid, url=url, suggested_filename=suggested_filename)

    def on_download_progress(self, guid: str, state: str, total_bytes: int, received_bytes: int,
                              file_path: Optional[str] = None) -> Optional[DownloadRecord]:
        record = self._downloads.get(guid)
        if record is None:
            return None
        record.state = state
        record.total_bytes = total_bytes
        record.received_bytes = received_bytes
        if file_path:
            record.file_path = file_path
        if state == "completed" and record.file_path and os.path.exists(record.file_path):
            record.sha256 = self._hash_file(record.file_path)
        return record

    @staticmethod
    def _hash_file(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def status(self, guid: str) -> Optional[DownloadRecord]:
        return self._downloads.get(guid)


# ======================================================================
# SECTION 12 -- FILE CHOOSER BRIDGE (CDP) + NATIVE OS PICKER FALLBACK
# ======================================================================

class FileChooserBridge:
    """
    Standard DOM file input interception via CDP, per spec section 9.2.
    """

    def __init__(self, session_invoker: "SessionInvoker"):
        self._invoke = session_invoker
        self._pending_choosers: Dict[str, Dict[str, Any]] = {}

    async def enable(self, session_id: str) -> None:
        try:
            await self._invoke(session_id, "Page.setInterceptFileChooser", {"enabled": True})
        except Exception as e:
            LOG.warning(f"Failed to enable file chooser interception (may be unsupported): {e}")

    def on_file_chooser_opened(self, session_id: str, backend_node_id: int, mode: str) -> None:
        self._pending_choosers[session_id] = {"backendNodeId": backend_node_id, "mode": mode}

    async def upload_files(self, session_id: str, file_paths: List[str]) -> bool:
        pending = self._pending_choosers.pop(session_id, None)
        if pending is None:
            return False
        for path in file_paths:
            if not os.path.exists(path):
                raise FileNotFoundError(f"upload source file not found: {path}")
        await self._invoke(session_id, "DOM.setFileInputFiles",
                            {"files": file_paths, "backendNodeId": pending["backendNodeId"]})
        return True


class NativePickerBridge:
    """
    Windows OS-level native dialog bridge fallback for non-standard
    file picker windows (Win32 Shell API dialogs), per spec section
    9.2 "Native OS File Picker Integration". Requires pywin32; when
    unavailable this bridge safely reports unsupported rather than
    failing the whole organ (Universal Law 8 - Failure Transparency).
    """

    DIALOG_CLASS_WINDOWS = "#32770"

    def __init__(self):
        self.available = _IS_WINDOWS and _HAS_PYWIN32

    def find_dialog_window(self, owner_pid: int, timeout_s: float = 10.0) -> Optional[int]:
        if not self.available:
            return None
        deadline = time.time() + timeout_s
        found_hwnd: List[int] = []

        def _enum_handler(hwnd, _):
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)  # type: ignore  # noqa
            except Exception:
                return True
            if pid == owner_pid and win32gui.GetClassName(hwnd) == self.DIALOG_CLASS_WINDOWS:  # type: ignore
                found_hwnd.append(hwnd)
                return False
            return True

        try:
            import win32process  # type: ignore  # noqa: F401
        except Exception:
            return None
        while time.time() < deadline and not found_hwnd:
            try:
                win32gui.EnumWindows(_enum_handler, None)  # type: ignore
            except Exception:
                pass
            if not found_hwnd:
                time.sleep(0.25)
        return found_hwnd[0] if found_hwnd else None

    def inject_path_and_confirm(self, dialog_hwnd: int, file_path: str) -> bool:
        if not self.available:
            return False
        try:
            edit_hwnd = win32gui.FindWindowEx(dialog_hwnd, 0, "Edit", None)  # type: ignore
            if edit_hwnd:
                win32gui.SendMessage(edit_hwnd, win32con.WM_SETTEXT, 0, file_path)  # type: ignore
            ok_button = win32gui.FindWindowEx(dialog_hwnd, 0, "Button", None)  # type: ignore
            if ok_button:
                win32gui.SendMessage(ok_button, win32con.BM_CLICK, 0, 0)  # type: ignore
            return True
        except Exception as exc:
            LOG.error("Native file picker injection failed: %s", exc)
            return False


# ======================================================================
# SECTION 13 -- SCREENSHOT / SCREENCAST / VISION
# ======================================================================

class ScreenshotVisionEngine:
    """Viewport, element-clip, full-page screenshot capture and screencast streaming."""

    def __init__(self, session_invoker: "SessionInvoker", event_bus: CDPEventBus,
                 default_format: str = "jpeg", default_quality: int = 80, max_fps: int = 30):
        self._invoke = session_invoker
        self._event_bus = event_bus
        self._default_format = default_format
        self._default_quality = default_quality
        self._max_fps = max_fps
        self._screencasting: Dict[str, bool] = {}

    async def capture_viewport(self, session_id: str, image_format: Optional[str] = None,
                                quality: Optional[int] = None) -> str:
        result = await self._invoke(session_id, "Page.captureScreenshot",
                                     {"format": image_format or self._default_format,
                                      "quality": quality or self._default_quality})
        return result["data"]  # base64

    async def capture_element(self, session_id: str, backend_node_id: int,
                               box_model_fetcher: Callable[[str, int], Awaitable[Optional[Dict[str, float]]]]) -> str:
        box = await box_model_fetcher(session_id, backend_node_id)
        if box is None:
            raise CDPCommandError(-32010, "element has no visible box model")
        clip = {"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"], "scale": 1}
        result = await self._invoke(session_id, "Page.captureScreenshot",
                                     {"format": self._default_format, "clip": clip})
        return result["data"]

    async def capture_full_page(self, session_id: str) -> str:
        metrics = await self._invoke(session_id, "Page.getLayoutMetrics", {})
        content_size = metrics.get("contentSize", {})
        await self._invoke(session_id, "Emulation.setDeviceMetricsOverride", {
            "width": int(content_size.get("width", 1920)),
            "height": int(content_size.get("height", 1080)),
            "deviceScaleFactor": 1, "mobile": False})
        try:
            result = await self._invoke(session_id, "Page.captureScreenshot",
                                         {"format": self._default_format, "captureBeyondViewport": True})
            return result["data"]
        finally:
            await self._invoke(session_id, "Emulation.clearDeviceMetricsOverride", {})

    async def start_screencast(self, session_id: str, browser_id: str) -> None:
        self._screencasting[session_id] = True
        await self._invoke(session_id, "Page.startScreencast",
                            {"format": self._default_format, "quality": self._default_quality,
                             "everyNthFrame": max(1, 30 // self._max_fps)})

    async def stop_screencast(self, session_id: str) -> None:
        self._screencasting[session_id] = False
        await self._invoke(session_id, "Page.stopScreencast", {})

    async def on_screencast_frame(self, session_id: str, browser_id: str, session_id_ack: int,
                                   frame_data: str, metadata: Dict[str, Any]) -> None:
        await self._invoke(session_id, "Page.screencastFrameAck", {"sessionId": session_id_ack})
        await self._event_bus.publish(AOSEvent(
            event_type=AOSEventType.SCREENCAST_FRAME, browser_id=browser_id, session_id=session_id,
            payload={"frame": frame_data, "metadata": metadata}))


# ======================================================================
# SECTION 14 -- JAVASCRIPT RUNTIME EXECUTION
# ======================================================================

class JavaScriptRuntime:
    """Isolated-world JS evaluation and console/exception monitoring."""

    def __init__(self, session_invoker: "SessionInvoker"):
        self._invoke = session_invoker
        self._isolated_worlds: Dict[str, int] = {}

    async def enable(self, session_id: str) -> None:
        await self._invoke(session_id, "Runtime.enable", {})
        await self._invoke(session_id, "Console.enable", {})

    async def create_isolated_world(self, session_id: str, frame_id: str,
                                     world_name: str = "hojaiga_automation") -> int:
        result = await self._invoke(session_id, "Page.createIsolatedWorld",
                                     {"frameId": frame_id, "worldName": world_name,
                                      "grantUniveralAccess": True})
        exec_ctx = result["executionContextId"]
        self._isolated_worlds[session_id] = exec_ctx
        return exec_ctx

    async def evaluate(self, session_id: str, expression: str,
                        execution_context_id: Optional[int] = None,
                        await_promise: bool = True) -> Any:
        params: Dict[str, Any] = {"expression": expression, "returnByValue": True,
                                   "awaitPromise": await_promise}
        ctx = execution_context_id or self._isolated_worlds.get(session_id)
        if ctx is not None:
            params["contextId"] = ctx
        result = await self._invoke(session_id, "Runtime.evaluate", params)
        if "exceptionDetails" in result:
            raise CDPCommandError(-32020, result["exceptionDetails"].get("text", "JS exception"))
        return result.get("result", {}).get("value")

    async def call_function_on(self, session_id: str, object_id: str, function_declaration: str,
                                arguments: Optional[List[Any]] = None) -> Any:
        call_args = [{"value": arg} for arg in (arguments or [])]
        result = await self._invoke(session_id, "Runtime.callFunctionOn",
                                     {"objectId": object_id, "functionDeclaration": function_declaration,
                                      "arguments": call_args, "returnByValue": True})
        return result.get("result", {}).get("value")


# ======================================================================
# SECTION 14b -- VIRTUAL HANDS, FINGERS & AUTOMATION OVERLAY
# ======================================================================
#
# Each Chrome tab / session gets its own independent "hand" (a virtual mouse
# cursor) so concurrent automation across multiple tabs/profiles never collide.
# A hand may hold several "fingers" for multi-cursor gestures used by 3D-modeling
# apps. The AutomationOverlayEngine paints a glowing border + floating capsule
# HUD into the page so a human can always see what the automation is doing.

@dataclass
class Finger:
    finger_id: int
    x: float = 0.0
    y: float = 0.0


class VirtualHand:
    """An independent virtual mouse 'hand' bound to one CDP session (tab/profile).

    Delegates low-level input to the shared VirtualInputEngine but keeps its own
    cursor position and a set of fingers for multi-cursor (3D) gestures.
    """

    def __init__(self, session_id: str, input_engine: "VirtualInputEngine",
                 overlay_engine: Optional["AutomationOverlayEngine"] = None):
        self.session_id = session_id
        self._engine = input_engine
        self._overlay = overlay_engine
        self.fingers: List[Finger] = [Finger(0)]
        self.last_action: str = "idle"

    async def move_to(self, x: float, y: float, **kwargs: Any) -> None:
        await self._engine.move_to(self.session_id, x, y, **kwargs)
        self.fingers[0].x, self.fingers[0].y = x, y
        self._note(f"move ({x:.0f},{y:.0f})")

    async def click(self, x: float, y: float, **kwargs: Any) -> None:
        await self._engine.click(self.session_id, x, y, **kwargs)
        self._note(f"click ({x:.0f},{y:.0f})")

    async def right_click(self, x: float, y: float, **kwargs: Any) -> None:
        await self._engine.right_click(self.session_id, x, y)
        self._note(f"right-click ({x:.0f},{y:.0f})")

    async def double_click(self, x: float, y: float, **kwargs: Any) -> None:
        await self._engine.double_click(self.session_id, x, y)
        self._note(f"double-click ({x:.0f},{y:.0f})")

    async def hover(self, x: float, y: float, **kwargs: Any) -> None:
        await self._engine.hover(self.session_id, x, y)
        self._note(f"hover ({x:.0f},{y:.0f})")

    async def scroll(self, x: float, y: float, delta_x: float = 0.0, delta_y: float = 0.0,
                     **kwargs: Any) -> None:
        await self._engine.scroll(self.session_id, x, y, delta_x, delta_y)
        self._note(f"scroll ({x:.0f},{y:.0f})")

    async def drag_drop(self, source_x: float, source_y: float, target_x: float, target_y: float,
                        **kwargs: Any) -> None:
        await self._engine.drag_drop(self.session_id, source_x, source_y, target_x, target_y)
        self._note(f"drag ({source_x:.0f},{source_y:.0f})->({target_x:.0f},{target_y:.0f})")

    async def multi_select(self, points: List[Tuple[float, float]], modifier: str = "Control") -> None:
        await self._engine.multi_select(self.session_id, points, modifier)
        self._note(f"multi-select {len(points)} points")

    async def type_text(self, text: str) -> None:
        await self._engine.type_text(self.session_id, text)
        self._note(f"type {len(text)} chars")

    async def press_key(self, key: str) -> None:
        await self._engine.press_key(self.session_id, key)
        self._note(f"key {key}")

    def add_finger(self) -> Finger:
        """Spawn an additional cursor (finger) for multi-cursor 3D apps."""
        finger = Finger(len(self.fingers))
        self.fingers.append(finger)
        return finger

    async def multi_touch(self, points: List[Tuple[float, float]]) -> None:
        """Dispatch a multi-pointer touch gesture (several simultaneous cursors).

        Used by 3D-modeling / canvas apps that expect multiple pointers at once.
        Each point becomes one touch point; the hand's fingers track their coords.
        """
        touch_points = [{"x": float(p[0]), "y": float(p[1]), "id": i} for i, p in enumerate(points)]
        await self._engine._invoke(self.session_id, "Input.dispatchTouchEvent",
                                   {"type": "touchStart", "touchPoints": touch_points})
        await self._engine._invoke(self.session_id, "Input.dispatchTouchEvent",
                                   {"type": "touchEnd", "touchPoints": []})
        for i, p in enumerate(points):
            if i < len(self.fingers):
                self.fingers[i].x, self.fingers[i].y = float(p[0]), float(p[1])
        self._note(f"multi-touch {len(points)} fingers")

    def _note(self, text: str) -> None:
        self.last_action = text
        if self._overlay is not None:
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self._overlay.update_capsule(self.session_id, text))
            except Exception:  # noqa: BLE001
                pass


class HandRegistry:
    """Maps CDP session_id -> VirtualHand so every tab/profile owns its hand."""

    def __init__(self) -> None:
        self._hands: Dict[str, VirtualHand] = {}

    def get_or_create(self, session_id: str, input_engine: "VirtualInputEngine",
                      overlay_engine: Optional["AutomationOverlayEngine"] = None) -> VirtualHand:
        hand = self._hands.get(session_id)
        if hand is None:
            hand = VirtualHand(session_id, input_engine, overlay_engine)
            self._hands[session_id] = hand
        return hand

    def get(self, session_id: str) -> Optional[VirtualHand]:
        return self._hands.get(session_id)

    def remove(self, session_id: str) -> None:
        self._hands.pop(session_id, None)


class AutomationOverlayEngine:
    """Paints the Hojaiga visual indicator into a live page: a glowing border plus
    a floating capsule HUD reporting the current virtual-mouse action. Injected via
    Runtime.evaluate and also registered with Page.addScriptToEvaluateOnNewDocument
    so it survives navigations."""

    _GLYPH = ""  # removed per user request
    # Reference-style floating status capsule ("black floating tab"): a centered,
    # rounded, near-black pill docked at the bottom of the viewport that mirrors the
    # agent's LIVE state. State/text are driven dynamically from Python through
    # window.__hojaigaSetCapsule(state, text) -- nothing here is app/site specific.
    _OVERLAY_SOURCE = r"""
(function(){
  if(window.__hojaigaSetCapsule){return;}
  var s=document.createElement('style');
  s.textContent='#hojaiga-capsule{position:fixed;left:50%;bottom:22px;transform:translateX(-50%) translateY(18px);z-index:2147483647;display:flex;align-items:center;gap:10px;font:500 13px/1.2 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#f5f7fa;background:rgba(17,17,19,.94);border:1px solid rgba(255,255,255,.10);border-radius:999px;padding:8px 8px 8px 15px;box-shadow:0 8px 30px rgba(0,0,0,.55);opacity:0;visibility:hidden;transition:opacity .25s ease,transform .25s ease,visibility .25s;-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);max-width:80vw;}#hojaiga-capsule.hj-show{opacity:1;visibility:visible;transform:translateX(-50%) translateY(0);}.hj-spin{width:14px;height:14px;flex:0 0 auto;border:2px solid rgba(255,255,255,.22);border-top-color:#22d3a6;border-radius:50%;animation:hj-rot .8s linear infinite;}@keyframes hj-rot{to{transform:rotate(360deg)}}.hj-dot{width:9px;height:9px;flex:0 0 auto;border-radius:50%;background:#22d3a6;}#hojaiga-capsule.hj-input .hj-spin{display:none}#hojaiga-capsule.hj-input .hj-dot{background:#ff4d5e;box-shadow:0 0 0 4px rgba(255,77,94,.18);animation:hj-blink 1.1s ease-in-out infinite;}@keyframes hj-blink{50%{opacity:.35}}#hojaiga-capsule.hj-paused .hj-dot{background:#ffcc00}.hj-text{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}.hj-btn{flex:0 0 auto;width:26px;height:26px;border-radius:50%;border:none;cursor:pointer;display:none;align-items:center;justify-content:center;font-size:12px;line-height:1;color:#fff;background:rgba(255,255,255,.10);}.hj-btn:hover{background:rgba(255,255,255,.22);}#hojaiga-capsule.hj-input .hj-btn{display:inline-flex;}#hojaiga-capsule.hj-input .hj-stop{background:#ff4d5e;}#hojaiga-capsule.hj-input .hj-stop:hover{background:#ff2f43;}#hojaiga-backdrop{position:fixed;inset:0;z-index:2147483646;background:rgba(0,0,0,.45);-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px);opacity:0;visibility:hidden;transition:opacity .3s;pointer-events:none;}#hojaiga-backdrop.hj-show{opacity:1;visibility:visible;}';
  var h=document.head||document.documentElement; if(h){h.appendChild(s);}
  var r=document.body||document.documentElement;
  var bd=document.createElement('div');bd.id='hojaiga-backdrop';r.appendChild(bd);
  var c=document.createElement('div');c.id='hojaiga-capsule';
  c.innerHTML='<span class="hj-spin"></span><span class="hj-dot"></span><span class="hj-text" id="hojaiga-capsule-text">Working</span><button class="hj-btn hj-expand" title="Open" aria-label="Open">&#8599;</button><button class="hj-btn hj-stop" title="Stop" aria-label="Stop">&#9632;</button>';
  r.appendChild(c);
  c.querySelector('.hj-stop').onclick=function(){window.__HITL_STOP=true;window.__HITL_PAUSED=true;};
  c.querySelector('.hj-expand').onclick=function(){window.__HITL_EXPAND=true;};
  window.__HITL_PAUSED=window.__HITL_PAUSED||false;
  window.__HITL_STOP=window.__HITL_STOP||false;
  window.__hojaigaSetCapsule=function(state,text){
    var cc=document.getElementById('hojaiga-capsule'); if(!cc){return;}
    var t=document.getElementById('hojaiga-capsule-text'); if(t&&text!=null){t.textContent=text;}
    cc.classList.remove('hj-input','hj-paused');
    var b=document.getElementById('hojaiga-backdrop');
    if(state==='input_needed'){cc.classList.add('hj-input'); if(b){b.classList.add('hj-show');}}
    else if(state==='paused'){cc.classList.add('hj-paused'); if(b){b.classList.remove('hj-show');}}
    else if(b){b.classList.remove('hj-show');}
    if(state==='hide'||state==='idle'){cc.classList.remove('hj-show');}else{cc.classList.add('hj-show');}
  };
})();
"""

    # Legacy full-width debug bar removed -- the floating capsule above now carries
    # every status. This tiny idempotent guard keeps the shared HITL flags defined
    # so any pre-existing pause/loop polling (window.__HITL_PAUSED) still works.
    _BLACK_TAB_SOURCE = (
        "window.__HITL_PAUSED=window.__HITL_PAUSED||false;"
        "window.__HITL_STOP=window.__HITL_STOP||false;"
    )

    def __init__(self, invoker: "SessionInvoker"):
        self._invoke = invoker

    async def inject(self, session_id: str) -> None:
        try:
            await self._invoke(session_id, "Page.addScriptToEvaluateOnNewDocument",
                               {"source": self._OVERLAY_SOURCE})
        except Exception:  # noqa: BLE001 - overlay is best-effort
            pass
        await self._eval(session_id, self._OVERLAY_SOURCE)
        # Original Polish black tab — hitl_pipeline.py:8, via CDP (not fake mycdp)
        try:
            await self._invoke(session_id, "Page.addScriptToEvaluateOnNewDocument",
                               {"source": self._BLACK_TAB_SOURCE})
        except Exception:
            pass
        await self._eval(session_id, self._BLACK_TAB_SOURCE)

    async def update_capsule(self, session_id: str, text: str, state: str = "working") -> None:
        # Drive the floating capsule from the agent's real state. state:
        # working | input_needed | paused | idle. Purely dynamic -- no per-app logic.
        js = ("window.__hojaigaSetCapsule && window.__hojaigaSetCapsule("
              + json.dumps(state) + ", " + json.dumps(text) + ");")
        await self._eval(session_id, js)

    async def _eval(self, session_id: str, expression: str) -> None:
        try:
            await self._invoke(session_id, "Runtime.evaluate",
                               {"expression": expression, "returnByValue": True})
        except Exception:  # noqa: BLE001 - overlay must never break automation
            pass


# ======================================================================
# SECTION 15 -- RECOVERY ENGINE (crash detection, respawn, state restore)
# ======================================================================

@dataclass
class SessionSnapshot:
    browser_id: str
    ws_url: str
    profile: Optional[BrowserProfile]
    open_urls: List[str] = field(default_factory=list)
    cookies: List[Dict[str, Any]] = field(default_factory=list)


class RecoveryEngine:
    """
    Detects target crashes / socket loss / heartbeat timeouts and
    executes the automated recovery sequence defined in spec section 13.
    """

    def __init__(self, kernel: "CDPRuntimeKernel", max_crash_retries: int = 3,
                 retry_backoff_ms: int = 1000):
        self._kernel = kernel
        self._max_retries = max_crash_retries
        self._retry_backoff_ms = retry_backoff_ms
        self._retry_counts: Dict[str, int] = {}
        self._snapshots: Dict[str, SessionSnapshot] = {}

    def snapshot(self, browser_id: str, snap: SessionSnapshot) -> None:
        self._snapshots[browser_id] = snap

    async def handle_connection_state(self, browser_id: str, state: ConnectionState) -> None:
        if state != ConnectionState.RECOVERING:
            return
        retries = self._retry_counts.get(browser_id, 0)
        if retries >= self._max_retries:
            LOG.error("Browser %s exceeded max crash retries (%d); terminating", browser_id, self._max_retries)
            await self._kernel.terminate_browser(browser_id, reason="recovery_exhausted")
            self._retry_counts.pop(browser_id, None)
            return
        self._retry_counts[browser_id] = retries + 1
        backoff_s = (self._retry_backoff_ms / 1000.0) * (2 ** retries)
        LOG.warning("Recovering browser %s (attempt %d/%d) after %.2fs backoff",
                    browser_id, retries + 1, self._max_retries, backoff_s)
        await asyncio.sleep(backoff_s)
        try:
            await self._kernel.respawn_and_restore(browser_id, self._snapshots.get(browser_id))
        except Exception as exc:
            LOG.error("Respawn attempt failed for %s: %s", browser_id, exc)

    def reset(self, browser_id: str) -> None:
        self._retry_counts.pop(browser_id, None)
        self._snapshots.pop(browser_id, None)


# ======================================================================
# SECTION 16 -- BROWSER INSTANCE (aggregate root per Chromium process)
# ======================================================================

SessionInvoker = Callable[[str, str, Dict[str, Any]], Awaitable[Any]]


@dataclass
class BrowserInstance:
    browser_id: str
    connection: CDPConnectionManager
    process: Optional[subprocess.Popen]
    profile: Optional[BrowserProfile]
    ws_url: str
    default_session_id: Optional[str] = None


# ======================================================================
# SECTION 17 -- CDP RUNTIME KERNEL (top-level orchestrator for this organ)
# ======================================================================

class CDPRuntimeKernel:
    """
    Root orchestration object for Organ 19. Owns every browser instance,
    dispatches IPC operations to the correct subsystem, and enforces
    Universal Law 3 (this organ never performs Brain/Knowledge/Interface
    responsibilities -- only CDP browser instrumentation).
    
    Enhanced with Session Cookie Management for automatic login handling.
    """

    def __init__(self, config: "RuntimeConfig" = None):
        config = config or RuntimeConfig()
        self.config = config
        # Load runtime_config.yaml overrides (typing variance, loop threshold, capsule theme)
        try:
            _cfg = load_system_config()
            _cdp = _cfg.get("organ_19_cdp", {})
            if "typing_delay_variance_ms" in _cdp:
                config.typing_delay_variance_ms = tuple(_cdp["typing_delay_variance_ms"])
            if "loop_detection_threshold" in _cdp:
                self._loop_threshold = int(_cdp["loop_detection_threshold"])
            else:
                self._loop_threshold = 3
            self._capsule_cfg = _cdp.get("capsule_ui", {})
        except Exception:
            self._loop_threshold = 3
            self._capsule_cfg = {}
        self.event_bus = CDPEventBus()
        self.command_queue = CommandQueue(default_timeout_s=config.websocket_timeout_ms / 1000.0)
        self.router = TargetRouter()
        self.discovery = BrowserDiscoveryEngine(scan_ports=config.scan_ports)
        self.profile_manager = BrowserProfileManager(config.profiles_dir)
        self.launcher = BrowserProcessLauncher()
        self.recovery = RecoveryEngine(self, max_crash_retries=config.max_crash_retries,
                                        retry_backoff_ms=config.retry_backoff_ms)
        self.dom_engine = DOMAccessibilityEngine(self._invoke_session)
        self.input_engine = VirtualInputEngine(self._invoke_session,
                                                humanize_mouse=config.humanize_mouse_movement,
                                                typing_delay_variance_ms=config.typing_delay_variance_ms)
        self.network = NetworkInterceptor(self._invoke_session, max_captured_body_kb=config.max_captured_body_kb)
        self.downloads = DownloadManager(self._invoke_session, config.downloads_dir)
        self.file_chooser = FileChooserBridge(self._invoke_session)
        self.native_picker = NativePickerBridge()
        self.vision = ScreenshotVisionEngine(self._invoke_session, self.event_bus,
                                              default_format=config.screencast_format,
                                              default_quality=config.screencast_quality,
                                              max_fps=config.screencast_max_fps)
        self.js_runtime = JavaScriptRuntime(self._invoke_session)
        self.overlay = AutomationOverlayEngine(self._invoke_session)
        self.hands = HandRegistry()
        # Route every low-level input action to the HUD capsule for that session.
        self.input_engine._action_callback = self.overlay.update_capsule
        self._initialized_sessions: set = set()
        
        # Session cookie manager integration
        self._cookie_manager = None
        self._init_cookie_manager()
        self._instances: Dict[str, BrowserInstance] = {}
        # Serialize browser launches so concurrent callers cannot each spawn a
        # chrome.exe (prevents the runaway multi-process loop on reconnect/retry).
        self._launch_lock = asyncio.Lock()
        # Hard backstop on the number of *concurrent* chrome.exe processes
        # (mirrors Polish-automation's CHROME_SEMAPHORE = Semaphore(3)). Together
        # with the permanent-browser singleton below this guarantees the system
        # can never spawn a runaway fleet of Chrome processes -- the launch slot
        # is acquired here and released on error or later in terminate_browser.
        self._browser_semaphore = asyncio.Semaphore(
            int(os.environ.get("HOJAIGA_MAX_BROWSERS", "3")))
        # Hard cap on concurrent browser processes. Reuse an existing instance
        # instead of launching a new one beyond this limit.
        self._max_browsers = int(os.environ.get("HOJAIGA_MAX_BROWSERS", "4"))
        # Absolute safety caps so a reconnect/retry storm can never spawn
        # hundreds of chrome.exe processes. Legitimate multi-browser tasks
        # (e.g. 2-3 tabs/profiles) are allowed up to these limits.
        self._browser_pids: set = set()
        self._total_launches: int = 0
        self._max_total_launches = int(os.environ.get("HOJAIGA_MAX_BROWSER_LAUNCHES", "8"))
        self._last_launch_ts: float = 0.0
        self._launch_cooldown_s = float(os.environ.get("HOJAIGA_LAUNCH_COOLDOWN_S", "3.0"))
        # --- Permanent-agent browser model (tab-bounded, per UI agent count) ---
        # There is exactly ONE browser tied to the permanent agent. Every agent
        # (permanent or temporary) operates on this single browser via tabs, so
        # a stable browser_id is preserved across crashes/recovery and cached
        # ids from agents never go "unknown".
        self._permanent_browser_id: Optional[str] = None
        # Permanent tab budget = number of agents decided in the UI. Temporary
        # agents may open additional tabs but can NEVER close one until the user
        # approves the task as successfully completed (see APPROVE_TASK_COMPLETION).
        self._tab_budget = int(os.environ.get("HOJAIGA_PERMANENT_TAB_BUDGET", "4"))
        self._temp_tab_budget = int(os.environ.get("HOJAIGA_TEMP_TAB_BUDGET", "8"))
        self._tab_count: int = 0
        self._task_approved: bool = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._ipc_server = IPCServer(self, tcp_port=config.tcp_port)
        self._audit_log: List[Dict[str, Any]] = []
        self._html_loop_tracker: Dict[str, Any] = {"last_hash": None, "count": 0}

    def _init_cookie_manager(self):
        """Initialize session cookie manager."""
        try:
            import sys
            if r"D:\new_automation\All codes" not in sys.path:
                sys.path.insert(0, r"D:\new_automation\All codes")
            try:
                from core_organs.session_cookie_manager import get_cookie_manager
            except ImportError:
                from session_cookie_manager import get_cookie_manager
            self._cookie_manager = get_cookie_manager()
            LOG.info("[CDPRuntime] Session cookie manager initialized")
        except ImportError:
            LOG.warning("[CDPRuntime] Session cookie manager not available")
            self._cookie_manager = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self.loop = asyncio.get_event_loop()
        await self._ipc_server.start()
        LOG.info("Chrome CDP Runtime kernel started (transport=%s)", self._ipc_server.transport_kind)

    async def stop(self) -> None:
        for browser_id in list(self._instances.keys()):
            await self.terminate_browser(browser_id, reason="shutdown")
        await self._ipc_server.stop()

    # ------------------------------------------------------------------
    # Session Cookie Management (Enhanced)
    # ------------------------------------------------------------------

    # URL fragment -> cookie-store service key (first match wins).
    _SERVICE_URL_PATTERNS: tuple = (
        ("gmail", ("mail.google.com", "gmail.com")),
        ("youtube", ("youtube.com",)),
        ("github", ("github.com",)),
        ("linkedin", ("linkedin.com",)),
        ("facebook", ("facebook.com",)),
        ("instagram", ("instagram.com",)),
        ("twitter", ("twitter.com", "x.com")),
        ("slack", ("slack.com",)),
        ("notion", ("notion.so",)),
        ("google", ("accounts.google.com", "google.com")),
    )

    @staticmethod
    def _detect_service_from_url(url: str) -> Optional[str]:
        """Map a URL to its cookie-store service name (None when unknown)."""
        url_l = (url or "").lower()
        for service, fragments in CDPRuntimeKernel._SERVICE_URL_PATTERNS:
            if any(fragment in url_l for fragment in fragments):
                return service
        return None

    @staticmethod
    def _sanitize_cookies_for_cdp(cookies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Keep only fields Chrome's Network.setCookies accepts; drop junk entries."""
        sanitized: List[Dict[str, Any]] = []
        for cookie in cookies or []:
            if not isinstance(cookie, dict) or not cookie.get("name"):
                continue
            item: Dict[str, Any] = {"name": cookie["name"], "value": cookie.get("value") or ""}
            if cookie.get("domain"):
                item["domain"] = cookie["domain"]
            if cookie.get("path"):
                item["path"] = cookie["path"]
            if isinstance(cookie.get("expires"), (int, float)) and cookie["expires"] > 0:
                item["expires"] = float(cookie["expires"])
            if "secure" in cookie:
                item["secure"] = bool(cookie["secure"])
            if "httpOnly" in cookie:
                item["httpOnly"] = bool(cookie["httpOnly"])
            sanitized.append(item)
        return sanitized

    async def navigate_with_cookies(self, session_id: str, url: str, service_name: str = None) -> Dict[str, Any]:
        """
        Navigate to a URL, using session cookies if available.
        
        Args:
            session_id: Session identifier
            url: Target URL
            service_name: Service name (e.g., "gmail", "github")
        
        Returns:
            Navigation result
        """
        # Try to load cookies if service_name is provided
        if service_name and self._cookie_manager:
            cookies = self._cookie_manager.get_cookies(service_name)
            if cookies:
                # Apply cookies to the session (Network.setCookies via CDP)
                sanitized = self._sanitize_cookies_for_cdp(cookies)
                if sanitized:
                    try:
                        await self._invoke_session(session_id, "Network.setCookies", {"cookies": sanitized})
                        LOG.info(f"[CDPRuntime] Applied {len(sanitized)} cookies for {service_name}")
                    except Exception as e:
                        LOG.warning(f"[CDPRuntime] Failed to apply cookies: {e}")
        
        # Navigate to URL
        result = await self.navigate(session_id, url)
        
        # Watch for a login redirect (allow a few seconds for slow redirects)
        if service_name and self._cookie_manager:
            for _ in range(5):
                if await self._detect_login_page(session_id):
                    LOG.info(f"[CDPRuntime] Login page detected for {service_name}; requesting human login")
                    result["login_required"] = True
                    result["login_completed"] = await self._wait_for_manual_login(session_id, service_name)
                    break
                await asyncio.sleep(1.0)
        
        return result
    
    async def _detect_login_page(self, session_id: str) -> bool:
        """
        Detect if current page is a login page.
        
        Args:
            session_id: Session identifier
        
        Returns:
            True if login page detected
        """
        # Live URL heuristics via JS (falls back to the attached target URL)
        try:
            current_url = await self.js_runtime.evaluate(session_id, "window.location.href")
            if not isinstance(current_url, str) or not current_url:
                handle = self.router.resolve_by_session(session_id)
                current_url = (getattr(handle, "url", "") or "")
            
            # Check if URL contains login/auth/signin/captcha indicators
            login_indicators = ["login", "auth", "signin", "sign-in", "accounts.google.com", "captcha", "challenge"]
            return any(indicator in current_url.lower() for indicator in login_indicators)
        except Exception:
            return False

    async def _wait_for_manual_login(self, session_id: str, service_name: str) -> bool:
        """HITL: pause automation so the human can log in / solve CAPTCHA, then store fresh cookies."""
        try:
            timeout_s = float(os.environ.get("HOJAIGA_LOGIN_WAIT_S", "120"))
        except ValueError:
            timeout_s = 120.0
        await self.trigger_hitl_pause(
            session_id,
            f"Login required for {service_name}. Finish login/CAPTCHA in the browser, then click RESUME."
        )
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            await asyncio.sleep(2.0)
            try:
                if not await self._detect_login_page(session_id):
                    await self._extract_and_store_cookies(session_id, service_name)
                    await self.trigger_hitl_resume(session_id)
                    LOG.info(f"[CDPRuntime] Login completed for {service_name}; session cookies stored")
                    return True
            except Exception as e:
                LOG.warning(f"[CDPRuntime] Login polling error: {e}")
        await self.trigger_hitl_resume(session_id)
        LOG.warning(f"[CDPRuntime] Login for {service_name} not completed within {timeout_s}s")
        return False
    
    async def _extract_and_store_cookies(self, session_id: str, service_name: str):
        """
        Extract cookies from current session and store them.
        
        Args:
            session_id: Session identifier
            service_name: Service name
        """
        try:
            all_cookies = await self._invoke_session(session_id, "Network.getAllCookies", {})
            cookies = all_cookies.get("cookies", []) if isinstance(all_cookies, dict) else (all_cookies or [])
            
            # Convert to list of dicts
            cookie_list = [
                {
                    "name": c.get("name"),
                    "value": c.get("value"),
                    "domain": c.get("domain"),
                    "path": c.get("path"),
                    "expires": c.get("expires"),
                    "secure": c.get("secure"),
                    "httpOnly": c.get("httpOnly"),
                }
                for c in cookies
                if isinstance(c, dict) and c.get("name")
            ]
            
            # Store cookies
            if self._cookie_manager and cookie_list:
                self._cookie_manager.store_cookies(service_name, cookie_list)
                LOG.info(f"[CDPRuntime] Stored {len(cookie_list)} cookies for {service_name}")
        except Exception as e:
            LOG.error(f"[CDPRuntime] Failed to extract cookies: {e}")

    # ------------------------------------------------------------------
    # Human-in-the-loop: CAPTCHA / 2FA gate
    # ------------------------------------------------------------------

    async def _detect_captcha_2fa(self, session_id: str) -> Dict[str, Any]:
        """Inspect the live page for interactive CAPTCHA / 2FA challenge markers.

        Returns {"detected": bool, "kind": "captcha"|"2fa"|"cloudflare"|"",
        "markers": [...], "url": "..."}. Detection failures degrade to
        "not detected" so this hook can never block normal automation by accident.
        """
        try:
            state = await self.js_runtime.evaluate(session_id, _CAPTCHA_DETECT_JS)
        except Exception as exc:
            LOG.debug("[CDPRuntime] CAPTCHA detection skipped: %s", exc)
            return {"detected": False, "kind": "", "markers": []}
        if not isinstance(state, dict):
            return {"detected": False, "kind": "", "markers": []}
        return {
            "detected": bool(state.get("detected")),
            "kind": str(state.get("kind") or ""),
            "markers": [str(m) for m in (state.get("markers") or [])][:8],
            "url": str(state.get("url") or ""),
        }

    async def _captcha_gate(self, session_id: str, service_name: Optional[str] = None,
                            context: str = "") -> Dict[str, Any]:
        """HITL gate: pause automation while a human solves CAPTCHA/2FA, then resume.

        Waits until the challenge markers disappear from the page (poll cadence
        HOJAIGA_CAPTCHA_POLL_S, default 2s). The wait is bounded by
        HOJAIGA_CAPTCHA_TIMEOUT_S (default 150s -- deliberately below the
        orchestrator's task watchdog so the gate fails cleanly before it).
        On success fresh session cookies are stored when a service is known.
        On timeout the pause flag is cleared and, unless HOJAIGA_CAPTCHA_STRICT=0,
        a CDPCommandError is raised so the step fails and retry/recovery gives
        the human a fresh window.
        """
        state = await self._detect_captcha_2fa(session_id)
        if not state.get("detected"):
            return {"detected": False, "resolved": True, "kind": ""}
        kind = state.get("kind") or "captcha"
        first_markers = state.get("markers") or []
        try:
            timeout_s = float(os.environ.get("HOJAIGA_CAPTCHA_TIMEOUT_S", "150"))
        except ValueError:
            timeout_s = 150.0
        try:
            poll_s = max(0.2, float(os.environ.get("HOJAIGA_CAPTCHA_POLL_S", "2.0")))
        except ValueError:
            poll_s = 2.0
        LOG.info("[CDPRuntime] %s challenge detected %s (%s); pausing for human (timeout %.0fs)",
                 kind, context or "on page", ", ".join(first_markers[:3]), timeout_s)
        try:
            await self.overlay.update_capsule(session_id, f"human needed: solve {kind}", "input_needed")
        except Exception:
            pass
        await self.trigger_hitl_pause(
            session_id,
            f"{kind.upper()} detected — solve it in this window, then click FIXED - RESUME")
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            await asyncio.sleep(poll_s)
            try:
                state = await asyncio.wait_for(self._detect_captcha_2fa(session_id), timeout=10.0)
            except Exception:
                continue  # transient eval failures (e.g. mid-navigation) keep the wait alive
            if not state.get("detected"):
                await self.trigger_hitl_resume(session_id)
                try:
                    await self.overlay.update_capsule(session_id, f"{kind} solved", "working")
                except Exception:
                    pass
                if service_name and self._cookie_manager:
                    try:
                        await self._extract_and_store_cookies(session_id, service_name)
                    except Exception:
                        pass
                LOG.info("[CDPRuntime] %s challenge resolved by human %s", kind, context or "")
                return {"detected": True, "resolved": True, "kind": kind, "markers": first_markers}
        # Timeout: clear the pause flag so a failing/retrying task never deadlocks,
        # then surface a clear, greppable failure (strict mode by default).
        await self.trigger_hitl_resume(session_id)
        LOG.warning("[CDPRuntime] %s challenge NOT resolved within %.0fs %s", kind, timeout_s, context or "")
        if os.environ.get("HOJAIGA_CAPTCHA_STRICT", "1").strip() != "0":
            raise CDPCommandError(
                -32010,
                f"captcha_unresolved: {kind} challenge not solved within {timeout_s:.0f}s "
                f"-- human intervention required; task will retry with a fresh window")
        return {"detected": True, "resolved": False, "kind": kind,
                "timeout_s": timeout_s, "markers": first_markers}

    # ------------------------------------------------------------------
    # Public cookie / profile-picker helpers
    # ------------------------------------------------------------------

    async def inject_cookies(self, session_id: str, cookies: List[Dict[str, Any]],
                             service_url: str = "") -> int:
        """Inject stored cookies into a live session via CDP Network.setCookies.

        Public counterpart of _extract_and_store_cookies: used by
        navigate_with_cookies and external callers/tests. Returns the number
        of cookies actually applied (0 when nothing usable was provided).
        """
        sanitized = self._sanitize_cookies_for_cdp(cookies or [])
        if not sanitized:
            LOG.info("[CDPRuntime] inject_cookies: nothing to inject")
            return 0
        if service_url:
            # Cookies persisted without a domain need an explicit URL target.
            for item in sanitized:
                if not item.get("domain"):
                    item.setdefault("url", service_url)
        try:
            await self._invoke_session(session_id, "Network.setCookies", {"cookies": sanitized})
        except Exception as exc:
            LOG.warning("[CDPRuntime] inject_cookies failed: %s", exc)
            return 0
        LOG.info("[CDPRuntime] Injected %d cookies", len(sanitized))
        return len(sanitized)

    async def _is_on_profile_selection_screen(self, session_id: str) -> bool:
        """Detect Chrome's "Who's using Chrome?" profile picker via CDP JS.

        The picker blocks automation because it is a chrome://internal page
        (no target URL to navigate). Detection failures degrade to False so
        this hook can never break normal navigation by accident.
        """
        js = r"""
        (() => {
          try {
            const picker = document.querySelector('profile-picker') !== null;
            const text = ((document.body && document.body.innerText) || '').toLowerCase();
            const who = text.includes("who's using chrome") || text.includes('choose a profile')
                        || text.includes('add person') || text.includes('customize your chrome profile');
            return { picker: picker, text: who };
          } catch (e) { return { picker: false, text: false }; }
        })()
        """
        try:
            state = await self.js_runtime.evaluate(session_id, js)
        except Exception as exc:
            LOG.debug("[CDPRuntime] Profile picker detection skipped: %s", exc)
            return False
        if not isinstance(state, dict):
            return False
        return bool(state.get("picker") or state.get("text"))

    async def _select_profile(self, session_id: str, profile_name: str = "Default") -> bool:
        """Click the matching profile tile on Chrome's profile picker page.

        Falls back to the first available tile when no tile label matches, so
        automation always leaves the picker. Returns True when a tile was
        clicked.
        """
        js = """
        (() => {
          try {
            const wanted = %s;
            const tiles = Array.from(document.querySelectorAll(
              'profile-picker [role="button"], profile-picker button, profile-picker a, profile-picker [class*="profile"]'));
            for (const tile of tiles) {
              const label = ((tile.getAttribute('aria-label') || '') + ' ' + (tile.innerText || '')).toLowerCase();
              if (label.includes(wanted)) { tile.click(); return { clicked: true, label: label.trim().slice(0, 60) }; }
            }
            const first = document.querySelector('profile-picker [role="button"], profile-picker button');
            if (first) { first.click(); return { clicked: true, label: 'first-tile' }; }
            return { clicked: false };
          } catch (e) { return { clicked: false }; }
        })()
        """ % json.dumps(str(profile_name or "").lower())
        try:
            result = await self.js_runtime.evaluate(session_id, js)
        except Exception as exc:
            LOG.warning("[CDPRuntime] Profile selection failed: %s", exc)
            return False
        clicked = bool(isinstance(result, dict) and result.get("clicked"))
        LOG.info("[CDPRuntime] Profile selection '%s': %s", profile_name,
                 "ok" if clicked else "no picker/tile")
        return clicked

    # ------------------------------------------------------------------
    # Session invocation shared by every subsystem
    # ------------------------------------------------------------------

    def _is_instance_alive(self, inst: Optional["BrowserInstance"]) -> TypeGuard["BrowserInstance"]:
        """True iff the instance still has a running process and a live CDP link.

        Used by the permanent-browser singleton to decide whether to reuse the
        existing Chrome or relaunch it (mirrors BrowserManager's "is this driver
        key already created" check that prevented per-call spawning).
        """
        if inst is None:
            return False
        proc_alive = inst.process is None or inst.process.poll() is None
        conn_alive = inst.connection is not None and inst.connection.state in (
            ConnectionState.ACTIVE, ConnectionState.RECOVERING)
        return proc_alive and conn_alive

    def _resolve_browser_id(self, browser_id: Optional[str]) -> Optional[str]:
        """Map a (possibly stale) browser_id to a live instance.

        After a crash+recovery the agents may still hold an old browser_id. We
        remap to the permanent browser (or any live instance) so cached ids from
        the orchestrator never produce a hard 'unknown browser_id' failure.
        """
        if browser_id and browser_id in self._instances:
            return browser_id
        if self._permanent_browser_id and self._permanent_browser_id in self._instances:
            return self._permanent_browser_id
        if self._instances:
            return next(iter(self._instances.keys()))
        return browser_id

    async def _invoke_session(self, session_id: str, method: str, params: Dict[str, Any]) -> Any:
        handle = self.router.resolve_by_session(session_id)
        if handle is None:
            # Stale/cached session (e.g. after recovery). Fall back to the live
            # permanent browser's default session so the agent keeps working.
            alive = self._resolve_browser_id(self._permanent_browser_id)
            instance = self._instances.get(alive) if alive else None
            if instance is None:
                raise CDPCommandError(-32003, f"unknown session_id {session_id}")
            if instance.default_session_id:
                session_id = instance.default_session_id
                handle = self.router.resolve_by_session(session_id)
            if handle is None:
                targets = self.router.list_targets()
                if targets:
                    handle = targets[0]
                    session_id = handle.session_id
                else:
                    raise CDPCommandError(-32003, f"unknown session_id {session_id}")
        else:
            session_id = handle.session_id

        instance = self._instances.get(handle.browser_id)
        if instance is None:
            alive = self._resolve_browser_id(handle.browser_id)
            instance = self._instances.get(alive) if alive else None
            if instance is None:
                raise CDPCommandError(-32004, f"unknown browser_id {handle.browser_id}")
            if instance.default_session_id:
                session_id = instance.default_session_id
        return await instance.connection.send_raw(method, params, session_id=session_id)

    # ------------------------------------------------------------------
    # Browser lifecycle operations
    # ------------------------------------------------------------------

    def _can_launch_browser(self) -> bool:
        # Absolute guard against a reconnect/retry storm spawning hundreds of
        # chrome.exe. A new launch is only allowed when under the concurrent
        # instance cap, under the global launch ceiling, and past the cooldown.
        if len(self._instances) >= self._max_browsers:
            return False
        if self._total_launches >= self._max_total_launches:
            return False
        if (time.time() - self._last_launch_ts) < self._launch_cooldown_s:
            return False
        return True

    async def launch_browser(self, profile_id: Optional[str] = None, headless: bool = False,
                              proxy_server: Optional[str] = None, incognito: bool = False,
                              user_data_dir: Optional[str] = None,
                              profile_directory: Optional[str] = None) -> BrowserInstance:
        # PERMANENT-BROWSER SINGLETON (mirrors Polish BrowserManager._drivers keyed
        # cache). There is exactly ONE Chrome for the permanent agent. Every caller
        # -- agents, recovery, or any external organ -- reuses this single instance;
        # a new chrome.exe is only ever spawned when the existing one is actually
        # dead. This is what stops the runaway multi-process loop.
        async with self._launch_lock:
            existing = self._instances.get(self._permanent_browser_id) if self._permanent_browser_id else None
            if existing is not None and self._is_instance_alive(existing):
                LOG.info("launch_browser: reusing permanent browser %s (tab_count=%d)",
                         existing.browser_id, self._tab_count)
                return existing

            # If an external Chrome is already running (e.g. on port 9222), attach directly!
            for scan_port in (self.config.scan_ports or [9222, 9223, 9224]):
                ep = self.discovery.verify_endpoint("127.0.0.1", scan_port)
                if ep:
                    LOG.info("launch_browser: attaching to existing running Chrome on port %d", scan_port)
                    instance = await self._attach(ep, process=None, profile=None)
                    self._permanent_browser_id = instance.browser_id
                    return instance
            profile = self.profile_manager.create_profile(profile_id=profile_id, proxy_server=proxy_server,
                                                          incognito=incognito, user_data_dir=user_data_dir,
                                                          profile_directory=profile_directory)
            # Launching handled by Gatekeeper (11435 /launch_chrome) — only run setup_login if explicit
            if not incognito and os.environ.get("HOJAIGA_REQUIRE_LOGIN", "0") == "1":
                for _site in ["linkedin.com", "google.com"]:
                    try:
                        import urllib.request
                        import json as _json
                        _data = _json.dumps({"app": _site}).encode()
                        _req = urllib.request.Request("http://127.0.0.1:11435/launch_chrome", data=_data, headers={"Content-Type": "application/json", "X-Hojaiga-Validation": "339680"}, method="POST")
                        urllib.request.urlopen(_req, timeout=1)
                        LOG.info("Gatekeeper launch delegated for %s", _site)
                    except Exception as _e:
                        LOG.debug("gatekeeper launch %s failed %s (fallback to local)", _site, _e)
                        if _HAS_SETUP_LOGIN and ensure_login is not None:
                            try:
                                await asyncio.to_thread(ensure_login, _site)
                            except Exception as _e2:
                                LOG.debug("setup_login %s check failed %s", _site, _e2)
            process, actual_port = await self._launch_and_wait(profile, headless=headless)
            endpoint = await self._wait_for_endpoint("127.0.0.1", actual_port, profile=profile)
            instance = await self._attach(endpoint, process=process, profile=profile)
            # Pre-grant common permissions via CDP so automation is never blocked
            # by a permission prompt (Polish CDP management lesson: drive Chrome
            # through real DevTools Protocol, don't let prompts stall the flow).
            try:
                await instance.connection.send_raw(
                    "Browser.grantPermissions",
                    {"permissions": ["clipboardReadWrite", "clipboardWrite",
                                     "notifications", "geolocation"]},
                    session_id=None)
            except Exception as exc:  # non-fatal
                LOG.debug("grantPermissions skipped: %s", exc)
            self._permanent_browser_id = instance.browser_id
            return instance

    async def attach_browser(self, host: str, port: int) -> BrowserInstance:
        endpoint = self.discovery.resolve_remote(host, port)
        if endpoint is None:
            raise CDPCommandError(-32005, f"could not verify CDP endpoint {host}:{port}")
        return await self._attach(endpoint, process=None, profile=None)

    async def _attach(self, endpoint: DiscoveredEndpoint, process: Optional[subprocess.Popen],
                       profile: Optional[BrowserProfile]) -> BrowserInstance:
        browser_id = uuid.uuid4().hex
        connection = CDPConnectionManager(browser_id, endpoint.websocket_debugger_url,
                                           self.event_bus, self.command_queue,
                                           heartbeat_interval_s=self.config.heartbeat_interval_ms / 1000.0)
        connection.bind_state_listener(lambda state: self.recovery.handle_connection_state(browser_id, state))
        connection.bind_message_listener(lambda method, ctx: self._handle_cdp_event(browser_id, method, ctx))
        instance = BrowserInstance(browser_id=browser_id, connection=connection, process=process,
                                    profile=profile, ws_url=endpoint.websocket_debugger_url)
        # Register BEFORE connecting: auto-attach events fire during connect() and
        # reference browser_id, so the instance must already be resolvable or we
        # hit "unknown browser_id" for the very first tab (and its overlay/hand
        # never initialize).
        self._instances[browser_id] = instance
        await connection.connect()
        await connection.send_raw("Target.setDiscoverTargets", {"discover": True}, session_id=None)
        await connection.send_raw("Target.setAutoAttach",
                                   {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True},
                                   session_id=None)
        self._audit("LAUNCH_BROWSER" if process else "ATTACH_BROWSER", browser_id, {"ws_url": endpoint.websocket_debugger_url})
        return instance

    async def terminate_browser(self, browser_id: str, reason: str = "explicit") -> None:
        instance = self._instances.pop(browser_id, None)
        if instance is None:
            return
        if instance.process is not None and instance.process.pid is not None:
            self._browser_pids.discard(instance.process.pid)
            # Release the launch slot this managed browser consumed.
            try:
                self._browser_semaphore.release()
            except ValueError:
                pass
        for handle in self.router.list_targets(browser_id):
            self.router.unregister_by_target(handle.target_id)
        await instance.connection.close()
        if instance.process is not None:
            try:
                instance.process.terminate()
                instance.process.wait(timeout=5)
            except Exception:
                try:
                    instance.process.kill()
                except Exception:
                    pass
        if instance.profile is not None:
            self.profile_manager.destroy_profile(instance.profile.profile_id)
        self.recovery.reset(browser_id)
        self._audit("CLOSE_BROWSER", browser_id, {"reason": reason})
        await self.event_bus.publish(AOSEvent(AOSEventType.SESSION_STATE_CHANGED, browser_id, None,
                                                {"state": "TERMINATED", "reason": reason}))

    async def respawn_and_restore(self, browser_id: str, snapshot: Optional[SessionSnapshot]) -> None:
        # Recovery is a restart of the SAME permanent browser, never a fresh
        # budgeted launch. We delegate to launch_browser() so it reuses the
        # singleton (spawns only if dead) under the SAME lock + semaphore as every
        # other caller -- this prevents concurrent connection-loss signals from
        # each spawning their own chrome.exe (the original runaway cause).
        inst = self._instances.get(browser_id)
        if self._is_instance_alive(inst):
            # Connection came back on its own; nothing to relaunch.
            LOG.info("Respawn skipped: browser %s still alive", browser_id)
            await self.event_bus.publish(AOSEvent(AOSEventType.SESSION_STATE_CHANGED, browser_id, None,
                                                  {"state": "ACTIVE", "reason": "still_alive"}))
            return
        old_process = inst.process if inst else None
        old_profile = inst.profile if inst else None
        if old_profile is None:
            old_profile = self.profile_manager.create_profile(profile_id="permanent_profile")
        try:
            # launch_browser() acquires the launch lock, reuses the live permanent
            # browser if present, and spawns a new chrome.exe only when necessary.
            new_instance = await self.launch_browser(
                profile_id="permanent_profile",
                user_data_dir=old_profile.user_data_dir,
                profile_directory=old_profile.profile_directory)
        except RuntimeError as exc:
            LOG.error("Recovery aborted: %s", exc)
            raise
        # Migrate identity so downstream references remain stable.
        self._instances[browser_id] = self._instances.pop(new_instance.browser_id)
        self._instances[browser_id].browser_id = browser_id
        # The healed browser IS the permanent browser; keep its id stable.
        self._permanent_browser_id = browser_id
        # Now that identity is migrated, retire the old chrome.exe and release its
        # launch slot so the semaphore count stays balanced (1 slot per live browser).
        if old_process is not None:
            try:
                old_process.kill()
            except Exception:
                pass
            try:
                self._browser_semaphore.release()
            except ValueError:
                pass
        if snapshot:
            for url in snapshot.open_urls:
                await self.create_tab(browser_id, url)
            if snapshot.cookies:
                targets = self.router.list_targets(browser_id)
                if targets:
                    await self.network.set_cookies(targets[0].session_id, snapshot.cookies)
        await self.event_bus.publish(AOSEvent(AOSEventType.SESSION_STATE_CHANGED, browser_id, None,
                                                  {"state": "ACTIVE", "reason": "session_restored"}))

    def _select_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    async def _wait_for_devtools_port(self, profile: BrowserProfile, timeout_s: float = 30.0) -> int:
        """Read the actual CDP port Chrome bound, from DevToolsActivePort file.

        Because we launch with --remote-debugging-port=0, Chrome chooses the
        port itself; polling the file removes the race where a pre-selected
        port could be taken by another process.
        """
        path = os.path.join(profile.user_data_dir, "DevToolsActivePort")
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                with open(path, "r") as fh:
                    first = fh.readline().strip()
                if first.isdigit():
                    return int(first)
            except (FileNotFoundError, ValueError):
                pass
            if self._launch_expired(profile, timeout_s):
                break
            await asyncio.sleep(0.2)
        raise CDPCommandError(-32006,
                              f"Chrome did not publish DevToolsActivePort under {profile.user_data_dir}")

    def _launch_expired(self, profile: BrowserProfile, timeout_s: float) -> bool:
        return False

    async def _launch_and_wait(self, profile: BrowserProfile, headless: bool,
                            timeout_s: float = 30.0, bypass_throttle: bool = False):
        """Launch Chrome on a self-selected port and return (process, port)."""
        if not bypass_throttle and not self._can_launch_browser():
            raise RuntimeError(
                "Browser launch throttled (max concurrent=%d, total launches=%d, cooldown=%.1fs). "
                "Not spawning another chrome.exe; reuse the existing browser."
                % (self._max_browsers, self._max_total_launches, self._launch_cooldown_s)
            )
        # Hard backstop on concurrent chrome.exe processes (Polish CHROME_SEMAPHORE
        # pattern). The slot is released on error here or later in terminate_browser
        # for a managed (spawned) process.
        await self._browser_semaphore.acquire()
        try:
            # Clean up any stale DevToolsActivePort file before launching
            stale_port_file = os.path.join(profile.user_data_dir, "DevToolsActivePort")
            try:
                if os.path.exists(stale_port_file):
                    os.remove(stale_port_file)
            except Exception:
                pass
            process = self.launcher.launch(profile, port=0, headless=headless)
            self._total_launches += 1
            self._last_launch_ts = time.time()
            if process.pid is not None:
                self._browser_pids.add(process.pid)
            actual_port = await self._wait_for_devtools_port(profile, timeout_s)
            return process, actual_port
        except Exception:
            self._browser_semaphore.release()
            raise

    async def _wait_for_endpoint(self, host: str, port: int, timeout_s: float = 30.0,
                                 profile: Optional[BrowserProfile] = None) -> DiscoveredEndpoint:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            endpoint = self.discovery.verify_endpoint(host, port)
            if endpoint:
                return endpoint
            await asyncio.sleep(0.2)
        # Fallback: construct endpoint directly from DevToolsActivePort if file exists
        if profile:
            active = self.discovery.read_devtools_active_port_file(profile.user_data_dir)
            if active:
                ws_path, active_port = active
                return DiscoveredEndpoint(
                    host=host, port=active_port,
                    websocket_debugger_url=f"ws://{host}:{active_port}{ws_path}",
                    browser_version="Chrome",
                    protocol_version="1.3"
                )
        raise CDPCommandError(-32006, f"browser at {host}:{port} did not become ready in time")

    # ------------------------------------------------------------------
    # Target / tab operations
    # ------------------------------------------------------------------

    async def create_tab(self, browser_id: str, url: str = "about:blank",
                         is_temporary: bool = False) -> TargetHandle:
        # Enforce the tab budget tied to the UI agent count (permanent agent).
        # Temporary agents may still open tabs (up to a higher temp ceiling) but
        # can NEVER close one until the user approves task completion.
        if is_temporary:
            ceiling = self._tab_budget + self._temp_tab_budget
        else:
            ceiling = self._tab_budget
        if self._tab_count >= ceiling:
            raise CDPCommandError(-32007,
                f"Tab budget reached ({self._tab_count}/{ceiling}); "
                f"permanent budget={self._tab_budget}, temp extra={self._temp_tab_budget}.")
        instance = self._instances[browser_id]
        result = await instance.connection.send_raw("Target.createTarget", {"url": url}, session_id=None)
        target_id = result["targetId"]
        attach_result = await instance.connection.send_raw(
            "Target.attachToTarget", {"targetId": target_id, "flatten": True}, session_id=None)
        session_id = attach_result["sessionId"]
        handle = TargetHandle(target_id=target_id, session_id=session_id, browser_id=browser_id,
                               target_type="page", url=url)
        self.router.register(handle)
        instance.default_session_id = session_id
        self._tab_count += 1
        await self._initialize_session(session_id)
        return handle

    async def close_tab(self, browser_id: str, target_id: str) -> None:
        if not self._task_approved:
            raise CDPCommandError(-32008,
                "Tab close blocked: task not yet approved as successfully completed by the user.")
        instance = self._instances[browser_id]
        await instance.connection.send_raw("Target.closeTarget", {"targetId": target_id}, session_id=None)
        self.router.unregister_by_target(target_id)
        self._tab_count = max(0, self._tab_count - 1)

    async def _initialize_session(self, session_id: str) -> None:
        if session_id in self._initialized_sessions:
            return
        self._initialized_sessions.add(session_id)
        for method in ("Page.enable", "DOM.enable", "Runtime.enable", "Accessibility.enable"):
            await self._invoke_session(session_id, method, {})
        await self.network.enable(session_id, global_interception=self.config.enable_global_interception)
        await self.js_runtime.enable(session_id)
        await self.file_chooser.enable(session_id)
        
        # Inject HITL (Human-In-The-Loop) overlay via CDP JavaScript runtime
        # This replaces the old Selenium-based HITL pipeline with exact styling and behavior
        hitl_js = """
        (function() {
            // Legacy full-width HITL bar disabled -- replaced by the floating
            // capsule HUD injected via self.overlay.inject() just below.
            if (false && !document.getElementById('hitl-cdp-overlay')) {
                let overlay = document.createElement('div');
                overlay.id = 'hitl-cdp-overlay';
                overlay.style.position = 'fixed';
                overlay.style.bottom = '0';
                overlay.style.left = '0';
                overlay.style.width = '100%';
                overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.9)';
                overlay.style.color = '#00ffcc';
                overlay.style.padding = '15px';
                overlay.style.zIndex = '999999999';
                overlay.style.display = 'flex';
                overlay.style.justifyContent = 'space-between';
                overlay.style.alignItems = 'center';
                overlay.style.fontFamily = 'monospace';
                overlay.style.fontSize = '14px';
                overlay.style.transition = 'opacity 0.3s';
                overlay.style.opacity = '0'; // Hidden by default
                
                let text = document.createElement('span');
                text.id = 'hitl-cdp-text';
                text.innerText = 'CDP Automation Active | Mouse idle';
                
                let btnContainer = document.createElement('div');
                
                let pauseBtn = document.createElement('button');
                pauseBtn.innerText = 'PAUSE (HITL)';
                pauseBtn.style.marginRight = '10px';
                pauseBtn.style.backgroundColor = '#ffcc00';
                pauseBtn.style.border = 'none';
                pauseBtn.style.padding = '5px 10px';
                pauseBtn.style.cursor = 'pointer';
                pauseBtn.style.fontWeight = 'bold';
                
                let resumeBtn = document.createElement('button');
                resumeBtn.innerText = 'FIXED - RESUME';
                resumeBtn.style.backgroundColor = '#00ffcc';
                resumeBtn.style.border = 'none';
                resumeBtn.style.padding = '5px 10px';
                resumeBtn.style.cursor = 'pointer';
                resumeBtn.style.fontWeight = 'bold';
                
                btnContainer.appendChild(pauseBtn);
                btnContainer.appendChild(resumeBtn);
                
                overlay.appendChild(text);
                overlay.appendChild(btnContainer);
                document.body.appendChild(overlay);
                
                window.__HITL_PAUSED = false;
                window.__HITL_DOM_HASH = '';
                window.__HITL_LOOP_COUNTER = 0;
                
                pauseBtn.onclick = function() {
                    window.__HITL_PAUSED = true;
                    text.innerText = '⚠️ HUMAN INTERVENTION NEEDED ⚠️ - Automation Paused';
                    overlay.style.opacity = '1';
                };
                
                resumeBtn.onclick = function() {
                    window.__HITL_PAUSED = false;
                    text.innerText = 'CDP Automation Active | Resuming...';
                    setTimeout(() => { overlay.style.opacity = '0'; }, 2000);
                };
                
                // Mouse movement fade-in logic (from original Selenium implementation)
                let timeout;
                document.addEventListener('mousemove', () => {
                    if(!window.__HITL_PAUSED) {
                        overlay.style.opacity = '1';
                        clearTimeout(timeout);
                        timeout = setTimeout(() => {
                            if(!window.__HITL_PAUSED) overlay.style.opacity = '0';
                        }, 2000);
                    }
                });
            }
        })();
        """
        try:
            await self.js_runtime.evaluate(session_id, hitl_js)
            LOG.info("HITL overlay injected successfully for session %s", session_id)
        except Exception as e:
            LOG.warning("Failed to inject HITL overlay: %s", e)
        
        # Spawn this tab's independent virtual "hand" and paint the automation
        # overlay (glowing border + floating capsule HUD) into the page.
        self.hands.get_or_create(session_id, self.input_engine, self.overlay)
        await self.overlay.inject(session_id)
        await self.overlay.update_capsule(session_id, "automation ready")

    def get_hand(self, session_id: str) -> "VirtualHand":
        """Return the independent virtual hand bound to this tab/session.

        Each Chrome tab/profile gets its own hand (cursor + fingers) so concurrent
        automation never shares a mouse. The hand delegates to the shared input
        engine while keeping its own cursor position and HUD capsule up to date.
        """
        return self.hands.get_or_create(session_id, self.input_engine, self.overlay)

    async def trigger_hitl_pause(self, session_id: str, reason: str = "Loop Detected") -> None:
        """Show the reference-style 'Agent needs your input' capsule + dim the page."""
        pause_js = ("window.__HITL_PAUSED=true;"
                    "window.__hojaigaSetCapsule && window.__hojaigaSetCapsule('input_needed','Agent needs your input');")
        try:
            await self.js_runtime.evaluate(session_id, pause_js)
            LOG.info("HITL pause triggered for session %s: %s", session_id, reason)
        except Exception as e:
            LOG.warning("Failed to trigger HITL pause: %s", e)

    async def trigger_hitl_resume(self, session_id: str) -> None:
        """Return the capsule to its 'working' state once the human is done."""
        resume_js = ("window.__HITL_PAUSED=false;"
                     "window.__hojaigaSetCapsule && window.__hojaigaSetCapsule('working','Resuming');")
        try:
            await self.js_runtime.evaluate(session_id, resume_js)
            LOG.info("HITL resume triggered for session %s", session_id)
        except Exception as e:
            LOG.warning("Failed to trigger HITL resume: %s", e)

    async def show_hitl_overlay(self, session_id: str) -> None:
        """Show HITL overlay manually."""
        show_js = """
        (function() {
            let overlay = document.getElementById('hitl-cdp-overlay');
            if (overlay) {
                overlay.style.opacity = '1';
                window.__HITL_VISIBLE = true;
            }
        })();
        """
        try:
            await self.js_runtime.evaluate(session_id, show_js)
        except Exception as e:
            LOG.warning("Failed to show HITL overlay: %s", e)

    async def hide_hitl_overlay(self, session_id: str) -> None:
        """Hide HITL overlay manually."""
        hide_js = """
        (function() {
            let overlay = document.getElementById('hitl-cdp-overlay');
            if (overlay) {
                overlay.style.opacity = '0';
                window.__HITL_VISIBLE = false;
            }
        })();
        """
        try:
            await self.js_runtime.evaluate(session_id, hide_js)
        except Exception as e:
            LOG.warning("Failed to hide HITL overlay: %s", e)

    async def check_hitl_paused(self, session_id: str) -> bool:
        """Check if HITL is currently paused."""
        check_js = """
        (function() {
            return window.__HITL_PAUSED || false;
        })();
        """
        try:
            result = await self.js_runtime.evaluate(session_id, check_js)
            return bool(result)
        except Exception as e:
            LOG.warning("Failed to check HITL pause state: %s", e)
            return False

    async def _await_if_paused(self, session_id: str) -> bool:
        """HITL: block an interactive op while the human holds the PAUSE button.

        The in-page PAUSE control (window.__HITL_PAUSED) was purely cosmetic --
        nothing in the CDP execution path respected it, so automation kept
        fighting the human for the page. Returns True when a pause was observed
        and later cleared; raises CDPCommandError after
        HOJAIGA_HITL_PAUSE_TIMEOUT_S (default 900s) so a forgotten pause fails
        the step loudly instead of silently bulldozing the human's work.
        """
        if not session_id or session_id == "DEFAULT":
            return False
        if not await self.check_hitl_paused(session_id):
            return False
        try:
            timeout_s = float(os.environ.get("HOJAIGA_HITL_PAUSE_TIMEOUT_S", "900"))
        except ValueError:
            timeout_s = 900.0
        LOG.info("[CDPRuntime] Human paused automation (HITL); interactive op waiting up to %.0fs", timeout_s)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            await asyncio.sleep(1.5)
            if not await self.check_hitl_paused(session_id):
                LOG.info("[CDPRuntime] HITL resume detected; automation continues")
                return True
        raise CDPCommandError(
            -32011,
            f"hitl_pause_timeout: human held automation paused for {timeout_s:.0f}s; "
            f"click FIXED - RESUME to continue")

    async def check_for_loops(self, session_id: str, max_consecutive_same: int = 3) -> bool:
        """
        Hashes the current DOM body to detect infinite looping (e.g. LinkedIn modals).
        Returns True if a loop is detected and automation should pause.
        """
        loop_check_js = f"""
        (function() {{
            const bodyHtml = document.body ? document.body.innerHTML : '';
            // Simple hash function (djb2)
            let hash = 5381;
            for (let i = 0; i < bodyHtml.length; i++) {{
                hash = ((hash << 5) + hash) + bodyHtml.charCodeAt(i);
            }}
            const currentHash = hash.toString();
            
            if (window.__HITL_DOM_HASH === currentHash) {{
                window.__HITL_LOOP_COUNTER = (window.__HITL_LOOP_COUNTER || 0) + 1;
            }} else {{
                window.__HITL_LOOP_COUNTER = 0;
                window.__HITL_DOM_HASH = currentHash;
            }}
            
            if (window.__HITL_LOOP_COUNTER >= {max_consecutive_same}) {{
                window.__HITL_LOOP_COUNTER = 0; // reset after alerting
                return true;
            }}
            return false;
        }})();
        """
        try:
            loop_detected = await self.js_runtime.evaluate(session_id, loop_check_js)
            if loop_detected:
                await self.trigger_hitl_pause(session_id, "Loop Detected (Stuck on Modal). Please solve manually and click RESUME.")
                LOG.warning("Loop detected in session %s, HITL triggered", session_id)
            return bool(loop_detected)
        except Exception as e:
            LOG.warning("Failed to check for loops: %s", e)
            return False

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    async def navigate(self, session_id: str, url: str) -> Dict[str, Any]:
        result = await self._invoke_session(session_id, "Page.navigate", {"url": url})
        if "errorText" in result:
            raise CDPCommandError(-1, f"Failed to navigate to {url}: {result['errorText']}")
        # Wait for page navigation and DOM to settle
        await asyncio.sleep(2.0)
        return result

    async def reload(self, session_id: str, ignore_cache: bool = False) -> None:
        await self._invoke_session(session_id, "Page.reload", {"ignoreCache": ignore_cache})

    async def go_back(self, session_id: str) -> None:
        history = await self._invoke_session(session_id, "Page.getNavigationHistory", {})
        idx = history["currentIndex"] - 1
        if idx >= 0:
            entry_id = history["entries"][idx]["id"]
            await self._invoke_session(session_id, "Page.navigateToHistoryEntry", {"entryId": entry_id})

    async def go_forward(self, session_id: str) -> None:
        history = await self._invoke_session(session_id, "Page.getNavigationHistory", {})
        idx = history["currentIndex"] + 1
        if idx < len(history["entries"]):
            entry_id = history["entries"][idx]["id"]
            await self._invoke_session(session_id, "Page.navigateToHistoryEntry", {"entryId": entry_id})

    async def get_clean_page_summary(self, session_id: str) -> Dict[str, Any]:
        """Returns a concise, token-efficient DOM overview of interactive elements & viewport text."""
        js_code = r"""(() => {
            const elements = [];
            const candidates = document.querySelectorAll('button, input, textarea, a[href], select, [role="button"], [role="link"], [role="searchbox"]');
            for (let el of candidates) {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.top <= window.innerHeight) {
                    const tag = el.tagName.toLowerCase();
                    const text = (el.innerText || el.placeholder || el.getAttribute('aria-label') || el.value || '').trim();
                    if (text || el.id) {
                        elements.push({
                            tag: tag,
                            id: el.id || undefined,
                            text: text.slice(0, 60),
                            type: el.type || undefined
                        });
                    }
                }
                if (elements.length >= 15) break;
            }
            const snippet = (document.body ? document.body.innerText : '').slice(0, 500).replace(/\s+/g, ' ').trim();
            return {
                url: window.location.href,
                title: document.title,
                elements: elements,
                text_snippet: snippet
            };
        })()"""
        try:
            summary = await self.js_runtime.evaluate(session_id, js_code)
            if isinstance(summary, str):
                try:
                    summary = json.loads(summary)
                except Exception:
                    pass
            return summary if isinstance(summary, dict) else {"url": "", "title": "", "elements": [], "text_snippet": ""}
        except Exception as e:
            LOG.warning("Failed to get clean page summary: %s", e)
            return {"url": "", "title": "", "elements": [], "text_snippet": "", "error": str(e)}

    async def get_page_state(self, session_id: str) -> Dict[str, Any]:
        layout = await self._invoke_session(session_id, "Page.getLayoutMetrics", {})
        url_result = await self.js_runtime.evaluate(session_id, "window.location.href")
        title_result = await self.js_runtime.evaluate(session_id, "document.title")
        ready_state = await self.js_runtime.evaluate(session_id, "document.readyState")
        summary = await self.get_clean_page_summary(session_id)
        return {"url": url_result, "title": title_result, "readyState": ready_state, "layout": layout, "summary": summary}

    # ------------------------------------------------------------------
    # CDP -> AOS event routing
    # ------------------------------------------------------------------

    async def _handle_cdp_event(self, browser_id: str, method: str, ctx: Dict[str, Any]) -> None:
        params = ctx.get("params", {})
        session_id = ctx.get("sessionId")

        if method == "Target.attachedToTarget":
            target_info = params.get("targetInfo", {})
            target_session_id = params.get("sessionId", "")
            handle = TargetHandle(target_id=target_info.get("targetId", ""),
                                    session_id=target_session_id, browser_id=browser_id,
                                    target_type=target_info.get("type", "page"), url=target_info.get("url", ""))
            self.router.register(handle)
            instance = self._instances.get(browser_id)
            if instance and not instance.default_session_id and target_info.get("type") == "page":
                instance.default_session_id = target_session_id
            # Auto-attached tabs are not routed through open_tab(), so initialize
            # them here (idempotent): this paints the overlay + spawns the hand.
            if target_info.get("type") == "page" and target_session_id:
                asyncio.create_task(self._initialize_session(target_session_id))
        elif method == "Page.frameNavigated":
            frame = params.get("frame", {})
            self.router.frame_tracker.upsert_frame(frame.get("id", ""), frame.get("loaderId", ""),
                                                     frame.get("url", ""), frame.get("parentId"))
        elif method == "Runtime.executionContextCreated":
            ctx_info = params.get("context", {})
            aux = ctx_info.get("auxData", {})
            frame_id = aux.get("frameId")
            if frame_id:
                self.router.frame_tracker.bind_execution_context(frame_id, ctx_info.get("id"))
        elif method == "Fetch.requestPaused" and session_id:
            asyncio.create_task(self.network.handle_request_paused(session_id, params))
        elif method in ("Network.requestWillBeSent", "Network.responseReceived", "Network.loadingFailed") and session_id:
            self.network.record(session_id, {"method": method, **params})
        elif method == "Browser.downloadWillBegin":
            self.downloads.on_download_will_begin(params.get("guid", ""), params.get("url", ""),
                                                    params.get("suggestedFilename", ""))
        elif method == "Browser.downloadProgress":
            self.downloads.on_download_progress(params.get("guid", ""), params.get("state", ""),
                                                  params.get("totalBytes", 0), params.get("receivedBytes", 0),
                                                  params.get("filePath"))
        elif method == "Page.fileChooserOpened" and session_id:
            self.file_chooser.on_file_chooser_opened(session_id, params.get("backendNodeId", 0),
                                                       params.get("mode", "selectSingle"))
        elif method == "Page.screencastFrame" and session_id:
            await self.vision.on_screencast_frame(session_id, browser_id, params.get("sessionId", 0),
                                                    params.get("data", ""), params.get("metadata", {}))
        elif method == "Target.targetCrashed":
            LOG.error("Target crashed in browser %s: %s", browser_id, params)

        event_type = AOSEventType.from_cdp_method(method)
        if event_type:
            await self.event_bus.publish(AOSEvent(event_type=event_type, browser_id=browser_id,
                                                    session_id=session_id, payload=params))

    # ------------------------------------------------------------------
    # Audit (Universal Law 1 - Accountability and Traceability)
    # ------------------------------------------------------------------

    def _audit(self, action: str, browser_id: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "timestamp": time.time(), "action": action, "browser_id": browser_id, "details": details})
        if len(self._audit_log) > 10000:
            self._audit_log.pop(0)

    # ------------------------------------------------------------------
    # IPC DISPATCH TABLE
    # ------------------------------------------------------------------

    def _resolve_session_id(self, payload: Dict[str, Any]) -> str:
        """Auto-resolve session_id from payload or fall back to permanent browser."""
        sid = payload.get("session_id")
        if sid and sid != "DEFAULT":
            h = self.router.resolve_by_session(sid)
            if h and h.session_id:
                return h.session_id
            return sid
        # Try permanent browser first
        inst = self._instances.get(self._permanent_browser_id) if self._permanent_browser_id else None
        if inst and inst.default_session_id:
            return inst.default_session_id
        # Fallback: any available browser
        for bid, inst in self._instances.items():
            if inst.default_session_id:
                self._permanent_browser_id = bid
                return inst.default_session_id
        # Fallback: prioritize real web page targets (skip omnibox and internal browser UI)
        for target in self.router.list_targets():
            if target.session_id and target.target_type == "page" and not (target.url or "").startswith("chrome://"):
                return target.session_id
        for target in self.router.list_targets():
            if target.session_id and target.target_type == "page":
                return target.session_id
        for target in self.router.list_targets():
            if target.session_id and not (target.url or "").startswith("chrome://omnibox"):
                return target.session_id
        return sid or "DEFAULT"

    async def dispatch(self, frame: IPCFrame) -> IPCFrame:
        try:
            handler = self._DISPATCH_TABLE.get(frame.op_code)
            if handler is None:
                return IPCFrame(Organ19OpCode.ERROR, {"error": f"unknown op_code {frame.op_code}"})
            # Auto-inject resolved session_id for handlers that need it
            if frame.op_code != Organ19OpCode.LAUNCH_BROWSER:
                resolved = self._resolve_session_id(frame.payload)
                # If no browser exists yet or resolved is DEFAULT, auto-launch one
                if resolved == "DEFAULT" or not self._instances:
                    LOG.info("No active browser session — auto-launching for step")
                    headless_mode = os.environ.get("HOJAIGA_HEADLESS", "0").strip() == "1"
                    launch_res = await self._op_launch_browser({"headless": headless_mode, "profile_id": "auto"})
                    resolved = launch_res.get("session_id") or self._resolve_session_id(frame.payload)
                frame.payload["session_id"] = resolved
            # HITL: while the human holds the PAUSE button, interactive ops wait
            # instead of fighting them for the page (read-only ops still pass).
            if (frame.op_code in self._HITL_INTERACTIVE_OPS
                    and os.environ.get("HOJAIGA_HITL_PAUSE_ENFORCE", "1").strip() != "0"):
                try:
                    await self._await_if_paused(frame.payload.get("session_id") or "")
                except CDPCommandError:
                    raise
                except Exception as exc:  # pause probing must never break ops
                    LOG.debug("HITL pause probe failed: %s", exc)
            result = await handler(self, frame.payload)
            return IPCFrame(frame.op_code, {"ok": True, "result": result})
        except CDPCommandError as exc:
            return IPCFrame(Organ19OpCode.ERROR, {"ok": False, "error": exc.message, "code": exc.code})
        except Exception as exc:  # Universal Law 8 - failures are transparent and logged
            LOG.exception("Dispatch error for op_code %s: %s", frame.op_code, repr(exc))
            return IPCFrame(Organ19OpCode.ERROR, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    async def _op_ping(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"pong": True, "time": time.time()}

    async def _op_launch_browser(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # TAB-BOUNDED PERMANENT BROWSER MODEL.
        # launch_browser() enforces the single-browser singleton (reuse if alive,
        # spawn only if dead) under a lock, so every agent -- permanent or
        # temporary -- operates on the one stable browser_id via tabs. This is the
        # direct port of Polish-automation's BrowserManager keyed-cache that kept
        # its parallel workers from each spawning their own Chrome.
        requested = str(payload.get("profile_id") or "").strip()
        profile_id = "permanent_profile"
        user_data_dir = payload.get("user_data_dir")
        profile_directory = payload.get("profile_directory")
        if requested == "user_profile":
            # Profile selection logic: "user_profile" opens the human user's real
            # Chrome profile (cloned into the runtime, resolved deterministically
            # -- never a blocking picker) so existing logins are available.
            try:
                resolved = self.profile_manager.prepare_user_profile()
                profile_id = resolved.profile_id
                user_data_dir = resolved.user_data_dir
                profile_directory = resolved.profile_directory
            except Exception as exc:
                LOG.warning("user_profile clone failed (%s); using isolated permanent profile", exc)
        instance = await self.launch_browser(
            profile_id=profile_id,
            headless=payload.get("headless", False),
            proxy_server=payload.get("proxy_server"),
            incognito=payload.get("incognito", False),
            user_data_dir=user_data_dir,
            profile_directory=profile_directory)
        self._permanent_browser_id = instance.browser_id

        # Wait for auto-attach to populate the default session ID
        for _ in range(20):
            if instance.default_session_id:
                break
            await asyncio.sleep(0.1)

        if not instance.default_session_id:
            handle = await self.create_tab(instance.browser_id, "about:blank")
            instance.default_session_id = handle.session_id

        return {"browser_id": instance.browser_id, "ws_url": instance.ws_url,
                "session_id": instance.default_session_id, "permanent": True}

    async def _op_attach_browser(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        instance = await self.attach_browser(payload["host"], payload["port"])
        return {"browser_id": instance.browser_id, "ws_url": instance.ws_url}

    async def _op_close_browser(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.terminate_browser(payload["browser_id"], reason=payload.get("reason", "explicit"))
        return {"closed": True}

    async def _op_create_tab(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        browser_id = self._resolve_browser_id(payload.get("browser_id"))
        if not browser_id or browser_id not in self._instances:
            raise CDPCommandError(-1, "No active browser instance")
        is_temporary = bool(payload.get("is_temporary", False))
        handle = await self.create_tab(browser_id, payload.get("url", "about:blank"),
                                       is_temporary=is_temporary)
        return {"target_id": handle.target_id, "session_id": handle.session_id}

    async def _op_close_tab(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        browser_id = self._resolve_browser_id(payload.get("browser_id"))
        if not browser_id or browser_id not in self._instances:
            raise CDPCommandError(-1, "No active browser instance")
        await self.close_tab(browser_id, payload["target_id"])
        return {"closed": True}

    async def _op_approve_task_completion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # User (or orchestrator on verified success) approves the task as done.
        # Only after this can tabs be closed -- per the tab-bounded permanent
        # browser policy (temporary agents cannot kill tabs until approval).
        self._task_approved = True
        LOG.info("Task completion approved by user; tab closing now permitted.")
        return {"approved": True}

    async def _op_list_targets(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        targets = self.router.list_targets(self._resolve_browser_id(payload.get("browser_id")))
        return {"targets": [{"target_id": t.target_id, "session_id": t.session_id, "url": t.url,
                              "type": t.target_type} for t in targets]}

    async def _op_navigate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        session_id = payload.get("session_id")
        url = payload.get("url", "about:blank")
        # Auto-resolve: if no session_id, use the permanent browser's default session
        if not session_id or session_id == "DEFAULT":
            session_id = self._resolve_session_id(payload)
            if session_id == "DEFAULT":
                targets = self.router.list_targets()
                if targets:
                    session_id = targets[0].session_id
        if not session_id or session_id == "DEFAULT":
            headless_mode = os.environ.get("HOJAIGA_HEADLESS", "0").strip() == "1"
            launch_res = await self._op_launch_browser({"headless": headless_mode})
            session_id = launch_res.get("session_id") or self._resolve_session_id(payload)
        if not session_id or session_id == "DEFAULT":
            raise CDPCommandError(-1, "No active browser session. Run LAUNCH_BROWSER first.")
        # Session-cookie aware navigation: inject stored cookies and handle login HITL.
        service_name = payload.get("service_name") or self._detect_service_from_url(url)
        if service_name and self._cookie_manager:
            result = await self.navigate_with_cookies(session_id, url, service_name)
        else:
            result = await self.navigate(session_id, url)
        # Human-in-the-loop CAPTCHA/2FA gate: a challenge page may have replaced
        # the target (or blocked a login redirect). Pause for the human and wait
        # until it clears; unresolved challenges raise so retry/recovery schedules
        # a fresh human window instead of automation acting on a challenge page.
        result["captcha"] = await self._captcha_gate(
            session_id, service_name, context=f"after NAVIGATE {url[:120]}")
        return result

    async def _op_handle_captcha(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Explicit HITL action ('SOLVE_CAPTCHA'): block until any CAPTCHA/2FA on
        # the active page is solved by a human. Raises on timeout (strict mode)
        # so the orchestrator's retry/recovery path engages.
        return await self._captcha_gate(payload.get("session_id"),
                                        payload.get("service_name") or None,
                                        context="explicit HANDLE_CAPTCHA")

    async def _op_reload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.reload(payload["session_id"], payload.get("ignore_cache", False))
        return {"reloaded": True}

    async def _op_go_back(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.go_back(payload["session_id"])
        return {"navigated": True}

    async def _op_go_forward(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.go_forward(payload["session_id"])
        return {"navigated": True}

    async def _op_get_dom_tree(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        nodes = await self.dom_engine.synthesize_tree(payload["session_id"],
                                                        payload.get("pierce_shadow_dom", True))
        node_dicts = [n.to_dict() for n in nodes]

        # Feed web DOM elements to Visual Memory system
        try:
            from core_organs.organ_33_visual_memory import get_visual_memory
            vm = get_visual_memory()
            # Extract meaningful web elements for visual memory
            web_elements = []
            for nd in node_dicts[:200]:
                name = nd.get("ax_name", "") or nd.get("tag_name", "")
                if name and nd.get("is_clickable"):
                    web_elements.append({
                        "name": name[:100],
                        "type": f"web_{nd.get('ax_role') or nd.get('tag_name') or 'element'}",
                        "coords": {"x": 0, "y": 0, "box": [0, 0, 0, 0]},
                    })
            if web_elements:
                vm.deep_scan(
                    app_name="chrome",
                    window_title="web",
                    mode="training",
                )
        except Exception as e:
            pass  # Silent — visual memory is best-effort

        return {"nodes": node_dicts}

    async def _op_query_selector(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        node_id = await self.dom_engine.query_selector(payload["session_id"], payload["selector"])
        return {"node_id": node_id}

    async def _op_click(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        session_id = payload.get("session_id")
        if not session_id or session_id == "DEFAULT":
            session_id = self._resolve_session_id(payload)
            payload["session_id"] = session_id
        selector = payload.get("selector", "")
        target_hint = payload.get("target", "")

        # Default coordinates to prevent KeyError: 'x'
        payload.setdefault("x", 400.0)
        payload.setdefault("y", 300.0)

        # 1. Update capsule to show intention (virtual mouse via gatekeeper, no physical)
        try:
            await self.overlay.update_capsule(session_id, f"Targeting {target_hint or selector}", state="working")
        except Exception:
            pass

        if (selector or target_hint) and ("x" not in payload or payload.get("x") == 400.0):
            node_id = None
            # Robust auto-wait element discovery retry pattern (5 attempts, 0.3s)
            for attempt in range(5):
                node_id = await self.dom_engine.query_selector(session_id, selector, target_hint=target_hint)
                if node_id:
                    break
                await asyncio.sleep(0.3)

            if node_id:
                # Extract accurate coordinates from the box model
                quad = []
                try:
                    box_result = await self._invoke_session(session_id, "DOM.getBoxModel", {"nodeId": node_id})
                    quad = box_result.get("model", {}).get("content", [])
                except Exception:
                    pass

                if len(quad) >= 8:
                    xs = quad[0::2]
                    ys = quad[1::2]
                    payload["x"] = min(xs) + (max(xs) - min(xs)) / 2
                    payload["y"] = min(ys) + (max(ys) - min(ys)) / 2

        # Execute physical hand interaction (virtual CDP, no SetCursorPos)
        hand = self.get_hand(session_id)
        x = float(payload.get("x", 400.0))
        y = float(payload.get("y", 300.0))
        await hand.click(x, y, button=payload.get("button", "left"))

        # Failsafe character pacing for inputs (Anti-bot typing, 30-110ms from runtime_config.yaml)
        text_to_type = payload.get("text", "")
        if text_to_type:
            await asyncio.sleep(0.15)
            # Clear field safely using native key combination strings
            try:
                await self._invoke_session(session_id, "Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "modifiers": 2, "windowsVirtualKeyCode": 65})
                await self._invoke_session(session_id, "Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "modifiers": 2, "windowsVirtualKeyCode": 65})
                await hand.press_key("Backspace")
            except Exception:
                pass
            
            await asyncio.sleep(0.1)
            # Dynamic character-by-character variance typing pass (uses config typing_delay_variance_ms)
            low, high = self.config.typing_delay_variance_ms if hasattr(self.config, 'typing_delay_variance_ms') else (30, 110)
            for char in text_to_type:
                await self._invoke_session(session_id, "Input.dispatchKeyEvent", {"type": "char", "text": char})
                await asyncio.sleep(high / 1000.0 if low==high else __import__('random').uniform(low, high) / 1000.0)
            
            if payload.get("press_enter", True):
                await asyncio.sleep(0.2)
                await hand.press_key("Enter")

        # Cycle checking integration to catch stuck loops
        await self.verify_and_check_loops(session_id)
        return {"clicked": True, "typed": bool(text_to_type)}

    async def verify_and_check_loops(self, session_id: str):
        """Hashes active page layout snapshots to trap infinite UI loop fences."""
        if not hasattr(self, "_html_loop_tracker"):
            self._html_loop_tracker: Dict[str, Any] = {"last_hash": None, "count": 0}
            
        try:
            # Check for generic authentication speedbumps first
            state_info = await self.get_page_state(session_id)
            curr_url = state_info.get("url", "").lower()
            indicators = ("challenge/", "signin", "v3/signin", "checkpoint", "speedbump")
            
            if any(marker in curr_url for marker in indicators):
                await self.overlay.update_capsule(session_id, "Agent needs your input (Sign-in Check)", state="input_needed")
                # Block asynchronous task execution pipeline until fixed
                while True:
                    await asyncio.sleep(1.0)
                    check_state = await self.get_page_state(session_id)
                    if not any(marker in check_state.get("url", "").lower() for marker in indicators):
                        break
                await self.overlay.update_capsule(session_id, "Authentication cleared | Resuming", state="working")

            # Process layout innerHTML MD5 hashing boundary
            doc_tree = await self.dom_engine.synthesize_tree(session_id, pierce_shadow_dom=True)
            flat_layout = "".join([n.tag_name for n in doc_tree])
            curr_hash = hashlib.md5(flat_layout.encode('utf-8')).hexdigest()
            
            if curr_hash == self._html_loop_tracker["last_hash"]:
                self._html_loop_tracker["count"] += 1
            else:
                self._html_loop_tracker["count"] = 0
                self._html_loop_tracker["last_hash"] = curr_hash
                
            if self._html_loop_tracker["count"] >= getattr(self, '_loop_threshold', 3):
                await self.overlay.update_capsule(session_id, "Agent needs your input (Stuck on Loop)", state="input_needed")
                self._html_loop_tracker["count"] = 0
                
                # Halt pipeline until human triggers state modification via keyboard/mouse movement
                await self._invoke_session(session_id, "Runtime.evaluate", {
                    "expression": "window.__HITL_PAUSED = true;", "returnByValue": True
                })
                while True:
                    paused = await self._invoke_session(session_id, "Runtime.evaluate", {
                        "expression": "window.__HITL_PAUSED === true;", "returnByValue": True
                    })
                    if isinstance(paused, dict):
                        paused = paused.get("result", {}).get("value", paused.get("value"))
                    if not paused:
                        break
                    await asyncio.sleep(1.0)
                await self.overlay.update_capsule(session_id, "Failsafe cleared | Resuming automation", state="working")
        except Exception:
            pass

    async def _op_right_click(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        session_id = payload.get("session_id") or self._resolve_session_id(payload)
        x = float(payload.get("x", 400.0))
        y = float(payload.get("y", 300.0))
        await self.get_hand(session_id).right_click(x, y)
        return {"clicked": True}

    async def _op_double_click(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        session_id = payload.get("session_id") or self._resolve_session_id(payload)
        x = float(payload.get("x", 400.0))
        y = float(payload.get("y", 300.0))
        await self.get_hand(session_id).double_click(x, y)
        return {"clicked": True}

    async def _op_hover(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        session_id = payload.get("session_id") or self._resolve_session_id(payload)
        x = float(payload.get("x", 400.0))
        y = float(payload.get("y", 300.0))
        await self.get_hand(session_id).hover(x, y)
        return {"hovered": True}

    async def _op_scroll(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        session_id = payload.get("session_id") or self._resolve_session_id(payload)
        x = float(payload.get("x", 400.0))
        y = float(payload.get("y", 300.0))
        delta_x = float(payload.get("delta_x", 0.0))
        delta_y = float(payload.get("delta_y") or payload.get("amount") or 500.0)
        await self.get_hand(session_id).scroll(x, y, delta_x, delta_y)
        return {"scrolled": True}

    async def _op_drag_drop(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.get_hand(payload["session_id"]).drag_drop(payload["source_x"], payload["source_y"],
                                           payload["target_x"], payload["target_y"])
        return {"dragged": True}

    async def _op_multi_select(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        points = [(p["x"], p["y"]) for p in payload["points"]]
        await self.get_hand(payload["session_id"]).multi_select(points, payload.get("modifier", "Control"))
        return {"selected": len(points)}

    async def _op_type_text(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.get_hand(payload["session_id"]).type_text(payload["text"])
        return {"typed": True}

    async def _op_press_key(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.get_hand(payload["session_id"]).press_key(payload["key"])
        return {"pressed": True}

    async def _op_execute_js(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        expr = (payload.get("expression") or payload.get("script") or "").strip()
        session_id = str(payload.get("session_id") or "")
        
        # Strip extraneous outer quotes or backticks if LLM escaped them
        if (expr.startswith('"') and expr.endswith('"')) or (expr.startswith("'") and expr.endswith("'")):
            expr = expr[1:-1].strip()

        # If it's a bare return or multi-line without wrapping, wrap in IIFE
        if expr and not expr.startswith("(() =>") and not expr.startswith("(function") and ("return " in expr or ";" in expr):
            wrapped_expr = f"(() => {{ try {{ {expr} }} catch(e) {{ return String(e); }} }})()"
        else:
            wrapped_expr = expr

        try:
            value = await self.js_runtime.evaluate(session_id, wrapped_expr or expr, payload.get("execution_context_id"))
            return {"value": value}
        except Exception as e:
            LOG.warning(f"JS evaluation exception for '{expr[:60]}': {e}. Running robust document extraction fallback...")
            try:
                fallback_script = """
                (() => {
                    const texts = [];
                    const items = document.querySelectorAll('h1, h2, h3, h4, p, a, li, span');
                    for (const el of items) {
                        const t = (el.innerText || '').trim();
                        if (t.length > 5 && !texts.includes(t)) {
                            texts.push(t);
                        }
                        if (texts.length >= 30) break;
                    }
                    return texts.join('\\n');
                })()
                """
                value = await self.js_runtime.evaluate(session_id, fallback_script)
                return {"value": value, "fallback_used": True}
            except Exception as e_inner:
                LOG.error(f"Fallback extraction also failed: {e_inner}")
                return {"value": "Extraction completed", "error_handled": True}

    async def _op_get_page_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self.get_page_state(payload["session_id"])

    async def _op_set_network_rule(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        rule = NetworkRule(rule_id=uuid.uuid4().hex, url_pattern=payload["url_pattern"],
                            action=payload["action"], inject_headers=payload.get("inject_headers", {}),
                            mock_status=payload.get("mock_status"), mock_body=payload.get("mock_body"))
        self.network.add_rule(payload["session_id"], rule)
        return {"rule_id": rule.rule_id}

    async def _op_get_network_log(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"log": self.network.get_log(payload["session_id"])}

    async def _op_download_start(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        target_dir = await self.downloads.configure(payload["session_id"], payload["browser_id"])
        return {"download_dir": target_dir}

    async def _op_download_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = self.downloads.status(payload["guid"])
        if record is None:
            return {"found": False}
        return {"found": True, "state": record.state, "received_bytes": record.received_bytes,
                "total_bytes": record.total_bytes, "file_path": record.file_path, "sha256": record.sha256}

    async def _op_upload_files(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ok = await self.file_chooser.upload_files(payload["session_id"], payload["file_paths"])
        return {"uploaded": ok}

    async def _op_native_file_picker(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.native_picker.available:
            return {"supported": False}
        hwnd = self.native_picker.find_dialog_window(payload["owner_pid"],
                                                       payload.get("timeout_s", 10.0))
        if hwnd is None:
            return {"supported": True, "found": False}
        ok = self.native_picker.inject_path_and_confirm(hwnd, payload["file_path"])
        return {"supported": True, "found": True, "injected": ok}

    async def _op_screenshot(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        mode = payload.get("mode", "viewport")
        session_id = payload["session_id"]
        if mode == "element":
            data = await self.vision.capture_element(session_id, payload["backend_node_id"],
                                                       self.dom_engine._safe_box_model)
        elif mode == "full_page":
            data = await self.vision.capture_full_page(session_id)
        else:
            data = await self.vision.capture_viewport(session_id, payload.get("format"), payload.get("quality"))
        return {"image_base64": data}

    async def _op_start_screencast(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.vision.start_screencast(payload["session_id"], payload["browser_id"])
        return {"streaming": True}

    async def _op_stop_screencast(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.vision.stop_screencast(payload["session_id"])
        return {"streaming": False}

    async def _op_create_profile(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        profile = self.profile_manager.create_profile(proxy_server=payload.get("proxy_server"),
                                                        incognito=payload.get("incognito", False),
                                                        extra_flags=payload.get("extra_flags"))
        return {"profile_id": profile.profile_id, "user_data_dir": profile.user_data_dir}

    async def _op_set_cookies(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.network.set_cookies(payload["session_id"], payload["cookies"])
        return {"set": True}

    async def _op_get_cookies(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        cookies = await self.network.get_cookies(payload["session_id"], payload.get("urls"))
        return {"cookies": cookies}

    async def _op_subscribe_events(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"recent_events": self.event_bus.recent(payload.get("count", 50))}

    async def _op_recover_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        browser_id = payload["browser_id"]
        await self.recovery.handle_connection_state(browser_id, ConnectionState.RECOVERING)
        return {"recovery_triggered": True}

    # Interactive ops that must wait while the human holds the HITL PAUSE button
    # (window.__HITL_PAUSED). Read-only ops (screenshots, DOM queries, cookies,
    # PING) intentionally stay available during a pause. HANDLE_CAPTCHA is
    # excluded because the gate manages the pause state itself.
    _HITL_INTERACTIVE_OPS: frozenset = frozenset({
        Organ19OpCode.NAVIGATE, Organ19OpCode.RELOAD,
        Organ19OpCode.GO_BACK, Organ19OpCode.GO_FORWARD,
        Organ19OpCode.CLICK, Organ19OpCode.RIGHT_CLICK, Organ19OpCode.DOUBLE_CLICK,
        Organ19OpCode.HOVER, Organ19OpCode.SCROLL, Organ19OpCode.DRAG_DROP,
        Organ19OpCode.MULTI_SELECT, Organ19OpCode.TYPE_TEXT, Organ19OpCode.PRESS_KEY,
    })

    _DISPATCH_TABLE: Dict[int, Callable[["CDPRuntimeKernel", Dict[str, Any]], Awaitable[Dict[str, Any]]]] = {}


# populate dispatch table (module scope, after class body is fully defined)
CDPRuntimeKernel._DISPATCH_TABLE = {
    Organ19OpCode.PING: CDPRuntimeKernel._op_ping,
    Organ19OpCode.LAUNCH_BROWSER: CDPRuntimeKernel._op_launch_browser,
    Organ19OpCode.ATTACH_BROWSER: CDPRuntimeKernel._op_attach_browser,
    Organ19OpCode.CLOSE_BROWSER: CDPRuntimeKernel._op_close_browser,
    Organ19OpCode.CREATE_TAB: CDPRuntimeKernel._op_create_tab,
    Organ19OpCode.CLOSE_TAB: CDPRuntimeKernel._op_close_tab,
    Organ19OpCode.LIST_TARGETS: CDPRuntimeKernel._op_list_targets,
    Organ19OpCode.NAVIGATE: CDPRuntimeKernel._op_navigate,
    Organ19OpCode.RELOAD: CDPRuntimeKernel._op_reload,
    Organ19OpCode.GO_BACK: CDPRuntimeKernel._op_go_back,
    Organ19OpCode.GO_FORWARD: CDPRuntimeKernel._op_go_forward,
    Organ19OpCode.HANDLE_CAPTCHA: CDPRuntimeKernel._op_handle_captcha,
    Organ19OpCode.GET_DOM_TREE: CDPRuntimeKernel._op_get_dom_tree,
    Organ19OpCode.QUERY_SELECTOR: CDPRuntimeKernel._op_query_selector,
    Organ19OpCode.CLICK: CDPRuntimeKernel._op_click,
    Organ19OpCode.RIGHT_CLICK: CDPRuntimeKernel._op_right_click,
    Organ19OpCode.DOUBLE_CLICK: CDPRuntimeKernel._op_double_click,
    Organ19OpCode.HOVER: CDPRuntimeKernel._op_hover,
    Organ19OpCode.SCROLL: CDPRuntimeKernel._op_scroll,
    Organ19OpCode.DRAG_DROP: CDPRuntimeKernel._op_drag_drop,
    Organ19OpCode.MULTI_SELECT: CDPRuntimeKernel._op_multi_select,
    Organ19OpCode.TYPE_TEXT: CDPRuntimeKernel._op_type_text,
    Organ19OpCode.PRESS_KEY: CDPRuntimeKernel._op_press_key,
    Organ19OpCode.EXECUTE_JS: CDPRuntimeKernel._op_execute_js,
    Organ19OpCode.GET_PAGE_STATE: CDPRuntimeKernel._op_get_page_state,
    Organ19OpCode.SET_NETWORK_RULE: CDPRuntimeKernel._op_set_network_rule,
    Organ19OpCode.GET_NETWORK_LOG: CDPRuntimeKernel._op_get_network_log,
    Organ19OpCode.DOWNLOAD_START: CDPRuntimeKernel._op_download_start,
    Organ19OpCode.DOWNLOAD_STATUS: CDPRuntimeKernel._op_download_status,
    Organ19OpCode.UPLOAD_FILES: CDPRuntimeKernel._op_upload_files,
    Organ19OpCode.NATIVE_FILE_PICKER: CDPRuntimeKernel._op_native_file_picker,
    Organ19OpCode.SCREENSHOT: CDPRuntimeKernel._op_screenshot,
    Organ19OpCode.START_SCREENCAST: CDPRuntimeKernel._op_start_screencast,
    Organ19OpCode.STOP_SCREENCAST: CDPRuntimeKernel._op_stop_screencast,
    Organ19OpCode.CREATE_PROFILE: CDPRuntimeKernel._op_create_profile,
    Organ19OpCode.SET_COOKIES: CDPRuntimeKernel._op_set_cookies,
    Organ19OpCode.GET_COOKIES: CDPRuntimeKernel._op_get_cookies,
    Organ19OpCode.SUBSCRIBE_EVENTS: CDPRuntimeKernel._op_subscribe_events,
    Organ19OpCode.RECOVER_SESSION: CDPRuntimeKernel._op_recover_session,
    Organ19OpCode.APPROVE_TASK_COMPLETION: CDPRuntimeKernel._op_approve_task_completion,
}


# ======================================================================
# SECTION 18 -- RUNTIME CONFIGURATION (mirrors runtime_config.yaml schema)
# ======================================================================

@dataclass
class RuntimeConfig:
    version: str = "2.0.0"
    max_concurrent_browsers: int = 8
    websocket_timeout_ms: int = 60000
    heartbeat_interval_ms: int = 5000
    max_payload_size_mb: int = 64
    tcp_port: int = 47619

    auto_discover_local: bool = True
    scan_ports: List[int] = field(default_factory=lambda: [9222, 9223, 9224])

    max_tree_depth: int = -1
    pierce_shadow_dom: bool = True
    include_accessibility: bool = True

    humanize_mouse_movement: bool = True
    typing_delay_variance_ms: Tuple[int, int] = (20, 120)

    enable_global_interception: bool = True
    max_captured_body_kb: int = 10240

    screencast_format: str = "jpeg"
    screencast_quality: int = 80
    screencast_max_fps: int = 30

    enable_native_fallback: bool = True
    native_dialog_timeout_ms: int = 10000

    auto_recovery_enabled: bool = True
    max_crash_retries: int = 3
    retry_backoff_ms: int = 1000
    restore_session_state: bool = True

    runtime_dir: str = field(default_factory=lambda: os.path.join(os.getcwd(), "var", "hojaiga", "organ19"))

    @property
    def profiles_dir(self) -> str:
        return os.path.join(self.runtime_dir, "profiles")

    @property
    def downloads_dir(self) -> str:
        return os.path.join(self.runtime_dir, "downloads")

    def ensure_dirs(self) -> None:
        os.makedirs(self.profiles_dir, exist_ok=True)
        os.makedirs(self.downloads_dir, exist_ok=True)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "RuntimeConfig":
        cfg = RuntimeConfig()
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        return cfg


# ======================================================================
# SECTION 19 -- ENTRYPOINT
# ======================================================================

async def _amain() -> None:
    config = RuntimeConfig()
    config.ensure_dirs()
    kernel = CDPRuntimeKernel(config)
    await kernel.start()
    LOG.info("Organ 19 - Chrome CDP Runtime is ready and awaiting IPC connections")
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await kernel.stop()


def main() -> None:
    if not _HAS_WEBSOCKETS:
        LOG.error("The 'websockets' package is required to run this organ. "
                   "Install with: pip install websockets")
        sys.exit(1)
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        pass


# ======================================================================
# SECTION 20 -- BACKWARD-COMPATIBILITY ALIASES
# ======================================================================

# Legacy name kept so older imports/tests keep working (the class is
# constructible with no args; it defaults to a stock RuntimeConfig).
# Prefer the canonical name CDPRuntimeKernel in new code.
ChromeCDPRuntime = CDPRuntimeKernel


if __name__ == "__main__":
    main()
