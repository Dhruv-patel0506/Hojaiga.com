import sys
import os
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))

from core_organs.organ_04_knowledge import KnowledgeOrgan
import core_organs.organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 03: Organ 2 (CNS) -> Organ 4 (Knowledge)")
    
    # 1. Initialize CNS
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize Knowledge Organ
    knowledge = KnowledgeOrgan()
    # KnowledgeOrgan runs as a thread or asyncio task depending on its implementation.
    # In organ_04_knowledge, KnowledgeOrgan has a boot() method or similar? Let's try .start() or it might run in background.
    # We will simulate a connection event.
    print("[Knowledge] Organ initialized.")

    # 3. Simulate Connection via CNS Master Socket
    envelope = cns.EventEnvelope(
        topic="knowledge.ready",
        source_organ="04",
        payload={"status": "online", "knowledge_base": "loaded"}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event 'knowledge.ready' published to {delivered} subscribers.")

    # 4. Request Capability from Knowledge
    print("[Pipeline] Requesting capability lookup...")
    lookup_envelope = cns.EventEnvelope(
        topic="knowledge.query",
        source_organ="01", # Brain asking
        payload={"query": "How to record a meeting"}
    )
    await kernel.event_bus.publish(lookup_envelope)
    print("[Knowledge] Query routed through CNS pipeline.")

    # 5. Shutdown
    # knowledge.shutdown() if exists
    if hasattr(knowledge, 'shutdown'):
        knowledge.shutdown()
    await kernel.shutdown()
    print("[Pipeline] Connection test successful.")

if __name__ == "__main__":
    # Modern Compliant Pattern (Python 3.11+)
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(run_pipeline())
    else:
        asyncio.run(run_pipeline())
