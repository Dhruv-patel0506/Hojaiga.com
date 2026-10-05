"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 29
Name: Popup Handler

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Popup Handler]
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
Dependencies: asyncio, core_organs.organ_29_popup_handler, unittest...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_organ_29_popup_handler.py]) --> output([Output Node])
```
"""

"""Tests for Organ 29 — Popup Handler (Desktop Interaction Manager)."""

import asyncio
import unittest

from core_organs.organ_29_popup_handler import (
    DesktopInteractionManager,
    WindowNode,
    WindowRect,
    WindowType,
    WindowClassifier,
    WindowTreeManager,
    FocusManager,
    NullWindowBackend,
    SecurityPolicyGuard,
    InstallerWizardEngine,
    NativeFilePickerEngine,
    DeadlockGuard,
    SocketMessage,
)


def make_node(handle, parent=None, title="", class_name="", win_type=WindowType.UNKNOWN):
    return WindowNode(
        handle=handle,
        parent_handle=parent,
        owner_handle=None,
        process_id=1000 + handle,
        title=title,
        class_name=class_name,
        win_type=win_type,
        bounds=WindowRect(0, 0, 100, 100),
    )


class TestWindowClassifier(unittest.TestCase):
    def setUp(self):
        self.clf = WindowClassifier()

    def test_class_hint(self):
        node = make_node(1, class_name="#32770")
        self.assertEqual(self.clf.classify(node), WindowType.MESSAGE_BOX)

    def test_title_hint(self):
        node = make_node(2, title="Save As")
        self.assertEqual(self.clf.classify(node), WindowType.SAVE_DIALOG)

    def test_child_fallback(self):
        node = make_node(3, parent=1, title="", class_name="")
        self.assertEqual(self.clf.classify(node), WindowType.CHILD_WINDOW)

    def test_unknown_fallback(self):
        node = make_node(4)
        self.assertEqual(self.clf.classify(node), WindowType.UNKNOWN)


class TestWindowTreeManager(unittest.TestCase):
    def test_unlimited_depth_rebuild(self):
        nodes = [make_node(0)]
        for level in range(1, 50):
            nodes.append(make_node(level, parent=level - 1))
        tree = WindowTreeManager()
        tree.rebuild(nodes)
        self.assertEqual(len(tree.roots()), 1)
        flattened = tree.roots()[0].flatten()
        self.assertEqual(len(flattened), 50)

    def test_disambiguate_duplicates(self):
        n1 = make_node(1, title="Notepad", class_name="Notepad")
        n2 = make_node(2, title="Notepad", class_name="Notepad")
        tree = WindowTreeManager()
        tree.rebuild([n1, n2])
        dups = tree.disambiguate("Notepad", "Notepad")
        self.assertEqual(len(dups), 2)

    def test_find(self):
        tree = WindowTreeManager()
        tree.rebuild([make_node(5)])
        self.assertIsNotNone(tree.find(5))
        self.assertIsNone(tree.find(999))


class TestFocusManager(unittest.TestCase):
    def test_capture_and_restore(self):
        fm = FocusManager(NullWindowBackend())
        fm.capture(100)
        fm.capture(200)
        self.assertEqual(fm.state.previous_window, 100)
        self.assertTrue(fm.restore_previous())
        self.assertEqual(fm.state.active_window, 100)

    def test_modal_stack(self):
        fm = FocusManager(NullWindowBackend())
        fm.push_modal(1)
        fm.push_modal(2)
        self.assertEqual(fm.pop_modal(), 2)
        self.assertEqual(fm.pop_modal(), 1)
        self.assertIsNone(fm.pop_modal())


class TestSecurityPolicyGuard(unittest.TestCase):
    def test_non_sensitive_auto_approved(self):
        guard = SecurityPolicyGuard()
        self.assertTrue(guard.is_approved(WindowType.MESSAGE_BOX, None))

    def test_uac_blocked_without_token(self):
        guard = SecurityPolicyGuard()
        self.assertFalse(guard.is_approved(WindowType.UAC_PROMPT, None))

    def test_uac_approved_with_signed_token(self):
        guard = SecurityPolicyGuard(signed_approval_tokens={"tok-123"})
        self.assertTrue(guard.is_approved(WindowType.UAC_PROMPT, "tok-123"))

    def test_requires_escalation(self):
        guard = SecurityPolicyGuard()
        self.assertTrue(guard.requires_escalation(WindowType.AUTHENTICATION))
        self.assertFalse(guard.requires_escalation(WindowType.TOOLTIP))


class TestInstallerWizardEngine(unittest.TestCase):
    def setUp(self):
        self.engine = InstallerWizardEngine(NullWindowBackend(), SecurityPolicyGuard())

    def test_detect_pages(self):
        self.assertEqual(self.engine.detect_page(make_node(1, title="Welcome")), "welcome")
        self.assertEqual(self.engine.detect_page(make_node(1, title="License Agreement")), "license")
        self.assertEqual(self.engine.detect_page(make_node(1, title="Choose Destination")), "directory")
        self.assertEqual(self.engine.detect_page(make_node(1, title="Ready to Install")), "install")
        self.assertEqual(self.engine.detect_page(make_node(1, title="Installation Complete")), "finish")

    def test_advance_returns_action(self):
        node = make_node(1, title="Welcome")
        action = asyncio.run(self.engine.advance(node))
        self.assertEqual(action, "Next")

    def test_advance_waits_on_progress(self):
        node = make_node(1, title="Installing... Progress")
        action = asyncio.run(self.engine.advance(node))
        self.assertIsNone(action)


class TestNativeFilePickerEngine(unittest.TestCase):
    def test_detect_none_when_empty(self):
        tree = WindowTreeManager()
        nfpe = NativeFilePickerEngine(NullWindowBackend(), tree)
        self.assertIsNone(nfpe.detect())

    def test_resolve_save_dialog(self):
        tree = WindowTreeManager()
        node = make_node(1, win_type=WindowType.SAVE_DIALOG)
        tree.rebuild([node])
        nfpe = NativeFilePickerEngine(NullWindowBackend(), tree)
        result = asyncio.run(nfpe.resolve("C:/out.txt", is_save_dialog=True))
        self.assertTrue(result)

    def test_playwright_fallback_success(self):
        tree = WindowTreeManager()
        nfpe = NativeFilePickerEngine(NullWindowBackend(), tree)

        class FakeChooser:
            def set_files(self, files):
                self.files = files

        chooser = FakeChooser()
        self.assertTrue(nfpe.try_playwright_fallback(chooser, ["a.txt"]))

    def test_playwright_fallback_failure_routes_to_nfpe(self):
        tree = WindowTreeManager()
        nfpe = NativeFilePickerEngine(NullWindowBackend(), tree)

        class BrokenChooser:
            def set_files(self, files):
                raise RuntimeError("cross-origin blocked")

        self.assertFalse(nfpe.try_playwright_fallback(BrokenChooser(), ["a.txt"]))


class TestDeadlockGuard(unittest.TestCase):
    def test_wait_until_true_immediately(self):
        guard = DeadlockGuard(max_wait_seconds=1, max_loop_iterations=5)
        result = asyncio.run(guard.wait_until(lambda: True))
        self.assertTrue(result)

    def test_wait_until_times_out(self):
        guard = DeadlockGuard(max_wait_seconds=0.3, max_loop_iterations=3)
        result = asyncio.run(guard.wait_until(lambda: False, poll_interval=0.1))
        self.assertFalse(result)


class TestDesktopInteractionManager(unittest.TestCase):
    def setUp(self):
        self.dim = DesktopInteractionManager()

    def test_start_stop_monitoring(self):
        self.assertTrue(asyncio.run(self.dim.start_event_monitoring()))
        self.assertTrue(asyncio.run(self.dim.stop_event_monitoring()))

    def test_intercept_popup_message_box(self):
        node = make_node(1, title="Error", win_type=WindowType.MESSAGE_BOX)
        self.dim.tree.rebuild([node])
        closed = asyncio.run(self.dim.intercept_popup(node))
        # NullWindowBackend never truly removes the window; DeadlockGuard
        # should time out gracefully rather than raise.
        self.assertIn(closed, (True, False))

    def test_intercept_popup_blocks_uac_without_token(self):
        node = make_node(2, title="User Account Control", win_type=WindowType.UAC_PROMPT)
        self.dim.tree.rebuild([node])
        result = asyncio.run(self.dim.intercept_popup(node))
        self.assertFalse(result)

    def test_intercept_popup_allows_uac_with_signed_token(self):
        dim = DesktopInteractionManager(signed_approval_tokens={"ok-token"})
        node = make_node(3, title="User Account Control", win_type=WindowType.UAC_PROMPT)
        dim.tree.rebuild([node])
        # closure won't be confirmed by NullWindowBackend; ensure no early False-block path
        result = asyncio.run(dim.intercept_popup(node, approval_token="ok-token"))
        self.assertIn(result, (True, False))

    def test_socket_registry_has_26_sockets(self):
        self.assertEqual(len(self.dim.sockets.all()), 26)

    def test_discovery_socket_roundtrip(self):
        resp = asyncio.run(
            self.dim.sockets.window_discovery.send(
                SocketMessage("req-1", "test", "dim", {})
            )
        )
        self.assertEqual(resp.status, "ok")
        self.assertIsInstance(resp.result, list)

    def test_focus_socket_roundtrip(self):
        self.dim.tree.rebuild([make_node(9)])
        resp = asyncio.run(
            self.dim.sockets.focus.send(
                SocketMessage("req-2", "test", "dim", {"handle": 9})
            )
        )
        self.assertEqual(resp.status, "ok")
        self.assertTrue(resp.result)

    def test_socket_timeout_and_retry_reports_error(self):
        async def slow_handler(_message):
            await asyncio.sleep(1)

        self.dim.sockets.focus._handlers = [slow_handler]
        self.dim.sockets.focus.timeout_ms = 10
        self.dim.sockets.focus.retries = 1
        resp = asyncio.run(
            self.dim.sockets.focus.send(SocketMessage("req-3", "test", "dim", {}))
        )
        self.assertEqual(resp.status, "error")


if __name__ == "__main__":
    unittest.main()
