"""
professor.priors -- the few UI CONVENTIONS that hold across applications (law L3: categories, never application names).

Window buttons: at the right end of a title bar the last control is Close; with three buttons they are Minimize, Maximize (or Restore), Close. These are
not read from anywhere and not per-app: every Windows caption bar works this way, and a vision model that sees a bare "x" or "square" glyph on a
grey bar guesses worse than this rule knows. Names from the accessibility tree always win; the convention only replaces unnamed or model-guessed names,
and the element says so (`sources` has 'convention', flag 'convention').
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from .schema import Region, UIElement, fold

_NAMES3 = ("Minimize", "Maximize", "Close")
_KNOWN = {"minimize", "maximize", "restore", "restore down", "close", "min", "max"}


def apply_window_buttons(elements: Sequence[UIElement], regions: Sequence[Region], size: Tuple[int, int]) -> int:
    """Name the caption buttons of every title bar region found. Returns how many elements were (re)named."""
    W = size[0]
    n = 0
    for r in regions:
        if r.kind != "titlebar":
            continue
        cand: List[UIElement] = [e for e in elements if (e.role in ("button", "icon", "window_control", "unknown") or "glyph-text" in e.flags) and e.bbox.overlap_frac(r.bbox) >= 0.6
                                 and e.bbox.cx >= 0.8 * W and e.bbox.w <= 70 and e.bbox.h <= 60 and "uia" not in e.sources]
        cand.sort(key=lambda e: e.bbox.x1)
        if len(cand) >= 3:
            group = cand[-3:]
            names = _NAMES3
        elif len(cand) >= 1 and cand[-1].bbox.x2 >= 0.97 * W:
            group = cand[-1:]
            names = ("Close",)
        else:
            continue
        for e, nm in zip(group, names):
            if fold(e.label) == fold(nm):
                continue
            if e.label and fold(e.label) in _KNOWN and "unverified" not in e.flags:
                continue
            e.hint = e.hint or (e.label if e.label else "")
            e.label, e.label_source, e.role = nm, "convention", "window_control"
            e.conf = max(e.conf, 0.8)
            if "convention" not in e.sources:
                e.sources.append("convention")
            e.flags = [f for f in e.flags if f not in ("unlabeled", "unverified", "glyph-text", "ambiguous")] + ["convention"]
            n += 1
    return n
