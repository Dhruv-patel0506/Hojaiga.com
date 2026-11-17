"""
professor.coverage -- the proof behind "it scanned literally every button".

A scan that merely lists what it found cannot say what it MISSED. This module measures it from the pixels:

  ink          every pixel that stands out from its background inside the interactive areas (toolbars, ribbons, panels, dialogs -- not the document canvas)
  claimed      pixels inside the box of some control we found
  residual     ink nobody claimed  -> connected shapes of glyph size = controls we may have missed
  coverage     1 - residual_ink / ink  per region and overall
  exhaust()    re-probe each residual shape (crop -> name it via the contact sheet); named -> a new control, "?" -> decoration (separator, shadow,
               border) that is remembered as such. Repeat until a round finds nothing new: the scan is EXHAUSTED, or the budget says it stopped early.
Reported honestly: `exhausted` is True only when the last audit left no unexplained control-sized shapes.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from .candidates import Candidate, _components, ink_mask
from .labeler import Label, Labeler
from .schema import Box, Region, UIElement, boxes_union

try:
    import cv2
except Exception:                                                                       # pragma: no cover
    cv2 = None


def _zone_mask(shape: Tuple[int, int], regions: Sequence[Region]) -> np.ndarray:
    H, W = shape
    zone = np.zeros((H, W), np.uint8)
    inter = [r for r in regions if r.interactive]
    if not inter:
        zone[:] = 1
        return zone
    for r in inter:
        x1, y1, x2, y2 = r.bbox.clip(W, H).ituple()
        zone[y1:y2, x1:x2] = 1
    return zone


def _claimed_mask(shape: Tuple[int, int], elements: Sequence[UIElement], pad: int) -> np.ndarray:
    H, W = shape
    m = np.zeros((H, W), np.uint8)
    for e in elements:
        b = e.bbox.expand(pad).clip(W, H)
        if b.valid:
            x1, y1, x2, y2 = b.ituple()
            m[y1:y2, x1:x2] = 1
    return m


def audit(img: Image.Image, elements: Sequence[UIElement], regions: Sequence[Region], scale: float = 1.0, ink: Optional[np.ndarray] = None,
          ignore: Sequence[Box] = ()) -> Dict[str, Any]:
    """Measure what the current element list leaves unexplained. Returns coverage numbers and the residual control-sized shapes (picture pixels)."""
    gray = np.asarray(img.convert("L"))
    H, W = gray.shape
    if ink is None:
        ink = ink_mask(gray, scale)
    zone = _zone_mask((H, W), regions)
    claimed = _claimed_mask((H, W), elements, max(3, int(round(6 * scale))))          # the local-contrast ink reaches ~half the blur window past a glyph's edge
    for b in ignore:
        bb = b.expand(2).clip(W, H)
        if bb.valid:
            x1, y1, x2, y2 = bb.ituple()
            claimed[y1:y2, x1:x2] = 1
    live = (ink > 0) & (zone > 0)
    resid = live & (claimed == 0)
    total, left = int(live.sum()), int(resid.sum())
    per_region: Dict[str, Any] = {}
    for r in regions:
        if not r.interactive:
            continue
        x1, y1, x2, y2 = r.bbox.clip(W, H).ituple()
        a = int(live[y1:y2, x1:x2].sum())
        b = int(resid[y1:y2, x1:x2].sum())
        per_region[r.id] = {"kind": r.kind, "label": r.label, "ink_px": a, "unexplained_px": b, "coverage": round(1 - b / a, 3) if a else 1.0}
    # control-sized unexplained shapes
    shapes: List[Box] = []
    if left:
        k = max(3, int(round(4 * scale)) | 1)
        merged = cv2.dilate(resid.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)), iterations=1)
        for x1, y1, x2, y2, a in _components(merged, int(10 * scale)):
            w, h = x2 - x1, y2 - y1
            if w < 8 * scale or h < 8 * scale or w > 90 * scale or h > 90 * scale:
                continue
            if max(w, h) / max(1, min(w, h)) > 7:
                continue                                                  # a rule / border line, not a control
            shapes.append(Box(x1, y1, x2, y2))
    return {"ink_px": total, "unexplained_px": left, "coverage": round(1 - left / total, 4) if total else 1.0, "per_region": per_region,
            "uncovered": shapes, "uncovered_n": len(shapes)}


def public(report: Dict[str, Any]) -> Dict[str, Any]:
    """JSON-safe copy (boxes as lists)."""
    r = dict(report)
    r["uncovered"] = [b.to_list() for b in r.get("uncovered", [])]
    return r


def exhaust(img: Image.Image, elements: List[UIElement], regions: Sequence[Region], scale: float, labeler: Optional[Labeler], budget_s: float,
            rounds: int = 3, ink: Optional[np.ndarray] = None) -> Tuple[List[UIElement], Dict[str, Any]]:
    """Re-probe everything the audit leaves unexplained until a round finds nothing new. New controls are appended (ids are assigned by the caller)."""
    t0 = time.time()
    decor: List[Box] = []
    added: List[UIElement] = []
    history: List[Dict[str, Any]] = []
    rep = audit(img, elements, regions, scale, ink)
    history.append({"round": 0, "coverage": rep["coverage"], "uncovered": rep["uncovered_n"]})
    for rd in range(1, rounds + 1):
        todo = [b for b in rep["uncovered"] if not any(b.iou(d) > 0.5 for d in decor)]
        if not todo or time.time() - t0 > budget_s:
            break
        labels: List[Optional[Label]] = [None] * len(todo)
        if labeler is not None:
            mem = labeler.from_memory(img, todo)
            need = [i for i, m in enumerate(mem) if m is None]
            for i, m in enumerate(mem):
                labels[i] = m
            if need:
                got, _meta = labeler.label_boxes(img, [todo[i] for i in need], max(5.0, budget_s - (time.time() - t0)))
                for i, g in zip(need, got):
                    labels[i] = g
        new = 0
        for b, lab in zip(todo, labels):
            if lab is None or not lab.text or lab.text.startswith("~"):
                decor.append(b)
                continue
            fl = ["reprobe"] + list(lab.flags)
            if lab.via.startswith("vlm") and lab.conf < 0.8:
                fl.append("unverified")
            e = UIElement(0, lab.text, "button", b.expand(2), "", ["cv", "icon_memory" if lab.via == "memory" else "vlm"], round(0.3 + 0.5 * lab.conf, 3),
                          lab.via, True, None, False, "", "", "", "", "", {}, fl)
            added.append(e)
            elements = elements + [e]
            new += 1
        rep = audit(img, elements, regions, scale, ink, ignore=decor)
        history.append({"round": rd, "new_controls": new, "decoration": len(decor), "coverage": rep["coverage"], "uncovered": rep["uncovered_n"]})
        if new == 0:
            break
    final = audit(img, elements, regions, scale, ink, ignore=decor)
    final["rounds"] = history
    final["added"] = len(added)
    final["decoration_ignored"] = len(decor)
    final["exhausted"] = final["uncovered_n"] == 0
    final["seconds"] = round(time.time() - t0, 2)
    return added, final
