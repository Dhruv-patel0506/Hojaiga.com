"""
professor.explore -- IDLE-TIME PERMUTATION LEARNING: while nobody is using the computer, test whether the ORDER of two safe actions matters, and learn how to get out of trouble.

The brief's third scenario ("sleep state") wants the system to discover behaviour nobody documented. This is the part of it that can be done without gambling with anybody's work:

  * ORDER EFFECTS   for every pair of safe, state-changing actions {A, B}: do A then B, record the final state, put the application back (verified), do B then A, record, put it back (verified),
                    compare. "Add Marker then Clear Markers" leaves 0 markers, "Clear then Add" leaves 1 -> order matters. The verdicts go to the state-transition history and make the planner's
                    sequences trustworthy ("clear first, then add").
  * RECOVERIES      whenever an action opens a dialog, it is closed again and HOW is logged (Escape / WM_CLOSE) - the escape sequence the system already knows when it must recover for real.

Boundaries (each enforced in code and tested), and why they differ from "drag things out of bounds, right-click empty space, press random hotkeys":
  * only a window the Professor LAUNCHED or one the user AUTHORISED (Effector gate); a user's authorised window is only explored while the machine is IDLE (no keyboard / mouse for
    `idle_required_s`), and exploration stops the moment the user returns;
  * only 'safe' verbs (professor.safety) - nothing that deletes, sends, saves, runs, records or opens a dialog; commit-class verbs only inside a window the Professor owns;
  * random hotkeys, out-of-bounds drags and blind right-clicks are NOT used: in someone's real document they can destroy work or send things, and an application cannot be told which of
    them was safe in advance. Every action is a catalog verb with a known safety class, every step is verified, and a step that cannot be undone STOPS the exploration (the same brake as probing);
  * headless like everything else (window messages / UI Automation), the user's focus handed back, the physical mouse and keyboard never touched or blocked.
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import safety
from .effectors import Effector
from .harvest import Catalog
from .probe import Hypothesis, ProbeEngine, delta, diff_state, snapshot


@dataclass
class PairResult:
    a: str
    b: str
    verdict: str                      # order_matters | commutes | untested
    ab: str = ""                      # what A-then-B left behind
    ba: str = ""
    diff: List[str] = field(default_factory=list)
    restored: bool = True
    note: str = ""


@dataclass
class ExploreReport:
    pairs: List[PairResult] = field(default_factory=list)
    stopped: str = ""
    seconds: float = 0.0
    actions: List[str] = field(default_factory=list)
    skipped: List[Tuple[str, str]] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {"actions": self.actions, "pairs": len(self.pairs), "order_matters": [f"{p.a} / {p.b}" for p in self.pairs if p.verdict == "order_matters"],
                "commute": [f"{p.a} / {p.b}" for p in self.pairs if p.verdict == "commutes"], "stopped": self.stopped, "seconds": self.seconds}


def idle_seconds() -> float:
    try:
        from core_organs.background_window import user_idle_ms
        return user_idle_ms() / 1000.0
    except Exception:
        return 0.0


class Explorer:
    def __init__(self, hwnd: int, effector: Effector, catalog: Catalog, app_key: str, history: Any = None, owned: bool = False, idle_required_s: float = 300.0,
                 max_actions: int = 4, budget_s: float = 180.0, idle_fn: Any = None, learner: Any = None, toolkit: str = ""):
        self.hwnd, self.fx, self.catalog, self.app_key, self.history, self.owned = hwnd, effector, catalog, app_key, history, owned
        self.idle_required_s, self.max_actions, self.budget_s = idle_required_s, max_actions, budget_s
        self.idle_fn = idle_fn or idle_seconds
        self.learner = learner
        self.engine = ProbeEngine(hwnd, effector, catalog, app_key, budget_s=budget_s, max_probes=40, owned=owned, history=history, toolkit=toolkit)

    # ---- pieces
    def _user_back(self, require_idle: bool) -> bool:
        return require_idle and self.idle_fn() < min(self.idle_required_s, 2.0)        # any input in the last 2 s (after a long idle) means the user is back

    def _apply(self, h: Hypothesis) -> Optional[Tuple[Any, Any, Any, Any, list]]:
        """Do one action. Returns (before, after, delta, node, nodes_before) or None when it could not be delivered."""
        from core_organs import fast_uia
        nodes0 = fast_uia.snapshot(self.hwnd, timeout_ms=4000) or []
        s0 = snapshot(self.hwnd, nodes=nodes0)
        node = self.engine._find(nodes0, h)
        if node is None:
            return None
        ok, how = self.fx.node(node)
        if not ok:
            return None
        s1 = self.engine._settle(s0)
        return s0, s1, delta(s0, s1), node, nodes0

    def _undo(self, h: Hypothesis, rec: Tuple[Any, Any, Any, Any, list]) -> bool:
        s0, s1, d, node, nodes0 = rec
        how, s2 = self.engine._unwind(h, node, nodes0, s0, s1, d)
        s2 = s2 or snapshot(self.hwnd)
        ok = not diff_state(s0, s2, pixel_tol=1.0)                                        # structure decides; pixels differ with focus / caret blink
        if not ok:
            time.sleep(0.5)
            ok = not diff_state(s0, snapshot(self.hwnd), pixel_tol=1.0)
        return ok

    def _order(self, first: Hypothesis, second: Hypothesis) -> Tuple[Optional[Any], bool, str]:
        """first then second -> (final snapshot, everything put back, note)."""
        r1 = self._apply(first)
        if r1 is None:
            return None, True, f"'{first.verb}' could not be delivered"
        r2 = self._apply(second)
        final = snapshot(self.hwnd) if r2 is None else r2[1]
        back = True
        if r2 is not None:
            back = self._undo(second, r2) and back
        back = self._undo(first, r1) and back
        return final, back, "" if r2 is not None else f"'{second.verb}' could not be delivered"

    # ---- the exploration
    def run(self, require_idle: bool = True) -> ExploreReport:
        t0 = time.time()
        rep = ExploreReport()
        if not self.fx.allowed:
            rep.stopped = "input closed: " + self.fx.why_not()
            return rep
        if not self.owned:
            require_idle = True                                                          # somebody else's window is only explored while nobody is there
        if require_idle and self.idle_fn() < self.idle_required_s:
            rep.stopped = f"the user is active (idle {self.idle_fn():.0f}s < {self.idle_required_s:.0f}s required)"
            return rep
        hyps, rep.skipped = self.engine.plan(k=12)
        pool = [h for h in hyps if h.kind == "state" and h.role in ("button", "menuitem", "checkbox", "splitbutton")][: self.max_actions]
        rep.actions = [h.verb for h in pool]
        import contextlib
        with (self.learner.training() if self.learner is not None else contextlib.nullcontext()), self.fx.focus_watch():
            for a, b in itertools.combinations(pool, 2):
                if time.time() - t0 > self.budget_s:
                    rep.stopped = "time budget"
                    break
                if self._user_back(require_idle):
                    rep.stopped = "the user came back: exploration stopped"
                    break
                ok_a, why_a = safety.may_probe(a.verb, "", self.owned)
                ok_b, why_b = safety.may_probe(b.verb, "", self.owned)
                if not (ok_a and ok_b):
                    rep.pairs.append(PairResult(a.verb, b.verb, "untested", note=f"{a.verb if not ok_a else b.verb} is {why_a if not ok_a else why_b}"))
                    continue
                s_start = snapshot(self.hwnd)
                ab, back1, n1 = self._order(a, b)
                ba, back2, n2 = self._order(b, a)
                s_end = snapshot(self.hwnd)
                restored = not diff_state(s_start, s_end, pixel_tol=1.0)
                if ab is None or ba is None:
                    pr = PairResult(a.verb, b.verb, "untested", restored=restored, note=n1 or n2)
                else:
                    diff = diff_state(ab, ba, pixel_tol=1.0)
                    pr = PairResult(a.verb, b.verb, "order_matters" if diff else "commutes", _brief(ab), _brief(ba), diff, restored)
                rep.pairs.append(pr)
                if self.history is not None:
                    try:
                        self.history.log(self.app_key, "sleep", "pair", f"{a.verb} / {b.verb}", "both orders", s_start.sig, "", s_end.sig, "; ".join(pr.diff)[:250] or pr.note, pr.verdict, pr.verdict != "untested",
                                         restored, detail={"ab": pr.ab, "ba": pr.ba, "diff": pr.diff})
                    except Exception:
                        pass
                if not restored:
                    rep.stopped = f"the application could not be put back after '{a.verb}' / '{b.verb}' - exploration stopped to protect it"
                    break
        rep.seconds = round(time.time() - t0, 1)
        return rep


def _brief(s: Any) -> str:
    return "; ".join(f"{v}" for _k, v in sorted(s.texts.items()))[:160]
