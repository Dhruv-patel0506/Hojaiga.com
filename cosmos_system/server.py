import asyncio
import json
import random
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active connected UI clients
connected_clients: list[WebSocket] = []

# Mock state for nodes across clusters
node_states = {
    "tutor": {"status": "ACTIVE", "task": "Generating Socratic math prompt", "health": 1.0},
    "animation": {"status": "RENDERING", "task": "Interpolating 60FPS SVG keyframes", "health": 1.0},
    "ppt": {"status": "SYNTHESIZING", "task": "Laying out executive summary charts", "health": 1.0},
    "automation": {"status": "ORCHESTRATING", "task": "Syncing webhook mesh across 42 workers", "health": 1.0},
    "healing": {"status": "MONITORING", "task": "Zero memory leaks detected; mesh stable", "health": 1.0}
}

class CosmosManager:
    async def broadcast(self, message: dict):
        for connection in connected_clients:
            try:
                await connection.send_text(json.dumps(message))
            except:
                pass

manager = CosmosManager()

@app.websocket("/ws/cosmos")
async def cosmos_websocket(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            packet = json.loads(data)
            
            # Handle client actions (e.g., click node, inject fault, spawn node)
            action = packet.get("action")
            if action == "inspect_node":
                node_id = packet.get("nodeId")
                cluster_type = packet.get("clusterType")
                # Send back real-time telemetry stream for this specific node
                await websocket.send_text(json.dumps({
                    "type": "node_stream",
                    "nodeId": node_id,
                    "telemetry": node_states.get(cluster_type, {"status": "ACTIVE", "task": "Processing...", "health": 1.0})
                }))
            elif action == "inject_fault":
                cluster_type = packet.get("clusterType")
                if cluster_type in node_states:
                    node_states[cluster_type]["health"] = 0.1
                    node_states[cluster_type]["status"] = "FAULT_DETECTED"
                    await manager.broadcast({
                        "type": "fault_alert",
                        "cluster": cluster_type,
                        "message": f"Fault injected into {cluster_type}. Immune mesh initiating auto-heal."
                    })
                    # Trigger auto-heal after 2 seconds
                    asyncio.create_task(self_heal_worker(cluster_type))
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

async def self_heal_worker(cluster_type: str):
    await asyncio.sleep(2.0)
    if cluster_type in node_states:
        node_states[cluster_type]["health"] = 1.0
        node_states[cluster_type]["status"] = "ACTIVE"
        await manager.broadcast({
            "type": "heal_success",
            "cluster": cluster_type,
            "message": f"Immune mesh successfully patched and restored {cluster_type} node."
        })

# Background telemetry broadcaster
@app.on_event("startup")
async def start_background_telemetry():
    async def loop():
        while True:
            await asyncio.sleep(1.5)
            # Randomly fluctuate metrics to show live system heartbeat
            await manager.broadcast({
                "type": "heartbeat",
                "activeNodes": random.randint(110, 135),
                "resilience": round(99.4 + random.random() * 0.5, 2)
            })
    asyncio.create_task(loop())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)