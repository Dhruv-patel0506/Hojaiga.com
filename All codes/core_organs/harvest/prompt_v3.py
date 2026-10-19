"""
harvest.prompt_v3 -- the compact, goal-trimmed prompt the Eye reads (and the Mind adds a hint to).

    Application: <app>
    Elements:
    #12 button "Save" (131,38)                  <- the ~40 elements that matter for THIS goal, centre point instead of a 4-number box
    Names: #12 Save | #31 Open                   <- UI Automation / OCR names of those elements
    Hint: <the step the RAG suggests>            <- optional; what the Mind remembers for this goal in this program
    Zoomed strips (2x, in order): 1              <- the crops of dense toolbars, as pictures, as before
    Goal: Click the Save button

Measured why: in v2 an element line cost ~27 tokens (the four box numbers are each several tokens) and the list held every element; 229 of 889 rows did not fit 2,048 tokens. A centre point halves the line, the Top-40
cut halves the list again. The same builder is used to write training rows and to build the live prompt, so the two can never drift apart.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

GENERIC = {"click", "the", "button", "tab", "menu", "icon", "field", "checkbox", "item", "option", "a", "an", "to", "on", "in", "of", "and", "text", "box", "press", "select"}
TOP_K = 40


def tokens(s: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 1]


def trim(elements: Sequence[Dict[str, Any]], goal: str, names: Optional[Dict[int, str]] = None, k: int = TOP_K, hint_words: Sequence[str] = (), reserve_headers: int = 6, reserve_neighbors: int = 6) -> List[Dict[str, Any]]:
    """The k elements that matter for the goal; ids unchanged; order = original order. In rank order:
      1. words the goal (and the RAG's retrieved step / menu names, `hint_words`) share with an element's label or accessibility name (a goal made ONLY of generic words - 'Click the Text button' - keeps them);
      2. the application's top-level headers: short-labelled menu / tab / button elements in the top band of the picture ('File', 'Edit', 'Insert', 'Home') - the parent of what a goal names;
      3. spatial neighbours of the best matches (a goal that names a value, a row or a category often names the thing beside the matched label);
      4. unlabeled icons, then buttons / fields."""
    names = names or {}
    base_want = [w for w in tokens(goal) if w not in GENERIC]
    want = base_want or [w for w in tokens(goal) if w not in ("click", "the", "to", "on", "in", "of", "and", "a", "an")]
    hint = {w for w in (h.lower() for h in hint_words) if len(w) > 1}

    def label_of(e: Dict[str, Any]) -> str:
        return ((e.get("label") or "") + " " + names.get(e["id"], "")).strip()

    def score(e: Dict[str, Any]) -> float:
        lab = label_of(e)
        toks = set(tokens(lab))
        s = len(set(want) & toks) * 2.0 + len(hint & toks) * 1.5
        if not lab:
            s += 0.6
        if e.get("type") in ("button", "field", "checkbox", "radio", "tab", "menu"):
            s += 0.2
        return s
    ranked = sorted(elements, key=lambda e: (-score(e), e["id"]))
    keep: List[int] = []
    for e in ranked[:max(k - reserve_headers - reserve_neighbors, 1)]:
        keep.append(e["id"])
    top_band = sorted({e["box"][1] for e in elements})[:1]
    y_limit = (top_band[0] if top_band else 0) + 130
    heads = [e for e in elements if e["id"] not in keep and e["box"][1] <= y_limit and len((e.get("label") or "").strip()) <= 12 and e.get("type") in ("menu", "tab", "button", "text", "menuitem")]
    for e in sorted(heads, key=lambda e: (e["box"][1], e["box"][0]))[:reserve_headers]:
        keep.append(e["id"])
    best = [e for e in ranked[:3] if score(e) >= 1.5]
    for b in best:
        bx, by = b["box"][0] + b["box"][2] / 2.0, b["box"][1] + b["box"][3] / 2.0
        near = sorted((e for e in elements if e["id"] not in keep), key=lambda e: (e["box"][0] + e["box"][2] / 2.0 - bx) ** 2 + (e["box"][1] + e["box"][3] / 2.0 - by) ** 2)
        for e in near[:max(reserve_neighbors // 3, 1)]:
            keep.append(e["id"])
    for e in ranked:                                                              # whatever room is left, by rank
        if len(keep) >= k:
            break
        if e["id"] not in keep:
            keep.append(e["id"])
    keepset = set(keep[:k])
    return [e for e in elements if e["id"] in keepset]


def element_line(e: Dict[str, Any]) -> str:
    x, y, w, h = e["box"]
    lab = (e.get("label") or "").strip()
    return f'#{e["id"]} {e.get("type", "")} ' + (f'"{lab}"' if lab else "(unnamed icon)") + f" ({int(x + w / 2)},{int(y + h / 2)})"


def build_text(app_key: str, elements: Sequence[Dict[str, Any]], names: Dict[int, str], hint: str, n_strips: int, goal: str) -> str:
    lines = [f"Application: {app_key}", "Elements:"] + [element_line(e) for e in elements]
    parts = [f"#{e['id']} {names[e['id']]}" for e in elements if names.get(e["id"])]
    if parts:
        lines.append("Names: " + " | ".join(parts[:TOP_K]))
    if hint:
        lines.append("Hint: " + hint[:110])
    if n_strips:
        lines.append(f"Zoomed strips (2x, in order): {n_strips}")
    lines.append(f"Goal: {goal}")
    return "\n".join(lines)
