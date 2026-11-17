"""
professor.archetype -- WORKSPACE TOPOLOGY -> MENTAL MODEL: what KIND of software is this, so the Professor knows where properties live, where structure lives and how work flows.

A human expert opening an unfamiliar tool recognises its kind from the layout and the verbs (a centre viewport with an outliner and an inspector is a 3D tool; a
bottom multi-track timeline is a media editor). The same evidence is available here without a rulebook per application:
  * VERBS      the catalog's menu / control labels  ("Extrude", "Modifier", "Render" -> spatial 3D; "Trim", "Track", "Ripple" -> timeline media)
  * AREAS      captions of the editor areas the scan found ("Outliner", "Properties", "Timeline", "Layers", "Explorer" ...)
  * LAYOUT     facts about where the areas sit (a big centre canvas, a right-hand panel, a bottom panel, a ribbon, a tab strip)
Scores are transparent (every point has its evidence listed). When two kinds are too close and a language model is reachable, it ADJUDICATES between the candidates
given that evidence -- it never invents a kind. Archetypes and their blueprints are data (data/archetypes.json), categories only (law L3).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .schema import ScreenModel, fold

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "archetypes.json")
_CACHE: Dict[str, Any] = {}


def library() -> List[Dict[str, Any]]:
    if "a" not in _CACHE:
        try:
            with open(_DATA, "r", encoding="utf-8") as fh:
                _CACHE["a"] = json.load(fh)["archetypes"]
        except Exception:
            _CACHE["a"] = []
    return _CACHE["a"]


def blueprint(archetype_id: str) -> Dict[str, Any]:
    return next((a for a in library() if a["id"] == archetype_id), {})


def layout_facts(sm: ScreenModel) -> Dict[str, bool]:
    """Where things sit, from the scan's areas (positions relative to the picture / window)."""
    W, H = max(1, sm.size[0]), max(1, sm.size[1])
    ox, oy = sm.origin
    facts = {"center_canvas": False, "right_panel": False, "left_panel": False, "bottom_panel": False, "ribbon": False, "tab_strip": False, "dialog": False}
    for r in sm.regions:
        b = r.bbox.shift(-ox, -oy)
        frac = b.area / (W * H)
        if r.kind == "canvas" and frac >= 0.2:
            facts["center_canvas"] = True
        if r.kind in ("panel", "list", "sidebar") and b.w < 0.45 * W and b.h > 0.35 * H:
            if b.cx > 0.6 * W:
                facts["right_panel"] = True
            elif b.cx < 0.4 * W:
                facts["left_panel"] = True
        if r.kind in ("panel", "list", "toolbar") and b.w > 0.45 * W and b.cy > 0.65 * H and b.h > 0.08 * H:
            facts["bottom_panel"] = True
        if r.kind == "ribbon":
            facts["ribbon"] = True
        if r.kind == "tab_strip":
            facts["tab_strip"] = True
        if r.kind == "dialog":
            facts["dialog"] = True
    if W < 900 and H < 700 and sm.window_title and not facts["center_canvas"] and len([e for e in sm.elements if e.role in ("field", "checkbox", "radio")]) >= 3:
        facts["dialog"] = True
    return facts


def _words(texts: Sequence[str]) -> str:
    return " " + " ".join(fold(t) for t in texts if t) + " "


def classify(sm: ScreenModel, catalog: Any = None, brain: Any = None, margin: float = 0.18) -> Dict[str, Any]:
    """{'id','name','confidence','evidence':[...],'ranked':[(id,score)],'blueprint':{...},'by':'rules'|'rules+model'}"""
    verbs = [v.label for v in (catalog.verbs if catalog is not None else [])] + [" ".join(v.path) for v in (catalog.verbs if catalog is not None else [])]
    verbs += [e.label for e in sm.elements if e.role in ("menu_item", "tab", "button", "dropdown") and e.label]
    areas = [r.label for r in sm.regions if r.label] + [e.label for e in sm.elements if e.label and e.role in ("text", "tab", "list_item", "tree_item")][:200]
    vtext, atext = _words(verbs), _words(areas)
    facts = layout_facts(sm)
    ranked: List[Tuple[float, str, List[str]]] = []
    for a in library():
        score, ev = 0.0, []
        for kw in a.get("verbs", []):
            if f" {fold(kw)} " in vtext or (len(kw) > 4 and f" {fold(kw)}" in vtext):
                score += 1.0
                ev.append(f"verb:{kw}")
        for kw in a.get("regions", []):
            if f" {fold(kw)} " in atext or f" {fold(kw)} " in vtext:
                score += 1.8
                ev.append(f"area:{kw}")
        want = a.get("layout", [])
        hit = [k for k in want if facts.get(k)]
        score += 1.2 * len(hit)
        ev += [f"layout:{k}" for k in hit]
        miss = [k for k in want if not facts.get(k)]
        score -= 0.5 * len(miss)
        if a["id"] == "settings_form" and not facts["dialog"]:
            score -= 3.0
        if a["id"] != "settings_form" and facts["dialog"] and not facts["center_canvas"]:
            score -= 1.5
        ranked.append((round(score, 2), a["id"], ev))
    ranked.sort(key=lambda t: -t[0])
    top, second = ranked[0], (ranked[1] if len(ranked) > 1 else (0.0, "", []))
    total = sum(max(0.0, s) for s, _i, _e in ranked) or 1.0
    conf = round(max(0.0, top[0]) / total, 3)
    by = "rules"
    chosen = top[1] if top[0] > 1.5 else "unknown"
    close = top[0] > 1.5 and second[0] > 0 and (top[0] - second[0]) / max(1.0, top[0]) < margin
    if close and brain is not None:
        try:
            if brain.available():
                names = {i: next(a["name"] for a in library() if a["id"] == i) for _s, i, _e in ranked[:3]}
                ev = "\n".join(f"{i}: " + ", ".join(e) for _s, i, e in ranked[:3])
                r = brain.generate("You classify software by its kind. Choose the best archetype id among the candidates, using ONLY the evidence given. Reply JSON {\"id\": \"...\"}.",
                                   f"Application window: {sm.window_title}\nCandidates: {json.dumps(names)}\nEvidence:\n{ev}",
                                   schema={"type": "object", "properties": {"id": {"type": "string", "enum": list(names)}}, "required": ["id"]}, max_tokens=40, temperature=0.0, timeout=45)
                if r.ok and isinstance(r.json, dict) and r.json.get("id") in names:
                    chosen, by = r.json["id"], "rules+model"
        except Exception:
            pass
    bp = blueprint(chosen)
    ev = next((e for _s, i, e in ranked if i == chosen), [])
    return {"id": chosen, "name": bp.get("name", "unknown kind of software"), "confidence": conf, "evidence": ev[:14], "ranked": [(i, s) for s, i, _e in ranked[:4]],
            "layout": facts, "blueprint": {k: bp.get(k) for k in ("entities", "pipeline", "properties_live", "structure_lives", "lifecycle")} if bp else {}, "by": by}


def teaching_line(arch: Dict[str, Any]) -> str:
    """One compact line for the teacher's prompt: what kind of software this is and where things live."""
    if not arch or arch.get("id") in (None, "unknown"):
        return ""
    bp = arch.get("blueprint") or {}
    return (f"KIND OF SOFTWARE: {arch['name']}. Properties of a selection live in {bp.get('properties_live', 'the inspector')}; structure lives in {bp.get('structure_lives', 'a tree')}. "
            f"Usual workflow: {' -> '.join(bp.get('pipeline', []))}.")
