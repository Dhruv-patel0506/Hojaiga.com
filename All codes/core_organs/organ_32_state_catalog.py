"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 32
Name: State Catalog (AOS-STC)

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [State Catalog]
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
Dependencies: enum, typing, future, json, time, threading, sqlite3, uuid, hashlib, asyncio, dataclasses...
"""
from __future__ import annotations

"""
Hojaiga Automation OS — Organ 32: State Catalog (AOS-STC)
Authority Order (highest first):
1. Constitution of Hojaiga
2. Hojaiga Law Book
3. Diagrams (Upper Surface + Inner Depth)
4. Legacy Code Migration Guide
5. Hojaiga Policy Manual
6. Master Architecture Blueprint
7. Organ Specification
8. State_Catalog.md (this organ's authoritative spec)

Purpose
AOS-STC is the authoritative, deterministic runtime state registry and
transition engine for every organ, service, task, workflow, connector,
plugin and runtime component operating inside Hojaiga. No component may
invent custom state names, bypass transition validation, or perform
illegal out-of-band state jumps.
"""

import asyncio
import hashlib
import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.organ32.stc")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[StateCatalog] %(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

__all__ = [
    "StateCatalogOrgan",
    "StateCategory",
    "StateName",
    "EntityType",
    "StateDefinition",
    "StateRecord",
    "TransitionReceipt",
    "TransitionRecord",
    "StateEvent",
    "StateCatalogError",
    "RegistrationError",
    "ValidationError",
    "TransitionError",
    "AuthError",
    "RecoveryError",
    "LookupError_",
]

SPEC_VERSION = "1.0.0"


# ==========================================================================
# SECTION 1 — ERRORS
# ==========================================================================
class StateCatalogError(Exception):
    code = "ERR_STATE_CATALOG"


class RegistrationError(StateCatalogError):
    code = "ERR_REGISTRATION_FAILED"


class ValidationError(StateCatalogError):
    code = "ERR_INVALID_STATE_TRANSITION"


class TransitionError(StateCatalogError):
    code = "ERR_TRANSITION_ABORTED"


class AuthError(StateCatalogError):
    code = "ERR_UNAUTHORIZED_STATE_REQUEST"


class RecoveryError(StateCatalogError):
    code = "ERR_RECOVERY_FAILED"


class LookupError_(StateCatalogError):
    code = "ERR_ENTITY_NOT_FOUND"


# ==========================================================================
# SECTION 2 — STATE CATEGORY / STATE NAME / ENTITY TYPE
# ==========================================================================
class StateCategory(str, Enum):
    SYSTEM = "SYSTEM"
    KERNEL = "KERNEL"
    SERVICE = "SERVICE"
    TASK = "TASK"
    WORKFLOW = "WORKFLOW"
    RESOURCE = "RESOURCE"
    MEMORY = "MEMORY"
    KNOWLEDGE = "KNOWLEDGE"
    BRAIN = "BRAIN"
    CNS = "CNS"
    CONTROLLER = "CONTROLLER"
    LEARNING = "LEARNING"
    AUTOMATION = "AUTOMATION"
    AGENT = "AGENT"
    PLUGIN = "PLUGIN"
    CONNECTOR = "CONNECTOR"
    INTERFACE = "INTERFACE"
    LLM_RUNTIME = "LLM_RUNTIME"
    WINDOW = "WINDOW"
    PLAYWRIGHT = "PLAYWRIGHT"
    API = "API"
    SECURITY = "SECURITY"
    RECOVERY = "RECOVERY"
    BACKUP = "BACKUP"
    UPDATE = "UPDATE"
    USER_SESSION = "USER_SESSION"


class StateName(str, Enum):
    CREATED = "CREATED"
    REGISTERED = "REGISTERED"
    VALIDATED = "VALIDATED"
    INITIALIZING = "INITIALIZING"
    STARTING = "STARTING"
    READY = "READY"
    IDLE = "IDLE"
    WAITING = "WAITING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    BUSY = "BUSY"
    PROCESSING = "PROCESSING"
    BLOCKED = "BLOCKED"
    PAUSED = "PAUSED"
    RESUMING = "RESUMING"
    COMPLETED = "COMPLETED"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    ROLLING_BACK = "ROLLING_BACK"
    RECOVERING = "RECOVERING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    TERMINATED = "TERMINATED"
    DISABLED = "DISABLED"
    MAINTENANCE = "MAINTENANCE"
    ARCHIVED = "ARCHIVED"
    DEPRECATED = "DEPRECATED"
    REMOVED = "REMOVED"
    UNKNOWN = "UNKNOWN"


class EntityType(str, Enum):
    SYSTEM = "SYSTEM"
    KERNEL = "KERNEL"
    TASK = "TASK"
    SERVICE = "SERVICE"
    PLUGIN = "PLUGIN"
    CONNECTOR = "CONNECTOR"
    RECOVERY = "RECOVERY"
    WORKFLOW = "WORKFLOW"


PRIVILEGE_MATRIX: Dict[str, Dict[str, Any]] = {
    "SYSTEM_KERNEL": {
        "categories": {StateCategory.SYSTEM, StateCategory.KERNEL},
        "allowed_targets": None,
        "permitted_invoker": "AOS_MICRO_KERNEL_CORE",
    },
    "SERVICE_ORGAN": {
        "categories": {StateCategory.SERVICE, StateCategory.CONTROLLER},
        "allowed_targets": {
            StateName.READY, StateName.RUNNING, StateName.STOPPING, StateName.PAUSED,
            StateName.INITIALIZING, StateName.STARTING, StateName.BUSY, StateName.IDLE,
            StateName.FAILED, StateName.RECOVERING, StateName.STOPPED
        },
        "permitted_invoker": "REGISTERED_SERVICE_MANAGER",
    },
    "WORKFLOW_TASK": {
        "categories": {StateCategory.WORKFLOW, StateCategory.TASK},
        "allowed_targets": {
            StateName.QUEUED, StateName.RUNNING, StateName.PROCESSING, StateName.COMPLETED,
            StateName.WAITING, StateName.SUCCESS, StateName.BLOCKED, StateName.PAUSED,
            StateName.FAILED, StateName.RETRYING, StateName.TERMINATED, StateName.ARCHIVED,
            StateName.REMOVED
        },
        "permitted_invoker": "EXECUTION_ORCHESTRATOR",
    },
    "PLUGIN_CONNECTOR": {
        "categories": {StateCategory.PLUGIN, StateCategory.CONNECTOR},
        "allowed_targets": {
            StateName.INITIALIZING, StateName.READY, StateName.RUNNING, StateName.STOPPED,
            StateName.DISABLED, StateName.FAILED, StateName.RECOVERING, StateName.STARTING,
            StateName.REGISTERED, StateName.TERMINATED, StateName.REMOVED
        },
        "permitted_invoker": "SUBSYSTEM_SANDBOX_HOST",
    },
}


def _privilege_bucket_for_category(category: StateCategory) -> Optional[str]:
    for bucket, spec in PRIVILEGE_MATRIX.items():
        if category in spec["categories"]:
            return bucket
    return None


# ==========================================================================
# SECTION 3 — STATE DEFINITIONS
# ==========================================================================
@dataclass(frozen=True)
class TimeoutRule:
    max_duration_ms: int
    action_on_timeout: str


@dataclass(frozen=True)
class RecoveryBehaviour:
    retry_allowed: bool
    max_retries: int
    fallback_state: str


@dataclass(frozen=True)
class StateDefinition:
    state_id: str
    state_name: str
    description: str
    category: StateCategory
    allowed_previous_states: Tuple[str, ...]
    allowed_next_states: Tuple[str, ...]
    entry_conditions: Tuple[str, ...]
    exit_conditions: Tuple[str, ...]
    timeout_rules: TimeoutRule
    recovery_behaviour: RecoveryBehaviour
    events_generated: Tuple[str, ...]
    related_errors: Tuple[str, ...]
    version: str = SPEC_VERSION
    owner: str = "AOS-STC"
    priority: int = 500

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_id": self.state_id,
            "state_name": self.state_name,
            "description": self.description,
            "category": self.category.value,
            "allowed_previous_states": list(self.allowed_previous_states),
            "allowed_next_states": list(self.allowed_next_states),
            "entry_conditions": list(self.entry_conditions),
            "exit_conditions": list(self.exit_conditions),
            "timeout_rules": {
                "max_duration_ms": self.timeout_rules.max_duration_ms,
                "action_on_timeout": self.timeout_rules.action_on_timeout,
            },
            "recovery_behaviour": {
                "retry_allowed": self.recovery_behaviour.retry_allowed,
                "max_retries": self.recovery_behaviour.max_retries,
                "fallback_state": self.recovery_behaviour.fallback_state,
            },
            "events_generated": list(self.events_generated),
            "related_errors": list(self.related_errors),
            "version": self.version,
            "owner": self.owner,
            "priority": self.priority,
        }


_RAW_STATES: Tuple[Tuple[str, str, int, str], ...] = (
    ("CREATED", "Entity instantiated in memory; metadata unverified.", 500, "TERMINATED"),
    ("REGISTERED", "Identified and recorded in the State Registry.", 1000, "TERMINATED"),
    ("VALIDATED", "Configuration, permissions, and dependencies passed assertion.", 1000, "FAILED"),
    ("INITIALIZING", "Loading configurations, allocating dynamic buffers.", 10000, "FAILED"),
    ("STARTING", "Spawning processes, opening listening sockets.", 5000, "RECOVERING"),
    ("READY", "Fully initialized, listening, awaiting execution request.", 0, "NONE"),
    ("IDLE", "Operational, zero active tasks assigned, low power profile.", 0, "NONE"),
    ("WAITING", "Suspended pending external event, signal, or temporal tick.", 60000, "FAILED"),
    ("QUEUED", "Scheduled in priority execution buffer.", 30000, "FAILED"),
    ("RUNNING", "Active task/process execution on thread pool.", 0, "RECOVERING"),
    ("BUSY", "Operational capacity saturated; rejecting new incoming work.", 15000, "WARNING"),
    ("PROCESSING", "Transforming payload, performing local calculation.", 30000, "RETRYING"),
    ("BLOCKED", "Interrupted by resource locks, mutex, or missing dependency.", 10000, "FAILED"),
    ("PAUSED", "Suspended via explicit administrative operator signal.", 0, "NONE"),
    ("RESUMING", "Restoring memory context from persistent swap.", 5000, "FAILED"),
    ("COMPLETED", "Execution cycle finished cleanly; awaiting output drain.", 2000, "ARCHIVED"),
    ("SUCCESS", "Operational payload verified successful.", 1000, "ARCHIVED"),
    ("WARNING", "Operating under non-fatal degraded execution profile.", 0, "RECOVERING"),
    ("FAILED", "Fatal fault encountered; execution halted.", 1000, "RECOVERING"),
    ("RETRYING", "Execution re-attempting via backoff timer.", 30000, "FAILED"),
    ("ROLLING_BACK", "Reverting transactional storage and memory mutations.", 15000, "TERMINATED"),
    ("RECOVERING", "Subsystem isolation and dynamic auto-repair active.", 20000, "TERMINATED"),
    ("STOPPING", "Flushing buffers, closing connections, releasing locks.", 10000, "TERMINATED"),
    ("STOPPED", "Process terminated gracefully; memory preserved.", 0, "STARTING"),
    ("TERMINATED", "Execution context destroyed, handles released.", 0, "REMOVED"),
    ("DISABLED", "Administratively blocked from execution startup.", 0, "REGISTERED"),
    ("MAINTENANCE", "Isolated for offline schema updates or system diagnostic.", 0, "READY"),
    ("ARCHIVED", "Execution record sealed and written to historical storage.", 0, "NONE"),
    ("DEPRECATED", "Active but marked for removal in future release.", 0, "DISABLED"),
    ("REMOVED", "Entity completely purged from runtime State Registry.", 0, "NONE"),
    ("UNKNOWN", "State unreadable due to memory corrupt or unmapped handle.", 0, "RECOVERING"),
)

_TIMEOUT_ACTION_MAP = {
    "NONE": "NONE",
    "TERMINATED": "TRANSITION_TO_FAILED",
    "FAILED": "TRANSITION_TO_FAILED",
    "RECOVERING": "TRANSITION_TO_RECOVERING",
}


def _build_default_catalog() -> Dict[str, StateDefinition]:
    catalog: Dict[str, StateDefinition] = {}
    for name, desc, max_ms, recovery_target in _RAW_STATES:
        action = _TIMEOUT_ACTION_MAP.get(recovery_target, "TRANSITION_TO_RECOVERING")
        if max_ms == 0:
            action = "NONE"
        catalog[name] = StateDefinition(
            state_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"aos.state.{name}")),
            state_name=name,
            description=desc,
            category=StateCategory.SYSTEM,
            allowed_previous_states=(),
            allowed_next_states=(),
            entry_conditions=(f"ENTITY_MAY_ENTER_{name}",),
            exit_conditions=(f"ENTITY_MAY_EXIT_{name}",),
            timeout_rules=TimeoutRule(max_ms, action),
            recovery_behaviour=RecoveryBehaviour(
                retry_allowed=recovery_target in ("FAILED", "RECOVERING", "RETRYING"),
                max_retries=3 if recovery_target in ("FAILED", "RECOVERING") else 0,
                fallback_state=recovery_target if recovery_target != "NONE" else name,
            ),
            events_generated=(f"EVT_STATE_{name}_ENTERED",),
            related_errors=(f"ERR_{name}_TIMEOUT",) if max_ms else (),
            priority=500,
        )
    return catalog


DEFAULT_STATE_CATALOG: Dict[str, StateDefinition] = _build_default_catalog()


# ==========================================================================
# SECTION 4 — FSM TRANSITION MATRICES
# ==========================================================================
_S = StateName

TRANSITION_MATRICES: Dict[EntityType, Dict[StateName, Tuple[StateName, ...]]] = {
    EntityType.SYSTEM: {
        _S.CREATED: (_S.REGISTERED,),
        _S.REGISTERED: (_S.VALIDATED,),
        _S.VALIDATED: (_S.INITIALIZING,),
        _S.INITIALIZING: (_S.STARTING, _S.FAILED),
        _S.STARTING: (_S.READY, _S.FAILED),
        _S.READY: (_S.RUNNING,),
        _S.RUNNING: (_S.WARNING, _S.STOPPING, _S.FAILED),
        _S.WARNING: (_S.BUSY, _S.RECOVERING, _S.RUNNING),
        _S.BUSY: (_S.RUNNING, _S.WARNING),
        _S.FAILED: (_S.RECOVERING,),
        _S.RECOVERING: (_S.RESUMING, _S.TERMINATED),
        _S.RESUMING: (_S.READY,),
        _S.STOPPING: (_S.STOPPED,),
        _S.STOPPED: (_S.TERMINATED,),
        _S.TERMINATED: (_S.REMOVED,),
        _S.REMOVED: (),
    },
    EntityType.KERNEL: {
        _S.CREATED: (_S.VALIDATED,),
        _S.VALIDATED: (_S.INITIALIZING,),
        _S.INITIALIZING: (_S.STARTING,),
        _S.STARTING: (_S.READY,),
        _S.READY: (_S.RUNNING,),
        _S.RUNNING: (_S.STOPPING, _S.FAILED),
        _S.FAILED: (_S.RECOVERING,),
        _S.RECOVERING: (_S.MAINTENANCE,),
        _S.MAINTENANCE: (_S.READY,),
        _S.STOPPING: (_S.STOPPED,),
        _S.STOPPED: (_S.TERMINATED,),
        _S.TERMINATED: (),
    },
    EntityType.TASK: {
        _S.CREATED: (_S.QUEUED,),
        _S.QUEUED: (_S.WAITING, _S.RETRYING),
        _S.WAITING: (_S.RUNNING,),
        _S.RUNNING: (_S.PROCESSING, _S.BLOCKED, _S.PAUSED),
        _S.PROCESSING: (_S.COMPLETED, _S.FAILED),
        _S.COMPLETED: (_S.SUCCESS,),
        _S.SUCCESS: (_S.ARCHIVED,),
        _S.BLOCKED: (_S.PAUSED, _S.RUNNING),
        _S.PAUSED: (_S.RUNNING,),
        _S.FAILED: (_S.RETRYING, _S.TERMINATED),
        _S.RETRYING: (_S.QUEUED,),
        _S.TERMINATED: (_S.REMOVED,),
        _S.ARCHIVED: (),
        _S.REMOVED: (),
    },
    EntityType.SERVICE: {
        _S.REGISTERED: (_S.INITIALIZING,),
        _S.INITIALIZING: (_S.STARTING,),
        _S.STARTING: (_S.READY,),
        _S.READY: (_S.RUNNING, _S.STOPPING),
        _S.RUNNING: (_S.BUSY, _S.IDLE, _S.FAILED, _S.STOPPING),
        _S.BUSY: (_S.RUNNING,),
        _S.IDLE: (_S.RUNNING,),
        _S.FAILED: (_S.RECOVERING,),
        _S.RECOVERING: (_S.STARTING,),
        _S.STOPPING: (_S.STOPPED,),
        _S.STOPPED: (),
    },
    EntityType.PLUGIN: {
        _S.INITIALIZING: (_S.READY, _S.FAILED),
        _S.READY: (_S.RUNNING, _S.DISABLED),
        _S.RUNNING: (_S.STOPPED, _S.FAILED),
        _S.DISABLED: (_S.REGISTERED,),
        _S.FAILED: (_S.RECOVERING,),
        _S.RECOVERING: (_S.INITIALIZING, _S.TERMINATED),
        _S.STOPPED: (_S.STARTING, _S.TERMINATED),
        _S.STARTING: (_S.READY,),
        _S.REGISTERED: (_S.INITIALIZING,),
        _S.TERMINATED: (_S.REMOVED,),
        _S.REMOVED: (),
    },
    EntityType.CONNECTOR: {
        _S.INITIALIZING: (_S.READY, _S.FAILED),
        _S.READY: (_S.RUNNING, _S.DISABLED),
        _S.RUNNING: (_S.STOPPED, _S.FAILED),
        _S.DISABLED: (_S.REGISTERED,),
        _S.FAILED: (_S.RECOVERING,),
        _S.RECOVERING: (_S.INITIALIZING, _S.TERMINATED),
        _S.STOPPED: (_S.STARTING, _S.TERMINATED),
        _S.STARTING: (_S.READY,),
        _S.REGISTERED: (_S.INITIALIZING,),
        _S.TERMINATED: (_S.REMOVED,),
        _S.REMOVED: (),
    },
    EntityType.RECOVERY: {
        _S.FAILED: (_S.RECOVERING,),
        _S.RECOVERING: (_S.ROLLING_BACK, _S.TERMINATED),
        _S.ROLLING_BACK: (_S.INITIALIZING,),
        _S.INITIALIZING: (_S.READY,),
        _S.READY: (),
        _S.TERMINATED: (),
    },
    EntityType.WORKFLOW: {
        _S.CREATED: (_S.QUEUED,),
        _S.QUEUED: (_S.RUNNING,),
        _S.RUNNING: (_S.PROCESSING, _S.PAUSED, _S.FAILED),
        _S.PROCESSING: (_S.COMPLETED, _S.FAILED),
        _S.COMPLETED: (_S.SUCCESS,),
        _S.SUCCESS: (_S.ARCHIVED,),
        _S.PAUSED: (_S.RUNNING,),
        _S.FAILED: (_S.RETRYING, _S.TERMINATED),
        _S.RETRYING: (_S.QUEUED,),
        _S.TERMINATED: (_S.REMOVED,),
        _S.ARCHIVED: (),
        _S.REMOVED: (),
    },
}

RECOVERY_ELIGIBLE_STATES = {StateName.FAILED, StateName.BLOCKED, StateName.UNKNOWN}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ms() -> float:
    return time.monotonic() * 1000.0


@dataclass
class StateRecord:
    entity_id: str
    entity_type: EntityType
    category: StateCategory
    current_state: StateName
    previous_state: Optional[StateName]
    entered_at_ms: float
    version: str = SPEC_VERSION
    checksum: str = ""

    def compute_checksum(self) -> str:
        payload = f"{self.entity_id}|{self.current_state.value}|{self.entered_at_ms}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def refresh_checksum(self) -> None:
        self.checksum = self.compute_checksum()

    def is_intact(self) -> bool:
        return self.checksum == self.compute_checksum()


@dataclass
class TransitionRecord:
    record_id: str
    entity_id: str
    previous_state: Optional[str]
    new_state: str
    triggering_vector: str
    timestamp: str
    prev_hash: str
    record_hash: str = field(init=False, default="")

    def compute_hash(self) -> str:
        payload = json.dumps(
            {
                "record_id": self.record_id,
                "entity_id": self.entity_id,
                "previous_state": self.previous_state,
                "new_state": self.new_state,
                "triggering_vector": self.triggering_vector,
                "timestamp": self.timestamp,
                "prev_hash": self.prev_hash,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def seal(self) -> None:
        self.record_hash = self.compute_hash()


@dataclass
class TransitionReceipt:
    success: bool
    entity_id: str
    previous_state: Optional[str]
    new_state: Optional[str]
    error: Optional[str] = None
    record_id: Optional[str] = None

    def to_result(self) -> Dict[str, Any]:
        if self.success:
            return {
                "ok": True,
                "value": {
                    "entity_id": self.entity_id,
                    "previous_state": self.previous_state,
                    "new_state": self.new_state,
                    "record_id": self.record_id,
                },
            }
        return {"ok": False, "error": self.error}


@dataclass
class StateEvent:
    event_name: str
    entity_id: str
    state: str
    timestamp: str = field(default_factory=_now_iso)
    payload: Dict[str, Any] = field(default_factory=dict)


# ==========================================================================
# SECTION 5 — MANAGERS AND REGISTRIES
# ==========================================================================
class StateRegistry:
    def __init__(self) -> None:
        self._bindings: Dict[str, Tuple[EntityType, StateCategory]] = {}
        self._lock = threading.RLock()

    def register_entity_fsm(self, entity_id: str, entity_type: EntityType,
                             category: StateCategory) -> None:
        with self._lock:
            if entity_type not in TRANSITION_MATRICES:
                raise RegistrationError(f"Unknown FSM schema for entity_type={entity_type}")
            self._bindings[entity_id] = (entity_type, category)

    def unregister_entity(self, entity_id: str) -> None:
        with self._lock:
            self._bindings.pop(entity_id, None)

    def get_binding(self, entity_id: str) -> Tuple[EntityType, StateCategory]:
        with self._lock:
            if entity_id not in self._bindings:
                raise LookupError_(f"Entity {entity_id} not bound to a registered FSM")
            return self._bindings[entity_id]

    def is_registered(self, entity_id: str) -> bool:
        with self._lock:
            return entity_id in self._bindings


class PermissionManager:
    def authorize_transition(self, subject_token: str, category: StateCategory,
                             target_state: StateName) -> bool:
        bucket = _privilege_bucket_for_category(category)
        if bucket is None:
            return True
        spec = PRIVILEGE_MATRIX[bucket]
        if bucket == "SYSTEM_KERNEL" and subject_token != spec["permitted_invoker"]:
            raise AuthError("Only AOS Micro-Kernel Core may mutate SYSTEM/KERNEL state")
        allowed_targets = spec["allowed_targets"]
        if allowed_targets is not None and target_state not in allowed_targets:
            raise AuthError(f"Target state {target_state} outside permitted set for {bucket}")
        return True


GuardFn = Callable[[str, StateName, StateName, Dict[str, Any]], bool]


class TransitionValidator:
    def __init__(self) -> None:
        self._guards: Dict[Tuple[EntityType, StateName, StateName], List[GuardFn]] = {}

    def register_guard(self, entity_type: EntityType, from_state: StateName,
                        to_state: StateName, guard: GuardFn) -> None:
        self._guards.setdefault((entity_type, from_state, to_state), []).append(guard)

    def is_transition_valid(self, entity_type: EntityType, current_state: StateName,
                             target_state: StateName) -> bool:
        matrix = TRANSITION_MATRICES.get(entity_type)
        if matrix is None:
            return False
        edges = matrix.get(current_state, ())
        return target_state in edges

    def assert_entry_conditions(self, entity_id: str, entity_type: EntityType,
                                 current_state: StateName, target_state: StateName,
                                 context: Dict[str, Any]) -> None:
        if not self.is_transition_valid(entity_type, current_state, target_state):
            raise ValidationError(
                f"Illegal transition {current_state}->{target_state} for "
                f"entity_type={entity_type} (entity_id={entity_id})")
        for guard in self._guards.get((entity_type, current_state, target_state), []):
            if not guard(entity_id, current_state, target_state, context):
                raise ValidationError(
                    f"Guard rejected transition {current_state}->{target_state} "
                    f"for entity_id={entity_id}")


class StateCore:
    def __init__(self) -> None:
        self._table: Dict[str, StateRecord] = {}
        self._lock = threading.RLock()

    def get_state(self, entity_id: str) -> StateRecord:
        record = self._table.get(entity_id)
        if record is None:
            raise LookupError_(f"No active state for entity_id={entity_id}")
        return record

    def batch_get_states(self, entity_ids: List[str]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for eid in entity_ids:
            rec = self._table.get(eid)
            if rec is not None:
                out[eid] = rec.current_state.value
        return out

    def set_state_direct(self, entity_id: str, record: StateRecord) -> bool:
        with self._lock:
            record.refresh_checksum()
            self._table[entity_id] = record
            return True

    def remove(self, entity_id: str) -> None:
        with self._lock:
            self._table.pop(entity_id, None)

    def all_records(self) -> List[StateRecord]:
        with self._lock:
            return list(self._table.values())


HookFn = Callable[[str, Dict[str, Any]], None]


class StateMachineEngine:
    def __init__(self) -> None:
        self._exit_hooks: Dict[StateName, List[HookFn]] = {}
        self._entry_hooks: Dict[StateName, List[HookFn]] = {}
        self._hook_timeout_ms = 200

    def on_exit(self, state: StateName, hook: HookFn) -> None:
        self._exit_hooks.setdefault(state, []).append(hook)

    def on_entry(self, state: StateName, hook: HookFn) -> None:
        self._entry_hooks.setdefault(state, []).append(hook)

    def run_exit_hooks(self, entity_id: str, state: StateName, context: Dict[str, Any]) -> None:
        self._run(self._exit_hooks.get(state, []), entity_id, context)

    def run_entry_hooks(self, entity_id: str, state: StateName, context: Dict[str, Any]) -> None:
        self._run(self._entry_hooks.get(state, []), entity_id, context)

    def _run(self, hooks: List[HookFn], entity_id: str, context: Dict[str, Any]) -> None:
        start = _now_ms()
        for hook in hooks:
            if _now_ms() - start > self._hook_timeout_ms:
                raise TransitionError("Hook execution timeout exceeded 200ms budget")
            hook(entity_id, context)


class StateHistory:
    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._lock = threading.RLock()
        self._last_hash: str = "0" * 64
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state_history (
                    record_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    previous_state TEXT,
                    new_state TEXT NOT NULL,
                    triggering_vector TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL
                );
                """
            )
            self._conn.commit()
            cur = self._conn.execute(
                "SELECT record_hash FROM state_history ORDER BY rowid DESC LIMIT 1;"
            )
            row = cur.fetchone()
            if row:
                self._last_hash = row[0]

    def log_state_transition(self, entity_id: str, previous_state: Optional[str],
                              new_state: str, triggering_vector: str) -> TransitionRecord:
        with self._lock:
            record = TransitionRecord(
                record_id=str(uuid.uuid4()),
                entity_id=entity_id,
                previous_state=previous_state,
                new_state=new_state,
                triggering_vector=triggering_vector,
                timestamp=_now_iso(),
                prev_hash=self._last_hash,
            )
            record.seal()
            self._conn.execute(
                "INSERT INTO state_history VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (record.record_id, record.entity_id, record.previous_state,
                 record.new_state, record.triggering_vector, record.timestamp,
                 record.prev_hash, record.record_hash),
            )
            self._conn.commit()
            self._last_hash = record.record_hash
            return record

    def query_entity_history(self, entity_id: str, start_time: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if start_time:
                cur = self._conn.execute(
                    "SELECT * FROM state_history WHERE entity_id=? AND timestamp>=? ORDER BY rowid ASC",
                    (entity_id, start_time),
                )
            else:
                cur = self._conn.execute(
                    "SELECT * FROM state_history WHERE entity_id=? ORDER BY rowid ASC",
                    (entity_id,),
                )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def verify_chain_integrity(self) -> bool:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM state_history ORDER BY rowid ASC")
            cols = [d[0] for d in cur.description]
            prev_hash = "0" * 64
            for row in cur.fetchall():
                d = dict(zip(cols, row))
                rec = TransitionRecord(
                    record_id=d["record_id"], entity_id=d["entity_id"],
                    previous_state=d["previous_state"], new_state=d["new_state"],
                    triggering_vector=d["triggering_vector"], timestamp=d["timestamp"],
                    prev_hash=d["prev_hash"],
                )
                rec.seal()
                if d["prev_hash"] != prev_hash or rec.record_hash != d["record_hash"]:
                    return False
                prev_hash = d["record_hash"]
            return True

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class StateMetrics:
    def __init__(self) -> None:
        self._durations: Dict[str, List[float]] = {}
        self._transition_count = 0
        self._error_count = 0
        self._lock = threading.RLock()

    def record_state_metrics(self, state_name: str, duration_ms: float) -> None:
        with self._lock:
            self._durations.setdefault(state_name, []).append(duration_ms)

    def record_transition(self, success: bool) -> None:
        with self._lock:
            self._transition_count += 1
            if not success:
                self._error_count += 1

    def get_system_state_summary(self) -> Dict[str, Any]:
        with self._lock:
            mtis = {
                name: (sum(vals) / len(vals) if vals else 0.0)
                for name, vals in self._durations.items()
            }
            error_rate = (
                self._error_count / self._transition_count
                if self._transition_count else 0.0
            )
            return {
                "mean_time_in_state_ms": mtis,
                "total_transitions": self._transition_count,
                "error_rate": error_rate,
            }


class RecoveryManager:
    def __init__(self, transition_fn: Callable[..., "TransitionReceipt"]) -> None:
        self._transition_fn = transition_fn
        self._attempts: Dict[str, int] = {}
        self._max_attempts = 3

    def initiate_recovery(self, entity_id: str, current_state: StateName,
                           entity_type: EntityType, failure_cause: str) -> Dict[str, Any]:
        if current_state not in RECOVERY_ELIGIBLE_STATES and current_state != StateName.WARNING:
            raise RecoveryError(f"State {current_state} is not recovery-eligible")

        attempts = self._attempts.get(entity_id, 0)
        if attempts >= self._max_attempts:
            self._transition_fn(entity_id=entity_id, target_state=StateName.TERMINATED,
                                 subject_token="AOS_MICRO_KERNEL_CORE",
                                 triggering_vector=f"RECOVERY_LOOP_EXHAUSTED:{failure_cause}")
            self._attempts.pop(entity_id, None)
            return {"outcome": "TERMINATED", "reason": "recovery_loop_failure"}

        self._attempts[entity_id] = attempts + 1
        target = StateName.RECOVERING if current_state != StateName.RECOVERING else StateName.ROLLING_BACK
        receipt = self._transition_fn(
            entity_id=entity_id, target_state=target,
            subject_token="AOS_MICRO_KERNEL_CORE",
            triggering_vector=f"RECOVERY:{failure_cause}",
        )
        if receipt.success:
            self._attempts.pop(entity_id, None)
        return {"outcome": target.value, "reason": failure_cause, "success": receipt.success}


class StateMonitor:
    def __init__(self, state_core: StateCore, recovery_manager: RecoveryManager,
                 sweep_interval_ms: int = 500) -> None:
        self._state_core = state_core
        self._recovery_manager = recovery_manager
        self._sweep_interval_ms = sweep_interval_ms
        self._stop_event: Optional[asyncio.Event] = None

    async def start_monitoring_loop(self) -> None:
        self._stop_event = asyncio.Event()
        while not self._stop_event.is_set():
            self._sweep()
            try:
                await asyncio.wait_for(self._stop_event.wait(),
                                        timeout=self._sweep_interval_ms / 1000.0)
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()

    def _sweep(self) -> None:
        now = _now_ms()
        for record in self._state_core.all_records():
            definition = DEFAULT_STATE_CATALOG.get(record.current_state.value)
            if definition is None:
                continue
            max_ms = definition.timeout_rules.max_duration_ms
            if max_ms <= 0:
                continue
            elapsed = now - record.entered_at_ms
            if elapsed > max_ms:
                try:
                    self._recovery_manager.initiate_recovery(
                        record.entity_id, record.current_state, record.entity_type,
                        failure_cause="STATE_TIMEOUT_EXCEEDED")
                except RecoveryError:
                    pass


class TransitionManager:
    def __init__(self, registry: StateRegistry, state_core: StateCore,
                 validator: TransitionValidator, engine: StateMachineEngine,
                 permission_manager: PermissionManager, history: StateHistory,
                 metrics: StateMetrics,
                 event_publisher: Callable[[StateEvent], None]) -> None:
        self._registry = registry
        self._state_core = state_core
        self._validator = validator
        self._engine = engine
        self._permissions = permission_manager
        self._history = history
        self._metrics = metrics
        self._publish = event_publisher
        self._lock = threading.RLock()

    def register_entity(self, entity_id: str, entity_type: EntityType,
                         category: StateCategory, initial_state: StateName = StateName.CREATED) -> StateRecord:
        with self._lock:
            self._registry.register_entity_fsm(entity_id, entity_type, category)
            record = StateRecord(
                entity_id=entity_id, entity_type=entity_type, category=category,
                current_state=initial_state, previous_state=None,
                entered_at_ms=_now_ms(),
            )
            self._state_core.set_state_direct(entity_id, record)
            self._history.log_state_transition(entity_id, None, initial_state.value, "REGISTRATION")
            self._publish(StateEvent(f"EVT_STATE_{initial_state.value}_ENTERED", entity_id, initial_state.value))
            return record

    def request_transition(self, entity_id: str, target_state: StateName,
                            subject_token: str = "SYSTEM",
                            triggering_vector: str = "MANUAL",
                            context: Optional[Dict[str, Any]] = None) -> TransitionReceipt:
        context = context or {}
        try:
            with self._lock:
                entity_type, category = self._registry.get_binding(entity_id)
                record = self._state_core.get_state(entity_id)

                if not record.is_intact():
                    raise TransitionError("State checksum mismatch: possible memory corruption")

                self._permissions.authorize_transition(subject_token, category, target_state)
                self._validator.assert_entry_conditions(
                    entity_id, entity_type, record.current_state, target_state, context)

                self._engine.run_exit_hooks(entity_id, record.current_state, context)

                previous_state = record.current_state
                duration_ms = _now_ms() - record.entered_at_ms
                self._metrics.record_state_metrics(previous_state.value, duration_ms)

                new_record = StateRecord(
                    entity_id=entity_id, entity_type=entity_type, category=category,
                    current_state=target_state, previous_state=previous_state,
                    entered_at_ms=_now_ms(),
                )
                self._state_core.set_state_direct(entity_id, new_record)

                self._engine.run_entry_hooks(entity_id, target_state, context)

                tr = self._history.log_state_transition(
                    entity_id, previous_state.value, target_state.value, triggering_vector)

                self._metrics.record_transition(success=True)
                self._publish(StateEvent(f"EVT_STATE_{target_state.value}_ENTERED",
                                          entity_id, target_state.value))

                return TransitionReceipt(True, entity_id, previous_state.value,
                                          target_state.value, record_id=tr.record_id)
        except StateCatalogError as exc:
            self._metrics.record_transition(success=False)
            return TransitionReceipt(False, entity_id, None, None, error=f"{exc.code}:{exc}")


class SocketBridge:
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}

    def subscribe(self, socket_name: str, handler: Callable[[Any], None]) -> None:
        self._subscribers.setdefault(socket_name, []).append(handler)

    def publish(self, socket_name: str, payload: Any) -> None:
        for handler in self._subscribers.get(socket_name, []):
            handler(payload)


class DocumentationManager:
    def __init__(self, registry: StateRegistry, state_core: StateCore) -> None:
        self._registry = registry
        self._state_core = state_core

    def generate_catalog_documentation(self, format_type: str = "json") -> str:
        catalog_export = {
            "version": SPEC_VERSION,
            "states": {name: d.to_dict() for name, d in DEFAULT_STATE_CATALOG.items()},
            "entity_types": [e.value for e in EntityType],
        }
        return json.dumps(catalog_export, indent=2)


# ==========================================================================
# SECTION 6 — PUBLIC FACADE: StateCatalogOrgan
# ==========================================================================
class StateCatalogOrgan:
    def __init__(self, db_path: str = ":memory:") -> None:
        self.registry = StateRegistry()
        self.state_core = StateCore()
        self.validator = TransitionValidator()
        self.engine = StateMachineEngine()
        self.permissions = PermissionManager()
        self.history = StateHistory(db_path=db_path)
        self.metrics = StateMetrics()
        self.socket_bridge = SocketBridge()
        self.transition_manager = TransitionManager(
            self.registry, self.state_core, self.validator, self.engine,
            self.permissions, self.history, self.metrics, self._publish_event)
        self.recovery_manager = RecoveryManager(self.transition_manager.request_transition)
        self.monitor = StateMonitor(self.state_core, self.recovery_manager)
        self.documentation = DocumentationManager(self.registry, self.state_core)
        self.cns: Optional[Any] = None

    def _publish_event(self, event: StateEvent) -> None:
        self.socket_bridge.publish("state_hist", event)

    def register_entity(self, entity_id: Optional[str], entity_type: EntityType,
                         category: StateCategory,
                         initial_state: StateName = StateName.CREATED) -> str:
        eid = entity_id or str(uuid.uuid4())
        self.transition_manager.register_entity(eid, entity_type, category, initial_state)
        return eid

    def unregister_entity(self, entity_id: str) -> None:
        self.registry.unregister_entity(entity_id)
        self.state_core.remove(entity_id)

    def request_transition(self, entity_id: str, target_state: StateName,
                            subject_token: str = "SYSTEM",
                            triggering_vector: str = "MANUAL",
                            context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        receipt = self.transition_manager.request_transition(
            entity_id, target_state, subject_token, triggering_vector, context)
        return receipt.to_result()

    def get_state(self, entity_id: str) -> Dict[str, Any]:
        record = self.state_core.get_state(entity_id)
        return {
            "entity_id": record.entity_id,
            "entity_type": record.entity_type.value,
            "category": record.category.value,
            "current_state": record.current_state.value,
            "previous_state": record.previous_state.value if record.previous_state else None,
        }

    def batch_get_states(self, entity_ids: List[str]) -> Dict[str, str]:
        return self.state_core.batch_get_states(entity_ids)

    def initiate_recovery(self, entity_id: str, failure_cause: str) -> Dict[str, Any]:
        record = self.state_core.get_state(entity_id)
        return self.recovery_manager.initiate_recovery(
            entity_id, record.current_state, record.entity_type, failure_cause)

    def query_entity_history(self, entity_id: str) -> List[Dict[str, Any]]:
        return self.history.query_entity_history(entity_id)

    def verify_history_integrity(self) -> bool:
        return self.history.verify_chain_integrity()

    def get_metrics_summary(self) -> Dict[str, Any]:
        return self.metrics.get_system_state_summary()

    async def start_monitor(self) -> None:
        await self.monitor.start_monitoring_loop()

    def stop_monitor(self) -> None:
        self.monitor.stop()

    def export_documentation(self, format_type: str = "json") -> str:
        return self.documentation.generate_catalog_documentation(format_type)

    # ── CNS Integration (Serializes Dict Receipts Properly) ─────────────

    async def start_cns(self, cns) -> None:
        self.cns = cns
        await self.cns.subscribe("STATE_TRANSITION_REQUEST", "organ_32", self._handle_cns_state_request)
        logger.info("StateCatalogOrgan connected to CNS.")

    async def _handle_cns_state_request(self, env) -> None:
        from core_organs.organ_02_cns_single_file import EventEnvelope
        payload = env.payload or {}
        entity_id = payload.get("entity_id")
        target_state_str = payload.get("target_state")
        
        try:
            target_state = StateName(target_state_str)
            receipt = self.request_transition(
                entity_id=entity_id,
                target_state=target_state,
                subject_token=getattr(env, "source_organ", "SYSTEM"),
                triggering_vector="CNS",
                context=payload.get("context")
            )
            
            if self.cns:
                await self.cns.publish(EventEnvelope(
                    topic="STATE_TRANSITION_COMPLETED",
                    source_organ="organ_32",
                    payload={"entity_id": entity_id, "receipt": receipt}
                ))
        except Exception as e:
            if self.cns:
                await self.cns.publish(EventEnvelope(
                    topic="STATE_TRANSITION_FAILED",
                    source_organ="organ_32",
                    payload={"entity_id": entity_id, "error": str(e)}
                ))

    def shutdown(self) -> None:
        self.stop_monitor()
        self.history.close()


if __name__ == "__main__":
    organ = StateCatalogOrgan()
    eid = organ.register_entity(None, EntityType.TASK, StateCategory.TASK)
    print("Registered task entity:", eid)
    res = organ.request_transition(eid, StateName.QUEUED, subject_token="EXECUTION_ORCHESTRATOR")
    print("Transition result:", res)
    organ.shutdown()
