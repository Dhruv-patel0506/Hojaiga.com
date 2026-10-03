import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

app = FastAPI()

@app.websocket("/hojaiga")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🟢 Frontend connected to CNS")
    try:
        # 1. Spawn an agent at Reception (Input Portal area)
        spawn_cmd = {
            "type": "SPAWN_AGENT",
            "payload": {"id": "Agent1", "x": 27, "y": 45, "organName": "Test Agent"}
        }
        await websocket.send_text(json.dumps(spawn_cmd))
        print("Spawned Agent1 at Reception")

        # Wait a moment for the frontend to render it
        await asyncio.sleep(2)

        # 2. Tell the agent to walk directly into the Reception->CNS suction portal!
        move_cmd = {
            "type": "MOVE_AGENT",
            "payload": {"id": "Agent1", "targetX": 30, "targetY": 36}
        }
        await websocket.send_text(json.dumps(move_cmd))
        print("Sent MOVE_AGENT command. Agent should now walk and get SLURPED!")

        while True:
            # Keep the connection alive
            await websocket.receive_text() 
    except WebSocketDisconnect:
        print("🔴 Frontend disconnected")

if __name__ == "__main__":
    print("Starting CNS WebSocket Server on port 8001...")
    uvicorn.run(app, host="0.0.0.0", port=8001)
