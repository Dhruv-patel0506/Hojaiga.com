"""
harvest.video_explain -- binds WHAT WAS SAID (transcript), WHAT CHANGED (keyframes + delta box) and WHAT THE SCREEN CONTAINED (Set-of-Marks) into two outputs at once:

    1. RAG entries    the transcript goes to Sub-RAG 3 (grounded steps, procedures) -- the same call the bridge makes, so it is idempotent
    2. training pairs Unsloth-ready conversational records: the pre-action frame + its numbered element list + the goal -> the JSON action the speaker performed (click target_id / hotkey / type)
                      with a verify_expectation made from the delta box (what appeared where). A pair is marked grounded only when the spoken target matches a numbered element.

Replaces the written-guide explainer with a video-aware one: no step is invented -- an action exists only where the speaker said something actionable shortly before the picture changed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Sequence

from .paths import harvest_dir

_SYSTEM_HINT = ("You operate desktop software by reading a numbered list of on-screen elements. Reply with a JSON list of actions: "
                '[{"step": 1, "action": "click|hotkey|type", "target_id": <number or null>, "hotkey": <keys or null>, "text": <text or null>, "verify_expectation": "<what the screen should show next>"}]')


def _tokens(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 1}


def match_element(som: Dict[str, Any], target: str) -> Optional[Dict[str, Any]]:
    """The numbered element the spoken target names: exact label first, then every word of the target inside the label (or the label inside the target)."""
    t = (target or "").strip().lower()
    if not t:
        return None
    tk = _tokens(t)
    best, score = None, 0.0
    for e in som["elements"]:
        lab = (e.get("label") or "").strip().lower()
        if not lab:
            continue
        if lab == t:
            return e
        lk = _tokens(lab)
        if tk and lk and (tk <= lk or lk <= tk):
            s = len(tk & lk) / max(len(tk | lk), 1)
            if s > score:
                best, score = e, s
    return best


def steps_before(segments: Sequence[Dict[str, Any]], t: float, lookback_s: float = 5.0, lookahead_s: float = 1.0) -> List[Dict[str, Any]]:
    """Actionable steps the speaker said in (t - lookback, t + lookahead): the instruction that explains the change at t. Newest last."""
    from core_organs.rag.procedures import extract_steps
    out = []
    for seg in segments:
        s0 = float(seg["start"])
        if t - lookback_s <= s0 <= t + lookahead_s:
            for st in extract_steps(seg["text"], [seg["text"]]):
                out.append(dict(st, t=s0))
    return out


def clean_labels(elements: Sequence[Dict[str, Any]], limit: int = 8) -> List[str]:
    """Element names fit to be shown as 'what appeared': at least 3 letters, mostly alphabetic, no OCR debris ('McC', '|||'), no duplicates."""
    out, seen = [], set()
    for e in elements:
        lab = (e.get("label") or "").strip()
        letters = sum(c.isalpha() for c in lab)
        if len(lab) < 3 or letters < 3 or letters / len(lab) < 0.7 or lab.lower() in seen or re.search(r"[a-z][A-Z]", lab):
            continue
        seen.add(lab.lower())
        out.append(lab)
        if len(out) >= limit:
            break
    return out


def _action(step: Dict[str, Any], target_id: Optional[int], expectation: str) -> Dict[str, Any]:
    if step.get("chord"):
        return {"step": 1, "action": "hotkey", "target_id": None, "hotkey": step["chord"], "text": None, "verify_expectation": expectation}
    if step.get("verb") in ("type", "enter") and step.get("quoted"):
        return {"step": 1, "action": "type", "target_id": target_id, "hotkey": None, "text": step["quoted"][0], "verify_expectation": expectation}
    return {"step": 1, "action": "click", "target_id": target_id, "hotkey": None, "text": None, "verify_expectation": expectation}


def explain_video(rag, app_key: str, video_id: str, segments: Sequence[Dict[str, Any]], keyframes: Sequence[Dict[str, Any]], title: str = "", out_jsonl: str = "", root: str = "",
                  som_fn: Optional[Callable[..., Dict[str, Any]]] = None, scan_delta: bool = True, max_pairs: int = 200, ingest: bool = True) -> Dict[str, Any]:
    """Produce training pairs (+ optionally the RAG entries) for one video. `keyframes` come from video_pipeline.extract_keyframes. `som_fn(image, region=None)` defaults to video_pipeline.som_of_frame."""
    from . import video_pipeline as VP
    som_fn = som_fn or VP.som_of_frame
    root = root or harvest_dir()[0]
    out_jsonl = out_jsonl or os.path.join(root, "training", "ui_training_dataset.jsonl")
    os.makedirs(os.path.dirname(out_jsonl), exist_ok=True)
    seen = set()
    if os.path.isfile(out_jsonl):
        for l in open(out_jsonl, encoding="utf-8"):
            try:
                seen.add(json.loads(l).get("meta", {}).get("pair_id"))
            except Exception:
                pass
    report: Dict[str, Any] = {"video_id": video_id, "keyframes": len(keyframes), "pairs": 0, "grounded": 0, "no_step_nearby": 0, "step_already_used": 0, "duplicates": 0, "som_seconds": 0.0}
    used_steps = set()                                         # an instruction labels the FIRST change it causes; later changes are consequences of later speech, not of this step
    if ingest and segments:
        r = rag.proc.ingest_transcript(app_key, list(segments), video_id, title)
        report["rag_chunks"] = r.inserted + r.updated
    rows = []
    for ev in list(keyframes)[:max_pairs]:
        steps = steps_before(segments, float(ev["t"]))
        if not steps:
            report["no_step_nearby"] += 1
            continue
        step = steps[-1]                                          # the most recent instruction before the change
        skey = (round(step["t"], 2), step["text"])
        if skey in used_steps:
            report["step_already_used"] += 1
            continue
        used_steps.add(skey)
        pair_id = hashlib.sha1(f"{video_id}|{ev['t']}|{step['text']}".encode()).hexdigest()[:16]
        if pair_id in seen:
            report["duplicates"] += 1
            continue
        som = som_fn(ev["pre"])
        report["som_seconds"] += som.get("seconds", 0.0)
        el = match_element(som, step.get("target", "")) or (match_element(som, step["quoted"][0]) if step.get("quoted") else None)
        expectation = f"the screen changes in the region {ev['bbox']}" if ev.get("bbox") else "the screen changes"
        if scan_delta and ev.get("bbox") and ev.get("post"):
            sub = som_fn(ev["post"], region=tuple(ev["bbox"]))     # delta-box scan: only the region that changed is analysed
            report["som_seconds"] += sub.get("seconds", 0.0)
            names = clean_labels(sub["elements"])
            if names:
                expectation = "new on screen: " + ", ".join(names)
        grounded = el is not None or bool(step.get("chord"))
        actions = [_action(step, el["id"] if el else None, expectation)]
        rel = lambda p: os.path.relpath(p, root).replace("\\", "/") if os.path.isabs(p) and p.startswith(root) else p
        rows.append({"messages": [
            {"role": "system", "content": [{"type": "text", "text": _SYSTEM_HINT}]},
            {"role": "user", "content": [{"type": "image", "image": rel(ev["pre"])}, {"type": "text", "text": f"Application: {app_key}\nElements:\n{VP.som_text(som)}\nGoal: {step['text']}"}]},
            {"role": "assistant", "content": [{"type": "text", "text": json.dumps(actions, ensure_ascii=False)}]}],
            "meta": {"pair_id": pair_id, "app_key": app_key, "video_id": video_id, "t": ev["t"], "pre": rel(ev["pre"]), "post": rel(ev.get("post", "")), "delta_bbox": ev.get("bbox"), "grounded": grounded,
                     "source_ref": f"{video_id}@{int(ev['t'])}", "som_elements": len(som["elements"])}})
        report["pairs"] += 1
        report["grounded"] += 1 if grounded else 0
    if rows:
        with open(out_jsonl, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    report["jsonl"] = out_jsonl
    report["som_seconds"] = round(report["som_seconds"], 2)
    return report
