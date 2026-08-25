"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 26
Name: Event Catalog

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Event Catalog]
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
Dependencies: enum, typing, __future__, time, asyncio...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_26_event_catalog.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
organ_26_event_catalog.py
Hojaiga Automation OS — Organ 26: Event Catalog
Authority: Event_Catalog.md > Organ Specification > Master Architecture Blueprint

PRE-CODE DIAGRAM (spec-derived)
--------------------------------
KERNEL -> EVENT CATALOG [Core, Registry, Metadata, VersionMgr, CategoryMgr, DiscoveryMgr]
        -> EVENT VALIDATOR [PayloadValidator, PermissionManager, CompatibilityValidator]
        -> EVENT ROUTER [Broadcast|P2P|PubSub|Priority|Filter]
        -> COMMUNICATION BUS -> {Organs, Runtime, Plugins, Interface, External Connectors}

ACTUAL-CODE DIAGRAM (implementation-reflecting)
------------------------------------------------
EventCatalog (composition root)
  ├─ EventRegistry        (register/lookup/dedupe)
  ├─ EventCategoryManager (32 categories + rules)
  ├─ EventMetadataManager (owner/annotations)
  ├─ EventVersionManager  (semver + deprecation)
  ├─ EventValidator        ├─ PayloadValidator
  │                        ├─ PermissionManager
  │                        └─ CompatibilityValidator
  ├─ EventRouter           ├─ PriorityQueue
  │                        └─ RoutingTopology (broadcast/p2p/pubsub)
  ├─ EventHistory (append-only + DLQ)
  ├─ EventMetrics
  ├─ AuditManager
  ├─ RecoveryManager (replay / DLQ reprocessing)
  └─ CommunicationLayer socket adapter (publish/subscribe only — no direct organ imports)

No organ is imported directly. All cross-organ traffic flows through
`EventCatalog.publish()` / `EventCatalog.subscribe()`, which are the only
public sockets this organ exposes.
"""


import asyncio
import re
import time
import uuid
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Awaitable, Optional

logger = logging.getLogger("aos.organ26.event_catalog")

# ---------------------------------------------------------------------------
# Enums (Section 5 — Event Structure)
# ---------------------------------------------------------------------------

class EventCategory(str, Enum):
    SYSTEM = "SYSTEM"; KERNEL = "KERNEL"; CONFIGURATION = "CONFIGURATION"
    RESOURCE = "RESOURCE"; SCHEDULER = "SCHEDULER"; SERVICE = "SERVICE"
    DEPENDENCY = "DEPENDENCY"; CAPABILITY = "CAPABILITY"; COMMUNICATION = "COMMUNICATION"
    SECURITY = "SECURITY"; MEMORY = "MEMORY"; KNOWLEDGE = "KNOWLEDGE"; BRAIN = "BRAIN"
    CNS = "CNS"; LEARNING = "LEARNING"; AUTOMATION = "AUTOMATION"; AGENTS = "AGENTS"
    CONTROLLERS = "CONTROLLERS"; INTERFACE = "INTERFACE"; LLM_RUNTIME = "LLM_RUNTIME"
    PLUGIN = "PLUGIN"; CONNECTOR = "CONNECTOR"; WINDOWS = "WINDOWS"; PLAYWRIGHT = "PLAYWRIGHT"
    API = "API"; WORKFLOW = "WORKFLOW"; USER = "USER"; BACKGROUND = "BACKGROUND"
    DIAGNOSTICS = "DIAGNOSTICS"; UPDATE = "UPDATE"; BACKUP = "BACKUP"; RECOVERY = "RECOVERY"


class EventPriority(str, Enum):
    CRITICAL = "CRITICAL"; HIGH = "HIGH"; NORMAL = "NORMAL"; LOW = "LOW"; BACKGROUND = "BACKGROUND"


_PRIORITY_ORDER = {EventPriority.CRITICAL: 0, EventPriority.HIGH: 1,
                    EventPriority.NORMAL: 2, EventPriority.LOW: 3, EventPriority.BACKGROUND: 4}


class PermissionLevel(str, Enum):
    KERNEL_ROOT = "KERNEL_ROOT"; SYSTEM_ORGAN = "SYSTEM_ORGAN"
    PLUGIN_RESTRICTED = "PLUGIN_RESTRICTED"; GUEST = "GUEST"


class SecurityClassification(str, Enum):
    PUBLIC = "PUBLIC"; INTERNAL = "INTERNAL"; CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"; SECRET_KERNEL = "SECRET_KERNEL"


class EventState(str, Enum):
    CREATED = "CREATED"; VALIDATED = "VALIDATED"; PUBLISHED = "PUBLISHED"
    QUEUED = "QUEUED"; DELIVERED = "DELIVERED"; PROCESSED = "PROCESSED"
    ACKNOWLEDGED = "ACKNOWLEDGED"; COMPLETED = "COMPLETED"; ARCHIVED = "ARCHIVED"
    DLQ = "DLQ"


class RoutingTopology(str, Enum):
    BROADCAST = "BROADCAST"; POINT_TO_POINT = "POINT_TO_POINT"; PUBSUB = "PUBSUB"


EVENT_NAME_PATTERN = re.compile(r"^[A-Z0-9_]+\.[A-Z0-9_]+(\.[A-Z0-9_]+)*$")
SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

# ---------------------------------------------------------------------------
# Data Contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetryPolicy:
    maxRetries: int = 3
    backoffMs: int = 200
    exponential: bool = True


@dataclass(frozen=True)
class EventEnvelope:
    eventId: str
    eventName: str
    category: EventCategory
    description: str
    producer: str
    consumer: list[str]
    payloadSchema: str
    payload: dict[str, Any]
    priority: EventPriority
    timestamp: int
    correlationId: str
    sessionId: str
    workflowId: str
    version: str
    permissionLevel: PermissionLevel
    retryPolicy: RetryPolicy
    timeout: int
    securityClassification: SecurityClassification
    deprecatedFlag: bool
    owner: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["priority"] = self.priority.value
        d["permissionLevel"] = self.permissionLevel.value
        d["securityClassification"] = self.securityClassification.value
        return d


@dataclass(frozen=True)
class EventManifest:
    """Boot-time / compile-time registration manifest for an event type."""
    eventName: str
    category: EventCategory
    description: str
    payloadSchema: dict[str, Any]
    allowedProducers: set[str]
    allowedConsumers: set[str]
    version: str = "1.0.0"
    defaultPriority: EventPriority = EventPriority.NORMAL
    defaultPermissionLevel: PermissionLevel = PermissionLevel.SYSTEM_ORGAN
    defaultSecurityClassification: SecurityClassification = SecurityClassification.INTERNAL
    deprecated: bool = False


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Event Registry
# ---------------------------------------------------------------------------

class EventRegistry:
    """Source of truth for all declared event specifications."""

    def __init__(self) -> None:
        self._manifests: dict[str, EventManifest] = {}
        self._by_category: dict[EventCategory, set[str]] = defaultdict(set)

    def register(self, manifest: EventManifest) -> None:
        if not EVENT_NAME_PATTERN.match(manifest.eventName):
            raise ValueError(f"Invalid event name format: {manifest.eventName}")
        if manifest.eventName in self._manifests:
            raise ValueError(f"Duplicate event registration: {manifest.eventName}")
        if not SEMVER_PATTERN.match(manifest.version):
            raise ValueError(f"Invalid semver: {manifest.version}")
        self._manifests[manifest.eventName] = manifest
        self._by_category[manifest.category].add(manifest.eventName)
        logger.info("event.registered name=%s category=%s", manifest.eventName, manifest.category)

    def get(self, event_name: str) -> Optional[EventManifest]:
        return self._manifests.get(event_name)

    def exists(self, event_name: str) -> bool:
        return event_name in self._manifests

    def list_by_category(self, category: EventCategory) -> list[str]:
        return sorted(self._by_category.get(category, set()))

    def all_names(self) -> list[str]:
        return sorted(self._manifests.keys())


# ---------------------------------------------------------------------------
# Event Category Manager
# ---------------------------------------------------------------------------

class EventCategoryManager:
    """Category-level security/priority defaults for the 32 categories."""

    _DEFAULT_PRIORITY: dict[EventCategory, EventPriority] = {
        EventCategory.SYSTEM: EventPriority.CRITICAL,
        EventCategory.SECURITY: EventPriority.CRITICAL,
        EventCategory.KERNEL: EventPriority.HIGH,
        EventCategory.RECOVERY: EventPriority.HIGH,
        EventCategory.BACKGROUND: EventPriority.BACKGROUND,
        EventCategory.DIAGNOSTICS: EventPriority.LOW,
    }

    def default_priority(self, category: EventCategory) -> EventPriority:
        return self._DEFAULT_PRIORITY.get(category, EventPriority.NORMAL)

    def validate_category(self, category: str) -> EventCategory:
        try:
            return EventCategory(category)
        except ValueError:
            logger.warning("category.unregistered value=%s -> BACKGROUND", category)
            return EventCategory.BACKGROUND


# ---------------------------------------------------------------------------
# Event Metadata Manager
# ---------------------------------------------------------------------------

class EventMetadataManager:
    def __init__(self) -> None:
        self._metadata: dict[str, dict[str, Any]] = defaultdict(dict)

    def set(self, event_name: str, key: str, value: Any) -> None:
        self._metadata[event_name][key] = value

    def get(self, event_name: str) -> dict[str, Any]:
        return dict(self._metadata.get(event_name, {}))


# ---------------------------------------------------------------------------
# Event Version Manager
# ---------------------------------------------------------------------------

class EventVersionManager:
    def __init__(self, registry: EventRegistry) -> None:
        self._registry = registry
        self._deprecated: set[str] = set()

    def is_compatible(self, event_name: str, incoming_version: str) -> bool:
        manifest = self._registry.get(event_name)
        if manifest is None:
            return False
        reg_major = int(manifest.version.split(".")[0])
        in_major = int(incoming_version.split(".")[0])
        return reg_major == in_major

    def deprecate(self, event_name: str) -> None:
        self._deprecated.add(event_name)

    def is_deprecated(self, event_name: str) -> bool:
        return event_name in self._deprecated


# ---------------------------------------------------------------------------
# Payload / Permission / Compatibility Validators
# ---------------------------------------------------------------------------

class PayloadValidator:
    """Minimal structural JSON-Schema-like validator (stdlib only)."""

    def validate(self, payload: dict[str, Any], schema: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        required = schema.get("required", [])
        props = schema.get("properties", {})
        for field_name in required:
            if field_name not in payload:
                errors.append(f"missing required field: {field_name}")
        for key, val in payload.items():
            spec = props.get(key)
            if spec is None:
                if schema.get("additionalProperties", True) is False:
                    errors.append(f"unexpected field: {key}")
                continue
            expected = spec.get("type")
            if expected and not self._type_ok(val, expected):
                errors.append(f"type mismatch for {key}: expected {expected}")
        return ValidationResult(valid=not errors, errors=errors)

    @staticmethod
    def _type_ok(value: Any, expected: str) -> bool:
        mapping = {"string": str, "integer": int, "number": (int, float),
                   "boolean": bool, "object": dict, "array": list}
        py_type = mapping.get(expected)
        return py_type is None or isinstance(value, py_type)


class PermissionManager:
    def check(self, manifest: EventManifest, producer: str, consumers: list[str]) -> ValidationResult:
        errors: list[str] = []
        if manifest.allowedProducers and producer not in manifest.allowedProducers:
            errors.append(f"producer '{producer}' not authorized for {manifest.eventName}")
        if manifest.allowedConsumers:
            unauthorized = [c for c in consumers if c not in manifest.allowedConsumers]
            if unauthorized:
                errors.append(f"unauthorized consumers: {unauthorized}")
        return ValidationResult(valid=not errors, errors=errors)


class CompatibilityValidator:
    def __init__(self, version_manager: EventVersionManager) -> None:
        self._version_manager = version_manager

    def check(self, event_name: str, version: str) -> ValidationResult:
        if not self._version_manager.is_compatible(event_name, version):
            return ValidationResult(valid=False, errors=[f"incompatible major version for {event_name}: {version}"])
        return ValidationResult(valid=True)


# ---------------------------------------------------------------------------
# Event Validator (orchestrator)
# ---------------------------------------------------------------------------

class EventValidator:
    def __init__(self, registry: EventRegistry, version_manager: EventVersionManager) -> None:
        self._registry = registry
        self._payload_validator = PayloadValidator()
        self._permission_manager = PermissionManager()
        self._compat_validator = CompatibilityValidator(version_manager)

    def validate(self, envelope: EventEnvelope) -> ValidationResult:
        errors: list[str] = []
        manifest = self._registry.get(envelope.eventName)
        if manifest is None:
            return ValidationResult(valid=False, errors=[f"unregistered event: {envelope.eventName}"])

        payload_result = self._payload_validator.validate(envelope.payload, manifest.payloadSchema)
        errors.extend(payload_result.errors)

        perm_result = self._permission_manager.check(manifest, envelope.producer, envelope.consumer)
        errors.extend(perm_result.errors)

        compat_result = self._compat_validator.check(envelope.eventName, envelope.version)
        errors.extend(compat_result.errors)

        return ValidationResult(valid=not errors, errors=errors)


# ---------------------------------------------------------------------------
# Priority Queue + Router
# ---------------------------------------------------------------------------

class PriorityQueue:
    def __init__(self) -> None:
        self._tiers: dict[EventPriority, deque[EventEnvelope]] = {p: deque() for p in EventPriority}

    def enqueue(self, event: EventEnvelope) -> bool:
        self._tiers[event.priority].append(event)
        return True

    def dequeue(self) -> Optional[EventEnvelope]:
        for priority in sorted(_PRIORITY_ORDER, key=lambda p: _PRIORITY_ORDER[p]):
            if self._tiers[priority]:
                return self._tiers[priority].popleft()
        return None

    def depth(self) -> int:
        return sum(len(q) for q in self._tiers.values())


Handler = Callable[[EventEnvelope], Awaitable[None]]


class EventRouter:
    """Broadcast / Point-to-Point / Pub-Sub routing with filter support."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, list[tuple[str, Handler]]] = defaultdict(list)
        self.queue = PriorityQueue()

    def subscribe(self, pattern: str, handler: Handler) -> str:
        handle_id = str(uuid.uuid4())
        self._subscriptions[pattern].append((handle_id, handler))
        return handle_id

    def unsubscribe(self, pattern: str, handle_id: str) -> None:
        self._subscriptions[pattern] = [
            (hid, h) for hid, h in self._subscriptions[pattern] if hid != handle_id
        ]

    def _matching_handlers(self, event_name: str) -> list[Handler]:
        handlers: list[Handler] = []
        for pattern, subs in self._subscriptions.items():
            if self._matches(pattern, event_name):
                handlers.extend(h for _, h in subs)
        return handlers

    @staticmethod
    def _matches(pattern: str, event_name: str) -> bool:
        if pattern == "*" or pattern == event_name:
            return True
        if pattern.endswith(".*"):
            return event_name.startswith(pattern[:-1])
        return False

    async def route(self, event: EventEnvelope, topology: RoutingTopology = RoutingTopology.PUBSUB) -> int:
        self.queue.enqueue(event)
        handlers = self._matching_handlers(event.eventName)
        delivered = 0
        if topology == RoutingTopology.POINT_TO_POINT and event.consumer:
            handlers = handlers[:1]
        for handler in handlers:
            try:
                await handler(event)
                delivered += 1
            except Exception:  # noqa: BLE001
                logger.exception("router.delivery_failed event=%s", event.eventName)
        return delivered


# ---------------------------------------------------------------------------
# History / Dead Letter Queue / Recovery
# ---------------------------------------------------------------------------

class EventHistory:
    """Append-only in-memory time-series log with bounded retention."""

    def __init__(self, max_size: int = 100_000) -> None:
        self._log: deque[tuple[EventEnvelope, EventState]] = deque(maxlen=max_size)
        self._dlq: deque[EventEnvelope] = deque(maxlen=max_size)

    def append(self, event: EventEnvelope, state: EventState) -> None:
        self._log.append((event, state))
        if state == EventState.DLQ:
            self._dlq.append(event)

    def replay(self, correlation_id: Optional[str] = None,
               category: Optional[EventCategory] = None) -> list[EventEnvelope]:
        results = [e for e, _ in self._log]
        if correlation_id:
            results = [e for e in results if e.correlationId == correlation_id]
        if category:
            results = [e for e in results if e.category == category]
        return results

    def dlq_snapshot(self) -> list[EventEnvelope]:
        return list(self._dlq)


class EventMetrics:
    def __init__(self) -> None:
        self.published = 0
        self.validated = 0
        self.rejected = 0
        self.delivered = 0
        self.dlq_count = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "published": self.published, "validated": self.validated,
            "rejected": self.rejected, "delivered": self.delivered,
            "dlq_count": self.dlq_count,
        }


class AuditManager:
    def __init__(self) -> None:
        self._ledger: list[dict[str, Any]] = []

    def record(self, event: EventEnvelope, action: str) -> None:
        self._ledger.append({
            "eventId": event.eventId, "eventName": event.eventName,
            "action": action, "timestamp": time.time(),
            "classification": event.securityClassification.value,
        })

    def ledger(self) -> list[dict[str, Any]]:
        return list(self._ledger)


class RecoveryManager:
    def __init__(self, history: EventHistory, router: EventRouter, validator: EventValidator) -> None:
        self._history = history
        self._router = router
        self._validator = validator
        self._poison_counts: dict[str, int] = defaultdict(int)

    async def replay_dlq(self, max_retries: int = 3) -> int:
        replayed = 0
        for event in self._history.dlq_snapshot():
            if self._poison_counts[event.eventId] >= max_retries:
                continue
            result = self._validator.validate(event)
            if result.valid:
                await self._router.route(event)
                replayed += 1
            else:
                self._poison_counts[event.eventId] += 1
        return replayed


# ---------------------------------------------------------------------------
# Communication Layer Socket Adapter
# ---------------------------------------------------------------------------

class CommunicationLayerSocket:
    """The ONLY surface this organ exposes to other organs (no direct imports)."""

    def __init__(self, catalog: "EventCatalog") -> None:
        self._catalog = catalog

    async def publish(self, envelope: EventEnvelope) -> ValidationResult:
        return await self._catalog.publish(envelope)

    def subscribe(self, pattern: str, handler: Handler) -> str:
        return self._catalog.subscribe(pattern, handler)


# ---------------------------------------------------------------------------
# EventCatalog — Composition Root (Organ 26 public interface)
# ---------------------------------------------------------------------------

class EventCatalog:
    """
    Public Interfaces (Organ Specification §Public API Rules)
    -----------------------------------------------------------
    register_event(manifest) -> None
    build_envelope(...)      -> EventEnvelope
    publish(envelope)        -> ValidationResult
    subscribe(pattern, handler) -> subscription handle (str)
    unsubscribe(pattern, handle) -> None
    replay(correlation_id=None, category=None) -> list[EventEnvelope]
    metrics() -> dict
    """

    def __init__(self) -> None:
        self.registry = EventRegistry()
        self.category_manager = EventCategoryManager()
        self.metadata_manager = EventMetadataManager()
        self.version_manager = EventVersionManager(self.registry)
        self.validator = EventValidator(self.registry, self.version_manager)
        self.router = EventRouter()
        self.history = EventHistory()
        self.metrics = EventMetrics()
        self.audit = AuditManager()
        self.recovery = RecoveryManager(self.history, self.router, self.validator)
        self.socket = CommunicationLayerSocket(self)
        self._bootstrap_standard_events()

    # ---- Registration -----------------------------------------------------

    def register_event(self, manifest: EventManifest) -> None:
        self.registry.register(manifest)

    def _bootstrap_standard_events(self) -> None:
        self.register_event(EventManifest(
            eventName="SYSTEM.CRASHED",
            category=EventCategory.SYSTEM,
            description="Unrecoverable system-level failure signal.",
            payloadSchema={"required": ["reason"], "properties": {"reason": {"type": "string"}},
                            "additionalProperties": True},
            allowedProducers=set(), allowedConsumers=set(),
            defaultPriority=EventPriority.CRITICAL,
        ))
        self.register_event(EventManifest(
            eventName="SECURITY.ALERT",
            category=EventCategory.SECURITY,
            description="Security policy violation alert.",
            payloadSchema={"required": ["reason"], "properties": {"reason": {"type": "string"}},
                            "additionalProperties": True},
            allowedProducers=set(), allowedConsumers=set(),
            defaultPriority=EventPriority.CRITICAL,
        ))

    # ---- Envelope construction ---------------------------------------------

    def build_envelope(
        self, *, event_name: str, producer: str, consumer: list[str],
        payload: dict[str, Any], correlation_id: Optional[str] = None,
        session_id: str = "", workflow_id: str = "",
        permission_level: PermissionLevel = PermissionLevel.SYSTEM_ORGAN,
        security_classification: Optional[SecurityClassification] = None,
        retry_policy: Optional[RetryPolicy] = None, timeout: int = 30_000,
    ) -> EventEnvelope:
        manifest = self.registry.get(event_name)
        if manifest is None:
            raise ValueError(f"cannot build envelope for unregistered event: {event_name}")
        return EventEnvelope(
            eventId=str(uuid.uuid4()), eventName=event_name, category=manifest.category,
            description=manifest.description, producer=producer, consumer=consumer,
            payloadSchema=event_name, payload=payload,
            priority=manifest.defaultPriority, timestamp=int(time.time() * 1000),
            correlationId=correlation_id or str(uuid.uuid4()), sessionId=session_id,
            workflowId=workflow_id, version=manifest.version, permissionLevel=permission_level,
            retryPolicy=retry_policy or RetryPolicy(), timeout=timeout,
            securityClassification=security_classification or manifest.defaultSecurityClassification,
            deprecatedFlag=self.version_manager.is_deprecated(event_name), owner=producer,
        )

    # ---- Pipelines (publish path) ------------------------------------------

    async def publish(self, envelope: EventEnvelope) -> ValidationResult:
        """PublishPipeline -> ValidationPipeline -> RoutingPipeline -> HistoryPipeline."""
        self.metrics.published += 1
        result = self.validator.validate(envelope)
        if not result.valid:
            self.metrics.rejected += 1
            self.history.append(envelope, EventState.DLQ)
            self.metrics.dlq_count += 1
            self.audit.record(envelope, action="REJECTED")
            logger.warning("publish.rejected event=%s errors=%s", envelope.eventName, result.errors)
            return result

        self.metrics.validated += 1
        self.history.append(envelope, EventState.VALIDATED)
        delivered = await self.router.route(envelope)
        self.metrics.delivered += delivered
        self.history.append(envelope, EventState.DELIVERED if delivered else EventState.QUEUED)
        if envelope.securityClassification in (
            SecurityClassification.RESTRICTED, SecurityClassification.SECRET_KERNEL
        ):
            self.audit.record(envelope, action="PUBLISHED")
        return result

    def subscribe(self, pattern: str, handler: Handler) -> str:
        return self.router.subscribe(pattern, handler)

    def unsubscribe(self, pattern: str, handle_id: str) -> None:
        self.router.unsubscribe(pattern, handle_id)

    def replay(self, correlation_id: Optional[str] = None,
               category: Optional[EventCategory] = None) -> list[EventEnvelope]:
        return self.history.replay(correlation_id=correlation_id, category=category)

    def get_metrics(self) -> dict[str, int]:
        return self.metrics.snapshot()
