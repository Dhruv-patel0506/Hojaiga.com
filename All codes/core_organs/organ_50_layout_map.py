"""
organ_50_layout_map.py — WHERE every control lives, section by section, as deep as the app allows.

Apps are made of sections: a menu bar, ribbon tabs, toolbars, a folder tree, a list or chat pane,
an editor, a canvas, a status bar. Knowing a control's NAME is not enough to operate the app; the
agent must know which section it belongs to and where in the window it sits (and keep knowing
that when the window is resized). This organ maps all of it with one generic method — no app
names, no per-app layouts:

  Phase 1  STATIC WALK (read-only, E0)
           Walk the whole UIA tree depth-first. Every named control and every container is
           recorded with role, name, AutomationId, class, which patterns it supports, absolute
           bbox AND window-relative fractions (0..1) so the position survives resizing.
           Containers open REGIONS: typed ones (menubar, toolbar, tabstrip, tree, list, grid,
           statusbar, titlebar, document, input) and untyped panes classified from geometry
           (sidebar / header / footer / content). A pane holding a list/document plus an input
           is tagged `conversation`. A big area with nothing UIA can see in it is `canvas`
           (honestly reported opaque: only the OCR/vision tiers can look inside).
  Phase 2  REVERSIBLE DEEPENING (E1 — every action has a verified unwind)
           * tab strips / ribbon tabs: select each tab, harvest what it reveals, restore the
             originally selected tab
           * folder trees: expand collapsed nodes, harvest children, collapse them again
           * scrollable lists: page through (virtualised items only exist when scrolled to),
             then restore the original scroll position
           Nothing is invoked; no command is run; destructive-looking names are never touched.
  Phase 3  PERSIST into the behavior model's `bm_layout` table, keyed by app + version hash,
           and answer `where()` queries ("where is 'Save'?") from it.

Time is adaptive (DiscoveryBudget): a small app finishes when discoveries flatten; a sprawling
one earns more time only while each unit of work keeps yielding new controls.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.organ_50_layout_map")

# control type -> region kind (generic UIA vocabulary, nothing app-specific)
REGION_BY_TYPE = {
    "MenuBarControl": "menubar", "ToolBarControl": "toolbar", "TabControl": "tabstrip",
    "TreeControl": "tree", "ListControl": "list", "DataGridControl": "grid", "TableControl": "grid",
    "StatusBarControl": "statusbar", "TitleBarControl": "titlebar", "DocumentControl": "document",
    "HeaderControl": "header", "MenuControl": "menu",
}
INTERACTIVE = {
    "ButtonControl", "MenuItemControl", "TabItemControl", "ListItemControl", "TreeItemControl",
    "CheckBoxControl", "RadioButtonControl", "ComboBoxControl", "HyperlinkControl", "EditControl",
    "SliderControl", "SplitButtonControl", "SpinnerControl", "DataItemControl", "ScrollBarControl",
    "ThumbControl", "ToggleButtonControl",
}
LABEL_TYPES = {"TextControl", "ImageControl", "HeaderItemControl"}
PATTERN_PROPS = (("invoke", "IsInvokePatternAvailableProperty"), ("toggle", "IsTogglePatternAvailableProperty"),
                 ("expand", "IsExpandCollapsePatternAvailableProperty"),
                 ("select", "IsSelectionItemPatternAvailableProperty"),
                 ("value", "IsValuePatternAvailableProperty"), ("scroll", "IsScrollPatternAvailableProperty"),
                 ("text", "IsTextPatternAvailableProperty"))
MAX_CONTROLS = 6000
AVOID_NAMES = ("delete", "remove", "close", "exit", "quit", "uninstall", "erase", "discard", "sign out", "log out")


def _rel(box: Tuple[int, int, int, int], win: Tuple[int, int, int, int]) -> Tuple[float, float, float, float]:
    w = max(win[2] - win[0], 1)
    h = max(win[3] - win[1], 1)
    return (round((box[0] - win[0]) / w, 4), round((box[1] - win[1]) / h, 4),
            round((box[2] - win[0]) / w, 4), round((box[3] - win[1]) / h, 4))


def _hash(*parts) -> str:
    return hashlib.md5("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


class LayoutMapper:
    def __init__(self, hwnd: int, app_name: str = "", budget=None):
        from core_organs import organ_48_app_behavior_model as bm
        import uiautomation as auto
        self.bm = bm
        self.auto = auto
        self.hwnd = hwnd
        self.app_name = app_name
        self.budget = budget or bm.DiscoveryBudget(base_s=12.0, extend_s=5.0, max_s=150.0, patience=8)
        self.controls: List[Dict[str, Any]] = []
        self.regions: Dict[str, Dict[str, Any]] = {}
        self._seen: set = set()
        self._root = None
        self._live: Dict[str, Any] = {}                 # ctrl_id -> snapshot Node / live control (for deepening)
        self.win = (0, 0, 1, 1)
        self.stats: Dict[str, Any] = {"deepen": {}, "skipped": []}

    # ------------------------------------------------------------------ geometry
    def _window_box(self, root) -> Tuple[int, int, int, int]:
        try:
            r = root.BoundingRectangle
            if r.right > r.left and r.bottom > r.top:
                return (r.left, r.top, r.right, r.bottom)
        except Exception:
            pass
        rr = wt.RECT()
        ctypes.windll.user32.GetWindowRect(self.hwnd, ctypes.byref(rr))
        return (rr.left, rr.top, rr.right, rr.bottom)

    def _geom_kind(self, box) -> str:
        """Classify an untyped pane from where it sits and how big it is."""
        rx0, ry0, rx1, ry1 = _rel(box, self.win)
        w, h = rx1 - rx0, ry1 - ry0
        if h < 0.16 and w > 0.5:
            return "header" if ry0 < 0.3 else "footer"
        if w < 0.4 and h > 0.5:
            return "sidebar_left" if rx0 < 0.3 else "sidebar_right"
        if w > 0.5 and h < 0.4 and ry0 > 0.6:
            return "footer"
        return "content"

    # ------------------------------------------------------------------ phase 1: static walk
    def _patterns(self, c, ctype: str) -> List[str]:
        if ctype not in INTERACTIVE and ctype not in ("PaneControl", "GroupControl", "CustomControl",
                                                      "ListControl", "TreeControl", "DocumentControl"):
            return []
        out = []
        for label, prop in PATTERN_PROPS:
            try:
                if c.GetPropertyValue(getattr(self.auto.PropertyId, prop)):
                    out.append(label)
            except Exception:
                continue
        return out

    def _open_region(self, parent_rid: str, kind: str, name: str, box, ctype: str, aid: str) -> str:
        rid = "rg_" + _hash(parent_rid, kind, name, aid, ctype)
        if rid not in self.regions:
            self.regions[rid] = {"region_id": rid, "parent": parent_rid, "kind": kind, "name": name,
                                 "automation_id": aid, "bbox": list(box), "n": 0, "via": "static",
                                 "opaque": False}
        return rid

    def _walk(self, root, via: str = "static", rid0: str = "rg_window", region_prefix: str = "",
              max_depth: int = 40) -> int:
        """Record every control under `root`. One bulk UIA call (fast_uia snapshot, ~10x faster than
        per-node reads); falls back to the per-node walk if the snapshot is unavailable.
        Returns the number of NEW controls recorded."""
        from core_organs import fast_uia
        nodes = None
        try:
            if root is self._root:
                nodes = fast_uia.snapshot(self.hwnd)
            else:
                nodes = fast_uia.snapshot_element(root.Element)
        except Exception:
            nodes = None
        if nodes:
            self.stats["fast_snapshot"] = True
            return self._walk_nodes(nodes, via, rid0, max_depth)
        self.stats["fast_snapshot"] = False
        return self._walk_slow(root, via, rid0, region_prefix, max_depth)

    def _walk_nodes(self, nodes, via: str, rid0: str, max_depth: int, rel_box=None) -> int:
        """`rel_box`: express positions relative to THIS box instead of the main window (used for popups:
        a flyout's items are located within the flyout, whatever screen position the popup guard gave it)."""
        new = 0
        if rid0 not in self.regions:
            self.regions[rid0] = {"region_id": rid0, "parent": "", "kind": "window",
                                  "name": self.app_name or "window", "automation_id": "",
                                  "bbox": list(self.win), "n": 0, "via": via, "opaque": False}
        # iterative DFS over the snapshot, carrying (node index, region id, path)
        stack = [(c, rid0, []) for c in reversed(nodes[0].children)]
        while stack:
            if len(self.controls) >= MAX_CONTROLS:
                self.stats["skipped"].append("control-cap")
                break
            if self.budget.elapsed() >= self.budget.max_s:
                self.stats["skipped"].append("hard-time-cap")
                break
            idx, rid, path = stack.pop()
            n = nodes[idx]
            if n.depth > max_depth:
                continue
            ctype, name, aid, box = n.ctype, n.name, n.aid, n.rect
            sized = box[2] > box[0] and box[3] > box[1]
            unlaid = (not sized) and bool(name) and bool(set(n.pats) & {"invoke", "toggle", "select", "expand"}) \
                and n.enabled and ctype in INTERACTIVE
            crid = rid
            kind = REGION_BY_TYPE.get(ctype)
            if kind is None and ctype in ("PaneControl", "GroupControl", "CustomControl") and sized \
                    and (name or aid) and self._area_frac(box) >= 0.02:
                kind = self._geom_kind(box)
            if kind is None and ctype == "EditControl" and sized and self._area_frac(box) >= 0.04:
                kind = "input" if (box[3] - box[1]) < 0.2 * (self.win[3] - self.win[1]) else "document"
            if kind and sized:
                crid = self._open_region(rid, kind, name or aid or kind, box, ctype, aid)
            label = name or aid
            record = (ctype in INTERACTIVE or (ctype in LABEL_TYPES and name)
                      or (kind is not None) or (ctype in ("PaneControl", "GroupControl") and name))
            if (record and sized) or unlaid:
                cid = "ctl_" + _hash(crid, ctype, name, aid, box if sized else ("nogeom", n.idx))
                if cid not in self._seen:
                    self._seen.add(cid)
                    new += 1
                    self.regions[crid]["n"] += 1
                    rel = _rel(box, rel_box or self.win) if sized else (0.0, 0.0, 0.0, 0.0)     # position unknown (not laid out)
                    pats = n.pats
                    self.controls.append({
                        "ctrl_id": cid, "region_id": crid, "role": ctype.replace("Control", "").lower(),
                        "name": name, "automation_id": aid, "cls": n.cls, "bbox": list(box),
                        "rel": list(rel), "center_rel": [round((rel[0] + rel[2]) / 2, 4),
                                                         round((rel[1] + rel[3]) / 2, 4)],
                        "enabled": n.enabled, "offscreen": n.offscreen,
                        "patterns": pats, "path": " > ".join(path + [label or ctype.replace("Control", "")])[:200],
                        "depth": n.depth, "via": via, "help": n.help, "accel": n.accel})
                    if ctype in ("TabItemControl", "TreeItemControl", "ListControl", "DataGridControl",
                                 "TreeControl", "DocumentControl", "PaneControl", "SplitButtonControl",
                                 "ComboBoxControl", "ButtonControl", "MenuItemControl") or "scroll" in pats:
                        self._live[cid] = n
            sub = path + ([label] if label and kind else [])
            for c in reversed(n.children):
                stack.append((c, crid, sub))
        return new

    def _walk_slow(self, root, via: str = "static", rid0: str = "rg_window", region_prefix: str = "",
                   max_depth: int = 40) -> int:
        """Per-node fallback: DFS the live tree under `root`."""
        new = 0
        if rid0 not in self.regions:
            self.regions[rid0] = {"region_id": rid0, "parent": "", "kind": "window",
                                  "name": self.app_name or "window", "automation_id": "",
                                  "bbox": list(self.win), "n": 0, "via": via, "opaque": False}
        stack: List[Tuple[Any, int, str, List[str]]] = [(root, 0, rid0, [])]
        while stack:
            if len(self.controls) >= MAX_CONTROLS:
                self.stats["skipped"].append("control-cap")
                break
            if self.budget.elapsed() >= self.budget.max_s:
                self.stats["skipped"].append("hard-time-cap")
                break
            c, depth, rid, path = stack.pop()
            try:
                children = c.GetChildren() if depth < max_depth else []
            except Exception:
                children = []
            for ch in reversed(children):
                try:
                    ctype = ch.ControlTypeName or ""
                    name = (ch.Name or "").strip()
                    aid = (getattr(ch, "AutomationId", "") or "").strip()
                    cls = (getattr(ch, "ClassName", "") or "")
                    r = ch.BoundingRectangle
                    box = (r.left, r.top, r.right, r.bottom)
                    offscreen = bool(getattr(ch, "IsOffscreen", False))
                    sized = box[2] > box[0] and box[3] > box[1]
                except Exception:
                    continue
                crid = rid
                kind = REGION_BY_TYPE.get(ctype)
                if kind is None and ctype in ("PaneControl", "GroupControl", "CustomControl") and sized \
                        and (name or aid) and self._area_frac(box) >= 0.02:
                    kind = self._geom_kind(box)
                if kind is None and ctype == "EditControl" and sized and self._area_frac(box) >= 0.04:
                    kind = "input" if (box[3] - box[1]) < 0.2 * (self.win[3] - self.win[1]) else "document"
                if kind and sized:
                    crid = self._open_region(rid, kind, name or aid or kind, box, ctype, aid)
                label = name or aid
                record = (ctype in INTERACTIVE or (ctype in LABEL_TYPES and name)
                          or (kind is not None) or (ctype in ("PaneControl", "GroupControl") and name))
                if record and sized:
                    cid = "ctl_" + _hash(crid, ctype, name, aid, box)
                    if cid not in self._seen:
                        self._seen.add(cid)
                        new += 1
                        self.regions[crid]["n"] += 1
                        rel = _rel(box, self.win)
                        pats = self._patterns(ch, ctype)
                        self.controls.append({
                            "ctrl_id": cid, "region_id": crid, "role": ctype.replace("Control", "").lower(),
                            "name": name, "automation_id": aid, "cls": cls, "bbox": list(box),
                            "rel": list(rel), "center_rel": [round((rel[0] + rel[2]) / 2, 4),
                                                             round((rel[1] + rel[3]) / 2, 4)],
                            "enabled": bool(getattr(ch, "IsEnabled", True)), "offscreen": offscreen,
                            "patterns": pats, "path": " > ".join(path + [label or ctype.replace("Control", "")])[:200],
                            "depth": depth + 1, "via": via})
                        if ctype in ("TabItemControl", "TreeItemControl", "ListControl", "DataGridControl",
                                     "TreeControl", "DocumentControl", "PaneControl") or "scroll" in pats:
                            self._live[cid] = ch
                stack.append((ch, depth + 1, crid, path + ([label] if label and kind else [])))
        return new

    def _area_frac(self, box) -> float:
        wa = max((self.win[2] - self.win[0]) * (self.win[3] - self.win[1]), 1)
        return max(box[2] - box[0], 0) * max(box[3] - box[1], 0) / wa

    def _classify_regions(self) -> None:
        """Post-pass: conversation panes, opaque canvases."""
        by_parent: Dict[str, List[Dict[str, Any]]] = {}
        for r in self.regions.values():
            by_parent.setdefault(r["parent"], []).append(r)
        for rid, r in self.regions.items():
            kids = by_parent.get(rid, [])
            kinds = {k["kind"] for k in kids}
            if r["kind"] in ("content", "sidebar_left", "sidebar_right", "pane") and kinds & {"list", "document"} \
                    and "input" in kinds:
                r["kind"] = "conversation"
            # command controls = things a user can operate; scrollbars/thumbs/rulers inside a drawing
            # surface do not make it operable through UIA
            cmd_roles = {t.replace("Control", "").lower() for t in INTERACTIVE} - {"scrollbar", "thumb"}
            command_inside = sum(1 for c in self.controls if c["region_id"] == rid and c["role"] in cmd_roles)
            area = self._area_frac(tuple(r["bbox"]))
            # a text surface UIA can READ (value/text pattern) is not opaque; a canvas it cannot is
            readable = any(c["region_id"] == rid and ("value" in c["patterns"] or "text" in c["patterns"])
                           for c in self.controls)
            if r["kind"] in ("content", "document") and area >= 0.15 and command_inside == 0 and not readable:
                r["opaque"] = True
                if r["kind"] == "content":
                    r["kind"] = "canvas"

    # ------------------------------------------------------------------ phase 2: reversible deepening
    def _settle(self, t: float = 0.25) -> None:
        time.sleep(t)

    @staticmethod
    def _live_ctrl(obj):
        """_live holds snapshot Nodes (fast path) or live Controls (slow path)."""
        return obj.ctrl if hasattr(obj, "ctrl") and not hasattr(obj, "GetChildren") else obj

    def _deepen_tabs(self, root) -> None:
        """Select each non-selected tab, harvest what it reveals, restore the original tab."""
        tabs: Dict[str, List[Tuple[str, Any]]] = {}
        for cid, ctl in list(self._live.items()):
            c = next((x for x in self.controls if x["ctrl_id"] == cid), None)
            if c and c["role"] == "tabitem" and "select" in c["patterns"]:
                tabs.setdefault(c["region_id"], []).append((cid, self._live_ctrl(ctl)))
        total = restored = 0
        self.budget.soft = max(self.budget.soft, self.budget.elapsed() + min(2.5 * sum(len(v) for v in tabs.values()), 60.0))
        for rid, items in tabs.items():
            selected = None
            for cid, ctl in items:
                try:
                    if ctl.GetSelectionItemPattern().IsSelected:
                        selected = ctl
                        break
                except Exception:
                    continue
            if selected is None or len(items) < 2:
                continue
            for cid, ctl in items[:24]:
                if self.budget.reason_to_stop() in ("hard-cap", "budget"):
                    self.stats["skipped"].append("tabs:budget")
                    break
                if ctl is selected:
                    continue
                meta = next(x for x in self.controls if x["ctrl_id"] == cid)
                if any(a in meta["name"].lower() for a in AVOID_NAMES):
                    continue
                try:
                    ctl.GetSelectionItemPattern().Select()
                    self._settle()
                    new = self._walk(root, via=f"tab:{meta['name'][:40]}")
                    total += 1
                    self.budget.credit(new)
                except Exception as exc:
                    logger.debug("tab deepen failed: %s", exc)
            try:                                                         # unwind: restore the original tab
                selected.GetSelectionItemPattern().Select()
                self._settle(0.2)
                restored += 1 if selected.GetSelectionItemPattern().IsSelected else 0
            except Exception:
                self.stats["skipped"].append("tabs:restore-failed")
        self.stats["deepen"]["tabs_visited"] = total
        self.stats["deepen"]["tab_strips_restored"] = restored

    def _deepen_trees(self, root) -> None:
        """Expand collapsed tree nodes (folders), harvest children, collapse them again."""
        done = 0
        for cid, ctl in list(self._live.items()):
            meta = next((x for x in self.controls if x["ctrl_id"] == cid), None)
            if not meta or meta["role"] != "treeitem" or "expand" not in meta["patterns"]:
                continue
            if self.budget.reason_to_stop() in ("hard-cap", "budget") or done >= 60:
                self.stats["skipped"].append("trees:budget")
                break
            if any(a in meta["name"].lower() for a in AVOID_NAMES):
                continue
            try:
                ctl = self._live_ctrl(ctl)
                pat = ctl.GetExpandCollapsePattern()
                if int(pat.ExpandCollapseState) != 0:                    # only collapsed nodes
                    continue
                pat.Expand()
                self._settle(0.2)
                new = self._walk(ctl, via=f"tree:{meta['name'][:40]}", rid0=meta["region_id"], max_depth=3)
                self.budget.credit(new)
                pat.Collapse()                                          # unwind
                done += 1
            except Exception as exc:
                logger.debug("tree deepen failed: %s", exc)
        self.stats["deepen"]["tree_nodes_expanded"] = done

    def _deepen_dropdowns(self, root) -> None:
        """Ribbon dropdowns, split buttons, combo boxes, galleries: anything that exposes ExpandCollapse
        and is currently collapsed. Expand it, harvest the popup it opens (one bulk snapshot), close it
        again. Menu-bar menus are the E0 crawler's job; nothing is invoked, only expanded."""
        from core_organs import fast_uia
        from core_organs import organ_48_app_behavior_model as bm
        done = opened = 0
        cands = []
        for cid, node in list(self._live.items()):
            if not isinstance(node, fast_uia.Node):
                continue
            if "expand" not in node.pats or node.expand_state != 0 or not node.enabled:
                continue
            if node.ctype not in ("SplitButtonControl", "ComboBoxControl", "ButtonControl", "MenuItemControl"):
                continue
            if node.ctype == "MenuItemControl":
                continue                                    # menu bar: E0 crawl
            if any(a in (node.name or "").lower() for a in AVOID_NAMES):
                continue
            cands.append((cid, node))
        # time scales with the observed frontier: ~1.3 s per candidate still to open (capped), not a fixed cap
        self.budget.soft = max(self.budget.soft, self.budget.elapsed() + min(1.3 * len(cands), 70.0))
        for cid, node in cands[:80]:
            if self.budget.reason_to_stop() in ("hard-cap", "budget"):
                self.stats["skipped"].append("dropdowns:budget")
                break
            meta = next((x for x in self.controls if x["ctrl_id"] == cid), None)
            if not meta:
                continue
            try:
                ctl = node.ctrl
                pat = ctl.GetExpandCollapsePattern()
                pat.Expand()
                opened += 1
                new = 0
                t_end = time.time() + 0.9
                seen_roots: set = set()
                while time.time() < t_end:
                    roots = bm._popup_roots(self.hwnd)
                    gained = 0
                    for r in roots:
                        try:
                            key = r.NativeWindowHandle or id(r)
                        except Exception:
                            key = id(r)
                        if key in seen_roots:
                            continue
                        snap = fast_uia.snapshot_element(r.Element)
                        if snap and len(snap) > 1:
                            seen_roots.add(key)
                            rid = self._open_region(meta["region_id"], "dropdown", meta["name"] or "dropdown",
                                                    meta["bbox"], "PaneControl", "")
                            sized = [n.rect for n in snap if n.rect[2] > n.rect[0] and n.rect[3] > n.rect[1]]
                            ref = (min(r[0] for r in sized), min(r[1] for r in sized),
                                   max(r[2] for r in sized), max(r[3] for r in sized)) if sized else None
                            gained += self._walk_nodes(snap, f"dropdown:{meta['name'][:30]}", rid, 12, rel_box=ref)
                    new += gained
                    if gained:
                        break
                    time.sleep(0.05)
                self.budget.credit(new)
                try:
                    pat.Collapse()                          # unwind
                except Exception:
                    pass
                if bm._open_popups(self.hwnd):
                    from core_organs import headless_input as hin
                    hin.post_key_combo(self.hwnd, "escape")
                done += 1
            except Exception as exc:
                logger.debug("dropdown deepen failed: %s", exc)
        self.stats["deepen"]["dropdowns_candidates"] = len(cands)
        self.stats["deepen"]["dropdowns_opened"] = opened

    def _deepen_scroll(self, root) -> None:
        """Page through scrollable containers (virtualised rows exist only when scrolled to)."""
        done = 0
        for cid, ctl in list(self._live.items()):
            meta = next((x for x in self.controls if x["ctrl_id"] == cid), None)
            if not meta or "scroll" not in meta["patterns"] or done >= 8:
                continue
            if self.budget.reason_to_stop() in ("hard-cap", "budget"):
                self.stats["skipped"].append("scroll:budget")
                break
            try:
                ctl = self._live_ctrl(ctl)
                sp = ctl.GetScrollPattern()
                if not sp.VerticallyScrollable:
                    continue
                orig = float(sp.VerticalScrollPercent)
                gained = 0
                for pct in (25.0, 50.0, 75.0, 100.0):
                    sp.SetScrollPercent(-1, pct)                         # -1 = leave horizontal unchanged
                    self._settle(0.15)
                    gained += self._walk(ctl, via=f"scroll:{meta['name'][:30]}", rid0=meta["region_id"], max_depth=6)
                sp.SetScrollPercent(-1, orig)                            # unwind
                self.budget.credit(gained)
                done += 1
            except Exception as exc:
                logger.debug("scroll deepen failed: %s", exc)
        self.stats["deepen"]["scrollables_paged"] = done

    # ------------------------------------------------------------------ orchestration
    def map(self, deepen: bool = True) -> Dict[str, Any]:
        t0 = time.time()
        try:
            from core_organs import fast_uia as _fu
            _fu.wait_ready(self.hwnd, timeout_s=10.0)         # never map a tree that is still populating
        except Exception:
            pass
        root = self.auto.ControlFromHandle(self.hwnd)
        if root is None:
            return {"error": "cannot attach to window"}
        self.win = self._window_box(root)
        self._root = root
        n_static = self._walk(root)
        self.budget.credit(n_static)
        self.stats["static_controls"] = n_static
        if deepen:
            for phase in (self._deepen_tabs, self._deepen_dropdowns, self._deepen_trees, self._deepen_scroll):
                try:
                    phase(root)
                except Exception as exc:
                    self.stats["skipped"].append(f"{phase.__name__}:{type(exc).__name__}")
        self._classify_regions()
        self.stats["elapsed_s"] = round(time.time() - t0, 2)
        self.stats["controls"] = len(self.controls)
        self.stats["regions"] = len(self.regions)
        # honest tier report: opaque regions can only be opened by OCR / vision
        opaque = [r for r in self.regions.values() if r["opaque"]]
        if opaque:
            self.stats["opaque_regions"] = [{"kind": r["kind"], "name": r["name"],
                                             "rel": list(_rel(tuple(r["bbox"]), self.win))} for r in opaque]
            self.stats["skipped"].append("canvas-interior:needs-ocr-or-vision")
        return self.summary()

    def summary(self) -> Dict[str, Any]:
        kinds: Dict[str, int] = {}
        for r in self.regions.values():
            kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        return {**self.stats, "region_kinds": kinds,
                "sections": [{"kind": r["kind"], "name": r["name"][:40], "controls": r["n"],
                              "rel": list(_rel(tuple(r["bbox"]), self.win)), "opaque": r["opaque"]}
                             for r in sorted(self.regions.values(), key=lambda x: (x["bbox"][1], x["bbox"][0]))
                             if r["kind"] != "window"][:60]}

    def structure_signature(self) -> str:
        return _hash(*sorted(f"{r['kind']}:{r['name']}" for r in self.regions.values()))


# ---------------------------------------------------------------------------
# Persistence + queries (kept next to the mapper; tables live in organ_48's DB)
# ---------------------------------------------------------------------------

LAYOUT_SCHEMA = """
CREATE TABLE IF NOT EXISTS bm_layout (
    ctrl_id TEXT, app_key TEXT, region_id TEXT, region_kind TEXT, region_name TEXT, role TEXT, name TEXT,
    automation_id TEXT, cls TEXT, x0 INTEGER, y0 INTEGER, x1 INTEGER, y1 INTEGER,
    rx0 REAL, ry0 REAL, rx1 REAL, ry1 REAL, enabled INTEGER, offscreen INTEGER, patterns TEXT,
    path TEXT, via TEXT, version_hash TEXT, ts REAL, PRIMARY KEY (app_key, ctrl_id));
CREATE INDEX IF NOT EXISTS bm_layout_name ON bm_layout(app_key, name);
CREATE TABLE IF NOT EXISTS bm_layout_regions (
    region_id TEXT, app_key TEXT, kind TEXT, name TEXT, rx0 REAL, ry0 REAL, rx1 REAL, ry1 REAL,
    n INTEGER, opaque INTEGER, version_hash TEXT, signature TEXT, ts REAL, PRIMARY KEY (app_key, region_id));
"""


def save_layout(model, app_key: str, mapper: LayoutMapper, version_hash: str = "") -> int:
    model._conn.executescript(LAYOUT_SCHEMA)
    prev = model._conn.execute("SELECT version_hash FROM bm_layout_regions WHERE app_key=? LIMIT 1", (app_key,)).fetchone()
    deepened = any(c.get("via", "static") != "static" for c in mapper.controls)
    if prev and prev["version_hash"] == version_hash and not deepened:
        pass        # same app version and a shallow (warm) pass: MERGE, never discard what deepening found earlier
    else:
        model._conn.execute("DELETE FROM bm_layout WHERE app_key=?", (app_key,))
        model._conn.execute("DELETE FROM bm_layout_regions WHERE app_key=?", (app_key,))
    now = time.time()
    rname = {r["region_id"]: r for r in mapper.regions.values()}
    sig = mapper.structure_signature()
    try:
        from core_organs.knowledge_store import redact as _redact
    except Exception:
        _redact = lambda t: t
    for c in mapper.controls:
        rg = rname.get(c["region_id"], {})
        c = dict(c, name=_redact(c["name"]), path=" > ".join(_redact(x.strip()) for x in (c["path"] or "").split(">")) if c.get("path") else c.get("path", ""))
        model._conn.execute(
            "INSERT OR REPLACE INTO bm_layout VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (c["ctrl_id"], app_key, c["region_id"], rg.get("kind", ""), _redact(rg.get("name", "")), c["role"], c["name"],
             c["automation_id"], c["cls"], *c["bbox"], *c["rel"], int(c["enabled"]), int(c["offscreen"]),
             ",".join(c["patterns"]), c["path"], c["via"], version_hash, now))
    for r in mapper.regions.values():
        rel = _rel(tuple(r["bbox"]), mapper.win)
        model._conn.execute("INSERT OR REPLACE INTO bm_layout_regions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (r["region_id"], app_key, r["kind"], r["name"], *rel, r["n"], int(r["opaque"]),
                             version_hash, sig, now))
    model._conn.commit()
    return len(mapper.controls)


def save_pixels(model, app_key: str, win: Tuple[int, int, int, int],
                elements: List[Dict[str, Any]], *, via: str = "ocr", version_hash: str = "") -> int:
    """Persist pixel-tier (OCR / vision) findings as ADDRESSABLE layout rows, keyed by a stable
    pixel id, so a tree-blind app can be acted on between scans without re-running the (slow) engine.
    Coordinates are stored BOTH absolute (as seen now) and window-relative (survives a move). These
    rows carry NO UIA patterns - they are pixel targets the actuator re-grounds before clicking.
    Replaces only the pixel rows of this app; structural UIA rows are never touched."""
    model._conn.executescript(LAYOUT_SCHEMA)
    model._conn.execute(
        "DELETE FROM bm_layout WHERE app_key=? AND region_kind='pixel'", (app_key,))
    now = time.time()
    n = 0
    for e in elements:
        name = (e.get("name") or "").strip()
        if not name:
            continue
        _b = [int(v) for v in (list(e.get("bbox") or [0, 0, 0, 0]) + [0, 0, 0, 0])[:4]]
        bbox: Tuple[int, int, int, int] = (_b[0], _b[1], _b[2], _b[3])
        rel = _rel(bbox, win) if win[2] > win[0] and win[3] > win[1] else (0.0, 0.0, 0.0, 0.0)
        cid = _hash("pixel", via, name.lower(), int(rel[0] * 100), int(rel[1] * 100))
        try:
            model._conn.execute(
                "INSERT OR REPLACE INTO bm_layout VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, app_key, "pixel", "pixel", via, e.get("role", "") or via, name[:200],
                 "", "", *bbox, *rel, 1, 0, "", "", via, version_hash, now))
            n += 1
        except Exception:  # noqa: BLE001
            continue
    model._conn.commit()
    return n


def pixel_rows(model, app_key: str, via: str = "") -> List[Dict[str, Any]]:
    """The persisted pixel targets of an app: name, role, window-relative rect, via (ocr/vision)."""
    try:
        model._conn.executescript(LAYOUT_SCHEMA)
        if via:
            rows = model._conn.execute(
                "SELECT name, role, rx0, ry0, rx1, ry1, x0, y0, x1, y1, via FROM bm_layout "
                "WHERE app_key=? AND region_kind='pixel' AND via=?", (app_key, via)).fetchall()
        else:
            rows = model._conn.execute(
                "SELECT name, role, rx0, ry0, rx1, ry1, x0, y0, x1, y1, via FROM bm_layout "
                "WHERE app_key=? AND region_kind='pixel'", (app_key,)).fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [{"name": r["name"], "role": r["role"], "rel": (r["rx0"], r["ry0"], r["rx1"], r["ry1"]),
             "bbox": (r["x0"], r["y0"], r["x1"], r["y1"]), "via": r["via"]} for r in rows]


def count_pixels(model, app_key: str) -> Dict[str, int]:
    out = {"ocr": 0, "vision": 0, "pixel": 0}
    try:
        model._conn.executescript(LAYOUT_SCHEMA)
        for r in model._conn.execute(
                "SELECT via, COUNT(*) n FROM bm_layout WHERE app_key=? AND region_kind='pixel' GROUP BY via",
                (app_key,)).fetchall():
            out[r["via"]] = r["n"]
            out["pixel"] += r["n"]
    except Exception:  # noqa: BLE001
        pass
    return out


def layout_cached(model, app_key: str, version_hash: str) -> Optional[Dict[str, Any]]:
    try:
        model._conn.executescript(LAYOUT_SCHEMA)
        row = model._conn.execute(
            "SELECT version_hash, signature, COUNT(*) n FROM bm_layout_regions WHERE app_key=? GROUP BY signature",
            (app_key,)).fetchone()
        if row and row["version_hash"] == version_hash and row["n"] > 0:
            return {"signature": row["signature"], "regions": row["n"]}
    except Exception:
        pass
    return None


def where(model, app_key: str, name: str, role: str = "") -> List[Dict[str, Any]]:
    """Where is the control called `name`? Returns region + window-relative position, best first
    (enabled, on-screen, interactive before label)."""
    try:
        model._conn.executescript(LAYOUT_SCHEMA)
        rows = model._conn.execute(
            "SELECT * FROM bm_layout WHERE app_key=? AND lower(name) LIKE ?", (app_key, f"%{name.lower().strip()}%")
        ).fetchall()
    except Exception:
        return []
    out = []
    for r in rows:
        if role and role not in (r["role"] or ""):
            continue
        exact = (r["name"] or "").lower().strip() == name.lower().strip()
        score = (2 if exact else 0) + (1 if r["enabled"] else 0) + (1 if not r["offscreen"] else 0) \
            + (1 if r["patterns"] else 0)
        out.append({"name": r["name"], "role": r["role"], "region": f"{r['region_kind']}:{r['region_name']}",
                    "center_rel": [round((r["rx0"] + r["rx1"]) / 2, 4), round((r["ry0"] + r["ry1"]) / 2, 4)],
                    "rel": [r["rx0"], r["ry0"], r["rx1"], r["ry1"]], "patterns": (r["patterns"] or "").split(","),
                    "path": r["path"], "via": r["via"], "score": score})
    return sorted(out, key=lambda x: -x["score"])


def map_layout(model, app_name: str, hwnd: int, *, deepen: bool = True, version_hash: str = "") -> Dict[str, Any]:
    """Map + persist in one call. Same code path for every app."""
    key = model_key(app_name)
    from core_organs import organ_48_app_behavior_model as _bm
    with _bm._bg(hwnd) as bg:                           # a minimized window has no layout: park it off-screen
        mapper = LayoutMapper(hwnd, app_name)
        summary = mapper.map(deepen=deepen)
        summary["window_mode"] = getattr(bg, "mode", "") or "visible"
    if "error" in summary:
        return summary
    saved = save_layout(model, key, mapper, version_hash)
    summary["saved"] = saved
    summary["signature"] = mapper.structure_signature()
    return summary


def model_key(app_name: str) -> str:
    from core_organs import organ_48_app_behavior_model as bm
    return bm._app_key(app_name)


# ---------------------------------------------------------------------------
# Scan <-> knowledge link: WHERE a control is  +  WHAT is known about it
# ---------------------------------------------------------------------------

LINK_SCHEMA = """
CREATE TABLE IF NOT EXISTS bm_links (
    app_key TEXT, cmd_id TEXT, ctrl_id TEXT, how TEXT, ts REAL, PRIMARY KEY (app_key, cmd_id, ctrl_id));
CREATE INDEX IF NOT EXISTS bm_links_ctrl ON bm_links(app_key, ctrl_id);
"""


def link_knowledge(model, app_key: str) -> Dict[str, int]:
    """Join the two halves of what we know about an app. Menu/E0/pack/probe commands carry meaning
    (risk, shortcut, trust, verified effect) but no position; layout controls carry position but no
    meaning. Link them by label so each side answers for the other. Returns link counts."""
    bm = __import__("core_organs.organ_48_app_behavior_model", fromlist=["x"])
    model._conn.executescript(LAYOUT_SCHEMA)
    model._conn.executescript(LINK_SCHEMA)
    model._conn.execute("DELETE FROM bm_links WHERE app_key=?", (app_key,))
    ctrls: Dict[str, List[Any]] = {}
    for r in model._conn.execute("SELECT ctrl_id, name, role FROM bm_layout WHERE app_key=? AND name<>''", (app_key,)):
        ctrls.setdefault(bm._norm(r["name"].replace("&", "")), []).append(r)
    linked_cmds = linked_ctrls = 0
    seen_ctrl: set = set()
    now = time.time()
    for c in model.commands(app_key, limit=20000):
        leaf = bm._norm((c["menu_path"] or "").split(">")[-1].replace("&", "")) or bm._norm(c["name"])
        hits = ctrls.get(leaf) or ctrls.get(bm._norm(c["name"]))
        if not hits:
            continue
        linked_cmds += 1
        for h in hits[:3]:
            model._conn.execute("INSERT OR REPLACE INTO bm_links VALUES (?,?,?,?,?)",
                                (app_key, c["cmd_id"], h["ctrl_id"], "label", now))
            seen_ctrl.add(h["ctrl_id"])
    linked_ctrls = len(seen_ctrl)
    model._conn.commit()
    return {"commands_linked": linked_cmds, "controls_linked": linked_ctrls}


def layout_to_commands(model, app_key: str) -> int:
    """Apps with ribbons / toolbars / calculator keypads have no classic menus, so the menu crawl yields
    nothing even though the layout holds hundreds of operable controls. Every named, enabled, operable
    control (it supports invoke / toggle / select / expand) becomes a COMMAND whose path is its section
    (and, for deepened content, the tab or dropdown that revealed it): 'Home > Font > Bold'. Entered as
    unverified `catalog` knowledge with a graded risk; nothing is executed."""
    bm = __import__("core_organs.organ_48_app_behavior_model", fromlist=["x"])
    model._conn.executescript(LAYOUT_SCHEMA)
    n = 0
    rows = model._conn.execute(
        "SELECT name, role, automation_id, patterns, path, via, region_kind, region_name FROM bm_layout "
        "WHERE app_key=? AND name<>'' AND enabled=1", (app_key,)).fetchall()
    for r in rows:
        pats = (r["patterns"] or "")
        if not any(p in pats for p in ("invoke", "toggle", "select", "expand")):
            continue
        if r["role"] in ("scrollbar", "thumb", "titlebar"):
            continue
        via = r["via"] or "static"
        prefix = via.split(":", 1)[1] if ":" in via else (r["region_name"] or r["region_kind"])
        path = f"{prefix} > {r['name']}"[:200]
        model.upsert_command(app_key, {"name": r["name"], "goal": r["name"], "verb": "invoke", "menu_path": path,
                                       "automation_id": r["automation_id"] or "",
                                       "risk": bm.classify_risk(r["name"], path),
                                       "post": [{"kind": "ui_changed"}]},
                             source="catalog", origin="layout")
        n += 1
    return n


def know(model, app_key: str, name: str, role: str = "") -> List[Dict[str, Any]]:
    """The combined answer for a label: position(s) AND knowledge (trust, risk, shortcut, effect)."""
    out = []
    for w in where(model, app_key, name, role)[:5]:
        row = {"name": w["name"], "role": w["role"], "region": w["region"], "center_rel": w["center_rel"],
               "via": w["via"], "knowledge": None}
        try:
            k = model._conn.execute(
                "SELECT c.name, c.menu_path, c.shortcut, c.risk, c.source, c.confidence, c.successes, c.opaque FROM bm_links l "
                "JOIN bm_layout y ON y.app_key=l.app_key AND y.ctrl_id=l.ctrl_id "
                "JOIN bm_commands c ON c.cmd_id=l.cmd_id "
                "WHERE l.app_key=? AND lower(y.name)=lower(?) ORDER BY c.confidence DESC LIMIT 1", (app_key, w["name"])).fetchone()
            if k:
                row["knowledge"] = {"command": k["name"], "menu_path": k["menu_path"], "shortcut": k["shortcut"],
                                    "risk": k["risk"], "trust": k["source"], "confidence": round(k["confidence"], 2),
                                    "verified_runs": k["successes"], "observable": not k["opaque"]}
        except Exception:
            pass
        out.append(row)
    return out
