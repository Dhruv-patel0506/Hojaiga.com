"""professor.knowledge.guide_explain -- WHAT A COMMAND DOES, IN THE VENDOR'S OWN WORDS.

A catalogued command with no tooltip and no description is still often EXPLAINED by the application's guide ('Select **Different First Page** to remove the header from the first
page'). For every command the catalog cannot explain, the guide corpus of THAT application is scanned for a sentence that names the command (its exact label, as a whole phrase);
the first such sentence becomes the command's description, cited ('guide: <section>'). Nothing is generated: a command no sentence names stays unexplained.

    enrich(catalog, index, guide_key) -> {"explained_before", "explained_now", "added", "total"}"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from ..schema import fold

_SENT = re.compile(r"(?<=[.!?])\s+|\n+")
_GENERIC = {"ok", "cancel", "yes", "no", "close", "more", "new", "open", "file", "edit", "view", "help", "home", "insert", "format", "tools", "options", "all", "none", "left",
            "right", "top", "bottom", "center", "back", "next", "up", "down", "on", "off", "other", "custom", "default", "apply", "reset", "show", "hide", "add", "remove", "delete"}


def _explained(v: Any, tooltips: Dict[str, str]) -> bool:
    return bool(v.desc or v.leads_to or tooltips.get((v.label or "").lower()))


def sentences(index: Any, guide_key: str) -> List[Tuple[str, str, str]]:
    """(folded sentence, sentence, cite) for every sentence of the application's guide corpus."""
    try:
        rows = index._load(guide_key)["rows"]
    except Exception:
        return []
    out: List[Tuple[str, str, str]] = []
    for r in rows:
        cite, text = str(r[1] or ""), str(r[2] or "")
        for s in _SENT.split(text):
            raw = re.sub(r"\s+", " ", s).strip()
            clean = raw.replace("**", "")
            if 20 <= len(clean) <= 300:
                out.append((_norm(raw), clean, cite))                       # the normalised RAW sentence keeps the manual's **bold** marks of interface terms
    return out


def _norm(t: str) -> str:
    """Lower case, punctuation to spaces - but the '**' of a bold interface term kept."""
    t = (t or "").lower().replace("“", " ").replace("”", " ").replace('"', " ")
    t = re.sub(r"[^\w*&+]+", " ", t)
    t = re.sub(r"\*\*\s*", "**", re.sub(r"\s*\*\*", "**", t))
    return re.sub(r"\s+", " ", t).strip()


_ACT = r"(?:select|click|choose|tap|use|press|open|turn on|turn off|check|clear|pick|go to)"


def names(folded_raw: str, lab: str) -> bool:
    """Does this sentence NAME the command (not merely use the word)? The manual bolds it ('**Different First Page**'), or a label of 2+ words follows an action verb."""
    if f"**{lab}**" in folded_raw:
        return True
    if len(lab.split()) >= 2:
        plain = folded_raw.replace("**", " ")
        return bool(re.search(r"\b" + _ACT + r"\s+(?:the\s+)?" + re.escape(lab) + r"\b", plain))
    return False


def enrich(catalog: Any, index: Any, guide_key: str, max_len: int = 240) -> Dict[str, Any]:
    tips = {k.lower(): v for k, v in (getattr(catalog, "tooltips", None) or {}).items()}
    before = sum(1 for v in catalog.verbs if _explained(v, tips))
    sents = sentences(index, guide_key)
    added = 0
    if sents:
        cache: Dict[str, str] = {}
        for v in catalog.verbs:
            if _explained(v, tips):
                continue
            lab = _norm(re.sub(r"\.\.\.$|…$", "", v.label or "")).replace("*", "").strip()
            if len(lab) < 4 or lab in _GENERIC or not re.search(r"[a-z]", lab):
                continue
            if lab not in cache:
                hit = next(((s, c) for fs, s, c in sents if lab in fs and names(fs, lab)), None)
                cache[lab] = (f"{hit[0][:max_len]} (guide: {hit[1][:80]})" if hit else "")
            if cache[lab]:
                v.desc = cache[lab]
                added += 1
    total = len(catalog.verbs)
    return {"explained_before": before, "explained_now": before + added, "added": added, "total": total,
            "percent_before": round(100.0 * before / total, 1) if total else None, "percent_now": round(100.0 * (before + added) / total, 1) if total else None}
