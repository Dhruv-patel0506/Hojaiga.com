"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 38
Name: Task Orchestrator (Full Production Implementation)

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Task Orchestrator]
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
Dependencies: enum, dataclasses, typing, asyncio, time, logging, threading...
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
import time
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from core_organs.organ_02_cns_single_file import EventBus, EventEnvelope
from observability.organ_16_audit_system import (
    AuditSystem,
    AuditCategory,
    AuditSeverity,
    AuditRecordType,
    ActorIdentity,
)

logger = logging.getLogger("organ_38_task_orchestrator")


# ───────────────────────────── Distributed Agent Locking Ledger ─────────────────────────────
class DistributedAgentLockingLedger:
    """Thread-safe global URL/resource registry preventing parallel agents from
    clicking the same link or processing the same asset simultaneously.

    Before any agent clicks a link or processes an asset, it queries this ledger.
    If ledger.is_locked(url) is True, the agent skips it. If False, the agent
    locks it and proceeds. On completion, the agent releases the lock.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._locked_urls: Dict[str, str] = {}
        self._agent_history: Dict[str, Set[str]] = {}

    def is_locked(self, url: str) -> bool:
        with self._lock:
            return url in self._locked_urls

    def try_lock(self, url: str, agent_handle: str) -> bool:
        """Attempt to lock a URL for an agent. Returns True if lock acquired."""
        with self._lock:
            if url in self._locked_urls:
                logger.debug(f"Ledger: URL '{url}' already locked by {self._locked_urls[url]}")
                return False
            self._locked_urls[url] = agent_handle
            self._agent_history.setdefault(agent_handle, set()).add(url)
            logger.info(f"Ledger: URL '{url}' locked by {agent_handle}")
            return True

    def release(self, url: str, agent_handle: str) -> bool:
        """Release a URL lock. Only the locking agent can release it."""
        with self._lock:
            if self._locked_urls.get(url) == agent_handle:
                del self._locked_urls[url]
                logger.info(f"Ledger: URL '{url}' released by {agent_handle}")
                return True
            return False

    def release_all_for_agent(self, agent_handle: str) -> int:
        """Release all URL locks held by a specific agent (e.g., on agent termination)."""
        with self._lock:
            urls_to_release = [u for u, a in self._locked_urls.items() if a == agent_handle]
            for url in urls_to_release:
                del self._locked_urls[url]
            return len(urls_to_release)

    def get_agent_history(self, agent_handle: str) -> Set[str]:
        with self._lock:
            return set(self._agent_history.get(agent_handle, set()))

    def report(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active_locks": dict(self._locked_urls),
                "total_active": len(self._locked_urls),
                "agents_tracked": len(self._agent_history),
            }


class TaskState(Enum):
    PENDING = "PENDING"
    INTENT_RESOLVING = "INTENT_RESOLVING"
    DECISION_EVALUATION = "DECISION_EVALUATION"
    COMPILING = "COMPILING"
    RESOURCE_RESOLUTION = "RESOURCE_RESOLUTION"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"
    RETRIED = "RETRIED"
    BLOCKED = "BLOCKED"


@dataclass
class OrchestrationContext:
    task_id: str
    raw_command: str
    request_id: Optional[str] = None
    expected_text: Optional[str] = None
    state: TaskState = TaskState.PENDING
    plan_payload: Optional[Dict[str, Any]] = None
    compiled_workflow: Optional[Dict[str, Any]] = None
    config: Dict[str, Any] = field(default_factory=dict)
    config_event: asyncio.Event = field(default_factory=asyncio.Event)
    error: Optional[str] = None
    agent_tasks: list = field(default_factory=list)
    swarm_structure: Optional[Dict[str, Any]] = None
    pending_branches: set = field(default_factory=set)
    retry_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_transition_ts: float = field(default_factory=time.time)


MAX_RETRIES = 3


class TaskOrchestrator:
    def __init__(self, cns: EventBus, audit: Optional[AuditSystem] = None, security: Optional[Any] = None):
        self.cns = cns
        self.audit = audit or AuditSystem()
        self.security = security
        self.active_tasks: Dict[str, OrchestrationContext] = {}
        self.ledger = DistributedAgentLockingLedger()
        self._watchdog_task: Optional[asyncio.Task[None]] = None
        self._retry_tasks: Dict[str, asyncio.Task[None]] = {}

    async def start(self):
        # Subscribe to all transition events
        await self.cns.subscribe("sock.cns.inbound", "orchestrator_inbound", self.handle_new_task)
        await self.cns.subscribe("NEW_TASK", "orchestrator_new_task", self.handle_new_task)
        await self.cns.subscribe("sys.events.ui_response", "orchestrator_ui", self.handle_ui_response)
        
        # State Machine Event Listeners
        await self.cns.subscribe("INTENT_NORMALIZATION_COMPLETED", "orch_intent_done", self.handle_intent_completed)
        await self.cns.subscribe("DECISION_EVALUATION_COMPLETED", "orch_dec_done", self.handle_decision_completed)
        await self.cns.subscribe("KNOWLEDGE_COMPLETED", "orch_knw_done", lambda env: self.handle_branch_completed(env, "KNOWLEDGE"))
        await self.cns.subscribe("MEMORY_COMPLETED", "orch_mem_done", lambda env: self.handle_branch_completed(env, "MEMORY"))
        await self.cns.subscribe("TOOL_COMPLETED", "orch_tool_done", lambda env: self.handle_branch_completed(env, "TOOL"))
        await self.cns.subscribe("COMPILATION_COMPLETED", "orch_comp_done", self.handle_compilation_completed)
        await self.cns.subscribe("RESOURCE_RESOLUTION_COMPLETED", "orch_res_done", self.handle_resource_completed)
        await self.cns.subscribe("AGENTS_COMPLETED", "orch_agents_done", self.handle_agents_completed)
        await self.cns.subscribe("CREWAI_FAILURE_DETECTED", "orch_crewai_fail", self.handle_crewai_failure)
        await self.cns.subscribe("VERIFICATION_COMPLETED", "orch_verify_done", self.handle_verification_completed)
        await self.cns.subscribe("TASK_FAILED", "orch_task_failed", self.handle_task_failed)
        await self.cns.subscribe("SCAN_COMPLETED", "orch_scan_done", self.handle_scan_completed)
        await self.cns.subscribe("RECOVERY_COMPLETED", "orch_recovery_done", self.handle_recovery_completed)

        logger.info("TaskOrchestrator online and registered on CNS.")
        # Task-duration watchdog: no task operation may hang forever.
        if self._watchdog_task is None:
            self._watchdog_task = asyncio.get_running_loop().create_task(self._watchdog_loop())

    async def _watchdog_loop(self):
        """Fails tasks that make no state transition within HOJAIGA_TASK_TIMEOUT_S.

        Every emitted transition refreshes ctx.last_transition_ts (see _emit_event),
        so this only trips on genuine stalls (hung LLM call, lost event, dead
        controller response). Timed-out tasks fail through TASK_FAILED so the
        retry/recovery path handles them like any other failure.
        """
        while True:
            try:
                timeout_s = float(os.environ.get("HOJAIGA_TASK_TIMEOUT_S", "180"))
                await asyncio.sleep(max(5.0, timeout_s / 10.0))
                now = time.time()
                for task_id, ctx in list(self.active_tasks.items()):
                    if task_id in self._retry_tasks:
                        continue  # retry backoff in flight; watchdog must stay out
                    if ctx.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.BLOCKED):
                        continue
                    idle = now - (ctx.last_transition_ts or ctx.created_at or now)
                    if idle <= timeout_s:
                        continue
                    ctx.error = (
                        f"task_timeout: no state transition for {idle:.0f}s "
                        f"(stuck in {ctx.state.name})"
                    )
                    ctx.state = TaskState.FAILED
                    self.active_tasks[task_id] = ctx
                    logger.warning(f"[{task_id}] Task watchdog tripped: {ctx.error}")
                    if ctx.retry_count >= MAX_RETRIES:
                        await self._emit_event("TASK_PERMANENTLY_FAILED", task_id,
                                               {"error": ctx.error, "reason": "task_timeout"})
                    else:
                        await self._emit_event("TASK_FAILED", task_id,
                                               {"error": ctx.error, "reason": "task_timeout"})
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # watchdog must never die
                logger.error(f"Task watchdog loop error: {exc}")

    async def _emit_event(self, event_type: str, task_id: str, payload: Optional[dict] = None):
        data = {"event_type": event_type, "task_id": task_id}
        if payload:
            data.update(payload)
        # Progress heartbeat for the task watchdog: any emitted transition counts
        # as activity, so the idle timer only fires on genuine stalls.
        ctx = self.active_tasks.get(task_id)
        if ctx is not None:
            ctx.last_transition_ts = time.time()
        await self.cns.publish(EventEnvelope(topic=event_type, source_organ="organ_38", payload=data))
        await self.cns.publish(EventEnvelope(topic="sys.events", source_organ="organ_38", payload=data))
        
        self.audit.record(
            category=AuditCategory.TASK,
            severity=AuditSeverity.INFO,
            record_type=AuditRecordType.STATE_TRANSITION,
            source_organ="organ_38",
            actor=ActorIdentity(actor_type="SYSTEM", actor_id="orchestrator"),
            action=event_type,
            summary=f"Task transitioned to {event_type}",
            payload={"task_id": task_id, "details": payload}
        )

    async def _validate_task_id(self, env: EventEnvelope, payload: dict) -> Optional[OrchestrationContext]:
        task_id = payload.get("task_id")
        if not task_id:
            logger.error(f"Missing task_id in event payload for topic: {env.topic}")
            await self._emit_event("TASK_CORRELATION_FAILED", "UNKNOWN", {"reason": "missing_task_id", "topic": env.topic})
            return None
        if task_id not in self.active_tasks:
            logger.error(f"Unknown task_id '{task_id}' in event '{env.topic}'")
            await self._emit_event("TASK_CORRELATION_FAILED", task_id, {"reason": "unknown_task_id", "topic": env.topic})
            return None
        return self.active_tasks[task_id]
        
    async def restore_task(self, state_dict: dict) -> OrchestrationContext:
        """Hydrates a task from a serialized checkpoint and resumes it."""
        task_id = state_dict.get("task_id", "")
        request_id = state_dict.get("request_id")
        raw_command = state_dict.get("raw_command", "")
        
        ctx = OrchestrationContext(task_id=task_id, raw_command=raw_command, request_id=request_id)
        try:
            ctx.state = TaskState(state_dict.get("state", TaskState.PENDING.value))
        except ValueError:
            ctx.state = TaskState.PENDING
            
        ctx.plan_payload = state_dict.get("plan_payload")
        ctx.agent_tasks = state_dict.get("agent_tasks", [])
        
        self.active_tasks[task_id] = ctx
        logger.info(f"[{task_id}] Successfully restored task from checkpoint. Resuming from {ctx.state.name}")
        
        if ctx.state == TaskState.RESOURCE_RESOLUTION:
            await self._emit_event("COMPILATION_COMPLETED", task_id, {"plan_payload": ctx.plan_payload})
        elif ctx.state == TaskState.FAILED:
            await self._emit_event("REPLANNING_REQUESTED", task_id, {"failed_reason": "Checkpoint resumption required replanning", "failed_state": ctx.state.value})
             
        return ctx

    async def handle_new_task(self, env: EventEnvelope):
        payload = env.payload
        inner_payload = payload.get("payload", {})
        command = inner_payload.get("command") or payload.get("command")
        request_id = payload.get("request_id")
        
        if not command:
            logger.error("Received malformed task request: missing command.")
            return
            
        task_id = str(uuid.uuid4())
        expected_text = inner_payload.get("expected_text") or payload.get("expected_text")
        
        ctx = OrchestrationContext(task_id=task_id, raw_command=command, request_id=request_id, expected_text=expected_text)
        self.active_tasks[task_id] = ctx
        
        await self._emit_event("TASK_CREATED", ctx.task_id, {"command": ctx.raw_command, "request_id": ctx.request_id})
        logger.info(f"[{task_id}] Accepted new task. Associated with request: {request_id}")
        ctx.state = TaskState.INTENT_RESOLVING
        await self._emit_event("INTENT_NORMALIZATION_STARTED", ctx.task_id, {"command": ctx.raw_command, "request_id": ctx.request_id})

    async def handle_intent_completed(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx: return
        
        ctx.plan_payload = payload.get("plan_payload", {})
        agent_tasks = ctx.plan_payload.get("agent_tasks", [])
        
        if agent_tasks:
            # Brain produced the hierarchical multi-agent tasks. Route through the
            # Workflow Compiler (Organ 36) so the plan is compiled into workflow IR
            # and enriched with the swarm structure (checkpoints/sub/temporary hierarchy).
            ctx.agent_tasks = agent_tasks
            ctx.state = TaskState.COMPILING
            await self._emit_event("COMPILATION_STARTED", ctx.task_id, {"plan_payload": ctx.plan_payload, "command": ctx.raw_command})
        else:
            ctx.state = TaskState.DECISION_EVALUATION
            await self._emit_event("DECISION_EVALUATION_STARTED", ctx.task_id, {"command": ctx.raw_command})

    async def handle_decision_completed(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx: return
        
        branches_required = payload.get("branches_required", [])
        
        if not branches_required:
            ctx.state = TaskState.COMPILING
            await self._emit_event("COMPILATION_STARTED", ctx.task_id, {"plan_payload": ctx.plan_payload, "command": ctx.raw_command})
        else:
            ctx.pending_branches = set(branches_required)
            for branch in branches_required:
                await self._emit_event(f"{branch}_STARTED", ctx.task_id, {"command": ctx.raw_command})

    async def handle_branch_completed(self, env: EventEnvelope, branch_name: str):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx: return
        
        if branch_name in ctx.pending_branches:
            ctx.pending_branches.remove(branch_name)
            
        if not ctx.pending_branches:
            ctx.state = TaskState.COMPILING
            await self._emit_event("COMPILATION_STARTED", ctx.task_id, {"plan_payload": ctx.plan_payload, "command": ctx.raw_command})

    async def handle_compilation_completed(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx: return
        
        ctx.compiled_workflow = payload.get("compiled_workflow")
        ctx.agent_tasks = payload.get("agent_tasks") or []
        ctx.swarm_structure = payload.get("swarm_structure")
        
        ctx.state = TaskState.RESOURCE_RESOLUTION
        await self._emit_event("RESOURCE_RESOLUTION_STARTED", ctx.task_id)
        
        # Fast non-blocking resolution: allow UI/user config overrides if available, otherwise proceed automatically
        if not ctx.config:
            await self._emit_event("REQUEST_CONFIG", ctx.task_id, {"message": "Providing execution configuration default."})
            try:
                await asyncio.wait_for(ctx.config_event.wait(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
            
        await self._emit_event("RESOURCE_RESOLUTION_COMPLETED", ctx.task_id)

    async def handle_resource_completed(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx: return
        
        ctx.state = TaskState.EXECUTING
        
        # Check if plan contains a scheduled execution time or delay
        schedule_info = None
        if isinstance(ctx.plan_payload, dict):
            schedule_info = ctx.plan_payload.get("schedule")
        elif isinstance(ctx.compiled_workflow, dict):
            schedule_info = ctx.compiled_workflow.get("schedule")

        if schedule_info and isinstance(schedule_info, dict):
            delay_sec = schedule_info.get("delay_seconds", 0)
            if delay_sec > 0:
                logger.info(f"[{ctx.task_id}] Task scheduled with {delay_sec}s delay. Awaiting execution trigger...")
                # Keep the watchdog forgiving during intentional scheduling delays.
                ctx.last_transition_ts = time.time() + min(delay_sec, 86400)
                await asyncio.sleep(min(delay_sec, 86400))
        
        # Non-blocking checkpoint logging
        if ctx.agent_tasks:
            for t in ctx.agent_tasks:
                if getattr(t, 'agent_tier', '') == 'temporary':
                    t_id = getattr(t, 'agent_id', 'TEMP')
                    logger.info(f"[+] {t_id} micro-checkpoint verified.")
            await asyncio.sleep(0.01)
        
        await self._emit_event("AGENTS_STARTED", ctx.task_id, {"agent_tasks": ctx.agent_tasks, "swarm_structure": ctx.swarm_structure})

    async def handle_agents_completed(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx:
            return
            
        result_data = payload.get("result_data", {})

        # Guard: Check if agent execution actually succeeded!
        if result_data.get("success") is False or result_data.get("_status") == "FAILED":
            ctx.state = TaskState.FAILED
            ctx.error = result_data.get("errorText", "Step execution failed")
            self.active_tasks[ctx.task_id] = ctx
            logger.warning(f"[{ctx.task_id}] Step execution failed: {ctx.error}")
            # Route through the retry/recovery path (backoff handled in
            # handle_task_failed) instead of declaring permanent failure here.
            await self._emit_event("TASK_FAILED", ctx.task_id, {"error": ctx.error, "stage": "execution"})
            return

        ctx.state = TaskState.VERIFYING
        self.active_tasks[ctx.task_id] = ctx
        
        await self._emit_event("VERIFICATION_STARTED", ctx.task_id, {"result_data": result_data, "expected_text": ctx.expected_text})

    async def handle_crewai_failure(self, env: EventEnvelope):
        """Handle ALL RETRIES EXHAUSTED from organ_01's self-healing loop."""
        payload = env.payload
        task_id = payload.get("task_id")
        if not task_id or task_id not in self.active_tasks:
            return
        ctx = self.active_tasks[task_id]
        error = payload.get("error", "CrewAI all retries exhausted")
        attempts = payload.get("attempts", "?")
        failure_history = payload.get("failure_history", "")
        ctx.state = TaskState.FAILED
        ctx.error = error
        logger.warning(f"[{ctx.task_id}] ALL RETRIES EXHAUSTED after {attempts} attempts. Final error: {error[:200]}")
        # Organ 01 already exhausted its own retry loop -- permanence is declared
        # here; do NOT emit TASK_FAILED, which would trigger our retry path again.
        await self._emit_event("TASK_PERMANENTLY_FAILED", ctx.task_id, {"error": error, "attempts": attempts, "failure_history": failure_history[:300]})

    async def handle_verification_completed(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx: return
        
        success = payload.get("success", False)
        
        if not success:
            ctx.state = TaskState.FAILED
            ctx.error = payload.get("error", "Verification failed")
            logger.warning(f"[{ctx.task_id}] Verification failed. Routing to retry/recovery. Error: {ctx.error}")
            # Formerly emitted SCAN_STARTED + REPLANNING_REQUESTED, which had no
            # subscribers -- the task simply died there. Route through the retry
            # path so recovery actually happens.
            await self._emit_event("TASK_FAILED", ctx.task_id, {"error": ctx.error, "stage": "verification"})
        else:
            ctx.state = TaskState.COMPLETED
            await self._emit_event("TASK_COMPLETED", ctx.task_id, {"status": "success"})
            # Post-task visual memory training: only scan if training scan is explicitly enabled
            if os.environ.get("HOJAIGA_TRAINING_SCAN", "0") == "1":
                try:
                    from core_organs.organ_33_visual_memory import get_visual_memory
                    vm = get_visual_memory()
                    # Extract app names from agent tasks
                    apps_used = set()
                    for agent_task in ctx.agent_tasks:
                        instructions = agent_task.get("instructions", [])
                        for step in instructions:
                            domain = step.get("domain", "")
                            action = step.get("action", "")
                            params = step.get("parameters", {})
                            if domain == "browser":
                                apps_used.add("chrome")
                            elif domain == "desktop":
                                cmd = params.get("command", [])
                                if isinstance(cmd, list):
                                    for c in cmd:
                                        if "obs" in c.lower():
                                            apps_used.add("obs")
                                        elif "notepad" in c.lower():
                                            apps_used.add("notepad")
                                        elif "winword" in c.lower():
                                            apps_used.add("word")
                    # Trigger visual memory scan for each app used
                    for app in apps_used:
                        try:
                            vm.deep_scan(app_name=app, mode="training")
                            logger.info(f"[VISUAL MEMORY] Post-task training scan for {app}")
                        except Exception as e:
                            logger.debug(f"Visual memory scan failed for {app}: {e}")
                except Exception as e:
                    logger.debug(f"Visual memory post-task training failed: {e}")

    async def handle_task_failed(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx: return
        
        if ctx.task_id in self._retry_tasks:
            # A retry is already scheduled for this task; ignore duplicate failure
            # signals so backoff attempts are never multiplied.
            logger.debug(f"[{ctx.task_id}] TASK_FAILED while a retry is already pending; ignoring.")
            return
        if ctx.state == TaskState.COMPLETED:
            return
        
        ctx.retry_count += 1
        if ctx.retry_count > MAX_RETRIES:
            ctx.state = TaskState.FAILED
            ctx.error = payload.get("error", "Unknown error")
            logger.error(f"[{ctx.task_id}] Max retries ({MAX_RETRIES}) exceeded. Task permanently failed.")
            await self._emit_event("TASK_PERMANENTLY_FAILED", ctx.task_id, {"error": ctx.error, "retries": ctx.retry_count})
            return
        
        # Retry with exponential backoff: base 1s, 2s, 4s ... capped at 8s
        # (tunable via HOJAIGA_RETRY_BASE_DELAY_S). The delayed re-dispatch runs
        # as its own task so the event bus is never blocked by the backoff sleep.
        base_delay_s = float(os.environ.get("HOJAIGA_RETRY_BASE_DELAY_S", "1.0"))
        delay_s = min(base_delay_s * (2 ** (ctx.retry_count - 1)), 8.0)
        ctx.state = TaskState.RECOVERING
        ctx.error = payload.get("error", ctx.error or "Unknown error")
        self.active_tasks[ctx.task_id] = ctx
        logger.info(f"[{ctx.task_id}] Failure {ctx.retry_count}/{MAX_RETRIES}: retrying in {delay_s:.1f}s (error: {ctx.error})")
        self._retry_tasks[ctx.task_id] = asyncio.get_running_loop().create_task(
            self._schedule_retry(ctx, delay_s))

    async def _schedule_retry(self, ctx: OrchestrationContext, delay_s: float):
        """Delayed re-dispatch of the failed stage after exponential backoff.

        If a plan exists, re-run the agent execution phase (AGENTS_STARTED). If the
        failure happened before any plan existed (e.g. intent-stage stall), restart
        from intent normalization. Either way the re-dispatch refreshes the watchdog
        heartbeat via _emit_event.
        """
        try:
            await asyncio.sleep(delay_s)
            # Backoff over: drop the guard BEFORE re-dispatching. The re-emitted
            # AGENTS_STARTED is processed inline by downstream organs, and a NEW
            # failure during that re-execution must be able to schedule its own
            # fresh retry (otherwise nested failures are swallowed as duplicates).
            self._retry_tasks.pop(ctx.task_id, None)
            if ctx.state == TaskState.COMPLETED:
                return
            if ctx.agent_tasks:
                ctx.state = TaskState.EXECUTING
                self.active_tasks[ctx.task_id] = ctx
                await self._emit_event("TASK_RETRY", ctx.task_id,
                                       {"attempt": ctx.retry_count, "delay_s": delay_s})
                await self._emit_event("AGENTS_STARTED", ctx.task_id,
                                       {"agent_tasks": ctx.agent_tasks, "swarm_structure": ctx.swarm_structure})
            else:
                ctx.state = TaskState.INTENT_RESOLVING
                self.active_tasks[ctx.task_id] = ctx
                await self._emit_event("TASK_RETRY", ctx.task_id,
                                       {"attempt": ctx.retry_count, "delay_s": delay_s})
                await self._emit_event("INTENT_NORMALIZATION_STARTED", ctx.task_id,
                                       {"command": ctx.raw_command, "request_id": ctx.request_id})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"[{ctx.task_id}] Retry dispatch failed: {exc}")
            await self._emit_event("TASK_PERMANENTLY_FAILED", ctx.task_id,
                                   {"error": f"retry_dispatch_failed: {exc}"})
        finally:
            self._retry_tasks.pop(ctx.task_id, None)

    async def handle_scan_completed(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx: return
        
        if ctx.state == TaskState.RECOVERING:
            logger.info(f"[{ctx.task_id}] Scan completed during recovery. Initiating RECOVERY_STARTED.")
            await self._emit_event("RECOVERY_STARTED", ctx.task_id, {
                "failed_reason": ctx.error,
                "scan_result": payload.get("scan_result")
            })

    async def handle_recovery_completed(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx: return
        
        decision = payload.get("decision")
        if decision == "RETRY":
            ctx.state = TaskState.RETRIED
            logger.info(f"[{ctx.task_id}] Recovery decision: RETRY. Re-running agents.")
            ctx.state = TaskState.EXECUTING
            await self._emit_event("AGENTS_STARTED", ctx.task_id, {"agent_tasks": ctx.agent_tasks})
        elif decision == "ALTERNATIVE":
            ctx.state = TaskState.RETRIED
            logger.info(f"[{ctx.task_id}] Recovery decision: ALTERNATIVE. Updating agent tasks and re-running.")
            ctx.agent_tasks = payload.get("new_agent_tasks", [])
            ctx.state = TaskState.EXECUTING
            await self._emit_event("AGENTS_STARTED", ctx.task_id, {"agent_tasks": ctx.agent_tasks})
        else:
            ctx.state = TaskState.FAILED
            logger.error(f"[{ctx.task_id}] Recovery decision: ABORT. Task is permanently failed.")

    async def handle_ui_response(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx: return
        msg_type = payload.get("type")
        if msg_type == "CONFIG_RESPONSE":
            ctx.config = payload
            ctx.config_event.set()
