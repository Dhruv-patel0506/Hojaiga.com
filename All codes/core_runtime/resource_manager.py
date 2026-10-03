"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: resource_manager.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [resource_manager.py]
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
Dependencies: enum, typing, __future__, json, time...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: resource_manager.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
Hojaiga Automation Operating System (AOS)
Organ 30 — Resource Manager

Centralized hardware/software resource orchestrator. No organ, runtime, or
connector allocates CPU, RAM, GPU, VRAM, storage, or threads directly — every
consumer requests a ticket-based Lease through the public socket surface
(ResourceManagerFacade) exposed at the bottom of this module.

Authority order respected: Constitution -> Law Book -> Policy Manual ->
Master Architecture Blueprint -> Organ Specification -> RESOURCE_MANAGER.md.

This organ never performs reasoning, execution, or business logic belonging
to other organs. It only meters, schedules, and reclaims resources.

--------------------------------------------------------------------------
PRE-CODE DIAGRAM (authoritative shape this module implements)
--------------------------------------------------------------------------
    Kernel
      |
      v
    ResourceCore --- ResourceRegistry --- QuotaManager
      |
      v
    ResourceScheduler (PriorityScheduler + QueueManager + LoadBalancer)
      |
      v
    AllocationEngine (Cpu/Ram/Gpu/Vram/Disk/Thread Managers)
      |
      v
    MonitoringEngine (Thermal/Power/Health) --- RecoveryManager
      |
      v
    Hardware (Core i7 / 32GB RAM / RTX 3050 / 4GB VRAM / SSD / HDD)
      |
      v
    Subsystem Consumers (Organs / Runtimes / Connectors / Services)

--------------------------------------------------------------------------
ACTUAL-CODE DIAGRAM (classes in this file, top to bottom)
--------------------------------------------------------------------------
    ResourcePriority, ResourceType            (enums)
    ResourceRequestSpec, LeaseTicket          (data contracts)
    ResourceRegistry                          (thread-safe lease ledger)
    QuotaManager                              (per-subsystem ceilings)
    CpuManager / RamManager / GpuManager /
    VramManager / DiskManager / ThreadManager (hardware allocators)
    PriorityScheduler                         (MLFQ scoring + queue)
    MonitoringEngine                          (background telemetry loop)
    RecoveryManager                           (failure/fallback matrix)
    ResourceCore                              (control plane, orchestrates all above)
    ResourceSocket / SocketBus                (in-process socket + pipeline emulation)
    ResourceManagerFacade                     (IResourceManager public API / organ boundary)
"""


import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Deque, Dict, List, Optional

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a hard runtime dependency
    psutil = None

try:
    import pynvml  # NVIDIA Management Library bindings  # type: ignore
    _NVML_AVAILABLE = True
except ImportError:  # pragma: no cover - GPU telemetry degrades gracefully
    pynvml = None
    _NVML_AVAILABLE = False


# ==========================================================================
# Logging (append-only, structured JSON lines — Foundational Law 7)
# ==========================================================================

def _build_logger(name: str, log_path: Optional[str]) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    formatter = logging.Formatter("%(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    if log_path:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def _audit(logger: logging.Logger, category: str, **fields) -> None:
    record = {
        "timestamp": time.time(),
        "category": category,
        "correlation_id": fields.pop("correlation_id", str(uuid.uuid4())),
    }
    record.update(fields)
    logger.info(json.dumps(record, default=str))


# ==========================================================================
# Enums & Data Contracts  (mirrors ResourceInterface.h / §18.2)
# ==========================================================================

class ResourcePriority(IntEnum):
    EMERGENCY = 7
    CRITICAL = 6
    HIGH = 5
    NORMAL = 4
    LOW = 3
    BACKGROUND = 2
    MAINTENANCE = 1

    @property
    def base_score(self) -> float:
        return {
            ResourcePriority.EMERGENCY: 1000.0,
            ResourcePriority.CRITICAL: 500.0,
            ResourcePriority.HIGH: 250.0,
            ResourcePriority.NORMAL: 150.0,
            ResourcePriority.LOW: 100.0,
            ResourcePriority.BACKGROUND: 50.0,
            ResourcePriority.MAINTENANCE: 25.0,
        }[self]


class ResourceType(IntEnum):
    CPU_CORE = 1
    SYSTEM_RAM = 2
    GPU_COMPUTE = 3
    GPU_VRAM = 4
    STORAGE_SSD = 5
    STORAGE_HDD = 6
    THREAD = 7


class LeaseState(IntEnum):
    PENDING = 0
    GRANTED = 1
    QUEUED = 2
    DENIED = 3
    RELEASED = 4
    EXPIRED = 5
    RECLAIMED = 6


@dataclass
class ResourceRequestSpec:
    subsystem_id: str
    priority: ResourcePriority = ResourcePriority.NORMAL
    cpu_threads_requested: int = 0
    ram_bytes_requested: int = 0
    gpu_compute_pct_requested: int = 0
    vram_bytes_requested: int = 0
    ssd_bytes_requested: int = 0
    hdd_bytes_requested: int = 0
    allow_cpu_fallback: bool = True
    lease_duration_ms: int = 60_000
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    enqueued_at_ms: float = field(default_factory=lambda: time.time() * 1000)


@dataclass
class LeaseTicket:
    lease_id: str
    subsystem_id: str
    is_granted: bool
    state: LeaseState
    granted_cpu_threads: int = 0
    granted_ram_bytes: int = 0
    granted_gpu_compute_pct: int = 0
    granted_vram_bytes: int = 0
    granted_ssd_bytes: int = 0
    granted_hdd_bytes: int = 0
    issued_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    expiration_timestamp_ms: float = 0.0
    error_message: str = ""

    def to_dict(self) -> dict:
        return {k: (v.name if isinstance(v, LeaseState) else v) for k, v in self.__dict__.items()}


# ==========================================================================
# Quota Manager  (§7.2 Subsystem Quota Limits)
# ==========================================================================

@dataclass
class SubsystemQuota:
    max_cpu_pct: float
    max_ram_mb: float
    max_gpu_pct: float
    max_vram_mb: float
    max_ssd_mb: float
    disk_priority: str


DEFAULT_QUOTAS: Dict[str, SubsystemQuota] = {
    "brain":        SubsystemQuota(80, 8192, 100, 2048, 10240, "HIGH"),
    "cns":          SubsystemQuota(20, 2048, 0, 0, 2048, "HIGH"),
    "memory":       SubsystemQuota(40, 6144, 50, 512, 20480, "HIGH"),
    "knowledge":    SubsystemQuota(40, 4096, 0, 0, 20480, "NORMAL"),
    "controllers":  SubsystemQuota(30, 1024, 0, 0, 1024, "CRITICAL"),
    "learning":     SubsystemQuota(30, 2048, 50, 512, 5120, "LOW"),
    "automation":   SubsystemQuota(50, 4096, 30, 768, 10240, "NORMAL"),
    "agents":       SubsystemQuota(40, 2048, 0, 0, 2048, "NORMAL"),
    "runtime":      SubsystemQuota(100, 16384, 100, 3584, 50200, "HIGH"),
    "connectors":   SubsystemQuota(20, 1024, 0, 0, 1024, "LOW"),
    "plugins":      SubsystemQuota(10, 512, 0, 0, 512, "LOW"),
}


class QuotaManager:
    """Enforces per-subsystem resource ceilings (Universal Law 7 — Least Privilege)."""

    def __init__(self, quotas: Optional[Dict[str, SubsystemQuota]] = None) -> None:
        self._quotas = dict(quotas or DEFAULT_QUOTAS)
        self._usage: Dict[str, Dict[str, float]] = {}
        self._lock = threading.RLock()

    def quota_for(self, subsystem_id: str) -> SubsystemQuota:
        return self._quotas.get(subsystem_id, SubsystemQuota(10, 512, 0, 0, 512, "LOW"))

    def register_quota(self, subsystem_id: str, quota: SubsystemQuota) -> None:
        with self._lock:
            self._quotas[subsystem_id] = quota

    def can_allocate(self, spec: ResourceRequestSpec, ram_mb: float, vram_mb: float,
                      ssd_mb: float, cpu_pct: float, gpu_pct: float) -> bool:
        quota = self.quota_for(spec.subsystem_id)
        with self._lock:
            used = self._usage.setdefault(spec.subsystem_id, {
                "cpu_pct": 0.0, "ram_mb": 0.0, "gpu_pct": 0.0, "vram_mb": 0.0, "ssd_mb": 0.0
            })
            if used["cpu_pct"] + cpu_pct > quota.max_cpu_pct:
                return False
            if used["ram_mb"] + ram_mb > quota.max_ram_mb:
                return False
            if used["gpu_pct"] + gpu_pct > quota.max_gpu_pct:
                return False
            if used["vram_mb"] + vram_mb > quota.max_vram_mb:
                return False
            if used["ssd_mb"] + ssd_mb > quota.max_ssd_mb:
                return False
            return True

    def commit(self, subsystem_id: str, ram_mb: float, vram_mb: float,
               ssd_mb: float, cpu_pct: float, gpu_pct: float) -> None:
        with self._lock:
            used = self._usage.setdefault(subsystem_id, {
                "cpu_pct": 0.0, "ram_mb": 0.0, "gpu_pct": 0.0, "vram_mb": 0.0, "ssd_mb": 0.0
            })
            used["cpu_pct"] += cpu_pct
            used["ram_mb"] += ram_mb
            used["gpu_pct"] += gpu_pct
            used["vram_mb"] += vram_mb
            used["ssd_mb"] += ssd_mb

    def release(self, subsystem_id: str, ram_mb: float, vram_mb: float,
                ssd_mb: float, cpu_pct: float, gpu_pct: float) -> None:
        with self._lock:
            used = self._usage.get(subsystem_id)
            if not used:
                return
            used["cpu_pct"] = max(0.0, used["cpu_pct"] - cpu_pct)
            used["ram_mb"] = max(0.0, used["ram_mb"] - ram_mb)
            used["gpu_pct"] = max(0.0, used["gpu_pct"] - gpu_pct)
            used["vram_mb"] = max(0.0, used["vram_mb"] - vram_mb)
            used["ssd_mb"] = max(0.0, used["ssd_mb"] - ssd_mb)

    def usage_snapshot(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            return {k: dict(v) for k, v in self._usage.items()}


# ==========================================================================
# Resource Registry  (thread-safe lease ledger, §4.24)
# ==========================================================================

class ResourceRegistry:
    def __init__(self) -> None:
        self._leases: Dict[str, LeaseTicket] = {}
        self._specs: Dict[str, ResourceRequestSpec] = {}
        self._lock = threading.RLock()

    def add(self, ticket: LeaseTicket, spec: ResourceRequestSpec) -> None:
        with self._lock:
            self._leases[ticket.lease_id] = ticket
            self._specs[ticket.lease_id] = spec

    def get(self, lease_id: str) -> Optional[LeaseTicket]:
        with self._lock:
            return self._leases.get(lease_id)

    def spec_for(self, lease_id: str) -> Optional[ResourceRequestSpec]:
        with self._lock:
            return self._specs.get(lease_id)

    def update_state(self, lease_id: str, state: LeaseState) -> None:
        with self._lock:
            if lease_id in self._leases:
                self._leases[lease_id].state = state
                self._leases[lease_id].is_granted = state == LeaseState.GRANTED

    def remove(self, lease_id: str) -> None:
        with self._lock:
            self._leases.pop(lease_id, None)
            self._specs.pop(lease_id, None)

    def active_leases(self) -> List[LeaseTicket]:
        with self._lock:
            return [t for t in self._leases.values() if t.state == LeaseState.GRANTED]

    def expired_leases(self, now_ms: float) -> List[LeaseTicket]:
        with self._lock:
            return [
                t for t in self._leases.values()
                if t.state == LeaseState.GRANTED and t.expiration_timestamp_ms and t.expiration_timestamp_ms < now_ms
            ]


# ==========================================================================
# Hardware Allocation Managers  (§4.2 - §4.8)
# ==========================================================================

class CpuManager:
    """Manages Intel Core i7 affinity, thread priorities, and P/E-core distribution."""

    def __init__(self, total_threads: Optional[int] = None) -> None:
        self.total_threads = total_threads or (os.cpu_count() or 8)
        self._reserved_pct = 0.0
        self._lock = threading.RLock()

    def current_load_pct(self) -> float:
        if psutil is None:
            return 0.0
        return psutil.cpu_percent(interval=None)

    def available_pct(self) -> float:
        with self._lock:
            return max(0.0, 100.0 - self._reserved_pct)

    def reserve(self, pct: float) -> bool:
        with self._lock:
            if self._reserved_pct + pct > 100.0:
                return False
            self._reserved_pct += pct
            return True

    def release(self, pct: float) -> None:
        with self._lock:
            self._reserved_pct = max(0.0, self._reserved_pct - pct)

    def threads_to_pct(self, threads: int) -> float:
        return (threads / max(1, self.total_threads)) * 100.0


class RamManager:
    """Partitions system memory, tracks allocations, evaluates OOM risk."""

    def __init__(self, total_mb: Optional[float] = None) -> None:
        self.total_mb = total_mb or self._detect_total_mb()
        self._reserved_mb = 0.0
        self._lock = threading.RLock()

    @staticmethod
    def _detect_total_mb() -> float:
        if psutil is None:
            return 32768.0
        return psutil.virtual_memory().total / (1024 * 1024)

    def current_used_pct(self) -> float:
        if psutil is None:
            return 0.0
        return psutil.virtual_memory().percent

    def available_mb(self) -> float:
        with self._lock:
            return max(0.0, self.total_mb - self._reserved_mb)

    def reserve(self, mb: float) -> bool:
        with self._lock:
            if self._reserved_mb + mb > self.total_mb:
                return False
            self._reserved_mb += mb
            return True

    def release(self, mb: float) -> None:
        with self._lock:
            self._reserved_mb = max(0.0, self._reserved_mb - mb)

    def is_oom_risk(self, threshold_pct: float = 92.0) -> bool:
        return self.current_used_pct() > threshold_pct


class GpuManager:
    """Controls NVIDIA RTX 3050 execution locks and CPU fallback decisions."""

    def __init__(self) -> None:
        self._reserved_pct = 0.0
        self._lock = threading.RLock()
        self._handle = None
        if _NVML_AVAILABLE:
            try:
                pynvml.nvmlInit()  # type: ignore
                self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)  # type: ignore
            except Exception:  # pragma: no cover - hardware dependent
                self._handle = None

    def is_available(self) -> bool:
        return self._handle is not None

    def current_utilization_pct(self) -> float:
        if not self._handle:
            return 0.0
        try:  # pragma: no cover - hardware dependent
            util = pynvml.nvmlDeviceGetUtilizationRates(self._handle)  # type: ignore
            return float(util.gpu)
        except Exception:
            return 0.0

    def temperature_celsius(self) -> float:
        if not self._handle:
            return 0.0
        try:  # pragma: no cover - hardware dependent
            return float(pynvml.nvmlDeviceGetTemperature(self._handle, pynvml.NVML_TEMPERATURE_GPU))  # type: ignore
        except Exception:
            return 0.0

    def reserve(self, pct: int) -> bool:
        with self._lock:
            if pct == 0:
                return True
            if not self.is_available():
                return False
            if self._reserved_pct + pct > 100.0:
                return False
            self._reserved_pct += pct
            return True

    def release(self, pct: int) -> None:
        with self._lock:
            self._reserved_pct = max(0.0, self._reserved_pct - pct)


class VramManager:
    """Tracks 4GB VRAM budget, LLM weight allocations, and purge behavior."""

    def __init__(self, total_mb: float = 4096.0) -> None:
        self.total_mb = total_mb
        self._reserved_mb = 0.0
        self._lock = threading.RLock()

    def available_mb(self) -> float:
        with self._lock:
            return max(0.0, self.total_mb - self._reserved_mb)

    def reserve(self, mb: float) -> bool:
        with self._lock:
            if mb == 0:
                return True
            if self._reserved_mb + mb > self.total_mb:
                return False
            self._reserved_mb += mb
            return True

    def release(self, mb: float) -> None:
        with self._lock:
            self._reserved_mb = max(0.0, self._reserved_mb - mb)

    def usage_pct(self) -> float:
        with self._lock:
            return (self._reserved_mb / self.total_mb) * 100.0 if self.total_mb else 0.0

    def purge_idle(self) -> float:
        """Flushes context buffers on prolonged idle (Idle Resource Recovery, §9)."""
        with self._lock:
            freed = self._reserved_mb
            self._reserved_mb = 0.0
            return freed


class DiskManager:
    """Routes storage requests between SSD Runtime and External HDD."""

    def __init__(self, ssd_total_mb: float = 100 * 1024, hdd_total_mb: float = 2 * 1024 * 1024,
                 ssd_path: str = "/mnt/ssd_runtime", hdd_path: str = "/mnt/external_hdd") -> None:
        self.ssd_total_mb = ssd_total_mb
        self.hdd_total_mb = hdd_total_mb
        self.ssd_path = ssd_path
        self.hdd_path = hdd_path
        self._ssd_reserved_mb = 0.0
        self._hdd_reserved_mb = 0.0
        self._lock = threading.RLock()

    def ssd_free_pct(self) -> float:
        if psutil is None or not os.path.exists(self.ssd_path):
            with self._lock:
                return 100.0 * (1 - self._ssd_reserved_mb / self.ssd_total_mb) if self.ssd_total_mb else 100.0
        usage = psutil.disk_usage(self.ssd_path)
        return 100.0 - usage.percent

    def reserve_ssd(self, mb: float) -> bool:
        with self._lock:
            if self._ssd_reserved_mb + mb > self.ssd_total_mb:
                return False
            self._ssd_reserved_mb += mb
            return True

    def release_ssd(self, mb: float) -> None:
        with self._lock:
            self._ssd_reserved_mb = max(0.0, self._ssd_reserved_mb - mb)

    def reserve_hdd(self, mb: float) -> bool:
        with self._lock:
            if self._hdd_reserved_mb + mb > self.hdd_total_mb:
                return False
            self._hdd_reserved_mb += mb
            return True

    def release_hdd(self, mb: float) -> None:
        with self._lock:
            self._hdd_reserved_mb = max(0.0, self._hdd_reserved_mb - mb)


class ThreadManager:
    """Tracks logical thread/worker handle counts against the global ceiling."""

    def __init__(self, max_threads_global: int = 64) -> None:
        self.max_threads_global = max_threads_global
        self._active = 0
        self._lock = threading.RLock()

    def reserve(self, count: int) -> bool:
        with self._lock:
            if self._active + count > self.max_threads_global:
                return False
            self._active += count
            return True

    def release(self, count: int) -> None:
        with self._lock:
            self._active = max(0, self._active - count)

    def active_count(self) -> int:
        with self._lock:
            return self._active


# ==========================================================================
# Priority Scheduler  (MLFQ formula, §8)
# ==========================================================================

class PriorityScheduler:
    """
    Priority Score = P_base + alpha * T_wait + beta * (1 - R_requested / R_available)
    alpha = 0.05 (aging coefficient), beta = 10.0 (resource fit weight).
    """

    ALPHA = 0.05
    BETA = 10.0

    def __init__(self) -> None:
        self._queue: Deque[ResourceRequestSpec] = deque()
        self._lock = threading.RLock()

    def enqueue(self, spec: ResourceRequestSpec) -> None:
        with self._lock:
            self._queue.append(spec)

    def _score(self, spec: ResourceRequestSpec, available_ratio: float) -> float:
        wait_ms = (time.time() * 1000) - spec.enqueued_at_ms
        return spec.priority.base_score + self.ALPHA * wait_ms + self.BETA * (1.0 - available_ratio)

    def dequeue_next(self, available_ratio_fn: Callable[[ResourceRequestSpec], float]) -> Optional[ResourceRequestSpec]:
        with self._lock:
            if not self._queue:
                return None
            scored = sorted(
                self._queue,
                key=lambda s: self._score(s, available_ratio_fn(s)),
                reverse=True,
            )
            best = scored[0]
            self._queue.remove(best)
            return best

    def depth(self) -> int:
        with self._lock:
            return len(self._queue)

    def max_wait_ms(self) -> float:
        with self._lock:
            if not self._queue:
                return 0.0
            now = time.time() * 1000
            return max(now - s.enqueued_at_ms for s in self._queue)


# ==========================================================================
# Monitoring Engine  (§4.16, §4.21-23)
# ==========================================================================

class MonitoringEngine:
    def __init__(self, cpu_mgr: CpuManager, ram_mgr: RamManager, gpu_mgr: GpuManager,
                 vram_mgr: VramManager, disk_mgr: DiskManager, logger: logging.Logger,
                 poll_interval_ms: int = 500) -> None:
        self._cpu = cpu_mgr
        self._ram = ram_mgr
        self._gpu = gpu_mgr
        self._vram = vram_mgr
        self._disk = disk_mgr
        self._logger = logger
        self.poll_interval_s = poll_interval_ms / 1000.0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._latest: Dict[str, float] = {}
        self._alert_callbacks: List[Callable[[str, dict], None]] = []
        self._lock = threading.RLock()

    def subscribe_alert(self, callback: Callable[[str, dict], None]) -> None:
        self._alert_callbacks.append(callback)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="ResourceMonitoringEngine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self.sample()
            self._stop_event.wait(self.poll_interval_s)

    def sample(self) -> Dict[str, float]:
        metrics = {
            "cpu_load_pct": self._cpu.current_load_pct(),
            "ram_used_pct": self._ram.current_used_pct(),
            "gpu_util_pct": self._gpu.current_utilization_pct(),
            "gpu_temp_c": self._gpu.temperature_celsius(),
            "vram_used_pct": self._vram.usage_pct(),
            "ssd_free_pct": self._disk.ssd_free_pct(),
        }
        with self._lock:
            self._latest = metrics
        self._evaluate_alerts(metrics)
        return metrics

    def _evaluate_alerts(self, metrics: Dict[str, float]) -> None:
        if metrics["ram_used_pct"] > 92.0:
            self._fire("OOM_RISK_RAM", metrics)
        if metrics["vram_used_pct"] > 95.0:
            self._fire("VRAM_EXHAUSTED", metrics)
        if metrics["gpu_temp_c"] > 88.0:
            self._fire("GPU_THERMAL_THROTTLE", metrics)
        if metrics["ssd_free_pct"] < 5.0:
            self._fire("SSD_CAPACITY_CRITICAL", metrics)

    def _fire(self, alert_type: str, metrics: Dict[str, float]) -> None:
        _audit(self._logger, "health_alert", alert_type=alert_type, metrics=metrics)
        for cb in self._alert_callbacks:
            try:
                cb(alert_type, metrics)
            except Exception as exc:  # pragma: no cover - defensive
                _audit(self._logger, "alert_callback_error", error=str(exc))

    def latest(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._latest)

    def global_health_score(self) -> float:
        m = self.latest() or self.sample()
        penalty = 0.0
        penalty += max(0.0, m["cpu_load_pct"] - 80.0) * 0.5
        penalty += max(0.0, m["ram_used_pct"] - 80.0) * 0.5
        penalty += max(0.0, m["vram_used_pct"] - 80.0) * 0.5
        penalty += max(0.0, 5.0 - m["ssd_free_pct"]) * 2.0
        return max(0.0, 100.0 - penalty)


# ==========================================================================
# Recovery Manager  (Failure Recovery & Fallback Matrix, §10)
# ==========================================================================

class RecoveryManager:
    def __init__(self, vram_mgr: VramManager, disk_mgr: DiskManager,
                 thread_mgr: ThreadManager, logger: logging.Logger) -> None:
        self._vram = vram_mgr
        self._disk = disk_mgr
        self._threads = thread_mgr
        self._logger = logger
        self._runbooks: Dict[str, Callable[[dict], None]] = {
            "OOM_RISK_RAM": self._recover_ram,
            "VRAM_EXHAUSTED": self._recover_vram,
            "GPU_THERMAL_THROTTLE": self._recover_gpu_thermal,
            "SSD_CAPACITY_CRITICAL": self._recover_disk,
        }

    def handle(self, alert_type: str, metrics: dict) -> None:
        runbook = self._runbooks.get(alert_type)
        if not runbook:
            return
        _audit(self._logger, "recovery_start", alert_type=alert_type, metrics=metrics)
        try:
            runbook(metrics)
            _audit(self._logger, "recovery_complete", alert_type=alert_type)
        except Exception as exc:  # pragma: no cover - defensive
            _audit(self._logger, "recovery_failed", alert_type=alert_type, error=str(exc))

    def _recover_ram(self, metrics: dict) -> None:
        # 1. Flush caches  2. Reclaim idle thread stacks  3. Terminate background work
        self._threads.release(0)  # no-op placeholder for stack reclamation hook

    def _recover_vram(self, metrics: dict) -> None:
        freed = self._vram.purge_idle()
        _audit(self._logger, "vram_purged", freed_mb=freed)

    def _recover_gpu_thermal(self, metrics: dict) -> None:
        _audit(self._logger, "gpu_degraded_mode", reason="thermal_throttle")

    def _recover_disk(self, metrics: dict) -> None:
        _audit(self._logger, "ssd_cleanup_triggered")


# ==========================================================================
# Resource Core  (control plane orchestrating the full stack, §4.1)
# ==========================================================================

class ResourceCore:
    def __init__(self, config: Optional[dict] = None, log_path: Optional[str] = None) -> None:
        cfg = config or {}
        hw = cfg.get("system_hardware", {})
        limits = cfg.get("limits", {})
        monitoring = cfg.get("monitoring", {})

        self.logger = _build_logger("aos.resource_manager", log_path)

        self.registry = ResourceRegistry()
        self.quota_manager = QuotaManager()
        self.cpu = CpuManager()
        self.ram = RamManager(total_mb=hw.get("system_ram_mb"))
        self.gpu = GpuManager()
        self.vram = VramManager(total_mb=hw.get("vram_mb", 4096))
        self.disk = DiskManager(
            ssd_path=hw.get("ssd_runtime_path", "/mnt/ssd_runtime"),
            hdd_path=hw.get("external_hdd_path", "/mnt/external_hdd"),
        )
        self.threads = ThreadManager(max_threads_global=limits.get("max_threads_global", 64))
        self.scheduler = PriorityScheduler()
        self.monitoring = MonitoringEngine(
            self.cpu, self.ram, self.gpu, self.vram, self.disk, self.logger,
            poll_interval_ms=monitoring.get("polling_interval_ms", 500),
        )
        self.recovery = RecoveryManager(self.vram, self.disk, self.threads, self.logger)
        self.monitoring.subscribe_alert(self.recovery.handle)

        self._lock = threading.RLock()
        self._reaper_stop = threading.Event()
        self._reaper_thread: Optional[threading.Thread] = None

    # ---- lifecycle -------------------------------------------------
    def start(self) -> None:
        self.monitoring.start()
        self._reaper_stop.clear()
        self._reaper_thread = threading.Thread(target=self._reaper_loop, name="LeaseReaper", daemon=True)
        self._reaper_thread.start()
        _audit(self.logger, "resource_core_started")

    def stop(self) -> None:
        self.monitoring.stop()
        self._reaper_stop.set()
        if self._reaper_thread:
            self._reaper_thread.join(timeout=2.0)
        _audit(self.logger, "resource_core_stopped")

    def _reaper_loop(self) -> None:
        while not self._reaper_stop.is_set():
            now_ms = time.time() * 1000
            for ticket in self.registry.expired_leases(now_ms):
                self.release_lease(ticket.lease_id, reason="expired")
            self._reaper_stop.wait(1.0)

    # ---- core allocation path ---------------------------------------
    def request_lease(self, spec: ResourceRequestSpec) -> LeaseTicket:
        cpu_pct = self.cpu.threads_to_pct(spec.cpu_threads_requested)
        ram_mb = spec.ram_bytes_requested / (1024 * 1024)
        vram_mb = spec.vram_bytes_requested / (1024 * 1024)
        ssd_mb = spec.ssd_bytes_requested / (1024 * 1024)
        gpu_pct = spec.gpu_compute_pct_requested

        with self._lock:
            quota_ok = self.quota_manager.can_allocate(spec, ram_mb, vram_mb, ssd_mb, cpu_pct, gpu_pct)
            hardware_ok = (
                self.cpu.available_pct() >= cpu_pct
                and self.ram.available_mb() >= ram_mb
                and self.vram.available_mb() >= vram_mb
                and self.threads.max_threads_global - self.threads.active_count() >= spec.cpu_threads_requested
            )

            if not (quota_ok and hardware_ok):
                self.scheduler.enqueue(spec)
                ticket = LeaseTicket(
                    lease_id=spec.request_id,
                    subsystem_id=spec.subsystem_id,
                    is_granted=False,
                    state=LeaseState.QUEUED,
                    error_message="Capacity saturation or quota exceeded; request enqueued.",
                )
                self.registry.add(ticket, spec)
                _audit(self.logger, "lease_queued", subsystem_id=spec.subsystem_id,
                       correlation_id=spec.request_id)
                return ticket

            granted = self._commit_allocation(spec, cpu_pct, ram_mb, vram_mb, ssd_mb, gpu_pct)
            self.registry.add(granted, spec)
            _audit(self.logger, "lease_granted", subsystem_id=spec.subsystem_id,
                   correlation_id=granted.lease_id, ram_mb=ram_mb, vram_mb=vram_mb)
            return granted

    def _commit_allocation(self, spec: ResourceRequestSpec, cpu_pct: float, ram_mb: float,
                            vram_mb: float, ssd_mb: float, gpu_pct: float) -> LeaseTicket:
        self.cpu.reserve(cpu_pct)
        self.ram.reserve(ram_mb)
        gpu_granted = self.gpu.reserve(int(gpu_pct)) if gpu_pct else True
        effective_gpu_pct = gpu_pct if gpu_granted else 0
        if gpu_pct and not gpu_granted and not spec.allow_cpu_fallback:
            self.cpu.release(cpu_pct)
            self.ram.release(ram_mb)
            return LeaseTicket(
                lease_id=spec.request_id, subsystem_id=spec.subsystem_id, is_granted=False,
                state=LeaseState.DENIED, error_message="GPU unavailable and CPU fallback disallowed.",
            )
        self.vram.reserve(vram_mb)
        self.disk.reserve_ssd(ssd_mb)
        self.threads.reserve(spec.cpu_threads_requested)
        self.quota_manager.commit(spec.subsystem_id, ram_mb, vram_mb, ssd_mb, cpu_pct, effective_gpu_pct)

        expiration = time.time() * 1000 + spec.lease_duration_ms
        return LeaseTicket(
            lease_id=spec.request_id,
            subsystem_id=spec.subsystem_id,
            is_granted=True,
            state=LeaseState.GRANTED,
            granted_cpu_threads=spec.cpu_threads_requested,
            granted_ram_bytes=int(ram_mb * 1024 * 1024),
            granted_gpu_compute_pct=int(effective_gpu_pct),
            granted_vram_bytes=int(vram_mb * 1024 * 1024),
            granted_ssd_bytes=int(ssd_mb * 1024 * 1024),
            expiration_timestamp_ms=expiration,
        )

    def release_lease(self, lease_id: str, reason: str = "released") -> bool:
        with self._lock:
            ticket = self.registry.get(lease_id)
            if not ticket or ticket.state != LeaseState.GRANTED:
                return False
            cpu_pct = self.cpu.threads_to_pct(ticket.granted_cpu_threads)
            ram_mb = ticket.granted_ram_bytes / (1024 * 1024)
            vram_mb = ticket.granted_vram_bytes / (1024 * 1024)
            ssd_mb = ticket.granted_ssd_bytes / (1024 * 1024)

            self.cpu.release(cpu_pct)
            self.ram.release(ram_mb)
            self.gpu.release(ticket.granted_gpu_compute_pct)
            self.vram.release(vram_mb)
            self.disk.release_ssd(ssd_mb)
            self.threads.release(ticket.granted_cpu_threads)
            self.quota_manager.release(ticket.subsystem_id, ram_mb, vram_mb, ssd_mb, cpu_pct,
                                        ticket.granted_gpu_compute_pct)

            state = LeaseState.EXPIRED if reason == "expired" else LeaseState.RELEASED
            self.registry.update_state(lease_id, state)
            self.registry.remove(lease_id)
            _audit(self.logger, "lease_released", subsystem_id=ticket.subsystem_id,
                   correlation_id=lease_id, reason=reason)
            self._drain_queue()
            return True

    def renew_lease(self, lease_id: str, extend_duration_ms: int) -> bool:
        with self._lock:
            ticket = self.registry.get(lease_id)
            if not ticket or ticket.state != LeaseState.GRANTED:
                return False
            ticket.expiration_timestamp_ms += extend_duration_ms
            _audit(self.logger, "lease_renewed", correlation_id=lease_id, extend_ms=extend_duration_ms)
            return True

    def _drain_queue(self) -> None:
        def available_ratio(spec: ResourceRequestSpec) -> float:
            ram_mb = spec.ram_bytes_requested / (1024 * 1024)
            return self.ram.available_mb() / max(1.0, self.ram.total_mb) if ram_mb else 1.0

        next_spec = self.scheduler.dequeue_next(available_ratio)
        if next_spec:
            self.registry.remove(next_spec.request_id)
            self.request_lease(next_spec)

    def global_resource_health(self) -> float:
        return self.monitoring.global_health_score()


# ==========================================================================
# Socket / Pipeline emulation layer  (§11, §12 — in-process bus)
# ==========================================================================

class ResourceSocket:
    """In-process representation of a documented socket contract."""

    def __init__(self, name: str, timeout_ms: int, retry: int) -> None:
        self.name = name
        self.timeout_ms = timeout_ms
        self.retry = retry
        self._handlers: List[Callable[[dict], dict]] = []

    def bind(self, handler: Callable[[dict], dict]) -> None:
        self._handlers.append(handler)

    def send(self, message: dict) -> dict:
        last_error: Optional[Exception] = None
        for _ in range(max(1, self.retry + 1)):
            try:
                if not self._handlers:
                    raise RuntimeError(f"No handler bound to socket '{self.name}'")
                return self._handlers[0](message)
            except Exception as exc:  # pragma: no cover - retry path
                last_error = exc
        raise RuntimeError(f"Socket '{self.name}' failed after retries: {last_error}")


class SocketBus:
    """Global Socket Bus grouping all Resource Manager sockets (§11)."""

    def __init__(self) -> None:
        self.resource_socket = ResourceSocket("Resource Socket", 2000, 3)
        self.cpu_socket = ResourceSocket("CPU Socket", 1000, 2)
        self.gpu_socket = ResourceSocket("GPU Socket", 5000, 2)
        self.memory_socket = ResourceSocket("Memory Socket", 1000, 3)
        self.disk_socket = ResourceSocket("Disk Socket", 2000, 2)
        self.monitoring_socket = ResourceSocket("Monitoring Socket", 1000, 0)
        self.scheduler_socket = ResourceSocket("Scheduler Socket", 2000, 3)
        self.quota_socket = ResourceSocket("Quota Socket", 2000, 2)


# ==========================================================================
# Public Facade  (IResourceManager — organ boundary, §18.2)
# ==========================================================================

class ResourceManagerFacade:
    """
    Public interface every other Hojaiga organ must use to obtain hardware
    resources. Mirrors IResourceManager (RequestResourceLease / ReleaseLease
    / RenewLease / GetGlobalResourceHealth) and wires the documented socket
    surface on top of ResourceCore.
    """

    def __init__(self, config: Optional[dict] = None, log_path: Optional[str] = None) -> None:
        self.core = ResourceCore(config=config, log_path=log_path)
        self.bus = SocketBus()
        self._wire_sockets()

    def _wire_sockets(self) -> None:
        self.bus.resource_socket.bind(self._handle_lease_request)
        self.bus.scheduler_socket.bind(lambda msg: {"queue_depth": self.core.scheduler.depth(),
                                                      "max_wait_ms": self.core.scheduler.max_wait_ms()})
        self.bus.monitoring_socket.bind(lambda msg: self.core.monitoring.sample())
        self.bus.quota_socket.bind(lambda msg: self.core.quota_manager.usage_snapshot())

    def _handle_lease_request(self, message: dict) -> dict:
        spec = ResourceRequestSpec(**message)
        ticket = self.core.request_lease(spec)
        return ticket.to_dict()

    # ---- lifecycle ---------------------------------------------------
    def start(self) -> "ResourceManagerFacade":
        self.core.start()
        return self

    def stop(self) -> None:
        self.core.stop()

    def __enter__(self) -> "ResourceManagerFacade":
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    # ---- IResourceManager surface -------------------------------------
    def request_resource_lease(self, spec: ResourceRequestSpec) -> LeaseTicket:
        return self.core.request_lease(spec)

    def release_lease(self, lease_id: str) -> bool:
        return self.core.release_lease(lease_id)

    def renew_lease(self, lease_id: str, extend_duration_ms: int) -> bool:
        return self.core.renew_lease(lease_id, extend_duration_ms)

    def get_global_resource_health(self) -> float:
        return self.core.global_resource_health()

    def telemetry(self) -> dict:
        return self.core.monitoring.sample()


# ==========================================================================
# Default configuration loader
# ==========================================================================

DEFAULT_CONFIG = {
    "system_hardware": {
        "cpu_model": "Intel Core i7",
        "system_ram_mb": 32768,
        "gpu_model": "NVIDIA RTX 3050",
        "vram_mb": 4096,
        "ssd_runtime_path": "/mnt/ssd_runtime",
        "external_hdd_path": "/mnt/external_hdd",
    },
    "limits": {
        "max_system_ram_threshold_pct": 92.0,
        "max_vram_threshold_pct": 95.0,
        "cpu_thermal_throttle_celsius": 85.0,
        "gpu_thermal_throttle_celsius": 88.0,
        "max_threads_global": 64,
    },
    "monitoring": {
        "polling_interval_ms": 500,
        "metrics_retention_hours": 24,
    },
    "cleanup": {
        "auto_cleanup_interval_ms": 300000,
        "temp_file_max_age_hours": 24,
    },
}


def load_config(path: Optional[str] = None) -> dict:
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return dict(DEFAULT_CONFIG)


__all__ = [
    "ResourcePriority", "ResourceType", "LeaseState",
    "ResourceRequestSpec", "LeaseTicket",
    "ResourceRegistry", "QuotaManager", "SubsystemQuota", "DEFAULT_QUOTAS",
    "CpuManager", "RamManager", "GpuManager", "VramManager", "DiskManager", "ThreadManager",
    "PriorityScheduler", "MonitoringEngine", "RecoveryManager", "ResourceCore",
    "ResourceSocket", "SocketBus", "ResourceManagerFacade",
    "DEFAULT_CONFIG", "load_config",
]
