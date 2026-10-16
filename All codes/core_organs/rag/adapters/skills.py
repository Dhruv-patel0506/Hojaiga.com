"""professor.skills (verified macro library) <-> the router: a skills_provider for DO requests, and verified skills exported as Sub-RAG 4 chord sequences."""
from __future__ import annotations

from typing import Any, Callable, List, Optional

from ..lexicon import canon
from ..types import PlanStep

_ROUTE = {"shortcut": "hotkey", "command": "wm_command", "control": "uia_invoke", "key": "hotkey", "text": "type"}


def steps_of(skill, app_key: str) -> List[PlanStep]:
    out = []
    for s in skill.steps:
        kind, _, detail = (s.route or "").partition(":")
        route = _ROUTE.get(kind or s.kind, "control_click")
        if s.kind == "text":
            route, args = "type", {"text": s.text}
        else:
            args = {"keys": detail} if route == "hotkey" else {"label": s.label, "path": list(s.path), "aid": s.aid}
        out.append(PlanStep(f"{app_key}:{canon(s.label or s.text or detail)}", route, args, None, s.label[:60], max(0.5, min(0.98, 0.5 + 0.1 * skill.verified)), "allow", [], False))
    return out


def provider(library: Any = None) -> Callable[[str, str], Optional[List[PlanStep]]]:
    def _p(goal: str, app_key: str) -> Optional[List[PlanStep]]:
        lib = library
        if lib is None:
            from core_organs.professor import skills as SK
            lib = SK.library()
        sk = lib.find(goal, app_key)
        return steps_of(sk, app_key) if sk and sk.steps else None
    return _p


def export_skills(rag, app_key: str, library: Any = None) -> int:
    lib = library
    if lib is None:
        from core_organs.professor import skills as SK
        lib = SK.library()
    rows = []
    for sk in lib.all(app_key):
        if sk.verified < 1 or not sk.steps or sk.status != "active":
            continue
        keys = [s.route.partition(":")[2] for s in sk.steps if s.route.startswith("shortcut:")]
        if len(keys) == len(sk.steps):
            rows.append({"app_key": app_key, "kind": "chord_seq", "task_pattern": sk.name, "payload": " ".join(keys), "source": "skill", "trust": "verified", "verified": True,
                         "n_ok": sk.verified, "n_fail": sk.failed})
    rep = rag.fast.upsert(rows) if rows else None
    return (rep.inserted + rep.updated) if rep else 0
