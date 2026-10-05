import sys, asyncio, subprocess, time, json, os

sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation")

from core_organs.organ_02_cns_single_file import EventBus, EventEnvelope
from core_organs.organ_05_controllers import ControllersCore
from core_organs.organ_19_chrome_cdp_runtime import IPCFrame, Organ19OpCode, IPC_LENGTH_HEADER

async def main():
    cns = EventBus()
    controllers = ControllersCore()
    await controllers.start_cns(cns)
    
    print("[1] Sending LAUNCH_BROWSER via CNS...")
    launch_event = EventEnvelope(
        topic="INVOKE_CONTROLLER", source_organ="test",
        payload={
            "task_id": "test-extract",
            "target_controller": "chrome",
            "action": "LAUNCH_BROWSER",
            "parameters": {"payload": {"headless": False, "profile_id": "Profile 1"}}
        }
    )
    await cns.publish(launch_event)
    await asyncio.sleep(3)
    
    print("[2] Sending NAVIGATE to Google...")
    nav_event = EventEnvelope(
        topic="INVOKE_CONTROLLER", source_organ="test",
        payload={
            "task_id": "test-extract",
            "target_controller": "chrome",
            "action": "NAVIGATE",
            "parameters": {"payload": {"url": "https://www.google.com", "session_id": "DEFAULT"}}
        }
    )
    await cns.publish(nav_event)
    await asyncio.sleep(3)

    print("[3] Sending EXTRACT_DATA (GET_DOM_TREE)...")
    t0 = time.time()
    extract_event = EventEnvelope(
        topic="INVOKE_CONTROLLER", source_organ="test",
        payload={
            "task_id": "test-extract",
            "target_controller": "chrome",
            "action": "EXTRACT_DATA",
            "parameters": {"payload": {"session_id": "DEFAULT", "pierce_shadow_dom": True}}
        }
    )
    await cns.publish(extract_event)
    await asyncio.sleep(10)
    print(f"[3] Done ({time.time()-t0:.1f}s)")

    print("\n[4] Sending TYPE_TEXT to search...")
    type_event = EventEnvelope(
        topic="INVOKE_CONTROLLER", source_organ="test",
        payload={
            "task_id": "test-extract",
            "target_controller": "chrome",
            "action": "TYPE",
            "parameters": {"payload": {"selector": "textarea[name='q']", "text": "interior designers tennessee", "session_id": "DEFAULT"}}
        }
    )
    await cns.publish(type_event)
    await asyncio.sleep(3)

    print("[5] Sending PRESS_KEY Enter...")
    enter_event = EventEnvelope(
        topic="INVOKE_CONTROLLER", source_organ="test",
        payload={
            "task_id": "test-extract",
            "target_controller": "chrome",
            "action": "PRESS_KEY",
            "parameters": {"payload": {"key": "Enter", "session_id": "DEFAULT"}}
        }
    )
    await cns.publish(enter_event)
    await asyncio.sleep(3)

    print("[6] Sending EXTRACT_DATA again after search...")
    t0 = time.time()
    extract2_event = EventEnvelope(
        topic="INVOKE_CONTROLLER", source_organ="test",
        payload={
            "task_id": "test-extract",
            "target_controller": "chrome",
            "action": "EXTRACT_DATA",
            "parameters": {"payload": {"session_id": "DEFAULT", "pierce_shadow_dom": True}}
        }
    )
    await cns.publish(extract2_event)
    await asyncio.sleep(15)
    print(f"[6] Done ({time.time()-t0:.1f}s)")

    print("\n=== ALL STEPS DISPATCHED ===")
    print("Check Chrome window to verify actions executed.")

asyncio.run(main())
