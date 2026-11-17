import json, pathlib, re

ROOT = pathlib.Path(r"D:\new_automation")
TRAIN_DIR = ROOT / "data" / "ai_root" / "harvest" / "training"
INBOX_DIR = ROOT / "data" / "inbox"
ROT_ROOT = TRAIN_DIR / "rotating_interleaved_seed100"

print("=" * 88)
print(" 1. FULL DISK DATASET vs. ACTUAL TRAINED ROWS AUDIT")
print("=" * 88)

def count_jsonl(p: pathlib.Path) -> int:
    if not p.exists(): return 0
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        return sum(1 for ln in f if ln.strip())

# Count unique vs synthetic rows inside the 12 rotating sections
rot_total, rot_drag, rot_real_pool, rot_synth = 0, 0, 0, 0
unique_prompts = set()
for sec in sorted(ROT_ROOT.glob("section_*")):
    tr = sec / "train.jsonl"
    if tr.exists():
        with open(tr, "r", encoding="utf-8", errors="ignore") as f:
            for ln in f:
                if not ln.strip(): continue
                rot_total += 1
                r = json.loads(ln)
                u_txt = str(r.get("messages", [{}])[-2].get("content", ""))
                unique_prompts.add(hash(u_txt))
                mod = r.get("meta", {}).get("action_modality", "")
                if mod == "drag":
                    rot_drag += 1
                if "pat" in str(r.get("meta", {}).get("pattern_category", "")):
                    rot_synth += 1
                else:
                    rot_real_pool += 1

print(f" • 12 Rotating Sections Total Train Rows : {rot_total:,}")
print(f"   ├─ Synthetic 8-Pattern Rows           : {rot_synth:,}")
print(f"   ├─ Real Disk Pool Rows Sliced In      : {rot_real_pool:,}")
print(f"   ├─ Rejected 'drag' Rows (Untrained)   : {rot_drag:,}")
print(f"   └─ Kept & Trained Rows Across 12 Secs : {rot_total - rot_drag:,} ({len(unique_prompts):,} unique prompts)")

print("\n" + "-" * 88)
print(" 2. RAW DATASETS ON DISK (WAITING OR PARTIALLY SAMPLED)")
print("-" * 88)
raw_files = [
    TRAIN_DIR / "qwen_50k_mega_overnight_train.jsonl",
    TRAIN_DIR / "vlm_50k_visual_dots_dataset.jsonl",
    TRAIN_DIR / "qwen_24k_train_ready.jsonl",
    TRAIN_DIR / "qwen_balanced_1to1to1_train.jsonl",
    TRAIN_DIR / "qwen_4modality_dynamic_train.jsonl",
    TRAIN_DIR / "synthetic_4modality_and_traps_4000.jsonl",
    TRAIN_DIR / "ultron_6tier_quality_photos_videos_rea_8000.jsonl",
    TRAIN_DIR / "hf_17_unpacked_multimodal_rows.jsonl",
    ROOT / "data" / "beam_distilled_master" / "distilled_causal_rag.jsonl",
    ROOT / "data" / "beam_distilled_master" / "distilled_qwen_dpo.jsonl",
]
total_raw_disk = 0
for rf in raw_files:
    c = count_jsonl(rf)
    total_raw_disk += c
    status = "SAMPLED (~4,800 rows)" if c > 0 and rf.name in ("qwen_balanced_1to1to1_train.jsonl", "synthetic_4modality_and_traps_4000.jsonl") else ("UNTOUCHED IN ROTATING RUN" if c > 0 else "NOT FOUND")
    print(f" • {rf.name:<50} : {c:>8,} rows | {status}")

hf_parquets = list(INBOX_DIR.rglob("*.parquet"))
hf_jsons = [p for p in INBOX_DIR.rglob("*.json*") if "1_model" not in str(p)]
print(f" • 17 HF Inbox Folders (.parquet / .json files)      : {len(hf_parquets)} parquet / {len(hf_jsons)} json files")
print(f" • Total Raw JSONL Rows on Disk                      : {total_raw_disk:,} rows")
print("=" * 88)
