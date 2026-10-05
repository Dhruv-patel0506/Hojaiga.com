import sys
import os
import asyncio
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes', 'core_organs')))

from core_organs.organ_06_automation import TaskEngine, BrowserManager, GUIManager, ClipboardManager, RetryManager, TaskRequest, WindowManager, MultiTouch_3D_Physics_Engine
from core_organs import organ_02_cns_single_file as cns

async def run_pipeline():
    print("Starting pipeline 05: Organ 2 (CNS) -> Organ 6 (Automation)")
    
    # 1. Initialize CNS
    kernel = cns.CNSKernel()
    await kernel.start()
    print("[CNS] Kernel started and listening.")

    # 2. Initialize Automation Organ
    browser = BrowserManager()
    win = WindowManager()
    gui = GUIManager(win)
    clip = ClipboardManager()
    retry = RetryManager()
    physics = MultiTouch_3D_Physics_Engine()
    automation = TaskEngine(browser, gui, clip, retry, physics)
    print("[Automation] Organ initialized.")

    # 3. Simulate Connection via CNS Master Socket
    envelope = cns.EventEnvelope(
        topic="automation.ready",
        source_organ="06",
        payload={"status": "online"}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event 'automation.ready' published to {delivered} subscribers.")

    # 4. Dispatch Task to Automation Organ
    print("[Pipeline] Dispatching action request to Automation...")
    task_req = TaskRequest(
        task_id=str(uuid.uuid4()),
        capability="navigation",
        target="about:blank",
        runtime="browser",
        params={}
    )
    result = await automation.submit(task_req)
    print(f"[Automation] Action result: {result.state}")

    # 5. Shutdown
    await automation.shutdown()
    await kernel.shutdown()
    print("[Pipeline] Connection test successful.")

if __name__ == "__main__":
    # Modern Compliant Pattern (Python 3.11+)
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(run_pipeline())
    else:
        asyncio.run(run_pipeline())
