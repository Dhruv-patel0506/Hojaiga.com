"""
compare_adapters -- did retraining on prompt format v2 (zoomed strips + control names) help, measured fairly?

    python -m core_organs.compare_adapters split          make the split (whole apps held out)
    python -m core_organs.compare_adapters run            train the new adapter, evaluate old + new (GPU, sequential)
    python -m core_organs.compare_adapters report         the comparison table

The split holds out WHOLE APPS that the old adapter never saw (zero-shot apps), so the question is generalisation, not memory: neither adapter has seen a pair of these apps. The same held-out pairs are asked in
three ways:
    old adapter, v1 prompt (the format it was trained on)              -> "old, model alone"
    new adapter, v2 prompt WITHOUT the Names line (strips only)         -> "new, model alone (strips)"
    new adapter, v2 prompt WITH the Names line                          -> "new, with UIA names"
The runtime name-assist (UIA name correction) is separate and is reported by multitier_eval.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List

from core_organs import train_qlora as TQ
from core_organs.harvest.paths import harvest_dir


BASE_MODEL = "Qwen/Qwen3-VL-2B-Instruct"                           # what the old adapter was trained on and what fits the 6 GB card (the 8B default is refused)


def _read(p: str) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in open(p, encoding="utf-8")] if os.path.isfile(p) else []


def _runs(root: str) -> List[str]:
    return sorted(glob.glob(os.path.join(root, "training", "runs", "run_*")), key=os.path.getmtime)


def old_run(root: str) -> str:
    """The latest run that has an adapter AND was trained on prompt v1 (not one of this module's own runs)."""
    for r in reversed(_runs(root)):
        if os.path.isdir(os.path.join(r, "adapter")) and "v2split" not in r:
            return r
    return ""


def strip_names(row: Dict[str, Any]) -> Dict[str, Any]:
    """The same row without its `Names:` line (the strips stay)."""
    import copy
    r = copy.deepcopy(row)
    c = r["messages"][1]["content"]
    c[-1]["text"] = re.sub(r"^Names:.*\n", "", c[-1]["text"], flags=re.M)
    r["meta"]["names"] = 0
    return r


def build_split(root: str = "", holdout: str = "alternate") -> Dict[str, Any]:
    root = root or harvest_dir()[0]
    tdir = os.path.join(root, "training")
    cfg = TQ.TrainConfig()
    old = old_run(root)
    old_apps = {r["meta"]["app_key"] for r in _read(os.path.join(old, "train.jsonl"))} if old else set()
    v2 = _read(os.path.join(tdir, "ui_training_dataset_v2_all.jsonl"))
    v1 = {r["meta"]["pair_id"]: r for r in _read(os.path.join(tdir, "ui_training_dataset.jsonl"))}
    good = []
    for r in v2:
        if TQ.validate_pair(r, root, cfg.require_ui_gate):
            continue
        try:
            if TQ.estimate_pair_tokens(r, root, cfg.max_pixels) > cfg.max_seq_length - 300:         # the estimate under-counts multi-image rows (measured: an 'ok' row was 2087 tokens)
                continue
        except Exception:
            continue
        good.append(r)
    by_app: Dict[str, int] = {}
    for r in good:
        by_app[r["meta"]["app_key"]] = by_app.get(r["meta"]["app_key"], 0) + 1
    zero = sorted(a for a, n in by_app.items() if a not in old_apps and n >= 5)
    if holdout == "alternate":                                                  # about a fifth of the rows, spread over apps of every kind (a few large apps would otherwise be most of the eval)
        budget, held, used = int(0.22 * len(good)), set(), 0
        for a in zero[1::2] + zero[0::2]:
            if by_app[a] <= 80 and used + by_app[a] <= budget:
                held.add(a)
                used += by_app[a]
    else:
        held = set(zero)
    ev = [r for r in good if r["meta"]["app_key"] in held]
    tr = [r for r in good if r["meta"]["app_key"] not in held]
    out_dir = os.path.join(tdir, "runs", "run_" + time.strftime("%Y%m%d_%H%M%S") + "_v2split")
    os.makedirs(out_dir, exist_ok=True)
    for name, rows in (("train", tr), ("eval", ev), ("eval_nonames", [strip_names(r) for r in ev]), ("eval_v1", [v1[r["meta"]["pair_id"]] for r in ev if r["meta"]["pair_id"] in v1])):
        with open(os.path.join(out_dir, name + ".jsonl"), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = {"run_dir": out_dir, "old_run": old, "old_adapter_apps": sorted(old_apps), "zero_shot_apps": zero, "held_out_apps": sorted(held), "train": len(tr), "eval": len(ev), "eval_with_names": sum(1 for r in ev if r["meta"].get("names")),
               "eval_v1": sum(1 for r in ev if r["meta"]["pair_id"] in v1), "rows_valid": len(good), "rows_total": len(v2)}
    json.dump(summary, open(os.path.join(out_dir, "split_summary.json"), "w"), indent=2)
    return summary


def _py(args: List[str]) -> int:
    return subprocess.run([sys.executable, "-u", "-W", "ignore", "-m", "core_organs.train_qlora"] + args + ([] if "--model" in args else ["--model", BASE_MODEL]), cwd=os.path.join("D:" + os.sep, "new_automation", "All codes")).returncode


def run(steps: int = 450, skip_train: bool = False) -> None:
    root = harvest_dir()[0]
    split = max(glob.glob(os.path.join(root, "training", "runs", "*_v2split")), key=os.path.getmtime)
    old = old_run(root)
    print("[compare] training the new adapter on", split, flush=True)
    rc = 0 if skip_train else _py(["train", "--presplit", split, "--steps", str(steps), "--model", BASE_MODEL, "--min-examples", "100"])
    print("[compare] train rc", rc, flush=True)
    print("[compare] new adapter, v2 with names", flush=True)
    _py(["evaluate", "--run", split, "--eval-file", "eval.jsonl", "--no-base", "--report", "eval_new_names.json"])
    print("[compare] new adapter, v2 without names", flush=True)
    _py(["evaluate", "--run", split, "--eval-file", "eval_nonames.jsonl", "--no-base", "--report", "eval_new_alone.json"])
    if old:
        print("[compare] old adapter, v1 prompt", flush=True)
        _py(["evaluate", "--run", split, "--eval-file", "eval_v1.jsonl", "--adapter", os.path.join(old, "adapter"), "--no-base", "--report", "eval_old_v1.json"])


def report() -> str:
    root = harvest_dir()[0]
    split = max(glob.glob(os.path.join(root, "training", "runs", "*_v2split")), key=os.path.getmtime)
    s = json.load(open(os.path.join(split, "split_summary.json")))

    def sc(name: str, key: str) -> Dict[str, Any]:
        p = os.path.join(split, name)
        return json.load(open(p)).get(key, {}).get("scores", {}) if os.path.isfile(p) else {}
    rows = [("base model (no adapter), v2 prompt with names", sc("eval_new_names.json", "base")), ("old adapter, v1 prompt (model alone)", sc("eval_old_v1.json", "adapter")),
            ("new adapter, v2 prompt, strips only (model alone)", sc("eval_new_alone.json", "adapter")), ("new adapter, v2 prompt + UIA names", sc("eval_new_names.json", "adapter"))]
    lines = [f"Held-out: {s['eval']} pairs from {len(s['held_out_apps'])} apps the old adapter never saw ({', '.join(s['held_out_apps'])}); trained on {s['train']} pairs.", "",
             "| model | n | valid JSON | right action kind | exact (right control) |", "|---|---|---|---|---|"]
    for name, d in rows:
        lines.append(f"| {name} | {d.get('n', '-')} | {d.get('valid_json', '-')} | {d.get('action_kind', '-')} | {d.get('exact', '-')} |")
    # per DOMAIN (desktop_app / website / web_app): the same answers, re-scored by the domain of each held-out pair (samples are in the order of the eval file)
    def by_domain(report_name: str, key: str, eval_file: str) -> Dict[str, Any]:
        p = os.path.join(split, report_name)
        if not os.path.isfile(p):
            return {}
        samples = json.load(open(p)).get(key, {}).get("samples", [])
        rows_ = _read(os.path.join(split, eval_file))
        acc: Dict[str, List[bool]] = {}
        for r, sm in zip(rows_, samples):
            ok = bool(TQ.score_action(TQ.parse_action(sm.get("reply", "")), sm.get("gold", {}))["exact"])
            acc.setdefault(r["meta"].get("domain", "desktop_app"), []).append(ok)
        return {d: (len(v), round(sum(v) / max(len(v), 1), 3)) for d, v in acc.items()}
    doms = {"old adapter, v1 (model alone)": by_domain("eval_old_v1.json", "adapter", "eval_v1.jsonl"), "new adapter, strips only (model alone)": by_domain("eval_new_alone.json", "adapter", "eval_nonames.jsonl"),
            "new adapter + UIA names": by_domain("eval_new_names.json", "adapter", "eval.jsonl")}
    lines += ["", "Exact (right control) by master domain: n / accuracy", "", "| model | desktop_app | website | web_app |", "|---|---|---|---|"]
    for name, d in doms.items():
        lines.append("| " + name + " | " + " | ".join(("%d / %.0f%%" % (d[k][0], 100 * d[k][1])) if k in d else "-" for k in ("desktop_app", "website", "web_app")) + " |")
    md = "\n".join(lines)
    open(os.path.join(split, "compare_report.md"), "w", encoding="utf-8").write(md)
    return md


def report_half() -> str:
    """The comparison on the SAME rows: every second row of the held-out set (the first variant was run on all 250, the other two on every second row), per variant and per master domain."""
    root = harvest_dir()[0]
    split = max(glob.glob(os.path.join(root, "training", "runs", "*_v2split")), key=os.path.getmtime)
    s = json.load(open(os.path.join(split, "split_summary.json")))
    full = _read(os.path.join(split, "eval.jsonl"))[::2]
    half_v1 = _read(os.path.join(split, "eval_v1_half.jsonl"))

    def samples(name: str, key: str, stride: int) -> List[Dict[str, Any]]:
        p = os.path.join(split, name)
        return json.load(open(p)).get(key, {}).get("samples", [])[::stride] if os.path.isfile(p) else []
    variants = [("old adapter, v1 prompt (model alone)", samples("eval_old_v1_half.json", "adapter", 1), half_v1),
                ("new adapter, v2 strips only (model alone)", samples("eval_new_alone_half.json", "adapter", 1), full),
                ("new adapter, v2 strips + UIA names", samples("eval_new_names.json", "adapter", 2), full)]
    lines = [f"Held-out: the same {len(full)} rows (every second row of {s['eval']}) from {len(s['held_out_apps'])} apps the old adapter never saw; new adapter trained on {s['train']} rows (checkpoint step 100).", "",
             "| model | n | valid JSON | right action kind | exact (right control) |", "|---|---|---|---|---|"]
    by_dom: Dict[str, Dict[str, List[bool]]] = {}
    for name, sm, rows in variants:
        n = min(len(sm), len(rows))
        if not n:
            lines.append(f"| {name} | - | - | - | - |")
            continue
        sc = [TQ.score_action(TQ.parse_action(x.get("reply", "")), x.get("gold", {})) for x in sm[:n]]
        valid = sum(1 for c in sc if c["valid"]) / n
        kind = sum(1 for c in sc if c["action"]) / n
        ex = sum(1 for c in sc if c["exact"]) / n
        lines.append(f"| {name} | {n} | {valid:.2f} | {kind:.2f} | {ex:.3f} |")
        for r, c in zip(rows[:n], sc):
            by_dom.setdefault(name, {}).setdefault(r["meta"].get("domain", "desktop_app"), []).append(bool(c["exact"]))
    lines += ["", "Exact by master domain: n / accuracy", "", "| model | desktop_app | website | web_app |", "|---|---|---|---|"]
    for name, d in by_dom.items():
        lines.append("| " + name + " | " + " | ".join(("%d / %.0f%%" % (len(d[k]), 100 * sum(d[k]) / len(d[k]))) if k in d else "-" for k in ("desktop_app", "website", "web_app")) + " |")
    md = "\n".join(lines)
    open(os.path.join(split, "compare_report_half.md"), "w", encoding="utf-8").write(md)
    return md


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "split"
    if cmd == "split":
        print(json.dumps(build_split(), indent=1))
    elif cmd == "run":
        run(int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 450, skip_train="evaluate-only" in sys.argv)
    elif cmd == "half":
        print(report_half())
    else:
        print(report())
