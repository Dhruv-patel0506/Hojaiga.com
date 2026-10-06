"""
quality_loop.py -- the bounded ITERATIVE-QUALITY driver (work order [7]).

The two robustness engines already exist and are NOT duplicated here:

    popup_policy.py   the ONE popup ladder (gate -> escalate -> T1 words/buttons -> T2 cache ->
                      T2.5 lexical -> T3 local LLM -> T4 verified Escape). Fully generic: it reads
                      what a dialog SAYS and answers by category policy. No per-app rules.
    organ_38          the LLM refinement engine (ask the local model what to change about THIS
                      failure). Degrades to a static gap statement when the model is down.

This module adds the piece neither of them owns: the GOAL-POSTCONDITION QUALITY LOOP.

    * every attempt is SCORED against the goal's postcondition checks (0..1) - so "each attempt
      measurably better" is a recorded number, not a claim;
    * two strikes with no score improvement => re-planning is not working => stop early and say so
      (a bounded loop must also stop when it is going nowhere, not only when it runs out);
    * at the bound, if the postcondition is not met, the status is NOT_DONE - honest, with the
      final gaps attached. "It produced something funky" never becomes a success here;
    * before and after every attempt the generic popup ladder is run over the target's real
      dialogs, and WHICH TIER answered is recorded per round (tiers_used) - an unexpected popup is
      cleared by the engine's own words/categories, never by a rule written for it;
    * every optional dependency reports what it could not do (tiers_skipped-style self-report in
      `self_relied_on`): brains judge, organ_38 planner, popup ladder.

Usage (the suite's RBG1 and organ_01's ledger both speak this shape):

    ql = quality_loop.QualityLoop(goal="save the report", max_attempts=3,
                                  checks=[quality_loop.Check("file holds the text",
                                              lambda ctx: ...)],
                                  popup_owner=hwnd, popup_exclude=pre_existing)
    report = ql.run(executor)            # executor(attempt:int, prev: dict) -> evidence dict
    # report: {status, goal_met, attempts:[{n, score, delta, passed, failed, plan,
    #          evidence, popups_cleared}], tiers_used, planner_used, self_relied_on}
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("hojaiga.quality_loop")

BRAINS_CHAT_URL = os.environ.get("HOJAIGA_BRAIN_URL", "http://127.0.0.1:11434/api/chat")
JUDGE_MODEL = os.environ.get("HOJAIGA_JUDGE_MODEL", "qwen2.5:7b")
BRAINS_TIMEOUT_S = float(os.environ.get("HOJAIGA_QUALITY_LLM_TIMEOUT_S", "15"))
IMPROVE_EPS = 1e-9            # any measurable rise counts; this is a floor, not a threshold


@dataclass
class Check:
    """One clause of the GOAL's postcondition. name is what shows in the report; fn reads the
    world (file, window, tree) and returns truthy/falsy. It must not mutate anything."""
    name: str
    fn: Callable[[Dict[str, Any]], bool]


@dataclass
class Round:
    """One attempt, scored. delta is the measurable improvement over the previous attempt."""
    n: int
    score: float
    delta: float
    passed: List[str]
    failed: List[str]
    plan: str
    evidence: Dict[str, Any]
    popups_cleared: List[str]
    ms: float

    def brief(self) -> Dict[str, Any]:
        return {"n": self.n, "score": self.score, "delta": self.delta, "passed": self.passed,
                "failed": self.failed, "plan": self.plan[:200], "popups_cleared": self.popups_cleared,
                "ms": self.ms}


# --------------------------------------------------------------------------------------------- brains helpers
def brains_available(timeout_s: float = 0.5) -> bool:
    """Is a local chat backend listening? (measured: a closed local port takes ~2 s to refuse on
    Windows, so probe with a socket, exactly like popup_policy probes the gatekeeper)."""
    import socket
    from urllib.parse import urlparse
    u = urlparse(BRAINS_CHAT_URL)
    try:
        socket.create_connection((u.hostname or "127.0.0.1", u.port or 80), timeout=timeout_s).close()
        return True
    except Exception:
        return False


def _brains_ask(prompt: str, timeout_s: float = BRAINS_TIMEOUT_S) -> str:
    """One JSON-mode question to the local model, bounded. '' on any failure (never raises)."""
    payload = {"model": JUDGE_MODEL, "stream": False, "format": "json",
               "messages": [{"role": "user", "content": prompt}],
               "options": {"temperature": 0.0, "num_predict": 220}}
    try:
        req = urllib.request.Request(BRAINS_CHAT_URL, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = (body.get("message", {}) or {}).get("content", "") or body.get("response", "") or ""
        return content
    except Exception as exc:                                  # noqa: BLE001
        logger.debug("[quality] brains ask failed: %s", exc)
        return ""


def default_planner(goal: str, round_: Round, attempt: int) -> str:
    """organ_38's LLM refinement, asked for THIS attempt's gap. Degrades to a static statement of
    the failed postconditions when the engine or the model is unavailable - the loop still gets a
    plan, and self_relied_on records honestly that no LLM fed it."""
    gaps = ", ".join(round_.failed) or "postcondition not met"
    static = f"unmet postconditions: {gaps}"
    try:
        if not brains_available():
            return static
        from core_organs import organ_38_progressive_refinement as ref38
        fb = ref38.ExecutionFeedback(
            step_id=f"quality#{attempt}", status="failed",
            error_message=f"goal: {goal[:200]}; unmet: {gaps[:250]}; evidence: {str(round_.evidence)[:250]}",
            unexpected_outcome=gaps[:120])
        plan = {"task": goal, "attempt": attempt, "steps": ""}
        eng = ref38.get_refinement_engine()
        if eng.should_refine(fb, plan):
            act = eng.generate_refinement(fb, plan, context={"quality_loop": True})
            dyn = "; ".join(s for s in (getattr(act, "suggested_changes", None) or []) if s).strip()
            if dyn:
                # the unmet clauses ride along with the model's words: the plan always states what
                # this attempt MEASURED as missing (the model's phrasing is a bonus, not the record)
                return f"unmet postconditions, retry plan: {dyn} | {static}"
    except Exception as exc:                                  # noqa: BLE001
        logger.debug("[quality] organ_38 planner degraded: %s", exc)
    return static


# --------------------------------------------------------------------------------------------- popup integration
def _ladder_pass(owner: int, exclude: Sequence[int]) -> Tuple[List[str], bool, str]:
    """Run the ONE popup ladder over the target's real blocking dialogs. Returns
    (handled_entries, need_human, degraded_note). Generic by construction: popup_policy decides
    from the dialog's own words - there is no per-app rule anywhere on this path."""
    if not owner:
        return [], False, ""        # a caller-owned loop simply has no app dialogs to sweep; not a degradation
    try:
        from core_organs import popup_policy as pp
        res = pp.clear_blockers(int(owner), mode="inflight", exclude=list(exclude or ()))
        return ([str(h) for h in res.get("handled") or []],
                bool(res.get("need_human")),
                "" if not res.get("left") else f"left_open={res['left']}")
    except Exception as exc:                                  # noqa: BLE001
        logger.debug("[quality] popup ladder unavailable: %s", exc)
        return [], False, f"ladder unavailable: {type(exc).__name__}"


def _tier_of(entry: str) -> str:
    """`no(bm-click):Error` / `escape_fallback:Info` -> the ACTION token; the ladder names the tier
    in its own log lines, which stay in the run log; the report keeps the answers given."""
    return (entry.split(":", 1) + [""])[0].split(" ", 1)[0]


# --------------------------------------------------------------------------------------------- THE loop
class QualityLoop:
    """Bounded, scored, honest retry driver (see module docstring)."""

    def __init__(self, goal: str, checks: Sequence[Check], *, max_attempts: int = 3,
                 executor_timeout_s: float = 0.0, popup_owner: int = 0,
                 popup_exclude: Sequence[int] = (), planner: Optional[Callable] = None,
                 on_round: Optional[Callable[[Round], None]] = None):
        self.goal = goal or ""
        self.checks = list(checks or [])
        self.max_attempts = max(1, int(max_attempts))
        self.popup_owner = int(popup_owner or 0)
        self.popup_exclude = tuple(popup_exclude or ())
        self.planner = planner or default_planner
        self.on_round = on_round
        self.rounds: List[Round] = []
        self.tiers_used: List[str] = []
        self.need_human = False
        self.self_relied_on: Dict[str, Any] = {}

    # ---- scoring
    def _evaluate(self, ctx: Dict[str, Any]) -> Tuple[float, List[str], List[str]]:
        if not self.checks:
            return (1.0 if ctx.get("success") else 0.0), (["executor-reported success"]
                                                           if ctx.get("success") else []), \
                  ([ ] if ctx.get("success") else ["executor-reported failure"])
        passed, failed = [], []
        for c in self.checks:
            try:
                ok = bool(c.fn(ctx))
            except Exception as exc:                          # noqa: BLE001
                ok = False
                failed.append(f"{c.name} (check errored: {type(exc).__name__})")
                continue
            (passed if ok else failed).append(c.name)
        return round(len(passed) / len(self.checks), 4), passed, failed

    # ---- the loop
    def run(self, executor: Callable[[int, Dict[str, Any]], Dict[str, Any]], app_hwnd: int = 0) -> Dict[str, Any]:
        """executor(attempt:int, prev_report:dict) -> evidence dict (any keys; `note` shows in the
        report). Raises are caught and recorded as that attempt's evidence - a crash is an
        unmet postcondition, not a cancelled run. `app_hwnd` adds the live target window to every
        popup sweep, so a dialog the APP throws up mid-run is cleared by the same generic ladder."""
        prev: Dict[str, Any] = {}
        for attempt in range(1, self.max_attempts + 1):
            t0 = time.perf_counter()
            # (a) BEFORE the attempt: an unexpected dialog still open from the last round cannot
            # block this one - the generic ladder sweeps it first.
            pre_cleared, pre_human, pre_note = _ladder_pass(self.popup_owner, self.popup_exclude)
            self.need_human = self.need_human or pre_human
            if app_hwnd:
                ac, ah, _an = _ladder_pass(int(app_hwnd), self.popup_exclude)
                pre_cleared, pre_human = pre_cleared + ac, pre_human or ah
            self.need_human = self.need_human or pre_human
            # (b) the attempt itself
            try:
                evidence = executor(attempt, prev) or {}
                crash = ""
            except Exception as exc:                          # noqa: BLE001
                evidence, crash = {"success": False}, f"{type(exc).__name__}: {str(exc)[:160]}"
            # (c) AFTER the attempt: clear anything new that appeared mid-run, per round, recorded
            post_cleared, post_human, post_note = _ladder_pass(self.popup_owner, self.popup_exclude)
            self.need_human = self.need_human or post_human
            if app_hwnd:
                ac, ah, _an = _ladder_pass(int(app_hwnd), self.popup_exclude)
                post_cleared, post_human = post_cleared + ac, post_human or ah
            self.need_human = self.need_human or post_human
            cleared = pre_cleared + post_cleared
            for entry in cleared:
                tier = _tier_of(entry)
                if tier and tier not in self.tiers_used:
                    self.tiers_used.append(tier)
            note = "; ".join(n for n in (pre_note, post_note) if n)
            if note:
                self.self_relied_on[f"popup_round_{attempt}"] = note[:200]

            score, passed, failed = self._evaluate(evidence)
            delta = round(score - (self.rounds[-1].score if self.rounds else 0.0), 4)
            # Each attempt RECORDS the feedback that DROVE it (the plan generated after the previous
            # failing attempt). The first attempt had no prior failure, so it carries an empty plan.
            rnd = Round(n=attempt, score=score, delta=delta, passed=passed, failed=failed,
                        plan=str(prev.get("last_plan") or ""), evidence=evidence,
                        popups_cleared=cleared,
                        ms=round((time.perf_counter() - t0) * 1000, 1))
            if crash:
                rnd.evidence = dict(rnd.evidence, crash=crash)
            self.rounds.append(rnd)
            if self.on_round:
                try:
                    self.on_round(rnd)
                except Exception:                             # noqa: BLE001
                    pass
            logger.info("[quality] attempt %d/%d scored %.2f (delta %+.2f) unmet=%s popups=%s",
                        attempt, self.max_attempts, score, delta, failed[:3], len(cleared))

            if score >= 1.0:                                  # GOAL POSTCONDITION MET
                return self._report("DONE")
            # re-plan for the NEXT attempt (the plan is carried forward in `prev`, so it shows up as
            # the following round's `plan`; a bounded loop also stops early when it isn't improving)
            plan = self.planner(self.goal, rnd, attempt)
            if len(self.rounds) >= 3 and self.rounds[-2].delta <= IMPROVE_EPS and delta <= IMPROVE_EPS:
                # the two attempts BEFORE this one both failed to improve: re-planning is going
                # nowhere - stop inside the bound and say why (a bounded loop must also stop on no
                # progress, not only on exhaustion).
                self.self_relied_on["stopped_early"] = \
                    f"two consecutive attempts with no measurable improvement (scores {[r.score for r in self.rounds]})"
                return self._report("NOT_DONE")
            prev = {"last_plan": plan, "last_failed": failed, "attempt": attempt}
        return self._report("NOT_DONE")

    # ---- report
    def _report(self, status: str) -> Dict[str, Any]:
        return {
            "status": status,                                # DONE | NOT_DONE (never a fake pass)
            "goal_met": status == "DONE",
            "goal": self.goal[:200],
            "max_attempts": self.max_attempts,
            "attempts": [r.brief() for r in self.rounds],
            "scores": [r.score for r in self.rounds],
            "improved": any(r.delta > IMPROVE_EPS for r in self.rounds[1:]) or
                        (len(self.rounds) == 1 and self.rounds[0].score >= 1.0),
            "final_gaps": self.rounds[-1].failed if self.rounds else ["no attempt ran"],
            "need_human": self.need_human,
            "tiers_used": list(self.tiers_used),
            "popup_rounds": {f"attempt_{r.n}": r.popups_cleared for r in self.rounds},
            "planner_used": "organ_38+brains" if brains_available() else "static_gaps",
            "self_relied_on": dict(self.self_relied_on),
        }


# --------------------------------------------------------------------------------------------- organ_01 ledger
class AttemptLedger:
    """The minimal, additive hook the CrewAI retry loop uses: record each attempt's postcondition
    score, and report the trajectory honestly at the end ('each attempt measurably better' must be
    a NUMBER in the final report, not a hope). It never changes the loop's control flow."""

    def __init__(self, goal: str, n_checks: int):
        self.goal = goal[:120]
        self.n = max(1, int(n_checks))
        self.rows: List[Dict[str, Any]] = []

    def record(self, attempt: int, passed: int, note: str = "") -> None:
        score = round(min(passed, self.n) / self.n, 3)
        prev = self.rows[-1]["score"] if self.rows else 0.0
        self.rows.append({"attempt": attempt, "score": score,
                          "delta": round(score - prev, 3), "note": (note or "")[:160]})
        logger.info("[quality][ledger] attempt %d: %d/%d postconditions met (score %.2f, delta %+.2f)",
                    attempt, min(passed, self.n), self.n, score, score - prev)

    def report(self) -> Dict[str, Any]:
        scores = [r["score"] for r in self.rows]
        improved = any(r["delta"] > IMPROVE_EPS for r in self.rows[1:])
        return {"goal": self.goal, "attempts": self.rows, "scores": scores,
                "each_better_than_last": improved,
                "final": ("MET" if scores and scores[-1] >= 1.0 else "NOT_MET") +
                          f" after {len(self.rows)} attempt(s)"}
