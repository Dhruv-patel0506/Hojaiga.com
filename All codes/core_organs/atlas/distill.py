"""
atlas.distill -- public documents -> claims, where EVERY claim must quote its source.

The local language model reads a document (README, article, manual page) and proposes facts as {category, claim, quote}. A fact is KEPT only
if its quote is literally present in the document (whitespace/case/punctuation-insensitive). The model therefore cannot add anything the
document does not say; what it can do is choose, shorten and categorise. A deterministic extractor (patterns, no model) runs alongside,
so the layer works with the model offline, and the result reports how many proposals were dropped (a hallucination meter).

Claims enter at 'published' trust with the URL and the exact quote as evidence.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from . import common as C
from . import llm

CATEGORIES = {
    "architecture": "arch.design", "language": "web.language", "scripting": "ext.scripting.published", "extension": "ext.published", "data_model": "model.published",
    "file_format": "io.published", "shortcut": "ui.shortcut.published", "mode": "model.modes", "feature": "web.feature", "limitation": "web.limitation",
    "cli": "ext.cli.published", "network": "net.published", "platform": "web.platform", "workflow": "model.workflow",
}

SYSTEM = ("You extract facts about a software application from ONE document. Reply with JSON only: "
          '{"facts":[{"category":"<one of: architecture, language, scripting, extension, data_model, file_format, shortcut, mode, feature, limitation, cli, network, platform, workflow>",'
          '"claim":"<one short factual sentence>","quote":"<an EXACT substring copied from the document, at most 200 characters>"}]}. '
          "Rules: at most 14 facts; only things the document states; prefer facts about how the application is built, how it is extended or scripted, what data it "
          "works on, its modes and workflows; never invent; the quote must be copied character for character.")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def quote_in(source_norm: str, quote: str) -> bool:
    q = _norm(quote)
    return len(q) >= 12 and q in source_norm


_STOPW = {"the", "and", "for", "with", "that", "this", "from", "have", "has", "are", "was", "can", "its", "their", "into", "which", "also", "such", "than", "then", "more"}


def supported(claim: str, quote: str) -> bool:
    """The quote must carry the claim: most of the claim's content words (4+ letters) appear in the quote, and the quote is prose, not a link list."""
    q = quote.strip()
    if re.match(r"^\s*[-*]\s*\[[^\]]*\]\([^)]*\)\s*$", q) or q.count("](") >= 1 and len(re.sub(r"\[[^\]]*\]\([^)]*\)", "", q).strip()) < 25:
        return False
    if len(re.findall(r"[A-Za-z]{3,}", q)) < 5:
        return False
    # the SUBJECT of a claim (capitalised: "Acme Studio", "Python") is usually elided in the quoted sentence; what must be supported is what is SAID about it
    plain = re.sub(r"\b[A-Z][A-Za-z0-9+#.]*\b", " ", claim)
    stem = lambda w: w[:5]
    cw = {stem(w) for w in re.findall(r"[a-z]{4,}", plain) if w not in _STOPW}
    if not cw:
        return False
    qw = {stem(w) for w in re.findall(r"[a-z]{4,}", q.lower())}
    return len(cw & qw) / len(cw) >= 0.5


PATTERNS: List[Tuple[str, str, "re.Pattern"]] = [
    ("language", "web.language", re.compile(r"[^.\n]*\b(?:written in|implemented in|built (?:with|using|on)|based on|powered by|uses the)\b[^.\n]{3,140}\.?", re.I)),
    ("scripting", "ext.scripting.published", re.compile(r"[^.\n]*\b(?:python api|scripting|scriptable|macro|add-?ons?|plug-?ins?|extensions?|api)\b[^.\n]{10,160}\.?", re.I)),
    ("architecture", "arch.design", re.compile(r"[^.\n]*\b(?:architecture|modular|multi-?process|client[- /]server|event loop|scene graph|node[- ]based|non-destructive|real-?time|multi-?thread\w*|gpu|renderer|engine)\b[^.\n]{10,160}\.?", re.I)),
    ("file_format", "io.published", re.compile(r"[^.\n]*\b(?:file format|supports? (?:the )?(?:import|export)|imports?|exports?|saves? (?:as|to)|\.\w{2,5} files?)\b[^.\n]{8,160}\.?", re.I)),
    ("mode", "model.modes", re.compile(r"[^.\n]*\b(?:modes?|workspaces?|editors?|views?|panels?|timeline|layers?|tracks?|decks?|mixer|outliner|viewport|properties)\b[^.\n]{12,160}\.?", re.I)),
    ("platform", "web.platform", re.compile(r"[^.\n]*\b(?:windows|macos|linux|android|ios|cross-?platform)\b[^.\n]{5,120}\.?", re.I)),
]


def deterministic(app_key: str, text: str, url: str, *, per_category: int = 3) -> List[C.Claim]:
    out: List[C.Claim] = []
    counts: Dict[str, int] = {}
    for cat, kind, rx in PATTERNS:
        for m in rx.finditer(text[:60000]):
            sent = re.sub(r"\s+", " ", m.group(0)).strip(" -*#>")
            if len(sent) < 25 or len(sent) > 260 or sent.count("|") > 2:
                continue
            if counts.get(cat, 0) >= per_category:
                break
            counts[cat] = counts.get(cat, 0) + 1
            out.append(C.Claim(app_key, kind, sent, "published", 0.55, [C.Evidence("url", url, sent[:200])], {"category": cat, "method": "pattern"}, "atlas.distill"))
    return out


def with_model(app_key: str, text: str, url: str, *, max_chars: int = 6500, timeout: float = 110.0) -> Tuple[List[C.Claim], Dict[str, Any]]:
    meta: Dict[str, Any] = {"model": None, "proposed": 0, "kept": 0, "dropped": 0, "seconds": 0.0, "error": ""}
    if not llm.available():
        meta["error"] = "local model not reachable"
        return [], meta
    body = text[:max_chars]
    r = llm.chat(SYSTEM, "DOCUMENT:\n" + body, timeout=timeout, max_tokens=1100)
    meta.update(model=r.get("model"), seconds=r.get("seconds", 0.0), error=r.get("error", ""))
    facts = ((r.get("json") or {}).get("facts") if isinstance(r.get("json"), dict) else None) or []
    src = _norm(body)
    out: List[C.Claim] = []
    for f in facts[:20]:
        if not isinstance(f, dict):
            continue
        meta["proposed"] += 1
        claim, quote, cat = str(f.get("claim", "")).strip(), str(f.get("quote", "")).strip(), str(f.get("category", "")).strip().lower()
        if not claim or not quote_in(src, quote) or not supported(claim, quote):
            meta["dropped"] += 1
            continue
        kind = CATEGORIES.get(cat, "web.feature")
        out.append(C.Claim(app_key, kind, claim[:300], "published", 0.7, [C.Evidence("url", url, quote[:200])], {"category": cat, "method": "model"}, "atlas.distill"))
        meta["kept"] += 1
    return out, meta


def distill(app_key: str, text: str, url: str, *, use_model: bool = True) -> Tuple[List[C.Claim], Dict[str, Any]]:
    det = deterministic(app_key, text, url)
    mod: List[C.Claim] = []
    meta: Dict[str, Any] = {"deterministic": len(det)}
    if use_model:
        mod, mm = with_model(app_key, text, url)
        meta["model"] = mm
    seen, out = set(), []
    for c in mod + det:
        k = C.fold(c.statement)[:80]
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out, meta
