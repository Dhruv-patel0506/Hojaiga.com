import sys
import os
import asyncio
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))
import core_organs.organ_02_cns_single_file as cns
try:
    import core_organs.organ_19_chrome_cdp_runtime as organ_19_chrome_cdp_runtime
except ImportError as e:
    print(f"Warning: could not import core_organs.organ_19_chrome_cdp_runtime as organ_19_chrome_cdp_runtime: {e}")

async def run_pipeline():
    print("Starting pipeline 18: Organ 2 (CNS) -> organ_19_chrome_cdp_runtime")
    kernel = cns.CNSKernel()
    await kernel.start()
    
    envelope = cns.EventEnvelope(
        topic="connection.test.organ_19_chrome_cdp_runtime",
        source_organ="18",
        payload={"status": "online"}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event published to {delivered} subscribers.")
    
    await kernel.shutdown()
    print("[Pipeline] Connection test successful for organ_19_chrome_cdp_runtime.")

if __name__ == "__main__":
    # Modern Compliant Pattern (Python 3.11+)
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(run_pipeline())
    else:
        asyncio.run(run_pipeline())
