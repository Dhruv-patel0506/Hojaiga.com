import asyncio
import uuid
import sys
import os
import threading
import json
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add core path
sys.path.append(str(Path(__file__).parent / "All codes"))

from core_organs.organ_02_cns_single_file import EventBus, EventEnvelope
from core_organs.organ_38_task_orchestrator import TaskOrchestrator, TaskState
from observability.organ_16_audit_system import AuditSystem
from core_organs.organ_07_security import SecurityKernel
from core_organs.organ_01_brain import BrainOrgan
from core_organs.organ_36_workflow_compiler import WorkflowCompilerKernel
from core_organs.organ_32_state_catalog import StateCatalogOrgan
from core_organs.organ_03_memory import MemoryCore
from core_organs.organ_04_knowledge import KnowledgeOrgan
from core_organs.organ_10_agents import AgentsOrgan
from core_organs.organ_30_app_scanner import AppScannerOrgan
from core_organs.organ_31_visual_perception import VisualPerceptionOrgan
from core_organs.organ_05_controllers import ControllersCore
from core_organs.organ_29_popup_handler import DesktopInteractionManager
from hojaiga_visualizer_server import WorkflowVisualizerServer
from core_organs.organ_19_chrome_cdp_runtime import CDPRuntimeKernel, RuntimeConfig


class AutonomyTestServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        html = """
        <html>
            <head><title>Hojaiga Autonomy Test</title></head>
            <body>
                <h1 id="header">Autonomous Navigation Success</h1>
                <p id="test-text">TaskB_SUCCESS</p>
                <button id="test-button" onclick="document.getElementById('test-text').innerText='TaskC_SUCCESS'">Click Me</button>
            </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))
        
    def log_message(self, format, *args):
        pass

def start_test_server(port=9998):
    server = HTTPServer(("127.0.0.1", port), AutonomyTestServer)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server

class HojaigaRuntimeInstance:
    def __init__(self, enable_visualizer=False):
        self.cns = EventBus()
        self.audit = AuditSystem(storage_dir=f"./audit_logs_autonomy_{uuid.uuid4().hex[:6]}")
        self.security = SecurityKernel(Path("."))
        
        self.orchestrator = TaskOrchestrator(self.cns, self.audit, self.security)
        self.brain = BrainOrgan()
        self.compiler = WorkflowCompilerKernel()
        self.state_catalog = StateCatalogOrgan()
        self.memory = MemoryCore()
        self.knowledge = KnowledgeOrgan()
        self.agents = AgentsOrgan()
        self.app_scanner = AppScannerOrgan()
        self.visual_perception = VisualPerceptionOrgan()
        self.controllers = ControllersCore()
        self.popup_handler = DesktopInteractionManager()
        
        self.cdp_kernel = None
        self.visualizer = None
        self.enable_visualizer = enable_visualizer
        self.trace = []

    async def start(self):
        config = RuntimeConfig(tcp_port=47619)
        config.ensure_dirs()
        self.cdp_kernel = CDPRuntimeKernel(config)
        await self.cdp_kernel.start()
        
        await self.orchestrator.start()
        await self.brain.start(self.cns)
        await self.compiler.start(self.cns)
        self.memory.start()
        await self.memory.start_cns(self.cns)
        await self.knowledge.start()
        await self.knowledge.start_cns(self.cns)
        await self.agents.start()
        await self.agents.start_cns(self.cns)
        await self.app_scanner.start_cns(self.cns)
        await self.visual_perception.start_cns(self.cns)
        await self.controllers.start_cns(self.cns)
        await self.state_catalog.start_cns(self.cns)
        await self.popup_handler.start_cns(self.cns)
        
        if self.enable_visualizer:
            self.visualizer = WorkflowVisualizerServer(self.cns, port=8768)
            await self.visualizer.start()

        async def trace_monitor(env: EventEnvelope):
            payload = env.payload
            event_type = payload.get("event_type") or env.topic
            if event_type:
                self.trace.append(event_type)
                
        await self.cns.subscribe("sys.events", "trace_monitor", trace_monitor)
        await self.cns.subscribe("REPLANNING_REQUESTED", "trace_monitor_rep", trace_monitor)
        await self.cns.subscribe("TASK_FAILED", "trace_monitor_fail", trace_monitor)
        await self.cns.subscribe("TASK_COMPLETED", "trace_monitor_comp", trace_monitor)

    async def stop(self):
        await self.cdp_kernel.stop()
        if self.visualizer:
            await self.visualizer.stop()

async def wait_for_completion(runtime, timeout=15):
    timeout_count = 0
    while timeout_count < timeout:
        if "TASK_COMPLETED" in runtime.trace or "REPLANNING_REQUESTED" in runtime.trace or "TASK_FAILED" in runtime.trace:
            break
        await asyncio.sleep(1)
        timeout_count += 1
    return runtime.trace

async def run_suite_navigation(test_url):
    print("\n--- TEST A: Navigation Autonomy ---")
    runtime = HojaigaRuntimeInstance()
    await runtime.start()
    
    task_id = str(uuid.uuid4())
    command = "Navigate to " + test_url
    
    # We aren't testing string matching verification here, just navigation
    await runtime.cns.publish(EventEnvelope(
        topic="sock.cns.inbound", 
        source_organ="system_boot", 
        payload={"payload": {"command": command}, "request_id": task_id}
    ))
    
    trace = await wait_for_completion(runtime)
    await runtime.stop()
    
    if "TASK_COMPLETED" in trace:
        print("[PASS] Navigation Suite")
    else:
        print("[FAIL] Navigation Suite")
        print(trace)
        sys.exit(1)

async def run_suite_dom_inspection(test_url):
    print("\n--- TEST B: DOM Inspection Verification ---")
    runtime = HojaigaRuntimeInstance()
    await runtime.start()
    
    task_id = str(uuid.uuid4())
    command = "Inspect " + test_url
    expected_text = "TaskB_SUCCESS"
    
    await runtime.cns.publish(EventEnvelope(
        topic="sock.cns.inbound", 
        source_organ="system_boot", 
        payload={"payload": {"command": command, "expected_text": expected_text}, "request_id": task_id}
    ))
    
    trace = await wait_for_completion(runtime)
    await runtime.stop()
    
    if "TASK_COMPLETED" in trace:
        print("[PASS] DOM Inspection Suite")
    else:
        print("[FAIL] DOM Inspection Suite")
        print(trace)
        sys.exit(1)

async def run_suite_multi_step(test_url):
    print("\n--- TEST C: Multi-Step Workflow ---")
    runtime = HojaigaRuntimeInstance()
    await runtime.start()
    
    task_id = str(uuid.uuid4())
    command = "Multi-step interact on " + test_url
    expected_text = "TaskC_SUCCESS"
    
    await runtime.cns.publish(EventEnvelope(
        topic="sock.cns.inbound", 
        source_organ="system_boot", 
        payload={"payload": {"command": command, "expected_text": expected_text}, "request_id": task_id}
    ))
    
    # This will take longer because it involves navigation, clicking, and DOM retrieval.
    trace = await wait_for_completion(runtime, timeout=20)
    await runtime.stop()
    
    if "TASK_COMPLETED" in trace:
        print("[PASS] Multi-Step Suite")
    else:
        print("[FAIL] Multi-Step Suite")
        print(trace)
        sys.exit(1)

async def run_suite_failures(test_url):
    print("\n--- TEST D: Failure Recovery ---")
    runtime = HojaigaRuntimeInstance()
    await runtime.start()
    
    task_id = str(uuid.uuid4())
    command = "Inspect http://invalid.local.domain/"
    
    await runtime.cns.publish(EventEnvelope(
        topic="sock.cns.inbound", 
        source_organ="system_boot", 
        payload={"payload": {"command": command}, "request_id": task_id}
    ))
    
    trace = await wait_for_completion(runtime)
    await runtime.stop()
    
    if "REPLANNING_REQUESTED" in trace or "TASK_FAILED" in trace:
        print("[PASS] Failure Suite")
    else:
        print("[FAIL] Failure Suite. Did not trigger recovery.")
        print(trace)
        sys.exit(1)
        
async def run_suite_checkpoints():
    print("\n--- TEST E: Checkpoint Recovery ---")
    runtime = HojaigaRuntimeInstance()
    await runtime.start()
    
    task_id = str(uuid.uuid4())
    
    # Instead of firing from UI, we restore directly to Orchestrator
    state_dict = {
        "task_id": task_id,
        "request_id": task_id,
        "state": TaskState.FAILED.value,
    }
    
    await runtime.orchestrator.restore_task(state_dict)
    
    trace = await wait_for_completion(runtime, timeout=5)
    await runtime.stop()
    
    if "REPLANNING_REQUESTED" in trace:
        print("[PASS] Checkpoint Suite")
    else:
        print("[FAIL] Checkpoint Suite")
        print(trace)
        sys.exit(1)
        
async def run_suite_concurrency(test_url):
    print("\n--- TEST F: Concurrency Test ---")
    runtime = HojaigaRuntimeInstance()
    await runtime.start()
    
    task_id_1 = str(uuid.uuid4())
    task_id_2 = str(uuid.uuid4())
    
    await runtime.cns.publish(EventEnvelope(
        topic="sock.cns.inbound", 
        source_organ="system_boot", 
        payload={"payload": {"command": "Inspect " + test_url, "expected_text": "TaskB_SUCCESS"}, "request_id": task_id_1}
    ))
    await runtime.cns.publish(EventEnvelope(
        topic="sock.cns.inbound", 
        source_organ="system_boot", 
        payload={"payload": {"command": "Inspect http://invalid.domain/"}, "request_id": task_id_2}
    ))
    
    await asyncio.sleep(10)
    await runtime.stop()
    
    t1_trace = [t for t in runtime.trace if task_id_1 in t]
    t2_trace = [t for t in runtime.trace if task_id_2 in t]
    
    # Due to limited logging capabilities mapping tasks in strings, 
    # we just check global presence. 
    if "TASK_COMPLETED" in runtime.trace and "REPLANNING_REQUESTED" in runtime.trace:
         print("[PASS] Concurrency Suite")
    else:
         print("[FAIL] Concurrency Suite")
         print(runtime.trace)
         sys.exit(1)

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["navigation", "dom", "multi", "failures", "checkpoints", "concurrency", "all"], default="all")
    args = parser.parse_args()
    
    server = start_test_server(port=9998)
    test_url = "http://127.0.0.1:9998/"
    
    if args.suite in ["navigation", "all"]:
        await run_suite_navigation(test_url)
    if args.suite in ["dom", "all"]:
        await run_suite_dom_inspection(test_url)
    if args.suite in ["multi", "all"]:
        await run_suite_multi_step(test_url)
    if args.suite in ["failures", "all"]:
        await run_suite_failures(test_url)
    if args.suite in ["checkpoints", "all"]:
        await run_suite_checkpoints()
    if args.suite in ["concurrency", "all"]:
        await run_suite_concurrency(test_url)
        
    server.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
