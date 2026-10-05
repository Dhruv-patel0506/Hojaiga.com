"""
Socket Throughput Test — Verifies CNS bridge can pass popup data under load.
Run via Aider: /run pytest test_socket_throughput.py
"""
import json
import sys
import time
import threading

sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs.cns_bridge import CNSSocketBridge, CNSPopupInterceptor
from core_organs.database_manager import DatabaseManager


def test_database_manager_layout_hash():
    """Test layout hash generation is deterministic."""
    db = DatabaseManager()
    h1 = db.generate_layout_hash("test popup title")
    h2 = db.generate_layout_hash("test popup title")
    assert h1 == h2, "Layout hash must be deterministic"
    assert len(h1) == 32, "MD5 hash must be 32 chars"
    print(f"[PASS] Layout hash: {h1}")


def test_database_manager_popup_fingerprint():
    """Test popup fingerprint from title + buttons."""
    db = DatabaseManager()
    fp1 = db.generate_popup_fingerprint("Error Dialog", ["OK", "Cancel"])
    fp2 = db.generate_popup_fingerprint("Error Dialog", ["OK", "Cancel"])
    fp3 = db.generate_popup_fingerprint("Error Dialog", ["Yes", "No"])
    assert fp1 == fp2, "Same input must produce same fingerprint"
    assert fp1 != fp3, "Different buttons must produce different fingerprint"
    print(f"[PASS] Popup fingerprint: {fp1}")


def test_database_manager_store_and_retrieve():
    """Test store and retrieve popup history."""
    db = DatabaseManager()
    test_title = "TestPopup_ThroughputTest"
    test_action = "click:OK"

    db.log_new_pathway(
        layout_hash="test_hash_123",
        element_name=test_title,
        x=100, y=200,
        action_type=test_action,
        parent_path="test_path",
        popup_type="INFORMATIONAL",
    )

    result = db.check_popup_history(test_title)
    assert result is not None, "Should find stored popup"
    assert result["action"] == test_action, f"Action mismatch: {result['action']}"
    print(f"[PASS] Store+retrieve: {result}")


def test_cns_socket_send_receive():
    """Test CNS socket bridge can send and receive messages."""
    received = []

    def on_message(msg):
        received.append(msg)

    bridge = CNSSocketBridge(role="TestHost", port=11437)
    bridge.start_listener(on_message)
    time.sleep(0.3)

    sent = bridge.send_alert({
        "type": "POPUP_DETECTED",
        "title": "Test Popup",
        "x": 150,
        "y": 250,
    })
    time.sleep(0.5)

    bridge.stop()
    assert sent, "Send should succeed"
    assert len(received) > 0, f"Should receive message, got {len(received)}"
    assert received[0]["type"] == "POPUP_DETECTED"
    print(f"[PASS] CNS send/receive: {received[0]}")


def test_cns_popup_interceptor():
    """Test CNSPopupInterceptor alert flow."""
    interceptor = CNSPopupInterceptor(role="TestApp", port=11438)
    interceptor.start()
    time.sleep(0.3)

    popup_id = interceptor.alert_popup_detected(
        title="Intercept Test",
        layout_hash="abc123",
        x=100, y=200,
    )
    assert popup_id, "Should return popup_id"
    print(f"[PASS] Popup interceptor alert: {popup_id}")

    interceptor.stop()


def test_throughput_burst():
    """Test 50 rapid-fire popup detections through CNS."""
    received = []

    def on_message(msg):
        received.append(msg)

    bridge = CNSSocketBridge(role="BurstTest", port=11439)
    bridge.start_listener(on_message)
    time.sleep(0.3)

    start = time.time()
    for i in range(50):
        bridge.send_alert({"type": "POPUP_DETECTED", "index": i, "title": f"Burst_{i}"})
    elapsed = time.time() - start

    time.sleep(1.0)
    bridge.stop()

    print(f"[PASS] Burst: 50 messages sent in {elapsed:.3f}s, received {len(received)}")
    assert len(received) >= 40, f"Expected >=40 received, got {len(received)}"


if __name__ == "__main__":
    tests = [
        test_database_manager_layout_hash,
        test_database_manager_popup_fingerprint,
        test_database_manager_store_and_retrieve,
        test_cns_socket_send_receive,
        test_cns_popup_interceptor,
        test_throughput_burst,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            print(f"\n--- {test.__name__} ---")
            test()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    sys.exit(0 if failed == 0 else 1)
