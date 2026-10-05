import asyncio
import json
import logging
import uuid
import time
from typing import Any, Callable, Awaitable, Protocol

try:
    import websockets
    from websockets.asyncio.server import ServerConnection
except ImportError:
    pass

log = logging.getLogger("organ_99_visual_adapter")
HOST = "127.0.0.1"
PORT = 8767

class EventBusWrapper:
    def __init__(self, event_bus) -> None:
        self.event_bus = event_bus

    async def subscribe(self, topic_pattern: str, handler: Callable[[Any], Awaitable[None]]) -> None:
        await self.event_bus.subscribe(topic_pattern, "organ_99", handler)

class VisualAdapterServer:
    def __init__(self, cns_handle: EventBusWrapper) -> None:
        self.cns = cns_handle
        self.clients: set[ServerConnection] = set()

    async def start(self) -> None:
        try:
            import websockets.asyncio.server
            self.server = await websockets.asyncio.server.serve(self._client_handler, HOST, PORT)
            log.info(f"Visual Adapter WebSocket server listening on {HOST}:{PORT}")
        except Exception as e:
            log.error(f"Failed to start WebSocket server: {e}")

    async def stop(self) -> None:
        if hasattr(self, 'server'):
            self.server.close()
            await self.server.wait_closed()

    async def _client_handler(self, websocket: ServerConnection) -> None:
        self.clients.add(websocket)
        try:
            # Send initial snapshot event to tell the UI we are connected
            await websocket.send(json.dumps({"type": "choreoEvent", "event": "CONNECTED"}))
            async for _ in websocket:
                pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.remove(websocket)

    # pyrefly: ignore [bad-function-definition]
    async def broadcast(self, choreo_event: str, data: dict = None) -> None:
        if not self.clients:
            return
        payload = json.dumps({"type": "choreoEvent", "event": choreo_event, "data": data or {}})
        for client in list(self.clients):
            try:
                await client.send(payload)
            except Exception:
                pass

    async def on_cns_event(self, env: Any) -> None:
        payload = getattr(env, "payload", {})
        if not payload:
            return
            
        event_type = payload.get("event_type") or getattr(env, "topic", "UNKNOWN")
        source = getattr(env, "source_organ", "UNKNOWN")

        # Map Hojaiga events to 8-Sequence Choreo events
        if event_type == "SYSTEM_BOOTED":
            await self.broadcast("SystemBoot")
        elif event_type == "ZONE_1_WARP":
            await self.broadcast("Zone1Warp")
        elif event_type == "TASK_RECEIVED" or event_type == "TASK_DISPATCHED":
            await self.broadcast("TaskReceived", {"taskId": payload.get("task_id")})
        elif event_type == "TASK_COMPILED" or event_type == "ROUTE_TO_CNS":
            await self.broadcast("TaskCompiled")
        elif event_type == "SECURITY_CLEARANCE":
            await self.broadcast("SecurityClearance")
        elif event_type == "EXECUTION_STARTED" or event_type == "SUBTASK_ASSIGNED":
            await self.broadcast("ExecutionStarted")
        elif event_type == "TEMP_AGENT_REQUIRED" or event_type == "HEAVY_SKILL_ASSIGNED":
            await self.broadcast("TempAgentRequired")
        elif event_type == "STATE_TRANSITION_FAILED" or event_type == "TASK_FAILED":
            await self.broadcast("TaskError")
        elif event_type == "TASK_COMPLETED":
            await self.broadcast("TaskCompleted")

if __name__ == "__main__":
    pass
