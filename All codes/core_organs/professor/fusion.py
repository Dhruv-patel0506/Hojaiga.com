"""
professor.fusion -- one list of controls from many witnesses.

Witnesses and what each is good at:
  uia          exact box + exact name + shortcut + enabled state           (apps with an accessibility tree)
  ocr / text   exact printed words                                         (every app)
  cv           a shape that looks like a control (icon, boxed button...)   (every app, no name)
  icon_memory  a name from a previous look at the same pixels              (every app, once learned)
  vlm          a name read by the vision model from a contact sheet        (every app, slowest)
Rules: a UIA box wins over everything that overlaps it; a printed caption wins over a model's guess; a model's guess is flagged `unverified`
unless another witness agrees; duplicates are merged with containment-aware overlap (IoU alone misses an icon inside a larger button).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .candidates import Candidate
from .labeler import Label
from .schema import Box, Region, UIElement, fold, make_uid

_ROLE_BY_KIND = {"icon": "icon", "text": "text", "icon_label": "button", "rect_button": "button", "checkbox": "checkbox", "radio": "radio",
                 "field": "field", "caret": "button"}


def infer_role(kind: str, region_kind: str, label: str, has_dropdown: bool) -> str:
    role = _ROLE_BY_KIND.get(kind, "unknown")
    if role == "text":
        if region_kind == "menubar":
            return "menu_item"
        if region_kind in ("tab_strip",):
            return "tab"
        return "text"
    if role == "icon":
        return "dropdown" if has_dropdown else "button"
    if role == "button" and has_dropdown:
        return "dropdown"
    return role


def _covered(box: Box, others: Sequence[Box], thr: float = 0.55) -> bool:
    for o in others:
        if box.overlap_frac(o) >= thr or (o.overlap_frac(box) >= 0.8 and box.area <= 2.2 * o.area):
            return True
    return False


def fuse(uia: Sequence[UIElement], cands: Sequence[Candidate], labels: Sequence[Optional[Label]], regions: Sequence[Region],
         vlm_extra: Sequence[Tuple[str, Box]] = (), clip: Optional[Box] = None, max_elements: int = 1500) -> List[UIElement]:
    """Merge every witness into UIElements (ids assigned in reading order). `labels[i]` names `cands[i]` (None = unnamed)."""
    out: List[UIElement] = []
    taken: List[Box] = []

    def add(e: UIElement) -> None:
        out.append(e)
        taken.append(e.bbox)

    # 1. accessibility tree (authoritative where present)
    for u in uia:
        if clip is not None and u.bbox.overlap_frac(clip) < 0.5:
            continue
        add(u)

    region_kind_at = lambda b: next((r.kind for r in sorted(regions, key=lambda r: r.bbox.area) if b.overlap_frac(r.bbox) >= 0.6), "")   # noqa: E731

    # 2. vision candidates not already explained by a tree control
    for i, c in enumerate(cands):
        lab = labels[i] if i < len(labels) else None
        match = next((u for u in out if "uia" in u.sources and (c.box.overlap_frac(u.bbox) >= 0.6 or u.bbox.overlap_frac(c.box) >= 0.6)), None)
        if match is not None:
            for s in ("cv" if c.kind != "text" else "ocr",):
                if s not in match.sources:
                    match.sources.append(s)
            if not match.label and c.text:
                match.label, match.label_source = c.text, "ocr"
            if lab and not match.label:
                match.label, match.label_source = lab.text, lab.via
            continue
        rk = region_kind_at(c.box)
        label, lsrc, conf = "", "", c.score
        flags: List[str] = list(c.flags)
        sources = ["ocr"] if c.kind == "text" else ["cv"]
        hint = ""
        short = c.kind == "text" and 0 < len(c.text.strip()) <= 2 and not c.text.strip().isdigit()
        if short:
            hint = c.text.strip()
            flags.append("glyph-text")
        if short and lab is not None:
            label, lsrc = lab.text, lab.via
            conf = max(0.3, min(0.95, 0.35 * c.score + 0.65 * lab.conf))
            sources = ["cv", "ocr", "icon_memory"] if lab.via == "memory" else ["cv", "ocr", "vlm"]
            flags += lab.flags
            if lab.via.startswith("vlm") and lab.conf < 0.8:
                flags.append("unverified")
        elif short:                                              # a glyph read as a letter: only a single capital (B I U S) is plausibly its real caption
            label = c.text.strip() if (len(c.text.strip()) == 1 and c.text.strip().isupper()) else ""
            lsrc, conf = ("ocr" if label else ""), 0.4
            if not label:
                flags.append("unlabeled")
        elif c.text:
            label, lsrc, conf = c.text, "ocr", max(c.score, min(0.95, c.ocr_conf / 100.0 + 0.1))
            if c.kind == "icon_label":
                sources = ["cv", "ocr"]
        elif lab is not None:
            label, lsrc = lab.text, lab.via
            conf = max(0.3, min(0.95, 0.35 * c.score + 0.65 * lab.conf))
            sources = ["cv", "icon_memory"] if lab.via == "memory" else ["cv", "vlm"]
            flags += lab.flags
            if lab.via.startswith("vlm") and lab.conf < 0.8:
                flags.append("unverified")
        else:
            flags.append("unlabeled")
        role = infer_role(c.kind, rk, label, c.has_dropdown)
        if short and lab is not None:
            role = "button" if rk not in ("menubar", "tab_strip") else role
        add(UIElement(0, label, role, c.box, "", sources, round(conf, 3), lsrc, True, None, c.has_dropdown, "", hint, "", "", "", {}, flags))

    # 3. model-found boxes nobody else saw (deep mode recall tiles / coverage re-probes)
    for name, b in vlm_extra:
        if clip is not None and b.overlap_frac(clip) < 0.5:
            continue
        if _covered(b, taken, 0.5):
            for e in out:
                if (b.iou(e.bbox) > 0.4 or b.overlap_frac(e.bbox) > 0.7) and name and not e.label:
                    e.label, e.label_source = name, "vlm"
                    if "vlm" not in e.sources:
                        e.sources.append("vlm")
                    e.flags.append("unverified")
                    break
            continue
        add(UIElement(0, name, infer_role("icon", region_kind_at(b), name, False), b, "", ["vlm"], 0.4, "vlm", True, None, False, "", "", "", "", "", {},
                      ["unverified", "vlm-only"]))

    # 4. reading order + ids + stable uids
    out = _dedupe(out)
    out.sort(key=lambda e: (round(e.bbox.cy / 28.0), e.bbox.x1))
    out = out[:max_elements]
    for i, e in enumerate(out, 1):
        e.id = i
    return out


def _dedupe(els: List[UIElement]) -> List[UIElement]:
    """Drop near-identical boxes (keep the one with the better name / more sources)."""
    els = sorted(els, key=lambda e: (-len(e.sources), -(1 if e.label else 0), -e.conf))
    keep: List[UIElement] = []
    for e in els:
        dup = None
        for k in keep:
            if e.bbox.iou(k.bbox) > 0.6 or (e.bbox.overlap_frac(k.bbox) > 0.85 and k.bbox.overlap_frac(e.bbox) > 0.5):
                dup = k
                break
        if dup is None:
            keep.append(e)
        else:
            for s in e.sources:
                if s not in dup.sources:
                    dup.sources.append(s)
            if not dup.label and e.label:
                dup.label, dup.label_source = e.label, e.label_source
    return keep


def finalize_uids(elements: List[UIElement], regions: Sequence[Region]) -> None:
    by_id = {r.id: r for r in regions}
    for e in elements:
        r = by_id.get(e.region_id)
        e.uid = make_uid(e.label, r.kind if r else "", e.bbox)
