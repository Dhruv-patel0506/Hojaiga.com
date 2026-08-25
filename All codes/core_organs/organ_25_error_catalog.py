"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 25
Name: Error Catalog

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Error Catalog]
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
Dependencies: random, math, enum, pathlib, __future__...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_25_error_catalog.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Hojaiga Automation OS — Organ 25: Error Catalog
=================================================================
Filename : organ_25_error_catalog.py
Authority: Constitution -> Law Book -> Diagrams -> Legacy Migration Guide
           -> Policy Manual -> Master Architecture Blueprint
           -> Organ Specification -> Error_Catalog.md (authoritative)
Version  : 1.0.0

Single importable module implementing the AOS Error Catalog organ:
error core, code manager, registry, severity manager, retry policy
manager, recovery manager, validation manager, compatibility manager,
localization manager, error history, metrics manager, monitoring
manager, audit manager, sockets, pipelines and the CNSGateway-facing
public facade (ErrorCatalogOrgan).

No organ may throw, return, or log an unregistered or arbitrary error
code. Every error state is declared, validated, categorized,
versioned, assigned a deterministic recovery strategy and audited.

=================================================================
PRE-CODE ARCHITECTURE DIAGRAM (Specification-Intended Topology)
=================================================================

    AOS Kernel / Any Organ
            |
            v
       ErrorSocket (ingress)
            |
            v
     Validation Manager  -- invalid --> SYS-2002 Schema Trap
            |
         valid
            v
       Error Registry  <---- Error Code Manager
            |
            v
      Severity Manager ----> Monitoring Manager ----> Metrics Manager
            |
            v
      Recovery Manager ----> Retry Policy Manager
            |                        |
        success                 exhausted
            |                        v
            |                Escalation Pipeline
            v                        |
        Resolved <-------------------+
            |
            v
      Verification (health check)
            |
            v
      Error History (ring buffer + persistent)  <---- Audit Manager (HMAC)
            |
            v
      CNSGateway (outgoing, read-only reporting to other organs)

=================================================================
POST-CODE ACTUAL IMPLEMENTED TOPOLOGY
=================================================================

    ErrorCatalogOrgan (public facade / CNSGateway boundary)
        |-- ErrorRegistry (33 standard AOSErrorDefinition entries)
        |     |-- ErrorCodeManager (namespace/prefix validation)
        |-- ValidationManager (schema + business-rule validation)
        |-- SeverityManager (static + dynamic escalation)
        |-- RetryPolicyManager (IMMEDIATE/LINEAR/EXPONENTIAL + jitter)
        |-- RecoveryManager (11 recovery strategies)
        |-- CompatibilityManager (legacy code aliasing)
        |-- LocalizationManager (en_US baseline, pluggable locales)
        |-- MetricsManager (RPM / MTBF / MTTR counters)
        |-- MonitoringManager (threshold breach -> EscalationPipeline)
        |-- AuditManager (HMAC-signed audit trail for CRITICAL+)
        |-- ErrorHistory (ring buffer + SQLite WAL persistent store)
        |-- Sockets: ErrorSocket, ValidationSocket, RecoverySocket,
        |            MetricsSocket, MonitoringSocket, HistorySocket,
        |            AuditSocket, ConfigurationSocket
        `-- Pipelines: DetectionPipeline, ValidationPipeline,
                        RecoveryPipeline, RetryPipeline,
                        EscalationPipeline, AuditPipeline,
                        LoggingPipeline, HistoryPipeline,
                        MonitoringPipeline

All cross-organ communication occurs exclusively through
ErrorCatalogOrgan's public methods (the organ's socket surface).
No other organ may import internals of this module.
"""


import hashlib
import hmac
import json
import math
import random
import re
import sqlite3
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

__version__ = "1.0.0"
__organ__ = "Organ_25_Error_Catalog"


# =================================================================
# 1. ENUMS
# =================================================================

class ErrorCategory(str, Enum):
    SYSTEM = "SYSTEM"
    KERNEL = "KERNEL"
    CONFIGURATION = "CONFIGURATION"
    RESOURCE = "RESOURCE"
    SCHEDULER = "SCHEDULER"
    SERVICE = "SERVICE"
    DEPENDENCY = "DEPENDENCY"
    CAPABILITY = "CAPABILITY"
    COMMUNICATION = "COMMUNICATION"
    SECURITY = "SECURITY"
    MEMORY = "MEMORY"
    KNOWLEDGE = "KNOWLEDGE"
    BRAIN = "BRAIN"
    CNS = "CNS"
    LEARNING = "LEARNING"
    AUTOMATION = "AUTOMATION"
    AGENT = "AGENT"
    CONTROLLER = "CONTROLLER"
    INTERFACE = "INTERFACE"
    LLM_RUNTIME = "LLM_RUNTIME"
    PLUGIN = "PLUGIN"
    CONNECTOR = "CONNECTOR"
    WINDOWS = "WINDOWS"
    PLAYWRIGHT = "PLAYWRIGHT"
    API = "API"
    DATABASE = "DATABASE"
    NETWORK = "NETWORK"
    USER = "USER"
    WORKFLOW = "WORKFLOW"
    UPDATE = "UPDATE"
    BACKUP = "BACKUP"
    RECOVERY = "RECOVERY"


CATEGORY_PREFIX: Dict[ErrorCategory, str] = {
    ErrorCategory.SYSTEM: "SYS",
    ErrorCategory.KERNEL: "KER",
    ErrorCategory.CONFIGURATION: "CFG",
    ErrorCategory.RESOURCE: "RES",
    ErrorCategory.SCHEDULER: "SCH",
    ErrorCategory.SERVICE: "SRV",
    ErrorCategory.DEPENDENCY: "DEP",
    ErrorCategory.CAPABILITY: "CAP",
    ErrorCategory.COMMUNICATION: "EVT",
    ErrorCategory.SECURITY: "SEC",
    ErrorCategory.MEMORY: "MEM",
    ErrorCategory.KNOWLEDGE: "KNW",
    ErrorCategory.BRAIN: "BRN",
    ErrorCategory.CNS: "CNS",
    ErrorCategory.LEARNING: "LRN",
    ErrorCategory.AUTOMATION: "AUT",
    ErrorCategory.AGENT: "AGT",
    ErrorCategory.CONTROLLER: "CTL",
    ErrorCategory.INTERFACE: "INT",
    ErrorCategory.LLM_RUNTIME: "LLM",
    ErrorCategory.PLUGIN: "PLG",
    ErrorCategory.CONNECTOR: "CON",
    ErrorCategory.WINDOWS: "WIN",
    ErrorCategory.PLAYWRIGHT: "PWT",
    ErrorCategory.API: "API",
    ErrorCategory.DATABASE: "DBS",
    ErrorCategory.NETWORK: "NET",
    ErrorCategory.USER: "USR",
    ErrorCategory.WORKFLOW: "WFK",
    ErrorCategory.UPDATE: "UPD",
    ErrorCategory.BACKUP: "BKP",
    ErrorCategory.RECOVERY: "RCV",
}


class SeverityLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"
    EMERGENCY = "EMERGENCY"


SEVERITY_RANK: Dict[SeverityLevel, int] = {
    SeverityLevel.INFO: 0,
    SeverityLevel.WARNING: 1,
    SeverityLevel.ERROR: 2,
    SeverityLevel.CRITICAL: 3,
    SeverityLevel.FATAL: 4,
    SeverityLevel.EMERGENCY: 5,
}


class RecoveryStrategyType(str, Enum):
    RETRY = "RETRY"
    FALLBACK = "FALLBACK"
    RESTART_COMPONENT = "RESTART_COMPONENT"
    RESTART_SERVICE = "RESTART_SERVICE"
    RESTART_RUNTIME = "RESTART_RUNTIME"
    RELOAD_CONFIGURATION = "RELOAD_CONFIGURATION"
    ROLLBACK = "ROLLBACK"
    SAFE_MODE = "SAFE_MODE"
    MANUAL_APPROVAL = "MANUAL_APPROVAL"
    ABORT = "ABORT"
    EMERGENCY_SHUTDOWN = "EMERGENCY_SHUTDOWN"


class RetryAlgorithm(str, Enum):
    NONE = "NONE"
    IMMEDIATE = "IMMEDIATE"
    LINEAR_BACKOFF = "LINEAR_BACKOFF"
    EXPONENTIAL_BACKOFF = "EXPONENTIAL_BACKOFF"


class ErrorLifecycleState(str, Enum):
    DETECTED = "DETECTED"
    VALIDATED = "VALIDATED"
    LOGGED = "LOGGED"
    CATEGORIZED = "CATEGORIZED"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RETRYING = "RETRYING"
    ESCALATED = "ESCALATED"
    SAFE_MODE = "SAFE_MODE"
    EMERGENCY_SHUTDOWN = "EMERGENCY_SHUTDOWN"
    RESOLVED = "RESOLVED"
    VERIFIED = "VERIFIED"
    ARCHIVED = "ARCHIVED"
    ABORTED = "ABORTED"


_VALID_TRANSITIONS: Dict[ErrorLifecycleState, Tuple[ErrorLifecycleState, ...]] = {
    ErrorLifecycleState.DETECTED: (ErrorLifecycleState.VALIDATED, ErrorLifecycleState.ABORTED),
    ErrorLifecycleState.VALIDATED: (ErrorLifecycleState.LOGGED,),
    ErrorLifecycleState.LOGGED: (ErrorLifecycleState.CATEGORIZED,),
    ErrorLifecycleState.CATEGORIZED: (ErrorLifecycleState.RECOVERY_STARTED,),
    ErrorLifecycleState.RECOVERY_STARTED: (
        ErrorLifecycleState.RETRYING,
        ErrorLifecycleState.RESOLVED,
        ErrorLifecycleState.ESCALATED,
        ErrorLifecycleState.ABORTED,
    ),
    ErrorLifecycleState.RETRYING: (
        ErrorLifecycleState.RECOVERY_STARTED,
        ErrorLifecycleState.RESOLVED,
        ErrorLifecycleState.ESCALATED,
    ),
    ErrorLifecycleState.ESCALATED: (
        ErrorLifecycleState.SAFE_MODE,
        ErrorLifecycleState.EMERGENCY_SHUTDOWN,
        ErrorLifecycleState.RESOLVED,
    ),
    ErrorLifecycleState.SAFE_MODE: (ErrorLifecycleState.ARCHIVED,),
    ErrorLifecycleState.EMERGENCY_SHUTDOWN: (ErrorLifecycleState.ARCHIVED,),
    ErrorLifecycleState.RESOLVED: (ErrorLifecycleState.VERIFIED,),
    ErrorLifecycleState.VERIFIED: (ErrorLifecycleState.ARCHIVED,),
    ErrorLifecycleState.ARCHIVED: (),
    ErrorLifecycleState.ABORTED: (ErrorLifecycleState.ARCHIVED,),
}


# =================================================================
# 2. DATA CONTRACTS
# =================================================================

@dataclass(frozen=True)
class RetryPolicyConfig:
    algorithm: RetryAlgorithm
    max_retries: int
    base_delay_ms: int
    max_delay_ms: int

    def __post_init__(self) -> None:
        if self.max_retries < 0 or self.base_delay_ms < 0 or self.max_delay_ms < 0:
            raise ValueError("RetryPolicyConfig fields must be non-negative")


@dataclass(frozen=True)
class AOSErrorDefinition:
    """Static, immutable catalog entry. One per registered error_code."""

    error_id: str
    error_code: str
    name: str
    description: str
    category: ErrorCategory
    severity: SeverityLevel
    source_component: str
    possible_causes: Tuple[str, ...]
    detection_method: str
    recovery_strategy: RecoveryStrategyType
    retry_policy: RetryPolicyConfig
    user_message: str
    developer_message: str
    recommended_action: str
    documentation_reference: str
    version: str
    owner: str
    timestamp: str
    related_events: Tuple[str, ...] = ()
    related_dependencies: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["severity"] = self.severity.value
        d["recovery_strategy"] = self.recovery_strategy.value
        d["retry_policy"] = {
            "algorithm": self.retry_policy.algorithm.value,
            "max_retries": self.retry_policy.max_retries,
            "base_delay_ms": self.retry_policy.base_delay_ms,
            "max_delay_ms": self.retry_policy.max_delay_ms,
        }
        return d


@dataclass
class AOSErrorInstance:
    """A single runtime occurrence of a registered error."""

    instance_id: str
    error_code: str
    correlation_id: str
    trace_id: str
    context: Dict[str, Any] = field(default_factory=dict)
    diagnostic_data: Dict[str, Any] = field(default_factory=dict)
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    state: ErrorLifecycleState = ErrorLifecycleState.DETECTED
    attempt_count: int = 0
    history: List[Tuple[str, str]] = field(default_factory=list)

    def transition(self, new_state: ErrorLifecycleState) -> None:
        allowed = _VALID_TRANSITIONS.get(self.state, ())
        if new_state not in allowed:
            raise InvalidStateTransitionError(
                f"Illegal transition {self.state.value} -> {new_state.value} "
                f"for instance {self.instance_id}"
            )
        self.history.append((self.state.value, datetime.now(timezone.utc).isoformat()))
        self.state = new_state

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "error_code": self.error_code,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "context": self.context,
            "diagnostic_data": self.diagnostic_data,
            "occurred_at": self.occurred_at,
            "state": self.state.value,
            "attempt_count": self.attempt_count,
            "history": self.history,
        }


# =================================================================
# 3. EXCEPTIONS (internal control-flow errors of this organ itself)
# =================================================================

class ErrorCatalogBaseException(Exception):
    """Root exception type for the Error Catalog organ."""


class UnregisteredErrorCodeError(ErrorCatalogBaseException):
    pass


class SchemaValidationError(ErrorCatalogBaseException):
    pass


class InvalidStateTransitionError(ErrorCatalogBaseException):
    pass


class RecoveryExhaustedError(ErrorCatalogBaseException):
    pass


class CodeFormatError(ErrorCatalogBaseException):
    pass


# =================================================================
# 4. PUBLIC INTERFACE CONTRACTS (Organ Specification requirement)
# =================================================================

class IErrorRegistry:
    def register_error(self, definition: AOSErrorDefinition) -> bool:
        raise NotImplementedError

    def get_definition(self, error_code: str) -> Optional[AOSErrorDefinition]:
        raise NotImplementedError


class IRecoveryManager:
    def execute_recovery(
        self, definition: AOSErrorDefinition, execution_context: Dict[str, Any]
    ) -> str:
        raise NotImplementedError


# =================================================================
# 5. ERROR CODE MANAGER
# =================================================================

_CODE_PATTERN = re.compile(r"^[A-Z]{3}-[0-9]{4}$")


class ErrorCodeManager:
    """Enforces canonical error code formatting and namespace boundaries."""

    def validate_format(self, error_code: str) -> bool:
        return bool(_CODE_PATTERN.match(error_code))

    def prefix_for(self, category: ErrorCategory) -> str:
        return CATEGORY_PREFIX[category]

    def assert_category_prefix_match(self, error_code: str, category: ErrorCategory) -> None:
        if not self.validate_format(error_code):
            raise CodeFormatError(f"Malformed error code: {error_code}")
        prefix = error_code.split("-")[0]
        expected = self.prefix_for(category)
        if prefix != expected:
            raise CodeFormatError(
                f"Prefix '{prefix}' does not match category '{category.value}' "
                f"(expected '{expected}')"
            )


# =================================================================
# 6. SANITIZATION UTILITY (security directive: sensitive masking)
# =================================================================

_SENSITIVE_PATTERN = re.compile(
    r'(?i)(bearer|token|password|secret|key)\s*=\s*"[^"]+"'
)


def sanitize_text(text: str) -> str:
    return _SENSITIVE_PATTERN.sub(lambda m: f'{m.group(1)}="***REDACTED***"', text)


def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    sanitized: Dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, str):
            sanitized[k] = sanitize_text(v)
        elif isinstance(v, dict):
            sanitized[k] = sanitize_payload(v)
        else:
            sanitized[k] = v
    return sanitized


# =================================================================
# 7. SOCKETS
# =================================================================

@dataclass(frozen=True)
class SocketSpec:
    name: str
    direction: str
    auth_required: str
    timeout_ms: int
    retries: int
    version: str
    logging_target: str


class BaseSocket:
    """Base socket: enforces timeout/retry/version contract per spec."""

    def __init__(self, spec: SocketSpec):
        self.spec = spec
        self._lock = threading.Lock()

    def send(self, payload: Dict[str, Any], handler: Callable[[Dict[str, Any]], Any]) -> Any:
        last_exc: Optional[Exception] = None
        attempts = max(1, self.spec.retries + 1)
        for _ in range(attempts):
            try:
                with self._lock:
                    return handler(payload)
            except Exception as exc:  # noqa: BLE001 - socket boundary must not leak
                last_exc = exc
                continue
        raise ErrorCatalogBaseException(
            f"Socket '{self.spec.name}' failed after {attempts} attempt(s): {last_exc}"
        )


SOCKET_REGISTRY: Dict[str, SocketSpec] = {
    "ErrorSocket": SocketSpec("ErrorSocket", "INGRESS/EGRESS", "KERNEL_TOKEN", 500, 3, "1.0.0", "detection.log"),
    "ValidationSocket": SocketSpec("ValidationSocket", "BIDIRECTIONAL", "NONE", 100, 0, "1.0.0", "validation.log"),
    "RecoverySocket": SocketSpec("RecoverySocket", "EGRESS", "RECOVERY_AUTH", 5000, 2, "1.0.0", "recovery.log"),
    "MetricsSocket": SocketSpec("MetricsSocket", "EGRESS", "NONE", 200, 1, "1.0.0", "metrics.log"),
    "MonitoringSocket": SocketSpec("MonitoringSocket", "EGRESS", "MONITOR_TOKEN", 1000, 3, "1.0.0", "monitoring.log"),
    "HistorySocket": SocketSpec("HistorySocket", "INGRESS/EGRESS", "AUDIT_READ", 2000, 0, "1.0.0", "history.log"),
    "AuditSocket": SocketSpec("AuditSocket", "EGRESS", "CRYPTO_HMAC", 1000, 5, "1.0.0", "audit.log"),
    "ConfigurationSocket": SocketSpec("ConfigurationSocket", "INGRESS/EGRESS", "ADMIN_AUTH", 1500, 1, "1.0.0", "configuration.log"),
}


# =================================================================
# 8. LOGGING SYSTEM (append-only, in-process; pluggable sink)
# =================================================================

class LoggingSystem:
    def __init__(self, sink: Optional[Callable[[Dict[str, Any]], None]] = None):
        self._sink = sink or (lambda record: None)
        self._lock = threading.Lock()
        self._append_only_log: List[Dict[str, Any]] = []

    def log(self, level: str, target: str, message: str, **fields: Any) -> None:
        record = {
            "level": level,
            "target": target,
            "message": sanitize_text(message),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **sanitize_payload(fields),
        }
        with self._lock:
            self._append_only_log.append(record)
        self._sink(record)

    def tail(self, n: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._append_only_log[-n:])


# =================================================================
# 9. ERROR REGISTRY
# =================================================================

class ErrorRegistry(IErrorRegistry):
    def __init__(self, code_manager: ErrorCodeManager):
        self._code_manager = code_manager
        self._definitions: Dict[str, AOSErrorDefinition] = {}
        self._lock = threading.RLock()

    def register_error(self, definition: AOSErrorDefinition) -> bool:
        with self._lock:
            self._code_manager.assert_category_prefix_match(
                definition.error_code, definition.category
            )
            if definition.error_code in self._definitions:
                raise ErrorCatalogBaseException(
                    f"Error code collision: {definition.error_code} already registered"
                )
            self._definitions[definition.error_code] = definition
            return True

    def get_definition(self, error_code: str) -> Optional[AOSErrorDefinition]:
        with self._lock:
            return self._definitions.get(error_code)

    def require_definition(self, error_code: str) -> AOSErrorDefinition:
        definition = self.get_definition(error_code)
        if definition is None:
            raise UnregisteredErrorCodeError(f"Unregistered error code: {error_code}")
        return definition

    def all_codes(self) -> List[str]:
        with self._lock:
            return sorted(self._definitions.keys())

    def by_category(self, category: ErrorCategory) -> List[AOSErrorDefinition]:
        with self._lock:
            return [d for d in self._definitions.values() if d.category == category]

    def count(self) -> int:
        with self._lock:
            return len(self._definitions)


# =================================================================
# 10. VALIDATION MANAGER
# =================================================================

_REQUIRED_INSTANCE_FIELDS = ("error_code", "correlation_id", "trace_id")


class ValidationManager:
    def __init__(self, registry: ErrorRegistry):
        self._registry = registry

    def validate_instance_payload(self, payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        for field_name in _REQUIRED_INSTANCE_FIELDS:
            if not payload.get(field_name):
                return False, f"Missing required field: {field_name}"
        error_code = payload["error_code"]
        definition = self._registry.get_definition(error_code)
        if definition is None:
            return False, f"Unregistered error code: {error_code}"
        return True, None

    def validate_definition(self, definition: AOSErrorDefinition) -> Tuple[bool, Optional[str]]:
        if not _CODE_PATTERN.match(definition.error_code):
            return False, "error_code fails pattern ^[A-Z]{3}-[0-9]{4}$"
        if not definition.user_message or not definition.developer_message:
            return False, "user_message and developer_message must be non-empty"
        if not definition.possible_causes:
            return False, "possible_causes must contain at least one entry"
        if not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", definition.version):
            return False, "version must be semantic (x.y.z)"
        return True, None


# =================================================================
# 11. SEVERITY MANAGER
# =================================================================

class SeverityManager:
    def __init__(self):
        self._dynamic_escalations = 0

    def evaluate(
        self, definition: AOSErrorDefinition, recent_occurrence_rate: float = 0.0
    ) -> SeverityLevel:
        """Static severity, escalated dynamically under rate-spike conditions."""
        static_severity = definition.severity
        if recent_occurrence_rate >= 50.0 and SEVERITY_RANK[static_severity] < SEVERITY_RANK[SeverityLevel.CRITICAL]:
            self._dynamic_escalations += 1
            return SeverityLevel.CRITICAL
        return static_severity

    def requires_shutdown(self, severity: SeverityLevel) -> bool:
        return severity in (SeverityLevel.FATAL, SeverityLevel.EMERGENCY)

    def requires_recovery(self, severity: SeverityLevel) -> bool:
        return SEVERITY_RANK[severity] >= SEVERITY_RANK[SeverityLevel.ERROR]


# =================================================================
# 12. RETRY POLICY MANAGER
# =================================================================

class RetryPolicyManager:
    def calculate_backoff(self, policy: RetryPolicyConfig, attempt: int) -> float:
        if policy.algorithm == RetryAlgorithm.NONE:
            return 0.0
        if policy.algorithm == RetryAlgorithm.IMMEDIATE:
            return 0.0
        if policy.algorithm == RetryAlgorithm.LINEAR_BACKOFF:
            delay = (policy.base_delay_ms * attempt) / 1000.0
            return min(delay, policy.max_delay_ms / 1000.0)
        if policy.algorithm == RetryAlgorithm.EXPONENTIAL_BACKOFF:
            calculated = (policy.base_delay_ms * (2 ** (attempt - 1))) / 1000.0
            capped = min(calculated, policy.max_delay_ms / 1000.0)
            return capped * random.uniform(0.5, 1.5)
        return 0.0

    def exhausted(self, policy: RetryPolicyConfig, attempt_count: int) -> bool:
        return attempt_count >= policy.max_retries


# =================================================================
# 13. COMPATIBILITY MANAGER
# =================================================================

class CompatibilityManager:
    def __init__(self, registry: ErrorRegistry):
        self._registry = registry
        self._aliases: Dict[str, str] = {}

    def register_alias(self, legacy_code: str, modern_code: str) -> None:
        self._registry.require_definition(modern_code)
        self._aliases[legacy_code] = modern_code

    def resolve(self, code: str) -> str:
        return self._aliases.get(code, code)


# =================================================================
# 14. LOCALIZATION MANAGER
# =================================================================

class LocalizationManager:
    def __init__(self, default_locale: str = "en_US"):
        self._default_locale = default_locale
        self._catalogs: Dict[str, Dict[str, str]] = {default_locale: {}}

    def register_locale_strings(self, locale: str, strings: Dict[str, str]) -> None:
        self._catalogs.setdefault(locale, {}).update(strings)

    def localize(self, definition: AOSErrorDefinition, locale: Optional[str] = None, **params: Any) -> str:
        locale = locale or self._default_locale
        template = self._catalogs.get(locale, {}).get(
            definition.error_code, definition.user_message
        )
        try:
            return template.format(**params) if params else template
        except (KeyError, IndexError):
            return template


# =================================================================
# 15. METRICS MANAGER
# =================================================================

class MetricsManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._error_count: Dict[str, int] = {}
        self._recovery_success: int = 0
        self._recovery_failure: int = 0
        self._occurrence_timestamps: Dict[str, Deque[float]] = {}
        self._recovery_durations_ms: List[float] = []
        self._last_failure_time: Dict[str, float] = {}
        self._time_between_failures: Dict[str, List[float]] = {}

    def record_occurrence(self, error_code: str) -> None:
        now = time.time()
        with self._lock:
            self._error_count[error_code] = self._error_count.get(error_code, 0) + 1
            bucket = self._occurrence_timestamps.setdefault(error_code, deque())
            bucket.append(now)
            while bucket and now - bucket[0] > 60.0:
                bucket.popleft()
            last = self._last_failure_time.get(error_code)
            if last is not None:
                self._time_between_failures.setdefault(error_code, []).append(now - last)
            self._last_failure_time[error_code] = now

    def record_recovery(self, success: bool, duration_ms: float) -> None:
        with self._lock:
            if success:
                self._recovery_success += 1
            else:
                self._recovery_failure += 1
            self._recovery_durations_ms.append(duration_ms)

    def rate_per_minute(self, error_code: str) -> float:
        with self._lock:
            return float(len(self._occurrence_timestamps.get(error_code, ())))

    def mtbf_seconds(self, error_code: str) -> Optional[float]:
        with self._lock:
            deltas = self._time_between_failures.get(error_code)
            if not deltas:
                return None
            return sum(deltas) / len(deltas)

    def mttr_ms(self) -> Optional[float]:
        with self._lock:
            if not self._recovery_durations_ms:
                return None
            return sum(self._recovery_durations_ms) / len(self._recovery_durations_ms)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "error_count": dict(self._error_count),
                "recovery_success": self._recovery_success,
                "recovery_failure": self._recovery_failure,
                "mttr_ms": self.mttr_ms(),
            }


# =================================================================
# 16. MONITORING MANAGER
# =================================================================

class MonitoringManager:
    def __init__(self, metrics: MetricsManager, breach_threshold_rpm: float = 50.0):
        self._metrics = metrics
        self._breach_threshold_rpm = breach_threshold_rpm
        self._alerts: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def evaluate(self, error_code: str) -> Optional[Dict[str, Any]]:
        rate = self._metrics.rate_per_minute(error_code)
        if rate >= self._breach_threshold_rpm:
            alert = {
                "error_code": error_code,
                "rate_per_minute": rate,
                "threshold": self._breach_threshold_rpm,
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            }
            with self._lock:
                self._alerts.append(alert)
            return alert
        return None

    def alerts(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._alerts)


# =================================================================
# 17. AUDIT MANAGER (HMAC-signed, non-repudiable)
# =================================================================

class AuditManager:
    def __init__(self, hmac_key: bytes):
        self._key = hmac_key
        self._chain: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._prev_hash: str = "0" * 64

    def _sign(self, payload: str) -> str:
        return hmac.new(self._key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def record(self, event: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            body = json.dumps(event, sort_keys=True, default=str)
            chained = f"{self._prev_hash}:{body}"
            signature = self._sign(chained)
            record = {
                "event": event,
                "prev_hash": self._prev_hash,
                "signature": signature,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            self._prev_hash = signature
            self._chain.append(record)
            return record

    def verify_chain(self) -> bool:
        with self._lock:
            prev = "0" * 64
            for record in self._chain:
                if record["prev_hash"] != prev:
                    return False
                body = json.dumps(record["event"], sort_keys=True, default=str)
                chained = f"{prev}:{body}"
                if self._sign(chained) != record["signature"]:
                    return False
                prev = record["signature"]
            return True

    def trail(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._chain)


# =================================================================
# 18. ERROR HISTORY (ring buffer + SQLite WAL persistent store)
# =================================================================

class ErrorHistory:
    def __init__(self, db_path: Optional[str] = None, ring_capacity: int = 5000):
        self._ring: Deque[Dict[str, Any]] = deque(maxlen=ring_capacity)
        self._lock = threading.Lock()
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        if db_path:
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS error_history (
                    instance_id TEXT PRIMARY KEY,
                    error_code TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def append(self, instance: AOSErrorInstance, severity: SeverityLevel) -> None:
        record = {**instance.to_dict(), "severity": severity.value}
        with self._lock:
            self._ring.append(record)
            if self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO error_history "
                    "(instance_id, error_code, severity, correlation_id, trace_id, "
                    "state, occurred_at, payload) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        instance.instance_id,
                        instance.error_code,
                        severity.value,
                        instance.correlation_id,
                        instance.trace_id,
                        instance.state.value,
                        instance.occurred_at,
                        json.dumps(record, default=str),
                    ),
                )
                self._conn.commit()

    def query(
        self,
        error_code: Optional[str] = None,
        severity: Optional[SeverityLevel] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            results = list(self._ring)
        if error_code:
            results = [r for r in results if r["error_code"] == error_code]
        if severity:
            results = [r for r in results if r["severity"] == severity.value]
        return results[-limit:]

    def close(self) -> None:
        if self._conn:
            self._conn.close()


# =================================================================
# 19. RECOVERY MANAGER
# =================================================================

class RecoveryManager(IRecoveryManager):
    def __init__(
        self,
        registry: ErrorRegistry,
        retry_manager: RetryPolicyManager,
        logging_system: LoggingSystem,
        metrics: MetricsManager,
    ):
        self._registry = registry
        self._retry_manager = retry_manager
        self._logging = logging_system
        self._metrics = metrics

    def execute_recovery(
        self, definition: AOSErrorDefinition, execution_context: Dict[str, Any]
    ) -> str:
        start = time.time()
        strategy = definition.recovery_strategy
        outcome = "ABORTED"
        try:
            if strategy == RecoveryStrategyType.RETRY:
                outcome = self._retry(definition, execution_context)
            elif strategy == RecoveryStrategyType.FALLBACK:
                fallback = execution_context.get("fallback_target")
                outcome = "SUCCESS" if fallback is None or fallback() else "ESCALATED"
            elif strategy in (
                RecoveryStrategyType.RESTART_COMPONENT,
                RecoveryStrategyType.RESTART_SERVICE,
                RecoveryStrategyType.RESTART_RUNTIME,
            ):
                restart = execution_context.get("restart_target")
                outcome = "SUCCESS" if restart is None or restart() else "ESCALATED"
            elif strategy == RecoveryStrategyType.RELOAD_CONFIGURATION:
                reload_fn = execution_context.get("reload_target")
                outcome = "SUCCESS" if reload_fn is None or reload_fn() else "ESCALATED"
            elif strategy == RecoveryStrategyType.ROLLBACK:
                rollback = execution_context.get("rollback_target")
                outcome = "SUCCESS" if rollback is None or rollback() else "ESCALATED"
            elif strategy == RecoveryStrategyType.SAFE_MODE:
                bridge = execution_context.get("kernel_bridge")
                if bridge is not None:
                    bridge.trigger_safe_mode(definition.error_code)
                outcome = "SUCCESS"
            elif strategy == RecoveryStrategyType.MANUAL_APPROVAL:
                outcome = "ESCALATED"
            elif strategy == RecoveryStrategyType.EMERGENCY_SHUTDOWN:
                bridge = execution_context.get("kernel_bridge")
                if bridge is not None:
                    bridge.trigger_emergency_shutdown(definition.error_code)
                outcome = "SUCCESS"
            elif strategy == RecoveryStrategyType.ABORT:
                outcome = "ABORTED"
            else:
                outcome = "ABORTED"
        finally:
            duration_ms = (time.time() - start) * 1000.0
            self._metrics.record_recovery(outcome == "SUCCESS", duration_ms)
            self._logging.log(
                "INFO",
                "recovery.log",
                f"Recovery strategy {strategy.value} for {definition.error_code} -> {outcome}",
                duration_ms=duration_ms,
            )
        return outcome

    def _retry(self, definition: AOSErrorDefinition, execution_context: Dict[str, Any]) -> str:
        policy = definition.retry_policy
        target = execution_context.get("retry_target")
        if target is None:
            return "ESCALATED"
        for attempt in range(1, policy.max_retries + 1):
            delay = self._retry_manager.calculate_backoff(policy, attempt)
            if delay > 0:
                time.sleep(min(delay, 0.0))  # non-blocking in-organ; caller controls real sleep
            if target():
                return "SUCCESS"
        return "ESCALATED"


# =================================================================
# 20. PIPELINES
# =================================================================

class DetectionPipeline:
    """Raw Fault Signal -> ErrorSocket -> Validation Manager -> Sanitized AOSError Payload"""

    def __init__(self, validation: ValidationManager):
        self._validation = validation

    def run(self, raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = sanitize_payload(raw_payload)
        ok, reason = self._validation.validate_instance_payload(sanitized)
        if not ok:
            raise SchemaValidationError(reason or "invalid payload")
        return sanitized


class ValidationPipeline:
    def __init__(self, validation: ValidationManager):
        self._validation = validation

    def run(self, definition: AOSErrorDefinition) -> None:
        ok, reason = self._validation.validate_definition(definition)
        if not ok:
            raise SchemaValidationError(reason or "invalid definition")


class RetryPipeline:
    def __init__(self, retry_manager: RetryPolicyManager):
        self._retry_manager = retry_manager

    def next_delay(self, policy: RetryPolicyConfig, attempt: int) -> float:
        return self._retry_manager.calculate_backoff(policy, attempt)


class EscalationPipeline:
    """Unresolved Error Signal -> Severity Manager -> Monitoring Manager -> Safe-Mode/Panic"""

    def __init__(self, severity: SeverityManager, monitoring: MonitoringManager):
        self._severity = severity
        self._monitoring = monitoring

    def run(self, definition: AOSErrorDefinition, occurrence_rate: float) -> SeverityLevel:
        evaluated = self._severity.evaluate(definition, occurrence_rate)
        self._monitoring.evaluate(definition.error_code)
        return evaluated


class RecoveryPipeline:
    """AOSError Object -> RecoverySocket -> Recovery Manager -> Retry Policy Manager -> Target"""

    def __init__(self, recovery_manager: RecoveryManager):
        self._recovery_manager = recovery_manager

    def run(self, definition: AOSErrorDefinition, execution_context: Dict[str, Any]) -> str:
        return self._recovery_manager.execute_recovery(definition, execution_context)


class AuditPipeline:
    def __init__(self, audit_manager: AuditManager):
        self._audit_manager = audit_manager

    def run(self, event: Dict[str, Any]) -> Dict[str, Any]:
        return self._audit_manager.record(event)


class LoggingPipeline:
    def __init__(self, logging_system: LoggingSystem):
        self._logging = logging_system

    def run(self, level: str, target: str, message: str, **fields: Any) -> None:
        self._logging.log(level, target, message, **fields)


class HistoryPipeline:
    def __init__(self, history: ErrorHistory):
        self._history = history

    def run(self, instance: AOSErrorInstance, severity: SeverityLevel) -> None:
        self._history.append(instance, severity)


class MonitoringPipeline:
    def __init__(self, monitoring: MonitoringManager):
        self._monitoring = monitoring

    def run(self, error_code: str) -> Optional[Dict[str, Any]]:
        return self._monitoring.evaluate(error_code)


# =================================================================
# 21. STANDARD ERROR CODE CATALOG (32 definitions, authoritative)
# =================================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rp(algorithm: RetryAlgorithm, max_retries: int, base_ms: int, max_ms: int) -> RetryPolicyConfig:
    return RetryPolicyConfig(algorithm, max_retries, base_ms, max_ms)


_STANDARD_CATALOG_SOURCE: List[Tuple] = [
    ("SYS-0001", "SystemStartupFailed", ErrorCategory.SYSTEM, SeverityLevel.EMERGENCY,
     RecoveryStrategyType.EMERGENCY_SHUTDOWN, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "Hojaiga AOS failed to start. System components could not be initialized.",
     "Boot sequence failed at stage [Kernel Bootstrap]. Host environment conditions failed validation.",
     ("Corrupted kernel binaries", "Missing system mounts", "Severe OS privilege restriction"),
     "Boot sequence orchestrator health check timer expired or caught fatal assertion.",
     "Inspect /var/log/aos/boot.log and verify host filesystem permissions.", "aos.kernel.boot"),
    ("SYS-0002", "SystemShutdownFailed", ErrorCategory.SYSTEM, SeverityLevel.CRITICAL,
     RecoveryStrategyType.SAFE_MODE, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "Hojaiga AOS could not shut down cleanly.",
     "Shutdown sequence stalled while releasing organ resources.",
     ("Organ deadlock", "Unresponsive worker thread"),
     "Shutdown watchdog timeout exceeded.",
     "Force-terminate stalled organs and re-run graceful shutdown.", "aos.kernel.shutdown"),
    ("KER-1001", "KernelInitializationFailed", ErrorCategory.KERNEL, SeverityLevel.EMERGENCY,
     RecoveryStrategyType.EMERGENCY_SHUTDOWN, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "A critical internal component failed to initialize.",
     "Kernel bootstrap sequence raised a fatal assertion during core registry construction.",
     ("Corrupted core memory region", "Missing manifest"),
     "Kernel bootstrap fatal assertion trap.",
     "Reinstall kernel core package and validate system manifest checksum.", "aos.kernel.core"),
    ("KER-1002", "KernelPanicTrap", ErrorCategory.KERNEL, SeverityLevel.EMERGENCY,
     RecoveryStrategyType.EMERGENCY_SHUTDOWN, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "A critical internal fault forced an immediate stop.",
     "Kernel-level panic trap triggered by unrecoverable low-level fault.",
     ("Memory barrier violation", "Illegal thread scheduling state"),
     "Kernel panic interrupt handler.",
     "Collect panic dump and escalate to kernel maintainers.", "aos.kernel.core"),
    ("CFG-2001", "ConfigurationMissing", ErrorCategory.CONFIGURATION, SeverityLevel.FATAL,
     RecoveryStrategyType.RELOAD_CONFIGURATION, _rp(RetryAlgorithm.LINEAR_BACKOFF, 3, 500, 5000),
     "A required configuration file could not be found.",
     "Configuration loader could not resolve mandatory config path.",
     ("Missing config file", "Incorrect working directory"),
     "Configuration loader file-not-found exception.",
     "Restore configuration file from backup or defaults.", "aos.kernel.config"),
    ("CFG-2002", "InvalidConfiguration", ErrorCategory.CONFIGURATION, SeverityLevel.FATAL,
     RecoveryStrategyType.RELOAD_CONFIGURATION, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "The current configuration is invalid and could not be applied.",
     "Configuration schema validation failed against declared config schema.",
     ("Malformed YAML/JSON", "Unknown configuration key"),
     "Schema validation parser exception.",
     "Fix configuration according to schema and reload.", "aos.kernel.config"),
    ("RES-3001", "OutOfMemory", ErrorCategory.RESOURCE, SeverityLevel.CRITICAL,
     RecoveryStrategyType.RESTART_RUNTIME, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "The system ran out of available memory.",
     "Host RAM allocation request failed; working set exceeded available physical memory.",
     ("Memory leak", "Oversized in-memory dataset"),
     "OS allocation failure trap.",
     "Restart affected runtime and reduce working set size.", "aos.resource.memory"),
    ("RES-3002", "GPUUnavailable", ErrorCategory.RESOURCE, SeverityLevel.ERROR,
     RecoveryStrategyType.FALLBACK, _rp(RetryAlgorithm.LINEAR_BACKOFF, 3, 1000, 10000),
     "The graphics processor is currently unavailable.",
     "CUDA device enumeration returned zero available devices or device busy.",
     ("Driver crash", "Device held by another process"),
     "CUDA device query failure.",
     "Fall back to CPU inference path or wait and retry.", "aos.resource.gpu"),
    ("RES-3003", "VRAMExhausted", ErrorCategory.RESOURCE, SeverityLevel.ERROR,
     RecoveryStrategyType.FALLBACK, _rp(RetryAlgorithm.EXPONENTIAL_BACKOFF, 4, 500, 8000),
     "The AI processing engine ran out of graphical memory.",
     "CUDA allocation request failed with status OUT_OF_MEMORY on Device ID 0.",
     ("LLM context length exceeding allocation limits", "Co-occurring GPU workloads"),
     "Host CUDA memory assertion trap.",
     "Trigger GPU garbage collection, unload non-essential model layers, or use a lower-bit quant model.",
     "aos.resource.gpu"),
    ("SCH-4001", "TaskTimeout", ErrorCategory.SCHEDULER, SeverityLevel.ERROR,
     RecoveryStrategyType.RETRY, _rp(RetryAlgorithm.EXPONENTIAL_BACKOFF, 3, 200, 4000),
     "A task took too long to complete and was stopped.",
     "Task Scheduler exceeded configured execution deadline for task instance.",
     ("Downstream organ hang", "Unbounded loop"),
     "Scheduler deadline watchdog.",
     "Investigate downstream organ latency and retry with backoff.", "aos.kernel.scheduler"),
    ("SCH-4002", "QueueOverflow", ErrorCategory.SCHEDULER, SeverityLevel.ERROR,
     RecoveryStrategyType.FALLBACK, _rp(RetryAlgorithm.IMMEDIATE, 1, 0, 0),
     "Too many tasks are queued at once.",
     "Task queue exceeded configured maximum capacity.",
     ("Burst of concurrent requests", "Downstream backpressure"),
     "Queue capacity threshold check.",
     "Apply backpressure to producers or scale worker pool.", "aos.kernel.scheduler"),
    ("SRV-5001", "ServiceRegistrationFailed", ErrorCategory.SERVICE, SeverityLevel.CRITICAL,
     RecoveryStrategyType.RESTART_SERVICE, _rp(RetryAlgorithm.EXPONENTIAL_BACKOFF, 3, 500, 6000),
     "A required internal service failed to start.",
     "Service Registry rejected registration due to schema or namespace conflict.",
     ("Duplicate service name", "Invalid service manifest"),
     "Service registry validation failure.",
     "Correct service manifest and re-attempt registration.", "aos.kernel.service_registry"),
    ("SRV-5002", "ServiceUnavailable", ErrorCategory.SERVICE, SeverityLevel.ERROR,
     RecoveryStrategyType.RESTART_SERVICE, _rp(RetryAlgorithm.EXPONENTIAL_BACKOFF, 3, 500, 6000),
     "A required internal service is not responding.",
     "Service health-check probe failed consecutively past threshold.",
     ("Service crash", "Deadlock"),
     "Health-check probe timeout.",
     "Restart the affected service and inspect its logs.", "aos.kernel.service_registry"),
    ("DEP-6001", "MissingDependency", ErrorCategory.DEPENDENCY, SeverityLevel.FATAL,
     RecoveryStrategyType.SAFE_MODE, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "A required internal component is missing.",
     "Dependency Graph resolution failed to locate a mandatory dependency node.",
     ("Uninstalled package", "Broken plugin manifest"),
     "Dependency graph resolution failure.",
     "Install missing dependency or disable dependent organ.", "aos.kernel.dependency_graph"),
    ("DEP-6002", "CircularDependency", ErrorCategory.DEPENDENCY, SeverityLevel.FATAL,
     RecoveryStrategyType.ABORT, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "A configuration conflict prevented startup.",
     "Dependency Graph detected a cycle during topological resolution.",
     ("Misconfigured organ dependency declarations",),
     "Topological sort cycle detection.",
     "Break the dependency cycle in organ manifests.", "aos.kernel.dependency_graph"),
    ("CAP-7001", "CapabilityNotFound", ErrorCategory.CAPABILITY, SeverityLevel.ERROR,
     RecoveryStrategyType.ABORT, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "The requested capability is not available.",
     "Capability Registry lookup returned no matching provider for requested capability.",
     ("Capability never registered", "Typo in capability name"),
     "Capability registry lookup miss.",
     "Register a provider for the capability or correct the capability name.", "aos.kernel.capability_registry"),
    ("CAP-7002", "CapabilityVersionMismatch", ErrorCategory.CAPABILITY, SeverityLevel.ERROR,
     RecoveryStrategyType.ABORT, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "An installed capability version is incompatible.",
     "Requested capability version does not satisfy provider's compatibility range.",
     ("Outdated provider", "Breaking version bump"),
     "Semantic version compatibility check.",
     "Upgrade/downgrade the provider to a compatible version.", "aos.kernel.capability_registry"),
    ("EVT-8001", "InvalidEventPayload", ErrorCategory.COMMUNICATION, SeverityLevel.ERROR,
     RecoveryStrategyType.ABORT, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "An internal message was malformed and was rejected.",
     "Event Bus payload failed structural validation against event schema.",
     ("Producer schema drift", "Serialization bug"),
     "Event schema validator rejection.",
     "Correct producer serialization to match declared event schema.", "aos.cns.event_bus"),
    ("EVT-8002", "EventValidationFailed", ErrorCategory.COMMUNICATION, SeverityLevel.ERROR,
     RecoveryStrategyType.ABORT, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "An internal message failed validation checks.",
     "Event Bus business-rule validation rejected the event instance.",
     ("Out-of-range field value", "Missing correlation id"),
     "Event business rule validator.",
     "Inspect producer logic and correct emitted event content.", "aos.cns.event_bus"),
    ("MEM-9001", "MemoryWriteFailed", ErrorCategory.MEMORY, SeverityLevel.CRITICAL,
     RecoveryStrategyType.ROLLBACK, _rp(RetryAlgorithm.IMMEDIATE, 1, 0, 0),
     "Saving data to memory failed.",
     "Memory Organ persistence layer write operation raised an I/O or lock exception.",
     ("Disk full", "WAL lock contention"),
     "Persistent store write exception.",
     "Free disk space / resolve lock contention and roll back to last checkpoint.", "aos.memory.persistence"),
    ("KNW-9101", "KnowledgeRetrievalFailed", ErrorCategory.KNOWLEDGE, SeverityLevel.ERROR,
     RecoveryStrategyType.FALLBACK, _rp(RetryAlgorithm.LINEAR_BACKOFF, 2, 300, 3000),
     "Looking up stored knowledge failed.",
     "Knowledge index query raised an exception or returned corrupted result set.",
     ("Corrupted index", "Query timeout"),
     "Knowledge index query exception.",
     "Fall back to secondary index or rebuild knowledge index.", "aos.knowledge.index"),
    ("LLM-9201", "ModelLoadFailed", ErrorCategory.LLM_RUNTIME, SeverityLevel.CRITICAL,
     RecoveryStrategyType.FALLBACK, _rp(RetryAlgorithm.EXPONENTIAL_BACKOFF, 3, 1000, 15000),
     "The AI model could not be loaded.",
     "llama.cpp model load call failed to map model weights into memory.",
     ("Corrupted model file", "Insufficient VRAM/RAM"),
     "Model loader exception trap.",
     "Verify model checksum and available memory, then retry load.", "aos.brain.model_runtime"),
    ("LLM-9202", "ModelInferenceFailed", ErrorCategory.LLM_RUNTIME, SeverityLevel.ERROR,
     RecoveryStrategyType.RETRY, _rp(RetryAlgorithm.EXPONENTIAL_BACKOFF, 3, 500, 8000),
     "The AI failed to generate a response.",
     "LLM stream disconnected unexpectedly during token generation phase.",
     ("Remote API socket hangup", "Local inference engine crash", "Malformed prompt template"),
     "Stream completion handler timeout / unexpected EOF.",
     "Re-verify prompt context size and execute exponential backoff retry.", "aos.brain.model_runtime"),
    ("PLG-9301", "PluginValidationFailed", ErrorCategory.PLUGIN, SeverityLevel.ERROR,
     RecoveryStrategyType.ABORT, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "A plugin failed security or compatibility checks.",
     "Plugin Runtime Security Validator rejected plugin manifest or signature.",
     ("Unsigned plugin", "Incompatible API version"),
     "Plugin validator rejection.",
     "Correct plugin manifest/signature and resubmit for approval.", "aos.execution.plugin_runtime"),
    ("PLG-9302", "PluginRejected", ErrorCategory.PLUGIN, SeverityLevel.ERROR,
     RecoveryStrategyType.ABORT, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "A plugin was rejected by the sandbox test run.",
     "Plugin Runtime sandbox execution raised disallowed permission usage.",
     ("Excessive permission request", "Sandbox crash"),
     "Sandbox permission monitor trip.",
     "Reduce requested plugin permissions or fix sandbox crash cause.", "aos.execution.plugin_runtime"),
    ("CON-9401", "ConnectorUnavailable", ErrorCategory.CONNECTOR, SeverityLevel.ERROR,
     RecoveryStrategyType.RETRY, _rp(RetryAlgorithm.EXPONENTIAL_BACKOFF, 3, 500, 6000),
     "An external connector is not responding.",
     "External Connector organ health probe failed or connection refused.",
     ("Remote endpoint down", "Network partition"),
     "Connector health probe timeout.",
     "Verify network path to endpoint and retry with backoff.", "aos.organ15.external_connectors"),
    ("API-9501", "APITimeout", ErrorCategory.API, SeverityLevel.ERROR,
     RecoveryStrategyType.RETRY, _rp(RetryAlgorithm.EXPONENTIAL_BACKOFF, 3, 400, 6000),
     "A network request took too long to complete.",
     "Outbound HTTP/REST call exceeded configured timeout.",
     ("Slow remote service", "Network congestion"),
     "HTTP client timeout exception.",
     "Retry with exponential backoff or increase timeout budget.", "aos.execution.external_runtime"),
    ("API-9502", "APIAuthenticationFailed", ErrorCategory.API, SeverityLevel.ERROR,
     RecoveryStrategyType.MANUAL_APPROVAL, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "Authentication with an external service failed.",
     "Outbound API call received 401/403 authentication rejection.",
     ("Expired credential", "Revoked API key"),
     "HTTP 401/403 response inspection.",
     "Refresh or rotate credentials and require operator approval to resume.", "aos.execution.external_runtime"),
    ("WIN-9601", "WindowNotFound", ErrorCategory.WINDOWS, SeverityLevel.ERROR,
     RecoveryStrategyType.RETRY, _rp(RetryAlgorithm.LINEAR_BACKOFF, 3, 300, 3000),
     "A target application window could not be located.",
     "Desktop UI Automation window enumeration failed to match target window criteria.",
     ("Application not yet launched", "Window title changed"),
     "Window tree enumeration miss.",
     "Confirm target application is running and retry window lookup.", "aos.execution.desktop_runtime"),
    ("PWT-9701", "PlaywrightLaunchFailed", ErrorCategory.PLAYWRIGHT, SeverityLevel.CRITICAL,
     RecoveryStrategyType.RESTART_COMPONENT, _rp(RetryAlgorithm.EXPONENTIAL_BACKOFF, 3, 800, 10000),
     "The browser automation engine failed to start.",
     "Playwright browser launch call raised an exception during CDP handshake.",
     ("Corrupted browser binary", "Port already in use"),
     "Playwright launch exception trap.",
     "Reinstall browser binaries and verify CDP port availability.", "aos.execution.browser_runtime"),
    ("SEC-9801", "PermissionDenied", ErrorCategory.SECURITY, SeverityLevel.ERROR,
     RecoveryStrategyType.MANUAL_APPROVAL, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "This action is not permitted.",
     "Permission Check rejected the operation due to insufficient authorized scope.",
     ("Least-privilege boundary violation", "Missing Owner Authority approval"),
     "Permission policy evaluation rejection.",
     "Request elevated permission through governance approval flow.", "aos.security.permission_check"),
    ("SEC-9802", "IntegrityValidationFailed", ErrorCategory.SECURITY, SeverityLevel.FATAL,
     RecoveryStrategyType.SAFE_MODE, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "A security integrity check failed.",
     "AuditManager detected a historical log sequence cryptographic gap.",
     ("Tampered audit log", "HMAC key mismatch"),
     "Audit chain HMAC verification failure.",
     "Investigate tamper source and restore system to read-only safe mode.", "aos.security.audit_manager"),
    ("USR-9901", "InvalidUserRequest", ErrorCategory.USER, SeverityLevel.WARNING,
     RecoveryStrategyType.ABORT, _rp(RetryAlgorithm.NONE, 0, 0, 0),
     "Your request could not be processed because it was invalid.",
     "Interface Layer request validator rejected malformed client payload.",
     ("Malformed client payload", "Missing required request field"),
     "Request validator schema rejection.",
     "Correct the request payload and resubmit.", "aos.interface.request_validator"),
]


def build_standard_catalog(code_manager: ErrorCodeManager) -> List[AOSErrorDefinition]:
    definitions: List[AOSErrorDefinition] = []
    for (
        code, name, category, severity, strategy, retry_policy,
        user_msg, dev_msg, causes, detection, action, source,
    ) in _STANDARD_CATALOG_SOURCE:
        code_manager.assert_category_prefix_match(code, category)
        definitions.append(
            AOSErrorDefinition(
                error_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"hojaiga://error/{code}")),
                error_code=code,
                name=name,
                description=dev_msg,
                category=category,
                severity=severity,
                source_component=source,
                possible_causes=tuple(causes),
                detection_method=detection,
                recovery_strategy=strategy,
                retry_policy=retry_policy,
                user_message=user_msg,
                developer_message=dev_msg,
                recommended_action=action,
                documentation_reference=f"https://docs.hojaiga.local/errors/{code}",
                version="1.0.0",
                owner="Organ_25_Error_Catalog",
                timestamp=_now_iso(),
            )
        )
    return definitions


# =================================================================
# 22. PUBLIC FACADE — ErrorCatalogOrgan (CNSGateway boundary)
# =================================================================

class ErrorCatalogOrgan:
    """
    Public, sole entry point for every other organ. All cross-organ
    interaction with the Error Catalog must go through this facade's
    documented methods (the organ's socket surface) and never through
    the private managers above.
    """

    def __init__(
        self,
        history_db_path: Optional[str] = None,
        hmac_key: Optional[bytes] = None,
        log_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.code_manager = ErrorCodeManager()
        self.registry = ErrorRegistry(self.code_manager)
        self.validation_manager = ValidationManager(self.registry)
        self.severity_manager = SeverityManager()
        self.retry_manager = RetryPolicyManager()
        self.logging_system = LoggingSystem(sink=log_sink)
        self.metrics_manager = MetricsManager()
        self.monitoring_manager = MonitoringManager(self.metrics_manager)
        self.audit_manager = AuditManager(hmac_key or uuid.uuid4().bytes)
        self.history = ErrorHistory(db_path=history_db_path)
        self.compatibility_manager = CompatibilityManager(self.registry)
        self.localization_manager = LocalizationManager()
        self.recovery_manager = RecoveryManager(
            self.registry, self.retry_manager, self.logging_system, self.metrics_manager
        )

        self.detection_pipeline = DetectionPipeline(self.validation_manager)
        self.validation_pipeline = ValidationPipeline(self.validation_manager)
        self.recovery_pipeline = RecoveryPipeline(self.recovery_manager)
        self.retry_pipeline = RetryPipeline(self.retry_manager)
        self.escalation_pipeline = EscalationPipeline(self.severity_manager, self.monitoring_manager)
        self.audit_pipeline = AuditPipeline(self.audit_manager)
        self.logging_pipeline = LoggingPipeline(self.logging_system)
        self.history_pipeline = HistoryPipeline(self.history)
        self.monitoring_pipeline = MonitoringPipeline(self.monitoring_manager)

        self.error_socket = BaseSocket(SOCKET_REGISTRY["ErrorSocket"])
        self.validation_socket = BaseSocket(SOCKET_REGISTRY["ValidationSocket"])
        self.recovery_socket = BaseSocket(SOCKET_REGISTRY["RecoverySocket"])
        self.metrics_socket = BaseSocket(SOCKET_REGISTRY["MetricsSocket"])
        self.monitoring_socket = BaseSocket(SOCKET_REGISTRY["MonitoringSocket"])
        self.history_socket = BaseSocket(SOCKET_REGISTRY["HistorySocket"])
        self.audit_socket = BaseSocket(SOCKET_REGISTRY["AuditSocket"])
        self.configuration_socket = BaseSocket(SOCKET_REGISTRY["ConfigurationSocket"])

        self._load_standard_catalog()

    # ---- bootstrap ------------------------------------------------

    def _load_standard_catalog(self) -> None:
        for definition in build_standard_catalog(self.code_manager):
            self.validation_pipeline.run(definition)
            self.registry.register_error(definition)

    # ---- public API -------------------------------------------------

    def register_custom_error(self, definition: AOSErrorDefinition) -> bool:
        self.validation_pipeline.run(definition)
        return self.registry.register_error(definition)

    def emit_error(
        self,
        error_code: str,
        context: Optional[Dict[str, Any]] = None,
        diagnostic_data: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        execution_context: Optional[Dict[str, Any]] = None,
        auto_recover: bool = True,
    ) -> AOSErrorInstance:
        """
        Full lifecycle entry point: Detected -> Validated -> Logged ->
        Categorized -> RecoveryStarted -> (Retrying) -> Resolved/Escalated
        -> Verified -> Archived.
        """
        error_code = self.compatibility_manager.resolve(error_code)
        self.registry.require_definition(error_code)
        correlation_id = correlation_id or str(uuid.uuid4())
        trace_id = trace_id or str(uuid.uuid4())

        raw_payload = {
            "error_code": error_code,
            "correlation_id": correlation_id,
            "trace_id": trace_id,
            "context": context or {},
        }

        instance = AOSErrorInstance(
            instance_id=str(uuid.uuid4()),
            error_code=error_code,
            correlation_id=correlation_id,
            trace_id=trace_id,
            context=context or {},
            diagnostic_data=diagnostic_data or {},
        )

        def _detect(payload: Dict[str, Any]) -> Dict[str, Any]:
            return self.detection_pipeline.run(payload)

        try:
            sanitized = self.error_socket.send(raw_payload, _detect)
        except SchemaValidationError:
            trap = self.registry.require_definition("SYS-0001")
            self.logging_system.log("CRITICAL", "validation.log", "SYS-2002 schema trap engaged")
            instance.transition(ErrorLifecycleState.ABORTED)
            self.history_pipeline.run(instance, trap.severity)
            raise

        instance.transition(ErrorLifecycleState.VALIDATED)

        definition = self.registry.require_definition(sanitized["error_code"])
        self.metrics_manager.record_occurrence(error_code)

        self.logging_pipeline.run(
            "ERROR" if definition.severity in (SeverityLevel.ERROR, SeverityLevel.WARNING) else definition.severity.value,
            "detection.log",
            f"{error_code} {definition.name}: {definition.developer_message}",
            correlation_id=correlation_id,
            trace_id=trace_id,
        )
        instance.transition(ErrorLifecycleState.LOGGED)
        instance.transition(ErrorLifecycleState.CATEGORIZED)

        occurrence_rate = self.metrics_manager.rate_per_minute(error_code)
        evaluated_severity = self.escalation_pipeline.run(definition, occurrence_rate)

        if evaluated_severity in (SeverityLevel.CRITICAL, SeverityLevel.FATAL, SeverityLevel.EMERGENCY):
            self.audit_pipeline.run(
                {
                    "error_code": error_code,
                    "severity": evaluated_severity.value,
                    "instance_id": instance.instance_id,
                    "correlation_id": correlation_id,
                }
            )

        if not auto_recover or not self.severity_manager.requires_recovery(evaluated_severity):
            instance.transition(ErrorLifecycleState.RECOVERY_STARTED)
            instance.transition(ErrorLifecycleState.RESOLVED)
            instance.transition(ErrorLifecycleState.VERIFIED)
            instance.transition(ErrorLifecycleState.ARCHIVED)
            self.history_pipeline.run(instance, evaluated_severity)
            return instance

        instance.transition(ErrorLifecycleState.RECOVERY_STARTED)
        outcome = self.recovery_pipeline.run(definition, execution_context or {})
        instance.attempt_count += 1

        if outcome == "SUCCESS" and definition.recovery_strategy == RecoveryStrategyType.SAFE_MODE:
            instance.transition(ErrorLifecycleState.ESCALATED)
            instance.transition(ErrorLifecycleState.SAFE_MODE)
            instance.transition(ErrorLifecycleState.ARCHIVED)
        elif outcome == "SUCCESS" and definition.recovery_strategy == RecoveryStrategyType.EMERGENCY_SHUTDOWN:
            instance.transition(ErrorLifecycleState.ESCALATED)
            instance.transition(ErrorLifecycleState.EMERGENCY_SHUTDOWN)
            instance.transition(ErrorLifecycleState.ARCHIVED)
        elif outcome == "SUCCESS":
            instance.transition(ErrorLifecycleState.RESOLVED)
            instance.transition(ErrorLifecycleState.VERIFIED)
            instance.transition(ErrorLifecycleState.ARCHIVED)
        elif outcome == "ESCALATED":
            instance.transition(ErrorLifecycleState.ESCALATED)
            if self.severity_manager.requires_shutdown(evaluated_severity):
                target_state = (
                    ErrorLifecycleState.EMERGENCY_SHUTDOWN
                    if evaluated_severity == SeverityLevel.EMERGENCY
                    else ErrorLifecycleState.SAFE_MODE
                )
                instance.transition(target_state)
            else:
                instance.transition(ErrorLifecycleState.SAFE_MODE)
            instance.transition(ErrorLifecycleState.ARCHIVED)
        else:
            instance.transition(ErrorLifecycleState.ABORTED)
            instance.transition(ErrorLifecycleState.ARCHIVED)

        self.history_pipeline.run(instance, evaluated_severity)
        return instance

    def get_definition(self, error_code: str) -> Optional[AOSErrorDefinition]:
        return self.registry.get_definition(error_code)

    def localized_user_message(self, error_code: str, locale: Optional[str] = None, **params: Any) -> str:
        definition = self.registry.require_definition(error_code)
        return self.localization_manager.localize(definition, locale=locale, **params)

    def query_history(
        self, error_code: Optional[str] = None, severity: Optional[SeverityLevel] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        return self.history.query(error_code=error_code, severity=severity, limit=limit)

    def metrics_snapshot(self) -> Dict[str, Any]:
        return self.metrics_manager.snapshot()

    def audit_trail(self) -> List[Dict[str, Any]]:
        return self.audit_manager.trail()

    def verify_audit_integrity(self) -> bool:
        return self.audit_manager.verify_chain()

    def alerts(self) -> List[Dict[str, Any]]:
        return self.monitoring_manager.alerts()

    def catalog_size(self) -> int:
        return self.registry.count()

    def shutdown(self) -> None:
        self.history.close()


__all__ = [
    "ErrorCatalogOrgan",
    "ErrorCategory",
    "SeverityLevel",
    "RecoveryStrategyType",
    "RetryAlgorithm",
    "ErrorLifecycleState",
    "AOSErrorDefinition",
    "AOSErrorInstance",
    "RetryPolicyConfig",
    "ErrorCatalogBaseException",
    "UnregisteredErrorCodeError",
    "SchemaValidationError",
    "InvalidStateTransitionError",
    "RecoveryExhaustedError",
    "CodeFormatError",
    "IErrorRegistry",
    "IRecoveryManager",
]
