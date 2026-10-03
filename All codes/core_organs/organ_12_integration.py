"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 12
Name: Integration

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Integration]
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
Dependencies: dataclasses, enum, pathlib, __future__, typing...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_12_integration.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
organ_12_integration.py
Hojaiga Automation OS — Organ 12: Integration Organ (Reference Implementation v1.0.0)

Single-file, production-grade implementation of the Integration Specification.
Import surface:
    from core_organs.organ_12_integration import IntegrationOrgan

All cross-organ contact happens exclusively through IntegrationOrgan's public
async methods (mirroring the IPC RPC surface) or through the live IPC/webhook
sockets started by `IntegrationOrgan.start()`. Internal classes are private
to this organ per Master Architecture Blueprint Chapter 10 (Plugin/Organ
Independence) and Universal Law 3 (Separation of Responsibility).
"""


import asyncio
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import struct
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, cast

try:
    from aiohttp import web
except ImportError:  # pragma: no cover - dependency documented in manifest
    web = None  # type: ignore

try:
    import jsonschema
except ImportError:  # pragma: no cover - dependency documented in manifest
    jsonschema = None  # type: ignore


# ══════════════════════════════════════════════════════════════════════════
# LOGGING (Policy Manual Chapter 8 — structured, append-only JSON logging)
# ══════════════════════════════════════════════════════════════════════════

logger = logging.getLogger("hojaiga.organ_12.integration")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


def _audit(event: str, **fields: Any) -> None:
    record = {
        "timestamp": time.time(),
        "organ": "organ_12_integration",
        "event": event,
        **fields,
    }
    logger.info(json.dumps(record, default=str))


# ══════════════════════════════════════════════════════════════════════════
# DATA CONTRACTS (Section 15 — JSON-Schema draft-07)
# ══════════════════════════════════════════════════════════════════════════

INTEGRATION_ACTION_REQUEST_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "IntegrationActionRequest",
    "type": "object",
    "properties": {
        "request_id": {"type": "string"},
        "adapter_id": {"type": "string"},
        "endpoint_action": {"type": "string"},
        "payload_parameters": {"type": "object"},
        "timeout_ms": {"type": "integer", "default": 15000},
    },
    "required": ["request_id", "adapter_id", "endpoint_action", "payload_parameters"],
}

INTEGRATION_ACTION_RESPONSE_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "IntegrationActionResponse",
    "type": "object",
    "properties": {
        "request_id": {"type": "string"},
        "status": {"type": "string", "enum": ["SUCCESS", "FAILED", "CIRCUIT_OPEN", "TIMED_OUT"]},
        "response_data": {"type": "object"},
        "http_status_code": {"type": "integer"},
        "error_message": {"type": "string"},
    },
    "required": ["request_id", "status"],
}


def _validate(payload: dict, schema: dict) -> None:
    if jsonschema is not None:
        jsonschema.validate(payload, schema)
    else:
        for field_name in schema.get("required", []):
            if field_name not in payload:
                raise ValueError(f"Missing required field: {field_name}")


# ══════════════════════════════════════════════════════════════════════════
# CIRCUIT BREAKER (resilience/circuit_breaker.py equivalent)
# ══════════════════════════════════════════════════════════════════════════

class CircuitState(str, Enum):
    DISABLED = "DISABLED"
    ACTIVE = "ACTIVE"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class AdapterFaultRecord:
    adapter_id: str
    state: CircuitState = CircuitState.ACTIVE
    fault_count: int = 0
    success_count: int = 0
    last_success: Optional[float] = None
    last_failure: Optional[float] = None
    opened_at: Optional[float] = None


class ICircuitBreaker:
    def record_success(self, service_id: str) -> None:
        raise NotImplementedError

    def record_failure(self, service_id: str) -> None:
        raise NotImplementedError


class CircuitBreakerRegistry(ICircuitBreaker):
    """Tracks per-adapter fault ratios; trips to CIRCUIT_OPEN at >50% error rate."""

    FAILURE_THRESHOLD_RATIO = 0.5
    MIN_SAMPLES_BEFORE_TRIP = 5
    COOL_OFF_SECONDS = 30

    def __init__(self, on_trip: Optional[Callable[[str], None]] = None) -> None:
        self._records: dict[str, AdapterFaultRecord] = {}
        self._lock = asyncio.Lock()
        self._on_trip = on_trip

    def _get(self, service_id: str) -> AdapterFaultRecord:
        return self._records.setdefault(service_id, AdapterFaultRecord(adapter_id=service_id))

    def record_success(self, service_id: str) -> None:
        rec = self._get(service_id)
        rec.success_count += 1
        rec.last_success = time.time()
        if rec.state == CircuitState.HALF_OPEN:
            rec.state = CircuitState.ACTIVE
            rec.fault_count = 0
            rec.opened_at = None
            _audit("circuit_recovered", adapter_id=service_id)

    def record_failure(self, service_id: str) -> None:
        rec = self._get(service_id)
        rec.fault_count += 1
        rec.last_failure = time.time()
        total = rec.fault_count + rec.success_count
        if rec.state == CircuitState.HALF_OPEN:
            rec.state = CircuitState.CIRCUIT_OPEN
            rec.opened_at = time.time()
            _audit("circuit_reopened", adapter_id=service_id)
            return
        if total >= self.MIN_SAMPLES_BEFORE_TRIP:
            ratio = rec.fault_count / total
            if ratio > self.FAILURE_THRESHOLD_RATIO and rec.state == CircuitState.ACTIVE:
                rec.state = CircuitState.CIRCUIT_OPEN
                rec.opened_at = time.time()
                _audit("circuit_tripped", adapter_id=service_id, fault_ratio=ratio)
                if self._on_trip:
                    self._on_trip(service_id)

    def check(self, service_id: str) -> CircuitState:
        rec = self._get(service_id)
        if rec.state == CircuitState.CIRCUIT_OPEN and rec.opened_at:
            if time.time() - rec.opened_at >= self.COOL_OFF_SECONDS:
                rec.state = CircuitState.HALF_OPEN
                _audit("circuit_half_open", adapter_id=service_id)
        return rec.state

    def snapshot(self, service_id: str) -> dict:
        rec = self._get(service_id)
        return {
            "adapter_id": rec.adapter_id,
            "state": rec.state.value,
            "fault_count": rec.fault_count,
            "success_count": rec.success_count,
            "last_success": rec.last_success,
            "last_failure": rec.last_failure,
        }


# ══════════════════════════════════════════════════════════════════════════
# RATE LIMITER (token bucket, Section 4 — Rate Limiting & Circuit Breaking)
# ══════════════════════════════════════════════════════════════════════════

class TokenBucketRateLimiter:
    def __init__(self, capacity: int = 20, refill_per_sec: float = 5.0) -> None:
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_per_sec = refill_per_sec
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


# ══════════════════════════════════════════════════════════════════════════
# STATE DATABASE (Section 16 — in-memory SQLite)
# ══════════════════════════════════════════════════════════════════════════

class IntegrationStateStore:
    def __init__(self) -> None:
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._lock = asyncio.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """CREATE TABLE adapter_status (
                adapter_id TEXT PRIMARY KEY,
                status TEXT,
                fault_count INTEGER,
                last_success TIMESTAMP,
                last_failure TIMESTAMP
            )"""
        )
        cur.execute(
            """CREATE TABLE webhook_subscriptions (
                endpoint_id TEXT PRIMARY KEY,
                path TEXT,
                hmac_secret_hash TEXT,
                active INTEGER
            )"""
        )
        self._conn.commit()

    async def upsert_adapter_status(self, adapter_id: str, status: str, fault_count: int,
                                     last_success: Optional[float], last_failure: Optional[float]) -> None:
        async with self._lock:
            self._conn.execute(
                """INSERT INTO adapter_status (adapter_id, status, fault_count, last_success, last_failure)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(adapter_id) DO UPDATE SET
                     status=excluded.status, fault_count=excluded.fault_count,
                     last_success=excluded.last_success, last_failure=excluded.last_failure""",
                (adapter_id, status, fault_count, last_success, last_failure),
            )
            self._conn.commit()

    async def register_webhook(self, endpoint_id: str, path: str, secret_hash: str) -> None:
        async with self._lock:
            self._conn.execute(
                """INSERT INTO webhook_subscriptions (endpoint_id, path, hmac_secret_hash, active)
                   VALUES (?, ?, ?, 1)
                   ON CONFLICT(endpoint_id) DO UPDATE SET
                     path=excluded.path, hmac_secret_hash=excluded.hmac_secret_hash, active=1""",
                (endpoint_id, path, secret_hash),
            )
            self._conn.commit()

    async def get_webhook_secret_hash(self, endpoint_id: str) -> Optional[str]:
        async with self._lock:
            cur = self._conn.execute(
                "SELECT hmac_secret_hash FROM webhook_subscriptions WHERE endpoint_id=? AND active=1",
                (endpoint_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None


# ══════════════════════════════════════════════════════════════════════════
# PROTOCOL BRIDGE (bridges/protocol_bridge.py equivalent)
# ══════════════════════════════════════════════════════════════════════════

class ProtocolBridge:
    """Maps raw external API JSON/XML payloads to/from internal CNS envelopes."""

    @staticmethod
    def to_internal(adapter_id: str, raw_payload: dict) -> dict:
        return {
            "source_adapter": adapter_id,
            "normalized_at": time.time(),
            "data": raw_payload,
        }

    @staticmethod
    def to_external(cns_payload: dict) -> dict:
        return dict(cns_payload.get("data", cns_payload))


# ══════════════════════════════════════════════════════════════════════════
# ADAPTERS (adapters/base_adapter.py + registry)
# ══════════════════════════════════════════════════════════════════════════

class IBaseAdapter:
    adapter_id: str = "base"
    allowed_domains: tuple[str, ...] = ()

    def __init__(self, config: dict) -> None:
        self.config = config

    async def initialize(self, adapter_config: dict) -> None:
        self.config = adapter_config

    def transform_to_internal(self, raw_payload: dict) -> dict:
        return ProtocolBridge.to_internal(self.adapter_id, raw_payload)

    def transform_to_external(self, cns_payload: dict) -> dict:
        return ProtocolBridge.to_external(cns_payload)

    async def execute(self, endpoint_action: str, payload_parameters: dict,
                       gateway_call: Callable[[str, str, dict], Awaitable[dict]]) -> dict:
        """gateway_call(method, url, body) -> Infrastructure Organ outbound proxy."""
        raise NotImplementedError


class GenericRestAdapter(IBaseAdapter):
    """Reference REST adapter driving arbitrary whitelisted JSON endpoints."""

    adapter_id = "generic_rest"

    async def execute(self, endpoint_action: str, payload_parameters: dict,
                       gateway_call: Callable[[str, str, dict], Awaitable[dict]]) -> dict:
        base_url = self.config.get("base_url", "")
        url = f"{base_url.rstrip('/')}/{endpoint_action.lstrip('/')}"
        method = payload_parameters.pop("_method", "POST")
        response = await gateway_call(method, url, payload_parameters)
        return self.transform_to_internal(response)


class AdapterRegistry:
    def __init__(self, manifest: dict) -> None:
        self._manifest = manifest
        self._adapters: dict[str, IBaseAdapter] = {}
        self._factories: dict[str, type[IBaseAdapter]] = {
            "generic_rest": GenericRestAdapter,
        }

    def register_factory(self, adapter_id: str, factory: type[IBaseAdapter]) -> None:
        self._factories[adapter_id] = factory

    async def load(self) -> None:
        for entry in self._manifest.get("adapters", []):
            adapter_id = entry["adapter_id"]
            factory = self._factories.get(entry.get("type", "generic_rest"), GenericRestAdapter)
            adapter = factory(entry)
            await adapter.initialize(entry)
            self._adapters[adapter_id] = adapter
        _audit("adapters_loaded", count=len(self._adapters))

    def get(self, adapter_id: str) -> Optional[IBaseAdapter]:
        return self._adapters.get(adapter_id)

    def is_whitelisted(self, adapter_id: str) -> bool:
        return adapter_id in self._adapters


# ══════════════════════════════════════════════════════════════════════════
# OAUTH MANAGER (services/oauth_manager.py equivalent)
# ══════════════════════════════════════════════════════════════════════════

class OAuthManager:
    def __init__(self, security_organ_client: Callable[[str], Awaitable[dict]],
                 event_emitter: Callable[[str, dict], Awaitable[None]]) -> None:
        self._get_secret = security_organ_client
        self._emit = event_emitter
        self._token_cache: dict[str, dict] = {}
        self._refresh_task: Optional[asyncio.Task] = None

    async def refresh_token(self, adapter_id: str) -> dict:
        secret = await self._get_secret(adapter_id)
        token_record = {
            "access_token": secret.get("access_token", ""),
            "expires_at": time.time() + secret.get("expires_in", 3600),
        }
        self._token_cache[adapter_id] = token_record
        await self._emit("EVENT_OAUTH_TOKEN_REFRESHED", {"adapter_id": adapter_id})
        _audit("oauth_token_refreshed", adapter_id=adapter_id)
        return token_record

    async def get_valid_token(self, adapter_id: str) -> Optional[str]:
        record = self._token_cache.get(adapter_id)
        if record is None or record["expires_at"] - time.time() < 30:
            record = await self.refresh_token(adapter_id)
        return record["access_token"]

    async def start_background_refresh(self, adapter_ids: list[str], interval_sec: int = 300) -> None:
        async def _loop() -> None:
            while True:
                for adapter_id in adapter_ids:
                    try:
                        await self.get_valid_token(adapter_id)
                    except Exception as exc:  # noqa: BLE001
                        _audit("oauth_refresh_error", adapter_id=adapter_id, error=str(exc))
                await asyncio.sleep(interval_sec)

        self._refresh_task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        if self._refresh_task:
            self._refresh_task.cancel()


# ══════════════════════════════════════════════════════════════════════════
# PERIPHERAL BRIDGE (bridges/peripheral_bridge.py equivalent)
# ══════════════════════════════════════════════════════════════════════════

class PeripheralBridge:
    """CPU-based serial/USB/network hardware event bridge (stub I/O channel)."""

    def __init__(self) -> None:
        self._channels: dict[str, Any] = {}

    async def trigger(self, channel_id: str, command: dict) -> dict:
        _audit("peripheral_command", channel_id=channel_id, command=command)
        return {"channel_id": channel_id, "status": "SUCCESS", "echo": command}


# ══════════════════════════════════════════════════════════════════════════
# WEBHOOK LISTENER (services/webhook_listener.py equivalent)
# ══════════════════════════════════════════════════════════════════════════

class WebhookListener:
    def __init__(self, state_store: IntegrationStateStore,
                 event_emitter: Callable[[str, dict], Awaitable[None]],
                 host: str = "127.0.0.1", port: int = 8712) -> None:
        self._state = state_store
        self._emit = event_emitter
        self.host = host
        self.port = port
        self._runner: Optional["web.AppRunner"] = None  # type: ignore

    @staticmethod
    def _verify_hmac(secret: str, body: bytes, signature: str) -> bool:
        computed = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, signature)

    async def _handle(self, request: "web.Request") -> "web.Response":  # type: ignore
        endpoint_id = request.match_info.get("endpoint_id", "default")
        secret_hash = await self._state.get_webhook_secret_hash(endpoint_id)
        body = await request.read()
        signature = request.headers.get("X-Hojaiga-Signature", "")

        if not secret_hash or not self._verify_hmac(secret_hash, body, signature):
            _audit("webhook_rejected", endpoint_id=endpoint_id)
            return web.Response(status=401, text="Unauthorized")  # type: ignore

        try:
            raw_payload = json.loads(body.decode() or "{}")
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")  # type: ignore

        envelope = ProtocolBridge.to_internal(endpoint_id, raw_payload)
        await self._emit("EVENT_WEBHOOK_RECEIVED", envelope)
        _audit("webhook_received", endpoint_id=endpoint_id)
        return web.Response(status=200, text="OK")  # type: ignore

    async def start(self) -> None:
        if web is None:
            _audit("webhook_listener_disabled", reason="aiohttp not installed")
            return
        app = web.Application()
        app.router.add_post("/webhook/{endpoint_id}", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()  # type: ignore
        runner = self._runner
        if runner is not None:
            site = web.TCPSite(runner, self.host, self.port)
        else:
            return
        await site.start()
        _audit("webhook_listener_started", host=self.host, port=self.port)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()


# ══════════════════════════════════════════════════════════════════════════
# IPC SERVER (sockets/ipc_server.py equivalent)
# Wire protocol: [4-byte length | 2-byte op_code | JSON payload]
# ══════════════════════════════════════════════════════════════════════════

class OpCode(int, Enum):
    EXECUTE_EXTERNAL_ACTION = 1
    REGISTER_WEBHOOK_ENDPOINT = 2
    REFRESH_OAUTH_TOKEN = 3
    GET_ADAPTER_HEALTH = 4
    TRIGGER_PERIPHERAL_COMMAND = 5


class IPCServer:
    MAX_PAYLOAD_SIZE = 32 * 1024 * 1024

    def __init__(self, dispatch: Callable[[OpCode, dict], Awaitable[dict]],
                 pipe_path: Optional[str] = None) -> None:
        self._dispatch = dispatch
        if os.name == "nt":
            self.pipe_path = pipe_path or r"\\.\pipe\hojaiga_integration"
        else:
            self.pipe_path = pipe_path or "/tmp/hojaiga_integration.sock"
        self._server: Optional[asyncio.AbstractServer] = None

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                header = await reader.readexactly(6)
                length, op_code = struct.unpack(">IH", header)
                if length > self.MAX_PAYLOAD_SIZE:
                    break
                body = await reader.readexactly(length)
                payload = json.loads(body.decode())
                result = await self._dispatch(OpCode(op_code), payload)
                out = json.dumps(result, default=str).encode()
                writer.write(struct.pack(">IH", len(out), op_code) + out)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            writer.close()

    async def start(self) -> None:
        if os.name == "nt":
            _audit("ipc_server_note", detail="Named pipe requires pywin32 on Windows target host")
            return
        if os.path.exists(self.pipe_path):
            os.remove(self.pipe_path)
        _start_unix_server = getattr(asyncio, "start_unix_server", None)
        if _start_unix_server is None:
            _audit("ipc_server_note", detail="asyncio.start_unix_server unavailable on this platform")
            return
        assert callable(_start_unix_server)
        _typed_unix_server = cast(Callable[..., Awaitable[Any]], _start_unix_server)
        self._server = await _typed_unix_server(self._handle_client, path=self.pipe_path)
        _audit("ipc_server_started", path=self.pipe_path)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()


# ══════════════════════════════════════════════════════════════════════════
# INTEGRATION KERNEL / ROUTER (core/integration_kernel.py + router.py)
# ══════════════════════════════════════════════════════════════════════════

class ExternalIntegrationPipeline:
    """Section 10 — 7-step outbound pipeline."""

    def __init__(self, security_client: Callable[[str], Awaitable[dict]],
                 gateway_client: Callable[[str, str, dict], Awaitable[dict]],
                 circuit_breaker: CircuitBreakerRegistry,
                 adapter_registry: AdapterRegistry,
                 rate_limiter: TokenBucketRateLimiter) -> None:
        self._security_client = security_client
        self._gateway = gateway_client
        self._cb = circuit_breaker
        self._adapters = adapter_registry
        self._rate_limiter = rate_limiter

    async def run(self, request: dict) -> dict:
        request_id = request["request_id"]
        adapter_id = request["adapter_id"]

        # Step 2: authorization
        await self._security_client(adapter_id)

        # Step 3: circuit breaker check
        state = self._cb.check(adapter_id)
        if state == CircuitState.CIRCUIT_OPEN:
            return {"request_id": request_id, "status": "CIRCUIT_OPEN"}

        if not await self._rate_limiter.acquire():
            return {"request_id": request_id, "status": "FAILED", "error_message": "Rate limit exceeded"}

        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            return {"request_id": request_id, "status": "FAILED", "error_message": "Unknown adapter"}

        timeout_s = request.get("timeout_ms", 15000) / 1000.0
        try:
            # Steps 4-6: mapping, outbound transfer, response validation
            result = await asyncio.wait_for(
                adapter.execute(request["endpoint_action"], dict(request["payload_parameters"]), self._gateway),
                timeout=timeout_s,
            )
            self._cb.record_success(adapter_id)
            return {"request_id": request_id, "status": "SUCCESS", "response_data": result,
                    "http_status_code": 200}
        except asyncio.TimeoutError:
            self._cb.record_failure(adapter_id)
            return {"request_id": request_id, "status": "TIMED_OUT"}
        except Exception as exc:  # noqa: BLE001
            self._cb.record_failure(adapter_id)
            return {"request_id": request_id, "status": "FAILED", "error_message": str(exc)}


class IntegrationRouter:
    def __init__(self, pipeline: ExternalIntegrationPipeline) -> None:
        self._pipeline = pipeline

    async def route_execute(self, payload: dict) -> dict:
        _validate(payload, INTEGRATION_ACTION_REQUEST_SCHEMA)
        response = await self._pipeline.run(payload)
        _validate(response, INTEGRATION_ACTION_RESPONSE_SCHEMA)
        return response


class IntegrationKernel:
    """Master IPC socket listener, adapter router, request lifecycle coordinator."""

    def __init__(self, config: dict, adapters_manifest: dict,
                 security_client: Callable[[str], Awaitable[dict]],
                 gateway_client: Callable[[str, str, dict], Awaitable[dict]],
                 event_emitter: Callable[[str, dict], Awaitable[None]]) -> None:
        self.config = config
        self.state_store = IntegrationStateStore()
        self.circuit_breaker = CircuitBreakerRegistry(on_trip=None)
        self.adapter_registry = AdapterRegistry(adapters_manifest)
        self.rate_limiter = TokenBucketRateLimiter(
            capacity=config.get("rate_limit_capacity", 20),
            refill_per_sec=config.get("rate_limit_refill_per_sec", 5.0),
        )
        self.peripheral_bridge = PeripheralBridge()
        self.oauth_manager = OAuthManager(security_client, event_emitter)
        self._event_emitter = event_emitter
        self._security_client = security_client
        self._gateway_client = gateway_client
        self.pipeline = ExternalIntegrationPipeline(
            security_client, gateway_client, self.circuit_breaker,
            self.adapter_registry, self.rate_limiter,
        )
        self.router = IntegrationRouter(self.pipeline)

    async def initialize(self) -> None:
        await self.adapter_registry.load()

    async def dispatch(self, op_code: OpCode, payload: dict) -> dict:
        if op_code == OpCode.EXECUTE_EXTERNAL_ACTION:
            return await self.router.route_execute(payload)
        if op_code == OpCode.REGISTER_WEBHOOK_ENDPOINT:
            secret_hash = hashlib.sha256(payload["hmac_secret"].encode()).hexdigest()
            await self.state_store.register_webhook(payload["endpoint_id"], payload["path"], secret_hash)
            return {"endpoint_id": payload["endpoint_id"], "status": "REGISTERED"}
        if op_code == OpCode.REFRESH_OAUTH_TOKEN:
            record = await self.oauth_manager.refresh_token(payload["adapter_id"])
            return {"adapter_id": payload["adapter_id"], "status": "REFRESHED", "expires_at": record["expires_at"]}
        if op_code == OpCode.GET_ADAPTER_HEALTH:
            return self.circuit_breaker.snapshot(payload["adapter_id"])
        if op_code == OpCode.TRIGGER_PERIPHERAL_COMMAND:
            return await self.peripheral_bridge.trigger(payload["channel_id"], payload.get("command", {}))
        return {"status": "FAILED", "error_message": f"Unknown op_code: {op_code}"}


# ══════════════════════════════════════════════════════════════════════════
# PUBLIC FACADE — the ONLY class other organs / the launcher should import
# ══════════════════════════════════════════════════════════════════════════

class IntegrationOrgan:
    """
    Public organ façade. Mirrors the documented IPC RPC surface:
      ExecuteExternalAction, RegisterWebhookEndpoint, RefreshOAuthToken,
      GetAdapterHealth, TriggerPeripheralCommand.
    """

    def __init__(
        self,
        config_dir: str = "./config",
        security_client: Optional[Callable[[str], Awaitable[dict]]] = None,
        gateway_client: Optional[Callable[[str, str, dict], Awaitable[dict]]] = None,
        cns_event_sink: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        webhook_host: str = "127.0.0.1",
        webhook_port: int = 8712,
    ) -> None:
        config, manifest = self._load_config(config_dir)

        self._security_client = security_client or self._default_security_client
        self._gateway_client = gateway_client or self._default_gateway_client
        self._event_sink = cns_event_sink or self._default_event_sink

        self.kernel = IntegrationKernel(
            config, manifest, self._security_client, self._gateway_client, self._emit_event,
        )
        self.webhook_listener = WebhookListener(
            self.kernel.state_store, self._emit_event, host=webhook_host, port=webhook_port,
        )
        self.ipc_server = IPCServer(self.kernel.dispatch)
        self._ready = False

    @staticmethod
    def _load_config(config_dir: str) -> tuple[dict, dict]:
        base = Path(config_dir)
        rules_path = base / "integration_rules.json"
        manifest_path = base / "adapters_manifest.json"
        rules = json.loads(rules_path.read_text()) if rules_path.exists() else {}
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"adapters": []}
        return rules, manifest

    async def _default_security_client(self, adapter_id: str) -> dict:
        return {"access_token": "", "expires_in": 3600}

    async def _default_gateway_client(self, method: str, url: str, body: dict) -> dict:
        _audit("gateway_call_stub", method=method, url=url)
        return {"stub": True, "url": url, "method": method}

    async def _default_event_sink(self, event_name: str, data: dict) -> None:
        _audit("cns_event_emitted", event_name=event_name)

    async def _emit_event(self, event_name: str, data: dict) -> None:
        await self._event_sink(event_name, data)

    # ── Boot / Shutdown (Sections 3-4) ──────────────────────────────────
    async def start(self) -> None:
        await self.kernel.initialize()
        await self.ipc_server.start()
        await self.webhook_listener.start()
        adapter_ids = list(self.kernel.adapter_registry._adapters.keys())
        await self.kernel.oauth_manager.start_background_refresh(adapter_ids)
        self._ready = True
        _audit("organ_ready", organ="organ_12_integration")

    async def start_cns(self, bus: Any = None) -> None:
        """Connects this Integration organ to the CNS event bus and starts services."""
        if bus is not None:
            self.cns = bus
            if hasattr(bus, "publish"):
                async def _bus_event_sink(event_name: str, data: dict) -> None:
                    try:
                        from core_organs.organ_02_cns_single_file import EventEnvelope
                        env = EventEnvelope(topic=event_name, source_organ="organ_12_integration", payload=data)
                        await bus.publish(env)
                    except Exception as e:
                        logger.warning("Failed to publish %s to CNS bus: %s", event_name, e)
                self._event_sink = _bus_event_sink
        await self.start()
        logger.info("IntegrationOrgan connected to CNS.")

    async def stop(self) -> None:
        self._ready = False
        await self.kernel.oauth_manager.stop()
        await self.webhook_listener.stop()
        await self.ipc_server.stop()
        _audit("organ_stopped", organ="organ_12_integration")

    # ── Public RPC surface ───────────────────────────────────────────────
    async def execute_external_action(self, request_id: str, adapter_id: str, endpoint_action: str,
                                       payload_parameters: dict, timeout_ms: int = 15000) -> dict:
        return await self.kernel.dispatch(OpCode.EXECUTE_EXTERNAL_ACTION, {
            "request_id": request_id, "adapter_id": adapter_id,
            "endpoint_action": endpoint_action, "payload_parameters": payload_parameters,
            "timeout_ms": timeout_ms,
        })

    async def register_webhook_endpoint(self, endpoint_id: str, path: str, hmac_secret: str) -> dict:
        return await self.kernel.dispatch(OpCode.REGISTER_WEBHOOK_ENDPOINT, {
            "endpoint_id": endpoint_id, "path": path, "hmac_secret": hmac_secret,
        })

    async def refresh_oauth_token(self, adapter_id: str) -> dict:
        return await self.kernel.dispatch(OpCode.REFRESH_OAUTH_TOKEN, {"adapter_id": adapter_id})

    async def get_adapter_health(self, adapter_id: str) -> dict:
        return await self.kernel.dispatch(OpCode.GET_ADAPTER_HEALTH, {"adapter_id": adapter_id})

    async def trigger_peripheral_command(self, channel_id: str, command: dict) -> dict:
        return await self.kernel.dispatch(OpCode.TRIGGER_PERIPHERAL_COMMAND, {
            "channel_id": channel_id, "command": command,
        })


__all__ = ["IntegrationOrgan"]
