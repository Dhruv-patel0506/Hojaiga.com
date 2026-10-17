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


_CHORD_RX = re.compile(r"\b(?:ctrl|control|shift|alt|cmd|win|fn)\s*\+\s*[a-z0-9]+\b|\bf\d{1,2}\b", re.I)


def _norm_tokens(s: str) -> set:
    """Tokens compared by meaning, not spelling: a shortcut hint in a menu label ('Save Ctrl+S') is dropped, plurals fold ('settings' = 'setting'), 'ok' counts."""
    s = _CHORD_RX.sub(" ", (s or "").lower())
    out = set()
    for w in re.findall(r"[a-z0-9]+", s):
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        if len(w) > 1:
            out.add(w)
    return out


def match_element(som: Dict[str, Any], target: str, min_cover: float = 0.66) -> Optional[Dict[str, Any]]:
    """The numbered element the spoken target names, by normalized token overlap: at least `min_cover` (two of three words) of the target's words are in the label, AND the target accounts for at least half of the label's
    words. 'save' -> 'Save Ctrl+S' and 'save' -> 'Save As' match; 'change font size' -> 'Font size' matches (2 of 3 words). The direction rule stays: 'share file' must NOT match the menu-bar item 'File'
    (1 of 2 words, found in QA as a wrong click label), so a single shared word never carries a multi-word target."""
    t = (target or "").strip().lower()
    if not t:
        return None
    tk = _norm_tokens(t)
    best, score = None, 0.0
    for e in som["elements"]:
        lab = (e.get("label") or "").strip().lower()
        if not lab:
            continue
        if lab == t:
            return e
        lk = _norm_tokens(lab)
        if not tk or not lk or len(lab) < 3:
            continue
        inter = len(tk & lk)
        cover = inter / len(tk)
        if cover < min_cover or inter / len(lk) < 0.5:
            continue
        s_ = cover * (inter / len(lk))                     # exactness: 1.0 for identical word sets
        if s_ > score:
            best, score = e, s_
    return best


def utterances(segments: Sequence[Dict[str, Any]], max_gap_s: float = 1.2, max_words: int = 30) -> List[Dict[str, Any]]:
    """Caption lines re-joined into utterances. Auto-captions break lines mid-sentence ("press the" / "Escape key"); a step extracted from half a sentence is not a step. A line joins the previous one
    when they are close in time, the previous does not end a sentence, and the result stays short."""
    out: List[Dict[str, Any]] = []
    for seg in sorted(segments, key=lambda s: float(s["start"])):
        txt = re.sub(r"\s+", " ", str(seg.get("text", ""))).strip()
        if not txt:
            continue
        s0, s1 = float(seg["start"]), float(seg["start"]) + float(seg.get("duration", 0.0))
        if out and s0 - out[-1]["end"] <= max_gap_s and not re.search(r"[.!?]$", out[-1]["text"]) and len((out[-1]["text"] + " " + txt).split()) <= max_words:
            out[-1]["text"] += " " + txt
            out[-1]["end"] = max(out[-1]["end"], s1)
        else:
            out.append({"start": s0, "end": s1, "text": txt})
    return out


_FILLER = {"this", "that", "these", "those", "it", "them", "one", "ones", "two", "three", "more", "similar", "option", "options", "thing", "things", "way", "time", "bit", "lot", "part", "here",
           "there", "something", "anything", "everything", "the", "a", "an", "your", "my", "our", "its", "any", "some", "other", "another", "same", "next", "first", "last", "left", "right", "just"}
_PREPS = {"of", "in", "on", "at", "to", "for", "with", "from", "about", "like", "up", "down", "out", "off", "over", "into", "onto", "so", "and", "or", "but", "if", "when", "then", "as", "than"}


def is_concrete(step: Dict[str, Any]) -> bool:
    """A step that names something to act on. 'press the', 'type of channel', 'click two more', 'select this option' are speech, not instructions: no chord, and no concrete object."""
    if step.get("chord"):
        return True
    if step.get("quoted"):
        return True
    words = re.findall(r"[A-Za-z][A-Za-z+'\-]*", step.get("target", ""))
    if not words or words[0].lower() in _PREPS:
        return False
    content = [w for w in words if w.lower() not in _FILLER and w.lower() not in _PREPS and len(w) >= 3]
    return bool(content)


def steps_before(segments: Sequence[Dict[str, Any]], t: float, lookback_s: float = 3.0, lookahead_s: float = 1.0) -> List[Dict[str, Any]]:
    """Actionable steps the speaker said in (t - lookback, t + lookahead): the instruction that explains the change at t. Newest last. Works on utterances, not caption lines."""
    from core_organs.rag.procedures import extract_steps
    out = []
    for u in utterances(segments):
        if t - lookback_s <= u["start"] <= t + lookahead_s:
            txt, span = u["text"], max(u["end"] - u["start"], 0.0)
            sts = extract_steps(txt)
            for i, st in enumerate(sts):
                # several steps in one utterance are not all said at its start: place each by where its words sit in the text (speech is roughly uniform), so "click File ... then press Ctrl+S" is two moments
                pos = txt.lower().find(str(st.get("text", ""))[:24].lower())
                frac = pos / max(len(txt), 1) if pos >= 0 else i / max(len(sts), 1)
                out.append(dict(st, t=u["start"] + frac * span))
    return out


def clean_labels(elements: Sequence[Dict[str, Any]], limit: int = 8) -> List[str]:
    """Element names fit to be shown as 'what appeared': at least 3 letters, mostly alphabetic, no OCR debris ('McC', '|||'), no duplicates."""
    out, seen = [], set()
    for e in elements:
        lab = (e.get("label") or "").strip()
        letters = sum(c.isalpha() for c in lab)
        if len(lab) < 3 or letters < 3 or letters / len(lab) < 0.7 or lab.lower() in seen or re.search(r"[a-z][A-Z]|[\[\]{}|\<>~^`]", lab):
            continue
        seen.add(lab.lower())
        out.append(lab)
        if len(out) >= limit:
            break
    return out


def goal_text(step: Dict[str, Any]) -> str:
    """The instruction as a short goal: from its verb to the end of the first clause (<= 12 words), not the whole run-on caption sentence."""
    txt = step.get("text", "")
    m = re.search(r"\b" + re.escape(step.get("verb", "")) + r"\b", txt, re.I) if step.get("verb") else None
    txt = txt[m.start():] if m else txt
    head = re.split(r"\b(?:so|which|that will|and then|in order|because)\b|[,.;!?]", txt, maxsplit=1)[0].strip()
    return " ".join((head or txt).split()[:12])


def _action(step: Dict[str, Any], target_id: Optional[int], expectation: str) -> Dict[str, Any]:
    if step.get("chord"):
        return {"step": 1, "action": "hotkey", "target_id": None, "hotkey": step["chord"], "text": None, "verify_expectation": expectation}
    if step.get("verb") in ("type", "enter") and step.get("quoted"):
        return {"step": 1, "action": "type", "target_id": target_id, "hotkey": None, "text": step["quoted"][0], "verify_expectation": expectation}
    return {"step": 1, "action": "click", "target_id": target_id, "hotkey": None, "text": None, "verify_expectation": expectation}


def build_row(root: str, app_key: str, video_id: str, ev: Dict[str, Any], som: Dict[str, Any], goal: str, actions: List[Dict[str, Any]], pair_id: str, grounded: bool, ui_checked: Optional[bool],
              extra_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One Unsloth-shaped training record (shared by the video explainer and the local recorder, so both emit exactly the same format). `ev` carries pre / post paths, t and the delta bbox."""
    from . import video_pipeline as VP
    rel = lambda p: os.path.relpath(p, root).replace("\\", "/") if os.path.isabs(p) and p.startswith(root) else p
    meta = {"pair_id": pair_id, "app_key": app_key, "video_id": video_id, "t": ev["t"], "pre": rel(ev["pre"]), "post": rel(ev.get("post", "")), "delta_bbox": ev.get("bbox"), "grounded": grounded, "ui_frames": ui_checked,
            "source_ref": f"{video_id}@{int(ev['t'])}", "som_elements": len(som["elements"])}
    meta.update(extra_meta or {})
    return {"messages": [
        {"role": "system", "content": [{"type": "text", "text": _SYSTEM_HINT}]},
        {"role": "user", "content": [{"type": "image", "image": rel(ev["pre"])}, {"type": "text", "text": f"Application: {app_key}\nElements:\n{VP.som_text(som)}\nGoal: {goal}"}]},
        {"role": "assistant", "content": [{"type": "text", "text": json.dumps(actions, ensure_ascii=False)}]}],
        "meta": meta}


def explain_video(rag, app_key: str, video_id: str, segments: Sequence[Dict[str, Any]], keyframes: Sequence[Dict[str, Any]], title: str = "", out_jsonl: str = "", root: str = "",
                  som_fn: Optional[Callable[..., Dict[str, Any]]] = None, scan_delta: bool = True, max_pairs: int = 200, ingest: bool = True, gate: Any = None, min_elements: int = 1, prefilter: Any = None) -> Dict[str, Any]:
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
    report: Dict[str, Any] = {"video_id": video_id, "keyframes": len(keyframes), "pairs": 0, "grounded": 0, "no_step_nearby": 0, "sparse_frame": 0, "prefiltered": 0, "not_ui_frame": 0, "unverified_frame": 0, "not_concrete": 0, "step_already_used": 0, "duplicates": 0, "som_seconds": 0.0}
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
        concrete = [s_ for s_ in steps if is_concrete(s_)]
        if not concrete:
            report["not_concrete"] += 1                           # speech, not an instruction: no OCR time is spent on it
            continue
        earlier = [s_ for s_ in concrete if s_["t"] <= float(ev["t"])]
        step = (earlier or concrete)[-1]                          # the most recent concrete instruction BEFORE the change (one said just after it is the fallback, never the preference)
        skey = (round(step["t"], 2), step["text"])
        if skey in used_steps:
            report["step_already_used"] += 1
            continue
        used_steps.add(skey)
        pair_id = hashlib.sha1(f"{video_id}|{ev['t']}|{step['text']}".encode()).hexdigest()[:16]
        if pair_id in seen:
            report["duplicates"] += 1
            continue
        if prefilter is not None:                                  # milliseconds, before any OCR or GPU time: an obvious presenter close-up / flat card
            keep, _why = prefilter(ev["pre"])
            if not keep:
                report["prefiltered"] += 1
                used_steps.discard(skey)
                continue
        # the frames must show a software UI. A cut to a presenter / title card / motion graphic is not an interface transition. gate=None means "not checked" and is recorded as such.
        ui_checked = None
        if gate is not None:
            for tag in ("pre", "post"):
                if tag == "post" and not ev.get("post"):
                    continue
                verdict, _why = gate.check(ev[tag])
                if verdict is None:
                    report["unverified_frame"] += 1
                    break
                if verdict is False:
                    report["not_ui_frame"] += 1
                    break
            else:
                ui_checked = True
            if ui_checked is not True:
                used_steps.discard(skey)                           # the instruction is still available for a later change that DOES show the interface
                continue
        som = som_fn(ev["pre"])
        report["som_seconds"] += som.get("seconds", 0.0)
        if len(som["elements"]) < min_elements:                    # a zoomed tooltip, a blank canvas: a UI, but with too little of it to learn a grounding from
            report["sparse_frame"] += 1
            used_steps.discard(skey)
            continue
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
        rows.append(build_row(root, app_key, video_id, ev, som, goal_text(step), actions, pair_id, grounded, ui_checked))
        report["pairs"] += 1
        report["grounded"] += 1 if grounded else 0
    if rows:
        with open(out_jsonl, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    report["jsonl"] = out_jsonl
    report["som_seconds"] = round(report["som_seconds"], 2)
    return report
