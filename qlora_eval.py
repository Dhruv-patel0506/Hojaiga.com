"""
qlora_eval -- benchmark BASE Qwen2.5-3B-Instruct vs the FINE-TUNED brain/qlora_adapter on the
held-out 30% TEST split task-intents: does the model emit the correct action_type in its
trajectory JSON? Loads the 4-bit base once (WDDM-safe: warmup disabled, offline, device_map
{'':0}), scores zero-shot, then wraps the LoRA adapter and re-scores. Writes
metrics.json['qlora_eval'] = {base_acc, adapter_acc, n}. Honest: exact substring match of the
expected action token in the model's emitted JSON.
"""
import os
os.environ.setdefault("HF_HOME", os.path.abspath("models/hf_home"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
import json
import transformers.modeling_utils as _mu
_mu.caching_allocator_warmup = lambda *a, **k: None
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

BASE = "Qwen/Qwen2.5-3B-Instruct"
ADAPTER = os.environ.get("QLORA_ADAPTER", "brain/qlora_adapter")
ROUND = os.environ.get("QLORA_ROUND", "round1")
METRICS = "reports/ml_analysis/metrics.json"
# held-out 30% TEST intents -> expected action_type the fine-tune should emit
EVAL = [("switch tab (test)", "CLICK"), ("filter (test)", "TYPE_TEXT"),
        ("login form submit", "TYPE_TEXT"), ("modal commit (test)", "CLICK"),
        ("web->Notepad chain (test)", "COPY"), ("type into field (test)", "TYPE_TEXT")]


def prompt(intent):
    return (f"You are Hojaiga, a Windows desktop/web automation agent. Task: {intent}. "
            f"Emit the ordered action trajectory as a JSON array of {{target, action_type, text, expected}}.")


def score(tok, model, label):
    model.eval()
    hit = 0
    for intent, exp in EVAL:
        s = tok.apply_chat_template([{"role": "user", "content": prompt(intent)}], tokenize=False, add_generation_prompt=True)
        inp = tok(s, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**inp, max_new_tokens=64, do_sample=False)
        gen = tok.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True)
        if exp.lower() in gen.lower():
            hit += 1
    acc = round(hit / len(EVAL), 3)
    print(f"[eval] {label}: {hit}/{len(EVAL)} = {acc}")
    return acc


def main():
    tok = AutoTokenizer.from_pretrained(BASE, local_files_only=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    base = AutoModelForCausalLM.from_pretrained(BASE, quantization_config=bnb, device_map={"": 0},
                                                low_cpu_mem_usage=True, attn_implementation="sdpa",
                                                local_files_only=True, trust_remote_code=True)
    base_acc = score(tok, base, "BASE 3B (zero-shot)")
    tuned = PeftModel.from_pretrained(base, ADAPTER)
    tuned_acc = score(tok, tuned, "FINE-TUNED 3B + qlora_adapter")
    m = json.load(open(METRICS, encoding="utf-8")) if os.path.exists(METRICS) else {}
    m["qlora_eval"] = {"base_acc": base_acc, "adapter_acc": tuned_acc, "n": len(EVAL),
                       "split": "held-out TEST 30%", "round": ROUND, "adapter": ADAPTER}
    os.makedirs("reports/ml_analysis", exist_ok=True)
    json.dump(m, open(METRICS, "w", encoding="utf-8"), indent=3)
    print(f"[eval] wrote metrics.json['qlora_eval']: base {base_acc} -> tuned {tuned_acc}")


if __name__ == "__main__":
    main()
