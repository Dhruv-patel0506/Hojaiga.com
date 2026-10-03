import asyncio
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent / "All codes"))
from test_hojaiga_browser_autonomy import HojaigaRuntimeInstance, start_test_server
from core_organs.organ_02_cns_single_file import EventEnvelope
import json

async def run_trace():
    server = start_test_server(9991)
    test_url = "http://127.0.0.1:9991"
    
    runtime = HojaigaRuntimeInstance()
    await runtime.start()
    
    events = []
    
    async def global_monitor(env: EventEnvelope):
        events.append({
            "topic": env.topic,
            "source_organ": env.source_organ,
            "payload": env.payload
        })
        print(f"EVENT: {env.topic} from {env.source_organ}: {env.payload}")
        
    # Subscribe to specific topics since wildcard might not work on EventBus
    topics_to_monitor = [
        "sys.events", "REPLANNING_REQUESTED", "TASK_FAILED", "TASK_COMPLETED", 
        "sock.cns.inbound", "CONTROLLER_EXECUTION_COMPLETED"
    ]
    for topic in topics_to_monitor:
        await runtime.cns.subscribe(topic, f"monitor_{topic}", global_monitor)
    
    task_id = "test-v2-1234"
    command = "Multi-step interact on " + test_url
    
    print("Publishing command...")
    await runtime.cns.publish(EventEnvelope(
        topic="sock.cns.inbound", 
        source_organ="interface", 
        payload={"payload": {"command": command}, "request_id": task_id}
    ))
    
    await asyncio.sleep(10) # Wait for execution
    await runtime.stop()
    
    with open("cns_trace.json", "w") as f:
        json.dump(events, f, indent=2)

if __name__ == "__main__":
    asyncio.run(run_trace())
