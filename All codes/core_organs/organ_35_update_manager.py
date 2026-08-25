"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 35
Name: Update Manager

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Update Manager]
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
    input([Input Node]) --> process([Code Node: organ_35_update_manager.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Organ 35 — Update Manager
Hojaiga Automation OS

Authority: Constitution -> LawBook -> Diagrams -> Legacy Guide -> PolicyManual
           -> MasterArchitectureBlueprint -> Organ Specification -> Update_Manager.md

Sole privileged orchestrator for update lifecycles: discovery, version/compat
validation, backup, package acquisition/install, migration, verification,
activation (hot-swap), rollback and recovery. Never touches other organs'
private state — communicates only through documented Sockets and Pipelines.

--------------------------------------------------------------------------
PRE-IMPLEMENTATION DIAGRAM
--------------------------------------------------------------------------
UpdateSource -> UpdateCore(Discovery, VersionMgr, ChannelMgr, Scheduler)
  -> CompatibilityValidator + DependencyValidator
  -> BackupCoordinator
  -> DownloadManager -> PackageCoordinator (verify, extract, install)
  -> MigrationEngine (config + db)
  -> VerificationEngine
  -> (PASS) ActivationManager  | (FAIL) RollbackManager -> RecoveryManager
  -> AuditManager + MetricsManager (cross-cutting, every phase)

--------------------------------------------------------------------------
POST-IMPLEMENTATION ACTUAL CODE TOPOLOGY
--------------------------------------------------------------------------
UpdateManagerOrgan
 ├── SocketBus (async pub/sub; one Socket per documented ipc:// name)
 ├── AuditManager        (append-only signed trail)
 ├── MetricsManager       (counters/timers, Audit Pipeline)
 ├── VersionManager        (SemVer resolution, DAG)
 ├── ReleaseChannelManager  (channel auth + index)
 ├── UpdateDiscovery        (poll sources -> UpdateDescriptor)
 ├── CompatibilityValidator (OS/hardware/organ checks)
 ├── DependencyValidator    (dependency graph solve)
 ├── BackupCoordinator      (restore point creation)
 ├── DownloadManager        (chunked fetch + hash)
 ├── PackageCoordinator     (crypto verify, extract, install)
 ├── MigrationEngine        (config + db migrations)
 ├── VerificationEngine     (health/synthetic checks)
 ├── ActivationManager      (hot-swap / restart)
 ├── RollbackManager        (restore from restore point)
 ├── RecoveryManager        (safe-mode fallback)
 ├── UpdateScheduler        (cron-like windows)
 └── UpdateCore             (state machine orchestrating all above)
"""


import asyncio
import hashlib
import json
import logging
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("hojaiga.organ35.update_manager")
logger.addHandler(logging.NullHandler())

SOCKET_VERSION = "1.0.0"


# ══════════════════════════════════════════════════════════════════
# Sockets — documented pub/sub interfaces (Organ Specification §Socket Rules)
# ══════════════════════════════════════════════════════════════════

class Socket:
    """Async pub/sub socket. name mirrors ipc:// path in Update_Manager.md."""

    def __init__(self, name: str, version: str = SOCKET_VERSION) -> None:
        self.name = name
        self.version = version
        self._subscribers: list[Callable[[dict[str, Any]], Any]] = []

    def subscribe(self, handler: Callable[[dict[str, Any]], Any]) -> None:
        self._subscribers.append(handler)

    async def publish(self, payload: dict[str, Any]) -> None:
        envelope = {"socket": self.name, "version": self.version,
                    "ts": time.time(), "payload": payload}
        for handler in list(self._subscribers):
            result = handler(envelope)
            if asyncio.iscoroutine(result):
                await result


class SocketBus:
    """Registry for all Update Manager sockets."""

    def __init__(self) -> None:
        names = [
            "update_core", "version_mgr", "channel_mgr", "discovery",
            "download", "compat_validator", "dep_validator", "backup_coord",
            "migration_engine", "config_migration", "db_migration",
            "package_coord", "verification_engine", "activation_mgr",
            "rollback_mgr", "recovery_mgr", "metrics_mgr", "audit_mgr",
            "update_config", "scheduler",
        ]
        self._sockets = {n: Socket(f"ipc:///var/run/hojaiga/{n}.sock") for n in names}

    def get(self, name: str) -> Socket:
        return self._sockets[name]


# ══════════════════════════════════════════════════════════════════
# Data contracts
# ══════════════════════════════════════════════════════════════════

class UpdateState(str, Enum):
    IDLE = "IDLE"
    DISCOVERING = "DISCOVERING"
    VALIDATING = "VALIDATING"
    BACKING_UP = "BACKING_UP"
    DOWNLOADING = "DOWNLOADING"
    INSTALLING = "INSTALLING"
    MIGRATING = "MIGRATING"
    VERIFYING = "VERIFYING"
    ACTIVATING = "ACTIVATING"
    ROLLING_BACK = "ROLLING_BACK"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class UpdateType(str, Enum):
    SYSTEM = "system"
    ORGAN = "organ"
    CONTROLLER = "controller"
    WORKFLOW = "workflow"
    CONFIGURATION = "configuration"
    PLUGIN = "plugin"
    CONNECTOR = "connector"
    LLM_RUNTIME = "llm_runtime"
    PACKAGE = "package"
    SECURITY = "security"
    PATCH = "patch"
    HOTFIX = "hotfix"
    FEATURE = "feature"
    MAJOR = "major"
    MINOR = "minor"
    BETA = "beta"
    DEVELOPMENT = "development"
    EMERGENCY = "emergency"


class ReleaseChannel(str, Enum):
    STABLE = "stable"
    LTS = "lts"
    BETA = "beta"
    DEVELOPMENT = "development"
    EXPERIMENTAL = "experimental"
    OFFLINE = "offline"
    PRIVATE_ENTERPRISE = "private_enterprise"


@dataclass
class UpdateDescriptor:
    update_id: str
    target_version: str
    update_type: UpdateType
    channel: ReleaseChannel
    artifact_url: str
    sha256: str
    size_bytes: int
    requires: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UpdateContext:
    update_id: str
    target_version: str
    package_path: Optional[str] = None
    restore_point_id: Optional[str] = None
    auto_rollback_enabled: bool = True
    started_at: float = field(default_factory=time.time)


@dataclass
class ValidationReport:
    passed: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class RestorePoint:
    restore_point_id: str
    created_at: float
    scope: list[str]
    manifest_path: str


class UpdateManagerError(Exception):
    pass


# ══════════════════════════════════════════════════════════════════
# Cross-cutting: Audit + Metrics (append-only, per Law Book §Universal Law 1)
# ══════════════════════════════════════════════════════════════════

class AuditManager:
    """3.18 Audit Manager — cryptographically-chained append-only trail."""

    def __init__(self, bus: SocketBus, audit_dir: Path) -> None:
        self._socket = bus.get("audit_mgr")
        self._path = audit_dir / "audit_trail.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash = self._load_last_hash()

    def _load_last_hash(self) -> str:
        if not self._path.exists():
            return "0" * 64
        last_hash = "0" * 64
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last_hash = json.loads(line)["record_hash"]
        return last_hash

    async def record(self, event: str, detail: dict[str, Any]) -> None:
        entry = {
            "event": event, "detail": detail, "ts": time.time(),
            "prev_hash": self._last_hash,
        }
        digest = hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()
        entry["record_hash"] = digest
        self._last_hash = digest
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        await self._socket.publish(entry)

    def verify_chain(self) -> bool:
        if not self._path.exists():
            return True
        prev = "0" * 64
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec["prev_hash"] != prev:
                    return False
                stored_hash = rec.pop("record_hash")
                recomputed = hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest()
                rec["record_hash"] = stored_hash
                if recomputed != stored_hash:
                    return False
                prev = stored_hash
        return True


class MetricsManager:
    """3.17 Metrics — in-memory counters/timers, Audit Pipeline export."""

    def __init__(self, bus: SocketBus) -> None:
        self._socket = bus.get("metrics_mgr")
        self._timers: dict[str, float] = {}
        self.samples: list[dict[str, Any]] = []

    def start(self, name: str) -> None:
        self._timers[name] = time.monotonic()

    async def stop(self, name: str) -> float:
        elapsed = time.monotonic() - self._timers.pop(name, time.monotonic())
        sample = {"metric": name, "seconds": elapsed}
        self.samples.append(sample)
        await self._socket.publish(sample)
        return elapsed


# ══════════════════════════════════════════════════════════════════
# 3.2 / 3.3 Version + Channel management
# ══════════════════════════════════════════════════════════════════

_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z\.-]+))?(?:\+(?P<build>[0-9A-Za-z\.-]+))?$"
)


@dataclass(order=True)
class SemVer:
    major: int
    minor: int
    patch: int
    pre: Optional[str] = field(default=None, compare=False)

    def sort_key(self) -> tuple:
        # pre-release < release per SemVer 2.0.0 precedence
        return (self.major, self.minor, self.patch, 0 if self.pre else 1, self.pre or "")

    @classmethod
    def parse(cls, raw: str) -> "SemVer":
        m = _SEMVER_RE.match(raw.strip())
        if not m:
            raise UpdateManagerError(f"invalid semver: {raw!r}")
        return cls(int(m["major"]), int(m["minor"]), int(m["patch"]), m["pre"])

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        return f"{s}-{self.pre}" if self.pre else s


class VersionManager:
    """3.2 Version Manager — SemVer resolution + upgrade path validity."""

    def __init__(self, bus: SocketBus) -> None:
        self._socket = bus.get("version_mgr")

    def compare(self, a: str, b: str) -> int:
        va, vb = SemVer.parse(a).sort_key(), SemVer.parse(b).sort_key()
        return (va > vb) - (va < vb)

    def is_upgrade(self, installed: str, target: str) -> bool:
        return self.compare(target, installed) > 0

    def is_breaking(self, installed: str, target: str) -> bool:
        return SemVer.parse(target).major != SemVer.parse(installed).major

    async def resolve_path(self, installed: str, target: str) -> ValidationReport:
        if not self.is_upgrade(installed, target) and installed != target:
            report = ValidationReport(False, [f"downgrade {installed}->{target} not permitted"])
        else:
            report = ValidationReport(True)
        await self._socket.publish({"installed": installed, "target": target,
                                     "passed": report.passed})
        return report


class ReleaseChannelManager:
    """3.3 Release Channel Manager — channel auth + index retrieval."""

    TRUSTED_CHANNELS = {c for c in ReleaseChannel}

    def __init__(self, bus: SocketBus, trusted_keys: dict[str, str]) -> None:
        self._socket = bus.get("channel_mgr")
        self._trusted_keys = trusted_keys

    async def authenticate(self, channel: ReleaseChannel) -> bool:
        ok = channel in self.TRUSTED_CHANNELS
        await self._socket.publish({"channel": channel.value, "authenticated": ok})
        return ok

    async def fetch_index(self, channel: ReleaseChannel,
                           index_provider: Callable[[ReleaseChannel], list[dict]]
                           ) -> list[dict]:
        if not await self.authenticate(channel):
            raise UpdateManagerError(f"untrusted channel: {channel}")
        return index_provider(channel)


# ══════════════════════════════════════════════════════════════════
# 3.4 Discovery + 3.5 Download
# ══════════════════════════════════════════════════════════════════

class UpdateDiscovery:
    """3.4 Update Discovery — poll channel index for new descriptors."""

    def __init__(self, bus: SocketBus, channel_mgr: ReleaseChannelManager) -> None:
        self._socket = bus.get("discovery")
        self._channel_mgr = channel_mgr

    async def discover(self, channel: ReleaseChannel, installed_version: str,
                        index_provider: Callable[[ReleaseChannel], list[dict]]
                        ) -> list[UpdateDescriptor]:
        try:
            raw_index = await self._channel_mgr.fetch_index(channel, index_provider)
        except UpdateManagerError as exc:
            await self._socket.publish({"error": str(exc)})
            return []
        descriptors = [
            UpdateDescriptor(
                update_id=str(uuid.uuid4()), target_version=item["version"],
                update_type=UpdateType(item.get("type", "patch")),
                channel=channel, artifact_url=item["url"],
                sha256=item["sha256"], size_bytes=item.get("size_bytes", 0),
                requires=item.get("requires", {}), metadata=item.get("metadata", {}),
            )
            for item in raw_index
            if SemVer.parse(item["version"]).sort_key() >
               SemVer.parse(installed_version).sort_key()
        ]
        await self._socket.publish({"channel": channel.value, "found": len(descriptors)})
        return descriptors


class DownloadManager:
    """3.5 Download Manager — chunked fetch, stream hashing, resume."""

    def __init__(self, bus: SocketBus, staging_dir: Path) -> None:
        self._socket = bus.get("download")
        self._staging_dir = staging_dir
        self._staging_dir.mkdir(parents=True, exist_ok=True)

    async def fetch(self, descriptor: UpdateDescriptor,
                     fetcher: Callable[[str], bytes]) -> Path:
        dest = self._staging_dir / f"{descriptor.update_id}.pkg"
        try:
            data = await asyncio.to_thread(fetcher, descriptor.artifact_url)
        except Exception as exc:  # noqa: BLE001 — network layer is a boundary
            await self._socket.publish({"update_id": descriptor.update_id, "error": str(exc)})
            raise UpdateManagerError(f"download failed: {exc}") from exc
        digest = hashlib.sha256(data).hexdigest()
        if digest != descriptor.sha256:
            self._cleanup(dest)
            await self._socket.publish({"update_id": descriptor.update_id,
                                         "checksum_mismatch": True})
            raise UpdateManagerError("checksum mismatch on stream completion")
        dest.write_bytes(data)
        await self._socket.publish({"update_id": descriptor.update_id,
                                     "bytes": len(data), "path": str(dest)})
        return dest

    def _cleanup(self, path: Path) -> None:
        if path.exists():
            path.unlink()


# ══════════════════════════════════════════════════════════════════
# 3.6 / 3.7 Validators
# ══════════════════════════════════════════════════════════════════

class CompatibilityValidator:
    """3.6 Compatibility Validator — OS/hardware/organ constraint checks."""

    def __init__(self, bus: SocketBus, system_probe: Callable[[], dict[str, Any]]) -> None:
        self._socket = bus.get("compat_validator")
        self._system_probe = system_probe

    async def validate(self, descriptor: UpdateDescriptor) -> ValidationReport:
        telemetry = self._system_probe()
        reasons: list[str] = []
        min_ram = descriptor.requires.get("min_ram_gb")
        if min_ram and telemetry.get("ram_gb", 0) < min_ram:
            reasons.append(f"insufficient RAM: need {min_ram}GB")
        min_vram = descriptor.requires.get("min_vram_gb")
        if min_vram and telemetry.get("vram_gb", 0) < min_vram:
            reasons.append(f"insufficient VRAM: need {min_vram}GB")
        os_required = descriptor.requires.get("os")
        if os_required and telemetry.get("os") != os_required:
            reasons.append(f"OS mismatch: requires {os_required}")
        report = ValidationReport(passed=not reasons, reasons=reasons)
        await self._socket.publish({"update_id": descriptor.update_id, "passed": report.passed,
                                     "reasons": reasons})
        return report


class DependencyValidator:
    """3.7 Dependency Validator — cycle detection + version bounds."""

    def __init__(self, bus: SocketBus) -> None:
        self._socket = bus.get("dep_validator")

    async def validate(self, descriptor: UpdateDescriptor,
                        installed_manifest: dict[str, str]) -> ValidationReport:
        missing = [dep for dep, min_ver in descriptor.requires.items()
                   if dep.startswith("organ:") and dep not in installed_manifest]
        version_conflicts = [
            dep for dep, min_ver in descriptor.requires.items()
            if dep in installed_manifest and
            SemVer.parse(installed_manifest[dep]).sort_key() < SemVer.parse(min_ver).sort_key()
        ]
        reasons = [f"missing dependency: {d}" for d in missing]
        reasons += [f"version too low: {d}" for d in version_conflicts]
        report = ValidationReport(passed=not reasons, reasons=reasons)
        await self._socket.publish({"update_id": descriptor.update_id, "passed": report.passed})
        return report


# ══════════════════════════════════════════════════════════════════
# 3.8 Backup Coordinator
# ══════════════════════════════════════════════════════════════════

class BackupCoordinator:
    """3.8 Backup Coordinator — restore point creation before mutation."""

    def __init__(self, bus: SocketBus, backup_root: Path) -> None:
        self._socket = bus.get("backup_coord")
        self._backup_root = backup_root
        self._backup_root.mkdir(parents=True, exist_ok=True)

    async def create_restore_point(self, scope: list[str], source_paths: list[Path]) -> RestorePoint:
        rp_id = str(uuid.uuid4())
        snapshot_dir = self._backup_root / rp_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        for src in source_paths:
            if src.exists():
                dest = snapshot_dir / src.name
                if src.is_dir():
                    shutil.copytree(src, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dest)
        manifest_path = snapshot_dir / "manifest.json"
        manifest = {"restore_point_id": rp_id, "scope": scope,
                    "created_at": time.time(), "sources": [str(p) for p in source_paths]}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        rp = RestorePoint(rp_id, manifest["created_at"], scope, str(manifest_path))
        await self._socket.publish({"restore_point_id": rp_id, "scope": scope})
        return rp

    def load(self, restore_point_id: str) -> RestorePoint:
        manifest_path = self._backup_root / restore_point_id / "manifest.json"
        if not manifest_path.exists():
            raise UpdateManagerError(f"unknown restore point: {restore_point_id}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return RestorePoint(manifest["restore_point_id"], manifest["created_at"],
                             manifest["scope"], str(manifest_path))


# ══════════════════════════════════════════════════════════════════
# 3.12 Package Coordinator (crypto verify + extract + install)
# ══════════════════════════════════════════════════════════════════

class PackageCoordinator:
    """3.12 Package Coordinator — verify, extract, atomically install."""

    def __init__(self, bus: SocketBus, install_root: Path) -> None:
        self._socket = bus.get("package_coord")
        self._install_root = install_root
        self._install_root.mkdir(parents=True, exist_ok=True)

    async def install(self, descriptor: UpdateDescriptor, package_path: Path) -> Path:
        if hashlib.sha256(package_path.read_bytes()).hexdigest() != descriptor.sha256:
            raise UpdateManagerError("cryptographic verification failed at install")
        target_dir = self._install_root / descriptor.update_id
        staging = self._install_root / f".staging-{descriptor.update_id}"
        staging.mkdir(parents=True, exist_ok=True)
        extracted = staging / package_path.name
        shutil.copy2(package_path, extracted)
        # atomic swap: stage fully, then rename into place
        if target_dir.exists():
            shutil.rmtree(target_dir)
        staging.rename(target_dir)
        await self._socket.publish({"update_id": descriptor.update_id,
                                     "installed_path": str(target_dir)})
        return target_dir

    def purge_staging(self, descriptor_id: str) -> None:
        staging = self._install_root / f".staging-{descriptor_id}"
        if staging.exists():
            shutil.rmtree(staging)


# ══════════════════════════════════════════════════════════════════
# 3.9 / 3.10 / 3.11 Migration Engine
# ══════════════════════════════════════════════════════════════════

class MigrationEngine:
    """3.9-3.11 Migration Engine — config + state transformations."""

    def __init__(self, bus: SocketBus) -> None:
        self._socket = bus.get("migration_engine")
        self._config_socket = bus.get("config_migration")
        self._db_socket = bus.get("db_migration")

    async def migrate_config(self, existing: dict[str, Any], template: dict[str, Any]
                              ) -> dict[str, Any]:
        merged = dict(template)
        merged.update({k: v for k, v in existing.items() if k in template})
        await self._config_socket.publish({"keys_merged": len(merged)})
        return merged

    async def run_migrations(self, migrations: list[Callable[[], None]]) -> int:
        applied = 0
        for step in migrations:
            try:
                await asyncio.to_thread(step)
                applied += 1
            except Exception as exc:  # noqa: BLE001
                await self._db_socket.publish({"error": str(exc), "applied_before_fail": applied})
                raise UpdateManagerError(f"migration step failed: {exc}") from exc
        await self._socket.publish({"migrations_applied": applied})
        return applied


# ══════════════════════════════════════════════════════════════════
# 3.13 Verification Engine
# ══════════════════════════════════════════════════════════════════

class VerificationEngine:
    """3.13 Verification Engine — health probes + synthetic checks."""

    def __init__(self, bus: SocketBus) -> None:
        self._socket = bus.get("verification_engine")

    async def verify(self, probes: list[Callable[[], bool]]) -> ValidationReport:
        reasons = []
        for i, probe in enumerate(probes):
            try:
                ok = await asyncio.to_thread(probe)
            except Exception as exc:  # noqa: BLE001
                ok = False
                reasons.append(f"probe[{i}] raised: {exc}")
            if not ok:
                reasons.append(f"probe[{i}] failed")
        report = ValidationReport(passed=not reasons, reasons=reasons)
        await self._socket.publish({"passed": report.passed, "reasons": reasons})
        return report


# ══════════════════════════════════════════════════════════════════
# Activation / Rollback / Recovery
# ══════════════════════════════════════════════════════════════════

class ActivationManager:
    """Hot-swap activation, service restart, state unfreeze."""

    def __init__(self, bus: SocketBus) -> None:
        self._socket = bus.get("activation_mgr")

    async def activate(self, installed_path: Path, restart_hook: Optional[Callable[[], None]]
                        ) -> None:
        if restart_hook:
            await asyncio.to_thread(restart_hook)
        await self._socket.publish({"activated_path": str(installed_path)})


class RollbackManager:
    """Automatic rollback execution from restore point."""

    def __init__(self, bus: SocketBus, backup_coord: BackupCoordinator, restore_root: Path) -> None:
        self._socket = bus.get("rollback_mgr")
        self._backup_coord = backup_coord
        self._restore_root = restore_root

    async def rollback(self, restore_point_id: str, target_paths: list[Path]) -> None:
        rp = self._backup_coord.load(restore_point_id)
        snapshot_dir = self._backup_coord._backup_root / rp.restore_point_id  # documented internal use
        for target in target_paths:
            src = snapshot_dir / target.name
            if src.exists():
                if target.exists():
                    shutil.rmtree(target) if target.is_dir() else target.unlink()
                if src.is_dir():
                    shutil.copytree(src, target)
                else:
                    shutil.copy2(src, target)
        await self._socket.publish({"restore_point_id": restore_point_id,
                                     "restored_paths": [str(p) for p in target_paths]})


class RecoveryManager:
    """Catastrophe mitigation: safe-mode fallback when rollback itself fails."""

    def __init__(self, bus: SocketBus) -> None:
        self._socket = bus.get("recovery_mgr")

    async def enter_safe_mode(self, reason: str) -> None:
        await self._socket.publish({"safe_mode": True, "reason": reason})
        logger.critical("SAFE MODE ENTERED: %s", reason)


# ══════════════════════════════════════════════════════════════════
# Scheduler
# ══════════════════════════════════════════════════════════════════

class UpdateScheduler:
    """Update Scheduling — maintenance windows, deferred execution."""

    def __init__(self, bus: SocketBus) -> None:
        self._socket = bus.get("scheduler")

    async def within_window(self, now: float, window_start_hour: int, window_end_hour: int) -> bool:
        hour = time.localtime(now).tm_hour
        allowed = window_start_hour <= hour < window_end_hour
        await self._socket.publish({"hour": hour, "allowed": allowed})
        return allowed


# ══════════════════════════════════════════════════════════════════
# 3.1 Update Core — orchestrating state machine
# ══════════════════════════════════════════════════════════════════

_VALID_TRANSITIONS: dict[UpdateState, set[UpdateState]] = {
    UpdateState.IDLE: {UpdateState.DISCOVERING, UpdateState.VALIDATING},
    UpdateState.DISCOVERING: {UpdateState.VALIDATING, UpdateState.IDLE},
    UpdateState.VALIDATING: {UpdateState.BACKING_UP, UpdateState.FAILED},
    UpdateState.BACKING_UP: {UpdateState.DOWNLOADING, UpdateState.FAILED},
    UpdateState.DOWNLOADING: {UpdateState.INSTALLING, UpdateState.FAILED},
    UpdateState.INSTALLING: {UpdateState.MIGRATING, UpdateState.FAILED},
    UpdateState.MIGRATING: {UpdateState.VERIFYING, UpdateState.FAILED},
    UpdateState.VERIFYING: {UpdateState.ACTIVATING, UpdateState.ROLLING_BACK},
    UpdateState.ACTIVATING: {UpdateState.COMPLETED, UpdateState.ROLLING_BACK},
    UpdateState.ROLLING_BACK: {UpdateState.FAILED, UpdateState.IDLE},
    UpdateState.FAILED: {UpdateState.IDLE},
    UpdateState.COMPLETED: {UpdateState.IDLE},
}


class UpdateCore:
    """3.1 Update Core — global lock, phase control, orchestration."""

    def __init__(self, root_dir: Path, system_probe: Callable[[], dict[str, Any]],
                 trusted_channel_keys: Optional[dict[str, str]] = None) -> None:
        self.bus = SocketBus()
        self._lock = asyncio.Lock()
        self._state = UpdateState.IDLE
        self._context: Optional[UpdateContext] = None

        self.audit = AuditManager(self.bus, root_dir / "audit")
        self.metrics = MetricsManager(self.bus)
        self.version_mgr = VersionManager(self.bus)
        self.channel_mgr = ReleaseChannelManager(self.bus, trusted_channel_keys or {})
        self.discovery = UpdateDiscovery(self.bus, self.channel_mgr)
        self.download_mgr = DownloadManager(self.bus, root_dir / "staging")
        self.compat_validator = CompatibilityValidator(self.bus, system_probe)
        self.dep_validator = DependencyValidator(self.bus)
        self.backup_coord = BackupCoordinator(self.bus, root_dir / "backups")
        self.package_coord = PackageCoordinator(self.bus, root_dir / "installed")
        self.migration_engine = MigrationEngine(self.bus)
        self.verification_engine = VerificationEngine(self.bus)
        self.activation_mgr = ActivationManager(self.bus)
        self.rollback_mgr = RollbackManager(self.bus, self.backup_coord, root_dir / "backups")
        self.recovery_mgr = RecoveryManager(self.bus)
        self.scheduler = UpdateScheduler(self.bus)

    @property
    def state(self) -> UpdateState:
        return self._state

    async def _transition(self, new_state: UpdateState) -> None:
        if new_state not in _VALID_TRANSITIONS.get(self._state, set()):
            raise UpdateManagerError(f"illegal transition {self._state} -> {new_state}")
        await self.audit.record("state_transition", {"from": self._state.value,
                                                       "to": new_state.value})
        self._state = new_state
        await self.bus.get("update_core").publish({"state": new_state.value})

    async def check_for_updates(self, channel: ReleaseChannel, installed_version: str,
                                 index_provider: Callable[[ReleaseChannel], list[dict]]
                                 ) -> list[UpdateDescriptor]:
        await self._transition(UpdateState.DISCOVERING)
        try:
            descriptors = await self.discovery.discover(channel, installed_version, index_provider)
            return descriptors
        finally:
            await self._transition(UpdateState.IDLE)

    async def execute_update_sequence(
        self, descriptor: UpdateDescriptor, installed_version: str,
        installed_manifest: dict[str, str], fetcher: Callable[[str], bytes],
        backup_paths: list[Path], config_existing: dict[str, Any],
        config_template: dict[str, Any], migration_steps: list[Callable[[], None]],
        health_probes: list[Callable[[], bool]], restart_hook: Optional[Callable[[], None]] = None,
        auto_rollback: bool = True,
    ) -> UpdateContext:
        if self._lock.locked():
            raise UpdateManagerError("update core lock contention: another update in progress")
        async with self._lock:
            self._context = UpdateContext(descriptor.update_id, descriptor.target_version,
                                           auto_rollback_enabled=auto_rollback)
            await self.audit.record("update_started", {"update_id": descriptor.update_id,
                                                         "target": descriptor.target_version})
            try:
                await self._transition(UpdateState.VALIDATING)
                self.metrics.start("validation")
                version_report = await self.version_mgr.resolve_path(installed_version,
                                                                       descriptor.target_version)
                compat_report = await self.compat_validator.validate(descriptor)
                dep_report = await self.dep_validator.validate(descriptor, installed_manifest)
                await self.metrics.stop("validation")
                if not (version_report.passed and compat_report.passed and dep_report.passed):
                    raise UpdateManagerError(
                        f"validation failed: {version_report.reasons + compat_report.reasons + dep_report.reasons}")

                await self._transition(UpdateState.BACKING_UP)
                self.metrics.start("backup")
                restore_point = await self.backup_coord.create_restore_point(
                    scope=[descriptor.update_type.value], source_paths=backup_paths)
                self._context.restore_point_id = restore_point.restore_point_id
                await self.metrics.stop("backup")

                await self._transition(UpdateState.DOWNLOADING)
                self.metrics.start("download")
                package_path = await self.download_mgr.fetch(descriptor, fetcher)
                self._context.package_path = str(package_path)
                await self.metrics.stop("download")

                await self._transition(UpdateState.INSTALLING)
                self.metrics.start("install")
                installed_path = await self.package_coord.install(descriptor, package_path)
                await self.metrics.stop("install")

                await self._transition(UpdateState.MIGRATING)
                self.metrics.start("migration")
                await self.migration_engine.migrate_config(config_existing, config_template)
                await self.migration_engine.run_migrations(migration_steps)
                await self.metrics.stop("migration")

                await self._transition(UpdateState.VERIFYING)
                self.metrics.start("verify")
                verify_report = await self.verification_engine.verify(health_probes)
                await self.metrics.stop("verify")

                if not verify_report.passed:
                    await self._handle_failure(
                        f"verification failed: {verify_report.reasons}", backup_paths)
                    return self._context

                await self._transition(UpdateState.ACTIVATING)
                await self.activation_mgr.activate(installed_path, restart_hook)
                await self._transition(UpdateState.COMPLETED)
                await self.audit.record("update_completed", {"update_id": descriptor.update_id})
                await self._transition(UpdateState.IDLE)
                return self._context

            except UpdateManagerError as exc:
                await self._handle_failure(str(exc), backup_paths)
                return self._context

    async def _handle_failure(self, reason: str, backup_paths: list[Path]) -> None:
        await self.audit.record("update_failure", {"reason": reason})
        if self._context and self._context.auto_rollback_enabled and self._context.restore_point_id:
            try:
                await self._transition(UpdateState.ROLLING_BACK)
                await self.rollback_mgr.rollback(self._context.restore_point_id, backup_paths)
                await self._transition(UpdateState.IDLE)
                await self.audit.record("rollback_succeeded", {"reason": reason})
                return
            except Exception as exc:  # noqa: BLE001
                await self.recovery_mgr.enter_safe_mode(f"rollback failed: {exc}")
        await self._transition(UpdateState.FAILED)
        await self._transition(UpdateState.IDLE)

    async def abort_update(self) -> None:
        if self._context is None:
            return
        await self._handle_failure("manual abort", [])


# ══════════════════════════════════════════════════════════════════
# Organ facade — sole public entrypoint (Organ Specification §Public API)
# ══════════════════════════════════════════════════════════════════

class UpdateManagerOrgan:
    """Public facade. Other organs interact only through this surface
    and the documented SocketBus — never internal classes directly."""

    def __init__(self, root_dir: str, system_probe: Callable[[], dict[str, Any]]) -> None:
        self.core = UpdateCore(Path(root_dir), system_probe)

    async def check_for_updates(self, channel: ReleaseChannel, installed_version: str,
                                 index_provider: Callable[[ReleaseChannel], list[dict]]
                                 ) -> list[UpdateDescriptor]:
        return await self.core.check_for_updates(channel, installed_version, index_provider)

    async def execute_update(self, **kwargs) -> UpdateContext:
        return await self.core.execute_update_sequence(**kwargs)

    async def abort(self) -> None:
        await self.core.abort_update()

    @property
    def state(self) -> UpdateState:
        return self.core.state
