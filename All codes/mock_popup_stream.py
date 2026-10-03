"""
Mock Popup Stream — High-throughput CNS stress tester
Floods the Gatekeeper with simulated popup events at 100ms intervals.
Tests thread safety, connection handling, and database locking under load.

Usage:
  1. Ensure Gatekeeper is running on :11435
  2. Run: python mock_popup_stream.py
  3. Watch Pane 2 (Gatekeeper) for thread blocking or connection drops
"""

import json
import random
import socket
import sys
import time

TARGET_HOST = "127.0.0.1"
TARGET_PORT = 11435
TOTAL_EVENTS = 50
INTERVAL_MS = 100

POPUP_TYPES = ["Informational Popup", "Error Popup", "Child Window"]
MOCK_TITLES = [
    "Validation Error",
    "Are you sure?",
    "Source Properties - Video Capture",
    "Update Hint",
    "Delete Scene",
    "Add Source",
    "Settings",
    "Audio Mixer Properties",
]


def stream_mock_data():
    print(f"[STRESS] Initializing CNS stream to {TARGET_HOST}:{TARGET_PORT}")
    print(f"[STRESS] {TOTAL_EVENTS} events at {INTERVAL_MS}ms intervals")
    print(f"[STRESS] Total time: ~{TOTAL_EVENTS * INTERVAL_MS / 1000:.1f}s")
    print()

    time.sleep(2)
    sent = 0
    failed = 0

    for i in range(1, TOTAL_EVENTS + 1):
        mock_payload = {
            "event_id": i,
            "window_title": random.choice(MOCK_TITLES),
            "layout_hash": f"mock_md5_{random.randint(100000, 999999)}",
            "detected_type": random.choice(POPUP_TYPES),
            "coordinates": {
                "x": random.randint(200, 1200),
                "y": random.randint(150, 900),
            },
            "suggested_action": "BypassClick",
            "timestamp": time.time(),
        }

        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(2.0)
            client.connect((TARGET_HOST, TARGET_PORT))
            client.sendall(json.dumps(mock_payload).encode("utf-8"))
            client.close()
            sent += 1

            status = "OK" if sent % 10 == 0 else ""
            print(f"  [{i:3d}/{TOTAL_EVENTS}] {mock_payload['detected_type']:25s} {status}")

        except ConnectionRefusedError:
            print(f"  [{i:3d}/{TOTAL_EVENTS}] CONNECTION REFUSED — Is Gatekeeper running on {TARGET_PORT}?")
            failed += 1
        except socket.timeout:
            print(f"  [{i:3d}/{TOTAL_EVENTS}] TIMEOUT — Gatekeeper may be blocked")
            failed += 1
        except Exception as e:
            print(f"  [{i:3d}/{TOTAL_EVENTS}] ERROR: {e}")
            failed += 1

        time.sleep(INTERVAL_MS / 1000.0)

    print()
    print(f"[STRESS] Complete: {sent} sent, {failed} failed out of {TOTAL_EVENTS}")
    if failed == 0:
        print("[STRESS] ALL CLEAR — No thread blocking or connection drops detected")
    else:
        print(f"[STRESS] WARNING — {failed} failures detected, check Gatekeeper logs")


if __name__ == "__main__":
    stream_mock_data()
