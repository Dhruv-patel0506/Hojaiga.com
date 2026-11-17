"""
phase2_live_validation -- PHASE 2 (Dynamic Live Validation / JIT Ephemeral) orchestrator.

Runs the blueprint's one-app-at-a-time loop over the curated Anchor suite so the
machine never accumulates thousands of installs:

    install -> launch (minimized/background) -> execute its EVAL trajectory through
    live_trajectory_executor -> verify (deep UIA differential) -> uninstall -> reset

Everything is GATED behind the 20 Anchor Apps in brain/phase2_eval_queue.json (never an
open-ended --execute across arbitrary packages). A trajectory is required and comes from
the held-out EVAL split; if the corpus has not been decomposed for that app yet, the app
is honestly SKIPPED (no fabricated test).

Safety (repo law: no destructive surprises, pilot-first):
  * DEFAULT IS PLAN-ONLY. Nothing is installed or launched. The plan shows the exact
    per-app sequence and whether a trajectory/launch command exist.
  * Real mutation needs BOTH --execute AND --yes. Even then it goes one app at a time
    and always attempts the cached uninstall afterward.
  * Delegates to the hardened organs only -- the installer engine and the live executor.
    No physical cursor, minimized windows use UIA patterns (see live_trajectory_executor).

Usage
-----
  python phase2_live_validation.py                         # PLAN the whole anchor queue
  python phase2_live_validation.py --only GIMP.GIMP        # plan one anchor
  python phase2_live_validation.py --execute --yes         # actually run the JIT loop (opt-in)
"""

from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
BRAIN = HERE / "brain"
QUEUE = BRAIN / "phase2_eval_queue.json"
ANCHORS = HERE / "anchor_apps.json"
EVAL_DIR = HERE / "trajectories" / "EVAL"
RESULT_LOG = BRAIN / "phase2_results.jsonl"


def log(m: str) -> None:
    print(f"[phase2] {m}", flush=True)


def load_queue_ids() -> list:
    try:
        return json.loads(QUEUE.read_text(encoding="utf-8")).get("anchor_apps", [])
    except Exception:
        return []


def load_anchor_meta() -> dict:
    """winget_id -> {name, launch, framework} for richer per-app planning."""
    try:
        meta = {a["winget_id"]: a for a in json.loads(ANCHORS.read_text(encoding="utf-8")).get("anchors", [])}
    except Exception:
        meta = {}
    for a in meta.values():
        a.setdefault("launch", "")
    return meta


def _tokens(s: str) -> set:
    import re
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2}


def find_eval_trajectory(name: str, winget_id: str) -> str | None:
    """Locate an EVAL-split trajectory JSON whose app_key/label overlaps this anchor."""
    want = _tokens(name) | _tokens(winget_id.split(".")[-2] if winget_id.count(".") >= 2 else winget_id)
    files = glob.glob(str(EVAL_DIR / "**" / "*.json"), recursive=True)
    for f in files:
        key_tokens = _tokens(Path(f).parent.name) | _tokens(Path(f).stem)
        if key_tokens & want:
            return f
    return None


def _run(cmd: list, timeout: int) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=str(HERE), shell=False, capture_output=True, text=True, timeout=timeout)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as exc:
        return -1, f"{type(exc).__name__}: {str(exc)[:120]}"


def validate_one(winget_id: str, meta: dict, execute: bool) -> dict:
    name = meta.get("app_name") or meta.get("name") or winget_id
    launch = meta.get("launch_command") or meta.get("launch") or ""
    title_rx = meta.get("window_title_regex") or ""
    traj = find_eval_trajectory(name, winget_id)
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "winget_id": winget_id, "name": name,
           "mode": "EXECUTE" if execute else "PLAN", "trajectory": traj,
           "launch": launch or None, "window_title_regex": title_rx or None}

    if not execute:
        # Plan: report readiness without touching the machine.
        steps = ["1: autonomous_installer_engine --plan -> confirm resolvable",
                 "2: autonomous_installer_engine --execute --yes -> silent install (GUI-wizard fallback)"]
        steps.append("3: launch via launch_command, bind window by title regex (no focus steal)") if launch else \
            steps.append("3: LAUNCH COMMAND UNSET -> add \"launch_command\" to anchor_apps.json for this app")
        steps.append("4: live_trajectory_executor --traj <EVAL traj> --title <name> -> deep-UIA verify + screenshot proof"
                     if traj else "4: NO EVAL TRAJECTORY for this app yet -> skip (decompose EVAL corpus first)")
        steps.append("5: autonomous_installer_engine --uninstall-cached --yes -> clean up + state reset")
        rec["status"] = "PLANNED" if traj and launch else "PLANNED_WITH_GAPS"
        rec["sequence"] = steps
        return rec

    # Execute (opt-in): install -> launch -> run -> uninstall. One app at a time.
    rc, out = _run([PY, "autonomous_installer_engine.py", "--execute", winget_id, "--yes"], timeout=1200)
    rec["install_rc"] = rc
    rec["install_note"] = out[-200:]
    if launch:
        rc, out = _run(["cmd", "/c", "start", ""] + launch.split(), timeout=60)
        rec["launch_rc"] = rc
        time.sleep(3.0)  # let the window settle
    if traj:
        rc, out = _run([PY, "live_trajectory_executor.py", "--traj", traj, "--title", name, "--proof"], timeout=300)
        rec["exec_rc"] = rc
        rec["exec_note"] = out[-300:]
    rc, out = _run([PY, "autonomous_installer_engine.py", "--uninstall-cached", winget_id, "--yes"], timeout=400)
    rec["uninstall_rc"] = rc
    rec["status"] = "RAN"
    return rec


def main():
    p = argparse.ArgumentParser(description="Phase-2 JIT ephemeral live validation over the anchor suite (plan-only by default).")
    p.add_argument("--only", default="", help="restrict to one winget_id")
    p.add_argument("--limit", type=int, default=0, help="process at most N anchors this run")
    p.add_argument("--execute", action="store_true", help="actually install/launch/test/uninstall (destructive)")
    p.add_argument("--yes", action="store_true", help="required alongside --execute to confirm mutation")
    args = p.parse_args()

    if args.execute and not args.yes:
        log("--execute requires --yes (this installs and uninstalls software). Aborted; nothing changed.")
        sys.exit(1)

    ids = [args.only] if args.only else load_queue_ids()
    if args.limit:
        ids = ids[:args.limit]
    meta = load_anchor_meta()
    log(f"anchor queue: {len(ids)} app(s); mode={'EXECUTE' if args.execute else 'PLAN'}")

    RESULT_LOG.parent.mkdir(parents=True, exist_ok=True)
    planned_with_traj = 0
    for wid in ids:
        rec = validate_one(wid, meta.get(wid, {}), args.execute)
        if rec.get("trajectory"):
            planned_with_traj += 1
        with RESULT_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        gap = "" if (rec.get("trajectory") and rec.get("launch")) else "  [gap]"
        log(f"  {wid:35s} {rec['status']}{gap} traj={'Y' if rec.get('trajectory') else 'N'} "
            f"launch={'Y' if rec.get('launch') else 'N'}")

    log(f"planned {len(ids)} anchors; {planned_with_traj} have a matching EVAL trajectory ready to run live")
    if not args.execute:
        log("PLAN mode: pass --execute --yes to run the JIT install/test/uninstall loop per anchor.")


if __name__ == "__main__":
    main()
