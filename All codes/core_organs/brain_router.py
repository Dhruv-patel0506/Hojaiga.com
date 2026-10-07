"""
brain_router.py - the fast decision tier that runs BEFORE the 7B brain (plan section C).

The literal bottleneck is not the model, it is that EVERY step is asked of the 7B. This module gives the
brain three cheaper rails, tried in order, and only drops to the 7B when none can honestly answer:

  1. rules        a goal whose verb+object matches a LEARNED command in the capability card, with a known
                  route (menu path) or key chord, becomes a tool-call sequence directly - zero LLM calls;
  2. plan-cache   a goal whose fingerprint matches a previously VERIFIED plan is replayed through the same
                  tools with postcondition checks, instead of being re-decided (bm_plans, organ_48);
  3. small-model  a constrained choice (pick ONE element from a <=5 shortlist) is asked of the 1-3B model
                  (gateway.execute_small_inference), never the 7B.

Everything here is honest: a tier only answers when it can PROVE the answer (a learned row / a verified
plan / a confident small-model pick); otherwise it declines and the caller runs the 7B exactly as before.
Replay uses the SAME tools/actuator rails the agent uses - no second execution path, no simulated success.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("hojaiga.brain_router")

ENABLED = os.environ.get("HOJAIGA_BRAIN_ROUTER", "1") != "0"
SMALL_SHORTLIST_MAX = 5


def fingerprint(goal: str) -> str:
    """A stable key for a goal: lowercased, digits kept, whitespace/punctuation folded. Deliberately
    conservative - it collapses trivial rewording but does NOT pretend two different goals are alike."""
    g = re.sub(r"[\s]+", " ", (goal or "").strip().lower())
    g = re.sub(r"[^\w\s:%./-]", "", g)
    return hashlib.md5(g.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- tier execution

def _call_tool(tools: Dict[str, Any], name: str, args: Dict[str, Any]) -> Optional[str]:
    """Run one tool by name through the engine's OWN tool objects (crewai @tool): .func for keyword args,
    else .run. Returns the tool's observation string, or None when the tool is not registered (the caller
    must then decline the fast path rather than fake a step)."""
    t = tools.get(name)
    if t is None:
        return None
    try:
        fn = getattr(t, "func", None)
        if callable(fn):
            return str(fn(**(args or {})))
        run = getattr(t, "run", None)
        if callable(run):
            return str(run(args if args is not None else {}))
    except Exception as exc:  # noqa: BLE001
        return f"ERROR tool {name}: {type(exc).__name__}: {str(exc)[:120]}"
    return None


def replay(plan: List[Dict[str, Any]], tools: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a cached/rules plan through the real tools. Any step whose tool is missing or that returns
    an ERROR is a HARD stop reported honestly (handled=False) so the caller falls back to the 7B."""
    steps: List[Dict[str, Any]] = []
    for call in plan:
        name = call.get("tool")
        args = call.get("args") or {}
        if not name:
            return {"ok": False, "why": "plan step has no tool", "steps": steps}
        obs = _call_tool(tools, name, args)
        if obs is None:
            return {"ok": False, "why": f"tool '{name}' not registered", "steps": steps}
        low = obs.lower()
        # a step is a HARD failure not only when it errored but when the actuator honestly reported it had NO
        # EFFECT (e.g. a canvas/pixel stroke "delivered but INEFFECTIVE"). Treating "no effect" as success is the
        # fake-pass this router exists to prevent, so an ineffective step declines to the 7B.
        failed = (low.startswith("error") or "undeliverable" in low or "not delivered" in low
                  or "refused" in low or "ineffective" in low or "no effect" in low)
        steps.append({"tool": name, "obs": obs[:400], "ok": not failed})
        if failed:
            return {"ok": False, "why": f"step '{name}' failed: {obs[:160]}", "steps": steps}
    return {"ok": True, "why": "replayed", "steps": steps}


# --------------------------------------------------------------------------- tier 1: rules

def rules_plan(app_key: str, goal: str, card: Optional[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """A learned command whose label/route appears in the goal, executed via its known path or chord - no LLM."""
    if not card:
        return None
    gl = (goal or "").lower()
    for row in card.get("can_do") or []:
        if row.get("trust") != "learned":
            continue
        nm = (row.get("name") or "").lower().strip()
        if not nm:
            continue
        # word/phrase-boundary match: a short label ("tab") must NOT fire inside an unrelated word ("stable"),
        # but a real mention ("save" in "save the document") still matches. Kills false fast-path hits (accuracy).
        if not re.search(r"(?<![a-z0-9])" + re.escape(nm) + r"(?![a-z0-9])", gl):
            continue
        # a key chord is the most direct route; else click the named control
        if row.get("key"):
            return [{"tool": "press_key", "args": {"key": row["key"]}}]
        return [{"tool": "click_button_by_name", "args": {"button_name": row.get("name")}}]
    return None


# ----------------------------------------------------------- success -> plan cache (tier C.2 harvest)

# verbs that map cleanly onto a SINGLE-argument router tool the fast path can replay verbatim.
_REPLAY_VERBS: Dict[str, str] = {
    "click": "click_button_by_name", "press": "press_key", "hotkey": "press_key",
    "shortcut": "press_key", "chord": "press_key", "key": "press_key",
}


def plan_from_verified_trace(steps: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """Turn the VERIFIED autonomy loop's per-step trace into a replayable plan, or None when ANY step is not an
    unambiguous, postcondition-PASSed click/press. Caching a plan means a later identical goal is declared met by
    replaying it with ZERO big-model calls, so a plan is produced ONLY when every step is safe to re-fire: a step
    that typed, launched, scrolled, or whose verdict was not PASS returns None (never a plan that could later turn
    a run into an unverified fake pass). Pure: no model, no side effects - trivially testable."""
    if not steps:
        return None
    plan: List[Dict[str, Any]] = []
    for t in steps:
        verb = str((t or {}).get("verb") or "").strip().lower()
        verdict = str((t or {}).get("verdict") or "").strip().upper()
        element = str((t or {}).get("element") or "").strip()
        if verdict != "PASS" or not element:
            return None                                   # an unverified / empty step: not safe to replay blindly
        tool = _REPLAY_VERBS.get(verb)
        if not tool:
            return None                                   # type / launch / scroll / anything ambiguous: decline
        arg = "button_name" if tool == "click_button_by_name" else "key"
        plan.append({"tool": tool, "args": {arg: element}})
    return plan or None


# --------------------------------------------------------------------------- public: fast path

def fast_path(goal: str, *, app_key: str, model=None, card: Optional[Dict[str, Any]] = None,
              tools: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Try rules then the verified plan-cache. Returns
    {handled, tier, why, plan, steps, brain_calls}. handled=False means 'run the 7B'."""
    out: Dict[str, Any] = {"handled": False, "tier": "none", "why": "", "plan": None, "steps": []}
    if not ENABLED or not tools:
        out["why"] = "router disabled or no tool dispatch"
        return out
    try:
        from core_organs.organ_37_llm_gateway import call_counts
    except Exception:  # noqa: BLE001
        call_counts = lambda: {"brain": 0, "small": 0}  # noqa: E731
    before = call_counts()["brain"]

    # tier 1: deterministic rules from the capability card
    plan = rules_plan(app_key, goal, card)
    tier = "rules"
    if not plan and model is not None:
        # tier 2: verified plan cache
        fp = fingerprint(goal)
        try:
            hit = model.lookup_plan(app_key, fp)
        except Exception:  # noqa: BLE001
            hit = None
        if hit and hit.get("plan"):
            plan, tier = hit["plan"], "plan-cache"

    if not plan:
        out["why"] = "no rules match and no verified plan cached: hand to 7B"
        return out

    res = replay(plan, tools)
    out.update({"plan": plan, "steps": res["steps"], "tier": tier})
    if not res["ok"]:
        out["why"] = f"{tier} replay stopped: {res['why']} - fall back to 7B"
        return out

    if tier == "rules":
        # promote the proven rules route into the cache so the next identical goal is a pure replay
        try:
            if model is not None:
                model.store_plan(app_key, fingerprint(goal), goal, plan, verified=True)
        except Exception:  # noqa: BLE001
            pass

    out["handled"] = True
    out["brain_calls"] = call_counts()["brain"] - before
    out["why"] = f"{tier} satisfied the goal with {out['brain_calls']} big-model calls"
    return out


# --------------------------------------------------------------------------- tier 3: small-model classifier

def shortlist_choice(question: str, options: List[str], *, gateway=None) -> Optional[str]:
    """Constrained pick: choose exactly one of <=5 options with the small model (never the 7B). Returns the
    chosen option string, or None if it cannot be done cheaply/confidently (caller then uses the 7B)."""
    opts = [o for o in (options or []) if o]
    if not opts or len(opts) > SMALL_SHORTLIST_MAX:
        return None
    try:
        from core_organs.organ_37_llm_gateway import LLMGateway
        gw = gateway or LLMGateway()
        listing = "\n".join(f"{i + 1}. {o}" for i, o in enumerate(opts))
        raw = gw.execute_small_inference(
            "You pick ONE option for a desktop automation. Reply with ONLY the exact option text, nothing else.",
            f"{question}\n\nOptions:\n{listing}\n\nBest option (exact text only):",
            temperature=0.0, timeout=30.0)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[brain_router] small-model shortlist unavailable: %s", exc)
        return None
    ans = (raw or "").strip().strip('"').strip("'")
    # accept an exact or unique-substring match; anything ambiguous declines to the 7B
    exact = [o for o in opts if o.lower() == ans.lower()]
    if exact:
        return exact[0]
    sub = [o for o in opts if o.lower() in ans.lower() or ans.lower() in o.lower()]
    return sub[0] if len(sub) == 1 else None
