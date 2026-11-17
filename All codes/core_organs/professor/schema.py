"""
professor.schema -- the data model every Professor stage speaks: Box, UIElement, Region, ScreenModel, PointCommand, LessonStep, Lesson.

All coordinates inside a ScreenModel are PHYSICAL SCREEN pixels (virtual-desktop space), so a box can be handed straight to the overlay.
Pure stdlib + dataclasses: importable anywhere, JSON round-trippable (a ScreenModel is stored next to its annotated picture).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ------------------------------------------------------------------------------------------------------------------ Box
@dataclass(frozen=True)
class Box:
    x1: float
    y1: float
    x2: float
    y2: float

    @staticmethod
    def of(t: Iterable[float]) -> "Box":
        a = [float(v) for v in t]
        return Box(a[0], a[1], a[2], a[3])

    @staticmethod
    def xywh(x: float, y: float, w: float, h: float) -> "Box":
        return Box(x, y, x + w, y + h)

    @property
    def w(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def h(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def center(self) -> Tuple[float, float]:
        return (self.cx, self.cy)

    @property
    def valid(self) -> bool:
        return self.x2 > self.x1 and self.y2 > self.y1

    def tuple(self) -> Tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)

    def ituple(self) -> Tuple[int, int, int, int]:
        return (int(round(self.x1)), int(round(self.y1)), int(round(self.x2)), int(round(self.y2)))

    def intersect(self, o: "Box") -> "Box":
        return Box(max(self.x1, o.x1), max(self.y1, o.y1), min(self.x2, o.x2), min(self.y2, o.y2))

    def union(self, o: "Box") -> "Box":
        return Box(min(self.x1, o.x1), min(self.y1, o.y1), max(self.x2, o.x2), max(self.y2, o.y2))

    def iou(self, o: "Box") -> float:
        inter = self.intersect(o).area
        if inter <= 0:
            return 0.0
        return inter / (self.area + o.area - inter)

    def overlap_frac(self, o: "Box") -> float:
        """Fraction of THIS box covered by `o` (containment-aware, unlike IoU)."""
        return self.intersect(o).area / self.area if self.area > 0 else 0.0

    def contains_point(self, x: float, y: float) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def contains(self, o: "Box", slack: float = 0.0) -> bool:
        return o.x1 >= self.x1 - slack and o.y1 >= self.y1 - slack and o.x2 <= self.x2 + slack and o.y2 <= self.y2 + slack

    def expand(self, px: float) -> "Box":
        return Box(self.x1 - px, self.y1 - px, self.x2 + px, self.y2 + px)

    def clip(self, w: float, h: float, x0: float = 0.0, y0: float = 0.0) -> "Box":
        return Box(max(x0, self.x1), max(y0, self.y1), min(w, self.x2), min(h, self.y2))

    def scale(self, sx: float, sy: Optional[float] = None) -> "Box":
        sy = sx if sy is None else sy
        return Box(self.x1 * sx, self.y1 * sy, self.x2 * sx, self.y2 * sy)

    def shift(self, dx: float, dy: float) -> "Box":
        return Box(self.x1 + dx, self.y1 + dy, self.x2 + dx, self.y2 + dy)

    def to_list(self) -> List[int]:
        return list(self.ituple())


def boxes_union(boxes: Iterable[Box]) -> Optional[Box]:
    out: Optional[Box] = None
    for b in boxes:
        out = b if out is None else out.union(b)
    return out


# ---------------------------------------------------------------------------------------------------- text normalisation
_WS = re.compile(r"\s+")
_NONWORD = re.compile(r"[^\w\s]+", re.UNICODE)


def fold(s: str) -> str:
    """Lower-case, punctuation-free, single-spaced: the key every label comparison uses."""
    return _WS.sub(" ", _NONWORD.sub(" ", (s or "").lower())).strip()


# ----------------------------------------------------------------------------------------------------------- UIElement
# role vocabulary the teacher and the overlay rely on
ROLES = ("button", "toggle", "dropdown", "menu", "menu_item", "tab", "field", "checkbox", "radio", "slider", "link", "list_item", "tree_item",
         "icon", "text", "image", "scrollbar", "window_control", "unknown")
SOURCES = ("uia", "ocr", "cv", "icon_memory", "vlm", "knowledge", "convention")


@dataclass
class UIElement:
    id: int                                   # position in ScreenModel.elements (1-based, reading order) -- what the teaching model cites as #id
    label: str                                # best human name ("" when nobody could name it)
    role: str
    bbox: Box
    region_id: str = ""
    sources: List[str] = field(default_factory=list)
    conf: float = 0.5
    label_source: str = ""                    # which source produced `label`
    enabled: bool = True
    selected: Optional[bool] = None
    has_dropdown: bool = False
    shortcut: str = ""
    hint: str = ""                            # tooltip / help text / what-it-does
    aid: str = ""                             # UIA automation id when known
    uid: str = ""                             # stable across scans: label + region kind + quantised position
    leads_to: str = ""                        # from app knowledge: "opens the Page Setup dialog"
    knowledge: Dict[str, Any] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)     # e.g. "unverified" (VLM only), "ambiguous" (two votes disagree), "unlabeled"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["bbox"] = self.bbox.to_list()
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "UIElement":
        d = dict(d)
        d["bbox"] = Box.of(d["bbox"])
        known = {k: d[k] for k in UIElement.__dataclass_fields__ if k in d}
        return UIElement(**known)

    def line(self, region_label: str = "") -> str:
        """One inventory line for the teaching model:  #12 [Home > Clipboard] button "Paste" (Ctrl+V) - opens ..."""
        bits = [f"#{self.id}"]
        if region_label:
            bits.append(f"[{region_label}]")
        bits.append(self.role)
        bits.append(f'"{self.label}"' if self.label else "(unnamed icon)")
        if self.shortcut:
            bits.append(f"({self.shortcut})")
        if self.has_dropdown:
            bits.append("+dropdown")
        if not self.enabled:
            bits.append("[disabled]")
        if self.leads_to:
            bits.append("- " + self.leads_to)
        elif self.hint:
            bits.append("- " + self.hint[:80])
        return " ".join(bits)


def make_uid(label: str, region_kind: str, box: Box, grid: int = 24) -> str:
    key = f"{fold(label)}|{region_kind}|{int(box.cx // grid)}|{int(box.cy // grid)}"
    return hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:10]


# ------------------------------------------------------------------------------------------------------------- Region
REGION_KINDS = ("titlebar", "menubar", "ribbon", "toolbar", "tab_strip", "sidebar", "panel", "canvas", "statusbar", "dialog", "list", "unknown")


@dataclass
class Region:
    id: str
    kind: str
    label: str
    bbox: Box
    source: str = "cv"                        # uia | cv | vlm | knowledge
    parent: str = ""
    element_ids: List[int] = field(default_factory=list)
    interactive: bool = True                  # False for canvases/documents: coverage is not measured there
    conf: float = 0.6

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["bbox"] = self.bbox.to_list()
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Region":
        d = dict(d)
        d["bbox"] = Box.of(d["bbox"])
        return Region(**{k: d[k] for k in Region.__dataclass_fields__ if k in d})


# ------------------------------------------------------------------------------------------------------- ScreenModel
@dataclass
class ScreenModel:
    """Everything the Professor knows about ONE look at the screen (or one window): regions, every control found, how it was found, how complete it is."""
    app_key: str = ""
    window_title: str = ""
    process: str = ""
    hwnd: int = 0
    origin: Tuple[int, int] = (0, 0)          # screen position of the captured picture's top-left
    size: Tuple[int, int] = (0, 0)            # captured picture size in pixels
    frame_hash: str = ""
    regions: List[Region] = field(default_factory=list)
    elements: List[UIElement] = field(default_factory=list)
    coverage: Dict[str, Any] = field(default_factory=dict)
    timings: Dict[str, float] = field(default_factory=dict)
    tiers_used: List[str] = field(default_factory=list)
    tiers_skipped: List[str] = field(default_factory=list)
    mode: str = "standard"
    created: float = field(default_factory=time.time)
    notes: List[str] = field(default_factory=list)

    # ---- lookups
    def element(self, eid: int) -> Optional[UIElement]:
        if 1 <= eid <= len(self.elements) and self.elements[eid - 1].id == eid:
            return self.elements[eid - 1]
        for e in self.elements:
            if e.id == eid:
                return e
        return None

    def region(self, rid: str) -> Optional[Region]:
        for r in self.regions:
            if r.id == rid:
                return r
        return None

    def region_label(self, e: UIElement) -> str:
        r = self.region(e.region_id)
        return r.label or r.kind if r else ""

    def region_path(self, rid: str) -> str:
        """'Properties > Transform': the chain of named containers from the outermost area down to this region (what an accessibility tree would call its path)."""
        names: List[str] = []
        seen = set()
        r = self.region(rid)
        while r is not None and r.id not in seen:
            seen.add(r.id)
            if r.label and r.label not in ("group", r.kind) and (not names or names[0] != r.label):
                names.insert(0, r.label)
            r = self.region(r.parent) if r.parent else None
        return " > ".join(names)

    def find(self, label: str, role: str = "", limit: int = 5) -> List[UIElement]:
        """Elements whose folded label equals / contains the query (exact first)."""
        q = fold(label)
        if not q:
            return []
        exact = [e for e in self.elements if fold(e.label) == q and (not role or e.role == role)]
        part = [e for e in self.elements if q in fold(e.label) and e not in exact and (not role or e.role == role)]
        return (exact + part)[:limit]

    def elements_in(self, box: Box, min_overlap: float = 0.5) -> List[UIElement]:
        return [e for e in self.elements if e.bbox.overlap_frac(box) >= min_overlap]

    def named(self) -> List[UIElement]:
        return [e for e in self.elements if e.label]

    def to_screen_point(self, x: float, y: float) -> Tuple[float, float]:
        """Picture pixel -> screen pixel (the picture was captured at origin; elements are already screen space)."""
        return (x + self.origin[0], y + self.origin[1])

    # ---- the text the teaching model reads
    def inventory_text(self, ids: Optional[Iterable[int]] = None, limit: int = 140) -> str:
        want = set(ids) if ids is not None else None
        lines: List[str] = []
        by_region: Dict[str, List[UIElement]] = {}
        for e in self.elements:
            if want is not None and e.id not in want:
                continue
            by_region.setdefault(e.region_id, []).append(e)
        n = 0
        for r in self.regions:
            els = by_region.get(r.id)
            if not els:
                continue
            path = self.region_path(r.id)
            lines.append(f"== {r.kind}: {path or r.label or r.kind} ==")
            for e in els:
                if n >= limit:
                    lines.append(f"... ({len(self.elements) - n} more controls not shown)")
                    return "\n".join(lines)
                lines.append(e.line())
                n += 1
        orphan = by_region.get("", [])
        for e in orphan:
            if n >= limit:
                break
            lines.append(e.line())
            n += 1
        return "\n".join(lines)

    def summary(self) -> Dict[str, Any]:
        by_src: Dict[str, int] = {}
        for e in self.elements:
            for s in e.sources:
                by_src[s] = by_src.get(s, 0) + 1
        return {"app": self.app_key, "title": self.window_title, "size": list(self.size), "elements": len(self.elements), "named": len(self.named()),
                "regions": [(r.kind, r.label, len(r.element_ids)) for r in self.regions], "by_source": by_src, "coverage": self.coverage,
                "tiers_used": self.tiers_used, "tiers_skipped": self.tiers_skipped, "mode": self.mode, "timings": self.timings}

    # ---- persistence
    def to_dict(self) -> Dict[str, Any]:
        return {"app_key": self.app_key, "window_title": self.window_title, "process": self.process, "hwnd": self.hwnd, "origin": list(self.origin),
                "size": list(self.size), "frame_hash": self.frame_hash, "regions": [r.to_dict() for r in self.regions],
                "elements": [e.to_dict() for e in self.elements], "coverage": self.coverage, "timings": self.timings, "tiers_used": self.tiers_used,
                "tiers_skipped": self.tiers_skipped, "mode": self.mode, "created": self.created, "notes": self.notes}

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ScreenModel":
        sm = ScreenModel(app_key=d.get("app_key", ""), window_title=d.get("window_title", ""), process=d.get("process", ""), hwnd=int(d.get("hwnd", 0)),
                         origin=tuple(d.get("origin", (0, 0))), size=tuple(d.get("size", (0, 0))), frame_hash=d.get("frame_hash", ""),  # type: ignore[arg-type]
                         coverage=d.get("coverage", {}), timings=d.get("timings", {}), tiers_used=d.get("tiers_used", []),
                         tiers_skipped=d.get("tiers_skipped", []), mode=d.get("mode", "standard"), created=d.get("created", time.time()), notes=d.get("notes", []))
        sm.regions = [Region.from_dict(r) for r in d.get("regions", [])]
        sm.elements = [UIElement.from_dict(e) for e in d.get("elements", [])]
        return sm

    @staticmethod
    def from_json(s: str) -> "ScreenModel":
        return ScreenModel.from_dict(json.loads(s))


# ------------------------------------------------------------------------------------------- pointing + lessons
ACTIONS = ("click", "double_click", "right_click", "type", "hover", "look", "scroll", "drag", "key", "wait")


@dataclass
class PointCommand:
    """One thing the overlay should show: where, how, and what to say next to it. `box` is in SCREEN pixels."""
    box: Optional[Box]
    label: str = ""
    kind: str = "highlight"                   # highlight | arrow | cursor | circle | underline
    action: str = "look"
    element_id: Optional[int] = None
    screen: int = 0
    dwell_s: float = 0.0                      # 0 = until the step ends

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["box"] = self.box.to_list() if self.box else None
        return d


@dataclass
class LessonStep:
    n: int
    say: str                                  # spoken narration for this step (written for the ear)
    action: str = "look"
    element_id: Optional[int] = None
    find: str = ""                            # description of a control that is not on screen yet (open its menu first)
    text: str = ""                            # what to type, if action == type
    keys: str = ""                            # shortcut, if action == key
    why: str = ""
    expect: str = ""                          # what should be visible after the learner acts (used to verify progress)
    box: Optional[Box] = None                 # resolved target in screen px (filled by the resolver)
    label: str = ""
    grounded_by: str = ""                     # scan | knowledge | vlm_locate | none
    status: str = "pending"                   # pending | shown | done | skipped | failed
    hotkey: str = ""                          # the shortcut THE APPLICATION itself prints for this control (resolved from the harvested catalog, never invented)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["box"] = self.box.to_list() if self.box else None
        return d


@dataclass
class Lesson:
    title: str
    speech: str                               # opening line (spoken before step 1)
    steps: List[LessonStep] = field(default_factory=list)
    mode: str = "answer"                      # answer (no steps) | lesson | clarify
    source: str = "llm"                       # llm | knowledge | fallback
    question: str = ""
    app_key: str = ""
    notes: List[str] = field(default_factory=list)
    principle: str = ""                       # the macro idea behind the whole task (taught BEFORE the clicks): first sentence of the opening line
    archetype: str = ""                       # kind of software the lesson was framed for (spatial_3d, temporal_media, ...)

    def to_dict(self) -> Dict[str, Any]:
        return {"title": self.title, "speech": self.speech, "mode": self.mode, "source": self.source, "question": self.question,
                "app_key": self.app_key, "notes": self.notes, "principle": self.principle, "archetype": self.archetype, "steps": [s.to_dict() for s in self.steps]}
