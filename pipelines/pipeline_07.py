import sys
import os
import asyncio
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))

from core_runtime.infrastructure_organ import InfrastructureOrgan, QuotaRequest
import core_organs.organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 07: Organ 2 (CNS) -> Organ 9 (Infrastructure)")
    
    # 1. Initialize CNS
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize Infrastructure Organ
    infra = InfrastructureOrgan()
    infra.start()
    print(f"[Infrastructure] Organ initialized and started.")

    # 3. Simulate Connection via CNS Master Socket
    envelope = cns.EventEnvelope(
        topic="infrastructure.ready",
        source_organ="09",
        payload={"status": "online"}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event 'infrastructure.ready' published to {delivered} subscribers.")

    # 4. Dispatch Quota Request to Infrastructure Organ
    print("[Pipeline] Dispatching quota request to Infrastructure...")
    quota_req = QuotaRequest(
        requesting_organ="02",
        cpu_weight=2.0,
        max_ram_mb=512.0,
        priority="high"
    )
    result = infra.allocate_quota(quota_req)
    print(f"[Infrastructure] Quota verdict: {result}")

    # 5. Shutdown
    infra.shutdown()
    await kernel.shutdown()
    print("[Pipeline] Connection test successful.")

if __name__ == "__main__":
    # Modern Compliant Pattern (Python 3.11+)
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(run_pipeline())
    else:
        asyncio.run(run_pipeline())
