"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 10
Name: Agents

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Agents]
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
Dependencies: pytest, core_organs.organ_10_agents, json, asyncio, struct...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ_10_agents.py]) --> output([Output Node])
```
"""

import asyncio

try:
    import pytest  # type: ignore
    mark_asyncio = pytest.mark.asyncio
except ImportError:  # pragma: no cover - allows standalone execution without pytest installed
    def mark_asyncio(fn):
        return fn

import core_organs.organ_10_agents as m


@mark_asyncio
async def test_spawn_and_complete_default_gateway():
    organ = m.AgentsOrgan(m.OrganConfig(tcp_fallback_port=0))
    handle = await organ.spawn_agent(m.AgentSpawnPayload(
        task_id="t1", role_id="CodeAgent", session_room_id="r1",
        assigned_sub_goal="write hello world", timeout_ms=2000, paradigms=[m.AgentParadigm.RESEARCH_AND_WRITE]))
    await asyncio.sleep(0.2)
    status = organ.get_agent_status(handle)
    assert status.status == m.AgentState.COMPLETED


@mark_asyncio
async def test_unknown_role_rejected():
    organ = m.AgentsOrgan(m.OrganConfig(tcp_fallback_port=0))
    with pytest.raises(ValueError):  # type: ignore
        await organ.spawn_agent(m.AgentSpawnPayload(
            task_id="t1", role_id="NoSuchRole", session_room_id="r1",
            assigned_sub_goal="x", paradigms=[m.AgentParadigm.RESEARCH_AND_WRITE]))


@mark_asyncio
async def test_capability_masking_blocks_unauthorized_tool():
    gateway = m.InMemoryCNSGateway()

    async def reasoning_hook(agent_handle, system_prompt, context):
        return {"action": "CONTINUE", "reasoning": "need forbidden tool",
                "tool_call": {"capability": "system.restart_service"}}

    gateway.set_reasoning_hook(reasoning_hook)
    organ = m.AgentsOrgan(m.OrganConfig(tcp_fallback_port=0), gateway=gateway)
    handle = await organ.spawn_agent(m.AgentSpawnPayload(
        task_id="t1", role_id="DocAgent", session_room_id="r1",
        assigned_sub_goal="x", timeout_ms=1000, paradigms=[m.AgentParadigm.RESEARCH_AND_WRITE]))
    await asyncio.sleep(0.2)
    status = organ.get_agent_status(handle)
    assert status.status == m.AgentState.TERMINATED


@mark_asyncio
async def test_delegation_spawns_child_agent():
    organ = m.AgentsOrgan(m.OrganConfig(tcp_fallback_port=0))
    parent = await organ.spawn_agent(m.AgentSpawnPayload(
        task_id="t1", role_id="BrowserAgent", session_room_id="r1",
        assigned_sub_goal="parent goal", timeout_ms=3000, paradigms=[m.AgentParadigm.PARALLEL_WEB_AUTOMATION]))
    deleg = await organ.delegate_sub_task(m.DelegationPayload(
        parent_handle=parent.agent_handle, child_role="DocAgent",
        sub_goal="child goal", paradigms=[m.AgentParadigm.RESEARCH_AND_WRITE]))
    assert deleg.child_agent_handle
    await asyncio.sleep(0.2)
    status = organ.get_agent_status(m.AgentHandle(deleg.child_agent_handle))
    assert status.role_id == "DocAgent"


@mark_asyncio
async def test_worker_pool_bounded():
    organ = m.AgentsOrgan(m.OrganConfig(max_workers=2, tcp_fallback_port=0))
    assert organ.kernel.pool.max_workers == 2


@mark_asyncio
async def test_role_registry_default_roles():
    registry = m.RoleRegistry()
    assert registry.has_role("BrowserAgent")
    assert registry.has_role("CodeAgent")
    assert not registry.has_role("GhostAgent")


@mark_asyncio
async def test_ipc_server_roundtrip():
    organ = m.AgentsOrgan(m.OrganConfig(tcp_fallback_port=47555))
    await organ.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", 47555)
        import json, struct
        payload = json.dumps({
            "task_id": "t1", "role_id": "DocAgent", "session_room_id": "r1",
            "assigned_sub_goal": "ipc test", "timeout_ms": 2000,
            "paradigms": ["research_and_write"], "is_permanent": True
        }).encode("utf-8")
        writer.write(struct.pack(">IH", len(payload), 1) + payload)
        await writer.drain()
        header = await reader.readexactly(6)
        length, op = struct.unpack(">IH", header)
        body = await reader.readexactly(length)
        response = json.loads(body.decode("utf-8"))
        assert response["ok"] is True
        assert "agent_handle" in response
        writer.close()
    finally:
        await organ.stop()
