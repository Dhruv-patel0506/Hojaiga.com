import asyncio
import json
import struct
import websockets
import threading
import time
import sys
import uuid

# Protocol constants
MAX_PAYLOAD_BYTES = 32 * 1024 * 1024
HEADER_STRUCT = struct.Struct("<IH")  # length(uint32) + type(uint16)

class MessageType:
    REGISTER_SOCKET = 1
    SUBSCRIBE_EVENT = 4

connected_clients = set()
loop = asyncio.new_event_loop()

# Track mock agent IDs to match Pixel Agents requirements
agents = {
    "brain": 1,
    "cns": 2,
    "runner": 3
}

def encode_frame(message_type: int, payload: dict) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    header = HEADER_STRUCT.pack(len(body), message_type)
    return header + body

def broadcast_to_clients(payload):
    if not connected_clients:
        return
    ws_msg = json.dumps(payload)
    asyncio.run_coroutine_threadsafe(broadcast_coro(ws_msg), loop)

async def broadcast_coro(msg):
    websockets.broadcast(connected_clients, msg)

def emit_pixel_event(event_type, **kwargs):
    payload = {"type": event_type}
    payload.update(kwargs)
    broadcast_to_clients(payload)

def handle_hojaiga_event(topic, payload):
    print(f"Mapping Hojaiga event: {topic}")
    
    if topic == "TASK_CREATED":
        emit_pixel_event("agentToolStart", id=agents["cns"], toolId=str(uuid.uuid4()), status="active", toolName="Dispatching Task")
    
    elif topic == "ACTION_REQUESTED":
        emit_pixel_event("agentCreated", id=agents["runner"], folderName="Execution")
        emit_pixel_event("agentToolStart", id=agents["runner"], toolId=str(uuid.uuid4()), status="active", toolName="Running Browser Action")
        
    elif topic == "ACTION_FAILED":
        emit_pixel_event("agentToolStart", id=agents["runner"], toolId=str(uuid.uuid4()), status="active", toolName="[!] Error! Seeking Recovery")
        
    elif topic == "SECURITY_CHECK":
        emit_pixel_event("agentToolStart", id=agents["runner"], toolId=str(uuid.uuid4()), status="active", toolName="Checking Security")
        
    elif topic == "TASK_COMPLETED":
        emit_pixel_event("agentToolDone", id=agents["runner"], toolId="all")
        emit_pixel_event("agentToolStart", id=agents["runner"], toolId=str(uuid.uuid4()), status="active", toolName="Delivering Result")
        time.sleep(2)
        emit_pixel_event("agentClosed", id=agents["runner"])
        emit_pixel_event("agentToolDone", id=agents["cns"], toolId="all")

def cns_listener_sync():
    pipe_path = r"\\.\pipe\hojaiga_cns_master"
    print(f"Connecting to CNS at {pipe_path}...")
    
    while True:
        try:
            with open(pipe_path, "r+b") as pipe:
                print("Connected to CNS!")
                
                # Register
                pipe.write(encode_frame(MessageType.REGISTER_SOCKET, {"organ_name": "organ_99_visualizer"}))
                pipe.flush()
                
                # Subscribe
                pipe.write(encode_frame(MessageType.SUBSCRIBE_EVENT, {"topic_pattern": "*"}))
                pipe.flush()
                
                while True:
                    header_bytes = pipe.read(HEADER_STRUCT.size)
                    if not header_bytes or len(header_bytes) != HEADER_STRUCT.size:
                        break
                    
                    length, msg_type = HEADER_STRUCT.unpack(header_bytes)
                    payload_bytes = pipe.read(length)
                    
                    if len(payload_bytes) != length:
                        break
                    
                    try:
                        envelope = json.loads(payload_bytes.decode("utf-8"))
                        handle_hojaiga_event(envelope.get("topic", ""), envelope)
                    except Exception as e:
                        pass
        except Exception as e:
            time.sleep(2)

async def ws_handler(websocket):
    print("New visualizer frontend connected!")
    connected_clients.add(websocket)
    
    # Initialize basic layout and standing persistent agents (Brain, CNS)
    emit_pixel_event("agentCreated", id=agents["brain"], folderName="Executive Suite")
    emit_pixel_event("agentCreated", id=agents["cns"], folderName="Dispatch Hub")
    
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.remove(websocket)

def start_ws_server():
    asyncio.set_event_loop(loop)
    print("Starting WebSocket Server on ws://127.0.0.1:8080")
    
    async def serve():
        async with websockets.serve(ws_handler, "127.0.0.1", 8080):
            await asyncio.Future()  # run forever
            
    loop.run_until_complete(serve())

if __name__ == "__main__":
    ws_thread = threading.Thread(target=start_ws_server, daemon=True)
    ws_thread.start()
    
    try:
        cns_listener_sync()
    except KeyboardInterrupt:
        pass
