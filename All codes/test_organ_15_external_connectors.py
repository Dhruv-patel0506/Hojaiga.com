"""
Tests for Organ 15: External Connectors.
Run with: pytest -q tests/test_external_connectors.py
"""

import asyncio
import os
import tempfile

import pytest  # type: ignore

from organ_15_external_connectors import (
    ConnectorGateway,
    ConnectorCommandRequest,
    ConnectorType,
    ResponseStatus,
    FileSystemConnector,
    ConnectorValidator,
    ValidationError,
    SecurityGate,
    PermissionDeniedError,
    RecoveryEngine,
)


@pytest.mark.asyncio
async def test_filesystem_write_and_read():
    with tempfile.TemporaryDirectory() as tmp:
        gateway = ConnectorGateway()
        gateway.register(FileSystemConnector(allowed_roots=[tmp]))

        write_req = ConnectorCommandRequest(
            connector_type=ConnectorType.FILESYSTEM,
            action_name="write",
            payload={"path": os.path.join(tmp, "file.txt"), "content": "hello"},
        )
        write_resp = await gateway.route(write_req)
        assert write_resp.status == ResponseStatus.OK

        read_req = ConnectorCommandRequest(
            connector_type=ConnectorType.FILESYSTEM,
            action_name="read",
            payload={"path": os.path.join(tmp, "file.txt")},
        )
        read_resp = await gateway.route(read_req)
        assert read_resp.status == ResponseStatus.OK
        # pyrefly: ignore [unsupported-operation]
        assert read_resp.result_payload["content"] == "hello"

        await gateway.shutdown()


@pytest.mark.asyncio
async def test_filesystem_path_traversal_denied():
    with tempfile.TemporaryDirectory() as tmp:
        gateway = ConnectorGateway()
        gateway.register(FileSystemConnector(allowed_roots=[tmp]))

        req = ConnectorCommandRequest(
            connector_type=ConnectorType.FILESYSTEM,
            action_name="read",
            payload={"path": "/etc/passwd"},
        )
        resp = await gateway.route(req)
        assert resp.status == ResponseStatus.DENIED
        await gateway.shutdown()


def test_validator_rejects_missing_action_name():
    validator = ConnectorValidator()
    req = ConnectorCommandRequest(connector_type=ConnectorType.FILESYSTEM, action_name="")
    with pytest.raises(ValidationError):
        validator.validate(req)


def test_security_gate_denies_unauthorized_capability():
    gate = SecurityGate(allowed_capabilities={"REST"})
    req = ConnectorCommandRequest(connector_type=ConnectorType.BROWSER, action_name="goto")
    with pytest.raises(PermissionDeniedError):
        gate.authorize(req)


def test_security_gate_strips_secrets():
    redacted = SecurityGate.strip_secrets({"token": "abc123", "user": "bob"})
    assert redacted["token"] == "***REDACTED***"
    assert redacted["user"] == "bob"


@pytest.mark.asyncio
async def test_recovery_engine_retries_then_succeeds():
    engine = RecoveryEngine()
    attempts = {"count": 0}

    async def flaky():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("transient failure")
        return "ok"

    result = await engine.execute_with_recovery(ConnectorType.REST, flaky)
    assert result == "ok"
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_gateway_returns_error_for_unregistered_connector():
    gateway = ConnectorGateway()
    req = ConnectorCommandRequest(connector_type=ConnectorType.WEBSOCKET, action_name="connect")
    resp = await gateway.route(req)
    assert resp.status == ResponseStatus.ERROR
    await gateway.shutdown()
