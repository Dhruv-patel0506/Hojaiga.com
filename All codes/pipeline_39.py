import sys
import os
import asyncio
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))
import core_organs.organ_02_cns_single_file as cns
try:
    import core_organs.organ_31_visual_perception as organ_31_visual_perception
except ImportError as e:
    print(f"Warning: could not import core_organs.organ_31_visual_perception as organ_31_visual_perception: {e}")

async def run_pipeline():
    print("Starting pipeline 39: Organ 2 (CNS) -> organ_31_visual_perception")
    kernel = cns.CNSKernel()
    await kernel.start()
    
    envelope = cns.EventEnvelope(
        topic="connection.test.organ_31_visual_perception",
        source_organ="39",
        payload={"status": "online"}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event published to {delivered} subscribers.")
    
    await kernel.shutdown()
    print("[Pipeline] Connection test successful for organ_31_visual_perception.")

if __name__ == "__main__":
    # Modern Compliant Pattern (Python 3.11+)
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(run_pipeline())
    else:
        asyncio.run(run_pipeline())
