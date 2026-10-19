"""
eval_v3 -- the held-out comparison for the overnight report: old adapter / new Top-40 adapter / the full pipeline (adapter + UIA names + RAG hint).

    python -m core_organs.eval_v3 run --v2 <v2 split dir> --v3 <v3 split dir> --old <old adapter> --new <new adapter>     (GPU, system python: runs the two adapters on the held-out rows)
    python -m core_organs.eval_v3 report --v2 ... --v3 ... [--old-report f] [--new-report f]                              (CPU: joins the per-row results and writes the table)

Held-out = whole applications the adapter never saw (the split was made by application). Rows are joined by pair_id so every number is over the SAME held-out requests:

    old_all            old adapter, v2 prompt (every element listed, strips), all held-out rows
    old_matching       the same adapter on the rows the Top-40 cut keeps (apples to apples with `new_alone`)
    new_alone          new adapter, v3 prompt (Top-40 + names [+ hint]), over the rows whose right element survived the cut
    new_alone_all      the same, counted over ALL held-out rows (a row whose answer was cut away counts as a miss): the conservative number
    uia_names          the deterministic layer: a control whose accessibility name contains every content word of the goal, if exactly one does (no model)
    pipeline           UIA-name layer first (when it is sure), else the new adapter, over ALL held-out rows. A row neither layer can answer is a miss.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, os.path.join("D:" + os.sep, "new_automation", "All codes"))


def load(path: str) -> List[Dict[str, Any]]:
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def gold_of(row: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(row["messages"][2]["content"][0]["text"])[0]


def text_of(row: Dict[str, Any]) -> str:
    return [c.get("text", "") for c in row["messages"][1]["content"] if c.get("type") == "text"][-1]


def name_layer(row_v2: Dict[str, Any]) -> Optional[int]:
    """The element id the accessibility names single out for the goal, or None (abstain)."""
    from core_organs.harvest import to_v3 as T3
    parts = T3.parse_user_text(text_of(row_v2))
    goal = parts["goal"].replace("Goal: ", "")
    want = [w for w in T3.tokens(goal) if w not in T3.GENERIC]
    if not want:
        return None
    names = T3.names_of(parts["names"])
    hits = []
    for e in parts["elements"]:
        have = set(T3.tokens((e["label"] + " " + names.get(e["id"], "")).strip()))
        if have and all(w in have for w in want):
            hits.append(e["id"])
    return hits[0] if len(hits) == 1 else None


def run_models(a: argparse.Namespace) -> int:
    from core_organs import train_qlora as TQ
    v2eval = load(os.path.join(a.v2, "eval.jsonl"))
    v3eval = load(os.path.join(a.v3, "eval.jsonl"))
    keep = {r["meta"]["pair_id"] for r in v3eval}
    with open(os.path.join(a.v2, "eval_matching.jsonl"), "w", encoding="utf-8") as f:
        for r in v2eval:
            if r["meta"]["pair_id"] in keep:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if not a.skip_old:
        TQ.evaluate_run(a.v2, a.model, eval_file="eval.jsonl", adapter_dir=a.old, with_base=False, report_name="eval_old_all.json")
    TQ.evaluate_run(a.v3, a.model, eval_file="eval.jsonl", adapter_dir=a.new, with_base=False, report_name="eval_v3_new.json")
    return 0


def report(a: argparse.Namespace) -> int:
    v2 = load(os.path.join(a.v2, "eval.jsonl"))
    v3 = load(os.path.join(a.v3, "eval.jsonl"))
    old = json.load(open(a.old_report or os.path.join(a.v2, "eval_old_all.json")))["adapter"]["samples"]
    new = json.load(open(a.new_report or os.path.join(a.v3, "eval_v3_new.json")))["adapter"]["samples"]
    old_by = {r["meta"]["pair_id"]: s["exact"] for r, s in zip(v2, old)}
    new_by = {r["meta"]["pair_id"]: s["exact"] for r, s in zip(v3, new)}
    hint_by = {r["meta"]["pair_id"]: bool(r["meta"].get("hint")) for r in v3}
    N = len(v2)
    rows = []
    for r in v2:
        pid = r["meta"]["pair_id"]
        g = gold_of(r)
        nm = name_layer(r) if g.get("action") == "click" else None
        name_hit = (nm is not None and nm == g.get("target_id"))
        rows.append({"pid": pid, "in_v3": pid in new_by, "old": old_by.get(pid, False), "new": new_by.get(pid, False), "name_sure": nm is not None, "name_hit": name_hit})
    pipe = pipe_old = either = 0
    for x in rows:
        pipe += 1 if (x["name_hit"] if x["name_sure"] else x["new"]) else 0
        pipe_old += 1 if (x["name_hit"] if x["name_sure"] else x["old"]) else 0
        either += 1 if (x["old"] or x["new"]) else 0
    kept = [x for x in rows if x["in_v3"]]
    with_hint = [pid for pid, h in hint_by.items() if h]
    out = {"held_out_rows": N, "rows_kept_by_top40": len(kept),
           "old_all": round(sum(x["old"] for x in rows) / N, 3),
           "old_matching": round(sum(x["old"] for x in kept) / max(len(kept), 1), 3),
           "new_alone": round(sum(x["new"] for x in kept) / max(len(kept), 1), 3),
           "new_alone_all": round(sum(x["new"] for x in kept) / N, 3),
           "uia_names_sure": sum(1 for x in rows if x["name_sure"]), "uia_names_precision": round(sum(1 for x in rows if x["name_hit"]) / max(sum(1 for x in rows if x["name_sure"]), 1), 3),
           "pipeline": round(pipe / N, 3),
           "pipeline_names_old": round(pipe_old / N, 3),
           "oracle_either_adapter": round(either / N, 3),
           "hard_rows": sum(1 for x in rows if not x["name_sure"]), "hard_old": sum(1 for x in rows if not x["name_sure"] and x["old"]), "hard_new": sum(1 for x in rows if not x["name_sure"] and x["new"]),
           "new_with_hint_rows": len(with_hint), "new_with_hint_exact": round(sum(new_by.get(p, False) for p in with_hint) / max(len(with_hint), 1), 3)}
    json.dump(out, open(a.out or os.path.join(a.v3, "eval_v3_summary.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "report"])
    ap.add_argument("--v2", required=True)
    ap.add_argument("--v3", required=True)
    ap.add_argument("--old", default="")
    ap.add_argument("--new", default="")
    ap.add_argument("--model", default="Qwen/Qwen3-VL-2B-Instruct")
    ap.add_argument("--skip-old", action="store_true")
    ap.add_argument("--old-report", default="")
    ap.add_argument("--new-report", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    return run_models(a) if a.cmd == "run" else report(a)


if __name__ == "__main__":
    sys.exit(main())
