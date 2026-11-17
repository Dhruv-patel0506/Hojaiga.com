"""
qlora_train -- (b) Qwen2.5-3B-Instruct 4-bit QLoRA on the GENUINELY-VERIFIED pool:
22 zero-poisoned episodic rows (10x oversampled) + grounded trajectory steps from the
Phase-1 corpus. Windows WDDM / RTX 3050 safe: caching_allocator_warmup disabled, offline
cache, device_map={"":0}, sdpa attention, fp16 compute, adamw_8bit (NOT paged), no
dataloader workers, use_reentrant=False. Refuses to run below the >=22-row clean gate.
"""
from __future__ import annotations
import os
import json
import sqlite3
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path("models/hf_home").resolve()))
os.environ.setdefault("HF_HUB_OFFLINE", "1")          # weights are cached; skip HF head checks
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

# WDDM fix: transformers>=4.45 runs caching_allocator_warmup() right before "Loading checkpoint
# shards" which pre-allocates a huge contiguous block and freezes 6 GB WDDM GPUs. Neutralize it.
import transformers.modeling_utils as _mu
_mu.caching_allocator_warmup = lambda *a, **k: None

MIN_ROWS = 22
BASE_MODEL = os.environ.get("QLORA_BASE", "Qwen/Qwen2.5-3B-Instruct")
OUT = Path(os.environ.get("QLORA_OUT", "brain/qlora_adapter"))
DB = Path("brain/episodic_memory.db")
TRAJ = Path("trajectories")
# Round-2: the 6 held-out TEST intents must NEVER appear in training (strict generalization test).
HELD_OUT_INTENTS = {"switch tab (test)", "filter (test)", "login form submit",
                    "modal commit (test)", "web->Notepad chain (test)", "type into field (test)"}


def _slim(steps):
    out = []
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        ui = s.get("ui_target", {}) or {}
        va = s.get("virtual_mouse_action", {}) or {}
        # accept BOTH schemas: nested (desktop executor) and flat (webapp/charmap suites)
        tgt = (ui.get("element_name") if isinstance(ui, dict) else None) or s.get("target")
        at = (va.get("action_type") if isinstance(va, dict) else None) or s.get("action_type")
        if tgt and at:                       # a GROUNDED step: concrete target + valid action
            txt = (va.get("text_payload") if isinstance(va, dict) else None) or s.get("text")
            exp = s.get("expected_state_change") or s.get("expected", "")
            out.append({"target": tgt, "action_type": at, "text": txt, "expected": exp})
    return out


def _gate():
    c = sqlite3.connect(str(DB)); cur = c.cursor()
    cur.execute("SELECT app_name, task_intent, trajectory_json FROM verified_trajectories")
    rows = cur.fetchall(); c.close()
    print(f"[qlora] episodic verified rows: {len(rows)} (gate >= {MIN_ROWS})")
    if len(rows) < MIN_ROWS:
        raise SystemExit(f"GATE NOT MET: {len(rows)} < {MIN_ROWS} clean rows -- refusing to train.")
    return rows


def build_dataset(rows):
    data = []
    for app, intent, tj in rows:
        if str(intent) in HELD_OUT_INTENTS:      # never train on the held-out TEST split
            continue
        slim = _slim(json.loads(tj)) if tj else []
        if not slim:
            continue
        user = (f"You are Hojaiga, a Windows desktop-automation agent. App: {app}. Task: {intent}. "
                f"Emit the ordered action trajectory as a JSON array of {{target, action_type, text, expected}}.")
        data.append({"messages": [{"role": "user", "content": user},
                                  {"role": "assistant", "content": json.dumps(slim, ensure_ascii=False)}]})
    data = data * 10                                   # 10x oversample the small verified set
    n_epi = len(data)
    # augment with grounded single-step examples from the Phase-1 trajectory corpus
    grounded = 0
    for j in TRAJ.rglob("*.json"):
        if grounded >= 600:
            break
        try:
            for s in _slim(json.loads(j.read_text(encoding="utf-8")).get("trajectory", [])):
                data.append({"messages": [
                    {"role": "user", "content": f"Ground the step '{s['action_type']}' on control '{s['target']}'."},
                    {"role": "assistant", "content": json.dumps([s], ensure_ascii=False)}]})
                grounded += 1
                if grounded >= 600:
                    break
        except Exception:
            continue
    print(f"[qlora] dataset: {n_epi} episodic(10x) + {grounded} grounded steps = {len(data)} examples")
    return data


def main():
    rows = _gate()
    data = build_dataset(rows)
    import torch
    from datasets import Dataset
    from transformers import (AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
                              Trainer, TrainingArguments, DataCollatorForLanguageModeling)
    from peft import LoraConfig, prepare_model_for_kbit_training

    ds = Dataset.from_list(data)
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, local_files_only=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    print(f"[qlora] loading {BASE_MODEL} 4-bit from cache (warmup disabled, device_map={{'':0}})...")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, quantization_config=bnb, device_map={"": 0}, low_cpu_mem_usage=True,
        attn_implementation="sdpa", local_files_only=True, trust_remote_code=True)
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model.add_adapter(LoraConfig(r=16, lora_alpha=32, target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
                                 lora_dropout=0.05, bias="none", task_type="CAUSAL_LM"))
    vram = torch.cuda.get_device_properties(0).total_memory / 1e9 if torch.cuda.is_available() else 0
    print(f"[qlora] CUDA={torch.cuda.is_available()} VRAM~{vram:.1f}GB  loaded OK -> training")

    # build "text" via the chat template, tokenize, and train with the plain transformers
    # Trainer + DataCollatorForLanguageModeling -- this bypasses trl 1.15's SFTTrainer
    # compute_loss ('NoneType' has no 'apply') entirely.
    def to_text(ex):
        return {"text": tok.apply_chat_template(ex["messages"], tokenize=False, add_generation_prompt=False)}
    ds = ds.map(to_text, remove_columns=ds.column_names)
    ds = ds.map(lambda ex: tok(ex["text"], truncation=True, max_length=512), remove_columns=["text"])

    targs = TrainingArguments(
        output_dir=str(OUT), per_device_train_batch_size=1, gradient_accumulation_steps=8,
        num_train_epochs=2, learning_rate=2e-4, lr_scheduler_type="cosine",
        logging_steps=5, save_strategy="epoch", optim="adamw_8bit", bf16=True, fp16=False,
        gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
        dataloader_num_workers=0, report_to=[])
    trainer = Trainer(model=model, args=targs, train_dataset=ds,
                      data_collator=DataCollatorForLanguageModeling(tok, mlm=False), processing_class=tok)
    print("[qlora] training (transformers.Trainer, trl-free)...")
    trainer.train()
    trainer.save_model(str(OUT)); tok.save_pretrained(str(OUT))
    print(f"[qlora] DONE. adapter saved -> {OUT}")


if __name__ == "__main__":
    main()
