"""
harvest.video_graph_live -- the side channel from the consolidated video graph into a LIVE run. OFF unless HOJAIGA_VIDEO_GRAPH=1; with the flag off every function returns what it was given.

    hint_text(app_key, image, goal)   a sentence for the grounder's `hint` slot: "tutorial videos click 'X' from a screen like this" (empty when nothing in the graph is found on this screen)
    elements(app_key, image, goal)    the element contract {id, name, role, bbox, provider_tier, confidence} with provider_tier 'tier4_offline_video_grounding'
    augment(hint, image, app_key, goal)   the one call the grounder wrapper makes: hint + video hint, or the hint untouched

Evidence that an edge applies to THIS screen, in order of strength:
  1. its label is among the live controls' labels (the Set-of-Marks / UI-tree names the grounder already holds): `augment(..., som=, controls=)` - cheap, language of the live UI, no picture work;
  2. its opener control is FOUND again in the live picture (below) - used for `elements()` and when no labels are available.
Nothing from a video is trusted as a coordinate, and the screen is NOT recognised by a global fingerprint (measured: the same screen in two recordings scores as low as 0.55 against 0.94 for two
different screens of one app, so a whole-screen signature cannot decide). What is trusted is LOCAL evidence: the graph stores a small edge crop of the control the author's pointer was about to
press (taken from the picture before the click). Live, that crop is searched for in the live picture at a few scales; it counts as FOUND only when the best match is strong AND clearly better
than the next-best place (a crop of a plain rectangle matches every rectangle and is rejected). The box that comes back is in live pixels; a control that is not found is not returned.
The output is a hint / candidate for the existing loop, whose own verifier still decides whether the action worked. This module never acts, never launches anything and never writes.
"""
from __future__ import annotations

import contextlib
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from core_organs.harvest import consolidate as C

TIER = "tier4_offline_video_grounding"
CACHE: Dict[str, C.AppGraph] = {}
MIN_LOCALIZE = 0.60                      # edge-map template score the best place must reach
MIN_MARGIN = 0.12                        # ... and by how much it must beat the next-best, non-overlapping place
MIN_TEMPLATE_EDGE_PX = 20                # a crop with fewer edge pixels than this is too plain to find again
SCREEN_GATE = 0.35                       # loose "is this the same app at all" gate against the graph's stored screens (a blank / unrelated picture fails it)
MAX_EDGES_TRIED = 200
SCALES = (0.8, 0.9, 1.0, 1.12, 1.25)


def enabled() -> bool:
    return os.environ.get("HOJAIGA_VIDEO_GRAPH", "0") == "1"


def _root_for(app_key: str, root: str = "") -> str:
    if root:
        return root
    base = os.environ.get("HOJAIGA_VIDEO_GRAPH_DIR", "")
    safe = re.sub(r"[^\w.-]+", "_", app_key)
    return os.path.join(base, safe) if base else os.path.join(C.GRAPH_DIR, safe)


def graph(app_key: str, root: str = "") -> Optional[C.AppGraph]:
    r = _root_for(app_key, root)
    if r not in CACHE:
        CACHE[r] = C.AppGraph.load(app_key, r)
    g = CACHE[r]
    return g if g.edges else None


def _words(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]{3,}", (s or "").lower())}


def _live_canvas(image: Any, size: Tuple[int, int] = C.NORM) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
    g = C._to_gray(image)
    box = C.crop_box(g)
    return C._canvas(g, box, size), box


def same_app_gate(g: C.AppGraph, canvas: np.ndarray) -> bool:
    sig = C.layout_signature(canvas)
    return any(C.cos(sig, n["sig"]) >= SCREEN_GATE for n in g.nodes)


def localize_crop(live_edges: np.ndarray, tpl_gray: np.ndarray) -> Optional[Tuple[Tuple[int, int, int, int], float]]:
    """((x, y, w, h) on the canvas, score) of the one clear best place of `tpl_gray` in the live edge map, else None."""
    import cv2
    best = None
    for sc in SCALES:
        t = cv2.resize(tpl_gray, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA) if sc != 1.0 else tpl_gray
        if t.shape[0] >= live_edges.shape[0] or t.shape[1] >= live_edges.shape[1] or min(t.shape) < 6:
            continue
        te = cv2.Canny(cv2.GaussianBlur(t, (3, 3), 0), 50, 150).astype(np.float32)
        if te.sum() / 255.0 < MIN_TEMPLATE_EDGE_PX:
            continue
        res = cv2.matchTemplate(live_edges, te, cv2.TM_CCOEFF_NORMED)
        _mn, mx, _ml, loc = cv2.minMaxLoc(res)
        if mx < MIN_LOCALIZE:
            continue
        r2 = res.copy()
        h, w = t.shape
        r2[max(0, loc[1] - h // 2):loc[1] + h // 2 + 1, max(0, loc[0] - w // 2):loc[0] + w // 2 + 1] = -1.0       # forget the neighbourhood of the best place
        second = float(r2.max())
        if mx - second < MIN_MARGIN:
            continue                                                                                           # many places look equally like it: not a distinct control
        if best is None or mx > best[1]:
            best = ((int(loc[0]), int(loc[1]), int(w), int(h)), float(mx))
    return best


def localize(image: Any, e: Dict[str, Any]) -> Optional[Tuple[List[int], float]]:
    """Find the edge's opener control in the LIVE picture. -> ([x0, y0, x1, y1] in live pixels, score) or None."""
    import cv2
    canvas, (cx0, cy0, cx1, cy1) = _live_canvas(image, C.LOC_NORM)
    live_e = cv2.Canny(cv2.GaussianBlur(canvas, (3, 3), 0), 50, 150).astype(np.float32)
    H, W = canvas.shape
    fx, fy = (cx1 - cx0) / W, (cy1 - cy0) / H
    best: Optional[Tuple[List[int], float]] = None
    for oc in e.get("opener_crops") or []:
        p = oc.get("path")
        if not p or not os.path.isfile(p):
            continue
        hit = localize_crop(live_e, C._to_gray(p))
        if hit and (best is None or hit[1] > best[1]):
            (x, y, w, h), s = hit
            best = ([int(cx0 + x * fx), int(cy0 + y * fy), int(cx0 + (x + w) * fx), int(cy0 + (y + h) * fy)], s)
    return best


def live_labels(som: Any = None, controls: Any = None) -> set:
    """Normalised labels of the controls the grounder already holds for this screen (Set-of-Marks `label`, UI-tree `name`)."""
    out = set()
    with contextlib.suppress(Exception):
        for e in (som or {}).get("elements", []) or []:
            out.add(C.label_key(str(e.get("label") or e.get("name") or "")))
    with contextlib.suppress(Exception):
        for c in controls or []:
            out.add(C.label_key(str(c.get("name") or c.get("label") or "") if isinstance(c, dict) else str(c)))
    out.discard("")
    return out


def candidates_by_label(g: C.AppGraph, labels: set, goal: str = "", limit: int = 3) -> List[Tuple[Dict[str, Any], None, float]]:
    """Labelled edges whose label is one of the live controls' labels, goal-relevant and best-supported first."""
    gw = _words(goal)
    hits = [e for e in g.edges if g.best_label(e) and g.best_label(e) in labels]
    hits.sort(key=lambda e: (-len(_words(g.best_label(e)) & gw), -g.support(e)))
    return [(e, None, 1.0) for e in hits[:limit]]


def candidates(g: C.AppGraph, image: Any, goal: str = "", limit: int = 3) -> List[Tuple[Dict[str, Any], List[int], float]]:
    """Labelled edges whose control is FOUND on the live picture: [(edge, live box, score)], goal-relevant and best-supported first."""
    canvas, _ = _live_canvas(image)
    if not same_app_gate(g, canvas):
        return []
    gw = _words(goal)
    pool = [e for e in g.edges if g.best_label(e) and e.get("opener_crops")]
    pool.sort(key=lambda e: (-len(_words(g.best_label(e)) & gw), -g.support(e)))
    found = []
    for e in pool[:MAX_EDGES_TRIED]:
        hit = localize(image, e)
        if hit:
            found.append((e, hit[0], hit[1]))
    found.sort(key=lambda t: (-len(_words(g.best_label(t[0])) & gw), -g.support(t[0]), -t[2]))
    return found[:limit]


def shortcut_hints(g: C.AppGraph, goal: str, labels: Optional[set] = None, limit: int = 2) -> List[Dict[str, Any]]:
    """Shortcut facts (read off several authors' screens) the goal names, or whose action is among the live controls: Path B of the multi-path ladder (keyboard) with its evidence."""
    gw = {w for w in re.findall(r"[a-z0-9]+", (goal or "").lower())}
    out = []
    for f in g.facts():
        key_tokens = C.label_key(f["action"]).split()
        if key_tokens and (set(key_tokens) <= gw or (labels and C.label_key(f["action"]) in labels)):
            out.append(f)
    out.sort(key=lambda f: -f["videos"])
    return out[:limit]


def hint_text(app_key: str, image: Any, goal: str = "", root: str = "", labels: Optional[set] = None) -> str:
    g = graph(app_key, root)
    if g is None:
        return ""
    with contextlib.suppress(Exception):
        sc = shortcut_hints(g, goal, labels)
        sc_txt = ("Shortcut seen on screen in tutorial videos: " + "; ".join(f"{f['action']} = {f['windows'].upper()} ({f['videos']} videos, unverified)" for f in sc) + ".") if sc else ""
        if image is None and not labels:
            return sc_txt
        found = candidates_by_label(g, labels, goal) if labels else candidates(g, image, goal)
        if not found:
            return sc_txt
        parts = []
        for e, _box, _s in found:
            n = g.support(e)
            parts.append(f"{g.best_kind(e)} '{g.best_label(e)}' ({'seen in ' + str(n) + ' tutorial videos' if n > 1 else 'seen in 1 tutorial video, an alternate path'})")
        return ("From a screen like this, tutorial videos next: " + "; ".join(parts) + ".") + ((" " + sc_txt) if sc_txt else "")
    return ""


def elements(app_key: str, image: Any, goal: str = "", root: str = "") -> List[Dict[str, Any]]:
    """Candidates in the loop's element contract, only for controls that were found again in the live picture."""
    g = graph(app_key, root)
    if g is None or image is None:
        return []
    out: List[Dict[str, Any]] = []
    with contextlib.suppress(Exception):
        for e, box, score in candidates(g, image, goal, limit=6):
            out.append({"id": f"vg{e['id']}", "name": g.best_label(e), "role": "button", "bbox": box, "provider_tier": TIER,
                        "confidence": round(min(0.99, score * min(1.0, 0.5 + 0.25 * g.support(e))), 3)})
    return out


def augment(hint: str, image: Any, app_key: str, goal: str = "", som: Any = None, controls: Any = None) -> str:
    """The single call the grounder wrapper makes. Flag off, no graph, unknown screen or any error: `hint` comes back unchanged."""
    if not enabled():
        return hint
    with contextlib.suppress(Exception):
        extra = hint_text(app_key, image, goal, labels=live_labels(som, controls) or None)
        if extra:
            return (hint + "\n" if hint else "") + extra
    return hint
