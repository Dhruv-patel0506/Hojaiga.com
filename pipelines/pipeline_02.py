import sys
import os
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))

from core_organs.organ_03_memory import MemoryCore, MemoryClient
import core_organs.organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 02: Organ 2 (CNS) -> Organ 3 (Memory)")
    
    # 1. Initialize CNS
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize Memory Organ
    memory_core = MemoryCore()
    memory_core.start()
    print("[Memory] Organ initialized and started.")

    # 3. Test Connection
    client = MemoryClient(memory_core)
    
    # Test Working Memory
    print("[Pipeline] Testing Working Memory...")
    client.store_working("connection_status", "active")
    val = client.fetch_working("connection_status")
    print(f"[Memory] Retrieved: connection_status = {val}")
    
    # Test Session Room
    print("[Pipeline] Testing Session Memory...")
    room_id = client.create_room(metadata={"context": "pipeline_02_test"})
    client.append_context(room_id, "system", "Organ 3 connected to Organ 2.")
    history = client.history(room_id)
    print(f"[Memory] Session room {room_id} history length: {len(history)}")

    # 4. Integrate with CNS EventBus
    envelope = cns.EventEnvelope(
        topic="memory.ready",
        source_organ="03",
        payload={"status": "online", "working_keys": 1, "rooms": 1}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event 'memory.ready' published to {delivered} subscribers.")

    # 5. Shutdown
    memory_core.stop()
    await kernel.shutdown()
    print("[Pipeline] Connection test successful.")

if __name__ == "__main__":
    # Modern Compliant Pattern (Python 3.11+)
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(run_pipeline())
    else:
        asyncio.run(run_pipeline())
