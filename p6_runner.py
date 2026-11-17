"""
p6_runner -- detached supervisor that drives the Phase-1 corpus run to 100% and then
auto-regenerates the data-science reports. Survives shell teardown (launched via
Start-Process) and OS sleep (decompose_guides now holds a SetThreadExecutionState wake
lock while it runs). If decompose is ever killed before writing the completion marker,
this relaunches it; decompose is cache-resumable, so a restart only spends model calls on
the guides not yet generated. When brain/phase1_run.json shows complete, it runs
ml_data_science_report.py + guide_intake_filter.py automatically.

Usage (normally launched detached):  python p6_runner.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

PY = sys.executable
ROOT = Path(__file__).resolve().parent
MARKER = ROOT / "brain" / "phase1_run.json"
LOG = ROOT / "_p6_runner.log"
MAX_RESTARTS = int(os.environ.get("P6_MAX_RESTARTS", "60"))

ENV = dict(os.environ)
ENV["HOJAIGA_GUIDES_XLSX"] = "app_guides_master.xlsx"
ENV["HOJAIGA_TRAJ_DIR"] = "trajectories"
ENV["HOJAIGA_BRAIN_DIR"] = "brain"


def log(m: str) -> None:
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(time.strftime("%Y-%m-%dT%H:%M:%SZ ") + m + "\n")


def complete() -> bool:
    try:
        return bool(json.loads(MARKER.read_text(encoding="utf-8")).get("complete"))
    except Exception:
        return False


def main() -> None:
    log("=== watchdog start ===")
    for i in range(1, MAX_RESTARTS + 1):
        if complete():
            log("completion marker already present; nothing to run")
            break
        log(f"launch decompose --full (attempt {i}/{MAX_RESTARTS})")
        r = subprocess.run([PY, "decompose_guides.py", "--full", "--engine", "ollama",
                            "--throttle-ms", "120"], cwd=str(ROOT), env=ENV)
        log(f"decompose exited code={r.returncode}")
        if complete():
            log("run reached completion")
            break
        time.sleep(8)   # brief backoff before resuming from cache

    if complete():
        log("post-run: regenerating data-science report + intake filter")
        subprocess.run([PY, "ml_data_science_report.py"], cwd=str(ROOT), env=ENV)
        subprocess.run([PY, "guide_intake_filter.py"], cwd=str(ROOT), env=ENV)
        log("post-run reports regenerated")
    else:
        log("exhausted restarts without completion marker")
    log("=== watchdog exit ===")


if __name__ == "__main__":
    main()
