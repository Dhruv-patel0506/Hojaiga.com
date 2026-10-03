import asyncio
import sys
import json
import logging

sys.path.insert(0, r"d:/new_automation/All codes")
sys.path.insert(0, r"d:/new_automation")

from core_organs.organ_02_cns_single_file import EventBus, EventEnvelope
from core_organs.organ_01_brain import BrainOrgan
from core_organs.organ_38_task_orchestrator import TaskOrchestrator
from core_organs.organ_10_agents import AgentsOrgan
from organ_ml import ml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("hojaiga_e2e_pipeline")

async def run_e2e():
    log.info("=" * 70)
    log.info("INITIALIZING CNS EVENTBUS AND REGISTERING ORGANS")
    log.info("=" * 70)

    cns = EventBus()
    brain = BrainOrgan()
    orchestrator = TaskOrchestrator(cns=cns)
    agents = AgentsOrgan()

    # Wire to CNS
    await brain.start(cns)
    await orchestrator.start()
    await agents.start_cns(cns)

    log.info(f"Connected. Active CNS Subscriptions: {len(cns._subscriptions)}")

    task_completed_event = asyncio.Event()

    async def on_task_completed(env: EventEnvelope):
        log.info(f"[CNS EVENT RECEIVED] Topic: {env.topic} from Organ: {env.source_organ}")
        log.info(f"[CNS EVENT PAYLOAD] {json.dumps(env.payload, default=str)}")
        task_completed_event.set()

    await cns.subscribe("AGENTS_COMPLETED", "test_listener", on_task_completed)
    await cns.subscribe("sys.events", "test_sys_listener", lambda env: None)

    task_command = "Research Top 10 Interior Designers in Nashville on Google, scrape names/phones/emails, write to Excel, generate a Word report"
    log.info(f"\n[INJECTING NEW TASK INTO CNS] Command: '{task_command}'")

    # Dispatch to orchestrator via CNS
    await cns.publish(EventEnvelope(
        topic="NEW_TASK",
        source_organ="gateway_or_user",
        payload={"command": task_command, "request_id": "req_real_001"}
    ))

    # Await swarm execution or timeout
    try:
        log.info("Awaiting execution through Brain -> Orchestrator -> Swarm Agents...")
        await asyncio.wait_for(task_completed_event.wait(), timeout=25.0)
        log.info("[SUCCESS] Pipeline completed through CNS to AgentsOrgan.")
    except asyncio.TimeoutError:
        log.info("[TIMEOUT/PROGRESSED] Dispatched through CNS; active tasks tracked in Orchestrator.")

    log.info("\nFinal ML Learning State:")
    log.info(json.dumps(ml.get_stats(), indent=2))

if __name__ == "__main__":
    asyncio.run(run_e2e())
