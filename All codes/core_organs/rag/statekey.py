"""
rag.statekey -- what makes two screenshots of an application the SAME STATE (DESIGN.md section 5.2).

A state is recognised by its STRUCTURE (menu-bar items, tabs, toolbar/ribbon buttons, group headers, dialog title, pane names), never by its content (document text, list rows,
title-bar text). Names are normalised (digits -> '#') and anything that looks like content (long, a path, a URL, an e-mail) is dropped, so a changed document title or a different
file list does not mint a new state. Pure functions; no I/O.

snapshot accepted:
    list of node-likes (fast_uia.Node / dict) with ctype, name, aid, depth, pid ...
    or a dict {"nodes": [...], "window_class": str, "toolkit": str, "role": "main|dialog|flyout|menu|backstage", "modal_stack": [window_kind,...],
               "ocr": [str], "icons": [label], "grid": "hex"}   (the last three feed the BLIND-TREE fallback)
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import config as C
from .lexicon import canon

STRUCTURAL = {"menuitem", "tabitem", "button", "splitbutton", "togglebutton", "group", "toolbar", "menubar", "menu", "tab", "checkbox", "radiobutton", "combobox", "hyperlink",
              "pane", "titlebar", "window", "dialog", "ribbon", "tree", "header", "headeritem", "statusbar", "tooltip"}
_VOLATILE = re.compile(r"(?:[a-z]:\\|\\\\|/[\w.-]+/|://|@[\w-]+\.|\.\w{2,4}\b)", re.I)
_DIGITS = re.compile(r"\d+")
_HEXISH = re.compile(r"\b[0-9a-f]{6,}\b")
_SPACE = re.compile(r"\s+")


@dataclass
class Features:
    window_kind: str
    modal_stack: List[str]
    landmarks: Dict[str, float]                     # landmark -> weight (1.0 structural, BLIND_LANDMARK_WEIGHT blind)
    blind: bool = False
    sig: str = ""
    title: str = ""
    n_nodes: int = 0
    titles: List[str] = field(default_factory=list)


def _get(n: Any, k: str, default: Any = "") -> Any:
    if isinstance(n, dict):
        return n.get(k, default)
    return getattr(n, k, default)


def norm_name(name: str) -> str:
    s = canon(name or "")
    s = _HEXISH.sub("#", s)
    s = _DIGITS.sub("#", s)
    return _SPACE.sub(" ", s).strip()


def is_structural_name(name: str) -> bool:
    if not name or len(name) > C.MAX_LANDMARK_NAME:
        return False
    return not _VOLATILE.search(name)


def norm_class(cls: str) -> str:
    s = (cls or "").lower()
    s = _HEXISH.sub("", s)
    s = _DIGITS.sub("#", s)
    return re.sub(r"[._]{2,}", ".", s).strip("._")


def window_kind(toolkit: str, cls: str, role: str) -> str:
    return f"{(toolkit or '').lower()}:{norm_class(cls)}:{(role or 'main').lower()}"


def _unpack(snapshot: Any) -> Dict[str, Any]:
    if isinstance(snapshot, dict):
        d = dict(snapshot)
        d["nodes"] = list(d.get("nodes") or [])
        return d
    return {"nodes": list(snapshot or [])}


def features(snapshot: Any, app_pids: Optional[Iterable[int]] = None) -> Features:
    d = _unpack(snapshot)
    pids = set(app_pids or ())
    lm: Dict[str, float] = {}
    titles: List[str] = []
    n = 0
    for node in d["nodes"]:
        pid = int(_get(node, "pid", 0) or 0)
        if pids and pid and pid not in pids:                   # a helper process's picker is not this application's interface
            continue
        n += 1
        ct = str(_get(node, "ctype", "") or "").lower().replace(" ", "")
        if ct not in STRUCTURAL:
            continue
        if _get(node, "offscreen", False):
            continue
        name = str(_get(node, "name", "") or "")
        aid = str(_get(node, "aid", "") or "")
        if ct in ("window", "dialog", "titlebar") and name:
            titles.append(norm_name(name))
        # title-bar text, and the title of a MAIN window, are content (the document's name): never a landmark. A dialog / flyout / menu title is structure.
        if ct == "titlebar" or (ct == "window" and str(d.get("role", "main")).lower() == "main"):
            continue
        if name and is_structural_name(name):
            nm = norm_name(name)
            if nm:
                lm[f"{ct}|{nm}"] = 1.0
        elif not name and aid and len(aid) <= C.MAX_LANDMARK_NAME and not _VOLATILE.search(aid):
            lm[f"{ct}|aid:{_DIGITS.sub('#', aid.lower())}"] = 1.0
    blind = len(lm) < C.BLIND_TREE_MIN_LANDMARKS
    if blind:
        for t in d.get("ocr") or []:
            nm = norm_name(str(t))
            if nm and is_structural_name(str(t)):
                lm[f"~ocr|{nm}"] = C.BLIND_LANDMARK_WEIGHT
        for t in d.get("icons") or []:
            nm = norm_name(str(t))
            if nm:
                lm[f"~icon|{nm}"] = C.BLIND_LANDMARK_WEIGHT
        if d.get("grid"):
            lm[f"~grid|{d['grid']}"] = C.BLIND_LANDMARK_WEIGHT
    wk = window_kind(d.get("toolkit", ""), d.get("window_class", ""), d.get("role", "main"))
    stack = [str(x) for x in (d.get("modal_stack") or [])]
    sig = hashlib.sha1(("|".join([wk, ",".join(stack)] + sorted(lm))).encode("utf-8")).hexdigest()
    return Features(wk, stack, lm, blind, sig, titles[0] if titles else "", n, titles)


def similarity(a: Dict[str, float], b: Dict[str, float], idf: Dict[str, float], default_idf: float = 1.0) -> float:
    """IDF-weighted Jaccard of two landmark sets. Landmarks every state shares ('File') weigh almost nothing."""
    if not a and not b:
        return 1.0
    inter = union = 0.0
    for k in set(a) | set(b):
        wa, wb = a.get(k), b.get(k)
        i = idf.get(k, default_idf)
        union += i * max(wa or 0.0, wb or 0.0)
        if wa is not None and wb is not None:
            inter += i * min(wa, wb)
    return inter / union if union else 0.0


def describe(f: Features, limit: int = 14) -> str:
    return describe_landmarks(f.window_kind, f.landmarks, limit)


def describe_landmarks(window_kind: str, landmarks, limit: int = 14) -> str:
    """The natural-language handle of a state: its window kind and the names of its structural landmarks (sorted, so the same state always reads the same). No titles: a main window's
    title is the document's name."""
    names = sorted(k.split("|", 1)[-1] for k in landmarks)[:limit]
    return " ".join([window_kind] + names)
