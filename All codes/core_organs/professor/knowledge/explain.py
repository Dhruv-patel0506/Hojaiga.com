"""
professor.knowledge.explain -- from a visible control to everything known about it, with the source of each fact.

    fact_sheet(element, model, ...)  ->  {where, shortcut, opens, how_to_reach, items, code:[{file,line,symbol,division,effects,reaches}], trust}
    spoken(sheet)                    ->  one or two plain sentences built ONLY from the sheet (no model, so it can never invent a feature)

The teaching model receives the sheet as facts to rephrase; it is not asked what the control does from its own memory.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .. import config as CFG
from ..schema import ScreenModel, UIElement
from . import app_knowledge
from .repo_graph import RepoGraph

_RG: Optional[RepoGraph] = None
_RG_FAILED = False


def fold_in(label: str, text: str) -> bool:
    """The manual passage really mentions the control (folded label inside folded text), so a loosely related chunk is never attached to it."""
    from ..schema import fold
    return bool(fold(label)) and fold(label) in fold(text)


def repo_graph() -> Optional[RepoGraph]:
    global _RG, _RG_FAILED
    if _RG is None and not _RG_FAILED:
        try:
            if os.path.isfile(CFG.REPO_DB):
                _RG = RepoGraph()
            else:
                _RG_FAILED = True
        except Exception:
            _RG_FAILED = True
    return _RG


def project_for(sm: ScreenModel, rg: Optional[RepoGraph]) -> str:
    forced = os.environ.get("HOJAIGA_PROF_PROJECT", "")
    if forced:
        return forced
    if rg is None:
        return ""
    projects = rg.stats().get("projects", [])
    proc = sm.process.replace(".exe", "")
    return app_knowledge.resolve_key([sm.app_key, proc, sm.window_title.split(" - ")[-1] if sm.window_title else ""], projects)


def _where(e: UIElement, sm: ScreenModel) -> str:
    r = sm.region(e.region_id)
    if r is None:
        return "somewhere in the window"
    lab = r.label if r.label and r.label != r.kind else ""
    return f"in the {lab + ' ' if lab else ''}{r.kind.replace('_', ' ')}".replace("  ", " ")


def fact_sheet(e: UIElement, sm: ScreenModel, rg: Optional[RepoGraph] = None, project: str = "", with_code: bool = True) -> Dict[str, Any]:
    ak = app_knowledge.for_model(sm)
    ck = ak.lookup(e.label, sm.region_label(e)) if e.label else None
    sheet: Dict[str, Any] = {"id": e.id, "label": e.label, "role": e.role, "where": _where(e, sm), "enabled": e.enabled,
                             "shortcut": e.shortcut or (ck.shortcut if ck else ""), "opens": (ck.outcome if ck else "") or e.leads_to, "dropdown": e.has_dropdown,
                             "how_to_reach": ck.path_text if ck else "", "items": ck.items if ck else [], "preconditions": ck.preconditions if ck else [],
                             "hint": e.hint, "found_by": e.sources, "confidence": e.conf, "flags": e.flags, "code": [], "trust": {}}
    if ck:
        sheet["trust"]["ui_knowledge"] = f"{ck.trust} ({ck.source})"
    if e.label:
        try:
            from . import manual_rag
            ix = manual_rag.index()
            if ix is not None:
                ps = ix.search(f"{e.label} {e.role}", sm.app_key if sm.app_key in ix.apps() else "", 1)
                if ps and ps[0].score >= 0.5 and fold_in(e.label, ps[0].text):
                    sheet["manual"] = {"cite": ps[0].cite, "text": ps[0].text[:300]}
                    sheet["trust"]["manual"] = "published (user manual, quoted)"
        except Exception:
            pass
    if with_code and e.label:
        rg = rg if rg is not None else repo_graph()
        if rg is not None:
            proj = project or project_for(sm, rg)
            for hit in rg.link_label(e.label, proj, limit=3):
                item = {"file": hit["file"], "line": hit["line"], "division": hit["division"], "score": hit["score"], "symbol": None, "reaches": {}}
                if hit.get("symbol"):
                    s = hit["symbol"]
                    item["symbol"] = f"{s['name']} ({s['kind']})"
                    item["effects"] = s["effects"]
                    item["reaches"] = rg.reach_effects(s["name"], depth=3).get("effects", {})
                    item["callees"] = hit.get("callees", [])[:6]
                sheet["code"].append(item)
            if sheet["code"]:
                sheet["trust"]["code"] = "static (source repository)"
    return sheet


_EFFECT_WORDS = {"database": "reads or writes a database", "network": "talks to the network", "file": "reads or writes files", "process": "starts another program",
                 "ui": "shows a dialog or message"}


def spoken(sheet: Dict[str, Any]) -> str:
    """Plain sentences from the sheet alone."""
    name = sheet.get("label") or "this control"
    bits: List[str] = []
    role = sheet.get("role") or "control"
    role_words = {"menu_item": "menu item", "list_item": "list item", "tree_item": "tree item", "window_control": "window button"}.get(role, role.replace("_", " "))
    if sheet.get("label"):
        bits.append(f"That's the {name} {role_words}, {sheet.get('where', '')}.".replace(" ,", ","))
    else:
        bits.append(f"That's an icon button {sheet.get('where', '')}, and I can't read its name.".replace("  ", " "))
    if sheet.get("opens"):
        bits.append(sheet["opens"].rstrip(".") + ".")
    elif sheet.get("items"):
        bits.append("It opens a list with " + ", ".join(sheet["items"][:5]) + ".")
    if sheet.get("dropdown") and not sheet.get("items") and not sheet.get("opens"):
        bits.append("It has a drop-down arrow, so it opens more choices.")
    if sheet.get("shortcut"):
        bits.append(f"The keyboard shortcut is {sheet['shortcut']}.")
    if not sheet.get("enabled", True):
        bits.append("It's greyed out right now, so something has to be selected or created first.")
    for pre in sheet.get("preconditions", [])[:1]:
        bits.append(pre.rstrip(".").capitalize() + ".")
    if sheet.get("manual"):
        bits.append("The manual says: " + sheet["manual"]["text"].split(". ")[0].rstrip(".") + ".")
    code = sheet.get("code") or []
    if code and code[0].get("symbol"):
        c = code[0]
        eff = [_EFFECT_WORDS[k] for k in (c.get("reaches") or {}) if k in _EFFECT_WORDS]
        line = f"In the source this is handled by {c['symbol']} in {os.path.basename(c['file'])}, in the {c['division'].replace('_', ' ')} division"
        if eff:
            line += ", and pressing it " + " and ".join(eff[:2])
        bits.append(line + ".")
    return " ".join(b for b in bits if b)
