"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: system_boot.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [system_boot.py]
        direction TB
        IN[Inputs] --> PROC[Processing]
        PROC --> OUT[Outputs]
    end
    
    COMPONENT -- event/socket --> DOWNSTREAM_A[CONSUMER A]
    COMPONENT -- event/socket --> DOWNSTREAM_B[CONSUMER B]
    
    class COMPONENT component;
```

Inputs: Discovered from runtime
Outputs: Discovered from runtime
Dependencies: core_organs.organ_13_interface_layer, socket, json, core_organs.organ_07_security, asyncio...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: system_boot.py]) --> output([Output Node])
```
"""

import asyncio
import threading
import logging
import json
import uuid

from core_organs.organ_02_cns_single_file import EventBus, EventEnvelope
from observability.organ_16_audit_system import AuditSystem
from core_organs.organ_07_security import SecurityKernel
from core_organs.organ_38_task_orchestrator import TaskOrchestrator
from core_organs.organ_01_brain import BrainOrgan
from core_organs.organ_22_decision_engine import DecisionEngineOrgan
from core_organs.organ_36_workflow_compiler import WorkflowCompilerKernel
from core_organs.organ_03_memory import MemoryCore
from core_organs.organ_04_knowledge import KnowledgeOrgan

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("system_boot")

class ArchitecturalError(Exception):
    """Exception raised when an architectural rule is violated."""
    pass

def start_system():
    logger.info("Initializing CNS EventBus...")
    cns = EventBus()
    
    logger.info("Initializing Audit System...")
    audit = AuditSystem(storage_dir="./audit_logs")
    
    from pathlib import Path
    logger.info("Initializing Security Kernel...")
    security = SecurityKernel(Path("."))
    
    logger.info("Initializing Task Orchestrator (organ_38)...")
    orchestrator = TaskOrchestrator(cns, audit, security)
    
    logger.info("Initializing Brain Organ (organ_01)...")
    brain = BrainOrgan()

    logger.info("Initializing Decision Engine (organ_22)...")
    decision_engine = DecisionEngineOrgan()
    
    logger.info("Initializing Workflow Compiler (organ_36)...")
    compiler = WorkflowCompilerKernel()
    
    logger.info("Initializing Memory Organ (organ_03)...")
    memory = MemoryCore()
    
    logger.info("Initializing Knowledge Organ (organ_04)...")
    knowledge = KnowledgeOrgan()
    
    
    # Terminal Logger Observer
    async def terminal_logger(env: EventEnvelope) -> None:
        payload = env.payload
        event_type = payload.get("event_type", "UNKNOWN_EVENT")
        task_id = payload.get("task_id", "none")
        print(f"\n[EXECUTION EVENT: {event_type}]")
        print(f"  task_id: {task_id}")
        for k, v in payload.items():
            if k not in ("event_type", "task_id"):
                print(f"  {k}: {v}")
        print("-" * 40)
    
    import socket
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # We still need the UDP UI visualizer updates based on CNS events
    async def vis_updater(env: EventEnvelope) -> None:
        payload = env.payload
        event_type = payload.get("event_type", "")
        # Updated translation mapping to match Target Architecture
        mapping = {
            "TASK_CREATED": ("USER_INPUT", "CNS"),
            "INTENT_NORMALIZATION_STARTED": ("CNS", "BRAIN"),
            "INTENT_NORMALIZATION_COMPLETED": ("BRAIN", "CNS"),
            "COMPILATION_STARTED": ("CNS", "COMPILER"),
            "COMPILATION_COMPLETED": ("COMPILER", "CNS"),
            "RESOURCE_RESOLUTION_STARTED": ("CNS", "REGISTRY"),
            "RESOURCE_RESOLUTION_COMPLETED": ("REGISTRY", "CNS"),
            "AGENTS_STARTED": ("CNS", "AUTOMATION"),
            "SCAN_STARTED": ("AUTOMATION", "PERCEPTION"),
            "SCAN_COMPLETED": ("PERCEPTION", "AUTOMATION"),
            "CONTROLLER_EXECUTING": ("AUTOMATION", "CONTROLLERS"),
            "AGENTS_COMPLETED": ("CONTROLLERS", "CNS"),
            "VERIFICATION_STARTED": ("CNS", "CHECKPOINTS"),
            "VERIFICATION_COMPLETED": ("CHECKPOINTS", "CNS"),
            "TASK_FAILED": ("CNS", "ERROR_CATALOG"),
            "REPLANNING_REQUESTED": ("ERROR_CATALOG", "CNS"),
            "REQUEST_CONFIG": None
        }
        if event_type in mapping:
            val = mapping[event_type]
            if val is not None:
                try:
                    udp_sock.sendto(json.dumps({"start": val[0], "end": val[1]}).encode(), ("127.0.0.1", 9999))
                except: pass
            elif event_type == "REQUEST_CONFIG":
                try:
                    udp_sock.sendto(json.dumps({"type": "REQUEST_CONFIG"}).encode(), ("127.0.0.1", 9999))
                except: pass

    # Cross-thread bridge context (filled by the CNS loop; read by interface handlers)
    _bridge_ctx: dict = {"cns": None, "loop": None}

    async def _run_cns():
        await orchestrator.start()
        await brain.start(cns)
        await decision_engine.start_cns(cns)
        await compiler.start(cns)

        # Controllers (organ_05): execute INVOKE_CONTROLLER actions (chrome/app/...)
        logger.info("Initializing Controllers (organ_05)...")
        from core_organs.organ_05_controllers import ControllersCore
        controllers = ControllersCore()
        await controllers.start_cns(cns)

        # Agents Organ (organ_10): consume AGENTS_STARTED and drive controllers
        logger.info("Initializing Agents Organ (organ_10)...")
        from core_organs.organ_10_agents import AgentsOrgan
        agents = AgentsOrgan()
        await agents.start()
        await agents.start_cns(cns)

        # Expose the CNS loop for cross-thread bridging (interface layer -> CNS)
        _bridge_ctx["cns"] = cns
        _bridge_ctx["loop"] = asyncio.get_running_loop()
        
        # Start and connect Memory and Knowledge
        memory.start()
        await memory.start_cns(cns)
        
        await knowledge.start()
        await knowledge.start_cns(cns)
        
        logger.info("CNS is now running and routing events.")
        await cns.subscribe("sys.events", "terminal_logger", terminal_logger)
        await cns.subscribe("sys.events", "vis_updater", vis_updater)
        
        # Start UDP listener for UI events
        class UIUDPProtocol(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                try:
                    msg = json.loads(data.decode('utf-8'))
                    msg_type = msg.get("type")
                    if msg_type == "TASK_INPUT":
                        # Convert to standard format and publish to inbound
                        task_id = str(uuid.uuid4())
                        payload = {
                            "payload": {"command": msg.get("text"), "args": {}},
                            "request_id": task_id
                        }
                        asyncio.create_task(cns.publish(EventEnvelope(topic="sock.cns.inbound", source_organ="system_boot", payload=payload)))
                    elif msg_type == "CONFIG_RESPONSE":
                        msg["task_id"] = "TBD" 
                        asyncio.create_task(cns.publish(EventEnvelope(topic="sys.events.ui_response", source_organ="system_boot", payload=msg)))
                except Exception as e:
                    logger.error(f"Error handling UI UDP message: {e}")

        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(
            lambda: UIUDPProtocol(),
            local_addr=('127.0.0.1', 9995)
        )
        logger.info("Listening for UI input on UDP 9995...")

        # Keep loop alive
        while True:
            await asyncio.sleep(1)

    threading.Thread(target=lambda: asyncio.run(_run_cns()), daemon=True).start()
    
    # Start UI
    logger.info("Starting Interface Layer...")
    import core_organs.organ_13_interface_layer as organ_13_interface_layer
    from core_organs.organ_13_interface_layer import SOCK_OUT_CNS_DISPATCH

    async def _interface_dispatch_to_cns(frame: dict) -> None:
        """Forward Organ 13 SOCK_OUT_CNS_DISPATCH frames onto the real CNS bus."""
        cns_bus = _bridge_ctx.get("cns")
        cns_loop = _bridge_ctx.get("loop")
        if cns_bus is None or cns_loop is None:
            logger.error("Interface bridge: CNS not ready; interface command dropped")
            return
        envelope = EventEnvelope(
            topic="sock.cns.inbound",
            source_organ="organ_13_bridge",
            payload={"payload": frame.get("payload", {}), "request_id": frame.get("request_id")},
        )
        future = asyncio.run_coroutine_threadsafe(cns_bus.publish(envelope), cns_loop)
        await asyncio.wrap_future(future)

    interface_organ = organ_13_interface_layer.InterfaceLayerOrgan()
    interface_organ.socket_bus.subscribe(SOCK_OUT_CNS_DISPATCH, _interface_dispatch_to_cns)

    organ_13_interface_layer.run_manual_interface(interface_organ)

if __name__ == "__main__":
    start_system()
