"""The one capped LLM call of the router (weak recall only -- DESIGN.md 7.6, never on every query): rewrite a user phrase into two manual-style queries.
Uses the Professor's Brain (vision server, else Ollama). Returns [] when no model is reachable, so the router simply reports the gap."""
from __future__ import annotations

from typing import Callable, List

_SYSTEM = "You rewrite a user's request into the wording an application's user manual would use (menu and command names). Reply with exactly two short search queries, one per line. No numbering, no commentary."


def rewriter(brain=None, timeout_s: float = 4.0) -> Callable[[str, str], List[str]]:
    def _r(app_key: str, goal: str) -> List[str]:
        b = brain
        if b is None:
            from core_organs.professor.brain import brain as get_brain
            b = get_brain()
        if not b.available():                              # cached for seconds: costs nothing when the model is down
            return []
        res = b.generate(_SYSTEM, f"Application: {app_key}\nUser request: {goal}", max_tokens=60, temperature=0.0, timeout=timeout_s)
        if not res.ok:
            return []
        return [l.strip(" -*\t0123456789.)") for l in res.text.splitlines() if l.strip()][:2]
    return _r
