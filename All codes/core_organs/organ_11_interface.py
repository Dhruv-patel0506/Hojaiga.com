"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 11
Name: Interface

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Interface]
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
Dependencies: platform, socket, dataclasses, PIL, uuid...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_11_interface.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
organ_11_interface.py

Hojaiga Automation OS — Organ 11: Interface Organ
Single-file production implementation.

Authority (highest to lowest):
    1. Constitution of Hojaiga
    2. Hojaiga Law Book
    3. Upper/Inner Surface Diagrams & Workflows
    4. Legacy Code Migration Guide (reference only, not architectural authority)
    5. Hojaiga Policy Manual
    6. Master Architecture Blueprint
    7. Organ Specification (Organ_11_Interface.md)

Responsibility boundary (Universal Law 3 — Separation of Responsibility):
    This organ owns ZERO automation logic, model inference, or private state
    databases. It is purely an event producer / renderer. All communication
    with the rest of Hojaiga occurs exclusively through the documented
    hojaiga_interface IPC socket (Section 7/9 of the Organ Specification).

Import contract:
    from core_organs.organ_11_interface import InterfaceKernel, run_cli, run_headless_tray

Python: 3.11+
Optional dependencies (all soft-imported, organ degrades gracefully without them):
    PySide6   -> DASHBOARD_ACTIVE GUI rendering
    pystray   -> HEADLESS_TRAY system tray icon
    plyer     -> native OS desktop toast notifications
    pywin32   -> real Windows named-pipe IPC transport (win32pipe/win32file)
"""


import os

# ─────────────────────────────────────────────────────────────────────────
# Engineering Recommendation (Section 46): force software rasterization
# BEFORE any Qt import ever happens, so zero VRAM is ever touched by this
# organ. Must execute at module import time.
# ─────────────────────────────────────────────────────────────────────────
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", ""))

import argparse
import json
import logging
import platform
import queue
import socket
import sqlite3
import struct
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Optional

# ═══════════════════════════════════════════════════════════════════════
# SECTION: Logging (Policy Manual Chapter 8 — structured JSON audit log)
# ═══════════════════════════════════════════════════════════════════════

# [2026-08-17] Deprecated old JSON formatters in favor of centralized clean terminal logs.
# class _JsonLogFormatter(logging.Formatter):
#     def format(self, record: logging.LogRecord) -> str:
#         payload = {
#             "timestamp": time.time(),
#             "level": record.levelname,
#             "component": "organ_11_interface",
#             "logger": record.name,
#             "message": record.getMessage(),
#         }
#         if record.exc_info:
#             payload["exception"] = self.formatException(record.exc_info)
#         extra = getattr(record, "audit_fields", None)
#         if extra:
#             payload.update(extra)
#         return json.dumps(payload, default=str)
# 
# 
# def _build_logger(name: str = "organ_11_interface") -> logging.Logger:
#     logger = logging.getLogger(name)
#     if not logger.handlers:
#         handler = logging.StreamHandler(sys.stdout)
#         handler.setFormatter(_JsonLogFormatter())
#         logger.addHandler(handler)
#         logger.setLevel(logging.INFO)
#         logger.propagate = False
#     return logger

def _build_logger(name: str = "organ_11_interface") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter('{"timestamp":"%(asctime)s","logger":"%(name)s","level":"%(levelname)s","message":"%(message)s"}'))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    return logger


LOGGER = _build_logger()


def audit_log(event: str, **fields: Any) -> None:
    """Foundational Law 7 — append-only operational history."""
    LOGGER.info(event, extra={"audit_fields": fields})


# ═══════════════════════════════════════════════════════════════════════
# SECTION: Enumerations (Section 13, 14, 15 of Organ Spec)
# ═══════════════════════════════════════════════════════════════════════

class UIMode(str, Enum):
    HEADLESS_TRAY = "HEADLESS_TRAY"
    DASHBOARD_ACTIVE = "DASHBOARD_ACTIVE"
    MODAL_AWAITING_HUMAN = "MODAL_AWAITING_HUMAN"
    CLI_MODE = "CLI_MODE"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Verdict(str, Enum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    TIMED_OUT = "TIMED_OUT"


class OpCode(int, Enum):
    """2-byte op_code as defined in Section 9 — Socket Definitions."""
    DISPLAY_APPROVAL_PROMPT = 0x0001
    APPROVAL_VERDICT = 0x0002
    UPDATE_TELEMETRY_DISPLAY = 0x0003
    TELEMETRY_ACK = 0x0004
    SEND_NOTIFICATION = 0x0005
    NOTIFICATION_ACK = 0x0006
    RENDER_TASK_PROGRESS = 0x0007
    PROGRESS_ACK = 0x0008
    GET_ACTIVE_USER_INPUTS = 0x0009
    USER_INPUT_PAYLOAD = 0x000A
    USER_GOAL_SUBMITTED = 0x000B
    UI_MODE_CHANGED = 0x000C
    UI_CLOSED = 0x000D
    GENERIC_ACK = 0x00FF


class EventName(str, Enum):
    USER_GOAL_SUBMITTED = "EVENT_USER_GOAL_SUBMITTED"
    HUMAN_APPROVAL_VERDICT = "EVENT_HUMAN_APPROVAL_VERDICT"
    UI_MODE_CHANGED = "EVENT_UI_MODE_CHANGED"
    UI_CLOSED = "EVENT_UI_CLOSED"


# ═══════════════════════════════════════════════════════════════════════
# SECTION: Data Contracts (Section 15 — JSON Schemas realized as dataclasses)
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_APPROVAL_TIMEOUT_MS = 300_000
MAX_GOAL_LENGTH = 4096


@dataclass
class ApprovalPromptRequest:
    prompt_id: str
    task_id: str
    requesting_organ: str
    action_summary: str
    risk_level: RiskLevel
    policy_violated: str = ""
    timeout_ms: int = DEFAULT_APPROVAL_TIMEOUT_MS
    request_hash: str = ""  # Section 26 — cryptographically signed request hash

    @staticmethod
    def from_json(data: dict[str, Any]) -> "ApprovalPromptRequest":
        required = ("prompt_id", "task_id", "requesting_organ", "action_summary", "risk_level")
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"ApprovalPromptRequest missing required fields: {missing}")
        return ApprovalPromptRequest(
            prompt_id=data["prompt_id"],
            task_id=data["task_id"],
            requesting_organ=data["requesting_organ"],
            action_summary=data["action_summary"],
            risk_level=RiskLevel(data["risk_level"]),
            policy_violated=data.get("policy_violated", ""),
            timeout_ms=int(data.get("timeout_ms", DEFAULT_APPROVAL_TIMEOUT_MS)),
            request_hash=data.get("request_hash", ""),
        )

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["risk_level"] = self.risk_level.value
        return d


@dataclass
class HumanApprovalResponse:
    prompt_id: str
    verdict: Verdict
    operator_notes: str = ""
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d


@dataclass
class TelemetryUpdatePayload:
    organ_health: dict[str, str] = field(default_factory=dict)
    task_progress_dag: dict[str, Any] = field(default_factory=dict)
    resource_counters: dict[str, float] = field(default_factory=dict)
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))

    @staticmethod
    def from_json(data: dict[str, Any]) -> "TelemetryUpdatePayload":
        return TelemetryUpdatePayload(
            organ_health=data.get("organ_health", {}),
            task_progress_dag=data.get("task_progress_dag", {}),
            resource_counters=data.get("resource_counters", {}),
            timestamp=int(data.get("timestamp", time.time() * 1000)),
        )


@dataclass
class NotificationPayload:
    title: str
    body: str
    severity: str = "INFO"
    notification_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @staticmethod
    def from_json(data: dict[str, Any]) -> "NotificationPayload":
        return NotificationPayload(
            title=data.get("title", "Hojaiga"),
            body=data.get("body", ""),
            severity=data.get("severity", "INFO"),
            notification_id=data.get("notification_id", str(uuid.uuid4())),
        )


@dataclass
class ProgressUpdatePayload:
    task_id: str
    step_name: str
    percent_complete: float
    status: str = "RUNNING"

    @staticmethod
    def from_json(data: dict[str, Any]) -> "ProgressUpdatePayload":
        return ProgressUpdatePayload(
            task_id=data["task_id"],
            step_name=data.get("step_name", ""),
            percent_complete=float(data.get("percent_complete", 0.0)),
            status=data.get("status", "RUNNING"),
        )


@dataclass
class UserGoalPayload:
    goal_id: str
    text: str
    source: str  # "GUI" | "CLI"
    submitted_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class ValidationError(Exception):
    pass


def sanitize_goal(raw_text: str) -> str:
    """Section 32 — Validation Rules.

    Goal submissions must not be empty, must stay under 4096 characters,
    and must pass input sanitization checks.
    """
    if raw_text is None:
        raise ValidationError("Goal submission is empty.")
    text = raw_text.strip()
    if not text:
        raise ValidationError("Goal submission is empty.")
    if len(text) > MAX_GOAL_LENGTH:
        raise ValidationError(f"Goal submission exceeds {MAX_GOAL_LENGTH} characters.")
    # Strip control characters (defense against IPC/protocol injection).
    sanitized = "".join(ch for ch in text if ch.isprintable() or ch in ("\n", "\t"))
    if not sanitized:
        raise ValidationError("Goal submission failed sanitization.")
    return sanitized


# ═══════════════════════════════════════════════════════════════════════
# SECTION: In-memory state store (Section 16 — Internal Database Structures)
# ═══════════════════════════════════════════════════════════════════════

class StateBridge:
    """Thread-safe in-memory SQLite view state store.

    Owns zero persistent state — Universal Law 3. This is a transient
    render cache only; the system of record lives in the Memory organ.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE ui_session_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE active_prompts (
                    prompt_id TEXT PRIMARY KEY,
                    task_id TEXT,
                    risk_level TEXT,
                    status TEXT,
                    created_at TIMESTAMP
                )
                """
            )

    def set_state(self, key: str, value: Any) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO ui_session_state (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, json.dumps(value, default=str), time.time()),
            )

    def get_state(self, key: str, default: Any = None) -> Any:
        with self._lock:
            cur = self._conn.execute("SELECT value FROM ui_session_state WHERE key = ?", (key,))
            row = cur.fetchone()
            if row is None:
                return default
            return json.loads(row[0])

    def register_prompt(self, prompt: ApprovalPromptRequest) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO active_prompts (prompt_id, task_id, risk_level, status, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (prompt.prompt_id, prompt.task_id, prompt.risk_level.value, "AWAITING", time.time()),
            )

    def resolve_prompt(self, prompt_id: str, verdict: Verdict) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE active_prompts SET status = ? WHERE prompt_id = ?",
                (verdict.value, prompt_id),
            )

    def active_prompt_count(self) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) FROM active_prompts WHERE status = 'AWAITING'")
            return cur.fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ═══════════════════════════════════════════════════════════════════════
# SECTION: Wire protocol (Section 9 — Socket Definitions)
# Length-Prefixed Binary Frame: [4-byte length | 2-byte op_code | JSON payload]
# ═══════════════════════════════════════════════════════════════════════

MAX_PAYLOAD_SIZE = 16 * 1024 * 1024  # 16 MB


class FrameProtocolError(Exception):
    pass


def encode_frame(op_code: OpCode, payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, default=str).encode("utf-8")
    if len(body) > MAX_PAYLOAD_SIZE:
        raise FrameProtocolError("Payload exceeds 16 MB maximum frame size.")
    header = struct.pack(">IH", len(body), int(op_code))
    return header + body


def decode_frame_header(header: bytes) -> tuple[int, int]:
    if len(header) != 6:
        raise FrameProtocolError("Malformed frame header.")
    length, op_code = struct.unpack(">IH", header)
    if length > MAX_PAYLOAD_SIZE:
        raise FrameProtocolError("Declared payload exceeds 16 MB maximum frame size.")
    return length, op_code


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("IPC connection closed by peer.")
        buf.extend(chunk)
    return bytes(buf)


def read_frame(sock: socket.socket) -> tuple[OpCode, dict[str, Any]]:
    header = _recv_exact(sock, 6)
    length, op_code = decode_frame_header(header)
    body = _recv_exact(sock, length) if length else b""
    payload = json.loads(body.decode("utf-8")) if body else {}
    return OpCode(op_code), payload


def write_frame(sock: socket.socket, op_code: OpCode, payload: dict[str, Any]) -> None:
    sock.sendall(encode_frame(op_code, payload))


# ═══════════════════════════════════════════════════════════════════════
# SECTION: Transport — hojaiga_interface socket
#   Windows target: \\.\pipe\hojaiga_interface   (via pywin32 if present)
#   Portable fallback: TCP loopback (documented, used when pywin32 absent
#   or platform != Windows), preserving the identical frame protocol.
# ═══════════════════════════════════════════════════════════════════════

WINDOWS_PIPE_NAME = r"\\.\pipe\hojaiga_interface"
UNIX_SOCKET_PATH = "/tmp/hojaiga_interface.sock"
LOOPBACK_FALLBACK_HOST = "127.0.0.1"
LOOPBACK_FALLBACK_PORT = 47_611

try:
    import win32pipe  # type: ignore
    import win32file  # type: ignore
    import win32event  # type: ignore
    import win32security  # type: ignore
    import pywintypes  # type: ignore
    _HAS_WIN32 = True
except Exception:
    _HAS_WIN32 = False


class IPCTransportUnavailable(Exception):
    pass


class IPCClient:
    """Outgoing connection FROM this organ TO the CNS-hosted socket server.

    Per Section 11/12, the Interface Organ is a client of the CNS IPC
    endpoint for emitting user goals, approval verdicts, and status
    signals, while also servicing inbound RPCs (Section 7) pushed by CNS.
    In this reference implementation the organ hosts the listener and
    the CNS process connects as a client, matching the RPC direction
    defined in Section 7 (CNS invokes DisplayApprovalPrompt, etc. on us).
    """

    def __init__(self, on_frame: Callable[[OpCode, dict[str, Any]], None]) -> None:
        self._on_frame = on_frame
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()

    def send(self, op_code: OpCode, payload: dict[str, Any]) -> None:
        with self._lock:
            if self._sock is None:
                LOGGER.warning("IPC client not connected; dropping frame %s", op_code)
                return
            try:
                write_frame(self._sock, op_code, payload)
            except OSError as exc:
                LOGGER.error("IPC send failed: %s", exc)


class IPCServer(threading.Thread):
    """Hosts the hojaiga_interface named-pipe (or TCP fallback) endpoint.

    Every accepted connection is serviced on its own worker thread; all
    inbound RPCs are marshalled onto a thread-safe queue consumed by the
    InterfaceKernel's dispatch loop (Section 19 — Thread Safety).
    """

    def __init__(self, kernel: "InterfaceKernel") -> None:
        super().__init__(name="IPCServerThread", daemon=True)
        self._kernel = kernel
        self._stop_event = threading.Event()
        self._server_socket: Optional[socket.socket] = None
        self.transport_description = ""

    def run(self) -> None:
        if platform.system() == "Windows":
            LOGGER.info("Windows named-pipe transport requested for hojaiga_interface.")
            if _HAS_WIN32:
                self._run_named_pipe_server()
                return
            LOGGER.warning(
                "pywin32 not installed; falling back to TCP loopback transport "
                "for hojaiga_interface (functionally identical wire protocol)."
            )
        self._run_tcp_or_unix_server()

    # ---- Windows Named Pipe implementation ------------------------------
    def _run_named_pipe_server(self) -> None:  # pragma: no cover - Windows-only
        self.transport_description = WINDOWS_PIPE_NAME
        while not self._stop_event.is_set():
            try:
                pipe = win32pipe.CreateNamedPipe(  # type: ignore
                    WINDOWS_PIPE_NAME,
                    win32pipe.PIPE_ACCESS_DUPLEX,  # type: ignore
                    win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,  # type: ignore
                    win32pipe.PIPE_UNLIMITED_INSTANCES,  # type: ignore
                    MAX_PAYLOAD_SIZE,
                    MAX_PAYLOAD_SIZE,
                    0,
                    win32security.SECURITY_ATTRIBUTES(),  # type: ignore
                )
                win32pipe.ConnectNamedPipe(pipe, None)  # type: ignore
                threading.Thread(
                    target=self._service_named_pipe_connection, args=(pipe,), daemon=True
                ).start()
            except Exception as exc:
                if not self._stop_event.is_set():
                    LOGGER.error("Named pipe accept loop error: %s", exc)
                    time.sleep(0.5)

    def _service_named_pipe_connection(self, pipe) -> None:  # pragma: no cover
        try:
            while not self._stop_event.is_set():
                header_hr, header = win32file.ReadFile(pipe, 6)  # type: ignore
                header_bytes = header if isinstance(header, bytes) else header.encode("utf-8")
                length, op_code = decode_frame_header(header_bytes)
                body = b""
                if length:
                    body_hr, body = win32file.ReadFile(pipe, length)  # type: ignore
                payload = json.loads(body if isinstance(body, str) else body.decode("utf-8")) if body else {}
                self._kernel.enqueue_inbound(OpCode(op_code), payload, reply=lambda oc, pl, p=pipe: self._reply_named_pipe(p, oc, pl))
        except Exception as exc:
            LOGGER.info("Named pipe connection closed: %s", exc)
        finally:
            try:
                win32file.CloseHandle(pipe)  # type: ignore
            except Exception:
                pass

    def _reply_named_pipe(self, pipe, op_code: OpCode, payload: dict[str, Any]) -> None:  # pragma: no cover
        frame = encode_frame(op_code, payload)
        win32file.WriteFile(pipe, frame)  # type: ignore

    # ---- Portable fallback (Unix domain socket / TCP loopback) ----------
    def _run_tcp_or_unix_server(self) -> None:
        use_unix = platform.system() != "Windows" and hasattr(socket, "AF_UNIX")
        if use_unix:
            try:
                if os.path.exists(UNIX_SOCKET_PATH):
                    os.remove(UNIX_SOCKET_PATH)
                self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore
                self._server_socket.bind(UNIX_SOCKET_PATH)
                self.transport_description = UNIX_SOCKET_PATH
            except OSError as exc:
                LOGGER.warning("Unix socket bind failed (%s); using TCP loopback.", exc)
                use_unix = False
                self._server_socket = None

        if not use_unix:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((LOOPBACK_FALLBACK_HOST, LOOPBACK_FALLBACK_PORT))
            self.transport_description = f"{LOOPBACK_FALLBACK_HOST}:{LOOPBACK_FALLBACK_PORT}"

        assert self._server_socket is not None
        self._server_socket.listen(8)
        self._server_socket.settimeout(0.5)
        audit_log("ipc_server_listening", transport=self.transport_description)

        while not self._stop_event.is_set():
            try:
                conn, _addr = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._service_socket_connection, args=(conn,), daemon=True).start()

    def _service_socket_connection(self, conn: socket.socket) -> None:
        self._kernel.attach_client_socket(conn)
        try:
            while not self._stop_event.is_set():
                op_code, payload = read_frame(conn)
                self._kernel.enqueue_inbound(
                    op_code, payload,
                    reply=lambda oc, pl, c=conn: write_frame(c, oc, pl),
                )
        except (ConnectionError, OSError, FrameProtocolError, ValueError) as exc:
            LOGGER.info("IPC connection closed: %s", exc)
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def stop(self) -> None:
        self._stop_event.set()
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════════════
# SECTION: Governance dialogs (Section 30, 31 — approval / timeout / deny)
# ═══════════════════════════════════════════════════════════════════════

class GovernanceDialogManager:
    """Human-in-the-loop approval loop. Universal Law 12."""

    def __init__(self, kernel: "InterfaceKernel") -> None:
        self._kernel = kernel
        self._pending: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def prompt_user_modal(
        self,
        request: ApprovalPromptRequest,
        on_verdict: Callable[[HumanApprovalResponse], None],
    ) -> None:
        self._kernel.state.register_prompt(request)
        self._kernel.set_ui_mode(UIMode.MODAL_AWAITING_HUMAN)
        audit_log(
            "governance_prompt_opened",
            prompt_id=request.prompt_id,
            task_id=request.task_id,
            risk_level=request.risk_level.value,
            requesting_organ=request.requesting_organ,
        )

        def _timeout_deny() -> None:
            self._resolve(request.prompt_id, Verdict.TIMED_OUT, "", on_verdict)

        timer = threading.Timer(request.timeout_ms / 1000.0, _timeout_deny)
        timer.daemon = True
        with self._lock:
            self._pending[request.prompt_id] = timer
        timer.start()

        if self._kernel.gui_bridge is not None:
            self._kernel.gui_bridge.show_approval_modal(request, lambda v, n: self._resolve(request.prompt_id, v, n, on_verdict))
        else:
            self._kernel.cli_bridge_prompt_approval(request, lambda v, n: self._resolve(request.prompt_id, v, n, on_verdict))

    def _resolve(
        self,
        prompt_id: str,
        verdict: Verdict,
        notes: str,
        on_verdict: Callable[[HumanApprovalResponse], None],
    ) -> None:
        with self._lock:
            timer = self._pending.pop(prompt_id, None)
        if timer is not None:
            timer.cancel()
        self._kernel.state.resolve_prompt(prompt_id, verdict)
        response = HumanApprovalResponse(prompt_id=prompt_id, verdict=verdict, operator_notes=notes)
        audit_log("governance_prompt_resolved", prompt_id=prompt_id, verdict=verdict.value)
        if self._kernel.state.active_prompt_count() == 0:
            self._kernel.set_ui_mode(self._kernel.previous_mode)
        on_verdict(response)


# ═══════════════════════════════════════════════════════════════════════
# SECTION: Notification engine (Section 4 — toast wrapper)
# ═══════════════════════════════════════════════════════════════════════

class NotificationEngine:
    def __init__(self) -> None:
        try:
            from plyer import notification as _plyer_notification  # type: ignore
            self._backend = _plyer_notification
        except Exception:
            self._backend = None

    def send(self, payload: NotificationPayload) -> None:
        audit_log("notification_dispatched", title=payload.title, severity=payload.severity)
        if self._backend is not None:
            try:
                self._backend.notify(title=payload.title, message=payload.body, timeout=6)
                return
            except Exception as exc:
                LOGGER.warning("Native notification backend failed: %s", exc)
        LOGGER.info("[NOTIFICATION] %s: %s", payload.title, payload.body)


# ═══════════════════════════════════════════════════════════════════════
# SECTION: Tray manager (Section 4 — system tray, headless-tray footprint)
# ═══════════════════════════════════════════════════════════════════════

class TrayManager:
    def __init__(self, on_open_dashboard: Callable[[], None], on_exit: Callable[[], None]) -> None:
        self._on_open_dashboard = on_open_dashboard
        self._on_exit = on_exit
        self._icon = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        try:
            import pystray  # type: ignore
            from PIL import Image  # type: ignore
        except Exception:
            LOGGER.info("pystray/Pillow unavailable; tray icon disabled (headless log-only mode).")
            return

        image = Image.new("RGB", (32, 32), color=(30, 30, 30))
        menu = pystray.Menu(
            pystray.MenuItem("Open Dashboard", lambda: self._on_open_dashboard()),
            pystray.MenuItem("Exit", lambda: self._exit()),
        )
        self._icon = pystray.Icon("hojaiga_interface", image, "Hojaiga", menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def _exit(self) -> None:
        if self._icon is not None:
            self._icon.stop()
        self._on_exit()

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()


# ═══════════════════════════════════════════════════════════════════════
# SECTION: Optional PySide6 GUI bridge (Section 5 — gui_renderer)
# ═══════════════════════════════════════════════════════════════════════

class GUIBridge:
    """Wraps a PySide6 QApplication + main window.

    Instantiated only when PySide6 is importable AND --mode gui was
    requested. All cross-thread updates are marshalled via Qt signals
    to comply with Section 19 (Thread Safety).
    """

    def __init__(self, kernel: "InterfaceKernel") -> None:
        from PySide6.QtWidgets import (  # type: ignore
            QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
            QTreeWidget, QTreeWidgetItem, QDialog, QPushButton, QHBoxLayout,
            QTextEdit, QLineEdit, QProgressBar,
        )
        from PySide6.QtCore import Qt, QObject, Signal  # type: ignore

        self._Qt = Qt
        self._QDialog = QDialog
        self._QPushButton = QPushButton
        self._QVBoxLayout = QVBoxLayout
        self._QHBoxLayout = QHBoxLayout
        self._QLabel = QLabel
        self._QTreeWidget = QTreeWidget
        self._QTreeWidgetItem = QTreeWidgetItem
        self._QLineEdit = QLineEdit
        self._QProgressBar = QProgressBar
        self._QWidget = QWidget

        self.kernel = kernel
        self.app = QApplication.instance() or QApplication(sys.argv)

        class _Bridge(QObject):
            telemetry_signal = Signal(object)
            modal_signal = Signal(object, object)

        self._bridge_qobject = _Bridge()
        self._bridge_qobject.telemetry_signal.connect(self._on_telemetry_main_thread)
        self._bridge_qobject.modal_signal.connect(self._on_modal_main_thread)

        self.window = QMainWindow()
        self.window.setWindowTitle("Hojaiga — Interface Organ")
        self.window.resize(760, 480)

        central = QWidget()
        layout = QVBoxLayout(central)
        self.health_tree = QTreeWidget()
        self.health_tree.setHeaderLabels(["Organ", "Status"])
        layout.addWidget(QLabel("Live Organ Health Tree"))
        layout.addWidget(self.health_tree)

        self.progress_bar = QProgressBar()
        layout.addWidget(QLabel("Active Task Progress"))
        layout.addWidget(self.progress_bar)

        goal_row = QHBoxLayout()
        self.goal_input = QLineEdit()
        self.goal_input.setPlaceholderText("Describe a goal for Hojaiga to execute…")
        submit_btn = QPushButton("Submit Goal")
        submit_btn.clicked.connect(self._submit_goal_clicked)
        goal_row.addWidget(self.goal_input)
        goal_row.addWidget(submit_btn)
        layout.addLayout(goal_row)

        self.window.setCentralWidget(central)
        self.window.closeEvent = self._on_close_event  # type: ignore[assignment]

    def launch_window(self) -> None:
        self.window.show()
        self.kernel.set_ui_mode(UIMode.DASHBOARD_ACTIVE)
        self.app.exec()

    def _submit_goal_clicked(self) -> None:
        text = self.goal_input.text()
        self.goal_input.clear()
        self.kernel.submit_user_goal(text, source="GUI")

    def update_organ_health_tree(self, health_data: dict[str, str]) -> None:
        self._bridge_qobject.telemetry_signal.emit(health_data)

    def _on_telemetry_main_thread(self, health_data: dict[str, str]) -> None:
        self.health_tree.clear()
        for organ, status in health_data.items():
            item = self._QTreeWidgetItem([organ, status])
            self.health_tree.addTopLevelItem(item)

    def show_approval_modal(
        self,
        request: ApprovalPromptRequest,
        on_verdict: Callable[[Verdict, str], None],
    ) -> None:
        self._bridge_qobject.modal_signal.emit(request, on_verdict)

    def _on_modal_main_thread(self, request: ApprovalPromptRequest, on_verdict) -> None:
        dialog = self._QDialog(self.window)
        dialog.setWindowTitle(f"Governance Approval Required — {request.risk_level.value}")
        layout = self._QVBoxLayout(dialog)
        layout.addWidget(self._QLabel(f"Requesting Organ: {request.requesting_organ}"))
        layout.addWidget(self._QLabel(f"Action: {request.action_summary}"))
        if request.policy_violated:
            layout.addWidget(self._QLabel(f"Policy Reference: {request.policy_violated}"))
        btn_row = self._QHBoxLayout()
        approve_btn = self._QPushButton("Approve")
        deny_btn = self._QPushButton("Deny")

        def _approve():
            dialog.accept()
            on_verdict(Verdict.APPROVED, "")

        def _deny():
            dialog.reject()
            on_verdict(Verdict.DENIED, "")

        approve_btn.clicked.connect(_approve)
        deny_btn.clicked.connect(_deny)
        btn_row.addWidget(approve_btn)
        btn_row.addWidget(deny_btn)
        layout.addLayout(btn_row)
        dialog.exec()

    def _on_close_event(self, event) -> None:
        self.kernel.set_ui_mode(UIMode.HEADLESS_TRAY)
        event.accept()


# ═══════════════════════════════════════════════════════════════════════
# SECTION: CLI terminal shell (Section 5 — cli_terminal)
# ═══════════════════════════════════════════════════════════════════════

class CLITerminalShell:
    """Interactive shell for CLI_MODE, operating without Qt dependencies."""

    PROMPT = "hojaiga> "

    def __init__(self, kernel: "InterfaceKernel") -> None:
        self.kernel = kernel
        self._running = False

    def run(self) -> None:
        self._running = True
        self.kernel.set_ui_mode(UIMode.CLI_MODE)
        print("Hojaiga Interface Organ — CLI Mode. Type 'help' for commands.")
        while self._running:
            try:
                line = input(self.PROMPT).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            self._handle_line(line)
        self.kernel.emit_ui_closed()

    def _handle_line(self, line: str) -> None:
        if line in ("exit", "quit"):
            self._running = False
            return
        if line == "help":
            print("Commands: help | status | goal <text> | exit")
            return
        if line == "status":
            print(json.dumps(self.kernel.snapshot_status(), indent=2, default=str))
            return
        if line.startswith("goal "):
            self.kernel.submit_user_goal(line[len("goal "):], source="CLI")
            return
        # Default: treat the entire line as a natural-language goal.
        self.kernel.submit_user_goal(line, source="CLI")

    def stop(self) -> None:
        self._running = False


# ═══════════════════════════════════════════════════════════════════════
# SECTION: Interface Kernel (Section 5 — interface_core / interface_kernel.py)
# ═══════════════════════════════════════════════════════════════════════

class InterfaceKernel:
    """Master IPC socket handler, event router, and UI state synchronizer.

    This is the sole integration point between transports (IPC), renderers
    (GUI/CLI/tray), and the governance dialog subsystem. Owns no automation
    logic (Universal Law 3).
    """

    def __init__(self) -> None:
        self.state = StateBridge()
        self.governance = GovernanceDialogManager(self)
        self.notifications = NotificationEngine()
        self.gui_bridge: Optional[GUIBridge] = None
        self.tray: Optional[TrayManager] = None
        self.cli: Optional[CLITerminalShell] = None

        self._ui_mode = UIMode.HEADLESS_TRAY
        self.previous_mode = UIMode.HEADLESS_TRAY
        self._mode_lock = threading.Lock()

        self._inbound_queue: "queue.Queue[tuple[OpCode, dict[str, Any], Callable]]" = queue.Queue()
        self._active_client_sockets: list[socket.socket] = []
        self._client_lock = threading.Lock()

        self._pending_cli_approval: Optional[Callable[[Verdict, str], None]] = None

        self.ipc_server = IPCServer(self)
        self._dispatch_thread = threading.Thread(target=self._dispatch_loop, name="KernelDispatch", daemon=True)
        self._running = False

    # ---- lifecycle --------------------------------------------------
    def start(self) -> None:
        self._running = True
        self.ipc_server.start()
        self._dispatch_thread.start()
        audit_log("interface_kernel_started", ui_mode=self._ui_mode.value)

    def stop(self) -> None:
        self._running = False
        self.ipc_server.stop()
        self.state.close()
        audit_log("interface_kernel_stopped")

    # ---- UI mode management (Section 13, 14) -------------------------
    def set_ui_mode(self, mode: UIMode) -> None:
        with self._mode_lock:
            if mode == self._ui_mode:
                return
            if self._ui_mode != UIMode.MODAL_AWAITING_HUMAN:
                self.previous_mode = self._ui_mode
            self._ui_mode = mode
        self.state.set_state("ui_mode", mode.value)
        self.broadcast(OpCode.UI_MODE_CHANGED, {"event": EventName.UI_MODE_CHANGED.value, "mode": mode.value})
        audit_log("ui_mode_changed", mode=mode.value)

    @property
    def ui_mode(self) -> UIMode:
        return self._ui_mode

    # ---- inbound RPC handling (Section 7) -----------------------------
    def attach_client_socket(self, sock: socket.socket) -> None:
        with self._client_lock:
            self._active_client_sockets.append(sock)

    def enqueue_inbound(self, op_code: OpCode, payload: dict[str, Any], reply: Callable[[OpCode, dict[str, Any]], None]) -> None:
        self._inbound_queue.put((op_code, payload, reply))

    def _dispatch_loop(self) -> None:
        while self._running:
            try:
                op_code, payload, reply = self._inbound_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._handle_inbound(op_code, payload, reply)
            except Exception as exc:
                LOGGER.error("Error handling inbound frame %s: %s", op_code, exc)
                try:
                    reply(OpCode.GENERIC_ACK, {"ok": False, "error": str(exc)})
                except Exception:
                    pass

    def _handle_inbound(self, op_code: OpCode, payload: dict[str, Any], reply: Callable) -> None:
        if op_code == OpCode.DISPLAY_APPROVAL_PROMPT:
            request = ApprovalPromptRequest.from_json(payload)

            def _on_verdict(response: HumanApprovalResponse) -> None:
                reply(OpCode.APPROVAL_VERDICT, response.to_json())

            self.governance.prompt_user_modal(request, _on_verdict)

        elif op_code == OpCode.UPDATE_TELEMETRY_DISPLAY:
            telemetry = TelemetryUpdatePayload.from_json(payload)
            self.state.set_state("latest_telemetry", asdict(telemetry))
            if self.gui_bridge is not None:
                self.gui_bridge.update_organ_health_tree(telemetry.organ_health)
            reply(OpCode.TELEMETRY_ACK, {"ok": True})

        elif op_code == OpCode.SEND_NOTIFICATION:
            notification = NotificationPayload.from_json(payload)
            self.notifications.send(notification)
            reply(OpCode.NOTIFICATION_ACK, {"ok": True, "notification_id": notification.notification_id})

        elif op_code == OpCode.RENDER_TASK_PROGRESS:
            progress = ProgressUpdatePayload.from_json(payload)
            self.state.set_state(f"progress:{progress.task_id}", asdict(progress))
            reply(OpCode.PROGRESS_ACK, {"ok": True})

        elif op_code == OpCode.GET_ACTIVE_USER_INPUTS:
            pending = self.state.get_state("pending_user_inputs", [])
            reply(OpCode.USER_INPUT_PAYLOAD, {"inputs": pending})

        else:
            reply(OpCode.GENERIC_ACK, {"ok": False, "error": f"Unsupported op_code {op_code}"})

    # ---- outbound event emission (Section 12) --------------------------
    def broadcast(self, op_code: OpCode, payload: dict[str, Any]) -> None:
        with self._client_lock:
            dead: list[socket.socket] = []
            for sock in self._active_client_sockets:
                try:
                    write_frame(sock, op_code, payload)
                except OSError:
                    dead.append(sock)
            for sock in dead:
                self._active_client_sockets.remove(sock)

    def submit_user_goal(self, raw_text: str, source: str) -> None:
        try:
            clean = sanitize_goal(raw_text)
        except ValidationError as exc:
            LOGGER.warning("Rejected goal submission from %s: %s", source, exc)
            self.notifications.send(NotificationPayload(title="Invalid Goal", body=str(exc), severity="WARNING"))
            return
        goal = UserGoalPayload(goal_id=str(uuid.uuid4()), text=clean, source=source)
        self.state.set_state(f"goal:{goal.goal_id}", goal.to_json())
        self.broadcast(OpCode.USER_GOAL_SUBMITTED, {"event": EventName.USER_GOAL_SUBMITTED.value, **goal.to_json()})
        audit_log("user_goal_submitted", goal_id=goal.goal_id, source=source)

    def emit_ui_closed(self) -> None:
        self.broadcast(OpCode.UI_CLOSED, {"event": EventName.UI_CLOSED.value})
        audit_log("ui_closed")

    # ---- CLI-mode governance bridge ------------------------------------
    def cli_bridge_prompt_approval(self, request: ApprovalPromptRequest, on_verdict: Callable[[Verdict, str], None]) -> None:
        print("\n=== GOVERNANCE APPROVAL REQUIRED ===")
        print(f"Risk Level      : {request.risk_level.value}")
        print(f"Requesting Organ: {request.requesting_organ}")
        print(f"Action          : {request.action_summary}")
        if request.policy_violated:
            print(f"Policy Reference: {request.policy_violated}")
        print(f"Timeout         : {request.timeout_ms} ms")
        try:
            answer = input("Approve? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        verdict = Verdict.APPROVED if answer == "y" else Verdict.DENIED
        on_verdict(verdict, "")

    # ---- diagnostics -----------------------------------------------
    def snapshot_status(self) -> dict[str, Any]:
        return {
            "ui_mode": self._ui_mode.value,
            "active_prompts": self.state.active_prompt_count(),
            "ipc_transport": self.ipc_server.transport_description,
            "latest_telemetry": self.state.get_state("latest_telemetry"),
        }


# ═══════════════════════════════════════════════════════════════════════
# SECTION: Entry points
# ═══════════════════════════════════════════════════════════════════════

def run_cli() -> None:
    kernel = InterfaceKernel()
    kernel.start()
    kernel.cli = CLITerminalShell(kernel)
    try:
        kernel.cli.run()
    finally:
        kernel.stop()


def run_headless_tray() -> None:
    kernel = InterfaceKernel()
    kernel.start()
    kernel.set_ui_mode(UIMode.HEADLESS_TRAY)

    stop_event = threading.Event()

    def _open_dashboard() -> None:
        run_gui(existing_kernel=kernel)

    def _on_exit() -> None:
        stop_event.set()

    kernel.tray = TrayManager(on_open_dashboard=_open_dashboard, on_exit=_on_exit)
    kernel.tray.start()
    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        kernel.emit_ui_closed()
        kernel.stop()


def run_gui(existing_kernel: Optional[InterfaceKernel] = None) -> None:
    kernel = existing_kernel or InterfaceKernel()
    if existing_kernel is None:
        kernel.start()
    try:
        kernel.gui_bridge = GUIBridge(kernel)
    except ImportError:
        LOGGER.error("PySide6 is not installed; cannot start DASHBOARD_ACTIVE mode. Falling back to CLI mode.")
        run_cli()
        return
    try:
        kernel.gui_bridge.launch_window()
    finally:
        kernel.emit_ui_closed()
        if existing_kernel is None:
            kernel.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Hojaiga Organ 11 — Interface Organ")
    parser.add_argument(
        "--mode",
        choices=["gui", "cli", "tray"],
        default="cli",
        help="Startup UI mode (default: cli).",
    )
    args = parser.parse_args()

    if args.mode == "gui":
        run_gui()
    elif args.mode == "tray":
        run_headless_tray()
    else:
        run_cli()


# =============================================================================
# Logic Engine: Audio Notification Engine
# =============================================================================
# Satisfies: Sound effects for Work Paused, Resumed, Finished, Critical Attention
# Placement: Bottom of organ_11_interface.py (append-only, no existing code modified)

class AudioNotificationEngine:
    """Cross-platform audio notification player that triggers specific .wav files
    when the orchestrator emits state changes (WORK_PAUSED, RESUMED, FINISHED,
    CRITICAL_ATTENTION). Does NOT pop up any UI — only plays audio.
    
    Uses winsound (Windows built-in, zero-cost) with fallback to playsound.
    """

    # Default sound mappings — can be overridden via set_sound()
    _DEFAULT_SOUNDS = {
        "WORK_PAUSED": None,
        "WORK_RESUMED": None,
        "WORK_FINISHED": None,
        "CRITICAL_ATTENTION": None,
        "NOTIFICATION": None,
    }

    def __init__(self, sounds_dir: str | None = None):
        import os
        self._sounds = dict(self._DEFAULT_SOUNDS)
        self._sounds_dir = sounds_dir or os.path.join(
            os.path.dirname(__file__), ""
        )
        # Auto-discover .wav files in the organ directory
        self._auto_discover_sounds()

    def _auto_discover_sounds(self):
        """Look for common wav files in the sounds directory."""
        import os
        if os.path.isdir(self._sounds_dir):
            for f in os.listdir(self._sounds_dir):
                if f.endswith(".wav"):
                    # Map the first found .wav to NOTIFICATION by default
                    full_path = os.path.join(self._sounds_dir, f)
                    if "verify" in f.lower():
                        self._sounds["WORK_FINISHED"] = full_path
                    elif "voice" in f.lower():
                        self._sounds["CRITICAL_ATTENTION"] = full_path
                    elif not self._sounds.get("NOTIFICATION"):
                        self._sounds["NOTIFICATION"] = full_path

    def set_sound(self, event_type: str, wav_path: str) -> None:
        """Override the .wav file for a specific event type."""
        self._sounds[event_type] = wav_path

    def play(self, event_type: str) -> dict:
        """Play the sound associated with an event type. Non-blocking."""
        import os
        wav_path = self._sounds.get(event_type)
        if not wav_path or not os.path.isfile(wav_path):
            return {"played": False, "reason": f"No sound file mapped for {event_type}"}

        try:
            if os.name == "nt":
                import winsound
                # SND_ASYNC = play asynchronously so it doesn't block the automation
                winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                # Fallback for non-Windows: use subprocess to call aplay/afplay
                import subprocess
                subprocess.Popen(["aplay", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"played": True, "event_type": event_type, "file": wav_path}
        except Exception as e:
            return {"played": False, "reason": str(e)}

    def play_work_paused(self) -> dict:
        return self.play("WORK_PAUSED")

    def play_work_resumed(self) -> dict:
        return self.play("WORK_RESUMED")

    def play_work_finished(self) -> dict:
        return self.play("WORK_FINISHED")

    def play_critical_attention(self) -> dict:
        return self.play("CRITICAL_ATTENTION")

    def report(self) -> dict:
        return {"configured_sounds": {k: v for k, v in self._sounds.items() if v}}


if __name__ == "__main__":
    main()
