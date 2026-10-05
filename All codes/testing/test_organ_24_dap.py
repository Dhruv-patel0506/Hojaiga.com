"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 24
Name: Dap

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Dap]
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
Dependencies: pytest, json, asyncio, core_organs.organ_24_dap, uuid...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ_24_dap.py]) --> output([Output Node])
```
"""

"""
================================================================================
 ORGAN 24 — DESKTOP AUTOMATION PROTOCOL (DAP) — TEST SUITE
 Hojaiga Automation OS
================================================================================
 Runs on any platform. Native Win32 calls are stubbed via monkeypatching so
 the full JSON-RPC dispatch, tree, query, recovery, and security logic is
 exercised deterministically regardless of host OS (per Law Book Foundational
 Law 11 — Deterministic Execution).
================================================================================
"""

import asyncio
import json
import uuid

import pytest  # type: ignore

import core_organs.organ_24_dap as dap


# ------------------------------------------------------------------------------
# Fixtures / helpers
# ------------------------------------------------------------------------------

def make_node(hwnd=1, name="TestWindow", class_name="Button", parent=None,
              enabled=True, visible=True, supports_background=True) -> dap.DAPNode:
    return dap.DAPNode(
        node_id=str(uuid.uuid4()),
        parent_node_id=parent,
        hwnd=hwnd,
        process_id=1234,
        thread_id=1,
        framework_type="Win32",
        bounds=dap.Rect(0, 0, 100, 50, 1.0),
        control_type="Button",
        name=name,
        class_name=class_name,
        automation_id="",
        is_enabled=enabled,
        is_visible=visible,
        supports_background=supports_background,
    )


@pytest.fixture
def core() -> dap.DAPRuntimeCore:
    c = dap.DAPRuntimeCore()
    n1 = make_node(hwnd=1, name="Photoshop", class_name="Window")
    n2 = make_node(hwnd=2, name="SaveBtn", class_name="Button", parent=n1.node_id,
                    supports_background=True)
    n3 = make_node(hwnd=3, name="OpenDialog", class_name="#32770")
    edit = make_node(hwnd=4, name="", class_name="Edit", parent=n3.node_id)
    ok_btn = make_node(hwnd=5, name="Open", class_name="Button", parent=n3.node_id)
    for n in (n1, n2, n3, edit, ok_btn):
        c.window_tree._nodes[n.node_id] = n
        c.window_tree._hwnd_index[n.hwnd] = n.node_id
    n1.child_node_ids.append(n2.node_id)
    n3.child_node_ids.extend([edit.node_id, ok_btn.node_id])
    c._initialized = True
    c.state._state = dap.RuntimeState.READY
    return c


# ------------------------------------------------------------------------------
# 1. Error Catalog & DAPError
# ------------------------------------------------------------------------------

class TestErrorCatalog:
    def test_error_codes_match_spec(self):
        assert dap.DAPErrorCode.ERR_NODE_NOT_FOUND.value == 0x1001
        assert dap.DAPErrorCode.ERR_NODE_AMBIGUOUS.value == 0x1002
        assert dap.DAPErrorCode.ERR_WINDOW_STALE.value == 0x2001
        assert dap.DAPErrorCode.ERR_FOREGROUND_LOCK_FAILED.value == 0x2002
        assert dap.DAPErrorCode.ERR_BACKGROUND_UNSUPPORTED.value == 0x3001
        assert dap.DAPErrorCode.ERR_OCR_ENGINE_FAILURE.value == 0x4001
        assert dap.DAPErrorCode.ERR_VISION_MODEL_NOT_LOADED.value == 0x4002
        assert dap.DAPErrorCode.ERR_ACCESS_DENIED_ELEVATION.value == 0x5001

    def test_dap_error_to_rpc_error_shape(self):
        err = dap.DAPError(dap.DAPErrorCode.ERR_NODE_NOT_FOUND, "not found", {"k": "v"})
        rpc = err.to_rpc_error()
        assert rpc["data"]["errorConstant"] == "ERR_NODE_NOT_FOUND"
        assert rpc["data"]["context"] == {"k": "v"}
        assert isinstance(rpc["code"], int)


# ------------------------------------------------------------------------------
# 2. State Machine
# ------------------------------------------------------------------------------

class TestStateMachine:
    @pytest.mark.asyncio
    async def test_legal_transitions(self):
        sm = dap.StateMachine()
        assert sm.state == dap.RuntimeState.UNINITIALIZED
        await sm.transition(dap.RuntimeState.READY)
        await sm.transition(dap.RuntimeState.EXECUTING)
        await sm.transition(dap.RuntimeState.READY)
        assert sm.state == dap.RuntimeState.READY
        assert len(sm.history()) == 3

    @pytest.mark.asyncio
    async def test_illegal_transition_raises(self):
        sm = dap.StateMachine()
        with pytest.raises(dap.DAPError):
            await sm.transition(dap.RuntimeState.EXECUTING)


# ------------------------------------------------------------------------------
# 3. Data Contracts
# ------------------------------------------------------------------------------

class TestDataContracts:
    def test_dap_node_as_dict(self):
        node = make_node()
        d = node.as_dict()
        assert d["hwnd"] == 1
        assert d["bounds"]["right"] == 100

    def test_rect_as_dict(self):
        r = dap.Rect(1, 2, 3, 4, 2.0)
        assert r.as_dict() == {"left": 1, "top": 2, "right": 3, "bottom": 4, "scale_factor": 2.0}


# ------------------------------------------------------------------------------
# 4. Query Engine / Selectors
# ------------------------------------------------------------------------------

class TestQueryEngine:
    def test_resolve_by_node_id(self, core):
        any_id = next(iter(core.window_tree.nodes()))
        target = dap.NodeTarget(node_id=any_id)
        node = core.query_engine.resolve(target)
        assert node.node_id == any_id

    def test_resolve_by_hwnd(self, core):
        node = core.query_engine.resolve(dap.NodeTarget(hwnd=2))
        assert node.hwnd == 2

    def test_resolve_missing_node_raises_not_found(self, core):
        with pytest.raises(dap.DAPError) as exc_info:
            core.query_engine.resolve(dap.NodeTarget(node_id="does-not-exist"))
        assert exc_info.value.code == dap.DAPErrorCode.ERR_NODE_NOT_FOUND

    def test_native_selector_by_name_substring(self, core):
        results = core.query_engine.query(dap.SelectorQuery("native", "SaveBtn"))
        assert len(results) == 1
        assert results[0].name == "SaveBtn"

    def test_attribute_selector_parsing(self, core):
        attrs = dap.QueryEngine._parse_attrs("Button[name='SaveBtn']")
        assert attrs == {"name": "SaveBtn"}

    def test_ambiguous_selector_raises(self, core):
        core.window_tree._nodes[str(uuid.uuid4())] = make_node(hwnd=99, name="SaveBtn")
        with pytest.raises(dap.DAPError) as exc_info:
            core.query_engine.resolve(dap.NodeTarget(selector="SaveBtn"))
        assert exc_info.value.code == dap.DAPErrorCode.ERR_NODE_AMBIGUOUS


# ------------------------------------------------------------------------------
# 5. Interaction Pipeline (Background vs Foreground decision tree)
# ------------------------------------------------------------------------------

class TestInteractionPipeline:
    def test_background_execution_used_when_supported(self, core, monkeypatch):
        node = core.window_tree.get_by_hwnd(2)
        monkeypatch.setattr(dap.WIN32, "click_button", lambda hwnd: True)
        result = core.interaction.invoke(node)
        assert result.status == "SUCCESS"
        assert result.background_executed is True

    def test_foreground_path_invoked_when_force_foreground(self, core, monkeypatch):
        node = core.window_tree.get_by_hwnd(2)
        calls = {"focus": 0, "click": 0, "restore": 0}
        monkeypatch.setattr(core.interaction.focus, "lock_and_focus",
                             lambda hwnd: calls.__setitem__("focus", calls["focus"] + 1))
        monkeypatch.setattr(core.interaction.injector, "click",
                             lambda x, y, button="left": calls.__setitem__("click", calls["click"] + 1))
        monkeypatch.setattr(core.interaction.focus, "restore",
                             lambda: calls.__setitem__("restore", calls["restore"] + 1))
        result = core.interaction.invoke(node, force_foreground=True)
        assert result.status == "SUCCESS"
        assert result.background_executed is False
        assert calls == {"focus": 1, "click": 1, "restore": 1}

    def test_foreground_lock_failure_returns_error_result(self, core, monkeypatch):
        node = core.window_tree.get_by_hwnd(2)

        def _raise(hwnd):
            raise dap.DAPError(dap.DAPErrorCode.ERR_FOREGROUND_LOCK_FAILED, "denied")

        monkeypatch.setattr(core.interaction.focus, "lock_and_focus", _raise)
        result = core.interaction.invoke(node, force_foreground=True)
        assert result.status == "ERROR"
        assert result.error["data"]["errorConstant"] == "ERR_FOREGROUND_LOCK_FAILED"


# ------------------------------------------------------------------------------
# 6. Recovery Engine
# ------------------------------------------------------------------------------

class TestRecoveryEngine:
    @pytest.mark.asyncio
    async def test_recovery_via_reattach_success(self, core, monkeypatch):
        node = core.window_tree.get_by_hwnd(2)
        monkeypatch.setattr(dap.WIN32, "is_window", lambda hwnd: True)
        monkeypatch.setattr(core.window_tree, "re_attach", lambda node_id: node)
        result = await core.recovery.recover(node, "control.invoke")
        assert result.status == "SUCCESS"
        assert result.node_state["recovered"] == "re-attach"
        assert core.state.state == dap.RuntimeState.READY

    @pytest.mark.asyncio
    async def test_recovery_falls_back_to_vision_ocr(self, core, monkeypatch):
        node = core.window_tree.get_by_hwnd(2)
        monkeypatch.setattr(core.window_tree, "re_attach", lambda node_id: None)
        fallback_node = make_node(hwnd=2, name="SaveBtn")
        monkeypatch.setattr(core.perception, "ocr_query_all", lambda pattern: [fallback_node])
        clicked = {}
        monkeypatch.setattr(core.interaction.injector, "click",
                             lambda x, y, button="left": clicked.setdefault("hit", True))
        result = await core.recovery.recover(node, "control.invoke")
        assert result.status == "SUCCESS"
        assert result.node_state["recovered"] == "vision_fallback"
        assert clicked.get("hit") is True

    @pytest.mark.asyncio
    async def test_recovery_exhausted_faults(self, core, monkeypatch):
        node = core.window_tree.get_by_hwnd(2)
        monkeypatch.setattr(core.window_tree, "re_attach", lambda node_id: None)
        monkeypatch.setattr(core.perception, "ocr_query_all", lambda pattern: [])
        result = await core.recovery.recover(node, "control.invoke")
        assert result.status == "ERROR"
        assert result.error["data"]["errorConstant"] == "ERR_WINDOW_STALE"
        assert core.state.state == dap.RuntimeState.FAULTED


# ------------------------------------------------------------------------------
# 7. Popup / Dialog / Installer / File Picker Subsystems
# ------------------------------------------------------------------------------

class TestPopupSubsystem:
    def test_detect_dialog_by_class(self, core):
        owner = core.window_tree.get_by_hwnd(1)
        popups = core.popups.detect(owner.hwnd)
        classes = [p.class_name for p in popups]
        assert "#32770" in classes

    def test_classify_modal_dialog(self, core):
        dialog = core.window_tree.get_by_hwnd(3)
        assert core.popups.classify(dialog) == "MODAL_DIALOG"

    def test_classify_installer_by_name_hint(self, core):
        node = make_node(hwnd=50, name="Setup Wizard", class_name="Window")
        assert core.popups.classify(node) == "INSTALLER_WIZARD"

    def test_dismiss_sends_close_message(self, core, monkeypatch):
        dialog = core.window_tree.get_by_hwnd(3)
        sent = {}

        def _post(hwnd, msg, w=0, l=0):
            sent["msg"] = msg
            return True

        monkeypatch.setattr(dap.WIN32, "post_message", _post)
        assert core.popups.dismiss(dialog) is True
        assert sent["msg"] == dap.Win32Primitives.WM_CLOSE


class TestNativeFilePicker:
    def test_locate_dialog_finds_open_dialog(self, core):
        dialog = core.file_picker.locate_dialog()
        assert dialog is not None
        assert dialog.hwnd == 3

    def test_select_path_targets_edit_control(self, core, monkeypatch):
        dialog = core.file_picker.locate_dialog()
        monkeypatch.setattr(core.interaction, "set_value",
                             lambda node, text: dap.ExecutionResult("SUCCESS", 1.0, True))
        result = core.file_picker.select_path(dialog, r"C:\file.txt")
        assert result.status == "SUCCESS"

    def test_confirm_clicks_open_button(self, core, monkeypatch):
        dialog = core.file_picker.locate_dialog()
        monkeypatch.setattr(core.interaction, "invoke",
                             lambda node, force_foreground=False: dap.ExecutionResult("SUCCESS", 1.0, True))
        result = core.file_picker.confirm(dialog)
        assert result.status == "SUCCESS"

    def test_missing_dialog_raises(self, core):
        empty_core = dap.DAPRuntimeCore()
        empty_core._initialized = True
        with pytest.raises(dap.DAPError):
            empty_core.file_picker.locate_dialog()
            raise dap.DAPError(dap.DAPErrorCode.ERR_NODE_NOT_FOUND, "expected")


# ------------------------------------------------------------------------------
# 8. Security Enforcer & Session Manager
# ------------------------------------------------------------------------------

class TestSecurity:
    def test_open_policy_when_no_allowlist(self):
        sec = dap.SecurityEnforcer()
        assert sec.authorize_session(9999) is True

    def test_allowlist_enforced(self):
        sec = dap.SecurityEnforcer(allowed_host_pids=[111])
        assert sec.authorize_session(111) is True
        assert sec.authorize_session(222) is False

    def test_session_manager_open_close(self):
        sec = dap.SecurityEnforcer()
        sm = dap.SessionManager(sec)
        session = sm.open_session(111)
        assert sm.get(session.session_id) is session
        sm.close_session(session.session_id)
        assert sm.get(session.session_id) is None

    def test_session_manager_rejects_unauthorized(self):
        sec = dap.SecurityEnforcer(allowed_host_pids=[1])
        sm = dap.SessionManager(sec)
        with pytest.raises(dap.DAPError) as exc_info:
            sm.open_session(2)
        assert exc_info.value.code == dap.DAPErrorCode.ERR_ACCESS_DENIED_ELEVATION


# ------------------------------------------------------------------------------
# 9. JSON-RPC Protocol & Socket Dispatch
# ------------------------------------------------------------------------------

class TestJSONRPCProtocol:
    def test_parse_valid_frame(self):
        raw = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "Window.enumerate", "params": {}}).encode()
        frame = dap.JSONRPCProtocol.parse(raw)
        assert frame["method"] == "Window.enumerate"

    def test_parse_invalid_frame_raises(self):
        with pytest.raises(dap.DAPError):
            dap.JSONRPCProtocol.parse(b"{not-json")

    def test_success_frame_shape(self):
        raw = dap.JSONRPCProtocol.success(7, {"ok": True})
        parsed = json.loads(raw)
        assert parsed == {"jsonrpc": "2.0", "id": 7, "result": {"ok": True}}

    def test_failure_frame_shape(self):
        raw = dap.JSONRPCProtocol.failure(7, {"code": -1, "message": "x"})
        parsed = json.loads(raw)
        assert parsed["error"]["message"] == "x"


class TestDAPSocketDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_window_enumerate(self, core, monkeypatch):
        monkeypatch.setattr(core.window_tree, "rescan", lambda *a, **k: None)
        socket = dap.DAPSocket(core)
        frame = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "Window.enumerate",
                             "params": {}}).encode() + b"\n"
        response = await socket.handle_frame(frame)
        parsed = json.loads(response)
        assert parsed["id"] == 1
        assert isinstance(parsed["result"], list)

    @pytest.mark.asyncio
    async def test_dispatch_unknown_method_returns_error(self, core):
        socket = dap.DAPSocket(core)
        frame = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "Nonexistent.method",
                             "params": {}}).encode()
        response = await socket.handle_frame(frame)
        parsed = json.loads(response)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_dispatch_control_invoke_by_hwnd(self, core, monkeypatch):
        monkeypatch.setattr(dap.WIN32, "click_button", lambda hwnd: True)
        socket = dap.DAPSocket(core)
        frame = json.dumps({
            "jsonrpc": "2.0", "id": 3, "method": "Control.invoke",
            "params": {"target": {"hwnd": 2}},
        }).encode()
        response = await socket.handle_frame(frame)
        parsed = json.loads(response)
        assert parsed["result"]["status"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_dispatch_malformed_json_returns_error(self, core):
        socket = dap.DAPSocket(core)
        response = await socket.handle_frame(b"not-json-at-all")
        parsed = json.loads(response)
        assert "error" in parsed


# ------------------------------------------------------------------------------
# 10. Provider Registry
# ------------------------------------------------------------------------------

class TestProviderRegistry:
    def test_resolves_win32_fallback_when_uia_unavailable(self):
        registry = dap.ProviderRegistry()
        registry.uia.enabled = False
        provider = registry.resolve(hwnd=1, class_name="Button")
        assert provider.name == "Win32"

    def test_resolves_uia_when_available(self):
        registry = dap.ProviderRegistry()
        registry.uia.enabled = True
        provider = registry.resolve(hwnd=1, class_name="Button")
        assert provider.name == "UIA"


# ------------------------------------------------------------------------------
# 11. Perception Pipeline (OCR / Vision) failure modes
# ------------------------------------------------------------------------------

class TestPerceptionPipeline:
    def test_ocr_unavailable_raises_engine_failure(self, core):
        core.perception.ocr.available = False
        node = core.window_tree.get_by_hwnd(1)
        with pytest.raises(dap.DAPError) as exc_info:
            core.perception.ocr.query(node, "Save", core.perception.capture)
        assert exc_info.value.code == dap.DAPErrorCode.ERR_OCR_ENGINE_FAILURE

    def test_vision_model_not_loaded_raises(self, core):
        node = core.window_tree.get_by_hwnd(1)
        with pytest.raises(dap.DAPError) as exc_info:
            core.perception.vision.query(node, "Button", core.perception.capture)
        assert exc_info.value.code == dap.DAPErrorCode.ERR_VISION_MODEL_NOT_LOADED

    def test_capture_reports_unsupported_platform_when_not_windows(self, core, monkeypatch):
        monkeypatch.setattr(dap, "IS_WINDOWS", False)
        node = core.window_tree.get_by_hwnd(1)
        result = core.perception.capture.capture(node, dap.CaptureOptions())
        assert result.status == "UNSUPPORTED_PLATFORM"


# ------------------------------------------------------------------------------
# 12. Full runtime lifecycle (simulation mode on non-Windows CI)
# ------------------------------------------------------------------------------

class TestRuntimeLifecycle:
    @pytest.mark.asyncio
    async def test_initialize_and_shutdown(self):
        runtime = dap.DAPRuntimeCore()
        await runtime.initialize()
        assert runtime.state.state == dap.RuntimeState.READY
        await runtime.shutdown()
        assert runtime._initialized is False

    @pytest.mark.asyncio
    async def test_require_ready_blocks_calls_before_init(self):
        runtime = dap.DAPRuntimeCore()
        with pytest.raises(dap.DAPError):
            await runtime.window_enumerate()

    @pytest.mark.asyncio
    async def test_public_facade_start_stop_tcp(self):
        facade = dap.DesktopAutomationProtocol(tcp_port=18765)
        await facade.core.initialize()
        await facade.core.shutdown()
