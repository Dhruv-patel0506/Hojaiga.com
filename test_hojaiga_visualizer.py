import asyncio
import uuid
import sys
import websockets
import json
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
from hojaiga_visualizer_server import WorkflowVisualizerServer

async def setup_test_env():
    cns = EventBus()
    audit = AuditSystem(storage_dir="./audit_logs_test_vis")
    security = SecurityKernel(Path("."))
    
    orchestrator = TaskOrchestrator(cns, audit, security)
    brain = BrainOrgan()
    compiler = WorkflowCompilerKernel()
    state_catalog = StateCatalogOrgan()
    
    await orchestrator.start()
    await brain.start(cns)
    await compiler.start(cns)
    await state_catalog.start_cns(cns)
    
    visualizer = WorkflowVisualizerServer(cns, port=8766)
    await visualizer.start()
    
    return cns, orchestrator, visualizer

async def test_visualizer_receives_events():
    print("\nRunning Test: Visualizer receives real CNS events.")
    cns, orchestrator, visualizer = await setup_test_env()
    
    received_events = []
    
    async def ws_client():
        try:
            async with websockets.connect("ws://127.0.0.1:8766") as ws:
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        data = json.loads(msg)
                        received_events.append(data["topic"])
                    except asyncio.TimeoutError:
                        break
        except Exception as e:
            print(f"WS client error: {e}")

    client_task = asyncio.create_task(ws_client())
    
    # Wait for connection
    await asyncio.sleep(0.5)
    
    # Emit test event
    task_id = str(uuid.uuid4())
    await cns.publish(EventEnvelope(
        topic="sock.cns.inbound", 
        source_organ="system_boot", 
        payload={"payload": {"command": "test visualizer"}, "request_id": task_id}
    ))
    
    # Let system run
    await asyncio.sleep(2.0)
    
    # Clean up client
    await client_task
    await visualizer.stop()
    
    passed = "TASK_CREATED" in received_events and "INTENT_NORMALIZATION_STARTED" in received_events
    if passed:
        print("[PASS] Visualizer receives real CNS events")
    else:
        print(f"[FAIL] Missing expected events in visualizer stream: {received_events}")
        
    return passed

async def run_acceptance_tests():
    print("Starting Hojaiga Visualizer Acceptance Tests...")
    passed = await test_visualizer_receives_events()
    
    print("\nRUNTIME VISUALIZER GATE: " + ("PASS" if passed else "FAIL"))

if __name__ == "__main__":
    asyncio.run(run_acceptance_tests())
