import asyncio
import uuid
import sys
from core_organs.organ_02_cns_single_file import EventBus, EventEnvelope

async def golden_test():
    print("Starting Hojaiga Architecture Golden Test...")
    cns = EventBus()
    
    # We will simulate the system boot routing by registering the orchestrator
    from core_organs.organ_38_task_orchestrator import TaskOrchestrator
    from observability.organ_16_audit_system import AuditSystem
    from core_organs.organ_07_security import SecurityKernel
    from core_organs.organ_01_brain import BrainOrgan
    from core_organs.organ_36_workflow_compiler import WorkflowCompilerKernel
    from core_organs.organ_03_memory import MemoryCore
    from core_organs.organ_04_knowledge import KnowledgeOrgan
    from core_organs.organ_10_agents import AgentsOrgan
    from core_organs.organ_30_app_scanner import AppScannerOrgan
    from core_organs.organ_31_visual_perception import VisualPerceptionOrgan
    from core_organs.organ_05_controllers import ControllersCore
    from core_organs.organ_32_state_catalog import StateCatalogOrgan
    from core_organs.organ_29_popup_handler import DesktopInteractionManager
    from pathlib import Path
    
    audit = AuditSystem(storage_dir="./audit_logs_test")
    security = SecurityKernel(Path("."))
    
    orchestrator = TaskOrchestrator(cns, audit, security)
    brain = BrainOrgan()
    compiler = WorkflowCompilerKernel()
    memory = MemoryCore()
    knowledge = KnowledgeOrgan()
    agents = AgentsOrgan()
    app_scanner = AppScannerOrgan()
    visual_perception = VisualPerceptionOrgan()
    controllers = ControllersCore()
    state_catalog = StateCatalogOrgan()
    popup_handler = DesktopInteractionManager()
    
    await orchestrator.start()
    await brain.start(cns)
    await compiler.start(cns)
    
    memory.start()
    await memory.start_cns(cns)
    
    await knowledge.start()
    await knowledge.start_cns(cns)
    
    await agents.start()
    await agents.start_cns(cns)
    
    await app_scanner.start_cns(cns)
    await visual_perception.start_cns(cns)
    
    await controllers.start_cns(cns)
    await state_catalog.start_cns(cns)
    await popup_handler.start_cns(cns)
    
    # Trace list to record actual events
    trace = []
    
    async def trace_monitor(env: EventEnvelope):
        payload = env.payload
        event_type = payload.get("event_type")
        if event_type:
            trace.append(event_type)
            print(f"[TRACE] {event_type} emitted by {env.source_organ}")
            
    await cns.subscribe("sys.events", "trace_monitor", trace_monitor)
    
    # Fire UI input
    task_id = str(uuid.uuid4())
    payload = {
        "payload": {"command": "Open OBS, configure Display Capture, record for 30 seconds", "args": {}},
        "request_id": task_id
    }
    
    print("Dispatching USER_INPUT to CNS...")
    await cns.publish(EventEnvelope(topic="sock.cns.inbound", source_organ="system_boot", payload=payload))
    
    # Wait for execution loop to settle (wait for TASK_COMPLETED or timeout)
    timeout_count = 0
    while timeout_count < 30:
        if "TASK_COMPLETED" in trace:
            break
        await asyncio.sleep(1)
        timeout_count += 1
    
    required_events = [
        "TASK_CREATED",
        "INTENT_NORMALIZATION_STARTED",
        "INTENT_NORMALIZATION_COMPLETED",
        "COMPILATION_STARTED",
        "COMPILATION_COMPLETED",
        "AGENTS_STARTED",
        "AGENT_ASSIGNED",
        "SCAN_STARTED",
        "SCAN_COMPLETED",
        "CONTROLLER_EXECUTING",
        "AGENTS_COMPLETED",
        "VERIFICATION_STARTED",
        "VERIFICATION_COMPLETED",
        "TASK_COMPLETED"
    ]
    
    print("\n--- TEST RESULTS ---")
    success = True
    print("Trace list:")
    for t in trace:
        print(f"  - {t}")
        
    for req in required_events:
        if req not in trace:
            print(f"[MISSING] EVENT: {req}")
            success = False
        else:
            print(f"[VERIFIED] EVENT: {req}")
            
    if success:
        print("\n[PASSED] GOLDEN TEST: Full Event-Driven Lifecycle Confirmed.")
    else:
        print("\n[FAILED] GOLDEN TEST: Architectural bypass detected. Execution did not flow through the EventBus.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(golden_test())
