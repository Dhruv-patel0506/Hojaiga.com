"""professor.workflows documents (guide procedures analysed against the live catalog) -> Sub-RAG 3 procedures, keeping each workflow's existing id."""
from __future__ import annotations

from typing import Any, Dict, Optional


def from_workflows(rag, app_key: str, doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if doc is None:
        from core_organs.professor import workflows as WF
        doc = WF.load(app_key)
    if not doc:
        return {"procedures": 0, "error": "no_workflow_document"}
    n = 0
    for wf in doc.get("workflows", []):
        if wf.get("status") in ("other-edition", "ungrounded"):
            continue
        steps = []
        for s in wf.get("steps", []):
            chord = s.get("shortcut") or s.get("chord") or ""
            vp = s.get("verb_path") or []
            steps.append({"text": s.get("text", ""), "target": s.get("verb") or s.get("target") or "", "chord": chord, "menu_path": vp if len(vp) > 1 else [],
                          "route_hint": "hotkey" if chord else ("menu_path" if len(vp) > 1 else ("type" if s.get("typed") else "control_click")), "safety": s.get("safety", "")})
        if steps:
            rag.proc.ingest_procedure(app_key, wf.get("goal") or wf.get("title") or wf.get("id", ""), steps, str(wf.get("cite") or doc.get("guide_key") or "guide"),
                                      trust="official_doc", procedure_id=str(wf.get("id", "")))
            n += 1
    return {"procedures": n}
