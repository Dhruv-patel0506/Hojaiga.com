import asyncio
import uuid
import sys
import os
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add core path
sys.path.append(str(Path(__file__).parent / "All codes"))

from core_organs.organ_02_cns_single_file import EventBus, EventEnvelope
from core_organs.organ_38_task_orchestrator import TaskOrchestrator
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


class SimpleTestServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        html = """
        <html>
            <head><title>Hojaiga Test Page</title></head>
            <body>
                <h1 id="test-header">Hojaiga Real Chrome Execution Test</h1>
                <p id="test-text">Expected Text: REAL_CDP_SUCCESS</p>
            </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))
        
    def log_message(self, format, *args):
        pass # Suppress logging

def start_test_server(port=9999):
    server = HTTPServer(("127.0.0.1", port), SimpleTestServer)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server

async def run_chrome_test(enable_visualizer: bool, inject_failure: bool = False, expected_text: str = None, url: str = None, test_name: str = "Standard Run"):
    print(f"\n{'='*50}\nStarting Real Chrome CDP Validation: {test_name}\n{'='*50}")
    
    # 1. Start Chrome CDP Runtime (organ 19)
    config = RuntimeConfig(tcp_port=47619)
    config.ensure_dirs()
    cdp_kernel = CDPRuntimeKernel(config)
    await cdp_kernel.start()
    print("CDP Runtime Kernel started.")
    
    cns = EventBus()
    audit = AuditSystem(storage_dir=f"./audit_logs_chrome_{uuid.uuid4().hex[:6]}")
    security = SecurityKernel(Path("."))
    
    orchestrator = TaskOrchestrator(cns, audit, security)
    brain = BrainOrgan()
    compiler = WorkflowCompilerKernel()
    state_catalog = StateCatalogOrgan()
    memory = MemoryCore()
    knowledge = KnowledgeOrgan()
    agents = AgentsOrgan()
    app_scanner = AppScannerOrgan()
    visual_perception = VisualPerceptionOrgan()
    controllers = ControllersCore()
    popup_handler = DesktopInteractionManager()
    
    await orchestrator.start()
    await brain.start(cns)
    await compiler.start(cns)
    memory.start()
    await memory.start_cns(cns)
    await knowledge.start()
    await knowledge.start_cns(cns)
    await agents.start()
    await agents.start_cns(cns)
    await app_scanner.start_cns(cns)
    await visual_perception.start_cns(cns)
    await controllers.start_cns(cns)
    await state_catalog.start_cns(cns)
    await popup_handler.start_cns(cns)
    
    visualizer = None
    if enable_visualizer:
        visualizer = WorkflowVisualizerServer(cns, port=8768)
        await visualizer.start()
        
    trace = []
    
    async def trace_monitor(env: EventEnvelope):
        payload = env.payload
        event_type = payload.get("event_type") or env.topic
        if event_type:
            trace.append(event_type)
            print(f"[TRACE] {event_type} emitted by {env.source_organ}")
            
    await cns.subscribe("sys.events", "trace_monitor", trace_monitor)
    await cns.subscribe("REPLANNING_REQUESTED", "trace_monitor_rep", trace_monitor)
    await cns.subscribe("TASK_FAILED", "trace_monitor_fail", trace_monitor)
    await cns.subscribe("TASK_COMPLETED", "trace_monitor_comp", trace_monitor)
    
    task_id = str(uuid.uuid4())
    command = "Open browser, navigate to local test page, inspect DOM, and verify element."
    
    payload = {
        "payload": {
            "command": command,
            "expected_text": expected_text,
            "url": url, 
            "inject_verification_failure": False
        },
        "request_id": task_id
    }
    
    if inject_failure:
        payload["payload"]["url"] = "http://invalid.local.domain.does.not.exist.internal/"
    
    print(f"Dispatching USER_INPUT to CNS... Task ID: {task_id}")
    await cns.publish(EventEnvelope(
        topic="sock.cns.inbound", 
        source_organ="system_boot", 
        payload=payload
    ))
    
    original_handle = agents._handle_cns_agents_started
    async def patched_handle(env):
        if url:
            for at in env.payload.get("agent_tasks", []):
                at["url"] = payload["payload"]["url"]
        await original_handle(env)
    agents._handle_cns_agents_started = patched_handle
    
    timeout_count = 0
    while timeout_count < 25:
        if "TASK_COMPLETED" in trace or "REPLANNING_REQUESTED" in trace or "TASK_FAILED" in trace:
            break
        await asyncio.sleep(1)
        timeout_count += 1
        
    await cdp_kernel.stop()
    if visualizer:
        await visualizer.stop()
        
    return trace

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", choices=["happy_path", "failure_path", "visualizer"], default="happy_path")
    args = parser.parse_args()
    
    server = start_test_server(port=9999)
    test_url = "http://127.0.0.1:9999/"
    expected_string = "REAL_CDP_SUCCESS"
    
    if args.test == "happy_path":
        print("\n--- TEST 1: Happy Path ---")
        trace1 = await run_chrome_test(enable_visualizer=False, expected_text=expected_string, url=test_url, test_name="Happy Path")
        if "TASK_COMPLETED" not in trace1:
            print("[FAIL] Happy Path did not complete.")
            sys.exit(1)
        else:
            print("[PASS] Happy Path completed.")
            
    elif args.test == "failure_path":
        print("\n--- TEST 2: Failure Path ---")
        trace2 = await run_chrome_test(enable_visualizer=False, expected_text=expected_string, url="http://invalid.local.domain/", inject_failure=True, test_name="Failure Path")
        if "TASK_FAILED" in trace2 or "REPLANNING_REQUESTED" in trace2 or "VERIFICATION_COMPLETED" in trace2:
            print("[PASS] Failure Path correctly detected failure.")
            if "TASK_COMPLETED" in trace2:
                print("[FAIL] Task should not have completed successfully.")
                sys.exit(1)
        else:
            print("[FAIL] Failure Path did not register failure.")
            sys.exit(1)
            
    elif args.test == "visualizer":
        print("\n--- TEST 3: Visualizer ON ---")
        trace3 = await run_chrome_test(enable_visualizer=True, expected_text=expected_string, url=test_url, test_name="Visualizer ON")
        if "TASK_COMPLETED" not in trace3:
            print("[FAIL] Visualizer ON did not complete.")
            sys.exit(1)
        else:
            print("[PASS] Visualizer ON completed.")
            
    server.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
