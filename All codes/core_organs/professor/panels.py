"""
professor.panels -- editor areas ("Outliner", "Properties", "Timeline", a docked side panel) found from the PICTURE when the application has no accessibility tree.

Dense editors (Blender, IDEs, DAWs, CAD) split their window with a recursive layout: a window is cut by one divider into two areas, each of which may be cut again.
That layout is a tree, and it can be recovered the same way it was made: find the divider that runs the full length of a rectangle, cut there, recurse.

  divider       a row (or column) across the WHOLE rectangle that (a) is a uniform thin stripe, or (b) is the edge between two differently coloured uniform fields
                -- and that differs from its surroundings on both sides. Text rows, grid lines and diagonal axes never span the rectangle uniformly.
  leaf          an area no further divider cuts. Its caption = the first printed words in its top strip ("Scene Collection", "Timeline"); the model can name the
                rest once per area (`name_panels`) instead of once per icon.
  hierarchy     every area carries its parent area and path ("Window > right column > Properties"), the same shape an accessibility tree would give.
Where an accessibility tree exists, uia_source's named containers are used instead (they carry the application's own names).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .schema import Box, Region, UIElement, fold


@dataclass
class Area:
    box: Box
    depth: int = 0
    children: List["Area"] = field(default_factory=list)
    axis: str = ""                       # how THIS area was cut: "h" (stacked) | "v" (side by side) | "" leaf


def _span_profile(rgb: np.ndarray, x1: int, y1: int, x2: int, y2: int, axis: str) -> Tuple[np.ndarray, np.ndarray]:
    """Per line across the rectangle: (mean colour [n,3], spread = max per-channel std along the line). axis 'h' -> one entry per row, 'v' -> per column."""
    sub = rgb[y1:y2, x1:x2].astype(np.float32)
    step = max(1, (x2 - x1) // 300) if axis == "h" else max(1, (y2 - y1) // 300)
    if axis == "h":
        s = sub[:, ::step, :]
        return s.mean(axis=1), s.std(axis=1).max(axis=1)
    s = sub[::step, :, :]
    return s.mean(axis=0), s.std(axis=0).max(axis=1)


def _best_cut(rgb: np.ndarray, box: Box, axis: str, min_side: int, scale: float) -> Optional[Tuple[int, int, float]]:
    """(start, end, strength) of the strongest divider along `axis` inside `box`, or None. Positions are absolute picture pixels."""
    x1, y1, x2, y2 = (int(v) for v in box.ituple())
    mean, spread = _span_profile(rgb, x1, y1, x2, y2, axis)
    n = len(mean)
    if n < 2 * min_side + 2:
        return None
    base = (y1 if axis == "h" else x1)
    best: Optional[Tuple[int, int, float]] = None
    uniform = spread < 10.0
    for i in range(min_side, n - min_side):
        if not uniform[i]:
            continue
        # a stripe of 1..8 uniform lines. It is a DIVIDER only if its colour differs from the BACKGROUND OF THE AREAS on both sides (the median colour of the lines
        # around it), not merely from the next line: a blank gap between two rows of controls has the area's own colour and must not cut anything.
        for w in range(1, 9):
            j = i + w
            if j + 3 >= n:
                break
            if not uniform[i:j].all():
                break
            stripe = mean[i:j].mean(axis=0)
            med_b = np.median(mean[max(0, i - 60):i], axis=0)
            med_a = np.median(mean[j:j + 60], axis=0)
            db, da = float(np.abs(stripe - med_b).max()), float(np.abs(stripe - med_a).max())
            strength = min(db, da)
            need = 18.0 if w <= 2 else 8.0                      # a 1-2 px line must be clearly different (grid lines are not area borders); a gutter of 3+ px less so
            if strength < need:
                # no gutter: the edge between two uniform fields of different colour
                near_b, near_a = mean[max(0, i - 4):i], mean[j:j + 4]
                if w == 1 and uniform[max(0, i - 4):i].all() and uniform[j:j + 4].all() and float(np.abs(near_b.mean(axis=0) - near_a.mean(axis=0)).max()) > 14 \
                        and float(np.abs(np.median(mean[max(0, i - 60):i], axis=0) - np.median(mean[j:j + 60], axis=0)).max()) > 14:
                    strength = float(np.abs(near_b.mean(axis=0) - near_a.mean(axis=0)).max())
                else:
                    continue
            if best is None or strength > best[2]:
                best = (base + i, base + j, strength)
    return best


def split_areas(rgb: np.ndarray, box: Box, scale: float = 1.0, min_side: int = 70, max_depth: int = 4, _depth: int = 0) -> Area:
    """Recursive guillotine cut of `box` at full-span dividers."""
    node = Area(box, _depth)
    if _depth >= max_depth:
        return node
    ms = int(min_side * scale)
    cuts = []
    for axis in ("h", "v"):
        c = _best_cut(rgb, box, axis, ms, scale)
        if c:
            cuts.append((c[2], axis, c))
    if not cuts:
        return node
    cuts.sort(reverse=True)
    _s, axis, (a, b, _st) = cuts[0]
    if axis == "h":
        parts = [Box(box.x1, box.y1, box.x2, a), Box(box.x1, b, box.x2, box.y2)]
    else:
        parts = [Box(box.x1, box.y1, a, box.y2), Box(b, box.y1, box.x2, box.y2)]
    node.axis = axis
    node.children = [split_areas(rgb, p, scale, min_side, max_depth, _depth + 1) for p in parts if p.w >= ms and p.h >= ms]
    if len(node.children) < 2:
        node.children, node.axis = [], ""
    return node


def leaves(a: Area) -> List[Area]:
    return [a] if not a.children else [l for c in a.children for l in leaves(c)]


def to_regions(root: Area, prefix: str = "p") -> List[Region]:
    """Every area of the layout tree as a Region (leaves 'panel', inner nodes 'panel' with parent links); the id encodes the path."""
    out: List[Region] = []

    def walk(a: Area, parent: str, path: str) -> None:
        rid = f"{prefix}{path}" if path else f"{prefix}0"
        if a.depth > 0:
            out.append(Region(rid, "panel", "panel", a.box, "cv", parent=parent, interactive=True, conf=0.5))
        for i, c in enumerate(a.children):
            walk(c, rid if a.depth > 0 else "", f"{path}{i}")

    walk(root, "", "")
    return out


def ink_fraction(ink: np.ndarray, box: Box) -> float:
    b = box.clip(ink.shape[1], ink.shape[0])
    if not b.valid:
        return 0.0
    x1, y1, x2, y2 = b.ituple()
    return float((ink[y1:y2, x1:x2] > 0).mean())


def classify_leaf(region: Region, elements: Sequence[UIElement], ink: Optional[np.ndarray], size: Tuple[int, int]) -> str:
    """'canvas' for a big, sparse work area (a viewport, a document), else 'panel' / 'list' by what is in it."""
    inside = [e for e in elements if e.bbox.overlap_frac(region.bbox) >= 0.6]
    dens = len(inside) / max(1.0, region.bbox.area / 10000.0)
    big = region.bbox.area >= 0.18 * size[0] * size[1]
    if big and dens < 1.2:
        return "canvas"
    rows = sorted({round(e.bbox.cy / 8) for e in inside if e.role in ("text", "list_item", "tree_item")})
    if len(inside) >= 6 and len(rows) >= 5 and region.bbox.w < 0.45 * size[0]:
        return "list"
    return "panel"


def caption(region: Region, elements: Sequence[UIElement], scale: float = 1.0) -> str:
    """The area's own title: the first real WORD printed in its top strip. Glyph letters ('Q' read off a search icon), numbers and one/two-character labels are not titles."""
    top = Box(region.bbox.x1, region.bbox.y1, region.bbox.x2, region.bbox.y1 + 40 * scale)
    heads = [e for e in elements if e.label and e.bbox.overlap_frac(top) >= 0.6 and e.role in ("text", "tab", "menu_item", "unknown")
             and "glyph-text" not in e.flags and sum(ch.isalpha() for ch in e.label) >= 4 and e.label.replace(" ", "").isalpha()]
    heads.sort(key=lambda e: (e.bbox.y1 // 12, e.bbox.x1))
    if not heads:
        return ""
    words = heads[0].label.split()
    while len(words) > 1 and (len(words[0]) < 4 or not any(ch in "aeiouAEIOU" for ch in words[0])):
        words.pop(0)                                              # an icon glyph read as 'Bcd' in front of the real title
    return " ".join(words)


def apply(regions: List[Region], elements: Sequence[UIElement], ink: Optional[np.ndarray], size: Tuple[int, int], scale: float = 1.0) -> None:
    """Label and classify the leaf areas; rename inner areas by their children's captions so the hierarchy reads 'right column > Properties'."""
    parents = {r.parent for r in regions if r.parent}
    for r in regions:
        if r.id in parents:
            r.label = "group"
            continue
        r.kind = classify_leaf(r, elements, ink, size)
        cap = caption(r, elements, scale)
        r.label = cap or ("work area" if r.kind == "canvas" else r.kind)
        r.interactive = r.kind != "canvas"
    canv = sorted([r for r in regions if r.kind == "canvas"], key=lambda r: -r.bbox.area)
    for r in canv[1:]:                                            # one work area per window: the other sparse areas (a timeline, a console) are panels
        r.kind, r.interactive = "panel", True
        if r.label == "work area":
            r.label = "panel"


def name_panels(regions: Sequence[Region], img, vlm, budget_s: float = 60.0) -> int:
    """One short model call for ALL unnamed areas together (a contact sheet of area crops) instead of one call per icon. Returns how many were named."""
    from . import labeler as LB
    parents = {r.parent for r in regions if r.parent}
    todo = [r for r in regions if r.id not in parents and (r.kind == "canvas" or not r.label or r.label in ("panel", "list", "group", "work area"))]
    if not todo or not vlm.available():
        return 0
    sheet_cells = [r.bbox for r in todo[:9]]
    names, _meta = LB.Labeler(vlm, None).label_boxes(img, sheet_cells, budget_s, 1, per_sheet=9, areas=True)
    n = 0
    for r, lab in zip(todo, names):
        if lab is not None and lab.text and not lab.text.startswith("~"):
            r.label = lab.text
            n += 1
    return n
