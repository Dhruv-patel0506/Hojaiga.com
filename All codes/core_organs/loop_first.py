"""
loop_first.py -- route the product through the VERIFIED desktop autonomy loop before the ReAct crew runs.

Why this exists
    The crew (organ_01_crewai_engine) lets a 7B model pick tools freely; its judge accuracy on real apps
    is 50-67%. The tested, deterministic capability is desktop_grounding.operate_app (perceive -> decide ->
    act -> verify). This module is the bridge: it turns the user's command into per-app micro-goals
    (with postconditions where the words themselves carry one), runs operate_app for each detected desktop
    app IN ORDER, and returns an honest report that the crew receives as evidence instead of having to
    rediscover it.

Rules this module keeps
    * Only sequencing. There is NO clipboard / data hand-off between apps; each app's final hwnd and step
      trace are recorded (APP_HANDLES) so a later stage can reference them, nothing more.
    * awaiting_human from any app STOPS the sequence (later apps are not started) and surfaces the capsule.
    * A goal whose only postcondition is the generic "something in the UI changed" is labelled WEAK in the
      evidence; it can never be presented as a verified outcome.
    * Browser targets stay with the CDP pre-navigation in organ_01; canvas drawing stays with the Draw tools
      (they cannot be expressed as element-level goals). Both are reported as delegated, not as done.
    * HOJAIGA_LOOP_FIRST=0 switches the whole pass off (default "1") so pure-ReAct stays reachable for bisection.
    * No app names live here: segmentation uses the command's own words and the positions the compiler found.
"""

from __future__ import annotations

import ast
import logging
import operator
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.loop_first")

# Browsers are driven through Organ 19 CDP (pre-navigation), never through element-level desktop goals.
BROWSER_APPS = frozenset({"google chrome", "chrome", "microsoft edge", "edge", "browser", "firefox", "brave",
                          "opera", "vivaldi"})

# Generic imperative verbs. They only decide WHERE a clause may be split into goals; they say nothing about
# any particular app.
_ACTION_VERBS = (
    "type", "write", "enter", "input", "save", "press", "click", "tap", "select", "choose", "set", "add", "insert",
    "copy", "paste", "cut", "open", "close", "search", "find", "calculate", "compute", "multiply", "divide",
    "subtract", "sum", "draw", "sketch", "paint", "rename", "create", "make", "play", "pause", "record", "stop",
    "export", "import", "print", "scroll", "zoom", "toggle", "turn", "check", "uncheck", "expand", "collapse",
    "navigate", "go", "read", "show", "hide", "undo", "redo", "format", "bold", "underline", "italicize",
    # irreversible verbs MUST be goals of their own so the risk gate (task_lifecycle D3) can see and queue them
    "delete", "remove", "erase", "send", "submit", "publish", "post", "pay", "buy", "purchase", "uninstall",
    "overwrite", "clear", "reset", "quit", "exit",
)
_VERB_ALT = "|".join(sorted(_ACTION_VERBS, key=len, reverse=True))

# Sequence boundaries between clauses of one command.
_BOUNDARY_RE = re.compile(
    r"(?:\s*;\s*|\.(?=\s|$)\s*|,?\s+and\s+then\s+|,?\s+then\s+|,?\s+after\s+that\s+|,?\s+afterwards\s+|,?\s+next\s*,?\s+"
    r"|,?\s+and\s+(?=(?:then\s+)?(?:open|launch|start|run|switch\s+to)\b)|,\s+(?=(?:open|launch|start|switch\s+to)\b))",
    re.I)

_DRAW_CUES = re.compile(r"\b(?:draw|sketch|doodle|trace|paint\s+(?:a|an|the|some)\b)", re.I)
_ARITH_RE = re.compile(r"(\d+(?:\.\d+)?(?:\s*[\+\-\*\/xX]\s*\d+(?:\.\d+)?)+)")
_COMPOSE_CUES = re.compile(r"\b(?:a|an|some|about|poem|haiku|story|summary|essay|paragraph|email|letter|joke|"
                           r"sentence|note|list|description|caption|slogan|quote)\b", re.I)
_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s'\"<>|?*]+")


def loop_first_enabled() -> bool:
    return os.environ.get("HOJAIGA_LOOP_FIRST", "1").strip().lower() not in ("0", "false", "no", "off")


def is_browser_app(app: str) -> bool:
    low = (app or "").lower()
    return low in BROWSER_APPS or any(b in low for b in ("chrome", "edge", "firefox", "browser"))


# ---------------------------------------------------------------------------------------------- planning

@dataclass
class AppPlan:
    app: str
    goals: List[str] = field(default_factory=list)
    expect_map: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    strength: List[str] = field(default_factory=list)       # per goal: "strong" | "weak"
    delegated: List[str] = field(default_factory=list)      # clauses left to other machinery (drawing)
    notes: List[str] = field(default_factory=list)
    clauses: List[str] = field(default_factory=list)        # the raw clause text assigned to this app

    def as_dict(self) -> Dict[str, Any]:
        return {"app": self.app, "goals": list(self.goals), "expect_map": {str(k): v for k, v in self.expect_map.items()},
                "strength": list(self.strength), "delegated": list(self.delegated), "notes": list(self.notes)}


def _protect_quotes(text: str) -> Tuple[str, Dict[str, str]]:
    """Quoted payloads may contain commas / 'and' / 'then'; hide them while the clause is split."""
    vault: Dict[str, str] = {}

    def _hide(m: "re.Match[str]") -> str:
        key = f"\x00Q{len(vault)}\x00"
        vault[key] = m.group(0)
        return key
    return re.sub(r"(\"[^\"]*\"|“[^”]*”|'[^']{2,}')", _hide, text), vault


def _restore_quotes(text: str, vault: Dict[str, str]) -> str:
    for k, v in vault.items():
        text = text.replace(k, v)
    return text


def _shield_same_length(text: str) -> str:
    """Blank out quoted payloads WITHOUT changing offsets (compiler positions index the original command)."""
    return re.sub(r"(\"[^\"]*\"|“[^”]*”|'[^']{2,}')", lambda m: "\x01" * len(m.group(0)), text)


def _clause_spans(text: str) -> List[Tuple[int, int]]:
    spans, pos = [], 0
    for m in _BOUNDARY_RE.finditer(text):
        if m.start() > pos:
            spans.append((pos, m.start()))
        pos = m.end()
    if pos < len(text):
        spans.append((pos, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def _surface_word(command: str, pos: int) -> str:
    m = re.match(r"[A-Za-z0-9+_\-]+", command[pos:pos + 40] or "")
    return m.group(0) if m else ""


def _mention_variants(app: str, command: str, pos: int) -> List[str]:
    """Regex fragments that name `app` inside the command: the normalized name, the word the user actually
    wrote at the compiler's detected position, and each word of a multi-word name."""
    raw = {app.strip(), _surface_word(command, pos)}
    raw.update(w for w in re.findall(r"[A-Za-z0-9+_\-]+", app) if len(w) >= 4)
    out = [re.escape(v).replace(r"\ ", r"\s+") for v in sorted((r for r in raw if r), key=len, reverse=True)]
    return out


def _strip_app_phrases(text: str, mentions: List[str]) -> str:
    t = text
    for m in mentions:
        t = re.sub(rf"\b(?:open|launch|start|run|switch\s+to|go\s+to|use)\s+(?:the\s+)?{m}(?:\s+(?:app|application|window|program))?\b\s*(?:,|and\b|then\b)?\s*",
                   " ", t, flags=re.I)
        t = re.sub(rf"\b(?:in|into|on|inside|using|with|within)\s+(?:the\s+)?{m}(?:\s+(?:app|application|window|program))?\b",
                   " ", t, flags=re.I)
        t = re.sub(rf"\b{m}\b", " ", t, flags=re.I)
    for _ in range(3):
        t = re.sub(r"^\s*(?:and|then|also|next|after that|afterwards|,)\s+", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" ,.;")


def _split_goals(text: str) -> List[str]:
    """Split one cleaned clause into micro-goals at a comma / 'and' / 'then' that is followed by a verb."""
    if not text:
        return []
    shielded, vault = _protect_quotes(text)
    parts = re.split(rf"\s*(?:,|;|\band\b|\bthen\b)\s*(?=(?:{_VERB_ALT})\b)", shielded, flags=re.I)
    return [_restore_quotes(p, vault).strip(" ,.;") for p in parts if p and p.strip(" ,.;")]


def _safe_eval(expr: str) -> Optional[float]:
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.USub: operator.neg}

    def ev(n: "ast.AST") -> float:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.operand))
        raise ValueError("unsupported")
    try:
        return ev(ast.parse(expr.replace("x", "*").replace("X", "*"), mode="eval"))
    except Exception:
        return None


def _arith_goals(expr: str) -> Tuple[List[str], Optional[str]]:
    """Button-press goals for an arithmetic expression, using the generic UI vocabulary shared with
    task_runner ('5' -> Five, '*' -> Multiply by, '=' -> Equals). Also returns the result text that must
    appear on screen afterwards (only for exact integers; otherwise None => the last goal stays weak)."""
    from core_organs.task_runner import _DIGIT_WORDS, _SYMBOL_WORDS
    compact = re.sub(r"\s+", "", expr)
    goals: List[str] = []
    for ch in compact:
        if ch in "xX":
            ch = "*"
        word = _DIGIT_WORDS.get(ch) or _SYMBOL_WORDS.get(ch)
        if word:
            goals.append(f"press {word[:1].upper()}{word[1:]}")
    goals.append("press Equals")
    value = _safe_eval(compact)
    result = None
    if value is not None and abs(value) < 1e12 and float(value).is_integer():
        result = str(int(value))
    return goals, result


def _literal_typing_goal(goal: str) -> str:
    """'type hello world' -> 'type "hello world"' so the judge types the user's exact words without
    an LLM rewrite. Instructions that need composing (a haiku, a summary...) are left for the judge."""
    m = re.match(r"^(type|write|enter|input)\s+(?:the\s+text\s+|that\s+)?(.+)$", goal.strip(), re.I)
    if not m:
        return goal
    payload = m.group(2).strip()
    if re.match(r"^[\"“'].*[\"”']$", payload):
        return goal
    if len(payload.split()) > 12 or _COMPOSE_CUES.search(payload) or _PATH_RE.search(payload):
        return goal
    return f'{m.group(1).lower()} "{payload}"'


def plan_app_goals(command: str, app_spans: List[Tuple[str, int]]) -> List[AppPlan]:
    """Per-app micro-goals from the command. `app_spans` = [(normalized_app, position_in_command)], in the
    compiler's order. Pure function: no I/O, unit-testable."""
    plans: Dict[str, AppPlan] = {}
    order: List[str] = []
    desktop = [(a, p) for a, p in app_spans if a and not is_browser_app(a)]
    for a, _p in desktop:
        if a not in plans:
            plans[a] = AppPlan(app=a)
            order.append(a)
    if not desktop:
        return []
    pos_of = {a: p for a, p in desktop}
    all_pos = [(p, a) for a, p in app_spans if a]          # includes browsers: their clauses are not ours
    spans = _clause_spans(_shield_same_length(command))
    current: Optional[str] = None
    pending: List[str] = []                                 # clauses seen before any app is known
    for s, e in spans:
        raw = command[s:e]
        here = [a for p, a in sorted(all_pos) if s <= p < e]
        mine = [a for a in here if a in plans]
        if len(here) > 1 and len(mine) >= 1 and len(set(here)) > 1:
            # one clause names several apps: sequence only, never guess which one the verbs belong to
            for a in mine:
                plans[a].notes.append(f"clause names several apps ('{raw[:50]}'): launched in order, goals not guessed")
            current = mine[-1]
            continue
        if mine:
            target = mine[0]
        elif here:                                          # a browser clause: someone else's work
            current = None
            continue
        else:
            target = current
        if target is None:
            pending.append(raw)
            continue
        current = target
        for pc in pending:
            plans[target].clauses.append(pc)
        pending = []
        plans[target].clauses.append(raw)

    for a in order:
        plan = plans[a]
        mentions = _mention_variants(a, command, pos_of[a])
        for clause in plan.clauses:
            cleaned = _strip_app_phrases(clause, mentions)
            if not cleaned:
                continue
            if _DRAW_CUES.search(cleaned):
                plan.delegated.append(cleaned)
                continue
            for goal in _split_goals(cleaned):
                m = _ARITH_RE.search(goal)
                # an expression inside a file name / path / typed text (2024-10-05.txt) is not arithmetic to press
                if m and not _PATH_RE.search(goal) and not re.match(
                        r"^(?:type|write|enter|input|save|export|open|rename|name|call)\b", goal, re.I):
                    seq, result = _arith_goals(m.group(1))
                    base = len(plan.goals)
                    for g in seq:
                        plan.goals.append(g)
                        plan.strength.append("weak")
                    if result is not None:
                        plan.expect_map[len(plan.goals) - 1] = {"name_visible": result}
                        plan.strength[-1] = "strong"
                    else:
                        plan.notes.append(f"'{m.group(1)}': result not an exact integer; final press stays weak")
                    continue
                goal = _literal_typing_goal(goal)
                plan.goals.append(goal)
                pm = _PATH_RE.search(goal)
                if pm and re.search(r"\bsave\b|\bexport\b", goal, re.I):
                    plan.expect_map[len(plan.goals) - 1] = {"file_created": pm.group(0)}
                    plan.strength.append("strong")
                elif re.match(r"^(?:type|write|enter|input)\b", goal, re.I):
                    plan.strength.append("strong")           # the loop adds text_contains for what it typed
                else:
                    plan.strength.append("weak")
        if not plan.goals and not plan.delegated:
            plan.notes.append("pure launch: no goals in the command")
    return [plans[a] for a in order]


# ---------------------------------------------------------------------------------------------- execution

APP_HANDLES: Dict[str, Dict[str, Any]] = {}      # app -> {hwnd, title, trace_tail, ts}: later stages may look these up


def handle_for(app: str) -> int:
    return int((APP_HANDLES.get(app) or {}).get("hwnd") or 0)


@dataclass
class AppRun:
    app: str
    plan: AppPlan
    status: str = "PENDING"        # COMPLETED | BLOCKED | NEEDS_HUMAN | READY | ERROR | DELEGATED | SKIPPED
    result: Dict[str, Any] = field(default_factory=dict)
    hwnd: int = 0
    elapsed_s: float = 0.0
    goal_verdicts: List[str] = field(default_factory=list)
    cursor_id: str = ""                                         # the child virtual cursor that drove this app (parallel runs)
    cursor_path: List[Tuple[int, int]] = field(default_factory=list)
    t_start: float = 0.0
    t_end: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        r = self.result
        return {"app": self.app, "status": self.status, "hwnd": self.hwnd, "elapsed_s": round(self.elapsed_s, 2),
                "cursor": self.cursor_id, "cursor_points": len(self.cursor_path),
                "steps": r.get("steps", 0), "completed": r.get("completed"), "awaiting_human": r.get("awaiting_human"),
                "blocked_at_goal": r.get("blocked_at_goal"), "goals": self.plan.goals,
                "strength": self.plan.strength, "goal_verdicts": self.goal_verdicts,
                "delegated": self.plan.delegated, "notes": self.plan.notes,
                "trace_tail": [(t.get("verb"), (t.get("element") or "")[:24], t.get("verdict"))
                               for t in (r.get("trace") or [])[-6:]]}


@dataclass
class LoopFirstResult:
    ran: bool = False
    reason: str = ""
    runs: List[AppRun] = field(default_factory=list)
    halted_for_human: bool = False
    capsule: str = ""
    elapsed_s: float = 0.0
    parallel: Dict[str, Any] = field(default_factory=dict)

    @property
    def all_completed(self) -> bool:
        return bool(self.runs) and all(r.status in ("COMPLETED", "READY", "DELEGATED") for r in self.runs) \
            and not self.halted_for_human

    def apps_touched(self) -> List[str]:
        return [r.app for r in self.runs if r.status in ("COMPLETED", "BLOCKED", "NEEDS_HUMAN", "READY")]

    def as_dict(self) -> Dict[str, Any]:
        return {"ran": self.ran, "reason": self.reason, "halted_for_human": self.halted_for_human,
                "capsule": self.capsule, "elapsed_s": round(self.elapsed_s, 2),
                "all_completed": self.all_completed, "parallel": dict(self.parallel), "apps": [r.as_dict() for r in self.runs]}

    def evidence_text(self) -> str:
        """The block the crew receives. Plain facts: what was DONE and VERIFIED, what was weak, what is left."""
        if not self.ran:
            return f"DETERMINISTIC DESKTOP PASS: not run ({self.reason or 'disabled'}). Plan every step yourself."
        lines = ["DETERMINISTIC DESKTOP PASS (the verified autonomy loop ran BEFORE you; every step was judged by a "
                 "postcondition verifier, not by a language model):"]
        for i, r in enumerate(self.runs, 1):
            head = f"  App {i} '{r.app}': {r.status}"
            if r.hwnd:
                head += f" (window hwnd={r.hwnd})"
            if r.result.get("steps"):
                head += f", {r.result.get('steps')} verified-loop steps in {r.elapsed_s:.1f}s"
            lines.append(head)
            for gi, g in enumerate(r.plan.goals):
                v = r.goal_verdicts[gi] if gi < len(r.goal_verdicts) else "NOT RUN"
                st = r.plan.strength[gi] if gi < len(r.plan.strength) else "weak"
                tag = {"PASS": "DONE", "NOT RUN": "NOT DONE"}.get(v, "NOT DONE")
                weak = "" if st == "strong" else " [WEAK evidence: the UI changed, nothing more was proven]"
                lines.append(f"    - '{g[:70]}' -> {tag} ({v}){weak if tag == 'DONE' else ''}")
            for d in r.plan.delegated:
                lines.append(f"    - '{d[:70]}' -> DELEGATED to the drawing tools (not an element-level goal); NOT DONE yet")
            for n in r.plan.notes:
                lines.append(f"    note: {n}")
            if r.status == "ERROR":
                lines.append(f"    error: {r.result.get('error', '')[:120]}")
        if self.halted_for_human:
            lines.append(f"  STOPPED: a human decision is required ({self.capsule}). Later apps were NOT started.")
        lines.append("  RULES: do NOT redo a goal marked DONE; do NOT re-type text that is already present. Work only on goals "
                     "marked NOT DONE or WEAK. No data was copied between apps; if the task needs that, do it yourself.")
        return "\n".join(lines)


def _goal_verdicts(plan: AppPlan, trace: List[Dict[str, Any]]) -> List[str]:
    last: Dict[str, str] = {}
    for t in trace or []:
        last[str(t.get("goal", ""))] = str(t.get("verdict", ""))
    return [last.get(g, "NOT RUN") for g in plan.goals]


def plans_independent(plans: List["AppPlan"]) -> Tuple[bool, str]:
    """May these per-app plans run at the same time? Only when they touch DISJOINT apps and no plan talks about another plan's app (a
    clause that names two apps is data moving between them: order matters, so the run stays sequential). DATA-driven: the app names come
    from the plans themselves."""
    apps = [p.app.lower() for p in plans if p.goals]
    if len(apps) < 2:
        return False, "fewer than two apps have goals"
    if len(set(apps)) != len(apps):
        return False, "two plans target the same app"
    for p in plans:
        others = [a for a in apps if a != p.app.lower()]
        blob = " ".join(p.clauses or p.goals).lower()
        for o in others:
            if o in blob:
                return False, f"a clause of '{p.app}' names '{o}' (data may move between them)"
    return True, "disjoint apps, no cross-app clause"


def _run_plans_parallel(plans, *, operate, capsule_cb, allow_destructive, max_steps_per_goal, record, out, notify) -> None:
    """One CHILD virtual cursor per app, all running at once. Each child has its own loop (operate(..., isolated=True)), its own sprite id and
    its own cursor path; the verifier judges every child independently. Shared, focus-dependent state (the UIA worker, the popup policy's task
    context) is serialized inside the loop, so concurrency only overlaps the waits and the posted messages."""
    import threading
    runs = [AppRun(app=p.app, plan=p) for p in plans]
    out.runs.extend(runs)

    def child(run: AppRun, idx: int) -> None:
        plan = run.plan
        run.cursor_id = f"child:{idx}:{plan.app}"
        sprite = None
        try:
            from core_organs import visual_cursor as vc
            sprite = vc.for_agent(run.cursor_id, plan.app, ttl=None)
        except Exception:                                      # no overlay available: the path is still recorded
            sprite = None

        def cursor_cb(x, y, _run=run, _spr=sprite):
            _run.cursor_path.append((int(x), int(y)))
            try:
                if _spr is not None:
                    _spr.fly_to(float(x), float(y), _run.app, 0.15)
            except Exception:  # noqa: BLE001
                pass
        run.t_start = time.perf_counter()
        try:
            try:                                           # a worker thread needs its OWN COM apartment before any UI Automation call
                import uiautomation as _auto
                _com = _auto.UIAutomationInitializerInThread()
                _com.__enter__()
            except Exception:  # noqa: BLE001
                _com = None
            res = operate(plan.app, list(plan.goals), allow_destructive=allow_destructive, capsule_cb=capsule_cb, cursor_cb=cursor_cb,
                          max_steps_per_goal=max_steps_per_goal, expect_map=dict(plan.expect_map) or None, isolated=True)
            run.result = res or {}
            run.hwnd = int(run.result.get("hwnd") or 0)
            run.goal_verdicts = _goal_verdicts(plan, run.result.get("trace") or [])
            run.status = "NEEDS_HUMAN" if run.result.get("awaiting_human") else ("COMPLETED" if run.result.get("completed") else "BLOCKED")
        except Exception as exc:  # noqa: BLE001
            logger.exception("[loop-first] child %s failed", plan.app)
            run.status, run.result = "ERROR", {"error": f"{type(exc).__name__}: {exc}"}
        run.t_end = time.perf_counter()
        run.elapsed_s = run.t_end - run.t_start
        APP_HANDLES[plan.app] = {"hwnd": run.hwnd, "title": run.result.get("window_title", ""),
                                 "trace_tail": run.as_dict()["trace_tail"], "ts": time.time()}
        record("LOOP_FIRST", plan.app, f"{run.status} (child cursor {run.cursor_id}) goals={len(plan.goals)} steps={run.result.get('steps', 0)}")
        try:
            from core_organs import visual_cursor as vc
            vc.release_agent(run.cursor_id)
        except Exception:  # noqa: BLE001
            pass

    threads = [threading.Thread(target=child, args=(r, i), daemon=True, name=f"child-cursor-{r.app}") for i, r in enumerate(runs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if any(r.status == "NEEDS_HUMAN" for r in runs):
        out.halted_for_human = True
        bad = next(r for r in runs if r.status == "NEEDS_HUMAN")
        out.capsule = f"{bad.app}: {bad.result.get('ready_reason') or 'a dialog or an ambiguous choice needs you'}"
        try:
            notify("input_needed", f"Agent needs your input - {out.capsule}")
        except Exception:  # noqa: BLE001
            pass


def run_loop_first(command: str, app_spans: List[Tuple[str, int]], *,
                   operate: Optional[Callable[..., Dict[str, Any]]] = None,
                   prepare: Optional[Callable[..., Dict[str, Any]]] = None,
                   capsule_cb: Optional[Callable[[str, str], None]] = None,
                   cursor_cb: Optional[Callable[[float, float], None]] = None,
                   notify: Optional[Callable[[str, str], None]] = None,
                   record_action: Optional[Callable[[str, str, str], None]] = None,
                   allow_destructive: bool = False, max_steps_per_goal: int = 5,
                   plan_filter: Optional[Callable[[List[AppPlan]], List[AppPlan]]] = None,
                   parallel: bool = False) -> LoopFirstResult:
    """Run operate_app for every detected desktop app, in the compiler's order. See the module docstring. `parallel=True` runs INDEPENDENT
    apps at the same time, one child virtual cursor each (see plans_independent / _run_plans_parallel); otherwise, or when the plans are not
    independent, the order is sequential exactly as before."""
    out = LoopFirstResult()
    if not loop_first_enabled():
        out.reason = "HOJAIGA_LOOP_FIRST=0"
        return out
    t0 = time.perf_counter()
    try:
        plans = plan_app_goals(command, app_spans)
    except Exception as exc:                                  # a planning bug must not take the product down
        logger.exception("[loop-first] planning failed")
        out.reason = f"planning failed: {type(exc).__name__}: {exc}"
        return out
    if plan_filter is not None:                               # e.g. the lifecycle's risk gate removes goals it queued for a human
        plans = plan_filter(plans)
    if not plans:
        out.reason = "no desktop app detected"
        return out
    if operate is None or prepare is None:
        from core_organs import desktop_grounding as dg
        operate = operate or dg.operate_app
        prepare = prepare or dg.prepare_app
    out.ran = True
    notify = notify or (lambda state, detail: None)
    record = record_action or (lambda *a: None)
    if parallel:
        ok_par, why_par = plans_independent(plans)
        out.parallel = {"requested": True, "used": bool(ok_par), "why": why_par}
        if ok_par:
            _run_plans_parallel([p for p in plans if p.goals], operate=operate, capsule_cb=capsule_cb, allow_destructive=allow_destructive,
                                max_steps_per_goal=max_steps_per_goal, record=record, out=out, notify=notify)
            out.elapsed_s = time.perf_counter() - t0
            return out
    for plan in plans:
        run = AppRun(app=plan.app, plan=plan)
        out.runs.append(run)
        ts = time.perf_counter()
        try:
            if plan.goals:
                res = operate(plan.app, list(plan.goals), allow_destructive=allow_destructive, capsule_cb=capsule_cb,
                              cursor_cb=cursor_cb, max_steps_per_goal=max_steps_per_goal,
                              expect_map=dict(plan.expect_map) or None)
                run.result = res or {}
                run.hwnd = int(run.result.get("hwnd") or 0)
                run.goal_verdicts = _goal_verdicts(plan, run.result.get("trace") or [])
                if run.result.get("awaiting_human"):
                    run.status = "NEEDS_HUMAN"
                elif run.result.get("completed"):
                    run.status = "COMPLETED"
                else:
                    run.status = "BLOCKED"
            elif plan.delegated:
                run.status = "DELEGATED"
            else:
                res = prepare(plan.app, capsule_cb=capsule_cb, cursor_cb=cursor_cb) or {}
                run.result = res
                run.hwnd = int(res.get("hwnd") or 0)
                run.status = "READY" if res.get("ready") else ("NEEDS_HUMAN" if res.get("awaiting_human") else "BLOCKED")
        except Exception as exc:
            logger.exception("[loop-first] %s failed", plan.app)
            run.status = "ERROR"
            run.result = {"error": f"{type(exc).__name__}: {exc}"}
        run.elapsed_s = time.perf_counter() - ts
        APP_HANDLES[plan.app] = {"hwnd": run.hwnd, "title": run.result.get("window_title", ""),
                                 "trace_tail": run.as_dict()["trace_tail"], "ts": time.time()}
        record("LOOP_FIRST", plan.app, f"{run.status} goals={len(plan.goals)} steps={run.result.get('steps', 0)} hwnd={run.hwnd}")
        if run.status == "NEEDS_HUMAN":
            out.halted_for_human = True
            why = run.result.get("ready_reason") or "a dialog or an ambiguous choice needs you"
            out.capsule = f"{plan.app}: {why}"
            try:
                notify("input_needed", f"Agent needs your input - {out.capsule}")
            except Exception:
                pass
            break
    out.elapsed_s = time.perf_counter() - t0
    return out
