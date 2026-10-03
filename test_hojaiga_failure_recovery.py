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
from core_organs.organ_36_workflow_compiler import WorkflowCompilerKernel
from core_organs.organ_32_state_catalog import StateCatalogOrgan

async def setup_test_env():
    cns = EventBus()
    audit = AuditSystem(storage_dir="./audit_logs_test_recovery")
    security = SecurityKernel(Path("."))
    
    orchestrator = TaskOrchestrator(cns, audit, security)
    brain = BrainOrgan()
    compiler = WorkflowCompilerKernel()
    state_catalog = StateCatalogOrgan()
    
    await orchestrator.start()
    await brain.start(cns)
    await compiler.start(cns)
    await state_catalog.start_cns(cns)
    
    trace = []
    
    async def trace_monitor(env: EventEnvelope):
        payload = env.payload
        event_type = payload.get("event_type") or env.topic
        if event_type:
            trace.append(event_type)
            
    await cns.subscribe("sys.events", "trace_monitor", trace_monitor)
    await cns.subscribe("REPLANNING_REQUESTED", "trace_monitor_rep", trace_monitor)
    await cns.subscribe("TASK_FAILED", "trace_monitor_fail", trace_monitor)
    await cns.subscribe("TASK_COMPLETED", "trace_monitor_comp", trace_monitor)
    await cns.subscribe("STATE_TRANSITION_FAILED", "trace_monitor_state_fail", trace_monitor)
    
    return cns, trace, orchestrator

async def run_tests():
    print("Starting Hojaiga Failure Recovery Test Suite...")
    
    tests_run = 0
    tests_passed = 0
    failures = []
    
    def report(name, condition):
        nonlocal tests_run, tests_passed
        tests_run += 1
        if condition:
            print(f"[PASS] {name}")
            tests_passed += 1
        else:
            print(f"[FAIL] {name}")
            failures.append(name)

    # =========================================================================
    # Test 8: Verification Failure
    # =========================================================================
    cns, trace, _ = await setup_test_env()
    task_id = str(uuid.uuid4())
    
    print("\nRunning Test 8: Verification Failure")
    # Simulate an intent that bypasses compilation straight to verification for speed
    await cns.publish(EventEnvelope(
        topic="sock.cns.inbound", 
        source_organ="system_boot", 
        payload={"payload": {"command": "test"}, "request_id": task_id}
    ))
    
    await asyncio.sleep(0.5)
    
    # Force verification step with injection payload
    await cns.publish(EventEnvelope(
        topic="VERIFICATION_STARTED",
        source_organ="organ_38",
        payload={"task_id": task_id, "inject_verification_failure": True}
    ))
    
    await asyncio.sleep(1.0)
    
    # It should emit REPLANNING_REQUESTED and NOT TASK_COMPLETED
    report("Test 8: VERIFICATION_FAILED does not emit TASK_COMPLETED", "TASK_COMPLETED" not in trace)
    report("Test 8: VERIFICATION_FAILED emits REPLANNING_REQUESTED", "REPLANNING_REQUESTED" in trace)


    # =========================================================================
    # Test 11: Invalid state transition
    # =========================================================================
    cns, trace, _ = await setup_test_env()
    task_id = str(uuid.uuid4())
    print("\nRunning Test 11: Invalid state transition")
    
    await cns.publish(EventEnvelope(
        topic="STATE_TRANSITION_REQUEST",
        source_organ="organ_38",
        payload={"entity_id": task_id, "target_state": "INVALID_GARBAGE"}
    ))
    
    await asyncio.sleep(0.5)
    
    # The state catalog should emit STATE_TRANSITION_FAILED due to ValueError parsing Enum
    report("Test 11: Invalid state transition blocked by State Catalog", "STATE_TRANSITION_FAILED" in trace)

    print(f"\n--- Validation Report ---")
    print(f"Tests Executed: {tests_run}")
    print(f"Tests Passed: {tests_passed}")
    print(f"Tests Failed: {tests_run - tests_passed}")
    
    if failures:
        print(f"Failures discovered: {failures}")
        
    print(f"False TASK_COMPLETED observed: {'Yes' if 'TASK_COMPLETED' in trace and 'Test 8' in failures else 'No'}")
    
    print("\nRUNTIME VALIDATION GATE: PASS" if tests_passed == tests_run else "\nRUNTIME VALIDATION GATE: FAIL")

if __name__ == "__main__":
    asyncio.run(run_tests())
