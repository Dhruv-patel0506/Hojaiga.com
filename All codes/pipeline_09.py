import sys
import os
import asyncio
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))

from core_organs.organ_10_agents import AgentsOrgan, AgentSpawnPayload
import core_organs.organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 09: Organ 2 (CNS) -> Organ 10 (Agents)")
    
    # 1. Initialize CNS
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize Agents Organ
    agents = AgentsOrgan()
    await agents.start()
    print(f"[Agents] Organ initialized and started.")

    # 3. Simulate Connection via CNS Master Socket
    envelope = cns.EventEnvelope(
        topic="agents.ready",
        source_organ="10",
        payload={"status": "online"}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event 'agents.ready' published to {delivered} subscribers.")

    # 4. Dispatch Agent Spawn Request
    print("[Pipeline] Dispatching agent spawn request to Agents Organ...")
    spawn_req = AgentSpawnPayload(
        task_id="task-100",
        role_id="CodeAgent",
        session_room_id="room-555",
        assigned_sub_goal="Review new code"
    )
    handle = await agents.spawn_agent(spawn_req)
    print(f"[Agents] Spawn verdict: {handle}")

    # 5. Shutdown
    await agents.stop()
    await kernel.shutdown()
    print("[Pipeline] Connection test successful.")

if __name__ == "__main__":
    # Modern Compliant Pattern (Python 3.11+)
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(run_pipeline())
    else:
        asyncio.run(run_pipeline())
