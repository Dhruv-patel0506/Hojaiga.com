import sys
import os
import asyncio
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))

from core_organs.organ_15_external_connectors import ConnectorGateway, ConnectorCommandRequest, ConnectorType
import core_organs.organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 14: Organ 2 (CNS) -> Organ 15 (External Connectors)")
    
    # 1. Initialize CNS
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize External Connectors Gateway
    gateway = ConnectorGateway()
    gateway.register_default_connectors()
    print("[External Connectors] Gateway initialized.")

    # 3. Simulate Connection via CNS Master Socket
    envelope = cns.EventEnvelope(
        topic="external_connectors.ready",
        source_organ="15",
        payload={"status": "online"}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event 'external_connectors.ready' published to {delivered} subscribers.")

    # 4. Route a lightweight filesystem list command
    print("[External Connectors] Routing file list command...")
    request = ConnectorCommandRequest(
        connector_type=ConnectorType.FILESYSTEM,
        action_name="list",
        payload={"path": "."}
    )
    response = await gateway.route(request)
    print(f"[External Connectors] File list response status: {response.status}")
    print(f"[External Connectors] Found files: {list(response.result_payload.keys())[:5] if response.result_payload else []}")

    # 5. Shutdown
    await gateway.shutdown()
    await kernel.shutdown()
    print("[Pipeline] Connection test successful.")

if __name__ == "__main__":
    # Modern Compliant Pattern (Python 3.11+)
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(run_pipeline())
    else:
        asyncio.run(run_pipeline())
