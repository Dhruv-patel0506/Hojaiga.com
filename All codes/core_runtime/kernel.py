"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: kernel.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [kernel.py]
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
Dependencies: enum, typing, __future__, json, time...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: kernel.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
AOS Kernel Organ (Organ 27)
============================
Deterministic orchestration layer for the Hojaiga Automation OS.
Zero AI reasoning. Zero domain automation. Pure orchestration.

PRE-CODE DIAGRAM (Boot Flow)
-----------------------------
Config -> Hardware Check -> Dependency Graph -> Registries Init ->
Communication Layer -> Service Manager -> Runtimes/Connectors ->
RUNNING

PRE-CODE DIAGRAM (Module Map)
------------------------------
KernelCore
 |-- StateManager
 |-- BootManager / ShutdownManager
 |-- DependencyManager
 |-- ResourceCoordinator
 |-- OrganRegistry / RuntimeRegistry / ServiceRegistry
 |-- ServiceManager (GlobalScheduler, BackgroundWorkers)
 |-- CommunicationLayer (SocketBus, EventDispatcher, PipelineBus)
 |-- HeartbeatManager -> RecoveryManager -> SafeModeManager
 |-- LoggingManager / MetricsManager / DiagnosticsManager
 |-- SecurityManager

All cross-organ communication happens exclusively through
`SocketBus.publish` / `EventDispatcher.subscribe` / `PipelineBus.run`.
This organ never imports or calls another organ's private code.
"""


import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Awaitable, Optional

__version__ = "1.0.0"

# --------------------------------------------------------------------------
# ACTUAL-CODE DIAGRAM (Data Model)
# SystemState -> HealthStatus -> OrganManifest -> Registries -> KernelCore
# --------------------------------------------------------------------------


class SystemState(str, Enum):
    INITIALIZING = "INITIALIZING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    BUSY = "BUSY"
    IDLE = "IDLE"
    PAUSED = "PAUSED"
    MAINTENANCE = "MAINTENANCE"
    RECOVERY = "RECOVERY"
    SAFE_MODE = "SAFE_MODE"
    UPDATING = "UPDATING"
    STOPPING = "STOPPING"
    SHUTDOWN = "SHUTDOWN"
    CRASHED = "CRASHED"


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    CRITICAL = "CRITICAL"


_VALID_TRANSITIONS: dict[SystemState, set[SystemState]] = {
    SystemState.INITIALIZING: {SystemState.STARTING, SystemState.CRASHED},
    SystemState.STARTING: {SystemState.RUNNING, SystemState.RECOVERY, SystemState.CRASHED},
    SystemState.RUNNING: {
        SystemState.BUSY, SystemState.IDLE, SystemState.PAUSED,
        SystemState.MAINTENANCE, SystemState.RECOVERY, SystemState.UPDATING,
        SystemState.STOPPING, SystemState.CRASHED,
    },
    SystemState.BUSY: {SystemState.RUNNING, SystemState.CRASHED},
    SystemState.IDLE: {SystemState.RUNNING, SystemState.STOPPING},
    SystemState.PAUSED: {SystemState.RUNNING, SystemState.STOPPING},
    SystemState.MAINTENANCE: {SystemState.RUNNING, SystemState.STOPPING},
    SystemState.RECOVERY: {SystemState.RUNNING, SystemState.SAFE_MODE},
    SystemState.SAFE_MODE: {SystemState.MAINTENANCE, SystemState.STOPPING},
    SystemState.UPDATING: {SystemState.RUNNING, SystemState.RECOVERY},
    SystemState.STOPPING: {SystemState.SHUTDOWN},
    SystemState.SHUTDOWN: set(),
    SystemState.CRASHED: {SystemState.SAFE_MODE, SystemState.RECOVERY},
}


class KernelError(Exception):
    """Base kernel exception."""


class InvalidStateTransition(KernelError):
    pass


class DependencyCycleError(KernelError):
    pass


class DuplicateRegistrationError(KernelError):
    pass


@dataclass(frozen=True)
class OrganManifest:
    organ_name: str
    version: str
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    sockets: tuple[str, ...] = field(default_factory=tuple)
    startup_order: int = 0
    shutdown_order: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OrganRecord:
    manifest: OrganManifest
    status: HealthStatus = HealthStatus.HEALTHY
    missed_heartbeats: int = 0
    registered_at: float = field(default_factory=time.time)
    restart_attempts: int = 0


# --------------------------------------------------------------------------
# Logging Manager
# --------------------------------------------------------------------------


class LoggingManager:
    def __init__(self, name: str = "aos.kernel") -> None:
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '{"ts":"%(asctime)s","level":"%(levelname)s","msg":%(message)r}'
            ))
            self._logger.addHandler(handler)
        self._logger.setLevel(logging.INFO)

    def log(self, level: str, msg: str, **fields: Any) -> None:
        payload = json.dumps({"msg": msg, **fields}, default=str)
        getattr(self._logger, level.lower(), self._logger.info)(payload)


# --------------------------------------------------------------------------
# State Manager
# --------------------------------------------------------------------------


class StateManager:
    def __init__(self, logger: LoggingManager) -> None:
        self._state = SystemState.INITIALIZING
        self._logger = logger
        self._history: list[tuple[float, SystemState, SystemState]] = []
        self._listeners: list[Callable[[SystemState, SystemState], None]] = []

    @property
    def state(self) -> SystemState:
        return self._state

    def on_transition(self, listener: Callable[[SystemState, SystemState], None]) -> None:
        self._listeners.append(listener)

    def transition(self, new_state: SystemState) -> None:
        allowed = _VALID_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise InvalidStateTransition(f"{self._state} -> {new_state} not permitted")
        old = self._state
        self._state = new_state
        self._history.append((time.time(), old, new_state))
        self._logger.log("info", "state_transition", old=old.value, new=new_state.value)
        for listener in self._listeners:
            listener(old, new_state)

    def history(self) -> list[tuple[float, SystemState, SystemState]]:
        return list(self._history)


# --------------------------------------------------------------------------
# Dependency Manager (DAG solver)
# --------------------------------------------------------------------------


class DependencyManager:
    def __init__(self) -> None:
        self._graph: dict[str, set[str]] = {}

    def add(self, name: str, dependencies: tuple[str, ...]) -> None:
        self._graph[name] = set(dependencies)

    def remove(self, name: str) -> None:
        self._graph.pop(name, None)

    def resolve_order(self) -> list[str]:
        visited: dict[str, int] = {}
        order: list[str] = []

        def visit(node: str, path: set[str]) -> None:
            state = visited.get(node, 0)
            if state == 1:
                raise DependencyCycleError(f"Cycle detected at {node}")
            if state == 2:
                return
            visited[node] = 1
            for dep in self._graph.get(node, ()):
                if dep not in self._graph:
                    raise KernelError(f"Unmet dependency: {node} -> {dep}")
                visit(dep, path | {node})
            visited[node] = 2
            order.append(node)

        for node in list(self._graph):
            visit(node, set())
        return order


# --------------------------------------------------------------------------
# Resource Coordinator
# --------------------------------------------------------------------------


@dataclass
class ResourceQuota:
    cpu_percent: float = 100.0
    ram_mb: int = 32_000
    gpu_vram_mb: int = 4_000


class ResourceCoordinator:
    def __init__(self, total: ResourceQuota, logger: LoggingManager) -> None:
        self._total = total
        self._allocated = ResourceQuota(0.0, 0, 0)
        self._leases: dict[str, ResourceQuota] = {}
        self._logger = logger

    def allocate(self, owner: str, request: ResourceQuota) -> bool:
        if (self._allocated.cpu_percent + request.cpu_percent > self._total.cpu_percent
                or self._allocated.ram_mb + request.ram_mb > self._total.ram_mb
                or self._allocated.gpu_vram_mb + request.gpu_vram_mb > self._total.gpu_vram_mb):
            self._logger.log("warning", "resource_denied", owner=owner)
            return False
        self._leases[owner] = request
        self._allocated.cpu_percent += request.cpu_percent
        self._allocated.ram_mb += request.ram_mb
        self._allocated.gpu_vram_mb += request.gpu_vram_mb
        self._logger.log("info", "resource_allocated", owner=owner, request=asdict(request))
        return True

    def release(self, owner: str) -> None:
        lease = self._leases.pop(owner, None)
        if lease is None:
            return
        self._allocated.cpu_percent -= lease.cpu_percent
        self._allocated.ram_mb -= lease.ram_mb
        self._allocated.gpu_vram_mb -= lease.gpu_vram_mb
        self._logger.log("info", "resource_released", owner=owner)

    def usage(self) -> ResourceQuota:
        return self._allocated


# --------------------------------------------------------------------------
# Registries
# --------------------------------------------------------------------------


class OrganRegistry:
    def __init__(self, logger: LoggingManager) -> None:
        self._organs: dict[str, OrganRecord] = {}
        self._logger = logger

    def register(self, manifest: OrganManifest) -> None:
        if manifest.organ_name in self._organs:
            raise DuplicateRegistrationError(manifest.organ_name)
        self._organs[manifest.organ_name] = OrganRecord(manifest=manifest)
        self._logger.log("info", "organ_registered", organ=manifest.organ_name)

    def unregister(self, name: str) -> None:
        self._organs.pop(name, None)
        self._logger.log("info", "organ_unregistered", organ=name)

    def get(self, name: str) -> Optional[OrganRecord]:
        return self._organs.get(name)

    def all(self) -> dict[str, OrganRecord]:
        return dict(self._organs)


class ServiceRegistry:
    def __init__(self) -> None:
        self._services: dict[str, dict] = {}

    def register(self, name: str, info: dict) -> None:
        self._services[name] = info

    def unregister(self, name: str) -> None:
        self._services.pop(name, None)

    def get(self, name: str) -> Optional[dict]:
        return self._services.get(name)


class RuntimeRegistry:
    def __init__(self) -> None:
        self._runtimes: dict[str, dict] = {}

    def register(self, name: str, info: dict) -> None:
        self._runtimes[name] = info

    def unregister(self, name: str) -> None:
        self._runtimes.pop(name, None)

    def get(self, name: str) -> Optional[dict]:
        return self._runtimes.get(name)


# --------------------------------------------------------------------------
# Communication Layer: SocketBus / EventDispatcher / PipelineBus
# --------------------------------------------------------------------------


@dataclass
class SocketMessage:
    msg_type: str
    payload: dict
    sender: str
    msg_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp_ns: int = field(default_factory=time.time_ns)


class SocketBus:
    """In-process pub/sub simulating the IPC socket layer described in
    KERNEL.md (ZeroMQ/Unix sockets in production; async queues here)."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[SocketMessage], Awaitable[None]]]] = {}

    def subscribe(self, socket_name: str, handler: Callable[[SocketMessage], Awaitable[None]]) -> None:
        self._subscribers.setdefault(socket_name, []).append(handler)

    async def publish(self, socket_name: str, message: SocketMessage) -> None:
        for handler in self._subscribers.get(socket_name, ()):
            await handler(message)


class EventDispatcher:
    def __init__(self, logger: LoggingManager) -> None:
        self._listeners: dict[str, list[Callable[[dict], None]]] = {}
        self._logger = logger

    def subscribe(self, event_name: str, listener: Callable[[dict], None]) -> None:
        self._listeners.setdefault(event_name, []).append(listener)

    def emit(self, event_name: str, payload: dict) -> None:
        self._logger.log("debug", "event_emitted", event=event_name)
        for listener in self._listeners.get(event_name, ()):
            listener(payload)


class PipelineBus:
    """Ordered stage pipelines (Boot Pipeline, Shutdown Pipeline, etc.)."""

    def __init__(self) -> None:
        self._pipelines: dict[str, list[Callable[[dict], Awaitable[dict]]]] = {}

    def define(self, name: str, stages: list[Callable[[dict], Awaitable[dict]]]) -> None:
        self._pipelines[name] = stages

    async def run(self, name: str, context: dict) -> dict:
        for stage in self._pipelines.get(name, ()):
            context = await stage(context) or context
        return context


# --------------------------------------------------------------------------
# Heartbeat & Recovery
# --------------------------------------------------------------------------


class HeartbeatManager:
    def __init__(
        self,
        registry: OrganRegistry,
        dispatcher: EventDispatcher,
        logger: LoggingManager,
        missed_threshold: int = 3,
    ) -> None:
        self._registry = registry
        self._dispatcher = dispatcher
        self._logger = logger
        self._threshold = missed_threshold
        self._ping_impl: Callable[[str], Awaitable[bool]] = self._default_ping

    async def _default_ping(self, organ_name: str) -> bool:
        return True

    def set_ping_implementation(self, fn: Callable[[str], Awaitable[bool]]) -> None:
        self._ping_impl = fn

    async def cycle(self) -> None:
        for name, record in self._registry.all().items():
            ok = await self._ping_impl(name)
            if ok:
                record.missed_heartbeats = 0
                record.status = HealthStatus.HEALTHY
            else:
                record.missed_heartbeats += 1
                if record.missed_heartbeats >= self._threshold:
                    record.status = HealthStatus.CRITICAL
                    self._logger.log("error", "organ_failed", organ=name)
                    self._dispatcher.emit("OrganFailed", {"organ": name})
                else:
                    record.status = HealthStatus.DEGRADED


class RecoveryManager:
    def __init__(
        self,
        registry: OrganRegistry,
        dispatcher: EventDispatcher,
        logger: LoggingManager,
        max_attempts: int = 3,
    ) -> None:
        self._registry = registry
        self._dispatcher = dispatcher
        self._logger = logger
        self._max_attempts = max_attempts
        self._restart_impl: Callable[[str], Awaitable[bool]] = self._default_restart
        dispatcher.subscribe("OrganFailed", self._on_failed)

    async def _default_restart(self, organ_name: str) -> bool:
        return True

    def set_restart_implementation(self, fn: Callable[[str], Awaitable[bool]]) -> None:
        self._restart_impl = fn

    def _on_failed(self, payload: dict) -> None:
        asyncio.ensure_future(self.recover(payload["organ"]))

    async def recover(self, organ_name: str) -> bool:
        record = self._registry.get(organ_name)
        if record is None:
            return False
        if record.restart_attempts >= self._max_attempts:
            self._logger.log("critical", "recovery_exhausted", organ=organ_name)
            self._dispatcher.emit("EscalateSafeMode", {"organ": organ_name})
            return False
        record.restart_attempts += 1
        ok = await self._restart_impl(organ_name)
        if ok:
            record.status = HealthStatus.HEALTHY
            record.missed_heartbeats = 0
            self._logger.log("info", "organ_recovered", organ=organ_name)
        return ok


# --------------------------------------------------------------------------
# Global Scheduler
# --------------------------------------------------------------------------


@dataclass(order=True)
class ScheduledTask:
    priority: int
    task_id: str = field(compare=False)
    payload: dict = field(compare=False)
    submitted_at: float = field(default_factory=time.time, compare=False)


class GlobalScheduler:
    def __init__(self, logger: LoggingManager) -> None:
        self._queue: asyncio.PriorityQueue[ScheduledTask] = asyncio.PriorityQueue()
        self._logger = logger

    async def submit(self, payload: dict, priority: int = 5) -> str:
        task_id = uuid.uuid4().hex
        await self._queue.put(ScheduledTask(priority=priority, task_id=task_id, payload=payload))
        self._logger.log("info", "task_submitted", task_id=task_id, priority=priority)
        return task_id

    async def next_task(self) -> ScheduledTask:
        return await self._queue.get()

    def qsize(self) -> int:
        return self._queue.qsize()


# --------------------------------------------------------------------------
# Security Manager
# --------------------------------------------------------------------------


class SecurityManager:
    """Enforces sandbox/authorization boundaries. No AI logic here."""

    def __init__(self) -> None:
        self._authorized_organs: set[str] = set()

    def authorize(self, organ_name: str) -> None:
        self._authorized_organs.add(organ_name)

    def revoke(self, organ_name: str) -> None:
        self._authorized_organs.discard(organ_name)

    def is_authorized(self, organ_name: str) -> bool:
        return organ_name in self._authorized_organs

    def verify_socket_message(self, message: SocketMessage) -> bool:
        return self.is_authorized(message.sender)


# --------------------------------------------------------------------------
# Boot / Shutdown Managers
# --------------------------------------------------------------------------


class BootManager:
    def __init__(self, pipelines: PipelineBus, logger: LoggingManager) -> None:
        self._pipelines = pipelines
        self._logger = logger

    async def boot(self, context: dict) -> dict:
        self._logger.log("info", "boot_started")
        result = await self._pipelines.run("boot", context)
        self._logger.log("info", "boot_completed")
        return result


class ShutdownManager:
    def __init__(self, pipelines: PipelineBus, logger: LoggingManager) -> None:
        self._pipelines = pipelines
        self._logger = logger

    async def shutdown(self, reason: str, context: Optional[dict] = None) -> dict:
        self._logger.log("info", "shutdown_started", reason=reason)
        ctx = context or {}
        ctx["reason"] = reason
        result = await self._pipelines.run("shutdown", ctx)
        self._logger.log("info", "shutdown_completed")
        return result


# --------------------------------------------------------------------------
# Kernel Core
# --------------------------------------------------------------------------


class KernelCore:
    """Primary execution authority. Composition root for all kernel modules."""

    def __init__(self, resource_quota: Optional[ResourceQuota] = None) -> None:
        self.logger = LoggingManager()
        self.state = StateManager(self.logger)
        self.dependencies = DependencyManager()
        self.resources = ResourceCoordinator(resource_quota or ResourceQuota(), self.logger)
        self.organs = OrganRegistry(self.logger)
        self.services = ServiceRegistry()
        self.runtimes = RuntimeRegistry()
        self.sockets = SocketBus()
        self.events = EventDispatcher(self.logger)
        self.pipelines = PipelineBus()
        self.scheduler = GlobalScheduler(self.logger)
        self.security = SecurityManager()
        self.heartbeat = HeartbeatManager(self.organs, self.events, self.logger)
        self.recovery = RecoveryManager(self.organs, self.events, self.logger)
        self.events.subscribe("EscalateSafeMode", self._on_escalate_safe_mode)
        self._register_default_pipelines()
        self._boot_mgr = BootManager(self.pipelines, self.logger)
        self._shutdown_mgr = ShutdownManager(self.pipelines, self.logger)

    def _register_default_pipelines(self) -> None:
        async def validate_config(ctx: dict) -> dict:
            ctx["config_validated"] = True
            return ctx

        async def resolve_dependencies(ctx: dict) -> dict:
            ctx["startup_order"] = self.dependencies.resolve_order()
            return ctx

        async def init_registries(ctx: dict) -> dict:
            ctx["registries_ready"] = True
            return ctx

        async def transition_running(ctx: dict) -> dict:
            if self.state.state == SystemState.STARTING:
                self.state.transition(SystemState.RUNNING)
            return ctx

        self.pipelines.define("boot", [validate_config, resolve_dependencies, init_registries, transition_running])

        async def flush_state(ctx: dict) -> dict:
            ctx["flushed"] = True
            return ctx

        async def teardown_organs(ctx: dict) -> dict:
            for name in list(self.organs.all()):
                self.organs.unregister(name)
                self.resources.release(name)
            return ctx

        async def finalize_shutdown(ctx: dict) -> dict:
            if self.state.state == SystemState.STOPPING:
                self.state.transition(SystemState.SHUTDOWN)
            return ctx

        self.pipelines.define("shutdown", [flush_state, teardown_organs, finalize_shutdown])

    def _on_escalate_safe_mode(self, payload: dict) -> None:
        try:
            self.state.transition(SystemState.SAFE_MODE)
        except InvalidStateTransition:
            pass

    # -- Public IKernelCore-equivalent API --------------------------------

    def register_organ(self, manifest: OrganManifest) -> bool:
        try:
            self.organs.register(manifest)
            self.dependencies.add(manifest.organ_name, manifest.dependencies)
            self.security.authorize(manifest.organ_name)
            return True
        except DuplicateRegistrationError:
            self.logger.log("warning", "duplicate_organ", organ=manifest.organ_name)
            return False

    def unregister_organ(self, organ_name: str) -> bool:
        self.organs.unregister(organ_name)
        self.dependencies.remove(organ_name)
        self.security.revoke(organ_name)
        self.resources.release(organ_name)
        return True

    async def boot(self) -> None:
        self.state.transition(SystemState.STARTING)
        await self._boot_mgr.boot({})

    async def shutdown(self, reason: str = "requested") -> None:
        self.state.transition(SystemState.STOPPING)
        await self._shutdown_mgr.shutdown(reason)

    async def run_heartbeat_cycle(self) -> None:
        await self.heartbeat.cycle()

    def get_state(self) -> SystemState:
        return self.state.state


def create_kernel(resource_quota: Optional[ResourceQuota] = None) -> KernelCore:
    """Factory entry point for the Kernel organ."""
    return KernelCore(resource_quota=resource_quota)
