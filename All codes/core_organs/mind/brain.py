"""
brain -- the front door: one call that turns a request into a considered plan.

    think("delete all my old emails permanently", app="webapp:mail.example.com", screen=[...labels on screen...])
    think("reply to Priya's email", app="outlook", incoming=<her message>, channel="email_reply", relationship="client", facts=[...])

What it decides, in order, with no model call (each part is a module that can be tested alone):
  1. consequence  - is this plan something to warn about? what will happen, what is the safer way?          (mind.consequence)
  2. kind + order - what kind of job is it and in what order does a professional do it?                      (mind.workflow.skeleton)
  3. the app      - can THIS app do the operations the job needs (from what the scanners found)? if not, which can?   (mind.capabilities)
  4. the voice    - if words will be written: language, register, length, shape, for whom                     (mind.persona)
  5. where it is  - the same job left half done? continue where the screen says it stopped, else start fresh  (mind.workflow.adopt)
Returns the pieces and `say`, the sentence(s) to speak to the person, and `decision`: proceed | ask_first | need_info | resume_or_restart.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core_organs.mind import consequence as CQ
from core_organs.mind import persona as P
from core_organs.mind import workflow as W

_WRITING = {"email", "post", "document"}
_CHANNEL_OF = {"email": "email", "post": "linkedin_post", "document": "document"}


def think(goal: str, app: str = "", screen: Optional[Sequence[str]] = None, app_labels: Optional[Sequence[str]] = None, incoming: str = "", channel: str = "", relationship: str = "",
          facts: Sequence[str] = (), language: str = "", store: Optional[W.Store] = None, plan_provider: Optional[Callable[[], Sequence[Dict[str, Any]]]] = None, title: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {"goal": goal, "app": app}
    say: List[str] = []
    decision = "proceed"

    cq = CQ.critique_goal(goal)
    out["consequence"] = cq
    if cq["gate"] == "confirm":
        decision = "ask_first"
        say.append(cq["heads_up"])

    sk = W.skeleton(goal)
    out["kind"], out["stages"] = sk["kind"], sk["stages"]

    if app_labels is not None:
        from core_organs.mind import capabilities as CP
        can = CP.can_do(app, sk["kind"], app_labels)
        out["app_can"] = can
        if not can["ok"]:
            note = f"{app or 'This app'} shows no {', '.join(can['missing'])} controls, which a {sk['kind']} job needs."
            try:
                better = [d["app"] for d in CP.best_for(sk["kind"], top=3) if d["app"] != app and not d["missing"]]
                out["better_apps"] = better
                if better:
                    note += f" Better suited: {', '.join(better)}."
            except Exception:
                pass
            say.append(note)

    writing = sk["kind"] in _WRITING or bool(channel)
    if writing:
        ch = channel or _CHANNEL_OF.get(sk["kind"], "email")
        brief = P.style_brief(incoming, ch, relationship or "unknown", intent=goal, language=language)
        out["voice"] = brief
        out["writer_prompt"] = P.compose_prompt(brief, facts, incoming)
        if not facts and not incoming:
            decision = "need_info" if decision == "proceed" else decision
            say.append("I need the facts to put in it (what happened, dates, numbers); I will not invent them.")
        else:
            say.append(f"I will write it in {brief['language_name']}, {brief['register']}, at most {brief['max_words']} words" + (f", greeting {brief['greet_name']}" if brief.get("greet_name") else "") + ".")

    if store is not None and plan_provider is not None:
        ad = W.adopt(store, goal, app, list(screen or []), plan_provider, title=title)
        out["workflow"] = {"action": ad["action"], "id": ad["workflow"]["id"], "step": ad["workflow"]["cursor"] + 1, "of": len(ad["workflow"]["steps"]), "why": ad["locate"]["why"]}
        say.append(ad["message"])
        if ad["action"] == "ask":
            decision = "resume_or_restart"
    elif sk["stages"]:
        say.append(f"Order of work: " + "; ".join(f"{s['i'] + 1}. {s['name']}" for s in sk["stages"]) + ".")

    out["decision"], out["say"] = decision, " ".join(say)
    return out


# ---- the natural brain: a teacher it consults, a ledger it learns from, and the switch that turns the teacher off ----------------------------------------
# Every step: the brain's own decision (deterministic fast path, trained picker, local judge) is made first. While the brain is not ready, the TEACHER (Claude on the
# user's key, else a free hosted model) sees the window and the numbered control list and proposes the step; the brain checks it (the control is really in the
# list, the verb exists) and the loop's verifier proves the result. Both answers and the proven outcome go to an append-only ledger; a step the teacher got right
# that was PROVEN is filed into the knowledge base as a procedure. When the brain's own answers agree with the proven teacher steps often enough, mode() turns
# the teacher off by itself. HOJAIGA_BRAIN_MODE = auto (default) | teacher | local | off.
import json as _json
import os as _os
import re as _re
import time as _time
import uuid as _uuid

LEDGER = _os.path.join(_os.environ.get("HOJAIGA_ROOT", r"D:\new_automation"), "data", "ai_root", "brain", "ledger.jsonl")
TEACH_SYSTEM = ("You operate a Windows app for a person. You see the app's window and a numbered list of its controls. Pick the ONE next action that moves the "
                "goal forward. Reply JSON only: {\"index\": <number from the list>, \"verb\": \"click\" | \"type\" | \"key\" | \"done\", \"text\": \"text to type or keys like "
                "ctrl+s, else empty\", \"why\": \"one short sentence\"}. 'done' means the goal is already met on screen. Never pay, send, delete, sign in or change "
                "settings unless the goal itself says so.")
TEACH_VERBS = {"click", "type", "key", "done"}
READY_RATE = float(_os.environ.get("HOJAIGA_BRAIN_READY_RATE", "0.95"))
READY_MIN = int(_os.environ.get("HOJAIGA_BRAIN_READY_MIN", "50"))
READY_WINDOW = int(_os.environ.get("HOJAIGA_BRAIN_READY_WINDOW", "300"))
_READY_CACHE: Dict[str, Any] = {"t": 0.0, "v": None}


def _rows() -> List[Dict[str, Any]]:
    try:
        with open(LEDGER, encoding="utf-8") as fh:
            return [_json.loads(l) for l in fh if l.strip()]
    except (OSError, ValueError):
        return []


def _append(row: Dict[str, Any]) -> None:
    _os.makedirs(_os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(_json.dumps(row, ensure_ascii=False) + "\n")
    _READY_CACHE["t"] = 0.0


def readiness(rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Over the last READY_WINDOW proven teacher steps: how often the brain's own answer was the same control and verb. Ready at READY_RATE over >= READY_MIN."""
    if rows is None and _time.time() - _READY_CACHE["t"] < 30 and _READY_CACHE["v"] is not None:
        return _READY_CACHE["v"]
    rs = rows if rows is not None else _rows()
    steps = {r["id"]: r for r in rs if r.get("kind") == "step"}
    outs = {r["id"]: r for r in rs if r.get("kind") == "outcome"}
    proven = [steps[i] for i in steps if i in outs and outs[i].get("verdict") == "PASS" and steps[i].get("teacher")][-READY_WINDOW:]
    agree = sum(1 for s in proven if s.get("agree"))
    by_who: Dict[str, int] = {}
    for s in steps.values():
        by_who[s.get("used", "?")] = by_who.get(s.get("used", "?"), 0) + 1
    v = {"proven_teacher_steps": len(proven), "brain_agreed": agree, "agree_rate": round(agree / len(proven), 3) if proven else 0.0,
         "ready": len(proven) >= READY_MIN and agree / max(1, len(proven)) >= READY_RATE, "steps_by_decider": by_who,
         "outcomes": {"PASS": sum(1 for o in outs.values() if o.get("verdict") == "PASS"), "other": sum(1 for o in outs.values() if o.get("verdict") != "PASS")}}
    if rows is None:
        _READY_CACHE.update(t=_time.time(), v=v)
    return v


def mode() -> str:
    """teacher | local | off. auto: the teacher until the brain is ready, then local (the teacher is asked again only when the brain has no answer)."""
    m = (_os.environ.get("HOJAIGA_BRAIN_MODE") or "auto").strip().lower()
    if m in ("teacher", "local", "off"):
        return m
    return "local" if readiness()["ready"] else "teacher"


def teach(goal: str, app: str, controls: Sequence[Tuple[str, str]], image_b64: str = "", ask: Optional[Callable[..., Tuple[Optional[str], str]]] = None) -> Optional[Dict[str, Any]]:
    """The teacher's step, CHECKED by the brain: {'index','verb','text','why','who'} or None (no teacher, no usable answer, or an index outside the list).
    `controls` = [(role, name)] in the order shown; `ask(system, prompt, images)` -> (text, who) replaces the gateway (tests)."""
    if not controls:
        return None
    if ask is None:
        from core_organs import organ_37_llm_gateway as GW
        ask = lambda s, p, im: GW.teacher_chat(s, p, im)
    listing = "\n".join(f"{i}. [{r or 'control'}] {n[:80]}" for i, (r, n) in enumerate(controls))
    prompt = f"App: {app or 'unknown'}\nGoal: {goal}\nControls:\n{listing}\nJSON:"
    text, who = ask(TEACH_SYSTEM, prompt, [image_b64] if image_b64 else None)
    m = _re.search(r"\{.*\}", text or "", _re.S)
    if not m:
        return None
    try:
        d = _json.loads(m.group(0))
        idx, verb = int(d.get("index", -1)), str(d.get("verb", "")).lower().strip()
    except (ValueError, TypeError):
        return None
    if not (0 <= idx < len(controls)) or verb not in TEACH_VERBS:              # the brain never acts on a control that is not on screen
        return None
    out = {"index": idx, "verb": verb, "text": str(d.get("text") or ""), "why": str(d.get("why") or "")[:200], "who": who}
    cq = CQ.classify_label(controls[idx][1].lower())
    if cq.get("gate") == "confirm" and CQ.critique_goal(goal).get("gate") != "confirm":
        out["risk"] = cq.get("risk")                                            # a risky control the goal never asked for: the loop's own gate will ask
    return out


def record(app: str, goal: str, controls: Sequence[Tuple[str, str]], teacher: Optional[Dict[str, Any]], local: Optional[Tuple[str, str]], used: str) -> str:
    """One decision in the ledger. `local` = (verb, control name) the brain chose itself; `used` = who decided (the teacher's name, or 'brain')."""
    sid = _uuid.uuid4().hex[:12]
    t_pick = (teacher["verb"], controls[teacher["index"]][1]) if teacher else None
    agree = bool(t_pick and local and t_pick[1].strip().lower() == (local[1] or "").strip().lower()
                 and (t_pick[0] == local[0] or {t_pick[0], local[0]} <= {"click", "invoke"}))
    _append({"kind": "step", "id": sid, "ts": _time.strftime("%Y-%m-%d %H:%M:%S"), "app": app, "goal": goal[:300], "controls": [n[:60] for _r, n in controls[:60]],
             "teacher": {**teacher, "control": controls[teacher["index"]][1]} if teacher else None, "local": list(local) if local else None, "agree": agree, "used": used})
    return sid


def outcome(sid: str, verdict: str, evidence: str = "", rag: Any = None) -> None:
    """The proven result of a recorded step. A teacher step that PASSED is filed into the knowledge base as a learned procedure (what to do, on what, and why)."""
    if not sid:
        return
    _append({"kind": "outcome", "id": sid, "verdict": verdict, "evidence": (evidence or "")[:200], "ts": _time.strftime("%Y-%m-%d %H:%M:%S")})
    if verdict != "PASS":
        return
    step = next((r for r in reversed(_rows()) if r.get("kind") == "step" and r.get("id") == sid), None)
    t = (step or {}).get("teacher")
    if not t:
        return
    try:
        if rag is None:
            from core_organs import rag as R
            rag = R.get_rag()
        app_key = _re.sub(r"[^a-z0-9]+", "_", (step.get("app") or "").lower()).strip("_") or "app"
        rag.proc.ingest_procedure(app_key, step["goal"], [{"text": f"{t['verb']} {t['control']}" + (f" '{t['text']}'" if t.get("text") else ""), "target": t["control"],
                                                            "why": t.get("why", "")}], source_ref=f"teacher:{t.get('who')}:{sid}", trust="teacher_proven")
    except Exception:
        pass
