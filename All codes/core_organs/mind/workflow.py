"""
workflow -- a task as steps that survive the person leaving it half done, and several tasks at once.

    skeleton(goal)                       -> the professional ORDER of stages for this kind of task (document, email, post, drawing, table, form, research ...), each with a query the RAG can answer per app
    new(goal, app, steps)                -> a workflow (steps = what a procedure from the RAG gives: text / target / expect)
    locate(wf, screen_labels, title)     -> where is the work NOW: resume at step k, fresh start, done already, reopen the menu, or lost (ask)
    adopt(store, goal, app, labels, plan)-> same task already open? continue it where the screen says it stopped; otherwise start fresh (and archive the stale one)
    Scheduler                            -> several workflows: one running per app lane, priority, fair turns, hands off a window the person is using

Nothing here knows an app. Where the task stopped is read from what is ON SCREEN compared with what each step should have left behind.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

DEFAULT_DIR = os.environ.get("HOJAIGA_WORKFLOW_DIR", r"D:\new_automation\data\ai_root\workflows")

# ---- the order a professional does it in, by kind of task. A stage names what is produced (so it can be checked) and the question to ask the RAG for the app in front of us.
_KINDS: List[Tuple[str, str, List[Tuple[str, str, str]]]] = [
    ("email", r"\b(email|e-mail|mail|reply|respond|inbox|gmail|outlook)\b", [
        ("read the thread", "every question and deadline listed", "open and read message"),
        ("decide what is being asked", "the asks in order, who owns each", ""),
        ("draft in the right voice", "a draft that fits the brief (language, register, length)", "compose new message"),
        ("check the draft", "recipients, attachments, tone, facts verified", "check recipients attachment"),
        ("send (the person confirms)", "sent, or left as a draft", "send message")]),
    ("post", r"\b(linkedin|post|tweet|blog|publish|article|caption|newsletter|announce)\b", [
        ("pick the one point and the reader", "a one-line message and who it is for", ""),
        ("write the hook and body", "a first line that stands alone, short paragraphs, one concrete example", "create new post"),
        ("check against the channel", "length, hashtags, no filler, facts from the person only", ""),
        ("preview", "how it will look to others", "preview post"),
        ("publish (the person confirms)", "published, or kept as a draft", "publish post")]),
    ("document", r"\b(document|report|proposal|spec|doc|essay|letter|resume|cv|memo|minutes|handbook|manual|documentation|readme|brief)\b", [
        ("define purpose and reader", "who reads it and what they do after", ""),
        ("outline", "headings in a logical order", "create outline heading styles"),
        ("draft each section", "every heading has its text", "type text in document"),
        ("add tables, figures, lists", "a table for every comparison, numbered steps for every procedure", "insert table"),
        ("format", "styles instead of manual formatting, consistent fonts, page numbers, contents", "apply heading style format paragraph"),
        ("proofread and save", "spelling, names, numbers checked; file saved and named", "save as")]),
    ("table", r"\b(table|spreadsheet|sheet|excel|csv|grid|tabulate|budget|tracker|invoice|schedule|timetable)\b", [
        ("decide the columns", "one idea per column, a header for each", ""),
        ("enter or import the rows", "data in, one row per item", "enter data cells"),
        ("add formulas and totals", "totals and checks as formulas, not typed numbers", "insert formula sum"),
        ("format", "header style, number formats, column widths, freeze the header", "format cells header"),
        ("sort, filter, chart if it helps", "the answer is visible without reading every row", "sort filter chart"),
        ("save", "file saved and named", "save as")]),
    ("drawing", r"\b(draw|sketch|paint|illustrat\w*|diagram|logo|design|model|3d|render|flowchart|poster|icon|shape)\b", [
        ("decide the subject and its parts", "a list of parts with rough size and position", ""),
        ("block in the big shapes", "the silhouette reads as the subject", "draw shape tool"),
        ("refine proportions", "parts in proportion and joined", "resize move shape"),
        ("colour and shade", "a palette of few colours, light direction consistent", "fill colour"),
        ("label or annotate", "text where it helps", "add text label"),
        ("check against the brief and export", "looks like the request; saved", "export save")]),
    ("form", r"\b(form|apply|application|register|registration|sign\s*up|checkout|booking|reservation|survey|questionnaire)\b", [
        ("collect what is needed", "every required field has a value from the person", ""),
        ("fill in order", "fields filled top to bottom, validation messages read", "fill field"),
        ("review", "everything re-read against the source", ""),
        ("submit (the person confirms)", "submitted, confirmation noted", "submit")]),
    ("research", r"\b(research|find out|look up|compare|investigate|summari[sz]e|learn about|what is|explain)\b", [
        ("turn the question into things to find", "3 to 6 specific questions", ""),
        ("gather from sources", "each answer with where it came from", "search"),
        ("cross-check", "the claims that matter agree in two places", ""),
        ("write it up", "the answer first, then support, then what is uncertain", "")]),
]


def skeleton(goal: str) -> Dict[str, Any]:
    g = (goal or "").lower()
    scored = []
    for kind, rx, stages in _KINDS:
        n = len(re.findall(rx, g))
        if n:
            scored.append((n, kind, stages))
    if not scored:
        return {"kind": "general", "stages": [{"i": 0, "name": "understand the goal", "produces": "a restatement the person agrees with", "query": ""},
                                              {"i": 1, "name": "do it in the smallest safe steps", "produces": "each step verified on screen", "query": ""},
                                              {"i": 2, "name": "check the result against the goal", "produces": "the result matches what was asked", "query": ""}]}
    scored.sort(key=lambda x: -x[0])
    n, kind, stages = scored[0]
    return {"kind": kind, "also": [k for _, k, _ in scored[1:]],
            "stages": [{"i": i, "name": s[0], "produces": s[1], "query": s[2]} for i, s in enumerate(stages)]}


# ---- matching what is on screen with what a step needs ----------------------------------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", re.sub(r"\s+", " ", (s or "").lower())).strip()


def _tokens(s: str) -> set:
    return {t for t in _norm(s).split() if len(t) > 1}


def same_label(a: str, b: str) -> bool:
    """Labels are cut at different lengths by different scanners: equal, one starts with the other, or most words shared."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    short, long_ = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(short) >= 4 and long_.startswith(short):
        return True
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / min(len(ta), len(tb)) >= 0.75 and len(ta & tb) >= (2 if min(len(ta), len(tb)) > 1 else 1)


def visible(label: str, screen: Sequence[str]) -> bool:
    return any(same_label(label, s) for s in screen)


def expect_labels(expect: Any) -> List[str]:
    """A step's expectation as labels that may be on screen afterwards: a list, or the phrase 'a menu opens, showing: A, B, C'."""
    if isinstance(expect, (list, tuple)):
        return [str(x) for x in expect if str(x).strip()]
    m = re.search(r"showing:\s*(.+)$", str(expect or ""))
    return [x.strip() for x in m.group(1).split(",") if x.strip()] if m else []


def _title_of(expect: Any) -> str:
    m = re.search(r"the page '([^']+)' opens", str(expect or ""))
    return m.group(1) if m else ""


# ---- the workflow -----------------------------------------------------------------------------------------------------------------------------------------
def new(goal: str, app: str, steps: Sequence[Dict[str, Any]], lane: str = "", priority: int = 5, kind: str = "") -> Dict[str, Any]:
    sk = skeleton(goal)
    return {"id": uuid.uuid4().hex[:12], "goal": goal, "app": app, "lane": lane or app, "priority": priority, "state": "ready", "kind": kind or sk["kind"], "created": time.time(), "updated": time.time(),
            "cursor": 0, "steps": [{"i": i, "text": s.get("text", ""), "target": s.get("target", "") or s.get("text", ""), "expect": s.get("expect", ""), "verb": s.get("verb", s.get("route_hint", "click")), "done": False, "tries": 0}
                                   for i, s in enumerate(steps)], "log": [], "stages": sk["stages"]}


def locate(wf: Dict[str, Any], screen: Sequence[str], title: str = "") -> Dict[str, Any]:
    """Where is the work, judged ONLY by what is on screen now."""
    steps = wf["steps"]
    if not steps:
        return {"mode": "lost", "index": 0, "why": "the workflow has no steps"}
    marker, ev = -1, ""
    for i in range(len(steps) - 1, -1, -1):                                  # the furthest step whose result is visible = the work has got at least that far
        labs = expect_labels(steps[i]["expect"])
        ttl = _title_of(steps[i]["expect"])
        hit = [l for l in labs if visible(l, screen)]
        if labs and len(hit) >= max(1, (len(labs) + 1) // 2):
            marker, ev = i, f"step {i + 1} left {len(hit)}/{len(labs)} of its expected controls on screen"
            break
        if ttl and title and (same_label(ttl, title) or _norm(ttl) in _norm(title)):
            marker, ev = i, f"step {i + 1} left its page title '{ttl}'"
            break
    if marker == len(steps) - 1:
        return {"mode": "done", "index": len(steps), "why": ev + "; that was the last step"}
    nxt = marker + 1
    def transient(j: int) -> bool:
        """Step j's control is one that the PREVIOUS step's result puts on screen (an item of the menu it opened): seeing it means the work is at least that far; a menu-bar item is on screen all the time and proves nothing."""
        return j > 0 and any(same_label(steps[j]["target"], l) for l in expect_labels(steps[j - 1]["expect"]))
    for j in range(len(steps) - 1, nxt, -1):                                 # the person went on ahead of the plan: carry on from the furthest step whose own control is in front of us
        if visible(steps[j]["target"], screen) and transient(j):
            return {"mode": "resume", "index": j, "why": f"the person already did steps {nxt + 1}-{j}; step {j + 1}'s control is on screen", "skipped": list(range(nxt, j))}
    if visible(steps[nxt]["target"], screen):
        return {"mode": "resume" if marker >= 0 else "fresh", "index": nxt, "why": (ev + "; " if ev else "") + f"step {nxt + 1}'s control '{steps[nxt]['target'][:40]}' is on screen"}
    if marker >= 0:
        if visible(steps[marker]["target"], screen):
            return {"mode": "reopen", "index": marker, "why": ev + f", but step {nxt + 1}'s control is hidden (a menu closed?): repeat step {marker + 1}"}
        return {"mode": "resume", "index": nxt, "why": ev + f"; step {nxt + 1}'s control '{steps[nxt]['target'][:40]}' is not in view yet (scroll or wait)"}
    if marker < 0 and visible(steps[0]["target"], screen):
        return {"mode": "fresh", "index": 0, "why": "step 1's control is on screen and nothing of the later steps is"}
    return {"mode": "lost", "index": max(marker, 0), "why": "none of the steps' controls or results are on screen: the app is somewhere the plan did not expect"}


# ---- store ----------------------------------------------------------------------------------------------------------------------------------------------------
class Store:
    def __init__(self, folder: str = "") -> None:
        self.dir = folder or DEFAULT_DIR
        os.makedirs(self.dir, exist_ok=True)

    def path(self, wid: str) -> str:
        return os.path.join(self.dir, f"{wid}.json")

    def save(self, wf: Dict[str, Any]) -> None:
        wf["updated"] = time.time()
        fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path(wf["id"]))

    def load(self, wid: str) -> Optional[Dict[str, Any]]:
        try:
            return json.load(open(self.path(wid), encoding="utf-8"))
        except Exception:
            return None

    def all(self) -> List[Dict[str, Any]]:
        out = []
        for n in os.listdir(self.dir):
            if n.endswith(".json"):
                w = self.load(n[:-5])
                if w:
                    out.append(w)
        return sorted(out, key=lambda w: -w.get("updated", 0))

    def open_ones(self, app: str = "") -> List[Dict[str, Any]]:
        return [w for w in self.all() if w["state"] in ("ready", "running", "paused", "stuck", "waiting_person") and (not app or w["app"] == app)]


def goal_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def adopt(store: Store, goal: str, app: str, screen: Sequence[str], make_plan: Callable[[], Sequence[Dict[str, Any]]], title: str = "", min_similarity: float = 0.6) -> Dict[str, Any]:
    """The person asks for a task. If the same one is already open (they left it midway), carry on where the SCREEN says it stopped; if the screen shows it is somewhere else, ask; otherwise start new."""
    same = [w for w in store.open_ones(app) if goal_similarity(goal, w["goal"]) >= min_similarity]
    if same:
        wf = same[0]
        loc = locate(wf, screen, title)
        if loc["mode"] in ("resume", "reopen", "fresh"):
            for s in wf["steps"][:loc["index"]]:
                s["done"] = True
            wf["cursor"], wf["state"] = loc["index"], "ready"
            wf["log"].append({"t": time.time(), "event": f"{loc['mode']} at step {loc['index'] + 1}", "why": loc["why"]})
            store.save(wf)
            return {"action": "resumed" if loc["mode"] != "fresh" else "restarted_in_place", "workflow": wf, "locate": loc,
                    "message": f"You left this half done. {loc['why']}. Carrying on from step {loc['index'] + 1}: {wf['steps'][loc['index']]['text'][:70]}."}
        if loc["mode"] == "done":
            wf["state"] = "done"
            wf["log"].append({"t": time.time(), "event": "found complete", "why": loc["why"]})
            store.save(wf)
            return {"action": "already_done", "workflow": wf, "locate": loc, "message": f"This looks finished already ({loc['why']}). I have not repeated it."}
        wf["state"] = "waiting_person"
        wf["log"].append({"t": time.time(), "event": "lost", "why": loc["why"]})
        store.save(wf)
        return {"action": "ask", "workflow": wf, "locate": loc,
                "message": f"I have an unfinished version of this (it got to step {wf['cursor'] + 1}), but {loc['why']}. Continue it from where you are, or start over?"}
    wf = new(goal, app, list(make_plan()))
    wf["state"] = "ready"
    store.save(wf)
    return {"action": "started", "workflow": wf, "locate": {"mode": "fresh", "index": 0, "why": "no open workflow for this goal"}, "message": f"Starting fresh: {len(wf['steps'])} steps."}


def advance(store: Store, wf: Dict[str, Any], verdict: str, evidence: str = "", max_tries: int = 3) -> Dict[str, Any]:
    """Record the result of the current step. PASS moves on; anything else retries, then marks the workflow stuck so the person is asked rather than looped on."""
    i = wf["cursor"]
    if i >= len(wf["steps"]):
        wf["state"] = "done"
        store.save(wf)
        return wf
    st = wf["steps"][i]
    if verdict == "PASS":
        st["done"] = True
        wf["cursor"] = i + 1
        wf["state"] = "done" if wf["cursor"] >= len(wf["steps"]) else "running"
    else:
        st["tries"] += 1
        if st["tries"] >= max_tries:
            wf["state"] = "stuck"
        else:
            wf["state"] = "running"
    wf["log"].append({"t": time.time(), "step": i + 1, "verdict": verdict, "evidence": evidence[:160]})
    store.save(wf)
    return wf


# ---- several tasks -------------------------------------------------------------------------------------------------------------------------------------------
class Scheduler:
    """Several workflows, one running per lane (an app window is a lane: two scripts never fight over one window), priority first (1 = most urgent), then whoever waited longest.
    A lane the person touched in the last `hands_off_s` seconds is skipped: their hands win."""

    def __init__(self, store: Store, hands_off_s: float = 20.0, clock: Callable[[], float] = time.time) -> None:
        self.store, self.hands_off_s, self.clock = store, hands_off_s, clock
        self._human: Dict[str, float] = {}
        self._ran: Dict[str, float] = {}
        self._claimed: Dict[str, str] = {}                      # lane -> workflow id that is running there right now

    def person_touched(self, lane: str) -> None:
        self._human[lane] = self.clock()

    def release(self, wid: str) -> None:
        self._claimed = {l: w for l, w in self._claimed.items() if w != wid}

    def next(self) -> Optional[Dict[str, Any]]:
        """The workflow to give a turn to, now claimed (call release() when its turn ends), or None when every lane is busy, hands-off, or empty."""
        now = self.clock()
        ok = [w for w in self.store.open_ones() if w["state"] in ("ready", "running") and w["lane"] not in self._claimed and now - self._human.get(w["lane"], -1e9) >= self.hands_off_s]
        if not ok:
            return None
        ok.sort(key=lambda w: (w["priority"], self._ran.get(w["id"], w["created"])))
        pick = ok[0]
        self._ran[pick["id"]] = now
        self._claimed[pick["lane"]] = pick["id"]
        return pick

    def table(self) -> List[Dict[str, Any]]:
        return [{"id": w["id"], "goal": w["goal"][:50], "app": w["app"], "lane": w["lane"], "state": w["state"], "step": f"{w['cursor']}/{len(w['steps'])}", "priority": w["priority"]} for w in self.store.all()]
