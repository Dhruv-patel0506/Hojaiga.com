"""
harvest.prompt_v2 -- training / inference prompt format v2: the screen PLUS what a 448x448 vision input crushes.

MEASURED (Notepad's toolbar): the formatting icons are ~16 px wide in the window picture; the model reads the picture at 448x448, where they shrink to ~7 px blurs, and the neighbouring unnamed icons (Italic,
Strikethrough, Link) get confused. Two additions, both DYNAMIC (nothing app-specific, no coordinates, no control ids):

  1. DENSE STRIPS: where the scanner finds a cluster of small elements (every element <= 28 px wide and high, at least `min_count` of them close together in a row or column), that strip is cropped from the
     full-resolution picture, enlarged 2x and attached as an extra image after the full picture.
  2. NAMES: when the application tells us what its controls are called (UI Automation name / tooltip) or the icon vault recognises a crop, the element list gets a `Names:` line `#id name | #id name ...`
     for exactly those elements.

A v2 record has the same roles and the same answer as v1; only the user turn is richer: [full image, strip crop 1, strip crop 2, ...] + text. The trainer's collator already accepts several images per turn.
`prompt_version` is recorded in meta so v1 and v2 pairs can be told apart (and an adapter trained on v1 is never fed v2).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

SMALL_PX = 28            # a control this small (both sides) is "dense-strip material"
MIN_STRIP = 4            # at least this many small elements near each other make a strip
GAP_PX = 36              # elements closer than this (edge to edge) along the strip axis belong together
ZOOM = 2.0
MAX_STRIPS = 4


def dense_strips(elements: Sequence[Dict[str, Any]], size: Tuple[int, int], small: int = SMALL_PX, min_count: int = MIN_STRIP, gap: int = GAP_PX, margin: int = 6, max_strips: int = MAX_STRIPS) -> List[Tuple[int, int, int, int]]:
    """Boxes (x0, y0, x1, y1) of dense clusters of small elements: elements with w, h <= `small` are grouped when they sit on one line (centres within half an element height) and neighbours are within
    `gap` px; a group of >= min_count becomes a strip (its union, plus a margin, clipped to the picture)."""
    smalls = [e for e in elements if e["box"][2] <= small and e["box"][3] <= small]
    smalls.sort(key=lambda e: (round((e["box"][1] + e["box"][3] / 2) / 12), e["box"][0]))
    groups: List[List[Dict[str, Any]]] = []
    for e in sorted(smalls, key=lambda e: (e["box"][1] + e["box"][3] / 2, e["box"][0])):
        cy = e["box"][1] + e["box"][3] / 2
        placed = False
        for g in groups:
            last = max(g, key=lambda q: q["box"][0] + q["box"][2])
            lcy = last["box"][1] + last["box"][3] / 2
            if abs(cy - lcy) <= max(8, 0.6 * e["box"][3]) and e["box"][0] - (last["box"][0] + last["box"][2]) <= gap and e["box"][0] >= last["box"][0]:
                g.append(e)
                placed = True
                break
        if not placed:
            groups.append([e])
    # the same for columns (a vertical toolbar): elements sharing an x centre
    cols: List[List[Dict[str, Any]]] = []
    for e in sorted(smalls, key=lambda e: (e["box"][0] + e["box"][2] / 2, e["box"][1])):
        cx = e["box"][0] + e["box"][2] / 2
        placed = False
        for g in cols:
            last = max(g, key=lambda q: q["box"][1] + q["box"][3])
            lcx = last["box"][0] + last["box"][2] / 2
            if abs(cx - lcx) <= max(8, 0.6 * e["box"][2]) and e["box"][1] - (last["box"][1] + last["box"][3]) <= gap and e["box"][1] >= last["box"][1]:
                g.append(e)
                placed = True
                break
        if not placed:
            cols.append([e])
    out: List[Tuple[int, int, int, int]] = []
    for g in sorted([g for g in groups + cols if len(g) >= min_count], key=lambda g: -len(g)):
        x0 = min(e["box"][0] for e in g) - margin
        y0 = min(e["box"][1] for e in g) - margin
        x1 = max(e["box"][0] + e["box"][2] for e in g) + margin
        y1 = max(e["box"][1] + e["box"][3] for e in g) + margin
        box = (max(0, int(x0)), max(0, int(y0)), min(size[0], int(x1)), min(size[1], int(y1)))
        if any(not (box[2] <= o[0] or o[2] <= box[0] or box[3] <= o[1] or o[3] <= box[1]) for o in out):
            continue                                                              # overlapping an already chosen strip: one crop is enough
        out.append(box)
        if len(out) >= max_strips:
            break
    return out


def strip_crops(image: Any, strips: Sequence[Tuple[int, int, int, int]], zoom: float = ZOOM, max_side: int = 900) -> List[Any]:
    """Each strip cut from the FULL-resolution picture and enlarged `zoom` times (bicubic), capped at max_side px on the long side."""
    from PIL import Image
    out = []
    for b in strips:
        c = image.crop(b)
        f = min(zoom, max_side / max(c.size)) if max(c.size) else zoom
        out.append(c.resize((max(1, int(c.size[0] * f)), max(1, int(c.size[1] * f))), Image.BICUBIC))
    return out


def names_line(elements: Sequence[Dict[str, Any]], names: Dict[int, str], limit: int = 40) -> str:
    """`Names: #18 Bold | #19 Italic ...` for the elements whose name is known (UIA / icon vault), in element order. '' when none is known."""
    parts = [f"#{e['id']} {names[e['id']]}" for e in elements if names.get(e["id"])]
    return ("Names: " + " | ".join(parts[:limit])) if parts else ""


def name_elements(elements: Sequence[Dict[str, Any]], controls: Sequence[Dict[str, Any]], min_cover: float = 0.6) -> Dict[int, str]:
    """{element id: control name} for elements that sit inside a named control's rectangle (the same containment rule the data pipeline uses to ground a click)."""
    out: Dict[int, str] = {}
    for e in elements:
        ex, ey, ew, eh = e["box"]
        cx, cy = ex + ew / 2, ey + eh / 2
        best = None
        for c in controls:
            x, y, w, h = c["box"]
            if x <= cx <= x + w and y <= cy <= y + h and (c.get("name") or "").strip():
                if best is None or w * h < best["box"][2] * best["box"][3]:
                    best = c
        if best is not None:
            out[e["id"]] = best["name"].strip()
    return out


def user_content(image: Any, som: Dict[str, Any], app_key: str, goal: str, controls: Optional[Sequence[Dict[str, Any]]] = None, names: Optional[Dict[int, str]] = None,
                 image_ref: Any = None, crop_refs: Optional[Sequence[Any]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """The v2 user turn: [full picture, strip crops...] + text (`Application`, `Elements`, `Names` when known, `Goal`). `image_ref` / `crop_refs` replace the pictures by paths when a record is written
    to disk. Returns (content list, info) where info records the strips and how many names were attached."""
    from . import video_pipeline as VP
    elements = som["elements"]
    strips = dense_strips(elements, image.size)
    crops = strip_crops(image, strips)
    nm = dict(names or {})
    if controls and not nm:
        nm = name_elements(elements, controls)
    text = f"Application: {app_key}\nElements:\n{VP.som_text(som)}\n"
    nl = names_line(elements, nm)
    if nl:
        text += nl + "\n"
    if crops:
        text += f"Zoomed strips (2x, in order): {len(crops)}\n"
    text += f"Goal: {goal}"
    content: List[Dict[str, Any]] = [{"type": "image", "image": image_ref if image_ref is not None else image}]
    for i, c in enumerate(crops):
        content.append({"type": "image", "image": (crop_refs[i] if crop_refs and i < len(crop_refs) else c)})
    content.append({"type": "text", "text": text})
    return content, {"strips": strips, "n_names": len(nm), "n_crops": len(crops)}
