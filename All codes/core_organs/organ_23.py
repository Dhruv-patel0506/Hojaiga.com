"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 23
Name: Unknown Organ 23

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Unknown Organ 23]
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
Dependencies: enum, pathlib, __future__, typing, json...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_23.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
ORGAN 23 — DEPENDENCY GRAPH (AOS-DEP)
======================================================================
Authority Order: Constitution > Law Book > Diagrams > Legacy Guide >
                  Policy Manual > Master Architecture Blueprint >
                  Organ Specification > Dependency_Graph.md (this organ)

Single importable module implementing the Dependency Graph organ of the
Hojaiga Automation Operating System. Communicates with other organs
exclusively through the socket/pipeline interfaces defined below.

----------------------------------------------------------------------
PRE-CODE DIAGRAM — HIGH LEVEL TOPOLOGY
----------------------------------------------------------------------
                              KERNEL
                                |
                                v
                        DEPENDENCY GRAPH (AOS-DEP)
                                |
        +-----------------------+-----------------------+
        |                       |                        |
        v                       v                        v
  DEPENDENCY DATABASE   DEPENDENCY VALIDATOR     DEPENDENCY RESOLVER
        |                                                 |
        +------------------------+------------------------+
                                  v
                         DEPENDENCY PLANNER
                                  |
        +-----------+-----------+-----------+-----------+
        v           v           v           v
     ORGANS      RUNTIME    SHARED SVC   EXTERNAL CONNECTORS
                                              |
                                              v
                                          PLUGINS

----------------------------------------------------------------------
PRE-CODE DIAGRAM — MODULE ARCHITECTURE (mirrors this file's sections)
----------------------------------------------------------------------
  DEPENDENCY CORE
    Registry | Database | Cache | Metrics | Health | Monitor
        |
        v
  ANALYSIS & VALIDATION
    Validator | CircularDetector | VersionCompatibilityEngine
        |
        v
  PLANNING & EXECUTION
    Resolver | StartupPlanner | ShutdownPlanner
    UpgradePlanner | RollbackPlanner | RecoveryPlanner
        |
        v
  GOVERNANCE & SUPPORT
    ConfigInterface | AuditManager | DependencyHistory

----------------------------------------------------------------------
ACTUAL-CODE DIAGRAM — RUNTIME CALL FLOW
----------------------------------------------------------------------
  DependencyGraphOrgan.register_dependency()
        -> DependencyValidator.validate()
        -> CircularDependencyDetector.assert_acyclic()
        -> DependencyRegistry.register()
        -> DependencyDatabase.persist_graph()
        -> AuditManager.record()
        -> SocketBus.publish("dep_core")

  DependencyGraphOrgan.compute_startup_sequence()
        -> TopologicalResolver.resolve_execution_order()
        -> StartupPlanner.generate_startup_sequence()

  DependencyGraphOrgan.handle_component_failure()
        -> RecoveryPlanner.plan_recovery()
        -> SocketBus.publish("dep_recovery")
======================================================================
"""


import json
import re
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Optional


# ======================================================================
# SECTION 1 — DATA SPECIFICATIONS
# ======================================================================

class DependencyType(str, Enum):
    KERNEL = "KERNEL"
    SHARED_SERVICE = "SHARED_SERVICE"
    BRAIN = "BRAIN"
    MEMORY = "MEMORY"
    KNOWLEDGE = "KNOWLEDGE"
    AUTOMATION = "AUTOMATION"
    CONTROLLER = "CONTROLLER"
    LEARNING = "LEARNING"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    SECURITY = "SECURITY"
    INTEGRATION = "INTEGRATION"
    INTERFACE = "INTERFACE"
    RUNTIME = "RUNTIME"
    CONNECTOR = "CONNECTOR"
    PLUGIN = "PLUGIN"
    HARDWARE = "HARDWARE"
    CONFIGURATION = "CONFIGURATION"
    CAPABILITY = "CAPABILITY"
    SERVICE = "SERVICE"
    WORKFLOW = "WORKFLOW"
    FUTURE = "FUTURE"


class DependencyStrength(str, Enum):
    MANDATORY = "MANDATORY"
    OPTIONAL = "OPTIONAL"
    CONDITIONAL = "CONDITIONAL"


class FailureImpact(str, Enum):
    FATAL = "FATAL"
    DEGRADED = "DEGRADED"
    ISOLATED = "ISOLATED"
    NON_CRITICAL = "NON_CRITICAL"


class ComponentState(str, Enum):
    UNREGISTERED = "UNREGISTERED"
    REGISTERED = "REGISTERED"
    INITIALIZED = "INITIALIZED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


COMPONENT_ID_PATTERN = re.compile(r"^[a-z0-9_]+:[a-z0-9_.\-]+$")


class DependencyGraphError(Exception):
    """Base error for all AOS-DEP operations."""


class RegistrationError(DependencyGraphError):
    pass


class DeregistrationError(DependencyGraphError):
    pass


class NotFoundError(DependencyGraphError):
    pass


class ValidationError(DependencyGraphError):
    pass


class CycleDetectedError(DependencyGraphError):
    def __init__(self, cycles: list[list[str]]):
        self.cycles = cycles
        super().__init__(f"Circular dependency detected: {cycles}")


class ResolutionError(DependencyGraphError):
    pass


class CapabilityResolutionError(DependencyGraphError):
    pass


class MatrixMismatchError(DependencyGraphError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AOSDependencyRecord:
    source_component: str
    target_component: str
    dependency_type: DependencyType
    dependency_strength: DependencyStrength
    version_requirement: str
    compatibility_range: str
    priority: int
    startup_order: int
    shutdown_order: int
    recovery_order: int
    failure_impact: FailureImpact
    owner: str
    dependency_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    condition_expression: Optional[str] = None
    registration_date: str = field(default_factory=_utc_now)
    last_updated: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not COMPONENT_ID_PATTERN.match(self.source_component):
            raise ValidationError(
                f"source_component '{self.source_component}' violates naming pattern"
            )
        if not COMPONENT_ID_PATTERN.match(self.target_component):
            raise ValidationError(
                f"target_component '{self.target_component}' violates naming pattern"
            )
        if not (0 <= self.priority <= 1000):
            raise ValidationError("priority must be within [0, 1000]")
        if self.dependency_strength == DependencyStrength.CONDITIONAL and not self.condition_expression:
            raise ValidationError("CONDITIONAL strength requires condition_expression")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dependency_type"] = self.dependency_type.value
        d["dependency_strength"] = self.dependency_strength.value
        d["failure_impact"] = self.failure_impact.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "AOSDependencyRecord":
        d = dict(d)
        d["dependency_type"] = DependencyType(d["dependency_type"])
        d["dependency_strength"] = DependencyStrength(d["dependency_strength"])
        d["failure_impact"] = FailureImpact(d["failure_impact"])
        return AOSDependencyRecord(**d)


@dataclass
class ComponentMeta:
    identifier: str
    state: ComponentState = ComponentState.UNREGISTERED
    dependency_type: Optional[DependencyType] = None
    version: str = "0.0.0"


@dataclass
class GraphSnapshot:
    records: list[AOSDependencyRecord] = field(default_factory=list)
    captured_at: str = field(default_factory=_utc_now)

    def adjacency(self) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = defaultdict(list)
        for r in self.records:
            adj[r.source_component].append(r.target_component)
        return dict(adj)


# ======================================================================
# SECTION 2 — SOCKET BUS / PIPELINES (inter-organ communication)
# ======================================================================

class SocketBus:
    """
    In-process publish/subscribe bus emulating the AOS-DEP UNIX domain
    sockets described in the specification. Other organs interact with
    this organ exclusively through named channels registered here.
    """

    CHANNELS = (
        "dep_core", "dep_registry", "dep_db", "dep_val", "dep_res",
        "dep_plan", "dep_upgrade", "dep_rollback", "dep_startup",
        "dep_shutdown", "dep_recovery", "dep_circular", "dep_version",
        "dep_aud",
    )

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[dict], None]]] = {
            c: [] for c in self.CHANNELS
        }
        self._lock = threading.Lock()

    def subscribe(self, channel: str, handler: Callable[[dict], None]) -> None:
        if channel not in self._subscribers:
            raise NotFoundError(f"Unknown socket channel: {channel}")
        with self._lock:
            self._subscribers[channel].append(handler)

    def publish(self, channel: str, payload: dict) -> None:
        if channel not in self._subscribers:
            raise NotFoundError(f"Unknown socket channel: {channel}")
        with self._lock:
            handlers = list(self._subscribers[channel])
        for handler in handlers:
            handler(payload)


class Pipeline:
    """A named, ordered sequence of processing stages."""

    def __init__(self, name: str, stages: list[Callable[[dict], dict]]):
        self.name = name
        self.stages = stages

    def run(self, payload: dict) -> dict:
        current = payload
        for stage in self.stages:
            current = stage(current)
        return current


# ======================================================================
# SECTION 3 — DEPENDENCY DATABASE (persistent, ACID via sqlite3)
# ======================================================================

class DependencyDatabase:
    """ACID-compliant persistence layer for dependency records."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;") if db_path != ":memory:" else None
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dependencies (
                    dependency_id TEXT PRIMARY KEY,
                    record_json TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    action TEXT NOT NULL,
                    dependency_id TEXT,
                    detail TEXT
                )
                """
            )

    def persist_record(self, record: AOSDependencyRecord) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO dependencies (dependency_id, record_json) VALUES (?, ?)",
                (record.dependency_id, json.dumps(record.to_dict())),
            )
            self._append_history("PERSIST", record.dependency_id, "record persisted")

    def delete_record(self, dependency_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM dependencies WHERE dependency_id = ?", (dependency_id,)
            )
            self._append_history("DELETE", dependency_id, "record removed")

    def _append_history(self, action: str, dependency_id: Optional[str], detail: str) -> None:
        self._conn.execute(
            "INSERT INTO history (ts, action, dependency_id, detail) VALUES (?, ?, ?, ?)",
            (_utc_now(), action, dependency_id, detail),
        )

    def load_graph(self) -> GraphSnapshot:
        with self._lock:
            rows = self._conn.execute("SELECT record_json FROM dependencies").fetchall()
        records = [AOSDependencyRecord.from_dict(json.loads(r[0])) for r in rows]
        return GraphSnapshot(records=records)

    def persist_graph(self, graph: GraphSnapshot) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM dependencies")
            for record in graph.records:
                self._conn.execute(
                    "INSERT INTO dependencies (dependency_id, record_json) VALUES (?, ?)",
                    (record.dependency_id, json.dumps(record.to_dict())),
                )
            self._append_history("SNAPSHOT", None, f"{len(graph.records)} records persisted")

    def history(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, ts, action, dependency_id, detail FROM history "
                "ORDER BY seq DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"seq": r[0], "ts": r[1], "action": r[2], "dependency_id": r[3], "detail": r[4]}
            for r in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ======================================================================
# SECTION 4 — DEPENDENCY REGISTRY (in-memory index)
# ======================================================================

class DependencyRegistry:
    """In-memory registration index management for edges and components."""

    def __init__(self) -> None:
        self._records: dict[str, AOSDependencyRecord] = {}
        self._components: dict[str, ComponentMeta] = {}
        self._lock = threading.RLock()

    def register(self, record: AOSDependencyRecord) -> str:
        with self._lock:
            self._records[record.dependency_id] = record
            self._touch_component(record.source_component, record.dependency_type)
            self._touch_component(record.target_component, record.dependency_type)
        return record.dependency_id

    def _touch_component(self, identifier: str, dep_type: DependencyType) -> None:
        meta = self._components.get(identifier)
        if meta is None:
            self._components[identifier] = ComponentMeta(
                identifier=identifier,
                state=ComponentState.REGISTERED,
                dependency_type=dep_type,
            )

    def deregister(self, dependency_id: str) -> bool:
        with self._lock:
            return self._records.pop(dependency_id, None) is not None

    def get_by_id(self, dependency_id: str) -> AOSDependencyRecord:
        with self._lock:
            record = self._records.get(dependency_id)
        if record is None:
            raise NotFoundError(f"Dependency {dependency_id} not found")
        return record

    def get_dependents(self, component_id: str) -> list[str]:
        with self._lock:
            return [
                r.source_component
                for r in self._records.values()
                if r.target_component == component_id
            ]

    def get_dependencies_of(self, component_id: str) -> list[str]:
        with self._lock:
            return [
                r.target_component
                for r in self._records.values()
                if r.source_component == component_id
            ]

    def lookup_component(self, identifier: str) -> ComponentMeta:
        with self._lock:
            meta = self._components.get(identifier)
        if meta is None:
            raise NotFoundError(f"Component {identifier} not found")
        return meta

    def set_component_state(self, identifier: str, state: ComponentState) -> None:
        with self._lock:
            meta = self._components.get(identifier)
            if meta is None:
                meta = ComponentMeta(identifier=identifier)
                self._components[identifier] = meta
            meta.state = state

    def list_registered_components(
        self, type_filter: Optional[DependencyType] = None
    ) -> list[ComponentMeta]:
        with self._lock:
            values = list(self._components.values())
        if type_filter is None:
            return values
        return [m for m in values if m.dependency_type == type_filter]

    def all_records(self) -> list[AOSDependencyRecord]:
        with self._lock:
            return list(self._records.values())

    def snapshot(self) -> GraphSnapshot:
        return GraphSnapshot(records=self.all_records())

    def load_snapshot(self, snapshot: GraphSnapshot) -> None:
        with self._lock:
            self._records.clear()
            self._components.clear()
            for record in snapshot.records:
                self.register(record)


# ======================================================================
# SECTION 5 — CIRCULAR DEPENDENCY DETECTOR (Tarjan's SCC algorithm)
# ======================================================================

class CircularDependencyDetector:
    """Graph cycle detection via Tarjan's strongly-connected-components algorithm."""

    def detect_cycles(self, adjacency_matrix: dict[str, list[str]]) -> list[list[str]]:
        index_counter = [0]
        stack: list[str] = []
        lowlink: dict[str, int] = {}
        index: dict[str, int] = {}
        on_stack: dict[str, bool] = {}
        result: list[list[str]] = []

        nodes = set(adjacency_matrix.keys())
        for targets in adjacency_matrix.values():
            nodes.update(targets)

        def strongconnect(node: str) -> None:
            index[node] = index_counter[0]
            lowlink[node] = index_counter[0]
            index_counter[0] += 1
            stack.append(node)
            on_stack[node] = True

            for neighbor in adjacency_matrix.get(node, []):
                if neighbor not in index:
                    strongconnect(neighbor)
                    lowlink[node] = min(lowlink[node], lowlink[neighbor])
                elif on_stack.get(neighbor):
                    lowlink[node] = min(lowlink[node], index[neighbor])

            if lowlink[node] == index[node]:
                component: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    component.append(w)
                    if w == node:
                        break
                if len(component) > 1 or (component and component[0] in adjacency_matrix.get(component[0], [])):
                    result.append(component)

        for node in nodes:
            if node not in index:
                strongconnect(node)

        return result

    def assert_acyclic(self, adjacency_matrix: dict[str, list[str]]) -> None:
        cycles = self.detect_cycles(adjacency_matrix)
        if cycles:
            raise CycleDetectedError(cycles)

    def analyze_edge_insertion(
        self, graph: GraphSnapshot, new_edge: AOSDependencyRecord
    ) -> None:
        trial = GraphSnapshot(records=graph.records + [new_edge])
        self.assert_acyclic(trial.adjacency())


# ======================================================================
# SECTION 6 — VERSION COMPATIBILITY ENGINE (SemVer 2.0.0)
# ======================================================================

@dataclass
class CompatibilityResult:
    compatible: bool
    reason: str = ""


class VersionCompatibilityEngine:
    """Enforces Semantic Versioning 2.0.0 compatibility rules."""

    _SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z\-.]+)?(?:\+[0-9A-Za-z\-.]+)?$")

    @classmethod
    def _parse(cls, version: str) -> tuple[int, int, int]:
        m = cls._SEMVER.match(version.strip())
        if not m:
            raise ValidationError(f"'{version}' is not a valid SemVer string")
        return int(m.group(1)), int(m.group(2)), int(m.group(3))

    def evaluate_compatibility(self, provided: str, required: str) -> CompatibilityResult:
        required = required.strip()
        try:
            p_major, p_minor, p_patch = self._parse(provided)
        except ValidationError as exc:
            return CompatibilityResult(False, str(exc))

        if required.startswith("^"):
            r_major, r_minor, r_patch = self._parse(required[1:])
            ok = (
                p_major == r_major
                and (p_minor, p_patch) >= (r_minor, r_patch)
            )
            return CompatibilityResult(ok, "caret range check")
        if required.startswith("~"):
            r_major, r_minor, r_patch = self._parse(required[1:])
            ok = p_major == r_major and p_minor == r_minor and p_patch >= r_patch
            return CompatibilityResult(ok, "tilde range check")
        if required.startswith(">="):
            r = self._parse(required[2:])
            ok = (p_major, p_minor, p_patch) >= r
            return CompatibilityResult(ok, ">= range check")
        if required.startswith("<="):
            r = self._parse(required[2:])
            ok = (p_major, p_minor, p_patch) <= r
            return CompatibilityResult(ok, "<= range check")
        if required.startswith(">"):
            r = self._parse(required[1:])
            ok = (p_major, p_minor, p_patch) > r
            return CompatibilityResult(ok, "> range check")
        if required.startswith("<"):
            r = self._parse(required[1:])
            ok = (p_major, p_minor, p_patch) < r
            return CompatibilityResult(ok, "< range check")
        # exact match
        r = self._parse(required)
        return CompatibilityResult((p_major, p_minor, p_patch) == r, "exact match")

    def validate_matrix(self, matrix: dict[str, tuple[str, str]]) -> None:
        """matrix: component -> (provided_version, required_range)."""
        for component, (provided, required) in matrix.items():
            result = self.evaluate_compatibility(provided, required)
            if not result.compatible:
                raise MatrixMismatchError(
                    f"Component '{component}' version mismatch: "
                    f"provided={provided} required={required} ({result.reason})"
                )


# ======================================================================
# SECTION 7 — DEPENDENCY VALIDATOR
# ======================================================================

class DependencyValidator:
    """
    Ensures structural integrity, policy compliance, and operational
    viability of proposed graph states prior to execution, per
    Universal Law 2 (Constitutional Compliance) and Universal Law 6
    (State Integrity).
    """

    def __init__(
        self,
        registry: DependencyRegistry,
        circular_detector: CircularDependencyDetector,
        version_engine: VersionCompatibilityEngine,
    ) -> None:
        self._registry = registry
        self._circular_detector = circular_detector
        self._version_engine = version_engine

    def validate_record(self, record: AOSDependencyRecord) -> None:
        if record.source_component == record.target_component:
            raise ValidationError("A component cannot depend on itself")
        for existing in self._registry.all_records():
            if (
                existing.source_component == record.source_component
                and existing.target_component == record.target_component
                and existing.dependency_id != record.dependency_id
            ):
                raise ValidationError(
                    f"Duplicate dependency edge {record.source_component} -> "
                    f"{record.target_component}"
                )
        graph = self._registry.snapshot()
        self._circular_detector.analyze_edge_insertion(graph, record)

    def validate_graph(self, graph: GraphSnapshot) -> None:
        self._circular_detector.assert_acyclic(graph.adjacency())
        seen: set[tuple[str, str]] = set()
        for record in graph.records:
            key = (record.source_component, record.target_component)
            if key in seen:
                raise ValidationError(f"Duplicate edge detected: {key}")
            seen.add(key)


# ======================================================================
# SECTION 8 — TOPOLOGICAL RESOLVER (Kahn's algorithm)
# ======================================================================

class TopologicalResolver:
    """
    Calculates execution topologies and resolves capability bindings.
    Note: an edge source->target is interpreted as "source depends on
    target", therefore target must execute (start) before source.
    """

    def resolve_execution_order(
        self, nodes: list[str], edges: list[AOSDependencyRecord]
    ) -> list[str]:
        in_degree: dict[str, int] = {n: 0 for n in nodes}
        adjacency: dict[str, list[str]] = defaultdict(list)

        for edge in edges:
            if edge.dependency_strength == DependencyStrength.OPTIONAL:
                continue
            # target must start before source -> edge target -> source
            adjacency[edge.target_component].append(edge.source_component)
            in_degree.setdefault(edge.source_component, 0)
            in_degree.setdefault(edge.target_component, 0)
            in_degree[edge.source_component] += 1

        for n in nodes:
            in_degree.setdefault(n, 0)

        queue = deque(sorted(n for n, d in in_degree.items() if d == 0))
        order: list[str] = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in sorted(adjacency.get(node, [])):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(in_degree):
            remaining = set(in_degree) - set(order)
            raise ResolutionError(
                f"Unresolvable graph: mandatory cycle involving {remaining}"
            )
        return order

    def generate_boot_waves(self, resolved_order: list[str]) -> list[list[str]]:
        return [[n] for n in resolved_order] if False else self._group_waves(resolved_order)

    def _group_waves(self, resolved_order: list[str]) -> list[list[str]]:
        # Placeholder wave grouping refined by StartupPlanner using real
        # dependency depth; here we expose the linear order as a single
        # baseline wave-per-node structure that StartupPlanner compacts.
        return [[node] for node in resolved_order]

    def resolve_subtree(
        self, root: str, edges: list[AOSDependencyRecord]
    ) -> list[str]:
        visited: set[str] = set()
        result: list[str] = []

        deps_of: dict[str, list[str]] = defaultdict(list)
        for e in edges:
            if e.dependency_strength != DependencyStrength.OPTIONAL:
                deps_of[e.source_component].append(e.target_component)

        def visit(node: str) -> None:
            if node in visited:
                return
            visited.add(node)
            for dep in sorted(deps_of.get(node, [])):
                visit(dep)
            result.append(node)

        visit(root)
        return result

    def resolve_capability(
        self, capability_id: str, providers: dict[str, list[ComponentMeta]]
    ) -> str:
        candidates = providers.get(capability_id, [])
        healthy = [
            c for c in candidates
            if c.state in (ComponentState.INITIALIZED, ComponentState.REGISTERED)
        ]
        if not healthy:
            raise CapabilityResolutionError(
                f"No healthy provider available for capability '{capability_id}'"
            )
        return healthy[0].identifier


# ======================================================================
# SECTION 9 — STARTUP / SHUTDOWN / RECOVERY PLANNERS
# ======================================================================

@dataclass
class StartupSequence:
    waves: list[list[str]]


@dataclass
class ShutdownSequence:
    waves: list[list[str]]
    mode: str


@dataclass
class RecoveryPlan:
    failed_component: str
    quarantined: list[str]
    restart_tree: list[str]


class StartupPlanner:
    """Translates raw topology into an optimized, wave-based boot sequence."""

    def __init__(self, resolver: TopologicalResolver) -> None:
        self._resolver = resolver

    def generate_startup_sequence(
        self, nodes: list[str], edges: list[AOSDependencyRecord]
    ) -> StartupSequence:
        order = self._resolver.resolve_execution_order(nodes, edges)
        depends_on: dict[str, set[str]] = defaultdict(set)
        for e in edges:
            if e.dependency_strength != DependencyStrength.OPTIONAL:
                depends_on[e.source_component].add(e.target_component)

        depth: dict[str, int] = {}
        for node in order:
            deps = depends_on.get(node, set())
            depth[node] = 0 if not deps else 1 + max(depth.get(d, 0) for d in deps)

        waves: dict[int, list[str]] = defaultdict(list)
        for node, d in depth.items():
            waves[d].append(node)
        ordered_waves = [sorted(waves[level]) for level in sorted(waves.keys())]
        return StartupSequence(waves=ordered_waves)


class ShutdownPlanner:
    """Computes strict reverse-topological teardown sequences."""

    def __init__(self, startup_planner: StartupPlanner) -> None:
        self._startup_planner = startup_planner

    def generate_shutdown_sequence(
        self, nodes: list[str], edges: list[AOSDependencyRecord], mode: str = "GRACEFUL"
    ) -> ShutdownSequence:
        startup = self._startup_planner.generate_startup_sequence(nodes, edges)
        reversed_waves = list(reversed([list(reversed(w)) for w in startup.waves]))
        return ShutdownSequence(waves=reversed_waves, mode=mode)


class RecoveryPlanner:
    """Generates dynamic recovery plans for runtime graph ruptures."""

    def __init__(self, registry: DependencyRegistry, resolver: TopologicalResolver) -> None:
        self._registry = registry
        self._resolver = resolver

    def plan_recovery(self, failed_component_id: str) -> RecoveryPlan:
        dependents = self._blast_radius(failed_component_id)
        edges = self._registry.all_records()
        restart_tree = self._resolver.resolve_subtree(failed_component_id, edges)
        restart_tree = [n for n in restart_tree if n in dependents or n == failed_component_id]
        return RecoveryPlan(
            failed_component=failed_component_id,
            quarantined=sorted(dependents),
            restart_tree=restart_tree,
        )

    def _blast_radius(self, component_id: str) -> set[str]:
        visited: set[str] = set()
        frontier = deque([component_id])
        while frontier:
            current = frontier.popleft()
            for dependent in self._registry.get_dependents(current):
                if dependent not in visited:
                    visited.add(dependent)
                    frontier.append(dependent)
        return visited


class UpgradePlanner:
    """Calculates safe, zero-downtime component upgrade sequences."""

    def __init__(self, registry: DependencyRegistry, resolver: TopologicalResolver) -> None:
        self._registry = registry
        self._resolver = resolver

    def plan_upgrade(self, target_component: str, new_version: str) -> dict:
        impacted = self._registry.get_dependents(target_component)
        edges = self._registry.all_records()
        quiescence_order = self._resolver.resolve_subtree(target_component, edges)
        return {
            "plan_id": str(uuid.uuid4()),
            "target_component": target_component,
            "new_version": new_version,
            "impacted_dependents": impacted,
            "quiescence_order": quiescence_order,
            "created_at": _utc_now(),
        }


class RollbackPlanner:
    """Provides fallback pathways restoring the graph to a known-valid state."""

    def __init__(self, database: DependencyDatabase) -> None:
        self._database = database
        self._checkpoints: dict[str, GraphSnapshot] = {}

    def checkpoint(self, label: str, graph: GraphSnapshot) -> None:
        self._checkpoints[label] = graph

    def generate_rollback_plan(self, failed_plan_id: str) -> dict:
        return {
            "rollback_id": str(uuid.uuid4()),
            "failed_plan_id": failed_plan_id,
            "generated_at": _utc_now(),
        }

    def execute_rollback(self, label: str, registry: DependencyRegistry) -> None:
        checkpoint = self._checkpoints.get(label)
        if checkpoint is None:
            raise NotFoundError(f"No rollback checkpoint '{label}' available")
        registry.load_snapshot(checkpoint)
        self._database.persist_graph(checkpoint)


# ======================================================================
# SECTION 10 — CACHE, METRICS, HEALTH, AUDIT
# ======================================================================

class DependencyCache:
    """Accelerates repeated graph queries and validation checks."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()
        self.ttl_seconds = 5.0

    def get(self, key: str) -> Optional[object]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.monotonic() - ts > self.ttl_seconds:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: object) -> None:
        with self._lock:
            self._store[key] = (time.monotonic(), value)

    def invalidate(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)


class DependencyMetrics:
    def __init__(self) -> None:
        self.registrations = 0
        self.deregistrations = 0
        self.validation_failures = 0
        self.resolutions = 0

    def snapshot(self) -> dict:
        return {
            "registrations": self.registrations,
            "deregistrations": self.deregistrations,
            "validation_failures": self.validation_failures,
            "resolutions": self.resolutions,
        }


class DependencyHealth:
    def __init__(self, registry: DependencyRegistry) -> None:
        self._registry = registry

    def report(self) -> dict:
        components = self._registry.list_registered_components()
        by_state: dict[str, int] = defaultdict(int)
        for c in components:
            by_state[c.state.value] += 1
        return {
            "total_components": len(components),
            "by_state": dict(by_state),
            "total_edges": len(self._registry.all_records()),
        }


class AuditManager:
    def __init__(self, database: DependencyDatabase) -> None:
        self._database = database

    def record(self, action: str, dependency_id: Optional[str], detail: str) -> None:
        self._database._append_history(action, dependency_id, detail)  # noqa: SLF001
        with self._database._lock, self._database._conn:  # noqa: SLF001
            pass


# ======================================================================
# SECTION 11 — CONFIGURATION INTERFACE
# ======================================================================

class ConfigInterface:
    def __init__(self, config: Optional[dict] = None) -> None:
        self._config = config or {
            "lock_timeout_ms": 50,
            "cache_ttl_seconds": 5.0,
            "topo_sort_target_ms": 10,
            "cycle_detection_target_ms": 5,
        }

    def get(self, key: str, default: object = None) -> object:
        return self._config.get(key, default)

    def load_from_file(self, path: str) -> None:
        p = Path(path)
        if p.exists():
            self._config.update(json.loads(p.read_text()))


# ======================================================================
# SECTION 12 — ORGAN FACADE (public entry point)
# ======================================================================

class DependencyGraphOrgan:
    """
    Public facade for Organ 23 — Dependency Graph (AOS-DEP).
    This is the ONLY object other organs should interact with. All
    cross-organ communication happens through `socket_bus` channels
    and the methods exposed here.
    """

    VERSION = "1.0.0"

    def __init__(self, db_path: str = ":memory:", config: Optional[dict] = None) -> None:
        self.config = ConfigInterface(config)
        self.database = DependencyDatabase(db_path)
        self.registry = DependencyRegistry()
        self.cache = DependencyCache()
        self.metrics = DependencyMetrics()
        self.health = DependencyHealth(self.registry)
        self.audit = AuditManager(self.database)
        self.socket_bus = SocketBus()

        self.circular_detector = CircularDependencyDetector()
        self.version_engine = VersionCompatibilityEngine()
        self.validator = DependencyValidator(
            self.registry, self.circular_detector, self.version_engine
        )
        self.resolver = TopologicalResolver()
        self.startup_planner = StartupPlanner(self.resolver)
        self.shutdown_planner = ShutdownPlanner(self.startup_planner)
        self.recovery_planner = RecoveryPlanner(self.registry, self.resolver)
        self.upgrade_planner = UpgradePlanner(self.registry, self.resolver)
        self.rollback_planner = RollbackPlanner(self.database)

        self._lock = threading.RLock()
        self._restore_from_database()

        self.request_pipeline = Pipeline(
            "dependency_registration_pipeline",
            [self._stage_validate, self._stage_persist, self._stage_publish],
        )

    def _restore_from_database(self) -> None:
        snapshot = self.database.load_graph()
        if snapshot.records:
            self.registry.load_snapshot(snapshot)

    # ---- Pipeline stages -------------------------------------------------

    def _stage_validate(self, payload: dict) -> dict:
        record: AOSDependencyRecord = payload["record"]
        self.validator.validate_record(record)
        return payload

    def _stage_persist(self, payload: dict) -> dict:
        record: AOSDependencyRecord = payload["record"]
        self.registry.register(record)
        self.database.persist_record(record)
        self.cache.invalidate()
        return payload

    def _stage_publish(self, payload: dict) -> dict:
        record: AOSDependencyRecord = payload["record"]
        self.socket_bus.publish("dep_core", {"event": "REGISTERED", "record": record.to_dict()})
        self.metrics.registrations += 1
        self.audit.record("REGISTER", record.dependency_id, "dependency registered")
        return payload

    # ---- Public API --------------------------------------------------

    def register_dependency(self, record: AOSDependencyRecord) -> str:
        with self._lock:
            try:
                self.request_pipeline.run({"record": record})
            except DependencyGraphError:
                self.metrics.validation_failures += 1
                raise
        return record.dependency_id

    def unregister_dependency(self, dependency_id: str) -> bool:
        with self._lock:
            ok = self.registry.deregister(dependency_id)
            if ok:
                self.database.delete_record(dependency_id)
                self.cache.invalidate()
                self.metrics.deregistrations += 1
                self.socket_bus.publish(
                    "dep_registry", {"event": "DEREGISTERED", "dependency_id": dependency_id}
                )
            return ok

    def get_dependency(self, dependency_id: str) -> AOSDependencyRecord:
        return self.registry.get_by_id(dependency_id)

    def update_dependency(self, dependency_id: str, record: AOSDependencyRecord) -> None:
        with self._lock:
            self.registry.deregister(dependency_id)
            record.dependency_id = dependency_id
            record.last_updated = _utc_now()
            self.register_dependency(record)

    def resolve_graph(self) -> list[str]:
        snapshot = self.registry.snapshot()
        nodes = list({r.source_component for r in snapshot.records} | {
            r.target_component for r in snapshot.records
        })
        order = self.resolver.resolve_execution_order(nodes, snapshot.records)
        self.metrics.resolutions += 1
        self.socket_bus.publish("dep_res", {"event": "RESOLVED", "order": order})
        return order

    def compute_startup_sequence(self) -> StartupSequence:
        cached = self.cache.get("startup_sequence")
        if cached is not None:
            return cached  # type: ignore
        snapshot = self.registry.snapshot()
        nodes = list({r.source_component for r in snapshot.records} | {
            r.target_component for r in snapshot.records
        })
        sequence = self.startup_planner.generate_startup_sequence(nodes, snapshot.records)
        self.cache.set("startup_sequence", sequence)
        self.socket_bus.publish("dep_startup", {"event": "SEQUENCE_READY", "waves": sequence.waves})
        return sequence

    def compute_shutdown_sequence(self, mode: str = "GRACEFUL") -> ShutdownSequence:
        snapshot = self.registry.snapshot()
        nodes = list({r.source_component for r in snapshot.records} | {
            r.target_component for r in snapshot.records
        })
        sequence = self.shutdown_planner.generate_shutdown_sequence(nodes, snapshot.records, mode)
        self.socket_bus.publish("dep_shutdown", {"event": "SEQUENCE_READY", "waves": sequence.waves})
        return sequence

    def handle_component_failure(self, failed_component_id: str) -> RecoveryPlan:
        self.registry.set_component_state(failed_component_id, ComponentState.FAILED)
        plan = self.recovery_planner.plan_recovery(failed_component_id)
        self.socket_bus.publish(
            "dep_recovery",
            {"event": "RECOVERY_PLANNED", "plan": asdict(plan)},
        )
        return plan

    def plan_upgrade(self, target_component: str, new_version: str) -> dict:
        checkpoint_label = f"pre-upgrade:{target_component}:{uuid.uuid4()}"
        self.rollback_planner.checkpoint(checkpoint_label, self.registry.snapshot())
        plan = self.upgrade_planner.plan_upgrade(target_component, new_version)
        plan["rollback_checkpoint"] = checkpoint_label
        self.socket_bus.publish("dep_upgrade", {"event": "UPGRADE_PLANNED", "plan": plan})
        return plan

    def rollback(self, checkpoint_label: str) -> None:
        self.rollback_planner.execute_rollback(checkpoint_label, self.registry)
        self.socket_bus.publish("dep_rollback", {"event": "ROLLED_BACK", "checkpoint": checkpoint_label})

    def detect_cycles(self) -> list[list[str]]:
        return self.circular_detector.detect_cycles(self.registry.snapshot().adjacency())

    def validate_full_graph(self) -> None:
        self.validator.validate_graph(self.registry.snapshot())

    def status(self) -> dict:
        return {
            "version": self.VERSION,
            "health": self.health.report(),
            "metrics": self.metrics.snapshot(),
        }

    def shutdown(self) -> None:
        self.database.close()
