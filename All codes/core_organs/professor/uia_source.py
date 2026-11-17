"""
professor.uia_source -- the cheapest, most exact source of controls: the application's own accessibility tree (UI Automation), when it has one.

READ-ONLY: one cached-tree snapshot (`fast_uia.snapshot`), no Invoke / Expand / SetFocus / click, so nothing opens, nothing steals the foreground.
Output is the same shape as the vision sources (UIElement + Region in SCREEN pixels), so fusion treats all sources alike and the teacher never needs to know
which one found a button. Apps that expose nothing (Blender, games, canvas-drawn UIs, remote desktops) simply yield an empty result and the vision
tiers carry the scan -- reported honestly in ScreenModel.tiers_skipped, never faked.
"""

from __future__ import annotations

import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from .schema import Box, Region, UIElement, fold

for _p in (r"D:\new_automation", r"D:\new_automation\All codes"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_ROLE = {
    "button": "button", "splitbutton": "dropdown", "combobox": "dropdown", "menuitem": "menu_item", "menu": "menu", "menubar": "menu",
    "tabitem": "tab", "edit": "field", "checkbox": "checkbox", "radiobutton": "radio", "slider": "slider", "spinner": "field",
    "hyperlink": "link", "listitem": "list_item", "treeitem": "tree_item", "dataitem": "list_item", "headeritem": "button",
    "thumb": "button", "scrollbar": "scrollbar", "image": "image", "text": "text", "appbar": "toolbar",
}
_INTERACTIVE = {"button", "splitbutton", "combobox", "menuitem", "tabitem", "edit", "checkbox", "radiobutton", "slider", "spinner", "hyperlink",
                "listitem", "treeitem", "headeritem", "thumb", "scrollbar", "dataitem"}
_REGION_OF = {"menubar": "menubar", "toolbar": "toolbar", "statusbar": "statusbar", "titlebar": "titlebar", "tab": "tab_strip", "appbar": "toolbar"}
_ACCEL_IN_NAME = re.compile(r"\(\s*((?:Ctrl|Alt|Shift|Win)\s*\+\s*[\w\+\s\[\]\-,\./]+?)\s*\)\s*$", re.I)


def available() -> bool:
    try:
        from core_organs import fast_uia                           # noqa: F401
        return True
    except Exception:
        return False


def _clean_name(name: str) -> Tuple[str, str]:
    """('Paste (Ctrl+V)') -> ('Paste', 'Ctrl+V')"""
    name = (name or "").strip()
    m = _ACCEL_IN_NAME.search(name)
    if m:
        return name[:m.start()].strip(), re.sub(r"\s+", "", m.group(1))
    return name, ""


def snapshot_window(hwnd: int, budget_s: float = 8.0, win_box: Optional[Box] = None) -> Tuple[List[UIElement], List[Region], Dict[str, Any]]:
    """(elements, regions, meta) for a window. Elements are unfiltered by occlusion (UIA knows nothing about overlaps); fusion clips them to the picture."""
    meta: Dict[str, Any] = {"nodes": 0, "seconds": 0.0, "error": ""}
    t0 = time.time()
    try:
        from core_organs import fast_uia
    except Exception as exc:
        meta["error"] = f"fast_uia unavailable: {type(exc).__name__}"
        return [], [], meta
    nodes = fast_uia.snapshot(hwnd, max_nodes=8000, timeout_ms=int(budget_s * 1000))
    meta["seconds"] = round(time.time() - t0, 2)
    if not nodes:
        meta["error"] = "no accessibility tree (application draws its own UI, or it is still loading)"
        return [], [], meta
    meta["nodes"] = len(nodes)
    wb: Optional[Box] = win_box
    if wb is None and nodes[0].rect[2] > nodes[0].rect[0]:
        wb = Box(*nodes[0].rect)
    elements: List[UIElement] = []
    regions: List[Region] = []
    # ---- structural nodes -> a HIERARCHY of regions (the application's own containers, with the application's own names)
    interactive_below: Dict[int, int] = {}                           # how many interactive controls live under each node: a container worth naming holds several
    for n in nodes:
        if n.ctype.replace("Control", "").lower() in _INTERACTIVE and Box(*n.rect).valid and not n.offscreen:
            p = n.parent
            while p >= 0:
                interactive_below[p] = interactive_below.get(p, 0) + 1
                p = nodes[p].parent
    region_of_node: Dict[int, str] = {}
    ribbon_hint = lambda n: ("ribbon" in (n.cls + n.aid + n.name).lower())                     # noqa: E731 - generic class/id hint, not an app name
    seen_boxes: List[Tuple[Box, str]] = []
    for n in nodes:
        role = n.role
        b = Box(*n.rect)
        if not b.valid or b.w < 20 or b.h < 8 or n.offscreen:
            continue
        kind = _REGION_OF.get(role)
        many = interactive_below.get(n.idx, 0)
        nm = (n.name or "").strip()
        pretty_aid = re.sub(r"(?<=[a-z])(?=[A-Z])|[_\-.]+", " ", n.aid or "").strip() if not nm and len(n.aid or "") >= 4 and not (n.aid or "").isdigit() else ""
        if kind is None and role in ("group", "pane", "custom", "document", "window") and (nm or pretty_aid) and many >= 2 and n.parent >= 0:
            kind = "toolbar" if (role == "group" and many <= 14) or ribbon_hint(n) else "panel"
        if kind is None and role in ("list", "tree", "table", "datagrid", "dataitem") and many >= 3 and (nm or pretty_aid):
            kind = "list"
        if kind is None:
            continue
        if wb is not None and b.area >= 0.8 * wb.area:
            continue
        if any(b.iou(sb) > 0.92 and sk == kind for sb, sk in seen_boxes):
            continue
        seen_boxes.append((b, kind))
        rid = f"u{n.idx}"
        parent = ""
        q = n.parent
        while q >= 0:
            if q in region_of_node:
                parent = region_of_node[q]
                break
            q = nodes[q].parent
        regions.append(Region(rid, kind, nm or pretty_aid or kind, b, "uia", parent=parent, conf=0.9))
        region_of_node[n.idx] = rid
    # ---- interactive nodes -> elements
    for n in nodes:
        low = n.ctype.replace("Control", "").lower()
        b = Box(*n.rect)
        if low not in _INTERACTIVE or not b.valid or n.offscreen:
            continue
        if b.w < 6 or b.h < 6 or (wb is not None and b.area >= 0.5 * wb.area):
            continue
        name, accel_in_name = _clean_name(n.name)
        if not name and not n.aid and not n.pats:
            continue
        has_dd = low in ("splitbutton", "combobox") or ("expand" in n.pats and low in ("button", "menuitem", "tabitem") and n.expand_state in (0, 1))
        sel = n.selected if n.selected is not None else (True if n.toggle_state == 1 else (False if n.toggle_state == 0 else None))
        role = _ROLE.get(low, "button")
        if role == "button" and ("toggle" in n.pats):
            role = "toggle"
        # climb to the nearest region
        rid, p = "", n.parent
        while p >= 0:
            if p in region_of_node:
                rid = region_of_node[p]
                break
            p = nodes[p].parent
        elements.append(UIElement(0, name, role, b, rid, ["uia"], 0.95, "uia", bool(n.enabled), sel, has_dd, n.accel or accel_in_name,
                                  (n.help or "").strip(), n.aid or ""))
    return elements, regions, meta


_INTERACTIVE_ROLES = {"button", "splitbutton", "combobox", "menuitem", "tabitem", "edit", "checkbox", "radiobutton", "slider", "hyperlink", "listitem"}


def blind_recall(truth: List[UIElement], found: List[UIElement], min_overlap: float = 0.5) -> Dict[str, Any]:
    """How many of the accessibility tree's controls did a NON-UIA pipeline also find? The honest self-test of the vision tiers on any app that has a tree."""
    vis = [t for t in truth if t.enabled or True]
    hit, miss = 0, []
    for t in vis:
        if any(f.bbox.overlap_frac(t.bbox) >= min_overlap or t.bbox.overlap_frac(f.bbox) >= min_overlap for f in found):
            hit += 1
        else:
            miss.append(t)
    return {"truth": len(vis), "hit": hit, "recall": round(hit / len(vis), 3) if vis else None, "missed": [(m.label, m.bbox.to_list()) for m in miss[:40]]}
