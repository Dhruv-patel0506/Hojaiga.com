"""
task_runner.py - give a task in plain words, walk away, get an HONEST result.

    from core_organs.task_runner import run_task
    r = run_task("type hello world; save the file as C:\\temp\\a.txt", app="Notepad")
    r["status"]   # DONE | UNVERIFIED | FAILED | ESCALATED     (never DONE without checked evidence)

Pipeline: parse the words into steps -> every step gets a MACHINE-CHECKABLE postcondition derived from the
words themselves (a path to save to => the file must exist; text to type => the control must hold it; an
'expect ...' clause => the UI must show it) -> run on a FRESH hidden window (never an existing window the user
may be using) -> verify each step from perception -> report with evidence.

Why it exists: the old loop treated "the UI changed" as success, so clicking the File menu counted as "saved
the file" and two tasks claimed success with no file on disk. Here a step with only weak evidence can never
make a task DONE; the best it can earn is UNVERIFIED, which says so.

Step grammar (plain words; ';' or ' then ' separates steps):
    type <text>                       -> value_contains <text>
    save [the file|image] as <path>   -> file_exists <path>
    press|click|open <label>          -> weak: ui_changed  (label matched against the live UI incl. aliases
                                          such as 2 -> "Two", * -> "Multiply by", = -> "Equals")
    expect <text>                     -> strong: some control name/value contains <text>
"""

from __future__ import annotations

import ctypes
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

_u32 = ctypes.windll.user32 if os.name == "nt" else None

# ------------------------------------------------------------------ label matching (generic UI vocabulary)

_DIGIT_WORDS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
                "6": "six", "7": "seven", "8": "eight", "9": "nine"}
_SYMBOL_WORDS = {"*": "multiply by", "x": "multiply by", "times": "multiply by", "multiply": "multiply by",
                 "/": "divide by", "divide": "divide by", "÷": "divide by", "+": "plus", "add": "plus",
                 "-": "minus", "subtract": "minus", "=": "equals", "equal": "equals", ".": "decimal separator",
                 "%": "percent", "c": "clear", "ce": "clear entry"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9&+*/=.%÷ ]", "", (s or "").lower().replace("&amp;", "&")).strip()


def label_variants(label: str) -> List[str]:
    """The names a control might carry for what a person calls `label`."""
    base = _norm(label)
    out = [base]
    if base in _DIGIT_WORDS:
        out.append(_DIGIT_WORDS[base])
    if base in _SYMBOL_WORDS:
        out.append(_SYMBOL_WORDS[base])
    if base.endswith(" button") or base.endswith(" key") or base.endswith(" page") or base.endswith(" tab"):
        out.append(base.rsplit(" ", 1)[0])
    return list(dict.fromkeys(v for v in out if v))


def match_label(label: str, candidates: List[Tuple[Any, str]]) -> Optional[Any]:
    """Best candidate for `label`: exact variant > name starts with variant > word overlap. Returns the payload."""
    variants = label_variants(label)
    best, best_score = None, 0.0
    for payload, name in candidates:
        n = _norm(name)
        if not n:
            continue
        score = 0.0
        for v in variants:
            if n == v:
                score = max(score, 100.0)
            elif n.startswith(v + " ") or n.startswith(v):
                score = max(score, 70.0 - min(len(n) - len(v), 20))
            elif v in n and len(v) >= 4:
                score = max(score, 50.0 - min(len(n) - len(v), 30))
        if score == 0:                                  # word overlap as the weakest signal
            vt, nt = set(variants[0].split()), set(n.split())
            if vt and len(vt & nt) / len(vt) >= 0.6 and len(vt) >= 2:
                score = 30.0
        if score > best_score:
            best, best_score = payload, score
    return best if best_score >= 30 else None


# ------------------------------------------------------------------ parsing

SPLIT_RE = re.compile(r"\s*;\s*|\s+then\s+|\s*\n\s*", re.I)
SAVE_RE = re.compile(r"^save(?:\s+(?:the|this|my))?(?:\s+\w+)?(?:\s+it)?\s+as\s+(.+)$", re.I)
EXPECT_RE = re.compile(r"^(?:expect|verify|check)\s+(?:that\s+)?(?:the\s+)?(?:display\s+|screen\s+|result\s+)?"
                       r"(?:shows?|reads?|contains?|is|has)?\s*(.+)$", re.I)
TYPE_RE = re.compile(r"^(?:type|write|enter)\s+(?:the\s+text\s+)?(.+)$", re.I)
PRESS_RE = re.compile(r"^(?:press|click|tap|hit|select|choose|open|go to|invoke)\s+(?:the\s+)?(.+)$", re.I)


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] in "\"'“‘" and s[-1] in "\"'”’":
        s = s[1:-1]
    return s.strip()


def parse_task(text: str) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    for raw in [p for p in SPLIT_RE.split(text or "") if p and p.strip()]:
        raw = raw.strip().rstrip(".")
        if (m := SAVE_RE.match(raw)):
            steps.append({"kind": "save", "path": _unquote(m.group(1)), "raw": raw})
        elif (m := EXPECT_RE.match(raw)):
            steps.append({"kind": "expect", "text": _unquote(m.group(1)), "raw": raw})
        elif (m := TYPE_RE.match(raw)):
            steps.append({"kind": "type", "text": _unquote(m.group(1)), "raw": raw})
        elif (m := PRESS_RE.match(raw)):
            steps.append({"kind": "press", "label": _unquote(m.group(1)), "raw": raw})
        else:
            steps.append({"kind": "unknown", "raw": raw})
    return steps


def to_leaves(steps: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Template leaf steps (same shape the TemplateRunner already executes + verifies) and a list of problems."""
    leaves: List[Dict[str, Any]] = []
    problems: List[str] = []
    for i, s in enumerate(steps):
        k = s["kind"]
        sid = f"s{i + 1}_{k}"
        if k == "type":
            leaves.append({"id": sid, "goal": s["raw"], "risk": "E1", "unwind": "undo",
                           "do": [{"verb": "type", "text": s["text"], "target_role": "document|edit"}],
                           "post": [{"kind": "value_contains", "text": s["text"]}], "retries": 2, "strong": True})
        elif k == "save":
            leaves.append({"id": sid + "_open", "goal": "open the save dialog", "risk": "E1", "unwind": "cancel the dialog",
                           "do": [{"verb": "key", "keys": "ctrl+s", "expect_popup": "save as"}],
                           "post": [{"kind": "window_opened"}], "retries": 2})
            leaves.append({"id": sid + "_path", "goal": f"save as {s['path']}", "risk": "E1", "unwind": "delete the created file",
                           "do": [{"verb": "file_dialog", "path": s["path"]}],
                           "post": [{"kind": "file_exists", "path": s["path"]}], "retries": 1, "strong": True})
        elif k == "press":
            leaves.append({"id": sid, "goal": s["raw"], "risk": "E1", "unwind": "none",
                           "do": [{"verb": "invoke", "name": s["label"], "label": s["label"]}],
                           "post": [{"kind": "ui_changed"}], "retries": 2, "weak": True})
        elif k == "expect":
            leaves.append({"id": sid, "goal": s["raw"], "risk": "E1", "do": [],
                           "post": [{"kind": "element_present", "name": s["text"]}], "retries": 0, "strong": True})
        else:
            problems.append(f"could not understand step: '{s['raw']}'")
    return leaves, problems


# ------------------------------------------------------------------ the runner

def _acquire_window(app: str, allow_visible: bool) -> Dict[str, Any]:
    """A window we may safely work on: a FRESH hidden instance whenever one can be made; an existing one only
    when the user cannot see it. Never an existing window in the user's view."""
    from core_organs import universal_scan as us
    from core_organs import desktop_grounding as dg
    from core_organs import background_window as bw
    info: Dict[str, Any] = {"hwnd": 0, "launched": False, "note": ""}
    li = us.launch_hidden(app)
    if li.get("hwnd"):
        info.update(hwnd=li["hwnd"], launched=True, note="fresh hidden instance")
        return info
    existing = dg.DesktopGrounding().find_window(app) or 0
    if existing and (allow_visible or not bw.user_can_see(existing)):
        info.update(hwnd=existing, note="existing window (not in the user's view)")
    elif existing:
        info.update(note="the app is already open in your view; refusing to drive it without permission")
    else:
        info.update(note="no window could be created")
    return info


def run_task(task: str, app: str, *, allow_visible: bool = False, model=None, close_when_done: bool = True) -> Dict[str, Any]:
    """Run `task` on `app` and return an honest report. status: DONE | UNVERIFIED | FAILED | ESCALATED."""
    from core_organs import organ_48_app_behavior_model as bm
    from core_organs import background_window as bw
    from core_organs import universal_scan as us
    t0 = time.time()
    rep: Dict[str, Any] = {"task": task, "app": app, "status": "FAILED", "steps": [], "evidence": []}
    steps = parse_task(task)
    leaves, problems = to_leaves(steps)
    rep["parsed"] = [{k: v for k, v in s.items() if k != "raw"} | {"raw": s["raw"][:60]} for s in steps]
    if problems or not leaves:
        rep.update(status="ESCALATED", reason="; ".join(problems) or "no steps", elapsed_s=round(time.time() - t0, 2))
        return rep
    model = model or bm.get_model()
    w = _acquire_window(app, allow_visible)
    rep["window"] = w["note"]
    rep["hwnd"] = w["hwnd"]
    hwnd = w["hwnd"]
    if not hwnd:
        rep.update(status="ESCALATED", reason=w["note"], elapsed_s=round(time.time() - t0, 2))
        return rep
    bw.pin_user_window(_u32.GetForegroundWindow())
    key = bm._app_key(app)
    tpl = bm.TemplateMatch(tpl_id="adhoc", app_key=key, name="adhoc task", steps=leaves, source="adhoc", confidence=0.5, score=1.0)
    runner = bm.TemplateRunner(model)
    run_id = "task_" + str(int(t0))
    results = []
    try:
        with bw.BackgroundSession(hwnd) as sess:
            rep["window_mode"] = sess.mode or "visible"
            from core_organs.universal_scan import wait_tree_ready
            rep["tree_nodes_when_ready"] = wait_tree_ready(hwnd)       # act only once the UI has populated
            for leaf in leaves:
                lr = runner.run_leaf(app, lambda h=hwnd: h if _u32.IsWindow(h) else 0, tpl, leaf, {}, run_id=run_id)
                results.append((leaf, lr))
                rep["steps"].append({"step": leaf["goal"][:50], "verdict": lr.verdict, "attempts": lr.attempts,
                                     "latency_s": lr.latency_s, "effectors": lr.effectors, "evidence": lr.evidence[:140]})
                if lr.verdict != "PASS":
                    break
    except Exception as exc:
        rep["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    finally:
        bw.unpin_user_window()
    passed = [lr.verdict == "PASS" for _, lr in results]
    all_ran = len(results) == len(leaves) and all(passed)
    strong_ok = [leaf.get("strong") for leaf, lr in results if lr.verdict == "PASS" and leaf.get("strong")]
    if all_ran and strong_ok:
        rep["status"] = "DONE"
    elif all_ran:
        rep["status"] = "UNVERIFIED"
        rep["evidence"].append("every step ran, but none had a strong postcondition (only 'the UI changed'); add an 'expect ...' clause to make it verifiable")
    elif any(lr.verdict == "ESCALATED" for _, lr in results):
        rep["status"] = "ESCALATED"
    else:
        rep["status"] = "FAILED"
    if not all_ran and results:
        rep["blocked_at"] = results[len(results) - 1][0]["goal"][:60]
    if w["launched"] and close_when_done:
        rep["closed"] = us.close_window(hwnd, discard_unsaved=True)
    rep["elapsed_s"] = round(time.time() - t0, 2)
    return rep
