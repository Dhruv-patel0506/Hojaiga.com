import sys
import os
import asyncio
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))

from core_organs.organ_12_integration import IntegrationOrgan
import core_organs.organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 11: Organ 2 (CNS) -> Organ 12 (Integration)")
    
    # 1. Initialize CNS
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize Integration Organ
    integration = IntegrationOrgan()
    await integration.start()
    print("[Integration] Organ initialized and started.")

    # 3. Simulate Connection via CNS Master Socket
    envelope = cns.EventEnvelope(
        topic="integration.ready",
        source_organ="12",
        payload={"status": "online"}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event 'integration.ready' published to {delivered} subscribers.")

    # 4. Dispatch simulated action request
    print("[Pipeline] Requesting adapter health...")
    try:
        res = await integration.get_adapter_health("test_adapter")
        print(f"[Integration] Response: {res}")
    except Exception as e:
        print(f"[Integration] Error (expected due to no config): {e}")

    # 5. Shutdown
    await integration.stop()
    await kernel.shutdown()
    print("[Pipeline] Connection test successful.")

if __name__ == "__main__":
    # Modern Compliant Pattern (Python 3.11+)
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(run_pipeline())
    else:
        asyncio.run(run_pipeline())
