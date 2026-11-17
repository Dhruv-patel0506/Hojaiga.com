"""
phase1_offline_training -- PHASE 1 (Offline Cognitive Training) orchestrator.

Runs the whole no-app, text-only knowledge pipeline end to end:

  1. ensure the app-level Dataset_Split manifest exists   (decompose_guides --assign-split)
  2. decompose the corpus guides -> trajectory JSON with the resident Ollama text
     model, resumable + throttled (Gap 1)                (decompose_guides --full ...)
  3. flatten trajectories/TRAIN -> ML training samples, EVAL + anchors held out
     in the Phase-2 queue, zero leakage                  (phase1_training_dataset.py)

HONESTY NOTE ON "TRAINING THE MODEL": this phase produces the offline dataset
(brain/train_samples.jsonl) that conditions the reasoning brain through retrieval /
few-shot prompting -- the "knowledge layer" in the blueprint. It does NOT run a
gradient fine-tune; no trainable-weights stage is wired into this repo yet. If and
when one is added, pass --fine-tune-hook "<cmd>" and it is invoked at the very end
with the sample file path appended. Nothing here fakes a training run.

Safety: purely text ingestion -- touches no windows, installs nothing, mutates no OS
state. The multi-hour --full pass is OFF by default; a bounded pilot batch runs
unless you explicitly ask for --full (pilot-first law).

Usage
-----
  python phase1_offline_training.py                     # bounded pilot batch (safe default)
  python phase1_offline_training.py --pilot 10 --throttle-ms 120
  python phase1_offline_training.py --full              # the multi-hour 6,711-guide pass
  python phase1_offline_training.py --dataset-only      # just rebuild samples from current trajectories
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
BRAIN = HERE / "brain"
RUN_MANIFEST = BRAIN / "phase1_run.json"


def log(m: str) -> None:
    print(f"[phase1] {m}", flush=True)


def _step(cmd: list, label: str, dry_run: bool) -> int:
    """Run one pipeline stage, streaming its output; returns the exit code."""
    log(f"-- {label}: {' '.join(cmd[1:])}")
    if dry_run:
        return 0
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(HERE))
    log(f"-- {label} exited rc={proc.returncode} in {round(time.time()-t0,1)}s")
    return proc.returncode


def ensure_split(dry_run: bool) -> int:
    return _step([PY, "decompose_guides.py", "--assign-split"],
                 "ensure Dataset_Split", dry_run)


def decompose(args, dry_run: bool) -> int:
    if args.dataset_only:
        log("-- decompose skipped (--dataset-only)")
        return 0
    cmd = [PY, "decompose_guides.py", "--engine", "ollama",
           "--throttle-ms", str(args.throttle_ms)]
    if args.full:
        cmd.append("--full")
    elif args.apps:
        cmd += ["--apps", args.apps]
    else:
        cmd += ["--pilot", str(args.pilot)]
    if args.force:
        cmd.append("--force")
    return _step(cmd, "decompose corpus", dry_run)


def build_dataset(dry_run: bool) -> int:
    return _step([PY, "phase1_training_dataset.py"], "flatten TRAIN -> samples", dry_run)


def fine_tune_hook(args, dry_run: bool) -> int:
    if not args.fine_tune_hook:
        log("-- no --fine-tune-hook given: dataset synthesis IS the training artifact here")
        return 0
    samples = str(BRAIN / "train_samples.jsonl")
    return _step([args.fine_tune_hook, samples], "fine-tune (external)", dry_run)


def load_dataset_counts() -> dict:
    try:
        return json.loads((BRAIN / "dataset_manifest.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    p = argparse.ArgumentParser(description="Phase-1 offline cognitive training pipeline (text-only, resumable, throttled).")
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--pilot", type=int, default=5, help="bounded pilot batch size (default, safe)")
    scope.add_argument("--full", action="store_true", help="decompose the ENTIRE corpus (multi-hour; explicit opt-in)")
    scope.add_argument("--dataset-only", action="store_true", help="skip decomposition, only rebuild samples")
    p.add_argument("--apps", default="", help="comma-separated app names to decompose (bounded)")
    p.add_argument("--throttle-ms", type=int, default=100, help="ms sleep after each inference call (Gap 1)")
    p.add_argument("--force", action="store_true", help="regenerate even if output JSON exists")
    p.add_argument("--dry-run", action="store_true", help="print the pipeline plan without running it")
    p.add_argument("--fine-tune-hook", default="", help="external command to run a real gradient fine-tune on train_samples.jsonl")
    args = p.parse_args()

    BRAIN.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    stages = {}
    stages["ensure_split"] = ensure_split(args.dry_run)
    stages["decompose"] = decompose(args, args.dry_run)
    stages["build_dataset"] = build_dataset(args.dry_run)
    stages["fine_tune"] = fine_tune_hook(args, args.dry_run)

    counts = load_dataset_counts()
    run = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": "full" if args.full else ("dataset-only" if args.dataset_only else ("apps" if args.apps else f"pilot{args.pilot}")),
        "throttle_ms": args.throttle_ms,
        "dry_run": args.dry_run,
        "stage_exit_codes": stages,
        "training_mode": "dataset_synthesis (retrieval/few-shot conditioning; NO gradient fine-tune wired)",
        "fine_tune_hook": args.fine_tune_hook or None,
        "dataset_manifest": counts,
        "wall_s": round(time.time() - t0, 1),
    }
    if not args.dry_run:
        RUN_MANIFEST.write_text(json.dumps(run, indent=3), encoding="utf-8")
    log(json.dumps({k: run[k] for k in ("scope", "stage_exit_codes", "training_mode", "wall_s")}, ensure_ascii=False))
    log(f"samples now: training_samples={counts.get('training_samples', '?')} "
        f"apps={counts.get('apps_with_samples', '?')} (see {BRAIN/'dataset_manifest.json'})")
    ok = all(v == 0 for v in stages.values())
    log("PHASE 1 " + ("OK" if ok else "had failures (see stage_exit_codes)"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
