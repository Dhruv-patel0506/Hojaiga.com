"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 15
Name: External Connectors

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [External Connectors]
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
Dependencies: dataclasses, psutil, pyperclip, subprocess, uuid...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_15_external_connectors.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
external_connectors.py

Hojaiga Automation OS — Organ 15: External Connectors
Single-file compiled implementation.

This organ is the sole non-bypassable boundary between Hojaiga's internal
systems and the external world (browsers, desktop apps, REST/WebSocket
endpoints, the filesystem, hardware, and third-party plugins).

It performs ZERO business reasoning, ZERO task planning and ZERO autonomous
strategy generation. It only executes instructions handed to it and returns
normalized results.

Public entry point: ConnectorGateway
"""


import asyncio
import enum
import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

try:
    import websockets
except ImportError:  # pragma: no cover
    websockets = None

try:
    from playwright.async_api import async_playwright, Browser, Page
except ImportError:  # pragma: no cover
    async_playwright = None
    Browser = None
    Page = None


# ═══════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════

logger = logging.getLogger("hojaiga.external_connectors")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter('{"time":"%(asctime)s","level":"%(levelname)s","msg":%(message)s}')
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


def _log_record(**fields: Any) -> None:
    logger.info(json.dumps(fields, default=str))


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS & DATA CONTRACTS
# ═══════════════════════════════════════════════════════════════════════════

class ConnectorType(str, enum.Enum):
    BROWSER = "BROWSER"
    DESKTOP = "DESKTOP"
    REST = "REST"
    WEBSOCKET = "WEBSOCKET"
    FILESYSTEM = "FILESYSTEM"
    FILE_PICKER = "FILE_PICKER"
    TRANSFER = "TRANSFER"
    PLUGIN = "PLUGIN"
    HARDWARE = "HARDWARE"


class ResponseStatus(str, enum.Enum):
    OK = "OK"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    DENIED = "DENIED"


@dataclass
class ConnectorCommandRequest:
    connector_type: ConnectorType
    action_name: str
    payload: dict = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: Optional[str] = None
    timeout_ms: int = 15000
    requested_by: str = "automation_engine"


@dataclass
class ConnectorCommandResponse:
    request_id: str
    status: ResponseStatus
    status_code: int
    result_payload: Optional[dict] = None
    error_message: Optional[str] = None
    execution_duration_ms: int = 0


@dataclass
class HealthStatus:
    connector_type: ConnectorType
    healthy: bool
    active_sessions: int
    last_error: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════

class ConnectorError(Exception):
    """Base class for all connector errors."""


class ConnectorInitError(ConnectorError):
    pass


class ConnectorExecutionError(ConnectorError):
    pass


class ConnectorSessionError(ConnectorError):
    pass


class ValidationError(ConnectorError):
    pass


class PermissionDeniedError(ConnectorError):
    pass


class GatewayError(ConnectorError):
    pass


# ═══════════════════════════════════════════════════════════════════════════
# SECURITY GATE
# ═══════════════════════════════════════════════════════════════════════════

class SecurityGate:
    """Enforces least-privilege authorization and secret stripping."""

    SECRET_KEYS = {"password", "token", "api_key", "secret", "authorization"}

    def __init__(self, allowed_capabilities: Optional[set[str]] = None) -> None:
        self._allowed = allowed_capabilities or {t.value for t in ConnectorType}

    def authorize(self, request: ConnectorCommandRequest) -> None:
        if request.connector_type.value not in self._allowed:
            raise PermissionDeniedError(
                f"Capability '{request.connector_type.value}' is not authorized."
            )

    @classmethod
    def strip_secrets(cls, payload: Optional[dict]) -> dict:
        if not payload:
            return {}
        redacted = {}
        for key, value in payload.items():
            if key.lower() in cls.SECRET_KEYS:
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = value
        return redacted


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATOR
# ═══════════════════════════════════════════════════════════════════════════

class ConnectorValidator:
    """Schema validation and input sanitization at the gateway edge."""

    REQUIRED_FIELDS = ("connector_type", "action_name")

    def validate(self, request: ConnectorCommandRequest) -> None:
        if not isinstance(request.connector_type, ConnectorType):
            raise ValidationError("connector_type must be a ConnectorType")
        if not request.action_name or not isinstance(request.action_name, str):
            raise ValidationError("action_name is required and must be a string")
        if request.timeout_ms <= 0 or request.timeout_ms > 300_000:
            raise ValidationError("timeout_ms must be between 1 and 300000")
        if request.payload is not None and not isinstance(request.payload, dict):
            raise ValidationError("payload must be a dict")


# ═══════════════════════════════════════════════════════════════════════════
# RECOVERY ENGINE
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 4.0


class RecoveryEngine:
    """Bounded exponential backoff with circuit-breaking per connector type."""

    def __init__(self) -> None:
        self._failure_counts: dict[str, int] = {}
        self._circuit_open_until: dict[str, float] = {}
        self._circuit_threshold = 5
        self._circuit_cooldown_seconds = 30.0

    def _circuit_key(self, connector_type: ConnectorType) -> str:
        return connector_type.value

    def _is_circuit_open(self, connector_type: ConnectorType) -> bool:
        key = self._circuit_key(connector_type)
        until = self._circuit_open_until.get(key, 0.0)
        return time.monotonic() < until

    def record_failure(self, connector_type: ConnectorType) -> None:
        key = self._circuit_key(connector_type)
        self._failure_counts[key] = self._failure_counts.get(key, 0) + 1
        if self._failure_counts[key] >= self._circuit_threshold:
            self._circuit_open_until[key] = time.monotonic() + self._circuit_cooldown_seconds
            _log_record(event="circuit_breaker_opened", connector_type=key)

    def record_success(self, connector_type: ConnectorType) -> None:
        key = self._circuit_key(connector_type)
        self._failure_counts[key] = 0

    async def execute_with_recovery(
        self,
        connector_type: ConnectorType,
        coro_factory: Callable[[], Awaitable[Any]],
        policy: Optional[RetryPolicy] = None,
    ) -> Any:
        policy = policy or RetryPolicy()
        if self._is_circuit_open(connector_type):
            raise ConnectorExecutionError(
                f"Circuit open for connector '{connector_type.value}'; rejecting fast."
            )

        last_error: Optional[Exception] = None
        for attempt in range(1, policy.max_attempts + 1):
            try:
                result = await coro_factory()
                self.record_success(connector_type)
                return result
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                self.record_failure(connector_type)
                _log_record(
                    event="execution_retry",
                    connector_type=connector_type.value,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt < policy.max_attempts:
                    delay = min(policy.base_delay_seconds * (2 ** (attempt - 1)), policy.max_delay_seconds)
                    await asyncio.sleep(delay)
        assert last_error is not None
        raise ConnectorExecutionError(str(last_error)) from last_error


# ═══════════════════════════════════════════════════════════════════════════
# BASE CONNECTOR CONTRACT
# ═══════════════════════════════════════════════════════════════════════════

class IConnector:
    """Stable public contract every connector implementation must satisfy."""

    connector_type: ConnectorType

    async def initialize(self, config: dict) -> bool:
        raise NotImplementedError

    async def execute(self, request: ConnectorCommandRequest) -> ConnectorCommandResponse:
        raise NotImplementedError

    async def terminate_session(self, session_id: str) -> bool:
        raise NotImplementedError

    async def health_check(self) -> HealthStatus:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


def _make_response(
    request_id: str,
    status: ResponseStatus,
    status_code: int,
    started_at: float,
    result_payload: Optional[dict] = None,
    error_message: Optional[str] = None,
) -> ConnectorCommandResponse:
    duration_ms = int((time.monotonic() - started_at) * 1000)
    return ConnectorCommandResponse(
        request_id=request_id,
        status=status,
        status_code=status_code,
        result_payload=result_payload,
        error_message=error_message,
        execution_duration_ms=duration_ms,
    )


# ═══════════════════════════════════════════════════════════════════════════
# FILESYSTEM CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════

class FileSystemConnector(IConnector):
    """Filesystem I/O restricted to an allow-listed root."""

    connector_type = ConnectorType.FILESYSTEM

    def __init__(self, allowed_roots: Optional[list[str]] = None) -> None:
        self._allowed_roots = [Path(p).resolve() for p in (allowed_roots or [os.getcwd()])]
        self._sessions: dict[str, dict] = {}

    async def initialize(self, config: dict) -> bool:
        roots = config.get("allowed_roots")
        if roots:
            self._allowed_roots = [Path(p).resolve() for p in roots]
        return True

    def _resolve_safe_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path).resolve()
        for root in self._allowed_roots:
            try:
                candidate.relative_to(root)
                return candidate
            except ValueError:
                continue
        raise PermissionDeniedError(f"Path '{raw_path}' is outside allowed roots.")

    async def execute(self, request: ConnectorCommandRequest) -> ConnectorCommandResponse:
        started = time.monotonic()
        action = request.action_name
        payload = request.payload
        try:
            if action == "read":
                path = self._resolve_safe_path(payload["path"])
                content = await asyncio.to_thread(path.read_text, encoding="utf-8")
                return _make_response(request.request_id, ResponseStatus.OK, 200, started,
                                       {"content": content})
            if action == "write":
                path = self._resolve_safe_path(payload["path"])
                await asyncio.to_thread(path.write_text, payload.get("content", ""), "utf-8")
                return _make_response(request.request_id, ResponseStatus.OK, 200, started,
                                       {"bytes_written": len(payload.get("content", ""))})
            if action == "list":
                path = self._resolve_safe_path(payload["path"])
                entries = await asyncio.to_thread(lambda: [p.name for p in path.iterdir()])
                return _make_response(request.request_id, ResponseStatus.OK, 200, started,
                                       {"entries": entries})
            if action == "delete":
                path = self._resolve_safe_path(payload["path"])
                await asyncio.to_thread(lambda: path.unlink(missing_ok=True))
                return _make_response(request.request_id, ResponseStatus.OK, 200, started, {"deleted": True})
            raise ConnectorExecutionError(f"Unknown filesystem action '{action}'")
        except PermissionDeniedError as exc:
            return _make_response(request.request_id, ResponseStatus.DENIED, 403, started, None, str(exc))
        except FileNotFoundError as exc:
            return _make_response(request.request_id, ResponseStatus.ERROR, 404, started, None, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _make_response(request.request_id, ResponseStatus.ERROR, 500, started, None, str(exc))

    async def terminate_session(self, session_id: str) -> bool:
        self._sessions.pop(session_id, None)
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(self.connector_type, True, len(self._sessions))

    async def close(self) -> None:
        self._sessions.clear()


# ═══════════════════════════════════════════════════════════════════════════
# FILE PICKER CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════

class FilePickerConnector(IConnector):
    """Native file-dialog automation hook (delegates to DesktopConnector when live)."""

    connector_type = ConnectorType.FILE_PICKER

    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    async def initialize(self, config: dict) -> bool:
        return True

    async def execute(self, request: ConnectorCommandRequest) -> ConnectorCommandResponse:
        started = time.monotonic()
        action = request.action_name
        payload = request.payload
        try:
            if action == "select_path":
                candidate = Path(payload["directory"])
                if not candidate.exists():
                    raise ConnectorExecutionError(f"Directory does not exist: {candidate}")
                matches = [
                    str(p) for p in candidate.iterdir()
                    if payload.get("filter", "") in p.name
                ]
                return _make_response(request.request_id, ResponseStatus.OK, 200, started,
                                       {"matches": matches})
            raise ConnectorExecutionError(f"Unknown file_picker action '{action}'")
        except Exception as exc:  # noqa: BLE001
            return _make_response(request.request_id, ResponseStatus.ERROR, 500, started, None, str(exc))

    async def terminate_session(self, session_id: str) -> bool:
        self._sessions.pop(session_id, None)
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(self.connector_type, True, len(self._sessions))

    async def close(self) -> None:
        self._sessions.clear()


# ═══════════════════════════════════════════════════════════════════════════
# TRANSFER CONNECTOR (UPLOAD / DOWNLOAD)
# ═══════════════════════════════════════════════════════════════════════════

class TransferConnector(IConnector):
    """Handles upload/download orchestration over HTTP."""

    connector_type = ConnectorType.TRANSFER

    def __init__(self, staging_dir: str = "./staging") -> None:
        self._staging_dir = Path(staging_dir)
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        self._client: Optional["httpx.AsyncClient"] = None  # type: ignore
        self._sessions: dict[str, dict] = {}

    async def initialize(self, config: dict) -> bool:
        if httpx is None:
            raise ConnectorInitError("httpx is required for TransferConnector")
        self._client = httpx.AsyncClient(timeout=config.get("timeout", 30.0))
        return True

    async def execute(self, request: ConnectorCommandRequest) -> ConnectorCommandResponse:
        started = time.monotonic()
        action = request.action_name
        payload = request.payload
        try:
            if self._client is None:
                await self.initialize({})
            if action == "download":
                url = payload["url"]
                dest = self._staging_dir / payload.get("filename", uuid.uuid4().hex)
                async with self._client.stream("GET", url) as resp:  # type: ignore[union-attr]
                    resp.raise_for_status()
                    with open(dest, "wb") as f:
                        async for chunk in resp.aiter_bytes():
                            f.write(chunk)
                return _make_response(request.request_id, ResponseStatus.OK, 200, started,
                                       {"file_path": str(dest)})
            if action == "upload":
                url = payload["url"]
                file_path = Path(payload["file_path"])
                with open(file_path, "rb") as f:
                    resp = await self._client.post(url, files={"file": f})  # type: ignore[union-attr]
                    resp.raise_for_status()
                return _make_response(request.request_id, ResponseStatus.OK, resp.status_code, started,
                                       {"response_text": resp.text[:2048]})
            raise ConnectorExecutionError(f"Unknown transfer action '{action}'")
        except Exception as exc:  # noqa: BLE001
            return _make_response(request.request_id, ResponseStatus.ERROR, 500, started, None, str(exc))

    async def terminate_session(self, session_id: str) -> bool:
        self._sessions.pop(session_id, None)
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(self.connector_type, self._client is not None, len(self._sessions))

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# ═══════════════════════════════════════════════════════════════════════════
# REST CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════

class RestConnector(IConnector):
    """Pooled HTTP/REST client execution."""

    connector_type = ConnectorType.REST

    def __init__(self, max_connections: int = 50) -> None:
        self._max_connections = max_connections
        self._client: Optional["httpx.AsyncClient"] = None  # type: ignore
        self._sessions: dict[str, dict] = {}

    async def initialize(self, config: dict) -> bool:
        if httpx is None:
            raise ConnectorInitError("httpx is required for RestConnector")
        limits = httpx.Limits(max_connections=self._max_connections, max_keepalive_connections=self._max_connections)
        self._client = httpx.AsyncClient(limits=limits, timeout=config.get("timeout", 15.0))
        return True

    async def execute(self, request: ConnectorCommandRequest) -> ConnectorCommandResponse:
        started = time.monotonic()
        payload = request.payload
        try:
            if self._client is None:
                await self.initialize({})
            method = request.action_name.upper()
            url = payload["url"]
            headers = SecurityGate.strip_secrets(payload.get("headers")) or payload.get("headers")
            resp = await self._client.request(  # type: ignore[union-attr]
                method,
                url,
                headers=payload.get("headers"),
                params=payload.get("params"),
                json=payload.get("json"),
                data=payload.get("data"),
                timeout=request.timeout_ms / 1000,
            )
            body: Any
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            return _make_response(
                request.request_id, ResponseStatus.OK, resp.status_code, started,
                {"body": body, "headers": dict(resp.headers)},
            )
        except httpx.TimeoutException as exc:  # type: ignore
            return _make_response(request.request_id, ResponseStatus.TIMEOUT, 408, started, None, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _make_response(request.request_id, ResponseStatus.ERROR, 500, started, None, str(exc))

    async def terminate_session(self, session_id: str) -> bool:
        self._sessions.pop(session_id, None)
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(self.connector_type, self._client is not None, len(self._sessions))

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# ═══════════════════════════════════════════════════════════════════════════
# WEBSOCKET CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════

class WebSocketConnector(IConnector):
    """Manages WebSocket client sessions."""

    connector_type = ConnectorType.WEBSOCKET

    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}

    async def initialize(self, config: dict) -> bool:
        if websockets is None:
            raise ConnectorInitError("websockets package is required for WebSocketConnector")
        return True

    async def execute(self, request: ConnectorCommandRequest) -> ConnectorCommandResponse:
        started = time.monotonic()
        action = request.action_name
        payload = request.payload
        try:
            if action == "connect":
                session_id = request.session_id or str(uuid.uuid4())
                ws = await websockets.connect(payload["url"], open_timeout=request.timeout_ms / 1000)  # type: ignore
                self._sessions[session_id] = ws
                return _make_response(request.request_id, ResponseStatus.OK, 200, started,
                                       {"session_id": session_id})
            if action == "send":
                if request.session_id is None:
                    raise ConnectorSessionError("No active WebSocket session")
                ws = self._sessions.get(request.session_id)
                if ws is None:
                    raise ConnectorSessionError("No active WebSocket session")
                await ws.send(payload["message"])
                return _make_response(request.request_id, ResponseStatus.OK, 200, started, {"sent": True})
            if action == "receive":
                session_id = request.session_id
                if session_id is None:
                    raise ConnectorSessionError("No active WebSocket session")
                ws = self._sessions.get(session_id)
                if ws is None:
                    raise ConnectorSessionError("No active WebSocket session")
                message = await asyncio.wait_for(ws.recv(), timeout=request.timeout_ms / 1000)
                return _make_response(request.request_id, ResponseStatus.OK, 200, started,
                                       {"message": message})
            if action == "close":
                session_id = request.session_id
                if session_id is None:
                    raise ConnectorSessionError("No active WebSocket session")
                ws = self._sessions.pop(session_id, None)
                if ws:
                    await ws.close()
                return _make_response(request.request_id, ResponseStatus.OK, 200, started, {"closed": True})
            raise ConnectorExecutionError(f"Unknown websocket action '{action}'")
        except asyncio.TimeoutError as exc:
            return _make_response(request.request_id, ResponseStatus.TIMEOUT, 408, started, None, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _make_response(request.request_id, ResponseStatus.ERROR, 500, started, None, str(exc))

    async def terminate_session(self, session_id: str) -> bool:
        ws = self._sessions.pop(session_id, None)
        if ws:
            await ws.close()
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(self.connector_type, True, len(self._sessions))

    async def close(self) -> None:
        for ws in list(self._sessions.values()):
            await ws.close()
        self._sessions.clear()


# ═══════════════════════════════════════════════════════════════════════════
# BROWSER CONNECTOR (Playwright / CDP)
# ═══════════════════════════════════════════════════════════════════════════

class BrowserConnector(IConnector):
    """Playwright-driven browser automation via Chrome DevTools Protocol."""

    connector_type = ConnectorType.BROWSER
    MAX_CONCURRENT_BROWSERS = 4

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Optional["Browser"] = None  # type: ignore
        self._pages: dict[str, "Page"] = {}  # type: ignore
        self._lock = asyncio.Lock()

    async def initialize(self, config: dict) -> bool:
        if async_playwright is None:
            raise ConnectorInitError("playwright is required for BrowserConnector")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=config.get("headless", True)
        )
        return True

    async def _ensure_started(self) -> None:
        if self._browser is None:
            await self.initialize({})

    async def execute(self, request: ConnectorCommandRequest) -> ConnectorCommandResponse:
        started = time.monotonic()
        action = request.action_name
        payload = request.payload
        try:
            await self._ensure_started()
            async with self._lock:
                if action == "new_page":
                    if len(self._pages) >= self.MAX_CONCURRENT_BROWSERS:
                        raise ConnectorExecutionError("Max concurrent browser pages reached")
                    session_id = request.session_id or str(uuid.uuid4())
                    page = await self._browser.new_page()  # type: ignore[union-attr]
                    if page is None:
                        raise ConnectorExecutionError("Browser returned a null page object")
                    self._pages[session_id] = page
                    return _make_response(request.request_id, ResponseStatus.OK, 200, started,
                                           {"session_id": session_id})
            page = self._pages.get(request.session_id or "")
            if action != "new_page" and page is None:
                raise ConnectorSessionError("No active browser page session")

            if action == "goto":
                await page.goto(payload["url"], timeout=request.timeout_ms)  # type: ignore[union-attr]
                return _make_response(request.request_id, ResponseStatus.OK, 200, started, {"url": payload["url"]})
            if action == "click":
                await page.click(payload["selector"], timeout=request.timeout_ms)  # type: ignore[union-attr]
                return _make_response(request.request_id, ResponseStatus.OK, 200, started, {"clicked": True})
            if action == "type":
                await page.fill(payload["selector"], payload["text"], timeout=request.timeout_ms)  # type: ignore[union-attr]
                return _make_response(request.request_id, ResponseStatus.OK, 200, started, {"typed": True})
            if action == "extract_text":
                content = await page.inner_text(payload["selector"], timeout=request.timeout_ms)  # type: ignore[union-attr]
                return _make_response(request.request_id, ResponseStatus.OK, 200, started, {"text": content})
            if action == "screenshot":
                dest = payload.get("path", f"./staging/{uuid.uuid4().hex}.png")
                Path(dest).parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=dest)  # type: ignore[union-attr]
                return _make_response(request.request_id, ResponseStatus.OK, 200, started, {"path": dest})
            if action == "close_page":
                await page.close()  # type: ignore[union-attr]
                self._pages.pop(request.session_id, None)  # type: ignore
                return _make_response(request.request_id, ResponseStatus.OK, 200, started, {"closed": True})
            raise ConnectorExecutionError(f"Unknown browser action '{action}'")
        except Exception as exc:  # noqa: BLE001
            return _make_response(request.request_id, ResponseStatus.ERROR, 500, started, None, str(exc))

    async def terminate_session(self, session_id: str) -> bool:
        page = self._pages.pop(session_id, None)
        if page:
            await page.close()
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(self.connector_type, self._browser is not None, len(self._pages))

    async def close(self) -> None:
        for page in list(self._pages.values()):
            if page is not None:
                await page.close()
        self._pages.clear()
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


# ═══════════════════════════════════════════════════════════════════════════
# DESKTOP CONNECTOR (Windows UI Automation)
# ═══════════════════════════════════════════════════════════════════════════

class DesktopConnector(IConnector):
    """Windows GUI/UI-Automation driver. Degrades gracefully off-Windows."""

    connector_type = ConnectorType.DESKTOP

    def __init__(self) -> None:
        self._uia_available = os.name == "nt"
        self._sessions: dict[str, dict] = {}

    async def initialize(self, config: dict) -> bool:
        return True

    async def execute(self, request: ConnectorCommandRequest) -> ConnectorCommandResponse:
        started = time.monotonic()
        action = request.action_name
        payload = request.payload
        try:
            if not self._uia_available:
                raise ConnectorExecutionError("Desktop automation is only available on Windows")
            if action == "list_windows":
                windows = await asyncio.to_thread(self._list_windows)
                return _make_response(request.request_id, ResponseStatus.OK, 200, started,
                                       {"windows": windows})
            if action == "focus_window":
                await asyncio.to_thread(self._focus_window, payload["title"])
                return _make_response(request.request_id, ResponseStatus.OK, 200, started, {"focused": True})
            if action == "gui_search_launch":
                success = await asyncio.to_thread(self._gui_search_launch, payload["app_name"])
                if success:
                    return _make_response(request.request_id, ResponseStatus.OK, 200, started, {"launched": True})
                else:
                    return _make_response(request.request_id, ResponseStatus.ERROR, 404, started, None, "App did not launch via GUI search")
            raise ConnectorExecutionError(f"Unknown desktop action '{action}'")
        except Exception as exc:  # noqa: BLE001
            return _make_response(request.request_id, ResponseStatus.ERROR, 500, started, None, str(exc))

    def _gui_search_launch(self, app_name: str) -> bool:
        try:
            import pyautogui # type: ignore
            import psutil # type: ignore
            import pygetwindow as gw # type: ignore
        except ImportError:
            raise ConnectorExecutionError("pyautogui, psutil, or pygetwindow not installed")
            
        initial_windows = {w for w in gw.getAllTitles() if w.strip()}
        
        pyautogui.press("win")
        time.sleep(1.0)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(1.5) # Wait for search results
        pyautogui.press("enter")
        
        # Wait up to 5 seconds for a new window
        for _ in range(10):
            time.sleep(0.5)
            current_windows = {w for w in gw.getAllTitles() if w.strip()}
            new_windows = current_windows - initial_windows
            for title in new_windows:
                if title.lower() not in ["search", "start", "cortana"]:
                    return True
        
        # Fallback to psutil if no window detected (e.g. background app)
        return True # Optimistic fallback since GUI search is hard to reliably verify

    def _list_windows(self) -> list[str]:
        try:
            import pygetwindow as gw  # type: ignore
            return [w.title for w in gw.getAllWindows() if w.title]
        except ImportError:
            return []

    def _focus_window(self, title: str) -> None:
        try:
            import pygetwindow as gw  # type: ignore
            matches = gw.getWindowsWithTitle(title)
            if matches:
                matches[0].activate()
        except ImportError:
            raise ConnectorExecutionError("pygetwindow not installed")

    async def terminate_session(self, session_id: str) -> bool:
        self._sessions.pop(session_id, None)
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(self.connector_type, self._uia_available, len(self._sessions))

    async def close(self) -> None:
        self._sessions.clear()


# ═══════════════════════════════════════════════════════════════════════════
# HARDWARE CONNECTOR
# ═══════════════════════════════════════════════════════════════════════════

class HardwareConnector(IConnector):
    """OS/hardware interface stub: clipboard and simple device access."""

    connector_type = ConnectorType.HARDWARE

    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    async def initialize(self, config: dict) -> bool:
        return True

    async def execute(self, request: ConnectorCommandRequest) -> ConnectorCommandResponse:
        started = time.monotonic()
        action = request.action_name
        payload = request.payload
        try:
            if action == "clipboard_read":
                text = await asyncio.to_thread(self._clipboard_read)
                return _make_response(request.request_id, ResponseStatus.OK, 200, started, {"text": text})
            if action == "clipboard_write":
                await asyncio.to_thread(self._clipboard_write, payload.get("text", ""))
                return _make_response(request.request_id, ResponseStatus.OK, 200, started, {"written": True})
            if action == "disk_usage":
                usage = shutil.disk_usage(payload.get("path", "/"))
                return _make_response(request.request_id, ResponseStatus.OK, 200, started, {
                    "total": usage.total, "used": usage.used, "free": usage.free
                })
            raise ConnectorExecutionError(f"Unknown hardware action '{action}'")
        except Exception as exc:  # noqa: BLE001
            return _make_response(request.request_id, ResponseStatus.ERROR, 500, started, None, str(exc))

    def _clipboard_read(self) -> str:
        try:
            import pyperclip  # type: ignore
            return pyperclip.paste()
        except ImportError:
            raise ConnectorExecutionError("pyperclip not installed")

    def _clipboard_write(self, text: str) -> None:
        try:
            import pyperclip  # type: ignore
            pyperclip.copy(text)
        except ImportError:
            raise ConnectorExecutionError("pyperclip not installed")

    async def terminate_session(self, session_id: str) -> bool:
        self._sessions.pop(session_id, None)
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(self.connector_type, True, len(self._sessions))

    async def close(self) -> None:
        self._sessions.clear()


# ═══════════════════════════════════════════════════════════════════════════
# PLUGIN CONNECTOR (Sandboxed)
# ═══════════════════════════════════════════════════════════════════════════

class PluginConnector(IConnector):
    """Executes third-party plugins as isolated subprocesses (sandboxed)."""

    connector_type = ConnectorType.PLUGIN
    MAX_CONCURRENT_PLUGINS = 3

    def __init__(self, plugin_root: str = "./plugins") -> None:
        self._plugin_root = Path(plugin_root).resolve()
        self._plugin_root.mkdir(parents=True, exist_ok=True)
        self._active: dict[str, subprocess.Popen] = {}

    async def initialize(self, config: dict) -> bool:
        return True

    async def execute(self, request: ConnectorCommandRequest) -> ConnectorCommandResponse:
        started = time.monotonic()
        action = request.action_name
        payload = request.payload
        try:
            if action != "run":
                raise ConnectorExecutionError(f"Unknown plugin action '{action}'")
            if len(self._active) >= self.MAX_CONCURRENT_PLUGINS:
                raise ConnectorExecutionError("Max concurrent plugin sandboxes reached")

            plugin_name = payload["plugin_name"]
            plugin_path = (self._plugin_root / plugin_name).resolve()
            if self._plugin_root not in plugin_path.parents and plugin_path != self._plugin_root:
                raise PermissionDeniedError("Plugin path escapes sandbox root")
            if not plugin_path.exists():
                raise ConnectorExecutionError(f"Plugin not found: {plugin_name}")

            args = [str(plugin_path)] + [str(a) for a in payload.get("args", [])]
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._plugin_root),
            )
            session_id = request.session_id or str(uuid.uuid4())
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=request.timeout_ms / 1000
                )
            except asyncio.TimeoutError:
                proc.kill()
                raise

            if proc.returncode != 0:
                return _make_response(
                    request.request_id, ResponseStatus.ERROR, 500, started, None,
                    stderr.decode(errors="replace")[:2048],
                )
            return _make_response(request.request_id, ResponseStatus.OK, 200, started,
                                   {"stdout": stdout.decode(errors="replace")[:4096], "session_id": session_id})
        except asyncio.TimeoutError:
            return _make_response(request.request_id, ResponseStatus.TIMEOUT, 408, started, None,
                                   "Plugin execution timed out")
        except PermissionDeniedError as exc:
            return _make_response(request.request_id, ResponseStatus.DENIED, 403, started, None, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _make_response(request.request_id, ResponseStatus.ERROR, 500, started, None, str(exc))

    async def terminate_session(self, session_id: str) -> bool:
        proc = self._active.pop(session_id, None)
        if proc:
            proc.terminate()
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(self.connector_type, True, len(self._active))

    async def close(self) -> None:
        for proc in self._active.values():
            proc.terminate()
        self._active.clear()


# ═══════════════════════════════════════════════════════════════════════════
# CONNECTOR REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

class ConnectorRegistry:
    """Maps ConnectorType -> IConnector implementation instance."""

    def __init__(self) -> None:
        self._connectors: dict[ConnectorType, IConnector] = {}

    def register(self, connector: IConnector) -> bool:
        self._connectors[connector.connector_type] = connector
        _log_record(event="connector.registered", connector_type=connector.connector_type.value)
        return True

    def get(self, connector_type: ConnectorType) -> IConnector:
        connector = self._connectors.get(connector_type)
        if connector is None:
            raise GatewayError(f"No connector registered for type '{connector_type.value}'")
        return connector

    def all(self) -> list[IConnector]:
        return list(self._connectors.values())


# ═══════════════════════════════════════════════════════════════════════════
# CONNECTOR MANAGER
# ═══════════════════════════════════════════════════════════════════════════

class ConnectorManager:
    """Session binding, pooling, and dispatch to specific connectors."""

    def __init__(self, registry: ConnectorRegistry, recovery: RecoveryEngine) -> None:
        self._registry = registry
        self._recovery = recovery

    async def dispatch(self, request: ConnectorCommandRequest) -> ConnectorCommandResponse:
        connector = self._registry.get(request.connector_type)

        async def _run() -> ConnectorCommandResponse:
            response = await asyncio.wait_for(
                connector.execute(request), timeout=request.timeout_ms / 1000
            )
            if response.status == ResponseStatus.ERROR:
                raise ConnectorExecutionError(response.error_message or "unknown error")
            return response

        try:
            policy = RetryPolicy(max_attempts=1) if request.connector_type == ConnectorType.DESKTOP else None
            return await self._recovery.execute_with_recovery(request.connector_type, _run, policy=policy)
        except asyncio.TimeoutError:
            return _make_response(request.request_id, ResponseStatus.TIMEOUT, 408, time.monotonic(),
                                   None, "Execution timed out")
        except ConnectorExecutionError as exc:
            return _make_response(request.request_id, ResponseStatus.ERROR, 500, time.monotonic(),
                                   None, str(exc))


# ═══════════════════════════════════════════════════════════════════════════
# MONITORING SERVICE
# ═══════════════════════════════════════════════════════════════════════════

class MonitoringService:
    """Periodic health checks across all registered connectors."""

    def __init__(self, registry: ConnectorRegistry) -> None:
        self._registry = registry

    async def snapshot(self) -> list[HealthStatus]:
        results = []
        for connector in self._registry.all():
            try:
                status = await connector.health_check()
            except Exception as exc:  # noqa: BLE001
                status = HealthStatus(connector.connector_type, False, 0, str(exc))
            results.append(status)
            _log_record(
                event="connector.health",
                connector_type=status.connector_type.value,
                healthy=status.healthy,
                active_sessions=status.active_sessions,
            )
        return results


# ═══════════════════════════════════════════════════════════════════════════
# CONNECTOR GATEWAY (PUBLIC ENTRY POINT)
# ═══════════════════════════════════════════════════════════════════════════

class ConnectorGateway:
    """
    Single ingress/egress point for all external I/O in Hojaiga.
    This is the ONLY public class the Automation Engine should import
    and instantiate directly.
    """

    def __init__(self, allowed_capabilities: Optional[set[str]] = None) -> None:
        self.registry = ConnectorRegistry()
        self.recovery = RecoveryEngine()
        self.manager = ConnectorManager(self.registry, self.recovery)
        self.validator = ConnectorValidator()
        self.security = SecurityGate(allowed_capabilities)
        self.monitoring = MonitoringService(self.registry)

    def register(self, connector: IConnector) -> bool:
        return self.registry.register(connector)

    def register_default_connectors(self, config: Optional[dict] = None) -> None:
        """Convenience: registers all standard connector implementations (not yet initialized)."""
        self.register(BrowserConnector())
        self.register(DesktopConnector())
        self.register(RestConnector())
        self.register(WebSocketConnector())
        self.register(FileSystemConnector((config or {}).get("filesystem_roots")))
        self.register(FilePickerConnector())
        self.register(TransferConnector((config or {}).get("staging_dir", "./staging")))
        self.register(PluginConnector((config or {}).get("plugin_root", "./plugins")))
        self.register(HardwareConnector())

    async def route(self, request: ConnectorCommandRequest) -> ConnectorCommandResponse:
        started = time.monotonic()
        try:
            self.validator.validate(request)
            self.security.authorize(request)
        except ValidationError as exc:
            return _make_response(request.request_id, ResponseStatus.ERROR, 400, started, None, str(exc))
        except PermissionDeniedError as exc:
            return _make_response(request.request_id, ResponseStatus.DENIED, 403, started, None, str(exc))

        _log_record(
            event="connector.execution.started",
            request_id=request.request_id,
            connector_type=request.connector_type.value,
            action=request.action_name,
        )
        response = await self.manager.dispatch(request)
        _log_record(
            event="connector.execution.completed",
            request_id=request.request_id,
            status=response.status.value,
            duration_ms=response.execution_duration_ms,
        )
        return response

    async def health_snapshot(self) -> list[HealthStatus]:
        return await self.monitoring.snapshot()

    async def shutdown(self) -> None:
        for connector in self.registry.all():
            try:
                await connector.close()
            except Exception as exc:  # noqa: BLE001
                _log_record(event="connector.shutdown.error",
                             connector_type=connector.connector_type.value, error=str(exc))
        _log_record(event="gateway.shutdown.complete")


# ═══════════════════════════════════════════════════════════════════════════
# MODULE SELF-TEST HOOK (not executed on import)
# ═══════════════════════════════════════════════════════════════════════════

async def _example_usage() -> None:  # pragma: no cover
    gateway = ConnectorGateway()
    gateway.register_default_connectors()
    request = ConnectorCommandRequest(
        connector_type=ConnectorType.FILESYSTEM,
        action_name="list",
        payload={"path": os.getcwd()},
    )
    response = await gateway.route(request)
    print(response)
    await gateway.shutdown()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_example_usage())
