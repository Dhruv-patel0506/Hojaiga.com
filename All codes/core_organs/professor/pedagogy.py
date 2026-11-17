"""
professor.pedagogy -- the glue between WHAT THE APPLICATION IS (catalog, archetype), HOW IT BEHAVES (probe graph) and HOW IT IS TAUGHT (teacher, lesson runner, overlay).

  StateWatcher     recognises that the learner DID something by a structural change of the accessibility tree (a control appeared, a value changed, a dialog opened) -- the
                   lesson advances on state change, not on a timer and not on pixels alone. Read-only: it never touches the application.
  frame_for        everything the teacher needs about an application in one call: catalog (loaded or harvested), archetype, behaviour notes learned by probing
  behaviour_lines  "Add Marker changes the state; Options switches the context" -- what probing measured, as short facts for the prompt
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .schema import ScreenModel, fold


class StateWatcher:
    """Baseline snapshot of the window's tree; `poll()` returns a Delta when something CHANGED since the baseline (None otherwise)."""

    def __init__(self, hwnd: int, with_image: bool = False):
        self.hwnd = hwnd
        self.with_image = with_image
        self.base = None
        self.polls = 0

    def rebase(self) -> None:
        from .probe import snapshot
        try:
            self.base = snapshot(self.hwnd, with_image=self.with_image)
        except Exception:
            self.base = None

    def poll(self) -> Optional[Any]:
        from .probe import snapshot, delta
        if self.base is None:
            self.rebase()
            return None
        try:
            now = snapshot(self.hwnd, with_image=self.with_image)
        except Exception:
            return None
        self.polls += 1
        if now.sig == self.base.sig and now.windows == self.base.windows:
            return None
        d = delta(self.base, now)
        if d.effect() == "no_effect":
            return None
        return d


def frame_for(sm: ScreenModel, hwnd: int = 0, brain: Any = None, harvest: bool = True, allow_hover: bool = False, owned: bool = False) -> Tuple[Optional[Any], Dict[str, Any]]:
    """(catalog, archetype) for a scanned window: the stored catalog when one exists for this application, else a fresh passive harvest (saved). The archetype is always
    recomputed (it depends on what is on screen now) and cached on the catalog."""
    from . import archetype as AR
    from .harvest import Catalog, harvest_model
    known = bool(sm.app_key) and sm.app_key != "unknown"                  # a picture of unknown origin has no application to remember a catalog for
    cat = Catalog.load(sm.app_key) if known else None
    if cat is None and harvest:
        cat = harvest_model(sm, hwnd, hover=allow_hover, allow_input=allow_hover, owned=owned)
        if known and hwnd:                                               # only a live window's catalog is stored (not a screenshot's)
            try:
                cat.save()
            except Exception:
                pass
    arch = AR.classify(sm, cat, brain)
    if cat is not None:
        cat.archetype = {k: arch[k] for k in ("id", "name", "confidence", "by")}
    return cat, arch


def behaviour_lines(app_key: str, limit: int = 6) -> str:
    """What probing measured about this application, as short facts (empty when it was never probed)."""
    import json
    import os
    from .probe import GRAPH_DIR
    p = os.path.join(GRAPH_DIR, (app_key or "app") + ".json")
    try:
        with open(p, "r", encoding="utf-8") as fh:
            rules = json.load(fh).get("rules", [])
    except Exception:
        return ""
    out: List[str] = []
    for r in rules:
        eff = r.get("effect")
        if eff in ("no_effect", "untested"):
            continue
        verb = r.get("verb", "")
        txt = {"state_change": f"'{verb}' changes the application's state", "context_change": f"'{verb}' switches what the panels show", "opens_dialog": f"'{verb}' opens a dialog",
               "visual_only": f"'{verb}' changes only the picture"}.get(eff, "")
        if txt:
            out.append(txt + (f" ({r['note']})" if r.get("note") and eff != "opens_dialog" else ""))
        if len(out) >= limit:
            break
    return "\n".join(out)
