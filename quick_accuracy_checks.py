import json, pathlib, torch
from peft import PeftModel
from transformers import AutoProcessor, AutoModelForImageTextToText

print("=" * 70)
print("   EVALUATION BENCHMARK: RECENTLY TRAINED ADAPTER")
print("=" * 70)

runs_dir = pathlib.Path(r"D:\new_automation\data\ai_root\harvest\training\runs")
target_run = runs_dir / "run_20261023_170523"
adapter_path = target_run / "adapter"

if not adapter_path.exists():
    target_run = max([d for d in runs_dir.iterdir() if d.is_dir() and (d / "adapter").exists()], key=lambda p: p.stat().st_mtime)
    adapter_path = target_run / "adapter"

eval_file = pathlib.Path(r"D:\new_automation\data\ai_root\harvest\training\qwen_10k_test_ready.jsonl")
report_path = pathlib.Path(r"D:\new_automation\current_adapter_accuracy_scorecard.json")

print(f"-> Loading Model & Adapter from: {adapter_path.name}")
model_id = "Qwen/Qwen3-VL-2B-Instruct"

processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
base_model = AutoModelForImageTextToText.from_pretrained(
    model_id,
    torch_dtype=torch.bfloat16,
    device_map="cuda",
    trust_remote_code=True
)
model = PeftModel.from_pretrained(base_model, str(adapter_path))
model.eval()

# Load test samples
samples = []
with open(eval_file, "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            samples.append(json.loads(line))
        if len(samples) >= 25:
            break

print(f"-> Running inference over {len(samples)} held-out test samples...\n")

valid_json, recoverable, action_kind_correct, exact_matches = 0, 0, 0, 0
actions_allowed = ["click", "type", "hotkey"]

for idx, sample in enumerate(samples, 1):
    msgs = sample["messages"]
    gold_reply = msgs[-1]["content"][0]["text"]
    
    try:
        gold_obj = json.loads(gold_reply)[0]
    except Exception:
        gold_obj = {"action": "click", "target_id": 1}
        
    gold_act = gold_obj.get("action", "click").lower()
    gold_id = str(gold_obj.get("target_id", 1))

    prompt_chat = [msgs[0], msgs[1]]
    text_input = processor.apply_chat_template(prompt_chat, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text_input], return_tensors="pt").to("cuda")

    with torch.no_grad():
        out_ids = model.generate(**inputs, max_new_tokens=48, do_sample=False)
        gen_tokens = out_ids[0][inputs.input_ids.shape[1]:]
        pred_text = processor.decode(gen_tokens, skip_special_tokens=True).strip()

    is_valid, is_rec, is_kind, is_exact = False, False, False, False
    try:
        parsed = json.loads(pred_text)
        if isinstance(parsed, list) and len(parsed) > 0:
            act_item = parsed[0]
            is_valid = True
            is_rec = True
            pred_act = act_item.get("action", "").lower()
            pred_id = str(act_item.get("target_id", ""))
            if pred_act in actions_allowed:
                is_kind = (pred_act == gold_act)
            if is_kind and (pred_id == gold_id):
                is_exact = True
    except Exception:
        pass

    valid_json += int(is_valid)
    recoverable += int(is_rec)
    action_kind_correct += int(is_kind)
    exact_matches += int(is_exact)

    status = "EXACT MATCH [PASS]" if is_exact else ("ACTION MATCH [OK]" if is_kind else "FORMAT ONLY [WARN]")
    print(f"[{idx:02d}/{len(samples):02d}] Predicted Action: {pred_text[:35]}... -> {status}")

n = len(samples)
res = {
    "evaluated_run": str(target_run.name),
    "sample_count": n,
    "valid_json_rate": round((valid_json / n) * 100, 2),
    "recoverable_action_rate": round((recoverable / n) * 100, 2),
    "action_kind_accuracy": round((action_kind_correct / n) * 100, 2),
    "exact_target_match_rate": round((exact_matches / n) * 100, 2)
}

with open(report_path, "w", encoding="utf-8") as f:
    json.dump(res, f, indent=2)

print("\n" + "=" * 65)
print(f"   ACCURACY SCORECARD: RUN {target_run.name}")
print("=" * 65)
print(f"{'Metric':32} | {'Score':15}")
print("-" * 65)
print(f"{'Valid JSON Structure':32} | {res['valid_json_rate']}%")
print(f"{'Recoverable Actions':32} | {res['recoverable_action_rate']}%")
print(f"{'Action Type Accuracy (Kind)':32} | {res['action_kind_accuracy']}%")
print(f"{'Exact Target Match Accuracy':32} | {res['exact_target_match_rate']}%")
print("=" * 65)
print(f"[+] Saved scorecard to: {report_path}")