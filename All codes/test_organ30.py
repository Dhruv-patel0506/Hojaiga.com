"""
Verification Test Script for AppScannerOrgan
Target: Running instance of OBS Studio
"""

import os
import sys
import json
import time
import logging
import win32gui
import win32process

# Configure verbose console logging to monitor real-time clicks
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("test_obs_scanner")

sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs.organ_30_app_scanner import AppScannerOrgan


def find_obs_hwnd() -> int:
    """Locates the top-level window handle for OBS Studio."""
    found_hwnds = []

    def enum_cb(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if "OBS" in title and ("Profile:" in title or "Scenes:" in title or "OBS Studio" in title):
                extra.append((hwnd, title))
        return True

    win32gui.EnumWindows(enum_cb, found_hwnds)
    if not found_hwnds:
        return 0

    # Pick the main workspace window
    hwnd, title = found_hwnds[0]
    logger.info("Found target OBS window: HWND=%s | Title='%s'", hwnd, title)
    return hwnd


def run_verification():
    hwnd = find_obs_hwnd()
    if not hwnd:
        logger.error("OBS Studio is not running. Launch OBS 64-bit and re-run.")
        sys.exit(1)

    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    logger.info("Process ID: %d | Starting physical test in 3 seconds...", pid)
    time.sleep(3.0)

    scanner = AppScannerOrgan(force=True)
    result = scanner.scan_app_active("OBS Studio", hwnd)

    print("\n" + "=" * 60)
    print("SCAN EXECUTION SUMMARY")
    print("=" * 60)
    print(f"Status:            {result.get('status')}")
    print(f"Tree Signature:    {result.get('tree_hash')}")
    print(f"Controls Scanned:  {result.get('controls_scanned')}")
    print(f"Controls Failed:   {result.get('controls_failed')}")
    print("=" * 60)

    elements = result.get("elements", [])
    print(f"\nTotal Mapped Elements with Coordinates: {len(elements)}")

    if elements:
        print("\nSample of Mapped Elements (First 15):")
        print(f"{'Type':<20} | {'Center (X, Y)':<16} | {'Name'}")
        print("-" * 65)
        for el in elements[:15]:
            center_str = f"({el['coords']['x']}, {el['coords']['y']})"
            print(f"{el['type']:<20} | {center_str:<16} | {el['name']}")

    # Save output for verification
    output_path = r"D:\new_automation\All codes\obs_scan_result.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\nFull scan data written to {output_path}")


if __name__ == "__main__":
    run_verification()
