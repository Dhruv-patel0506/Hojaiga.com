"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 20
Name: Configuration Manager

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Configuration Manager]
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
Dependencies: copy, enum, pathlib, __future__, typing...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_20_configuration_manager.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Configuration Manager Organ — Hojaiga Automation OS
=====================================================

PRE-CODE DIAGRAM
-----------------
System Layer
    |
    v
ConfigurationManager (Core)
    |-- ConfigRegistry      (component -> file path index)
    |-- ConfigCache         (in-memory resolved payloads)
    |-- SchemaManager        (JSON Schema store + compile)
    |-- ConfigValidator      (schema/type/dependency checks)
    |-- EnvironmentManager   (env var overrides)
    |-- SecretsRefManager    (secret:// URI resolution)
    |-- VersionManager       (semver + revision history)
    |-- MigrationManager     (up/down transforms)
    |-- BackupManager        (snapshot + restore)
    |-- LiveReloadManager    (file watch + subscriber notify)
    |-- AuditLog             (append-only JSONL)
    v
Socket (ConfigSocket) <--> Pipeline (ConfigPipeline) <--> Subsystem Consumers

ACTUAL-CODE DIAGRAM
--------------------
get_configuration(component_id)
  -> cache hit? return
  -> load from disk -> validate -> resolve secrets -> resolve env overrides
  -> cache write -> audit -> return

set_configuration(component_id, payload)
  -> validate -> version bump -> backup snapshot -> write disk
  -> cache invalidate -> live reload dispatch -> audit -> return

Communicates ONLY via ConfigSocket/ConfigPipeline (Universal Law 5).
"""


import copy
import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


# --------------------------------------------------------------------------- #
# Status / Errors
# --------------------------------------------------------------------------- #

class ConfigStatus(str, Enum):
    SUCCESS = "SUCCESS"
    INVALID_SCHEMA = "INVALID_SCHEMA"
    NOT_FOUND = "NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TIMEOUT = "TIMEOUT"
    CONFLICT = "CONFLICT"


class ConfigError(Exception):
    def __init__(self, status: ConfigStatus, message: str):
        self.status = status
        self.message = message
        super().__init__(f"[{status.value}] {message}")


# --------------------------------------------------------------------------- #
# Data contracts
# --------------------------------------------------------------------------- #

@dataclass
class ConfigRequest:
    component_id: str
    category: str = "default"
    environment: str = "production"
    user_id: str = "system"


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ConfigRecord:
    component_id: str
    payload: dict
    version: str
    checksum: str
    updated_at: float


# --------------------------------------------------------------------------- #
# Audit Log (append-only)
# --------------------------------------------------------------------------- #

class AuditLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(self, action: str, component_id: str, status: str, detail: str = ""):
        entry = {
            "id": str(uuid.uuid4()),
            "ts": time.time(),
            "action": action,
            "component_id": component_id,
            "status": status,
            "detail": detail,
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")


# --------------------------------------------------------------------------- #
# Schema Manager
# --------------------------------------------------------------------------- #

class SchemaManager:
    """Minimal draft-07-style JSON Schema store and validator (no external deps)."""

    def __init__(self):
        self._schemas: dict[str, dict] = {}

    def register(self, category: str, schema: dict):
        self._schemas[category] = schema

    def get(self, category: str) -> Optional[dict]:
        return self._schemas.get(category)

    @staticmethod
    def validate(payload: dict, schema: dict) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        required = schema.get("required", [])
        for field_name in required:
            if field_name not in payload:
                errors.append(f"missing required field: {field_name}")

        props = schema.get("properties", {})
        for key, value in payload.items():
            spec = props.get(key)
            if spec is None:
                continue
            expected_type = spec.get("type")
            if expected_type and not SchemaManager._check_type(value, expected_type):
                errors.append(f"field '{key}' expected type {expected_type}, got {type(value).__name__}")
            if "minimum" in spec and isinstance(value, (int, float)) and value < spec["minimum"]:
                errors.append(f"field '{key}' below minimum {spec['minimum']}")
            if "maximum" in spec and isinstance(value, (int, float)) and value > spec["maximum"]:
                errors.append(f"field '{key}' above maximum {spec['maximum']}")
            if "enum" in spec and value not in spec["enum"]:
                errors.append(f"field '{key}' not in allowed enum {spec['enum']}")

        for key in schema.get("deprecated", []):
            if key in payload:
                warnings.append(f"field '{key}' is deprecated")

        return ValidationResult(is_valid=not errors, errors=errors, warnings=warnings)

    @staticmethod
    def _check_type(value: Any, expected: str) -> bool:
        mapping = {
            "string": str, "number": (int, float), "integer": int,
            "boolean": bool, "object": dict, "array": list, "null": type(None),
        }
        py_type = mapping.get(expected)
        return py_type is None or isinstance(value, py_type)


# --------------------------------------------------------------------------- #
# Validator (schema + dependency)
# --------------------------------------------------------------------------- #

class ConfigValidator:
    def __init__(self, schema_manager: SchemaManager):
        self._schemas = schema_manager

    def validate(self, category: str, payload: dict) -> ValidationResult:
        schema = self._schemas.get(category)
        if schema is None:
            return ValidationResult(is_valid=True, warnings=[f"no schema registered for '{category}'"])
        result = self.schema_manager_validate(payload, schema)
        deps = schema.get("dependencies", {})
        for key, required_keys in deps.items():
            if key in payload:
                for dep in required_keys:
                    if dep not in payload:
                        result.errors.append(f"dependency violation: '{key}' requires '{dep}'")
                        result.is_valid = False
        return result

    def schema_manager_validate(self, payload: dict, schema: dict) -> ValidationResult:
        return SchemaManager.validate(payload, schema)


# --------------------------------------------------------------------------- #
# Environment / Secrets Managers
# --------------------------------------------------------------------------- #

class EnvironmentManager:
    """Applies env var overrides: HOJAIGA_<COMPONENT>_<KEY>=value"""

    PREFIX = "HOJAIGA"

    def apply_overrides(self, component_id: str, payload: dict) -> dict:
        result = copy.deepcopy(payload)
        prefix = f"{self.PREFIX}_{component_id.upper()}_"
        for env_key, env_val in os.environ.items():
            if env_key.startswith(prefix):
                field_name = env_key[len(prefix):].lower()
                result[field_name] = self._coerce(env_val)
        return result

    @staticmethod
    def _coerce(value: str) -> Any:
        if value.lower() in ("true", "false"):
            return value.lower() == "true"
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value


class SecretsReferenceManager:
    """Resolves 'secret://vault/key' URIs into proxy handles (never plaintext)."""

    PATTERN = re.compile(r"^secret://(?P<vault>[\w\-]+)/(?P<key>[\w\-./]+)$")

    def resolve(self, payload: dict) -> dict:
        return self._walk(payload)

    def _walk(self, node: Any) -> Any:
        if isinstance(node, dict):
            return {k: self._walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [self._walk(v) for v in node]
        if isinstance(node, str):
            match = self.PATTERN.match(node)
            if match:
                return {
                    "__secret_ref__": True,
                    "vault": match.group("vault"),
                    "key": match.group("key"),
                    "handle": f"vault-proxy:{match.group('vault')}:{match.group('key')}",
                }
        return node


# --------------------------------------------------------------------------- #
# Version Manager
# --------------------------------------------------------------------------- #

class VersionManager:
    def __init__(self):
        self._history: dict[str, list[ConfigRecord]] = {}
        self._lock = threading.Lock()

    def bump(self, component_id: str, payload: dict) -> str:
        with self._lock:
            history = self._history.setdefault(component_id, [])
            major, minor, patch = 1, 0, 0
            if history:
                major, minor, patch = map(int, history[-1].version.split("."))
                patch += 1
            version = f"{major}.{minor}.{patch}"
            checksum = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            record = ConfigRecord(component_id, copy.deepcopy(payload), version, checksum, time.time())
            history.append(record)
            return version

    def latest(self, component_id: str) -> Optional[ConfigRecord]:
        history = self._history.get(component_id)
        return history[-1] if history else None

    def rollback(self, component_id: str, steps: int = 1) -> Optional[ConfigRecord]:
        with self._lock:
            history = self._history.get(component_id, [])
            if len(history) <= steps:
                return None
            for _ in range(steps):
                history.pop()
            return history[-1]


# --------------------------------------------------------------------------- #
# Migration Manager
# --------------------------------------------------------------------------- #

MigrationFn = Callable[[dict], dict]


class MigrationManager:
    def __init__(self):
        self._migrations: dict[str, list[tuple[str, MigrationFn]]] = {}

    def register(self, category: str, to_version: str, fn: MigrationFn):
        self._migrations.setdefault(category, []).append((to_version, fn))

    def migrate(self, category: str, payload: dict) -> dict:
        result = copy.deepcopy(payload)
        for _, fn in self._migrations.get(category, []):
            result = fn(result)
        return result


# --------------------------------------------------------------------------- #
# Backup Manager
# --------------------------------------------------------------------------- #

class BackupManager:
    def __init__(self, backup_dir: Path):
        self.backup_dir = backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def create(self, component_id: str, payload: dict, label: str = "auto") -> str:
        with self._lock:
            ts = int(time.time() * 1000)
            filename = f"{component_id}.{label}.{ts}.json"
            path = self.backup_dir / filename
            checksum = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            data = {"component_id": component_id, "payload": payload, "checksum": checksum, "ts": ts}
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return str(path)

    def restore(self, backup_path: str) -> dict:
        path = Path(backup_path)
        if not path.exists():
            raise ConfigError(ConfigStatus.NOT_FOUND, f"backup not found: {backup_path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        expected = data["checksum"]
        actual = hashlib.sha256(json.dumps(data["payload"], sort_keys=True).encode()).hexdigest()
        if expected != actual:
            raise ConfigError(ConfigStatus.INVALID_SCHEMA, "backup checksum mismatch: corrupt archive")
        return data["payload"]


# --------------------------------------------------------------------------- #
# Live Reload Manager (subscriber notification)
# --------------------------------------------------------------------------- #

class LiveReloadManager:
    def __init__(self):
        self._subscribers: dict[str, list[Callable[[str, dict], bool]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, component_id: str, callback: Callable[[str, dict], bool]):
        with self._lock:
            self._subscribers.setdefault(component_id, []).append(callback)

    def dispatch(self, component_id: str, new_payload: dict) -> bool:
        callbacks = self._subscribers.get(component_id, [])
        all_ack = True
        for cb in callbacks:
            try:
                ack = cb(component_id, new_payload)
                all_ack = all_ack and ack
            except Exception:
                all_ack = False
        return all_ack


# --------------------------------------------------------------------------- #
# Cache / Registry / Storage
# --------------------------------------------------------------------------- #

class ConfigCache:
    def __init__(self):
        self._store: dict[str, dict] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            return copy.deepcopy(self._store.get(key))

    def set(self, key: str, value: dict):
        with self._lock:
            self._store[key] = copy.deepcopy(value)

    def invalidate(self, key: str):
        with self._lock:
            self._store.pop(key, None)


class ConfigRegistry:
    def __init__(self):
        self._entries: dict[str, Path] = {}

    def register(self, component_id: str, path: Path):
        self._entries[component_id] = path

    def resolve(self, component_id: str) -> Optional[Path]:
        return self._entries.get(component_id)


class StorageEngine:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, component_id: str) -> Path:
        return self.root / f"{component_id}.json"

    def read(self, component_id: str) -> dict:
        path = self.path_for(component_id)
        if not path.exists():
            raise ConfigError(ConfigStatus.NOT_FOUND, f"no config file for '{component_id}'")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(ConfigStatus.INVALID_SCHEMA, f"malformed JSON: {exc}") from exc

    def write(self, component_id: str, payload: dict):
        path = self.path_for(component_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)


# --------------------------------------------------------------------------- #
# Socket / Pipeline (in-process contract; transport-agnostic)
# --------------------------------------------------------------------------- #

class ConfigSocket:
    """Documented public entry socket. Version: 1"""
    VERSION = 1

    def __init__(self, manager: "ConfigurationManager"):
        self._manager = manager

    def request(self, message_type: str, payload: dict) -> dict:
        handlers = {
            "GET": self._handle_get,
            "SET": self._handle_set,
            "VALIDATE": self._handle_validate,
            "RELOAD": self._handle_reload,
        }
        handler = handlers.get(message_type)
        if handler is None:
            raise ConfigError(ConfigStatus.NOT_FOUND, f"unknown message type: {message_type}")
        return handler(payload)

    def _handle_get(self, payload: dict) -> dict:
        req = ConfigRequest(**payload)
        record = self._manager.get_configuration(req)
        return {"status": ConfigStatus.SUCCESS.value, "payload": record}

    def _handle_set(self, payload: dict) -> dict:
        req = ConfigRequest(component_id=payload["component_id"], category=payload.get("category", "default"))
        status = self._manager.set_configuration(req, payload["payload"])
        return {"status": status.value}

    def _handle_validate(self, payload: dict) -> dict:
        result = self._manager.validate_configuration(payload["category"], payload["payload"])
        return {"is_valid": result.is_valid, "errors": result.errors, "warnings": result.warnings}

    def _handle_reload(self, payload: dict) -> dict:
        ok = self._manager.trigger_live_reload(payload["component_id"])
        return {"acknowledged": ok}


class ConfigPipeline:
    """Ordered processing stages matching the documented Load Flow."""

    def __init__(self, manager: "ConfigurationManager"):
        self._manager = manager

    def run_get(self, request: ConfigRequest) -> dict:
        return self._manager.get_configuration(request)

    def run_set(self, request: ConfigRequest, payload: dict) -> ConfigStatus:
        return self._manager.set_configuration(request, payload)


# --------------------------------------------------------------------------- #
# Configuration Manager (Core)
# --------------------------------------------------------------------------- #

class ConfigurationManager:
    """Single source of truth for Hojaiga configuration. Socket/Pipeline access only."""

    def __init__(self, base_dir: str | Path = "./config_store"):
        base = Path(base_dir)
        self.storage = StorageEngine(base / "store")
        self.registry = ConfigRegistry()
        self.cache = ConfigCache()
        self.schemas = SchemaManager()
        self.validator = ConfigValidator(self.schemas)
        self.env = EnvironmentManager()
        self.secrets = SecretsReferenceManager()
        self.versions = VersionManager()
        self.migrations = MigrationManager()
        self.backups = BackupManager(base / "backups")
        self.reload = LiveReloadManager()
        self.audit = AuditLog(base / "audit" / "config_audit.jsonl")
        self.socket = ConfigSocket(self)
        self.pipeline = ConfigPipeline(self)
        self._defaults: dict[str, dict] = {}

    # ---- schema/defaults registration ---- #

    def register_schema(self, category: str, schema: dict):
        self.schemas.register(category, schema)

    def register_defaults(self, category: str, defaults: dict):
        self._defaults[category] = defaults

    def register_migration(self, category: str, to_version: str, fn: MigrationFn):
        self.migrations.register(category, to_version, fn)

    # ---- core operations ---- #

    def get_configuration(self, request: ConfigRequest) -> dict:
        cache_key = f"{request.component_id}:{request.environment}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.audit.record("GET", request.component_id, "CACHE_HIT")
            return cached

        try:
            raw = self.storage.read(request.component_id)
        except ConfigError:
            raw = self._defaults.get(request.category, {})
            if not raw:
                self.audit.record("GET", request.component_id, "NOT_FOUND")
                raise

        merged = {**self._defaults.get(request.category, {}), **raw}
        result = self.validator.validate(request.category, merged)
        if not result.is_valid:
            self.audit.record("GET", request.component_id, "INVALID", "; ".join(result.errors))
            raise ConfigError(ConfigStatus.INVALID_SCHEMA, "; ".join(result.errors))

        migrated = self.migrations.migrate(request.category, merged)
        with_secrets = self.secrets.resolve(migrated)
        resolved = self.env.apply_overrides(request.component_id, with_secrets)

        self.cache.set(cache_key, resolved)
        self.audit.record("GET", request.component_id, "SUCCESS")
        return resolved

    def set_configuration(self, request: ConfigRequest, payload: dict) -> ConfigStatus:
        result = self.validator.validate(request.category, payload)
        if not result.is_valid:
            self.audit.record("SET", request.component_id, "INVALID", "; ".join(result.errors))
            return ConfigStatus.INVALID_SCHEMA

        try:
            current = self.storage.read(request.component_id)
            self.backups.create(request.component_id, current, label="pre-set")
        except ConfigError:
            pass  # no prior config to snapshot

        version = self.versions.bump(request.component_id, payload)
        self.storage.write(request.component_id, payload)
        self.registry.register(request.component_id, self.storage.path_for(request.component_id))
        self.cache.invalidate(f"{request.component_id}:{request.environment}")

        acked = self.reload.dispatch(request.component_id, payload)
        self.audit.record("SET", request.component_id, "SUCCESS", f"version={version} acked={acked}")
        return ConfigStatus.SUCCESS

    def validate_configuration(self, category: str, payload: dict) -> ValidationResult:
        return self.validator.validate(category, payload)

    def trigger_live_reload(self, component_id: str) -> bool:
        try:
            payload = self.storage.read(component_id)
        except ConfigError:
            return False
        self.cache.invalidate(component_id)
        ok = self.reload.dispatch(component_id, payload)
        self.audit.record("RELOAD", component_id, "SUCCESS" if ok else "PARTIAL")
        return ok

    def rollback_configuration(self, component_id: str, steps: int = 1) -> Optional[ConfigRecord]:
        record = self.versions.rollback(component_id, steps)
        if record is None:
            self.audit.record("ROLLBACK", component_id, "FAILED", "insufficient history")
            return None
        self.storage.write(component_id, record.payload)
        self.cache.invalidate(component_id)
        self.reload.dispatch(component_id, record.payload)
        self.audit.record("ROLLBACK", component_id, "SUCCESS", f"version={record.version}")
        return record

    def create_backup(self, component_id: str, label: str = "manual") -> str:
        payload = self.storage.read(component_id)
        path = self.backups.create(component_id, payload, label)
        self.audit.record("BACKUP", component_id, "SUCCESS", path)
        return path

    def restore_backup(self, component_id: str, backup_path: str) -> ConfigStatus:
        payload = self.backups.restore(backup_path)
        self.storage.write(component_id, payload)
        self.cache.invalidate(component_id)
        self.reload.dispatch(component_id, payload)
        self.audit.record("RESTORE", component_id, "SUCCESS", backup_path)
        return ConfigStatus.SUCCESS

    def subscribe(self, component_id: str, callback: Callable[[str, dict], bool]):
        self.reload.subscribe(component_id, callback)
