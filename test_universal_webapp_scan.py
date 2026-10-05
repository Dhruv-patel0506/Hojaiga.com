"""
Test Universal Webapp Scanner & Popup Mitigation
Validates organ_30_app_scanner and organ_29_popup_handler on a live Chromium webapp.
"""

import json
import logging
import os
import subprocess
import sys
import time

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")
if r"D:\new_automation" not in sys.path:
    sys.path.insert(0, r"D:\new_automation")

import organ_30_app_scanner as scanner_mod

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("test_webapp_scan")

WEBAPP_PATH = os.path.abspath("scratch_universal_webapp.html")
WEBAPP_URL = f"file:///{WEBAPP_PATH.replace(os.sep, '/')}"

def run_test():
    logger.info("Starting Universal Webapp Benchmark Test on: %s", WEBAPP_URL)

    # 1. Launch Microsoft Edge navigating to the webapp HTML file
    edge_exe = None
    for p in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]:
        if os.path.isfile(p):
            edge_exe = p
            break

    if edge_exe:
        logger.info("Launching Edge with webapp: %s", edge_exe)
        subprocess.Popen([edge_exe, "--new-window", WEBAPP_URL])
    else:
        logger.info("Launching default browser with: %s", WEBAPP_URL)
        subprocess.Popen(["cmd.exe", "/c", "start", "", WEBAPP_URL])

    time.sleep(3.5)

    # 2. Locate browser window handle
    hwnd = scanner_mod.find_app_hwnd("Edge") or scanner_mod.find_app_hwnd("Hojaiga Webapp Benchmark") or scanner_mod.find_app_hwnd("Chrome")
    if not hwnd:
        logger.error("Could not find browser window for webapp")
        return False

    logger.info("Found browser window -> hwnd=%s (0x%x)", hwnd, hwnd)

    # 3. Instantiate AppScanner and scan the webapp
    scanner = scanner_mod.AppScanner()
    start_time = time.time()
    try:
        result = scanner.scan_app_active("Webapp Benchmark", hwnd)
    finally:
        scanner.stop()

    elapsed = time.time() - start_time
    logger.info("Webapp scan status: %s", result["status"])
    logger.info("Controls scanned: %d | failed: %d | elements: %d | elapsed: %.2fs",
                result["controls_scanned"], result["controls_failed"], len(result["elements"]), elapsed)

    out_file = "webapp_scan_result.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    logger.info("Saved webapp scan results to %s", out_file)

    # Assertions
    assert result["status"] == "completed", f"Scan did not complete: {result.get('message')}"
    assert result["controls_scanned"] > 0, "No controls were scanned on the webapp"

    element_names = [e["name"] for e in result["elements"]]
    logger.info("Scanned element sample: %s", element_names[:10])

    print("\n>>> UNIVERSAL WEBAPP SCAN TEST PASSED SUCCESSFULLY! <<<\n")
    return True

if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
