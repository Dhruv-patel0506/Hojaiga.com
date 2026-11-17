"""
phase1_training_dataset -- builds the ML training set from the offline corpus.

Part of Hojaiga PART-2 Phase-1 (Offline Cognitive Training). It reads the
decomposed trajectory JSON under trajectories/TRAIN/ and flattens every step into
a model training sample (Intent -> step decomposition -> target element type ->
expected state delta). No apps are installed here; it is pure text/structural
learning, exactly as the blueprint specifies.

Leakage rule (the whole point of the app-level split): ONLY trajectories/TRAIN
feeds this builder. trajectories/EVAL is written to a separate Phase-2 queue and is
never mixed into training samples.

Output:
  brain/train_samples.jsonl   one JSON training sample per non-empty step
  brain/phase2_eval_queue.json apps/steps held for live validation (EVAL + anchors)
  brain/dataset_manifest.json honest counts + provenance

Usage:
  python phase1_training_dataset.py            # build from current TRAIN trajectories
  python phase1_training_dataset.py --summary   # just report counts
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path

TRAJ = Path(os.environ.get("HOJAIGA_TRAJ_DIR", "trajectories"))
BRAIN = Path(os.environ.get("HOJAIGA_BRAIN_DIR", "brain"))
TRAIN_DIR = TRAJ / "TRAIN"
EVAL_DIR = TRAJ / "EVAL"
ANCHORS = Path("anchor_apps.json")

VALID_ACTIONS = {"CLICK", "RIGHT_CLICK", "DOUBLE_CLICK", "HOVER", "DRAG_AND_DROP",
                 "CONTINUOUS_DRAG", "TYPE_TEXT", "KEY_COMBINATION"}


def log(m: str) -> None:
    print(f"[dataset] {m}", flush=True)


def is_target_grounded(ui: dict) -> bool:
    """A step is only trainable if it names a real widget the executor could later find.
    Offline samples legitimately carry NO coordinates (those are filled + verified in
    Phase 2), but a step whose ui_target has no element name / automation id / hierarchy
    path teaches the model to 'click nothing' -- that is noise, so we drop it."""
    ui = ui or {}
    return bool(ui.get("element_name") or ui.get("automation_id") or ui.get("hierarchical_path"))


def sample_from_step(app_key: str, doc: dict, step: dict, require_grounding: bool = True) -> dict | None:
    traj_action = step.get("virtual_mouse_action", {}) or {}
    atype = (traj_action.get("action_type") or "").upper()
    if atype not in VALID_ACTIONS:
        return None
    ui = step.get("ui_target", {}) or {}
    if require_grounding and not is_target_grounded(ui):
        return None
    inst = str(step.get("low_level_instruction", "")).strip()
    exp = str(step.get("expected_state_change", "")).strip()
    if not inst:
        return None
    sid = hashlib.sha1(f"{app_key}|{step.get('step_id')}|{inst}".encode()).hexdigest()[:16]
    return {
        "sample_id": sid,
        "app_key": app_key,
        "split": "TRAIN",
        "task": str(doc.get("high_level_task", "")).strip(),
        "prerequisite_state": str(doc.get("prerequisite_state", "")).strip(),
        "step_id": step.get("step_id"),
        "instruction": inst,
        "target_element_name": ui.get("element_name"),
        "target_element_type": ui.get("element_type"),
        "action_type": atype,
        "modifiers": traj_action.get("modifiers") or [],
        "has_coordinates": bool(traj_action.get("coordinates")),
        "expected_state_change": exp,
        # target is NAMED (grounded to a widget); coordinates are still filled + verified in Phase 2
        "target_named": True,
        "grounded": False,
        "verified": False,
        "source": "decompose_guides",
    }


def build(execute_summary_only: bool = False, require_grounding: bool = True) -> dict:
    files = sorted(glob.glob(str(TRAIN_DIR / "**" / "*.json"), recursive=True))
    samples = 0
    apps = set()
    per_action: Counter = Counter()
    skipped_empty = 0
    dropped_ungrounded = 0
    out_path = BRAIN / "train_samples.jsonl"
    BRAIN.mkdir(parents=True, exist_ok=True)

    if execute_summary_only:
        fh = None
    else:
        fh = out_path.open("w", encoding="utf-8")

    for f in files:
        try:
            doc = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            skipped_empty += 1
            continue
        app_key = doc.get("_meta", {}).get("app_key") or doc.get("app_metadata", {}).get("app_name", "")
        steps = doc.get("trajectory") or []
        got = 0
        for step in steps:
            ui = step.get("ui_target", {}) or {}
            traj_action = step.get("virtual_mouse_action", {}) or {}
            atype = (traj_action.get("action_type") or "").upper()
            if (require_grounding and atype in VALID_ACTIONS
                    and str(step.get("low_level_instruction", "")).strip()
                    and not is_target_grounded(ui)):
                dropped_ungrounded += 1
            s = sample_from_step(app_key, doc, step, require_grounding)
            if not s:
                continue
            got += 1
            per_action[s["action_type"]] += 1
            if fh:
                fh.write(json.dumps(s, ensure_ascii=False) + "\n")
        if got:
            apps.add(app_key)
            samples += got
        else:
            skipped_empty += 1
    if fh:
        fh.close()

    manifest = {
        "built": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "train_trajectory_files": len(files),
        "apps_with_samples": len(apps),
        "training_samples": samples,
        "trajectories_skipped_empty": skipped_empty,
        "dropped_ungrounded_steps": dropped_ungrounded,
        "grounding_filter": "ON (steps must name a target widget)" if require_grounding else "OFF",
        "action_distribution": dict(per_action),
        "leakage_note": "TRAIN-only; EVAL + anchors routed to Phase-2 eval queue, never into training.",
        "grounded": 0,
        "next": "run decompose_guides.py --full to populate the millions-row corpus, then rebuild.",
    }

    # Phase-2 eval queue: EVAL trajectories + curated anchors (kept separate from training).
    eval_files = sorted(glob.glob(str(EVAL_DIR / "**" / "*.json"), recursive=True))
    anchors = []
    if ANCHORS.exists():
        anchors = json.loads(ANCHORS.read_text(encoding="utf-8")).get("anchors", [])
    anchor_ids = [a["winget_id"] for a in anchors]
    n_eval = len(eval_files)
    n_anchors = len(anchor_ids)
    queue = {"created": manifest["built"],
             "eval_trajectory_files": n_eval,
             "anchor_apps": anchor_ids,
             "note": "install one at a time via autonomous_installer_engine, test via live_trajectory_executor, then uninstall."}
    (BRAIN / "phase2_eval_queue.json").write_text(json.dumps(queue, indent=3), encoding="utf-8")
    (BRAIN / "dataset_manifest.json").write_text(json.dumps(manifest, indent=3), encoding="utf-8")

    log(json.dumps(manifest, ensure_ascii=False, indent=3))
    log(f"EVAL queue: {n_eval} eval trajectory files, {n_anchors} anchors -> {BRAIN/'phase2_eval_queue.json'}")
    if not execute_summary_only:
        log(f"Wrote {samples} training samples -> {out_path}")
    return manifest


def main():
    p = argparse.ArgumentParser(description="Flatten TRAIN trajectories into ML training samples (Phase-1).")
    p.add_argument("--summary", action="store_true", help="report counts without writing samples")
    p.add_argument("--allow-ungrounded", action="store_true",
                   help="keep steps whose ui_target names no widget (default: drop them as noise)")
    args = p.parse_args()
    build(execute_summary_only=args.summary, require_grounding=not args.allow_ungrounded)


if __name__ == "__main__":
    main()
