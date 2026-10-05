# Organ 27 — Kernel

**Version:** 1.0.0
**Authority:** Constitution → Law Book → Diagrams → Legacy Guide → Policy Manual → Master Blueprint → Organ Specification

## Purpose
Deterministic orchestration authority for Hojaiga AOS. No AI reasoning, no domain automation.

## Responsibilities
Boot/shutdown sequencing, dependency DAG resolution, organ/service/runtime registries,
resource quota enforcement, heartbeat + recovery, event/socket/pipeline communication,
global scheduling, security boundary checks, state machine enforcement.

## Strict Architectural Directives
- **No Black Box Execution**: The live visualization mirrors real execution events; it does not drive them.
- **Event-Driven Execution Barrier**: Every execution request must go through Brain compilation and CNS approval before any action begins. Nothing advances in the pipeline until the current organ publishes a completion event on the CNS EventBus.
- **Fail-Safe Halt**: If any required event (e.g., compilation, decision approval) is missing or times out, the system must immediately stop and report an `ArchitecturalError`. It must never attempt to bypass the pipeline or execute unverified actions.
- **Intelligence Layer Primacy**: The LLM must reason about user intent *first*, generating a structured JSON execution plan. No raw text or unstructured instructions may go straight to controllers. The Brain's structured plan explicitly dictates controller access and safety checkpoints.

## Public Interfaces
- `KernelCore.register_organ(manifest) -> bool`
- `KernelCore.unregister_organ(name) -> bool`
- `KernelCore.boot() / shutdown(reason)`
- `KernelCore.get_state() -> SystemState`
- `KernelCore.run_heartbeat_cycle()`

## Sockets
Boot Socket, Shutdown Socket, Registry Socket, Heartbeat Socket, Event Socket,
Scheduler Socket, Health Socket, Recovery Socket, Logging Socket — modeled via `SocketBus`.

## Pipelines
`boot`: validate_config → resolve_dependencies → init_registries → transition_running
`shutdown`: flush_state → teardown_organs → finalize_shutdown

## State Diagram
INITIALIZING → STARTING → RUNNING ⇄ {BUSY, IDLE, PAUSED, MAINTENANCE, UPDATING}
RUNNING → RECOVERY → {RUNNING, SAFE_MODE} ; RUNNING → STOPPING → SHUTDOWN
Enforced by `_VALID_TRANSITIONS` — illegal transitions raise `InvalidStateTransition`.

## Failure Modes / Recovery
- Missed heartbeats ≥ 3 → `OrganFailed` event → `RecoveryManager.recover`
- Restart attempts exhausted → `EscalateSafeMode` → state = SAFE_MODE
- Resource requests exceeding quota are denied, never over-allocated

## Security
`SecurityManager` authorizes organs on registration; revokes on unregistration.
Only authorized senders pass `verify_socket_message`.

## Extension Points
Custom pipelines via `PipelineBus.define`; custom heartbeat/restart strategies via
`set_ping_implementation` / `set_restart_implementation`; resource quotas configurable
per hardware profile (i7 / RTX 3050 4GB / 32GB RAM target).

## Independence
No imports from other organs. All interaction via `SocketBus`, `EventDispatcher`, `PipelineBus`.
