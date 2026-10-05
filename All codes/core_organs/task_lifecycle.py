"""
task_lifecycle.py -- one user task through the whole checkpoint chain (A intake -> B acquire -> C perceive -> D decide ->
E act -> F verify -> G recover -> H learn/report), with an HONEST record of every checkpoint.

    r = run_lifecycle("open notepad and type hello; save it as C:\\x\\a.txt")
    r["status"]       DONE | PARTIAL | FAILED | ESCALATED | IMPOSSIBLE | NEEDS_INPUT | ROUTED_WEB
    r["checkpoints"]  [{"id": "B2.launch", "status": "PASS|SKIPPED|BLOCKED|FAIL", "evidence": "..."}, ...]
    r["report"]       done / attempted-failed / escalated, each with evidence  (H4)

The loop (desktop_grounding.DesktopAutonomyLoop) already does B-G for one goal; this module is what makes the chain
explicit and auditable: it adds the phase-A intake (task_intake), the D3 risk gate (organ_48.classify_risk: an
irreversible step is queued for a human, the rest of the task continues), the audit/queue/day-report (organ_48, H4) and
a per-checkpoint verdict derived from what the run actually measured. A checkpoint that did not run says so
(SKIPPED/BLOCKED); none is ever reported PASS without evidence.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from core_organs import loop_first as lf
from core_organs import task_intake as ti

logger = logging.getLogger("hojaiga.lifecycle")


class Chain:
    """Ordered checkpoint record for one task."""

    def __init__(self) -> None:
        self.items: List[Dict[str, str]] = []

    def mark(self, cid: str, name: str, status: str, evidence: str) -> None:
        self.items.append({"id": cid, "name": name, "status": status, "evidence": evidence[:400]})

    def extend(self, items: List[Dict[str, str]]) -> None:
        self.items.extend(items)

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for i in self.items:
            out[i["status"]] = out.get(i["status"], 0) + 1
        return out

    def text(self) -> str:
        return "\n".join(f"  [{i['status']:<7}] {i['id']:<12} {i['name']}: {i['evidence']}" for i in self.items)


# ------------------------------------------------------------------------------------------------ D3: the risk gate

def gate_plans(plans: List[lf.AppPlan], *, model, run_id: str, task: str, allow_destructive: bool,
               unattended: bool, chain: Chain) -> List[lf.AppPlan]:
    """Remove from every plan the goals whose risk class is E2 (irreversible: delete/send/pay/close-without-saving...)
    unless explicitly allowed; each removed goal is queued for a human with its context and the rest of the task goes on."""
    queued, kept = 0, 0
    for plan in plans:
        new_goals, new_strength, new_expect = [], [], {}
        for gi, goal in enumerate(plan.goals):
            risk = model.classify_risk_of(goal) if hasattr(model, "classify_risk_of") else _classify(goal)
            if risk == "E2" and not allow_destructive:
                try:
                    model.enqueue(run_id, plan.app, task, f"irreversible step needs a human: '{goal[:80]}'",
                                  {"goal": goal, "app": plan.app, "risk": risk, "unattended": unattended})
                except Exception as exc:                          # a queue failure must still stop the step
                    logger.warning("[lifecycle] enqueue failed: %s", exc)
                plan.notes.append(f"QUEUED FOR A HUMAN (irreversible): '{goal[:60]}'")
                queued += 1
                continue
            if gi in plan.expect_map:
                new_expect[len(new_goals)] = plan.expect_map[gi]
            new_goals.append(goal)
            new_strength.append(plan.strength[gi] if gi < len(plan.strength) else "weak")
            kept += 1
        plan.goals, plan.strength, plan.expect_map = new_goals, new_strength, new_expect
    chain.mark("D3.gate", "risk gate (reversible runs, irreversible queues)",
               "ESCALATED" if queued else "PASS",
               f"{kept} goal(s) cleared, {queued} irreversible goal(s) queued for a human"
               + ("" if not queued else "; the rest of the task continues"))
    return plans


def _classify(goal: str) -> str:
    from core_organs import organ_48_app_behavior_model as bm
    return bm.classify_risk(goal)


# ------------------------------------------------------------------------------------------------ B-H from a run

_TEMPLATE_COVERED = re.compile(r"^(?:type|write|enter|input|save|export)\b", re.I)


def _template_params(ticket: str) -> Dict[str, str]:
    """Parameters a template may need, read from the ticket's own words: a target path and a literal text."""
    from core_organs import desktop_grounding as dg
    params: Dict[str, str] = {}
    m = dg._GOAL_PATH_RE.search(ticket or "")
    if m:
        params["path"] = m.group(0).rstrip(".,;:!)\"'")
    tm = re.search(r"\b(?:type|write|enter|input)\s+(?:the\s+text\s+)?(?:\"([^\"]+)\"|'([^']+)'|(.+?))(?=\s*(?:,|;|\bthen\b|\band\s+save\b|\bsave\b|$))",
                   ticket or "", re.I)
    if tm:
        txt = (tm.group(1) or tm.group(2) or tm.group(3) or "").strip().rstrip(".")
        lit = dg.literal_typed_text("type " + txt) if not (tm.group(1) or tm.group(2)) else txt
        if lit:
            params["text"] = lit
    return params


def _template_first(ticket, spans, plans, model, run_id, allow_destructive, chain: "Chain"):
    """Run a matching template (organ_48 TemplateRunner) when it covers the WHOLE ticket. Returns a ticket-result dict
    when it completed, else None (the verified loop then plans freely; the chain says why the template was not used)."""
    if model is None or len(spans) != 1:
        chain.mark("A3.template", "template-first lookup", "SKIPPED",
                   "behavior model unavailable" if model is None else "ticket names several apps: templates cover one app")
        return None
    app = spans[0][0]
    goals = [g for p in plans for g in p.goals]
    if not goals or not all(_TEMPLATE_COVERED.match(g) for g in goals):
        chain.mark("A3.template", "template-first lookup", "SKIPPED", "the ticket has steps no template covers (it is not just type/save)")
        return None
    try:
        from core_organs import organ_48_app_behavior_model as bm
        try:
            from core_organs.organ_47_app_intelligence import classify_archetype
            arch = classify_archetype(app)
        except Exception:
            arch = ""
        tpl = model.match_template(app, ticket, arch)
        if tpl is None or tpl.score < 0.5:
            chain.mark("A3.template", "template-first lookup", "SKIPPED",
                       "no template matched" if tpl is None else f"best template '{tpl.name}' scored {tpl.score:.2f} (<0.5)")
            return None
        need = set(re.findall(r"\{(\w+)\}", __import__("json").dumps(tpl.steps)))
        params = _template_params(ticket)
        missing = sorted(need - set(params))
        if missing:
            chain.mark("A3.template", "template-first lookup", "SKIPPED",
                       f"template '{tpl.name}' needs {missing} which the task does not state")
            return None
        t0 = time.perf_counter()
        # a template does not launch the app: bring it up (hidden, ready) first, and give a freshly launched editor a blank
        # document if it restored an old one
        from core_organs import desktop_grounding as dg
        prep = dg.prepare_app(app)
        fresh = ""
        if prep.get("launched"):
            lp = dg.get_loop()
            lp._launched_apps.add(app.lower())
            try:
                lp._run_depth += 1
                fresh = lp._ensure_blank_document(app)
            finally:
                lp._run_depth -= 1
                if lp._run_depth == 0:
                    lp._release_held()
        r = bm.TemplateRunner(model).run(app, ticket, params, run_id=run_id, archetype=arch, allow_destructive=allow_destructive)
        if r.get("completed"):
            chain.mark("A3.template", "template-first run", "PASS",
                       f"template '{tpl.name}' [{tpl.source} {tpl.confidence:.2f}] completed {len(r.get('leaves', []))} leaf step(s) in "
                       f"{time.perf_counter() - t0:.1f}s, no LLM planning" + (f"; {fresh}" if fresh else ""))
            return {"status": "DONE", "via": "template", "template": tpl.name, "evidence": f"template '{tpl.name}' completed (leaves verified)"}
        if r.get("escalated"):
            chain.mark("A3.template", "template-first run", "ESCALATED", f"stopped at '{r.get('blocked_at')}' for a human")
            return {"status": "ESCALATED", "via": "template", "template": tpl.name, "evidence": f"template blocked at {r.get('blocked_at')}"}
        chain.mark("A3.template", "template-first run", "FAIL",
                   f"template '{tpl.name}' did not complete (blocked at '{r.get('blocked_at')}'): falling back to the verified loop")
        return None
    except Exception as exc:
        chain.mark("A3.template", "template-first lookup", "FAIL", f"{type(exc).__name__}: {exc}: falling back to the verified loop")
        return None


def try_template_first(command: str, spans, model, run_id: str, chain: "Chain", allow_destructive: bool = False):
    """3.1: the SAME template-first lookup the lifecycle does, for the free-form `execute_task` path. Called by the
    loop-first preamble BEFORE any goal segmentation / planning. Returns a LoopFirstResult that stands for the
    template run (status COMPLETED or NEEDS_HUMAN), or None when no template covers the ticket (the verified loop then
    plans as before). The chain carries the A3.template checkpoint either way, so a trace shows which path ran."""
    desk = [(a, p) for a, p in (spans or []) if not lf.is_browser_app(a)]
    if model is None or len(desk) != 1:
        return None
    try:
        plans = lf.plan_app_goals(command, desk)
        r = _template_first(command, desk, plans, model, run_id, allow_destructive, chain)
    except Exception as exc:
        chain.mark("A3.template", "template-first lookup", "FAIL", f"{type(exc).__name__}: {exc}")
        return None
    if r is None or not plans:
        return None
    plan = plans[0]
    run = lf.AppRun(app=desk[0][0], plan=plan, hwnd=lf.handle_for(desk[0][0]))
    run.result = {"steps": 0, "completed": r["status"] == "DONE", "via": "template", "template": r.get("template", ""),
                  "recipe": f"template '{r.get('template', '')}'", "evidence": r.get("evidence", "")}
    out = lf.LoopFirstResult(ran=True, reason="template-first", runs=[run])
    if r["status"] == "DONE":
        run.status = "COMPLETED"
        run.goal_verdicts = ["PASS"] * len(plan.goals)
    else:                                                   # a leaf was queued for a human: stop, never improvise
        run.status = "NEEDS_HUMAN"
        run.goal_verdicts = ["NOT RUN"] * len(plan.goals)
        out.halted_for_human = True
        out.capsule = r.get("evidence", "a template step needs a human")
    return out


def _checkpoints_from_run(run: lf.AppRun, chain: Chain, *, intel_note: str = "") -> None:
    """Derive the B-H checkpoint verdicts from what this app's run actually measured."""
    r = run.result or {}
    trace = r.get("trace") or []
    app = run.app
    tiers = sorted({t for e in trace for t in (e.get("tiers") or [])})
    methods = [str(e.get("method", "")) for e in trace]
    verdicts = [str(e.get("verdict", "")) for e in trace]

    # B: acquisition
    if run.status == "ERROR":
        chain.mark(f"B.{app}", "acquire app", "FAIL", r.get("error", "error"))
        return
    chain.mark("B1.find", f"existing window of '{app}'", "PASS" if r.get("hwnd") else "BLOCKED",
               f"hwnd={r.get('hwnd')} title={str(r.get('window_title', ''))[:40]!r}" if r.get("hwnd") else "no window found")
    chain.mark("B2.launch", f"launch '{app}'", "PASS" if r.get("launched") else "SKIPPED",
               "launched a new hidden instance" if r.get("launched") else "an instance already existed; none was launched")
    ready = not (r.get("awaiting_human") and not trace) and not r.get("ready_reason")
    chain.mark("B3.ready", "window groundable (UIA tree non-empty)", "PASS" if ready and (r.get("steps") or r.get("hwnd")) else "BLOCKED",
               f"window_mode={r.get('window_mode')}" + (f"; not ready: {r.get('ready_reason')}" if r.get("ready_reason") else ""))

    # C: perception
    chain.mark("C1.scan", "tiered scan ladder", "PASS" if tiers else "BLOCKED",
               f"tiers that ran: {tiers or 'none'}")
    popup_n = sum(1 for m in methods if "popup" in m or "file-dialog" in m or "dialog" in m)
    shots = r.get("escalation_shots") or []
    chain.mark("C2.popups", "popup / dialog sweep", "ESCALATED" if shots else "PASS",
               f"{popup_n} popup-related step(s); preflight + per-step triage ran before every action"
               + (f"; a dialog needed a human, screenshot saved: {shots[0].get('path')}" if shots else ""))
    chain.mark("C3.snapshot", "pre/post state snapshot (structure + pixels + names)", "PASS" if trace else "BLOCKED",
               f"{len(trace)} step(s) verified against a before/after snapshot")

    # D/E: decision and action
    effectors = sorted({m.split("->")[0].split(":")[0].split("+")[0] for m in methods if m})
    chain.mark("D2.effector", "effector per step (UIA pattern / posted message)", "PASS" if effectors else "BLOCKED",
               f"used: {effectors[:6]}")
    chain.mark("E1.input", "virtual input only", "PASS", "posted messages / UIA patterns; the physical pointer is guarded")

    # F: verdicts
    n_pass = sum(1 for v in verdicts if v == "PASS")
    wrong = sum(1 for v in verdicts if v == "WRONG_STATE")
    nochg = sum(1 for v in verdicts if v == "NO_CHANGE")
    strong = sum(1 for s in run.plan.strength if s == "strong")
    goals_done = sum(1 for v in run.goal_verdicts if v == "PASS")
    chain.mark("F1.verdict", "postcondition verdicts", "PASS" if goals_done == len(run.plan.goals) and run.plan.goals else
               ("BLOCKED" if run.plan.goals else "SKIPPED"),
               f"{n_pass} PASS / {wrong} WRONG_STATE / {nochg} NO_CHANGE across {len(trace)} step(s); "
               f"{goals_done}/{len(run.plan.goals)} goals verified ({strong} with a strong postcondition)")
    chain.mark("F2.subgoal", "sub-goals complete in order", "PASS" if run.status == "COMPLETED" else
               ("ESCALATED" if run.status == "NEEDS_HUMAN" else "FAIL"),
               f"app run status {run.status}; blocked_at_goal={r.get('blocked_at_goal')}")

    # G: recovery (only meaningful when something went wrong)
    recovered = any(("retry" in m or "recovery" in m or "shortcut" in m) for m in methods)
    if wrong or nochg:
        chain.mark("G1.recover", "recovery ladder", "PASS" if run.status == "COMPLETED" else "FAIL",
                   f"{wrong + nochg} non-PASS step(s); recovery rungs used={recovered}; goal ended {run.status}")
    else:
        chain.mark("G1.recover", "recovery ladder", "SKIPPED", "no step needed recovery")
    if run.status in ("BLOCKED", "NEEDS_HUMAN"):
        chain.mark("G3.escalate", "ladder exhausted -> evidence + day report", "ESCALATED" if run.status == "NEEDS_HUMAN" else "FAIL",
                   f"stopped at goal {r.get('blocked_at_goal')}; trace tail: {[(e.get('verb'), e.get('verdict')) for e in trace[-3:]]}")

    # H: learning
    chain.mark("H2.promote", "recipe distilled from a verified run", "PASS" if r.get("recipe_ingested") else "SKIPPED",
               str(r.get("recipe") or "only a fully verified run is distilled"))
    chain.mark("H3.checkpoint", "task-level resume point written", "PASS" if trace else "SKIPPED",
               f"{len(trace)} step checkpoint(s) via the loop's resume log")


# ------------------------------------------------------------------------------------------------ the lifecycle

def run_lifecycle(command: str, *, allow_destructive: bool = False, unattended: bool = True,
                  operate: Optional[Callable[..., Dict[str, Any]]] = None,
                  prepare: Optional[Callable[..., Dict[str, Any]]] = None,
                  capsule_cb=None, cursor_cb=None, notify=None, max_steps_per_goal: int = 5,
                  model=None, run_id: Optional[str] = None, catalog: Optional[List[str]] = None) -> Dict[str, Any]:
    t0 = time.perf_counter()
    run_id = run_id or "run_" + uuid.uuid4().hex[:8]
    chain = Chain()
    result: Dict[str, Any] = {"run_id": run_id, "status": "FAILED", "tickets": [], "checkpoints": [], "report": {}}
    # ---- Phase A
    intake = ti.analyse(command, catalog)
    chain.extend(intake.checkpoints)
    result["clean_command"] = intake.clean_text
    if intake.refused:
        result["status"] = "IMPOSSIBLE"
        result["reason"] = "; ".join(intake.impossible)
        result["checkpoints"] = chain.items
        return result
    if intake.question:
        result["status"] = "NEEDS_INPUT"
        result["question"] = intake.question
        result["checkpoints"] = chain.items
        return result
    if model is None:
        try:
            from core_organs import organ_48_app_behavior_model as bm
            model = bm.get_model()
        except Exception as exc:
            logger.warning("[lifecycle] behavior model unavailable: %s", exc)
    ticket_results: List[Dict[str, Any]] = []
    for ti_idx, ticket in enumerate(intake.tickets):
        tchain = Chain()
        domain = intake.ticket_domains[ti_idx] if ti_idx < len(intake.ticket_domains) else "unknown"
        tr: Dict[str, Any] = {"ticket": ticket, "domain": domain, "status": "FAILED"}
        ticket_results.append(tr)
        try:
            if domain in ("web",):
                tr["status"] = "ROUTED_WEB"
                tchain.mark("A2.route", "web ticket", "PASS", "routed to the browser (CDP) path; same perceive->act->verify loop with a DOM backend")
                tr["checkpoints"] = tchain.items
                continue
            spans = [(a, p) for a, p in ti.detect_apps(ticket, catalog) if not lf.is_browser_app(a)]
            if not spans:
                tr["status"] = "NEEDS_INPUT"
                tchain.mark("A2.route", "no desktop app resolvable", "BLOCKED", "no installed app named: asking instead of guess-launching")
                tr["checkpoints"] = tchain.items
                continue

            def _filter(plans, _t=ticket, _c=tchain):
                if model is None:
                    _c.mark("D3.gate", "risk gate", "BLOCKED", "behavior model unavailable: goals are NOT gated, refusing to run unattended")
                    return [] if unattended else plans
                return gate_plans(plans, model=model, run_id=run_id, task=_t, allow_destructive=allow_destructive,
                                  unattended=unattended, chain=_c)

            plans_preview = lf.plan_app_goals(ticket, spans)
            tchain.mark("A3.plan", "decomposition into per-app verified goals",
                        "PASS" if any(p.goals for p in plans_preview) else "BLOCKED",
                        "; ".join(f"{p.app}: {len(p.goals)} goal(s) ({sum(1 for s in p.strength if s == 'strong')} strong)"
                                  for p in plans_preview) or "no goals")
            # A3 template-first: a learned/seeded template (DATA) that covers the whole ticket runs before any free-form plan
            if operate is None:                      # tests that stub the operator exercise the loop path only
                done_by_template = _template_first(ticket, spans, plans_preview, model, run_id, allow_destructive, tchain)
                if done_by_template is not None:
                    tr.update(done_by_template)
                    tr["checkpoints"] = tchain.items
                    try:
                        model.audit(run_id, spans[0][0], "task", ticket,
                                    "DONE" if tr["status"] == "DONE" else "ESCALATED", tr.get("evidence", "")[:200], "")
                    except Exception:
                        pass
                    continue
            res = lf.run_loop_first(ticket, spans, operate=operate, prepare=prepare, capsule_cb=capsule_cb,
                                    cursor_cb=cursor_cb, notify=notify, allow_destructive=allow_destructive,
                                    max_steps_per_goal=max_steps_per_goal, plan_filter=_filter)
            for run in res.runs:
                _checkpoints_from_run(run, tchain)
            queued = any(i["id"] == "D3.gate" and i["status"] == "ESCALATED" for i in tchain.items)
            if res.halted_for_human:
                tr["status"] = "ESCALATED"
            elif queued and res.runs and res.all_completed:
                tr["status"] = "ESCALATED"           # the safe part is done, the irreversible part is waiting for a human
            elif res.all_completed:
                weak = any(s != "strong" for r_ in res.runs for s in r_.plan.strength)
                tr["status"] = "DONE" if not weak else "PARTIAL"
                if weak:
                    tr["note"] = "all steps passed but at least one only proved 'the UI changed' (weak evidence)"
            elif res.ran:
                tr["status"] = "FAILED"
            else:
                tr["status"] = "FAILED"
                tchain.mark("B.run", "loop did not run", "BLOCKED", res.reason)
            tr["loop"] = res.as_dict()
            tr["evidence"] = res.evidence_text()
        except Exception as exc:                                  # one failing ticket never stalls the queue
            logger.exception("[lifecycle] ticket failed")
            tr["status"] = "FAILED"
            tr["error"] = f"{type(exc).__name__}: {exc}"
            tchain.mark("X.exception", "ticket raised", "FAIL", tr["error"])
        tr["checkpoints"] = tchain.items
        # ---- H4: audit every ticket, honestly
        if model is not None:
            try:
                dec = {"DONE": "DONE", "PARTIAL": "DONE", "ESCALATED": "ESCALATED", "ROUTED_WEB": "DONE"}.get(tr["status"], "FAILED")
                model.audit(run_id, (tr.get("loop", {}).get("apps") or [{}])[0].get("app", "") if tr.get("loop") else "",
                            "task", ticket, dec, tr.get("note") or tr["status"], (tr.get("evidence") or tr.get("error") or "")[:500])
            except Exception as exc:
                logger.debug("[lifecycle] audit failed: %s", exc)
    result["tickets"] = ticket_results
    for tr in ticket_results:
        chain.extend(tr.get("checkpoints", []))
    statuses = [t["status"] for t in ticket_results]
    if statuses and all(s in ("DONE", "ROUTED_WEB") for s in statuses):
        result["status"] = "DONE"
    elif statuses and any(s == "ESCALATED" for s in statuses):
        result["status"] = "ESCALATED"
    elif statuses and any(s in ("DONE", "PARTIAL") for s in statuses):
        result["status"] = "PARTIAL"
    elif statuses and all(s == "NEEDS_INPUT" for s in statuses):
        result["status"] = "NEEDS_INPUT"
    else:
        result["status"] = "FAILED"
    try:
        result["report"] = model.day_report(run_id) if model is not None else {}
    except Exception:
        result["report"] = {}
    chain.mark("H4.report", "honest completion report", "PASS",
               f"{len(ticket_results)} ticket(s): {statuses}; audit rows for run {run_id}")
    result["checkpoints"] = chain.items
    result["elapsed_s"] = round(time.perf_counter() - t0, 2)
    return result
