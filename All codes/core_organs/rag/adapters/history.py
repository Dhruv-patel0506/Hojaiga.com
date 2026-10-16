"""professor.history app registry -> Lexicon apps table (tier, toolkit), so the router knows an app's tier before it has a snapshot."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


def sync_apps(rag, registry: Optional[Iterable[Dict[str, Any]]] = None) -> int:
    if registry is None:
        from core_organs.professor import history as H
        registry = H.library().registry()
    n = 0
    for r in registry:
        key = r.get("app_key") or r.get("key")
        if key:
            tier = r.get("tier")
            rag.lex.set_app(key, tier=tier if isinstance(tier, int) and tier >= 0 else None, toolkit=r.get("toolkit", "") or "")
            n += 1
    return n
