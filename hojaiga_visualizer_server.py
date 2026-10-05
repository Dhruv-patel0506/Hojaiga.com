import asyncio
import json
import logging
from typing import Set

import websockets
from websockets import ServerConnection

from core_organs.organ_02_cns_single_file import EventBus, EventEnvelope

logger = logging.getLogger("hojaiga_visualizer")

class WorkflowVisualizerServer:
    """
    READ-ONLY observability layer.
    Connects to the CNS EventBus, subscribes to sys.events and state transitions,
    and broadcasts them to connected WebSocket clients (the UI).
    """
    def __init__(self, cns: EventBus, host: str = "127.0.0.1", port: int = 8765):
        self.cns = cns
        self.host = host
        self.port = port
        self.clients: Set[ServerConnection] = set()
        self.server_task = None
        
    async def start(self):
        # Start WebSocket server
        self.server_task = await websockets.serve(self._handler, self.host, self.port)
        logger.info(f"Visualizer Server running on ws://{self.host}:{self.port}")
        
        # Subscribe to CNS as a read-only observer
        # We listen to everything to build the timeline
        await self.cns.subscribe("sys.events", "visualizer", self._on_event)
        await self.cns.subscribe("TASK_CREATED", "visualizer", self._on_event)
        await self.cns.subscribe("INTENT_NORMALIZATION_STARTED", "visualizer", self._on_event)
        await self.cns.subscribe("INTENT_NORMALIZATION_COMPLETED", "visualizer", self._on_event)
        await self.cns.subscribe("COMPILATION_STARTED", "visualizer", self._on_event)
        await self.cns.subscribe("COMPILATION_COMPLETED", "visualizer", self._on_event)
        await self.cns.subscribe("AGENTS_STARTED", "visualizer", self._on_event)
        await self.cns.subscribe("AGENT_ASSIGNED", "visualizer", self._on_event)
        await self.cns.subscribe("SCAN_STARTED", "visualizer", self._on_event)
        await self.cns.subscribe("SCAN_COMPLETED", "visualizer", self._on_event)
        await self.cns.subscribe("POPUP_RESOLVED", "visualizer", self._on_event)
        await self.cns.subscribe("CONTROLLER_EXECUTING", "visualizer", self._on_event)
        await self.cns.subscribe("AGENTS_COMPLETED", "visualizer", self._on_event)
        await self.cns.subscribe("VERIFICATION_STARTED", "visualizer", self._on_event)
        await self.cns.subscribe("VERIFICATION_COMPLETED", "visualizer", self._on_event)
        await self.cns.subscribe("REPLANNING_REQUESTED", "visualizer", self._on_event)
        await self.cns.subscribe("TASK_FAILED", "visualizer", self._on_event)
        await self.cns.subscribe("TASK_COMPLETED", "visualizer", self._on_event)
        await self.cns.subscribe("STATE_TRANSITION_FAILED", "visualizer", self._on_event)
        await self.cns.subscribe("STATE_TRANSITION_REQUEST", "visualizer", self._on_event)

    async def stop(self):
        if self.server_task:
            self.server_task.close()
            await self.server_task.wait_closed()
            
    async def _handler(self, websocket: ServerConnection):
        self.clients.add(websocket)
        try:
            # Just keep the connection open, we only push data to clients.
            async for message in websocket:
                # The visualizer is read-only. We ignore incoming messages to prevent control-path injection.
                pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.remove(websocket)

    async def _on_event(self, env: EventEnvelope):
        if not self.clients:
            return
            
        # Serialize event for the UI
        try:
            payload = {
                "topic": env.topic,
                "source": env.source_organ,
                "timestamp": env.timestamp_ms,
                "priority": env.priority,
                "data": env.payload
            }
            msg = json.dumps(payload)
            
            # Fire-and-forget broadcast to avoid blocking the CNS
            for client in list(self.clients):
                asyncio.create_task(self._safe_send(client, msg))
        except Exception as e:
            logger.error(f"Visualizer serialization error: {e}")
            
    async def _safe_send(self, client: ServerConnection, msg: str):
        try:
            await client.send(msg)
        except websockets.exceptions.ConnectionClosed:
            self.clients.discard(client)
