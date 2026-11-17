"""
professor.perms -- PRACTICE: run the PERMUTATIONS and COMBINATIONS of what an application offers, so the router learns from more than the single route one guide procedure happened to need.

WHY THIS EXISTS. A guide procedure asks for one action, the ladder tries its routes in order and stops at the first that works. The model therefore sees a lopsided world: 'shortcut' rarely gets a
fair try on a toolbar button, 'command' almost never on a menu item, and nobody ever learns what happens when a pane is opened BEFORE a search rather than after. Practice performs the alternatives
on purpose, records the outcome as a real transition row, and puts the interface back the way it was.

GENERIC BY CONSTRUCTION. Which verbs qualify is read from the catalog (their own labels, roles, shortcuts and patterns) and from safety's classification - nothing here names an application. Only
actions that can be UNDONE are exercised: a toggle (press it twice and the world is as it was), a view surface (open it, close it), a navigation (go, come back) and a document edit (undo). Anything
that writes a file, sends something, or the safety gate calls unsafe / sensitive is never touched, and an application in `navigate` mode (it holds the person's own account) is skipped entirely.

Two exercises, both cheap:
  * ROUTE permutation  - the same control reached by every route it offers (control / shortcut / command / click), the ladder's favourite last: rows the outcome model has never been fed.
  * ORDER combination  - a PAIR of safe reversible actions performed in both orders (A then B, B then A): does the second control still be found? Rows land as primitive='pair', which is exactly
                         what History.order_effects() was written to read.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from . import safety
from .schema import fold

# a control that can be put back the way it was: those, and only those, are exercised
TOGGLE_ROLES = ("checkbox", "togglebutton", "button", "splitbutton", "tabitem", "listitem", "radiobutton")
OPEN_RX = re.compile(r"^(?:show|hide|open|close|expand|collapse|toggle)\b")
PAIR_SOURCE = "practice"


def _undoes_itself(v: Any) -> bool:
    """A control whose second press returns the world to where it was: a toggle, or a word on it that says open / close / show / hide."""
    lab = (v.label or "").strip().lower()
    if any(p in set(v.sources or []) for p in ("toggle",)):
        return True
    role = (v.role or "").lower()
    if role in ("checkbox", "togglebutton"):
        return True
    if role in ("tabitem", "listitem", "radiobutton"):
        return True
    return bool(OPEN_RX.match(lab))


def _quiet(label: str) -> bool:
    """Safety's own answer, plus the plain-words rule: a label whose action could not be undone is not practice material."""
    if not label:
        return False
    if safety.classify(label) != "safe":
        return False
    return True


def pick_verbs(cat: Any, ex: Any, limit: int) -> List[Any]:
    """The catalog's own words decide what may be practised: enabled, nameable, reversible and safe."""
    out: List[Any] = []
    seen = set()
    for v in getattr(cat, "verbs", []) or []:
        try:
            if not getattr(v, "enabled", True):
                continue
            lab = (v.label or "").strip()
            if len(lab) < 2 or fold(lab) in seen:
                continue
            if ex.resolve(lab) is None:                                            # it must still be a control the executor can reach
                continue
            if not _quiet(lab) or not _undoes_itself(v):
                continue
            if ex._live_node(v) is None:                                           # nothing on screen: practice would only re-run the search path
                continue
            seen.add(fold(lab))
            out.append(v)
            if len(out) >= limit:
                break
        except Exception:                                                          # noqa: BLE001
            continue
    return out


def pair_targets(procedure_steps: List[Any], limit: int) -> List[Tuple[str, str]]:
    """The combinations a guide procedure implies, in BOTH orders: (A, B) and (B, A) for every neighbouring pair of its own steps."""
    labels = [str(getattr(s, "target", "") or getattr(s, "raw", "") or "").strip() for s in procedure_steps or []]
    labels = [l for l in labels if 2 < len(l) < 60]
    pairs: List[Tuple[str, str]] = []
    for a, b in zip(labels, labels[1:]):
        if pairs.count((a, b)) == 0:
            pairs.append((a, b))
            pairs.append((b, a))
        if len(pairs) >= limit:
            break
    return pairs


class Practise:
    """Perform alternatives, measure what the interface did, put it back, and feed the rows to the history the models train on."""

    def __init__(self, ex: Any, fx: Any, history: Any, app_key: str, hwnd: int, toolkit: str = "", archetype: str = "", log: Optional[Any] = None):
        self.ex, self.fx, self.history = ex, fx, history
        self.app_key, self.hwnd = app_key, hwnd
        self.toolkit, self.archetype = toolkit, archetype
        self.log = log or (lambda s: None)
        self.stats: Dict[str, Any] = {"routes": 0, "routes_reached": 0, "pairs": 0, "seconds": 0.0, "skipped_safety": 0, "unwound": 0}

    # -------------------------------------------------------------------------------------------- one action
    def _step(self, v: Any, r: Any) -> Tuple[bool, str, str]:
        s0 = self.ex._snap()
        ok, how = self.ex._deliver(v, r)
        if not ok:
            return False, how, "no_effect"
        s1 = self.ex._settle(s0, float(os.environ.get("HOJAIGA_PRACTICE_SETTLE", "1.6")))
        from .probe import delta                                                       # the same measurement a guide step gets
        d = delta(s0, s1)
        eff = d.effect()
        self._row(v, r, s0, s1, d, how)
        return True, how, eff

    def _row(self, v: Any, r: Any, s0: Any, s1: Any, d: Any, how: str) -> None:
        if self.history is None:
            return
        try:
            primitive = {"shortcut": "key", "control": "invoke", "value": "set_value", "click": "click", "command": "command"}.get(r.kind, "click")
            self.history.log(self.app_key, PAIR_SOURCE, primitive, (v.label or "")[:60], r.label(), s0.sig, f"{len(s0.names)} controls", s1.sig,
                             d.summary(), d.effect(), d.effect() != "no_effect", None, getattr(v, "aid", "") or "",
                             {"how": how, "practised": True}, toolkit=self.toolkit, archetype=self.archetype,
                             role=getattr(v, "role", "") or "", safety=safety.classify(v.label or ""))
        except Exception:                                                              # noqa: BLE001
            pass

    def _unwind(self, v: Any) -> None:
        """Put the interface back: press the same control again (a toggle) and undo what a text editor document took."""
        with self._safe():
            role = (getattr(v, "role", "") or "").lower()
            if role in ("checkbox", "togglebutton") or OPEN_RX.match((v.label or "").lower()):
                n = self.ex._live_node(v)
                if n is not None:
                    self.ex._deliver(v, self.ex.routes_for(v)[0])
                    self.stats["unwound"] += 1

    def _safe(self):
        import contextlib
        return contextlib.suppress(Exception)

    # -------------------------------------------------------------------------------------------- exercises
    def route_permutations(self, verbs: List[Any], budget_s: float) -> List[Dict[str, Any]]:
        """Every route a control offers, each one tried on purpose - the ladder stops at the first success, so the ones it ranks low would otherwise never be measured."""
        out: List[Dict[str, Any]] = []
        end = time.time() + budget_s
        for v in verbs:
            if time.time() > end:
                break
            try:
                routes = self.ex.routes_for(v)
            except Exception:                                                          # noqa: BLE001
                continue
            if len(routes) < 2:
                continue
            reached = 0
            for r in routes[1:]:                                                       # route 0 the guide already uses; the alternatives are the news
                if time.time() > end:
                    break
                self.stats["routes"] += 1
                ok, how, eff = self._step(v, r)
                reached += 1 if eff != "no_effect" else 0
                if ok and eff != "no_effect":
                    self._unwind(v)
                out.append({"verb": v.label, "route": r.label(), "effect": eff, "how": how[:90]})
            self.stats["routes_reached"] += reached
        return out

    def order_combinations(self, pairs: List[Tuple[str, str]], budget_s: float) -> List[Dict[str, Any]]:
        """A then B, and B then A. Does the second control still get found when the first ran the other way round? That is what a plan needs to know and what no single guide run ever shows."""
        out: List[Dict[str, Any]] = []
        end = time.time() + budget_s
        for a, b in pairs:
            if time.time() > end:
                break
            va, vb = self.ex.resolve(a), self.ex.resolve(b)
            if va is None or vb is None:
                continue
            self.stats["pairs"] += 1
            first = self._step(va, self.ex.routes_for(va)[0])
            self._unwind(va)
            second = self._step(vb, self.ex.routes_for(vb)[0])
            self._unwind(vb)
            verdict = "works" if second[0] and second[2] != "no_effect" else ("no_effect" if second[0] else "unreachable")
            if self.history is not None:
                try:
                    self.history.log(self.app_key, PAIR_SOURCE, "pair", f"{a} + {b}"[:110], "order", "", "", "", f"{first[1]} -> {second[1]}"[:200], verdict, verdict == "works", None,
                                     "", {"ab": [first[2], second[2]], "order": "ab"}, toolkit=self.toolkit, archetype=self.archetype, safety="safe")
                    self.history.log(self.app_key, PAIR_SOURCE, "pair", f"{b} + {a}"[:110], "order", "", "", "", f"{second[1]} -> {first[1]}"[:200], verdict, verdict == "works", None,
                                     "", {"ab": [second[2], first[2]], "order": "ba"}, toolkit=self.toolkit, archetype=self.archetype, safety="safe")
                except Exception:                                                      # noqa: BLE001
                    pass
            out.append({"pair": [a, b], "verdict": verdict, "ab": [first[2], second[2]], "ba": [second[2], first[2]]})
        return out


def practise(ex: Any, fx: Any, history: Any, cat: Any, app_key: str, hwnd: int, *, toolkit: str = "", archetype: str = "", mode: str = "full",
             steps: Optional[List[Any]] = None, max_verbs: int = 0, budget_s: float = 0.0, log: Optional[Any] = None) -> Dict[str, Any]:
    """The whole exercise session, capped in count and in time (a run must not spend its evening practising). Returns what was done, for the report."""
    max_verbs = max_verbs or int(os.environ.get("HOJAIGA_PRACTICE_MAX", "10"))
    budget_s = budget_s or float(os.environ.get("HOJAIGA_PRACTICE_BUDGET", "120"))
    if mode == "navigate" or ex is None or fx is None:                                 # an application holding the person's account is never experimented on
        return {"skipped": "navigate mode: the account is the person's" if mode == "navigate" else "no executor / effector"}
    t0 = time.time()
    p = Practise(ex, fx, history, app_key, hwnd, toolkit=toolkit, archetype=archetype, log=log)
    verbs = pick_verbs(cat, ex, max_verbs)
    p.log(f"practice: {len(verbs)} reversible, safe control(s) out of {len(getattr(cat, 'verbs', []) or [])} catalogued")
    routes = p.route_permutations(verbs, budget_s * 0.6)
    left = max(0.0, budget_s - (time.time() - t0))
    orders = p.order_combinations(pair_targets(steps or [], max(2, max_verbs // 2)), left)
    p.stats["seconds"] = round(time.time() - t0, 1)
    p.stats["routes_detail"] = routes[:24]
    p.stats["pairs_detail"] = orders[:12]
    return p.stats
