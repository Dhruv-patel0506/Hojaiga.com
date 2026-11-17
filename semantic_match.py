"""
semantic_match -- THE MISSING LINK between offline JSON and live UIA.

The text model writes a trajectory step whose ui_target reads e.g.
    {"element_name": "Get", "element_type": "Button", "hierarchical_path": "Store > App > Get"}
while the live FlaUI/uiautomation tree names that same thing
    Node(name="Get button", aid="DownloadApp_Btn", role="button", rect=(...)).
Manual wording and code identifiers rarely agree. This module is the translator:
it scores every live node against a JSON target and returns the best candidate
(plus its bounding box) so the virtual mouse knows where to click -- or reports
"not confidently matched" so the caller can hand off to the vision tier.

Three tiers, best-confidence-wins, each honest about what it did:
  1. lexical   : normalised difflib ratio + token Jaccard + substring/aid match.
  2. type      : element_type vs live control-type agreement (a soft boost/penalty).
  3. embedding : local Ollama nomic-embed-text cosine, used only when lexical is
                 ambiguous (0.35 <= score < 0.60). No cloud, bounded, degrades to
                 "None" if the embedding server is down -- never fakes a match.

No window is touched here; it is pure scoring over node objects already scanned.
A "node" is any object/dict exposing name, aid, cls, role, rect, enabled,
offscreen, help (fast_uia.Node satisfies this).
"""

from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests

OLLAMA_URL = os.environ.get("HOJAIGA_PROF_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
EMBED_MODEL = os.environ.get("HOJAIGA_ATLAS_EMBED_MODEL", "nomic-embed-text")

# element_type (from JSON) -> fast_uia role (control type, lowercased, no 'Control')
TYPE_TO_ROLES: Dict[str, set] = {
    "button": {"button"},
    "textbox": {"edit", "document"},
    "edit": {"edit"},
    "menuitem": {"menuitem"},
    "menu": {"menu", "menubar"},
    "tab": {"tab", "tabitem"},
    "listitem": {"listitem"},
    "list": {"list"},
    "slider": {"slider"},
    "checkbox": {"checkbox"},
    "combobox": {"combobox", "dropdown"},
    "canvas": {"pane", "custom", "image"},
}

STOPWORDS = {"the", "a", "an", "to", "of", "in", "on", "and", "or", "button",
             "click", "select", "choose", "menu", "item", "for", "your", "this"}

LEX_STRONG = 0.72      # at/above -> accept as a confident lexical match
LEX_AMBIG_LO = 0.35    # ambiguous band -> try embeddings
LEX_AMBIG_HI = 0.60
EMB_ACCEPT = 0.80      # embedding cosine needed to rescue an ambiguous case


@dataclass
class Match:
    node: Any
    score: float
    how: str                    # "lexical" | "embedding" | "none"
    coords: Tuple[int, int]     # rect centre in screen pixels
    rect: Tuple[int, int, int, int]


def _get(node: Any, field: str, default: Any = "") -> Any:
    if isinstance(node, dict):
        return node.get(field, default)
    return getattr(node, field, default)


def norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(s or "").lower()).strip()


def toks(s: str) -> set:
    return {t for t in norm(s).split() if t and t not in STOPWORDS}


def _aid_tokens(aid: str) -> set:
    # split camelCase + underscores of an AutomationId like DownloadApp_Btn
    raw = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(aid or ""))
    raw = re.sub(r"[^A-Za-z0-9]+", " ", raw)
    return {t.lower() for t in raw.split() if len(t) > 2 and t.lower() not in STOPWORDS}


def _lexical(target_text: str, node: Any) -> float:
    tn = norm(target_text)
    if not tn:
        return 0.0
    best = 0.0
    for field in ("name", "help", "aid"):
        fv = norm(_get(node, field, ""))
        if not fv:
            continue
        # full-string similarity
        best = max(best, difflib.SequenceMatcher(None, tn, fv).ratio())
        # containment (target inside label or label inside target)
        if tn in fv or fv in tn:
            best = max(best, 0.9)
        # token overlap
        tt, ft = toks(target_text), toks(fv)
        if tt and ft:
            jac = len(tt & ft) / max(1, len(tt | ft))
            best = max(best, 0.5 + 0.5 * jac if (tt & ft) else jac)
    # literal AutomationId token hit (DownloadApp_Btn ~ "Get" won't hit, but "save" ~ "Save_Btn" will)
    if toks(target_text) & _aid_tokens(_get(node, "aid", "")):
        best = max(best, 0.82)
    return round(best, 3)


def _type_consistency(element_type: str, node: Any) -> float:
    """1.0 agree, 0.5 neutral (unknown), -0.25 disagree (used as a score modifier)."""
    et = norm(element_type)
    if not et:
        return 0.5
    role = str(_get(node, "role", "") or "").lower()
    want = TYPE_TO_ROLES.get(et, set())
    if not role:
        return 0.5
    if role in want:
        return 1.0
    return -0.25


def _embed(texts: List[str]) -> Optional[List[List[float]]]:
    try:
        r = requests.post(OLLAMA_URL + "/api/embed",
                          json={"model": EMBED_MODEL, "input": texts}, timeout=15)
        r.raise_for_status()
        return r.json().get("embeddings")
    except Exception:
        return None


def _cosine(a: List[float], b: List[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _center(rect: Tuple[int, int, int, int]) -> Tuple[int, int]:
    l, t, r, b = rect
    return (l + r) // 2, (t + b) // 2


def resolve(step_target: Dict[str, Any], nodes: List[Any],
            *, use_embeddings: bool = True, limit: int = 400) -> Match:
    """Best node for one JSON ui_target. Returns Match(how='none') when nothing is confident.

    step_target = {"element_name","automation_id","element_type","hierarchical_path",
                   "visual_description"(optional)}.
    """
    name = step_target.get("element_name") or ""
    aid = step_target.get("automation_id") or ""
    etype = step_target.get("element_type") or ""
    # candidate target texts, most specific first
    target_text = " ".join(str(x) for x in (name, aid) if x).strip() or str(
        step_target.get("visual_description") or "")
    if not target_text:
        return Match(None, 0.0, "none", (0, 0), (0, 0, 0, 0))

    scored: List[Tuple[float, Any]] = []
    usable = [n for n in nodes
              if _get(n, "enabled", True) and not _get(n, "offscreen", False)] or nodes
    for n in usable[:limit]:
        lex = _lexical(target_text, n)
        # direct automation_id equality is a hard, trustworthy signal
        n_aid = norm(_get(n, "aid", ""))
        if aid and n_aid and n_aid == norm(aid):
            lex = max(lex, 0.97)
        mod = _type_consistency(etype, n)
        score = lex if mod < 0 else (lex + 0.10 * mod)
        scored.append((round(min(1.0, max(0.0, score)), 3), n))

    scored.sort(key=lambda x: -x[0])
    if not scored:
        return Match(None, 0.0, "none", (0, 0), (0, 0, 0, 0))

    best_score, best_node = scored[0]

    if best_score >= LEX_STRONG:
        return Match(best_node, best_score, "lexical", _center(_get(best_node, "rect", (0, 0, 0, 0))),
                     _get(best_node, "rect", (0, 0, 0, 0)))

    # ambiguous band -> local embedding rescue (honest if unavailable)
    if use_embeddings and LEX_AMBIG_LO <= best_score < LEX_AMBIG_HI:
        cands = scored[:8]
        labels = [norm(_get(n, "name", "")) or norm(_get(n, "aid", "")) for _, n in cands]
        labels = [lbl for lbl in labels if lbl]
        if labels:
            embs = _embed([target_text] + labels)
            if embs and len(embs) == len(labels) + 1:
                qv = embs[0]
                sims = [(_cosine(qv, embs[i + 1]), cands[i][1]) for i in range(len(labels))]
                sims.sort(key=lambda x: -x[0])
                if sims and sims[0][0] >= EMB_ACCEPT:
                    s, node = sims[0]
                    return Match(node, round(s, 3), "embedding", _center(_get(node, "rect", (0, 0, 0, 0))),
                                 _get(node, "rect", (0, 0, 0, 0)))

    # below the strong line and not rescued: report best but flag as not confident
    return Match(best_node, best_score, "none" if best_score < LEX_AMBIG_LO else "weak",
                 _center(_get(best_node, "rect", (0, 0, 0, 0))), _get(best_node, "rect", (0, 0, 0, 0)))
