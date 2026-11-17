r"""
D:\new_automation\real_gpu_eval-v2.py
======================================
HOJAIGA QWEN3-VL REAL GPU PYTORCH INFERENCE ENGINE (v2)
- Fixes AutoModel selection for Vision-Language Models (Qwen3-VL / Qwen2-VL).
- Uses AutoModelForVision2Seq / AutoModelForImageTextToText / AutoModel with trust_remote_code=True.
- Loads 4-bit NF4 weights onto RTX 3050 and attaches fine-tuned QLoRA adapter.
"""

from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch

ROOT_DIR = Path(r"D:\new_automation")
DATA_DIR = ROOT_DIR / "data"
DISTILLED_DIR = DATA_DIR / "beam_distilled_master"
TEST_SPLIT_FILE = DISTILLED_DIR / "qwen_test_30.jsonl"
RUNS_DIR = DATA_DIR / "ai_root" / "harvest" / "training" / "runs"
REPORTS_DIR = ROOT_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def get_latest_adapter_path() -> Optional[Path]:
    """Finds the latest trained QLoRA adapter directory."""
    if not RUNS_DIR.exists():
        return None
    runs = sorted(
        [d for d in RUNS_DIR.iterdir() if d.is_dir() and d.name.startswith("run_")],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    for r in runs:
        adapter_p = r / "adapter"
        if adapter_p.exists():
            return adapter_p
    return None


def run_real_gpu_evaluation(num_samples: int = 5) -> None:
    print("=" * 80)
    print("      HOJAIGA QWEN3-VL REAL GPU INFERENCE & EVALUATION ENGINE (v2)")
    print("=" * 80)

    adapter_path = get_latest_adapter_path()
    if not adapter_path:
        print("❌ Error: No trained adapter found under data/ai_root/harvest/training/runs/")
        return

    print(f"  • Loading Adapter Path : {adapter_path}")
    print(f"  • Target Device        : {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")

    # Load test split data
    test_samples = []
    if TEST_SPLIT_FILE.exists():
        for line in TEST_SPLIT_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    test_samples.append(json.loads(line))
                except Exception:
                    continue

    if not test_samples:
        ui_dataset = DATA_DIR / "ai_root" / "harvest" / "training" / "ui_training_dataset.jsonl"
        if ui_dataset.exists():
            lines = [ln.strip() for ln in ui_dataset.read_text(encoding="utf-8").splitlines() if ln.strip()]
            split_idx = int(len(lines) * 0.70)
            for ln in lines[split_idx:]:
                try:
                    test_samples.append(json.loads(ln))
                except Exception:
                    continue

    print(f"  • Loaded Test Dataset  : {len(test_samples)} unseen samples available")
    eval_subset = test_samples[:num_samples]
    print(f"  • Running Real GPU Pass on Top-{len(eval_subset)} samples...")
    print("-" * 80)

    try:
        from transformers import AutoTokenizer, AutoProcessor, BitsAndBytesConfig, AutoModel
        from peft import PeftModel

        # Try VLM-compatible loaders dynamically
        try:
            from transformers import AutoModelForVision2Seq as VLMLoader
        except ImportError:
            try:
                from transformers import AutoModelForImageTextToText as VLMLoader
            except ImportError:
                VLMLoader = AutoModel

        base_model_id = "Qwen/Qwen3-VL-2B-Instruct"
        print(f"\n[1/3] Loading VLM base model '{base_model_id}' in 4-bit NF4...")
        
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
        )

        try:
            tokenizer = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True)
        except Exception:
            tokenizer = None

        try:
            processor = AutoProcessor.from_pretrained(base_model_id, trust_remote_code=True)
        except Exception:
            processor = None

        base_model = VLMLoader.from_pretrained(
            base_model_id,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True
        )

        print(f"[2/3] Mounting fine-tuned LoRA adapter from {adapter_path}...")
        model = PeftModel.from_pretrained(base_model, str(adapter_path))
        model.eval()

        print("[3/3] Executing real-time PyTorch forward passes on GPU...\n")
        
        valid_json = 0

        for idx, sample in enumerate(eval_subset, 1):
            prompt = sample.get("prompt", sample.get("user", "Goal: Select primary button"))
            expected_raw = sample.get("completion", sample.get("target", sample.get("chosen_action", "")))

            formatted_prompt = f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"

            if processor is not None:
                inputs = processor(text=formatted_prompt, return_tensors="pt").to("cuda")
            elif tokenizer is not None:
                inputs = tokenizer(formatted_prompt, return_tensors="pt").to("cuda")
            else:
                raise ValueError("Neither AutoProcessor nor AutoTokenizer could be loaded.")

            t_start = time.time()
            with torch.no_grad():
                output_ids = model.generate(
                    **inputs,
                    max_new_tokens=128,
                    temperature=0.1,
                    do_sample=False
                )
            latency = round(time.time() - t_start, 2)

            if processor is not None:
                pred_text = processor.batch_decode(output_ids, skip_special_tokens=True)[0].strip()
            else:
                pred_text = tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()

            if "<|im_start|>assistant" in pred_text:
                pred_text = pred_text.split("<|im_start|>assistant")[-1].strip()

            is_json = pred_text.startswith("{") and pred_text.endswith("}")
            if is_json:
                valid_json += 1

            print(f"Sample #{idx:02d} [{latency}s GPU pass]:")
            print(f"  • User Prompt     : {prompt[:90]}...")
            print(f"  • Expected Output : {str(expected_raw)[:90]}")
            print(f"  • Model Prediction: {pred_text}")
            print("  " + "-" * 60)

        print("=" * 80)
        print("REAL GPU INFERENCE EVALUATION COMPLETE")
        print(f"  • Evaluated Samples : {len(eval_subset)}")
        print(f"  • Valid JSON Rate   : {(valid_json / len(eval_subset)) * 100:.1f}%")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error during GPU inference loading: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_real_gpu_evaluation(num_samples=5)
