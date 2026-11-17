"""
professor.ribbon -- A RIBBON, RECOGNISED BY ITS SHAPE AND READ TAB BY TAB.

A ribbon is not a list of English tab names. It is a STRUCTURE: a strip of sibling tab items, and below it a band of named groups, each holding several controls; selecting another tab
replaces the groups. Document tabs (a tab per open file) look like a tab strip too, but nothing grouped sits under them and each carries its own Close button.

  detect(nodes)                 the best tab strip that has the ribbon shape (tab items under one parent, no per-tab close buttons, >= 2 named groups of controls right below it) -> Ribbon / None
  confirm(...)                  the shape is a HYPOTHESIS until one other tab has been selected and the group band changed (owned windows only)
  walk(...)                     every tab: select it, file each group's controls under  tab > group,  open every opener of the tab (split buttons, drop-downs, galleries, combo boxes) and read
                                its items - submenus too, to depth 3 (professor.menus) - then put the starting tab back. Items are never activated.
Each tab / opener is a history row ('ribbon'), so the ML models learn how ribbon toolkits behave. Nothing here names an application or a tab.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from . import menus as MN
from .harvest import Catalog
from .schema import fold

INTERACTIVE = {"button", "splitbutton", "combobox", "menuitem", "checkbox", "radiobutton", "edit", "listitem", "hyperlink", "spinner", "slider"}
CLOSE_RX = re.compile(r"(?i)^(close|close tab|x)$|close tab")
BACKSTAGE_RX = re.compile(r"(?i)^file( tab)?$")                  # the tab that opens a full-window menu (backstage) is a tab of the strip in shape but a page in behaviour: read by the reveal pass


@dataclass
class Ribbon:
    strip: int                              # index of the parent node of the tab items
    tabs: List[Any] = field(default_factory=list)
    groups: List[Any] = field(default_factory=list)
    band: Tuple[int, int, int, int] = (0, 0, 0, 0)       # where the group band sits (left, top, right, bottom)
    score: float = 0.0
    confirmed: Optional[bool] = None
    why: str = ""

    def tab_names(self) -> List[str]:
        return [t.name for t in self.tabs]

    def contains(self, n: Any) -> bool:
        """Is this node in the ribbon (its tab strip or its group band)?"""
        _l, t, _r, b = self.band
        y = (n.rect[1] + n.rect[3]) / 2
        return t - 4 <= y <= b + 30                                                   # vertical only: another tab may hold more groups, further to the right


def _owner_group(nodes: Sequence[Any], i: int) -> int:
    """The nearest named GroupControl above node i. Parent indices are only meaningful within ONE snapshot, so the walk is bounded and stops at an index that is out of range or seen twice
    (a filtered or concatenated node list must never loop)."""
    p = nodes[i].parent
    seen = {i}
    while 0 <= p < len(nodes) and p not in seen:
        seen.add(p)
        if nodes[p].ctype == "GroupControl" and nodes[p].name:
            return p
        p = nodes[p].parent
    return -1


def _children(nodes: Sequence[Any], i: int) -> List[int]:
    return [k for k, n in enumerate(nodes) if n.parent == i]


def detect(nodes: Sequence[Any]) -> Optional[Ribbon]:
    """The ribbon among the window's nodes, from structure alone (see the module doc). None when nothing has the shape. `nodes` must be ONE snapshot in its own order (parent indices)."""
    nodes = _one_snapshot(nodes)
    strips: Dict[int, List[int]] = {}
    for i, n in enumerate(nodes):
        if n.role == "tabitem" and n.name and n.rect[2] > n.rect[0]:
            strips.setdefault(n.parent, []).append(i)
    per_group: Dict[int, int] = {}
    for i, n in enumerate(nodes):
        if n.role in INTERACTIVE and n.name and not n.offscreen:
            g = _owner_group(nodes, i)
            if g >= 0:
                per_group[g] = per_group.get(g, 0) + 1
    best: Optional[Ribbon] = None
    for parent, idxs in strips.items():
        if len(idxs) < 3:
            continue
        tabs = [nodes[i] for i in idxs]
        closers = sum(1 for i in idxs for k in _children(nodes, i) if nodes[k].role == "button" and CLOSE_RX.search(nodes[k].name or ""))
        if closers >= max(1, len(idxs) // 2):
            continue                                                             # a tab per document: each one has its own Close button
        bottom = max(t.rect[3] for t in tabs)
        left = min(t.rect[0] for t in tabs)
        top_band, right = bottom - 12, max(t.rect[2] for t in tabs)
        grp = [k for k, c in per_group.items() if c >= 2 and nodes[k].rect[1] >= top_band and nodes[k].rect[1] <= bottom + 220 and nodes[k].rect[3] > nodes[k].rect[1]]
        grp = [k for k in grp if not any(per_group.get(j, 0) >= 2 and j != k and _is_ancestor(nodes, j, k) for j in grp)] or grp      # the innermost named groups (a tab's own wrapper group holds them)
        grp = [k for k in grp if not any(_is_ancestor(nodes, k, j) for j in grp if j != k)]
        if len(grp) < 2:
            continue
        gnodes = [nodes[k] for k in grp]
        band = (min([left] + [g.rect[0] for g in gnodes]), min(t.rect[1] for t in tabs), max([right] + [g.rect[2] for g in gnodes]), max(g.rect[3] for g in gnodes))
        score = len(grp) + 0.5 * len(idxs)
        if best is None or score > best.score:
            best = Ribbon(parent, tabs, gnodes, band, score, None, f"{len(idxs)} tabs over {len(grp)} groups of controls")
    return best


def _one_snapshot(nodes: Sequence[Any]) -> Sequence[Any]:
    """The leading part of a list that is a single snapshot: each node's idx equals its position (a list filtered or extended with pop-up trees is cut where that stops being true)."""
    for k, n in enumerate(nodes):
        if getattr(n, "idx", k) != k:
            return nodes[:k]
    return nodes


def _is_ancestor(nodes: Sequence[Any], a: int, b: int) -> bool:
    """Is node a an ancestor of node b?"""
    p = nodes[b].parent
    seen = {b}
    while 0 <= p < len(nodes) and p not in seen:
        if p == a:
            return True
        seen.add(p)
        p = nodes[p].parent
    return False


def group_controls(nodes: Sequence[Any], rib: Ribbon) -> Dict[str, List[Any]]:
    """{group name: [controls]} for the tab that is showing now (the main window's own snapshot only: pop-up trees have parent indices of their own)."""
    out: Dict[str, List[Any]] = {}
    nodes = _one_snapshot(nodes)
    for i, n in enumerate(nodes):
        if n.role not in INTERACTIVE or not n.name or n.offscreen or n.rect[2] <= n.rect[0]:
            continue
        g = _owner_group(nodes, i)
        if g < 0 or not rib.contains(nodes[g]):
            continue
        out.setdefault(nodes[g].name, []).append(n)
    return out


def _selected_tab(nodes: Sequence[Any], rib: Ribbon) -> str:
    names = {fold(t.name) for t in rib.tabs}
    for n in nodes:
        if n.role == "tabitem" and fold(n.name) in names and n.selected:
            return n.name
    return ""


def _find_tab(nodes: Sequence[Any], name: str) -> Any:
    return next((n for n in nodes if n.role == "tabitem" and fold(n.name) == fold(name) and not n.offscreen), None)


def _await_tab(all_nodes: Callable[[], List[Any]], rib: Ribbon, name: str, before: Set[str], wait_s: float = 3.0) -> List[Any]:
    """Poll until the tab reports selected and the group band has changed (or settled)."""
    end = time.time() + wait_s
    nodes: List[Any] = []
    last = None
    while time.time() < end:
        time.sleep(0.3)
        nodes = all_nodes()
        if fold(_selected_tab(nodes, rib)) != fold(name):
            continue
        cur = frozenset(group_controls(nodes, rib))
        if cur and (cur != frozenset(before) or last == cur):
            return nodes
        last = cur
    return nodes


LIST_ITEMS = 40                                                                    # more items than this under one opener: a list / gallery (read, not descended)


def walk(fx: Any, all_nodes: Callable[[], List[Any]], cat: Catalog, rib: Ribbon, budget_s: float = 240.0, per_tab_s: float = 40.0, history: Any = None, toolkit: str = "",
         on_items: Optional[Callable[[Any, List[Any]], None]] = None, max_depth: int = 3, max_items: int = 60, log: Callable[[str], None] = lambda s: None,
         done: Optional[Set[Tuple[str, str, str]]] = None, per_opener_s: float = 15.0) -> Dict[str, Any]:
    """Read the whole ribbon into `cat` (owned window: the effector refuses otherwise). Returns a report. `done`: openers (tab, group, opener - folded) an earlier run of the same
    build already read: counted, not opened again. A tab gets at least `per_opener_s` per opener it has (a fixed allowance per tab left whole groups unread)."""
    done = set(done or ())
    t0 = time.time()
    rep: Dict[str, Any] = {"detected": rib.why, "tabs": [], "groups": 0, "controls": 0, "openers": 0, "opened": 0, "items": 0, "submenus": 0, "confirmed": None, "failed": [], "skipped": [],
                           "seconds": 0.0, "read": [], "openers_found": 0, "opened_earlier": 0, "tabs_found": len(rib.tabs), "tabs_read": 0}
    if not fx.allowed:
        rep["failed"].append("dry run: " + fx.why_not())
        return rep
    have = {(tuple(v.path), fold(v.label)) for v in cat.verbs}
    nodes0 = all_nodes()
    start_tab = _selected_tab(nodes0, rib)
    groups_before = set(group_controls(nodes0, rib))
    seen_openers: Set[Tuple[str, str, str]] = set()
    for tab in rib.tabs:
        if time.time() - t0 > budget_s:
            rep["failed"].append("time budget reached")
            rep["skipped"].append({"path": tab.name, "why": "time budget reached before this tab (read by the next run of this build)"})
            continue
        if BACKSTAGE_RX.match(tab.name.strip()):
            rep["tabs_found"] -= 1
            rep["skipped"].append({"path": tab.name, "why": "opens the full-window file menu (backstage): read by the reveal pass, not as a ribbon tab"})
            continue
        t_tab = time.time()
        row: Dict[str, Any] = {"tab": tab.name, "groups": 0, "controls": 0, "openers": 0, "items": 0}
        live = _find_tab(all_nodes(), tab.name)
        if live is None:
            rep["failed"].append(f"{tab.name}: tab not in the tree")
            continue
        if fold(_selected_tab(all_nodes(), rib)) != fold(tab.name):
            ok, how = MN._expand(fx, live)
            if not ok:
                rep["failed"].append(f"{tab.name}: {how}")
                continue
            nodes = _await_tab(all_nodes, rib, tab.name, groups_before)
        else:
            nodes = all_nodes()
        gc = group_controls(nodes, rib)
        if rep["confirmed"] is None and fold(tab.name) != fold(start_tab):
            rep["confirmed"] = bool(set(gc) and set(gc) != groups_before)
        for gname, ctrls in gc.items():
            row["groups"] += 1
            for n in ctrls:
                if _file(cat, have, [tab.name, gname], n):
                    row["controls"] += 1
                row["seen"] = row.get("seen", 0) + 1
                rep["read"].append({"path": [tab.name, gname], "label": MN._item_label(n)[0], "role": n.role, "pats": list(n.pats or []), "aid": n.aid or "", "enabled": bool(n.enabled)})
        # the tab's openers: split buttons, drop-downs, galleries, combo boxes - opened, read, closed
        openers = [(gname, n) for gname, ctrls in gc.items() for n in ctrls if MN._is_opener(n) and n.role != "tabitem" and not MN.PRIVATE_RX.search(n.name or "")]
        uniq = {(fold(tab.name), fold(g), fold(o.name)) for g, o in openers}
        rep["openers_found"] += len(uniq - seen_openers)
        tab_allow = max(per_tab_s, per_opener_s * len(uniq - done))
        row["openers_found"] = len(uniq)
        for gname, op in openers:
            key = (fold(tab.name), fold(gname), fold(op.name))
            if key in seen_openers:
                continue
            seen_openers.add(key)
            if key in done:                                                     # read by an earlier run of this build: its items are in the catalog already
                rep["opened_earlier"] += 1
                continue
            if time.time() - t_tab > tab_allow or time.time() - t0 > budget_s:
                rep["skipped"].append({"path": f"{tab.name} > {gname} > {op.name}", "why": "time allowance used up (read by the next run of this build)"})
                continue
            row["openers"] += 1
            r = _open_and_read(fx, all_nodes, cat, have, op, [tab.name, gname], max_depth, max_items, on_items, rep)
            row["items"] += r
        rep["groups"] += row["groups"]
        rep["controls"] += row["controls"]
        rep["openers"] += row["openers"]
        rep["items"] += row["items"]
        row["seconds"] = round(time.time() - t_tab, 1)
        rep["tabs"].append(row)
        rep["tabs_read"] += 1
        rep["controls_seen"] = rep.get("controls_seen", 0) + row.get("seen", 0)
        log(f"ribbon tab '{tab.name}': {row['groups']} groups, {row.get('seen', 0)} controls seen ({row['controls']} new to the catalog), {row['openers']} openers ({row['items']} new items) in {row['seconds']}s")
        groups_before = set(gc)
        if history is not None:
            try:
                history.log(cat.app_key, "ribbon", "select", tab.name, "uia-select", "", f"{row['controls']} controls", "", f"{row['groups']} groups", "context_change", row["controls"] > 0, True,
                            tab.aid or "", {"items": row["items"]}, toolkit=toolkit, role="tab", safety="safe")
            except Exception:
                pass
    if start_tab:                                                                   # the person's starting tab is put back
        st = _find_tab(all_nodes(), start_tab)
        if st is not None and not st.selected:
            MN._expand(fx, st)
            time.sleep(0.5)
    cat.sources["ribbon"] = cat.sources.get("ribbon", 0) + rep["controls"] + rep["items"]
    cat.verbs.sort(key=lambda v: (v.path, v.label.lower()))
    rep["seconds"] = round(time.time() - t0, 1)
    return rep


def _open_and_read(fx: Any, all_nodes: Callable[[], List[Any]], cat: Catalog, have: Set[Tuple[Tuple[str, ...], str]], op: Any, path: List[str], max_depth: int, max_items: int,
                   on_items: Optional[Callable[[Any, List[Any]], None]], rep: Dict[str, Any]) -> int:
    """Open one opener of the ribbon, file its items under path + [opener], go down into submenus (menus._descend), close it. Returns the number of items filed."""
    base = {MN._ident(n) for n in all_nodes()}
    added = 0
    with fx.holding():
        ok, how = MN._expand(fx, op)
        _nodes, new = MN._await_items(all_nodes, base, wait_s=2.5)
        if ok and not new:
            ok, how = MN._expand(fx, op)
            _nodes, new = MN._await_items(all_nodes, base, wait_s=2.5)
        label = MN._item_label(op)[0]
        vpath = list(path) + [label]
        new = [n for n in new if fold(MN._item_label(n)[0]) != fold(label)]
        long_list = len(new) > LIST_ITEMS                                         # a font list / style gallery: a LIST to read, not a menu to descend into
        new = new[:max_items]
        for n in new:
            added += 1 if _file(cat, have, vpath, n) else 0
            rep["read"].append({"path": list(vpath), "label": MN._item_label(n)[0], "role": n.role, "pats": list(n.pats or []), "aid": n.aid or "", "enabled": bool(n.enabled)})
        if ok:
            rep["opened"] += 1
            rep.setdefault("opened_names", []).append(label)
        else:
            rep["failed"].append(f"{' > '.join(vpath)}: {how}")
        if on_items is not None and new:
            try:
                on_items(op, new)
            except Exception:
                pass
        if ok and new and max_depth > 1 and not long_list and any(MN._is_opener(n) for n in new):
            def reopen(op=op, base=base) -> None:
                MN._expand(fx, op)
                MN._await_items(all_nodes, base, wait_s=2.0)
            sub = {"skipped": rep["skipped"], "submenus": 0, "items": 0, "by_opener": {}, "failed": rep["failed"]}
            try:
                MN._descend(fx, all_nodes, cat, have, op, new, vpath, 2, max_depth, time.time() + 8.0, on_items, sub, reopen)
            except Exception as exc:
                rep["failed"].append(f"{' > '.join(vpath)}: submenu descent {type(exc).__name__}")
            rep["submenus"] += sub["submenus"]
            added += sub["items"]
        if ok:
            MN.collapse(op)
            time.sleep(0.2)
        try:
            fx.key("escape") if (ok and new and _still_open(all_nodes, base)) else None
        except Exception:
            pass
    return added


def _file(cat: Catalog, have: Set[Tuple[Tuple[str, ...], str]], vpath: List[str], n: Any) -> bool:
    """File a control read live from the ribbon. A control the catalog already knows (the vendor's manifest, an earlier scan) is not duplicated: it is MARKED as seen live ('ribbon' source,
    its live automation id, state and accelerator). Returns True only when the control was new."""
    if MN.add_item_verb(cat, have, vpath, n, source="ribbon"):
        return True
    label, chord = MN._item_label(n)
    lab = re.sub(r"(\.\.\.|…)\s*$", "", label).strip()
    key = (tuple(fold(p) for p in vpath), fold(lab))
    for v in cat.verbs:
        if (tuple(fold(p) for p in v.path), fold(v.label)) == key:
            if "ribbon" not in v.sources:
                v.sources.append("ribbon")
            v.enabled = bool(n.enabled)
            v.shortcut = v.shortcut or chord
            if n.aid and (not v.aid or v.aid.startswith("mso:")):
                v.aid = n.aid if not v.aid else v.aid
            break
    return False


def _still_open(all_nodes: Callable[[], List[Any]], base: Set[Tuple[str, str, str]]) -> bool:
    return sum(1 for n in all_nodes() if MN._ident(n) not in base and not n.offscreen and n.name and n.role in MN.ITEM_ROLES) > 2
