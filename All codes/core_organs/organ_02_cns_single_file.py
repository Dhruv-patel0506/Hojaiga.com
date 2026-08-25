"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 2
Name: Central Nervous System (CNS Single File)

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Central Nervous System]
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
Dependencies: signal, dataclasses, enum, typing, struct, asyncio, logging, json, time, uuid...
"""
from __future__ import annotations

"""
organ_02_cns_single_file.py
Hojaiga Automation OS -- Organ 02: Central Nervous System (CNS)
SINGLE-FILE CONSOLIDATED PRODUCTION BUILD

Includes:
- Binary protocol framing and length-prefixed encoding/decoding.
- Multi-transport listener (Windows Named Pipes, Unix Domain Sockets, TCP Loopback).
- Prioritized Fan-Out EventBus with Dead-Letter telemetry alerts.
- SessionBus, SocketRegistry, PriorityScheduler, and PipelineEngine.
- Heartbeat monitor and Expiring SyncEngine (mutex lock tokens).
- CNSKernel master orchestrator and standalone daemon entrypoint.
"""

import asyncio
import fnmatch
import heapq
import itertools
import json
import logging
import os
import signal
import struct
import sys
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Awaitable, Callable, Coroutine, Optional, List, Dict, Tuple, Set

logger = logging.getLogger("hojaiga.organ02.cns")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[CNS] %(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)


# ============================================================================
# SECTION 1 -- PROTOCOL FRAMING & DATA CONTRACTS
# ============================================================================
MAX_PAYLOAD_BYTES = 32 * 1024 * 1024
HEADER_STRUCT = struct.Struct("<IH")  # length(uint32) + type(uint16)
CLOCK_SKEW_TOLERANCE_MS = 10000


class MessageType(IntEnum):
    REGISTER_SOCKET = 1
    UNREGISTER_SOCKET = 2
    PUBLISH_EVENT = 3
    SUBSCRIBE_EVENT = 4
    EVENT_DELIVERY = 5
    DISPATCH_TASK = 6
    TASK_RESULT = 7
    EXECUTE_PIPELINE = 8
    PIPELINE_RESULT = 9
    ACQUIRE_LOCK = 10
    RELEASE_LOCK = 11
    LOCK_GRANT = 12
    HEARTBEAT = 13
    HEARTBEAT_ACK = 14
    ACK = 15
    ERROR = 16


class ProtocolError(Exception):
    """Raised on malformed frames, oversize payloads, or header violations."""


def encode_frame(message_type: MessageType, payload: dict) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_PAYLOAD_BYTES:
        raise ProtocolError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    header = HEADER_STRUCT.pack(len(body), int(message_type))
    return header + body


def decode_header(header_bytes: bytes) -> tuple[int, int]:
    if len(header_bytes) != HEADER_STRUCT.size:
        raise ProtocolError("incomplete frame header")
    length, msg_type = HEADER_STRUCT.unpack(header_bytes)
    if length > MAX_PAYLOAD_BYTES:
        raise ProtocolError("declared frame length exceeds maximum payload size")
    return length, msg_type


def decode_payload(payload_bytes: bytes) -> dict:
    try:
        return json.loads(payload_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError(f"invalid JSON payload: {exc}") from exc


def new_event_id() -> str:
    return str(uuid.uuid4())


def now_ms() -> int:
    return int(time.time() * 1000)


def validate_envelope_header(source_organ: str, target: str, event_id: str, timestamp_ms: int) -> None:
    try:
        uuid.UUID(event_id, version=4)
    except (ValueError, AttributeError) as exc:
        raise ProtocolError(f"invalid event_id: {event_id}") from exc
    if not source_organ:
        raise ProtocolError("source_organ is required")
    if not target:
        raise ProtocolError("target is required")
    drift = abs(now_ms() - timestamp_ms)
    if drift > CLOCK_SKEW_TOLERANCE_MS:
        raise ProtocolError(f"timestamp drift {drift}ms exceeds tolerance")


@dataclass
class EventEnvelope:
    """Canonical CNS event envelope routed across all organs."""
    topic: str
    source_organ: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=new_event_id)
    timestamp_ms: int = field(default_factory=now_ms)
    priority: int = 5  # 1 (highest) .. 9 (lowest)
    correlation_id: Optional[str] = None

    def validate(self) -> None:
        validate_envelope_header(self.source_organ, self.topic, self.event_id, self.timestamp_ms)
        if not (1 <= self.priority <= 9):
            raise ProtocolError("priority must be within [1, 9]")

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "topic": self.topic,
            "source_organ": self.source_organ,
            "timestamp_ms": self.timestamp_ms,
            "priority": self.priority,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EventEnvelope":
        env = cls(
            topic=data["topic"],
            source_organ=data["source_organ"],
            payload=data.get("payload", {}),
            event_id=data.get("event_id", new_event_id()),
            timestamp_ms=data.get("timestamp_ms", now_ms()),
            priority=data.get("priority", 5),
            correlation_id=data.get("correlation_id"),
        )
        env.validate()
        return env


@dataclass
class TaskPayload:
    target_organ: str
    capability: str
    source_organ: str
    task_id: str = field(default_factory=new_event_id)
    priority: int = 5
    context: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 30000

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "target_organ": self.target_organ,
            "capability": self.capability,
            "source_organ": self.source_organ,
            "priority": self.priority,
            "context": self.context,
            "timeout_ms": self.timeout_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskPayload":
        return cls(
            target_organ=data["target_organ"],
            capability=data["capability"],
            source_organ=data["source_organ"],
            task_id=data.get("task_id", new_event_id()),
            priority=data.get("priority", 5),
            context=data.get("context", {}),
            timeout_ms=data.get("timeout_ms", 30000),
        )


# ============================================================================
# SECTION 2 -- TRANSPORT LAYER
# ============================================================================
WINDOWS_PIPE_NAME = r"\\.\pipe\hojaiga_cns_master"
UNIX_SOCKET_PATH = "/tmp/hojaiga_cns_master.sock"
ORGAN_PIPE_TEMPLATE_WIN = r"\\.\pipe\hojaiga_organ_{organ_id}"
ORGAN_SOCKET_TEMPLATE_POSIX = "/tmp/hojaiga_organ_{organ_id}.sock"

ConnectionHandler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]
IS_WINDOWS = sys.platform.startswith("win")


def organ_endpoint(organ_id: str) -> str:
    if IS_WINDOWS:
        return ORGAN_PIPE_TEMPLATE_WIN.format(organ_id=organ_id)
    return ORGAN_SOCKET_TEMPLATE_POSIX.format(organ_id=organ_id)


@dataclass
class ListenerHandle:
    server: Any
    endpoint: str

    async def close(self) -> None:
        if hasattr(self.server, "close"):
            self.server.close()
            wait = getattr(self.server, "wait_closed", None)
            if wait is not None:
                await wait()
        if not IS_WINDOWS and os.path.exists(self.endpoint):
            try:
                os.unlink(self.endpoint)
            except OSError:
                pass


async def start_master_listener(handler: ConnectionHandler) -> ListenerHandle:
    if IS_WINDOWS:
        loop = asyncio.get_running_loop()
        if isinstance(loop, getattr(asyncio, "ProactorEventLoop", type(None))):
            async def _client_connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                await handler(reader, writer)
            server = await loop.start_serving_pipe(  # type: ignore
                lambda: _PipeProtocolAdapter(_client_connected, loop),
                WINDOWS_PIPE_NAME,
            )
            return ListenerHandle(server=server, endpoint=WINDOWS_PIPE_NAME)
        else:
            # Fallback for standard selector loops on Windows
            server = await asyncio.start_server(handler, host="127.0.0.1", port=47620)
            return ListenerHandle(server=server, endpoint="127.0.0.1:47620")

    if os.path.exists(UNIX_SOCKET_PATH):
        try:
            os.unlink(UNIX_SOCKET_PATH)
        except OSError:
            pass
    server = await asyncio.start_unix_server(handler, path=UNIX_SOCKET_PATH)
    try:
        os.chmod(UNIX_SOCKET_PATH, 0o660)
    except OSError:
        pass
    return ListenerHandle(server=server, endpoint=UNIX_SOCKET_PATH)


class _PipeProtocolAdapter(asyncio.StreamReaderProtocol):
    def __init__(self, on_connected: ConnectionHandler, loop: asyncio.AbstractEventLoop) -> None:
        self._on_connected = on_connected
        self._loop = loop
        self._reader = asyncio.StreamReader(loop=loop)
        super().__init__(self._reader, loop=loop)

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        super().connection_made(transport)
        writer = asyncio.StreamWriter(transport, self, self._reader, self._loop)  # type: ignore
        asyncio.ensure_future(self._on_connected(self._reader, writer), loop=self._loop)

    def connection_lost(self, exc: Exception | None) -> None:
        super().connection_lost(exc)


# ============================================================================
# SECTION 3 -- EVENT BUS & SESSION BUS
# ============================================================================
Subscriber = Callable[[EventEnvelope], Coroutine[Any, Any, None]]


@dataclass
class Subscription:
    subscription_id: str
    topic_pattern: str
    organ_id: str
    callback: Subscriber
    min_priority: int = 9


class EventBus:
    """Prioritized topic router with guaranteed fan-out and dead-letter alert dispatch."""

    def __init__(self, max_retries: int = 3, retry_backoff_s: float = 0.1) -> None:
        self._subscriptions: dict[str, Subscription] = {}
        self._max_retries = max_retries
        self._retry_backoff_s = retry_backoff_s
        self._dead_letters: list[dict] = []
        self._lock = asyncio.Lock()

    async def subscribe(
        self, topic_pattern: str, organ_id: str, callback: Subscriber, min_priority: int = 9
    ) -> str:
        sub_id = str(uuid.uuid4())
        async with self._lock:
            self._subscriptions[sub_id] = Subscription(sub_id, topic_pattern, organ_id, callback, min_priority)
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        async with self._lock:
            return self._subscriptions.pop(subscription_id, None) is not None

    async def unsubscribe_organ(self, organ_id: str) -> int:
        async with self._lock:
            to_remove = [sid for sid, sub in self._subscriptions.items() if sub.organ_id == organ_id]
            for sid in to_remove:
                del self._subscriptions[sid]
            return len(to_remove)

    def _matching_subscriptions(self, envelope: EventEnvelope) -> list[Subscription]:
        return [
            sub
            for sub in self._subscriptions.values()
            if fnmatch.fnmatch(envelope.topic, sub.topic_pattern) and envelope.priority <= sub.min_priority
        ]

    async def publish(self, envelope: EventEnvelope) -> int:
        envelope.validate()
        matches = self._matching_subscriptions(envelope)
        delivered = 0
        results = await asyncio.gather(
            *(self._deliver_with_retry(sub, envelope) for sub in matches), return_exceptions=True
        )
        for result in results:
            if result is True:
                delivered += 1
        return delivered

    async def _deliver_with_retry(self, sub: Subscription, envelope: EventEnvelope) -> bool:
        attempt = 0
        while attempt <= self._max_retries:
            try:
                await sub.callback(envelope)
                return True
            except Exception as exc:
                attempt += 1
                if attempt > self._max_retries:
                    dead_record = {
                        "event_id": envelope.event_id,
                        "topic": envelope.topic,
                        "subscription_id": sub.subscription_id,
                        "organ_id": sub.organ_id,
                        "error": str(exc),
                        "failed_at_ms": int(time.time() * 1000),
                    }
                    self._dead_letters.append(dead_record)

                    # Notify sys.events and Error Catalog about dead letter without raising
                    if envelope.topic != "sys.events":
                        try:
                            sys_alert = EventEnvelope(
                                topic="sys.events",
                                source_organ="02",
                                payload={
                                    "event_type": "EVENT_DEAD_LETTER_LOGGED",
                                    "dead_letter": dead_record,
                                },
                                priority=1,
                            )
                            matches = [s for s in self._subscriptions.values() if fnmatch.fnmatch("sys.events", s.topic_pattern)]
                            for s in matches:
                                asyncio.create_task(s.callback(sys_alert))
                        except Exception:
                            pass
                    return False
                await asyncio.sleep(self._retry_backoff_s * attempt)
        return False

    def dead_letters(self) -> list[dict]:
        return list(self._dead_letters)


@dataclass
class SessionContext:
    session_id: str
    owner_organ: str
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    state: dict[str, Any] = field(default_factory=dict)
    expires_at_ms: int | None = None


class SessionBus:
    def __init__(self, default_ttl_ms: int = 3600_000) -> None:
        self._sessions: dict[str, SessionContext] = {}
        self._default_ttl_ms = default_ttl_ms
        self._lock = asyncio.Lock()

    async def create_session(self, owner_organ: str, ttl_ms: int | None = None) -> SessionContext:
        session_id = str(uuid.uuid4())
        now = int(time.time() * 1000)
        ctx = SessionContext(
            session_id=session_id,
            owner_organ=owner_organ,
            created_at_ms=now,
            expires_at_ms=now + (ttl_ms if ttl_ms is not None else self._default_ttl_ms),
        )
        async with self._lock:
            self._sessions[session_id] = ctx
        return ctx

    async def get_session(self, session_id: str) -> SessionContext | None:
        async with self._lock:
            ctx = self._sessions.get(session_id)
            if ctx is None:
                return None
            if ctx.expires_at_ms is not None and ctx.expires_at_ms < int(time.time() * 1000):
                del self._sessions[session_id]
                return None
            return ctx

    async def update_state(self, session_id: str, patch: dict[str, Any]) -> bool:
        async with self._lock:
            ctx = self._sessions.get(session_id)
            if ctx is None:
                return False
            ctx.state.update(patch)
            return True

    async def close_session(self, session_id: str) -> bool:
        async with self._lock:
            return self._sessions.pop(session_id, None) is not None


# ============================================================================
# SECTION 4 -- SOCKET REGISTRY & CONNECTION POOL
# ============================================================================
PermissionChecker = Callable[[str, str], Awaitable[bool]]


@dataclass
class OrganConnection:
    organ_id: str
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    connected_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    last_heartbeat_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    healthy: bool = True

    async def send(self, message_type: MessageType, payload: dict) -> None:
        frame = encode_frame(message_type, payload)
        self.writer.write(frame)
        await self.writer.drain()

    async def close(self) -> None:
        try:
            self.writer.close()
            wait_closed = getattr(self.writer, "wait_closed", None)
            if wait_closed is not None:
                await wait_closed()
        except (ConnectionError, OSError):
            pass


class SocketRegistry:
    def __init__(self, permission_checker: Optional[PermissionChecker] = None) -> None:
        self._connections: dict[str, OrganConnection] = {}
        self._permission_checker = permission_checker
        self._lock = asyncio.Lock()

    async def bind_socket(
        self, organ_id: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> OrganConnection:
        conn = OrganConnection(organ_id=organ_id, reader=reader, writer=writer)
        async with self._lock:
            existing = self._connections.get(organ_id)
            if existing is not None:
                await existing.close()
            self._connections[organ_id] = conn
        return conn

    async def unbind_socket(self, organ_id: str) -> bool:
        async with self._lock:
            conn = self._connections.pop(organ_id, None)
        if conn is None:
            return False
        await conn.close()
        return True

    def resolve_route(self, destination_organ: str) -> Optional[OrganConnection]:
        return self._connections.get(destination_organ)

    def is_bound(self, organ_id: str) -> bool:
        return organ_id in self._connections

    def bound_organs(self) -> list[str]:
        return list(self._connections.keys())

    def mark_heartbeat(self, organ_id: str) -> None:
        conn = self._connections.get(organ_id)
        if conn is not None:
            conn.last_heartbeat_ms = int(time.time() * 1000)
            conn.healthy = True

    def mark_unhealthy(self, organ_id: str) -> None:
        conn = self._connections.get(organ_id)
        if conn is not None:
            conn.healthy = False

    def stale_organs(self, timeout_ms: int) -> list[str]:
        now = int(time.time() * 1000)
        return [
            organ_id
            for organ_id, conn in self._connections.items()
            if now - conn.last_heartbeat_ms > timeout_ms
        ]

    async def authorize(self, source_organ: str, destination_organ: str) -> bool:
        if self._permission_checker is None:
            return True
        return await self._permission_checker(source_organ, destination_organ)

    async def route_message(self, destination_organ: str, message_type: MessageType, payload: dict) -> bool:
        conn = self.resolve_route(destination_organ)
        if conn is None:
            return False
        try:
            await conn.send(message_type, payload)
            return True
        except (ConnectionError, OSError):
            self.mark_unhealthy(destination_organ)
            return False

    async def close_all(self) -> None:
        async with self._lock:
            conns = list(self._connections.values())
            self._connections.clear()
        await asyncio.gather(*(c.close() for c in conns), return_exceptions=True)


# ============================================================================
# SECTION 5 -- SCHEDULER & PIPELINE ENGINES
# ============================================================================
DispatchFn = Callable[[TaskPayload], Awaitable[dict]]


@dataclass(order=True)
class _QueueItem:
    priority: int
    sequence: int
    task: TaskPayload = field(compare=False)
    enqueued_at_ms: int = field(compare=False)


@dataclass
class TaskResult:
    task_id: str
    success: bool
    result: dict
    duration_ms: int
    error: Optional[str] = None


class PriorityScheduler:
    def __init__(self, dispatch_fn: DispatchFn, worker_count: int = 4) -> None:
        self._heap: list[_QueueItem] = []
        self._counter = itertools.count()
        self._condition = asyncio.Condition()
        self._dispatch_fn = dispatch_fn
        self._worker_count = worker_count
        self._workers: list[asyncio.Task] = []
        self._results: dict[str, TaskResult] = {}
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._workers = [asyncio.create_task(self._worker_loop(i)) for i in range(self._worker_count)]

    async def stop(self) -> None:
        self._running = False
        async with self._condition:
            self._condition.notify_all()
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def enqueue(self, task: TaskPayload) -> None:
        item = _QueueItem(
            priority=task.priority,
            sequence=next(self._counter),
            task=task,
            enqueued_at_ms=int(time.time() * 1000),
        )
        async with self._condition:
            heapq.heappush(self._heap, item)
            self._condition.notify()

    async def _worker_loop(self, worker_index: int) -> None:
        while self._running:
            item = await self._dequeue()
            if item is None:
                continue
            started = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    self._dispatch_fn(item.task), timeout=item.task.timeout_ms / 1000
                )
                duration_ms = int((time.monotonic() - started) * 1000)
                self._results[item.task.task_id] = TaskResult(
                    task_id=item.task.task_id, success=True, result=result, duration_ms=duration_ms
                )
            except asyncio.TimeoutError:
                duration_ms = int((time.monotonic() - started) * 1000)
                self._results[item.task.task_id] = TaskResult(
                    task_id=item.task.task_id,
                    success=False,
                    result={},
                    duration_ms=duration_ms,
                    error="dispatch timeout exceeded",
                )
            except Exception as exc:
                duration_ms = int((time.monotonic() - started) * 1000)
                self._results[item.task.task_id] = TaskResult(
                    task_id=item.task.task_id, success=False, result={}, duration_ms=duration_ms, error=str(exc)
                )

    async def _dequeue(self) -> Optional[_QueueItem]:
        async with self._condition:
            while not self._heap and self._running:
                await self._condition.wait()
            if not self._running:
                return None
            return heapq.heappop(self._heap)


StageFn = Callable[[dict], Awaitable[dict]]


@dataclass
class Stage:
    name: str
    fn: StageFn
    parallel_group: str | None = None


@dataclass
class PipelineDefinition:
    pipeline_id: str
    stages: list[Stage] = field(default_factory=list)

    def add_stage(self, name: str, fn: StageFn, parallel_group: str | None = None) -> "PipelineDefinition":
        self.stages.append(Stage(name=name, fn=fn, parallel_group=parallel_group))
        return self


@dataclass
class StageTrace:
    name: str
    duration_ms: int
    ok: bool
    error: str | None = None


@dataclass
class PipelineResult:
    pipeline_id: str
    payload: dict[str, Any]
    trace: list[StageTrace]
    success: bool
    error: str | None = None


class PipelineEngine:
    def __init__(self) -> None:
        self._pipelines: dict[str, PipelineDefinition] = {}

    def register(self, definition: PipelineDefinition) -> None:
        self._pipelines[definition.pipeline_id] = definition

    def compile_pipeline(self, pipeline_id: str) -> PipelineDefinition:
        definition = self._pipelines.get(pipeline_id)
        if definition is None:
            raise KeyError(f"unknown pipeline: {pipeline_id}")
        return definition

    async def execute_stage(self, stage: Stage, input_payload: dict) -> tuple[dict, StageTrace]:
        started = time.monotonic()
        try:
            output = await stage.fn(input_payload)
            duration_ms = int((time.monotonic() - started) * 1000)
            return output, StageTrace(name=stage.name, duration_ms=duration_ms, ok=True)
        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            return input_payload, StageTrace(name=stage.name, duration_ms=duration_ms, ok=False, error=str(exc))

    async def execute(self, pipeline_id: str, input_payload: dict) -> PipelineResult:
        definition = self.compile_pipeline(pipeline_id)
        payload = dict(input_payload)
        trace: list[StageTrace] = []

        index = 0
        stages = definition.stages
        while index < len(stages):
            stage = stages[index]
            if stage.parallel_group is None:
                payload, stage_trace = await self.execute_stage(stage, payload)
                trace.append(stage_trace)
                if not stage_trace.ok:
                    return PipelineResult(pipeline_id, payload, trace, success=False, error=stage_trace.error)
                index += 1
                continue

            group_id = stage.parallel_group
            group_stages = []
            while index < len(stages) and stages[index].parallel_group == group_id:
                group_stages.append(stages[index])
                index += 1

            results = await asyncio.gather(*(self.execute_stage(s, payload) for s in group_stages))
            for output, stage_trace in results:
                trace.append(stage_trace)
                if not stage_trace.ok:
                    return PipelineResult(pipeline_id, payload, trace, success=False, error=stage_trace.error)
                payload.update(output)

        return PipelineResult(pipeline_id, payload, trace, success=True)


# ============================================================================
# SECTION 6 -- HEARTBEAT & MUTEX LOCKS
# ============================================================================
@dataclass
class LockGrant:
    resource_id: str
    holder_organ: str
    lock_token: str
    granted_at_ms: int
    expires_at_ms: int


class LockTimeoutError(Exception):
    pass


class SyncEngine:
    def __init__(self) -> None:
        self._locks: dict[str, LockGrant] = {}
        self._waiters: dict[str, asyncio.Condition] = {}

    def _condition_for(self, resource_id: str) -> asyncio.Condition:
        cond = self._waiters.get(resource_id)
        if cond is None:
            cond = asyncio.Condition()
            self._waiters[resource_id] = cond
        return cond

    async def acquire_lock(
        self, resource_id: str, holder_organ: str, ttl_ms: int = 30000, wait_timeout_ms: int = 10000
    ) -> LockGrant:
        cond = self._condition_for(resource_id)
        deadline = time.monotonic() + wait_timeout_ms / 1000
        async with cond:
            while True:
                self._expire_if_needed(resource_id)
                if resource_id not in self._locks:
                    grant = LockGrant(
                        resource_id=resource_id,
                        holder_organ=holder_organ,
                        lock_token=str(uuid.uuid4()),
                        granted_at_ms=int(time.time() * 1000),
                        expires_at_ms=int(time.time() * 1000) + ttl_ms,
                    )
                    self._locks[resource_id] = grant
                    return grant
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LockTimeoutError(f"timed out acquiring lock on {resource_id}")
                try:
                    await asyncio.wait_for(cond.wait(), timeout=remaining)
                except asyncio.TimeoutError as exc:
                    raise LockTimeoutError(f"timed out acquiring lock on {resource_id}") from exc

    def _expire_if_needed(self, resource_id: str) -> None:
        grant = self._locks.get(resource_id)
        if grant is not None and grant.expires_at_ms < int(time.time() * 1000):
            del self._locks[resource_id]

    async def release_lock(self, resource_id: str, lock_token: str) -> bool:
        cond = self._condition_for(resource_id)
        async with cond:
            grant = self._locks.get(resource_id)
            if grant is None or grant.lock_token != lock_token:
                return False
            del self._locks[resource_id]
            cond.notify_all()
            return True


class HeartbeatMonitor:
    def __init__(self, registry: SocketRegistry, interval_ms: int = 1000, timeout_ms: int = 4000) -> None:
        self._registry = registry
        self._interval_s = interval_ms / 1000
        self._timeout_ms = timeout_ms
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            stale = set(self._registry.stale_organs(self._timeout_ms))
            for organ_id in stale:
                self._registry.mark_unhealthy(organ_id)
            for organ_id in self._registry.bound_organs():
                await self._registry.route_message(organ_id, MessageType.HEARTBEAT, {"timestamp_ms": now_ms()})
            await asyncio.sleep(self._interval_s)


# ============================================================================
# SECTION 7 -- CNS STATE MACHINE & MASTER KERNEL
# ============================================================================
class CNSState(str, Enum):
    BOOTSTRAPPING = "BOOTSTRAPPING"
    OPERATIONAL = "OPERATIONAL"
    DEGRADED = "DEGRADED"
    PAUSED = "PAUSED"
    SHUTTING_DOWN = "SHUTTING_DOWN"


class CNSKernel:
    """Central Nervous System master runtime."""

    def __init__(self, security_permission_checker: Optional[PermissionChecker] = None) -> None:
        self.registry = SocketRegistry(permission_checker=security_permission_checker)
        self.event_bus = EventBus()
        self.session_bus = SessionBus()
        self.pipeline_engine = PipelineEngine()
        self.sync_engine = SyncEngine()
        self.scheduler = PriorityScheduler(dispatch_fn=self._dispatch_task_to_organ)
        self.heartbeat_monitor = HeartbeatMonitor(self.registry)
        self.state = CNSState.BOOTSTRAPPING
        self._listener_handle: Optional[ListenerHandle] = None
        self._register_default_pipelines()

    async def start(self) -> None:
        self._listener_handle = await start_master_listener(self._handle_connection)
        await self.scheduler.start()
        await self.heartbeat_monitor.start()
        self.state = CNSState.OPERATIONAL
        await self._emit_system_event("EVENT_CNS_STARTED", {"endpoint": self._listener_handle.endpoint})
        logging.info("CNS Kernel operational at %s", self._listener_handle.endpoint)

    async def shutdown(self) -> None:
        self.state = CNSState.SHUTTING_DOWN
        await self.heartbeat_monitor.stop()
        await self.scheduler.stop()
        await self.registry.close_all()
        if self._listener_handle is not None:
            await self._listener_handle.close()
        logging.info("CNS Kernel shutdown completed.")

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        organ_id: Optional[str] = None
        try:
            while True:
                header_bytes = await reader.readexactly(6)
                length, msg_type = decode_header(header_bytes)
                body_bytes = await reader.readexactly(length) if length else b""
                payload = decode_payload(body_bytes) if body_bytes else {}
                message_type = MessageType(msg_type)

                if message_type == MessageType.REGISTER_SOCKET and organ_id is None:
                    organ_id = payload.get("organ_id")
                    if not organ_id:
                        writer.write(encode_frame(MessageType.ERROR, {"error": "organ_id required"}))
                        await writer.drain()
                        continue
                    await self.registry.bind_socket(organ_id, reader, writer)
                    await self._emit_system_event("EVENT_ORGAN_CONNECTED", {"organ_id": organ_id})
                    writer.write(encode_frame(MessageType.ACK, {"status": "REGISTERED", "organ_id": organ_id}))
                    await writer.drain()
                    continue

                if organ_id is None:
                    writer.write(encode_frame(MessageType.ERROR, {"error": "Must REGISTER_SOCKET first"}))
                    await writer.drain()
                    continue

                await self._route_rpc(organ_id, message_type, payload, writer)
        except (asyncio.IncompleteReadError, ConnectionResetError, ProtocolError):
            pass
        finally:
            if organ_id is not None:
                await self.registry.unbind_socket(organ_id)
                await self.event_bus.unsubscribe_organ(organ_id)
                await self._emit_system_event("EVENT_ORGAN_DISCONNECTED", {"organ_id": organ_id})

    async def _route_rpc(self, organ_id: str, message_type: MessageType, payload: dict, writer: asyncio.StreamWriter) -> None:
        if message_type == MessageType.PUBLISH_EVENT:
            envelope = EventEnvelope.from_dict(payload)
            delivered = await self.event_bus.publish(envelope)
            writer.write(encode_frame(MessageType.ACK, {"event_id": envelope.event_id, "delivered": delivered}))
            await writer.drain()
        elif message_type == MessageType.SUBSCRIBE_EVENT:
            topic = payload["topic_pattern"]
            async def _forward(env: EventEnvelope) -> None:
                await self.registry.route_message(organ_id, MessageType.EVENT_DELIVERY, env.to_dict())
            sub_id = await self.event_bus.subscribe(topic, organ_id, _forward, payload.get("min_priority", 9))
            writer.write(encode_frame(MessageType.ACK, {"subscription_id": sub_id}))
            await writer.drain()
        elif message_type == MessageType.HEARTBEAT:
            self.registry.mark_heartbeat(organ_id)
            writer.write(encode_frame(MessageType.HEARTBEAT_ACK, {"timestamp_ms": now_ms()}))
            await writer.drain()
        elif message_type == MessageType.ACQUIRE_LOCK:
            grant = await self.sync_engine.acquire_lock(payload["resource_id"], organ_id, payload.get("ttl_ms", 30000))
            writer.write(encode_frame(MessageType.LOCK_GRANT, {"resource_id": grant.resource_id, "lock_token": grant.lock_token}))
            await writer.drain()
        elif message_type == MessageType.RELEASE_LOCK:
            released = await self.sync_engine.release_lock(payload["resource_id"], payload["lock_token"])
            writer.write(encode_frame(MessageType.ACK, {"released": released}))
            await writer.drain()

    async def _dispatch_task_to_organ(self, task: TaskPayload) -> dict:
        delivered = await self.registry.route_message(task.target_organ, MessageType.DISPATCH_TASK, task.to_dict())
        if not delivered:
            raise ConnectionError(f"Target organ {task.target_organ} unreachable")
        return {"status": "DISPATCHED", "target_organ": task.target_organ}

    async def _emit_system_event(self, topic: str, payload: dict) -> None:
        envelope = EventEnvelope(topic=topic, source_organ="02", payload=payload, priority=2)
        await self.event_bus.publish(envelope)

    def _register_default_pipelines(self) -> None:
        std = PipelineDefinition(pipeline_id="StandardTaskDispatchPipeline")
        std.add_stage("ingest", lambda p: asyncio.sleep(0, result={**p, "ok": True}))
        self.pipeline_engine.register(std)


# ============================================================================
# SECTION 8 -- ENTRYPOINT
# ============================================================================
async def run_daemon() -> None:
    kernel = CNSKernel()
    await kernel.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await kernel.shutdown()


def main() -> None:
    asyncio.run(run_daemon())


if __name__ == "__main__":
    main()
