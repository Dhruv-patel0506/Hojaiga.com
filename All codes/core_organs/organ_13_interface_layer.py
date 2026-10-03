"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 13
Name: Interface Layer

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Interface Layer]
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
Dependencies: traceback, hashlib, soundfile, dataclasses, tkinter...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_13_interface_layer.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
HAOS Organ 13 — Interface Layer
Single-file compiled implementation.

Public entrypoint: InterfaceLayerOrgan
Sockets:  SOCK_IN_*, SOCK_OUT_*  (in-process pub/sub, replace with real transport bindings)
Pipelines: PIPE_* (ordered async processing chains)

This organ is the sole ingress/egress boundary of HAOS. It performs:
Authentication, Authorization, Validation, Session Management,
Request Dispatch, Notification, Plugin/LLM/Knowledge management surfaces.

It contains ZERO business logic, ZERO automation execution, ZERO decisioning.
All standardized commands are forwarded to the CNS Socket for downstream handling.
"""


import asyncio
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
import uuid
import os
import threading
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

# Voice / AI Audio Dependencies
sr = None
pyttsx3 = None
Groq = None
SpeakerRecognition = None
speechbrain = None
try:
    import speech_recognition as sr
    import pyttsx3
    from groq import Groq
    from speechbrain.inference.speaker import SpeakerRecognition
    import speechbrain.utils.fetching
except ImportError:
    # They will degrade gracefully if not installed
    sr = None
    pyttsx3 = None
    Groq = None
    SpeakerRecognition = None
    speechbrain = None

# ─────────────────────────────────────────────────────────────────────────
# LOGGING / AUDIT
# ─────────────────────────────────────────────────────────────────────────

logger = logging.getLogger("haos.interface_layer")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logger.addHandler(_h)


class AuditSystem:
    """Append-only audit trail (Law Book: Universal Law 1, 8; Policy Manual Ch.8/9)."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def record(self, execution_id: str, component: str, action: str,
               status: str, detail: Optional[dict[str, Any]] = None) -> None:
        entry = {
            "execution_id": execution_id,
            "timestamp": time.time(),
            "component": component,
            "action": action,
            "status": status,
            "detail": detail or {},
        }
        self._entries.append(entry)
        logger.info("AUDIT %s", entry)

    def history(self) -> list[dict[str, Any]]:
        return list(self._entries)


# ─────────────────────────────────────────────────────────────────────────
# ERROR CATALOG
# ─────────────────────────────────────────────────────────────────────────

class InterfaceErrorCode(Enum):
    INVALID_PAYLOAD = "IL-400-INVALID_PAYLOAD"
    UNAUTHENTICATED = "IL-401-UNAUTHENTICATED"
    UNAUTHORIZED = "IL-403-UNAUTHORIZED"
    NOT_FOUND = "IL-404-NOT_FOUND"
    RATE_LIMITED = "IL-429-RATE_LIMITED"
    SESSION_EXPIRED = "IL-440-SESSION_EXPIRED"
    INTERNAL_ERROR = "IL-500-INTERNAL_ERROR"
    DISPATCH_FAILURE = "IL-502-DISPATCH_FAILURE"


class InterfaceLayerError(Exception):
    def __init__(self, code: InterfaceErrorCode, message: str,
                 detail: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}

    def to_response(self) -> dict[str, Any]:
        return {"error_code": self.code.value, "message": self.message, "detail": self.detail}


# ─────────────────────────────────────────────────────────────────────────
# SOCKET BUS (in-process pub/sub abstraction — swappable transport)
# ─────────────────────────────────────────────────────────────────────────

class SocketBus:
    """Implements the documented Socket contract: publish/subscribe with
    named channels. Real network transports (WSS, REST, IPC) adapt onto this."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[dict[str, Any]], Awaitable[None]]]] = {}

    def subscribe(self, channel: str, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._subscribers.setdefault(channel, []).append(handler)

    async def publish(self, channel: str, frame: dict[str, Any]) -> None:
        for handler in self._subscribers.get(channel, []):
            await handler(frame)


# Documented socket channel names
SOCK_IN_TELEMETRY = "SOCK_IN_TELEMETRY"
SOCK_IN_TASK_STATUS = "SOCK_IN_TASK_STATUS"
SOCK_OUT_SYSTEM_COMMAND = "SOCK_OUT_SYSTEM_COMMAND"
SOCK_OUT_CNS_DISPATCH = "SOCK_OUT_CNS_DISPATCH"
SOCK_IN_NOTIFICATION = "SOCK_IN_NOTIFICATION"
SOCK_OUT_PLUGIN_COMMAND = "SOCK_OUT_PLUGIN_COMMAND"
SOCK_OUT_LLM_COMMAND = "SOCK_OUT_LLM_COMMAND"


# ─────────────────────────────────────────────────────────────────────────
# AUTHENTICATION
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class Credential:
    user_id: str
    password_hash: str
    roles: list[str]
    permissions: list[str]


class AuthenticationGateway:
    """Cryptographic identity verification (HMAC-signed tokens)."""

    def __init__(self, signing_key: Optional[bytes] = None) -> None:
        self._signing_key = signing_key or secrets.token_bytes(32)
        self._credentials: dict[str, Credential] = {}

    def register_user(self, user_id: str, password: str, roles: list[str],
                       permissions: list[str]) -> None:
        pw_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
        self._credentials[user_id] = Credential(user_id, pw_hash, roles, permissions)

    def authenticate(self, user_id: str, password: str) -> Credential:
        cred = self._credentials.get(user_id)
        pw_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
        if cred is None or not hmac.compare_digest(cred.password_hash, pw_hash):
            raise InterfaceLayerError(InterfaceErrorCode.UNAUTHENTICATED, "Invalid credentials")
        return cred

    def sign(self, payload: str) -> str:
        return hmac.new(self._signing_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify_signature(self, payload: str, signature: str) -> bool:
        expected = self.sign(payload)
        return hmac.compare_digest(expected, signature)


# ─────────────────────────────────────────────────────────────────────────
# AUTHORIZATION (RBAC / ABAC)
# ─────────────────────────────────────────────────────────────────────────

class AuthorizationEngine:
    def __init__(self) -> None:
        self._role_permissions: dict[str, set[str]] = {
            "admin": {"*"},
            "operator": {"task.read", "task.create", "telemetry.read", "plugin.read"},
            "viewer": {"telemetry.read", "task.read"},
        }

    def is_permitted(self, roles: list[str], required_permission: str) -> bool:
        for role in roles:
            perms = self._role_permissions.get(role, set())
            if "*" in perms or required_permission in perms:
                return True
        return False

    def enforce(self, roles: list[str], required_permission: str) -> None:
        if not self.is_permitted(roles, required_permission):
            raise InterfaceLayerError(
                InterfaceErrorCode.UNAUTHORIZED,
                f"Missing permission '{required_permission}'",
                {"roles": roles},
            )


# ─────────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────────

class InputValidator:
    """Structural and semantic validation of ingress payloads."""

    _SAFE_STRING_RE = re.compile(r"^[\w\s\-\.\,\:\/@]{0,4096}$", re.UNICODE)

    def validate_schema(self, payload: dict[str, Any], required_fields: list[str]) -> None:
        missing = [f for f in required_fields if f not in payload]
        if missing:
            raise InterfaceLayerError(
                InterfaceErrorCode.INVALID_PAYLOAD,
                f"Missing required fields: {missing}",
            )

    def sanitize_string(self, value: str, field_name: str) -> str:
        if not isinstance(value, str) or not self._SAFE_STRING_RE.match(value):
            raise InterfaceLayerError(
                InterfaceErrorCode.INVALID_PAYLOAD,
                f"Field '{field_name}' failed sanitation constraints",
            )
        return value


# ─────────────────────────────────────────────────────────────────────────
# RATE LIMITING
# ─────────────────────────────────────────────────────────────────────────

class RateLimiter:
    def __init__(self, max_requests: int = 100, window_seconds: float = 60.0) -> None:
        self._max_requests = max_requests
        self._window = window_seconds
        self._buckets: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, [])
        while bucket and now - bucket[0] > self._window:
            bucket.pop(0)
        if len(bucket) >= self._max_requests:
            return False
        bucket.append(now)
        return True

    def enforce(self, key: str) -> None:
        if not self.allow(key):
            raise InterfaceLayerError(InterfaceErrorCode.RATE_LIMITED, f"Rate limit exceeded for '{key}'")


# ─────────────────────────────────────────────────────────────────────────
# SESSION MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class UserSessionContext:
    session_id: str
    user_id: str
    roles: list[str]
    permissions: list[str]
    issued_at: float
    expires_at: float
    last_activity: float
    is_mfa_authenticated: bool = False


class SessionManager:
    def __init__(self, ttl_seconds: float = 3600.0, max_concurrent_per_user: int = 5) -> None:
        self._ttl = ttl_seconds
        self._max_concurrent = max_concurrent_per_user
        self._sessions: dict[str, UserSessionContext] = {}

    def create_session(self, user_id: str, roles: list[str],
                        permissions: list[str]) -> UserSessionContext:
        active = [s for s in self._sessions.values() if s.user_id == user_id]
        if len(active) >= self._max_concurrent:
            oldest = min(active, key=lambda s: s.last_activity)
            self.revoke_session(oldest.session_id)

        now = time.time()
        session = UserSessionContext(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            roles=roles,
            permissions=permissions,
            issued_at=now,
            expires_at=now + self._ttl,
            last_activity=now,
        )
        self._sessions[session.session_id] = session
        return session

    def validate_session(self, session_id: str) -> UserSessionContext:
        session = self._sessions.get(session_id)
        if session is None:
            raise InterfaceLayerError(InterfaceErrorCode.SESSION_EXPIRED, "Session not found")
        if time.time() > session.expires_at:
            del self._sessions[session_id]
            raise InterfaceLayerError(InterfaceErrorCode.SESSION_EXPIRED, "Session expired")
        session.last_activity = time.time()
        return session

    def revoke_session(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def purge_expired(self) -> int:
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if now > s.expires_at]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)


# ─────────────────────────────────────────────────────────────────────────
# REQUEST DISPATCHER
# ─────────────────────────────────────────────────────────────────────────

class TransportProtocol(Enum):
    REST_HTTPS = "REST_HTTPS"
    CLI_PIPE = "CLI_PIPE"
    WEBSOCKET_WSS = "WEBSOCKET_WSS"
    NAMED_PIPE = "NAMED_PIPE"
    LOCAL_SHARED_MEM = "LOCAL_SHARED_MEM"


@dataclass
class GatewayRequestFrame:
    request_id: str
    session_id: Optional[str]
    protocol: TransportProtocol
    payload: dict[str, Any]
    ingress_timestamp_ms: int


@dataclass
class GatewayResponseFrame:
    request_id: str
    status_code: int
    payload: dict[str, Any]
    error_message: Optional[str]
    egress_timestamp_ms: int


class RequestDispatcher:
    """Priority queue broker forwarding standardized commands to the CNS socket."""

    def __init__(self, socket_bus: SocketBus, audit: AuditSystem, max_queue: int = 10_000) -> None:
        self._bus = socket_bus
        self._audit = audit
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue)

    async def dispatch(self, frame: GatewayRequestFrame, session: UserSessionContext) -> GatewayResponseFrame:
        command = {
            "request_id": frame.request_id,
            "session_id": session.session_id,
            "user_id": session.user_id,
            "roles": session.roles,
            "payload": frame.payload,
            "protocol": frame.protocol.value,
        }
        try:
            await self._bus.publish(SOCK_OUT_CNS_DISPATCH, command)
            self._audit.record(frame.request_id, "RequestDispatcher", "dispatch", "SUCCESS", command)
            return GatewayResponseFrame(
                request_id=frame.request_id,
                status_code=202,
                payload={"accepted": True},
                error_message=None,
                egress_timestamp_ms=int(time.time() * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            self._audit.record(frame.request_id, "RequestDispatcher", "dispatch", "FAILURE", {"error": str(exc)})
            raise InterfaceLayerError(InterfaceErrorCode.DISPATCH_FAILURE, str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────
# NOTIFICATION CENTER
# ─────────────────────────────────────────────────────────────────────────

class NotificationCenter:
    def __init__(self, socket_bus: SocketBus) -> None:
        self._bus = socket_bus
        self._subscribers: dict[str, list[Callable[[dict[str, Any]], Awaitable[None]]]] = {}

    def subscribe(self, session_id: str, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._subscribers.setdefault(session_id, []).append(handler)

    async def notify(self, session_id: str, message: dict[str, Any]) -> None:
        for handler in self._subscribers.get(session_id, []):
            await handler(message)
        await self._bus.publish(SOCK_IN_NOTIFICATION, {"session_id": session_id, **message})


# ─────────────────────────────────────────────────────────────────────────
# PLUGIN MANAGER (management surface only — execution lives in Plugin Runtime organ)
# ─────────────────────────────────────────────────────────────────────────

class PluginManagerSurface:
    def __init__(self, socket_bus: SocketBus) -> None:
        self._bus = socket_bus
        self._registry: dict[str, dict[str, Any]] = {}

    def list_plugins(self) -> list[dict[str, Any]]:
        return list(self._registry.values())

    async def request_install(self, plugin_id: str, source: str) -> None:
        await self._bus.publish(SOCK_OUT_PLUGIN_COMMAND, {"action": "install", "plugin_id": plugin_id, "source": source})

    async def request_toggle(self, plugin_id: str, enabled: bool) -> None:
        await self._bus.publish(SOCK_OUT_PLUGIN_COMMAND, {"action": "toggle", "plugin_id": plugin_id, "enabled": enabled})


# ─────────────────────────────────────────────────────────────────────────
# LLM MANAGER (management surface only — Brain runtime lives elsewhere)
# ─────────────────────────────────────────────────────────────────────────

class LLMManagerSurface:
    def __init__(self, socket_bus: SocketBus) -> None:
        self._bus = socket_bus

    async def request_status(self) -> None:
        await self._bus.publish(SOCK_OUT_LLM_COMMAND, {"action": "status"})

    async def request_shutdown(self) -> None:
        await self._bus.publish(SOCK_OUT_LLM_COMMAND, {"action": "shutdown"})


# ─────────────────────────────────────────────────────────────────────────
# KNOWLEDGE / MEMORY / HISTORY VIEWERS (read-only surfaces)
# ─────────────────────────────────────────────────────────────────────────

class ReadOnlyViewer:
    """Generic read-only projection surface for Knowledge, Memory, and History.
    Actual storage lives in the Memory/Knowledge organs; this issues query
    commands over the CNS socket and returns whatever is published back."""

    def __init__(self, socket_bus: SocketBus, channel: str) -> None:
        self._bus = socket_bus
        self._channel = channel

    async def query(self, filters: dict[str, Any]) -> None:
        await self._bus.publish(self._channel, {"action": "query", "filters": filters})


# ─────────────────────────────────────────────────────────────────────────
# INTERFACE GATEWAY (single non-bypassable boundary)
# ─────────────────────────────────────────────────────────────────────────

class InterfaceGateway:
    def __init__(
        self,
        auth: AuthenticationGateway,
        authz: AuthorizationEngine,
        validator: InputValidator,
        rate_limiter: RateLimiter,
        sessions: SessionManager,
        dispatcher: RequestDispatcher,
        audit: AuditSystem,
    ) -> None:
        self._auth = auth
        self._authz = authz
        self._validator = validator
        self._rate_limiter = rate_limiter
        self._sessions = sessions
        self._dispatcher = dispatcher
        self._audit = audit

    async def process_inbound(
        self,
        protocol: TransportProtocol,
        session_id: Optional[str],
        raw_payload: dict[str, Any],
        required_permission: str,
        client_key: str,
    ) -> GatewayResponseFrame:
        request_id = str(uuid.uuid4())
        try:
            self._rate_limiter.enforce(client_key)
            self._validator.validate_schema(raw_payload, ["command"])

            if session_id is None:
                raise InterfaceLayerError(InterfaceErrorCode.UNAUTHENTICATED, "Missing session")
            session = self._sessions.validate_session(session_id)
            self._authz.enforce(session.roles, required_permission)

            frame = GatewayRequestFrame(
                request_id=request_id,
                session_id=session_id,
                protocol=protocol,
                payload=raw_payload,
                ingress_timestamp_ms=int(time.time() * 1000),
            )
            return await self._dispatcher.dispatch(frame, session)

        except InterfaceLayerError as err:
            self._audit.record(request_id, "InterfaceGateway", "process_inbound", "REJECTED", err.to_response())
            return GatewayResponseFrame(
                request_id=request_id,
                status_code=_status_for(err.code),
                payload={},
                error_message=err.message,
                egress_timestamp_ms=int(time.time() * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            self._audit.record(request_id, "InterfaceGateway", "process_inbound", "ERROR", {"error": str(exc)})
            return GatewayResponseFrame(
                request_id=request_id,
                status_code=500,
                payload={},
                error_message="Internal interface error",
                egress_timestamp_ms=int(time.time() * 1000),
            )


def _status_for(code: InterfaceErrorCode) -> int:
    mapping = {
        InterfaceErrorCode.INVALID_PAYLOAD: 400,
        InterfaceErrorCode.UNAUTHENTICATED: 401,
        InterfaceErrorCode.UNAUTHORIZED: 403,
        InterfaceErrorCode.NOT_FOUND: 404,
        InterfaceErrorCode.RATE_LIMITED: 429,
        InterfaceErrorCode.SESSION_EXPIRED: 440,
        InterfaceErrorCode.INTERNAL_ERROR: 500,
        InterfaceErrorCode.DISPATCH_FAILURE: 502,
    }
    return mapping.get(code, 500)


# ─────────────────────────────────────────────────────────────────────────
# EDGE ADAPTERS — CLI
# ─────────────────────────────────────────────────────────────────────────

class CLIAdapter:
    def __init__(self, gateway: InterfaceGateway) -> None:
        self._gateway = gateway

    async def handle_line(self, session_id: Optional[str], command: str, args: dict[str, Any],
                           client_key: str = "cli-local") -> GatewayResponseFrame:
        payload = {"command": command, "args": args}
        return await self._gateway.process_inbound(
            TransportProtocol.CLI_PIPE, session_id, payload, "task.create", client_key
        )


# ─────────────────────────────────────────────────────────────────────────
# EDGE ADAPTERS — REST (framework-agnostic handler; bind to FastAPI/Flask externally)
# ─────────────────────────────────────────────────────────────────────────

class RESTAdapter:
    def __init__(self, gateway: InterfaceGateway) -> None:
        self._gateway = gateway

    async def handle_request(self, headers: dict[str, str], body: dict[str, Any],
                              required_permission: str, remote_addr: str) -> dict[str, Any]:
        session_id = headers.get("X-Session-Id")
        response = await self._gateway.process_inbound(
            TransportProtocol.REST_HTTPS, session_id, body, required_permission, remote_addr
        )
        return {
            "request_id": response.request_id,
            "status_code": response.status_code,
            "payload": response.payload,
            "error_message": response.error_message,
        }


# ─────────────────────────────────────────────────────────────────────────
# EDGE ADAPTERS — WEBSOCKET / IPC
# ─────────────────────────────────────────────────────────────────────────

class WebSocketAdapter:
    def __init__(self, gateway: InterfaceGateway, notifications: NotificationCenter) -> None:
        self._gateway = gateway
        self._notifications = notifications

    async def handle_frame(self, session_id: str, message: dict[str, Any], client_key: str) -> GatewayResponseFrame:
        required_permission = message.get("required_permission", "task.read")
        return await self._gateway.process_inbound(
            TransportProtocol.WEBSOCKET_WSS, session_id, message, required_permission, client_key
        )

    def register_stream(self, session_id: str, on_message: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._notifications.subscribe(session_id, on_message)


# ─────────────────────────────────────────────────────────────────────────
# ORGAN FACADE — single import surface
# ─────────────────────────────────────────────────────────────────────────

class InterfaceLayerOrgan:
    """Top-level composition root for Organ 13. Wires every subcomponent
    according to the documented socket/pipeline contracts."""

    def __init__(self) -> None:
        self.socket_bus = SocketBus()
        self.audit = AuditSystem()

        self.auth = AuthenticationGateway()
        self.authz = AuthorizationEngine()
        self.validator = InputValidator()
        self.rate_limiter = RateLimiter()
        self.sessions = SessionManager()
        self.dispatcher = RequestDispatcher(self.socket_bus, self.audit)

        self.gateway = InterfaceGateway(
            self.auth, self.authz, self.validator, self.rate_limiter,
            self.sessions, self.dispatcher, self.audit,
        )

        self.notifications = NotificationCenter(self.socket_bus)
        self.plugin_manager = PluginManagerSurface(self.socket_bus)
        self.llm_manager = LLMManagerSurface(self.socket_bus)
        self.knowledge_viewer = ReadOnlyViewer(self.socket_bus, SOCK_OUT_CNS_DISPATCH)
        self.memory_viewer = ReadOnlyViewer(self.socket_bus, SOCK_OUT_CNS_DISPATCH)
        self.history_viewer = ReadOnlyViewer(self.socket_bus, SOCK_OUT_CNS_DISPATCH)

        self.cli = CLIAdapter(self.gateway)
        self.rest = RESTAdapter(self.gateway)
        self.websocket = WebSocketAdapter(self.gateway, self.notifications)

        self.cns: Optional[Any] = None

    def login(self, user_id: str, password: str) -> UserSessionContext:
        cred = self.auth.authenticate(user_id, password)
        return self.sessions.create_session(user_id, cred.roles, cred.permissions)

    def logout(self, session_id: str) -> bool:
        return self.sessions.revoke_session(session_id)

    async def start_cns(self, bus: Any) -> None:
        """Connect this organ to the central nervous system event bus."""
        self.cns = bus
        logger.info("InterfaceLayerOrgan connected to CNS.")

    async def submit_command(
        self,
        raw_command: Optional[str] = None,
        command: Optional[str] = None,
        expected_text: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """Ingests a command through the interface layer and dispatches to CNS."""
        from core_organs.organ_02_cns_single_file import EventEnvelope

        actual_command = raw_command or command or ""
        tid = task_id or str(uuid.uuid4())
        payload: dict[str, Any] = {"command": actual_command}
        if expected_text is not None:
            payload["expected_text"] = expected_text

        envelope = EventEnvelope(
            topic="sock.cns.inbound",
            source_organ="organ_13_interface",
            payload={"payload": payload, "request_id": tid},
        )
        if self.cns is not None:
            await self.cns.publish(envelope)
        else:
            logger.warning("InterfaceLayerOrgan.submit_command called before CNS connection established.")
        return tid

    async def housekeeping_loop(self, interval_seconds: float = 60.0) -> None:
        """Background loop: purge expired sessions (never blocks ingress)."""
        while True:
            purged = self.sessions.purge_expired()
            if purged:
                logger.info("Purged %d expired sessions", purged)
            await asyncio.sleep(interval_seconds)


# ─────────────────────────────────────────────────────────────────────────
# HOJAIGA VOICE INTERFACE (HOJAIGA MODE)
# ─────────────────────────────────────────────────────────────────────────

class HojaigaVoiceInterface:
    def __init__(self, organ: InterfaceLayerOrgan, session: UserSessionContext, submit_callback):
        self.organ = organ
        self.session = session
        self.submit_callback = submit_callback
        self.is_booted = False
        self.engine_powered_on = False
        self.is_sleeping = False
        self.ui_label: Optional[Any] = None
        self.ptt_active = False
        
        # Initialize Groq client
        self.groq_client = None
        try:
            if Groq is not None:
                # Get API key from environment or configuration
                api_key = os.getenv("GROQ_API_KEY")
                if api_key:
                    self.groq_client = Groq(api_key=api_key)
                else:
                    logger.warning("GROQ_API_KEY not found in environment")
        except Exception as e:
            logger.warning(f"Failed to initialize Groq client: {e}")
        
        # Load audio tools
        self.sr = None
        self.recognizer = None
        self.mic = None
        try:
            self.sr = sr
            if self.sr is None:
                raise NameError("speech_recognition is not available")

            self.recognizer = self.sr.Recognizer()
            # Make the microphone extremely sensitive to catch whispers
            self.recognizer.energy_threshold = 150
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.dynamic_energy_ratio = 1.2  # Less aggressive noise floor adjustment
            self.recognizer.pause_threshold = 0.8

            from user_io.local_stt_engine import LocalSTTEngine
            self.stt_engine = LocalSTTEngine(model_size="small")
            self.stt_engine.warm_up()

            self.mic = self.sr.Microphone()
        except (NameError, AttributeError) as e:
            logger.error(f"Voice dependencies missing: {e}")
            self.sr = None
            self.recognizer = None
            self.mic = None

        # Load Biometrics (SpeechBrain)
        self.profile_path = os.path.join(os.path.dirname(__file__), "voice_profile.wav")
        self.config_path = os.path.join(os.path.dirname(__file__), "voice_config.json")
        self.verification_model = None
        try:
            if speechbrain is None or SpeakerRecognition is None:
                raise NameError("speechbrain or SpeakerRecognition is not available")

            logger.info("Initializing Voice Biometrics... (This may take a few minutes the very first time as it downloads the AI model from HuggingFace. DO NOT CLOSE!)")
            self.verification_model = SpeakerRecognition.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                run_opts={"device": "cpu"},
                local_strategy=speechbrain.utils.fetching.LocalStrategy.COPY,
            )
            logger.info("Voice Biometrics model loaded successfully.")
        except (NameError, AttributeError, TypeError) as e:
            logger.warning(f"Speaker verification model failed to load: {e}")
            self.verification_model = None

        self.security_question = ""
        self.security_answer = ""
        self._load_config()

    def _load_config(self):
        # The user has explicitly set their question and answers. We bypass the json load.
        self.security_question = "What is the name of your grandmother?"
        self.security_answers = ["lila", "liaben", "lilabaa", "manjibaa", "manjulaben", "leela", "lyla", "leila"]

    def set_ui_status(self, status: str):
        if self.ui_label is not None:
            try:
                self.ui_label.config(text=status)
            except: pass

    def speak(self, text: str):
        logger.info(f"Hojaiga Voice: {text}")
        self.set_ui_status(f"Speaking: {text}")
        try:
            import pyttsx3
            tts = pyttsx3.init()
            tts.setProperty('rate', 170)
            tts.say(text)
            tts.runAndWait()
        except Exception as e:
            logger.error(f"TTS Error: {e}")

    def transcribe_audio_groq(self, audio_data) -> str:
        if self.groq_client is None:
            # Fall back to the 100% free, offline fast-whisper model
            try:
                return self.stt_engine.transcribe(audio_data).lower().strip()
            except Exception as e:
                logger.error(f"Local STT fallback failed: {e}")
                return ""

        # Save to temp wav file
        temp_wav = os.path.join(os.path.dirname(__file__), "temp_stt.wav")
        with open(temp_wav, "wb") as f:
            f.write(audio_data.get_wav_data())

        try:
            with open(temp_wav, "rb") as f:
                transcription = self.groq_client.audio.transcriptions.create(
                    file=("temp.wav", f.read()),
                    model="whisper-large-v3",
                    response_format="json",
                    prompt="boot up, hojaiga", # Biases Whisper to listen for these words even in heavy noise
                    temperature=0.0
                )
            return transcription.text.lower().strip()
        except Exception as e:
            logger.error(f"Groq STT failed: {e}")
            if "Rate limit" in str(e) or "429" in str(e):
                self.speak("I'm sorry, my voice transcription service has hit a rate limit. Please wait a moment before speaking again.")
            return ""

    def verify_speaker(self, audio_data) -> bool:
        if not self.verification_model or not os.path.exists(self.profile_path):
            return True # Fallback if no biometrics setup
            
        temp_wav = os.path.join(os.path.dirname(__file__), "temp_verify.wav")
        with open(temp_wav, "wb") as f:
            f.write(audio_data.get_wav_data())
            
        try:
            import torch
            import soundfile as sf
            x, _ = sf.read(self.profile_path)
            y, _ = sf.read(temp_wav)
            
            # Ensure 1D to 2D tensor (Batch=1, Time)
            x = torch.tensor(x, dtype=torch.float32)
            y = torch.tensor(y, dtype=torch.float32)
            if x.ndim == 1: x = x.unsqueeze(0)
            if y.ndim == 1: y = y.unsqueeze(0)
            
            # Extract embeddings and compute cosine similarity
            emb_x = self.verification_model.encode_batch(x)
            emb_y = self.verification_model.encode_batch(y)
            score = torch.nn.functional.cosine_similarity(emb_x, emb_y, dim=-1).mean().item()
            
            logger.info(f"Biometric Match Score: {score:.3f}")
            # Dropped threshold to 0.05 to allow highly whispered/noisy matches
            return score > 0.05
        except Exception as e:
            import traceback
            logger.error(f"Verification error: {e}")
            logger.error(traceback.format_exc())
            return False

    def setup_voice_profile(self):
        if not os.path.exists(self.profile_path):
            if self.mic is None or self.recognizer is None:
                logger.error("Microphone or recognizer not available for voice profile setup")
                return
            self.speak("Initial setup required. Please say the following phrase to register your voice print: 'Hojaiga is the ultimate automation system.'")
            try:
                with self.mic as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=1)
                    audio = self.recognizer.listen(source, timeout=10)
                    with open(self.profile_path, "wb") as f:
                        f.write(audio.get_wav_data())
                self.speak("Voice print successfully registered. Setup complete.")
            except Exception as e:
                logger.error(f"Voice profile setup failed: {e}")

    def run_loop(self):
        import speech_recognition as sr

        if not self.sr or self.mic is None or self.recognizer is None:
            logger.error("Voice system unavailable: microphone or recognizer is not initialized")
            return
        self.setup_voice_profile()
        self.speak("Hojaiga Voice Interface online. Waiting for boot sequence.")

        import keyboard
        import ctypes
        self.force_record = False
        self.is_active = False
        
        def is_trigger_pressed():
            if self.force_record:
                return True
            try:
                if os.name == 'nt':
                    # Windows kernel hardware buffer keycodes
                    VK_LCONTROL = 0xA2
                    VK_RCONTROL = 0xA3
                    VK_OEM_3 = 0xC0  # ~ or ` key
                    
                    l_ctrl = bool(ctypes.windll.user32.GetAsyncKeyState(VK_LCONTROL) & 0x8000)
                    r_ctrl = bool(ctypes.windll.user32.GetAsyncKeyState(VK_RCONTROL) & 0x8000)
                    tilde = bool(ctypes.windll.user32.GetAsyncKeyState(VK_OEM_3) & 0x8000)
                    
                    # STRICTLY require BOTH Left Ctrl AND Right Ctrl held down together, OR ~
                    return tilde or (l_ctrl and r_ctrl)
                else:
                    return keyboard.is_pressed('~') or keyboard.is_pressed('`') or (keyboard.is_pressed('left ctrl') and keyboard.is_pressed('right ctrl'))
            except Exception:
                return False

        while True:
            if not is_trigger_pressed():
                self.is_active = False
                time.sleep(0.1)
                continue

            self.is_active = True
            self.set_ui_status("Listening...")
            frames = []
            try:
                with self.mic as source:
                    # Record audio while trigger is held or force_record is True
                    start_time = time.time()
                    while is_trigger_pressed() or (self.force_record and time.time() - start_time < 5.0):
                        try:
                            # Use record() instead of listen() to strictly enforce the PTT button state
                            chunk = self.recognizer.record(source, duration=0.2)
                            frames.append(chunk.frame_data)
                        except Exception:
                            continue
                    
                    self.force_record = False
                    sample_rate = source.SAMPLE_RATE
                    sample_width = source.SAMPLE_WIDTH
            except Exception as e:
                logger.error(f"Audio read error: {e}")
                self.force_record = False
                continue

            if not frames:
                continue

            combined_raw = b"".join(frames)
            audio = sr.AudioData(combined_raw, sample_rate, sample_width)
            
            self.set_ui_status("Transcribing...")
            # Use Groq for robust accent and language support
            text = self.transcribe_audio_groq(audio).lower().strip()
            
            if not text.strip():
                continue
                
            if not self.is_booted:
                if "boot up" in text:
                    self.engine_powered_on = True
                    self.set_ui_status("Verifying Biometrics...")
                    if self.verify_speaker(audio):
                        self.speak(self.security_question)
                        self.set_ui_status("Hold trigger to speak password...")
                        
                        # Wait for trigger to speak password
                        while not is_trigger_pressed():
                            time.sleep(0.1)
                            
                        self.set_ui_status("Listening for password...")
                        ans_frames = []
                        with self.mic as source:
                            while is_trigger_pressed():
                                try:
                                    ans_chunk = self.recognizer.record(source, duration=0.2)
                                    ans_frames.append(ans_chunk.frame_data)
                                except Exception:
                                    continue
                        
                        if ans_frames:
                            ans_audio = sr.AudioData(b"".join(ans_frames), sample_rate, sample_width)
                            self.set_ui_status("Checking Password...")
                            ans_text = self.transcribe_audio_groq(ans_audio).lower().strip()
                            logger.info(f"Hojaiga Voice heard password: '{ans_text}'")
                            
                            if any(ans in ans_text for ans in self.security_answers):
                                self.is_booted = True
                                self.speak("Password accepted. System booted and ready for tasks.")
                            else:
                                self.speak("Incorrect password. Boot sequence aborted.")
                        else:
                            self.speak("No password provided. Aborting.")
                    else:
                        self.speak("Biometric verification failed. Unauthorized voice detected.")
            else:
                if self.is_sleeping:
                    if text:
                        # User spoke while sleeping! Wake up UI and ask for password directly
                        if self.ui_label:
                            try:
                                self.ui_label.master.deiconify()
                            except: pass
                        self.speak("If you want the voice command to activate, please perform the bootup sequence! Please provide the password.")
                        
                        self.set_ui_status("Awaiting Password...")
                        if self.mic is None or self.recognizer is None:
                            logger.error("Microphone unavailable for password capture")
                            continue
                        with self.mic as source:
                            ans_audio = self.recognizer.record(source, duration=3)
                        self.set_ui_status("Checking Password...")
                        ans_text = self.stt_engine.transcribe(ans_audio, prompt="lila, liaben, lilabaa, manjibaa, manjulaben, leela, lyla, leila").lower().strip()
                        
                        if any(ans in ans_text for ans in self.security_answers):
                            self.is_sleeping = False
                            self.speak("Password accepted. System resumed.")
                        else:
                            self.speak("Incorrect password. Returning to sleep.")
                            if self.ui_label:
                                try:
                                    self.ui_label.master.withdraw()
                                except: pass
                    continue

                if text:
                    if "close the voice command" in text or "go to sleep" in text:
                        self.is_sleeping = True
                        self.speak("Voice command interface going offline.")
                        if self.ui_label:
                            try:
                                self.ui_label.master.withdraw()
                            except: pass
                        continue
                        
                    self.set_ui_status("Processing...")
                    self.set_ui_status("Processing...")
                    try:
                        # Forward directly to CNS for real intent parsing (No more fake local conversation)
                        self.speak("Processing...")
                        self.submit_callback(text)
                    except Exception as e:
                        logger.error(f"Failed to submit to CNS: {e}")
                        self.speak("I'm sorry, I encountered an error connecting to the Central Nervous System.")
                        
                    self.set_ui_status("Listening for Tasks...")
                    
# ─────────────────────────────────────────────────────────────────────────
# MANUAL INTERFACE ENTRYPOINT (STANDALONE GUI)
# ─────────────────────────────────────────────────────────────────────────

def run_manual_interface(organ: Optional["InterfaceLayerOrgan"] = None) -> None:
    """Launches a standalone input box for the user to provide dynamic tasks.

    Args:
        organ: Optional pre-wired InterfaceLayerOrgan. system_boot.py passes an
            instance whose SocketBus is bridged to the live CNS loop; when omitted
            (standalone launch), a fresh instance is created.
    """
    import tkinter as tk
    from tkinter import messagebox
    import threading

    if organ is None:
        organ = InterfaceLayerOrgan()
    organ.auth.register_user("admin", "changeme", roles=["admin"], permissions=["*"])
    session = organ.login("admin", "changeme")

    # The fake CNS stub has been removed to allow proper routing to the 36-organ CNS.

    def submit_task(prompt_text: str):
        if not prompt_text:
            return
        logger.info(f"Received manual task: {prompt_text}")
        
        # Run async dispatch in a background thread to not block UI
        def dispatch_bg():
            asyncio.run(organ.cli.handle_line(session.session_id, prompt_text, {}))
            
        threading.Thread(target=dispatch_bg, daemon=True).start()

    # Start Voice Interface in background
    voice_interface = HojaigaVoiceInterface(organ, session, submit_task)
    threading.Thread(target=voice_interface.run_loop, daemon=True).start()

    # Build simple Tkinter UI
    root = tk.Tk()
    root.title("Hojaiga - Organ 13 (Manual Task Input)")
    root.geometry("600x400")

    # Launch Floating Black Voice UI
    voice_window = tk.Toplevel(root)
    voice_window.title("Hojaiga Voice")
    voice_window.geometry("300x120+50+50")
    voice_window.configure(bg="black")
    voice_window.overrideredirect(True) # Frameless
    voice_window.attributes("-topmost", True)
    
    v_label = tk.Label(voice_window, text="Initializing...", fg="#00ff00", bg="black", font=("Consolas", 10, "bold"), wraplength=280)
    v_label.pack(expand=True, fill="both", padx=10, pady=5)
    voice_interface.ui_label = v_label

    root.geometry("600x400")
    root.configure(bg="#2E3440")
    root.attributes("-topmost", True)

    label = tk.Label(root, text="Enter dynamic task below:", bg="#2E3440", fg="#D8DEE9", font=("Helvetica", 14, "bold"))
    label.pack(pady=15)

    text_box = tk.Text(root, height=12, width=65, font=("Consolas", 12), bg="#3B4252", fg="#ECEFF4", insertbackground="white", wrap=tk.WORD)
    text_box.pack(pady=10)

    def on_submit():
        text = text_box.get("1.0", tk.END).strip()
        submit_task(text)
        text_box.delete("1.0", tk.END)
        messagebox.showinfo("Success", "Task injected securely into Organ 13.")

    submit_btn = tk.Button(root, text="Submit to CNS", command=on_submit, font=("Helvetica", 12, "bold"), bg="#88C0D0", fg="#2E3440", relief=tk.FLAT, padx=20, pady=10)
    submit_btn.pack(pady=15)

    logger.info("Starting manual input UI loop...")
    root.mainloop()


# =============================================================================
# Logic Engine: Data Visualization Graphing Engine
# =============================================================================
# Satisfies: Question 13 — Complex visual graphs (Agents vs Time, Success Ratio, etc.)
# Placement: Bottom of organ_13_interface_layer.py (append-only, no existing code modified)

class DataVisualizationGraphingEngine:
    """Consumes paradigm analytics JSON data and generates visual .png graphs
    using matplotlib (free library). Renders complex relationship plots like
    Agents vs Time, Success Ratio vs Intelligence, Paradigm Distribution, etc.
    """

    def __init__(self, output_dir: str = "./data/organ_13/graphs"):
        import os
        self._output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def plot_paradigm_success_rates(self, paradigm_report: dict, filename: str = "paradigm_success_rates.png") -> str:
        """Bar chart of success rates across all 7 paradigms."""
        try:
            import matplotlib
            matplotlib.use("Agg")  # Non-interactive backend, no GUI needed
            import matplotlib.pyplot as plt
        except ImportError:
            return "ERROR: matplotlib not installed. Run: pip install matplotlib"

        import os
        paradigms_data = paradigm_report.get("paradigms", {})
        names = list(paradigms_data.keys())
        rates = [paradigms_data[n].get("success_rate", 0) * 100 for n in names]

        fig, ax = plt.subplots(figsize=(12, 6))
        bars = ax.barh(names, rates, color=["#88C0D0", "#81A1C1", "#5E81AC",
                                             "#BF616A", "#D08770", "#EBCB8B", "#A3BE8C"])
        ax.set_xlabel("Success Rate (%)")
        ax.set_title("Paradigm Success Rates — Hojaiga Analytics")
        ax.set_xlim(0, 100)
        for bar, rate in zip(bars, rates):
            ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
                    f"{rate:.1f}%", va="center", fontsize=9)
        plt.tight_layout()
        path = os.path.join(self._output_dir, filename)
        plt.savefig(path, dpi=150)
        plt.close()
        return path

    def plot_agent_execution_timeline(self, telemetry_entries: list, filename: str = "agent_timeline.png") -> str:
        """Scatter plot of agent executions over time."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return "ERROR: matplotlib not installed. Run: pip install matplotlib"

        import os
        if not telemetry_entries:
            return "No telemetry data to plot."

        timestamps = [e["timestamp"] for e in telemetry_entries]
        durations = [e["duration_ms"] for e in telemetry_entries]
        colors = ["#A3BE8C" if e["status"] == "success" else "#BF616A" for e in telemetry_entries]

        fig, ax = plt.subplots(figsize=(14, 6))
        ax.scatter(timestamps, durations, c=colors, alpha=0.7, s=40)
        ax.set_xlabel("Timestamp (epoch)")
        ax.set_ylabel("Duration (ms)")
        ax.set_title("Agent Execution Timeline — Hojaiga Analytics")
        plt.tight_layout()
        path = os.path.join(self._output_dir, filename)
        plt.savefig(path, dpi=150)
        plt.close()
        return path

    def plot_intelligence_vs_success(self, telemetry_entries: list, filename: str = "intelligence_vs_success.png") -> str:
        """Grouped bar chart comparing success rates across intelligence levels."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return "ERROR: matplotlib not installed. Run: pip install matplotlib"

        import os
        from collections import defaultdict
        groups = defaultdict(lambda: {"success": 0, "total": 0})
        for e in telemetry_entries:
            level = e.get("intelligence_level", "standard")
            groups[level]["total"] += 1
            if e["status"] == "success":
                groups[level]["success"] += 1

        levels = list(groups.keys())
        rates = [(groups[l]["success"] / groups[l]["total"] * 100) if groups[l]["total"] > 0 else 0 for l in levels]

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(levels, rates, color="#88C0D0")
        ax.set_ylabel("Success Rate (%)")
        ax.set_title("Intelligence Level vs Success Rate — Hojaiga Analytics")
        ax.set_ylim(0, 100)
        plt.tight_layout()
        path = os.path.join(self._output_dir, filename)
        plt.savefig(path, dpi=150)
        plt.close()
        return path


if __name__ == "__main__":
    run_manual_interface()
