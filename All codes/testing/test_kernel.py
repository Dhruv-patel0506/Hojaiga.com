"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: test_kernel.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [test_kernel.py]
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
Dependencies: pytest, aos_kernel.kernel, asyncio, aos_kernel...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_kernel.py]) --> output([Output Node])
```
"""

import asyncio
import pytest  # type: ignore

from core_runtime.kernel import (  # type: ignore
    KernelCore, SystemState, OrganManifest, ResourceQuota,
    InvalidStateTransition, DependencyCycleError, DuplicateRegistrationError,
)


@pytest.fixture
def kernel() -> KernelCore:
    return KernelCore(ResourceQuota(cpu_percent=100, ram_mb=1000, gpu_vram_mb=4000))


def test_initial_state(kernel: KernelCore):
    assert kernel.get_state() == SystemState.INITIALIZING


@pytest.mark.asyncio
async def test_boot_transitions_to_running(kernel: KernelCore):
    await kernel.boot()
    assert kernel.get_state() == SystemState.RUNNING


@pytest.mark.asyncio
async def test_shutdown_transitions_to_shutdown(kernel: KernelCore):
    await kernel.boot()
    await kernel.shutdown("test")
    assert kernel.get_state() == SystemState.SHUTDOWN


def test_invalid_transition_raises(kernel: KernelCore):
    with pytest.raises(InvalidStateTransition):
        kernel.state.transition(SystemState.SHUTDOWN)


def test_register_and_unregister_organ(kernel: KernelCore):
    manifest = OrganManifest(organ_name="brain", version="1.0.0")
    assert kernel.register_organ(manifest) is True
    assert kernel.organs.get("brain") is not None
    assert kernel.security.is_authorized("brain") is True
    kernel.unregister_organ("brain")
    assert kernel.organs.get("brain") is None
    assert kernel.security.is_authorized("brain") is False


def test_duplicate_registration_returns_false(kernel: KernelCore):
    manifest = OrganManifest(organ_name="memory", version="1.0.0")
    kernel.register_organ(manifest)
    assert kernel.register_organ(manifest) is False


def test_dependency_cycle_detected(kernel: KernelCore):
    kernel.dependencies.add("a", ("b",))
    kernel.dependencies.add("b", ("a",))
    with pytest.raises(DependencyCycleError):
        kernel.dependencies.resolve_order()


def test_dependency_order_respected(kernel: KernelCore):
    kernel.dependencies.add("config", ())
    kernel.dependencies.add("registry", ("config",))
    kernel.dependencies.add("scheduler", ("registry",))
    order = kernel.dependencies.resolve_order()
    assert order.index("config") < order.index("registry") < order.index("scheduler")


def test_resource_allocation_within_quota(kernel: KernelCore):
    ok = kernel.resources.allocate("worker1", ResourceQuota(cpu_percent=50, ram_mb=500, gpu_vram_mb=1000))
    assert ok is True
    kernel.resources.release("worker1")
    assert kernel.resources.usage().ram_mb == 0


def test_resource_allocation_denied_when_exceeding_quota(kernel: KernelCore):
    ok = kernel.resources.allocate("worker2", ResourceQuota(cpu_percent=50, ram_mb=5000, gpu_vram_mb=1000))
    assert ok is False


@pytest.mark.asyncio
async def test_heartbeat_marks_organ_failed_and_triggers_recovery(kernel: KernelCore):
    manifest = OrganManifest(organ_name="vision", version="1.0.0")
    kernel.register_organ(manifest)

    async def failing_ping(name: str) -> bool:
        return False

    async def restart_ok(name: str) -> bool:
        return True

    kernel.heartbeat.set_ping_implementation(failing_ping)
    kernel.recovery.set_restart_implementation(restart_ok)

    for _ in range(3):
        await kernel.run_heartbeat_cycle()
    await asyncio.sleep(0)

    record = kernel.organs.get("vision")
    assert record.missed_heartbeats >= 3


@pytest.mark.asyncio
async def test_scheduler_priority_ordering(kernel: KernelCore):
    await kernel.scheduler.submit({"job": "low"}, priority=9)
    await kernel.scheduler.submit({"job": "high"}, priority=1)
    first = await kernel.scheduler.next_task()
    assert first.payload["job"] == "high"


@pytest.mark.asyncio
async def test_socket_bus_publish_subscribe(kernel: KernelCore):
    received = []

    async def handler(message):
        received.append(message.payload)

    kernel.sockets.subscribe("test.socket", handler)
    from core_runtime.kernel import SocketMessage  # type: ignore
    await kernel.sockets.publish("test.socket", SocketMessage(msg_type="PING", payload={"x": 1}, sender="brain"))
    assert received == [{"x": 1}]


def test_event_dispatcher_emit(kernel: KernelCore):
    received = []
    kernel.events.subscribe("Custom", lambda p: received.append(p))
    kernel.events.emit("Custom", {"a": 1})
    assert received == [{"a": 1}]


@pytest.mark.asyncio
async def test_pipeline_bus_runs_stages_in_order(kernel: KernelCore):
    async def stage1(ctx):
        ctx["order"] = ["s1"]
        return ctx

    async def stage2(ctx):
        ctx["order"].append("s2")
        return ctx

    kernel.pipelines.define("custom", [stage1, stage2])
    result = await kernel.pipelines.run("custom", {})
    assert result["order"] == ["s1", "s2"]
