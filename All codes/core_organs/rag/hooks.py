"""
rag.hooks -- the three integration points between the Professor and the RAG. Every function is safe to call from existing code: it never raises, does nothing when HOJAIGA_RAG=off or the
RAG is unavailable, and returns exactly what the caller's own old path returns when it has nothing to add (DESIGN.md section 15 step 10: the old path stays the fallback).

    observe_report(app_key, report)     executor -> RAG: an ExecReport's attempted steps become Outcomes (routes learn reliability, verbs become known commands, telemetry is kept)
    prompt_lines(question, app_key)     teacher / manual_rag -> RAG: cited passages for an application the manual index has nothing for (same per-app partition: never another program's text)
    enabled()                           the single switch
"""
from __future__ import annotations

import os
import time
from typing import Any, List, Tuple

_ATTEMPTED = {"done": True, "no_effect": False, "failed": False}       # statuses that mean "the route was tried"; refused / needs_human / skipped / dry_run / unknown / disabled were not
_ROUTE_KIND = {"shortcut": "hotkey", "command": "wm_command", "control": "uia_invoke", "key": "hotkey", "value": "type", "click": "posted_click", "text": "type"}


def enabled() -> bool:
    return os.environ.get("HOJAIGA_RAG", "on").lower() not in ("off", "0", "false", "no")


def _rag():
    from . import get_rag
    return get_rag()


def observe_report(app_key: str, report: Any) -> int:
    """Feed a finished ExecReport to the RAG. Returns how many steps were reported (0 when disabled / nothing attempted / any failure)."""
    if not enabled() or not app_key or report is None or getattr(report, "dry_run", True):
        return 0
    try:
        from .lexicon import command_id
        from .types import Outcome, PlanStep
        R = _rag()
        run_id = f"exec-{int(time.time())}-{id(report) & 0xffff:04x}"
        by_index = {s.index: s for s in getattr(report, "steps", [])}
        n = 0
        for res in getattr(report, "results", []):
            ok = _ATTEMPTED.get(res.status)
            if ok is None:
                continue
            step = by_index.get(res.index)
            label = (step.verb if step and step.verb else (step.goal if step else "")) or res.verb
            if not label and not (step and step.kind == "text"):
                continue
            kind, _, detail = (res.route or "").partition(":")
            route = _ROUTE_KIND.get(kind, "control_click")
            cid = command_id(app_key, label) if label else f"{app_key}:type"
            args = {"label": label}
            if route == "hotkey" and detail:
                chord = detail.lower().replace(" ", "")
                args["keys"] = chord
                for ev in R.fast.by_command(app_key, cid, limit=10):         # credit the vault row that carries this very chord
                    if ev.payload["payload"] == chord:
                        args["fast_id"] = ev.payload["fast_id"]
                        break
            if ok and res.verified is False:
                ok = False                                                   # the screen did not show the expected result: the route did not work
            if ok and label:
                R.lex.add_command(app_key, label, source="executor", trust="learned")
            R.observe(Outcome(run_id, app_key, PlanStep(cid, route, args, None, res.expected[:60], 0.5, getattr(step, "safety", "allow") if getattr(step, "safety", "safe") != "safe" else "allow"),
                              ok=bool(ok), effect=res.effect or ("" if ok else "no_effect"), latency_ms=float(res.ms or 0), failure_code="" if ok else (res.status if res.status != "done" else "no_effect")))
            n += 1
        return n
    except Exception:
        return 0


def prompt_lines(question: str, app_key: str, max_chars: int = 520, k: int = 3) -> Tuple[str, List[Any]]:
    """('MANUAL EXCERPTS ...' text, [Passage-like]) from the RAG for an application, or ('', []). Only that application's own passages are ever returned."""
    if not enabled() or not app_key:
        return "", []
    try:
        from . import storage as ST
        from . import _RAG
        if _RAG is None and not os.path.isfile(os.path.join(ST.resolve_root()[0], "rag", "meta.json")):
            return "", []                          # nothing has ever been ingested: do not create a store just to find it empty
        R = _rag()
        if R.proc.chunk_count(app_key) == 0:
            return "", []
        ev = R.proc.query(app_key, question, "", None, k)
        if not ev:
            return "", []
        from core_organs.professor.knowledge.manual_rag import Passage
        ps = [Passage(e.text[:max_chars], e.payload.get("heading_path") or e.citation, app_key, e.payload.get("source_kind", ""), e.score, e.citation, "rag") for e in ev]
        lines = [f"[{i}] ({p.cite}) {p.text}" for i, p in enumerate(ps, 1)]
        return "MANUAL EXCERPTS (quoted from the application's own documentation; prefer these over memory):\n" + "\n".join(lines), ps
    except Exception:
        return "", []
