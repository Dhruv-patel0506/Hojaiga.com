# Organ 30 — Resource Manager

**Authority:** Constitution → Law Book → Policy Manual → Master Architecture Blueprint → Organ Specification → RESOURCE_MANAGER.md
**Version:** 1.0

---

## Metadata

| Field | Value |
|---|---|
| Organ ID | 30 |
| Organ Name | Resource Manager |
| Layer | Core Service Layer / Resource Management Engine |
| Language | Python 3.10+ |
| Entry Module | `resource_manager.py` |
| Public Entry Class | `ResourceManagerFacade` |

## Purpose

Centralized hardware/software resource orchestrator for the Hojaiga AOS. No
organ, runtime, connector, or agent is permitted to allocate CPU, RAM, GPU,
VRAM, or storage directly. All access is mediated through ticket-based
`LeaseTicket` grants issued by this organ.

## Responsibilities

- Meter and lease CPU threads, system RAM, GPU compute, VRAM, SSD, and HDD.
- Enforce per-subsystem quota ceilings (§7.2 of RESOURCE_MANAGER.md).
- Schedule contended requests using an MLFQ priority formula.
- Monitor hardware telemetry (CPU/RAM/GPU/VRAM/disk) on a background loop.
- Detect and recover from OOM, VRAM exhaustion, GPU thermal throttling, and
  disk exhaustion using documented runbooks.
- Reap expired leases and reclaim their reserved resources automatically.

## Internal Philosophy

The organ performs no reasoning or business logic. It is a pure control
plane: request in, lease ticket out. All state mutation is protected by
re-entrant locks so the organ is safe for concurrent multi-consumer access.

## Internal Modules

| Class | Purpose | Owned State |
|---|---|---|
| `ResourceRegistry` | Thread-safe lease ledger | active/expired lease tickets |
| `QuotaManager` | Per-subsystem ceilings | per-subsystem usage counters |
| `CpuManager` | CPU thread/affinity accounting | reserved CPU % |
| `RamManager` | System RAM accounting | reserved RAM MB |
| `GpuManager` | GPU compute accounting (NVML-backed) | reserved GPU % |
| `VramManager` | VRAM budget accounting | reserved VRAM MB |
| `DiskManager` | SSD/HDD accounting | reserved SSD/HDD MB |
| `ThreadManager` | Global thread ceiling | active thread count |
| `PriorityScheduler` | MLFQ queue for denied requests | pending request queue |
| `MonitoringEngine` | Background telemetry + alerting | latest metrics snapshot |
| `RecoveryManager` | Failure/fallback runbooks | none (stateless handlers) |
| `ResourceCore` | Orchestrates all of the above | composition root |
| `SocketBus` / `ResourceSocket` | Documented socket surface | bound handlers |
| `ResourceManagerFacade` | Public organ boundary (`IResourceManager`) | none |

## Folder Structure

```
aos/resource_manager/
├── resource_manager.py        # single importable implementation
├── config/
│   └── resource_manager.json  # default runtime configuration
├── tests/
│   └── test_resource_manager.py
└── docs/
    └── ORGAN_30_RESOURCE_MANAGER.md
```

## Public Interfaces

`ResourceManagerFacade` (mirrors `IResourceManager` from §18.2):

```python
facade = ResourceManagerFacade(config=load_config()).start()

ticket = facade.request_resource_lease(ResourceRequestSpec(
    subsystem_id="automation",
    priority=ResourcePriority.NORMAL,
    cpu_threads_requested=2,
    ram_bytes_requested=512 * 1024 * 1024,
    lease_duration_ms=60_000,
))

facade.renew_lease(ticket.lease_id, extend_duration_ms=30_000)
facade.release_lease(ticket.lease_id)
facade.get_global_resource_health()   # -> float 0-100
facade.stop()
```

Errors are surfaced via `LeaseTicket.error_message` and `LeaseTicket.state`
(`GRANTED`, `QUEUED`, `DENIED`, `RELEASED`, `EXPIRED`). No exceptions are
raised for capacity saturation — the request is queued and drained by the
`PriorityScheduler` as capacity frees up (Failure Transparency, Universal
Law 8).

## Internal Interfaces / Socket Definitions

| Socket | Direction | Timeout | Retry |
|---|---|---|---|
| Resource Socket | In/Out | 2000ms | 3 |
| CPU Socket | In/Out | 1000ms | 2 |
| GPU Socket | In/Out | 5000ms | 2 |
| Memory Socket | In/Out | 1000ms | 3 |
| Disk Socket | In/Out | 2000ms | 2 |
| Monitoring Socket | Outbound | 1000ms | 0 |
| Scheduler Socket | In/Out | 2000ms | 3 |
| Quota Socket | In/Out | 2000ms | 2 |

Each socket is emulated in-process via `ResourceSocket.send(message)` and
bound to a handler in `ResourceManagerFacade._wire_sockets`. Retries are
enforced at the socket boundary, not inside `ResourceCore`.

## Pipeline Definitions

`Request → Validation (Quota + Hardware) → Scheduling (if denied) →
Allocation → Registry Commit → Audit Log`. Release follows the mirror path:
`Release → Deallocation → Quota Release → Queue Drain → Audit Log`.

## Incoming / Outgoing Connections

- **Incoming:** Kernel and all Subsystem Consumers (Organs, Runtimes,
  Connectors, Shared Services) via the Resource Socket.
- **Outgoing:** Monitoring Socket streams telemetry to any subscribed
  observer (e.g., a future Logging organ); Recovery actions are internal.

## Data Contracts

`ResourceRequestSpec` and `LeaseTicket` (see §18.2 of RESOURCE_MANAGER.md);
implemented as Python `dataclasses` in `resource_manager.py`.

## State Management

All mutable state lives inside re-entrant-locked manager instances owned by
`ResourceCore`. No module-level mutable globals are used except the
`DEFAULT_QUOTAS` table, which is copied per `QuotaManager` instance.

## Events

`lease_granted`, `lease_queued`, `lease_released`, `lease_renewed`,
`lease_denied`, `health_alert`, `recovery_start`, `recovery_complete`,
`recovery_failed` — all emitted as structured JSON audit log lines.

## Thread Safety

Every manager guards its mutable state with `threading.RLock`. The
`MonitoringEngine` and lease-reaper run on dedicated daemon threads and only
communicate with `ResourceCore` through its locked public methods.

## Resource Management (of the Resource Manager itself)

The organ's own footprint is bounded: it holds only lease ledgers and
rolling telemetry (no unbounded history in-memory — persistence of history
is delegated to a future Logging/History organ via the Monitoring Socket).

## Performance Targets

- Allocation ticket latency: < 1.0 ms (in-process; no I/O on the hot path).
- Telemetry polling overhead: default 500ms interval, configurable.
- Static memory footprint: no large buffers held; scales with active lease
  count only.

## Hardware Considerations

| Resource | Baseline |
|---|---|
| CPU | Intel Core i7 (P/E-core aware via thread-percentage accounting) |
| RAM | 32GB, OOM threshold 92% |
| GPU | NVIDIA RTX 3050, optional NVML telemetry (`pynvml`), degrades to CPU fallback when absent |
| VRAM | 4GB, exhaustion threshold 95%, idle purge available |
| SSD | Runtime partition, capacity alert < 5% free |
| HDD | External model/archive repository |

## SSD / HDD / GPU / Memory Usage

Handled by `DiskManager` (SSD + HDD paths from config), `GpuManager` (NVML
optional), `VramManager`, and `RamManager` respectively — see Internal
Modules table above.

## Logging

Structured JSON-line audit logging via `_audit()`; append-only, written to
stdout and, when `log_path` is supplied, to a rotated-by-caller log file.

## Versioning

This organ implements RESOURCE_MANAGER.md v1.0 against Organ Specification
v1.0. Public dataclass contracts (`ResourceRequestSpec`, `LeaseTicket`) are
additive-only across minor versions.

## Security

Least-privilege is enforced structurally: consumers never touch hardware
managers directly, only `ResourceManagerFacade`. Socket authentication
tokens are a documented contract point for the future Security organ to
inject via socket handler wrapping.

## Failure Recovery

Implements the Failure Recovery & Fallback Matrix (§10): RAM pressure,
VRAM exhaustion, GPU thermal throttling, and SSD capacity exhaustion each
have a dedicated `RecoveryManager` runbook triggered by `MonitoringEngine`
alerts.

## Validation

Every lease request is validated against both the subsystem quota table and
live hardware headroom before being granted; failing either results in a
non-throwing `QUEUED`/`DENIED` ticket rather than an exception.

## Testing

See `tests/test_resource_manager.py` — 17 unit/integration tests covering
quota enforcement, MLFQ scheduling/aging, all hardware managers, lease
grant/release/renew/expiry, socket bus dispatch, and global health scoring.
Run with:

```
python3 -m unittest aos.resource_manager.tests.test_resource_manager -v
```

## Extension Points

- Swap `GpuManager`'s NVML backend for DirectML/ONNX to support non-NVIDIA
  accelerators without changing the public `IAccelerator`-style surface.
- `SocketBus` sockets can be rebound to real ZeroMQ/named-pipe transports
  for out-of-process deployment without touching `ResourceCore`.

## Future Roadmap

- Persist audit logs to the History organ via a dedicated pipeline.
- Multi-GPU (`vgpu:N`) ordinal support in `GpuManager`.
- Distributed worker pool scaling via the documented RPC socket contract.

## Implementation Checklist

- [x] Resource Core, Registry, Quota Manager
- [x] CPU / RAM / GPU / VRAM / Disk / Thread managers
- [x] MLFQ Priority Scheduler
- [x] Monitoring Engine with alerting
- [x] Recovery Manager runbooks
- [x] Socket Bus (8 documented sockets)
- [x] Public Facade (`IResourceManager` surface)
- [x] Configuration loader + default JSON config
- [x] Unit + integration tests (17/17 passing)
- [x] Documentation
