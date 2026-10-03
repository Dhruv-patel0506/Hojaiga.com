import sys
import os
import asyncio
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))

from core_organs.organ_07_security import SecurityKernel, SocketAuthRequest, SecurityState
import core_organs.organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 06: Organ 2 (CNS) -> Organ 7 (Security)")
    
    # 1. Initialize CNS
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize Security Organ
    base_dir = Path(os.path.dirname(__file__)).parent
    security = SecurityKernel(base_dir)
    print(f"[Security] Organ initialized in state: {security.state}")

    # Security must be unlocked to be operational
    security.unlock("init_master_key")
    print(f"[Security] Organ unlocked. State: {security.state}")

    # 3. Simulate Connection via CNS Master Socket
    envelope = cns.EventEnvelope(
        topic="security.ready",
        source_organ="07",
        payload={"status": "online"}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event 'security.ready' published to {delivered} subscribers.")

    # 4. Dispatch Auth Check to Security Organ
    print("[Pipeline] Dispatching socket auth request to Security...")
    import uuid
    auth_req = SocketAuthRequest(
        request_id=str(uuid.uuid4()),
        source_organ="01",
        target_organ="07",
        requested_action="connect"
    )
    result = security.authorize_socket_connection(auth_req)
    print(f"[Security] Auth verdict: {result}")

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
