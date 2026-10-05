import sys
import os
import asyncio
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))

from core_organs.organ_14_llm_runtime_single_file import build_llm_runtime_organ, InferenceRequest
import core_organs.organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 13: Organ 2 (CNS) -> Organ 14 (LLM Runtime)")
    
    # 1. Initialize CNS
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize LLM Runtime Organ
    model_store = "d:/new_automation/scratch_models"
    os.makedirs(model_store, exist_ok=True)
    
    # Build LLM Runtime Gateway
    gateway = build_llm_runtime_organ(model_store_dir=model_store)
    print(f"[LLM Runtime] Gateway initialized. State: {gateway.runtime_state()}")

    # 3. Simulate Connection via CNS Master Socket
    envelope = cns.EventEnvelope(
        topic="llm_runtime.ready",
        source_organ="14",
        payload={"status": "online", "state": str(gateway.runtime_state())}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event 'llm_runtime.ready' published to {delivered} subscribers.")

    # 4. Perform a lightweight health snapshot check
    report = gateway.health_report()
    print(f"[LLM Runtime] Health report: {report}")

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
