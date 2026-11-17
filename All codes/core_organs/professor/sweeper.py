"""
professor.sweeper -- THE scan: one call turns a screen or window into a ScreenModel listing every control, where it is, what it is called, and how sure we are.

    scan(hwnd=..., mode="quick|standard|deep")          a window (plus its pop-ups) as the user sees it
    scan(image=PIL)                                      any picture (tests, screenshots, remote desktops)
    rescan(previous, hwnd=...)                           after the learner acted: only the CHANGED areas are analysed again

Pipeline (cheapest signal first; each tier reports itself in tiers_used / tiers_skipped -- nothing is faked):
  1 capture           mss of the window rectangle (+ owned pop-ups); PrintWindow when it is hidden
  2 uia               accessibility tree snapshot (exact boxes, names, shortcuts)                         [apps that have one]
  3 cv + ocr          every candidate shape and printed phrase (candidates.py)                            [always]
  4 regions           bands, ribbon groups, sidebars, canvas (regions.py)
  5 naming            icon memory first, then vision-model contact sheets for what is still unnamed       [standard, deep]
  6 recall tiles      the model reads each toolbar strip at native resolution and lists what it sees        [deep]  catches shapes CV missed
  7 fusion            one list, no duplicates, provenance on every control (fusion.py)
  8 coverage          pixel audit of what is still unexplained, re-probe until a round finds nothing         [standard (1 round), deep (3 rounds)]
  9 learn + link      UIA-named icons teach the icon memory; app knowledge adds shortcuts / what-it-opens
Budgets are hard caps: when time runs out the stage stops and says so.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from . import candidates as CV
from . import config as CFG
from . import coverage as COV
from . import fusion as FUS
from . import regions as RG
from . import uia_source
from .capture import Frame, changed_boxes, changed_fraction, frame_from_image, frame_hash, grab_box, grab_composite, grab_screen, grab_window, hash_distance, \
    monitor_at, pick_target_window, window_info, foreground_hwnd, virtual_screen
from .icon_memory import IconMemory, fingerprint, memory as _memory
from .labeler import Label, Labeler
from .schema import Box, Region, ScreenModel, UIElement, boxes_union, fold
from .vlm import VisionClient, client as _client

Progress = Optional[Callable[[str, Dict[str, Any]], None]]


@dataclass
class ScanOptions:
    mode: str = "standard"
    budget_s: float = 0.0                     # 0 = the mode's default
    use_uia: bool = True
    use_vlm: bool = True
    ocr: bool = True
    consistency: int = 1                      # 2 = every icon named twice from differently shuffled sheets (deep default)
    recall_tiles: bool = False
    exhaust_rounds: int = 1
    learn: bool = True
    save: bool = False
    knowledge: bool = True
    include_popups: bool = True
    panels: bool = True                       # split the work area into editor areas at full-span dividers (pixel layout tree; used where no tree exists)
    cancel: Optional[Callable[[], bool]] = None   # background upgrades stop naming as soon as a question is waiting
    ml_observe: bool = field(default_factory=lambda: os.environ.get("HOJAIGA_PROF_ML_OBSERVE", "0") == "1")   # a scan of a window WITH a tree labels the candidates -> trains professor.ml.CandidateModel
    ml_filter: bool = field(default_factory=lambda: os.environ.get("HOJAIGA_PROF_ML_FILTER", "0") == "1")     # where there is no tree: drop the candidates the model is nearly sure are noise
    yolo: bool = field(default_factory=lambda: os.environ.get("HOJAIGA_PROF_YOLO_DEFAULT", "0") == "1")   # optional icon-detector rung (professor.icon_detector): only where the tree is sparse

    @staticmethod
    def for_mode(mode: str) -> "ScanOptions":
        if mode == "quick":
            return ScanOptions("quick", CFG.BUDGETS.scan_quick_s, use_vlm=False, exhaust_rounds=0)
        if mode == "deep":
            return ScanOptions("deep", CFG.BUDGETS.scan_deep_s, consistency=2, recall_tiles=True, exhaust_rounds=3)
        return ScanOptions("standard", CFG.BUDGETS.scan_standard_s)


def _say(progress: Progress, stage: str, **info: Any) -> None:
    if progress:
        try:
            progress(stage, info)
        except Exception:
            pass


# ------------------------------------------------------------------------------------------------------ capture step
def popup_hwnds(hwnd: int) -> List[int]:
    try:
        from core_organs import background_window as bw
        return [h for h in bw.target_popups(hwnd, visible_only=True) if h != hwnd]
    except Exception:
        return []


def capture_target(hwnd: int = 0, image: Optional[Image.Image] = None, title_hint: str = "", include_popups: bool = True, isolated: bool = False,
                   origin: Tuple[int, int] = (0, 0), dpi_scale: float = 1.0) -> Tuple[Optional[Frame], int, List[int]]:
    """(frame, hwnd, popup hwnds). With an image: that picture. With a window: its rectangle united with the rectangles of its owned pop-ups (so an open
    drop-down menu, which is its own top-level window outside the frame, is part of what the Professor sees)."""
    if image is not None:
        return frame_from_image(image, origin=origin, dpi_scale=dpi_scale), hwnd, []
    if not hwnd:
        w = pick_target_window(title_hint)
        hwnd = w.hwnd if w else 0
    if not hwnd:
        return grab_screen(monitor_at(*(0, 0)).index), 0, []
    pops = popup_hwnds(hwnd) if include_popups else []
    if pops and not isolated:
        try:
            wb = window_info(hwnd).box
            if wb.overlap_frac(virtual_screen()) < 0.5:                       # parked off-screen: nothing to screen-grab; render each window from its own surface
                fr = grab_composite(hwnd, pops)
                if fr is not None:
                    return fr, hwnd, pops
        except Exception:
            pass
    if not pops or isolated:
        return grab_window(hwnd, isolated=isolated), hwnd, pops
    box = window_info(hwnd).box
    for p in pops:
        pb = window_info(p).box
        if pb.valid:
            box = box.union(pb)
    f = grab_box(box)
    if f is not None:
        f.kind, f.hwnd = "window", hwnd
    return f, hwnd, pops


# ----------------------------------------------------------------------------------------------------------- helpers
def _priority(i: int, c: CV.Candidate) -> Tuple[int, float]:
    return (0 if c.in_strip >= 0 else 1, -(c.box.w * c.box.h))


def _short_glyph_text(c: CV.Candidate) -> bool:
    t = (c.text or "").strip()
    return c.kind == "text" and 0 < len(t) <= 2 and not t.isdigit()


def _where_hint(box: Box, regs: Sequence[Region]) -> str:
    """'title bar' / 'ribbon group Font' / 'status bar' ...: the smallest region holding the control, in words the vision model can use."""
    best = None
    for r in regs:
        if box.overlap_frac(r.bbox) >= 0.6 and (best is None or r.bbox.area < best.bbox.area):
            best = r
    if best is None:
        return ""
    words = {"titlebar": "title bar", "menubar": "menu bar", "statusbar": "status bar", "tab_strip": "tab strip", "sidebar": "side tool strip"}
    lab = best.label if best.label and best.label != best.kind.replace("_", " ") and best.label != best.kind else ""
    kind = words.get(best.kind, best.kind.replace("_", " "))
    return f"{kind} ({lab.replace('ribbon > ', 'group ')})" if lab else kind


def _need_name(c: CV.Candidate, named_uia: Sequence[UIElement]) -> bool:
    if _short_glyph_text(c):                                             # 'B', 'x', 'o': a glyph the OCR read as a letter, not a caption -- name it by sight
        return not any(c.box.overlap_frac(u.bbox) >= 0.6 and u.label for u in named_uia)
    if c.text or c.kind in ("text", "checkbox", "radio", "field"):
        return False
    return not any(c.box.overlap_frac(u.bbox) >= 0.6 and u.label for u in named_uia)


def _tile_boxes(b: Box, max_w: int = 900, max_h: int = 360, overlap: int = 40) -> List[Box]:
    xs = [b.x1]
    while xs[-1] + max_w < b.x2:
        xs.append(xs[-1] + max_w - overlap)
    ys = [b.y1]
    while ys[-1] + max_h < b.y2:
        ys.append(ys[-1] + max_h - overlap)
    return [Box(x, y, min(b.x2, x + max_w), min(b.y2, y + max_h)) for y in ys for x in xs]


def recall_tiles(img: Image.Image, regs: Sequence[Region], vlm: VisionClient, budget_s: float, max_tiles: int = 10,
                 per_tile_items: int = 30) -> Tuple[List[Tuple[str, Box]], Dict[str, Any]]:
    """Deep mode: the model reads every control-bearing strip at (near) native resolution and lists what it sees; boxes arrive in picture pixels.
    Strong at things CV does not isolate (a button that is only a coloured background, tiny text-icons); slow, therefore capped and last."""
    t0 = time.time()
    found: List[Tuple[str, Box]] = []
    meta: Dict[str, Any] = {"tiles": 0, "items": 0, "seconds": 0.0, "stopped": ""}
    zones = [r for r in regs if r.kind in ("menubar", "ribbon", "toolbar", "tab_strip", "sidebar", "titlebar", "statusbar") and r.parent == ""]
    for r in zones:
        for tb in _tile_boxes(r.bbox):
            if meta["tiles"] >= max_tiles or time.time() - t0 > budget_s:
                meta["stopped"] = "budget" if time.time() - t0 > budget_s else "max_tiles"
                meta["seconds"] = round(time.time() - t0, 1)
                return found, meta
            crop = img.crop(tb.clip(img.width, img.height).ituple())
            if crop.width < 24 or crop.height < 12:
                continue
            items, res = vlm.detect(crop, "List every clickable control in this strip of a software window: buttons, icons, tabs, menu items, drop-downs.",
                                    max_items=per_tile_items, timeout=min(CFG.BUDGETS.vlm_call_s, max(30.0, budget_s - (time.time() - t0))), min_side=64)
            meta["tiles"] += 1
            if not res.ok:
                meta["stopped"] = res.error[:60]
                meta["seconds"] = round(time.time() - t0, 1)
                return found, meta
            for name, b in items:
                found.append((name, b.shift(tb.x1, tb.y1)))
            meta["items"] += len(items)
    meta["seconds"] = round(time.time() - t0, 1)
    return found, meta


# --------------------------------------------------------------------------------------------------------------- scan
def scan(*, hwnd: int = 0, image: Optional[Image.Image] = None, title_hint: str = "", mode: str = "standard", options: Optional[ScanOptions] = None,
         vlm: Optional[VisionClient] = None, memory: Optional[IconMemory] = None, progress: Progress = None, origin: Tuple[int, int] = (0, 0),
         isolated: bool = False, app_key: str = "", dpi_scale: float = 1.0) -> Tuple[ScreenModel, Optional[Frame]]:
    """Returns (ScreenModel, Frame). The model's boxes are SCREEN pixels (frame.origin + picture pixels)."""
    t_start = time.time()
    opt = options or ScanOptions.for_mode(mode)
    budget = opt.budget_s or {"quick": CFG.BUDGETS.scan_quick_s, "standard": CFG.BUDGETS.scan_standard_s, "deep": CFG.BUDGETS.scan_deep_s}.get(opt.mode, 120.0)
    deadline = t_start + budget
    left = lambda: max(0.0, deadline - time.time())                                          # noqa: E731
    sm = ScreenModel(mode=opt.mode)
    vlm = vlm or _client()
    mem = memory or (_memory() if (opt.learn or opt.use_vlm) else None)

    # ---- 1 capture
    _say(progress, "capture")
    frame, hwnd, pops = capture_target(hwnd, image, title_hint, opt.include_popups, isolated, origin, dpi_scale)
    if frame is None:
        sm.notes.append("capture failed: window not capturable")
        sm.tiers_skipped.append("capture:failed")
        return sm, None
    img = frame.image
    scale = max(1.0, frame.dpi_scale)
    info = window_info(hwnd) if hwnd else None
    sm.hwnd, sm.origin, sm.size, sm.frame_hash = hwnd, frame.origin, frame.size, frame.hash()
    if info:
        sm.window_title, sm.process = info.title, info.process
    try:
        from core_organs.atlas import common as AC
        sm.app_key = app_key or AC.app_key_of(sm.process.replace(".exe", "") or sm.window_title)
    except Exception:
        sm.app_key = app_key or fold(sm.process or sm.window_title).replace(" ", "_")
    sm.tiers_used.append("capture:" + (frame.via or frame.kind))
    sm.timings["capture"] = round(time.time() - t_start, 3)
    window_mode = frame.kind == "window"

    # ---- 2 accessibility tree
    uia_els: List[UIElement] = []
    uia_regs: List[Region] = []
    if opt.use_uia and hwnd:
        ts = time.time()
        wins = [hwnd] + pops
        for wh in wins:
            els, regs, meta = uia_source.snapshot_window(wh, min(CFG.BUDGETS.uia_s, max(1.0, left())), window_info(wh).box)
            uia_els += els
            uia_regs += [Region(f"{r.id}@{wh}", r.kind, r.label, r.bbox, r.source, conf=r.conf) for r in regs]
            for e in els:
                if e.region_id:
                    e.region_id = f"{e.region_id}@{wh}"
            if meta.get("error") and wh == hwnd:
                sm.tiers_skipped.append("uia:" + meta["error"][:80])
        if uia_els:
            sm.tiers_used.append(f"uia:{len(uia_els)}")
        sm.timings["uia"] = round(time.time() - ts, 2)
    elif opt.use_uia and not hwnd:
        sm.tiers_skipped.append("uia:no-window")
    # UIA is in screen space; the vision stages work in picture space
    ox, oy = frame.origin
    for e in uia_els:
        e.bbox = e.bbox.shift(-ox, -oy)
    for r in uia_regs:
        r.bbox = r.bbox.shift(-ox, -oy)
    uia_els = [e for e in uia_els if e.bbox.overlap_frac(Box(0, 0, img.width, img.height)) >= 0.5]

    # ---- 3 candidates (cv + ocr)
    _say(progress, "candidates")
    ts = time.time()
    cs = CV.detect(img, scale, ocr=opt.ocr, budget_s=max(3.0, min(CFG.BUDGETS.ocr_s + 10, left() * 0.4)))
    sm.tiers_used.append(f"cv:{len(cs.candidates)}")
    sm.tiers_skipped += cs.skipped
    if opt.yolo and len(uia_els) < 15:                                    # a tree names the controls itself; the detector is for UIA-blind applications
        try:
            from . import icon_detector as ID
            info = ID.augment(cs, img, scale, None, budget_s=left())
            if info.get("added"):
                sm.tiers_used.append(f"yolo:+{info['added']}")
            elif info.get("skipped"):
                sm.tiers_skipped.append("yolo:" + str(info["skipped"])[:80])
            sm.timings["yolo"] = info.get("seconds", 0.0)
        except Exception as exc:
            sm.tiers_skipped.append(f"yolo:{type(exc).__name__}")
    if opt.ml_observe or opt.ml_filter:
        try:
            from .ml import get_learner
            lrn = get_learner()
            ink_ml = CV.ink_mask(np.asarray(img.convert("L")), scale)
            if opt.ml_observe and len([e for e in uia_els if e.label]) >= 12:
                interactive_boxes = [e.bbox for e in uia_els if e.label and (getattr(e, "role", "") in {"button", "splitbutton", "combobox", "menuitem", "tabitem", "edit", "checkbox", "radiobutton", "slider", "spinner", "hyperlink", "listitem", "toggle"})]
                info_ml = lrn.observe_scan(cs.candidates, img.size, ink_ml, interactive_boxes or [e.bbox for e in uia_els if e.label], source=sm.app_key or sm.process)
                sm.tiers_used.append(f"ml:learned {info_ml.get('examples', 0)}")
            elif opt.ml_filter and len(uia_els) < 15:
                kept, dropped = lrn.candidate_filter(cs.candidates, img.size, ink_ml)
                if dropped:
                    cs.candidates = kept
                    sm.tiers_used.append(f"ml:-{dropped}")
        except Exception as exc:
            sm.tiers_skipped.append(f"ml:{type(exc).__name__}")
    sm.timings["candidates"] = round(time.time() - ts, 2)
    sm.timings.update({f"cv.{k}": v for k, v in cs.timings.items() if k != "total"})

    # ---- 4 regions
    ts = time.time()
    ink = CV.ink_mask(np.asarray(img.convert("L")), scale)
    cv_regs = RG.regions_from_cv(cs, img.size, scale, window_mode, ink, np.asarray(img.convert("RGB")))
    regs = RG.merge_regions(uia_regs, cv_regs)
    panel_regs: List[Region] = []
    if opt.panels:
        try:
            from . import panels as PN
            canvas = next((r for r in regs if r.kind == "canvas" and r.source != "uia"), None)
            if canvas is not None and not any(r.kind == "panel" and r.source == "uia" for r in regs):
                tops = [r.bbox.y2 for r in regs if r.kind in ("ribbon", "menubar", "tab_strip", "titlebar") and r.bbox.w > 0.6 * img.width]
                bots = [r.bbox.y1 for r in regs if r.kind == "statusbar" and r.bbox.w > 0.6 * img.width]
                area = Box(0, max(tops, default=0.0), img.width, min(bots, default=float(img.height)))     # everything between the top bars and the status bar
                root = PN.split_areas(np.asarray(img.convert("RGB")), area, scale)
                panel_regs = PN.to_regions(root)
                if len([r for r in panel_regs if not any(o.parent == r.id for o in panel_regs)]) >= 2:
                    regs = [r for r in regs if r is not canvas] + panel_regs
                    sm.tiers_used.append(f"panels:{len(panel_regs)}")
                else:
                    panel_regs = []
        except Exception as exc:
            sm.tiers_skipped.append("panels:" + type(exc).__name__)
    sm.timings["regions"] = round(time.time() - ts, 2)

    # ---- 5 naming
    labels: List[Optional[Label]] = [None] * len(cs.candidates)
    labeler = Labeler(vlm, mem) if (mem is not None or opt.use_vlm) else None
    if labeler is not None:
        labeler.cancel = opt.cancel
    named_uia = [e for e in uia_els if e.label]
    need = [i for i, c in enumerate(cs.candidates) if _need_name(c, named_uia)]
    need.sort(key=lambda i: _priority(i, cs.candidates[i]))
    if labeler is not None and need:
        _say(progress, "naming", unnamed=len(need))
        ts = time.time()
        got = labeler.from_memory(img, [cs.candidates[i].box for i in need])
        for i, g in zip(need, got):
            labels[i] = g
        mem_hits = sum(1 for g in got if g is not None)
        if mem_hits:
            sm.tiers_used.append(f"icon_memory:{mem_hits}")
        rest = [i for i in need if labels[i] is None]
        if opt.use_vlm and rest and left() > 8:
            if not vlm.available():
                sm.tiers_skipped.append("vlm:server-down")
            else:
                got2, meta = labeler.label_boxes(img, [cs.candidates[i].box for i in rest], max(6.0, left() * 0.55), opt.consistency,
                                                 hints=[_where_hint(cs.candidates[i].box, regs) for i in rest])
                for i, g in zip(rest, got2):
                    if g is not None:
                        labels[i] = g
                sm.tiers_used.append(f"vlm_sheets:{meta['named']}/{len(rest)}")
                if meta.get("skipped"):
                    sm.tiers_skipped.append(str(meta["skipped"]))
        elif not opt.use_vlm and rest:
            sm.tiers_skipped.append("vlm:disabled-in-mode")
        sm.timings["naming"] = round(time.time() - ts, 2)
    # decoration the memory already knows about is dropped
    keep_idx = [i for i, l in enumerate(labels) if not (l is not None and l.text.startswith("~"))]
    cands = [cs.candidates[i] for i in keep_idx]
    labels = [labels[i] for i in keep_idx]

    # ---- 6 recall tiles (deep)
    extra: List[Tuple[str, Box]] = []
    if opt.recall_tiles and opt.use_vlm and vlm.available() and left() > 40:
        _say(progress, "recall_tiles")
        extra, meta = recall_tiles(img, regs, vlm, left() * 0.45)
        sm.tiers_used.append(f"vlm_tiles:{meta['items']}")
        sm.timings["recall_tiles"] = meta["seconds"]
        if meta.get("stopped"):
            sm.tiers_skipped.append("vlm_tiles:" + str(meta["stopped"]))
    elif opt.recall_tiles:
        sm.tiers_skipped.append("vlm_tiles:" + ("server-down" if opt.use_vlm else "disabled"))

    # ---- 7 fusion
    ts = time.time()
    clip = Box(0, 0, img.width, img.height)
    elements = FUS.fuse(uia_els, cands, labels, regs, extra, clip, CFG.BUDGETS.max_elements)
    sm.timings["fusion"] = round(time.time() - ts, 2)

    # editor areas are classified BEFORE the audit: a sparse 3D viewport / document is a canvas (not measured), a crowded one is a panel (measured)
    if panel_regs:
        from . import panels as PN
        PN.apply(panel_regs, elements, ink, img.size, scale)

    # ---- 8 coverage
    if opt.exhaust_rounds > 0:
        _say(progress, "coverage")
        added, rep = COV.exhaust(img, elements, regs, scale, labeler if opt.use_vlm else (Labeler(vlm, mem) if mem is not None else None),
                                 max(4.0, left() * 0.8), rounds=opt.exhaust_rounds, ink=ink)
        elements = elements + added
        sm.coverage = COV.public(rep)
    else:
        rep = COV.audit(img, elements, regs, scale, ink)
        sm.coverage = COV.public(rep)
        sm.coverage["exhausted"] = None

    # ---- convention: the window buttons at the right end of a title bar (a generic OS convention, not per-application knowledge)
    try:
        from .priors import apply_window_buttons
        n_conv = apply_window_buttons(elements, regs, img.size)
        if n_conv:
            sm.notes.append(f"window-button convention applied to {n_conv} title-bar icons")
    except Exception:
        pass

    # ---- finalize ids, regions, coordinates
    elements.sort(key=lambda e: (round(e.bbox.cy / 28.0), e.bbox.x1))
    for i, e in enumerate(elements, 1):
        e.id = i
    if panel_regs:
        from . import panels as PN
        if opt.use_vlm and vlm.available() and left() > 30:
            named = PN.name_panels([r for r in panel_regs if r.label in ("panel", "list", "group", "work area") or r.kind == "canvas"], img, vlm, min(60.0, left() * 0.3))
            if named:
                sm.tiers_used.append(f"vlm_panels:{named}")
        RG.nest_fragments(regs, panel_regs)
    RG.assign_elements(regs, elements)
    RG.attach_captions(regs, elements)
    FUS.finalize_uids(elements, regs)
    # learn: UIA names teach the icon memory (free supervised data), so UIA-blind apps benefit later
    if opt.learn and mem is not None:
        learned = 0
        for e in elements:
            if "uia" in e.sources and e.label and ("cv" in e.sources or e.role in ("button", "toggle", "dropdown")) and e.bbox.w <= 90 and e.bbox.h <= 90:
                try:
                    mem.learn(fingerprint(img.crop(e.bbox.clip(img.width, img.height).ituple())), e.label, "uia", sm.app_key)
                    learned += 1
                except Exception:
                    pass
        for i, e in enumerate(elements):
            if e.label and e.label_source in ("vlm2",) and "ambiguous" not in e.flags:
                try:
                    mem.learn(fingerprint(img.crop(e.bbox.clip(img.width, img.height).ituple())), e.label, "vlm", sm.app_key)
                except Exception:
                    pass
        if learned:
            sm.notes.append(f"icon memory +{learned} from the accessibility tree")
    for e in elements:
        e.bbox = e.bbox.shift(ox, oy)
    for r in regs:
        r.bbox = r.bbox.shift(ox, oy)
    sm.elements, sm.regions = elements, regs
    sm.coverage["uncovered"] = [[int(b[0] + ox), int(b[1] + oy), int(b[2] + ox), int(b[3] + oy)] for b in sm.coverage.get("uncovered", [])]

    # ---- 8b native menus: a classic Win32 menu bar holds every item name + shortcut in memory, readable without opening anything
    if hwnd and opt.use_uia:
        try:
            from . import native_menu
            items = native_menu.harvest(hwnd)
            if items:
                m = native_menu.apply_menus(elements, items)
                sm.tiers_used.append(f"native_menu:{len(items)}items/{m}bar")
                sm.notes.append(f"native menu tree: {len(items)} items readable without opening any menu")
        except Exception as exc:
            sm.tiers_skipped.append("native_menu:" + type(exc).__name__)

    # ---- 9 knowledge link
    if opt.knowledge:
        try:
            from .knowledge import app_knowledge
            app_knowledge.enrich(sm)
        except Exception as exc:
            sm.tiers_skipped.append("knowledge:" + type(exc).__name__)
    sm.timings["total"] = round(time.time() - t_start, 2)
    if opt.save:
        save_scan(sm, img)
    return sm, frame


def save_scan(sm: ScreenModel, img: Optional[Image.Image] = None, name: str = "") -> Dict[str, str]:
    CFG.ensure_dirs()
    stem = name or f"{sm.app_key or 'screen'}_{int(sm.created)}"
    jp = os.path.join(CFG.SCAN_DIR, stem + ".json")
    with open(jp, "w", encoding="utf-8") as fh:
        fh.write(sm.to_json(indent=1))
    out = {"json": jp}
    if img is not None:
        from .viz import annotate
        pp = os.path.join(CFG.SCAN_DIR, stem + ".annotated.png")
        annotate(img, sm).save(pp)
        out["annotated"] = pp
    return out


# ------------------------------------------------------------------------------------------------------- re-scan
def rescan(previous: ScreenModel, previous_image: Image.Image, *, hwnd: int = 0, image: Optional[Image.Image] = None, mode: str = "standard",
           vlm: Optional[VisionClient] = None, memory: Optional[IconMemory] = None, progress: Progress = None,
           origin: Tuple[int, int] = (0, 0)) -> Tuple[ScreenModel, Optional[Frame], Dict[str, Any]]:
    """Look again after the learner acted. Unchanged picture -> the old model, instantly. Small changes (a menu opened, a dialog appeared, a field filled)
    -> only the changed rectangles are analysed and spliced into the old model. Large changes (a different screen) -> a full scan."""
    t0 = time.time()
    frame, hwnd2, pops = capture_target(hwnd or previous.hwnd, image, "", True, False, origin)
    if frame is None:
        return previous, None, {"path": "capture-failed"}
    if frame.size != previous_image.size or frame.origin != previous.origin:
        sm, fr = scan(hwnd=hwnd2, image=image, mode=mode, vlm=vlm, memory=memory, progress=progress, origin=origin, app_key=previous.app_key)
        return sm, fr, {"path": "full (geometry changed)", "seconds": round(time.time() - t0, 2)}
    frac = changed_fraction(previous_image, frame.image)
    if frac < 0.0015:
        return previous, frame, {"path": "unchanged", "changed_fraction": round(frac, 5), "seconds": round(time.time() - t0, 3)}
    boxes = changed_boxes(previous_image, frame.image, cell=32, thresh=6.0, pad=24)
    if frac > 0.4 or not boxes:
        sm, fr = scan(hwnd=hwnd2, image=image, mode=mode, vlm=vlm, memory=memory, progress=progress, origin=origin, app_key=previous.app_key)
        return sm, fr, {"path": "full (large change)", "changed_fraction": round(frac, 3), "seconds": round(time.time() - t0, 2)}
    # partial: re-detect inside the changed rectangles only
    vlm = vlm or _client()
    mem = memory or _memory()
    opt = ScanOptions.for_mode(mode)
    scale = max(1.0, frame.dpi_scale)
    ox, oy = frame.origin
    union = boxes_union(boxes)
    sm = ScreenModel(app_key=previous.app_key, window_title=previous.window_title, process=previous.process, hwnd=previous.hwnd, origin=previous.origin,
                     size=previous.size, frame_hash=frame.hash(), mode=mode, tiers_used=["partial_rescan"])
    keep = [e for e in previous.elements if not any(b.shift(ox, oy).overlap_frac(e.bbox) > 0.25 or e.bbox.overlap_frac(b.shift(ox, oy)) > 0.6 for b in boxes)]
    new_els: List[UIElement] = []
    new_regs: List[Region] = []
    labeler = Labeler(vlm, mem)
    for b in boxes:
        cs = CV.detect(frame.image, scale, ocr=True, budget_s=15.0, roi=b)
        labs: List[Optional[Label]] = [None] * len(cs.candidates)
        need = [i for i, c in enumerate(cs.candidates) if _need_name(c, [])]
        if need:
            got = labeler.from_memory(frame.image, [cs.candidates[i].box for i in need])
            for i, g in zip(need, got):
                labs[i] = g
            rest = [i for i in need if labs[i] is None]
            if opt.use_vlm and rest and vlm.available():
                got2, _m = labeler.label_boxes(frame.image, [cs.candidates[i].box for i in rest], 40.0, 1)
                for i, g in zip(rest, got2):
                    labs[i] = g
        ink = CV.ink_mask(np.asarray(frame.image.convert("L")), scale)
        rr = RG.regions_from_cv(cs, frame.image.size, scale, True, ink, np.asarray(frame.image.convert("RGB")))
        new_regs += [r for r in rr if r.kind not in ("canvas", "statusbar") and r.bbox.overlap_frac(b) > 0.5]
        els = FUS.fuse([], cs.candidates, labs, rr, (), b.expand(2))
        for e in els:
            e.bbox = e.bbox.shift(ox, oy)
        new_els += els
    for r in new_regs:
        r.bbox = r.bbox.shift(ox, oy)
    sm.regions = [r for r in previous.regions if not any(b.shift(ox, oy).overlap_frac(r.bbox) > 0.5 for b in boxes)] + new_regs
    # a changed rectangle that sits inside an old region re-uses that region
    allel = keep + new_els
    allel.sort(key=lambda e: (round(e.bbox.cy / 28.0), e.bbox.x1))
    for i, e in enumerate(allel, 1):
        e.id = i
        e.region_id = ""
    RG.assign_elements(sm.regions, allel)
    FUS.finalize_uids(allel, sm.regions)
    sm.elements = allel
    sm.coverage = dict(previous.coverage)
    sm.coverage["note"] = "partial rescan: coverage figures are from the full scan"
    try:
        from .knowledge import app_knowledge
        app_knowledge.enrich(sm)
    except Exception:
        pass
    sm.timings["total"] = round(time.time() - t0, 2)
    return sm, frame, {"path": "partial", "changed_fraction": round(frac, 3), "rects": len(boxes), "kept": len(keep), "new": len(new_els),
                       "seconds": round(time.time() - t0, 2)}
