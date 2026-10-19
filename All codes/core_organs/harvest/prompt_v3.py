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


def trim(elements: Sequence[Dict[str, Any]], goal: str, names: Optional[Dict[int, str]] = None, k: int = TOP_K) -> List[Dict[str, Any]]:
    """The k elements that matter for the goal (label / name words shared with it first, unlabeled icons next, then buttons / fields); ids unchanged; order = original order."""
    names = names or {}
    want = [w for w in tokens(goal) if w not in GENERIC]

    def score(e: Dict[str, Any]) -> float:
        lab = ((e.get("label") or "") + " " + names.get(e["id"], "")).strip()
        s = len(set(want) & set(tokens(lab))) * 2.0
        if not lab:
            s += 0.6
        if e.get("type") in ("button", "field", "checkbox", "radio", "tab", "menu"):
            s += 0.2
        return s
    keep = {e["id"] for e in sorted(elements, key=lambda e: (-score(e), e["id"]))[:k]}
    return [e for e in elements if e["id"] in keep]


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
