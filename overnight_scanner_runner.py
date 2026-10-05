"""
Hojaiga Automation OS — Autonomous Overnight Scanner Runner
Continuously scans desktop applications (OBS Studio, Notepad, Webapps, Calculator)
with full deep active probing on all controls, popup mitigation through Organ 29
via CNS Bridge, and real-time validation through Brain Gatekeeper on port 11435.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional

# Ensure workspace paths are accessible
WORKSPACE_ROOT = r"D:\new_automation"
ALL_CODES = r"D:\new_automation\All codes"

for p in (WORKSPACE_ROOT, ALL_CODES):
    if p not in sys.path:
        sys.path.insert(0, p)

# Configure logging
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(WORKSPACE_ROOT, "overnight_scanner.log"), mode="a", encoding="utf-8")
    ]
)
logger = logging.getLogger("overnight_runner")

# Target Apps Specification (Universal Multi-Framework Benchmark Suite)
BENCHMARK_TARGETS = [
    {
        "name": "Notepad",
        "exe": r"C:\Windows\System32\notepad.exe",
        "description": "WinUI 3 / XAML modern multi-tab editor benchmark",
    },
    {
        "name": "Calculator",
        "exe": r"C:\Windows\System32\calc.exe",
        "description": "WinUI 3 / XAML rich button calculation grid benchmark",
    },
    {
        "name": "OpenCode",
        "exe": None,
        "description": "Electron desktop development environment benchmark",
    },
    {
        "name": "WhatsApp",
        "exe": None,
        "description": "React Native / Electron desktop messaging benchmark with in-window dialogs",
    },
    {
        "name": "Webapp Benchmark",
        "exe": None,
        "url": os.path.join(WORKSPACE_ROOT, "scratch_universal_webapp.html"),
        "description": "Chromium HTML DOM crawler benchmark with in-window dialogs & cookie banner",
    },
    {
        "name": "OBS Studio",
        "exe": r"D:\obs-studio\bin\64bit\obs64.exe",
        "description": "Qt6 Multi-Dock desktop benchmark with keyboard accelerators",
    },
]

GATEKEEPER_PORT = 11435
GATEKEEPER_SECRET = "339680"
ORGAN29_PORT = 11436


def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    """Checks if a TCP socket is actively listening on host:port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def verify_gatekeeper() -> bool:
    """Ensures Brain_Gatekeeper is running on port 11435."""
    if not is_port_open(GATEKEEPER_PORT):
        logger.warning("[WATCHDOG] Gatekeeper offline on port %d. Starting daemon...", GATEKEEPER_PORT)
        gatekeeper_script = os.path.join(WORKSPACE_ROOT, "Brain_Gatekeeper.py")
        subprocess.Popen(
            [sys.executable, gatekeeper_script],
            cwd=WORKSPACE_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        for _ in range(15):
            time.sleep(0.5)
            if is_port_open(GATEKEEPER_PORT):
                break

    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{GATEKEEPER_PORT}/api/tags",
            headers={"X-Hojaiga-Validation": GATEKEEPER_SECRET}
        )
        resp = urllib.request.urlopen(req, timeout=3.0)
        logger.info("[WATCHDOG] Gatekeeper verified online on port %d (HTTP %d)",
                    GATEKEEPER_PORT, resp.getcode())
        return True
    except Exception as e:
        logger.error("[WATCHDOG] Gatekeeper health check failed: %s", e)
        return False


def verify_organ_29() -> bool:
    """Ensures Organ 29 (DesktopInteractionManager) is listening on port 11436."""
    if not is_port_open(ORGAN29_PORT):
        logger.warning("[WATCHDOG] Organ 29 offline on port %d. Starting HostAgent daemon...", ORGAN29_PORT)
        organ29_script = os.path.join(ALL_CODES, "core_organs", "organ_29_popup_handler.py")
        subprocess.Popen(
            [sys.executable, organ29_script],
            cwd=WORKSPACE_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        for _ in range(15):
            time.sleep(0.5)
            if is_port_open(ORGAN29_PORT):
                break

    online = is_port_open(ORGAN29_PORT)
    logger.info("[WATCHDOG] Organ 29 HostAgent listener verified on port %d: %s", ORGAN29_PORT, online)
    return online


def run_single_scan(target_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Runs a single deep scan against the target app or webapp."""
    app_name = target_spec["name"]
    exe_path = target_spec.get("exe")
    url = target_spec.get("url")

    logger.info("==================================================")
    logger.info("  STARTING SCAN PASS: %s", app_name)
    logger.info("==================================================")

    import organ_30_app_scanner as scanner_mod

    # 1. Ensure target application is running
    hwnd = None
    if url:
        browser_exe = None
        for p in [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]:
            if os.path.isfile(p):
                browser_exe = p
                break
        url_formatted = url if url.startswith("http") else f"file:///{os.path.abspath(url).replace(os.sep, '/')}"
        if browser_exe:
            subprocess.Popen([browser_exe, "--new-window", url_formatted])
        else:
            subprocess.Popen(["cmd.exe", "/c", "start", "", url_formatted])
        time.sleep(3.5)
        hwnd = (
            scanner_mod.find_app_hwnd("Universal Webapp")
            or scanner_mod.find_app_hwnd("Benchmark")
            or scanner_mod.find_app_hwnd("Hojaiga")
            or scanner_mod.find_app_hwnd("Chrome")
            or scanner_mod.find_app_hwnd("Edge")
        )
    else:
        hwnd = scanner_mod.find_app_hwnd(app_name)
        if not hwnd and exe_path:
            hwnd = scanner_mod.ensure_app_running(app_name, exe_path=exe_path)

    if not hwnd:
        logger.warning("[SKIP] Target app '%s' window not currently available. Proceeding to next target.", app_name)
        return {"status": "skipped", "message": f"App '{app_name}' window not found"}

    # 2. Instantiate AppScanner with AppAgent CNS connection
    scanner = scanner_mod.AppScanner()
    start_time = time.time()
    try:
        result = scanner.scan_app_active(app_name, hwnd)
    finally:
        scanner.stop()

    elapsed = time.time() - start_time
    result["elapsed_seconds"] = round(elapsed, 2)
    result["scanned_at"] = datetime.datetime.now().isoformat()

    logger.info("Scan completed for '%s': %d controls scanned, %d failed, hash=%s (%.2fs)",
                app_name, result.get("controls_scanned", 0),
                result.get("controls_failed", 0), result.get("tree_hash", ""), elapsed)

    # 3. Save JSON artifacts
    results_dir = os.path.join(WORKSPACE_ROOT, "overnight_results")
    os.makedirs(results_dir, exist_ok=True)

    safe_name = re.sub(r"[^\w\-]", "_", app_name.lower()).strip("_")
    latest_file = os.path.join(WORKSPACE_ROOT, f"{safe_name}_deep_scan_result.json")
    history_file = os.path.join(results_dir, f"{safe_name}_{int(time.time())}.json")

    for fpath in (latest_file, history_file):
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        except Exception as write_err:
            logger.warning("Could not write result file %s: %s", fpath, write_err)

    return result


def main_overnight_loop(max_cycles: Optional[int] = None, delay_between_apps: float = 8.0):
    """Main continuous overnight runner loop."""
    logger.info("************************************************************")
    logger.info("  HOJAIGA AUTOMATION OS — OVERNIGHT SCANNER ACTIVE")
    logger.info("  Autonomous Deep Clicking & CNS Popup Mitigation Mode")
    logger.info("************************************************************")

    # Initial daemon check
    verify_gatekeeper()
    verify_organ_29()

    status_file = os.path.join(WORKSPACE_ROOT, "overnight_status.json")
    cycle = 0
    total_controls_all_time = 0

    while True:
        cycle += 1
        logger.info("\n>>> STARTING OVERNIGHT SCAN CYCLE #%d at %s <<<",
                    cycle, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # Verify daemons are still alive before each cycle
        verify_gatekeeper()
        verify_organ_29()

        cycle_controls = 0
        cycle_results = {}

        for target in BENCHMARK_TARGETS:
            try:
                res = run_single_scan(target)
                controls_count = res.get("controls_scanned", 0)
                cycle_controls += controls_count
                total_controls_all_time += controls_count
                cycle_results[target["name"]] = {
                    "status": res.get("status"),
                    "controls_scanned": controls_count,
                    "controls_failed": res.get("controls_failed", 0),
                    "tree_hash": res.get("tree_hash", ""),
                    "elapsed_seconds": res.get("elapsed_seconds", 0),
                }
            except Exception as e:
                logger.error("Scan exception for target '%s': %s", target["name"], e, exc_info=True)
                cycle_results[target["name"]] = {"status": "error", "error": str(e)}

            time.sleep(delay_between_apps)

        # Write cycle status
        status_payload = {
            "last_cycle": cycle,
            "last_cycle_time": datetime.datetime.now().isoformat(),
            "total_controls_all_time": total_controls_all_time,
            "gatekeeper_online": is_port_open(GATEKEEPER_PORT),
            "organ_29_online": is_port_open(ORGAN29_PORT),
            "cycle_results": cycle_results,
        }
        try:
            with open(status_file, "w", encoding="utf-8") as sf:
                json.dump(status_payload, sf, indent=2)
        except Exception:
            pass

        logger.info("Cycle #%d completed: %d controls probed. Total scanned: %d",
                    cycle, cycle_controls, total_controls_all_time)

        if max_cycles and cycle >= max_cycles:
            logger.info("Reached maximum requested cycles (%d). Stopping.", max_cycles)
            break

        logger.info("Resting 15 seconds before next overnight cycle...")
        time.sleep(15.0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hojaiga Autonomous Overnight Scanner Runner")
    parser.add_argument("--cycles", type=int, default=None, help="Maximum number of cycles (default: unlimited)")
    parser.add_argument("--delay", type=float, default=8.0, help="Delay in seconds between applications")
    args = parser.parse_args()

    try:
        main_overnight_loop(max_cycles=args.cycles, delay_between_apps=args.delay)
    except KeyboardInterrupt:
        logger.info("Overnight scanner stopped by user.")
