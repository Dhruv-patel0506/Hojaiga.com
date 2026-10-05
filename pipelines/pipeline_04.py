import sys
import os
import asyncio
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))

from core_organs.organ_05_controllers import ControllersCore, ControllerTaskRequest, TargetController
import core_organs.organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 04: Organ 2 (CNS) -> Organ 5 (Controllers)")
    
    # 1. Initialize CNS
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize Controllers Organ
    controllers = ControllersCore()
    print("[Controllers] Organ initialized.")

    # 3. Simulate Connection via CNS Master Socket
    envelope = cns.EventEnvelope(
        topic="controllers.ready",
        source_organ="05",
        payload={"status": "online"}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event 'controllers.ready' published to {delivered} subscribers.")

    # 4. Dispatch Task Request to Controllers
    print("[Pipeline] Dispatching task request to Controllers...")
    task_req = ControllerTaskRequest(
        task_id=str(uuid.uuid4()),
        target_controller=TargetController.EXECUTION,
        action="ping"
        # Removed payload argument
    )
    result = await controllers.dispatch(task_req)
    print(f"[Controllers] Dispatch result: {result}")

    # 5. Shutdown
    await kernel.shutdown()
    print("[Pipeline] Connection test successful.")

if __name__ == "__main__":
    # Modern Compliant Pattern (Python 3.11+)
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(run_pipeline())
    else:
        asyncio.run(run_pipeline())
