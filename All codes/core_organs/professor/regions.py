"""
professor.regions -- "the whole button section": turning a pile of controls into named areas (menu bar, ribbon, ribbon GROUPS, toolbars, side panels, canvas, status bar).

Sources, merged by overlap:
  uia   exact containers from the accessibility tree (toolbar, menubar, statusbar, titlebar, tab strip, named groups)
  cv    bands/strips found from the geometry of the controls themselves (candidates.find_strips) -- the only source for UIA-blind applications
  text  a region's caption is the first printed text near its top/left edge ("Outliner", "Properties", "Clipboard")
A ribbon band is further split into GROUPS at the vertical separator lines between them, each named by the caption printed under its buttons.
Elements are then assigned to the smallest region that contains them, so the teacher can say "in the Clipboard group of the Home tab".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from .candidates import Candidate, CandidateSet, Strip, ink_mask
from .schema import Box, Region, UIElement, boxes_union, fold

try:
    import cv2
except Exception:                                                                       # pragma: no cover
    cv2 = None


def classify_band(box: Box, word_frac: float, size: Tuple[int, int], scale: float, window_mode: bool, orient: str = "row") -> str:
    W, H = size
    if orient == "col":
        return "sidebar"
    top_zone = box.y1 < 0.14 * H + 40 * scale
    if box.cy > H - 70 * scale and box.h <= 48 * scale:
        return "statusbar"
    if top_zone:
        if box.h <= 46 * scale and word_frac >= 0.75:
            return "menubar"
        if box.h >= 64 * scale:
            return "ribbon"
        return "toolbar"
    if box.h >= 64 * scale and box.w >= 0.5 * W:
        return "ribbon"
    return "toolbar"


def _caption_for(box: Box, cands: Sequence[Candidate], pos: str = "top") -> str:
    """First printed text in the top-left of a region (panel header) or the lowest centred text (ribbon group caption)."""
    texts = [c for c in cands if c.kind == "text" and c.text and (c.box.overlap_frac(box) >= 0.7 or box.contains(c.box, slack=2))]
    if not texts:
        return ""
    if pos == "bottom":
        lowest = max(texts, key=lambda c: c.box.cy)
        if lowest.box.cy >= box.y1 + 0.55 * box.h:
            return lowest.text.strip()
        return ""
    head = [c for c in texts if c.box.cy <= box.y1 + max(30.0, 0.14 * box.h)]
    if not head:
        return ""
    head.sort(key=lambda c: (c.box.y1, c.box.x1))
    return head[0].text.strip()


def _vertical_separators(ink: np.ndarray, band: Box, scale: float) -> List[float]:
    """x positions of long thin vertical lines inside a band (ribbon group dividers)."""
    b = band.clip(ink.shape[1], ink.shape[0])
    if not b.valid or b.h < 36 * scale:
        return []
    x1, y1, x2, y2 = b.ituple()
    sub = ink[y1:y2, x1:x2]
    k = max(12, int(0.55 * (y2 - y1)))
    opened = cv2.morphologyEx(sub, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, k)))
    cols = (opened > 0).sum(axis=0)
    xs = np.nonzero(cols >= 0.55 * (y2 - y1))[0]
    seps: List[float] = []
    for x in xs:
        if not seps or x - seps[-1] > 4 * scale:
            seps.append(float(x))
    return [s + x1 for s in seps]


def ribbon_groups(band_region: Region, cs: CandidateSet, gray_ink: np.ndarray, scale: float) -> List[Region]:
    """Split a ribbon/toolbar band into its groups at divider lines; caption = text printed lowest inside the group."""
    b = band_region.bbox
    if b.h < 56 * scale:
        return []
    seps = _vertical_separators(gray_ink, b, scale)
    edges = [b.x1] + [s for s in seps if b.x1 + 20 * scale < s < b.x2 - 20 * scale] + [b.x2]
    out: List[Region] = []
    for i in range(len(edges) - 1):
        gb = Box(edges[i], b.y1, edges[i + 1], b.y2)
        inside = [c for c in cs.candidates if c.box.overlap_frac(gb) >= 0.6]
        if len(inside) < 2:
            continue
        cap = _caption_for(gb, inside, "bottom")
        out.append(Region(f"{band_region.id}g{i}", "toolbar", (band_region.label + " > " + cap) if cap else band_region.label, gb, "cv",
                          parent=band_region.id, conf=0.55 if cap else 0.4))
    return out if len(out) >= 2 else []


@dataclass
class RowBand:
    y1: int
    y2: int
    bg: Tuple[int, int, int]
    full: float                       # mean share of the row that is background: a toolbar row is mostly background, a document row is not


def row_bands(rgb: np.ndarray, scale: float = 1.0) -> List[RowBand]:
    """Horizontal stripes of constant background colour (title bar, menu bar, tab strip, ribbon, status bar each have their own tint or are divided by a
    1-px rule). The stripe a strip of controls sits in tells how far its section REALLY extends -- far beyond the controls themselves."""
    H, W, _c = rgb.shape
    step = max(1, W // 400)
    px = rgb[:, ::step, :].astype(np.int16)
    q = (px // 8).astype(np.int32)
    key = q[..., 0] * 1024 + q[..., 1] * 32 + q[..., 2]
    bg = np.zeros((H, 3), np.int16)
    frac = np.zeros(H, np.float32)
    for y in range(H):
        vals, counts = np.unique(key[y], return_counts=True)
        k = vals[int(np.argmax(counts))]
        sel = key[y] == k
        bg[y] = px[y][sel].mean(axis=0)
        frac[y] = counts.max() / key.shape[1]
    diff = np.abs(np.diff(bg, axis=0)).max(axis=1)
    cuts = set(int(i) + 1 for i in np.nonzero(diff > 5)[0])
    rowdiff = np.abs(np.diff(px, axis=0)).max(axis=2)                      # row-to-row change per sampled column
    rule = np.nonzero((rowdiff > 12).mean(axis=1) > 0.85)[0]               # a full-width 1-px line
    for i in rule:
        cuts.add(int(i))
        cuts.add(int(i) + 2)
    edges = [0] + sorted(c for c in cuts if 0 < c < H) + [H]
    bands: List[RowBand] = []
    for a, b in zip(edges[:-1], edges[1:]):
        if b - a < max(6, int(6 * scale)):
            continue
        seg = frac[a:b]
        col = tuple(int(v) for v in np.median(bg[a:b], axis=0))
        bands.append(RowBand(a, b, col, float(seg.mean())))                 # type: ignore[arg-type]
    return bands


def _band_at(bands: Sequence[RowBand], y: float, max_h: float) -> Optional[RowBand]:
    for b in bands:
        if b.y1 <= y < b.y2 and (b.y2 - b.y1) <= max_h and b.full >= 0.5:
            return b
    return None


def _classify(band: Box, word_frac: float, size: Tuple[int, int], scale: float, window_mode: bool, has_controls_right: bool, next_tall: bool) -> str:
    W, H = size
    if band.cy > H - 80 * scale and band.h <= 56 * scale:
        return "statusbar"
    if band.y1 <= 6 * scale and band.h <= 52 * scale and has_controls_right:
        return "titlebar"
    if band.h >= 60 * scale:
        return "ribbon" if band.y1 < H * 0.3 else "toolbar"
    if word_frac >= 0.7 and band.y1 < H * 0.3:
        return "tab_strip" if next_tall else "menubar"
    return "toolbar"


def regions_from_cv(cs: CandidateSet, size: Tuple[int, int], scale: float, window_mode: bool, ink: Optional[np.ndarray] = None,
                    rgb: Optional[np.ndarray] = None) -> List[Region]:
    """Sections from geometry + background: each row of controls is placed in its background stripe; the section is the whole stripe when the stripe is
    window-wide (menu bar, ribbon, status bar), else the controls' own box. Ribbons are split into captioned groups; columns of icons become side strips."""
    W, H = size
    regions: List[Region] = []
    bands = row_bands(rgb, scale) if rgb is not None else []
    row_strips = [(i, s) for i, s in enumerate(cs.strips) if s.orient == "row"]
    grouped: Dict[int, List[int]] = {}
    loose: List[int] = []
    for i, s in row_strips:
        rb = _band_at(bands, s.box.cy, 230 * scale)
        if rb is None:
            loose.append(i)
        else:
            grouped.setdefault(bands.index(rb), []).append(i)
    order = sorted(grouped)
    tall_idx = {bi for bi in order if (bands[bi].y2 - bands[bi].y1) >= 60 * scale}
    n = 0
    for pos, bi in enumerate(order):
        rb = bands[bi]
        members = grouped[bi]
        sb = boxes_union(cs.strips[i].box for i in members)
        wide = rb.full >= 0.75
        box = Box(0, rb.y1, W, rb.y2) if wide else sb.expand(4 * scale)
        toks = [cs.candidates[m] for i in members for m in cs.strips[i].members]
        wf = float(np.mean([c.kind == "text" for c in toks])) if toks else 0.0
        right_controls = any(c.kind != "text" and c.box.x2 >= 0.9 * W for c in toks)
        next_tall = any(b2 in tall_idx for b2 in order[pos + 1:pos + 2])
        kind = _classify(box, wf, size, scale, window_mode, right_controls, next_tall)
        cap = _caption_for(box, toks, "top") if kind in ("toolbar",) and not wide else ""
        regions.append(Region(f"c{n}", kind, cap or kind.replace("_", " "), box, "cv", conf=0.65 if wide else 0.5))
        n += 1
    canvas_guess = _free_area(regions, size)
    for i in loose:                                                     # strips whose stripe could not be isolated keep their own box
        s = cs.strips[i]
        wf = s.word_frac
        if wf >= 0.5 and canvas_guess is not None and s.box.overlap_frac(canvas_guess) >= 0.8:
            continue                                                    # a row of words inside the work area is text, not a toolbar
        kind = _classify(s.box, wf, size, scale, window_mode, False, False)
        regions.append(Region(f"c{n}", kind, kind.replace("_", " "), s.box.expand(4 * scale), "cv", conf=0.4))
        n += 1
    # vertical strips of icons: extend down the stripe of constant colour that holds them
    for i, s in enumerate(cs.strips):
        if s.orient != "col":
            continue
        box = s.box.expand(4 * scale)
        if rgb is not None:
            box = _extend_column(rgb, box, regions, size, scale)
        top = max((rg.bbox.y2 for rg in regions if rg.kind in ("ribbon", "toolbar", "menubar", "tab_strip", "titlebar") and rg.bbox.w > 0.4 * W), default=0.0)
        box = Box(box.x1, max(box.y1, top), box.x2, box.y2)
        if box.h < 40 * scale:
            continue
        regions.append(Region(f"s{i}", "sidebar", "tool strip", box, "cv", conf=0.5))
    if ink is not None and cv2 is not None:
        extra: List[Region] = []
        for r in regions:
            if r.kind in ("ribbon", "toolbar") and r.bbox.h >= 56 * scale and r.bbox.w >= 200 * scale:
                extra.extend(ribbon_groups(r, cs, ink, scale))
        regions.extend(extra)
    canvas = _free_area(regions, size)
    if canvas is not None:
        regions.append(Region("canvas0", "canvas", "work area", canvas, "cv", interactive=False, conf=0.4))
    return regions


def _extend_column(rgb: np.ndarray, box: Box, regions: Sequence[Region], size: Tuple[int, int], scale: float) -> Box:
    """A strip of icon buttons usually sits on a background stripe from the last toolbar down to the status bar: grow the box while the colour at its
    left edge stays the stripe's colour."""
    H, W, _c = rgb.shape
    x = int(max(0, min(W - 1, box.x1 + 1)))
    ref = rgb[int(min(H - 1, box.cy)), x].astype(np.int16)
    y1, y2 = int(box.y1), int(box.y2)
    lim_top = int(max((r.bbox.y2 for r in regions if r.kind in ("ribbon", "toolbar", "menubar", "tab_strip", "titlebar") and r.bbox.w > 0.4 * W), default=0))
    lim_bot = int(min((r.bbox.y1 for r in regions if r.kind == "statusbar"), default=H))
    while y1 - 1 > lim_top and np.abs(rgb[y1 - 1, x].astype(np.int16) - ref).max() <= 6:
        y1 -= 1
    while y2 + 1 < lim_bot and np.abs(rgb[y2 + 1, x].astype(np.int16) - ref).max() <= 6:
        y2 += 1
    xr = int(box.x2)
    while xr + 1 < W * 0.5 and np.abs(rgb[int(box.cy), min(W - 1, xr + 1)].astype(np.int16) - ref).max() <= 6:
        xr += 1
    return Box(box.x1, y1, max(box.x2, xr), y2)


def _free_area(regions: Sequence[Region], size: Tuple[int, int]) -> Optional[Box]:
    """Biggest axis-aligned rectangle between the control bands (top bands push the top edge down, bottom bands pull the bottom edge up, columns the sides)."""
    W, H = size
    top, bot, left, right = 0.0, float(H), 0.0, float(W)
    for r in regions:
        b = r.bbox
        if r.kind in ("menubar", "ribbon", "toolbar", "titlebar", "tab_strip") and b.cy < H * 0.4 and b.w > 0.4 * W:
            top = max(top, b.y2)
        elif r.kind == "statusbar" or (r.kind in ("toolbar",) and b.cy > H * 0.8 and b.w > 0.4 * W):
            bot = min(bot, b.y1)
        elif r.kind == "sidebar" and b.h > 0.3 * H:
            if b.cx < W / 2:
                left = max(left, b.x2)
            else:
                right = min(right, b.x1)
    c = Box(left, top, right, bot)
    return c if c.w > 0.3 * W and c.h > 0.25 * H else None


def merge_regions(*groups: Sequence[Region]) -> List[Region]:
    """Union of region lists by priority (first list wins on conflict): drops a region that mostly duplicates a higher-priority one but donates its caption."""
    out: List[Region] = []
    for g in groups:
        for r in g:
            dup = next((o for o in out if o.kind == r.kind and (o.bbox.iou(r.bbox) > 0.55 or r.bbox.overlap_frac(o.bbox) > 0.85)), None)
            if dup is not None:
                if (not dup.label or dup.label == dup.kind) and r.label and r.label != r.kind:
                    dup.label = r.label
                continue
            out.append(r)
    order = {"titlebar": 0, "menubar": 1, "ribbon": 2, "tab_strip": 3, "toolbar": 4, "sidebar": 5, "panel": 6, "list": 7, "canvas": 8, "statusbar": 9, "dialog": 10}
    out.sort(key=lambda r: (order.get(r.kind, 11), r.bbox.y1, r.bbox.x1))
    return out


def assign_elements(regions: List[Region], elements: List[UIElement]) -> None:
    """Each element goes to the SMALLEST region that holds >= 60% of it. Region.element_ids and element.region_id are filled; ids must already be set."""
    for r in regions:
        r.element_ids = []
    ranked = sorted(regions, key=lambda r: r.bbox.area)
    for e in elements:
        if e.region_id and any(r.id == e.region_id for r in regions):
            r = next(r for r in regions if r.id == e.region_id)
            r.element_ids.append(e.id)
            continue
        e.region_id = ""
        for r in ranked:
            if e.bbox.overlap_frac(r.bbox) >= 0.6:
                e.region_id = r.id
                r.element_ids.append(e.id)
                break


def nest_fragments(regions: List[Region], panel_regs: Sequence[Region]) -> None:
    """A toolbar/side-strip fragment found by shape analysis that lies inside an editor area belongs to that area: parent link + label 'Outliner toolbar'."""
    parents = {p.parent for p in panel_regs if p.parent}
    leaves = [p for p in panel_regs if p.id not in parents]
    for r in regions:
        if r.source == "uia" or r in panel_regs or r.kind not in ("toolbar", "sidebar", "list"):
            continue
        host = next((p for p in sorted(leaves, key=lambda p: p.bbox.area) if r.bbox.overlap_frac(p.bbox) >= 0.8 and r.bbox.area <= 0.8 * p.bbox.area), None)
        if host is None:
            continue
        r.parent = host.id
        if not r.label or r.label in (r.kind, "toolbar", "tool strip"):
            r.label = f"{host.label} {r.kind.replace('sidebar', 'strip')}".strip()


def attach_captions(regions: List[Region], elements: Sequence[UIElement]) -> None:
    """Regions still called by their bare kind take the first printed text near their top edge."""
    for r in regions:
        if r.label and r.label != r.kind:
            continue
        if r.kind in ("menubar", "statusbar", "canvas", "titlebar", "ribbon", "tab_strip"):
            continue
        heads = [e for e in elements if e.label and e.role in ("text", "tab", "unknown") and r.bbox.contains(e.bbox, slack=3)
                 and e.bbox.cy <= r.bbox.y1 + max(30.0, 0.12 * r.bbox.h)]
        if heads:
            heads.sort(key=lambda e: (e.bbox.y1, e.bbox.x1))
            r.label = heads[0].label
