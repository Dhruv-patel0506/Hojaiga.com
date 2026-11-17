"""
professor.knowledge.app_knowledge -- measured facts about an application's controls, joined to what the Professor sees on screen.

Sources (all produced earlier by Atlas / the scanners; nothing is re-scanned here, and the application is never touched):
  uimap          data/atlas/uimap/<app>.json       tab / group / control / drop-down item / dialog tree, shortcuts, what each control leads to
  knowledge base data/knowledge_bases/<app>_knowledge.json   probed interactions (label -> effect type), capabilities
Matching a visible control to a known one uses its folded label (and the region caption as a tiebreak); a control with no label cannot be matched,
and is then explained by its position and neighbours instead -- never by a guess.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .. import config as CFG
from ..schema import ScreenModel, UIElement, fold

for _p in (r"D:\new_automation", r"D:\new_automation\All codes"):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@dataclass
class ControlKnowledge:
    name: str
    path_text: str = ""                    # "Open the Insert tab of the ribbon > in the Illustrations group > click Pictures"
    shortcut: str = ""
    outcome: str = ""                      # "A dialog 'Insert Picture' opens with: ..."
    dialog: str = ""
    items: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    kind: str = ""
    trust: str = "measured"
    source: str = ""                       # uimap | knowledge_base
    surface: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def _tokens(s: str) -> set:
    return {t for t in fold(s).split() if len(t) > 1}


def _available_keys() -> Dict[str, List[str]]:
    keys: Dict[str, List[str]] = {"uimap": [], "kb": []}
    for p in glob.glob(os.path.join(CFG.ATLAS_DIR, "uimap", "*.json")):
        keys["uimap"].append(os.path.splitext(os.path.basename(p))[0])
    for p in glob.glob(os.path.join(CFG.KNOWLEDGE_BASES_DIR, "*_knowledge.json")):
        keys["kb"].append(os.path.basename(p)[: -len("_knowledge.json")])
    return keys


def resolve_key(candidates: List[str], pool: List[str]) -> str:
    """Pick the stored knowledge name that best matches the window's identity strings (process, title, atlas app key)."""
    want = [fold(c).replace(" ", "") for c in candidates if c]
    best, best_s = "", 0
    for k in pool:
        kk = fold(k).replace(" ", "")
        if not kk or kk in ("app",):
            continue
        for w in want:
            if not w:
                continue
            s = 0
            if kk == w:
                s = 100
            elif kk in w or w in kk:
                s = 60 + min(len(kk), len(w))
            if s > best_s:
                best, best_s = k, s
    return best


class AppKnowledge:
    def __init__(self, ui_key: str = "", kb_key: str = ""):
        self.ui_key, self.kb_key = ui_key, kb_key
        self.index: Dict[str, List[Dict[str, Any]]] = {}
        self.kb: Dict[str, Any] = {}
        self.kb_index: Dict[str, Dict[str, Any]] = {}
        self.entries: List[Dict[str, Any]] = []
        self._load()

    @property
    def known(self) -> bool:
        return bool(self.entries or self.kb_index)

    def _load(self) -> None:
        if self.ui_key:
            try:
                from core_organs.atlas import teach
                m = teach.load_map(self.ui_key)
                self.entries = teach.flatten(m) if m else []
                for e in self.entries:
                    self.index.setdefault(fold(e["name"]), []).append(e)
            except Exception:
                self.entries = []
        if self.kb_key:
            try:
                with open(os.path.join(CFG.KNOWLEDGE_BASES_DIR, f"{self.kb_key}_knowledge.json"), "r", encoding="utf-8") as fh:
                    self.kb = json.load(fh)
                for it in self.kb.get("interactions", []):
                    self.kb_index.setdefault(fold(it.get("label", "")), it)
            except Exception:
                self.kb = {}

    # ------------------------------------------------------------------------------------------------- lookup
    def lookup(self, label: str, region_label: str = "") -> Optional[ControlKnowledge]:
        q = fold(label)
        if not q:
            return None
        cands = self.index.get(q)
        if cands:
            best = cands[0]
            if len(cands) > 1 and region_label:
                rt = _tokens(region_label)
                best = max(cands, key=lambda e: (len(rt & (_tokens(e.get("group", "")) | _tokens(e.get("surface", "")))), -e["depth"]))
            else:
                best = min(cands, key=lambda e: e["depth"])
            try:
                from core_organs.atlas import teach
                r = teach.route_of(best, 1.0)
            except Exception:
                r = {"text": "", "shortcut": best.get("accel", ""), "outcome": "", "preconditions": [], "dialog": ""}
            items = []
            lt = best.get("lt") or {}
            for it in (lt.get("items") or [])[:12]:
                items.append(it["name"] if isinstance(it, dict) else str(it))
            return ControlKnowledge(best["name"], re.sub(r"\*\*", "", r.get("text", "")), r.get("shortcut", ""), re.sub(r"\*\*", "", r.get("outcome", "")),
                                    r.get("dialog", "") or "", items, r.get("preconditions", []), best.get("kind", ""), "measured", "uimap", best.get("surface", ""))
        it = self.kb_index.get(q)
        if it:
            et = (it.get("effect_type") or "").replace("_", " ")
            return ControlKnowledge(it.get("label", label), "", "", f"Probing showed it {et}" if et else "", "", [], [], "", "measured", "knowledge_base")
        return None

    def howto(self, question: str, limit: int = 3) -> Dict[str, Any]:
        if not self.ui_key:
            return {"ok": False, "why": "no UI map for this application"}
        try:
            from core_organs.atlas import teach
            return teach.routes_for(self.ui_key, question, limit=limit, use_model=False)
        except Exception as exc:
            return {"ok": False, "why": f"{type(exc).__name__}: {exc}"}

    def overview(self) -> Dict[str, Any]:
        if not self.ui_key:
            return {"ok": False}
        try:
            from core_organs.atlas import teach
            return teach.overview(self.ui_key)
        except Exception:
            return {"ok": False}


_CACHE: Dict[Tuple[str, str], AppKnowledge] = {}


def for_identity(*names: str) -> AppKnowledge:
    keys = _available_keys()
    ui = resolve_key(list(names), keys["uimap"])
    kb = resolve_key(list(names), keys["kb"])
    ck = (ui, kb)
    if ck not in _CACHE:
        _CACHE[ck] = AppKnowledge(ui, kb)
    return _CACHE[ck]


def for_model(sm: ScreenModel) -> AppKnowledge:
    proc = sm.process.replace(".exe", "").replace(".EXE", "")
    return for_identity(sm.app_key, proc, sm.window_title.split(" - ")[-1] if sm.window_title else "")


def enrich(sm: ScreenModel) -> Dict[str, Any]:
    """Attach shortcut / leads_to / hint / knowledge{} to every labelled control that the stored knowledge recognises. Returns a small report."""
    ak = for_model(sm)
    rep = {"ui_map": ak.ui_key, "knowledge_base": ak.kb_key, "matched": 0, "labelled": 0}
    if not ak.known:
        sm.tiers_skipped.append("knowledge:none-stored-for-app")
        return rep
    for e in sm.elements:
        if not e.label:
            continue
        rep["labelled"] += 1
        ck = ak.lookup(e.label, sm.region_label(e))
        if ck is None:
            continue
        rep["matched"] += 1
        if ck.shortcut and not e.shortcut:
            e.shortcut = ck.shortcut
        if ck.outcome and not e.leads_to:
            e.leads_to = ck.outcome[:160]
        e.knowledge = ck.to_dict()
        if "knowledge" not in e.sources:
            e.sources.append("knowledge")
    sm.tiers_used.append(f"knowledge:{rep['matched']}/{rep['labelled']}")
    return rep
