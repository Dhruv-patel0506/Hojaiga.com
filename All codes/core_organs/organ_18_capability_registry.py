"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 18
Name: Capability Registry

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Capability Registry]
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
Dependencies: math, enum, typing, __future__, collections...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_18_capability_registry.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
==============================================================================
HOJAIGA AUTOMATION OS — CAPABILITY REGISTRY ORGAN
==============================================================================
Document ID   : SPEC-AOS-CAPREG-001
Organ         : Capability Registry
Authority     : Constitution -> Law Book -> Diagrams -> Legacy Migration
                Guide -> Policy Manual -> Master Architecture Blueprint ->
                Organ Specification -> Capability Registry Architecture
                Specification (this organ's authoritative spec)
Status        : Production implementation, single importable module.

------------------------------------------------------------------------------
PRE-CODE ARCHITECTURE DIAGRAM (Component View)
------------------------------------------------------------------------------
                        Hojaiga Brain / Any Organ
                                  |
                          Capability Query
                                  |
                                  v
+----------------------------------------------------------------------+
|                        CAPABILITY REGISTRY CORE                      |
|                                                                        |
|   +----------------+   +------------------+   +--------------------+ |
|   | L1 Cache       |-->| Search Engine    |-->| Permissions &      | |
|   | Manager        |   | (attr/tag/semantic)| | Validator          | |
|   +----------------+   +------------------+   +--------------------+ |
|            ^                     |                       |            |
|            |                     v                       v            |
|   +----------------+   +------------------+   +--------------------+ |
|   | Capability DB  |<--| Compatibility    |   | Ranking Engine     | |
|   | (records+index)|   | Validator        |-->| (weighted scoring) | |
|   +----------------+   +------------------+   +--------------------+ |
|            ^                                            |             |
|            |                                            v             |
|   +----------------+   +------------------+   +--------------------+ |
|   | Dynamic Reg /  |   | Health Monitor   |   | Capability Resolver| |
|   | Removal Mgr    |   | (heartbeats)     |   | -> InvocationHandle| |
|   +----------------+   +------------------+   +--------------------+ |
|            ^                     |                       |            |
|            |                     v                       v            |
|   +----------------+   +------------------+   +--------------------+ |
|   | History Mgr    |   | Metrics Mgr      |   | Audit Manager      | |
|   | (append only)  |   | (telemetry)      |   | (tamper evident)   | |
|   +----------------+   +------------------+   +--------------------+ |
|                                                                        |
|   Sockets: Capability, Discovery, Search, Registration, Validation,   |
|            Permission, Ranking, Health                                |
|   Pipelines: Registration, Search, Validation, Ranking, Discovery,    |
|              Update, Removal, Recovery, Monitoring                    |
+----------------------------------------------------------------------+
                                  |
                     Selected Provider Record / Handle
                                  v
                        Hojaiga Brain / Calling Organ

------------------------------------------------------------------------------
ACTUAL CODE DIAGRAM (Runtime Sequence — resolve_capability)
------------------------------------------------------------------------------
Caller -> CapabilityRegistryCore.process_query(QueryDTO)
       -> CacheManager.get(hash)                      [cache hit -> return]
       -> SearchEngine.search(QueryDTO)                -> candidates
       -> PermissionsManager.filter(candidates, scope) -> permitted
       -> CapabilityValidator.validate(permitted)      -> valid
       -> CompatibilityValidator.filter(valid)         -> compatible
       -> HealthMonitor.filter_healthy(compatible)     -> healthy
       -> RankingEngine.rank(healthy)                  -> ranked
       -> CapabilityResolver.build_handle(ranked[0])   -> InvocationHandle
       -> CacheManager.put(hash, handle)
       -> AuditManager.record(event)
       -> return handle

Registration Sequence:
Provider -> RegistrationPipeline.submit(spec)
         -> CapabilityValidator.validate_spec(spec)
         -> CompatibilityValidator.validate_spec(spec)
         -> PermissionsManager.check_namespace(spec)
         -> CapabilityDatabase.insert(record)
         -> SearchEngine.index(record)
         -> CacheManager.invalidate(record.capability_name)
         -> HistoryManager.record(CREATED, record)
         -> AuditManager.record(REGISTERED, record)
==============================================================================
"""


import hashlib
import json
import re
import threading
import time
import uuid
import asyncio
import os
from abc import ABC, abstractmethod
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ==============================================================================
# SECTION 1 — ENUMERATIONS & CONSTANTS
# ==============================================================================

class ProviderType(str, Enum):
    ORGAN = "ORGAN"
    CONNECTOR = "CONNECTOR"
    PLUGIN = "PLUGIN"
    RUNTIME = "RUNTIME"
    HARDWARE = "HARDWARE"
    APPLICATION = "APPLICATION"
    WEB_APPLICATION = "WEB_APPLICATION"


class ConfidenceLevel(str, Enum):
    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CONFIRMED = "CONFIRMED"


class CapabilityStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    DEPRECATED = "DEPRECATED"
    OFFLINE = "OFFLINE"
    TOMBSTONED = "TOMBSTONED"


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    OFFLINE = "OFFLINE"


class PermissionLevel(str, Enum):
    PUBLIC = "LEVEL_0_PUBLIC"
    INTERNAL = "LEVEL_1_INTERNAL"
    PRIVILEGED = "LEVEL_2_PRIVILEGED"
    GOVERNANCE = "LEVEL_3_GOVERNANCE"


class ValidationResult(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    DEGRADED = "DEGRADED"


class HistoryEventType(str, Enum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    DEGRADED = "DEGRADED"
    DEPRECATED = "DEPRECATED"
    REMOVED = "REMOVED"


MAX_QUERY_CANDIDATES = 100
DEFAULT_TTL_SECONDS = 300
L1_CACHE_CAPACITY = 10_000
MISSED_HEARTBEATS_OFFLINE_LIMIT = 3
RESERVED_NAMESPACES = ("organ.brain", "kernel.", "security.")

DEFAULT_WEIGHTS = {
    "health": 0.30,
    "performance": 0.20,
    "user_preference": 0.15,
    "static_priority": 0.10,
    "version_precision": 0.10,
    "availability": 0.10,
    "hardware_acceleration": 0.05,
    "local_app_preference": 0.15,
    "installation_penalty": -0.20,
    "confidence": 0.10,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ==============================================================================
# SECTION 2 — DATA CONTRACTS (DTOs)
# ==============================================================================

@dataclass
class PerformanceMetrics:
    p95_latency_ms: float = 5.0
    max_throughput_rps: float = 100.0
    memory_footprint_mb: float = 32.0
    hardware_accelerated: bool = False


@dataclass
class CompatibilityProfile:
    os_constraints: List[str] = field(default_factory=list)
    hardware_requirements: List[str] = field(default_factory=list)
    runtime_requirements: List[str] = field(default_factory=list)


@dataclass
class CapabilitySpecDTO:
    capability_name: str
    description: str
    provider: str
    provider_type: ProviderType
    version: str
    dependencies: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    priority: int = 500
    supported_inputs: Dict[str, Any] = field(default_factory=dict)
    supported_outputs: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    category: str = "General"
    owner: str = "unknown"
    performance_metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    compatibility: CompatibilityProfile = field(default_factory=CompatibilityProfile)
    permission_level: PermissionLevel = PermissionLevel.INTERNAL
    provider_secret_key: Optional[str] = None
    capability_id: uuid.UUID = field(default_factory=uuid.uuid4)
    confidence_level: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    needs_installation: bool = False
    application_aliases: List[str] = field(default_factory=list)
    executable_path: Optional[str] = None
    is_web_app: bool = False


@dataclass
class CapabilityRecord:
    capability_id: uuid.UUID
    capability_name: str
    description: str
    provider: str
    provider_type: ProviderType
    version: str
    status: CapabilityStatus
    dependencies: List[str]
    permissions: List[str]
    priority: int
    supported_inputs: Dict[str, Any]
    supported_outputs: Dict[str, Any]
    performance_metrics: PerformanceMetrics
    health_status: HealthStatus
    compatibility: CompatibilityProfile
    tags: List[str]
    category: str
    owner: str
    permission_level: PermissionLevel
    registration_date: str
    last_updated: str
    signature: str = ""
    availability_ratio: float = 1.0
    missed_heartbeats: int = 0
    pinned_by_user: bool = False
    confidence_level: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    needs_installation: bool = False
    application_aliases: List[str] = field(default_factory=list)
    executable_path: Optional[str] = None
    is_web_app: bool = False


@dataclass
class SearchQueryDTO:
    name: Optional[str] = None
    category: Optional[str] = None
    provider: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    version_range: Optional[str] = None
    max_p95_latency_ms: Optional[float] = None
    required_health: Tuple[HealthStatus, ...] = (HealthStatus.HEALTHY, HealthStatus.DEGRADED)
    caller_scope: PermissionLevel = PermissionLevel.INTERNAL
    caller_permissions: List[str] = field(default_factory=list)
    semantic_text: Optional[str] = None


@dataclass
class CapabilityInvocationHandle:
    capability_id: uuid.UUID
    capability_name: str
    provider_endpoint: str
    selected_version: str
    auth_token: str
    score: float = 0.0


@dataclass
class AuditRecord:
    trace_id: str
    timestamp: str
    organ: str
    module: str
    event_type: str
    log_level: str
    payload: Dict[str, Any]
    signature: str = ""


@dataclass
class HistoryEntry:
    event_type: HistoryEventType
    capability_id: uuid.UUID
    timestamp: str
    snapshot: Dict[str, Any]


# ==============================================================================
# SECTION 3 — INTERFACES (SOCKET / PUBLIC CONTRACTS)
# ==============================================================================

class ICapabilityResolver(ABC):
    @abstractmethod
    def resolve_capability(self, query_payload: Dict[str, Any], caller_scope: str) -> CapabilityInvocationHandle:
        ...


class ICapabilityRegistryManager(ABC):
    @abstractmethod
    def register_capability(self, spec: CapabilitySpecDTO) -> bool:
        ...

    @abstractmethod
    def deregister_capability(self, capability_id: uuid.UUID, provider_key: str) -> bool:
        ...


class ICapabilityRankingEngine(ABC):
    @abstractmethod
    def compute_ranks(self, candidates: List[CapabilityRecord]) -> List[CapabilityRecord]:
        ...


class ICapabilitySocket(ABC):
    """Base contract for all registry sockets."""

    @abstractmethod
    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        ...


class UnresolvedCapabilityException(Exception):
    pass


class CapabilityValidationError(Exception):
    pass


class CapabilitySecurityError(Exception):
    pass


# ==============================================================================
# SECTION 4 — UTILITIES: SEMVER, SIGNATURES
# ==============================================================================

class SemVer:
    _PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z\.-]+)?(?:\+[0-9A-Za-z\.-]+)?$")

    @classmethod
    def parse(cls, version: str) -> Tuple[int, int, int]:
        match = cls._PATTERN.match(version.strip())
        if not match:
            raise CapabilityValidationError(f"Invalid SemVer string: {version}")
        return int(match.group(1)), int(match.group(2)), int(match.group(3))

    @classmethod
    def compare(cls, a: str, b: str) -> int:
        pa, pb = cls.parse(a), cls.parse(b)
        if pa == pb:
            return 0
        return -1 if pa < pb else 1

    @classmethod
    def satisfies(cls, version: str, expression: Optional[str]) -> bool:
        if not expression:
            return True
        clauses = expression.replace(",", " ").split()
        for clause in clauses:
            m = re.match(r"(>=|<=|>|<|==)?\s*(\d+\.\d+\.\d+)", clause)
            if not m:
                continue
            op, target = m.group(1) or "==", m.group(2)
            cmp = cls.compare(version, target)
            if op == ">=" and not cmp >= 0:
                return False
            if op == "<=" and not cmp <= 0:
                return False
            if op == ">" and not cmp > 0:
                return False
            if op == "<" and not cmp < 0:
                return False
            if op == "==" and not cmp == 0:
                return False
        return True

    @classmethod
    def precision_score(cls, requested: Optional[str], actual: str) -> float:
        if not requested:
            return 1.0
        try:
            rq, av = cls.parse(requested), cls.parse(actual)
        except CapabilityValidationError:
            return 0.5
        if rq == av:
            return 1.0
        if rq[0] == av[0] and rq[1] == av[1]:
            return 0.8
        if rq[0] == av[0]:
            return 0.6
        return 0.2


def compute_signature(record: CapabilityRecord) -> str:
    payload = json.dumps(
        {
            "capability_id": str(record.capability_id),
            "capability_name": record.capability_name,
            "provider": record.provider,
            "version": record.version,
            "supported_inputs": record.supported_inputs,
            "supported_outputs": record.supported_outputs,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ==============================================================================
# SECTION 5 — L1 CACHE MANAGER
# ==============================================================================

class L1CacheManager:
    """Fast in-memory LRU cache with TTL for resolved query hashes."""

    def __init__(self, capacity: int = L1_CACHE_CAPACITY, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._capacity = capacity
        self._ttl = ttl_seconds
        self._store: "OrderedDict[str, Tuple[float, Any]]" = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def hash_query(query: SearchQueryDTO) -> str:
        payload = json.dumps(
            {
                "name": query.name,
                "category": query.category,
                "provider": query.provider,
                "tags": sorted(query.tags),
                "version_range": query.version_range,
                "semantic_text": query.semantic_text,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.time() > expires_at:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.time() + self._ttl, value)
            self._store.move_to_end(key)
            while len(self._store) > self._capacity:
                self._store.popitem(last=False)

    def invalidate(self, name_prefix: str) -> None:
        with self._lock:
            keys = list(self._store.keys())
            for k in keys:
                del self._store[k]  # coarse invalidation on any mutation

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# ==============================================================================
# SECTION 6 — CAPABILITY DATABASE (RECORD STORE + INVERTED INDEX)
# ==============================================================================

class CapabilityDatabase:
    """Authoritative in-memory record store with inverted indices."""

    def __init__(self) -> None:
        self._records: Dict[uuid.UUID, CapabilityRecord] = {}
        self._by_name: Dict[str, List[uuid.UUID]] = defaultdict(list)
        self._by_tag: Dict[str, List[uuid.UUID]] = defaultdict(list)
        self._by_category: Dict[str, List[uuid.UUID]] = defaultdict(list)
        self._by_provider: Dict[str, List[uuid.UUID]] = defaultdict(list)
        self._lock = threading.RLock()

    def insert(self, record: CapabilityRecord) -> bool:
        with self._lock:
            duplicate = self._find_duplicate(record.provider, record.capability_name, record.version)
            if duplicate is not None:
                return False
            self._records[record.capability_id] = record
            self._by_name[record.capability_name].append(record.capability_id)
            for tag in record.tags:
                self._by_tag[tag].append(record.capability_id)
            self._by_category[record.category].append(record.capability_id)
            self._by_provider[record.provider].append(record.capability_id)
            return True

    def _find_duplicate(self, provider: str, name: str, version: str) -> Optional[uuid.UUID]:
        for cap_id in self._by_name.get(name, []):
            rec = self._records[cap_id]
            if rec.provider == provider and rec.version == version and rec.status != CapabilityStatus.TOMBSTONED:
                return cap_id
        return None

    def update(self, capability_id: uuid.UUID, **fields: Any) -> bool:
        with self._lock:
            record = self._records.get(capability_id)
            if record is None:
                return False
            for key, value in fields.items():
                setattr(record, key, value)
            record.last_updated = utc_now_iso()
            record.signature = compute_signature(record)
            return True

    def tombstone(self, capability_id: uuid.UUID) -> bool:
        return self.update(capability_id, status=CapabilityStatus.TOMBSTONED)

    def get(self, capability_id: uuid.UUID) -> Optional[CapabilityRecord]:
        with self._lock:
            return self._records.get(capability_id)

    def lookup_by_name(self, name: str) -> List[CapabilityRecord]:
        with self._lock:
            return [self._records[i] for i in self._by_name.get(name, []) if i in self._records]

    def lookup_by_tag(self, tag: str) -> List[CapabilityRecord]:
        with self._lock:
            return [self._records[i] for i in self._by_tag.get(tag, []) if i in self._records]

    def lookup_by_category(self, category_prefix: str) -> List[CapabilityRecord]:
        with self._lock:
            results = []
            for cat, ids in self._by_category.items():
                if cat == category_prefix or cat.startswith(category_prefix.rstrip("*")):
                    results.extend(self._records[i] for i in ids if i in self._records)
            return results

    def lookup_by_provider(self, provider: str) -> List[CapabilityRecord]:
        with self._lock:
            return [self._records[i] for i in self._by_provider.get(provider, []) if i in self._records]

    def all_active(self) -> List[CapabilityRecord]:
        with self._lock:
            return [r for r in self._records.values() if r.status != CapabilityStatus.TOMBSTONED]

    def verify_integrity(self) -> List[uuid.UUID]:
        """Returns list of capability_ids whose stored signature no longer matches computed signature."""
        corrupted = []
        with self._lock:
            for cap_id, record in self._records.items():
                if record.signature and record.signature != compute_signature(record):
                    corrupted.append(cap_id)
        return corrupted


# ==============================================================================
# SECTION 7 — VALIDATORS (STRUCTURAL + COMPATIBILITY)
# ==============================================================================

class CapabilityValidator:
    """Enforces structural/schema integrity of capability specs."""

    REQUIRED_FIELDS = ("capability_name", "provider", "version", "provider_type")

    def validate_spec(self, spec: CapabilitySpecDTO) -> ValidationResult:
        if not spec.capability_name or "." not in spec.capability_name:
            return ValidationResult.INVALID
        try:
            SemVer.parse(spec.version)
        except CapabilityValidationError:
            return ValidationResult.INVALID
        if not isinstance(spec.supported_inputs, dict) or not isinstance(spec.supported_outputs, dict):
            return ValidationResult.INVALID
        if spec.priority < 0 or spec.priority > 1000:
            return ValidationResult.DEGRADED
        return ValidationResult.VALID


class CompatibilityValidator:
    """Evaluates version, hardware, and dependency compatibility."""

    def __init__(self, host_hardware_features: Optional[List[str]] = None) -> None:
        self._host_hardware_features = set(host_hardware_features or ["CPU", "GPU_RTX3050_4GB"])

    def check_hardware(self, record: CapabilityRecord) -> bool:
        required = set(record.compatibility.hardware_requirements)
        return required.issubset(self._host_hardware_features)

    def check_version_range(self, record: CapabilityRecord, version_range: Optional[str]) -> bool:
        return SemVer.satisfies(record.version, version_range)

    def check_dependencies(self, record: CapabilityRecord, db: CapabilityDatabase) -> bool:
        for dependency_name in record.dependencies:
            matches = [r for r in db.lookup_by_name(dependency_name) if r.status == CapabilityStatus.ACTIVE]
            if not matches:
                return False
        return True

    def detect_circular_dependency(self, name: str, db: CapabilityDatabase, visited: Optional[set] = None) -> bool:
        visited = visited or set()
        if name in visited:
            return True
        visited.add(name)
        for record in db.lookup_by_name(name):
            for dep in record.dependencies:
                if self.detect_circular_dependency(dep, db, set(visited)):
                    return True
        return False


# ==============================================================================
# SECTION 8 — PERMISSIONS MANAGER
# ==============================================================================

class PermissionsManager:
    """Enforces namespace protection and scope-based access control."""

    _LEVEL_ORDER = {
        PermissionLevel.PUBLIC: 0,
        PermissionLevel.INTERNAL: 1,
        PermissionLevel.PRIVILEGED: 2,
        PermissionLevel.GOVERNANCE: 3,
    }

    def check_namespace(self, spec: CapabilitySpecDTO, provider_secret_key: Optional[str], trusted_key: str) -> bool:
        for reserved in RESERVED_NAMESPACES:
            if spec.capability_name.startswith(reserved):
                return provider_secret_key == trusted_key
        return True

    def caller_can_access(self, record: CapabilityRecord, caller_scope: PermissionLevel, caller_permissions: List[str]) -> bool:
        if self._LEVEL_ORDER[caller_scope] < self._LEVEL_ORDER[record.permission_level]:
            return False
        if record.permissions and not set(record.permissions).issubset(set(caller_permissions) | {"*"}):
            return False
        return True

    def filter_permitted(self, records: List[CapabilityRecord], caller_scope: PermissionLevel, caller_permissions: List[str]) -> List[CapabilityRecord]:
        return [r for r in records if self.caller_can_access(r, caller_scope, caller_permissions)]


# ==============================================================================
# SECTION 9 — HEALTH MONITOR
# ==============================================================================

class HealthMonitor:
    """Tracks heartbeats, latency, and error rate derived health status."""

    def __init__(self) -> None:
        self._last_heartbeat: Dict[uuid.UUID, float] = {}
        self._error_counts: Dict[uuid.UUID, int] = defaultdict(int)
        self._call_counts: Dict[uuid.UUID, int] = defaultdict(int)
        self._lock = threading.RLock()

    def heartbeat(self, capability_id: uuid.UUID, db: CapabilityDatabase) -> None:
        with self._lock:
            self._last_heartbeat[capability_id] = time.time()
            record = db.get(capability_id)
            if record and record.missed_heartbeats > 0:
                db.update(capability_id, missed_heartbeats=0, health_status=HealthStatus.HEALTHY)

    def record_call(self, capability_id: uuid.UUID, error: bool) -> None:
        with self._lock:
            self._call_counts[capability_id] += 1
            if error:
                self._error_counts[capability_id] += 1

    def error_rate(self, capability_id: uuid.UUID) -> float:
        with self._lock:
            calls = self._call_counts.get(capability_id, 0)
            if calls == 0:
                return 0.0
            return self._error_counts.get(capability_id, 0) / calls

    def evaluate(self, capability_id: uuid.UUID, db: CapabilityDatabase) -> HealthStatus:
        record = db.get(capability_id)
        if record is None:
            return HealthStatus.OFFLINE
        rate = self.error_rate(capability_id)
        if record.missed_heartbeats >= MISSED_HEARTBEATS_OFFLINE_LIMIT:
            status = HealthStatus.OFFLINE
        elif rate >= 0.25:
            status = HealthStatus.UNHEALTHY
        elif rate >= 0.05:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY
        db.update(capability_id, health_status=status)
        return status

    def mark_missed_heartbeat(self, capability_id: uuid.UUID, db: CapabilityDatabase) -> None:
        with self._lock:
            record = db.get(capability_id)
            if record is None:
                return
            db.update(capability_id, missed_heartbeats=record.missed_heartbeats + 1)
            self.evaluate(capability_id, db)

    def filter_healthy(self, records: List[CapabilityRecord], allowed: Tuple[HealthStatus, ...]) -> List[CapabilityRecord]:
        return [r for r in records if r.health_status in allowed]


# ==============================================================================
# SECTION 10 — SEARCH ENGINE
# ==============================================================================

class SearchEngine:
    """Multi-attribute, tag-based and lightweight semantic search."""

    def __init__(self, db: CapabilityDatabase) -> None:
        self._db = db

    def _semantic_score(self, text: str, record: CapabilityRecord) -> float:
        haystack = " ".join([record.capability_name, record.description, " ".join(record.tags), record.category]).lower()
        tokens = [t for t in re.split(r"\W+", text.lower()) if t]
        if not tokens:
            return 0.0
        hits = sum(1 for t in tokens if t in haystack)
        return hits / len(tokens)

    def search(self, query: SearchQueryDTO) -> List[CapabilityRecord]:
        candidate_sets: List[List[CapabilityRecord]] = []

        if query.name:
            exact = self._db.lookup_by_name(query.name)
            prefix = [r for r in self._db.all_active() if r.capability_name.startswith(query.name)]
            candidate_sets.append(exact or prefix)
        if query.category:
            candidate_sets.append(self._db.lookup_by_category(query.category))
        if query.provider:
            candidate_sets.append(self._db.lookup_by_provider(query.provider))
        if query.tags:
            tag_hits: List[CapabilityRecord] = []
            for tag in query.tags:
                tag_hits.extend(self._db.lookup_by_tag(tag))
            candidate_sets.append(tag_hits)

        if candidate_sets:
            ids = set(r.capability_id for r in candidate_sets[0])
            for cs in candidate_sets[1:]:
                ids &= set(r.capability_id for r in cs)
            pool = [self._db.get(i) for i in ids if self._db.get(i) is not None]
        else:
            pool = self._db.all_active()

        pool = [r for r in pool if r is not None and r.status != CapabilityStatus.TOMBSTONED]

        if query.version_range:
            pool = [r for r in pool if SemVer.satisfies(r.version, query.version_range)]

        if query.max_p95_latency_ms is not None:
            pool = [r for r in pool if r.performance_metrics.p95_latency_ms <= query.max_p95_latency_ms]

        if query.semantic_text:
            scored = [(r, self._semantic_score(query.semantic_text, r)) for r in pool]
            scored = [t for t in scored if t[1] > 0]
            scored.sort(key=lambda t: t[1], reverse=True)
            pool = [r for r, _ in scored]

        return pool[:MAX_QUERY_CANDIDATES]


# ==============================================================================
# SECTION 11 — RANKING ENGINE
# ==============================================================================

class CapabilityRankingEngine(ICapabilityRankingEngine):
    """Computes weighted composite utility score S_p for each candidate."""

    def __init__(self, weights: Optional[Dict[str, float]] = None, pinned_providers: Optional[set] = None) -> None:
        self._weights = weights or dict(DEFAULT_WEIGHTS)
        self._pinned_providers = pinned_providers or set()

    def set_user_pin(self, provider: str) -> None:
        self._pinned_providers.add(provider)

    def clear_user_pin(self, provider: str) -> None:
        self._pinned_providers.discard(provider)

    def _health_factor(self, r: CapabilityRecord) -> float:
        return {
            HealthStatus.HEALTHY: 1.0,
            HealthStatus.DEGRADED: 0.5,
            HealthStatus.UNHEALTHY: 0.0,
            HealthStatus.OFFLINE: 0.0,
        }[r.health_status]

    def _performance_factor(self, r: CapabilityRecord, baseline_ms: float = 50.0) -> float:
        latency = max(r.performance_metrics.p95_latency_ms, 0.001)
        import math
        score = 1.0 - (math.log10(latency) / math.log10(max(baseline_ms, 10)))
        return max(0.0, min(1.0, score))

    def _version_factor(self, r: CapabilityRecord, requested_version: Optional[str]) -> float:
        return SemVer.precision_score(requested_version, r.version)

    def _availability_factor(self, r: CapabilityRecord) -> float:
        return max(0.0, min(1.0, r.availability_ratio))

    def _priority_factor(self, r: CapabilityRecord) -> float:
        return max(0.0, min(1.0, r.priority / 1000.0))

    def _preference_factor(self, r: CapabilityRecord) -> float:
        return 1.0 if (r.pinned_by_user or r.provider in self._pinned_providers) else 0.0

    def _hardware_factor(self, r: CapabilityRecord) -> float:
        return 1.0 if r.performance_metrics.hardware_accelerated else 0.5

    def _local_app_factor(self, r: CapabilityRecord) -> float:
        # Prefer local installed applications over web apps
        if r.provider_type == ProviderType.APPLICATION:
            return 0.0 if r.is_web_app else 1.0
        return 0.5  # Neutral for other providers

    def _installation_penalty(self, r: CapabilityRecord) -> float:
        # Penalize if it needs installation
        return 1.0 if r.needs_installation else 0.0

    def _confidence_factor(self, r: CapabilityRecord) -> float:
        return {
            ConfidenceLevel.UNKNOWN: 0.1,
            ConfidenceLevel.LOW: 0.3,
            ConfidenceLevel.MEDIUM: 0.6,
            ConfidenceLevel.HIGH: 0.9,
            ConfidenceLevel.CONFIRMED: 1.0,
        }.get(r.confidence_level, 0.1)

    def score(self, record: CapabilityRecord, requested_version: Optional[str] = None) -> float:
        w = self._weights
        s = (
            w.get("health", 0.3) * self._health_factor(record)
            + w.get("performance", 0.2) * self._performance_factor(record)
            + w.get("version_precision", 0.1) * self._version_factor(record, requested_version)
            + w.get("availability", 0.1) * self._availability_factor(record)
            + w.get("static_priority", 0.1) * self._priority_factor(record)
            + w.get("user_preference", 0.15) * self._preference_factor(record)
            + w.get("hardware_acceleration", 0.05) * self._hardware_factor(record)
            + w.get("local_app_preference", 0.15) * self._local_app_factor(record)
            + w.get("installation_penalty", -0.20) * self._installation_penalty(record)
            + w.get("confidence", 0.10) * self._confidence_factor(record)
        )
        return round(s * 100.0, 4)

    def compute_ranks(self, candidates: List[CapabilityRecord], requested_version: Optional[str] = None) -> List[CapabilityRecord]:
        scored = [(r, self.score(r, requested_version)) for r in candidates]
        scored.sort(key=lambda t: t[1], reverse=True)
        for record, s in scored:
            record.__dict__["_last_score"] = s
        return [r for r, _ in scored]


# ==============================================================================
# SECTION 12 — AUDIT / HISTORY / METRICS MANAGERS
# ==============================================================================

class HistoryManager:
    """Append-only immutable event store for capability mutations."""

    def __init__(self) -> None:
        self._events: List[HistoryEntry] = []
        self._lock = threading.RLock()

    def record(self, event_type: HistoryEventType, record: CapabilityRecord) -> None:
        with self._lock:
            self._events.append(
                HistoryEntry(
                    event_type=event_type,
                    capability_id=record.capability_id,
                    timestamp=utc_now_iso(),
                    snapshot={
                        "capability_name": record.capability_name,
                        "provider": record.provider,
                        "version": record.version,
                        "status": record.status.value,
                    },
                )
            )

    def timeline_for(self, capability_id: uuid.UUID) -> List[HistoryEntry]:
        with self._lock:
            return [e for e in self._events if e.capability_id == capability_id]

    def all_events(self) -> List[HistoryEntry]:
        with self._lock:
            return list(self._events)


class AuditManager:
    """Tamper-evident structured audit logging."""

    def __init__(self) -> None:
        self._records: List[AuditRecord] = []
        self._lock = threading.RLock()

    def record(self, module: str, event_type: str, payload: Dict[str, Any], log_level: str = "INFO") -> AuditRecord:
        trace_id = f"tr-{uuid.uuid4()}"
        entry = AuditRecord(
            trace_id=trace_id,
            timestamp=utc_now_iso(),
            organ="CapabilityRegistry",
            module=module,
            event_type=event_type,
            log_level=log_level,
            payload=payload,
        )
        entry.signature = hashlib.sha256(
            json.dumps({"trace_id": trace_id, "event_type": event_type, "payload": payload}, sort_keys=True, default=str).encode()
        ).hexdigest()
        with self._lock:
            self._records.append(entry)
        return entry

    def verify_chain(self) -> bool:
        with self._lock:
            for entry in self._records:
                expected = hashlib.sha256(
                    json.dumps(
                        {"trace_id": entry.trace_id, "event_type": entry.event_type, "payload": entry.payload},
                        sort_keys=True,
                        default=str,
                    ).encode()
                ).hexdigest()
                if expected != entry.signature:
                    return False
            return True

    def all_records(self) -> List[AuditRecord]:
        with self._lock:
            return list(self._records)


class MetricsManager:
    """Collects operational telemetry: latencies, cache ratios, error rates."""

    def __init__(self) -> None:
        self._query_latencies: List[float] = []
        self._cache_hits = 0
        self._cache_misses = 0
        self._invocation_counts: Dict[str, int] = defaultdict(int)
        self._lock = threading.RLock()

    def record_query(self, latency_ms: float, cache_hit: bool) -> None:
        with self._lock:
            self._query_latencies.append(latency_ms)
            if cache_hit:
                self._cache_hits += 1
            else:
                self._cache_misses += 1

    def record_invocation(self, provider: str) -> None:
        with self._lock:
            self._invocation_counts[provider] += 1

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            total = self._cache_hits + self._cache_misses
            avg_latency = sum(self._query_latencies) / len(self._query_latencies) if self._query_latencies else 0.0
            return {
                "avg_query_latency_ms": round(avg_latency, 4),
                "cache_hit_ratio": round(self._cache_hits / total, 4) if total else 0.0,
                "total_queries": total,
                "invocation_counts": dict(self._invocation_counts),
            }


# ==============================================================================
# SECTION 13 — CONFIGURATION MANAGER
# ==============================================================================

class CapabilityRegistryConfig:
    """Loads and serves operational parameters with factory-default fallback."""

    _FACTORY_DEFAULTS: Dict[str, Any] = {
        "core": {
            "enable_auto_discovery": True,
            "discovery_sweep_interval_ms": 30000,
            "max_query_candidates": MAX_QUERY_CANDIDATES,
            "enable_semantic_search": True,
        },
        "cache": {
            "l1_capacity_items": L1_CACHE_CAPACITY,
            "default_ttl_seconds": DEFAULT_TTL_SECONDS,
        },
        "health_monitoring": {
            "heartbeat_interval_ms": 5000,
            "missed_heartbeats_offline_limit": MISSED_HEARTBEATS_OFFLINE_LIMIT,
        },
        "ranking_weights": dict(DEFAULT_WEIGHTS),
        "security": {
            "enforce_strict_namespaces": True,
            "audit_all_mutations": True,
        },
    }

    def __init__(self, overrides: Optional[Dict[str, Any]] = None) -> None:
        self._config = json.loads(json.dumps(self._FACTORY_DEFAULTS))
        if overrides:
            self._deep_merge(self._config, overrides)

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get(self, path: str, default: Any = None) -> Any:
        node: Any = self._config
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


# ==============================================================================
# SECTION 14 — SOCKETS (INTERFACE BOUNDARIES)
# ==============================================================================

class CapabilitySocket(ICapabilitySocket):
    """Generic query/resolution ingress socket."""

    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        query = SearchQueryDTO(**{k: v for k, v in message.items() if k in SearchQueryDTO.__dataclass_fields__})
        try:
            handle = self._core.process_query(query)
            return {"status": "OK", "handle": handle}
        except UnresolvedCapabilityException as exc:
            return {"status": "UNRESOLVED", "error": str(exc)}


class RegistrationSocket(ICapabilitySocket):
    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        action = message.get("action", "register")
        if action == "register":
            spec = message["spec"]
            ok = self._core.register(spec)
            return {"status": "OK" if ok else "REJECTED"}
        elif action == "deregister":
            ok = self._core.deregister(message["capability_id"], message.get("provider_key", ""))
            return {"status": "OK" if ok else "REJECTED"}
        return {"status": "UNKNOWN_ACTION"}


class DiscoverySocket(ICapabilitySocket):
    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "OK", "records": [r.capability_name for r in self._core.db.all_active()]}


class HealthSocket(ICapabilitySocket):
    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        capability_id = uuid.UUID(message["capability_id"])
        if message.get("action") == "heartbeat":
            self._core.health_monitor.heartbeat(capability_id, self._core.db)
            return {"status": "OK"}
        status = self._core.health_monitor.evaluate(capability_id, self._core.db)
        return {"status": "OK", "health": status.value}


class SearchSocket(ICapabilitySocket):
    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        query = SearchQueryDTO(**{k: v for k, v in message.items() if k in SearchQueryDTO.__dataclass_fields__})
        results = self._core.search_engine.search(query)
        return {"status": "OK", "results": [r.capability_name for r in results]}


class ValidationSocket(ICapabilitySocket):
    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        spec: CapabilitySpecDTO = message["spec"]
        result = self._core.validator.validate_spec(spec)
        return {"status": "OK", "result": result.value}


class PermissionSocket(ICapabilitySocket):
    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        capability_id = uuid.UUID(message["capability_id"])
        record = self._core.db.get(capability_id)
        if record is None:
            return {"status": "NOT_FOUND"}
        scope = PermissionLevel(message.get("caller_scope", PermissionLevel.INTERNAL.value))
        perms = message.get("caller_permissions", [])
        allowed = self._core.permissions.caller_can_access(record, scope, perms)
        return {"status": "OK", "allowed": allowed}


class RankingSocket(ICapabilitySocket):
    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        names = message.get("capability_names", [])
        candidates = [r for n in names for r in self._core.db.lookup_by_name(n)]
        ranked = self._core.ranking_engine.compute_ranks(candidates)
        return {"status": "OK", "ranked": [r.capability_name for r in ranked]}


# ==============================================================================
# SECTION 15 — PIPELINES
# ==============================================================================

class RegistrationPipeline:
    """Validate -> namespace-check -> insert -> index -> invalidate -> history/audit."""

    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def run(self, spec: CapabilitySpecDTO) -> bool:
        core = self._core
        result = core.validator.validate_spec(spec)
        if result == ValidationResult.INVALID:
            core.audit.record("RegistrationPipeline", "REGISTRATION_REJECTED", {"reason": "INVALID_SPEC", "name": spec.capability_name})
            return False

        if not core.permissions.check_namespace(spec, spec.provider_secret_key, core.trusted_key):
            core.audit.record("RegistrationPipeline", "REGISTRATION_REJECTED", {"reason": "NAMESPACE_VIOLATION", "name": spec.capability_name}, "WARNING")
            return False

        record = CapabilityRecord(
            capability_id=spec.capability_id,
            capability_name=spec.capability_name,
            description=spec.description,
            provider=spec.provider,
            provider_type=spec.provider_type,
            version=spec.version,
            status=CapabilityStatus.ACTIVE,
            dependencies=spec.dependencies,
            permissions=spec.permissions,
            priority=spec.priority,
            supported_inputs=spec.supported_inputs,
            supported_outputs=spec.supported_outputs,
            performance_metrics=spec.performance_metrics,
            health_status=HealthStatus.HEALTHY,
            compatibility=spec.compatibility,
            tags=spec.tags,
            category=spec.category,
            owner=spec.owner,
            permission_level=spec.permission_level,
            registration_date=utc_now_iso(),
            last_updated=utc_now_iso(),
        )
        record.signature = compute_signature(record)

        if not core.db.insert(record):
            core.audit.record("RegistrationPipeline", "REGISTRATION_REJECTED", {"reason": "DUPLICATE", "name": spec.capability_name}, "WARNING")
            return False

        core.cache.invalidate(record.capability_name)
        core.history.record(HistoryEventType.CREATED, record)
        core.audit.record("RegistrationPipeline", "CAPABILITY_REGISTERED", {"name": record.capability_name, "provider": record.provider, "version": record.version})
        return True


class RemovalPipeline:
    """Tombstone -> drain -> evict cache -> history/audit."""

    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def run(self, capability_id: uuid.UUID, provider_key: str) -> bool:
        core = self._core
        record = core.db.get(capability_id)
        if record is None:
            return False
        if not core.db.tombstone(capability_id):
            return False
        core.cache.invalidate(record.capability_name)
        core.history.record(HistoryEventType.REMOVED, record)
        core.audit.record("RemovalPipeline", "CAPABILITY_DEREGISTERED", {"name": record.capability_name, "provider": record.provider})
        return True


class SearchPipeline:
    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def run(self, query: SearchQueryDTO) -> List[CapabilityRecord]:
        return self._core.search_engine.search(query)


class ValidationPipeline:
    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def run(self, records: List[CapabilityRecord], query: SearchQueryDTO) -> List[CapabilityRecord]:
        core = self._core
        permitted = core.permissions.filter_permitted(records, query.caller_scope, query.caller_permissions)
        compatible = [
            r for r in permitted
            if core.compatibility.check_hardware(r)
            and core.compatibility.check_version_range(r, query.version_range)
            and core.compatibility.check_dependencies(r, core.db)
        ]
        return core.health_monitor.filter_healthy(compatible, query.required_health)


class RankingPipeline:
    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def run(self, records: List[CapabilityRecord], requested_version: Optional[str] = None) -> List[CapabilityRecord]:
        return self._core.ranking_engine.compute_ranks(records, requested_version)


class DiscoveryPipeline:
    """Boot-time sweep to auto-register embedded providers via a callback registry."""

    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core
        self._sources: List[Callable[[], List[CapabilitySpecDTO]]] = []

    def add_source(self, source: Callable[[], List[CapabilitySpecDTO]]) -> None:
        self._sources.append(source)

    def run(self) -> int:
        registered = 0
        for source in self._sources:
            for spec in source():
                if self._core.register(spec):
                    registered += 1
        return registered


class UpdatePipeline:
    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def run(self, capability_id: uuid.UUID, **fields: Any) -> bool:
        core = self._core
        record = core.db.get(capability_id)
        if record is None:
            return False
        ok = core.db.update(capability_id, **fields)
        if ok:
            core.cache.invalidate(record.capability_name)
            core.history.record(HistoryEventType.UPDATED, record)
            core.audit.record("UpdatePipeline", "CAPABILITY_UPDATED", {"name": record.capability_name, "fields": list(fields.keys())})
        return ok


class RecoveryPipeline:
    """Rebuild caches/indices, detect corruption, broadcast re-registration request."""

    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def run(self) -> Dict[str, Any]:
        core = self._core
        core.cache.clear()
        corrupted = core.db.verify_integrity()
        for cap_id in corrupted:
            core.db.tombstone(cap_id)
        core.audit.record("RecoveryPipeline", "RECOVERY_EXECUTED", {"corrupted_count": len(corrupted)}, "WARNING" if corrupted else "INFO")
        return {"corrupted": [str(c) for c in corrupted], "cache_cleared": True}


class MonitoringPipeline:
    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def run(self) -> Dict[str, Any]:
        return self._core.metrics.snapshot()


# ==============================================================================
# SECTION 16 — CAPABILITY RESOLVER
# ==============================================================================

class CapabilityResolver(ICapabilityResolver):
    def __init__(self, core: "CapabilityRegistryCore") -> None:
        self._core = core

    def build_handle(self, record: CapabilityRecord) -> CapabilityInvocationHandle:
        token = hashlib.sha256(f"{record.capability_id}:{time.time()}".encode()).hexdigest()[:32]
        return CapabilityInvocationHandle(
            capability_id=record.capability_id,
            capability_name=record.capability_name,
            provider_endpoint=f"{record.provider}::{record.capability_name}",
            selected_version=record.version,
            auth_token=token,
            score=record.__dict__.get("_last_score", 0.0),
        )

    def resolve_capability(self, query_payload: Dict[str, Any], caller_scope: str) -> CapabilityInvocationHandle:
        query = SearchQueryDTO(
            name=query_payload.get("name"),
            category=query_payload.get("category"),
            provider=query_payload.get("provider"),
            tags=query_payload.get("tags", []),
            version_range=query_payload.get("version_range"),
            caller_scope=PermissionLevel(caller_scope),
            caller_permissions=query_payload.get("caller_permissions", []),
            semantic_text=query_payload.get("semantic_text"),
        )
        return self._core.process_query(query)


# ==============================================================================
# SECTION 17 — ALIAS MANAGERS & DISCOVERY CRAWLER
# ==============================================================================

class CapabilityAliasRegistry:
    def __init__(self):
        self._aliases: Dict[str, str] = {}
        
    def add_alias(self, alias: str, normalized_capability: str) -> None:
        self._aliases[alias.lower().strip()] = normalized_capability
        
    def resolve(self, query: str) -> str:
        return self._aliases.get(query.lower().strip(), query.strip())


class ApplicationAliasRegistry:
    def __init__(self):
        self._aliases: Dict[str, str] = {}
        
    def add_alias(self, alias: str, canonical_name: str) -> None:
        self._aliases[alias.lower().strip()] = canonical_name
        
    def resolve(self, query: str) -> str:
        return self._aliases.get(query.lower().strip(), query.strip())


class LocalAppDiscoveryCrawler:
    def __init__(self, db: CapabilityDatabase, max_depth: int = 4, max_concurrency: int = 5):
        self.db = db
        self.max_depth = max_depth
        self.max_concurrency = max_concurrency
        self.visited_paths = set()
        self.is_running = False
        
    async def crawl_roots(self, roots: List[str]) -> None:
        self.is_running = True
        try:
            sem = asyncio.Semaphore(self.max_concurrency)
            tasks = []
            for root in roots:
                if os.path.exists(root):
                    tasks.append(self._crawl_dir(root, 0, sem))
            if tasks:
                await asyncio.gather(*tasks)
        finally:
            self.is_running = False
            
    async def _crawl_dir(self, path: str, depth: int, sem: asyncio.Semaphore) -> None:
        if depth > self.max_depth or path in self.visited_paths:
            return
        self.visited_paths.add(path)
        
        try:
            async with sem:
                with os.scandir(path) as it:
                    dirs = []
                    for entry in it:
                        if entry.is_dir(follow_symlinks=False):
                            dirs.append(entry.path)
                        elif entry.is_file(follow_symlinks=False) and entry.name.endswith('.exe'):
                            self._register_discovered_app(entry.name, entry.path)
                
            await asyncio.sleep(0.01)
            
            tasks = [self._crawl_dir(d, depth + 1, sem) for d in dirs]
            if tasks:
                await asyncio.gather(*tasks)
                
        except (PermissionError, OSError):
            pass

    def _register_discovered_app(self, filename: str, path: str) -> None:
        app_name = filename[:-4]
        # Check if already registered
        if self.db.lookup_by_provider(app_name):
            return
            
        record = CapabilityRecord(
            capability_id=uuid.uuid4(),
            capability_name=f"app.local.{app_name.lower()}",
            description=f"Local application discovered at {path}",
            provider=app_name,
            provider_type=ProviderType.APPLICATION,
            version="1.0.0",
            status=CapabilityStatus.ACTIVE,
            dependencies=[],
            permissions=[],
            priority=500,
            supported_inputs={},
            supported_outputs={},
            performance_metrics=PerformanceMetrics(),
            health_status=HealthStatus.HEALTHY,
            compatibility=CompatibilityProfile(),
            tags=["application", "local"],
            category="Application",
            owner="system",
            permission_level=PermissionLevel.PUBLIC,
            registration_date=utc_now_iso(),
            last_updated=utc_now_iso(),
            signature="",
            availability_ratio=1.0,
            missed_heartbeats=0,
            pinned_by_user=False,
            confidence_level=ConfidenceLevel.HIGH,
            needs_installation=False,
            application_aliases=[],
            executable_path=path,
            is_web_app=False,
        )
        record.signature = compute_signature(record)
        self.db.insert(record)


# ==============================================================================
# SECTION 18 — CAPABILITY REGISTRY CORE (ORGAN ORCHESTRATOR)
# ==============================================================================

class CapabilityRegistryCore(ICapabilityRegistryManager):
    """
    Central operational driver for the Capability Registry organ.
    Public entrypoint for every other organ / socket consumer.
    """

    def __init__(self, config: Optional[CapabilityRegistryConfig] = None, trusted_key: str = "hojaiga-root-key") -> None:
        self.config = config or CapabilityRegistryConfig()
        self.trusted_key = trusted_key

        self.db = CapabilityDatabase()
        self.cache = L1CacheManager(
            capacity=self.config.get("cache.l1_capacity_items", L1_CACHE_CAPACITY),
            ttl_seconds=self.config.get("cache.default_ttl_seconds", DEFAULT_TTL_SECONDS),
        )
        self.search_engine = SearchEngine(self.db)
        self.validator = CapabilityValidator()
        self.compatibility = CompatibilityValidator()
        self.permissions = PermissionsManager()
        self.health_monitor = HealthMonitor()
        self.ranking_engine = CapabilityRankingEngine(weights=self.config.get("ranking_weights"))
        self.history = HistoryManager()
        self.audit = AuditManager()
        self.metrics = MetricsManager()
        
        self.capability_alias = CapabilityAliasRegistry()
        self.application_alias = ApplicationAliasRegistry()
        self.app_crawler = LocalAppDiscoveryCrawler(self.db)
        
        self.resolver = CapabilityResolver(self)

        self.registration_pipeline = RegistrationPipeline(self)
        self.removal_pipeline = RemovalPipeline(self)
        self.search_pipeline = SearchPipeline(self)
        self.validation_pipeline = ValidationPipeline(self)
        self.ranking_pipeline = RankingPipeline(self)
        self.discovery_pipeline = DiscoveryPipeline(self)
        self.update_pipeline = UpdatePipeline(self)
        self.recovery_pipeline = RecoveryPipeline(self)
        self.monitoring_pipeline = MonitoringPipeline(self)

        self.capability_socket = CapabilitySocket(self)
        self.registration_socket = RegistrationSocket(self)
        self.discovery_socket = DiscoverySocket(self)
        self.health_socket = HealthSocket(self)
        self.search_socket = SearchSocket(self)
        self.validation_socket = ValidationSocket(self)
        self.permission_socket = PermissionSocket(self)
        self.ranking_socket = RankingSocket(self)

    # ---- Registration / Deregistration -------------------------------------
    def register(self, spec: CapabilitySpecDTO) -> bool:
        return self.registration_pipeline.run(spec)

    def register_capability(self, spec: CapabilitySpecDTO) -> bool:  # ICapabilityRegistryManager
        return self.register(spec)

    def deregister(self, capability_id: uuid.UUID, provider_key: str) -> bool:
        return self.removal_pipeline.run(capability_id, provider_key)

    def deregister_capability(self, capability_id: uuid.UUID, provider_key: str) -> bool:  # ICapabilityRegistryManager
        return self.deregister(capability_id, provider_key)

    # ---- Query / Resolution --------------------------------------------------
    def process_query(self, query: SearchQueryDTO) -> CapabilityInvocationHandle:
        start = time.perf_counter()
        
        if query.name:
            # Resolve functionality aliases ("record screen" -> "screen_recording")
            query.name = self.capability_alias.resolve(query.name)
            # Resolve application discovery aliases ("obs" -> "OBS Studio")
            query.name = self.application_alias.resolve(query.name)
            
        cache_key = self.cache.hash_query(query)
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.metrics.record_query((time.perf_counter() - start) * 1000, cache_hit=True)
            return cached

        candidates = self.search_pipeline.run(query)
        validated = self.validation_pipeline.run(candidates, query)
        if not validated:
            self.audit.record("CapabilityRegistryCore", "RESOLUTION_FAILED", {"query": query.name}, "WARNING")
            raise UnresolvedCapabilityException(f"No provider resolved for query: {query.name or query.tags}")

        ranked = self.ranking_pipeline.run(validated, query.version_range)
        top = ranked[0]
        handle = self.resolver.build_handle(top)

        self.cache.put(cache_key, handle)
        self.metrics.record_query((time.perf_counter() - start) * 1000, cache_hit=False)
        self.metrics.record_invocation(top.provider)
        self.audit.record(
            "CapabilityRegistryCore",
            "CAPABILITY_RESOLVED",
            {
                "query": query.name,
                "candidates_found": len(candidates),
                "selected_provider": top.provider,
                "selected_version": top.version,
                "cache_hit": False,
            },
        )
        return handle

    def resolve_with_fallback(self, query: SearchQueryDTO, fallback_names: List[str]) -> CapabilityInvocationHandle:
        try:
            return self.process_query(query)
        except UnresolvedCapabilityException:
            for name in fallback_names:
                fallback_query = SearchQueryDTO(name=name, caller_scope=query.caller_scope, caller_permissions=query.caller_permissions)
                try:
                    return self.process_query(fallback_query)
                except UnresolvedCapabilityException:
                    continue
            raise

    # ---- Provider ranking preference (user pinning) --------------------------
    def pin_provider(self, provider: str) -> None:
        self.ranking_engine.set_user_pin(provider)
        self.audit.record("CapabilityRegistryCore", "PROVIDER_PINNED", {"provider": provider})

    def unpin_provider(self, provider: str) -> None:
        self.ranking_engine.clear_user_pin(provider)
        self.audit.record("CapabilityRegistryCore", "PROVIDER_UNPINNED", {"provider": provider})

    # ---- Health -----------------------------------------------------------
    def heartbeat(self, capability_id: uuid.UUID) -> None:
        self.health_monitor.heartbeat(capability_id, self.db)

    def report_invocation_result(self, capability_id: uuid.UUID, error: bool) -> None:
        self.health_monitor.record_call(capability_id, error)
        self.health_monitor.evaluate(capability_id, self.db)

    # ---- Lifecycle ----------------------------------------------------------
    def boot(self) -> None:
        self.discovery_pipeline.run()
        self.audit.record("CapabilityRegistryCore", "ORGAN_BOOTED", {})

    def shutdown(self) -> None:
        self.audit.record("CapabilityRegistryCore", "ORGAN_SHUTDOWN", {})

    def recover(self) -> Dict[str, Any]:
        return self.recovery_pipeline.run()
