import asyncio
import sys
import uuid
import time
from pathlib import Path
sys.path.append(str(Path(__file__).parent / "All codes"))
from test_hojaiga_browser_autonomy import HojaigaRuntimeInstance, start_test_server
from core_organs.organ_02_cns_single_file import EventEnvelope
from core_organs.organ_22_decision_engine import DecisionEngineOrgan

class RecoveryExecutionTrace:
    def __init__(self, task_name):
        self.task_name = task_name
        self.state_history = []
        self.converged = False

async def run_recovery_test():
    server = start_test_server(9995)
    
    runtime = HojaigaRuntimeInstance()
    decision_engine = DecisionEngineOrgan()
    
    await runtime.start()
    await decision_engine.start_cns(runtime.cns)
    
    # Mock branches to prevent hanging if selected
    async def mock_branch_handler(env, branch):
        await runtime.cns.publish(EventEnvelope(
            topic=f"{branch}_COMPLETED",
            source_organ=f"mock_{branch.lower()}",
            payload={"task_id": env.payload.get("task_id")}
        ))
    await runtime.cns.subscribe("KNOWLEDGE_STARTED", "mock_knw", lambda env: mock_branch_handler(env, "KNOWLEDGE"))
    await runtime.cns.subscribe("MEMORY_STARTED", "mock_mem", lambda env: mock_branch_handler(env, "MEMORY"))
    await runtime.cns.subscribe("TOOL_STARTED", "mock_tool", lambda env: mock_branch_handler(env, "TOOL"))

    # Mock compilation to advance to Resource Resolution
    async def mock_compilation(env):
        await runtime.cns.publish(EventEnvelope(
            topic="COMPILATION_COMPLETED",
            source_organ="mock_compiler",
            payload={"task_id": env.payload.get("task_id"), "compiled_workflow": {}, "agent_tasks": [{"id": 1}]}
        ))
    await runtime.cns.subscribe("COMPILATION_STARTED", "mock_comp", mock_compilation)

    # Mock resource resolution to advance to Agents
    async def mock_resource(env):
        # We need to answer the config request
        await runtime.cns.publish(EventEnvelope(
            topic="sys.events.ui_response",
            source_organ="mock_ui",
            payload={"type": "CONFIG_RESPONSE", "task_id": env.payload.get("task_id"), "config": {}}
        ))
    await runtime.cns.subscribe("REQUEST_CONFIG", "mock_ui_req", mock_resource)

    # We will simulate the Controller by intercepting AGENTS_STARTED
    # and emitting TASK_FAILED the first time, and SUCCESS the second time.
    controller_attempts = {}
    
    async def mock_controller_handler(env):
        task_id = env.payload.get("task_id")
        if task_id not in controller_attempts:
            controller_attempts[task_id] = 1
        else:
            controller_attempts[task_id] += 1
            
        print(f"[{task_id}] Mock Controller executing attempt {controller_attempts[task_id]}...")
        await asyncio.sleep(0.5)
        
        if controller_attempts[task_id] == 1:
            print(f"[{task_id}] Mock Controller emitting TASK_FAILED")
            await runtime.cns.publish(EventEnvelope(
                topic="TASK_FAILED",
                source_organ="mock_controller",
                payload={"task_id": task_id, "error": "Simulated transient network failure"}
            ))
        else:
            print(f"[{task_id}] Mock Controller emitting SUCCESS via VERIFICATION_STARTED mock path")
            # In V2, Agents completed means Verification starts.
            await runtime.cns.publish(EventEnvelope(
                topic="AGENTS_COMPLETED",
                source_organ="mock_controller",
                payload={"task_id": task_id, "result_data": {"nodes": ["success_mock"]}}
            ))
            
    # Hijack AGENTS_STARTED to route to our mock controller
    # We use high priority so we handle it before the real agent
    await runtime.cns.subscribe("AGENTS_STARTED", "mock_ctrl", mock_controller_handler, min_priority=1)

    # Hijack VERIFICATION_STARTED to just emit VERIFICATION_COMPLETED success
    async def mock_verification(env):
        task_id = env.payload.get("task_id")
        await runtime.cns.publish(EventEnvelope(
            topic="VERIFICATION_COMPLETED",
            source_organ="mock_verifier",
            payload={"task_id": task_id, "success": True}
        ))
    await runtime.cns.subscribe("VERIFICATION_STARTED", "mock_verifier_sub", mock_verification, min_priority=1)


    traces = {}
    
    async def trace_handler(env):
        task_id = env.payload.get("task_id")
        if not task_id or task_id not in traces:
            return
            
        trace = traces[task_id]
        
        # Track important lifecycle events
        if env.topic == "TASK_FAILED":
            trace.state_history.append("FAILED")
            print(f"[{trace.task_name}] Step failed. Node marked FAILED.")
        elif env.topic == "TASK_BLOCKED":
            trace.state_history.append("BLOCKED")
            print(f"[{trace.task_name}] Downstream nodes marked BLOCKED.")
        elif env.topic == "RECOVERY_STARTED":
            trace.state_history.append("RECOVERING")
            print(f"[{trace.task_name}] Recovery handler activated: RECOVERING.")
        elif env.topic == "AGENTS_STARTED":
            if "RECOVERING" in trace.state_history:
                trace.state_history.append("RETRIED")
                print(f"[{trace.task_name}] Step re-run: RETRIED.")
        elif env.topic == "VERIFICATION_COMPLETED" and env.payload.get("success"):
            trace.state_history.append("SUCCESS")
            print(f"[{trace.task_name}] Execution SUCCESS.")
        elif env.topic == "TASK_COMPLETED":
            trace.converged = True
            print(f"[{trace.task_name}] Task fully completed.")

    # Subscribe trace handler to monitor states
    for topic in ["TASK_FAILED", "TASK_BLOCKED", "RECOVERY_STARTED", "AGENTS_STARTED", "VERIFICATION_COMPLETED", "TASK_COMPLETED"]:
        await runtime.cns.subscribe(topic, f"tracer_{topic}", trace_handler)

    test_name = "V2 Recovery Sequence"
    command = "multi-step interacting scenario"
    
    print(f"\n{'='*50}\nStarting {test_name}\n{'='*50}")
    request_id = str(uuid.uuid4())
    
    task_id_event = asyncio.Event()
    task_id = None
    
    async def task_created_handler(env):
        nonlocal task_id
        if env.payload.get("request_id") == request_id:
            task_id = env.payload.get("task_id")
            traces[task_id] = RecoveryExecutionTrace(test_name)
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
    while time.time() - start_wait < 15.0:
        if traces[task_id].converged:
            break
        await asyncio.sleep(0.1)
        
    t = traces[task_id]
    print(f"\n--- {test_name} Trace ---")
    print(f"State History: {t.state_history}")
    print(f"Convergence: {t.converged}")
    
    required_states = ["FAILED", "BLOCKED", "RECOVERING", "RETRIED", "SUCCESS"]
    for s in required_states:
        assert s in t.state_history, f"Expected state {s} missing from history!"
        
    # Check ordering loosely
    failed_idx = t.state_history.index("FAILED")
    blocked_idx = t.state_history.index("BLOCKED")
    rec_idx = t.state_history.index("RECOVERING")
    retry_idx = t.state_history.index("RETRIED")
    succ_idx = t.state_history.index("SUCCESS")
    
    assert failed_idx < rec_idx, "FAILED must occur before RECOVERING"
    assert rec_idx < retry_idx, "RECOVERING must occur before RETRIED"
    assert retry_idx < succ_idx, "RETRIED must occur before SUCCESS"
    
    print(f"{test_name} PASSED.")
    
    server.shutdown()
    server.server_close()
    print("\nALL RECOVERY TESTS PASSED.")

if __name__ == "__main__":
    asyncio.run(run_recovery_test())
