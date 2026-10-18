"""
rag.logic_chains -- a tutorial is not a list of facts, it is DECISION LOGIC: what must be true before a step, what the step does, what should be true after it, and what to do when it is not.

    precondition_state  ->  action (click / hotkey / menu path)  ->  expected_post_state  ->  fallback_if_blocked

From the ordered steps of an illustrated tutorial (text, the control names and key combinations each step names, and the screen shown with each step) this module builds those chains and writes each link
into the stores that hold that kind of knowledge, so a single retrieval can answer "can I do this here, how, what will I see, and what if it does not work":

    Sub-RAG 1 icons       the control's picture (cropped from the tutorial screenshot) <-> its name
    Sub-RAG 2 UI graph    state(labels of the screen before) --action--> state(labels after): the PREREQUISITE edge ("Insert Chart needs the Insert tab open")
    Sub-RAG 3 procedures  the chain as one readable step: 'PRECONDITION ... | ACTION ... | EXPECT ... | IF BLOCKED ...'
    Sub-RAG 4 hotkeys     the key combination for the same goal, so a hidden / collapsed button can be replaced by the shortcut (multi-path equivalence: icon = menu path = hotkey)
    Sub-RAG 5 recovery    'If you do not see X ...' / troubleshooting sentences, tied to the step they belong to

Nothing here knows an application: the labels come from the screenshot scan, the names and keys from the step text.
"""
from __future__ import annotations

import contextlib
import hashlib
import re
import time
from typing import Any, Dict, List, Optional, Sequence

KEY_RX = re.compile(r"\b((?:Ctrl|Control|Alt|Shift|Win|Cmd|Command|Option)(?:\s*\+\s*[A-Za-z0-9]{1,6}|\s*\+\s*(?:Shift|Alt|Tab|Enter|Esc|Space|Del|F\d{1,2}))+)\b")
WHERE_RX = re.compile(r"\b(?:in|on|under|from|within|inside)\s+the\s+([A-Z][\w &/-]{1,28}?)\s+(tab|menu|dialog|panel|window|ribbon|toolbar|pane|sidebar|page|section)\b", re.I)
PATH_RX = re.compile(r"\b([A-Z][\w &-]{1,24}(?:\s*(?:>|→|›)\s*[A-Z][\w &-]{1,24}){1,4})")
FALLBACK_RX = re.compile(r"^(?:if|when|in case|should|otherwise|note:?\s*if|tip:?\s*if)\b[^.!?]{8,220}[.!?]", re.I)
NOT_SEEN_RX = re.compile(r"\b(?:don'?t|do not|cannot|can'?t|unable to|does not|doesn'?t) (?:see|find|have|appear|show|work)\b", re.I)


def action_of(step: Dict[str, Any]) -> Dict[str, Any]:
    """What the step DOES: a click on a named control, a hotkey, or a menu path, with every alternative the text gives for the same goal."""
    text = step.get("text", "")
    names = list(step.get("names") or [])
    keys = list(step.get("keys") or []) or [k if isinstance(k, str) else k[0] for k in KEY_RX.findall(text)]
    mp = PATH_RX.search(text)
    path = [p.strip() for p in re.split(r"\s*(?:>|→|›)\s*", mp.group(1))] if mp else []
    if path:                                                                     # 'Open File > Export': the verb in front of the first menu is not part of its name
        path[0] = re.sub(r"^(?:(?:click|select|choose|open|go to|press|then|use|navigate to|on|in|the|and)\s+)+", "", path[0], flags=re.I).strip() or path[0]
        path = [(re.match(r"[A-Z][\w-]*(?:\s+[A-Z][\w-]*){0,3}", p) or [p])[0] for p in path]     # a menu name is its capitalised words: 'PDF to finish' -> 'PDF'
    kind = "click" if names else ("hotkey" if keys else ("menu_path" if path else ("act" if step.get("verbatim") and text else "observe")))
    return {"kind": kind, "target": names[0] if names else (path[-1] if path else (text[:90] if kind == "act" else "")), "keys": keys[:2], "menu_path": path, "alternatives": {"names": names[1:4], "keys": keys[1:3]}}


def precondition_of(step: Dict[str, Any], labels_before: Sequence[str]) -> Dict[str, Any]:
    """What must be true BEFORE: the place the text names ('in the Insert tab') and the control labels visible on the screen shown with the step."""
    m = WHERE_RX.search(step.get("text", ""))
    return {"where": (f"{m.group(1).strip()} {m.group(2).lower()}" if m else ""), "screen_labels": [l for l in labels_before if l][:10]}


def expectation_of(step: Dict[str, Any], next_step: Optional[Dict[str, Any]], labels_before: Sequence[str], labels_after: Sequence[str]) -> Dict[str, Any]:
    """What should be true AFTER: labels that appear on the next screen and were not on this one, and the next step's own opening words."""
    before = {l.lower() for l in labels_before}
    new = [l for l in labels_after if l and l.lower() not in before][:8]
    return {"new_labels": new, "next": (next_step or {}).get("text", "")[:120]}


def fallbacks_of(page_text: str, step: Dict[str, Any]) -> List[str]:
    """'If you do not see X, ...' sentences: the ones in the step itself, and the page's troubleshooting sentences that name a control the step names."""
    out: List[str] = []
    for s in re.split(r"(?<=[.!?])\s+", step.get("text", "")):
        if FALLBACK_RX.match(s.strip()) or NOT_SEEN_RX.search(s):
            out.append(s.strip()[:240])
    names = [n.lower() for n in (step.get("names") or [])]
    if names:
        for s in re.split(r"(?<=[.!?])\s+", page_text):
            s = s.strip()
            if (FALLBACK_RX.match(s) or NOT_SEEN_RX.search(s)) and any(n in s.lower() for n in names) and s not in out:
                out.append(s[:240])
    return out[:3]


def build_chains(steps: Sequence[Dict[str, Any]], labels: Sequence[Sequence[str]], page_text: str = "") -> List[Dict[str, Any]]:
    """One chain per step. `labels[i]` = the control labels of the screen shown with step i (empty when the step has no picture)."""
    chains = []
    for i, st in enumerate(steps):
        before = labels[i] if i < len(labels) else []
        after = labels[i + 1] if i + 1 < len(labels) else []
        a = action_of(st)
        if a["kind"] == "observe" and not st.get("text"):
            continue
        chains.append({"step": i + 1, "text": st.get("text", "")[:240], "precondition": precondition_of(st, before), "action": a,
                       "expected": expectation_of(st, steps[i + 1] if i + 1 < len(steps) else None, before, after), "fallback": fallbacks_of(page_text, st)})
    return chains


def chain_text(c: Dict[str, Any]) -> str:
    a = c["action"]
    act = {"click": f"click '{a['target']}'", "hotkey": f"press {' or '.join(a['keys'])}", "menu_path": "choose " + " > ".join(a["menu_path"]), "act": "do: " + a["target"], "observe": "look at the screen"}[a["kind"]]
    if a["kind"] == "click" and a["keys"]:
        act += f" (or press {a['keys'][0]})"
    pre = c["precondition"]["where"] or ("with these controls visible: " + ", ".join(c["precondition"]["screen_labels"][:5]) if c["precondition"]["screen_labels"] else "any state")
    exp = ("new on screen: " + ", ".join(c["expected"]["new_labels"][:5])) if c["expected"]["new_labels"] else (c["expected"]["next"][:80] or "the next step becomes possible")
    fb = " ; ".join(c["fallback"]) if c["fallback"] else "none given: re-check the screen, then use the keyboard route or Escape and retry"
    return f"PRECONDITION: {pre} | ACTION: {act} | EXPECT: {exp} | IF BLOCKED: {fb}"


def _snap(labels: Sequence[str]) -> Dict[str, Any]:
    return {"nodes": [{"name": l, "ctype": "button", "offscreen": False} for l in labels if l][:60], "role": "main"}


def write(rag: Any, app_key: str, app_name: str, chains: Sequence[Dict[str, Any]], labels: Sequence[Sequence[str]], source_url: str, title: str = "",
          crops: Optional[Sequence[Any]] = None) -> Dict[str, int]:
    """Each link of each chain into the store that holds that kind of knowledge. Idempotent (the stores dedupe on content)."""
    n = {"procedures": 0, "edges": 0, "hotkeys": 0, "playbooks": 0, "icons": 0}
    if rag is None or not chains:
        return n
    with contextlib.suppress(Exception):
        steps = [{"text": chain_text(c), "target": c["action"]["target"] or None, "route_hint": "hotkey" if c["action"]["kind"] == "hotkey" else "control_click"} for c in chains]
        r = rag.proc.ingest_procedure(app_key, (title or f"How to use {app_name}")[:150] + " (logic chain)", steps, source_url, trust="web")
        n["procedures"] += r.inserted + r.updated
    from core_organs.rag import Outcome, PlanStep
    from core_organs.rag.lexicon import command_id
    for c in chains:
        a = c["action"]
        i = c["step"] - 1
        if a["target"]:
            with contextlib.suppress(Exception):
                rag.lex.add_command(app_key, a["target"], source="web", trust="learned")
        if a["kind"] in ("click", "hotkey") and i + 1 < len(labels) and labels[i] and labels[i + 1]:
            with contextlib.suppress(Exception):                           # the prerequisite edge: the screen with these labels --action--> the screen with those
                src = rag.localize(app_key, _snap(labels[i])).state_id
                cid = command_id(app_key, a["target"] or " ".join(a["keys"]))
                route = "control_click" if a["kind"] == "click" else "hotkey"
                args = {"label": a["target"], "kind": "tutorial"} if a["kind"] == "click" else {"label": c["text"][:60], "keys": a["keys"][0] if a["keys"] else ""}
                rag.observe(Outcome(f"tutorial-{hashlib.sha1(source_url.encode()).hexdigest()[:8]}", app_key, PlanStep(cid, route, args, None, "", 0.6, "allow"), src_state=src, observed_snapshot=_snap(labels[i + 1]),
                                    ok=True, effect=chain_text(c)[:200], latency_ms=0.0, failure_code=""))
                n["edges"] += 1
        if a["keys"] and a["target"]:
            with contextlib.suppress(Exception):                           # icon = menu path = hotkey for ONE goal
                from core_organs.harvest import bridge as BR
                BR.ingest_hotkeys(rag, [{"app_name": app_name, "app_key": app_key, "action": a["target"], "shortcut": a["keys"][0], "source": "web_table", "url": source_url}])
                n["hotkeys"] += 1
        for fb in c["fallback"]:
            with contextlib.suppress(Exception):
                rag.rec.upsert([{"app_key": app_key, "failure_code": "tutorial_fallback", "message_template": fb, "signature": hashlib.sha1((app_key + fb).encode()).hexdigest()[:12],
                                 "resolution": [{"action": "follow_text", "text": fb, "step": c["step"]}], "source": source_url}])
                n["playbooks"] += 1
        if crops and i < len(crops) and crops[i] is not None and a["target"] and rag.icons is not None:
            with contextlib.suppress(Exception):
                if rag.icons.learn(a["target"], "web", crop=crops[i], app_key=app_key):
                    n["icons"] += 1
    return n
