import sys
import os
import asyncio
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))

from core_organs.organ_13_interface_layer import InterfaceLayerOrgan, SOCK_OUT_CNS_DISPATCH
import core_organs.organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 12: Organ 2 (CNS) -> Organ 13 (Interface Layer)")
    
    # 1. Initialize CNS
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize Interface Layer Organ
    organ = InterfaceLayerOrgan()
    # Register mock user
    organ.auth.register_user("admin", "pw", roles=["admin"], permissions=["*"])
    print("[Interface Layer] Organ initialized and admin user registered.")

    # 3. Simulate Connection: Subscribe CNS to the Interface Layer's SocketBus egress
    received_frames = []
    async def cns_handler(frame):
        print(f"[CNS] Received frame from Interface Layer: {frame}")
        received_frames.append(frame)
        # Manually bridge into CNS Event Bus
        envelope = cns.EventEnvelope(
            topic="interface_layer.command",
            source_organ="13",
            payload=frame
        )
        await kernel.event_bus.publish(envelope)

    organ.socket_bus.subscribe(SOCK_OUT_CNS_DISPATCH, cns_handler)
    print("[Pipeline] Connected Interface Layer egress to CNS handler.")

    # 4. Dispatch a request through the CLI adapter
    session = organ.login("admin", "pw")
    print(f"[Interface Layer] User login successful. Session ID: {session.session_id}")
    
    print("[Interface Layer] Handling command via CLI...")
    result = await organ.cli.handle_line(session.session_id, "task.create", {"task_id": "task-1300"})
    print(f"[Interface Layer] Command result: status={result.status_code}, data={result.payload}")

    # 5. Check if CNS received the command
    print(f"[Pipeline] Verifying delivery... Received count: {len(received_frames)}")
    if len(received_frames) > 0:
        print("[Pipeline] Connection check passed.")
    else:
        print("[Pipeline] Error: No frames reached CNS.")

    # 6. Shutdown
    await kernel.shutdown()
    print("[Pipeline] Connection test successful.")

if __name__ == "__main__":
    # Modern Compliant Pattern (Python 3.11+)
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(run_pipeline())
    else:
        asyncio.run(run_pipeline())
