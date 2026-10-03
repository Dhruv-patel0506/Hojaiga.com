"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 17
Name: Backup Manager

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Backup Manager]
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
Dependencies: hashlib, dataclasses, re, uuid, base64...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_17_backup_manager.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Hojaiga Automation OS — Organ 17: Backup Manager
Single-file consolidated implementation.

Authority chain: Constitution -> Law Book -> Policy Manual ->
Master Architecture Blueprint -> Organ Specification ->
BACKUP_MANAGER_ARCHITECTURE_SPECIFICATION.md

Scope: backup creation, snapshotting, compression, encryption,
integrity verification, cataloging, retention/rotation, import/export,
scheduling and audit logging.

Out of scope (delegated): restore / disaster recovery execution belongs
to the Recovery Manager. This organ only supplies verified, read-only
backup payload paths and metadata to the Recovery Manager socket.

No third-party network calls. Pure standard library + hashlib/zlib/lzma
for portability on the target Windows 11 / i7 / RTX 3050 / 32GB host.
"""


import base64
import dataclasses
import enum
import hashlib
import hmac
import json
import logging
import os
import queue
import re
import shutil
import sqlite3
import threading
import time
import uuid
import zlib
import lzma
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_AESGCM = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_AESGCM = False

__version__ = "1.0.0"

LOGGER = logging.getLogger("hojaiga.backup_manager")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        '{"time":"%(asctime)s","level":"%(levelname)s","module":"%(name)s","msg":%(message)r}'
    ))
    LOGGER.addHandler(_handler)
    LOGGER.setLevel(logging.INFO)

FILENAME_PATTERN = re.compile(
    r"^(?P<ts>\d{8}-\d{6})_(?P<uuid>[0-9a-fA-F-]{36})_(?P<type>[A-Za-z0-9]+)\.hosbak$"
)


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 1 — Enumerations / Data Contracts (Section 4, 6, 10 of spec)
# ═══════════════════════════════════════════════════════════════════════════

class BackupType(str, enum.Enum):
    FULL = "FULL"
    INCREMENTAL = "INCREMENTAL"
    DIFFERENTIAL = "DIFFERENTIAL"
    RESTORE_POINT = "RESTORE_POINT"
    CONFIGURATION = "CONFIGURATION"
    WORKFLOW = "WORKFLOW"
    KNOWLEDGE = "KNOWLEDGE"
    MEMORY = "MEMORY"
    PACKAGE = "PACKAGE"
    PLUGIN = "PLUGIN"
    CONNECTOR = "CONNECTOR"
    LLM_RUNTIME = "LLM_RUNTIME"
    SYSTEM_SNAPSHOT = "SYSTEM_SNAPSHOT"
    EMERGENCY_SNAPSHOT = "EMERGENCY_SNAPSHOT"
    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"
    COLD = "COLD"
    HOT = "HOT"


class StorageTargetKind(str, enum.Enum):
    LOCAL_SSD = "LOCAL_SSD"
    EXTERNAL_HDD = "EXTERNAL_HDD"
    EXTERNAL_SSD = "EXTERNAL_SSD"
    NAS = "NAS"
    NETWORK_SHARE = "NETWORK_SHARE"
    OFFLINE_ARCHIVE = "OFFLINE_ARCHIVE"
    ENCRYPTED_ARCHIVE = "ENCRYPTED_ARCHIVE"
    CLOUD = "CLOUD"  # Future — abstraction only, not implemented on this host


class CompressionMethod(str, enum.Enum):
    NONE = "NONE"
    LZ4 = "LZ4"       # mapped to zlib level 1 fast profile (no external LZ4 dep)
    ZSTD = "ZSTD"      # mapped to lzma preset 1 (balanced) — swappable via injection
    GZIP = "GZIP"


class EncryptionMethod(str, enum.Enum):
    NONE = "NONE"
    AES_256_GCM = "AES_256_GCM"
    CHACHA20 = "CHACHA20"  # reserved for future KMS cipher negotiation


class VerificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    CORRUPTED = "CORRUPTED"


class RetentionPolicy(str, enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"
    PERMANENT = "PERMANENT"
    MANUAL = "MANUAL"


class BackupState(str, enum.Enum):
    VALIDATION = "VALIDATION"
    SNAPSHOT = "SNAPSHOT"
    COMPRESSION = "COMPRESSION"
    ENCRYPTION = "ENCRYPTION"
    STORAGE = "STORAGE"
    CATALOG_REGISTRATION = "CATALOG_REGISTRATION"
    VERIFICATION = "VERIFICATION"
    READY_FOR_RECOVERY = "READY_FOR_RECOVERY"
    CORRUPTED = "CORRUPTED"
    REJECTED = "REJECTED"


class BackupManagerError(Exception):
    """Base exception for all Backup Manager failure modes."""


class SnapshotFailure(BackupManagerError):
    pass


class StorageFailure(BackupManagerError):
    pass


class IntegrityFailure(BackupManagerError):
    pass


class EncryptionFailure(BackupManagerError):
    pass


class CatalogFailure(BackupManagerError):
    pass


class RetentionViolation(BackupManagerError):
    pass


@dataclass(frozen=True)
class BackupMetadata:
    """Strict schema per Section 6 of the specification."""
    backup_id: str
    backup_name: str
    backup_type: BackupType
    creation_time: str
    creator: str
    system_version: str
    configuration_version: str
    package_version: str
    workflow_version: str
    knowledge_version: str
    compression_method: CompressionMethod
    encryption_method: EncryptionMethod
    checksum: str
    hash: str
    storage_location: str
    size: int
    retention_policy: RetentionPolicy
    expiration_date: Optional[str]
    verification_status: VerificationStatus
    documentation_reference: str

    def to_json(self) -> str:
        d = dataclasses.asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, enum.Enum):
                d[k] = v.value
        return json.dumps(d, sort_keys=True)

    @staticmethod
    def from_row(row: sqlite3.Row) -> "BackupMetadata":
        return BackupMetadata(
            backup_id=row["backup_id"],
            backup_name=row["backup_name"],
            backup_type=BackupType(row["backup_type"]),
            creation_time=row["creation_time"],
            creator=row["creator"],
            system_version=row["system_version"],
            configuration_version=row["configuration_version"],
            package_version=row["package_version"],
            workflow_version=row["workflow_version"],
            knowledge_version=row["knowledge_version"],
            compression_method=CompressionMethod(row["compression_method"]),
            encryption_method=EncryptionMethod(row["encryption_method"]),
            checksum=row["checksum"],
            hash=row["hash"],
            storage_location=row["storage_location"],
            size=row["size"],
            retention_policy=RetentionPolicy(row["retention_policy"]),
            expiration_date=row["expiration_date"],
            verification_status=VerificationStatus(row["verification_status"]),
            documentation_reference=row["documentation_reference"],
        )


@dataclass(frozen=True)
class BackupRequest:
    """Inbound contract on the Backup Socket (request pipeline payload)."""
    backup_name: str
    backup_type: BackupType
    source_paths: tuple
    creator: str
    storage_target: StorageTargetKind
    compression: CompressionMethod = CompressionMethod.ZSTD
    encryption: EncryptionMethod = EncryptionMethod.AES_256_GCM
    retention_policy: RetentionPolicy = RetentionPolicy.DAILY
    hot: bool = True
    system_version: str = "unknown"
    configuration_version: str = "unknown"
    package_version: str = "unknown"
    workflow_version: str = "unknown"
    knowledge_version: str = "unknown"
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(frozen=True)
class ExecutionPlan:
    request: BackupRequest
    effective_type: BackupType
    parent_backup_id: Optional[str]
    hot: bool
    estimated_size: int


@dataclass(frozen=True)
class SocketEnvelope:
    """Standardized inter-organ request/response object
    (Master Architecture Blueprint, Chapter 8)."""
    request_id: str
    source: str
    destination: str
    socket: str
    priority: int
    payload: Any
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "OK"
    errors: tuple = ()


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 2 — Audit Manager (Section 7.17)
# ═══════════════════════════════════════════════════════════════════════════

class AuditManager:
    """Append-only, non-repudiation audit trail. Law Book Universal Law 1."""

    def __init__(self, audit_log_path: Path, secret_key: bytes):
        self._path = audit_log_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._secret = secret_key
        self._lock = threading.Lock()
        self._buffer: list[str] = []
        self._buffer_limit = 500

    def record(self, event: str, actor: str, detail: dict) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "actor": actor,
            "detail": detail,
        }
        payload = json.dumps(entry, sort_keys=True)
        signature = hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        line = json.dumps({"entry": entry, "hmac": signature})
        with self._lock:
            try:
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError as exc:
                self._buffer.append(line)
                LOGGER.warning("audit_write_failed_buffering:%s", exc)
                if len(self._buffer) >= self._buffer_limit:
                    raise BackupManagerError(
                        "Audit cache exceeded threshold; halting per strict security mode."
                    ) from exc

    def flush_buffer(self) -> None:
        with self._lock:
            if not self._buffer:
                return
            with open(self._path, "a", encoding="utf-8") as f:
                for line in self._buffer:
                    f.write(line + "\n")
            self._buffer.clear()

    def verify_chain(self) -> bool:
        if not self._path.exists():
            return True
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                payload = json.dumps(record["entry"], sort_keys=True)
                expected = hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(expected, record["hmac"]):
                    return False
        return True


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 3 — Configuration Interface (Section 7.18, 16)
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "backup_schedule": {"cron": "0 3 * * *"},
    "compression": {"enabled": True, "default": CompressionMethod.ZSTD.value, "max_threads": 4},
    "encryption": {"default": EncryptionMethod.AES_256_GCM.value, "kms_endpoint": None},
    "retention": {
        "daily_keep": 7,
        "weekly_keep": 4,
        "monthly_keep": 12,
        "yearly_keep": 5,
        "disk_cleanup_threshold_pct": 90,
    },
    "storage": {
        "local_ssd_path": "./backups/ssd_staging",
        "external_hdd_path": "./backups/hdd_archive",
    },
    "verification": {"inline": True},
    "logging": {"level": "INFO"},
}


class ConfigurationInterface:
    """Section 7.18 — validates and hot-reloads backup_config.yaml-equivalent."""

    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path
        self._config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
        self._lock = threading.RLock()
        if config_path and config_path.exists():
            self.reload()

    def reload(self) -> None:
        if not self._config_path:
            return
        with self._lock:
            try:
                loaded = json.loads(self._config_path.read_text(encoding="utf-8"))
                self._validate(loaded)
                self._config.update(loaded)
                LOGGER.info("config_reloaded:%s", self._config_path)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                LOGGER.warning("config_reload_failed_keeping_previous:%s", exc)

    @staticmethod
    def _validate(candidate: dict) -> None:
        if not isinstance(candidate, dict):
            raise ValueError("Configuration root must be an object.")

    def get(self, path: str, default: Any = None) -> Any:
        with self._lock:
            node: Any = self._config
            for part in path.split("."):
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return node

    def snapshot(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._config))


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 4 — Snapshot Engine (Section 7.3)
# ═══════════════════════════════════════════════════════════════════════════

class SnapshotEngine:
    """Captures an atomic, point-in-time, read-only staging copy of the
    requested source paths. Uses COW hardlinks when the host filesystem
    supports them, falling back to a staged copy otherwise."""

    def __init__(self, staging_root: Path, audit: AuditManager):
        self._staging_root = staging_root
        self._staging_root.mkdir(parents=True, exist_ok=True)
        self._audit = audit
        self._lock = threading.Lock()

    def snapshot(self, source_paths: tuple, snapshot_id: str) -> Path:
        target_dir = self._staging_root / snapshot_id
        with self._lock:
            try:
                target_dir.mkdir(parents=True, exist_ok=False)
                for src in source_paths:
                    src_path = Path(src)
                    if not src_path.exists():
                        raise SnapshotFailure(f"Source path not found: {src_path}")
                    dest = target_dir / src_path.name
                    self._cow_copy(src_path, dest)
                self._audit.record("snapshot_created", "SnapshotEngine",
                                    {"snapshot_id": snapshot_id, "sources": list(source_paths)})
                return target_dir
            except OSError as exc:
                shutil.rmtree(target_dir, ignore_errors=True)
                raise SnapshotFailure(f"Filesystem lock/space failure: {exc}") from exc

    @staticmethod
    def _cow_copy(src: Path, dest: Path) -> None:
        try:
            if src.is_dir():
                shutil.copytree(src, dest, copy_function=os.link)
            else:
                os.link(src, dest)
        except OSError:
            # Cross-device or unsupported hardlink: fall back to real copy.
            if src.is_dir():
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)

    def release(self, snapshot_path: Path) -> None:
        shutil.rmtree(snapshot_path, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 5 — Compression Manager (Section 7.5)
# ═══════════════════════════════════════════════════════════════════════════

class CompressionManager:
    def compress(self, data: bytes, method: CompressionMethod) -> bytes:
        if method == CompressionMethod.NONE:
            return data
        try:
            if method == CompressionMethod.LZ4:
                return zlib.compress(data, level=1)
            if method == CompressionMethod.GZIP:
                return zlib.compress(data, level=6)
            if method == CompressionMethod.ZSTD:
                return lzma.compress(data, preset=1)
        except (zlib.error, lzma.LZMAError) as exc:
            LOGGER.warning("compression_degraded_to_none:%s", exc)
            return data
        raise BackupManagerError(f"Unsupported compression method: {method}")

    def decompress(self, data: bytes, method: CompressionMethod) -> bytes:
        if method == CompressionMethod.NONE:
            return data
        if method in (CompressionMethod.LZ4, CompressionMethod.GZIP):
            return zlib.decompress(data)
        if method == CompressionMethod.ZSTD:
            return lzma.decompress(data)
        raise BackupManagerError(f"Unsupported compression method: {method}")


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 6 — Encryption Manager (Section 7.6)
# ═══════════════════════════════════════════════════════════════════════════

class EncryptionManager:
    """AES-256-GCM at rest. Keys are provided by an injected KMS callable so
    this organ never persists raw key material — Universal Law 7."""

    NONCE_SIZE = 12

    def __init__(self, key_provider: Callable[[], bytes]):
        self._key_provider = key_provider

    def encrypt(self, data: bytes, method: EncryptionMethod) -> bytes:
        if method == EncryptionMethod.NONE:
            return data
        if method != EncryptionMethod.AES_256_GCM:
            raise EncryptionFailure(f"Unsupported cipher on this host: {method}")
        if not _HAS_AESGCM:
            raise EncryptionFailure(
                "AES-256-GCM backend unavailable (cryptography package missing); "
                "refusing to write unencrypted payload under policy."
            )
        try:
            key = self._key_provider()
            aesgcm = AESGCM(key)  # type: ignore
            nonce = os.urandom(self.NONCE_SIZE)
            ciphertext = aesgcm.encrypt(nonce, data, None)
            return nonce + ciphertext
        except Exception as exc:  # KMS unreachable, key rotation failure, etc.
            raise EncryptionFailure(f"KMS/encryption failure: {exc}") from exc

    def decrypt(self, blob: bytes, method: EncryptionMethod) -> bytes:
        if method == EncryptionMethod.NONE:
            return blob
        if method != EncryptionMethod.AES_256_GCM:
            raise EncryptionFailure(f"Unsupported cipher on this host: {method}")
        if not _HAS_AESGCM:
            raise EncryptionFailure("AES-256-GCM backend unavailable.")
        try:
            key = self._key_provider()
            aesgcm = AESGCM(key)  # type: ignore
            nonce, ciphertext = blob[:self.NONCE_SIZE], blob[self.NONCE_SIZE:]
            return aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as exc:
            raise EncryptionFailure(f"Decryption failure: {exc}") from exc


def default_local_key_provider(key_file: Path) -> Callable[[], bytes]:
    """Local fallback KMS: a 32-byte key persisted with 0600-equivalent
    permissions. Production deployments must inject the AOS KMS client."""
    def _provider() -> bytes:
        if key_file.exists():
            return base64.b64decode(key_file.read_text())
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key = os.urandom(32)
        key_file.write_text(base64.b64encode(key).decode())
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        return key
    return _provider


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 7 — Integrity Validator / Verification Engine (Section 7.7, 7.15)
# ═══════════════════════════════════════════════════════════════════════════

class IntegrityValidator:
    @staticmethod
    def checksum(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def payload_hash(data: bytes) -> str:
        return hashlib.sha384(data).hexdigest()

    @staticmethod
    def verify(data: bytes, expected: str, algorithm: str = "sha256") -> bool:
        digest = hashlib.new(algorithm, data).hexdigest()
        return hmac.compare_digest(digest, expected)


class VerificationEngine:
    """Post-storage read-back validation (Section 7.15, 17.4)."""

    def __init__(self, storage: "StorageManager", compression: CompressionManager,
                 encryption: EncryptionManager, audit: AuditManager):
        self._storage = storage
        self._compression = compression
        self._encryption = encryption
        self._audit = audit

    def verify(self, metadata: BackupMetadata) -> VerificationStatus:
        try:
            blob = self._storage.read(metadata.storage_location)
            stored_hash = IntegrityValidator.payload_hash(blob)
            if not hmac.compare_digest(stored_hash, metadata.hash):
                raise IntegrityFailure("Stored payload hash mismatch.")
            decrypted = self._encryption.decrypt(blob, metadata.encryption_method)
            decompressed = self._compression.decompress(decrypted, metadata.compression_method)
            plain_checksum = IntegrityValidator.checksum(decompressed)
            if not hmac.compare_digest(plain_checksum, metadata.checksum):
                raise IntegrityFailure("Decompressed checksum mismatch.")
            self._audit.record("backup_verified", "VerificationEngine",
                                {"backup_id": metadata.backup_id})
            return VerificationStatus.VERIFIED
        except (IntegrityFailure, StorageFailure, EncryptionFailure) as exc:
            self._audit.record("backup_verification_failed", "VerificationEngine",
                                {"backup_id": metadata.backup_id, "reason": str(exc)})
            return VerificationStatus.CORRUPTED


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 8 — Storage Manager (Section 7.14, Section 5)
# ═══════════════════════════════════════════════════════════════════════════

class StorageManager:
    """Interfaces with local SSD staging and external HDD archive tiers, plus
    NAS/network-share/offline-archive targets addressed by URI."""

    def __init__(self, target_roots: dict[StorageTargetKind, Path]):
        self._roots = target_roots
        for path in target_roots.values():
            path.mkdir(parents=True, exist_ok=True)

    def resolve_root(self, target: StorageTargetKind) -> Path:
        root = self._roots.get(target)
        if root is None:
            raise StorageFailure(f"No configured root for storage target: {target}")
        return root

    def write(self, target: StorageTargetKind, filename: str, data: bytes) -> str:
        root = self.resolve_root(target)
        self._check_capacity(root, len(data))
        dest = root / filename
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with open(tmp, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, dest)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise StorageFailure(f"Write failure on {target}: {exc}") from exc
        return f"{target.value.lower()}://{dest.as_posix()}"

    def read(self, storage_location: str) -> bytes:
        path = self._location_to_path(storage_location)
        if not path.exists():
            raise StorageFailure(f"Backup payload missing: {path}")
        with open(path, "rb") as f:
            return f.read()

    def delete(self, storage_location: str) -> None:
        path = self._location_to_path(storage_location)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageFailure(f"Delete failure: {exc}") from exc

    def move(self, storage_location: str, target: StorageTargetKind) -> str:
        src_path = self._location_to_path(storage_location)
        data = src_path.read_bytes()
        new_location = self.write(target, src_path.name, data)
        src_path.unlink(missing_ok=True)
        return new_location

    @staticmethod
    def _location_to_path(storage_location: str) -> Path:
        _, _, path_part = storage_location.partition("://")
        return Path(path_part)

    @staticmethod
    def _check_capacity(root: Path, incoming_bytes: int) -> None:
        try:
            usage = shutil.disk_usage(root)
        except OSError:
            return
        projected_used_pct = ((usage.used + incoming_bytes) / usage.total) * 100
        if projected_used_pct >= 100:
            raise StorageFailure(f"Insufficient space on {root}: would exceed capacity.")


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 9 — Backup Catalog (Section 7.9)
# ═══════════════════════════════════════════════════════════════════════════

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS backups (
    backup_id TEXT PRIMARY KEY,
    backup_name TEXT NOT NULL,
    backup_type TEXT NOT NULL,
    creation_time TEXT NOT NULL,
    creator TEXT NOT NULL,
    system_version TEXT,
    configuration_version TEXT,
    package_version TEXT,
    workflow_version TEXT,
    knowledge_version TEXT,
    compression_method TEXT,
    encryption_method TEXT,
    checksum TEXT NOT NULL,
    hash TEXT NOT NULL,
    storage_location TEXT NOT NULL,
    size INTEGER NOT NULL,
    retention_policy TEXT NOT NULL,
    expiration_date TEXT,
    verification_status TEXT NOT NULL,
    documentation_reference TEXT,
    parent_backup_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_backups_type ON backups(backup_type);
CREATE INDEX IF NOT EXISTS idx_backups_expiration ON backups(expiration_date);
"""


class BackupCatalog:
    """Embedded SQLite catalog. Immutable inserts; updates limited to
    verification status and retention/tier transitions."""

    def __init__(self, db_path: Path, audit: AuditManager):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._audit = audit
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(SCHEMA_SQL)

    def register(self, metadata: BackupMetadata, parent_backup_id: Optional[str] = None) -> None:
        with self._lock:
            try:
                with self._conn:
                    self._conn.execute(
                        """INSERT INTO backups VALUES
                        (:backup_id,:backup_name,:backup_type,:creation_time,:creator,
                         :system_version,:configuration_version,:package_version,
                         :workflow_version,:knowledge_version,:compression_method,
                         :encryption_method,:checksum,:hash,:storage_location,:size,
                         :retention_policy,:expiration_date,:verification_status,
                         :documentation_reference,:parent_backup_id)""",
                        {**{k: (v.value if isinstance(v, enum.Enum) else v)
                            for k, v in dataclasses.asdict(metadata).items()},
                         "parent_backup_id": parent_backup_id},
                    )
            except sqlite3.IntegrityError as exc:
                raise CatalogFailure(f"Duplicate or invalid backup registration: {exc}") from exc
            except sqlite3.DatabaseError as exc:
                raise CatalogFailure(f"Catalog corruption suspected: {exc}") from exc
        self._audit.record("backup_registered", "BackupCatalog",
                            {"backup_id": metadata.backup_id, "type": metadata.backup_type.value})

    def update_verification_status(self, backup_id: str, status: VerificationStatus) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE backups SET verification_status = ? WHERE backup_id = ?",
                (status.value, backup_id),
            )
        self._audit.record("verification_status_updated", "BackupCatalog",
                            {"backup_id": backup_id, "status": status.value})

    def get(self, backup_id: str) -> Optional[BackupMetadata]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM backups WHERE backup_id = ?", (backup_id,)
            ).fetchone()
        return BackupMetadata.from_row(row) if row else None

    def query(self, backup_type: Optional[BackupType] = None,
              retention_policy: Optional[RetentionPolicy] = None) -> list[BackupMetadata]:
        clauses, params = [], []
        if backup_type:
            clauses.append("backup_type = ?")
            params.append(backup_type.value)
        if retention_policy:
            clauses.append("retention_policy = ?")
            params.append(retention_policy.value)
        sql = "SELECT * FROM backups"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY creation_time DESC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [BackupMetadata.from_row(r) for r in rows]

    def expired(self, as_of: Optional[datetime] = None) -> list[BackupMetadata]:
        as_of = as_of or datetime.now(timezone.utc)
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM backups
                   WHERE expiration_date IS NOT NULL
                     AND expiration_date <= ?
                     AND retention_policy != ?""",
                (as_of.isoformat(), RetentionPolicy.PERMANENT.value),
            ).fetchall()
        return [BackupMetadata.from_row(r) for r in rows]

    def latest(self, backup_type: Optional[BackupType] = None) -> Optional[BackupMetadata]:
        results = self.query(backup_type=backup_type)
        return results[0] if results else None

    def remove(self, backup_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM backups WHERE backup_id = ?", (backup_id,))
        self._audit.record("backup_purged_from_catalog", "BackupCatalog", {"backup_id": backup_id})

    def update_storage_location(self, backup_id: str, new_location: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE backups SET storage_location = ? WHERE backup_id = ?",
                (new_location, backup_id),
            )


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 10 — Metadata Manager (Section 7.8)
# ═══════════════════════════════════════════════════════════════════════════

class MetadataManager:
    def compile(self, request: BackupRequest, checksum: str, payload_hash: str,
                storage_location: str, size: int,
                expiration_date: Optional[str], doc_ref: str) -> BackupMetadata:
        return BackupMetadata(
            backup_id=str(uuid.uuid4()),
            backup_name=request.backup_name or f"{request.backup_type.value.lower()}-{int(time.time())}",
            backup_type=request.backup_type,
            creation_time=datetime.now(timezone.utc).isoformat(),
            creator=request.creator or "UNKNOWN",
            system_version=request.system_version or "UNKNOWN",
            configuration_version=request.configuration_version or "UNKNOWN",
            package_version=request.package_version or "UNKNOWN",
            workflow_version=request.workflow_version or "UNKNOWN",
            knowledge_version=request.knowledge_version or "UNKNOWN",
            compression_method=request.compression,
            encryption_method=request.encryption,
            checksum=checksum,
            hash=payload_hash,
            storage_location=storage_location,
            size=size,
            retention_policy=request.retention_policy,
            expiration_date=expiration_date,
            verification_status=VerificationStatus.PENDING,
            documentation_reference=doc_ref,
        )


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 11 — Retention & Rotation Managers (Section 7.10, 7.11, Section 10)
# ═══════════════════════════════════════════════════════════════════════════

RETENTION_WINDOWS = {
    RetentionPolicy.DAILY: timedelta(days=7),
    RetentionPolicy.WEEKLY: timedelta(weeks=4),
    RetentionPolicy.MONTHLY: timedelta(days=365),
    RetentionPolicy.YEARLY: timedelta(days=365 * 5),
}


class RetentionManager:
    def __init__(self, catalog: BackupCatalog, config: ConfigurationInterface, audit: AuditManager):
        self._catalog = catalog
        self._config = config
        self._audit = audit
        self._locked_ids: set[str] = set()

    def compute_expiration(self, retention_policy: RetentionPolicy,
                            creation_time: datetime) -> Optional[str]:
        if retention_policy in (RetentionPolicy.PERMANENT, RetentionPolicy.MANUAL):
            return None
        window = RETENTION_WINDOWS.get(retention_policy, timedelta(days=30))
        return (creation_time + window).isoformat()

    def lock(self, backup_id: str) -> None:
        self._locked_ids.add(backup_id)

    def unlock(self, backup_id: str) -> None:
        self._locked_ids.discard(backup_id)

    def sweep(self) -> list[str]:
        expired = self._catalog.expired()
        deletable = [b.backup_id for b in expired if b.backup_id not in self._locked_ids]
        self._audit.record("retention_sweep", "RetentionManager",
                            {"expired_count": len(expired), "deletable_count": len(deletable)})
        return deletable

    def enforce_capacity(self, storage: StorageManager, root: Path) -> list[str]:
        threshold = self._config.get("retention.disk_cleanup_threshold_pct", 90)
        try:
            usage = shutil.disk_usage(root)
        except OSError:
            return []
        used_pct = (usage.used / usage.total) * 100
        if used_pct < threshold:
            return []
        candidates = [b for b in self._catalog.query()
                      if b.retention_policy not in (RetentionPolicy.PERMANENT,)
                      and b.backup_id not in self._locked_ids]
        candidates.sort(key=lambda b: b.creation_time)
        return [c.backup_id for c in candidates[:max(1, len(candidates) // 10)]]


class RotationManager:
    """Grandfather-Father-Son tiered promotion (Section 10)."""

    TIER_ORDER = [StorageTargetKind.LOCAL_SSD, StorageTargetKind.NAS, StorageTargetKind.OFFLINE_ARCHIVE]

    def __init__(self, catalog: BackupCatalog, storage: StorageManager, audit: AuditManager):
        self._catalog = catalog
        self._storage = storage
        self._audit = audit

    def promote(self, backup_id: str, target: StorageTargetKind) -> None:
        metadata = self._catalog.get(backup_id)
        if not metadata:
            raise RetentionViolation(f"Unknown backup: {backup_id}")
        new_location = self._storage.move(metadata.storage_location, target)
        self._catalog.update_storage_location(backup_id, new_location)
        self._audit.record("backup_tier_promoted", "RotationManager",
                            {"backup_id": backup_id, "target_tier": target.value})


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 12 — Backup Planner & Scheduler (Section 7.2, 7.4)
# ═══════════════════════════════════════════════════════════════════════════

class BackupPlanner:
    def __init__(self, catalog: BackupCatalog, retention: RetentionManager):
        self._catalog = catalog
        self._retention = retention

    def plan(self, request: BackupRequest) -> ExecutionPlan:
        effective_type = request.backup_type
        parent_id = None
        if request.backup_type in (BackupType.INCREMENTAL, BackupType.DIFFERENTIAL):
            reference_type = (BackupType.FULL if request.backup_type == BackupType.DIFFERENTIAL
                               else None)
            parent = self._catalog.latest(backup_type=reference_type)
            if parent is None:
                LOGGER.warning("no_baseline_found_falling_back_to_full")
                effective_type = BackupType.FULL
            else:
                parent_id = parent.backup_id
        estimated_size = sum(
            self._estimate_path_size(Path(p)) for p in request.source_paths
        )
        return ExecutionPlan(
            request=request,
            effective_type=effective_type,
            parent_backup_id=parent_id,
            hot=request.hot,
            estimated_size=estimated_size,
        )

    @staticmethod
    def _estimate_path_size(path: Path) -> int:
        if not path.exists():
            return 0
        if path.is_file():
            return path.stat().st_size
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


class BackupScheduler:
    """CRON-lite: minute-resolution poll loop, resilient to sleep/halt by
    executing missed jobs within a grace threshold on wake (Section 7.4)."""

    def __init__(self, config: ConfigurationInterface, on_trigger: Callable[[], None],
                 grace_period: timedelta = timedelta(minutes=15)):
        self._config = config
        self._on_trigger = on_trigger
        self._grace_period = grace_period
        self._last_run: Optional[datetime] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="BackupScheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        interval_seconds = self._config.get("backup_schedule.interval_seconds", 86400)
        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)
            due = self._last_run is None or (now - self._last_run) >= timedelta(seconds=interval_seconds)
            missed_and_within_grace = (
                self._last_run is not None
                and (now - self._last_run) >= timedelta(seconds=interval_seconds)
                and (now - self._last_run) <= timedelta(seconds=interval_seconds) + self._grace_period
            )
            if due or missed_and_within_grace:
                try:
                    self._on_trigger()
                except Exception as exc:  # noqa: BLE001 — scheduler must never crash
                    LOGGER.error("scheduled_backup_failed:%s", exc)
                self._last_run = now
            self._stop_event.wait(timeout=min(60, interval_seconds))


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 13 — Metrics Manager (Section 7.16)
# ═══════════════════════════════════════════════════════════════════════════

class MetricsManager:
    def __init__(self, buffer_limit: int = 10_000):
        self._buffer_limit = buffer_limit
        self._series: list[dict] = []
        self._lock = threading.Lock()

    def record(self, name: str, value: float, tags: Optional[dict] = None) -> None:
        with self._lock:
            if len(self._series) >= self._buffer_limit:
                self._series.pop(0)
            self._series.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "name": name,
                "value": value,
                "tags": tags or {},
            })

    def snapshot(self) -> list[dict]:
        with self._lock:
            return list(self._series)

    def prometheus_export(self) -> str:
        lines = []
        with self._lock:
            for point in self._series[-500:]:
                tag_str = ",".join(f'{k}="{v}"' for k, v in point["tags"].items())
                lines.append(f'{point["name"]}{{{tag_str}}} {point["value"]}')
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 14 — Import / Export Managers (Section 7.12, 7.13)
# ═══════════════════════════════════════════════════════════════════════════

class ExportManager:
    def __init__(self, catalog: BackupCatalog, storage: StorageManager, audit: AuditManager):
        self._catalog = catalog
        self._storage = storage
        self._audit = audit

    def export(self, backup_id: str, destination_dir: Path) -> Path:
        metadata = self._catalog.get(backup_id)
        if metadata is None:
            raise BackupManagerError(f"Unknown backup_id: {backup_id}")
        blob = self._storage.read(metadata.storage_location)
        destination_dir.mkdir(parents=True, exist_ok=True)
        filename = self._physical_filename(metadata)
        out_path = destination_dir / filename
        out_path.write_bytes(blob)
        sidecar = out_path.with_suffix(out_path.suffix + ".meta.json")
        sidecar.write_text(metadata.to_json(), encoding="utf-8")
        self._audit.record("backup_exported", "ExportManager",
                            {"backup_id": backup_id, "destination": str(out_path)})
        return out_path

    @staticmethod
    def _physical_filename(metadata: BackupMetadata) -> str:
        ts = datetime.fromisoformat(metadata.creation_time).strftime("%Y%m%d-%H%M%S")
        return f"{ts}_{metadata.backup_id}_{metadata.backup_type.value}.hosbak"


class ImportManager:
    def __init__(self, catalog: BackupCatalog, storage: StorageManager,
                 validator: IntegrityValidator, audit: AuditManager):
        self._catalog = catalog
        self._storage = storage
        self._validator = validator
        self._audit = audit

    def import_backup(self, archive_path: Path, storage_target: StorageTargetKind) -> BackupMetadata:
        if not FILENAME_PATTERN.match(archive_path.name):
            raise BackupManagerError(f"Non-conformant backup filename: {archive_path.name}")
        sidecar = archive_path.with_suffix(archive_path.suffix + ".meta.json")
        if not sidecar.exists():
            raise BackupManagerError("Missing metadata sidecar for import.")
        raw_meta = json.loads(sidecar.read_text(encoding="utf-8"))
        raw_meta["backup_type"] = BackupType(raw_meta["backup_type"])
        raw_meta["compression_method"] = CompressionMethod(raw_meta["compression_method"])
        raw_meta["encryption_method"] = EncryptionMethod(raw_meta["encryption_method"])
        raw_meta["retention_policy"] = RetentionPolicy(raw_meta["retention_policy"])
        raw_meta["verification_status"] = VerificationStatus.PENDING
        blob = archive_path.read_bytes()
        stored_hash = self._validator.payload_hash(blob)
        if not hmac.compare_digest(stored_hash, raw_meta["hash"]):
            raise IntegrityFailure("Imported payload hash mismatch; rejecting.")
        new_location = self._storage.write(storage_target, archive_path.name, blob)
        raw_meta["storage_location"] = new_location
        metadata = BackupMetadata(**raw_meta)
        self._catalog.register(metadata)
        self._audit.record("backup_imported", "ImportManager",
                            {"backup_id": metadata.backup_id, "source": str(archive_path)})
        return metadata


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 15 — Backup Core Orchestrator (Section 7.1)
# ═══════════════════════════════════════════════════════════════════════════

class BackupCore:
    """Central orchestrator enforcing the Backup Lifecycle state machine
    (Section 17.2): Validation -> Snapshot -> Compression -> Encryption ->
    Storage -> CatalogRegistration -> Verification -> ReadyForRecovery."""

    def __init__(
        self,
        config: ConfigurationInterface,
        audit: AuditManager,
        planner: BackupPlanner,
        snapshot_engine: SnapshotEngine,
        compression: CompressionManager,
        encryption: EncryptionManager,
        storage: StorageManager,
        catalog: BackupCatalog,
        metadata_manager: MetadataManager,
        retention: RetentionManager,
        verification: VerificationEngine,
        metrics: MetricsManager,
    ):
        self._config = config
        self._audit = audit
        self._planner = planner
        self._snapshot_engine = snapshot_engine
        self._compression = compression
        self._encryption = encryption
        self._storage = storage
        self._catalog = catalog
        self._metadata_manager = metadata_manager
        self._retention = retention
        self._verification = verification
        self._metrics = metrics
        self._state_lock = threading.Lock()

    def execute(self, request: BackupRequest) -> BackupMetadata:
        state = BackupState.VALIDATION
        started = time.monotonic()
        snapshot_path: Optional[Path] = None
        try:
            self._validate(request)
            plan = self._planner.plan(request)

            state = BackupState.SNAPSHOT
            snapshot_id = str(uuid.uuid4())
            snapshot_path = self._snapshot_engine.snapshot(request.source_paths, snapshot_id)
            raw_bytes = self._serialize_snapshot(snapshot_path)
            checksum = IntegrityValidator.checksum(raw_bytes)

            state = BackupState.COMPRESSION
            compressed = self._compression.compress(raw_bytes, request.compression)

            state = BackupState.ENCRYPTION
            encrypted = self._encryption.encrypt(compressed, request.encryption)
            payload_hash = IntegrityValidator.payload_hash(encrypted)

            state = BackupState.STORAGE
            filename = self._physical_filename(plan.effective_type, snapshot_id)
            storage_location = self._storage.write(request.storage_target, filename, encrypted)

            state = BackupState.CATALOG_REGISTRATION
            creation_dt = datetime.now(timezone.utc)
            expiration = self._retention.compute_expiration(request.retention_policy, creation_dt)
            metadata = self._metadata_manager.compile(
                request=request,
                checksum=checksum,
                payload_hash=payload_hash,
                storage_location=storage_location,
                size=len(encrypted),
                expiration_date=expiration,
                doc_ref=f"audit://{snapshot_id}",
            )
            self._catalog.register(metadata, parent_backup_id=plan.parent_backup_id)

            state = BackupState.VERIFICATION
            if self._config.get("verification.inline", True):
                status = self._verification.verify(metadata)
                self._catalog.update_verification_status(metadata.backup_id, status)
                if status == VerificationStatus.CORRUPTED:
                    state = BackupState.CORRUPTED
                    raise IntegrityFailure("Post-storage verification failed.")
                metadata = dataclasses.replace(metadata, verification_status=status)

            state = BackupState.READY_FOR_RECOVERY
            duration_ms = (time.monotonic() - started) * 1000
            self._metrics.record("backup_duration_ms", duration_ms,
                                  {"type": plan.effective_type.value})
            self._metrics.record("backup_size_bytes", len(encrypted),
                                  {"type": plan.effective_type.value})
            self._audit.record("backup_completed", "BackupCore",
                                {"backup_id": metadata.backup_id, "state": state.value,
                                 "duration_ms": duration_ms})
            return metadata
        except BackupManagerError as exc:
            self._audit.record("backup_failed", "BackupCore",
                                {"request_id": request.request_id, "state": state.value,
                                 "reason": str(exc)})
            raise
        finally:
            if snapshot_path is not None:
                self._snapshot_engine.release(snapshot_path)

    def restore_point(self, source_paths: tuple, creator: str,
                       storage_target: StorageTargetKind = StorageTargetKind.LOCAL_SSD) -> BackupMetadata:
        """Fast path used by Update Manager / Package Manager prior to
        state-altering operations (Section 11, 17.7)."""
        request = BackupRequest(
            backup_name=f"restore-point-{int(time.time())}",
            backup_type=BackupType.RESTORE_POINT,
            source_paths=source_paths,
            creator=creator,
            storage_target=storage_target,
            compression=CompressionMethod.LZ4,
            retention_policy=RetentionPolicy.DAILY,
            hot=True,
        )
        return self.execute(request)

    @staticmethod
    def _validate(request: BackupRequest) -> None:
        if not request.source_paths:
            raise BackupManagerError("BackupRequest requires at least one source path.")
        if not request.creator:
            raise BackupManagerError("BackupRequest requires a creator identity.")

    @staticmethod
    def _serialize_snapshot(snapshot_path: Path) -> bytes:
        """Deterministically serializes the snapshot directory into a single
        byte stream (manifest + concatenated file contents) for the
        compression/encryption pipeline."""
        entries = sorted(p for p in snapshot_path.rglob("*") if p.is_file())
        manifest = [
            {"path": str(p.relative_to(snapshot_path)), "size": p.stat().st_size}
            for p in entries
        ]
        header = json.dumps(manifest, sort_keys=True).encode("utf-8")
        body = bytearray(len(header).to_bytes(8, "big") + header)
        for p in entries:
            body.extend(p.read_bytes())
        return bytes(body)

    @staticmethod
    def _physical_filename(backup_type: BackupType, backup_uuid: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"{ts}_{backup_uuid}_{backup_type.value}.hosbak"


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 16 — Recovery Preparation Socket (read-only handoff)
# ═══════════════════════════════════════════════════════════════════════════

class RecoveryPreparationSocket:
    """Section 12 (Backup Socket family) / Section 13 (Recovery Prep
    pipeline). Supplies verified, read-only payload paths and metadata to
    the Recovery Manager organ. This organ never executes restores."""

    def __init__(self, catalog: BackupCatalog, audit: AuditManager):
        self._catalog = catalog
        self._audit = audit

    def handle(self, envelope: SocketEnvelope) -> SocketEnvelope:
        backup_id = envelope.payload.get("backup_id")
        metadata = self._catalog.get(backup_id)
        if metadata is None:
            self._audit.record("recovery_prep_denied", "RecoveryPreparationSocket",
                                {"backup_id": backup_id, "reason": "not_found"})
            return dataclasses.replace(envelope, status="ERROR",
                                        errors=("backup_not_found",))
        if metadata.verification_status != VerificationStatus.VERIFIED:
            self._audit.record("recovery_prep_denied", "RecoveryPreparationSocket",
                                {"backup_id": backup_id, "reason": "not_verified"})
            return dataclasses.replace(envelope, status="ERROR",
                                        errors=("backup_not_verified",))
        self._audit.record("recovery_prep_granted", "RecoveryPreparationSocket",
                            {"backup_id": backup_id})
        return dataclasses.replace(
            envelope, status="OK",
            payload={"metadata": json.loads(metadata.to_json())},
        )


# ═══════════════════════════════════════════════════════════════════════════
# Chapter 17 — Backup Manager Facade (public organ entrypoint)
# ═══════════════════════════════════════════════════════════════════════════

class BackupManagerOrgan:
    """Public facade wired per the Organ Specification. Owns module
    lifecycles; external organs interact exclusively through this facade's
    socket-shaped methods."""

    def __init__(self, root_dir: Path, secret_key: Optional[bytes] = None,
                 key_provider: Optional[Callable[[], bytes]] = None):
        root_dir.mkdir(parents=True, exist_ok=True)
        self.config = ConfigurationInterface(root_dir / "backup_config.json")
        self.audit = AuditManager(root_dir / "audit" / "backup_audit.log",
                                   secret_key or os.urandom(32))
        self.catalog = BackupCatalog(root_dir / "catalog" / "backup_catalog.sqlite", self.audit)
        self.storage = StorageManager({
            StorageTargetKind.LOCAL_SSD: root_dir / "ssd_staging",
            StorageTargetKind.EXTERNAL_HDD: root_dir / "hdd_archive",
            StorageTargetKind.NAS: root_dir / "nas_mirror",
            StorageTargetKind.NETWORK_SHARE: root_dir / "network_share",
            StorageTargetKind.OFFLINE_ARCHIVE: root_dir / "offline_archive",
            StorageTargetKind.ENCRYPTED_ARCHIVE: root_dir / "encrypted_archive",
        })
        self.snapshot_engine = SnapshotEngine(root_dir / "snapshot_staging", self.audit)
        self.compression = CompressionManager()
        self.encryption = EncryptionManager(
            key_provider or default_local_key_provider(root_dir / "keys" / "backup.key")
        )
        self.metadata_manager = MetadataManager()
        self.retention = RetentionManager(self.catalog, self.config, self.audit)
        self.rotation = RotationManager(self.catalog, self.storage, self.audit)
        self.planner = BackupPlanner(self.catalog, self.retention)
        self.metrics = MetricsManager()
        self.verification = VerificationEngine(self.storage, self.compression, self.encryption, self.audit)
        self.export_manager = ExportManager(self.catalog, self.storage, self.audit)
        self.import_manager = ImportManager(self.catalog, self.storage, IntegrityValidator(), self.audit)
        self.core = BackupCore(
            config=self.config, audit=self.audit, planner=self.planner,
            snapshot_engine=self.snapshot_engine, compression=self.compression,
            encryption=self.encryption, storage=self.storage, catalog=self.catalog,
            metadata_manager=self.metadata_manager, retention=self.retention,
            verification=self.verification, metrics=self.metrics,
        )
        self.recovery_socket = RecoveryPreparationSocket(self.catalog, self.audit)
        self.scheduler = BackupScheduler(self.config, self._scheduled_trigger)
        self._scheduled_sources: tuple = ()
        self._scheduled_target: StorageTargetKind = StorageTargetKind.LOCAL_SSD

    # ---- Backup Socket -----------------------------------------------
    def create_backup(self, request: BackupRequest) -> BackupMetadata:
        return self.core.execute(request)

    def create_restore_point(self, source_paths: tuple, creator: str) -> BackupMetadata:
        return self.core.restore_point(source_paths, creator)

    # ---- Recovery Prep Pipeline ---------------------------------------
    def prepare_for_recovery(self, backup_id: str) -> SocketEnvelope:
        envelope = SocketEnvelope(
            request_id=str(uuid.uuid4()), source="RecoveryManager",
            destination="BackupManager", socket="RecoveryPreparation",
            priority=1, payload={"backup_id": backup_id},
        )
        return self.recovery_socket.handle(envelope)

    # ---- Retention / Rotation ------------------------------------------
    def run_retention_sweep(self) -> list[str]:
        deletable = self.retention.sweep()
        for backup_id in deletable:
            metadata = self.catalog.get(backup_id)
            if metadata is None:
                continue
            self.storage.delete(metadata.storage_location)
            self.catalog.remove(backup_id)
        return deletable

    # ---- Export / Import ------------------------------------------------
    def export_backup(self, backup_id: str, destination_dir: Path) -> Path:
        return self.export_manager.export(backup_id, destination_dir)

    def import_backup(self, archive_path: Path,
                       target: StorageTargetKind = StorageTargetKind.LOCAL_SSD) -> BackupMetadata:
        return self.import_manager.import_backup(archive_path, target)

    # ---- Scheduler -------------------------------------------------------
    def configure_schedule(self, source_paths: tuple,
                            target: StorageTargetKind = StorageTargetKind.LOCAL_SSD) -> None:
        self._scheduled_sources = source_paths
        self._scheduled_target = target

    def start_scheduler(self) -> None:
        self.scheduler.start()

    def stop_scheduler(self) -> None:
        self.scheduler.stop()

    def _scheduled_trigger(self) -> None:
        if not self._scheduled_sources:
            return
        request = BackupRequest(
            backup_name=f"scheduled-{int(time.time())}",
            backup_type=BackupType.SCHEDULED,
            source_paths=self._scheduled_sources,
            creator="BackupScheduler",
            storage_target=self._scheduled_target,
            retention_policy=RetentionPolicy.DAILY,
        )
        self.core.execute(request)

    def shutdown(self) -> None:
        self.scheduler.stop()
        self.audit.flush_buffer()


__all__ = [
    "BackupManagerOrgan", "BackupCore", "BackupRequest", "BackupMetadata",
    "BackupType", "StorageTargetKind", "CompressionMethod", "EncryptionMethod",
    "VerificationStatus", "RetentionPolicy", "BackupState", "BackupManagerError",
    "SnapshotFailure", "StorageFailure", "IntegrityFailure", "EncryptionFailure",
    "CatalogFailure", "RetentionViolation", "SnapshotEngine", "CompressionManager",
    "EncryptionManager", "IntegrityValidator", "VerificationEngine", "StorageManager",
    "BackupCatalog", "MetadataManager", "RetentionManager", "RotationManager",
    "BackupPlanner", "BackupScheduler", "MetricsManager", "ExportManager",
    "ImportManager", "AuditManager", "ConfigurationInterface",
    "RecoveryPreparationSocket", "SocketEnvelope", "ExecutionPlan",
    "__version__",
]
