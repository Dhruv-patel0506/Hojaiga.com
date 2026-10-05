# Organ 10 — Agents

**Version:** 1.0.0
**Authority Order:** Constitution → Law Book → Policy Manual → Master Architecture Blueprint → Organ Specification → Legacy Code Migration Guide → Upper Surface Diagrams → Inner Depth Diagrams
**Implementation File:** `organ_10_agents.py` (single-file, self-contained)

---

## 1. Overview

The Agents Organ is the ephemeral, single-purpose task-execution runtime of Hojaiga. It translates task dispatches routed through the Central Nervous System (CNS) into role-scoped agent workers (`BrowserAgent`, `CodeAgent`, `DocAgent`, `SysAdminAgent`, extensible) that reason via the Brain Organ, invoke tools via the Controllers Organ, and report structured decision traces back to the CNS. It owns no persistent private infrastructure and communicates exclusively through the documented socket and the `CNSGateway` interface boundary.

---

## 2. Agent Hierarchy

```
DOMAIN CONTROLLER (Grandfather — goals, policies, permissions)
        │
ENVIRONMENT CONTROLLER (Father — resources, browser, filesystem, APIs)
        │
EXECUTION CONTROLLER (Child — planner, executor, validator, retry)
        │
        ▼
   AGENTS ORGAN (Organ 10)
        │
        ├── Parent Agent (role-bound worker)
        │        │
        │        └── Child Agent(s) — spawned via DelegationEngine
        │                 └── Grandchild Agent(s) — same mechanism, recursive
        │
        └── Sibling Agents — independent workers under the same task_id,
             isolated by session_room_id and capability_token
```

Agents are ephemeral: spawned per sub-goal, executed to completion or termination, then reclaimed. No agent persists across tasks. Parent–child relationships exist only for delegation traceability (`parent_handle`); a child agent does not inherit its parent's capability grant automatically — it is granted only the capabilities explicitly requested and present in its own role definition (least privilege, Universal Law 7).

---

## 3. Task Distribution

1. CNS dispatches an `AgentSpawnPayload` (`task_id`, `role_id`, `session_room_id`, `assigned_sub_goal`, `allowed_capabilities`, `timeout_ms`).
2. `AgentFactory` validates the role against `RoleRegistry`, intersects requested capabilities with the role's declared capability set, and instantiates a `_WorkerRecord`.
3. `WorkerPool` admits the worker under a bounded `asyncio.Semaphore` sized to the physical CPU core budget (default 8, matching the Intel Core i7 target).
4. `TaskRunner` drives the step loop: bind context → request reasoning → optionally dispatch a tool call → record trace → repeat until `FINISHED`, `FAILED` (after retry budget), `BLOCKED`, timeout, or `max_steps` exhaustion.
5. Parent agents may call `DelegationEngine.spawn_child_agent` to fan out independent sub-goals; each child is an independent entry in the same worker pool and store, subject to the same pool bound.

Distribution is CPU-first: all context assembly, capability checks, and trace packaging execute on host CPU cores. GPU-bound LLM inference is never performed inside this organ — reasoning requests are forwarded through `CNSGateway.request_reasoning`, which is the sole channel to the Brain Organ (`llama.cpp` / Qwen3 8B), and VRAM lifecycle is owned entirely by the Brain Organ.

---

## 4. Permissions

* **Role Capability Masking.** Every worker's `allowed_capabilities` is the intersection of the spawn request's requested set and the role's declared set in `RoleRegistry`. A `DocAgent` cannot request `system.restart_service`; the runner returns `StepStatus.BLOCKED` and terminates the agent (Universal Law 7 — Least Privilege).
* **Capability Token Verification.** Each tool dispatch carries a per-agent `capability_token` (assigned at instantiation) that `CNSGateway.verify_capability_token` must approve before dispatch proceeds. A production gateway routes this check to the Security Organ.
* **No Direct Organ Access.** The Agents Organ never imports Brain, Memory, or Controllers internals. All cross-organ calls are mediated by the `CNSGateway` protocol, satisfying Universal Law 4 (Modularity) and Universal Law 5 (Standardized Communication).
* **Governance Boundary.** Agents cannot modify governing documents, architecture, or configuration (Law Book, Article IV §4 / Foundational Law 12). No code path in this organ writes to `/constitution`, `/lawbook`, `/policies`, or `/architecture`.

---

## 5. Agent Communication

* **Transport:** Length-prefixed binary frames — `[4-byte big-endian length][2-byte op_code][JSON payload]`, max 16 MB per frame, served over a named pipe (`\\.\pipe\hojaiga_agents` on Windows) with a loopback TCP fallback (`127.0.0.1:47010`) preserving the identical frame protocol.
* **RPC Surface (op_codes 1–6):** `SpawnAgent`, `ExecuteAgentStep`, `DelegateSubTask`, `GetAgentStatus`, `TerminateAgent`, `GetActiveAgentsSummary` — matching Organ Specification §7 exactly.
* **Event Emissions (via `CNSGateway.emit_event`):** `EVENT_AGENT_SPAWNED`, `EVENT_AGENT_STARTED`, `EVENT_AGENT_STEP_COMPLETED`, `EVENT_AGENT_DELEGATION_INITIATED`, `EVENT_AGENT_TIMEOUT`, `EVENT_AGENT_FAILED`.
* **Context Sockets:** `ContextScopeManager` binds each `session_room_id` to a pruned rolling window (default 40 items) of conversation/tool history fetched from the Memory Organ via `CNSGateway.fetch_memory_context`, and released on completion.

Nobody calls another organ's function directly. Every interaction — reasoning, tool execution, memory retrieval, event emission, capability verification — passes through the single `CNSGateway` protocol, which is the only extension point a live CNS transport needs to implement.

---

## 6. Worker Model

* **Ephemeral Workers.** Each agent is a coroutine task registered in `WorkerPool`, holding an isolated `_WorkerRecord` (state, capability grant, capability token, room id). No worker survives its task.
* **Concurrency Bound.** `WorkerPool` enforces a hard cap (default 8) via `asyncio.Semaphore`, matching the physical core budget of the target hardware and preventing unbounded thread/coroutine proliferation.
* **State Machine.** `AgentState`: `INSTANTIATED → WAITING_FOR_BRAIN → (WAITING_FOR_TOOL | EXECUTING) → (WAITING_FOR_BRAIN | COMPLETED | TERMINATED)`. Transitions are validated against a fixed transition table (`_VALID_TRANSITIONS`); an illegal transition raises `InvalidStateTransition` rather than silently corrupting state (Universal Law 6 — State Integrity).
* **Retry Budget.** Failed steps retry up to `TaskRunner.MAX_RETRIES` (2) before the agent is terminated and `EVENT_AGENT_FAILED` is emitted.
* **Timeout Enforcement.** Every agent carries a `timeout_ms` deadline; the runner checks the deadline before each step and wraps the reasoning call in `asyncio.wait_for`, terminating and emitting `EVENT_AGENT_TIMEOUT` on breach.
* **Trace Persistence.** Every step is recorded into an in-memory SQLite store (`active_agents`, `agent_traces`) via `TraceCollector`; payloads over 1 MB are flagged for SSD streaming rather than accumulating in RAM (Section 18 Memory Strategy — 512 MB resident cap intent).

---

## 7. Execution Coordination

```
CNS Dispatch
   │
   ▼
AgentsKernel.spawn_agent
   │
   ├─ AgentFactory.instantiate  (role validation, capability intersection)
   ├─ AgentStore.insert_agent   (SQLite runtime record)
   ├─ WorkerPool.register       (bounded semaphore slot reserved on run)
   └─ emit EVENT_AGENT_SPAWNED
   │
   ▼
TaskRunner.run  (bounded by WorkerPool semaphore)
   │
   ├─ ContextScopeManager.bind_room   → Memory Organ (via CNSGateway)
   ├─ loop:
   │     ├─ CNSGateway.request_reasoning → Brain Organ
   │     ├─ capability check (role mask + Security Organ token verify)
   │     ├─ CNSGateway.dispatch_tool     → Controllers Organ
   │     ├─ TraceCollector.record_step   → SQLite + optional SSD stream
   │     └─ emit EVENT_AGENT_STEP_COMPLETED
   │  until FINISHED | FAILED(retry-exhausted) | BLOCKED | TIMEOUT | max_steps
   │
   ├─ DelegationEngine.spawn_child_agent (optional, recursive re-entry into spawn_agent)
   │
   ▼
AgentStatusPayload returned → CNS
   │
   ▼
ContextScopeManager.release  (memory room detached, worker slot freed)
```

Coordination guarantees:
* Single-responsibility separation between instantiation (`AgentFactory`), execution (`TaskRunner`), delegation (`DelegationEngine`), context (`ContextScopeManager`), and audit (`TraceCollector`) — Universal Law 3.
* Deterministic, append-only trace history — Foundational Law 7.
* No architectural mutation performed by any agent at runtime — Foundational Law 1 / Foundational Law 14.

---

## 8. Data Contracts (implemented as `dataclasses`)

* `AgentSpawnPayload`, `AgentStepPayload`, `StepExecutionResult`, `DelegationPayload`, `DelegationHandle`, `AgentStatusPayload`, `TerminationAck`, `AgentSummaryList` — field-for-field equivalents of the JSON Schemas in Organ Specification §15.

---

## 9. Pre-Code Architecture Diagram (Specification Intent)

```
                                   CNS (Organ 02)
                                        │
                              IPC Socket / RPC Contract
                                        │
                                        ▼
                              ┌─────────────────────┐
                              │   agents_core        │
                              │  (Kernel/Registry)    │
                              └──────────┬────────────┘
                                        │
                 ┌──────────────────────┼──────────────────────┐
                 ▼                      ▼                      ▼
        ┌────────────────┐   ┌───────────────────┐   ┌─────────────────┐
        │ agent_factory   │   │  worker_pool       │   │ role_registry    │
        │ (instantiate)   │   │  (scheduler, cap 8)│   │ (role catalog)   │
        └────────┬────────┘   └──────────┬─────────┘   └─────────────────┘
                 │                       │
                 └───────────┬───────────┘
                             ▼
                     ┌──────────────────┐
                     │   task_runner     │◄──────────────┐
                     │ (step loop, retry)│                │
                     └────────┬──────────┘                │
                              │                            │
       ┌──────────────────────┼───────────────────────┐    │
       ▼                      ▼                       ▼    │
┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐
│context_scope_ │    │  delegation_     │    │ trace_collector   │
│  manager       │    │    engine        │    │ (audit payloads)  │
└───────┬────────┘    └────────┬─────────┘    └─────────┬──────────┘
        │                     │                          │
        ▼                     ▼                          ▼
 Memory Organ (CNS)   spawn child → agents_core     SQLite (active_agents,
                                                        agent_traces)
                                        │
                                        ▼
                        Brain Organ (reasoning) / Controllers Organ (tools)
                                (both reached only via CNS)
```

---

## 10. Post-Code Architecture Diagram (As Implemented in `organ_10_agents.py`)

```
                          IPCServer (asyncio TCP :47010 / Windows named pipe)
                                        │  frame: [len|op_code|JSON]
                                        ▼
                              AgentsKernel  (facade: AgentsOrgan)
        ┌───────────────┬───────────────┼───────────────┬───────────────────┐
        ▼               ▼               ▼               ▼                   ▼
  RoleRegistry     AgentStore      WorkerPool      AgentFactory     ContextScopeManager
 (default roles /  (sqlite :memory:  (asyncio        (role+capability   (per-room rolling
  agent_roles.json)  active_agents,   Semaphore(8),    intersection,      context, prune@40,
                      agent_traces)    _WorkerRecord   token issuance)     CNSGateway.fetch_
                                       registry)                           memory_context)
        │                                                                        │
        └──────────────────────────────┬─────────────────────────────────────────┘
                                        ▼
                                  TaskRunner.run
                     (state machine INSTANTIATED→WAITING_FOR_BRAIN→
                      WAITING_FOR_TOOL/EXECUTING→COMPLETED/TERMINATED,
                      MAX_RETRIES=2, per-step + per-agent deadline)
                                        │
                 ┌───────────────────────┼────────────────────────┐
                 ▼                       ▼                        ▼
     CNSGateway.request_reasoning  CNSGateway.dispatch_tool  TraceCollector.record_step
        (→ Brain Organ)          (capability-token gated,      (→ AgentStore.insert_trace,
                                    → Controllers Organ)          SSD-stream flag > 1MB)
                                        │
                                        ▼
                              CNSGateway.emit_event
                (EVENT_AGENT_SPAWNED / STARTED / STEP_COMPLETED /
                 DELEGATION_INITIATED / TIMEOUT / FAILED)
                                        │
                                        ▼
                              DelegationEngine.spawn_child_agent
                          (re-enters AgentsKernel.spawn_agent, new
                           _WorkerRecord, parent_handle linkage)
                                        │
                                        ▼
                      AgentStatusPayload / StepExecutionResult / DelegationHandle
                                  returned to IPCServer → CNS
```

---

## 11. Compliance Checklist

* [x] Modular — every internal module (`AgentFactory`, `RoleRegistry`, `WorkerPool`, `TaskRunner`, `DelegationEngine`, `ContextScopeManager`, `TraceCollector`, `IPCServer`) is independently replaceable behind stable interfaces.
* [x] CPU-first, zero direct GPU usage.
* [x] Least-privilege capability masking + token verification.
* [x] Append-only trace history (SQLite `agent_traces`, insert-only).
* [x] Bounded concurrency (8 workers, matching target CPU).
* [x] Explicit timeout + retry + termination handling.
* [x] Single documented socket (`hojaiga_agents`) with versioned frame protocol.
* [x] No cross-organ private-implementation imports; `CNSGateway` is the sole boundary.
* [x] No architecture, governance, or credential files touched by this organ.
