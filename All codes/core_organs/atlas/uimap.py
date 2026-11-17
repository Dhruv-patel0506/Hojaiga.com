"""
atlas.uimap -- the CARTOGRAPHER: a complete, structured map of an application's command surface.

What the flat explorer lacks and this adds: STRUCTURE and DESTINATIONS.

    surface (ribbon tab | menu bar | backstage/File | quick-access bar)
      -> group            ("Images", "Clipboard")
        -> control        ("Pictures": split button, shortcut, automation id, enabled, toggle state)
          -> leads_to     menu | gallery | dialog | pane | inline | none   (+ the ITEMS inside, recursively, + the dialog schema)

How it works (generic, no per-application knowledge):
  * tab strips are found structurally (a Tab control with >= 2 selectable TabItems); the ribbon region is "what lives under the strip's parent, below the strip"
  * groups are the innermost NAMED Group/ToolBar ancestor of a control
  * every control that can EXPAND (UIA ExpandCollapse: it runs no application code) is expanded, its items are read as the DIFFERENCE of the UI tree before/after
    (Office-style popups keep their items in the main tree, WinForms/WPF in a popup window), submenus are followed two levels deep, and the control is COLLAPSED
    again; an unwind that does not return to the starting tree is counted, never hidden
  * an item or control that promises a dialog (ellipsis) is OPENED through the explorer's trigger ladder and its schema read (master/detail pages included)
  * the File/backstage view is entered, every page is read, and it is left again
  * nothing is ever COMMITTED: plain commands are not invoked here (their effect is the job of the effect prober); destructive words are never touched

Output: one JSON document (data/atlas/uimap/<app>.json), evidenced claims (ui.ribbon.tab / ui.ribbon.group / ui.path), and commands with full ribbon paths in the
engine database ("Insert > Images > Pictures > This Device...") so the planner and the teacher can route through them.
"""
from __future__ import annotations

import collections
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from . import common as C
from . import explorer as X

ITEM_TYPES = {"MenuItemControl": "menuitem", "ListItemControl": "item", "ButtonControl": "button", "CheckBoxControl": "checkbox", "RadioButtonControl": "radio",
              "SplitButtonControl": "split", "TreeItemControl": "treeitem", "HyperlinkControl": "link", "ComboBoxControl": "combobox", "EditControl": "edit",
              "SpinnerControl": "spinner", "SliderControl": "slider", "TabItemControl": "tab"}
CONTROL_TYPES = {"ButtonControl": "button", "SplitButtonControl": "split", "MenuItemControl": "dropdown", "ComboBoxControl": "combobox", "CheckBoxControl": "checkbox",
                 "RadioButtonControl": "radio", "EditControl": "edit", "SpinnerControl": "spinner", "SliderControl": "slider", "HyperlinkControl": "link", "ListItemControl": "item",
                 "ListControl": "gallery", "TextControl": None}
COMPOSITE_PARENTS = {"SplitButtonControl", "ComboBoxControl", "SpinnerControl", "SliderControl", "ScrollBarControl", "EditControl"}
GROUP_TYPES = {"GroupControl", "ToolBarControl"}
MAX_DEPTH = 2
MAX_ITEMS = 120
RUNTIME_RX = re.compile(r"\b(from beginning|from current slide|present(ing)?|play|start|run|preview|rehearse|launch|go live|broadcast|stream|live|connect|join|begin|resume|record(ing)?)\b", re.I)
PRIVATE_LIST_RX = re.compile(r"\b(recent|recently|favou?rites?|pinned|shared with me|history|frequent|suggested|jump ?list|mru|open recent|downloads?)\b", re.I)
GENERIC_NAMES = {"", "ribbon", "lower ribbon", "ribbon tabs", "quick access toolbar", "more options", "open", "close", "minimize", "maximize", "restore"}


def _f(s: str) -> str:
    return C.fold(s)


def _nid(n) -> Tuple[str, str, str]:
    return (n.ctype, n.name, n.aid)


def subtree(nodes, idx: int) -> List[Any]:
    """Nodes below `idx` in document order (the snapshot is a DFS pre-order list, so the subtree is the run of deeper nodes right after it)."""
    out = []
    d = nodes[idx].depth
    for n in nodes[idx + 1:]:
        if n.depth <= d:
            break
        out.append(n)
    return out


def ancestors(nodes, n) -> List[Any]:
    out, i = [], n.parent
    while i is not None and i >= 0 and i < len(nodes):
        out.append(nodes[i])
        i = nodes[i].parent
    return out


ACCOUNT_RX = re.compile(r"^(onedrive|sharepoint|dropbox|google drive|box|icloud)\s*[-:–]\s*.+$", re.I)
EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def clean_name(name: str) -> str:
    """Account / organisation / e-mail details inside a label are the user's identity, not the program's structure: 'OneDrive - <organisation>' -> 'OneDrive (account)'."""
    m = ACCOUNT_RX.match(name or "")
    if m:
        return f"{m.group(1)} (account)"
    return EMAIL_RX.sub("<email>", name or "")


def private_context(nodes, n) -> bool:
    """True when `n` sits inside a list/group that holds the USER'S OWN items (recent files, favourites, history): such names are personal data, never recorded."""
    for a in ancestors(nodes, n):
        if a.ctype in ("ListControl", "GroupControl", "PaneControl", "TreeControl") and a.name and PRIVATE_LIST_RX.search(a.name):
            return True
    return False


def kind_of(n) -> str:
    base = ITEM_TYPES.get(n.ctype) or CONTROL_TYPES.get(n.ctype) or "control"
    if base == "button" and "toggle" in n.pats:
        return "toggle"
    if base == "menuitem" and "expand" in n.pats:
        return "dropdown"
    return base


class Sentinel:
    """Watches the mapped program for a window that TAKES OVER the user's screen (a slide show, a full-screen player, a recorder bar): any window of the
    program's process that is visible, on a real monitor and large (>= 35 % of it) is an intrusion. It is ended at once (Escape, then WM_CLOSE) and logged with the
    action that was running, so the culprit is known and can be named 'not-opened' next time. Runs on its own thread for the whole walk."""

    def __init__(self, carto: "Cartographer", every_s: float = 0.12):
        import threading
        self.c = carto
        self.every = every_s
        self.stop = threading.Event()
        self.incidents: List[Dict[str, Any]] = []
        self.th = threading.Thread(target=self.loop, daemon=True, name="atlas-sentinel")

    def start(self) -> "Sentinel":
        self.th.start()
        return self

    def halt(self) -> None:
        self.stop.set()

    def loop(self) -> None:
        from core_organs import background_window as bw
        from core_organs import headless_input as hin
        closed_at: Dict[int, float] = {}
        while not self.stop.is_set():
            try:
                top = self.c.ex.hwnd
                if not X._u32.IsWindow(top):
                    return
                screens = bw._screens()
                for w in hin.process_windows(top, include_hidden=False):
                    if w == top or not X._u32.IsWindowVisible(w) or X._u32.IsIconic(w):
                        continue
                    if bw._owner_chain_has(w, top):
                        continue                                                    # a dialog / menu owned by the program's own window: the popup guard and the explorer handle those
                    l, t, r, b = bw._rect(w)
                    if not bw._on_real_screen((l, t, r, b)):
                        continue
                    area = max(0, (min(r, screens[0][2]) - max(l, screens[0][0])) * (min(b, screens[0][3]) - max(t, screens[0][1])))
                    mon = max(1, (screens[0][2] - screens[0][0]) * (screens[0][3] - screens[0][1]))
                    if area / mon < 0.35:
                        continue
                    now = time.time()
                    if now - closed_at.get(w, 0) < 0.8:
                        continue
                    closed_at[w] = now
                    cls = X.Explorer._class_of(w)
                    same_frame = cls == X.Explorer._class_of(top)
                    self.incidents.append({"class": cls, "rect": [l, t, r, b], "during": self.c.last_action, "at_s": round(now - self.c.t0, 1), "handled": "minimized" if same_frame else "ended"})
                    if same_frame:
                        X._u32.ShowWindow(w, 7)                                    # another document frame of the program: put it away, never close a document
                        continue
                    X._u32.PostMessageW(w, 0x0100, 0x1B, 0)                        # a takeover window (slide show, player): Escape ends it, WM_CLOSE only if it stays
                    X._u32.PostMessageW(w, 0x0101, 0x1B, 0)
                    if len([i for i in self.incidents if i["class"] == cls]) > 2:
                        X._u32.PostMessageW(w, 0x0010, 0, 0)
            except Exception:
                pass
            time.sleep(self.every)


class Cartographer:
    def __init__(self, ex: X.Explorer, *, budget_s: float = 600.0, log=None, run_id: str = ""):
        self.ex = ex
        self.budget_s = budget_s
        self.t0 = time.time()
        self.log = log or (lambda s: None)
        self.run_id = run_id or ex.run_id
        self.map: Dict[str, Any] = {"app_key": ex.key, "run_id": self.run_id, "surfaces": []}
        self.stats: Dict[str, Any] = {"tabs": 0, "groups": 0, "controls": 0, "expanded": 0, "items": 0, "dialogs": 0, "unwind_failures": 0, "skipped_unsafe": 0, "collapsed_groups": 0}
        self.dialogs: Dict[str, Dict[str, Any]] = {}
        self.last_action = "start"
        self._size0 = None
        self.created_workspace = False
        self._item_cache: Dict[str, Dict[str, Any]] = {}
        self.base_windows: Set[int] = set()
        self.base_popups: List[int] = []

    def left(self) -> float:
        return self.budget_s - (time.time() - self.t0)

    def alive(self) -> bool:
        """The window we are mapping still exists. A walk that outlives its window must stop at once and say what it was doing."""
        ok = bool(X._u32.IsWindow(self.ex.hwnd))
        if not ok:
            self.map.setdefault("died", {"during": self.last_action, "after_s": round(time.time() - self.t0, 1)})
        return ok

    def act(self, what: str) -> None:
        self.last_action = what

    # ------------------------------------------------------------------------------------------ preparation
    def widen(self, width: int = 2400, height: int = 900) -> Dict[str, Any]:
        """A parked window is laid out at ITS size; a narrow ribbon collapses groups into drop-downs. Make the parked window wide (restored on exit)."""
        out: Dict[str, Any] = {}
        try:
            from core_organs import background_window as bw
            h = self.ex.hwnd
            if bw.is_parked(h):
                r0 = bw._rect(h)
                X._u32.SetWindowPos.argtypes = [X.wt.HWND, X.wt.HWND, ctypes_int, ctypes_int, ctypes_int, ctypes_int, X.wt.UINT]
                X._u32.SetWindowPos(h, 0, 0, 0, width, height, 0x0002 | 0x0004 | 0x0010)         # NOMOVE | NOZORDER | NOACTIVATE
                time.sleep(0.9)
                try:
                    bw.sliver(h)
                except Exception:
                    pass
                time.sleep(0.6)
                out = {"from": [r0[2] - r0[0], r0[3] - r0[1]], "to": [width, height]}
                self._size0 = (r0[2] - r0[0], r0[3] - r0[1])
        except Exception as exc:
            out = {"error": f"{type(exc).__name__}: {str(exc)[:80]}"}
        return out

    def settle(self, max_s: float = 2.5, min_nodes: int = 5) -> List[Any]:
        """Snapshot until the node count stops changing (a ribbon realises its controls lazily after a tab switch)."""
        last, nodes, end = -1, [], time.time() + max_s
        while time.time() < end:
            nodes = self.ex.snap(ms=6000)
            if len(nodes) == last and len(nodes) >= min_nodes:
                break
            last = len(nodes)
            time.sleep(0.25)
        return nodes

    # ------------------------------------------------------------------------------------------ finding surfaces
    def tab_strips(self, nodes) -> List[Tuple[Any, List[Any]]]:
        out = []
        by_parent: Dict[int, List[Any]] = collections.defaultdict(list)
        for n in nodes:
            if n.ctype == "TabItemControl" and "select" in n.pats and n.name:
                by_parent[n.parent].append(n)
        for par, items in by_parent.items():
            if len(items) >= 3:                                          # a ribbon / settings strip, not a 2-page toggle
                strip = nodes[par]
                out.append((strip, items))
        out.sort(key=lambda s: (s[0].rect[1], s[0].rect[0]))
        return out

    def file_button(self, nodes, strip) -> Optional[Any]:
        """The backstage entry: an invokable button/tab left of the first tab with the name File (or an id that says so)."""
        cands = [n for n in nodes if n.ctype in ("ButtonControl", "TabItemControl", "MenuItemControl") and ("invoke" in n.pats or "select" in n.pats)
                 and (re.fullmatch(r"(file|file tab|home|menu)", _f(n.name)) or re.search(r"filetab|backstage|appmenu", n.aid, re.I))
                 and n.rect[1] < strip.rect[3] + 4 and n.rect[2] <= strip.rect[0] + 60]
        cands = [c for c in cands if re.search(r"file|backstage|appmenu", c.name + c.aid, re.I)]
        return cands[0] if cands else None

    def recover(self, why: str = "") -> bool:
        """The window stopped answering like a ribbon (a dialog is still open, the tree is empty or has no tab strip): end every window the walk opened (Cancel button, else
        WM_CLOSE), collapse popups, and check that the tab strip is back. Logged; a walk that cannot recover stops instead of poking a broken window."""
        ex = self.ex
        rec: Dict[str, Any] = {"why": why, "during": self.last_action, "closed": []}
        for _ in range(3):
            for w in ex.hin.process_windows(ex.hwnd, include_hidden=False):
                if w == ex.hwnd or w in self.base_windows:
                    continue
                cls = X.Explorer._class_of(w)
                if cls in ("SysShadow",) or cls == X.Explorer._class_of(ex.hwnd):
                    continue
                title = ex.bm._win_title(w) or cls
                ok = False
                for nm in ("Cancel", "Close", "No", "Don't Save"):
                    if ex.click_button(w, nm):
                        ok = True
                        break
                if not ok:
                    X._u32.PostMessageW(w, 0x0010, 0, 0)
                rec["closed"].append(title)
            ex.close_surfaces(self.base_popups)
            time.sleep(0.8)
            if self.tab_strips(ex.snap(ms=6000)):
                rec["ok"] = True
                self.map.setdefault("recoveries", []).append(rec)
                return True
        rec["ok"] = False
        self.map.setdefault("recoveries", []).append(rec)
        return False

    def group_signature(self, nodes, strip) -> Tuple[str, ...]:
        names = []
        for c in self.region_controls(nodes, strip)[:400]:
            if c["group"] and c["group"] not in names:
                names.append(c["group"])
        return tuple(names)

    def select_tab(self, name: str, prev_sig: Tuple[str, ...]) -> Tuple[List[Any], Any, bool]:
        """Select a tab and wait until the ribbon IS that tab's (selected flag set and, for a tab after the first, the group set changed)."""
        ex = self.ex
        nodes: List[Any] = []
        strip = None
        for attempt in range(3):
            cur = ex.snap(ms=6000)
            tab = next((n for n in cur if n.ctype == "TabItemControl" and n.name == name and "select" in n.pats), None)
            if tab is None and attempt == 0:
                self.recover(f"tab {name!r} not found ({len(cur)} nodes)")
                cur = ex.snap(ms=6000)
                tab = next((n for n in cur if n.ctype == "TabItemControl" and n.name == name and "select" in n.pats), None)
            if tab is None:
                self.map.setdefault("tab_diagnostics", []).append({"tab": name, "nodes": len(cur), "during": self.last_action,
                                                                   "windows": [X.Explorer._class_of(w) for w in ex.hin.process_windows(ex.hwnd, include_hidden=False)][:8]})
                return cur, None, False
            if not tab.selected:
                ex.uia(tab, "GetSelectionItemPattern", "Select", wait=1.2)
            end = time.time() + 4.0
            while time.time() < end:
                time.sleep(0.35)
                nodes = ex.snap(ms=6000)
                t2 = next((n for n in nodes if n.ctype == "TabItemControl" and n.name == name and "select" in n.pats), None)
                if t2 is None:
                    continue
                strip = nodes[t2.parent] if 0 <= t2.parent < len(nodes) else None
                if strip is None or not t2.selected:
                    continue
                sig = self.group_signature(nodes, strip)
                if sig and (not prev_sig or sig != prev_sig):
                    return nodes, strip, True
            time.sleep(0.5)
        return nodes, strip, False

    # ------------------------------------------------------------------------------------------ reading a tab
    def region_controls(self, nodes, strip) -> List[Dict[str, Any]]:
        """Controls in the ribbon region below the tab strip, with their innermost named group."""
        container = strip.parent if strip.parent >= 0 else 0
        sub = [n for n in subtree(nodes, container)]
        strip_ids = {n.idx for n in subtree(nodes, strip.idx)} | {strip.idx}
        floor = strip.rect[3] - 2
        tab_names = {_f(t.name) for t in nodes if t.ctype == "TabItemControl"}
        out: List[Dict[str, Any]] = []
        seen_idx: Set[int] = set()
        for n in sub:
            if n.idx in strip_ids or n.idx in seen_idx:
                continue
            if n.rect[1] < floor and n.rect != (0, 0, 0, 0):
                continue                                                  # quick-access bar / title bar / tell-me box live above the strip's bottom edge
            par = nodes[n.parent] if 0 <= n.parent < len(nodes) else None
            if par is not None and par.ctype in COMPOSITE_PARENTS:
                continue                                                  # an internal part of a split button / combo box / spinner
            if private_context(nodes, n) or (n.ctype == "ListControl" and PRIVATE_LIST_RX.search(n.name or "")):
                continue
            is_gallery = n.ctype == "ListControl" and any(nodes[c].ctype == "ListItemControl" for c in n.children)
            kind = CONTROL_TYPES.get(n.ctype)
            if not is_gallery and (not kind or n.ctype == "TextControl"):
                continue
            if not is_gallery and not n.name and not n.aid:
                continue
            if n.ctype == "ListItemControl" and par is not None and par.ctype == "ListControl":
                continue                                                  # an item of an inline gallery: reported with its gallery
            grp = ""
            for a in ancestors(nodes, n):
                if a.ctype in GROUP_TYPES and a.name and _f(a.name) not in tab_names and _f(a.name) not in GENERIC_NAMES:
                    grp = a.name
                    break
            c: Dict[str, Any] = {"name": n.name or n.aid, "aid": n.aid, "kind": "gallery" if is_gallery else kind_of(n), "pats": list(n.pats), "accel": n.accel, "help": (n.help or "")[:140],
                                 "enabled": bool(n.enabled), "offscreen": bool(n.offscreen), "group": grp, "rect": n.rect, "_node": n}
            if n.toggle_state in (0, 1, 2):
                c["state"] = {0: "off", 1: "on", 2: "indeterminate"}[n.toggle_state]
            if is_gallery:
                c["items"] = [nodes[i].name for i in n.children if nodes[i].ctype == "ListItemControl" and nodes[i].name][:MAX_ITEMS]
                c["n_items"] = len(n.children)
            out.append(c)
            seen_idx.add(n.idx)
        return out

    # ------------------------------------------------------------------------------------------ expansion
    def _new_nodes(self, before, after) -> List[Any]:
        """Nodes present after and not before (multiset difference on identity + parent identity): what an expansion revealed."""
        def key(nodes, n):
            p = nodes[n.parent] if 0 <= n.parent < len(nodes) else None
            return (n.ctype, n.name, n.aid, p.ctype if p is not None else "", p.name if p is not None else "")
        cnt = collections.Counter(key(before, n) for n in before)
        out = []
        for n in after:
            k = key(after, n)
            if cnt[k] > 0:
                cnt[k] -= 1
            else:
                out.append(n)
        return out

    def _read_items(self, before, after, new_popups: List[int]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        seen: Set[Tuple[str, str]] = set()

        def take(nodes, pool, popup: int = 0) -> None:
            for n in pool:
                k = ITEM_TYPES.get(n.ctype)
                if not k or n.ctype == "TabItemControl":
                    continue
                if not n.name and not n.aid:
                    continue
                if n.rect == (0, 0, 0, 0) and not n.name:
                    continue
                par = nodes[n.parent] if 0 <= n.parent < len(nodes) else None
                if par is not None and par.ctype in COMPOSITE_PARENTS and par.ctype != "SplitButtonControl":
                    continue
                if _f(n.name) in ("more options",) and k in ("menuitem",):
                    continue
                if private_context(nodes, n):
                    continue
                sig = (n.name, n.ctype)
                if sig in seen:
                    continue
                seen.add(sig)
                grp = ""
                for a in ancestors(nodes, n):
                    if a.ctype in GROUP_TYPES and a.name and _f(a.name) not in GENERIC_NAMES:
                        grp = a.name
                        break
                it = {"name": n.name or n.aid, "aid": n.aid, "kind": kind_of(n), "pats": list(n.pats), "accel": n.accel, "enabled": bool(n.enabled), "group": grp, "_node": n, "_popup": popup}
                if n.toggle_state in (0, 1, 2):
                    it["state"] = {0: "off", 1: "on", 2: "indeterminate"}[n.toggle_state]
                if getattr(n, "selected", None):
                    it["selected"] = True
                items.append(it)
        for w in new_popups[:3]:
            ns = self.ex.snap(w, ms=3000)
            if ns and len(ns) > 3:
                take(ns, ns, w)
        if not items:
            take(after, self._new_nodes(before, after))
        return items

    def expand_read(self, node, depth: int = 0, base_popups: Optional[List[int]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Expand one control, return (items, info). The control is collapsed again before returning."""
        ex = self.ex
        info: Dict[str, Any] = {"ok": False}
        self.act(f"expand {node.name!r}")
        if not self.alive():
            info["why"] = "window gone"
            return [], info
        base = ex.popups() if base_popups is None else base_popups
        before = ex.snap(ms=5000)
        ok, how = ex.uia(node, "GetExpandCollapsePattern", "Expand", wait=1.2)
        if not ok and ("COMError" in how or "event was unable" in how):             # the provider was busy re-rendering: one more try
            time.sleep(0.8)
            ok, how = ex.uia(node, "GetExpandCollapsePattern", "Expand", wait=1.2)
        if not ok:
            info["why"] = how
            return [], info
        end, new_pop = time.time() + 1.4, []
        after = before
        while time.time() < end:
            time.sleep(0.18)
            new_pop = [w for w in ex.popups() if w not in base]
            after = ex.snap(ms=5000)
            if new_pop or len(self._new_nodes(before, after)) > 0:
                break
        time.sleep(0.15)
        after = ex.snap(ms=5000)
        items = self._read_items(before, after, new_pop)
        info.update(ok=True, items=len(items), popup=bool(new_pop))
        # submenus: expand each expandable item, read, collapse
        if depth + 1 < MAX_DEPTH:
            for it in items[:40]:
                if self.left() < 5:
                    break
                if "expand" in it["pats"] and it["enabled"] and not X.UNSAFE_RX.search(it["name"]) and not X.SENSITIVE_RX.search(it["name"]):
                    sub, sinfo = self.expand_read(it["_node"], depth + 1, base)
                    if sinfo.get("ok"):
                        it["items"] = [{k: v for k, v in s.items() if not k.startswith("_")} for s in sub[:MAX_ITEMS]]
                        it["n_items"] = len(sub)
        # unwind: collapse the control, then make sure no surface is left
        ex.uia(node, "GetExpandCollapsePattern", "Collapse", wait=0.9)
        time.sleep(0.2)
        if [w for w in ex.popups() if w not in base]:
            ex.close_surfaces(base)
        check = ex.snap(ms=5000)
        if len(self._new_nodes(before, check)) > 2:                       # leftovers (a menu that did not close)
            ex.close_surfaces(base)
            time.sleep(0.2)
            check = ex.snap(ms=5000)
            if len(self._new_nodes(before, check)) > 2:
                info["unwound"] = False
                self.stats["unwind_failures"] += 1
                return items, info
        info["unwound"] = True
        return items, info

    # ------------------------------------------------------------------------------------------ one tab
    def read_tab(self, tab_name: str, nodes, strip) -> Dict[str, Any]:
        ctrls = self.region_controls(nodes, strip)
        groups: Dict[str, List[Dict[str, Any]]] = collections.OrderedDict()
        for c in sorted(ctrls, key=lambda c: (c["rect"][0] // 40, c["rect"][1])):
            groups.setdefault(c["group"] or "(ungrouped)", []).append(c)
        surface: Dict[str, Any] = {"id": f"tab:{tab_name}", "kind": "ribbon-tab", "name": tab_name, "groups": []}
        for gname, gcs in groups.items():
            g = {"name": gname, "controls": []}
            for c in gcs:
                if not self.alive():
                    break
                if self.left() < 6:
                    c["leads_to"] = {"type": "unknown", "why": "budget"}
                    g["controls"].append(c)
                    continue
                self.stats["controls"] += 1
                unsafe = bool(X.UNSAFE_RX.search(c["name"])) or bool(X.SENSITIVE_RX.search(c["name"]))
                if unsafe:
                    self.stats["skipped_unsafe"] += 1
                    c["leads_to"] = {"type": "not-opened", "why": "capture / share / account / destructive control: named, never opened by a scan"}
                    g["controls"].append(c)
                    continue
                if c["kind"] == "gallery":
                    c["leads_to"] = {"type": "gallery", "items": c.get("items", []), "n_items": c.get("n_items", 0)}
                elif "expand" in c["pats"] and c["enabled"] and not unsafe and c["kind"] != "combobox":
                    items, info = self.expand_read(c["_node"])
                    self.stats["expanded"] += 1
                    self.stats["items"] += len(items)
                    if items:
                        typ = "gallery" if sum(1 for i in items if i["kind"] == "item") > max(3, len(items) // 2) else "menu"
                        c["leads_to"] = {"type": typ, "items": [{k: v for k, v in i.items() if not k.startswith("_")} for i in items[:MAX_ITEMS]], "n_items": len(items), "unwound": info.get("unwound")}
                    else:
                        c["leads_to"] = {"type": "unknown", "why": info.get("why") or "expanded, nothing read"}
                elif "expand" in c["pats"] and c["kind"] == "combobox":
                    c["leads_to"] = {"type": "choice-list"}
                elif c["kind"] in ("toggle", "checkbox"):
                    c["leads_to"] = {"type": "toggle", "state": c.get("state", "")}
                elif X.OPENER_RX.search(c["name"]):
                    if RUNTIME_RX.search(c["name"]) or X.SENSITIVE_RX.search(c["group"] or "") or X.SENSITIVE_RX.search(tab_name):
                        c["leads_to"] = {"type": "not-opened", "why": "starts a runtime mode (show / recording / playback): named, never triggered by a scan"}
                        self.stats["skipped_unsafe"] += 1
                    else:
                        c["leads_to"] = {"type": "dialog", "pending": True}
                elif c["kind"] in ("edit", "spinner", "slider"):
                    c["leads_to"] = {"type": "value-entry"}
                else:
                    c["leads_to"] = {"type": "command"}
                g["controls"].append(c)
            surface["groups"].append(g)
            self.stats["groups"] += 1
        self.stats["tabs"] += 1
        return surface

    # ------------------------------------------------------------------------------------------ dialogs reached from the map
    def open_pending_dialogs(self, surface: Dict[str, Any], strip_getter) -> None:
        """Every control marked dialog-pending (ellipsis) is opened through the explorer's ladder; its schema is stored; the dialog is cancelled."""
        ex = self.ex
        for g in surface["groups"]:
            for c in g["controls"]:
                lt = c.get("leads_to", {})
                if not lt.get("pending") or self.left() < 8:
                    continue
                if not c.get("enabled"):
                    lt.update(type="disabled", why="disabled in this state: it needs a selection or object first", pending=False)
                    continue
                if X.UNSAFE_RX.search(c["name"]) or X.SENSITIVE_RX.search(c["name"]):
                    continue
                node = c.get("_node")
                if node is None:
                    continue
                self.act(f"open dialog {c['name']!r}")
                if not self.alive():
                    return
                rec = ex.probe_opener(node)
                if rec:
                    lt.pop("pending", None)
                    lt["type"] = "dialog" if rec.get("effect") == "dialog" else ("pane" if rec.get("effect") == "inline_change" else "command")
                    for k in ("dialog", "controls", "pages", "wizard", "master_detail", "fields", "file_dialog", "commit", "cancel"):
                        if rec.get(k) is not None:
                            lt[k] = rec[k]
                    self.stats["dialogs"] += 1 if rec.get("effect") == "dialog" else 0
                    if rec.get("effect") == "inline_change":
                        self.restore_inline(node)

    def open_menu_items(self, surface: Dict[str, Any], tab_name: str) -> None:
        """Items inside expanded menus that promise a dialog ("This Device...", "Paste Special..."): reopen the menu, invoke the item through UIA on a worker thread
        (a posted click would close a modal menu loop), read the dialog, cancel it. The tab must still be the selected one."""
        for g in surface["groups"]:
            for c in g["controls"]:
                lt = c.get("leads_to") or {}
                items = lt.get("items") if isinstance(lt.get("items"), list) else []
                todo = [i for i in items if isinstance(i, dict) and X.OPENER_RX.search(i["name"]) and i.get("enabled", True)
                        and not (X.UNSAFE_RX.search(i["name"]) or X.SENSITIVE_RX.search(i["name"]) or RUNTIME_RX.search(i["name"]) or X.SENSITIVE_RX.search(c["name"]))]
                if not todo or lt.get("type") not in ("menu", "gallery") or not c.get("enabled", True):
                    continue
                for it in todo[:6]:
                    if self.left() < 10 or not self.alive():
                        return
                    if it["name"] in self._item_cache:                                 # the same item in many menus (More Colors... under every pen): opened once
                        it["leads_to"] = dict(self._item_cache[it["name"]], same_as_seen=True)
                        continue
                    self.act("open menu item %r > %r" % (c["name"], it["name"]))
                    try:
                        rec = self._reach_and_invoke(c, it["name"])
                    except Exception as exc:
                        rec = {"effect": "error", "why": "%s: %s" % (type(exc).__name__, str(exc)[:60])}
                    if rec:
                        it["leads_to"] = {k: v for k, v in rec.items() if k in ("effect", "dialog", "controls", "pages", "wizard", "master_detail", "fields", "file_dialog", "commit", "cancel", "why", "unwound")}
                        it["leads_to"]["type"] = "dialog" if rec.get("effect") == "dialog" else "command"
                        if rec.get("effect") == "dialog":
                            self._item_cache[it["name"]] = dict(it["leads_to"])
                        if rec.get("effect") == "dialog":
                            self.stats["dialogs"] += 1

    def _reach_and_invoke(self, c: Dict[str, Any], item_name: str) -> Optional[Dict[str, Any]]:
        ex = self.ex
        cur = ex.snap(ms=6000)
        node = next((n for n in cur if n.ctype == c["_node"].ctype and n.name == c["_node"].name and n.aid == c["_node"].aid and n.rect != (0, 0, 0, 0)), None)
        if node is None or "expand" not in node.pats:
            return None
        base = ex.popups()
        sig0 = ex.signature(cur)
        before = cur
        ok, how = ex.uia(node, "GetExpandCollapsePattern", "Expand", wait=1.2)
        if not ok:
            return {"effect": "none", "why": how}
        time.sleep(0.5)
        new_pop = [w for w in ex.popups() if w not in base]
        after = ex.snap(ms=5000)
        pool = self._read_items(before, after, new_pop)
        tgt = next((i for i in pool if i["name"] == item_name), None)
        if tgt is None:
            ex.uia(node, "GetExpandCollapsePattern", "Collapse", wait=0.9)
            ex.close_surfaces(base)
            return {"effect": "none", "why": "item not found on reopening"}
        ok, how = ex.uia(tgt["_node"], "GetInvokePattern", "Invoke", wait=1.2)
        end = time.time() + 3.0
        dlgs: List[int] = []
        top_cls = X.Explorer._class_of(ex.hwnd)
        while ok and time.time() < end:
            time.sleep(0.15)
            dlgs = [w for w in ex.popups() if w not in base and w not in new_pop and X._u32.IsWindow(w)]
            if not dlgs:
                dlgs = [w for w in ex.hin.process_windows(ex.hwnd, include_hidden=False) if w != ex.hwnd and w not in base and w not in new_pop and X._u32.IsWindowVisible(w)
                        and X.Explorer._class_of(w) not in ("SysShadow", top_cls)]
            if dlgs:
                break
        rec: Dict[str, Any] = {"effect": "none", "via": how}
        if dlgs:
            time.sleep(0.3)
            w = dlgs[0]
            title = ex.bm._win_title(w) or ex.bm._win_class(w)
            info = ex.learn_dialog(w, title, via="%s > %s" % (c["name"], item_name), uia_blocked="still running" in how)
            rec.update(effect="dialog", dialog=title, **{k: v for k, v in info.items() if k in ("controls", "pages", "wizard", "master_detail", "fields", "file_dialog", "commit", "cancel")})
        ex.uia(node, "GetExpandCollapsePattern", "Collapse", wait=0.9)
        un = ex.close_surfaces(base)
        back = ex.snap(ms=5000)
        if not un or ex.signature(back) != sig0:
            self.stats["unwind_failures"] += 1
            rec["unwound"] = False
        return rec

    def restore_inline(self, node) -> None:
        """A control that changed the window in place (a task pane opened): toggle it back, then check the tree."""
        ex = self.ex
        ex.uia(node, "GetInvokePattern", "Invoke", wait=1.0)
        time.sleep(0.4)

    # ------------------------------------------------------------------------------------------ menu-bar apps
    def menubar(self, nodes) -> Optional[Dict[str, Any]]:
        bars = [n for n in nodes if n.ctype == "MenuBarControl" and _f(n.name) != "system"]
        tops: List[Any] = []
        for b in bars:
            tops += [nodes[i] for i in b.children if nodes[i].ctype == "MenuItemControl" and nodes[i].name and _f(nodes[i].name) not in X.CHROME]
        if not tops:
            return None
        surface: Dict[str, Any] = {"id": "menubar", "kind": "menubar", "name": "Menu bar", "groups": [{"name": "", "controls": []}]}
        for top in tops:
            if self.left() < 6:
                break
            c = {"name": top.name, "aid": top.aid, "kind": "dropdown", "pats": list(top.pats), "accel": top.accel, "help": "", "enabled": True, "group": "", "rect": top.rect, "_node": top}
            if "expand" in top.pats:
                items, info = self.expand_read(top)
                self.stats["expanded"] += 1
                self.stats["items"] += len(items)
                c["leads_to"] = {"type": "menu", "items": [{k: v for k, v in i.items() if not k.startswith("_")} for i in items[:MAX_ITEMS]], "n_items": len(items), "unwound": info.get("unwound")}
            else:
                c["leads_to"] = {"type": "menu", "items": [], "note": "opened by click only"}
            surface["groups"][0]["controls"].append(c)
            self.stats["controls"] += 1
        self.stats["groups"] += 1
        return surface

    def quick_access(self, nodes) -> Optional[Dict[str, Any]]:
        """The quick-access toolbar (a ToolBar named like it): its buttons, and the items of its own customise drop-down."""
        qa = next((n for n in nodes if n.ctype == "ToolBarControl" and re.search(r"quick access", n.name or "", re.I)), None)
        if qa is None:
            return None
        surf: Dict[str, Any] = {"id": "qat", "kind": "toolbar", "name": "Quick Access Toolbar", "groups": [{"name": "", "controls": []}]}
        for n in subtree(nodes, qa.idx):
            par = nodes[n.parent] if 0 <= n.parent < len(nodes) else None
            if par is not None and par.ctype in COMPOSITE_PARENTS:
                continue
            if n.ctype not in CONTROL_TYPES or not CONTROL_TYPES.get(n.ctype) or not (n.name or n.aid):
                continue
            c = {"name": n.name or n.aid, "aid": n.aid, "kind": kind_of(n), "pats": list(n.pats), "accel": n.accel, "help": "", "enabled": bool(n.enabled), "group": "", "rect": n.rect, "_node": n}
            if "expand" in n.pats and re.search(r"customi[sz]e", n.name or "", re.I) and self.left() > 10:
                items, info = self.expand_read(n)
                c["leads_to"] = {"type": "menu", "items": [{k: v for k, v in i.items() if not k.startswith("_")} for i in items[:MAX_ITEMS]], "n_items": len(items), "unwound": info.get("unwound")}
            elif "expand" in n.pats:
                c["leads_to"] = {"type": "menu", "items": [], "note": "history / list drop-down: contents depend on the document"}
            else:
                c["leads_to"] = {"type": "toggle" if "toggle" in n.pats else "command"}
            surf["groups"][0]["controls"].append(c)
            self.stats["controls"] += 1
        return surf if surf["groups"][0]["controls"] else None

    def hoist_chrome(self) -> None:
        """Controls that repeat on every tab outside any group (display options...) belong to the ribbon, not to a tab: one surface, said once."""
        tabs = [s for s in self.map["surfaces"] if s["kind"] == "ribbon-tab"]
        if len(tabs) < 3:
            return
        count: Dict[Tuple[str, str], int] = collections.Counter()
        for s in tabs:
            for g in s["groups"]:
                if g["name"] in ("(ungrouped)", ""):
                    for c in g["controls"]:
                        count[(c["name"], c.get("aid", ""))] += 1
        shared = {k for k, v in count.items() if v >= max(3, len(tabs) - 1)}
        if not shared:
            return
        chrome: List[Dict[str, Any]] = []
        seen: Set[Tuple[str, str]] = set()
        for s in tabs:
            for g in s["groups"]:
                keep = []
                for c in g["controls"]:
                    k = (c["name"], c.get("aid", ""))
                    if g["name"] in ("(ungrouped)", "") and k in shared:
                        if k not in seen:
                            seen.add(k)
                            chrome.append(c)
                    else:
                        keep.append(c)
                g["controls"] = keep
            s["groups"] = [g for g in s["groups"] if g["controls"]]
        if chrome:
            self.map["surfaces"].append({"id": "ribbon-chrome", "kind": "toolbar", "name": "Ribbon (all tabs)", "groups": [{"name": "", "controls": chrome}]})

    # ------------------------------------------------------------------------------------------ contexts (selection-dependent UI)
    def tab_names(self, nodes) -> List[str]:
        st = self.tab_strips(nodes)
        return [t.name for t in st[0][1]] if st else []

    def undo_button(self, nodes):
        cands = [n for n in nodes if n.ctype == "ButtonControl" and re.fullmatch(r"undo", _f(n.name)) and "invoke" in n.pats and n.enabled and n.rect != (0, 0, 0, 0)]
        return cands[0] if cands else None

    def contexts(self, max_contexts: int = 6) -> List[Dict[str, Any]]:
        """Some UI exists only while something is selected (a table's own tabs, enabled font controls). In the DISPOSABLE document the scan created, perform a few
        immediate 'insert' actions taken from the map itself (an item of an Insert-like tab's drop-down), see which tabs appear and which disabled controls
        become enabled, read the new tabs, then undo and verify the window is back to its starting tab set. Never runs in a document the scan did not create."""
        ex = self.ex
        if not (self.created_workspace or ex.pristine):
            return [{"skipped": "not a document this scan created: no actions are performed in it"}]
        cands: List[Tuple[str, Dict[str, Any], Dict[str, Any], Dict[str, Any]]] = []
        for s in self.map["surfaces"]:
            if s["kind"] != "ribbon-tab" or not re.search(r"insert|add|new", s["name"], re.I):
                continue
            for g in s["groups"]:
                for c in g["controls"]:
                    lt = c.get("leads_to") or {}
                    if lt.get("type") not in ("menu", "gallery") or not c.get("enabled", True):
                        continue
                    if X.UNSAFE_RX.search(c["name"]) or X.SENSITIVE_RX.search(c["name"]) or RUNTIME_RX.search(c["name"]):
                        continue
                    for it in lt.get("items") or []:
                        if isinstance(it, dict) and not X.OPENER_RX.search(it["name"]) and it.get("enabled", True) and not it.get("items")                                 and not (X.UNSAFE_RX.search(it["name"]) or X.SENSITIVE_RX.search(it["name"]) or RUNTIME_RX.search(it["name"])):
                            cands.append((s["name"], g, c, it))
                            break
        out: List[Dict[str, Any]] = []
        base_tabs = self.tab_names(ex.snap(ms=6000))
        base_enabled = {}
        for s in self.map["surfaces"]:
            if s["kind"] == "ribbon-tab":
                for g in s["groups"]:
                    for c in g["controls"]:
                        base_enabled[(s["name"], c["name"], c.get("aid", ""))] = c.get("enabled", True)
        for sname, g, c, it in cands[:max_contexts]:
            if self.left() < 40 or not self.alive():
                break
            cond = f"{sname} > {g['name']} > {c['name']} > {it['name']}" if g.get("name") else f"{sname} > {c['name']} > {it['name']}"
            self.act(f"context: {cond}")
            path = [{"kind": "surface", "name": sname}] + ([{"kind": "group", "name": g["name"]}] if g.get("name") else []) + [{"kind": "control", "name": c["name"]}, {"kind": "item", "name": it["name"]}]
            rec: Dict[str, Any] = {"when": cond, "applied": False}
            try:
                dr = drive(ex.hwnd, path)
                rec["applied"] = bool(dr.get("ok"))
                rec["why"] = dr.get("why", "")
            except Exception as exc:
                rec["why"] = f"{type(exc).__name__}: {str(exc)[:60]}"
            time.sleep(1.0)
            cur = self.settle(2.5)
            now_tabs = self.tab_names(cur)
            new_tabs = [t for t in now_tabs if t not in base_tabs]
            rec["new_tabs"] = new_tabs
            for t in new_tabs[:4]:
                if self.left() < 20:
                    break
                nodes2, strip2, ver = self.select_tab(t, ())
                if strip2 is None:
                    continue
                surf = self.read_tab(t, nodes2, strip2)
                surf.update(id=f"context:{t}", kind="context-tab", when=cond, verified_selected=ver)
                self.map["surfaces"].append(surf)
            # which controls that were disabled are enabled now (read the first tab again)
            first = next((t for t in base_tabs), None)
            if first:
                nodes3, strip3, ver3 = self.select_tab(first, ())
                if strip3 is not None:
                    enabled_now = {(c2["name"], c2.get("aid", "")): c2["enabled"] for c2 in self.region_controls(nodes3, strip3)}
                    unlocked = []
                    for s in self.map["surfaces"]:
                        if s["name"] != first:
                            continue
                        for g2 in s["groups"]:
                            for c2 in g2["controls"]:
                                if not c2.get("enabled", True) and enabled_now.get((c2["name"], c2.get("aid", ""))):
                                    c2.setdefault("enabled_when", []).append(cond)
                                    unlocked.append(c2["name"])
                    rec["unlocked"] = unlocked[:60]
            # undo: back to the starting tab set
            for _ in range(4):
                cur = ex.snap(ms=6000)
                if self.tab_names(cur) == base_tabs:
                    break
                ub = self.undo_button(cur)
                if ub is None:
                    break
                ex.uia(ub, "GetInvokePattern", "Invoke", wait=1.0)
                time.sleep(0.8)
            X._u32.PostMessageW(ex.hwnd, 0x0100, 0x1B, 0)
            X._u32.PostMessageW(ex.hwnd, 0x0101, 0x1B, 0)
            rec["restored"] = self.tab_names(ex.snap(ms=6000)) == base_tabs
            if not rec["restored"]:
                self.stats["unwind_failures"] += 1
            out.append(rec)
            if not rec["restored"]:
                break                                               # the document is not back to its start: stop acting in it
        return out

    # ------------------------------------------------------------------------------------------ everything else in the main window
    CHROME_NAMES = {"minimize", "maximize", "restore", "close", "system", "help", "ribbon display options"}

    def window_surface(self, nodes, mapped: Set[Tuple[str, str, str]], limit: int = 90) -> Optional[Dict[str, Any]]:
        """Controls of the main window that no other surface covers (status bar, side panes, docks, a calculator's keypad, a mixer's buttons): grouped by the nearest named
        container, drop-downs expanded and read exactly like ribbon controls. This is the whole map for programs without a ribbon or a menu bar."""
        ex = self.ex
        groups: Dict[str, List[Dict[str, Any]]] = collections.OrderedDict()
        n_total = 0
        for n in nodes:
            if n.ctype not in CONTROL_TYPES or not CONTROL_TYPES.get(n.ctype) or n.ctype in ("TextControl", "ListItemControl", "EditControl") and not ("invoke" in n.pats or "select" in n.pats or "value" in n.pats):
                continue
            if not (n.name or n.aid) or n.rect == (0, 0, 0, 0) or n.offscreen and not n.name:
                continue
            if _f(n.name) in self.CHROME_NAMES or (n.ctype, n.name, n.aid) in mapped:
                continue
            par = nodes[n.parent] if 0 <= n.parent < len(nodes) else None
            if par is not None and par.ctype in COMPOSITE_PARENTS:
                continue
            if private_context(nodes, n):
                continue
            if n.ctype == "ListItemControl" and par is not None and par.ctype == "ListControl":
                continue
            grp = ""
            for a in ancestors(nodes, n):
                if a.ctype in (GROUP_TYPES | {"PaneControl", "ListControl", "TabControl", "StatusBarControl", "TreeControl", "DocumentControl"}) and a.name and _f(a.name) not in GENERIC_NAMES and a.idx != 0:
                    grp = a.name
                    break
                if a.ctype == "StatusBarControl":
                    grp = "Status bar"
                    break
            c = {"name": n.name or n.aid, "aid": n.aid, "kind": kind_of(n), "pats": list(n.pats), "accel": n.accel, "help": (n.help or "")[:140], "enabled": bool(n.enabled), "group": grp, "rect": n.rect, "_node": n}
            if n.toggle_state in (0, 1, 2):
                c["state"] = {0: "off", 1: "on", 2: "indeterminate"}[n.toggle_state]
            groups.setdefault(grp or "(main)", []).append(c)
            n_total += 1
            if n_total >= limit * 4:
                break
        if not groups:
            return None
        surf: Dict[str, Any] = {"id": "window", "kind": "window", "name": "Window", "groups": []}
        expanded = 0
        for gname, gcs in groups.items():
            g = {"name": gname, "controls": []}
            for c in gcs:
                if not self.alive():
                    break
                unsafe = bool(X.UNSAFE_RX.search(c["name"]) or X.SENSITIVE_RX.search(c["name"]))
                self.stats["controls"] += 1
                if unsafe:
                    c["leads_to"] = {"type": "not-opened", "why": "capture / share / account / destructive control: named, never opened by a scan"}
                    self.stats["skipped_unsafe"] += 1
                elif "expand" in c["pats"] and c["enabled"] and c["kind"] != "combobox" and expanded < limit and self.left() > 15:
                    items, info = self.expand_read(c["_node"])
                    expanded += 1
                    self.stats["expanded"] += 1
                    self.stats["items"] += len(items)
                    c["leads_to"] = ({"type": "menu", "items": [{k: v for k, v in i.items() if not k.startswith("_")} for i in items[:MAX_ITEMS]], "n_items": len(items), "unwound": info.get("unwound")}
                                     if items else {"type": "unknown", "why": info.get("why") or "expanded, nothing read"})
                elif c["kind"] in ("toggle", "checkbox"):
                    c["leads_to"] = {"type": "toggle", "state": c.get("state", "")}
                elif X.OPENER_RX.search(c["name"]) and not RUNTIME_RX.search(c["name"]):
                    c["leads_to"] = {"type": "dialog", "pending": True}
                elif c["kind"] in ("edit", "spinner", "slider", "combobox"):
                    c["leads_to"] = {"type": "value-entry"}
                else:
                    c["leads_to"] = {"type": "command"}
                g["controls"].append(c)
            surf["groups"].append(g)
            self.stats["groups"] += 1
        return surf

    def mapped_ids(self) -> Set[Tuple[str, str, str]]:
        out: Set[Tuple[str, str, str]] = set()
        for s in self.map["surfaces"]:
            for g in s["groups"]:
                for c in g["controls"]:
                    nd = c.get("_node")
                    if nd is not None:
                        out.add((nd.ctype, nd.name, nd.aid))
        return out

    # ------------------------------------------------------------------------------------------ backstage
    def backstage(self, nodes, strip) -> Optional[Dict[str, Any]]:
        ex = self.ex
        fb = self.file_button(nodes, strip)
        if fb is None or self.left() < 20:
            return None
        base = ex.popups()
        before = ex.snap(ms=6000)
        sig0 = ex.signature(before)
        ok, how = ex.uia(fb, "GetInvokePattern", "Invoke", wait=1.5) if "invoke" in fb.pats else ex.uia(fb, "GetSelectionItemPattern", "Select", wait=1.5)
        time.sleep(1.0)
        after = self.settle(2.5)
        new = self._new_nodes(before, after)
        pages = [n for n in new if n.ctype in ("ButtonControl", "ListItemControl", "TabItemControl", "MenuItemControl", "HyperlinkControl", "RadioButtonControl") and n.name and n.rect != (0, 0, 0, 0)]
        surface: Dict[str, Any] = {"id": "backstage", "kind": "backstage", "name": fb.name or "File", "groups": [], "via": how}
        if not pages:
            self._leave_backstage(fb, before, sig0)
            return None
        # navigation entries are the invokable/selectable ones on the left edge
        left_edge = min(n.rect[0] for n in pages)
        nav = [n for n in pages if n.rect[0] <= left_edge + 60 and ("invoke" in n.pats or "select" in n.pats)]
        seen: Set[str] = set()
        g = {"name": "Backstage pages", "controls": []}
        for n in nav:
            if _f(n.name) in seen:
                continue
            seen.add(_f(n.name))
            c = {"name": n.name, "aid": n.aid, "kind": kind_of(n), "pats": list(n.pats), "accel": n.accel, "help": "", "enabled": bool(n.enabled), "group": "Backstage pages", "rect": n.rect, "_node": n}
            if X.UNSAFE_RX.search(n.name) or X.SENSITIVE_RX.search(n.name):
                c["leads_to"] = {"type": "unsafe-skipped"}
                self.stats["skipped_unsafe"] += 1
                g["controls"].append(c)
                continue
            if n.aid == fb.aid and fb.aid or _f(n.name) in ("back", "go back"):
                c["leads_to"] = {"type": "leaves-backstage"}                  # the way OUT of the view: used for the unwind, never walked
                g["controls"].append(c)
                continue
            if self.left() < 10 or not self.alive():
                break
            lt: Dict[str, Any] = {"type": "page"}
            try:
                self.act(f"backstage page {n.name!r}")
                cur0 = self.ex.snap(ms=6000)
                live_n = next((m for m in cur0 if m.ctype == n.ctype and m.name == n.name and m.rect != (0, 0, 0, 0)), None)
                if live_n is None:
                    lt["type"] = "page-not-reachable"                          # the view is no longer showing (left it, or it changed): do not poke stale elements
                    c["leads_to"] = lt
                    g["controls"].append(c)
                    break
                if "select" in live_n.pats:
                    ex.uia(live_n, "GetSelectionItemPattern", "Select", wait=1.2)
                else:
                    ex.uia(live_n, "GetInvokePattern", "Invoke", wait=1.2)
                time.sleep(0.7)
                cur = self.settle(2.0)
                popups_now = [w for w in ex.popups() if w not in base]
                if popups_now:
                    title = ex.bm._win_title(popups_now[0]) or ex.bm._win_class(popups_now[0])
                    info = ex.learn_dialog(popups_now[0], title, via=f"File > {n.name}")
                    lt.update(type="dialog", dialog=title, controls=info.get("controls"), pages=info.get("pages"))
                    self.stats["dialogs"] += 1
                    ex.close_surfaces(base)
                else:
                    fresh = [m for m in self._new_nodes(cur0, cur) if ITEM_TYPES.get(m.ctype) and m.name and m.rect != (0, 0, 0, 0) and not private_context(cur, m)]
                    lt["controls"] = [{"name": m.name, "kind": kind_of(m)} for m in fresh[:60]]
            except Exception as exc:
                lt["error"] = f"{type(exc).__name__}: {str(exc)[:60]}"
            c["leads_to"] = lt
            g["controls"].append(c)
            self.stats["controls"] += 1
        surface["groups"].append(g)
        self.stats["groups"] += 1
        self._leave_backstage(fb, before, sig0)
        return surface

    def _leave_backstage(self, fb, before, sig0: str) -> None:
        """Back out of the File view: its Back button, else the File button again, else Escape; verified against the starting signature."""
        ex = self.ex
        for attempt in range(3):
            cur = ex.snap(ms=6000)
            if ex.signature(cur) == sig0 and len(self._new_nodes(before, cur)) <= 2:
                return
            back = next((n for n in cur if n.ctype == "ButtonControl" and re.fullmatch(r"back|go back|close", _f(n.name)) and n.rect != (0, 0, 0, 0)), None)
            if attempt == 0 and back is not None:
                ex.uia(back, "GetInvokePattern", "Invoke", wait=1.2)
            elif attempt == 1:
                ex.uia(fb, "GetInvokePattern", "Invoke", wait=1.2) if "invoke" in fb.pats else None
            else:
                X._u32.PostMessageW(ex.hwnd, 0x0100, 0x1B, 0)
                X._u32.PostMessageW(ex.hwnd, 0x0101, 0x1B, 0)
            time.sleep(0.8)
        self.stats["unwind_failures"] += 1

    # ------------------------------------------------------------------------------------------ run
    BLANK_RX = re.compile(r"^(blank|new blank|empty|untitled|new (document|presentation|workbook|spreadsheet|file|project|drawing|canvas|image|notebook|page))\b", re.I)

    def ensure_workspace(self) -> Dict[str, Any]:
        """A program that opens on a START / HOME screen has no working surface yet (no ribbon, no document). Create the disposable empty one a person would:
        the 'Blank ...' / 'New ...' choice on the start screen. Generic: found by label, never by application. Nothing is saved or typed."""
        ex = self.ex
        nodes = self.settle(3.0)
        strips = self.tab_strips(nodes)
        cands = [n for n in nodes if n.ctype in ("ListItemControl", "ButtonControl", "HyperlinkControl", "MenuItemControl", "TreeItemControl") and n.name and self.BLANK_RX.search(n.name)
                 and n.enabled and ("invoke" in n.pats or "select" in n.pats)]
        if not cands:
            if strips and len(self.region_controls(nodes, strips[0][0])) >= 8:
                return {"state": "ready"}
            return {"state": "unknown", "why": "no ribbon and no 'Blank ...' start-screen choice"}
        cands.sort(key=lambda n: (not _f(n.name).startswith("blank"), n.rect[1], n.rect[0]))
        tgt = cands[0]
        self.act(f"create blank workspace via {tgt.name!r}")
        ok, how = ex.uia(tgt, "GetInvokePattern", "Invoke", wait=1.5) if "invoke" in tgt.pats else ex.uia(tgt, "GetSelectionItemPattern", "Select", wait=1.5)
        end = time.time() + 14.0
        while time.time() < end:
            time.sleep(0.8)
            cur = self.ex.snap(ms=6000)
            st = self.tab_strips(cur)
            if st and len(self.region_controls(cur, st[0][0])) >= 8:
                self.created_workspace = True
                return {"state": "created", "via": tgt.name, "seconds": round(14.0 - (end - time.time()), 1)}
        return {"state": "failed", "via": tgt.name, "how": how}

    def unwiden(self) -> None:
        if self._size0 and X._u32.IsWindow(self.ex.hwnd):
            try:
                X._u32.SetWindowPos(self.ex.hwnd, 0, 0, 0, int(self._size0[0]), int(self._size0[1]), 0x0002 | 0x0004 | 0x0010)
                time.sleep(0.6)
            except Exception:
                pass

    def run(self) -> Dict[str, Any]:
        sen = Sentinel(self).start()
        try:
            return self._run()
        finally:
            sen.halt()
            if sen.incidents:
                self.map["incidents"] = sen.incidents[:20]
            self.unwiden()

    def _run(self) -> Dict[str, Any]:
        ex = self.ex
        try:
            self.base_windows = set(ex.hin.process_windows(ex.hwnd, include_hidden=True))
            self.base_popups = ex.popups()
        except Exception:
            pass
        self.map["workspace"] = self.ensure_workspace()
        self.map["widen"] = self.widen()
        nodes = self.settle(3.0)
        strips = self.tab_strips(nodes)
        self.map["applicable"] = bool(strips) or any(n.ctype == "MenuBarControl" for n in nodes) or sum(1 for n in nodes if (set(n.pats) & {"invoke", "toggle", "expand", "select"}) and n.name) >= 6
        if strips:
            strip, items = strips[0]
            orig = next((i for i in items if i.selected), None)
            order = [i for i in items if i is not orig] + ([orig] if orig is not None else [])
            order.sort(key=lambda t: t.rect[0])
            only = [x.strip().lower() for x in os.environ.get("HOJAIGA_ATLAS_ONLY_TABS", "").split(",") if x.strip()]
            if only:
                order = [t for t in order if t.name.lower() in only]
            prev_sig: Tuple[str, ...] = ()
            for tab in order:
                if self.left() < 10 or not self.alive():
                    self.map.setdefault("budget_exhausted_at", tab.name)
                    break
                self.act(f"select tab {tab.name!r}")
                cur, strip_now, verified = self.select_tab(tab.name, prev_sig if tab is not orig else ())
                if strip_now is None:
                    self.map.setdefault("tab_failures", []).append(tab.name)
                    continue
                if not verified:
                    self.map.setdefault("tab_unverified", []).append(tab.name)
                self.log(f"tab {tab.name}")
                surf = self.read_tab(tab.name, cur, strip_now)
                surf["verified_selected"] = verified
                prev_sig = self.group_signature(cur, strip_now)
                self.open_pending_dialogs(surf, None)
                self.open_menu_items(surf, tab.name)
                self.map["surfaces"].append(surf)
            # restore the originally selected tab
            if orig is not None:
                cur = ex.snap(ms=6000)
                o2 = next((n for n in cur if n.ctype == "TabItemControl" and n.name == orig.name and "select" in n.pats), None)
                if o2 is not None:
                    ex.uia(o2, "GetSelectionItemPattern", "Select", wait=1.2)
                    time.sleep(0.3)
            cur = self.settle(2.0)
            strips2 = self.tab_strips(cur)
            if strips2:
                bs = self.backstage(cur, strips2[0][0])
                if bs:
                    self.map["surfaces"].insert(0, bs)
        if os.environ.get("HOJAIGA_ATLAS_CONTEXTS", "1") != "0":
            try:
                self.map["contexts"] = self.contexts()
            except Exception as exc:
                self.map["contexts"] = [{"error": f"{type(exc).__name__}: {str(exc)[:100]}"}]
        qa = self.quick_access(self.settle(2.0))
        if qa:
            self.map["surfaces"].insert(0, qa)
        self.hoist_chrome()
        mb = self.menubar(self.settle(2.0))
        if mb:
            self.map["surfaces"].append(mb)
        try:
            ws = self.window_surface(self.settle(2.0), self.mapped_ids())
            if ws:
                self.open_pending_dialogs(ws, None)
                self.map["surfaces"].append(ws)
        except Exception as exc:
            self.map["window_surface_error"] = f"{type(exc).__name__}: {str(exc)[:100]}"
        self.map["stats"] = self.stats
        self.map["seconds"] = round(time.time() - self.t0, 1)
        return self.map

    # ------------------------------------------------------------------------------------------ output
    @staticmethod
    def clean(o: Any) -> Any:
        if isinstance(o, dict):
            return {k: (clean_name(v) if k == "name" and isinstance(v, str) else Cartographer.clean(v)) for k, v in o.items() if not k.startswith("_") and k != "rect"}
        if isinstance(o, list):
            return [Cartographer.clean(v) for v in o]
        if isinstance(o, tuple):
            return list(o)
        return o

    def save(self) -> str:
        d = os.path.join(C.ATLAS_DIR, "uimap")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"{self.ex.key}.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(self.clean(self.map), fh, indent=1, ensure_ascii=False)
        return p


ctypes_int = X.ctypes.c_int


# ---------------------------------------------------------------------------------------------- map -> knowledge
def describe_control(c: Dict[str, Any]) -> str:
    lt = c.get("leads_to") or {}
    typ = lt.get("type", "")
    bits = [c["name"]]
    k = c.get("kind", "")
    if k in ("split", "dropdown") and typ in ("menu", "gallery"):
        bits.append("(dropdown)")
    if c.get("accel"):
        bits.append(f"[{c['accel']}]")
    if typ in ("menu", "gallery") and lt.get("items"):
        names = [i["name"] if isinstance(i, dict) else str(i) for i in lt["items"]]
        bits.append("-> " + ", ".join(names[:12]) + (f", ... ({lt.get('n_items')} total)" if (lt.get("n_items") or 0) > 12 else ""))
    elif typ == "dialog":
        bits.append(f"-> opens dialog '{lt.get('dialog', '')}'")
    elif typ == "toggle":
        bits.append("(toggle)")
    elif typ == "value-entry" or typ == "choice-list":
        bits.append("(value you set)")
    return " ".join(bits)


def to_knowledge(key: str, m: Dict[str, Any], store: C.AtlasStore, model, run_id: str, file_path: str) -> Dict[str, int]:
    """Evidenced claims + commands with full paths from a cartographer map."""
    n_claims = n_cmds = 0
    mm = Cartographer.clean(m)
    ev = lambda ref, q="": [C.Evidence("probe", f"{run_id}:uimap:{ref}", q or f"read from the live window; map file {os.path.basename(file_path)}")]
    store.delete_claims(key, source="atlas.uimap")
    for s in mm.get("surfaces", []):
        sname = s["name"]
        gsum = []
        for g in s["groups"]:
            ctrls = g["controls"]
            if not ctrls:
                continue
            gname = g["name"] or "(ungrouped)"
            descs = [describe_control(c) for c in ctrls]
            gsum.append(f"{gname}: " + "; ".join(c['name'] for c in ctrls[:30]))
            kind = "ui.ribbon.group" if s["kind"] in ("ribbon-tab", "backstage") else "ui.menu.tree"
            where = f"{sname} tab" if s["kind"] == "ribbon-tab" else sname
            try:
                store.put_claim(C.Claim(key, kind, f"In the {where}, group '{gname}' has: " + " | ".join(descs)[:1800], "measured", 0.93, ev(f"{sname}/{gname}", f"{len(ctrls)} controls read"),
                                        {"surface": sname, "group": gname, "controls": ctrls}, "atlas.uimap"))
                n_claims += 1
            except C.EvidenceRequired:
                pass
            for c in ctrls:
                lt = c.get("leads_to") or {}
                base_path = f"{sname} > {gname} > {c['name']}" if s["kind"] == "ribbon-tab" and g["name"] else f"{sname} > {c['name']}"
                paths = [(base_path, c)]
                for it in lt.get("items", []) if isinstance(lt.get("items"), list) else []:
                    if isinstance(it, dict):
                        paths.append((f"{base_path} > {it['name']}", it))
                        for sub in it.get("items", []) or []:
                            if isinstance(sub, dict):
                                paths.append((f"{base_path} > {it['name']} > {sub['name']}", sub))
                for pth, ctl in paths:
                    nm = re.sub(r"\s+", " ", str(ctl.get("name", ""))).strip()
                    if not nm or len(nm) > 80:
                        continue
                    try:
                        model.upsert_command(key, {"name": nm, "menu_path": pth, "verb": "invoke", "shortcut": (ctl.get("accel") or "").replace(" ", "") or None,
                                                   "risk": "E2" if X.UNSAFE_RX.search(nm) else None, "automation_id": ctl.get("aid") or None},
                                             source="learned", origin="atlas:uimap", evidence=f"path read from the live window: {pth}")
                        n_cmds += 1
                    except Exception:
                        continue
        if gsum:
            try:
                store.put_claim(C.Claim(key, "ui.ribbon.tab" if s["kind"] == "ribbon-tab" else "ui.surface", f"{sname} ({s['kind']}) groups -> " + " || ".join(gsum)[:2200], "measured", 0.93,
                                        ev(sname, f"{len(s['groups'])} groups"), {"surface": sname, "kind": s["kind"], "groups": [g["name"] for g in s["groups"]]}, "atlas.uimap"))
                n_claims += 1
            except C.EvidenceRequired:
                pass
    return {"claims": n_claims, "commands": n_cmds}


# ---------------------------------------------------------------------------------------------- drive a learned route
def drive(hwnd: int, path: List[Dict[str, str]], *, settle_s: float = 0.7) -> Dict[str, Any]:
    """Follow a route from the map on the live window with UI Automation only (no pointer, no focus): select the tab, find the control (by id, else by name inside the
    ribbon region), expand it if the route goes through its items, find each item, invoke the last element. Returns what happened and what appeared."""
    from core_organs import fast_uia
    from core_organs import organ_63_app_mastery as m63
    rec: Dict[str, Any] = {"ok": False, "steps": []}
    names = [(p["kind"], p["name"]) for p in path if p["kind"] in ("surface", "group", "control", "item")]
    surface = next((n for k, n in names if k == "surface"), "")
    ctrl = next((n for k, n in names if k == "control"), "")
    items = [n for k, n in names if k == "item"]
    group = next((n for k, n in names if k == "group"), "")

    def snap():
        return fast_uia.snapshot(hwnd, timeout_ms=6000) or []

    def pick(nodes, name, ctypes_=None, grp=""):
        cands = [n for n in nodes if n.name == name and n.rect != (0, 0, 0, 0) and (not ctypes_ or n.ctype in ctypes_)]
        if grp and len(cands) > 1:
            def in_group(n):
                return any(a.ctype in GROUP_TYPES and a.name == grp for a in ancestors(nodes, n))
            g = [n for n in cands if in_group(n)]
            cands = g or cands
        cands.sort(key=lambda n: (not n.enabled, n.offscreen, n.depth))
        return cands[0] if cands else None

    before = snap()
    base_names = {(n.ctype, n.name) for n in before}
    if surface and any(n.ctype == "TabItemControl" and n.name == surface for n in before):
        tab = pick(before, surface, {"TabItemControl"})
        if tab is not None and not tab.selected:
            ok, how = m63._uia_call(tab, "GetSelectionItemPattern", "Select", wait_s=1.2)
            rec["steps"].append({"select_tab": surface, "ok": ok, "how": how})
            time.sleep(settle_s)
    elif surface and surface.lower() in ("file", "file tab"):
        pass
    nodes = snap()
    node = pick(nodes, ctrl, None, group)
    if node is None:
        rec["why"] = f"control '{ctrl}' not found (is the {surface} tab showing?)"
        return rec
    if not node.enabled:
        rec["why"] = f"control '{ctrl}' is disabled right now (it needs a selection or object first)"
        return rec
    if items:
        ok, how = m63._uia_call(node, "GetExpandCollapsePattern", "Expand", wait_s=1.2)
        rec["steps"].append({"expand": ctrl, "ok": ok, "how": how})
        if not ok:
            rec["why"] = how
            return rec
        time.sleep(settle_s)
        for i, nm in enumerate(items):
            cur = snap()
            cand = [n for n in cur if n.name == nm and n.rect != (0, 0, 0, 0) and n.ctype in ITEM_TYPES]
            it = sorted(cand, key=lambda n: (not n.enabled, n.offscreen))[0] if cand else None
            if it is None:
                rec["why"] = f"item '{nm}' not found under '{ctrl}'"
                return rec
            last = i == len(items) - 1
            if last:
                pats = [("invoke", "GetInvokePattern", "Invoke"), ("toggle", "GetTogglePattern", "Toggle"), ("select", "GetSelectionItemPattern", "Select")]
            else:
                pats = [("expand", "GetExpandCollapsePattern", "Expand"), ("invoke", "GetInvokePattern", "Invoke")]
            done = False
            for p, getter, call in pats:
                if p in it.pats:
                    ok, how = m63._uia_call(it, getter, call, wait_s=1.2)
                    rec["steps"].append({"item": nm, "call": call, "ok": ok, "how": how})
                    done = ok
                    break
            if not done:
                rec["why"] = f"item '{nm}' has no actionable pattern"
                return rec
            time.sleep(settle_s)
    else:
        for p, getter, call in (("invoke", "GetInvokePattern", "Invoke"), ("toggle", "GetTogglePattern", "Toggle"), ("select", "GetSelectionItemPattern", "Select"), ("expand", "GetExpandCollapsePattern", "Expand")):
            if p in node.pats:
                ok, how = m63._uia_call(node, getter, call, wait_s=1.2)
                rec["steps"].append({"control": ctrl, "call": call, "ok": ok, "how": how})
                if not ok:
                    rec["why"] = how
                    return rec
                break
        else:
            rec["why"] = f"'{ctrl}' has no actionable pattern"
            return rec
        time.sleep(settle_s)
    after = snap()
    rec["ok"] = True
    rec["new_controls"] = sorted({n.name for n in after if (n.ctype, n.name) not in base_names and n.name})[:20]
    return rec
