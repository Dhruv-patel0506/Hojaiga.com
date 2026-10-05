"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: infrastructure_organ.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [infrastructure_organ.py]
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
    input([Input Node]) --> process([Code Node: infrastructure_organ.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
infrastructure_organ.py

Hojaiga Automation OS — Organ 09: Infrastructure

Single-file production implementation of the Infrastructure Organ:
hardware telemetry, resource scheduling, append-only structured logging,
SSD/HDD filesystem partitioning, checksum-verified downloads, outbound
API gateway with circuit breaking, version management, and a background
monitoring loop that emits threshold events to subscribers (the CNS in
the full Hojaiga topology).

Compliance:
    Universal Law 5  — Standardized Communication (single public facade)
    Universal Law 7  — Security and Least Privilege
    Universal Law 8  — Failure Transparency and Recovery
    Universal Law 11 — Resource Responsibility
    Policy Manual Ch. 8, 10, 12, 14

The Brain (Qwen3-8B / llama.cpp) is never instantiated here. This organ
only observes GPU/VRAM state.
"""


import hashlib
import json
import logging
import shutil
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import psutil
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "psutil is required for Organ 09 (Infrastructure). Install with "
        "'pip install psutil'."
    ) from exc

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # APIGateway.route() will raise a clear error if used.

try:
    import pynvml  # type: ignore

    _NVML_AVAILABLE = True
except ImportError:  # pragma: no cover
    pynvml = None
    _NVML_AVAILABLE = False


_LOGGER = logging.getLogger("hojaiga.infrastructure")
_LOGGER.addHandler(logging.NullHandler())


# ═══════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════

class OrganState(str, Enum):
    BOOTSTRAPPING = "BOOTSTRAPPING"
    OPERATIONAL = "OPERATIONAL"
    THROTTLED = "THROTTLED"
    DEGRADED = "DEGRADED"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    STOPPED = "STOPPED"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class QuotaClass(str, Enum):
    NORMAL = "NORMAL"
    LOW_PRIORITY = "LOW_PRIORITY"
    SUSPENDED = "SUSPENDED"


# ═══════════════════════════════════════════════════════════════════════
# Data Contracts
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class HardwareStatus:
    cpu_percent: float
    ram_percent: float
    ram_used_mb: float
    ram_total_mb: float
    vram_used_mb: Optional[float]
    vram_total_mb: Optional[float]
    ssd_free_gb: float
    hdd_free_gb: Optional[float]
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class QuotaRequest:
    requesting_organ: str
    cpu_weight: float = 1.0          # relative weight, 0.0-1.0
    max_ram_mb: Optional[float] = None
    priority: str = "normal"         # normal | low | high


@dataclass(frozen=True)
class QuotaGrant:
    grant_id: str
    requesting_organ: str
    quota_class: QuotaClass
    max_ram_mb: Optional[float]
    granted_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class LogEntry:
    execution_id: str
    responsible_component: str
    agent_model: Optional[str]
    task_description: str
    level: LogLevel = LogLevel.INFO
    decision_summary: Optional[str] = None
    files_read: tuple = ()
    files_modified: tuple = ()
    output_summary: Optional[str] = None
    errors: Optional[str] = None
    recovery_actions: Optional[str] = None
    duration_ms: Optional[float] = None
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class DownloadRequest:
    url: str
    destination_relative_path: str
    expected_sha256: Optional[str] = None
    max_bytes_per_sec: Optional[int] = None


@dataclass(frozen=True)
class DownloadHandle:
    download_id: str
    final_path: str
    bytes_written: int
    sha256: str
    verified: bool
    duration_ms: float


@dataclass(frozen=True)
class APIRequest:
    method: str
    url: str
    headers: Optional[dict] = None
    json_body: Optional[dict] = None
    timeout_sec: float = 15.0


@dataclass(frozen=True)
class APIResponse:
    status_code: int
    body: Optional[dict]
    elapsed_ms: float
    error: Optional[str] = None


@dataclass(frozen=True)
class VersionManifest:
    organ: str = "infrastructure"
    version: str = "1.0.0"
    schema_version: str = "1.0.0"
    build_timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ArchivalRequest:
    runtime_relative_path: str
    delete_source: bool = True


@dataclass(frozen=True)
class ArchivalStatus:
    success: bool
    archive_path: Optional[str]
    error: Optional[str] = None


@dataclass(frozen=True)
class InfraEvent:
    event_type: str
    payload: dict
    timestamp: float = field(default_factory=time.time)


# ═══════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class InfrastructureConfig:
    ssd_root: Path
    hdd_root: Optional[Path]
    ram_warning_percent: float = 85.0
    vram_warning_mb: float = 3584.0  # 3.5 GB of 4GB RTX 3050
    ssd_free_warning_gb: float = 5.0
    monitor_interval_sec: float = 1.0
    log_flush_interval_sec: float = 2.0
    log_batch_max: int = 500
    api_rate_limit_per_sec: float = 10.0
    api_circuit_failure_threshold: int = 5
    api_circuit_cooldown_sec: float = 30.0

    @staticmethod
    def defaults(base_dir: Optional[str] = None) -> "InfrastructureConfig":
        base = Path(base_dir) if base_dir else Path.cwd() / "organ_10_infrastructure"
        ssd_root = base / "storage" / "ssd_runtime"
        hdd_root = base / "storage" / "hdd_archive"
        for p in (
            ssd_root / "downloads",
            ssd_root / "log_buffer",
            hdd_root / "logs",
            hdd_root / "history",
            hdd_root / "backups",
        ):
            p.mkdir(parents=True, exist_ok=True)
        return InfrastructureConfig(ssd_root=ssd_root, hdd_root=hdd_root)

    @staticmethod
    def from_file(path: str) -> "InfrastructureConfig":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        cfg = InfrastructureConfig.defaults(raw.get("base_dir"))
        for key, value in raw.items():
            if hasattr(cfg, key) and key not in ("ssd_root", "hdd_root"):
                setattr(cfg, key, value)
        return cfg


# ═══════════════════════════════════════════════════════════════════════
# Hardware Controller
# ═══════════════════════════════════════════════════════════════════════

class HardwareController:
    """CPU-first hardware telemetry. GPU access is read-only and never
    loads workloads; the Brain organ owns all VRAM allocation for
    inference."""

    def __init__(self, config: InfrastructureConfig):
        self._config = config
        self._nvml_ready = False
        if _NVML_AVAILABLE:
            try:
                pynvml.nvmlInit()  # type: ignore
                self._nvml_ready = True
            except Exception as exc:  # pragma: no cover
                _LOGGER.warning("NVML init failed, falling back: %s", exc)

    def query_cpu_and_ram(self) -> tuple[float, float, float, float]:
        cpu_percent = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        ram_used_mb = (vm.total - vm.available) / (1024 * 1024)
        ram_total_mb = vm.total / (1024 * 1024)
        return cpu_percent, vm.percent, ram_used_mb, ram_total_mb

    def query_vram_usage(self) -> Optional[tuple[float, float]]:
        if self._nvml_ready:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)  # type: ignore
                meminfo = pynvml.nvmlDeviceGetMemoryInfo(handle)  # type: ignore
                return (
                    float(meminfo.used) / (1024 * 1024),
                    float(meminfo.total) / (1024 * 1024),
                )
            except Exception as exc:  # pragma: no cover
                _LOGGER.debug("NVML query failed: %s", exc)
        return self._query_vram_via_smi()

    @staticmethod
    def _query_vram_via_smi() -> Optional[tuple[float, float]]:
        try:
            out = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            )
            used_str, total_str = out.stdout.strip().splitlines()[0].split(",")
            return float(used_str.strip()), float(total_str.strip())
        except Exception:
            return None

    def _disk_free_gb(self, path: Path) -> Optional[float]:
        try:
            return shutil.disk_usage(path).free / (1024 ** 3)
        except FileNotFoundError:
            return None

    def snapshot(self) -> HardwareStatus:
        cpu_pct, ram_pct, ram_used_mb, ram_total_mb = self.query_cpu_and_ram()
        vram = self.query_vram_usage()
        ssd_free = self._disk_free_gb(self._config.ssd_root) or 0.0
        hdd_free = (
            self._disk_free_gb(self._config.hdd_root)
            if self._config.hdd_root
            else None
        )
        return HardwareStatus(
            cpu_percent=cpu_pct,
            ram_percent=ram_pct,
            ram_used_mb=ram_used_mb,
            ram_total_mb=ram_total_mb,
            vram_used_mb=vram[0] if vram else None,
            vram_total_mb=vram[1] if vram else None,
            ssd_free_gb=ssd_free,
            hdd_free_gb=hdd_free,
        )

    def shutdown(self) -> None:
        if self._nvml_ready:
            try:
                pynvml.nvmlShutdown()  # type: ignore
            except Exception:  # pragma: no cover
                pass


# ═══════════════════════════════════════════════════════════════════════
# Resource Scheduler
# ═══════════════════════════════════════════════════════════════════════

class ResourceScheduler:
    """In-process quota governor. Enforces a low-priority execution mode
    across cooperating organs when the system is under load. Does not
    manage GPU allocation (reserved exclusively for the Brain organ)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._grants: dict[str, QuotaGrant] = {}
        self._quota_class = QuotaClass.NORMAL

    def allocate(self, request: QuotaRequest) -> QuotaGrant:
        with self._lock:
            grant = QuotaGrant(
                grant_id=str(uuid.uuid4()),
                requesting_organ=request.requesting_organ,
                quota_class=self._quota_class,
                max_ram_mb=request.max_ram_mb,
            )
            self._grants[grant.grant_id] = grant
            return grant

    def release(self, grant_id: str) -> bool:
        with self._lock:
            return self._grants.pop(grant_id, None) is not None

    def set_quota_class(self, quota_class: QuotaClass) -> None:
        with self._lock:
            self._quota_class = quota_class

    def current_class(self) -> QuotaClass:
        with self._lock:
            return self._quota_class

    def active_grants(self) -> int:
        with self._lock:
            return len(self._grants)


# ═══════════════════════════════════════════════════════════════════════
# Central Logger
# ═══════════════════════════════════════════════════════════════════════

class CentralLogger:
    """Thread-safe, non-blocking, append-only structured JSON logger.
    Writes batches to an SSD staging buffer on a background thread.
    Callers never block on disk I/O (Law Book, Universal Law 8)."""

    def __init__(self, config: InfrastructureConfig):
        self._config = config
        self._queue: deque[LogEntry] = deque()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._buffer_file = (
            config.ssd_root / "log_buffer" / f"session_{int(time.time())}.jsonl"
        )
        self._worker = threading.Thread(
            target=self._flush_worker, name="infra-log-flush", daemon=True
        )
        self._worker.start()

    def write(self, entry: LogEntry) -> None:
        with self._lock:
            self._queue.append(entry)

    def _drain_batch(self) -> list[LogEntry]:
        with self._lock:
            batch = []
            while self._queue and len(batch) < self._config.log_batch_max:
                batch.append(self._queue.popleft())
            return batch

    def _flush_worker(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(self._config.log_flush_interval_sec)
            self._flush_once()
        self._flush_once()  # final drain on shutdown

    def _flush_once(self) -> None:
        batch = self._drain_batch()
        if not batch:
            return
        try:
            with self._buffer_file.open("a", encoding="utf-8") as fh:
                for entry in batch:
                    record: dict[str, Any] = asdict(entry)
                    record["level"] = entry.level.value
                    fh.write(json.dumps(record, default=str) + "\n")
        except OSError as exc:  # pragma: no cover
            _LOGGER.error("Log flush failed: %s", exc)

    def archive_current_buffer(self, hdd_root: Optional[Path]) -> Optional[Path]:
        if hdd_root is None or not self._buffer_file.exists():
            return None
        target = hdd_root / "logs" / self._buffer_file.name
        try:
            shutil.copy2(self._buffer_file, target)
            return target
        except OSError as exc:  # pragma: no cover
            _LOGGER.error("Log archival failed: %s", exc)
            return None

    def shutdown(self) -> None:
        self._stop_event.set()
        self._worker.join(timeout=5.0)


# ═══════════════════════════════════════════════════════════════════════
# Filesystem Manager
# ═══════════════════════════════════════════════════════════════════════

class FilesystemManager:
    """Enforces the SSD runtime / HDD archive partition boundary and
    guards against path traversal outside managed roots."""

    def __init__(self, config: InfrastructureConfig):
        self._config = config

    def _resolve_within(self, root: Path, relative_path: str) -> Path:
        candidate = (root / relative_path).resolve()
        root_resolved = root.resolve()
        if root_resolved not in candidate.parents and candidate != root_resolved:
            raise PermissionError(
                f"Path traversal blocked: '{relative_path}' escapes '{root}'."
            )
        return candidate

    def get_runtime_path(self, relative_path: str) -> Path:
        return self._resolve_within(self._config.ssd_root, relative_path)

    def get_archive_path(self, relative_path: str) -> Path:
        if self._config.hdd_root is None:
            raise RuntimeError("External HDD archive root is not configured.")
        return self._resolve_within(self._config.hdd_root, relative_path)

    def archive_file(self, request: ArchivalRequest) -> ArchivalStatus:
        try:
            source = self.get_runtime_path(request.runtime_relative_path)
            if not source.exists():
                return ArchivalStatus(False, None, "Source file does not exist.")
            destination = self.get_archive_path(request.runtime_relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if request.delete_source:
                source.unlink()
            return ArchivalStatus(True, str(destination))
        except (PermissionError, RuntimeError, OSError) as exc:
            return ArchivalStatus(False, None, str(exc))

    def free_space_bytes(self, path: Path) -> int:
        return shutil.disk_usage(path).free


# ═══════════════════════════════════════════════════════════════════════
# Download Manager
# ═══════════════════════════════════════════════════════════════════════

class DownloadManager:
    """Checksum-verified, optionally throttled file transfer into the
    SSD runtime `downloads/` staging area."""

    _CHUNK_SIZE = 1024 * 256

    def __init__(self, config: InfrastructureConfig, fs: FilesystemManager):
        self._config = config
        self._fs = fs

    def download(self, request: DownloadRequest) -> DownloadHandle:
        if requests is None:
            raise RuntimeError(
                "The 'requests' package is required for DownloadManager."
            )
        start = time.perf_counter()
        destination = self._fs.get_runtime_path(
            f"downloads/{request.destination_relative_path}"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)

        sha256 = hashlib.sha256()
        bytes_written = 0
        with requests.get(request.url, stream=True, timeout=30) as response:
            response.raise_for_status()
            with destination.open("wb") as fh:
                last_tick = time.perf_counter()
                bytes_since_tick = 0
                for chunk in response.iter_content(chunk_size=self._CHUNK_SIZE):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    sha256.update(chunk)
                    bytes_written += len(chunk)
                    bytes_since_tick += len(chunk)
                    if request.max_bytes_per_sec:
                        elapsed = time.perf_counter() - last_tick
                        expected = bytes_since_tick / request.max_bytes_per_sec
                        if expected > elapsed:
                            time.sleep(expected - elapsed)
                        if elapsed >= 1.0:
                            last_tick = time.perf_counter()
                            bytes_since_tick = 0

        digest = sha256.hexdigest()
        verified = (
            request.expected_sha256 is None
            or request.expected_sha256.lower() == digest.lower()
        )
        if not verified:
            destination.unlink(missing_ok=True)

        return DownloadHandle(
            download_id=str(uuid.uuid4()),
            final_path=str(destination),
            bytes_written=bytes_written,
            sha256=digest,
            verified=verified,
            duration_ms=(time.perf_counter() - start) * 1000,
        )


# ═══════════════════════════════════════════════════════════════════════
# API Gateway (rate limit + circuit breaker)
# ═══════════════════════════════════════════════════════════════════════

class _CircuitBreaker:
    def __init__(self, failure_threshold: int, cooldown_sec: float):
        self._threshold = failure_threshold
        self._cooldown = cooldown_sec
        self._failures = 0
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if time.time() - self._opened_at >= self._cooldown:
                self._opened_at = None
                self._failures = 0
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._threshold:
                self._opened_at = time.time()


class APIGateway:
    """Outbound HTTP egress with token-bucket rate limiting and a
    circuit breaker to prevent cascading external-service failures."""

    def __init__(self, config: InfrastructureConfig):
        self._config = config
        self._lock = threading.Lock()
        self._tokens = config.api_rate_limit_per_sec
        self._last_refill = time.perf_counter()
        self._breaker = _CircuitBreaker(
            config.api_circuit_failure_threshold, config.api_circuit_cooldown_sec
        )

    def _acquire_token(self) -> None:
        with self._lock:
            now = time.perf_counter()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._config.api_rate_limit_per_sec,
                self._tokens + elapsed * self._config.api_rate_limit_per_sec,
            )
            self._last_refill = now
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._config.api_rate_limit_per_sec
                time.sleep(max(wait, 0.0))
                self._tokens = 0.0
            else:
                self._tokens -= 1.0

    def route(self, request: APIRequest) -> APIResponse:
        if requests is None:
            return APIResponse(0, None, 0.0, "The 'requests' package is not installed.")
        if not self._breaker.allow():
            return APIResponse(0, None, 0.0, "Circuit breaker open: egress suspended.")

        self._acquire_token()
        start = time.perf_counter()
        try:
            response = requests.request(
                method=request.method,
                url=request.url,
                headers=request.headers,
                json=request.json_body,
                timeout=request.timeout_sec,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._breaker.record_success()
            try:
                body = response.json()
            except ValueError:
                body = None
            return APIResponse(response.status_code, body, elapsed_ms)
        except Exception as exc:
            self._breaker.record_failure()
            elapsed_ms = (time.perf_counter() - start) * 1000
            return APIResponse(0, None, elapsed_ms, str(exc))


# ═══════════════════════════════════════════════════════════════════════
# Version Manager
# ═══════════════════════════════════════════════════════════════════════

class VersionManager:
    def __init__(self, manifest: Optional[VersionManifest] = None):
        self._manifest = manifest or VersionManifest()

    def get_manifest(self) -> VersionManifest:
        return self._manifest


# ═══════════════════════════════════════════════════════════════════════
# Monitoring Engine
# ═══════════════════════════════════════════════════════════════════════

class MonitoringEngine:
    """Background telemetry loop. Samples hardware at a fixed interval
    and raises threshold events without ever mutating other organs'
    state directly (Universal Law 3 — Separation of Responsibility)."""

    def __init__(
        self,
        config: InfrastructureConfig,
        hardware: HardwareController,
        on_event: Callable[[InfraEvent], None],
        on_state_hint: Callable[[str], None],
    ):
        self._config = config
        self._hardware = hardware
        self._on_event = on_event
        self._on_state_hint = on_state_hint
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._loop, name="infra-monitor", daemon=True
        )
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                status = self._hardware.snapshot()
                self._evaluate(status)
            except Exception as exc:  # pragma: no cover
                _LOGGER.error("Monitoring loop error: %s", exc)
            self._stop_event.wait(self._config.monitor_interval_sec)

    def _evaluate(self, status: HardwareStatus) -> None:
        throttle_needed = status.ram_percent >= self._config.ram_warning_percent
        vram_breach = (
            status.vram_used_mb is not None
            and status.vram_used_mb >= self._config.vram_warning_mb
        )
        if throttle_needed or vram_breach:
            self._on_event(
                InfraEvent(
                    "EVENT_INFRASTRUCTURE_RESOURCE_WARNING",
                    {
                        "ram_percent": status.ram_percent,
                        "vram_used_mb": status.vram_used_mb,
                    },
                )
            )
            self._on_state_hint("THROTTLED")
        else:
            self._on_state_hint("OPERATIONAL")

        if status.ssd_free_gb < self._config.ssd_free_warning_gb:
            self._on_event(
                InfraEvent(
                    "EVENT_STORAGE_QUOTA_BREACH",
                    {"ssd_free_gb": status.ssd_free_gb},
                )
            )

        if status.hdd_free_gb is None:
            self._on_state_hint("DEGRADED")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)


# ═══════════════════════════════════════════════════════════════════════
# Infrastructure Organ (Public Facade / Kernel)
# ═══════════════════════════════════════════════════════════════════════

class InfrastructureOrgan:
    """Public entry point for Organ 09. All other organs interact with
    Infrastructure exclusively through this facade, per Universal Law 5
    (Standardized Communication) and Organ Specification Section 7."""

    def __init__(self, config: Optional[InfrastructureConfig] = None):
        self.config = config or InfrastructureConfig.defaults()
        self.state = OrganState.BOOTSTRAPPING

        self.hardware = HardwareController(self.config)
        self.scheduler = ResourceScheduler()
        self.logger = CentralLogger(self.config)
        self.filesystem = FilesystemManager(self.config)
        self.downloads = DownloadManager(self.config, self.filesystem)
        self.gateway = APIGateway(self.config)
        self.versions = VersionManager()

        self._subscribers: dict[str, Callable[[InfraEvent], None]] = {}
        self._sub_lock = threading.Lock()

        self.monitor = MonitoringEngine(
            self.config, self.hardware, self._dispatch_event, self._apply_state_hint
        )

        self.state = OrganState.OPERATIONAL

    # ---- lifecycle -----------------------------------------------------

    def start(self) -> None:
        self.monitor.start()

    def shutdown(self) -> None:
        self.state = OrganState.SHUTTING_DOWN
        self.monitor.stop()
        self.logger.archive_current_buffer(self.config.hdd_root)
        self.logger.shutdown()
        self.hardware.shutdown()
        self.state = OrganState.STOPPED

    def __enter__(self) -> "InfrastructureOrgan":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()

    # ---- event dispatch --------------------------------------------------

    def subscribe_events(self, callback: Callable[[InfraEvent], None]) -> str:
        sub_id = str(uuid.uuid4())
        with self._sub_lock:
            self._subscribers[sub_id] = callback
        return sub_id

    def unsubscribe_events(self, sub_id: str) -> bool:
        with self._sub_lock:
            return self._subscribers.pop(sub_id, None) is not None

    def _dispatch_event(self, event: InfraEvent) -> None:
        with self._sub_lock:
            callbacks = list(self._subscribers.values())
        for cb in callbacks:
            try:
                cb(event)
            except Exception as exc:  # pragma: no cover
                _LOGGER.error("Event subscriber raised: %s", exc)

    def _apply_state_hint(self, hint: str) -> None:
        if self.state in (OrganState.SHUTTING_DOWN, OrganState.STOPPED):
            return
        if hint == "DEGRADED":
            self.state = OrganState.DEGRADED
        elif hint == "THROTTLED" and self.state != OrganState.DEGRADED:
            self.state = OrganState.THROTTLED
            self.scheduler.set_quota_class(QuotaClass.LOW_PRIORITY)
        elif hint == "OPERATIONAL" and self.state == OrganState.THROTTLED:
            self.state = OrganState.OPERATIONAL
            self.scheduler.set_quota_class(QuotaClass.NORMAL)

    # ---- public contract ----------------------------------------------

    def get_hardware_status(self) -> HardwareStatus:
        return self.hardware.snapshot()

    def allocate_quota(self, request: QuotaRequest) -> QuotaGrant:
        return self.scheduler.allocate(request)

    def release_quota(self, grant_id: str) -> bool:
        return self.scheduler.release(grant_id)

    def append_log(self, entry: LogEntry) -> bool:
        self.logger.write(entry)
        return True

    def initiate_download(self, request: DownloadRequest) -> DownloadHandle:
        return self.downloads.download(request)

    def route_outbound(self, request: APIRequest) -> APIResponse:
        return self.gateway.route(request)

    def get_version(self) -> VersionManifest:
        return self.versions.get_manifest()

    def archive(self, request: ArchivalRequest) -> ArchivalStatus:
        return self.filesystem.archive_file(request)


# ═══════════════════════════════════════════════════════════════════════
# Manual smoke test (not part of the public contract)
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":  # pragma: no cover
    with InfrastructureOrgan() as infra:
        print(infra.get_hardware_status())
        infra.append_log(
            LogEntry(
                execution_id=str(uuid.uuid4()),
                responsible_component="smoke_test",
                agent_model=None,
                task_description="Manual verification of Organ 09 boot sequence.",
            )
        )
        print(infra.get_version())
        time.sleep(1.5)
        print("State:", infra.state)
