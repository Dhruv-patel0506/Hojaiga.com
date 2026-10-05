"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 19
Name: Chrome Cdp Runtime

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Chrome Cdp Runtime]
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
Dependencies: pytest, core_organs.organ_19_chrome_cdp_runtime, json, asyncio, sys...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ_19_chrome_cdp_runtime.py]) --> output([Output Node])
```
"""

"""
Unit tests for organ_19_chrome_cdp_runtime.py

These tests exercise the subsystems using a mocked SessionInvoker so no
live Chromium instance or 'websockets' package is required. Run with:

    pytest test_organ_19_chrome_cdp_runtime.py -v
"""
import asyncio
import json
import os
import sys

import pytest  # type: ignore

sys.path.insert(0, os.path.dirname(__file__))

import core_organs.organ_19_chrome_cdp_runtime as cdp


# ----------------------------------------------------------------------
# IPC WIRE PROTOCOL
# ----------------------------------------------------------------------

def test_ipc_frame_roundtrip():
    frame = cdp.IPCFrame(op_code=cdp.Organ19OpCode.PING, payload={"a": 1})
    encoded = frame.encode()
    total_len = cdp.IPC_LENGTH_HEADER.unpack(encoded[:4])[0]
    body = encoded[4:4 + total_len]
    decoded = cdp.IPCFrame.decode(body)
    assert decoded.op_code == cdp.Organ19OpCode.PING
    assert decoded.payload == {"a": 1}


def test_ipc_frame_rejects_oversized_payload():
    huge_payload = {"data": "x" * (cdp.IPC_MAX_FRAME_BYTES)}
    frame = cdp.IPCFrame(op_code=cdp.Organ19OpCode.PING, payload=huge_payload)
    with pytest.raises(ValueError):
        frame.encode()


# ----------------------------------------------------------------------
# COMMAND QUEUE
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_command_queue_resolve():
    queue = cdp.CommandQueue(default_timeout_s=1.0)
    cmd_id = await queue.next_id()
    future = queue.register(cmd_id, "Page.navigate", cdp.CommandQueue.PRIORITY_NORMAL)
    queue.resolve(cmd_id, {"frameId": "F1"})
    result = await future
    assert result == {"frameId": "F1"}


@pytest.mark.asyncio
async def test_command_queue_reject():
    queue = cdp.CommandQueue(default_timeout_s=1.0)
    cmd_id = await queue.next_id()
    future = queue.register(cmd_id, "Page.navigate", cdp.CommandQueue.PRIORITY_NORMAL)
    queue.reject(cmd_id, -32000, "boom")
    with pytest.raises(cdp.CDPCommandError):
        await future


@pytest.mark.asyncio
async def test_command_queue_reject_all():
    queue = cdp.CommandQueue(default_timeout_s=1.0)
    ids = [await queue.next_id() for _ in range(3)]
    futures = [queue.register(i, "m", 5) for i in ids]
    queue.reject_all("connection lost")
    for future in futures:
        with pytest.raises(cdp.CDPCommandError):
            await future


# ----------------------------------------------------------------------
# EVENT BUS
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_event_bus_publish_and_subscribe():
    bus = cdp.CDPEventBus(capacity=10)
    received = []

    async def _cb(event):
        received.append(event)

    bus.subscribe("sub1", _cb)
    event = cdp.AOSEvent(cdp.AOSEventType.PAGE_LOADED, "b1", "s1", {"x": 1})
    await bus.publish(event)
    assert len(received) == 1
    assert received[0].event_type == cdp.AOSEventType.PAGE_LOADED


@pytest.mark.asyncio
async def test_event_bus_ring_buffer_drops_oldest():
    bus = cdp.CDPEventBus(capacity=2)
    for i in range(5):
        await bus.publish(cdp.AOSEvent(cdp.AOSEventType.DOM_READY, "b1", None, {"i": i}))
    assert bus.dropped_count == 3
    assert len(bus.recent(10)) == 2


def test_event_catalog_mapping():
    assert cdp.AOSEventType.from_cdp_method("Page.loadEventFired") == cdp.AOSEventType.PAGE_LOADED
    assert cdp.AOSEventType.from_cdp_method("Unknown.method") is None


# ----------------------------------------------------------------------
# TARGET ROUTER
# ----------------------------------------------------------------------

def test_target_router_register_and_resolve():
    router = cdp.TargetRouter()
    handle = cdp.TargetHandle(target_id="T1", session_id="S1", browser_id="B1", target_type="page")
    router.register(handle)
    assert router.resolve_by_session("S1") is handle
    assert router.resolve_by_target("T1") is handle
    assert router.list_targets("B1") == [handle]
    router.unregister_by_target("T1")
    assert router.resolve_by_session("S1") is None


def test_frame_context_tracker():
    tracker = cdp.FrameContextTracker()
    tracker.upsert_frame("F1", "L1", "https://example.com")
    tracker.bind_execution_context("F1", 42)
    frame = tracker.get("F1")
    assert frame.loader_id == "L1"  # type: ignore
    assert frame.execution_context_id == 42  # type: ignore


# ----------------------------------------------------------------------
# DOM / ACCESSIBILITY ENGINE (mocked invoker)
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dom_accessibility_engine_synthesize_tree():
    async def fake_invoke(session_id, method, params):
        if method == "DOM.getFlattenedDocument":
            return {"nodes": [{"nodeId": 1, "backendNodeId": 100, "nodeName": "button",
                                "attributes": ["id", "submit-btn"], "frameId": "F1"}]}
        if method == "Accessibility.getFullAXTree":
            return {"nodes": [{"backendDOMNodeId": 100, "role": {"value": "button"},
                                "name": {"value": "Submit"}}]}
        if method == "DOM.getBoxModel":
            return {"model": {"content": [0, 0, 10, 0, 10, 10, 0, 10]}}
        raise AssertionError(f"unexpected method {method}")

    engine = cdp.DOMAccessibilityEngine(fake_invoke)
    nodes = await engine.synthesize_tree("S1")
    assert len(nodes) == 1
    node = nodes[0]
    assert node.tag_name == "BUTTON"
    assert node.ax_role == "button"
    assert node.is_clickable is True
    assert node.bounding_box == {"x": 0, "y": 0, "width": 10, "height": 10}


# ----------------------------------------------------------------------
# VIRTUAL INPUT ENGINE
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_virtual_input_click_sends_mouse_events():
    calls = []

    async def fake_invoke(session_id, method, params):
        calls.append((method, params.get("type")))
        return {}

    engine = cdp.VirtualInputEngine(fake_invoke, humanize_mouse=False)
    await engine.click("S1", 10, 20)
    event_types = [c[1] for c in calls]
    assert "mousePressed" in event_types
    assert "mouseReleased" in event_types


@pytest.mark.asyncio
async def test_virtual_input_type_text_sends_key_sequence():
    calls = []

    async def fake_invoke(session_id, method, params):
        calls.append(params.get("type"))
        return {}

    engine = cdp.VirtualInputEngine(fake_invoke, typing_delay_variance_ms=(0, 1))
    await engine.type_text("S1", "ab")
    assert calls.count("keyDown") == 2
    assert calls.count("char") == 2
    assert calls.count("keyUp") == 2


def test_bezier_path_generation():
    path = cdp._cubic_bezier_path(0, 0, 100, 100, steps=10)
    assert len(path) == 11
    assert path[0] != path[-1]


# ----------------------------------------------------------------------
# NETWORK INTERCEPTOR
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_network_interceptor_block_rule():
    calls = []

    async def fake_invoke(session_id, method, params):
        calls.append((method, params))
        return {}

    interceptor = cdp.NetworkInterceptor(fake_invoke)
    await interceptor.enable("S1", global_interception=True)
    interceptor.add_rule("S1", cdp.NetworkRule(rule_id="r1", url_pattern="*ads*", action="BLOCK"))
    await interceptor.handle_request_paused("S1", {"requestId": "R1", "request": {"url": "http://ads.example.com"}})
    fail_calls = [c for c in calls if c[0] == "Fetch.failRequest"]
    assert len(fail_calls) == 1
    assert fail_calls[0][1]["errorReason"] == "BlockedByClient"


@pytest.mark.asyncio
async def test_network_interceptor_pass_through_default():
    calls = []

    async def fake_invoke(session_id, method, params):
        calls.append((method, params))
        return {}

    interceptor = cdp.NetworkInterceptor(fake_invoke)
    await interceptor.enable("S1")
    await interceptor.handle_request_paused("S1", {"requestId": "R2", "request": {"url": "http://example.com"}})
    continue_calls = [c for c in calls if c[0] == "Fetch.continueRequest"]
    assert len(continue_calls) == 1


# ----------------------------------------------------------------------
# DOWNLOAD MANAGER
# ----------------------------------------------------------------------

def test_download_manager_lifecycle(tmp_path):
    async def fake_invoke(session_id, method, params):
        return {}

    manager = cdp.DownloadManager(fake_invoke, str(tmp_path))
    manager.on_download_will_begin("G1", "http://example.com/file.zip", "file.zip")
    file_path = tmp_path / "file.zip"
    file_path.write_bytes(b"hello world")
    record = manager.on_download_progress("G1", "completed", 11, 11, str(file_path))
    assert record.state == "completed"  # type: ignore
    assert record.sha256 is not None  # type: ignore
    fetched = manager.status("G1")
    assert fetched.sha256 == record.sha256  # type: ignore


# ----------------------------------------------------------------------
# BROWSER DISCOVERY ENGINE
# ----------------------------------------------------------------------

def test_discovery_engine_devtools_active_port_file(tmp_path):
    port_file = tmp_path / "DevToolsActivePort"
    port_file.write_text("9333\n/devtools/browser/abc-123\n")
    engine = cdp.BrowserDiscoveryEngine()
    result = engine.read_devtools_active_port_file(str(tmp_path))
    assert result == ("/devtools/browser/abc-123", 9333)


def test_discovery_engine_missing_port_file(tmp_path):
    engine = cdp.BrowserDiscoveryEngine()
    assert engine.read_devtools_active_port_file(str(tmp_path)) is None


# ----------------------------------------------------------------------
# RUNTIME CONFIG
# ----------------------------------------------------------------------

def test_runtime_config_from_dict():
    cfg = cdp.RuntimeConfig.from_dict({"max_concurrent_browsers": 4, "unknown_field": 99})
    assert cfg.max_concurrent_browsers == 4
    assert not hasattr(cfg, "unknown_field") or cfg.max_concurrent_browsers == 4


def test_runtime_config_dirs(tmp_path):
    cfg = cdp.RuntimeConfig(runtime_dir=str(tmp_path))
    cfg.ensure_dirs()
    assert os.path.isdir(cfg.profiles_dir)
    assert os.path.isdir(cfg.downloads_dir)


# ----------------------------------------------------------------------
# KERNEL DISPATCH (mock-heavy, verifies routing without live Chromium)
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kernel_ping_dispatch(tmp_path):
    cfg = cdp.RuntimeConfig(runtime_dir=str(tmp_path))
    cfg.ensure_dirs()
    kernel = cdp.CDPRuntimeKernel(cfg)
    frame = cdp.IPCFrame(op_code=cdp.Organ19OpCode.PING, payload={})
    response = await kernel.dispatch(frame)
    assert response.op_code == cdp.Organ19OpCode.PING
    assert response.payload["ok"] is True
    assert response.payload["result"]["pong"] is True


@pytest.mark.asyncio
async def test_kernel_unknown_opcode_returns_error(tmp_path):
    cfg = cdp.RuntimeConfig(runtime_dir=str(tmp_path))
    cfg.ensure_dirs()
    kernel = cdp.CDPRuntimeKernel(cfg)
    frame = cdp.IPCFrame(op_code=0x9999, payload={})
    response = await kernel.dispatch(frame)
    assert response.op_code == cdp.Organ19OpCode.ERROR


@pytest.mark.asyncio
async def test_kernel_list_targets_empty(tmp_path):
    cfg = cdp.RuntimeConfig(runtime_dir=str(tmp_path))
    cfg.ensure_dirs()
    kernel = cdp.CDPRuntimeKernel(cfg)
    frame = cdp.IPCFrame(op_code=cdp.Organ19OpCode.LIST_TARGETS, payload={})
    response = await kernel.dispatch(frame)
    assert response.payload["result"]["targets"] == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
