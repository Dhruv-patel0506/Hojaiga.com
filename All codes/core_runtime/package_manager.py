"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: package_manager.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [package_manager.py]
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
Dependencies: enum, pathlib, __future__, typing, tempfile...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: package_manager.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Hojaiga Automation OS — Organ 28: Package Manager
===================================================
Authority: PACKAGE_MANAGER.md > Organ Specification > Master Architecture Blueprint
Sockets: PackageSocket, RepositorySocket, InstallationSocket, AuditSocket
Pipelines: DiscoveryPipeline, InstallationPipeline, UpdatePipeline,
           RemovalPipeline, ValidationPipeline, RecoveryPipeline

PRE-CODE DIAGRAM
----------------
Request -> PackageSocket -> PackageCore -> {Resolver, Verifier} -> Installer
   -> Registry -> AuditManager -> PackageCommandResult

ACTUAL-CODE DIAGRAM
--------------------
PackageCore
 ├─ RepositoryManager  (discovery)
 ├─ MetadataManager    (parsing/cache)
 ├─ DependencyResolver (SAT-lite resolution)
 ├─ IntegrityVerifier  (sha256 + signature)
 ├─ SandboxRunner      (isolated post-install test)
 ├─ PackageInstaller   (atomic staging + swap)
 ├─ PackageUninstaller
 ├─ RollbackManager
 ├─ PackageRegistry    (sqlite state)
 └─ AuditManager       (append-only log)

Single-file organ: import as `from package_manager import PackageCore`.
No dependency on other organs' private state — communication only via
the dataclass contracts defined below (documented sockets/pipelines).
"""

import hashlib
import json
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

# ─────────────────────────── Contracts (Public API) ────────────────────────

class Operation(str, Enum):
    INSTALL = "INSTALL"
    UPGRADE = "UPGRADE"
    DOWNGRADE = "DOWNGRADE"
    REMOVE = "REMOVE"
    ROLLBACK = "ROLLBACK"
    SYNC = "SYNC"


class Status(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


@dataclass
class PackageCommandRequest:
    package_id: str
    operation: Operation
    target_version: Optional[str] = None
    allow_prerelease: bool = False
    force_reinstall: bool = False
    offline_only: bool = False
    auth_token: str = ""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class PackageCommandResult:
    request_id: str
    transaction_id: str
    status: Status
    package_id: str
    active_version: Optional[str]
    installed_files: list[str]
    execution_time_ms: float
    error_message: Optional[str] = None


@dataclass
class PackageManifest:
    package_id: str
    version: str
    dependencies: dict[str, str]  # package_id -> semver constraint (">=1.0.0")
    sha256: str
    files: list[str]
    signature: Optional[str] = None


# ───────────────────────────── Errors ───────────────────────────────────────

class PackageManagerError(Exception):
    pass


class DependencyError(PackageManagerError):
    pass


class IntegrityError(PackageManagerError):
    pass


class InstallError(PackageManagerError):
    pass


# ───────────────────────────── Versioning ───────────────────────────────────

def parse_version(v: str) -> tuple[int, int, int]:
    parts = (v.split("+")[0].split("-")[0]).split(".")
    nums = [int(p) for p in (parts + ["0", "0", "0"])[:3]]
    return nums[0], nums[1], nums[2]


def satisfies(version: str, constraint: str) -> bool:
    constraint = constraint.strip()
    if not constraint or constraint == "*":
        return True
    ops = [(">=", lambda a, b: a >= b), ("<=", lambda a, b: a <= b),
           ("==", lambda a, b: a == b), (">", lambda a, b: a > b),
           ("<", lambda a, b: a < b)]
    for sym, fn in ops:
        if constraint.startswith(sym):
            return fn(parse_version(version), parse_version(constraint[len(sym):]))
    return parse_version(version) == parse_version(constraint)


# ───────────────────────────── Audit Manager ─────────────────────────────────

class AuditManager:
    """Append-only audit log per Law Book Foundational Law 7 / Policy Ch.8."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(self, transaction_id: str, event: str, **fields) -> None:
        entry = {
            "transaction_id": transaction_id,
            "timestamp": time.time(),
            "event": event,
            **fields,
        }
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")


# ───────────────────────────── Registry ─────────────────────────────────────

class PackageRegistry:
    """Local durable state store (SQLite) — installed/available/deprecated."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = threading.Lock()
        self._migrate()

    def _migrate(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS packages (
                    package_id TEXT PRIMARY KEY,
                    version TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    installed_at REAL NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                )"""
            )
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    action TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    ts REAL NOT NULL
                )"""
            )

    def get(self, package_id: str) -> Optional[PackageManifest]:
        with self._lock:
            row = self._conn.execute(
                "SELECT manifest_json FROM packages WHERE package_id=? AND active=1",
                (package_id,),
            ).fetchone()
        return PackageManifest(**json.loads(row[0])) if row else None

    def reverse_dependents(self, package_id: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT package_id, manifest_json FROM packages WHERE active=1"
            ).fetchall()
        dependents = []
        for pid, mj in rows:
            deps = json.loads(mj).get("dependencies", {})
            if package_id in deps:
                dependents.append(pid)
        return dependents

    def upsert(self, manifest: PackageManifest, action: str) -> None:
        mj = json.dumps(manifest.__dict__)
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO packages (package_id, version, manifest_json, installed_at, active)
                   VALUES (?,?,?,?,1)
                   ON CONFLICT(package_id) DO UPDATE SET
                     version=excluded.version, manifest_json=excluded.manifest_json,
                     installed_at=excluded.installed_at, active=1""",
                (manifest.package_id, manifest.version, mj, time.time()),
            )
            self._conn.execute(
                "INSERT INTO history (package_id, version, action, manifest_json, ts) VALUES (?,?,?,?,?)",
                (manifest.package_id, manifest.version, action, mj, time.time()),
            )

    def deactivate(self, package_id: str, action: str) -> None:
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT manifest_json FROM packages WHERE package_id=?", (package_id,)
            ).fetchone()
            self._conn.execute("UPDATE packages SET active=0 WHERE package_id=?", (package_id,))
            if row:
                self._conn.execute(
                    "INSERT INTO history (package_id, version, action, manifest_json, ts) VALUES (?,?,?,?,?)",
                    (package_id, json.loads(row[0])["version"], action, row[0], time.time()),
                )

    def previous_version_manifest(self, package_id: str) -> Optional[PackageManifest]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT manifest_json FROM history WHERE package_id=? AND action IN ('INSTALL','UPGRADE','DOWNGRADE') ORDER BY id DESC",
                (package_id,),
            ).fetchall()
        if len(rows) < 2:
            return None
        return PackageManifest(**json.loads(rows[1][0]))


# ─────────────────────── Repository / Metadata Manager ──────────────────────

class RepositoryManager:
    """Package discovery. `source` is a pluggable resolver: package_id -> PackageBundle."""

    def __init__(self, source: dict[str, dict]):
        # source: {package_id: {version: {manifest:..., archive_path:...}}}
        self._source = source

    def query(self, package_id: str) -> dict[str, dict]:
        if package_id not in self._source:
            raise DependencyError(f"Package not found in repository: {package_id}")
        return self._source[package_id]

    def resolve_manifest(self, package_id: str, version: str) -> PackageManifest:
        versions = self.query(package_id)
        if version not in versions:
            raise DependencyError(f"Version not found: {package_id}=={version}")
        return PackageManifest(**versions[version]["manifest"])

    def archive_path(self, package_id: str, version: str) -> Path:
        return Path(self.query(package_id)[version]["archive_path"])

    def latest_version(self, package_id: str, allow_prerelease: bool = False) -> str:
        versions = list(self.query(package_id).keys())
        versions.sort(key=parse_version)
        return versions[-1]


# ───────────────────────────── Dependency Resolver ───────────────────────────

class DependencyResolver:
    """Deterministic depth-first resolver with cycle & conflict detection."""

    def __init__(self, registry: PackageRegistry, repo: RepositoryManager):
        self.registry = registry
        self.repo = repo

    def compute_install_plan(self, package_id: str, version: Optional[str]) -> list[PackageManifest]:
        version = version or self.repo.latest_version(package_id)
        plan: list[PackageManifest] = []
        visiting: set[str] = set()
        resolved: dict[str, str] = {}

        def visit(pid: str, constraint: str) -> None:
            if pid in visiting:
                raise DependencyError(f"Circular dependency detected at {pid}")
            if pid in resolved:
                if not satisfies(resolved[pid], constraint):
                    raise DependencyError(
                        f"Version conflict for {pid}: {resolved[pid]} vs {constraint}"
                    )
                return
            candidates = [v for v in self.repo.query(pid).keys() if satisfies(v, constraint)]
            if not candidates:
                raise DependencyError(f"No version of {pid} satisfies {constraint}")
            candidates.sort(key=parse_version)
            candidate_version = candidates[-1]
            visiting.add(pid)
            manifest = self.repo.resolve_manifest(pid, candidate_version)
            for dep_id, dep_constraint in manifest.dependencies.items():
                visit(dep_id, dep_constraint)
            resolved[pid] = candidate_version
            plan.append(manifest)
            visiting.discard(pid)

        visit(package_id, f"=={version}")
        return plan


# ───────────────────────────── Integrity Verifier ────────────────────────────

class IntegrityVerifier:
    def verify_checksum(self, archive_path: Path, expected_sha256: str) -> None:
        h = hashlib.sha256()
        with archive_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        digest = h.hexdigest()
        if digest != expected_sha256:
            raise IntegrityError(
                f"Checksum mismatch for {archive_path.name}: expected {expected_sha256}, got {digest}"
            )

    def verify_signature(self, manifest: PackageManifest, verify_fn: Optional[Callable[[PackageManifest], bool]]) -> None:
        if manifest.signature and verify_fn and not verify_fn(manifest):
            raise IntegrityError(f"Signature verification failed for {manifest.package_id}")


# ───────────────────────────── Sandbox Runner ────────────────────────────────

class SandboxRunner:
    """Isolated post-install smoke test in a temp directory. CPU-only, no GPU."""

    def run(self, staged_dir: Path, test_fn: Optional[Callable[[Path], bool]]) -> bool:
        if test_fn is None:
            return True
        return test_fn(staged_dir)


# ───────────────────────────── Installer / Uninstaller ───────────────────────

class PackageInstaller:
    def __init__(self, install_root: Path, verifier: IntegrityVerifier, sandbox: SandboxRunner):
        self.install_root = install_root
        self.install_root.mkdir(parents=True, exist_ok=True)
        self.verifier = verifier
        self.sandbox = sandbox

    def install(self, manifest: PackageManifest, archive_path: Path,
                sig_fn: Optional[Callable[[PackageManifest], bool]] = None,
                test_fn: Optional[Callable[[Path], bool]] = None) -> list[str]:
        self.verifier.verify_checksum(archive_path, manifest.sha256)
        self.verifier.verify_signature(manifest, sig_fn)

        target_dir = self.install_root / manifest.package_id
        with tempfile.TemporaryDirectory(prefix=f"pkg_stage_{manifest.package_id}_") as tmp:
            staging = Path(tmp)
            if archive_path.is_dir():
                shutil.copytree(archive_path, staging, dirs_exist_ok=True)
            else:
                shutil.unpack_archive(str(archive_path), str(staging))

            if not self.sandbox.run(staging, test_fn):
                raise InstallError(f"Sandbox validation failed for {manifest.package_id}")

            self._atomic_swap(staging, target_dir)

        return [str(p) for p in target_dir.rglob("*") if p.is_file()]

    @staticmethod
    def _atomic_swap(staging: Path, target_dir: Path) -> None:
        backup: Optional[Path] = None
        if target_dir.exists():
            backup = target_dir.with_suffix(".bak")
            if backup.exists():
                shutil.rmtree(backup)
            target_dir.rename(backup)
        try:
            shutil.copytree(staging, target_dir)
        except Exception:
            if target_dir.exists():
                shutil.rmtree(target_dir)
            if backup is not None:
                backup.rename(target_dir)
            raise
        else:
            if backup is not None:
                shutil.rmtree(backup)


class PackageUninstaller:
    def __init__(self, install_root: Path, registry: PackageRegistry):
        self.install_root = install_root
        self.registry = registry

    def uninstall(self, package_id: str, force: bool = False) -> list[str]:
        dependents = self.registry.reverse_dependents(package_id)
        if dependents and not force:
            raise DependencyError(
                f"Cannot remove {package_id}: required by {dependents}"
            )
        target_dir = self.install_root / package_id
        removed = [str(p) for p in target_dir.rglob("*") if p.is_file()] if target_dir.exists() else []
        if target_dir.exists():
            shutil.rmtree(target_dir)
        return removed


# ───────────────────────────── Rollback Manager ──────────────────────────────

class RollbackManager:
    def __init__(self, installer: PackageInstaller, registry: PackageRegistry, repo: RepositoryManager):
        self.installer = installer
        self.registry = registry
        self.repo = repo

    def rollback(self, package_id: str) -> PackageManifest:
        previous = self.registry.previous_version_manifest(package_id)
        if previous is None:
            raise PackageManagerError(f"No previous version to rollback for {package_id}")
        archive = self.repo.archive_path(package_id, previous.version)
        self.installer.install(previous, archive)
        self.registry.upsert(previous, "ROLLBACK")
        return previous


# ───────────────────────────── Package Core (Orchestrator) ──────────────────

class PackageCore:
    """Master orchestrator — sole entry point exposed via PackageSocket."""

    def __init__(self, root: Path,
                 repository_source: Optional[dict] = None,
                 sig_fn: Optional[Callable[[PackageManifest], bool]] = None,
                 test_fn: Optional[Callable[[Path], bool]] = None):
        root.mkdir(parents=True, exist_ok=True)
        self.registry = PackageRegistry(root / "registry.sqlite3")
        self.audit = AuditManager(root / "audit.log")
        self.repo = RepositoryManager(repository_source or {})
        self.resolver = DependencyResolver(self.registry, self.repo)
        self.verifier = IntegrityVerifier()
        self.sandbox = SandboxRunner()
        self.installer = PackageInstaller(root / "packages", self.verifier, self.sandbox)
        self.uninstaller = PackageUninstaller(root / "packages", self.registry)
        self.rollback_mgr = RollbackManager(self.installer, self.registry, self.repo)
        self._sig_fn = sig_fn
        self._test_fn = test_fn
        self._lock = threading.Lock()

    def execute_command(self, cmd: PackageCommandRequest) -> PackageCommandResult:
        transaction_id = str(uuid.uuid4())
        start = time.time()
        self.audit.record(transaction_id, "COMMAND_RECEIVED", package_id=cmd.package_id, op=cmd.operation)
        try:
            with self._lock:
                if cmd.operation in (Operation.INSTALL, Operation.UPGRADE, Operation.DOWNGRADE):
                    files, version = self._install_or_update(cmd, transaction_id)
                elif cmd.operation == Operation.REMOVE:
                    files = self.uninstaller.uninstall(cmd.package_id, force=cmd.force_reinstall)
                    self.registry.deactivate(cmd.package_id, "REMOVE")
                    version = None
                elif cmd.operation == Operation.ROLLBACK:
                    manifest = self.rollback_mgr.rollback(cmd.package_id)
                    files, version = manifest.files, manifest.version
                elif cmd.operation == Operation.SYNC:
                    files, version = [], None
                else:
                    raise PackageManagerError(f"Unsupported operation: {cmd.operation}")

            self.audit.record(transaction_id, "COMMAND_SUCCESS", package_id=cmd.package_id)
            return PackageCommandResult(
                request_id=cmd.request_id, transaction_id=transaction_id, status=Status.SUCCESS,
                package_id=cmd.package_id, active_version=version, installed_files=files,
                execution_time_ms=(time.time() - start) * 1000,
            )
        except PackageManagerError as exc:
            self.audit.record(transaction_id, "COMMAND_FAILED", package_id=cmd.package_id, error=str(exc))
            return PackageCommandResult(
                request_id=cmd.request_id, transaction_id=transaction_id, status=Status.FAILED,
                package_id=cmd.package_id, active_version=None, installed_files=[],
                execution_time_ms=(time.time() - start) * 1000, error_message=str(exc),
            )
        except Exception as exc:  # unexpected panic — recover per Universal Law 8
            self.audit.record(transaction_id, "COMMAND_PANIC", package_id=cmd.package_id, error=str(exc))
            return PackageCommandResult(
                request_id=cmd.request_id, transaction_id=transaction_id, status=Status.REJECTED,
                package_id=cmd.package_id, active_version=None, installed_files=[],
                execution_time_ms=(time.time() - start) * 1000, error_message=f"internal error: {exc}",
            )

    def _install_or_update(self, cmd: PackageCommandRequest, transaction_id: str) -> tuple[list[str], str]:
        plan = self.resolver.compute_install_plan(cmd.package_id, cmd.target_version)
        self.audit.record(transaction_id, "PLAN_RESOLVED", plan=[m.package_id + "@" + m.version for m in plan])
        installed_files: list[str] = []
        for manifest in plan:
            archive = self.repo.archive_path(manifest.package_id, manifest.version)
            files = self.installer.install(manifest, archive, self._sig_fn, self._test_fn)
            self.registry.upsert(manifest, cmd.operation.value)
            installed_files.extend(files)
        top = plan[-1]
        return installed_files, top.version


__all__ = [
    "PackageCore", "PackageCommandRequest", "PackageCommandResult",
    "PackageManifest", "Operation", "Status",
    "PackageManagerError", "DependencyError", "IntegrityError", "InstallError",
]
