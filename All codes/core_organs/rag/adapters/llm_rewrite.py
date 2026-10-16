"""The one capped LLM call of the router (weak recall only): rewrite a user phrase into two manual-style queries. Uses the Professor's brain when reachable; returns [] otherwise."""
from __future__ import annotations

from typing import Callable, List


def rewriter(brain=None, timeout_s: float = 4.0) -> Callable[[str, str], List[str]]:
    def _r(app_key: str, goal: str) -> List[str]:
        b = brain
        if b is None:
            from core_organs.professor import brain as BR
            b = getattr(BR, "get", lambda: None)() or getattr(BR, "brain", lambda: None)()
        if b is None or not hasattr(b, "text"):
            return []
        prompt = (f"Application: {app_key}. A user asked: '{goal}'. Write exactly two short search queries, one per line, in the wording of the application's user manual "
                  "(menu and command names). No numbering, no commentary.")
        txt = b.text(prompt, timeout=timeout_s)
        return [l.strip(" -*\t") for l in str(txt).splitlines() if l.strip()][:2]
    return _r
