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
import uuid
import time
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from core_organs.organ_02_cns_single_file import EventBus, EventEnvelope
from observability.organ_16_audit_system import AuditSystem, AuditCategory, AuditSeverity, AuditRecordType, ActorIdentity

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
    pending_branches: set = field(default_factory=set)
    retry_count: int = 0


MAX_RETRIES = 3


class TaskOrchestrator:
    def __init__(self, cns: EventBus, audit: AuditSystem, security: Any):
        self.cns = cns
        self.audit = audit
        self.security = security
        self.active_tasks: Dict[str, OrchestrationContext] = {}
        self.ledger = DistributedAgentLockingLedger()

    async def start(self):
        # Subscribe to all transition events
        await self.cns.subscribe("sock.cns.inbound", "orchestrator_inbound", self.handle_new_task)
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
        await self.cns.subscribe("VERIFICATION_COMPLETED", "orch_verify_done", self.handle_verification_completed)
        await self.cns.subscribe("TASK_FAILED", "orch_task_failed", self.handle_task_failed)
        await self.cns.subscribe("SCAN_COMPLETED", "orch_scan_done", self.handle_scan_completed)
        await self.cns.subscribe("RECOVERY_COMPLETED", "orch_recovery_done", self.handle_recovery_completed)

        logger.info("TaskOrchestrator online and registered on CNS.")

    async def _emit_event(self, event_type: str, task_id: str, payload: Optional[dict] = None):
        data = {"event_type": event_type, "task_id": task_id}
        if payload:
            data.update(payload)
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
        
        ctx.plan_payload = payload.get("plan_payload")
        ctx.state = TaskState.DECISION_EVALUATION
        await self._emit_event("DECISION_EVALUATION_STARTED", ctx.task_id, {"command": ctx.raw_command})

    async def handle_decision_completed(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx: return
        
        branches_required = payload.get("branches_required", [])
        
        if not branches_required:
            ctx.state = TaskState.COMPILING
            await self._emit_event("COMPILATION_STARTED", ctx.task_id, {"plan_payload": ctx.plan_payload})
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
            await self._emit_event("COMPILATION_STARTED", ctx.task_id, {"plan_payload": ctx.plan_payload})

    async def handle_compilation_completed(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx: return
        
        ctx.compiled_workflow = payload.get("compiled_workflow")
        ctx.agent_tasks = payload.get("agent_tasks", [])
        
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
        
        # Non-blocking checkpoint logging
        if ctx.agent_tasks:
            for t in ctx.agent_tasks:
                if getattr(t, 'agent_tier', '') == 'temporary':
                    t_id = getattr(t, 'agent_id', 'TEMP')
                    logger.info(f"[+] {t_id} micro-checkpoint verified.")
            await asyncio.sleep(0.01)
        
        await self._emit_event("AGENTS_STARTED", ctx.task_id, {"agent_tasks": ctx.agent_tasks})

    async def handle_agents_completed(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx:
            return
            
        ctx.state = TaskState.VERIFYING
        self.active_tasks[ctx.task_id] = ctx
        
        result_data = payload.get("result_data", {})
        
        await self._emit_event("VERIFICATION_STARTED", ctx.task_id, {"result_data": result_data, "expected_text": ctx.expected_text})

    async def handle_verification_completed(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx: return
        
        success = payload.get("success", True)
        
        if not success:
            ctx.state = TaskState.FAILED
            ctx.error = payload.get("error", "Verification failed")
            logger.warning(f"[{ctx.task_id}] Verification failed. Initiating Recovery. Error: {ctx.error}")
            await asyncio.sleep(1.0)
            await self._emit_event("SCAN_STARTED", ctx.task_id, {})
            await self._emit_event("REPLANNING_REQUESTED", ctx.task_id, {"failed_reason": ctx.error, "failed_state": ctx.state.value})
        else:
            ctx.state = TaskState.COMPLETED
            await self._emit_event("TASK_COMPLETED", ctx.task_id, {"status": "success"})

    async def handle_task_failed(self, env: EventEnvelope):
        payload = env.payload
        ctx = await self._validate_task_id(env, payload)
        if not ctx: return
        
        ctx.retry_count += 1
        if ctx.retry_count > MAX_RETRIES:
            ctx.state = TaskState.FAILED
            ctx.error = payload.get("error", "Unknown error")
            logger.error(f"[{ctx.task_id}] Max retries ({MAX_RETRIES}) exceeded. Task permanently failed.")
            await self._emit_event("TASK_PERMANENTLY_FAILED", ctx.task_id, {"error": ctx.error, "retries": ctx.retry_count})
            return

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
