"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 33
Name: System Manifest

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [System Manifest]
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
    input([Input Node]) --> process([Code Node: organ_33_system_manifest.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Organ 33 — System Manifest
===========================
Authority: Constitution > Law Book > Diagrams > Legacy Guide > Policy Manual
           > Master Architecture Blueprint > Organ Specification > System_Manifest.md

PRE-CODE DIAGRAM (spec-derived)
--------------------------------
SystemManifest
  +-- ManifestCore (orchestrator)
  +-- ComponentRegistry (+ 12 domain sub-registries: Organ/Controller/Manager/
  |     Service/Registry/Runtime/Connector/Plugin/Package/Task/Interface/Custom)
  +-- DependencyRegistry (DAG + Tarjan cycle detection + SemVer range resolve)
  +-- VersionRegistry (SemVer matrix + breaking-change guard + compat map)
  +-- HealthRegistry (heartbeat + state aggregation)
  +-- ConfigurationRegistry (schema binding + env map + secret refs)
  +-- DocumentationRegistry (spec/doc path map)
  +-- SecurityRegistry (clearance + permission masks)
  +-- ManifestValidator (side-effect-free strict validation)
  +-- ManifestLoader / ManifestExporter / ManifestImporter (persistence)
  +-- AuditInterface (append-only signed audit log)

ACTUAL-CODE DIAGRAM (implementation-reflecting)
------------------------------------------------
SystemManifest (facade)
  -> ManifestCore
       -> ComponentRegistry --uses--> DependencyRegistry, VersionRegistry
       -> HealthRegistry, ConfigurationRegistry, DocumentationRegistry,
          SecurityRegistry
       -> ManifestValidator (pure functions, no state mutation)
       -> AuditInterface (hash-chained JSONL ledger)
       -> ManifestLoader / ManifestExporter / ManifestImporter (JSON snapshot IO)
All cross-organ communication occurs only via the AOS communication layer
(SocketBus / PipelineBus) documented in Section "Socket & Pipeline Definitions"
below. This module never imports another organ.
"""


import asyncio
import hashlib
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# ======================================================================
# Enumerations
# ======================================================================

class ComponentCategory(str, Enum):
    SYSTEM = "SYSTEM"
    KERNEL = "KERNEL"
    ORGAN = "ORGAN"
    CONTROLLER = "CONTROLLER"
    MANAGER = "MANAGER"
    SERVICE = "SERVICE"
    REGISTRY = "REGISTRY"
    CATALOG = "CATALOG"
    COMPILER = "COMPILER"
    ENGINE = "ENGINE"
    SCHEDULER = "SCHEDULER"
    RUNTIME = "RUNTIME"
    LLM_RUNTIME = "LLM_RUNTIME"
    INTERFACE = "INTERFACE"
    PLUGIN = "PLUGIN"
    CONNECTOR = "CONNECTOR"
    PACKAGE = "PACKAGE"
    WORKFLOW = "WORKFLOW"
    TASK = "TASK"
    SECURITY = "SECURITY"
    RESOURCE = "RESOURCE"
    MEMORY = "MEMORY"
    KNOWLEDGE = "KNOWLEDGE"
    API = "API"
    DATABASE = "DATABASE"
    UTILITY = "UTILITY"
    CUSTOM = "CUSTOM"


class ComponentStatus(str, Enum):
    REGISTERED = "REGISTERED"
    ACTIVATED = "ACTIVATED"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    FAULT = "FAULT"
    UNKNOWN = "UNKNOWN"


class LifecycleStage(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    REGISTERED = "REGISTERED"
    CONFIGURED = "CONFIGURED"
    DEPENDENCY_RESOLVED = "DEPENDENCY_RESOLVED"
    ACTIVATED = "ACTIVATED"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"
    REMOVED = "REMOVED"


_COMPONENT_ID_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
_COMPONENT_NAME_RE = re.compile(r"^[a-z0-9_]+$")
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


# ======================================================================
# Errors
# ======================================================================

class ManifestError(Exception):
    code = "ERR_MANIFEST"


class DuplicateRegistrationError(ManifestError):
    code = "ERR_DUPLICATE_REGISTRATION"


class CyclicDependencyError(ManifestError):
    code = "ERR_CYCLIC_DEPENDENCY"


class VersionMismatchError(ManifestError):
    code = "ERR_VERSION_MISMATCH"


class UnknownComponentError(ManifestError):
    code = "ERR_UNKNOWN_COMPONENT"


class ValidationFailedError(ManifestError):
    code = "ERR_VALIDATION_FAILED"


# ======================================================================
# Data Contracts
# ======================================================================

@dataclass
class ComponentDependency:
    target_component_id: str
    version_range: str
    optional: bool = False


@dataclass
class ComponentEvents:
    emits: List[str] = field(default_factory=list)
    subscribes: List[str] = field(default_factory=list)


@dataclass
class ResourceRequirements:
    cpu_units: float = 0.1
    memory_mb: int = 32
    gpu_vram_mb: int = 0


@dataclass
class ComponentMetadata:
    component_id: str
    component_name: str
    display_name: str
    description: str
    category: ComponentCategory
    version: str
    status: ComponentStatus = ComponentStatus.REGISTERED
    owner: str = "hojaiga"
    maintainer: str = "hojaiga"
    dependencies: List[ComponentDependency] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    services: List[str] = field(default_factory=list)
    events: ComponentEvents = field(default_factory=ComponentEvents)
    states: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    config_file: str = ""
    documentation_file: str = ""
    implementation_location: str = ""
    health_status: HealthStatus = HealthStatus.UNKNOWN
    resource_requirements: ResourceRequirements = field(default_factory=ResourceRequirements)
    security_level: int = 0
    permissions: List[str] = field(default_factory=list)
    creation_date: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    last_updated: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    compatibility_version: str = "1.0.0"
    deprecated: bool = False
    lifecycle_status: LifecycleStage = LifecycleStage.CREATED

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["status"] = self.status.value
        d["health_status"] = self.health_status.value
        d["lifecycle_status"] = self.lifecycle_status.value
        return d


@dataclass
class ValidationReport:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class RegistrationResponse:
    success: bool
    component_id: str
    errors: List[str] = field(default_factory=list)


@dataclass
class DiscoveryQuery:
    component_id: Optional[str] = None
    category: Optional[ComponentCategory] = None
    capability: Optional[str] = None
    health_status: Optional[HealthStatus] = None
    owner: Optional[str] = None


# ======================================================================
# Manifest Validator (side-effect-free)
# ======================================================================

class ManifestValidator:
    """Pure validation. Never mutates state, never executes I/O side effects."""

    def validate(self, meta: ComponentMetadata, existing_ids: Set[str]) -> ValidationReport:
        errors: List[str] = []
        warnings: List[str] = []

        if not _COMPONENT_ID_RE.match(meta.component_id):
            errors.append(f"ERR_INVALID_ID: {meta.component_id}")
        if not _COMPONENT_NAME_RE.match(meta.component_name):
            errors.append(f"ERR_INVALID_NAME: {meta.component_name}")
        if len(meta.display_name) < 3:
            errors.append("ERR_DISPLAY_NAME_TOO_SHORT")
        if len(meta.description) < 10:
            errors.append("ERR_DESCRIPTION_TOO_SHORT")
        if not _SEMVER_RE.match(meta.version):
            errors.append(f"ERR_INVALID_SEMVER: {meta.version}")
        if meta.component_id in existing_ids:
            errors.append("ERR_DUPLICATE_REGISTRATION")
        for dep in meta.dependencies:
            if not dep.target_component_id:
                errors.append("ERR_EMPTY_DEPENDENCY_TARGET")
        if meta.security_level < 0:
            errors.append("ERR_NEGATIVE_SECURITY_LEVEL")
        if not meta.implementation_location:
            warnings.append("WARN_MISSING_IMPLEMENTATION_LOCATION")
        if not meta.documentation_file:
            warnings.append("WARN_MISSING_DOCUMENTATION_FILE")

        return ValidationReport(valid=len(errors) == 0, errors=errors, warnings=warnings)


# ======================================================================
# SemVer utilities
# ======================================================================

def parse_semver(v: str) -> Tuple[int, int, int]:
    m = _SEMVER_RE.match(v)
    if not m:
        raise VersionMismatchError(f"Invalid SemVer: {v}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def satisfies_range(version: str, version_range: str) -> bool:
    """Supports '*', '^x.y.z', '~x.y.z', '>=x.y.z', exact 'x.y.z'."""
    if version_range in ("*", "", None):
        return True
    v_major, v_minor, v_patch = parse_semver(version)
    if version_range.startswith("^"):
        r_major, r_minor, r_patch = parse_semver(version_range[1:])
        if v_major != r_major:
            return False
        return (v_minor, v_patch) >= (r_minor, r_patch)
    if version_range.startswith("~"):
        r_major, r_minor, r_patch = parse_semver(version_range[1:])
        return v_major == r_major and v_minor == r_minor and v_patch >= r_patch
    if version_range.startswith(">="):
        return (v_major, v_minor, v_patch) >= parse_semver(version_range[2:])
    return version == version_range


class VersionRegistry:
    """SemVer Matrix Engine + Breaking Change Guard + Compatibility Map."""

    def __init__(self) -> None:
        self._matrix: Dict[str, List[str]] = {}
        self._compat_map: Dict[str, Set[str]] = {}

    def record(self, component_id: str, version: str) -> None:
        parse_semver(version)
        self._matrix.setdefault(component_id, [])
        if version not in self._matrix[component_id]:
            self._matrix[component_id].append(version)

    def is_breaking_change(self, old_version: str, new_version: str) -> bool:
        return parse_semver(old_version)[0] != parse_semver(new_version)[0]

    def register_compatibility(self, component_id: str, compatible_with: str) -> None:
        self._compat_map.setdefault(component_id, set()).add(compatible_with)

    def is_compatible(self, component_id: str, other_id: str) -> bool:
        return other_id in self._compat_map.get(component_id, set())

    def history(self, component_id: str) -> List[str]:
        return list(self._matrix.get(component_id, []))


# ======================================================================
# Dependency Registry (DAG + Tarjan SCC cycle detection)
# ======================================================================

class DependencyRegistry:
    def __init__(self) -> None:
        self._edges: Dict[str, List[ComponentDependency]] = {}
        self._lock = threading.RLock()

    def declare(self, component_id: str, dependencies: List[ComponentDependency]) -> None:
        with self._lock:
            self._edges[component_id] = list(dependencies)

    def remove(self, component_id: str) -> None:
        with self._lock:
            self._edges.pop(component_id, None)

    def graph(self) -> Dict[str, List[str]]:
        with self._lock:
            return {k: [d.target_component_id for d in v] for k, v in self._edges.items()}

    def detect_cycles(self) -> List[List[str]]:
        """Tarjan's strongly connected components; SCCs of size > 1, or a
        self-loop, indicate a cyclic dependency."""
        graph = self.graph()
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

            for successor in graph.get(node, []):
                if successor not in index:
                    strongconnect(successor)
                    lowlink[node] = min(lowlink[node], lowlink[successor])
                elif on_stack.get(successor):
                    lowlink[node] = min(lowlink[node], index[successor])

            if lowlink[node] == index[node]:
                scc: List[str] = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    scc.append(w)
                    if w == node:
                        break
                if len(scc) > 1 or (len(scc) == 1 and scc[0] in graph.get(scc[0], [])):
                    result.append(scc)

        for n in list(graph.keys()):
            if n not in index:
                strongconnect(n)
        return result

    def validate_no_cycles(self) -> None:
        cycles = self.detect_cycles()
        if cycles:
            raise CyclicDependencyError(f"ERR_CYCLIC_DEPENDENCY: {cycles}")

    def resolve(self, component_id: str, resolver: Callable[[str], Optional[str]]) -> List[str]:
        """Resolve dependency versions via resolver(component_id) -> version.
        Returns list of unresolved dependency ids (missing & not optional)."""
        unresolved: List[str] = []
        for dep in self._edges.get(component_id, []):
            resolved_version = resolver(dep.target_component_id)
            if resolved_version is None:
                if not dep.optional:
                    unresolved.append(dep.target_component_id)
                continue
            if not satisfies_range(resolved_version, dep.version_range):
                unresolved.append(dep.target_component_id)
        return unresolved


# ======================================================================
# Health Registry
# ======================================================================

class HealthRegistry:
    def __init__(self) -> None:
        self._health: Dict[str, HealthStatus] = {}
        self._heartbeats: Dict[str, float] = {}
        self._lock = threading.RLock()
        self.stale_after_seconds: float = 60.0

    def report(self, component_id: str, status: HealthStatus) -> None:
        with self._lock:
            self._health[component_id] = status
            self._heartbeats[component_id] = time.time()

    def get(self, component_id: str) -> HealthStatus:
        with self._lock:
            last = self._heartbeats.get(component_id)
            if last is not None and (time.time() - last) > self.stale_after_seconds:
                self._health[component_id] = HealthStatus.UNKNOWN
            return self._health.get(component_id, HealthStatus.UNKNOWN)

    def overview(self) -> Dict[str, str]:
        with self._lock:
            return {k: self.get(k).value for k in self._health.keys()}

    def remove(self, component_id: str) -> None:
        with self._lock:
            self._health.pop(component_id, None)
            self._heartbeats.pop(component_id, None)


# ======================================================================
# Configuration / Documentation / Security registries
# ======================================================================

class ConfigurationRegistry:
    def __init__(self) -> None:
        self._config: Dict[str, Dict[str, Any]] = {}
        self._secret_refs: Dict[str, List[str]] = {}

    def bind(self, component_id: str, config_file: str, env: Optional[Dict[str, str]] = None) -> None:
        self._config[component_id] = {"config_file": config_file, "env": env or {}}

    def secrets_ref(self, component_id: str, refs: List[str]) -> None:
        self._secret_refs[component_id] = refs

    def get(self, component_id: str) -> Optional[Dict[str, Any]]:
        return self._config.get(component_id)


class DocumentationRegistry:
    def __init__(self) -> None:
        self._docs: Dict[str, str] = {}

    def map(self, component_id: str, documentation_file: str) -> None:
        self._docs[component_id] = documentation_file

    def get(self, component_id: str) -> Optional[str]:
        return self._docs.get(component_id)

    def stale(self, exists_fn: Callable[[str], bool]) -> List[str]:
        return [cid for cid, path in self._docs.items() if path and not exists_fn(path)]


class SecurityRegistry:
    def __init__(self) -> None:
        self._clearance: Dict[str, int] = {}
        self._permissions: Dict[str, List[str]] = {}

    def set_clearance(self, component_id: str, level: int, permissions: List[str]) -> None:
        self._clearance[component_id] = level
        self._permissions[component_id] = permissions

    def check(self, component_id: str, required_level: int, required_permission: Optional[str] = None) -> bool:
        level_ok = self._clearance.get(component_id, 0) >= required_level
        if required_permission is None:
            return level_ok
        return level_ok and required_permission in self._permissions.get(component_id, [])


# ======================================================================
# Audit Interface (append-only, hash-chained)
# ======================================================================

class AuditInterface:
    def __init__(self, log_path: Optional[Path] = None) -> None:
        self._entries: List[Dict[str, Any]] = []
        self._last_hash: str = "0" * 64
        self._lock = threading.RLock()
        self._log_path = log_path

    def record(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            entry = {
                "event_id": str(uuid.uuid4()),
                "event_type": event_type,
                "payload": payload,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "prev_hash": self._last_hash,
            }
            digest = hashlib.sha256(json.dumps(entry, sort_keys=True, default=str).encode()).hexdigest()
            entry["hash"] = digest
            self._last_hash = digest
            self._entries.append(entry)
            if self._log_path:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, default=str) + "\n")
            return entry

    def verify_chain(self) -> bool:
        with self._lock:
            prev = "0" * 64
            for entry in self._entries:
                if entry["prev_hash"] != prev:
                    return False
                check = dict(entry)
                digest = check.pop("hash")
                recomputed = hashlib.sha256(json.dumps(check, sort_keys=True, default=str).encode()).hexdigest()
                if recomputed != digest:
                    return False
                prev = digest
            return True

    def history(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._entries)


# ======================================================================
# Component Registry (primary index)
# ======================================================================

class ComponentRegistry:
    def __init__(self, dependency_registry: DependencyRegistry, version_registry: VersionRegistry) -> None:
        self._components: Dict[str, ComponentMetadata] = {}
        self._category_index: Dict[ComponentCategory, Set[str]] = {c: set() for c in ComponentCategory}
        self._capability_index: Dict[str, Set[str]] = {}
        self._owner_index: Dict[str, Set[str]] = {}
        self._dependency_registry = dependency_registry
        self._version_registry = version_registry
        self._lock = threading.RLock()

    def exists(self, component_id: str) -> bool:
        with self._lock:
            return component_id in self._components

    def get(self, component_id: str) -> ComponentMetadata:
        with self._lock:
            comp = self._components.get(component_id)
            if comp is None:
                raise UnknownComponentError(component_id)
            return comp

    def register(self, meta: ComponentMetadata) -> None:
        with self._lock:
            self._components[meta.component_id] = meta
            self._category_index[meta.category].add(meta.component_id)
            for cap in meta.capabilities:
                self._capability_index.setdefault(cap, set()).add(meta.component_id)
            self._owner_index.setdefault(meta.owner, set()).add(meta.component_id)
            self._dependency_registry.declare(meta.component_id, meta.dependencies)
            self._version_registry.record(meta.component_id, meta.version)

    def unregister(self, component_id: str) -> None:
        with self._lock:
            meta = self._components.pop(component_id, None)
            if meta is None:
                return
            self._category_index[meta.category].discard(component_id)
            for cap in meta.capabilities:
                self._capability_index.get(cap, set()).discard(component_id)
            self._owner_index.get(meta.owner, set()).discard(component_id)
            self._dependency_registry.remove(component_id)

    def query(self, q: DiscoveryQuery) -> List[ComponentMetadata]:
        with self._lock:
            results = set(self._components.keys())
            if q.component_id:
                results &= {q.component_id} if q.component_id in self._components else set()
            if q.category:
                results &= self._category_index.get(q.category, set())
            if q.capability:
                results &= self._capability_index.get(q.capability, set())
            if q.owner:
                results &= self._owner_index.get(q.owner, set())
            comps = [self._components[cid] for cid in results]
            if q.health_status:
                comps = [c for c in comps if c.health_status == q.health_status]
            return sorted(comps, key=lambda c: c.component_id)

    def all(self) -> List[ComponentMetadata]:
        with self._lock:
            return list(self._components.values())

    def count(self) -> int:
        with self._lock:
            return len(self._components)


# ======================================================================
# Manifest Loader / Exporter / Importer
# ======================================================================

class ManifestLoader:
    def load(self, path: Path) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


class ManifestExporter:
    def export(self, snapshot: Dict[str, Any], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, default=str)


class ManifestImporter:
    def diff(self, current: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
        current_ids = set(current.get("components", {}).keys())
        incoming_ids = set(incoming.get("components", {}).keys())
        return {
            "added": sorted(incoming_ids - current_ids),
            "removed": sorted(current_ids - incoming_ids),
            "common": sorted(current_ids & incoming_ids),
        }


# ======================================================================
# Manifest Core — Orchestrator
# ======================================================================

class ManifestCore:
    """Central execution engine: registration, loading, discovery, state sync.

    Sockets:  ManifestSocket, AuditSocket
    Pipelines: RegistrationPipeline, AuditPipeline
    Recovery: on state-tree corruption, falls back to last exported snapshot.
    """

    MANIFEST_VERSION = "33.1.0"
    SYSTEM_IDENTITY = "hojaiga.aos.system_manifest"

    def __init__(self, audit_log_path: Optional[Path] = None) -> None:
        self.dependency_registry = DependencyRegistry()
        self.version_registry = VersionRegistry()
        self.component_registry = ComponentRegistry(self.dependency_registry, self.version_registry)
        self.health_registry = HealthRegistry()
        self.configuration_registry = ConfigurationRegistry()
        self.documentation_registry = DocumentationRegistry()
        self.security_registry = SecurityRegistry()
        self.validator = ManifestValidator()
        self.audit = AuditInterface(audit_log_path)
        self.loader = ManifestLoader()
        self.exporter = ManifestExporter()
        self.importer = ManifestImporter()
        self._lock = threading.RLock()
        self._boot_time = time.time()

    # -- Registration -----------------------------------------------
    def register_component(self, meta: ComponentMetadata) -> RegistrationResponse:
        with self._lock:
            existing_ids = set(c.component_id for c in self.component_registry.all())
            report = self.validator.validate(meta, existing_ids)
            if not report.valid:
                self.audit.record("REGISTRATION_REJECTED", {"component_id": meta.component_id, "errors": report.errors})
                return RegistrationResponse(success=False, component_id=meta.component_id, errors=report.errors)

            self.component_registry.register(meta)
            try:
                self.dependency_registry.validate_no_cycles()
            except CyclicDependencyError as exc:
                self.component_registry.unregister(meta.component_id)
                self.audit.record("REGISTRATION_REJECTED", {"component_id": meta.component_id, "errors": [str(exc)]})
                return RegistrationResponse(success=False, component_id=meta.component_id, errors=[str(exc)])
            self.configuration_registry.bind(meta.component_id, meta.config_file)
            self.documentation_registry.map(meta.component_id, meta.documentation_file)
            self.security_registry.set_clearance(meta.component_id, meta.security_level, meta.permissions)
            self.health_registry.report(meta.component_id, meta.health_status)

            self.audit.record("COMPONENT_REGISTERED", {"component_id": meta.component_id, "version": meta.version})
            return RegistrationResponse(success=True, component_id=meta.component_id, errors=[])

    def unregister_component(self, component_id: str) -> None:
        with self._lock:
            self.component_registry.unregister(component_id)
            self.health_registry.remove(component_id)
            self.audit.record("COMPONENT_REMOVED", {"component_id": component_id})

    def update_health(self, component_id: str, status: HealthStatus) -> None:
        if not self.component_registry.exists(component_id):
            raise UnknownComponentError(component_id)
        self.health_registry.report(component_id, status)
        self.component_registry.get(component_id).health_status = status
        self.audit.record("HEALTH_UPDATED", {"component_id": component_id, "status": status.value})

    def transition_lifecycle(self, component_id: str, stage: LifecycleStage) -> None:
        meta = self.component_registry.get(component_id)
        meta.lifecycle_status = stage
        meta.last_updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.audit.record("LIFECYCLE_TRANSITION", {"component_id": component_id, "stage": stage.value})

    # -- Discovery -----------------------------------------------
    def discover(self, query: DiscoveryQuery) -> List[ComponentMetadata]:
        return self.component_registry.query(query)

    # -- Dependency resolution -----------------------------------
    def resolve_dependencies(self, component_id: str) -> List[str]:
        def resolver(cid: str) -> Optional[str]:
            if self.component_registry.exists(cid):
                return self.component_registry.get(cid).version
            return None
        return self.dependency_registry.resolve(component_id, resolver)

    # -- Topology / summary ----------------------------------------
    def architecture_summary(self) -> Dict[str, Any]:
        comps = self.component_registry.all()
        by_category: Dict[str, int] = {}
        for c in comps:
            by_category[c.category.value] = by_category.get(c.category.value, 0) + 1
        return {
            "total_components": len(comps),
            "by_category": by_category,
            "dependency_graph": self.dependency_registry.graph(),
            "health_overview": self.health_registry.overview(),
            "uptime_seconds": round(time.time() - self._boot_time, 3),
        }

    # -- Snapshot / persistence -------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        return {
            "system_identity": self.SYSTEM_IDENTITY,
            "manifest_version": self.MANIFEST_VERSION,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "components": {c.component_id: c.to_dict() for c in self.component_registry.all()},
            "dependency_graph": self.dependency_registry.graph(),
            "health_overview": self.health_registry.overview(),
            "audit_chain_valid": self.audit.verify_chain(),
        }

    def export_manifest(self, path: Path) -> None:
        self.exporter.export(self.snapshot(), path)
        self.audit.record("MANIFEST_EXPORTED", {"path": str(path)})

    def import_manifest(self, path: Path) -> Dict[str, Any]:
        incoming = self.loader.load(path)
        diff = self.importer.diff(self.snapshot(), incoming)
        self.audit.record("MANIFEST_IMPORTED", {"path": str(path), "diff": diff})
        return diff


# ======================================================================
# System Manifest — Public Facade (single organ entry point)
# ======================================================================

class SystemManifest:
    """Organ 33 public facade. All external organs interact only through
    this facade's documented sockets/pipelines — never through internal
    registries directly."""

    def __init__(self, audit_log_path: Optional[str] = None) -> None:
        self._core = ManifestCore(Path(audit_log_path) if audit_log_path else None)
        self._socket_subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}

    # -- Socket layer (pub/sub) --------------------------------------
    def subscribe(self, socket_name: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        self._socket_subscribers.setdefault(socket_name, []).append(handler)

    def _publish(self, socket_name: str, message: Dict[str, Any]) -> None:
        for handler in self._socket_subscribers.get(socket_name, []):
            handler(message)

    # -- RegistrationPipeline -----------------------------------------
    def register(self, meta: ComponentMetadata) -> RegistrationResponse:
        response = self._core.register_component(meta)
        self._publish("RegistrationSocket", asdict(response))
        return response

    def unregister(self, component_id: str) -> None:
        self._core.unregister_component(component_id)
        self._publish("RegistrationSocket", {"removed": component_id})

    # -- HealthPipeline --------------------------------------------
    def report_health(self, component_id: str, status: HealthStatus) -> None:
        self._core.update_health(component_id, status)
        self._publish("HealthSocket", {"component_id": component_id, "status": status.value})

    # -- DiscoveryPipeline -------------------------------------------
    def discover(self, **kwargs: Any) -> List[Dict[str, Any]]:
        query = DiscoveryQuery(**kwargs)
        return [c.to_dict() for c in self._core.discover(query)]

    def get_component(self, component_id: str) -> Dict[str, Any]:
        return self._core.component_registry.get(component_id).to_dict()

    # -- DependencyPipeline -------------------------------------------
    def resolve_dependencies(self, component_id: str) -> List[str]:
        return self._core.resolve_dependencies(component_id)

    def dependency_graph(self) -> Dict[str, List[str]]:
        return self._core.dependency_registry.graph()

    def has_cycles(self) -> bool:
        return len(self._core.dependency_registry.detect_cycles()) > 0

    # -- Lifecycle -------------------------------------------------
    def transition(self, component_id: str, stage: LifecycleStage) -> None:
        self._core.transition_lifecycle(component_id, stage)

    # -- Architecture / summary ---------------------------------------
    def architecture_summary(self) -> Dict[str, Any]:
        return self._core.architecture_summary()

    # -- Persistence (ManifestSocket) ---------------------------------
    def export_to(self, path: str) -> None:
        self._core.export_manifest(Path(path))

    def import_from(self, path: str) -> Dict[str, Any]:
        return self._core.import_manifest(Path(path))

    def snapshot(self) -> Dict[str, Any]:
        return self._core.snapshot()

    # -- Audit -------------------------------------------------------
    def audit_history(self) -> List[Dict[str, Any]]:
        return self._core.audit.history()

    def audit_chain_valid(self) -> bool:
        return self._core.audit.verify_chain()

    # -- Async task-scheduler integration (non-blocking bulk ops) -----
    async def register_many(self, metas: List[ComponentMetadata]) -> List[RegistrationResponse]:
        loop = asyncio.get_event_loop()
        return await asyncio.gather(*[loop.run_in_executor(None, self.register, m) for m in metas])


__all__ = [
    "SystemManifest", "ManifestCore", "ComponentMetadata", "ComponentDependency",
    "ComponentEvents", "ResourceRequirements", "ComponentCategory", "ComponentStatus",
    "HealthStatus", "LifecycleStage", "DiscoveryQuery", "RegistrationResponse",
    "ValidationReport", "ManifestValidator", "VersionRegistry", "DependencyRegistry",
    "HealthRegistry", "ConfigurationRegistry", "DocumentationRegistry",
    "SecurityRegistry", "AuditInterface", "ComponentRegistry",
    "ManifestError", "DuplicateRegistrationError", "CyclicDependencyError",
    "VersionMismatchError", "UnknownComponentError", "ValidationFailedError",
    "satisfies_range", "parse_semver",
]
