import asyncio
import sys
import uuid
import time
import json
from pathlib import Path
sys.path.append(str(Path(__file__).parent / "All codes"))
from test_hojaiga_browser_autonomy import HojaigaRuntimeInstance, start_test_server
from core_organs.organ_02_cns_single_file import EventEnvelope
from core_organs.organ_22_decision_engine import DecisionEngineOrgan

class BranchExecutionTrace:
    def __init__(self, task_name, expected_branch):
        self.task_name = task_name
        self.expected_branch = expected_branch
        self.decision_started = False
        self.selected_branches = set()
        self.branch_states = {
            "KNOWLEDGE": "SKIPPED",
            "MEMORY": "SKIPPED",
            "TOOL": "SKIPPED"
        }
        self.converged = False

async def run_branch_test():
    server = start_test_server(9996)
    
    runtime = HojaigaRuntimeInstance()
    decision_engine = DecisionEngineOrgan()
    
    await runtime.start()
    await decision_engine.start_cns(runtime.cns)
    
    async def mock_branch_handler(env, branch):
        print(f"[{env.payload.get('task_id')}] Executing {branch} branch...")
        await asyncio.sleep(0.1)
        await runtime.cns.publish(EventEnvelope(
            topic=f"{branch}_COMPLETED",
            source_organ=f"mock_{branch.lower()}",
            payload={"task_id": env.payload.get("task_id")}
        ))
        
    await runtime.cns.subscribe("KNOWLEDGE_STARTED", "mock_knw", lambda env: mock_branch_handler(env, "KNOWLEDGE"))
    await runtime.cns.subscribe("MEMORY_STARTED", "mock_mem", lambda env: mock_branch_handler(env, "MEMORY"))
    await runtime.cns.subscribe("TOOL_STARTED", "mock_tool", lambda env: mock_branch_handler(env, "TOOL"))

    tests = [
        ("Test 1: Knowledge branch", "retrieve knowledge about architecture", "KNOWLEDGE"),
        ("Test 2: Memory branch", "recall memory of last session", "MEMORY"),
        ("Test 3: Tool branch", "use tool to calculate", "TOOL"),
        ("Test 4: No Context", "multi-step interact", None)
    ]
    
    traces = {}
    
    async def trace_handler(env):
        task_id = env.payload.get("task_id")
        print(f"DEBUG TRACER RECEIVED: {env.topic} for {task_id}")
        if task_id not in traces:
            return
            
        trace = traces[task_id]
        
        if env.topic == "DECISION_EVALUATION_STARTED":
            trace.decision_started = True
            print(f"[{trace.task_name}] DECISION evaluation started.")
        elif env.topic == "DECISION_EVALUATION_COMPLETED":
            trace.selected_branches = set(env.payload.get("branches_required", []))
            for b in trace.selected_branches:
                trace.branch_states[b] = "SELECTED"
            print(f"[{trace.task_name}] Decision engine selected branches: {list(trace.selected_branches)}")
        elif env.topic.endswith("_STARTED") and env.topic.split("_")[0] in ["KNOWLEDGE", "MEMORY", "TOOL"]:
            branch = env.topic.split("_")[0]
            if trace.branch_states[branch] == "SELECTED":
                trace.branch_states[branch] = "SUCCESS"
            print(f"[{trace.task_name}] Branch {branch} execution SUCCESS.")
        elif env.topic == "COMPILATION_STARTED":
            trace.converged = True
            print(f"[{trace.task_name}] Convergence achieved. Compilation started.")

    await runtime.cns.subscribe("sys.events", "tracer", trace_handler)
    await runtime.cns.subscribe("DECISION_EVALUATION_STARTED", "tracer_sys", trace_handler)
    await runtime.cns.subscribe("DECISION_EVALUATION_COMPLETED", "tracer_sys", trace_handler)
    await runtime.cns.subscribe("KNOWLEDGE_STARTED", "tracer_sys", trace_handler)
    await runtime.cns.subscribe("MEMORY_STARTED", "tracer_sys", trace_handler)
    await runtime.cns.subscribe("TOOL_STARTED", "tracer_sys", trace_handler)
    await runtime.cns.subscribe("COMPILATION_STARTED", "tracer_sys", trace_handler)
    
    for test_name, command, expected_branch in tests:
        print(f"\n{'='*50}\nStarting {test_name}\n{'='*50}")
        request_id = str(uuid.uuid4())
        
        task_id_event = asyncio.Event()
        task_id = None
        
        async def task_created_handler(env):
            nonlocal task_id
            if env.payload.get("request_id") == request_id:
                task_id = env.payload.get("task_id")
                traces[task_id] = BranchExecutionTrace(test_name, expected_branch)
                task_id_event.set()
                
        sub_id = await runtime.cns.subscribe("TASK_CREATED", "task_created_tracer", task_created_handler)
        
        await runtime.cns.publish(EventEnvelope(
            topic="sock.cns.inbound",
            source_organ="test_runner",
            payload={
                "request_id": request_id,
                "payload": {
                    "command": command
                }
            }
        ))
        
        await asyncio.wait_for(task_id_event.wait(), 2.0)
        await runtime.cns.unsubscribe(sub_id)
        
        start_wait = time.time()
        while time.time() - start_wait < 5.0:
            if traces[task_id].converged:
                break
            await asyncio.sleep(0.1)
            
        t = traces[task_id]
        print(f"\n--- {test_name} Trace ---")
        print(f"Decision Engine Active: {t.decision_started}")
        for b in ["KNOWLEDGE", "MEMORY", "TOOL"]:
            print(f"Branch {b}: {t.branch_states[b]}")
        print(f"Convergence: {t.converged}")
        
        if expected_branch:
            assert t.branch_states[expected_branch] == "SUCCESS", f"Expected {expected_branch} to be SUCCESS, got {t.branch_states[expected_branch]}"
        for b in ["KNOWLEDGE", "MEMORY", "TOOL"]:
            if b != expected_branch:
                assert t.branch_states[b] == "SKIPPED", f"Expected {b} to be SKIPPED, got {t.branch_states[b]}"
        
        assert t.converged, "Task did not converge"
        print(f"{test_name} PASSED.")
        
    server.terminate()
    server.join()
    print("\nALL BRANCHING TESTS PASSED.")
    
if __name__ == "__main__":
    asyncio.run(run_branch_test())
