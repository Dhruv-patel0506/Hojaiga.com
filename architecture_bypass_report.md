# Architectural Bypass and Dependency Report

## 1. Executive Summary
A comprehensive inspection of the runtime execution loop reveals that the architecture is suffering from a "God Object" anti-pattern centered around `organ_38_task_orchestrator.py`. While `system_boot.py` correctly establishes the CNS EventBus and routes UI inputs, the Task Orchestrator is bypassing the event-driven architecture by directly importing, instantiating, and synchronously executing the cognitive and execution organs.

## 2. Bypass Analysis
**Expected Target Architecture (Event-Driven):**
`UI` -> `[TASK_CREATED]` -> `CNS` -> `Brain` -> `[INTENT_NORMALIZATION_COMPLETED]` -> `CNS` -> `Compiler` -> ...

**Actual Runtime Implementation (Bypass):**
`UI` -> `system_boot` -> `CNS` -> `TaskOrchestrator` -> Direct function calls to `BrainOrgan`, `WorkflowCompilerKernel`, `DecisionEngineCore`, `AgentsKernel`, `ControllersCore`, `AppScanner`, and `VisualPerception`.

### Specific Violations Identified:
1. **Direct Instantiation**: `organ_38_task_orchestrator.py` instantiates `self.brain = BrainOrgan()`, `self.compiler = WorkflowCompilerKernel()`, etc.
2. **Synchronous Execution**: The method `_run_task_lifecycle` uses blocking or direct async calls (e.g., `ctx.plan = self.brain.handle_task(req)`) rather than emitting `[INTENT_NORMALIZATION_STARTED]` and yielding back to the event loop.
3. **Fake Event Emission**: The Orchestrator emits events like `INTENT_NORMALIZATION_COMPLETED` *after* it has already done the work synchronously itself, effectively using the EventBus as a logging mechanism rather than a true Message Broker.
4. **Missing Checkpoint Pub/Sub**: Checkpoints and App Scanner are invoked manually via `self.app_scanner.scan_state(ctx.task_id)` instead of through CNS delegation.

## 3. Repair Strategy
To restore the architectural integrity without destroying the components:
1. **Refactor Orchestrator**: Strip all direct organ instantiations from `organ_38_task_orchestrator.py`. It should only manage the State Machine and emit control events.
2. **Refactor Organs**: Ensure `Brain`, `Compiler`, `Agents`, etc., are standalone services that subscribe to `sock.cns.inbound` or their specific trigger events.
3. **Update Composition Root**: Modify `system_boot.py` to instantiate and register all these organs onto the CNS EventBus during startup.

I have generated the `hojaiga_nodemation_v2.html` which correctly reflects the intended event-driven states. I will now proceed to repair the execution loop in the codebase.
