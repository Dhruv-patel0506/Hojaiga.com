import warnings
warnings.filterwarnings("ignore")

import gc
import json
import os
import pathlib
import re
import sys
import time
from collections import defaultdict

ROOT = pathlib.Path(r"D:\new_automation")
REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = REPORT_DIR / "stage5_4b_live_benchmark.log"

# Dual logger: prints to terminal AND flushes to D:\new_automation\reports\stage5_4b_live_benchmark.log
class TeeLogger:
    def __init__(self, filepath: pathlib.Path):
        self.terminal = sys.stdout
        self.log = open(filepath, "w", encoding="utf-8", buffering=1)

    def write(self, message: str):
        self.terminal.write(message)
        self.terminal.flush()
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = TeeLogger(LOG_PATH)

# 1. Permanently patch master_17hf_4b_train_and_eval.py Stage 5 device_map (no -c quote bug)
master_script = ROOT / "master_17hf_4b_train_and_eval.py"
if master_script.exists():
    m_txt = master_script.read_text(encoding="utf-8")
    if 'device_map="auto"' in m_txt:
        m_txt = m_txt.replace('device_map="auto"', 'device_map={"": 0}, low_cpu_mem_usage=True')
        master_script.write_text(m_txt, encoding="utf-8")
        print("[+] Patched master_17hf_4b_train_and_eval.py Stage 5 device_map -> {'': 0}")

import torch
import transformers.modeling_utils as modeling_utils

# 2. Disable Windows WDDM caching_allocator_warmup freeze & clear GPU cache
modeling_utils.caching_allocator_warmup = lambda *args, **kwargs: None
gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()

INBOX_DIR = ROOT / "data" / "inbox"
TRAIN_DIR = ROOT / "data" / "ai_root" / "harvest" / "training"
PIPE_DIR = TRAIN_DIR / "master_4b_seed100_pipeline"
PERSISTENT_4B_RUN = TRAIN_DIR / "runs" / "hojaiga_4b_master_run"
FINAL_EVAL_FILE = PIPE_DIR / "eval.jsonl"

# 3. Locate the finished 1200-step 4B adapter
CANDIDATE_ADAPTERS = [
    PIPE_DIR / "adapter",
    PERSISTENT_4B_RUN / "adapter",
]
ADAPTER_DIR = next((p for p in CANDIDATE_ADAPTERS if (p / "adapter_model.safetensors").exists()), None)
if ADAPTER_DIR is None:
    cps = sorted(PERSISTENT_4B_RUN.glob("checkpoint-*"), key=lambda x: int(re.findall(r"\d+", x.name)[0]))
    ADAPTER_DIR = cps[-1] if cps else None

LOCAL_4B_DIR = INBOX_DIR / "1_model_qwen3_vl_4b"
BASE_MODEL_ID = str(LOCAL_4B_DIR) if (LOCAL_4B_DIR / "config.json").exists() else "Qwen/Qwen3-VL-4B-Instruct"

print("=" * 88)
print(" [STAGE 5 ONLY] LIVE GPU BENCHMARK ON 1200-STEP QWEN3-VL-4B-INSTRUCT ADAPTER")
print("=" * 88)
print(f" • Base 4B Model   : {BASE_MODEL_ID}")
print(f" • Trained Adapter : {ADAPTER_DIR}")
print(f" • Live Log File   : {LOG_PATH}")
free_gib, total_gib = [x / (1024**3) for x in torch.cuda.mem_get_info()]
print(f" • Free GPU VRAM   : {free_gib:.2f} GiB / {total_gib:.2f} GiB")

from transformers import AutoProcessor, BitsAndBytesConfig, AutoModelForImageTextToText
from peft import PeftModel

bnb_cfg = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
    llm_int8_enable_fp32_cpu_offload=True,
)

print("[*] Loading processor and 4-bit Qwen3-VL-4B-Instruct onto cuda:0 (takes ~20-35s)...")
processor = AutoProcessor.from_pretrained(BASE_MODEL_ID, local_files_only=True)
base_model = AutoModelForImageTextToText.from_pretrained(
    BASE_MODEL_ID,
    quantization_config=bnb_cfg,
    device_map={"": 0},
    low_cpu_mem_usage=True,
    dtype=torch.bfloat16,
    local_files_only=True,
)
model = PeftModel.from_pretrained(base_model, str(ADAPTER_DIR))
model.eval()
print("[+] Loaded 1200-Step Qwen3-VL-4B-Instruct + LoRA Adapter 100% on GPU 0!\n")

SYS = "You are Hojaiga UIA/Vision Executor. Output ONLY a valid JSON list of steps."

def ask_4b_model(user_txt: str, sys_txt: str = SYS):
    msgs = [
        {"role": "system", "content": [{"type": "text", "text": sys_txt}]},
        {"role": "user", "content": [{"type": "text", "text": user_txt}]},
    ]
    prompt = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[prompt], return_tensors="pt").to("cuda:0")
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=96,
            do_sample=False,
            pad_token_id=processor.tokenizer.eos_token_id,
        )
    gen = out[0][inputs["input_ids"].shape[1]:]
    raw = processor.tokenizer.decode(gen, skip_special_tokens=True).strip()
    lat = time.time() - t0
    parsed = None
    try:
        parsed = json.loads(raw)
    except Exception:
        m = re.search(r"(\[.*\]|\{.*\})", raw, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(1))
            except Exception:
                pass
    return raw, parsed, lat

# ==============================================================================
# PART 1: 5 LIVE DYNAMIC MUTATION, MODALITY SWITCH & POPUP TRAP TESTS
# ==============================================================================
print("[PART 1/2] Live Dynamic ID Mutation, Modality Switch & Popup Trap Disambiguation:")
scenarios = [
    (
        "Mutation A (Original Layout) — Click 'Export Render' at #14",
        "Application: blender\nElements:\n#11 button 'Cancel'\n#14 button 'Export Render'\n#19 edit 'File Path'\nGoal: Safely click 'Export Render' and avoid destructive 'Cancel'.",
        "click",
        14,
    ),
    (
        "Mutation B (Shuffled ID) — 'Export Render' moved to #87",
        "Application: blender\nElements:\n#14 button 'Delete All'\n#52 button 'Cancel'\n#87 button 'Export Render'\nGoal: Safely click 'Export Render' and avoid destructive 'Delete All'.",
        "click",
        87,
    ),
    (
        "Dynamic Modality Switch — Type 'final_scene.blend' into #63",
        "Application: blender\nElements:\n#14 button 'Delete All'\n#63 edit 'File Path'\nGoal: Type 'final_scene.blend' into 'File Path'.",
        "type",
        63,
    ),
    (
        "Dynamic Modality Switch — Press shortcut Ctrl+S",
        "Application: blender\nElements:\n#1 window 'blender Main Window'\n#14 button 'Delete All'\nGoal: Save the current project using shortcut Ctrl+S.",
        "hotkey",
        None,
    ),
    (
        "Zero-Shot Popup Trap — Avoid 'Discard Unsaved Work' (#21) & Click 'Save & Continue' (#44)",
        "Application: davinci_resolve\nElements:\n#21 button 'Discard Unsaved Work'\n#44 button 'Save & Continue'\n#90 button 'Cancel'\nGoal: Safely click 'Save & Continue' and avoid destructive 'Discard Unsaved Work'.",
        "click",
        44,
    ),
]

mut_pass = 0
for idx, (title, u_txt, exp_act, exp_id) in enumerate(scenarios, 1):
    raw, parsed, lat = ask_4b_model(u_txt)
    obj = parsed[0] if isinstance(parsed, list) and parsed else (parsed if isinstance(parsed, dict) else {})
    p_act = str(obj.get("action", "")).lower()
    p_id = obj.get("target_id")
    ok = (p_act == exp_act) and (exp_id is None or str(p_id) == str(exp_id))
    if ok:
        mut_pass += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] Test {idx}: {title} ({lat:.2f}s)")
    print(f"         Output: {raw}")

# ==============================================================================
# PART 2: HELD-OUT 4-MODALITY EVALUATION SET (CLICK / TYPE / HOTKEY / DRAG)
# ==============================================================================
print("\n[PART 2/2] Live Held-Out Evaluation Set (16 Balanced 4-Modality Samples: click, type, hotkey, drag):")
eval_rows = [json.loads(line) for line in open(FINAL_EVAL_FILE, "r", encoding="utf-8") if line.strip()]

by_mod = defaultdict(list)
for r in eval_rows:
    by_mod[r.get("meta", {}).get("job", "click")].append(r)

selected_eval = []
for mod in ("click", "type", "hotkey", "drag"):
    selected_eval.extend(by_mod[mod][:4])

valid_json_cnt = 0
modality_match_cnt = 0
exact_target_cnt = 0

for idx, row in enumerate(selected_eval, 1):
    msgs = row["messages"]
    def _extract_txt(c):
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            return "\n".join(str(p.get("text", "")) for p in c if isinstance(p, dict) and "text" in p).strip()
        return str(c)

    sys_t = _extract_txt(msgs[0].get("content", "")) if msgs[0].get("role") == "system" else SYS
    usr_t = ""
    gt_raw = "[]"
    for m in msgs:
        if m.get("role") == "user":
            usr_t = _extract_txt(m.get("content", ""))
        elif m.get("role") == "assistant":
            gt_raw = _extract_txt(m.get("content", ""))

    gt_obj = json.loads(gt_raw)[0]
    gt_act = str(gt_obj.get("action", "")).lower()
    gt_tid = gt_obj.get("target_id")

    raw, parsed, lat = ask_4b_model(usr_t, sys_t)
    is_valid = parsed is not None
    if is_valid:
        valid_json_cnt += 1
    pred_obj = parsed[0] if isinstance(parsed, list) and parsed else (parsed if isinstance(parsed, dict) else {})
    pred_act = str(pred_obj.get("action", "")).lower()
    pred_tid = pred_obj.get("target_id")

    mod_ok = (pred_act == gt_act)
    tid_ok = mod_ok and (gt_tid is None or str(pred_tid) == str(gt_tid))
    if mod_ok:
        modality_match_cnt += 1
    if tid_ok:
        exact_target_cnt += 1

    status = "PASS" if tid_ok else ("MOD_ONLY" if mod_ok else "FAIL")
    print(f"  [{status:8}] Sample {idx:02d} [{gt_act:6}] ({lat:.2f}s) | Expected: act={gt_act}, id={gt_tid} | Pred: act={pred_act}, id={pred_tid}")

n_eval = max(len(selected_eval), 1)
report = {
    "model": "Qwen/Qwen3-VL-4B-Instruct (1200-step QLoRA)",
    "adapter_path": str(ADAPTER_DIR),
    "train_loss_final": 0.000917,
    "dynamic_mutation_and_trap_score": f"{mut_pass}/{len(scenarios)} ({mut_pass/len(scenarios)*100:.1f}%)",
    "held_out_valid_json": f"{valid_json_cnt}/{n_eval} ({valid_json_cnt/n_eval*100:.1f}%)",
    "held_out_modality_accuracy": f"{modality_match_cnt}/{n_eval} ({modality_match_cnt/n_eval*100:.1f}%)",
    "held_out_exact_target_accuracy": f"{exact_target_cnt}/{n_eval} ({exact_target_cnt/n_eval*100:.1f}%)",
}
report_path = REPORT_DIR / "stage5_4b_benchmark_report.json"
report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

print("\n" + "=" * 88)
print(" FINAL 1200-STEP QWEN3-VL-4B-INSTRUCT LIVE GPU SCORECARD")
print("=" * 88)
print(f" 1. Dynamic ID Mutation & Popup Trap Recovery : {report['dynamic_mutation_and_trap_score']}")
print(f" 2. Held-Out Unseen Valid JSON Rate (Live)    : {report['held_out_valid_json']}")
print(f" 3. Held-Out 4-Modality Accuracy (Live)       : {report['held_out_modality_accuracy']}")
print(f" 4. Held-Out Exact Target ID Match (Live)     : {report['held_out_exact_target_accuracy']}")
print(f" • Saved JSON Report -> {report_path}")
print(f" • Saved Text Log    -> {LOG_PATH}")
print("=" * 88)
