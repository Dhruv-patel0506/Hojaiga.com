"""
goal_planner.py - turns ONE compound instruction into an ORDERED list of atomic, individually-verifiable
sub-goals, so the closed-loop executor (which proves one action per step) can drive it.

WHY THIS EXISTS (measured 2026-10-07). With perception and actuation both working - a parked WinUI
Calculator now exposes its 48 named buttons and every one is clickable through UIA Invoke, each press
verified PASS - a single compound goal like "add 21 and 21" / "type 21, press +, type 21, press ="
still failed: the judge is asked to pick EXACTLY ONE element per step, so a multi-action sentence has no
honest single answer and the run burned three invalid strikes straight to human-in-the-loop. The same
instruction, split into "press 2 / press 1 / press plus / press 2 / press 1 / press equals", completed
6/6 PASS. So the missing piece is not seeing or touching the app - it is DECOMPOSITION.

Generic by construction:
  * nothing here knows an app's name or a specific key layout. The plan is grounded ONLY in the control
    labels the running app actually exposes (passed in), and every emitted step must name one of them;
  * if a confident, fully-grounded plan cannot be produced, the ORIGINAL goal is returned untouched -
    decomposition can only ever make a run as good as before, never worse, and never fake a step;
  * each sub-goal stays a normal goal, so the postcondition verifier still judges every press on its own.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hojaiga.goal_planner")

ENABLED = os.environ.get("HOJAIGA_GOAL_PLANNER", "1") != "0"

# verbs that mean "one discrete on-screen action" - a goal stringing two or more of these is compound.
_ACTION_VERBS = ("press", "click", "tap", "type", "enter", "select", "choose", "invoke",
                 "toggle", "hit", "push", "open", "close", "save", "submit", "clear")
# an arithmetic sentence is compound even when it spells no verbs ("add 21 and 21", "what is 7 times 8").
_ARITH_RE = re.compile(r"\b(add|plus|subtract|minus|multiply|times|multiplied|divide|divided|over|"
                       r"mod(?:ulo)?|power|squared|calculate|compute|equals?)\b", re.I)
_CHAIN_RE = re.compile(r"\b(?:then|and then|after that|followed by)\b|\b(?:press|click|type)\b[^,.;]*"
                       r"[,;]\s*(?:press|click|type)\b", re.I)


def is_compound(goal: str) -> bool:
    """True when ONE goal clearly asks for MORE than a single discrete action."""
    g = (goal or "").strip()
    if not g:
        return False
    verbs = sum(len(re.findall(r"\b" + v + r"\b", g, re.I)) for v in _ACTION_VERBS)
    if verbs >= 2:
        return True
    if _CHAIN_RE.search(g):
        return True
    # "add 21 and 21", "5 plus 3": an arithmetic expression the app must be walked through key by key.
    if _ARITH_RE.search(g) and re.search(r"\d", g):
        return True
    return False


def _norm(label: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (label or "").lower())).strip()


# Universal English key vocabulary - NOT an app's names. The digits and the arithmetic operators are the same
# words in every keyboard UI; we only ever check whether a control whose OWN label matches one of them is on
# screen, so nothing is assumed about which app is running.
_DIGIT_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_OP_SYNONYMS = {
    "+": ("plus", "add"),
    "-": ("minus", "subtract"),
    "*": ("multiply by", "times", "multiply"),
    "/": ("divide by", "divide", "over"),
    "=": ("equals", "equal"),
    ".": ("point", "decimal point", "dot"),
    "(": ("left parenthesis", "open parenthesis"),
    ")": ("right parenthesis", "close parenthesis"),
}
_MAX_PLAN_STEPS = 40


# English arithmetic is the same everywhere - this reads the instruction's OWN words, never an app.
_ARITH_OP_WORDS = (
    (r"\b(?:add|plus)\b", "+"),
    (r"\b(?:subtract|minus|less)\b", "-"),
    (r"\b(?:multiply|multiplied|times)\b", "*"),
    (r"\b(?:divide|divided|over)\b", "/"),
)


def _deterministic_expression(goal: str) -> Optional[str]:
    """Read a plain arithmetic instruction into an expression from its own words - no model, so no drift:
    'add 21 and 21'->'21+21', 'subtract 5 from 30'->'30-5', 'what is 7 times 8'->'7*8', '21 + 21'->'21+21'.
    Returns None for anything that is not exactly two operands and one operator (the caller then asks the
    model, and if that too fails the goal is kept whole)."""
    g = (goal or "").lower()
    nums = re.findall(r"\d+(?:\.\d+)?", g)
    # an already-symbolic expression wins if it is there verbatim ('21+21', '7 * 8')
    sym = re.search(r"\d+(?:\.\d+)?\s*[-+*/x×÷]\s*\d+(?:\.\d+)?", g)
    if sym:
        e = sym.group(0).replace("×", "*").replace("÷", "/").replace("x", "*")
        return re.sub(r"\s+", "", e)
    if len(nums) != 2:
        return None
    op = None
    for pat, o in _ARITH_OP_WORDS:
        if re.search(pat, g):
            op = o
            break
    if op is None:
        return None
    # 'subtract 5 from 30' reads with the second number as the left operand (30-5). 'divide 30 by 5' does NOT
    # swap (30/5), so only the '-' + 'from' shape reverses.
    if op == "-" and re.search(r"\bfrom\b", g):
        a, b = nums[1], nums[0]
    else:
        a, b = nums[0], nums[1]
    return f"{a}{op}{b}"


def _label_for(token: str, labels: List[str]) -> Optional[str]:
    """The on-screen control whose own label IS this key (a digit word/digit, or an operator synonym),
    else None. Matching is by normalized label equality, so an app that names a key differently just is not
    matched and the plan is rejected - we never press something the model invented."""
    t = _norm(token)
    if len(t) == 1 and t.isdigit():
        want = _DIGIT_WORDS[int(t)]
        return next((l for l in labels if _norm(l) in (want, t)), None)
    return next((l for l in labels if _norm(l) == t), None)


def _map_expression(expr: str, labels: List[str]) -> Optional[List[str]]:
    """Deterministically turn '21+21=' into the ordered on-screen labels for it. Any character with no
    matching control rejects the whole plan (None) - never a partial or invented sequence."""
    out: List[str] = []
    for ch in (expr or ""):
        if ch.isspace():
            continue
        if ch in "*x×":
            ch = "*"
        elif ch in "/÷":
            ch = "/"
        elif ch in "-–":
            ch = "-"
        hit = _label_for(ch, labels)
        if hit is None:
            for syn in _OP_SYNONYMS.get(ch, ()):
                hit = next((l for l in labels if _norm(l) == _norm(syn)), None)
                if hit:
                    break
        if hit is None:
            return None
        out.append(hit)
    return out or None


def _expression_via_model(goal: str) -> Optional[str]:
    """For an arithmetic instruction, ask the model ONLY for the literal expression to key in - digits and
    + - * / . = only, in order, NOT the answer. A one-line echo of the numbers is far more reliable for a
    small model than emitting a whole button plan (measured: asked for labels it hallucinated 78-78+21+21)."""
    expr = _ask_model(goal,
                      "Return ONLY the arithmetic expression this instruction means, using just the characters "
                      "0-9 + - * / . = with no spaces and no other words. Do NOT compute or give the result - "
                      "give the keys to press in order.\nINSTRUCTION: ")
    if not expr or not re.fullmatch(r"[0-9+\-*/.= ]{1,40}", expr.strip()):
        return None
    return expr.strip()


def _labels_via_model(goal: str, labels: List[str]) -> Optional[List[str]]:
    """For a compound that is NOT arithmetic ('click File then click Save'), ask the model for the ordered
    list of exact on-screen labels to press; every returned label must actually be on screen."""
    listing = ", ".join(repr(l) for l in labels[:180])
    presses = _ask_model(goal,
                         "Turn this instruction into the exact ORDER of on-screen controls to press, one per "
                         "step. Use ONLY labels from CONTROLS spelled exactly; if it cannot be done, return an "
                         f"empty list.\nCONTROLS: [{listing}]\nINSTRUCTION: ")
    if not presses:
        return None
    by_norm = {_norm(l): l for l in labels}
    out: List[str] = []
    for raw in presses if isinstance(presses, list) else []:
        hit = by_norm.get(_norm(str(raw)))
        if hit is None:
            return None
        out.append(hit)
    return out or None


def _ask_model(goal: str, preamble: str) -> Any:
    """One grounded Ollama call. Returns parsed JSON for non-arithmetic prompts, or the plain expression
    string for the arithmetic prompt (detected by its wording). None on any doubt or error."""
    from core_organs.desktop_grounding import BRAINS_CHAT_URL, JUDGE_MODEL  # lazy: no import cycle
    prompt = preamble + (goal or "")
    is_arith = "arithmetic expression" in prompt
    payload = {"model": JUDGE_MODEL, "stream": False,
               "messages": [{"role": "user", "content": prompt}],
               "options": {"temperature": 0.0, "num_predict": (40 if is_arith else 200)}}
    if not is_arith:
        payload["format"] = "json"
    try:
        req = urllib.request.Request(BRAINS_CHAT_URL, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=float(os.environ.get("HOJAIGA_PLAN_TIMEOUT_S", "30"))) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = ((body.get("message", {}) or {}).get("content", "") or body.get("response", "")).strip()
    except Exception as exc:  # noqa: BLE001
        logger.debug("[plan] model unavailable (%s): leaving the goal whole", exc)
        return None
    if is_arith:
        return content.strip().strip('"').strip("'")
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0)).get("presses")
    except Exception:  # noqa: BLE001
        return None


def expand(goal: str, labels: List[str]) -> List[str]:
    """A compound goal -> an ordered list of atomic 'press <exact label>' sub-goals.

    Arithmetic ('add 21 and 21'): the model returns ONLY the expression, then each character is mapped
    deterministically to a real on-screen key and an '=' is appended - the model never chooses buttons.
    Any other compound ('click File then click Save'): the model returns the ordered labels, each validated.
    Anything that cannot be grounded to real controls comes back as [goal] unchanged (never worse)."""
    if not ENABLED or not goal or not labels or not is_compound(goal):
        return [goal]
    try:
        arithmetic = bool(_ARITH_RE.search(goal)) and bool(re.search(r"\d", goal or ""))
        if arithmetic:
            expr = _deterministic_expression(goal)          # read the words first: a model drifts on 'add 21 and 21'
            if not expr:
                expr = _expression_via_model(goal)
            if not expr:
                return [goal]
            if "=" not in expr:
                expr += "="
            presses = _map_expression(expr, labels)
            logger.info("[plan] arithmetic '%s' -> expression %s", goal[:40], expr)
        else:
            presses = _labels_via_model(goal, labels)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[plan] expansion error (%s): goal kept whole", exc)
        return [goal]
    if not presses or len(presses) < 2 or len(presses) > _MAX_PLAN_STEPS:
        return [goal]
    logger.info("[plan] '%s' -> %s", goal[:48], [f"press {p}" for p in presses])
    return [f"press {p}" for p in presses]

