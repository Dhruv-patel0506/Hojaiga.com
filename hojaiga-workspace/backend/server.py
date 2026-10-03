import asyncio
import json
import websockets

async def wait_for_arrival(websocket, target_npc_id):
    async for message in websocket:
        data = json.loads(message)
        if data.get("type") == "TASK_COMPLETE" and data.get("npcId") == target_npc_id:
            return

async def run_pathfinding_test(websocket):
    await asyncio.sleep(2) 
    
    await websocket.send(json.dumps({
        "type": "MOVE_AGENT",
        "payload": {
            "npcId": "Brain", "targetZone": "zone_3",
            "targetX": 48, "targetY": 22 
        }
    }))
    
    await wait_for_arrival(websocket, "Brain")
    
    await websocket.send(json.dumps({
        "type": "UPDATE_STATUS",
        "payload": {
            "npcId": "Brain",
            "statusText": "Acquired the last puff. Morale +10.",
            "showThinkingBubble": True
        }
    }))
    
    await asyncio.sleep(3)
    
    await websocket.send(json.dumps({
        "type": "MOVE_AGENT",
        "payload": {
            "npcId": "Brain", "targetZone": "zone_2a",
            "targetX": 55, "targetY": 35 
        }
    }))
    
    await wait_for_arrival(websocket, "Brain")

async def main():
    async with websockets.serve(run_pathfinding_test, "localhost", 8000):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
