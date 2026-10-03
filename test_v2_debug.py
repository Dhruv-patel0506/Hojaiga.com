"""Debug Test A specifically: check why ctx.status ends up not SUCCESS."""
import asyncio
import sys
import uuid
from typing import Dict, Set, List
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "All codes"))
from core_organs.organ_02_cns_single_file import EventEnvelope, EventBus
from core_organs.organ_38_task_orchestrator import TaskOrchestrator
from core_organs.organ_22_decision_engine import DecisionEngineOrgan

class MockAuditSystem:
    def record(self, *args, **kwargs): pass

class TaskContext:
    def __init__(self, request_id: str):
        self.request_id = request_id
        self.status = "PENDING"
        self.events: List[str] = []
        self.transitions: List[str] = []
        self.branches_requested: Set[str] = set()
        self.branches_executed: Set[str] = set()
        self.branches_completed: Set[str] = set()
        self.error = None
        self.is_done = asyncio.Event()

async def main():
    cns = EventBus()
    mock_audit = MockAuditSystem()
    orchestrator = TaskOrchestrator(cns, mock_audit, None)
    decision_engine = DecisionEngineOrgan()
    
    tasks: Dict[str, TaskContext] = {}
    request_to_task: Dict[str, str] = {}
    
    await orchestrator.start()
    await decision_engine.start_cns(cns)
    
    # Mock brain intent
    async def mock_brain(env):
        tid = env.payload.get("task_id")
        await cns.publish(EventEnvelope(
            topic="INTENT_NORMALIZATION_COMPLETED",
            source_organ="mock_brain",
            payload={"task_id": tid, "plan_payload": env.payload.get("command", "")}
        ))
    
    # Mock workflow compiler
    async def mock_compiler(env):
        tid = env.payload.get("task_id")
        await cns.publish(EventEnvelope(
            topic="COMPILATION_COMPLETED",
            source_organ="mock_compiler",
            payload={"task_id": tid, "agent_tasks": []}
        ))
    
    # Mock agents
    async def mock_agents(env):
        tid = env.payload.get("task_id")
        await cns.publish(EventEnvelope(
            topic="AGENTS_COMPLETED",
            source_organ="mock_agents",
            payload={"task_id": tid, "result_data": {}}
        ))
    
    # Mock verification
    async def mock_verify(env):
        tid = env.payload.get("task_id")
        await cns.publish(EventEnvelope(
            topic="VERIFICATION_COMPLETED",
            source_organ="mock_verify",
            payload={"task_id": tid, "success": True}
        ))
    
    # Mock UI config
    async def mock_ui(env):
        tid = env.payload.get("task_id")
        print(f"  [mock_ui] REQUEST_CONFIG received for task_id={tid[:12]}...")
        await cns.publish(EventEnvelope(
            topic="sys.events.ui_response",
            source_organ="mock_ui",
            payload={"task_id": tid, "type": "CONFIG_RESPONSE", "config_data": {}}
        ))
    
    await cns.subscribe("INTENT_NORMALIZATION_STARTED", "mock_brain", mock_brain)
    await cns.subscribe("COMPILATION_STARTED", "mock_compiler", mock_compiler)
    await cns.subscribe("AGENTS_STARTED", "mock_agents", mock_agents)
    await cns.subscribe("VERIFICATION_STARTED", "mock_verify", mock_verify)
    await cns.subscribe("REQUEST_CONFIG", "mock_ui", mock_ui)
    
    # Monitor - same as harness
    async def monitor(env):
        payload = env.payload
        event_type = env.topic
        
        if event_type == "sys.events":
            event_type = payload.get("event_type")
            task_id = payload.get("task_id")
        else:
            task_id = payload.get("task_id") or payload.get("request_id")
        
        print(f"  [monitor] {event_type:45s} task_id={str(task_id)[:12]}...")
        
        if event_type == "TASK_CREATED":
            req_id = payload.get("request_id")
            if req_id in tasks:
                actual_task_id = payload.get("task_id")
                request_to_task[actual_task_id] = req_id
                print(f"  [monitor] MAPPED orch_id={actual_task_id[:12]}... -> req_id={req_id[:12]}...")
            else:
                print(f"  [monitor] WARNING: req_id={req_id[:12]}... NOT in tasks dict!")
        
        mapped_req_id = request_to_task.get(task_id, task_id)
        if not mapped_req_id or mapped_req_id not in tasks:
            print(f"  [monitor] SKIPPED: mapped_req_id={str(mapped_req_id)[:12]}... not in tasks")
            return
        
        ctx = tasks[mapped_req_id]
        if not ctx.events or ctx.events[-1] != event_type:
            ctx.events.append(event_type)
        
        if event_type == "TASK_COMPLETED":
            ctx.status = "SUCCESS"
            print(f"  [monitor] >>> TASK_COMPLETED -> status=SUCCESS, setting is_done")
            ctx.is_done.set()
        elif event_type == "TASK_FAILED":
            ctx.status = "FAILED"
            print(f"  [monitor] >>> TASK_FAILED -> status=FAILED, setting is_done")
            ctx.is_done.set()
    
    events_to_monitor = [
        "TASK_CREATED", "INTENT_NORMALIZATION_STARTED", "INTENT_NORMALIZATION_COMPLETED",
        "DECISION_EVALUATION_STARTED", "DECISION_EVALUATION_COMPLETED",
        "COMPILATION_STARTED", "COMPILATION_COMPLETED",
        "TASK_COMPLETED", "TASK_FAILED"
    ]
    for ev in events_to_monitor:
        await cns.subscribe(ev, "monitor", monitor)
    
    # --- TEST A ---
    tid = str(uuid.uuid4())
    tasks[tid] = TaskContext(tid)
    print(f"\n=== TEST A: Submitting request_id={tid[:12]}... ===\n")
    
    await cns.publish(EventEnvelope(
        topic="sock.cns.inbound",
        source_organ="interface",
        payload={"payload": {"command": "simple test"}, "request_id": tid}
    ))
    
    ctx = tasks[tid]
    print(f"\n  After submit: ctx.status={ctx.status}, is_done={ctx.is_done.is_set()}")
    print(f"  Events so far: {ctx.events}")
    
    try:
        await asyncio.wait_for(ctx.is_done.wait(), timeout=15.0)
    except asyncio.TimeoutError:
        ctx.status = "TIMEOUT"
    
    print(f"\n=== TEST A RESULT: {ctx.status} ===")
    print(f"  Events: {ctx.events}")
    print(f"  request_to_task mapping: {dict((k[:12]+'...', v[:12]+'...') for k,v in request_to_task.items())}")

if __name__ == "__main__":
    asyncio.run(main())
