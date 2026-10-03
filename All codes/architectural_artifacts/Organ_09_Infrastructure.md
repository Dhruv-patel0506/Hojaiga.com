# Organ 09 — Infrastructure Specification Document

**Version:** 1.0.0
**Authority Chain:** Constitution → Law Book → Policy Manual → Master Architecture Blueprint → Organ Specification → Upper Surface Diagrams → Inner Depth Diagrams → Legacy Reference Guide

---

## 1. Metadata

| Field | Value |
|---|---|
| Organ ID | 09 |
| Organ Name | Infrastructure |
| Layer | Kernel / Cross-Cutting Substrate |
| Language | Python 3.11+ |
| Deployment Target | Windows 11, Intel Core i7, RTX 3050 4GB VRAM, 32GB RAM |
| Storage | SSD (runtime) + External HDD (archive) |
| Governance | Universal Law 7, 11 · Policy Manual Ch. 12, 14 |

---

## 2. Purpose

The Infrastructure Organ is the hardware abstraction, resource governance, filesystem, logging, configuration, monitoring, and download substrate of Hojaiga. It isolates every other organ from raw OS/hardware primitives (Universal Law 5 — Standardized Communication) and enforces least-privilege, CPU-first, GPU-reserved-for-Brain execution (Universal Law 7).

The Brain (Qwen3-8B via llama.cpp) is never instantiated inside this organ. Infrastructure only observes GPU/VRAM state; it never loads or manages LLM weights.

---

## 3. Responsibilities

- Hardware telemetry: CPU, RAM, GPU/VRAM, disk.
- Resource quota enforcement (soft, cross-platform; Windows Job Objects where available).
- Append-only structured logging with SSD staging → HDD archival flush.
- Filesystem partitioning: `ssd_runtime/` vs `hdd_archive/`, path traversal protection.
- Bandwidth-aware, checksum-verified downloads/uploads.
- Versioned configuration loading and migration.
- Outbound API gateway with rate limiting, timeouts, circuit breaker.
- Continuous monitoring loop emitting warning/breach events to the CNS Socket.

---

## 4. Socket & Pipeline Contract (Public Interface)

Infrastructure exposes a single in-process facade, `InfrastructureOrgan`, callable by other organs via the documented method contract below (wire-compatible with a future named-pipe/gRPC transport; the transport itself is out of scope for this organ and is provided by the CNS/Interface organs).

| Method | Input | Output |
|---|---|---|
| `get_hardware_status()` | — | `HardwareStatus` |
| `allocate_quota(request)` | `QuotaRequest` | `QuotaGrant` |
| `append_log(entry)` | `LogEntry` | `bool` (ack) |
| `initiate_download(request)` | `DownloadRequest` | `DownloadHandle` |
| `route_outbound(request)` | `APIRequest` | `APIResponse` |
| `get_version()` | — | `VersionManifest` |
| `archive(request)` | `ArchivalRequest` | `ArchivalStatus` |
| `subscribe_events(callback)` | `Callable[[Event], None]` | subscription id |

All events (`EVENT_INFRASTRUCTURE_RESOURCE_WARNING`, `EVENT_STORAGE_QUOTA_BREACH`) are pushed to registered subscribers (the CNS Event Bus in the full system).

---

## 5. State Machine

`BOOTSTRAPPING → OPERATIONAL ⇄ THROTTLED`, `OPERATIONAL ⇄ DEGRADED`, `OPERATIONAL → SHUTTING_DOWN → [terminal]`.

---

## 6. Pre-Code Architecture Diagram (Intended Design, per Specification)

```
                         ┌────────────────────────────┐
                         │   Any Hojaiga Organ         │
                         │ (Brain / CNS / Memory / ...)│
                         └──────────────┬───────────────┘
                                        │ public contract calls
                                        ▼
                         ┌────────────────────────────┐
                         │   INFRASTRUCTURE ORGAN      │
                         │   (infra_kernel facade)     │
                         └──────────────┬───────────────┘
             ┌──────────────┬───────────┼───────────┬──────────────┬────────────┐
             ▼              ▼           ▼           ▼              ▼            ▼
     HardwareController  ResourceScheduler  CentralLogger  FilesystemManager  DownloadManager  APIGateway
             │              │           │           │              │            │
             ▼              ▼           ▼           ▼              ▼            ▼
        CPU/RAM/GPU     Priority/Quota  Ring Buffer  ssd_runtime/  Checksummed  Rate-limited
        (psutil/NVML)   Enforcement     -> SSD ->HDD  hdd_archive/  Transfers    HTTP Egress

                                        │
                                        ▼
                         ┌────────────────────────────┐
                         │  MonitoringEngine (loop)    │
                         │  1000ms telemetry sampling  │
                         └──────────────┬───────────────┘
                                        │ emits
                                        ▼
                         ┌────────────────────────────┐
                         │  Event Subscribers (CNS)    │
                         │  RESOURCE_WARNING / QUOTA   │
                         └────────────────────────────┘

State Machine:
  BOOTSTRAPPING -> OPERATIONAL -> {THROTTLED, DEGRADED} -> OPERATIONAL -> SHUTTING_DOWN
```

---

## 7. Post-Code Architecture Diagram (As Implemented)

```
infrastructure_organ.py
│
├── enums:  OrganState, LogLevel, QuotaClass
├── dataclasses:
│     HardwareStatus, QuotaRequest, QuotaGrant, LogEntry,
│     DownloadRequest, DownloadHandle, APIRequest, APIResponse,
│     VersionManifest, ArchivalRequest, ArchivalStatus, InfraEvent
│
├── InfrastructureConfig            (loads/validates hardware_limits + gateway config)
│     └── from_file() / defaults()
│
├── HardwareController              (psutil CPU/RAM, optional pynvml GPU)
│     ├── query_cpu_and_ram() -> (cpu%, ram%, ram_used_mb)
│     ├── query_vram_usage()  -> (vram_used_mb, vram_total_mb) | None
│     └── snapshot() -> HardwareStatus
│
├── ResourceScheduler                (in-process quota + throttle governor)
│     ├── allocate(request) -> QuotaGrant
│     ├── release(grant_id)
│     └── current_class() -> QuotaClass
│
├── CentralLogger                    (thread-safe ring buffer + async flush worker)
│     ├── write(entry)
│     ├── _flush_worker()   [daemon thread]
│     └── shutdown()
│
├── FilesystemManager                (path partitioning + traversal guard)
│     ├── get_runtime_path(rel) -> Path   [ssd_runtime/]
│     ├── get_archive_path(rel) -> Path   [hdd_archive/]
│     ├── archive_file(request) -> ArchivalStatus
│     └── free_space(path) -> bytes
│
├── DownloadManager                  (checksum-verified, throttled transfer)
│     └── download(request) -> DownloadHandle
│
├── APIGateway                       (rate-limited outbound HTTP + circuit breaker)
│     ├── route(request) -> APIResponse
│     └── _circuit: CircuitBreaker
│
├── VersionManager                   (semantic version + migration manifest)
│     └── get_manifest() -> VersionManifest
│
├── MonitoringEngine                 (background 1000ms loop)
│     ├── start() / stop()
│     └── _loop()  -> emits InfraEvent to InfrastructureOrgan._dispatch_event
│
└── InfrastructureOrgan              (facade / kernel; public contract)
      ├── state: OrganState (BOOTSTRAPPING -> OPERATIONAL -> ... -> SHUTTING_DOWN)
      ├── get_hardware_status()
      ├── allocate_quota() / release_quota()
      ├── append_log()
      ├── initiate_download()
      ├── route_outbound()
      ├── get_version()
      ├── archive()
      ├── subscribe_events() / _dispatch_event()
      ├── start() / shutdown()
      └── __enter__ / __exit__   (context-manager lifecycle)

Runtime Data Flow:
  Organ.append_log(entry)
        -> InfrastructureOrgan.append_log
        -> CentralLogger.write (lockless deque enqueue)
        -> _flush_worker (daemon thread, batched)
        -> ssd_runtime/log_buffer/*.jsonl
        -> periodic archival -> hdd_archive/logs/*.jsonl

  MonitoringEngine._loop (every 1000ms)
        -> HardwareController.snapshot()
        -> threshold check (RAM>85%, VRAM>3.5GB, SSD free<5GB)
        -> InfrastructureOrgan._dispatch_event(InfraEvent)
        -> subscribers notified
        -> OrganState transitions OPERATIONAL <-> THROTTLED / DEGRADED
```

---

## 8. Implementation Files

The implementation is delivered as separate, directly importable files (not embedded in this document):

- `infrastructure_organ.py` — full production implementation of the Infrastructure Organ (HardwareController, ResourceScheduler, CentralLogger, FilesystemManager, DownloadManager, APIGateway, VersionManager, MonitoringEngine, and the `InfrastructureOrgan` public facade).
- `test_infrastructure_organ.py` — pytest suite covering hardware telemetry shape, quota lifecycle, log flush, path-traversal protection, archival failure handling, version manifest, and event subscription.

Import with:

```python
from infrastructure_organ import InfrastructureOrgan, InfrastructureConfig
```

## 9. Dependencies

- `psutil` (CPU/RAM/disk telemetry) — required.
- `pynvml` (NVIDIA VRAM telemetry) — optional; falls back to `nvidia-smi` subprocess, then to `None` if unavailable.
- `requests` (API Gateway egress, downloads) — required for `route_outbound` / `initiate_download`.
- Standard library only otherwise (`threading`, `queue`/`deque`, `hashlib`, `json`, `pathlib`, `dataclasses`, `time`, `enum`, `logging`).

Install: `pip install psutil pynvml requests`

## 10. Documentation Updates

- Registered Organ 09 (Infrastructure) in the runtime hierarchy under `HOJAIGA AUTOMATION OS → Kernel → Infrastructure`, sibling to Memory, Execution Controller, and the Brain runtime, per Master Architecture Blueprint Chapter 9 storage layout and Chapter 3 controller list.
- Socket names reserved for future transport binding: `hojaiga_infrastructure` (named pipe / gRPC), consistent with Organ 09 reference naming; this file implements the in-process facade equivalent (`InfrastructureOrgan`) pending transport wiring by the Interface/CNS organs.
- Events emitted: `EVENT_INFRASTRUCTURE_RESOURCE_WARNING`, `EVENT_STORAGE_QUOTA_BREACH` — both consumed by the CNS Event Bus per Upper Surface Diagram §5 (Communication Architecture) and Inner Depth Diagram (Global Socket Bus).
- GPU/VRAM is read-only telemetry in this organ; VRAM allocation and release remain the exclusive responsibility of the Brain organ (Universal Law 3 — Separation of Responsibility).
