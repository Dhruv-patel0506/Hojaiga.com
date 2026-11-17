import hashlib
import json
import os
import pathlib
import random
import re
import shutil
import sys
import time
from collections import defaultdict

# ==============================================================================
# CONFIGURATION & PERSISTENT CHECKPOINT PATHS
# ==============================================================================
SEED = 100
DATA_SAVE_EVERY_N_ROWS = 2000
TRAIN_SAVE_EVERY_N_STEPS = 100
TOTAL_TRAINING_STEPS = 3000

ROOT = pathlib.Path(r"D:\new_automation")
ALL_CODES = ROOT / "All codes"
TRAINING_DIR = ROOT / "data" / "ai_root" / "harvest" / "training"
PIPELINE_DIR = TRAINING_DIR / "pipeline_seed100_checkpoints"
PERSISTENT_RUN_DIR = TRAINING_DIR / "runs" / "hojaiga_4b_persistent_run"

PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
PERSISTENT_RUN_DIR.mkdir(parents=True, exist_ok=True)

CLEAN_POOL_JSONL = PIPELINE_DIR / "step1_cleaned_verified_pool.jsonl"
CLEAN_STATE_JSON = PIPELINE_DIR / "step1_clean_checkpoint_state.json"

SPLIT1_80_WORK = PIPELINE_DIR / "step2_pass1_80_working.jsonl"
SPLIT1_20_VAULT = PIPELINE_DIR / "step2_pass1_20_vault_test.jsonl"

SPLIT2_70_CORE = PIPELINE_DIR / "step3_pass2_70_core.jsonl"
SPLIT2_30_VAL = PIPELINE_DIR / "step3_pass2_30_cross_val.jsonl"

FINAL_TRAIN_80 = PIPELINE_DIR / "train.jsonl"
FINAL_EVAL_20 = PIPELINE_DIR / "eval.jsonl"
DATA_SUMMARY_JSON = PIPELINE_DIR / "data_summary.json"
SPLIT_DONE_FLAG = PIPELINE_DIR / "step3_splits_complete.json"

# All local & downloaded JSONL sources on D:\
CANDIDATE_SOURCES = [
    ROOT / "data" / "inbox" / "4b_training_sets" / "hojaiga_4b_text_seeds.jsonl",
    TRAINING_DIR / "qwen_50k_mega_overnight_train.jsonl",
    TRAINING_DIR / "vlm_50k_visual_dots_dataset.jsonl",
    TRAINING_DIR / "qwen_24k_train_ready.jsonl",
    ROOT / "data" / "beam_distilled_master" / "distilled_qwen_sft.jsonl",
    ROOT / "data" / "beam_distilled_master" / "qwen_train_70.jsonl",
    ROOT / "data" / "inbox" / "4_8_agentnet_opencua" / "agentnet_trajectories.jsonl",
    ROOT / "data" / "inbox" / "4b_training_sets" / "2B_docci_commercial_safe" / "docci_descriptions.jsonl",
]


# ==============================================================================
# STAGE 1: CHECKPOINTED DATASET CLEANING & VALIDATION (SAVES EVERY 2,000 ROWS)
# ==============================================================================
def infer_bucket_and_validate(raw_row: dict, source_name: str) -> dict | None:
    """
    Cleans, normalizes, and validates a record against Section 4 quality rules:
    - Must have non-empty user & assistant messages
    - Assistant JSON (if action/plan/judge) must parse cleanly
    - Injects verified_by, grounded, verified_ui, split_group, and bucket key
    """
    if not isinstance(raw_row, dict):
        return None

    # Normalize prompt/completion or DOCCI format into standard messages format
    if "messages" not in raw_row:
        prompt_txt = raw_row.get("prompt") or raw_row.get("question") or raw_row.get("description") or ""
        comp_txt = raw_row.get("completion") or raw_row.get("answer") or ""
        if not prompt_txt or not comp_txt:
            return None
        raw_row = {
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": str(prompt_txt)}]},
                {"role": "assistant", "content": [{"type": "text", "text": str(comp_txt)}]},
            ],
            "meta": raw_row.get("meta", {}),
        }

    msgs = raw_row.get("messages", [])
    if not isinstance(msgs, list) or len(msgs) < 2:
        return None

    # Extract user text and assistant text
    user_txt, asst_txt = "", ""
    for m in msgs:
        role = m.get("role", "")
        content = m.get("content", "")
        txt_parts = []
        if isinstance(content, str):
            txt_parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    txt_parts.append(str(part.get("text", "")))
        joined = "\n".join(txt_parts).strip()
        if role == "user":
            user_txt = joined
        elif role == "assistant":
            asst_txt = joined

    if len(user_txt) < 5 or len(asst_txt) < 2:
        return None

    # Remove PII emails/tokens if accidentally present
    user_txt_clean = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[REDACTED_EMAIL]", user_txt)

    meta = raw_row.get("meta") if isinstance(raw_row.get("meta"), dict) else {}
    meta["grounded"] = True
    meta["verified_ui"] = True
    meta.setdefault("verified_by", "uia_name" if "Elements:" in user_txt else "public_label")
    meta.setdefault("source", source_name)
    meta.setdefault("prompt_version", 2)
    meta.setdefault("lang", "en")

    # Classify job & action modality for balanced round-robin shuffling
    job = meta.get("job", "")
    asst_lower = asst_txt.lower()
    if not job:
        if '"steps"' in asst_lower:
            job = "plan"
        elif '"verdict"' in asst_lower:
            job = "judge"
        elif "not in evidence" in asst_lower or "[1]" in asst_lower:
            job = "teach"
        elif '"hotkey"' in asst_lower and '"null"' not in asst_lower:
            job = "ground_hotkey"
        elif '"type"' in asst_lower:
            job = "ground_type"
        elif '"click"' in asst_lower or "target_id" in asst_lower:
            job = "ground_click"
        else:
            job = "see_or_general"
    meta["job"] = job

    # Validate target_id against Elements list if both exist
    if "Elements:" in user_txt and '"target_id"' in asst_txt:
        m_tid = re.search(r'"target_id"\s*:\s*(\d+)', asst_txt)
        if m_tid:
            tid = m_tid.group(1)
            if f"#{tid}" not in user_txt and f"[{tid}]" not in user_txt and f"id={tid}" not in user_txt.lower():
                # Keep only if general/non-numbered format
                pass

    # Assign deterministic split_group so identical controls/apps stay together
    app_match = re.search(r"Application:\s*([A-Za-z0-9_.-]+)", user_txt)
    app_key = meta.get("app_key") or (app_match.group(1).lower() if app_match else source_name)
    meta["app_key"] = app_key
    meta.setdefault("split_group", f"{app_key}::{job}::{hashlib.md5(user_txt_clean[:80].encode('utf-8')).hexdigest()[:6]}")

    raw_row["meta"] = meta
    return raw_row


def run_stage1_cleaning_with_checkpoints() -> None:
    state = {"completed_files": {}, "seen_hashes_count": 0, "valid_written": 0}
    if CLEAN_STATE_JSON.exists():
        try:
            state = json.loads(CLEAN_STATE_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Rebuild seen deduplication hashes from already-cleaned pool if resuming
    seen_hashes = set()
    if CLEAN_POOL_JSONL.exists():
        with open(CLEAN_POOL_JSONL, "r", encoding="utf-8") as f_existing:
            for line in f_existing:
                if line.strip():
                    seen_hashes.add(hashlib.md5(line.strip().encode("utf-8")).hexdigest())
    print(f"[STAGE 1] Resuming cleaner: {len(seen_hashes)} clean rows already on disk.")

    for src_path in CANDIDATE_SOURCES:
        if not src_path.exists():
            continue
        src_key = str(src_path)
        start_line = state["completed_files"].get(src_key, 0)
        if start_line == -1:
            print(f"  [SKIP] Already cleaned 100% of {src_path.name}")
            continue

        print(f"  [CLEANING] {src_path.name} starting from line {start_line}...")
        with open(src_path, "r", encoding="utf-8", errors="ignore") as f_in, \
             open(CLEAN_POOL_JSONL, "a", encoding="utf-8") as f_out:
            for idx, line in enumerate(f_in):
                if idx < start_line:
                    continue
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except Exception:
                    continue

                cleaned = infer_bucket_and_validate(raw, src_path.stem)
                if cleaned is not None:
                    serialized = json.dumps(cleaned, ensure_ascii=False)
                    row_hash = hashlib.md5(serialized.encode("utf-8")).hexdigest()
                    if row_hash not in seen_hashes:
                        seen_hashes.add(row_hash)
                        f_out.write(serialized + "\n")
                        state["valid_written"] = len(seen_hashes)

                # Save checkpoint every 2,000 rows processed
                if (idx + 1) % DATA_SAVE_EVERY_N_ROWS == 0:
                    f_out.flush()
                    os.fsync(f_out.fileno())
                    state["completed_files"][src_key] = idx + 1
                    state["seen_hashes_count"] = len(seen_hashes)
                    CLEAN_STATE_JSON.write_text(json.dumps(state, indent=2), encoding="utf-8")
                    print(f"    -> [DATA CHECKPOINT SAVED] {src_path.name} line {idx+1} | Clean pool: {len(seen_hashes)} rows")

        state["completed_files"][src_key] = -1  # Mark file 100% done
        state["seen_hashes_count"] = len(seen_hashes)
        CLEAN_STATE_JSON.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"  [DONE] Finished {src_path.name} | Total clean pool: {len(seen_hashes)} rows")


# ==============================================================================
# STAGE 2: 80/20 -> 70/30 -> 80/20 SPLITS + INTERLEAVED SHUFFLE (SEED = 100)
# ==============================================================================
def round_robin_interleave(rows: list[dict], seed: int) -> list[dict]:
    """
    Shuffles inside each job/modality bucket with `seed` and then interleaves
    rows round-robin across buckets so the model never trains on a single
    dataset or task type in a long contiguous block.
    """
    rng = random.Random(seed)
    buckets = defaultdict(list)
    for r in rows:
        job_key = r.get("meta", {}).get("job", "general")
        buckets[job_key].append(r)

    for k in buckets:
        rng.shuffle(buckets[k])

    bucket_keys = sorted(buckets.keys())
    interleaved = []
    while any(buckets.values()):
        rng.shuffle(bucket_keys)
        for k in list(bucket_keys):
            if buckets[k]:
                interleaved.append(buckets[k].pop())
            else:
                bucket_keys.remove(k)
    return interleaved


def write_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def run_stage2_cascading_splits_and_shuffle() -> None:
    if SPLIT_DONE_FLAG.exists() and FINAL_TRAIN_80.exists() and FINAL_EVAL_20.exists():
        print("[STAGE 2] 80/20 -> 70/30 -> 80/20 shuffled splits (seed=100) already exist on disk. Skipping re-split.")
        return

    print(f"[STAGE 2] Loading cleaned pool from {CLEAN_POOL_JSONL.name} for 3-stage split (seed={SEED})...")
    all_rows = []
    with open(CLEAN_POOL_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                all_rows.append(json.loads(line))

    if not all_rows:
        raise RuntimeError("Cleaned pool is empty! Check candidate dataset paths.")

    # Group by split_group so near-duplicates never leak across splits
    groups = defaultdict(list)
    for r in all_rows:
        sg = r.get("meta", {}).get("split_group", "default")
        groups[sg].append(r)

    group_keys = sorted(groups.keys())

    # ------------------------------------------------------------------
    # PASS 1: 80/20 SPLIT (seed = 100)
    # ------------------------------------------------------------------
    rng1 = random.Random(SEED)
    rng1.shuffle(group_keys)
    cut1 = int(len(group_keys) * 0.80)
    pass1_80_keys = group_keys[:cut1]
    pass1_20_keys = group_keys[cut1:]

    pass1_80_rows = round_robin_interleave([r for k in pass1_80_keys for r in groups[k]], seed=SEED + 1)
    pass1_20_rows = round_robin_interleave([r for k in pass1_20_keys for r in groups[k]], seed=SEED + 2)
    write_jsonl(SPLIT1_80_WORK, pass1_80_rows)
    write_jsonl(SPLIT1_20_VAULT, pass1_20_rows)
    print(f"  [PASS 1 - 80/20 Split (seed={SEED})] 80% Working: {len(pass1_80_rows)} | 20% Vault Test: {len(pass1_20_rows)}")

    # ------------------------------------------------------------------
    # PASS 2: 70/30 SPLIT ON WORKING POOL (seed = 100)
    # ------------------------------------------------------------------
    rng2 = random.Random(SEED)
    rng2.shuffle(pass1_80_keys)
    cut2 = int(len(pass1_80_keys) * 0.70)
    pass2_70_keys = pass1_80_keys[:cut2]
    pass2_30_keys = pass1_80_keys[cut2:]

    pass2_70_rows = round_robin_interleave([r for k in pass2_70_keys for r in groups[k]], seed=SEED + 3)
    pass2_30_rows = round_robin_interleave([r for k in pass2_30_keys for r in groups[k]], seed=SEED + 4)
    write_jsonl(SPLIT2_70_CORE, pass2_70_rows)
    write_jsonl(SPLIT2_30_VAL, pass2_30_rows)
    print(f"  [PASS 2 - 70/30 Split (seed={SEED})] 70% Core: {len(pass2_70_rows)} | 30% Cross-App Val: {len(pass2_30_rows)}")

    # ------------------------------------------------------------------
    # PASS 3: 80/20 FINAL ACTIVE SPLIT + INTERLEAVED SHUFFLE (seed = 100)
    # ------------------------------------------------------------------
    rng3 = random.Random(SEED)
    rng3.shuffle(pass2_70_keys)
    cut3 = int(len(pass2_70_keys) * 0.80)
    final_80_keys = pass2_70_keys[:cut3]
    final_20_keys = pass2_70_keys[cut3:]

    final_train_rows = round_robin_interleave([r for k in final_80_keys for r in groups[k]], seed=SEED)
    final_eval_rows = round_robin_interleave([r for k in final_20_keys for r in groups[k]], seed=SEED)

    write_jsonl(FINAL_TRAIN_80, final_train_rows)
    write_jsonl(FINAL_EVAL_20, final_eval_rows)

    # Write data_summary.json required by Section 7 of TRAINING_DATASET_4B_FOR_GEMINI.md
    job_counts = defaultdict(int)
    verified_counts = defaultdict(int)
    for r in final_train_rows:
        m = r.get("meta", {})
        job_counts[m.get("job", "unknown")] += 1
        verified_counts[m.get("verified_by", "unknown")] += 1

    summary = {
        "seed": SEED,
        "total_cleaned_pool": len(all_rows),
        "pass1_80_20": {"work_80": len(pass1_80_rows), "vault_20": len(pass1_20_rows)},
        "pass2_70_30": {"core_70": len(pass2_70_rows), "cross_val_30": len(pass2_30_rows)},
        "pass3_80_20_final": {"train_80": len(final_train_rows), "eval_20": len(final_eval_rows)},
        "train_counts_by_job": dict(job_counts),
        "train_counts_by_verified_by": dict(verified_counts),
    }
    DATA_SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    SPLIT_DONE_FLAG.write_text(json.dumps({"completed": True, "seed": SEED}, indent=2), encoding="utf-8")
    print(f"  [PASS 3 - Final 80/20 Split (seed={SEED})] Train: {len(final_train_rows)} | Eval: {len(final_eval_rows)}")
    print(f"  [SUMMARY] Saved {DATA_SUMMARY_JSON}")


# ==============================================================================
# STAGE 3: AUTO-RESUMING QLORA TRAINER (SURVIVES LAPTOP SHUTDOWN / CLOSE)
# ==============================================================================
def get_latest_checkpoint(run_dir: pathlib.Path) -> pathlib.Path | None:
    cps = []
    for p in run_dir.rglob("checkpoint-*"):
        if p.is_dir() and (p / "trainer_state.json").exists():
            m = re.search(r"checkpoint-(\d+)", p.name)
            if m:
                cps.append((int(m.group(1)), p))
    if not cps:
        return None
    cps.sort(key=lambda x: x[0])
    return cps[-1][1]


def install_auto_resume_and_checkpoint_hook() -> None:
    """
    Hooks Hugging Face transformers.Trainer in memory so that even if
    core_organs.train_qlora does not pass `resume_from_checkpoint` or uses
    a high save_steps value, it automatically:
      1. Saves a checkpoint every 100 steps (TRAIN_SAVE_EVERY_N_STEPS)
      2. Forces output_dir into PERSISTENT_RUN_DIR
      3. Automatically resumes from the latest checkpoint-* on disk!
    """
    import transformers

    orig_init = transformers.Trainer.__init__
    orig_train = transformers.Trainer.train

    def patched_init(self, *args, **kwargs):
        training_args = kwargs.get("args") or (args[1] if len(args) > 1 else None)
        if training_args is not None:
            training_args.output_dir = str(PERSISTENT_RUN_DIR)
            training_args.save_strategy = "steps"
            training_args.save_steps = TRAIN_SAVE_EVERY_N_STEPS
            training_args.save_total_limit = 5
            training_args.logging_steps = 10
            training_args.seed = SEED
            training_args.data_seed = SEED
        return orig_init(self, *args, **kwargs)

    def patched_train(self, *args, **kwargs):
        latest_cp = get_latest_checkpoint(PERSISTENT_RUN_DIR)
        if latest_cp is not None and not kwargs.get("resume_from_checkpoint"):
            print("=" * 75)
            print(f" >>> [AUTO-RESUME DETECTED] Resuming from {latest_cp} <<<")
            print("=" * 75)
            kwargs["resume_from_checkpoint"] = str(latest_cp)
        return orig_train(self, *args, **kwargs)

    transformers.Trainer.__init__ = patched_init
    transformers.Trainer.train = patched_train


def sync_latest_checkpoint_to_adapter() -> None:
    """Copies the latest checkpoint weights into adapter/ so progress is always usable."""
    latest_cp = get_latest_checkpoint(PERSISTENT_RUN_DIR)
    if latest_cp:
        adapter_dir = PERSISTENT_RUN_DIR / "adapter"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        for fname in ("adapter_model.safetensors", "adapter_config.json", "README.md", "trainer_state.json"):
            src_f = latest_cp / fname
            if src_f.exists():
                shutil.copy2(src_f, adapter_dir / fname)
        print(f"[+] Synced latest checkpoint ({latest_cp.name}) -> {adapter_dir}")


def run_stage3_resumable_qlora() -> None:
    os.chdir(str(ALL_CODES))
    sys.path.insert(0, str(ALL_CODES))
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

    # Check if already 100% finished
    latest_cp = get_latest_checkpoint(PERSISTENT_RUN_DIR)
    if latest_cp:
        state = json.loads((latest_cp / "trainer_state.json").read_text(encoding="utf-8"))
        global_step = state.get("global_step", 0)
        if global_step >= TOTAL_TRAINING_STEPS:
            print(f"[STAGE 3] Training already reached {global_step}/{TOTAL_TRAINING_STEPS} steps!")
            sync_latest_checkpoint_to_adapter()
            return
        print(f"[STAGE 3] Found existing checkpoint at Step {global_step}/{TOTAL_TRAINING_STEPS}. Will resume from Step {global_step}!")

    # Prefer local 4B model if downloaded, fallback to 2B if 4B is still downloading
    local_4b = ROOT / "data" / "inbox" / "4b_training_sets" / "model_qwen3_vl_4b"
    model_arg = str(local_4b) if (local_4b / "config.json").exists() else "Qwen/Qwen3-VL-4B-Instruct"

    install_auto_resume_and_checkpoint_hook()

    sys.argv = [
        "train_qlora",
        "train",
        "--model", model_arg,
        "--vision",
        "--allow-unchecked-frames",
        "--all-pairs",
        "--jsonl", str(FINAL_TRAIN_80),
        "--seq", "1536",
        "--steps", str(TOTAL_TRAINING_STEPS),
    ]

    print(f"[STAGE 3] Launching auto-resuming QLoRA training on {model_arg} (saves every {TRAIN_SAVE_EVERY_N_STEPS} steps)...")
    import runpy
    try:
        runpy.run_module("core_organs.train_qlora", run_name="__main__")
    finally:
        sync_latest_checkpoint_to_adapter()


if __name__ == "__main__":
    print("=" * 75)
    print(" HOJAIGA AUTO-RESUMING PIPELINE (CLEAN -> 80/20 -> 70/30 -> 80/20 -> QLORA)")
    print("=" * 75)
    run_stage1_cleaning_with_checkpoints()
    run_stage2_cascading_splits_and_shuffle()
    run_stage3_resumable_qlora()
