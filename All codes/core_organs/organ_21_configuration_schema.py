"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 21
Name: Configuration Schema

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Configuration Schema]
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
Dependencies: enum, typing, __future__, threading, urllib.parse...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_21_configuration_schema.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Hojaiga Automation OS — Configuration Schema Organ
====================================================
Authority: Configuration_Schema.md (Prompt 21)

PRE-CODE DIAGRAM
-----------------
ConfigFiles -> ConfigurationManager -> SchemaCore
SchemaCore -> {SchemaRegistry, TypeManager, VersionManager,
               DefaultValueManager, EnvironmentManager,
               DependencyValidator, MigrationManager,
               CompatibilityManager, SchemaDiscovery,
               DocumentationGenerator, AuditManager}
SchemaCore -> SchemaValidator -> {ConstraintManager, DependencyValidator,
                                   TypeManager, SecurityAssertor}
SchemaValidator -> ValidatedConfiguration -> {RuntimeComponents, SystemOrgans}

ACTUAL-CODE DIAGRAM
--------------------
SchemaCore.register_key()      -> SchemaRegistry.register()
SchemaCore.validate_configuration() -> SchemaValidator.validate()
SchemaCore.migrate_configuration()  -> MigrationManager.execute_migration()
SchemaValidator.validate() -> TypeManager.parse() -> ConstraintManager.assert_()
                            -> DependencyValidator.validate()
                            -> VersionManager.check_compatibility()
                            -> SecurityAssertor.assert_policy()

This module is side-effect-free and non-executing: it never performs
network I/O, never mutates external files, and never runs arbitrary code.
"""


import hashlib
import hmac
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Pattern, Tuple
from urllib.parse import urlparse


# ═══════════════════════════════════════════════════════════════════════
# ERROR CODES
# ═══════════════════════════════════════════════════════════════════════

class ErrorCode(str, Enum):
    ERR_UNDOCUMENTED_KEY = "ERR_UNDOCUMENTED_KEY"
    ERR_MISSING_REQUIRED_KEY = "ERR_MISSING_REQUIRED_KEY"
    ERR_TYPE_MISMATCH = "ERR_TYPE_MISMATCH"
    ERR_CONSTRAINT_EXCEEDED = "ERR_CONSTRAINT_EXCEEDED"
    ERR_REGEX_MISMATCH = "ERR_REGEX_MISMATCH"
    ERR_ENUM_VIOLATION = "ERR_ENUM_VIOLATION"
    ERR_DEPENDENCY_UNSATISFIED = "ERR_DEPENDENCY_UNSATISFIED"
    ERR_MUTUAL_EXCLUSIVITY_VIOLATION = "ERR_MUTUAL_EXCLUSIVITY_VIOLATION"
    ERR_DUPLICATE_KEY = "ERR_DUPLICATE_KEY"
    ERR_VERSION_INCOMPATIBLE = "ERR_VERSION_INCOMPATIBLE"
    ERR_ENVIRONMENT_VIOLATION = "ERR_ENVIRONMENT_VIOLATION"
    ERR_INVALID_SCHEMA_DEFINITION = "ERR_INVALID_SCHEMA_DEFINITION"
    ERR_MIGRATION_FAILED = "ERR_MIGRATION_FAILED"
    ERR_UNIT_PARSE_FAILURE = "ERR_UNIT_PARSE_FAILURE"
    ERR_SECURITY_CLEARANCE_DENIED = "ERR_SECURITY_CLEARANCE_DENIED"
    ERR_DEPRECATED_KEY_ACCESS = "ERR_DEPRECATED_KEY_ACCESS"
    ERR_SCHEMA_CORRUPTION = "ERR_SCHEMA_CORRUPTION"


class SchemaException(Exception):
    def __init__(self, code: ErrorCode, message: str, config_path: str = ""):
        self.code = code
        self.config_path = config_path
        super().__init__(f"{code.value}: {message}")


# ═══════════════════════════════════════════════════════════════════════
# DATA TYPES (Section 6 — 17 primary types)
# ═══════════════════════════════════════════════════════════════════════

class DataType(str, Enum):
    BOOLEAN = "Boolean"
    INTEGER = "Integer"
    FLOAT = "Float"
    STRING = "String"
    ENUM = "Enum"
    ARRAY = "Array"
    OBJECT = "Object"
    MAP = "Map"
    PATH = "Path"
    URL = "URL"
    DURATION = "Duration"
    MEMORY_SIZE = "MemorySize"
    CPU_PERCENTAGE = "CpuPercentage"
    GPU_PERCENTAGE = "GpuPercentage"
    REGULAR_EXPRESSION = "RegularExpression"
    CUSTOM_TYPE = "CustomType"
    SECRET_REFERENCE = "SecretReference"


_DURATION_UNITS = {"ms": 1, "s": 1000, "m": 60_000, "h": 3_600_000, "d": 86_400_000}
_MEMORY_UNITS = {
    "B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4,
}
_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)(ms|s|m|h|d)$")
_MEMORY_RE = re.compile(r"^(\d+(?:\.\d+)?)(B|KB|MB|GB|TB)$")
_PERCENT_RE = re.compile(r"^(\d+(?:\.\d+)?)%$")
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class SecretReference:
    """Non-resolving pointer to an externally stored secret. Never holds
    the plaintext secret value; Configuration Schema never resolves secrets."""

    __slots__ = ("vault", "key")

    def __init__(self, vault: str, key: str):
        self.vault = vault
        self.key = key

    def __repr__(self) -> str:
        return f"SecretReference(vault={self.vault!r}, key=***)"

    @staticmethod
    def parse(raw: str) -> "SecretReference":
        # Format: secret://<vault>/<key>
        if not raw.startswith("secret://"):
            raise SchemaException(ErrorCode.ERR_TYPE_MISMATCH,
                                   f"Invalid secret reference: {raw}")
        body = raw[len("secret://"):]
        parts = body.split("/", 1)
        if len(parts) != 2 or not all(parts):
            raise SchemaException(ErrorCode.ERR_TYPE_MISMATCH,
                                   f"Malformed secret reference: {raw}")
        return SecretReference(parts[0], parts[1])


class TypeManager:
    """Section 3.4 — Type Manager. Parses raw values into deterministic
    native representations. Side-effect free."""

    def parse(self, value: Any, data_type: DataType,
              config_path: str, custom_validator: Optional[Callable[[Any], bool]] = None) -> Any:
        try:
            if data_type == DataType.BOOLEAN:
                return self._parse_bool(value)
            if data_type == DataType.INTEGER:
                return self._parse_int(value)
            if data_type == DataType.FLOAT:
                return float(value)
            if data_type == DataType.STRING:
                if not isinstance(value, str):
                    raise ValueError("not a string")
                return value
            if data_type == DataType.ENUM:
                if not isinstance(value, str):
                    raise ValueError("enum value must be string")
                return value
            if data_type == DataType.ARRAY:
                if not isinstance(value, (list, tuple)):
                    raise ValueError("not an array")
                return list(value)
            if data_type == DataType.OBJECT:
                if not isinstance(value, dict):
                    raise ValueError("not an object")
                return dict(value)
            if data_type == DataType.MAP:
                if not isinstance(value, dict):
                    raise ValueError("not a map")
                return dict(value)
            if data_type == DataType.PATH:
                if not isinstance(value, str) or not value:
                    raise ValueError("invalid path")
                return value.replace("\\", "/")
            if data_type == DataType.URL:
                parsed = urlparse(value)
                if not parsed.scheme or not parsed.netloc:
                    raise ValueError("invalid URL")
                return value
            if data_type == DataType.DURATION:
                return self._parse_duration(value)
            if data_type == DataType.MEMORY_SIZE:
                return self._parse_memory(value)
            if data_type in (DataType.CPU_PERCENTAGE, DataType.GPU_PERCENTAGE):
                return self._parse_percentage(value)
            if data_type == DataType.REGULAR_EXPRESSION:
                return self._parse_regex(value)
            if data_type == DataType.SECRET_REFERENCE:
                return SecretReference.parse(value) if isinstance(value, str) else value
            if data_type == DataType.CUSTOM_TYPE:
                if custom_validator and not custom_validator(value):
                    raise ValueError("custom validator rejected value")
                return value
            raise ValueError(f"unsupported data type {data_type}")
        except (ValueError, TypeError) as exc:
            raise SchemaException(ErrorCode.ERR_TYPE_MISMATCH,
                                   f"{data_type.value} parse failure: {exc}",
                                   config_path) from exc

    @staticmethod
    def _parse_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            low = value.strip().lower()
            if low in ("true", "1"):
                return True
            if low in ("false", "0"):
                return False
        raise ValueError("not a boolean literal")

    @staticmethod
    def _parse_int(value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("bool is not integer")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.lstrip("-").isdigit():
            return int(value)
        raise ValueError("not an integer")

    @staticmethod
    def _parse_duration(value: Any) -> int:
        if isinstance(value, (int, float)):
            return int(value)
        match = _DURATION_RE.match(str(value).strip())
        if not match:
            raise ValueError(f"invalid duration format: {value}")
        amount, unit = match.groups()
        return int(float(amount) * _DURATION_UNITS[unit])

    @staticmethod
    def _parse_memory(value: Any) -> int:
        if isinstance(value, int):
            return value
        match = _MEMORY_RE.match(str(value).strip())
        if not match:
            raise ValueError(f"invalid memory size format: {value}")
        amount, unit = match.groups()
        return int(float(amount) * _MEMORY_UNITS[unit])

    @staticmethod
    def _parse_percentage(value: Any) -> float:
        if isinstance(value, (int, float)):
            result = float(value)
        else:
            match = _PERCENT_RE.match(str(value).strip())
            if not match:
                raise ValueError(f"invalid percentage format: {value}")
            result = float(match.group(1)) / 100.0
        if not (0.0 <= result <= 1.0):
            raise ValueError("percentage out of 0-100% range")
        return result

    @staticmethod
    def _parse_regex(value: Any) -> Pattern:
        if isinstance(value, re.Pattern):
            return value
        return re.compile(value)


# ═══════════════════════════════════════════════════════════════════════
# SCHEMA KEY STRUCTURE (Section 5)
# ═══════════════════════════════════════════════════════════════════════

class Environment(str, Enum):
    DEVELOPMENT = "Development"
    TESTING = "Testing"
    PRODUCTION = "Production"
    LOCAL = "Local"
    CLOUD = "Cloud"
    HYBRID = "Hybrid"
    OFFLINE = "Offline"
    DISTRIBUTED = "Distributed"


class DependencyCondition(str, Enum):
    EQUALS = "EQUALS"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"


class MigrationAction(str, Enum):
    RENAME = "RENAME"
    TRANSFORM = "TRANSFORM"
    CAST = "CAST"
    SET_DEFAULT = "SET_DEFAULT"


@dataclass(frozen=True)
class DependencyRule:
    target_path: str
    condition: DependencyCondition
    expected_value: Any = None


@dataclass(frozen=True)
class MigrationRule:
    from_version: str
    to_version: str
    action: MigrationAction
    transform: Optional[Callable[[Any], Any]] = None
    rename_to: Optional[str] = None


@dataclass(frozen=True)
class ConfigKeyDefinition:
    config_id: str
    config_path: str
    key_name: str
    description: str
    category: str
    data_type: DataType
    required: bool = False
    default_value: Any = None
    allowed_values: Optional[List[Any]] = None
    minimum_value: Optional[float] = None
    maximum_value: Optional[float] = None
    regular_expression: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_items: Optional[int] = None
    max_items: Optional[int] = None
    dependencies: Tuple[DependencyRule, ...] = field(default_factory=tuple)
    mutually_exclusive_with: Tuple[str, ...] = field(default_factory=tuple)
    environment_support: Tuple[Environment, ...] = field(
        default_factory=lambda: tuple(Environment))
    version: str = "1.0.0"
    migration_rules: Tuple[MigrationRule, ...] = field(default_factory=tuple)
    deprecated: bool = False
    replacement_key: Optional[str] = None
    owner: str = "system"
    documentation_reference: str = ""
    is_secret: bool = False
    security_clearance: str = "SYSTEM_ORGAN"
    custom_validator: Optional[Callable[[Any], bool]] = None

    def __post_init__(self):
        if not self.config_path or not self.category or not self.data_type:
            raise SchemaException(
                ErrorCode.ERR_INVALID_SCHEMA_DEFINITION,
                "Missing required metadata fields (config_path/category/data_type)",
                self.config_path or "<unknown>")
        if not _SEMVER_RE.match(self.version):
            raise SchemaException(
                ErrorCode.ERR_INVALID_SCHEMA_DEFINITION,
                f"Version must follow MAJOR.MINOR.PATCH: {self.version}",
                self.config_path)


# ═══════════════════════════════════════════════════════════════════════
# VALIDATION RESULT TYPES
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ValidationError:
    code: ErrorCode
    config_path: str
    message: str
    provided_value: Any = None


@dataclass
class ValidationWarning:
    code: str
    config_path: str
    message: str


@dataclass
class ValidationResult:
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationWarning] = field(default_factory=list)
    validated_payload: Optional[Dict[str, Any]] = None


# ═══════════════════════════════════════════════════════════════════════
# AUDIT MANAGER (Section 3.14)
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class AuditRecord:
    timestamp: float
    event: str
    config_path: str
    signature: str


class AuditManager:
    """Append-only in-memory audit trail with HMAC tamper-evidence."""

    def __init__(self, secret_key: bytes = b"hojaiga-audit-key"):
        self._secret_key = secret_key
        self._records: List[AuditRecord] = []
        self._lock = threading.Lock()

    def log_event(self, event: str, config_path: str) -> AuditRecord:
        ts = time.time()
        payload = f"{ts}|{event}|{config_path}".encode("utf-8")
        signature = hmac.new(self._secret_key, payload, hashlib.sha256).hexdigest()
        record = AuditRecord(ts, event, config_path, signature)
        with self._lock:
            self._records.append(record)
        return record

    def history(self) -> Tuple[AuditRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def verify(self, record: AuditRecord) -> bool:
        payload = f"{record.timestamp}|{record.event}|{record.config_path}".encode("utf-8")
        expected = hmac.new(self._secret_key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, record.signature)


# ═══════════════════════════════════════════════════════════════════════
# SCHEMA REGISTRY (Section 3.2)
# ═══════════════════════════════════════════════════════════════════════

class SchemaRegistry:
    """Thread-safe central repository of registered schema definitions."""

    def __init__(self):
        self._by_path: Dict[str, ConfigKeyDefinition] = {}
        self._by_category: Dict[str, List[str]] = {}
        self._lock = threading.RLock()

    def register(self, key_def: ConfigKeyDefinition) -> bool:
        with self._lock:
            if key_def.config_path in self._by_path:
                raise SchemaException(
                    ErrorCode.ERR_DUPLICATE_KEY,
                    f"Configuration path already registered: {key_def.config_path}",
                    key_def.config_path)
            self._by_path[key_def.config_path] = key_def
            self._by_category.setdefault(key_def.category, []).append(key_def.config_path)
            return True

    def get(self, config_path: str) -> Optional[ConfigKeyDefinition]:
        with self._lock:
            return self._by_path.get(config_path)

    def is_registered(self, config_path: str) -> bool:
        with self._lock:
            return config_path in self._by_path

    def keys_in_category(self, category: str) -> Tuple[str, ...]:
        with self._lock:
            return tuple(self._by_category.get(category, ()))

    def search(self, pattern: str) -> Tuple[ConfigKeyDefinition, ...]:
        regex = re.compile(pattern)
        with self._lock:
            return tuple(d for p, d in self._by_path.items() if regex.search(p))

    def all_keys(self) -> Tuple[str, ...]:
        with self._lock:
            return tuple(self._by_path.keys())

    def unregister(self, config_path: str) -> None:
        with self._lock:
            key_def = self._by_path.pop(config_path, None)
            if key_def:
                self._by_category.get(key_def.category, []).remove(config_path)


# ═══════════════════════════════════════════════════════════════════════
# CONSTRAINT MANAGER (Section 3.5)
# ═══════════════════════════════════════════════════════════════════════

class ConstraintManager:
    def assert_constraints(self, value: Any, key_def: ConfigKeyDefinition) -> Optional[ValidationError]:
        path = key_def.config_path

        if key_def.allowed_values is not None and value not in key_def.allowed_values:
            return ValidationError(ErrorCode.ERR_ENUM_VIOLATION, path,
                                    f"Value {value!r} not in allowed set {key_def.allowed_values}", value)

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if key_def.minimum_value is not None and value < key_def.minimum_value:
                return ValidationError(ErrorCode.ERR_CONSTRAINT_EXCEEDED, path,
                                        f"Value {value} below minimum {key_def.minimum_value}", value)
            if key_def.maximum_value is not None and value > key_def.maximum_value:
                return ValidationError(ErrorCode.ERR_CONSTRAINT_EXCEEDED, path,
                                        f"Value {value} exceeds maximum {key_def.maximum_value}", value)

        if isinstance(value, str):
            if key_def.min_length is not None and len(value) < key_def.min_length:
                return ValidationError(ErrorCode.ERR_CONSTRAINT_EXCEEDED, path,
                                        f"String shorter than min_length {key_def.min_length}", value)
            if key_def.max_length is not None and len(value) > key_def.max_length:
                return ValidationError(ErrorCode.ERR_CONSTRAINT_EXCEEDED, path,
                                        f"String longer than max_length {key_def.max_length}", value)
            if key_def.regular_expression and not re.match(key_def.regular_expression, value):
                return ValidationError(ErrorCode.ERR_REGEX_MISMATCH, path,
                                        f"Value does not match pattern {key_def.regular_expression}", value)

        if isinstance(value, (list, tuple)):
            if key_def.min_items is not None and len(value) < key_def.min_items:
                return ValidationError(ErrorCode.ERR_CONSTRAINT_EXCEEDED, path,
                                        f"Array shorter than min_items {key_def.min_items}", value)
            if key_def.max_items is not None and len(value) > key_def.max_items:
                return ValidationError(ErrorCode.ERR_CONSTRAINT_EXCEEDED, path,
                                        f"Array longer than max_items {key_def.max_items}", value)

        return None


# ═══════════════════════════════════════════════════════════════════════
# DEPENDENCY VALIDATOR (Section 3.7)
# ═══════════════════════════════════════════════════════════════════════

class DependencyValidator:
    def validate(self, payload: Dict[str, Any],
                 key_def: ConfigKeyDefinition) -> List[ValidationError]:
        errors: List[ValidationError] = []
        present = key_def.config_path in payload

        for rule in key_def.dependencies:
            target_present = rule.target_path in payload
            target_value = payload.get(rule.target_path)
            satisfied = True
            if rule.condition == DependencyCondition.EXISTS:
                satisfied = target_present
            elif rule.condition == DependencyCondition.NOT_EXISTS:
                satisfied = not target_present
            elif rule.condition == DependencyCondition.EQUALS:
                satisfied = target_present and target_value == rule.expected_value
            if present and not satisfied:
                errors.append(ValidationError(
                    ErrorCode.ERR_DEPENDENCY_UNSATISFIED, key_def.config_path,
                    f"Requires {rule.target_path} to satisfy {rule.condition.value}"))

        if present:
            for exclusive_path in key_def.mutually_exclusive_with:
                if exclusive_path in payload:
                    errors.append(ValidationError(
                        ErrorCode.ERR_MUTUAL_EXCLUSIVITY_VIOLATION, key_def.config_path,
                        f"Mutually exclusive with {exclusive_path}"))
        return errors


# ═══════════════════════════════════════════════════════════════════════
# DEFAULT VALUE MANAGER (Section 3.6, 8 — 6-tier hierarchy)
# ═══════════════════════════════════════════════════════════════════════

class DefaultTier(str, Enum):
    RECOVERY = "RECOVERY"
    FALLBACK = "FALLBACK"
    PRODUCTION = "PRODUCTION"
    DEVELOPMENT = "DEVELOPMENT"
    ENVIRONMENT = "ENVIRONMENT"
    SYSTEM = "SYSTEM"


class DefaultValueManager:
    """Resolves default values through a 6-tier precedence chain:
    RECOVERY > FALLBACK > PRODUCTION > DEVELOPMENT > ENVIRONMENT > SYSTEM."""

    _RESOLUTION_ORDER = (
        DefaultTier.RECOVERY, DefaultTier.FALLBACK, DefaultTier.PRODUCTION,
        DefaultTier.DEVELOPMENT, DefaultTier.ENVIRONMENT, DefaultTier.SYSTEM,
    )

    def __init__(self):
        self._tier_values: Dict[DefaultTier, Dict[str, Any]] = {t: {} for t in DefaultTier}

    def set_tier_value(self, tier: DefaultTier, config_path: str, value: Any) -> None:
        self._tier_values[tier][config_path] = value

    def resolve(self, key_def: ConfigKeyDefinition, environment: Environment) -> Any:
        for tier in self._RESOLUTION_ORDER:
            values = self._tier_values[tier]
            if tier == DefaultTier.PRODUCTION and environment != Environment.PRODUCTION:
                continue
            if tier == DefaultTier.DEVELOPMENT and environment != Environment.DEVELOPMENT:
                continue
            if key_def.config_path in values:
                return values[key_def.config_path]
        if key_def.default_value is not None:
            return key_def.default_value
        raise SchemaException(
            ErrorCode.ERR_MISSING_REQUIRED_KEY,
            f"No default resolvable for {key_def.config_path} in {environment.value}",
            key_def.config_path)


# ═══════════════════════════════════════════════════════════════════════
# VERSION MANAGER (Section 3.8, 9)
# ═══════════════════════════════════════════════════════════════════════

class CompatibilityStatus(str, Enum):
    COMPATIBLE = "COMPATIBLE"
    MIGRATION_REQUIRED = "MIGRATION_REQUIRED"
    INCOMPATIBLE = "INCOMPATIBLE"


class VersionManager:
    def __init__(self, max_major_gap: int = 1):
        self._max_major_gap = max_major_gap

    @staticmethod
    def parse(version: str) -> Tuple[int, int, int]:
        match = _SEMVER_RE.match(version)
        if not match:
            raise SchemaException(ErrorCode.ERR_VERSION_INCOMPATIBLE,
                                   f"Unparseable semver: {version}")
        return tuple(int(part) for part in match.groups())  # type: ignore

    def check_compatibility(self, incoming: str, system: str) -> CompatibilityStatus:
        in_major, in_minor, _ = self.parse(incoming)
        sys_major, sys_minor, _ = self.parse(system)
        if in_major == sys_major:
            return CompatibilityStatus.COMPATIBLE
        gap = abs(sys_major - in_major)
        if gap <= self._max_major_gap:
            return CompatibilityStatus.MIGRATION_REQUIRED
        return CompatibilityStatus.INCOMPATIBLE


# ═══════════════════════════════════════════════════════════════════════
# MIGRATION MANAGER (Section 3.9)
# ═══════════════════════════════════════════════════════════════════════

class MigrationManager:
    def __init__(self, registry: SchemaRegistry, version_mgr: VersionManager,
                 audit: AuditManager):
        self._registry = registry
        self._version_mgr = version_mgr
        self._audit = audit

    def execute_migration(self, payload: Dict[str, Any],
                           from_version: str, to_version: str) -> Dict[str, Any]:
        result = dict(payload)
        for config_path, key_def in ((p, self._registry.get(p)) for p in self._registry.all_keys()):
            if key_def is None:
                continue
            for rule in key_def.migration_rules:
                if rule.from_version != from_version or rule.to_version != to_version:
                    continue
                try:
                    result = self._apply_rule(result, config_path, rule)
                except Exception as exc:
                    raise SchemaException(
                        ErrorCode.ERR_MIGRATION_FAILED,
                        f"Migration rule failed for {config_path}: {exc}",
                        config_path) from exc
        self._audit.log_event("MIGRATION_EXECUTED", f"{from_version}->{to_version}")
        return result

    @staticmethod
    def _apply_rule(payload: Dict[str, Any], config_path: str,
                     rule: MigrationRule) -> Dict[str, Any]:
        if rule.action == MigrationAction.RENAME and rule.rename_to and config_path in payload:
            payload[rule.rename_to] = payload.pop(config_path)
        elif rule.action == MigrationAction.TRANSFORM and rule.transform and config_path in payload:
            payload[config_path] = rule.transform(payload[config_path])
        elif rule.action == MigrationAction.CAST and rule.transform and config_path in payload:
            payload[config_path] = rule.transform(payload[config_path])
        elif rule.action == MigrationAction.SET_DEFAULT and config_path not in payload:
            payload[config_path] = rule.transform(None) if rule.transform else None
        return payload


# ═══════════════════════════════════════════════════════════════════════
# COMPATIBILITY MANAGER (Section 3.10)
# ═══════════════════════════════════════════════════════════════════════

class CompatibilityManager:
    def __init__(self, version_mgr: VersionManager):
        self._version_mgr = version_mgr

    def check_organ(self, organ_schema_version: str, core_version: str) -> CompatibilityStatus:
        return self._version_mgr.check_compatibility(organ_schema_version, core_version)


# ═══════════════════════════════════════════════════════════════════════
# ENVIRONMENT MANAGER (Section 3.11)
# ═══════════════════════════════════════════════════════════════════════

class EnvironmentManager:
    _LOCKED_IN_PRODUCTION = {"debug_mode", "verbose_logging", "mock_services"}

    def validate_override(self, config_path: str, environment: Environment) -> Optional[ValidationError]:
        leaf = config_path.rsplit(".", 1)[-1]
        if environment == Environment.PRODUCTION and leaf in self._LOCKED_IN_PRODUCTION:
            return ValidationError(
                ErrorCode.ERR_ENVIRONMENT_VIOLATION, config_path,
                f"'{leaf}' cannot be overridden in Production environment")
        return None

    @staticmethod
    def map_env_vars(prefix: str, raw_env: Dict[str, str]) -> Dict[str, str]:
        mapped: Dict[str, str] = {}
        upper_prefix = prefix.upper() + "_"
        for key, value in raw_env.items():
            if key.upper().startswith(upper_prefix):
                path = key[len(upper_prefix):].lower().replace("__", ".")
                mapped[path] = value
        return mapped


# ═══════════════════════════════════════════════════════════════════════
# SECURITY ASSERTOR
# ═══════════════════════════════════════════════════════════════════════

_CLEARANCE_RANK = {"KERNEL_ROOT": 0, "SYSTEM_ORGAN": 1, "INTERNAL": 2, "PUBLIC": 3}


class SecurityAssertor:
    def assert_policy(self, key_def: ConfigKeyDefinition, caller_clearance: str) -> Optional[ValidationError]:
        required = _CLEARANCE_RANK.get(key_def.security_clearance, 3)
        actual = _CLEARANCE_RANK.get(caller_clearance, 3)
        if actual > required:
            return ValidationError(
                ErrorCode.ERR_SECURITY_CLEARANCE_DENIED, key_def.config_path,
                f"Caller clearance {caller_clearance} insufficient for {key_def.security_clearance}")
        return None

    @staticmethod
    def mask_secrets(payload: Dict[str, Any], registry: SchemaRegistry) -> Dict[str, Any]:
        masked = dict(payload)
        for path in registry.all_keys():
            key_def = registry.get(path)
            if key_def and key_def.is_secret and path in masked:
                masked[path] = "***MASKED***"
        return masked


# ═══════════════════════════════════════════════════════════════════════
# SCHEMA DISCOVERY (Section 3.13)
# ═══════════════════════════════════════════════════════════════════════

class SchemaDiscovery:
    def __init__(self, registry: SchemaRegistry):
        self._registry = registry

    def by_category(self, category: str) -> Tuple[ConfigKeyDefinition, ...]:
        return tuple(key_def for key_def in (self._registry.get(p) for p in self._registry.keys_in_category(category)) if key_def is not None)

    def search(self, pattern: str) -> Tuple[ConfigKeyDefinition, ...]:
        return self._registry.search(pattern)


# ═══════════════════════════════════════════════════════════════════════
# DOCUMENTATION GENERATOR (Section 3.12)
# ═══════════════════════════════════════════════════════════════════════

class DocumentationGenerator:
    def __init__(self, registry: SchemaRegistry):
        self._registry = registry

    def to_markdown(self) -> str:
        lines = ["# Configuration Schema Reference", ""]
        for path in sorted(self._registry.all_keys()):
            key_def = self._registry.get(path)
            lines.append(f"## `{path}`")
            lines.append(f"- Type: {key_def.data_type.value}")  # type: ignore
            lines.append(f"- Required: {key_def.required}")  # type: ignore
            lines.append(f"- Category: {key_def.category}")  # type: ignore
            lines.append(f"- Description: {key_def.description}")  # type: ignore
            lines.append("")
        return "\n".join(lines)

    def to_json_schema(self) -> Dict[str, Any]:
        properties = {}
        required = []
        for path in self._registry.all_keys():
            key_def = self._registry.get(path)
            properties[path] = {"type": key_def.data_type.value, "description": key_def.description}  # type: ignore
            if key_def.required:  # type: ignore
                required.append(path)
        return {"type": "object", "properties": properties, "required": required,
                "additionalProperties": False}


# ═══════════════════════════════════════════════════════════════════════
# SCHEMA VALIDATOR (Section 3.3, 7)
# ═══════════════════════════════════════════════════════════════════════

class SchemaValidator:
    def __init__(self, registry: SchemaRegistry, type_mgr: TypeManager,
                 constraint_mgr: ConstraintManager, dependency_validator: DependencyValidator,
                 env_mgr: EnvironmentManager, security: SecurityAssertor,
                 default_mgr: DefaultValueManager):
        self._registry = registry
        self._type_mgr = type_mgr
        self._constraint_mgr = constraint_mgr
        self._dependency_validator = dependency_validator
        self._env_mgr = env_mgr
        self._security = security
        self._default_mgr = default_mgr

    def validate(self, category: str, payload: Dict[str, Any], environment: Environment,
                 caller_clearance: str = "SYSTEM_ORGAN",
                 reject_undocumented: bool = True) -> ValidationResult:
        errors: List[ValidationError] = []
        warnings: List[ValidationWarning] = []
        validated: Dict[str, Any] = {}

        category_keys = set(self._registry.keys_in_category(category))

        # 1. Structural check — reject undocumented keys
        if reject_undocumented:
            for path in payload:
                if path not in category_keys:
                    errors.append(ValidationError(
                        ErrorCode.ERR_UNDOCUMENTED_KEY, path,
                        f"Key '{path}' is not registered in category '{category}'"))

        for path in category_keys:
            key_def = self._registry.get(path)

            if key_def is None:
                errors.append(ValidationError(
                    ErrorCode.ERR_UNDOCUMENTED_KEY, path,
                    f"Key '{path}' not found in registry"))
                continue

            if key_def.deprecated:  # type: ignore
                warnings.append(ValidationWarning(
                    ErrorCode.ERR_DEPRECATED_KEY_ACCESS.value, path,
                    f"Deprecated; use {key_def.replacement_key or 'no replacement'}"))  # type: ignore

            if path not in payload:
                if key_def.required:  # type: ignore
                    try:
                        validated[path] = self._default_mgr.resolve(key_def, environment)
                    except SchemaException:
                        errors.append(ValidationError(
                            ErrorCode.ERR_MISSING_REQUIRED_KEY, path,
                            "Required key missing and no default resolvable"))
                else:
                    try:
                        validated[path] = self._default_mgr.resolve(key_def, environment)
                    except SchemaException:
                        pass
                continue

            raw_value = payload[path]

            if environment not in key_def.environment_support:  # type: ignore
                errors.append(ValidationError(
                    ErrorCode.ERR_ENVIRONMENT_VIOLATION, path,
                    f"Key not supported in environment {environment.value}"))
                continue

            env_error = self._env_mgr.validate_override(path, environment)
            if env_error:
                errors.append(env_error)
                continue

            sec_error = self._security.assert_policy(key_def, caller_clearance)
            if sec_error:
                errors.append(sec_error)
                continue

            try:
                parsed_value = self._type_mgr.parse(raw_value, key_def.data_type, path,  # type: ignore
                                                      key_def.custom_validator)  # type: ignore
            except SchemaException as exc:
                errors.append(ValidationError(exc.code, path, str(exc), raw_value))
                continue

            constraint_error = self._constraint_mgr.assert_constraints(parsed_value, key_def)
            if constraint_error:
                errors.append(constraint_error)
                continue

            dep_errors = self._dependency_validator.validate(payload, key_def)
            errors.extend(dep_errors)

            validated[path] = parsed_value

        is_valid = len(errors) == 0
        return ValidationResult(is_valid, errors, warnings,
                                 validated if is_valid else None)


# ═══════════════════════════════════════════════════════════════════════
# SCHEMA CORE (Section 3.1, 20.1 — Public Entry Point)
# ═══════════════════════════════════════════════════════════════════════

class SchemaCore:
    """Primary entry point for the Configuration Schema organ. Orchestrates
    registration, validation, migration, discovery and documentation."""

    SYSTEM_VERSION = "1.0.0"

    def __init__(self):
        self.registry = SchemaRegistry()
        self.type_manager = TypeManager()
        self.constraint_manager = ConstraintManager()
        self.dependency_validator = DependencyValidator()
        self.default_value_manager = DefaultValueManager()
        self.version_manager = VersionManager()
        self.environment_manager = EnvironmentManager()
        self.security_assertor = SecurityAssertor()
        self.audit_manager = AuditManager()
        self.migration_manager = MigrationManager(self.registry, self.version_manager, self.audit_manager)
        self.compatibility_manager = CompatibilityManager(self.version_manager)
        self.discovery = SchemaDiscovery(self.registry)
        self.documentation_generator = DocumentationGenerator(self.registry)
        self.validator = SchemaValidator(
            self.registry, self.type_manager, self.constraint_manager,
            self.dependency_validator, self.environment_manager,
            self.security_assertor, self.default_value_manager)

    def register_key(self, key_def: ConfigKeyDefinition) -> bool:
        success = self.registry.register(key_def)
        if success:
            self.audit_manager.log_event("KEY_REGISTERED", key_def.config_path)
        return success

    def validate_configuration(self, category: str, payload: Dict[str, Any],
                                environment: Environment,
                                caller_clearance: str = "SYSTEM_ORGAN") -> ValidationResult:
        result = self.validator.validate(category, payload, environment, caller_clearance)
        self.audit_manager.log_event(
            "VALIDATE_CONFIGURATION" if result.valid else "VALIDATE_CONFIGURATION_FAILED",
            category)
        return result

    def migrate_configuration(self, payload: Dict[str, Any],
                               from_version: str, to_version: str) -> Dict[str, Any]:
        return self.migration_manager.execute_migration(payload, from_version, to_version)

    def check_compatibility(self, incoming_version: str) -> CompatibilityStatus:
        return self.version_manager.check_compatibility(incoming_version, self.SYSTEM_VERSION)


# ═══════════════════════════════════════════════════════════════════════
# RECOVERY SCHEMA — Hardcoded SAFE-mode fallback (Tier 1 Recovery Defaults)
# ═══════════════════════════════════════════════════════════════════════

RECOVERY_SCHEMA_DEFAULTS: Dict[str, Any] = {
    "kernel.process.max_threads": 4,
    "kernel.boot.safe_mode": True,
    "brain.llm.enabled": False,
}
