"""
web_train_prep -- the web action rows (harvest/web_actions.py) as a QLoRA run folder: whole SITES held out, so the eval measures sites the adapter never saw a label for.

    python -m core_organs.harvest.web_train_prep [--rows P] [--out DIR] [--eval-sites 0.2] [--seed N]

Writes DIR/train.jsonl, DIR/eval.jsonl and DIR/data_summary.json; then
    python -m core_organs.train_qlora train --model Qwen/Qwen3-VL-2B-Instruct --presplit DIR --steps N --min-examples 100
    python -m core_organs.train_qlora evaluate --model Qwen/Qwen3-VL-2B-Instruct --run DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
from typing import Any, Dict, List, Optional, Sequence

ROWS = r"D:\new_automation\data\ai_root\harvest\training\web_action_rows.jsonl"
RUNS = r"D:\new_automation\data\ai_root\harvest\training\runs"


def usable(r: Dict[str, Any]) -> bool:
    """A click row names a target that is in the list it shows; the answer is one JSON action."""
    try:
        a = json.loads(r["messages"][2]["content"][0]["text"])[0]
        txt = r["messages"][1]["content"][0]["text"]
        return a.get("action") == "click" and a.get("target_id") is not None and f"#{a['target_id']} " in txt
    except Exception:
        return False


def split(rows: Sequence[Dict[str, Any]], eval_sites: float = 0.2, seed: int = 3407) -> Dict[str, List[Dict[str, Any]]]:
    seen, good = set(), []
    for r in rows:
        key = hashlib.md5((r["messages"][1]["content"][0]["text"] + r["messages"][2]["content"][0]["text"]).encode()).hexdigest()
        if key in seen or not usable(r):
            continue
        seen.add(key)
        good.append(r)
    hosts = sorted({r["meta"].get("host", "") for r in good})
    rnd = random.Random(seed)
    rnd.shuffle(hosts)
    n_eval = max(1, int(round(len(hosts) * eval_sites))) if len(hosts) > 1 else 0
    held = set(hosts[:n_eval])
    return {"train": [r for r in good if r["meta"].get("host", "") not in held], "eval": [r for r in good if r["meta"].get("host", "") in held], "held_sites": sorted(held), "dropped": len(rows) - len(good)}


def prepare(rows_path: str = ROWS, out_dir: str = "", eval_sites: float = 0.2, seed: int = 3407) -> Dict[str, Any]:
    rows = [json.loads(l) for l in open(rows_path, encoding="utf-8") if l.strip()]
    sp = split(rows, eval_sites, seed)
    out_dir = out_dir or os.path.join(RUNS, time.strftime("run_%Y%m%d_web"))
    os.makedirs(out_dir, exist_ok=True)
    for name in ("train", "eval"):
        with open(os.path.join(out_dir, f"{name}.jsonl"), "w", encoding="utf-8") as f:
            for r in sp[name]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = {"rows_file": rows_path, "rows_read": len(rows), "dropped_duplicates_or_unusable": sp["dropped"], "train": len(sp["train"]), "eval": len(sp["eval"]),
               "train_sites": len({r["meta"].get("host") for r in sp["train"]}), "held_out_sites": sp["held_sites"], "out_dir": out_dir}
    json.dump(summary, open(os.path.join(out_dir, "data_summary.json"), "w"), indent=2)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Split the web action rows by site into a QLoRA run folder.")
    ap.add_argument("--rows", default=ROWS)
    ap.add_argument("--out", default="")
    ap.add_argument("--eval-sites", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=3407)
    a = ap.parse_args(argv)
    print(json.dumps(prepare(a.rows, a.out, a.eval_sites, a.seed), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
