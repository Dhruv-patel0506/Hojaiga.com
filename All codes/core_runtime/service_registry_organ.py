"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: service_registry_organ.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [service_registry_organ.py]
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
Dependencies: enum, typing, __future__, collections, json...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: service_registry_organ.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Hojaiga Automation OS - Service Registry Organ
Authoritative runtime management and discovery engine for every long-running
executable service inside Hojaiga AOS.

Authority Order: Constitution -> Law Book -> Policy Manual ->
Master Architecture Blueprint -> Organ Specification ->
Service Registry Architecture Specification (SPEC-AOS-SERVREG-001)

Single-file consolidated implementation. No external organ imports.
Communication with other organs occurs exclusively through the documented
Socket classes defined in this module (RegistrationSocket, DiscoverySocket,
LifecycleSocket, HealthSocket, HeartbeatSocket, DependencySocket,
MonitoringSocket, RecoverySocket, MetricsSocket).
"""


import json
import re
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

__version__ = "1.0.0"


# ═══════════════════════════════════════════════════════════════════════
# SECTION 1 — ENUMERATIONS
# ═══════════════════════════════════════════════════════════════════════

class ServiceState(Enum):
    CREATED = "CREATED"
    REGISTERED = "REGISTERED"
    VALIDATED = "VALIDATED"
    INITIALIZING = "INITIALIZING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    IDLE = "IDLE"
    BUSY = "BUSY"
    PAUSED = "PAUSED"
    WAITING = "WAITING"
    UPDATING = "UPDATING"
    RESTARTING = "RESTARTING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"
    MAINTENANCE = "MAINTENANCE"
    DISABLED = "DISABLED"
    ARCHIVED = "ARCHIVED"
    REMOVED = "REMOVED"


class HealthStatus(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    OFFLINE = "OFFLINE"


class PermissionLevel(Enum):
    LEVEL_0_PUBLIC = 0
    LEVEL_1_INTERNAL = 1
    LEVEL_2_RESTRICTED = 2
    LEVEL_3_ADMIN = 3
    LEVEL_4_KERNEL = 4


class FailureType(Enum):
    CRASH = "CRASH"
    HANG = "HANG"
    RESOURCE_EXHAUSTION = "RESOURCE_EXHAUSTION"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"


class RestartPolicy(Enum):
    ALWAYS = "ALWAYS"
    ON_FAILURE = "ON_FAILURE"
    NEVER = "NEVER"


class ServiceCategory(Enum):
    KERNEL_SERVICES = "KERNEL_SERVICES"
    SHARED_SERVICES = "SHARED_SERVICES"
    BRAIN_SERVICES = "BRAIN_SERVICES"
    MEMORY_SERVICES = "MEMORY_SERVICES"
    KNOWLEDGE_SERVICES = "KNOWLEDGE_SERVICES"
    AUTOMATION_SERVICES = "AUTOMATION_SERVICES"
    CONTROLLER_SERVICES = "CONTROLLER_SERVICES"
    LEARNING_SERVICES = "LEARNING_SERVICES"
    INFRASTRUCTURE_SERVICES = "INFRASTRUCTURE_SERVICES"
    SECURITY_SERVICES = "SECURITY_SERVICES"
    INTEGRATION_SERVICES = "INTEGRATION_SERVICES"
    INTERFACE_SERVICES = "INTERFACE_SERVICES"
    RUNTIME_SERVICES = "RUNTIME_SERVICES"
    CONNECTOR_SERVICES = "CONNECTOR_SERVICES"
    PLUGIN_SERVICES = "PLUGIN_SERVICES"
    BACKGROUND_WORKERS = "BACKGROUND_WORKERS"
    MONITORING_SERVICES = "MONITORING_SERVICES"
    FUTURE_SERVICES = "FUTURE_SERVICES"


# Legal state transition graph per Section 6 (Official Service State Machine)
_LEGAL_TRANSITIONS: Dict[ServiceState, set] = {
    ServiceState.CREATED: {ServiceState.REGISTERED, ServiceState.DISABLED},
    ServiceState.REGISTERED: {ServiceState.VALIDATED, ServiceState.FAILED},
    ServiceState.VALIDATED: {ServiceState.INITIALIZING, ServiceState.FAILED},
    ServiceState.INITIALIZING: {ServiceState.STARTING, ServiceState.FAILED},
    ServiceState.STARTING: {ServiceState.RUNNING, ServiceState.FAILED},
    ServiceState.RUNNING: {
        ServiceState.PAUSED, ServiceState.WAITING, ServiceState.BUSY,
        ServiceState.MAINTENANCE, ServiceState.UPDATING, ServiceState.FAILED,
        ServiceState.STOPPING, ServiceState.IDLE,
    },
    ServiceState.IDLE: {ServiceState.RUNNING, ServiceState.BUSY, ServiceState.STOPPING, ServiceState.FAILED},
    ServiceState.BUSY: {ServiceState.RUNNING, ServiceState.IDLE, ServiceState.FAILED, ServiceState.STOPPING},
    ServiceState.PAUSED: {ServiceState.RUNNING, ServiceState.STOPPING},
    ServiceState.WAITING: {ServiceState.RUNNING, ServiceState.STOPPING},
    ServiceState.MAINTENANCE: {ServiceState.RUNNING, ServiceState.STOPPING},
    ServiceState.UPDATING: {ServiceState.RUNNING, ServiceState.FAILED},
    ServiceState.FAILED: {ServiceState.RECOVERING, ServiceState.DISABLED},
    ServiceState.RECOVERING: {ServiceState.STARTING, ServiceState.DISABLED, ServiceState.RUNNING},
    ServiceState.RESTARTING: {ServiceState.STARTING, ServiceState.FAILED},
    ServiceState.STOPPING: {ServiceState.STOPPED},
    ServiceState.STOPPED: {ServiceState.ARCHIVED, ServiceState.STARTING},
    ServiceState.ARCHIVED: {ServiceState.REMOVED},
    ServiceState.DISABLED: {ServiceState.REGISTERED, ServiceState.REMOVED},
    ServiceState.REMOVED: set(),
}


# ═══════════════════════════════════════════════════════════════════════
# SECTION 2 — EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════

class ServiceRegistryError(Exception):
    """Base exception for all Service Registry organ errors."""


class RegistrationValidationError(ServiceRegistryError):
    """Raised when a service manifest fails structural or schema validation."""


class ServiceNotFoundException(ServiceRegistryError):
    """Raised when a discovery query yields no matching service."""


class PermissionDeniedException(ServiceRegistryError):
    """Raised when an invoker lacks sufficient permission tier."""


class CircularDependencyError(ServiceRegistryError):
    """Raised when the dependency DAG contains a cycle."""


class IllegalStateTransitionError(ServiceRegistryError):
    """Raised when a requested state transition violates the lifecycle machine."""


class VersionIncompatibleError(ServiceRegistryError):
    """Raised when a SemVer constraint cannot be satisfied."""


# ═══════════════════════════════════════════════════════════════════════
# SECTION 3 — DATA CONTRACTS (DTOs)
# ═══════════════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid7() -> str:
    # UUIDv7-style time-ordered identifier (fallback: uuid4 with time prefix)
    ts_ms = int(time.time() * 1000).to_bytes(6, "big")
    rand = uuid.uuid4().bytes[6:]
    raw = bytearray(ts_ms + rand)
    raw[6] = (raw[6] & 0x0F) | 0x70
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(raw)))


@dataclass
class ServiceManifestDTO:
    service_name: str
    description: str
    category: str
    version: str
    owner: str
    dependencies: List[Dict[str, str]] = field(default_factory=list)
    capabilities_ref: List[str] = field(default_factory=list)
    priority: int = 500
    permission_level: str = PermissionLevel.LEVEL_1_INTERNAL.name
    supported_interfaces: List[str] = field(default_factory=list)
    runtime: str = "PYTHON_3_12"
    config_ref: str = ""
    service_id: str = field(default_factory=_uuid7)


@dataclass
class ServiceRecord:
    service_id: str
    service_name: str
    description: str
    category: str
    version: str
    owner: str
    status: ServiceState = ServiceState.CREATED
    dependencies: List[Dict[str, str]] = field(default_factory=list)
    capabilities_ref: List[str] = field(default_factory=list)
    config_ref: str = ""
    health_status: HealthStatus = HealthStatus.OFFLINE
    priority: int = 500
    startup_order: int = -1
    shutdown_order: int = -1
    process_id: Optional[int] = None
    memory_usage_mb: float = 0.0
    cpu_usage_pct: float = 0.0
    gpu_usage_pct: float = 0.0
    runtime: str = "PYTHON_3_12"
    registration_date: str = field(default_factory=_now_iso)
    last_updated: str = field(default_factory=_now_iso)
    last_health_check: str = field(default_factory=_now_iso)
    last_restart: Optional[str] = None
    supported_interfaces: List[str] = field(default_factory=list)
    permission_level: str = PermissionLevel.LEVEL_1_INTERNAL.name
    restart_policy: str = RestartPolicy.ON_FAILURE.name
    restart_attempts: int = 0
    restart_window_start: float = field(default_factory=time.time)
    missed_heartbeats: int = 0
    auth_secret: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["health_status"] = self.health_status.value
        return d


@dataclass
class ServiceInvocationEndpoint:
    service_id: str
    service_name: str
    endpoint_uri: str
    protocol: str
    auth_token: str


@dataclass
class DiscoveryQueryDTO:
    service_name: Optional[str] = None
    category: Optional[str] = None
    service_id: Optional[str] = None
    min_version: Optional[str] = None
    require_healthy: bool = True
    caller_scope: str = PermissionLevel.LEVEL_1_INTERNAL.name


@dataclass
class HeartbeatFrameDTO:
    service_id: str
    tick: int
    timestamp: str = field(default_factory=_now_iso)


@dataclass
class HealthProbeDTO:
    service_id: str
    cpu_usage_pct: float
    memory_usage_mb: float
    gpu_usage_pct: float = 0.0
    latency_ms: float = 0.0
    timestamp: str = field(default_factory=_now_iso)


@dataclass
class FailureAlertDTO:
    service_id: str
    failure_type: FailureType
    reason: str
    timestamp: str = field(default_factory=_now_iso)


@dataclass
class MetricsDTO:
    counters: Dict[str, int] = field(default_factory=dict)
    gauges: Dict[str, float] = field(default_factory=dict)
    histograms: Dict[str, List[float]] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 4 — PUBLIC INTERFACES (Section 16.2 Core Interface Definitions)
# ═══════════════════════════════════════════════════════════════════════

class IServiceRegistry(ABC):
    @abstractmethod
    def register_service(self, manifest: ServiceManifestDTO) -> bool: ...

    @abstractmethod
    def discover_service(self, query_params: Dict[str, Any], caller_scope: str) -> ServiceInvocationEndpoint: ...

    @abstractmethod
    def deregister_service(self, service_id: str, auth_key: str) -> bool: ...


class ILifecycleManager(ABC):
    @abstractmethod
    def start_service(self, service_id: str) -> bool: ...

    @abstractmethod
    def stop_service(self, service_id: str, graceful: bool) -> bool: ...

    @abstractmethod
    def restart_service(self, service_id: str) -> bool: ...


class IDependencyManager(ABC):
    @abstractmethod
    def validate_graph(self) -> bool: ...

    @abstractmethod
    def get_startup_sequence(self) -> List[str]: ...


class IProcessDriver(ABC):
    """Pluggable execution driver. Default: in-memory simulated process."""

    @abstractmethod
    def spawn(self, record: ServiceRecord) -> int: ...

    @abstractmethod
    def terminate(self, pid: int, force: bool = False) -> bool: ...

    @abstractmethod
    def is_alive(self, pid: int) -> bool: ...


# ═══════════════════════════════════════════════════════════════════════
# SECTION 5 — UTILITIES (src/utils)
# ═══════════════════════════════════════════════════════════════════════

class TarjanDAG:
    """Directed graph with Tarjan's SCC cycle detection and Kahn topological sort."""

    def __init__(self) -> None:
        self._edges: Dict[str, set] = defaultdict(set)
        self._nodes: set = set()
        self._lock = threading.RLock()

    def add_node(self, node: str) -> None:
        with self._lock:
            self._nodes.add(node)

    def remove_node(self, node: str) -> None:
        with self._lock:
            self._nodes.discard(node)
            self._edges.pop(node, None)
            for deps in self._edges.values():
                deps.discard(node)

    def add_edge(self, src: str, dst: str) -> None:
        with self._lock:
            self._nodes.add(src)
            self._nodes.add(dst)
            self._edges[src].add(dst)

    def detect_cycles(self) -> List[List[str]]:
        """Tarjan's strongly connected components; SCCs of size > 1 or
        self-loops indicate a cycle."""
        with self._lock:
            index_counter = [0]
            stack: List[str] = []
            lowlink: Dict[str, int] = {}
            index: Dict[str, int] = {}
            on_stack: Dict[str, bool] = {}
            result: List[List[str]] = []

            def strongconnect(node: str) -> None:
                index[node] = index_counter[0]
                lowlink[node] = index_counter[0]
                index_counter[0] += 1
                stack.append(node)
                on_stack[node] = True

                for successor in self._edges.get(node, ()):
                    if successor not in index:
                        strongconnect(successor)
                        lowlink[node] = min(lowlink[node], lowlink[successor])
                    elif on_stack.get(successor):
                        lowlink[node] = min(lowlink[node], index[successor])

                if lowlink[node] == index[node]:
                    component = []
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        component.append(w)
                        if w == node:
                            break
                    if len(component) > 1 or node in self._edges.get(node, ()):
                        result.append(component)
            for n in list(self._nodes):
                if n not in index:
                    strongconnect(n)
            return result

    def topological_order(self) -> List[str]:
        """Kahn's algorithm. Raises CircularDependencyError on cycle."""
        with self._lock:
            in_degree = {n: 0 for n in self._nodes}
            for src, deps in self._edges.items():
                for d in deps:
                    in_degree[d] = in_degree.get(d, 0) + 1
            queue = deque(sorted(n for n, deg in in_degree.items() if deg == 0))
            order: List[str] = []
            local_in_degree = dict(in_degree)
            while queue:
                node = queue.popleft()
                order.append(node)
                for dep in sorted(self._edges.get(node, ())):
                    local_in_degree[dep] -= 1
                    if local_in_degree[dep] == 0:
                        queue.append(dep)
            if len(order) != len(self._nodes):
                raise CircularDependencyError(
                    f"Dependency graph contains a cycle involving: "
                    f"{set(self._nodes) - set(order)}"
                )
            return order


_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z\-.]+))?(?:\+(?P<build>[0-9A-Za-z\-.]+))?$"
)

_RANGE_RE = re.compile(r"^(?P<op>>=|<=|==|>|<|\^|~)?\s*(?P<version>\d+\.\d+\.\d+.*)$")


class SemVerParser:
    """SemVer 2.0.0 parsing and range comparison utility."""

    @staticmethod
    def parse(version: str) -> Tuple[int, int, int, str, str]:
        m = _SEMVER_RE.match(version.strip())
        if not m:
            raise VersionIncompatibleError(f"Malformed SemVer string: {version!r}")
        gd = m.groupdict()
        return (
            int(gd["major"]), int(gd["minor"]), int(gd["patch"]),
            gd["prerelease"] or "", gd["build"] or "",
        )

    @classmethod
    def compare(cls, a: str, b: str) -> int:
        ta, tb = cls.parse(a)[:3], cls.parse(b)[:3]
        return (ta > tb) - (ta < tb)

    @classmethod
    def satisfies(cls, version: str, constraint: str) -> bool:
        """Evaluate a single constraint expression, e.g. '>=2.1.0', '^1.2.0'."""
        constraint = constraint.strip()
        if not constraint:
            return True
        m = _RANGE_RE.match(constraint)
        if not m:
            raise VersionIncompatibleError(f"Malformed version range: {constraint!r}")
        op = m.group("op") or "=="
        target = m.group("version")
        cmp = cls.compare(version, target)
        if op == "==":
            return cmp == 0
        if op == ">=":
            return cmp >= 0
        if op == "<=":
            return cmp <= 0
        if op == ">":
            return cmp > 0
        if op == "<":
            return cmp < 0
        if op == "^":
            tmajor = cls.parse(target)[0]
            vmajor = cls.parse(version)[0]
            return vmajor == tmajor and cmp >= 0
        if op == "~":
            tmajor, tminor = cls.parse(target)[:2]
            vmajor, vminor = cls.parse(version)[:2]
            return vmajor == tmajor and vminor == tminor and cmp >= 0
        raise VersionIncompatibleError(f"Unsupported operator: {op}")


class InProcessDriver(IProcessDriver):
    """Default lightweight process driver: simulates a service process using
    a daemon thread executing a supplied target callable (or a no-op idle
    loop). Suitable for services that are themselves in-process Python
    runnables; external OS processes can be modeled via a custom driver
    implementing IProcessDriver."""

    def __init__(self) -> None:
        self._threads: Dict[int, threading.Event] = {}
        self._pid_counter = 1000
        self._lock = threading.Lock()

    def spawn(self, record: ServiceRecord) -> int:
        with self._lock:
            self._pid_counter += 1
            pid = self._pid_counter
        stop_event = threading.Event()
        self._threads[pid] = stop_event

        def _run() -> None:
            while not stop_event.is_set():
                time.sleep(0.05)

        t = threading.Thread(target=_run, name=f"svc-{record.service_name}-{pid}", daemon=True)
        t.start()
        return pid

    def terminate(self, pid: int, force: bool = False) -> bool:
        ev = self._threads.pop(pid, None)
        if ev is None:
            return False
        ev.set()
        return True

    def is_alive(self, pid: int) -> bool:
        return pid in self._threads


# ═══════════════════════════════════════════════════════════════════════
# SECTION 6 — SOCKETS (src/sockets) — Section 10 Socket Definitions
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SocketSpec:
    name: str
    version: str
    direction: str
    allowed_data: Tuple[type, ...]
    auth_tier: PermissionLevel
    timeout_ms: int
    retry_attempts: int


class BaseSocket:
    """Base class enforcing socket contract: Name, Version, Direction,
    Allowed Data, Validation, Security, Failure Behaviour, Retry Behaviour."""

    spec: SocketSpec

    def __init__(self, handler: Callable[[Any, PermissionLevel], Any]):
        self._handler = handler

    def _validate(self, payload: Any) -> None:
        if not isinstance(payload, self.spec.allowed_data):
            raise RegistrationValidationError(
                f"{self.spec.name}: payload type {type(payload)} not in allowed "
                f"data contract {self.spec.allowed_data}"
            )

    def _check_auth(self, caller_scope: PermissionLevel) -> None:
        if caller_scope.value < self.spec.auth_tier.value:
            raise PermissionDeniedException(
                f"{self.spec.name}: caller scope {caller_scope.name} below required "
                f"tier {self.spec.auth_tier.name}"
            )

    def send(self, payload: Any, caller_scope: PermissionLevel = PermissionLevel.LEVEL_1_INTERNAL) -> Any:
        self._validate(payload)
        self._check_auth(caller_scope)
        last_error: Optional[Exception] = None
        attempts = max(1, self.spec.retry_attempts)
        for _ in range(attempts):
            try:
                return self._handler(payload, caller_scope)
            except (ServiceNotFoundException, PermissionDeniedException,
                    RegistrationValidationError, CircularDependencyError,
                    IllegalStateTransitionError, VersionIncompatibleError) as exc:
                raise exc
            except Exception as exc:  # noqa: BLE001 - failure behaviour per spec
                last_error = exc
        raise ServiceRegistryError(f"{self.spec.name}: exhausted retries") from last_error


class RegistrationSocket(BaseSocket):
    spec = SocketSpec("RegistrationSocket", "v1.0.0", "Bidirectional",
                       (ServiceManifestDTO, tuple), PermissionLevel.LEVEL_3_ADMIN, 2000, 3)


class DiscoverySocket(BaseSocket):
    spec = SocketSpec("DiscoverySocket", "v1.0.0", "Inbound",
                       (DiscoveryQueryDTO,), PermissionLevel.LEVEL_0_PUBLIC, 300, 2)


class LifecycleSocket(BaseSocket):
    spec = SocketSpec("LifecycleSocket", "v1.0.0", "Outbound",
                       (tuple,), PermissionLevel.LEVEL_4_KERNEL, 5000, 3)


class HealthSocket(BaseSocket):
    spec = SocketSpec("HealthSocket", "v1.0.0", "Inbound",
                       (HealthProbeDTO,), PermissionLevel.LEVEL_1_INTERNAL, 200, 1)


class HeartbeatSocket(BaseSocket):
    spec = SocketSpec("HeartbeatSocket", "v1.0.0", "Inbound",
                       (HeartbeatFrameDTO,), PermissionLevel.LEVEL_1_INTERNAL, 50, 1)


class DependencySocket(BaseSocket):
    spec = SocketSpec("DependencySocket", "v1.0.0", "Bidirectional",
                       (tuple,), PermissionLevel.LEVEL_1_INTERNAL, 1000, 2)


class MonitoringSocket(BaseSocket):
    spec = SocketSpec("MonitoringSocket", "v1.0.0", "Outbound",
                       (tuple,), PermissionLevel.LEVEL_1_INTERNAL, 1000, 1)


class RecoverySocket(BaseSocket):
    spec = SocketSpec("RecoverySocket", "v1.0.0", "Bidirectional",
                       (FailureAlertDTO, tuple), PermissionLevel.LEVEL_4_KERNEL, 3000, 5)


class MetricsSocket(BaseSocket):
    spec = SocketSpec("MetricsSocket", "v1.0.0", "Outbound",
                       (tuple,), PermissionLevel.LEVEL_0_PUBLIC, 500, 1)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 7 — CORE STORAGE
# ═══════════════════════════════════════════════════════════════════════

class ServiceCache:
    """L1 in-memory TTL + LRU cache for resolved discovery endpoints."""

    def __init__(self, capacity: int = 5000, ttl_seconds: int = 120) -> None:
        self._capacity = capacity
        self._ttl = ttl_seconds
        self._store: "OrderedDict[str, Tuple[float, ServiceInvocationEndpoint]]" = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[ServiceInvocationEndpoint]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, endpoint = entry
            if time.time() - ts > self._ttl:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return endpoint

    def put(self, key: str, endpoint: ServiceInvocationEndpoint) -> None:
        with self._lock:
            self._store[key] = (time.time(), endpoint)
            self._store.move_to_end(key)
            while len(self._store) > self._capacity:
                self._store.popitem(last=False)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def invalidate_service(self, service_id: str, service_name: str) -> None:
        with self._lock:
            for k in [k for k in self._store if service_id in k or service_name in k]:
                del self._store[k]

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class ServiceDatabase:
    """In-memory indexed state store with an append-only Write-Ahead Log."""

    def __init__(self) -> None:
        self._by_id: Dict[str, ServiceRecord] = {}
        self._by_name: Dict[str, str] = {}
        self._by_pid: Dict[int, str] = {}
        self._wal: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    def _append_wal(self, op: str, record: ServiceRecord) -> None:
        self._wal.append({
            "op": op, "timestamp": _now_iso(),
            "service_id": record.service_id, "status": record.status.value,
        })

    def insert(self, record: ServiceRecord) -> bool:
        with self._lock:
            if record.service_name in self._by_name:
                return False
            self._by_id[record.service_id] = record
            self._by_name[record.service_name] = record.service_id
            self._append_wal("INSERT", record)
            return True

    def update(self, record: ServiceRecord) -> None:
        with self._lock:
            record.last_updated = _now_iso()
            self._by_id[record.service_id] = record
            if record.process_id is not None:
                self._by_pid[record.process_id] = record.service_id
            self._append_wal("UPDATE", record)

    def remove(self, service_id: str) -> Optional[ServiceRecord]:
        with self._lock:
            record = self._by_id.pop(service_id, None)
            if record is None:
                return None
            self._by_name.pop(record.service_name, None)
            if record.process_id is not None:
                self._by_pid.pop(record.process_id, None)
            self._append_wal("REMOVE", record)
            return record

    def get(self, service_id: str) -> Optional[ServiceRecord]:
        with self._lock:
            return self._by_id.get(service_id)

    def get_by_name(self, name: str) -> Optional[ServiceRecord]:
        with self._lock:
            sid = self._by_name.get(name)
            return self._by_id.get(sid) if sid else None

    def get_by_pid(self, pid: int) -> Optional[ServiceRecord]:
        with self._lock:
            sid = self._by_pid.get(pid)
            return self._by_id.get(sid) if sid else None

    def all_records(self) -> List[ServiceRecord]:
        with self._lock:
            return list(self._by_id.values())

    def query(self, category: Optional[str] = None,
              status: Optional[ServiceState] = None) -> List[ServiceRecord]:
        with self._lock:
            results = list(self._by_id.values())
        if category:
            results = [r for r in results if r.category == category]
        if status:
            results = [r for r in results if r.status == status]
        return results

    def wal_snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._wal)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 8 — SUPPORTING MANAGERS
# ═══════════════════════════════════════════════════════════════════════

class MetadataManager:
    _TAG_RE = re.compile(r"^[A-Za-z0-9_\-.: ]{0,256}$")

    def sanitize(self, manifest: ServiceManifestDTO) -> ServiceManifestDTO:
        if not self._TAG_RE.match(manifest.description or ""):
            manifest.description = re.sub(r"[^A-Za-z0-9_\-.: ]", "", manifest.description or "")[:256]
        return manifest


class PermissionManager:
    def check(self, caller_scope: str, required: PermissionLevel) -> bool:
        try:
            scope = PermissionLevel[caller_scope]
        except KeyError:
            return False
        return scope.value >= required.value

    def enforce(self, caller_scope: str, required: PermissionLevel) -> None:
        if not self.check(caller_scope, required):
            raise PermissionDeniedException(
                f"Caller scope {caller_scope!r} insufficient; requires {required.name}"
            )


class VersionManager:
    def validate_syntax(self, version: str) -> bool:
        try:
            SemVerParser.parse(version)
            return True
        except VersionIncompatibleError:
            return False

    def satisfies(self, version: str, constraint: str) -> bool:
        return SemVerParser.satisfies(version, constraint)


class CompatibilityValidator:
    def __init__(self, version_manager: VersionManager) -> None:
        self._version_manager = version_manager

    def validate(self, manifest: ServiceManifestDTO, db: ServiceDatabase) -> None:
        if not self._version_manager.validate_syntax(manifest.version):
            raise VersionIncompatibleError(f"Invalid SemVer: {manifest.version}")
        for dep in manifest.dependencies:
            dep_name = dep.get("service_name")
            constraint = dep.get("version_range", "")
            if dep.get("optional") == "true":
                continue
            existing = db.get_by_name(dep_name) if dep_name else None
            if existing is not None and constraint:
                if not self._version_manager.satisfies(existing.version, constraint):
                    raise VersionIncompatibleError(
                        f"Dependency {dep_name} version {existing.version} does not satisfy {constraint}"
                    )


class ConfigurationInterface:
    """Serves operational configuration with hot-reload and factory fallback."""

    _DEFAULTS: Dict[str, Any] = {
        "core": {
            "enable_cache": True, "cache_capacity": 5000, "cache_ttl_seconds": 120,
            "max_registered_services": 1000,
        },
        "health_monitoring": {
            "heartbeat_interval_ms": 3000, "heartbeat_timeout_ms": 9000,
            "health_probe_interval_ms": 10000, "max_cpu_threshold_pct": 90.0,
            "max_memory_threshold_mb": 4096.0,
        },
        "recovery_policies": {
            "global_max_restart_attempts": 3, "restart_window_seconds": 300,
            "base_backoff_delay_ms": 1000, "max_backoff_delay_ms": 30000,
            "enable_safe_mode_fallback": True,
        },
        "security": {
            "enforce_binary_signatures": True, "default_isolation_level": "RESTRICTED",
            "audit_all_lifecycle_actions": True,
        },
    }

    def __init__(self, overrides: Optional[Dict[str, Any]] = None) -> None:
        self._config = json.loads(json.dumps(self._DEFAULTS))
        if overrides:
            self.reload(overrides)

    def reload(self, overrides: Dict[str, Any]) -> None:
        for section, values in overrides.items():
            if section in self._config and isinstance(values, dict):
                self._config[section].update(values)
            else:
                self._config[section] = values

    def get(self, path: str, default: Any = None) -> Any:
        node: Any = self._config
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


class AuditManager:
    def __init__(self) -> None:
        self._records: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def log(self, event_type: str, module: str, payload: Dict[str, Any],
            log_level: str = "INFO", security_scope: str = "LEVEL_1_INTERNAL") -> None:
        record = {
            "timestamp": _now_iso(),
            "trace_id": f"tr-{uuid.uuid4()}",
            "organ": "ServiceRegistry",
            "module": module,
            "event_type": event_type,
            "log_level": log_level,
            "payload": payload,
            "security_context": {"authenticated_scope": security_scope},
        }
        with self._lock:
            self._records.append(record)

    def records(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._records)


class HistoryManager:
    def __init__(self, retention: int = 5000) -> None:
        self._history: deque = deque(maxlen=retention)
        self._lock = threading.Lock()

    def archive(self, record: ServiceRecord, reason: str) -> None:
        with self._lock:
            self._history.append({
                "timestamp": _now_iso(), "service_id": record.service_id,
                "service_name": record.service_name, "final_status": record.status.value,
                "reason": reason,
            })

    def query(self, service_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._history)
        if service_id:
            items = [i for i in items if i["service_id"] == service_id]
        return items


class MetricsManager:
    def __init__(self) -> None:
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._histograms[name].append(value)
            if len(self._histograms[name]) > 1000:
                self._histograms[name] = self._histograms[name][-1000:]

    def snapshot(self) -> MetricsDTO:
        with self._lock:
            return MetricsDTO(
                counters=dict(self._counters), gauges=dict(self._gauges),
                histograms={k: list(v) for k, v in self._histograms.items()},
            )


class MonitoringManager:
    def __init__(self, db: ServiceDatabase, metrics: MetricsManager) -> None:
        self._db = db
        self._metrics = metrics

    def aggregate(self) -> Dict[str, Any]:
        records = self._db.all_records()
        total_mem = sum(r.memory_usage_mb for r in records)
        total_cpu = sum(r.cpu_usage_pct for r in records)
        by_health = defaultdict(int)
        for r in records:
            by_health[r.health_status.value] += 1
        self._metrics.set_gauge("registry.total_memory_mb", total_mem)
        self._metrics.set_gauge("registry.total_cpu_pct", total_cpu)
        return {
            "service_count": len(records), "total_memory_mb": total_mem,
            "total_cpu_pct": total_cpu, "by_health": dict(by_health),
        }


# ═══════════════════════════════════════════════════════════════════════
# SECTION 9 — STATE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════

class StateManager:
    def __init__(self, db: ServiceDatabase, audit: AuditManager) -> None:
        self._db = db
        self._audit = audit
        self._subscribers: List[Callable[[ServiceRecord, ServiceState, ServiceState], None]] = []
        self._lock = threading.RLock()

    def subscribe(self, callback: Callable[[ServiceRecord, ServiceState, ServiceState], None]) -> None:
        self._subscribers.append(callback)

    def transition(self, service_id: str, new_state: ServiceState, force: bool = False) -> ServiceRecord:
        with self._lock:
            record = self._db.get(service_id)
            if record is None:
                raise ServiceNotFoundException(f"No service with id {service_id}")
            old_state = record.status
            if not force and new_state not in _LEGAL_TRANSITIONS.get(old_state, set()):
                raise IllegalStateTransitionError(
                    f"Illegal transition {old_state.value} -> {new_state.value} for {service_id}"
                )
            record.status = new_state
            self._db.update(record)
            self._audit.log("STATE_TRANSITION", "StateManager",
                             {"service_id": service_id, "from": old_state.value, "to": new_state.value})
            for cb in self._subscribers:
                cb(record, old_state, new_state)
            return record


# ═══════════════════════════════════════════════════════════════════════
# SECTION 10 — REGISTRATION / DISCOVERY
# ═══════════════════════════════════════════════════════════════════════

class RegistrationManager:
    _NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

    def __init__(self, db: ServiceDatabase, metadata: MetadataManager,
                 compat: CompatibilityValidator, permission: PermissionManager,
                 state_manager: StateManager, audit: AuditManager) -> None:
        self._db = db
        self._metadata = metadata
        self._compat = compat
        self._permission = permission
        self._state_manager = state_manager
        self._audit = audit

    def _validate_schema(self, manifest: ServiceManifestDTO) -> None:
        if not manifest.service_name or not self._NAME_RE.match(manifest.service_name):
            raise RegistrationValidationError(
                f"service_name must be dot-notation (e.g. organ.category.name): "
                f"{manifest.service_name!r}"
            )
        if manifest.category not in {c.value for c in ServiceCategory}:
            raise RegistrationValidationError(f"Unknown category: {manifest.category}")
        if manifest.permission_level not in PermissionLevel.__members__:
            raise RegistrationValidationError(f"Unknown permission_level: {manifest.permission_level}")
        if not (0 <= manifest.priority <= 1000):
            raise RegistrationValidationError("priority must be within 0..1000")

    def register(self, manifest: ServiceManifestDTO, caller_scope: str = "LEVEL_3_ADMIN") -> ServiceRecord:
        self._permission.enforce(caller_scope, PermissionLevel.LEVEL_3_ADMIN)
        self._validate_schema(manifest)
        manifest = self._metadata.sanitize(manifest)
        self._compat.validate(manifest, self._db)

        if self._db.get_by_name(manifest.service_name):
            raise RegistrationValidationError(
                f"service_name collision: {manifest.service_name} already registered"
            )

        record = ServiceRecord(
            service_id=manifest.service_id, service_name=manifest.service_name,
            description=manifest.description, category=manifest.category,
            version=manifest.version, owner=manifest.owner,
            dependencies=manifest.dependencies, capabilities_ref=manifest.capabilities_ref,
            config_ref=manifest.config_ref, priority=manifest.priority,
            runtime=manifest.runtime, supported_interfaces=manifest.supported_interfaces,
            permission_level=manifest.permission_level,
        )
        if not self._db.insert(record):
            raise RegistrationValidationError(f"Failed to persist {manifest.service_name}")
        self._state_manager.transition(record.service_id, ServiceState.REGISTERED, force=True)
        self._audit.log("SERVICE_REGISTERED", "RegistrationManager",
                         {"service_id": record.service_id, "service_name": record.service_name},
                         security_scope=caller_scope)
        return record


class DependencyManager(IDependencyManager):
    def __init__(self, db: ServiceDatabase, compat: CompatibilityValidator) -> None:
        self._db = db
        self._compat = compat
        self._dag = TarjanDAG()
        self._lock = threading.RLock()

    def sync_graph(self) -> None:
        with self._lock:
            self._dag = TarjanDAG()
            for record in self._db.all_records():
                self._dag.add_node(record.service_id)
                for dep in record.dependencies:
                    dep_name = dep.get("service_name")
                    dep_record = self._db.get_by_name(dep_name) if dep_name else None
                    if dep_record:
                        self._dag.add_edge(record.service_id, dep_record.service_id)

    def validate_graph(self) -> bool:
        self.sync_graph()
        cycles = self._dag.detect_cycles()
        if cycles:
            raise CircularDependencyError(f"Circular dependency detected: {cycles}")
        return True

    def get_startup_sequence(self) -> List[str]:
        self.sync_graph()
        order = self._dag.topological_order()
        # dependencies must start before dependents: reverse Kahn source order
        return list(reversed(order))

    def get_shutdown_sequence(self) -> List[str]:
        return list(reversed(self.get_startup_sequence()))

    def dependencies_healthy(self, service_id: str) -> bool:
        record = self._db.get(service_id)
        if record is None:
            return False
        for dep in record.dependencies:
            if dep.get("optional") == "true":
                continue
            dep_record = self._db.get_by_name(dep.get("service_name", ""))
            if dep_record is None or dep_record.status not in (
                ServiceState.RUNNING, ServiceState.IDLE, ServiceState.BUSY,
            ):
                return False
        return True


class DiscoveryManager:
    def __init__(self, db: ServiceDatabase, cache: ServiceCache,
                 permission: PermissionManager, metrics: MetricsManager) -> None:
        self._db = db
        self._cache = cache
        self._permission = permission
        self._metrics = metrics

    def _cache_key(self, query: DiscoveryQueryDTO) -> str:
        return f"{query.service_id}|{query.service_name}|{query.category}|{query.min_version}"

    def discover(self, query: DiscoveryQueryDTO) -> ServiceInvocationEndpoint:
        self._metrics.increment("registry.discovery.requests")
        key = self._cache_key(query)
        cached = self._cache.get(key)
        if cached is not None:
            self._metrics.increment("registry.discovery.cache_hits")
            return cached

        record: Optional[ServiceRecord] = None
        if query.service_id:
            record = self._db.get(query.service_id)
        elif query.service_name:
            record = self._db.get_by_name(query.service_name)
        elif query.category:
            candidates = self._db.query(category=query.category)
            candidates = [c for c in candidates if not query.require_healthy
                          or c.health_status == HealthStatus.HEALTHY]
            if candidates:
                record = max(candidates, key=lambda r: r.priority)

        if record is None:
            raise ServiceNotFoundException(f"No service matched query: {query}")

        if query.min_version and not SemVerParser.satisfies(record.version, f">={query.min_version}"):
            raise ServiceNotFoundException(
                f"Service {record.service_name} version {record.version} below required {query.min_version}"
            )

        self._permission.enforce(query.caller_scope, PermissionLevel[record.permission_level])

        if query.require_healthy and record.health_status not in (HealthStatus.HEALTHY, HealthStatus.DEGRADED):
            raise ServiceNotFoundException(
                f"Service {record.service_name} is not healthy (status={record.health_status.value})"
            )

        endpoint = ServiceInvocationEndpoint(
            service_id=record.service_id, service_name=record.service_name,
            endpoint_uri=f"ipc://service-registry/{record.service_name}",
            protocol=record.supported_interfaces[0] if record.supported_interfaces else "IPC",
            auth_token=record.auth_secret,
        )
        self._cache.put(key, endpoint)
        return endpoint


# ═══════════════════════════════════════════════════════════════════════
# SECTION 11 — HEALTH / HEARTBEAT / FAILURE / RECOVERY
# ═══════════════════════════════════════════════════════════════════════

class HeartbeatManager:
    def __init__(self, db: ServiceDatabase, config: ConfigurationInterface) -> None:
        self._db = db
        self._config = config
        self._last_tick: Dict[str, float] = {}
        self._lock = threading.RLock()

    def receive(self, frame: HeartbeatFrameDTO) -> None:
        with self._lock:
            record = self._db.get(frame.service_id)
            if record is None:
                raise ServiceNotFoundException(f"Heartbeat for unknown service {frame.service_id}")
            self._last_tick[frame.service_id] = time.time()
            record.missed_heartbeats = 0
            record.last_health_check = _now_iso()
            self._db.update(record)

    def check_missed(self, service_id: str) -> bool:
        timeout_s = self._config.get("health_monitoring.heartbeat_timeout_ms", 9000) / 1000.0
        last = self._last_tick.get(service_id)
        if last is None:
            return False
        return (time.time() - last) > timeout_s


class FailureDetector:
    def __init__(self, db: ServiceDatabase, heartbeat_mgr: HeartbeatManager) -> None:
        self._db = db
        self._heartbeat_mgr = heartbeat_mgr
        self._listeners: List[Callable[[FailureAlertDTO], None]] = []

    def on_failure(self, callback: Callable[[FailureAlertDTO], None]) -> None:
        self._listeners.append(callback)

    def evaluate(self, service_id: str) -> Optional[FailureAlertDTO]:
        record = self._db.get(service_id)
        if record is None:
            return None
        if self._heartbeat_mgr.check_missed(service_id):
            record.missed_heartbeats += 1
            self._db.update(record)
            if record.missed_heartbeats >= 3:
                alert = FailureAlertDTO(service_id=service_id, failure_type=FailureType.HANG,
                                         reason="missed_heartbeat_threshold_exceeded")
                for cb in self._listeners:
                    cb(alert)
                return alert
        return None

    def evaluate_process(self, service_id: str, alive: bool) -> Optional[FailureAlertDTO]:
        if alive:
            return None
        alert = FailureAlertDTO(service_id=service_id, failure_type=FailureType.CRASH,
                                 reason="process_exit_detected")
        for cb in self._listeners:
            cb(alert)
        return alert


class HealthMonitor:
    def __init__(self, db: ServiceDatabase, config: ConfigurationInterface,
                 state_manager: StateManager) -> None:
        self._db = db
        self._config = config
        self._state_manager = state_manager

    def probe(self, probe: HealthProbeDTO) -> HealthStatus:
        record = self._db.get(probe.service_id)
        if record is None:
            raise ServiceNotFoundException(f"Health probe for unknown service {probe.service_id}")
        record.cpu_usage_pct = probe.cpu_usage_pct
        record.memory_usage_mb = probe.memory_usage_mb
        record.gpu_usage_pct = probe.gpu_usage_pct
        record.last_health_check = _now_iso()

        max_cpu = self._config.get("health_monitoring.max_cpu_threshold_pct", 90.0)
        max_mem = self._config.get("health_monitoring.max_memory_threshold_mb", 4096.0)

        if probe.cpu_usage_pct >= max_cpu or probe.memory_usage_mb >= max_mem:
            record.health_status = HealthStatus.DEGRADED
        else:
            record.health_status = HealthStatus.HEALTHY
        self._db.update(record)
        return record.health_status

    def mark_offline(self, service_id: str) -> None:
        record = self._db.get(service_id)
        if record:
            record.health_status = HealthStatus.OFFLINE
            self._db.update(record)


class RestartManager:
    def __init__(self, config: ConfigurationInterface, lifecycle: "LifecycleManager") -> None:
        self._config = config
        self._lifecycle = lifecycle

    def compute_backoff(self, attempt: int) -> float:
        base = self._config.get("recovery_policies.base_backoff_delay_ms", 1000) / 1000.0
        cap = self._config.get("recovery_policies.max_backoff_delay_ms", 30000) / 1000.0
        return min(cap, base * (2 ** attempt))

    def within_limits(self, record: ServiceRecord) -> bool:
        window = self._config.get("recovery_policies.restart_window_seconds", 300)
        max_attempts = self._config.get("recovery_policies.global_max_restart_attempts", 3)
        if time.time() - record.restart_window_start > window:
            record.restart_attempts = 0
            record.restart_window_start = time.time()
        return record.restart_attempts < max_attempts

    def restart(self, service_id: str) -> bool:
        return self._lifecycle.restart_service(service_id)


class RecoveryManager:
    def __init__(self, db: ServiceDatabase, restart_mgr: RestartManager,
                 state_manager: StateManager, audit: AuditManager,
                 history: HistoryManager) -> None:
        self._db = db
        self._restart_mgr = restart_mgr
        self._state_manager = state_manager
        self._audit = audit
        self._history = history

    def handle_failure(self, alert: FailureAlertDTO) -> None:
        record = self._db.get(alert.service_id)
        if record is None:
            return
        self._audit.log("SERVICE_FAILURE", "RecoveryManager",
                         {"service_id": alert.service_id, "failure_type": alert.failure_type.value,
                          "reason": alert.reason}, log_level="WARN")
        try:
            self._state_manager.transition(alert.service_id, ServiceState.FAILED)
        except IllegalStateTransitionError:
            self._state_manager.transition(alert.service_id, ServiceState.FAILED, force=True)

        if record.restart_policy == RestartPolicy.NEVER.value:
            self._state_manager.transition(alert.service_id, ServiceState.DISABLED, force=True)
            self._history.archive(record, "restart_policy_never")
            return

        if not self._restart_mgr.within_limits(record):
            self._state_manager.transition(alert.service_id, ServiceState.DISABLED, force=True)
            self._audit.log("SERVICE_SAFE_MODE", "RecoveryManager",
                             {"service_id": alert.service_id}, log_level="ERROR")
            self._history.archive(record, "max_restart_attempts_exceeded")
            return

        self._state_manager.transition(alert.service_id, ServiceState.RECOVERING, force=True)
        record.restart_attempts += 1
        self._db.update(record)
        backoff = self._restart_mgr.compute_backoff(record.restart_attempts)
        self._audit.log("SERVICE_RECOVERY_SCHEDULED", "RecoveryManager",
                         {"service_id": alert.service_id, "backoff_seconds": backoff,
                          "attempt": record.restart_attempts})
        threading.Timer(backoff, self._restart_mgr.restart, args=(alert.service_id,)).start()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 12 — LIFECYCLE MANAGER
# ═══════════════════════════════════════════════════════════════════════

class LifecycleManager(ILifecycleManager):
    def __init__(self, db: ServiceDatabase, state_manager: StateManager,
                 dependency_mgr: DependencyManager, driver: IProcessDriver,
                 audit: AuditManager, history: HistoryManager) -> None:
        self._db = db
        self._state_manager = state_manager
        self._dependency_mgr = dependency_mgr
        self._driver = driver
        self._audit = audit
        self._history = history

    def start_service(self, service_id: str) -> bool:
        record = self._db.get(service_id)
        if record is None:
            raise ServiceNotFoundException(service_id)
        if not self._dependency_mgr.dependencies_healthy(service_id):
            raise ServiceRegistryError(f"Dependencies not healthy for {service_id}")

        self._state_manager.transition(service_id, ServiceState.VALIDATED, force=True)
        self._state_manager.transition(service_id, ServiceState.INITIALIZING)
        self._state_manager.transition(service_id, ServiceState.STARTING)
        try:
            pid = self._driver.spawn(record)
            record.process_id = pid
            record.last_restart = _now_iso()
            self._db.update(record)
            self._state_manager.transition(service_id, ServiceState.RUNNING)
            self._audit.log("SERVICE_STARTED", "LifecycleManager",
                             {"service_id": service_id, "pid": pid})
            return True
        except Exception as exc:  # noqa: BLE001
            self._state_manager.transition(service_id, ServiceState.FAILED, force=True)
            self._audit.log("SERVICE_START_FAILED", "LifecycleManager",
                             {"service_id": service_id, "error": str(exc)}, log_level="ERROR")
            return False

    def stop_service(self, service_id: str, graceful: bool = True) -> bool:
        record = self._db.get(service_id)
        if record is None:
            raise ServiceNotFoundException(service_id)
        self._state_manager.transition(service_id, ServiceState.STOPPING, force=True)
        ok = True
        if record.process_id is not None:
            ok = self._driver.terminate(record.process_id, force=not graceful)
        self._state_manager.transition(service_id, ServiceState.STOPPED, force=True)
        self._history.archive(record, "graceful_stop" if graceful else "forced_stop")
        self._audit.log("SERVICE_STOPPED", "LifecycleManager",
                         {"service_id": service_id, "graceful": graceful})
        return ok

    def restart_service(self, service_id: str) -> bool:
        record = self._db.get(service_id)
        if record is None:
            raise ServiceNotFoundException(service_id)
        self._state_manager.transition(service_id, ServiceState.RESTARTING, force=True)
        if record.process_id is not None:
            self._driver.terminate(record.process_id, force=True)
            record.process_id = None
            self._db.update(record)
        return self.start_service(service_id)

    def pause_service(self, service_id: str) -> None:
        self._state_manager.transition(service_id, ServiceState.PAUSED)

    def resume_service(self, service_id: str) -> None:
        self._state_manager.transition(service_id, ServiceState.RUNNING, force=True)

    def start_all_in_order(self) -> List[str]:
        started: List[str] = []
        for service_id in self._dependency_mgr.get_startup_sequence():
            if self.start_service(service_id):
                started.append(service_id)
        return started

    def stop_all_in_order(self) -> List[str]:
        stopped: List[str] = []
        for service_id in self._dependency_mgr.get_shutdown_sequence():
            record = self._db.get(service_id)
            if record and record.status in (ServiceState.RUNNING, ServiceState.IDLE, ServiceState.BUSY):
                self.stop_service(service_id, graceful=True)
                stopped.append(service_id)
        return stopped


# ═══════════════════════════════════════════════════════════════════════
# SECTION 13 — PIPELINES (src/pipelines)
# ═══════════════════════════════════════════════════════════════════════

class RegistrationPipeline:
    """[Ingest Payload] -> [Validate Schema] -> [Auth Check] -> [DAG Check] -> [Persist DB]"""

    def __init__(self, registration_mgr: RegistrationManager, dependency_mgr: DependencyManager) -> None:
        self._registration_mgr = registration_mgr
        self._dependency_mgr = dependency_mgr

    def run(self, manifest: ServiceManifestDTO, caller_scope: str) -> ServiceRecord:
        record = self._registration_mgr.register(manifest, caller_scope)
        self._dependency_mgr.sync_graph()
        try:
            self._dependency_mgr.validate_graph()
        except CircularDependencyError:
            self._registration_mgr._db.remove(record.service_id)  # rollback per spec
            raise
        return record


class DiscoveryPipeline:
    """[Search Query] -> [Cache Check] -> [Auth Check] -> [Query DB] -> [Return Endpoint]"""

    def __init__(self, discovery_mgr: DiscoveryManager) -> None:
        self._discovery_mgr = discovery_mgr

    def run(self, query: DiscoveryQueryDTO) -> ServiceInvocationEndpoint:
        return self._discovery_mgr.discover(query)


class StartupPipeline:
    """[Start Trigger] -> [Check Dep States] -> [Alloc Slot] -> [Spawn PID] -> [Running]"""

    def __init__(self, lifecycle_mgr: LifecycleManager) -> None:
        self._lifecycle_mgr = lifecycle_mgr

    def run(self, service_id: str) -> bool:
        return self._lifecycle_mgr.start_service(service_id)


class ShutdownPipeline:
    """[Stop Trigger] -> [Stop Downstream] -> [SIGTERM] -> [Wait] -> [SIGKILL if Hung]"""

    def __init__(self, lifecycle_mgr: LifecycleManager) -> None:
        self._lifecycle_mgr = lifecycle_mgr

    def run(self, service_id: str, graceful: bool = True) -> bool:
        return self._lifecycle_mgr.stop_service(service_id, graceful)


class HeartbeatPipeline:
    """[Heartbeat Frame] -> [Validate ID] -> [Reset Timer] -> [Update Last Health Time]"""

    def __init__(self, heartbeat_mgr: HeartbeatManager) -> None:
        self._heartbeat_mgr = heartbeat_mgr

    def run(self, frame: HeartbeatFrameDTO) -> None:
        self._heartbeat_mgr.receive(frame)


class HealthPipeline:
    """[Health Probe] -> [Read RAM/CPU] -> [Evaluate Limits] -> [Update Health Status]"""

    def __init__(self, health_monitor: HealthMonitor) -> None:
        self._health_monitor = health_monitor

    def run(self, probe: HealthProbeDTO) -> HealthStatus:
        return self._health_monitor.probe(probe)


class RecoveryPipeline:
    """[Crash Signal] -> [Classify Error] -> [Check Policy] -> [Trigger Backoff Restart]"""

    def __init__(self, recovery_mgr: RecoveryManager) -> None:
        self._recovery_mgr = recovery_mgr

    def run(self, alert: FailureAlertDTO) -> None:
        self._recovery_mgr.handle_failure(alert)


class RestartPipeline:
    """[Restart Trigger] -> [Graceful Stop] -> [Apply Backoff] -> [Execute Launch Sequence]"""

    def __init__(self, restart_mgr: RestartManager) -> None:
        self._restart_mgr = restart_mgr

    def run(self, service_id: str) -> bool:
        return self._restart_mgr.restart(service_id)


class MonitoringPipeline:
    """[Telemetry Tick] -> [Aggregate Footprint] -> [Build Metrics] -> [Stream Output]"""

    def __init__(self, monitoring_mgr: MonitoringManager) -> None:
        self._monitoring_mgr = monitoring_mgr

    def run(self) -> Dict[str, Any]:
        return self._monitoring_mgr.aggregate()


class MetricsPipeline:
    """[Event Trigger] -> [Increment Counters] -> [Update Histograms] -> [Export Stream]"""

    def __init__(self, metrics_mgr: MetricsManager) -> None:
        self._metrics_mgr = metrics_mgr

    def run(self) -> MetricsDTO:
        return self._metrics_mgr.snapshot()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 14 — SERVICE REGISTRY CORE (Master Orchestrator)
# ═══════════════════════════════════════════════════════════════════════

class ServiceRegistryCore(IServiceRegistry):
    """Central operational coordinator for the Service Registry organ.
    Owns all internal managers, sockets, and pipelines. Provides thread-safe
    read/write locking over internal system state via StateManager."""

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None,
                 process_driver: Optional[IProcessDriver] = None) -> None:
        self._lock = threading.RLock()
        self.config = ConfigurationInterface(config_overrides)
        self.db = ServiceDatabase()
        self.cache = ServiceCache(
            capacity=self.config.get("core.cache_capacity", 5000),
            ttl_seconds=self.config.get("core.cache_ttl_seconds", 120),
        )
        self.audit = AuditManager()
        self.history = HistoryManager()
        self.metrics = MetricsManager()
        self.monitoring = MonitoringManager(self.db, self.metrics)

        self.metadata_mgr = MetadataManager()
        self.permission_mgr = PermissionManager()
        self.version_mgr = VersionManager()
        self.compat_validator = CompatibilityValidator(self.version_mgr)
        self.state_mgr = StateManager(self.db, self.audit)
        self.registration_mgr = RegistrationManager(
            self.db, self.metadata_mgr, self.compat_validator,
            self.permission_mgr, self.state_mgr, self.audit,
        )
        self.dependency_mgr = DependencyManager(self.db, self.compat_validator)
        self.discovery_mgr = DiscoveryManager(self.db, self.cache, self.permission_mgr, self.metrics)

        self.heartbeat_mgr = HeartbeatManager(self.db, self.config)
        self.failure_detector = FailureDetector(self.db, self.heartbeat_mgr)
        self.health_monitor = HealthMonitor(self.db, self.config, self.state_mgr)

        self.driver = process_driver or InProcessDriver()
        self.lifecycle_mgr = LifecycleManager(
            self.db, self.state_mgr, self.dependency_mgr, self.driver, self.audit, self.history,
        )
        self.restart_mgr = RestartManager(self.config, self.lifecycle_mgr)
        self.recovery_mgr = RecoveryManager(self.db, self.restart_mgr, self.state_mgr,
                                             self.audit, self.history)
        self.failure_detector.on_failure(self.recovery_mgr.handle_failure)

        # cache invalidation on any state mutation
        self.state_mgr.subscribe(
            lambda rec, old, new: self.cache.invalidate_service(rec.service_id, rec.service_name)
        )

        # Pipelines
        self.registration_pipeline = RegistrationPipeline(self.registration_mgr, self.dependency_mgr)
        self.discovery_pipeline = DiscoveryPipeline(self.discovery_mgr)
        self.startup_pipeline = StartupPipeline(self.lifecycle_mgr)
        self.shutdown_pipeline = ShutdownPipeline(self.lifecycle_mgr)
        self.heartbeat_pipeline = HeartbeatPipeline(self.heartbeat_mgr)
        self.health_pipeline = HealthPipeline(self.health_monitor)
        self.recovery_pipeline = RecoveryPipeline(self.recovery_mgr)
        self.restart_pipeline = RestartPipeline(self.restart_mgr)
        self.monitoring_pipeline = MonitoringPipeline(self.monitoring)
        self.metrics_pipeline = MetricsPipeline(self.metrics)

        # Sockets — bound to pipeline entry points
        self.registration_socket = RegistrationSocket(
            lambda payload, scope: self.registration_pipeline.run(payload, scope.name)
        )
        self.discovery_socket = DiscoverySocket(
            lambda payload, scope: self.discovery_pipeline.run(payload)
        )
        self.lifecycle_socket = LifecycleSocket(self._lifecycle_socket_handler)
        self.health_socket = HealthSocket(
            lambda payload, scope: self.health_pipeline.run(payload)
        )
        self.heartbeat_socket = HeartbeatSocket(
            lambda payload, scope: self.heartbeat_pipeline.run(payload)
        )
        self.dependency_socket = DependencySocket(self._dependency_socket_handler)
        self.monitoring_socket = MonitoringSocket(
            lambda payload, scope: self.monitoring_pipeline.run()
        )
        self.recovery_socket = RecoverySocket(self._recovery_socket_handler)
        self.metrics_socket = MetricsSocket(
            lambda payload, scope: self.metrics_pipeline.run()
        )

        self._running = False

    # ---- socket dispatch handlers ------------------------------------

    def _lifecycle_socket_handler(self, payload: Tuple, scope: PermissionLevel) -> bool:
        action, service_id, *rest = payload
        if action == "start":
            return self.startup_pipeline.run(service_id)
        if action == "stop":
            graceful = rest[0] if rest else True
            return self.shutdown_pipeline.run(service_id, graceful)
        if action == "restart":
            return self.restart_pipeline.run(service_id)
        if action == "pause":
            self.lifecycle_mgr.pause_service(service_id)
            return True
        if action == "resume":
            self.lifecycle_mgr.resume_service(service_id)
            return True
        raise ServiceRegistryError(f"Unknown lifecycle action: {action}")

    def _dependency_socket_handler(self, payload: Tuple, scope: PermissionLevel) -> Any:
        action = payload[0]
        if action == "validate":
            return self.dependency_mgr.validate_graph()
        if action == "startup_sequence":
            return self.dependency_mgr.get_startup_sequence()
        if action == "shutdown_sequence":
            return self.dependency_mgr.get_shutdown_sequence()
        raise ServiceRegistryError(f"Unknown dependency action: {action}")

    def _recovery_socket_handler(self, payload: Any, scope: PermissionLevel) -> Any:
        if isinstance(payload, FailureAlertDTO):
            self.recovery_pipeline.run(payload)
            return True
        action = payload[0]
        if action == "history":
            service_id = payload[1] if len(payload) > 1 else None
            return self.history.query(service_id)
        raise ServiceRegistryError(f"Unknown recovery action: {action}")

    # ---- IServiceRegistry implementation -------------------------------

    def register_service(self, manifest: ServiceManifestDTO) -> bool:
        with self._lock:
            self.registration_pipeline.run(manifest, PermissionLevel.LEVEL_3_ADMIN.name)
            return True

    def discover_service(self, query_params: Dict[str, Any], caller_scope: str) -> ServiceInvocationEndpoint:
        query = DiscoveryQueryDTO(caller_scope=caller_scope, **query_params)
        return self.discovery_pipeline.run(query)

    def deregister_service(self, service_id: str, auth_key: str) -> bool:
        with self._lock:
            record = self.db.get(service_id)
            if record is None:
                raise ServiceNotFoundException(service_id)
            if record.auth_secret != auth_key:
                raise PermissionDeniedException("Invalid deregistration auth key")
            if record.status in (ServiceState.RUNNING, ServiceState.IDLE, ServiceState.BUSY):
                self.lifecycle_mgr.stop_service(service_id, graceful=True)
            self.state_mgr.transition(service_id, ServiceState.ARCHIVED, force=True)
            self.history.archive(record, "deregistered")
            self.dependency_mgr._dag.remove_node(service_id)
            self.db.remove(service_id)
            self.audit.log("SERVICE_DEREGISTERED", "ServiceRegistryCore", {"service_id": service_id})
            return True

    # ---- lifecycle bootstrap --------------------------------------------

    def boot(self) -> List[str]:
        self.dependency_mgr.validate_graph()
        started = self.lifecycle_mgr.start_all_in_order()
        self._running = True
        self.audit.log("REGISTRY_BOOTED", "ServiceRegistryCore", {"started": started})
        return started

    def shutdown(self) -> List[str]:
        stopped = self.lifecycle_mgr.stop_all_in_order()
        self._running = False
        self.audit.log("REGISTRY_SHUTDOWN", "ServiceRegistryCore", {"stopped": stopped})
        return stopped

    def health_sweep(self) -> None:
        """Periodic sweep: evaluate missed heartbeats and process liveness for all
        RUNNING services. Intended to be invoked by an external scheduler tick
        (e.g. from Infrastructure's Task Scheduler socket) rather than a
        self-managed thread, to respect Universal Law 11 (Resource Responsibility)."""
        for record in self.db.query(status=ServiceState.RUNNING):
            self.failure_detector.evaluate(record.service_id)
            if record.process_id is not None:
                alive = self.driver.is_alive(record.process_id)
                self.failure_detector.evaluate_process(record.service_id, alive)
