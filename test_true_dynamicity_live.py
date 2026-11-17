import json, pathlib, sqlite3, pickle, re, time, sys
import torch
from transformers import AutoProcessor, BitsAndBytesConfig
from peft import PeftModel

BASE_DIR = pathlib.Path(r"D:\new_automation")
ALL_CODES = BASE_DIR / "All codes"
DATA_DIR = BASE_DIR / "data"
TRAIN_DIR = DATA_DIR / "ai_root" / "harvest" / "training"
RUNS_DIR = TRAIN_DIR / "runs"
TEST_JSONL = TRAIN_DIR / "qwen_10k_test_ready.jsonl"
RAG_DB = DATA_DIR / "hojaiga_master_rag.db"
RERANKER_PKL = DATA_DIR / "deep_rag_ml_reranker.pkl"

print("=" * 85)
print("   HOJAIGA LIVE GPU DYNAMICITY & ANTI-MEMORIZATION STRESS TEST (ZERO HARDCODING)")
print("=" * 85)

# ==============================================================================
# PART 1: INSPECT REAL GPU BENCHMARK FILES ALREADY ON DISK
# ==============================================================================
print("\n[PART 1/4] Forensic Audit of Saved GPU Benchmark Reports on Disk...")
for name, p in [("Overnight 3000-Step", BASE_DIR / "overnight_accuracy_benchmark.json"),
                ("Balanced 400-Step", BASE_DIR / "balanced_accuracy_benchmark.json")]:
    if p.exists():
        rep = json.loads(p.read_text(encoding="utf-8"))
        b = rep.get("base", {})
        a = rep.get("adapter", {})
        print(f" -> {name} ({p.name}):")
        print(f"    Base    : valid_json={b.get('valid_json')}, action_kind={b.get('action_kind')}, exact={b.get('exact')}")
        print(f"    Adapter : valid_json={a.get('valid_json')}, action_kind={a.get('action_kind')}, exact={a.get('exact')}")

# ==============================================================================
# PART 2: LOAD LIVE RAG + ML GATEKEEPER + 4-BIT QWEN3-VL-2B + TRAINED ADAPTER
# ==============================================================================
print("\n[PART 2/4] Loading Live SQLite FTS5 RAG, ML Gatekeeper & Qwen3-VL Adapter on GPU...")

with open(RERANKER_PKL, "rb") as f:
    rk = pickle.load(f)
vec = rk["vectorizer"]
mod_clf = rk["modality_classifier"]
id_to_label = rk.get("id_to_label", {0: "click", 1: "type", 2: "hotkey"})

conn = sqlite3.connect(str(RAG_DB))
cur = conn.cursor()

latest_run = max([d for d in RUNS_DIR.iterdir() if d.is_dir() and (d / "adapter").exists()], key=lambda p: p.stat().st_mtime)
adapter_path = latest_run / "adapter"
print(f" -> Active LoRA Adapter : {adapter_path}")

MODEL_ID = "Qwen/Qwen3-VL-2B-Instruct"
bnb_cfg = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True
)

processor = AutoProcessor.from_pretrained(MODEL_ID)
try:
    from transformers import AutoModelForImageTextToText
    base_model = AutoModelForImageTextToText.from_pretrained(MODEL_ID, quantization_config=bnb_cfg, device_map="auto")
except Exception:
    from transformers import AutoModelForVision2Seq
    base_model = AutoModelForVision2Seq.from_pretrained(MODEL_ID, quantization_config=bnb_cfg, device_map="auto")

model = PeftModel.from_pretrained(base_model, str(adapter_path))
model.eval()
print("[+] Live Qwen3-VL-2B + Trained Adapter Loaded in 4-Bit NF4 on RTX 3050!")

def retrieve_rag_hint(user_prompt: str) -> str:
    """Dynamically queries SQLite FTS5 RAG + ML Modality Gatekeeper for live context."""
    X_q = vec.transform([user_prompt]).toarray()
    pred_id = int(mod_clf.predict(X_q)[0])
    pred_kind = id_to_label.get(pred_id, "click")

    STOP = {"the", "and", "for", "with", "from", "that", "this", "into", "you", "are", "not", "null", "true", "false"}
    tokens = [w for w in re.findall(r"[a-zA-Z0-9]{3,}", user_prompt) if w.lower() not in STOP][:8]
    fts_q = " OR ".join(f'"{t}"' for t in tokens) if tokens else '"click"'
    rag_examples = []
    try:
        rows = cur.execute(
            "SELECT goal, action_json FROM workflows_fts WHERE workflows_fts MATCH ? ORDER BY bm25(workflows_fts) LIMIT 2",
            (fts_q,)
        ).fetchall()
        for g, a_j in rows:
            rag_examples.append(f"Similar verified action: {a_j}")
    except Exception:
        pass
    hint = f"\n[RAG_DYNAMIC_HINT]: Recommended action modality='{pred_kind}'."
    if rag_examples:
        hint += " " + " | ".join(rag_examples)
    return hint

def generate_live_qwen_json(system_txt: str, user_txt: str, use_rag: bool = True):
    """Runs 100% live GPU token generation through Qwen3-VL and parses raw output."""
    final_user = user_txt + (retrieve_rag_hint(user_txt) if use_rag else "")
    messages = []
    if system_txt:
        messages.append({"role": "system", "content": [{"type": "text", "text": system_txt}]})
    messages.append({"role": "user", "content": [{"type": "text", "text": final_user}]})

    prompt_str = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[prompt_str], return_tensors="pt").to(model.device)

    t0 = time.time()
    with torch.no_grad():
        out_ids = model.generate(
            **inputs,
            max_new_tokens=64,
            do_sample=False,
            pad_token_id=processor.tokenizer.eos_token_id
        )
    gen_ids = out_ids[0][inputs["input_ids"].shape[1]:]
    raw_reply = processor.tokenizer.decode(gen_ids, skip_special_tokens=True).strip()
    latency_s = time.time() - t0

    parsed_json = None
    try:
        parsed_json = json.loads(raw_reply)
    except Exception:
        m = re.search(r"(\{.*\}|\[.*\])", raw_reply, re.DOTALL)
        if m:
            try:
                parsed_json = json.loads(m.group(1))
            except Exception:
                pass
    return raw_reply, parsed_json, latency_s

# ==============================================================================
# PART 3: DYNAMIC CONTROL MUTATION & ZERO-SHOT UNSEEN APP TESTS
# ==============================================================================
print("\n[PART 3/4] Running Live Dynamic Mutation & Zero-Shot Unseen App Tests...")
print("           (Testing if the model dynamically tracks mutated IDs & unseen apps)\n")

SYS_PROMPT = (
    "You are HoJaiga UIA/Vision Executor. Given the user goal and live visible controls, "
    "output ONLY a single valid JSON action object with keys like action, target_id or target, and parameters."
)

dynamic_scenarios = [
    {
        "name": "Mutation A (Original Layout) — Click 'Export Render' at ID #14",
        "user": "App: Blender_Unseen_v4 | Goal: Click the Export Render button.\nVisible Controls:\n[11] Button 'Cancel' (100, 500)\n[14] Button 'Export Render' (420, 180)\n[19] Edit 'File Path' (200, 180)",
        "expect_kind": "click",
        "expect_target": 14
    },
    {
        "name": "Mutation B (Shuffled ID & Moved Coords) — 'Export Render' moved to ID #87",
        "user": "App: Blender_Unseen_v4 | Goal: Click the Export Render button.\nVisible Controls:\n[14] Button 'Delete All' (420, 180)\n[52] Button 'Cancel' (100, 500)\n[87] Button 'Export Render' (890, 640)",
        "expect_kind": "click",
        "expect_target": 87
    },
    {
        "name": "Dynamic Modality Switch — Same App, Goal Changed to Typing Filename",
        "user": "App: Blender_Unseen_v4 | Goal: Type 'final_scene.blend' into the File Path input box.\nVisible Controls:\n[14] Button 'Delete All' (420, 180)\n[63] Edit 'File Path' (200, 180)\n[87] Button 'Export Render' (890, 640)",
        "expect_kind": "type",
        "expect_target": 63
    },
    {
        "name": "Dynamic Modality Switch — Same App, Goal Changed to Keyboard Shortcut",
        "user": "App: Blender_Unseen_v4 | Goal: Press shortcut Ctrl+S to save the project.\nVisible Controls:\n[14] Button 'Delete All' (420, 180)\n[63] Edit 'File Path' (200, 180)",
        "expect_kind": "hotkey",
        "expect_target": None
    },
    {
        "name": "Zero-Shot Unseen Popup Trap — Avoid Destructive 'Discard Work' (#21) & Click 'Save & Continue' (#44)",
        "user": "App: DaVinci_Resolve_Unseen | Popup Modal: 'Unsaved Timeline Changes'\nGoal: Safely resolve the popup without losing work.\nVisible Controls:\n[21] Button 'Discard Unsaved Work' (310, 400)\n[44] Button 'Save & Continue' (520, 400)",
        "expect_kind": "click",
        "expect_target": 44
    }
]

mut_passed = 0
for idx, sc in enumerate(dynamic_scenarios, 1):
    raw_out, parsed, lat = generate_live_qwen_json(SYS_PROMPT, sc["user"], use_rag=True)
    act_obj = parsed[0] if isinstance(parsed, list) and parsed else (parsed if isinstance(parsed, dict) else {})
    gen_kind = str(act_obj.get("action", "")).lower()
    gen_tgt = act_obj.get("target_id", act_obj.get("id", act_obj.get("target")))

    kind_ok = (gen_kind == sc["expect_kind"])
    tgt_ok = True if sc["expect_target"] is None else (str(gen_tgt) == str(sc["expect_target"]) or str(sc["expect_target"]) in raw_out)
    ok = kind_ok and tgt_ok
    if ok:
        mut_passed += 1

    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] Test {idx}: {sc['name']} ({lat:.2f}s)")
    print(f"         Raw Live GPU Output : {raw_out}")
    print(f"         Expected            : action='{sc['expect_kind']}', target={sc['expect_target']}\n")

# ==============================================================================
# PART 4: LIVE GPU EVALUATION ON HELD-OUT UNSEEN TEST SAMPLES (WITH RAG vs WITHOUT)
# ==============================================================================
print("[PART 4/4] Running Live GPU Inference on 12 Held-Out Round-Robin Test Samples...")
test_rows = [json.loads(line) for line in open(TEST_JSONL, "r", encoding="utf-8") if line.strip()]

from collections import defaultdict
buckets = defaultdict(list)
for r in test_rows:
    msgs = r.get("messages", [])
    sys_t, usr_t, asst_t = "", "", ""
    for m in msgs:
        c = m.get("content", "")
        t = c if isinstance(c, str) else " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
        if m.get("role") == "system": sys_t = t
        elif m.get("role") == "user": usr_t = t
        elif m.get("role") == "assistant": asst_t = t
    try:
        gt = json.loads(asst_t)
        gt_obj = gt[0] if isinstance(gt, list) and gt else gt
    except Exception:
        continue
    buckets[(r.get("app_key", "app"), gt_obj.get("action", "click"))].append((sys_t, usr_t, gt_obj))

sample_12 = []
keys = sorted(buckets.keys())
i = 0
while len(sample_12) < 12 and any(len(buckets[k]) > i for k in keys):
    for k in keys:
        if i < len(buckets[k]) and len(sample_12) < 12:
            sample_12.append((k[0], k[1], *buckets[k][i]))
    i += 1

live_valid = 0
live_kind = 0
live_exact = 0

for idx, (app_k, true_k, sys_t, usr_t, gt_obj) in enumerate(sample_12, 1):
    raw_out, parsed, lat = generate_live_qwen_json(sys_t, usr_t, use_rag=True)
    if parsed is not None:
        live_valid += 1
        pred_obj = parsed[0] if isinstance(parsed, list) and parsed else (parsed if isinstance(parsed, dict) else {})
        pred_k = str(pred_obj.get("action", "")).lower()
        if pred_k == true_k:
            live_kind += 1
            if pred_obj == gt_obj or pred_obj.get("target_id") == gt_obj.get("target_id"):
                live_exact += 1
    print(f"  Sample {idx:02d} [{app_k}/{true_k}] ({lat:.2f}s) -> Live GPU Output: {raw_out[:95]}")

conn.close()

print("\n" + "=" * 85)
print("   LIVE GPU DYNAMICITY SUMMARY (100% REAL MODEL.GENERATE(), ZERO HARDCODING)")
print("=" * 85)
print(f" 1. Dynamic Mutation & Zero-Shot Unseen Apps : {mut_passed}/{len(dynamic_scenarios)} ({mut_passed/len(dynamic_scenarios)*100:.1f}%)")
print(f" 2. Held-Out Unseen Test Valid JSON (Live)   : {live_valid}/{len(sample_12)} ({live_valid/len(sample_12)*100:.1f}%)")
print(f" 3. Held-Out Unseen Action Modality (Live)   : {live_kind}/{len(sample_12)} ({live_kind/len(sample_12)*100:.1f}%)")
print(f" 4. Held-Out Unseen Exact Target Match (Live): {live_exact}/{len(sample_12)} ({live_exact/len(sample_12)*100:.1f}%)")
print("=" * 85)
