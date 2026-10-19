"""
router_calibrate -- how sure is the model when it is right, and when it is wrong? One adapter, a sample of held-out rows, the model's own confidence per answer.

    python -m core_organs.router_calibrate --run-dir <dir with eval.jsonl> --adapter <adapter dir> --n 100 --seed 7 --out conf_new.json

Confidence = the geometric mean of the model's own token probabilities over the answer it generated (1.0 = certain), computed from generate(output_scores=True). The report joins the two adapters' files (same pair ids):

    python -m core_organs.router_calibrate --report conf_new.json conf_old.json --names data_names.json

and picks the threshold for the router "Top-40 adapter if it is sure, else the full-list adapter" from the data: for each candidate threshold the accuracy of the router over the sample, against each adapter alone. System Python (peft); the GPU must be free.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, os.path.join("D:" + os.sep, "new_automation", "All codes"))


def run(a: argparse.Namespace) -> int:
    import torch
    from peft import PeftModel
    from transformers import AutoProcessor, BitsAndBytesConfig, Qwen3VLForConditionalGeneration
    from core_organs import train_qlora as TQ
    rows = [json.loads(l) for l in open(os.path.join(a.run_dir, "eval.jsonl"), encoding="utf-8")]
    if a.ids:
        want = set(json.load(open(a.ids)))
        rows = [r for r in rows if r["meta"]["pair_id"] in want]
    else:
        random.Random(a.seed).shuffle(rows)
        rows = rows[:a.n]
    model_id = a.model
    bf16 = torch.cuda.is_bf16_supported()
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16 if bf16 else torch.float16, llm_int8_skip_modules=["visual", "lm_head"])
    model = Qwen3VLForConditionalGeneration.from_pretrained(model_id, quantization_config=bnb, device_map={"": 0}, dtype=torch.bfloat16 if bf16 else torch.float16)
    proc = AutoProcessor.from_pretrained(model_id)
    col = TQ.VLMCollator(proc, TQ.default_root(), TQ.TrainConfig.max_pixels, TQ.TrainConfig.max_seq_length)
    m = PeftModel.from_pretrained(model, a.adapter)
    m.eval()
    out: List[Dict[str, Any]] = []
    for i, r in enumerate(rows):
        gold = json.loads(r["messages"][2]["content"][0]["text"])[0]
        msgs = col._messages(r)[:-1]
        enc = proc.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt")
        enc = {k: (v.to(m.device) if hasattr(v, "to") else v) for k, v in enc.items()}
        with torch.no_grad():
            gen = m.generate(**enc, max_new_tokens=72, do_sample=False, stop_strings=['"verify_expectation"'], tokenizer=getattr(proc, "tokenizer", proc), return_dict_in_generate=True, output_scores=True)
        text = proc.batch_decode(gen.sequences[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        sc = TQ.score_action(TQ.parse_action(text), gold)
        vals = [float(x) for x in m.compute_transition_scores(gen.sequences, gen.scores, normalize_logits=True)[0].float().cpu().tolist()]
        out.append({"pid": r["meta"]["pair_id"], "exact": bool(sc["exact"]), "conf": round(math.exp(sum(vals) / max(len(vals), 1)), 4), "min_p": round(math.exp(min(vals)), 4) if vals else 0.0})
        if (i + 1) % 10 == 0:
            print(f"[calib] {i + 1}/{len(rows)} acc so far {sum(x['exact'] for x in out) / len(out):.3f}", flush=True)
            json.dump(out, open(a.out, "w"), indent=1)
    json.dump(out, open(a.out, "w"), indent=1)
    return 0


def report(a: argparse.Namespace) -> int:
    new = {r["pid"]: r for r in json.load(open(a.report[0]))}
    old = {r["pid"]: r for r in json.load(open(a.report[1]))}
    names = json.load(open(a.names)) if a.names else {}                    # {pid: id of the control the accessibility-name layer is sure of, or null} and {pid: gold id}
    pids = [p for p in new if p in old]
    n = len(pids)
    base = {"new_alone": sum(new[p]["exact"] for p in pids) / n, "old_alone": sum(old[p]["exact"] for p in pids) / n, "either_oracle": sum(new[p]["exact"] or old[p]["exact"] for p in pids) / n}
    rows = []
    for tau in [0.0, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.98, 1.01]:
        used_new = [p for p in pids if new[p]["conf"] >= tau]
        acc = sum((new[p]["exact"] if new[p]["conf"] >= tau else old[p]["exact"]) for p in pids) / n
        prec_new = (sum(new[p]["exact"] for p in used_new) / len(used_new)) if used_new else None
        rows.append({"tau": tau, "router_accuracy": round(acc, 3), "share_answered_by_top40": round(len(used_new) / n, 3), "top40_precision_when_used": None if prec_new is None else round(prec_new, 3)})
    best = max(rows, key=lambda r: (r["router_accuracy"], -abs(r["tau"] - 0.85)))
    res = {"n": n, **{k: round(v, 3) for k, v in base.items()}, "table": rows, "best_tau": best["tau"], "best_router_accuracy": best["router_accuracy"]}
    json.dump(res, open(a.out or "router_report.json", "w"), indent=1)
    print(json.dumps(res, indent=1))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="")
    ap.add_argument("--adapter", default="")
    ap.add_argument("--model", default="Qwen/Qwen3-VL-2B-Instruct")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--ids", default="", help="json list of pair ids to use (so two adapters see the same rows)")
    ap.add_argument("--out", default="")
    ap.add_argument("--report", nargs=2, default=None)
    ap.add_argument("--names", default="")
    a = ap.parse_args(argv)
    return report(a) if a.report else run(a)


if __name__ == "__main__":
    sys.exit(main())
