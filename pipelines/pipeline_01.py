import sys
import os
import asyncio
import threading

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))

from core_organs.organ_01_brain import BrainOrgan, TaskRequest
import core_organs.organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 01: Organ 1 (Brain) -> Organ 2 (CNS)")
    
    # 1. Initialize Organ 2 (CNS)
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize Organ 1 (Brain)
    brain = BrainOrgan()
    print("[Brain] Organ initialized.")

    # 3. Define the connector (Pipeline)
    def on_brain_plan_emitted(payload):
        # When brain emits a plan, push it to CNS event bus
        # Note: EventBus.publish is async, so we use run_coroutine_threadsafe
        # But wait, we are in the same event loop in this script.
        pass

    # For this simple test, we just call handle_task directly
    # and manually bridge it into CNS as a published event.
    task = TaskRequest(task_id="test-task", raw_text="ping status please")
    print(f"[Pipeline] Sending task to Brain: {task.raw_text}")
    
    plan = brain.handle_task(task)
    print(f"[Brain] Plan generated: {plan.to_dict()}")

    # 4. Push plan into CNS
    envelope = cns.EventEnvelope(
        topic="brain.plan_emitted",
        source_organ="01",
        payload=plan.to_dict()
    )
    
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event published to {delivered} subscribers.")

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
