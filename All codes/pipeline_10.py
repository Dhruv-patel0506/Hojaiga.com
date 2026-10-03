import sys
import os
import asyncio
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))

from core_organs.organ_11_interface import InterfaceKernel
import core_organs.organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 10: Organ 2 (CNS) -> Organ 11 (Interface)")
    
    # 1. Initialize CNS
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize Interface Organ
    interface = InterfaceKernel()
    interface.start()
    print(f"[Interface] Organ initialized in mode: {interface.ui_mode}")

    # 3. Simulate Connection via CNS Master Socket
    envelope = cns.EventEnvelope(
        topic="interface.ready",
        source_organ="11",
        payload={"status": "online"}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event 'interface.ready' published to {delivered} subscribers.")

    # 4. Dispatch a simulated user goal
    print("[Pipeline] Dispatching user goal to Interface...")
    interface.submit_user_goal("Check my emails and summarize", source="cli")
    print(f"[Interface] Goal submitted.")

    # 5. Shutdown
    interface.stop()
    await kernel.shutdown()
    print("[Pipeline] Connection test successful.")

if __name__ == "__main__":
    # Modern Compliant Pattern (Python 3.11+)
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(run_pipeline())
    else:
        asyncio.run(run_pipeline())
