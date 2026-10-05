"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 13
Name: Interface Layer

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Interface Layer]
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
Dependencies: pytest, asyncio, core_organs.organ_13_interface_layer...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ_13_interface_layer.py]) --> output([Output Node])
```
"""

import asyncio
import pytest  # type: ignore

from core_organs.organ_13_interface_layer import (
    InterfaceLayerOrgan, InterfaceLayerError, TransportProtocol, SOCK_OUT_CNS_DISPATCH,
)


@pytest.fixture
def organ():
    o = InterfaceLayerOrgan()
    o.auth.register_user("admin", "pw", roles=["admin"], permissions=["*"])
    o.auth.register_user("viewer1", "pw", roles=["viewer"], permissions=["telemetry.read"])
    return o


def test_login_creates_session(organ):
    session = organ.login("admin", "pw")
    assert session.user_id == "admin"
    assert organ.sessions.validate_session(session.session_id).session_id == session.session_id


def test_login_bad_password_raises(organ):
    with pytest.raises(InterfaceLayerError):
        organ.auth.authenticate("admin", "wrong")


def test_session_revocation(organ):
    session = organ.login("admin", "pw")
    assert organ.logout(session.session_id) is True
    with pytest.raises(InterfaceLayerError):
        organ.sessions.validate_session(session.session_id)


@pytest.mark.asyncio
async def test_cli_dispatch_reaches_cns(organ):
    received = []

    async def handler(frame):
        received.append(frame)

    organ.socket_bus.subscribe(SOCK_OUT_CNS_DISPATCH, handler)
    session = organ.login("admin", "pw")
    result = await organ.cli.handle_line(session.session_id, "task.create", {"x": 1})
    assert result.status_code == 202
    assert len(received) == 1
    assert received[0]["payload"]["command"] == "task.create"


@pytest.mark.asyncio
async def test_unauthenticated_rejected(organ):
    result = await organ.cli.handle_line(None, "task.create", {})
    assert result.status_code == 401


@pytest.mark.asyncio
async def test_unauthorized_permission_rejected(organ):
    session = organ.login("viewer1", "pw")
    result = await organ.gateway.process_inbound(
        TransportProtocol.REST_HTTPS, session.session_id, {"command": "admin.delete"},
        required_permission="admin.delete", client_key="viewer1",
    )
    assert result.status_code == 403


@pytest.mark.asyncio
async def test_rate_limiter_blocks_after_threshold(organ):
    organ.rate_limiter._max_requests = 2  # tighten for test
    session = organ.login("admin", "pw")
    key = "rl-test"
    r1 = await organ.gateway.process_inbound(TransportProtocol.REST_HTTPS, session.session_id, {"command": "a"}, "task.create", key)
    r2 = await organ.gateway.process_inbound(TransportProtocol.REST_HTTPS, session.session_id, {"command": "a"}, "task.create", key)
    r3 = await organ.gateway.process_inbound(TransportProtocol.REST_HTTPS, session.session_id, {"command": "a"}, "task.create", key)
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r3.status_code == 429


def test_validator_rejects_missing_fields(organ):
    with pytest.raises(InterfaceLayerError):
        organ.validator.validate_schema({}, ["command"])


@pytest.mark.asyncio
async def test_session_purge(organ):
    session = organ.login("admin", "pw")
    organ.sessions._sessions[session.session_id].expires_at = 0
    purged = organ.sessions.purge_expired()
    assert purged == 1


@pytest.mark.asyncio
async def test_submit_command_dispatches_to_cns(organ):
    published = []

    class MockCNS:
        async def publish(self, env):
            published.append(env)

    mock_cns = MockCNS()
    await organ.start_cns(mock_cns)

    task_id = await organ.submit_command(raw_command="test task", expected_text="verify ok")
    assert task_id is not None
    assert len(published) == 1
    assert published[0].topic == "sock.cns.inbound"
    assert published[0].payload["payload"]["command"] == "test task"
    assert published[0].payload["payload"]["expected_text"] == "verify ok"
    assert published[0].payload["request_id"] == task_id

