"""
live_eval -- how often does the trained adapter click the RIGHT element on screens it was not trained on?

The 13 held-out pairs of the training run are too few. This builds a fresh test set from a LIVE owned app: every safe control UI Automation reports is a question with a known answer (the Set-of-Marks element
that contains the control's rectangle; the same grounding the training pairs used), asked in the same words ("Click the <name> <kind>"). No click is made: the model answers on the current screen and its
target_id is compared with the answer. Controls are split by whether the adapter's TRAINING data contained that control (same app, same UIA name):

    seen     the control's own label was in the training set (on this layout or another state)
    unseen   never labelled in training: the generalisation that matters

Two baselines keep the number honest: a lexical matcher (the spoken name inside an on-screen label, no model, the same rule the data pipeline uses) and chance (1 / number of elements).
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

from core_organs import agent_verify as AV, safety_guard as SG
from core_organs.harvest import local_recorder as LR, video_explain as VE


def trained_control_names(run_dir: str) -> Dict[str, Set[str]]:
    """{app_key: {uia_name}} of the locally recorded pairs in the run's TRAIN split (the eval split is deliberately excluded)."""
    out: Dict[str, Set[str]] = {}
    path = os.path.join(run_dir, "train.jsonl")
    for line in open(path, encoding="utf-8"):
        m = json.loads(line).get("meta", {})
        if m.get("source") == "local_uia" and m.get("uia_name"):
            out.setdefault(m["app_key"], set()).add(m["uia_name"])
    return out


def _askable(c: Dict[str, Any]) -> bool:
    name = c["name"]
    if LR.CHROME_RX.search(name):
        return False
    return SG.is_safe(name) and not LR.DENY_RX.search(name) and not LR._personal(name) and not LR.volatile(name)


def click_accuracy(app: Any, app_key: str, ground: Callable[..., Any], seen_names: Set[str], som_fn: Callable[..., Dict[str, Any]], max_controls: int = 40, state: str = "initial") -> Dict[str, Any]:
    """Ask the adapter about each askable control on the app's CURRENT screen. `app` has grab(popups=) and controls(origin, size) (an OwnedApp, or a stand-in)."""
    img, origin = app.grab(popups=True)
    if img is None:
        return {"state": state, "error": "no picture", "rows": [], "summary": {}}
    som = som_fn(img)
    rows: List[Dict[str, Any]] = []
    t0 = time.time()
    askable: List[Dict[str, Any]] = []
    listed: Set[str] = set()
    all_controls = app.controls(origin, img.size)
    for c in all_controls:
        if _askable(c) and c["name"] not in listed:           # a control is often listed twice (its list item and its button): asked once
            listed.add(c["name"])
            askable.append(c)
    if len(askable) > max_controls:                               # more controls than we will ask about: an even spread through the tree, not just the first ones (menus, then tools, then shapes, then colours)
        step = len(askable) / float(max_controls)
        askable = [askable[int(i * step)] for i in range(max_controls)]
    for c in askable:
        if len(rows) >= max_controls:
            break
        gt = LR.element_at(som, c["box"])
        if gt is None:                                           # the scanner found nothing inside this control: there is no right answer to ask for
            continue
        goal = LR.goal_for(c["name"], c["type"])
        try:
            action, reply = ground(img, som, app_key, goal, controls=all_controls)       # a v2 grounder uses the control names; a v1 one does not take them
        except TypeError:
            action, reply = ground(img, som, app_key, goal)
        fixed, note = AV.uia_assist(goal, action, {"som": som, "controls": all_controls}, LR.element_at)       # the same UIA-name correction the Agent applies
        final = fixed or action
        lexical = VE.match_element(som, re.sub(r"\(.*?\)", "", c["name"]).strip())
        rows.append({"state": state, "name": c["name"], "goal": goal, "gt": gt["id"], "gt_label": gt.get("label", ""), "seen": c["name"] in seen_names,
                     "pred": (action or {}).get("target_id"), "kind": (action or {}).get("action"), "valid": action is not None,
                     "exact": bool(action and action.get("action") == "click" and action.get("target_id") == gt["id"]),
                     "assisted_exact": bool(final and final.get("action") == "click" and final.get("target_id") == gt["id"]), "assist_changed": bool(fixed),
                     "dense": c["box"][2] <= 28 and c["box"][3] <= 28, "unique_name": sum(1 for x in all_controls if x["name"] == c["name"]) == 1,
                     "lexical": bool(lexical and lexical["id"] == gt["id"]), "chance": 1.0 / max(len(som["elements"]), 1)})
    return {"state": state, "rows": rows, "summary": summarize(rows), "seconds": round(time.time() - t0, 1), "elements": len(som["elements"])}


def _rate(rows: Sequence[Dict[str, Any]], key: str) -> Optional[float]:
    return round(sum(1 for r in rows if r[key]) / len(rows), 3) if rows else None


def summarize(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    def part(rs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        return {"n": len(rs), "exact": _rate(rs, "exact"), "assisted_exact": _rate(rs, "assisted_exact"), "lexical_baseline": _rate(rs, "lexical"), "valid": _rate(rs, "valid"),
                "chance": round(sum(r["chance"] for r in rs) / len(rs), 3) if rs else None}
    return {"all": part(rows), "seen": part([r for r in rows if r["seen"]]), "unseen": part([r for r in rows if not r["seen"]]), "dense_icons": part([r for r in rows if r.get("dense")])}


def merge(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [r for res in results for r in res.get("rows", [])]
    return {"rows": rows, "summary": summarize(rows)}
