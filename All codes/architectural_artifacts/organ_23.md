# Organ 23 — Dependency Graph (AOS-DEP)

**Authority:** Constitution → Law Book → Diagrams (Upper/Inner Surface) →
Legacy Migration Guide → Policy Manual → Master Architecture Blueprint →
Organ Specification → `Dependency_Graph.md`

**Version:** 1.0.0
**Files:** `organ_23.py`, `organ_23_test.py`, `organ_23.md`

---

## 1. Purpose

Organ 23 is the authoritative, deterministic relationship model for every
component, organ, service, plugin, and connector in Hojaiga. It governs
startup ordering, shutdown ordering, upgrade/rollback sequencing, failure
blast-radius analysis, and circular-dependency prevention.

## 2. Pre-Code Diagram (Topology)

```
KERNEL
   |
   v
DEPENDENCY GRAPH (AOS-DEP)
   |
   +---------------+---------------+
   |               |               |
DATABASE       VALIDATOR       RESOLVER
   |                               |
   +---------------+---------------+
                   |
                   v
           DEPENDENCY PLANNER
                   |
   +--------+--------+--------+
 ORGANS  RUNTIME  SHARED_SVC  EXTERNAL_CONNECTORS -> PLUGINS
```

## 3. Actual-Code Diagram (Call Flow)

```
DependencyGraphOrgan.register_dependency()
   -> DependencyValidator.validate_record()
        -> CircularDependencyDetector.analyze_edge_insertion()  (Tarjan SCC)
   -> DependencyRegistry.register()
   -> DependencyDatabase.persist_record()  (SQLite, WAL)
   -> SocketBus.publish("dep_core")

DependencyGraphOrgan.compute_startup_sequence()
   -> TopologicalResolver.resolve_execution_order()  (Kahn)
   -> StartupPlanner.generate_startup_sequence()  (wave grouping by depth)

DependencyGraphOrgan.handle_component_failure()
   -> RecoveryPlanner.plan_recovery()  (BFS blast-radius)
   -> SocketBus.publish("dep_recovery")
```

## 4. Module Map

| Section | Class | Responsibility |
|---|---|---|
| Core | `DependencyRegistry` | In-memory registration index |
| Core | `DependencyDatabase` | ACID persistence (SQLite + WAL + history log) |
| Core | `DependencyCache` | TTL query cache |
| Core | `DependencyMetrics` / `DependencyHealth` | Counters and health reporting |
| Analysis | `DependencyValidator` | Structural/policy validation |
| Analysis | `CircularDependencyDetector` | Tarjan SCC cycle detection |
| Analysis | `VersionCompatibilityEngine` | SemVer 2.0.0 range matching |
| Planning | `TopologicalResolver` | Kahn's algorithm execution ordering |
| Planning | `StartupPlanner` / `ShutdownPlanner` | Wave-based boot/teardown sequencing |
| Planning | `UpgradePlanner` / `RollbackPlanner` | Safe live-upgrade + fallback |
| Planning | `RecoveryPlanner` | Blast-radius failure recovery |
| Governance | `ConfigInterface` | Runtime configuration |
| Governance | `AuditManager` | Append-only audit trail |
| Interface | `SocketBus` / `Pipeline` | Inter-organ communication (Universal Law 5) |
| Facade | `DependencyGraphOrgan` | Sole public entry point |

## 5. Dependency Record Schema

Mirrors `Dependency_Graph.md §2.1` exactly: `dependency_id`,
`source_component`, `target_component`, `dependency_type` (21-value enum),
`dependency_strength` (MANDATORY/OPTIONAL/CONDITIONAL),
`version_requirement`, `compatibility_range`, `priority` (0–1000),
`startup_order`, `shutdown_order`, `recovery_order`,
`failure_impact` (FATAL/DEGRADED/ISOLATED/NON_CRITICAL), `owner`,
`registration_date`, `last_updated`. Component identifiers must match
`^[a-z0-9_]+:[a-z0-9_.-]+$`.

## 6. Sockets

`dep_core`, `dep_registry`, `dep_db`, `dep_val`, `dep_res`, `dep_plan`,
`dep_upgrade`, `dep_rollback`, `dep_startup`, `dep_shutdown`,
`dep_recovery`, `dep_circular`, `dep_version`, `dep_aud`.

Other organs subscribe via `organ.socket_bus.subscribe(channel, handler)`
and never touch internal registry/database state directly, per Law Book
Universal Law 7 (Least Privilege) and Universal Law 5 (Standardized
Communication).

## 7. Pipelines

`request_pipeline` = validate → persist → publish, matching
`Dependency_Graph.md §3.1` ("Kernel Event Loop → Authorization
Verification → Registry Ingestion Queue").

## 8. Algorithms

- **Cycle detection:** Tarjan's strongly-connected-components algorithm,
  O(V+E).
- **Execution ordering:** Kahn's algorithm over MANDATORY/CONDITIONAL
  edges only (OPTIONAL edges never block ordering).
- **Boot wave grouping:** longest-path depth over the dependency DAG.
- **Recovery blast radius:** BFS over reverse-dependency edges
  (`get_dependents`).

## 9. Failure Modes & Recovery

| Condition | Behavior |
|---|---|
| Cycle on insertion | `CycleDetectedError`; insertion rejected, prior state untouched |
| Duplicate edge | `ValidationError`; insertion rejected |
| Unresolvable mandatory graph | `ResolutionError` naming the stuck component set |
| Component crash | `RecoveryPlanner` quarantines all transitive dependents, computes minimal restart tree |
| DB corruption | Reload from latest snapshot; history log replay supported via `history()` |
| Upgrade failure | `RollbackPlanner` restores the pre-upgrade checkpoint snapshot |

## 10. Testing Strategy

`organ_23_test.py` (33 tests, all passing):

1. **Unit** — schema validation, Tarjan cycles, Kahn ordering, SemVer
   matching, capability resolution.
2. **Integration** — organ facade registration/persistence round-trip
   (SQLite file-backed), socket event delivery, startup/shutdown wave
   symmetry, upgrade+rollback checkpoint restore.
3. **Chaos** — repeated component-failure handling, blast-radius
   correctness under multi-hop dependent chains.
4. **Graph-wide** — full-graph validation, cycle absence assertions,
   status/metrics reporting.

Run: `python3 -m pytest organ_23_test.py -v`

## 11. Hardware & Performance Notes

CPU-first, no GPU usage (GPU reserved exclusively for Brain inference per
Constitution Article III and hardware target). SQLite WAL mode used for
disk-backed instances; `:memory:` mode for embedded/unit-test use.
Registry mutations are guarded by an `RLock`; the specification's 50 ms
lock-timeout threshold is honored by keeping all critical-path operations
lock-local and allocation-light.

## 12. Independence Guarantee

This organ has no import-time or runtime dependency on any other organ's
internals. All interaction surfaces are the public `DependencyGraphOrgan`
methods and the `SocketBus` channels listed above, in compliance with
Organ Specification's socket/pipeline-only communication rule.
