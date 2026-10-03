import asyncio
import uuid
import sys
from pathlib import Path

# Add core path
sys.path.append(str(Path(__file__).parent / "All codes"))

from core_organs.organ_02_cns_single_file import EventBus, EventEnvelope
from core_organs.organ_38_task_orchestrator import TaskOrchestrator
from observability.organ_16_audit_system import AuditSystem
from core_organs.organ_07_security import SecurityKernel
from core_organs.organ_01_brain import BrainOrgan

async def concurrency_test():
    print("Starting Concurrency Task Correlation Test...")
    cns = EventBus()
    
    audit = AuditSystem(storage_dir=f"./audit_logs_test_concurrency_{uuid.uuid4().hex[:6]}")
    security = SecurityKernel(Path("."))
    
    orchestrator = TaskOrchestrator(cns, audit, security)
    brain = BrainOrgan()
    
    # We only start Orchestrator and Brain because we only care about INTENT_NORMALIZATION_COMPLETED
    await orchestrator.start()
    await brain.start(cns)
    
    trace_a = []
    trace_b = []
    
    # A dictionary to capture the assigned task_id for request A and request B
    canonical_ids = {}
    
    req_id_a = "req_A"
    req_id_b = "req_B"
    
    async def trace_monitor(env: EventEnvelope):
        payload = env.payload
        event_type = payload.get("event_type") or env.topic
        
        req = payload.get("request_id")
        tid = payload.get("task_id")
        
        if event_type == "TASK_CREATED":
            if req == req_id_a: canonical_ids["A"] = tid
            if req == req_id_b: canonical_ids["B"] = tid
            
        if tid:
            if tid == canonical_ids.get("A"):
                trace_a.append(event_type)
            elif tid == canonical_ids.get("B"):
                trace_b.append(event_type)
                
    await cns.subscribe("sys.events", "trace_monitor", trace_monitor)
    await cns.subscribe("TASK_CORRELATION_FAILED", "trace_monitor_err", trace_monitor)
    
    payload_a = {"payload": {"command": "Task A"}, "request_id": req_id_a}
    payload_b = {"payload": {"command": "Task B"}, "request_id": req_id_b}
    
    print("Dispatching TASK A and TASK B concurrently...")
    
    await asyncio.gather(
        cns.publish(EventEnvelope(topic="sock.cns.inbound", source_organ="system_boot", payload=payload_a)),
        cns.publish(EventEnvelope(topic="sock.cns.inbound", source_organ="system_boot", payload=payload_b))
    )
    
    # Wait for execution to settle (up to COMPILATION_STARTED since we don't have a compiler)
    timeout = 0
    while timeout < 10:
        if "COMPILATION_STARTED" in trace_a and "COMPILATION_STARTED" in trace_b:
            break
        await asyncio.sleep(0.5)
        timeout += 1
        
    print("\n--- TEST RESULTS ---")
    
    print(f"Canonical ID A: {canonical_ids.get('A')}")
    print(f"Canonical ID B: {canonical_ids.get('B')}")
    
    success = True
    if canonical_ids.get('A') == canonical_ids.get('B') or not canonical_ids.get('A'):
        print("[FAILED] Task IDs are identical or missing.")
        success = False
        
    required = ["TASK_CREATED", "INTENT_NORMALIZATION_STARTED", "INTENT_NORMALIZATION_COMPLETED", "COMPILATION_STARTED"]
    
    for req in required:
        if req not in trace_a:
            print(f"[MISSING A] EVENT: {req}")
            success = False
        if req not in trace_b:
            print(f"[MISSING B] EVENT: {req}")
            success = False
            
    if success:
        print("\n[PASSED] CONCURRENCY TEST: Tasks advanced independently without cross-correlation.")
    else:
        print("\n[FAILED] CONCURRENCY TEST.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(concurrency_test())
