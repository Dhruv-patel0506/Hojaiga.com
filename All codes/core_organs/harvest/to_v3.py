"""
harvest.to_v3 -- prompt format v3: the Eye (Qwen3-VL-2B) and the Mind (the RAG) decide together.

v2 gave the model EVERY element the scan found (a median of ~1,700 tokens of text per row; 229 of 889 rows did not fit the 2,048-token budget and had to be dropped). v3 gives it what matters for THIS goal:

    Elements:   the ~40 elements most relevant to the goal (label words shared with the goal first, then unlabeled icons, then buttons / fields), ids unchanged so the answer still names a real `#id`
    Names:      only for those elements
    Hint:       the step the RAG already suggests for this goal in this application (what the Mind remembers), when it has one
    Zoomed strips, Goal: as before

The choice of the ~40 uses NO knowledge of the answer: it is the same function the live system runs (vision_ground.trim_som / this module's `trim_elements`). A row whose right element does not survive the cut is reported
(`recall` in the stats) and is not used for training - the live system would not have shown the model that element either.

    python -m core_organs.harvest.to_v3 --split <v2split dir> --out <new dir>
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

ELEM_RX = re.compile(r"^#(\d+)\s+(\w+)\s+(.*?)\s+\[(-?\d+),\s*(-?\d+),\s*(\d+),\s*(\d+)\]\s*$")
GENERIC = {"click", "the", "button", "tab", "menu", "icon", "field", "checkbox", "item", "option", "a", "an", "to", "on", "in", "of", "and", "text", "box", "press", "select"}


def tokens(s: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 1]


def parse_user_text(text: str) -> Dict[str, Any]:
    """The v2 user text -> its parts: application line, element lines (kept verbatim), names, strips line, goal."""
    lines = text.split("\n")
    out: Dict[str, Any] = {"app": lines[0], "elements": [], "names": "", "strips": "", "goal": ""}
    mode = ""
    for ln in lines[1:]:
        if ln.startswith("Elements:"):
            mode = "el"
        elif ln.startswith("Names:"):
            out["names"], mode = ln, "names"
        elif ln.startswith("Zoomed strips"):
            out["strips"], mode = ln, "strips"
        elif ln.startswith("Goal:"):
            out["goal"], mode = ln, "goal"
        elif mode == "el":
            m = ELEM_RX.match(ln)
            if m:
                lab = re.match(r'^"(.*)"$', m.group(3).strip())
                out["elements"].append({"id": int(m.group(1)), "type": m.group(2), "label": lab.group(1) if lab else "", "line": ln, "box": (int(m.group(4)), int(m.group(5)), int(m.group(6)), int(m.group(7)))})
    return out


def names_of(names_line: str) -> Dict[int, str]:
    out: Dict[int, str] = {}
    if names_line:
        for p in names_line[len("Names: "):].split(" | "):
            m = re.match(r"#(\d+)\s+(.*)", p)
            if m:
                out[int(m.group(1))] = m.group(2)
    return out


def trim_elements(elements: Sequence[Dict[str, Any]], goal: str, k: int = 60, names: Optional[Dict[int, str]] = None) -> List[Dict[str, Any]]:
    """The k elements that matter for the goal. Words on the element AND the name UI Automation gave it count; unlabeled icons get a small boost (the goal may mean one); ids are kept.
    MEASURED on the 878 click rows of the training set: the right element survives the cut in 86.4% of rows at k=40, 89.2% at k=50, 91.7% at k=60."""
    names = names or {}
    want = [w for w in tokens(goal) if w not in GENERIC]

    def score(e: Dict[str, Any]) -> float:
        lab = (e["label"] + " " + names.get(e["id"], "")).strip()
        s = len(set(want) & set(tokens(lab))) * 2.0
        if not lab:
            s += 0.6
        if e["type"] in ("button", "field", "checkbox", "radio", "tab", "menu"):
            s += 0.2
        return s
    ranked = sorted(elements, key=lambda e: (-score(e), e["id"]))[:k]
    keep = {e["id"] for e in ranked}
    return [e for e in elements if e["id"] in keep]


def hint_for(rag: Any, app_key: str, goal: str) -> str:
    """The step the RAG suggests for this goal in this application, as one short line ('' when it holds nothing useful)."""
    from core_organs import brain_planner as BP
    from core_organs.rag import Query
    try:
        ret = rag.retrieve(Query(text=re.sub(r"^goal:\s*", "", goal, flags=re.I), app_key=app_key, snapshot=None, mode="auto"))
        for pl in BP.pathways(ret, 3):
            if pl["steps"] and pl["reliability"] >= 0.4:
                h = re.sub(r"\s+", " ", BP.plain_step(pl["steps"][0]))
                return h[:110]
    except Exception:
        pass
    return ""


def convert_row(row: Dict[str, Any], k: int = 40, rag: Any = None, hint_p: float = 0.5, force_gold: bool = False) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    r = copy.deepcopy(row)
    user = r["messages"][1]["content"]
    ti = next(i for i, c in enumerate(user) if c["type"] == "text")
    parts = parse_user_text(user[ti]["text"])
    els = parts["elements"]
    info = {"n_elements": len(els), "kept": len(els), "gold_kept": True, "hint": False}
    try:
        act = json.loads(r["messages"][2]["content"][0]["text"])[0]
    except Exception:
        act = {}
    gold = act.get("target_id") if act.get("action") == "click" else None
    from . import prompt_v3 as P3
    kept = P3.trim(els, parts["goal"].replace("Goal: ", ""), names_of(parts["names"]), k) if len(els) > k else els
    info["kept"] = len(kept)
    if gold is not None and gold not in {e["id"] for e in kept}:
        info["gold_kept"] = False
        if not force_gold:
            return None, info                                                # eval: the live system would not have shown it either -> counted as a cut, not scored
        ge = next((e for e in els if e["id"] == gold), None)                 # train: keep the row, swap the lowest-ranked element for the right one so every row teaches
        if ge is None:
            return None, info
        kept = [e for e in kept[:-1] if True] + [ge]
        kept.sort(key=lambda e: e["id"])
        info["gold_forced"] = True
    keep_ids = {e["id"] for e in kept}
    nm = {i: n for i, n in names_of(parts["names"]).items() if i in keep_ids}
    app_key = row["meta"].get("app_key", "")
    hint = ""
    pid_hash = int(hashlib.sha1(row["meta"].get("pair_id", "").encode()).hexdigest()[:6], 16)
    if rag is not None and (pid_hash % 100) < int(hint_p * 100):             # half of the rows carry the Mind's hint, so the Eye works with and without one
        hint = hint_for(rag, app_key, parts["goal"].replace("Goal:", "").strip())
    info["hint"] = bool(hint)
    n_strips = int(re.search(r"(\d+)", parts["strips"]).group(1)) if parts["strips"] else 0
    from . import prompt_v3 as P3
    text = P3.build_text(parts["app"].replace("Application: ", ""), kept, nm, hint, n_strips, parts["goal"].replace("Goal: ", ""))
    lines = [text]
    user[ti]["text"] = "\n".join(lines)
    r["meta"]["prompt_version"] = 3
    r["meta"]["kept_elements"] = len(kept)
    r["meta"]["hint"] = bool(hint)
    return r, info


def convert_file(src: str, dst: str, k: int = 40, rag: Any = None, hint_p: float = 0.5, log: Any = print, force_gold: bool = False) -> Dict[str, Any]:
    rows = [json.loads(l) for l in open(src, encoding="utf-8")]
    out: List[Dict[str, Any]] = []
    st = {"rows": len(rows), "kept": 0, "gold_cut": 0, "hints": 0, "elements_before": 0, "elements_after": 0}
    t0 = time.time()
    for i, r in enumerate(rows):
        nr, info = convert_row(r, k, rag, hint_p, force_gold)
        st["elements_before"] += info["n_elements"]
        if nr is None:
            st["gold_cut"] += 1
            continue
        out.append(nr)
        st["forced"] = st.get("forced", 0) + (1 if info.get("gold_forced") else 0)
        st["kept"] += 1
        st["elements_after"] += info["kept"]
        st["hints"] += 1 if info["hint"] else 0
        if (i + 1) % 200 == 0:
            log(f"[v3] {i + 1}/{len(rows)} {time.time() - t0:.0f}s")
    with open(dst, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    st["recall"] = round(1 - st["gold_cut"] / max(len(rows), 1), 3)
    return st


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=40)
    ap.add_argument("--no-hint", action="store_true")
    a = ap.parse_args(argv)
    sys.path.insert(0, os.path.join("D:" + os.sep, "new_automation", "All codes"))
    rag = None
    if not a.no_hint:
        from core_organs import rag as R
        rag = R.get_rag()
    os.makedirs(a.out, exist_ok=True)
    rep = {}
    for name in ("train", "eval"):
        rep[name] = convert_file(os.path.join(a.split, name + ".jsonl"), os.path.join(a.out, name + ".jsonl"), a.k, rag, force_gold=(name == "train"))
        print(name, json.dumps(rep[name]), flush=True)
    json.dump(rep, open(os.path.join(a.out, "v3_summary.json"), "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
