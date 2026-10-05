import sys
import os
import asyncio
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))

from core_organs.organ_08_learning import LearningKernel, TracePayload
import core_organs.organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 08: Organ 2 (CNS) -> Organ 8 (Learning)")
    
    # 1. Initialize CNS
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize Learning Organ
    learning = LearningKernel()
    print(f"[Learning] Organ initialized in state: {learning.state}")

    # 3. Simulate Connection via CNS Master Socket
    envelope = cns.EventEnvelope(
        topic="learning.ready",
        source_organ="08",
        payload={"status": "online"}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event 'learning.ready' published to {delivered} subscribers.")

    # 4. Dispatch Trace Evaluation Request to Learning Organ
    print("[Pipeline] Dispatching evaluate task outcome to Learning...")
    payload = {
        "trace_id": "trace-1234",
        "task_id": "task-5678",
        "status": "SUCCESS",
        "duration_ms": 1500,
        "goal": "initialize cluster",
        "executing_organ": "02",
        "tool_used": "cns_kernel",
        "error_log": ""
    }
    
    result = await learning.evaluate_task_outcome(payload)
    print(f"[Learning] Evaluation result: {result}")

    # 5. Shutdown
    learning.close()
    await kernel.shutdown()
    print("[Pipeline] Connection test successful.")

if __name__ == "__main__":
    # Modern Compliant Pattern (Python 3.11+)
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(run_pipeline())
    else:
        asyncio.run(run_pipeline())
