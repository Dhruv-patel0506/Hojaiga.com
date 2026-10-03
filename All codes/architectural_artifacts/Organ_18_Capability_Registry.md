# Organ 18 — Capability Registry

**Document ID:** SPEC-AOS-CAPREG-001
**System:** Hojaiga Automation Operating System (AOS)
**Organ:** Capability Registry
**Status:** Production
**Implementation File:** `organ_18_capability_registry.py`
**Test File:** `test_organ_18_capability_registry.py`

---

## 1. Purpose

The Capability Registry is the system-wide discovery service for Hojaiga. It
maintains a searchable, indexed, and audited catalog of every capability
provided by organs, runtime services, connectors, plugins, AI models, and
future extensions. No component hardcodes another component's concrete
implementation — every consumer queries the Capability Registry to locate,
validate, rank, and resolve the optimal provider for an operational intent.

Authority order followed: Constitution → Law Book → Diagrams (Inner + Upper)
→ Legacy Code Migration Guide → Policy Manual → Master Architecture Blueprint
→ Organ Specification → Capability Registry Architecture Specification.

---

## 2. Scope

**In scope:** registration, discovery, metadata indexing, attribute/tag/semantic
search, health tracking, version compatibility validation, provider ranking,
permission-gated resolution, audit, history, metrics, recovery.

**Out of scope:** execution of provider logic (handled by the resolved
Organ/Plugin/Connector), hardware resource allocation (Resource Manager),
task execution ordering (Task Scheduler).

---

## 3. Architecture Diagrams

### 3.1 Component View

```
                        Hojaiga Brain / Any Organ
                                  |
                          Capability Query
                                  v
+----------------------------------------------------------------------+
|                        CAPABILITY REGISTRY CORE                      |
|   L1 Cache -> Search Engine -> Permissions & Validator                |
|   Capability DB <-> Compatibility Validator -> Ranking Engine         |
|   Dynamic Reg/Removal Mgr, Health Monitor, Capability Resolver        |
|   History Mgr, Metrics Mgr, Audit Manager                             |
|                                                                        |
|   Sockets: Capability, Discovery, Search, Registration, Validation,   |
|            Permission, Ranking, Health                                |
|   Pipelines: Registration, Search, Validation, Ranking, Discovery,    |
|              Update, Removal, Recovery, Monitoring                    |
+----------------------------------------------------------------------+
                                  |
                     Selected Provider Record / Handle
                                  v
                        Hojaiga Brain / Calling Organ
```

### 3.2 Resolution Sequence

```
Caller -> process_query(QueryDTO)
       -> CacheManager.get(hash)                      [hit -> return]
       -> SearchEngine.search(QueryDTO)                -> candidates
       -> PermissionsManager.filter(candidates, scope) -> permitted
       -> CapabilityValidator + CompatibilityValidator -> valid/compatible
       -> HealthMonitor.filter_healthy(compatible)     -> healthy
       -> RankingEngine.rank(healthy)                  -> ranked
       -> CapabilityResolver.build_handle(ranked[0])   -> InvocationHandle
       -> CacheManager.put(hash, handle)
       -> AuditManager.record(event)
       -> return handle
```

### 3.3 Registration State Machine

```
[*] -> Unregistered -> Validating -> Rejected (schema/security fail)
                                  -> Registering -> Active
Active -> Degraded -> Active (health restored)
Active -> Offline -> Active (provider restored)
Active -> Deprecated -> Tombstoned -> [*] (evicted)
Active -> Tombstoned (dynamic removal)
```

---

## 4. Modules Implemented

| Module | Class | Responsibility |
|---|---|---|
| Capability Core | `CapabilityRegistryCore` | Orchestrator, public entrypoint |
| Capability Registry / DB | `CapabilityDatabase` | Record store + inverted indices |
| Capability Resolver | `CapabilityResolver` | Builds `CapabilityInvocationHandle` |
| Search Engine | `SearchEngine` | Attribute/tag/semantic candidate search |
| Capability Validator | `CapabilityValidator` | Structural/schema integrity |
| Compatibility Validator | `CompatibilityValidator` | SemVer, hardware, dependency checks |
| Permissions Manager | `PermissionsManager` | Namespace protection, scope access control |
| Ranking Engine | `CapabilityRankingEngine` | Weighted composite scoring `S_p` |
| Cache Manager | `L1CacheManager` | LRU + TTL query cache |
| Health Monitor | `HealthMonitor` | Heartbeats, error rate, health status |
| History Manager | `HistoryManager` | Append-only mutation event store |
| Audit Manager | `AuditManager` | Tamper-evident SHA-256 signed audit log |
| Metrics Manager | `MetricsManager` | Latency, cache ratio, invocation telemetry |
| Configuration | `CapabilityRegistryConfig` | Hot-loadable operating parameters |
| Recovery | `RecoveryPipeline` | Crash recovery, integrity verification |
| Dynamic Registration/Removal | `RegistrationPipeline` / `RemovalPipeline` | Hot-plug lifecycle |

---

## 5. Sockets

`CapabilitySocket`, `RegistrationSocket`, `DiscoverySocket`, `HealthSocket`,
`SearchSocket`, `ValidationSocket`, `PermissionSocket`, `RankingSocket` — each
implements `ICapabilitySocket.handle(message: dict) -> dict`, matching the
Organ Specification's socket contract requirements (documented boundary,
no direct cross-organ calls).

## 6. Pipelines

`RegistrationPipeline`, `RemovalPipeline`, `SearchPipeline`,
`ValidationPipeline`, `RankingPipeline`, `DiscoveryPipeline`,
`UpdatePipeline`, `RecoveryPipeline`, `MonitoringPipeline`.

---

## 7. Ranking Formula

```
S_p = (w_H * H_p) + (w_P * P_p) + (w_V * V_p) + (w_A * A_p)
    + (w_R * R_p) + (w_U * U_p) + (w_M * M_p)
```

Default weights: Health 0.30, Performance 0.20, User Preference 0.15,
Static Priority 0.10, Version Precision 0.10, Availability 0.10,
Hardware Acceleration 0.05 (sum = 1.0), matching the specification's
default weighting coefficients.

---

## 8. Security

- Reserved namespaces (`organ.brain`, `kernel.*`, `security.*`) require a
  trusted provider key (`PermissionsManager.check_namespace`).
- Every record is SHA-256 signed (`compute_signature`); `verify_integrity()`
  detects tampering.
- Every audit entry is signed and chain-verifiable (`AuditManager.verify_chain`).
- Duplicate `(provider, capability_name, version)` tuples are rejected.

---

## 9. Public Data Contracts

`CapabilitySpecDTO`, `CapabilityRecord`, `SearchQueryDTO`,
`CapabilityInvocationHandle`, `AuditRecord`, `HistoryEntry` — all defined as
typed dataclasses in the implementation file.

Public interfaces: `ICapabilityResolver`, `ICapabilityRegistryManager`,
`ICapabilityRankingEngine`, `ICapabilitySocket`.

---

## 10. Testing

`test_organ_18_capability_registry.py` — 14 unit tests covering
registration, duplicate rejection, namespace security, deregistration,
unresolved-capability handling, health-based ranking, user-pin ranking,
cache-hit stability, fallback resolution, permission gating, audit-chain
verification, recovery, and dependency gating.

Result: **14/14 passing.**

Run:

```bash
python3 -m unittest test_organ_18_capability_registry.py -v
```

---

## 11. Independence & Compliance

- No dependency on another organ's private implementation — only the
  documented socket/pipeline surface is exposed.
- Complies with Law Book Universal Laws 1–12 and Foundational Laws 1–14
  (traceability via Audit/History, single responsibility per module,
  standardized DTOs, least privilege via `PermissionsManager`, append-only
  history, minimal/controlled file footprint — one importable module).
- Complies with Policy Manual Ch. 8/9/14 (structured logging, append-only
  history, protected resource handling).
