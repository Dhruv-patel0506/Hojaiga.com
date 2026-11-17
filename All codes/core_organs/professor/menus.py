"""
professor.menus -- READ THE MENUS THE TREE CANNOT SEE.

An accessibility tree lists what is on screen. A closed menu, drop-down or ribbon tab lists nothing: 'File > Page Setup' is not in the tree until File is opened. A guide speaks in those paths
('Select Page Setup from the File menu'), so before a guide can be run the openers have to be opened ONCE, their items read, and the menu closed again.

  expand_menus(...)   for every opener in a window the Professor OWNS (a node that offers ExpandCollapse - menu-bar items, drop-down and split buttons - and, in a ribbon application, the
                      ribbon tabs): open it with the ExpandCollapse pattern (never Invoke: a split button's Invoke performs its main action), read the new items from the window and its
                      pop-up windows, add them to the catalog as verbs with path [opener], close it, verify the application is back where it was. Items are never activated.
  descend(...)        inside an OPEN flyout, an item that is itself an opener (View > Zoom, Tools > Options > ...) is expanded, read and collapsed again - to a bounded depth.
Each opener is one row in the history database (source 'menu-expand'), so the ML models also learn how openers behave per toolkit.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from .harvest import Catalog, Verb, verb_id, chords_in, normalize_chord, split_tooltip
from .schema import fold
from . import safety

ITEM_ROLES = {"menuitem", "button", "listitem", "checkbox", "radiobutton", "hyperlink", "splitbutton", "combobox", "edit", "tabitem", "treeitem", "slider", "spinner"}
DOC_TAB_RX = re.compile(r"(untitled|unmodified|\.(txt|md|docx?|xlsx?|pptx?|png|jpe?g|json|py|log)\b|\bmodified\b|\bnew tab\b|^tab \d+)", re.I)
SKIP_OPENER_RX = re.compile(r"\b(close|minimi[sz]e|maximi[sz]e|restore|system|exit|quit|sign|account|profile)\b", re.I)
# a submenu that lists the USER'S OWN things (recent files, history, pinned items): reading it would copy file names out of the person's life into a catalog - it is named in the report and left closed
PRIVATE_RX = re.compile(r"\b(recent|history|frequent|most used|jump ?list|pinned|last (?:opened|used))\b", re.I)
VERB_ROLE = {"menuitem": "menu_item", "tabitem": "tab", "listitem": "list_item", "radiobutton": "radio", "splitbutton": "dropdown", "combobox": "dropdown", "edit": "field", "treeitem": "tree_item"}


def _ident(n: Any) -> Tuple[str, str, str]:
    return (n.aid or "", fold(n.name), n.ctype)


NAV_OPENER_RX = re.compile(r"(?i)\b(navigation|nav\b|toggle pane|open navigation|main menu)\b")
NAV_AID_RX = re.compile(r"(?i)(togglepane|navbutton|hamburger|navigationbutton)")


def _is_opener(n: Any) -> bool:
    if not n.name or n.offscreen or not n.enabled or SKIP_OPENER_RX.search(n.name):
        return False
    pats = set(getattr(n, "pats", []) or [])
    has_expand = "expand" in pats or getattr(n, "expand_state", None) in (0, 1, 2)
    is_nav = bool(NAV_OPENER_RX.search(n.name) or (getattr(n, "aid", None) and NAV_AID_RX.search(n.aid)))
    return n.role in ("menuitem", "button", "splitbutton", "combobox", "tabitem", "radiobutton", "listitem", "checkbox", "treeitem") and (has_expand or n.role == "menuitem" or is_nav)



def find_openers(nodes: Sequence[Any], ribbon: Optional[bool] = None, exclude: Optional[Callable[[Any], bool]] = None) -> List[Any]:
    """Every node worth opening once. Tab items count only when they are the tabs of a RIBBON - recognised by its structure (professor.ribbon.detect: a strip of tabs over named groups of
    controls, no per-tab close button), never by tab names. `exclude`: nodes another pass reads (a ribbon walked tab by tab)."""
    tab_names: Set[str] = set()
    if ribbon is None or ribbon:
        from .ribbon import detect
        rib = detect(nodes)
        if rib is not None:
            tab_names = {fold(t.name) for t in rib.tabs}
    out: List[Any] = []
    seen: Set[Any] = set()
    for n in nodes:
        if exclude is not None and exclude(n):
            continue
        if n.role == "tabitem":
            if ribbon is False or DOC_TAB_RX.search(n.name) or fold(n.name) not in tab_names:
                continue
        elif not _is_opener(n):
            continue
        key = (fold(n.name), n.rect[0] // 40, n.rect[1] // 40)                 # the same name in two places ('More Options' under Selection and under Brushes) is two openers
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def _expand(fx: Any, n: Any, deadline_s: float = 2.0) -> Tuple[bool, str]:
    """Open an opener WITHOUT performing its main action: ExpandCollapse.Expand / SelectionItem.Select for a tab; Invoke only for a plain menu item (opening its flyout is all it does)."""
    if not fx.allowed:
        return False, "refused: " + fx.why_not()
    try:
        ctrl = n.ctrl
        from .effectors import pattern_of
        if n.role in ("tabitem", "listitem") and not ("expand" in (n.pats or []) and n.role == "listitem"):
            p = pattern_of(ctrl, "SelectionItem")
            if p is not None:
                p.Select()                                                  # a tab, or a navigation list's item (Settings 'System' -> its page with 'Power & battery')
                return True, f"UIA Select ({'tab' if n.role == 'tabitem' else 'navigation item'})"
        p = pattern_of(ctrl, "ExpandCollapse") if ("expand" in (n.pats or []) or getattr(n, "expand_state", None) in (0, 1, 2)) else None
        if p is not None:
            p.Expand()
            return True, "UIA Expand"
        is_nav = bool(NAV_OPENER_RX.search(n.name) or (getattr(n, "aid", None) and NAV_AID_RX.search(n.aid)))
        if n.role in ("menuitem", "button", "splitbutton") or is_nav or "invoke" in (n.pats or []):
            p = pattern_of(ctrl, "Invoke")
            if p is not None:
                p.Invoke()
                return True, f"UIA Invoke ({'nav' if is_nav else n.role})"
        try:
            lp = pattern_of(ctrl, "LegacyIAccessible")
            if lp is not None and getattr(lp, "DefaultAction", ""):
                lp.DoDefaultAction()
                return True, f"UIA LegacyIAccessible.DoDefaultAction ({lp.DefaultAction})"
        except Exception:
            pass
    except Exception:
        pass
    res: Dict[str, str] = {}

    def work() -> None:
        try:
            import uiautomation as _ua
            with _ua.UIAutomationInitializerInThread():
                ctrl = n.ctrl
                from .effectors import pattern_of
                if n.role in ("tabitem", "listitem") and not ("expand" in (n.pats or []) and n.role == "listitem"):
                    p = pattern_of(ctrl, "SelectionItem")
                    if p is not None:
                        p.Select()                                                  # a tab, or a navigation list's item (Settings 'System' -> its page with 'Power & battery')
                        res["how"] = f"UIA Select ({'tab' if n.role == 'tabitem' else 'navigation item'})"
                        return
                p = pattern_of(ctrl, "ExpandCollapse") if ("expand" in (n.pats or []) or getattr(n, "expand_state", None) in (0, 1, 2)) else None
                if p is not None:
                    p.Expand()
                    res["how"] = "UIA Expand"
                    return
                is_nav = bool(NAV_OPENER_RX.search(n.name) or (getattr(n, "aid", None) and NAV_AID_RX.search(n.aid)))
                if n.role in ("menuitem", "button", "splitbutton") or is_nav or "invoke" in (n.pats or []):
                    p = pattern_of(ctrl, "Invoke")
                    if p is not None:
                        p.Invoke()
                        res["how"] = f"UIA Invoke ({'nav' if is_nav else n.role})"
                        return
                try:
                    lp = pattern_of(ctrl, "LegacyIAccessible")
                    if lp is not None and getattr(lp, "DefaultAction", ""):
                        lp.DoDefaultAction()
                        res["how"] = f"UIA LegacyIAccessible.DoDefaultAction ({lp.DefaultAction})"
                        return
                except Exception:
                    pass
                res["how"] = "no safe opener pattern"
        except Exception as exc:
            res["how"] = f"UIA error {type(exc).__name__}"

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(deadline_s)
    how = res.get("how", "UIA call still running")
    return how.startswith("UIA ") and "error" not in how, how


def _await_items(all_nodes: Callable[[], List[Any]], base: Set[Tuple[str, str, str]], wait_s: float = 2.0, step_s: float = 0.25) -> Tuple[List[Any], List[Any]]:
    """Poll until items that were not there before appear and their number stops growing (a flyout builds its items a moment after it opens)."""
    end = time.time() + wait_s
    last = -1
    nodes: List[Any] = []
    new: List[Any] = []
    time.sleep(step_s)
    while True:
        nodes = all_nodes()
        new = [n for n in nodes if _ident(n) not in base and n.name and not n.offscreen and n.role in ITEM_ROLES]
        if new and len(new) == last:
            return nodes, new
        last = len(new)
        if time.time() > end:
            return nodes, new
        time.sleep(step_s)


def collapse(n: Any, deadline_s: float = 1.5) -> bool:
    """Close an opener again through ExpandCollapse.Collapse: a combo-box or drop-down popup does not always follow Escape (it needs focus), the pattern always works."""
    try:
        from .effectors import pattern_of
        p = pattern_of(n.ctrl, "ExpandCollapse")
        if p is not None:
            p.Collapse()
            return True
        is_nav = bool(NAV_OPENER_RX.search(n.name) or (getattr(n, "aid", None) and NAV_AID_RX.search(n.aid)))
        if is_nav or n.role in ("menuitem", "button", "splitbutton") or "invoke" in (n.pats or []):
            p = pattern_of(n.ctrl, "Invoke")
            if p is not None:
                p.Invoke()
                return True
    except Exception:
        pass
    res: Dict[str, bool] = {}

    def work() -> None:
        try:
            import uiautomation as _ua
            with _ua.UIAutomationInitializerInThread():
                from .effectors import pattern_of
                p = pattern_of(n.ctrl, "ExpandCollapse")
                if p is not None:
                    p.Collapse()
                    res["ok"] = True
                    return
                is_nav = bool(NAV_OPENER_RX.search(n.name) or (getattr(n, "aid", None) and NAV_AID_RX.search(n.aid)))
                if is_nav or n.role in ("menuitem", "button", "splitbutton") or "invoke" in (n.pats or []):
                    p = pattern_of(n.ctrl, "Invoke")
                    if p is not None:
                        p.Invoke()
                        res["ok"] = True
                        return
        except Exception:
            res["ok"] = False

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(deadline_s)
    return bool(res.get("ok"))


def is_submenu(n: Any) -> bool:
    """An item inside an open flyout that opens another flyout (it offers ExpandCollapse)."""
    return n.role in ("menuitem", "button", "splitbutton", "combobox") and ("expand" in (n.pats or []) or getattr(n, "expand_state", None) in (0, 1, 2))


def add_item_verb(cat: Catalog, have: Set[Tuple[Tuple[str, ...], str]], vpath: Sequence[str], n: Any, source: str = "menu-expand") -> bool:
    """File one control read out of a flyout / dialog / page into the catalog under its path. False when it was filed already."""
    label, chord = _item_label(n)
    if not label or len(label) > 80:
        return False
    from .privacy import looks_private
    if looks_private(label):                                                   # the title of a window the person has open (a 'Screenshot' gallery lists them): never filed
        return False
    key = (tuple(vpath), fold(label))
    if key in have:
        return False
    have.add(key)
    nm, desc, tchord = split_tooltip(n.help) if n.help else ("", "", "")
    leads = "opens a dialog" if re.search(r"(\.\.\.|…)\s*$", n.name or "") else ("opens a submenu" if is_submenu(n) else "")
    cat.verbs.append(Verb(verb_id(list(vpath), label), re.sub(r"(\.\.\.|…)\s*$", "", label).strip(), list(vpath), chord or tchord, (desc or n.help or "").strip(), bool(n.enabled),
                          bool(n.selected) or n.toggle_state == 1, leads, 0, n.aid or "", VERB_ROLE.get(n.role, n.role), [source], "measured", safety.classify(label, " ".join(vpath))))
    return True


def _item_label(n: Any) -> Tuple[str, str]:
    """(label, shortcut): XAML menu items put the accelerator in the name ('Open\tCtrl+O'), in AcceleratorKey, or in a help text."""
    name = re.sub(r"\s+", " ", (n.name or "").replace("\t", " ").replace("&", "")).strip()
    sc = n.accel or ""
    ch = chords_in(name)
    if ch and not sc:
        sc = ch[0]
    if ch:
        name = re.sub(r"\s*\(?" + re.escape(ch[0]).replace(r"\+", r"\s*\+\s*") + r"\)?\s*$", "", name, flags=re.I).strip() or name
    return name, (normalize_chord(sc) if sc else "")


def _descend(fx: Any, all_nodes: Callable[[], List[Any]], cat: Catalog, have: Set[Tuple[Tuple[str, ...], str]], parent: Any, items: Sequence[Any], vpath: List[str], depth: int, max_depth: int,
             t_end: float, on_items: Optional[Callable[[Any, List[Any]], None]], rep: Dict[str, Any], reopen: Callable[[], None]) -> None:
    """The flyout of `parent` is open and shows `items`. Every item that opens a flyout of its own is expanded, read, drawn and collapsed - recursively, up to `max_depth` levels."""
    seen: Set[str] = set()                                                        # a XAML flyout can be listed twice (its popup window and its host): one visit per name
    for it in list(items):
        if depth > max_depth or time.time() > t_end:
            return
        if not is_submenu(it) or not it.enabled or it.offscreen:
            continue
        label, _ = _item_label(it)
        if not label or fold(label) == fold(parent.name) or fold(label) in seen:
            continue
        seen.add(fold(label))
        child_path = list(vpath) + [label]
        if PRIVATE_RX.search(label):
            rep["skipped"].append({"path": " > ".join(child_path), "why": "lists the person's own files / history - left closed"})
            continue
        base = {_ident(n) for n in all_nodes()}
        ok, how = _expand(fx, it)
        _nodes, sub = _await_items(all_nodes, base)
        if ok and not sub:                                                        # a submenu can be slow to build the first time
            ok, how = _expand(fx, it)
            _nodes, sub = _await_items(all_nodes, base, wait_s=2.5)
        sub = [n for n in sub if fold(_item_label(n)[0]) != fold(label)]
        added = 0
        for n in sub:
            added += 1 if add_item_verb(cat, have, child_path, n) else 0
        rep["submenus"] += 1
        rep["items"] += added
        rep["by_opener"][" > ".join(child_path)] = added
        if not ok:
            rep["failed"].append(f"{' > '.join(child_path)}: {how}")
        if on_items is not None and sub:
            try:
                on_items(it, sub)
            except Exception:
                pass
        if sub:
            _descend(fx, all_nodes, cat, have, it, sub, child_path, depth + 1, max_depth, t_end, on_items, rep, reopen)
        if ok:
            collapse(it)
            time.sleep(0.25)
        if not any(_ident(x) == _ident(it) and not x.offscreen for x in all_nodes()):          # collapsing the child took the parent's flyout with it: open the parent again
            reopen()


def expand_menus(fx: Any, hwnd: int, cat: Catalog, all_nodes: Callable[[], List[Any]], budget_s: float = 45.0, max_openers: int = 24, history: Any = None, toolkit: str = "",
                 log: Callable[[str], None] = lambda s: None, restore_popups: Optional[List[int]] = None, on_items: Optional[Callable[[Any, List[Any]], None]] = None,
                 max_depth: int = 3, exclude: Optional[Callable[[Any], bool]] = None, ribbon: Optional[bool] = None, done: Optional[Set[Tuple[str, str]]] = None) -> Dict[str, Any]:
    """Open each opener once, read its items into `cat`, close it. Only for windows the caller OWNS (the effector refuses otherwise). `done` = {(fold(opener), fold(group))} pairs an
    earlier run of this build already read (carried in from its saved catalog): those openers are NOT opened again - the repeat run starts guiding in minutes, not in half an hour. Returns a report."""
    from .probe import snapshot, delta
    t0 = time.time()
    rep: Dict[str, Any] = {"openers": 0, "opened": 0, "items": 0, "dialog_openers": 0, "submenus": 0, "failed": [], "skipped": [], "seconds": 0.0, "by_opener": {}, "read": [], "reused": 0}
    base_nodes = all_nodes()
    openers = [n for n in find_openers(base_nodes, ribbon=ribbon, exclude=exclude) if (n.rect[2] > n.rect[0] or (n.pats and any(p in n.pats for p in ("expand", "invoke", "select"))))][:max_openers]
    groups = [g for g in base_nodes if g.ctype == "GroupControl" and g.name and g.rect[2] > g.rect[0]]
    have = {(tuple(v.path), fold(v.label)) for v in cat.verbs}
    before_popups = set(restore_popups or [])
    for op in openers:
        if time.time() - t0 > budget_s:
            rep["failed"].append("time budget reached")
            break
        grp0 = next((g.name for g in groups if g.rect[0] <= op.rect[0] and g.rect[1] <= op.rect[1] and op.rect[2] <= g.rect[2] and op.rect[3] <= g.rect[3] and g.name != op.name), "")
        if done and (fold(op.name), fold(grp0)) in done:                        # this build already gave us this flyout: carried in, no need to open it again
            rep["reused"] += 1
            rep["skipped"].append({"path": (grp0 + " > " if grp0 else "") + op.name, "why": "read by an earlier run of this build (carried in)"})
            continue
        rep["openers"] += 1
        base = {_ident(n) for n in all_nodes()}
        s0 = snapshot(hwnd)
        ok, how = _expand(fx, op)
        nodes, new = _await_items(all_nodes, base)
        if ok and not new:                                                       # a first-time flyout can be slow: ask once more
            ok, how = _expand(fx, op)
            nodes, new = _await_items(all_nodes, base, wait_s=2.5)
        s1 = snapshot(hwnd)
        d = delta(s0, s1)
        added = 0
        vpath: List[str] = []
        for n in new:
            label, _chord = _item_label(n)
            if not label or fold(label) == fold(op.name):
                continue
            grp = next((g.name for g in groups if g.rect[0] <= op.rect[0] and g.rect[1] <= op.rect[1] and op.rect[2] <= g.rect[2] and op.rect[3] <= g.rect[3] and g.name != op.name), "")
            vpath = ([grp] if grp else []) + [op.name]                          # 'Selection > More Options > Rectangle': the group keeps two openers of the same name apart
            if add_item_verb(cat, have, vpath, n):
                added += 1
                rep["dialog_openers"] += 1 if re.search(r"(\.\.\.|…)\s*$", n.name or "") else 0
                rep["read"].append({"path": list(vpath), "label": label, "role": n.role, "pats": list(n.pats or []), "aid": n.aid or "", "enabled": bool(n.enabled)})
        if on_items is not None and new:
            try:
                on_items(op, new)                                                # the flyout is OPEN right now: a picture of it can be taken
            except Exception:
                pass
        rep["by_opener"][op.name] = added
        rep["items"] += added
        if ok and new and max_depth > 0:                                         # the flyout is still open: go into the items that open flyouts of their own
            def reopen(op=op, base=base) -> None:
                _expand(fx, op)
                _await_items(all_nodes, base, wait_s=2.0)
            try:
                with fx.holding():
                    _descend(fx, all_nodes, cat, have, op, new, vpath or [op.name], 1, max_depth, min(t0 + budget_s, time.time() + 15.0), on_items, rep, reopen)      # the descent of ONE opener may not starve the openers after it
            except Exception as exc:
                rep["failed"].append(f"{op.name}: submenu descent {type(exc).__name__}")
        rep["opened"] += 1 if (ok and (added or d.effect() != "no_effect")) else 0
        if not ok:
            rep["failed"].append(f"{op.name}: {how}")
        if history is not None:
            try:
                history.log(cat.app_key, "menu-expand", "expand", op.name, "uia-expand", s0.sig, f"{len(s0.names)} controls", s1.sig, d.summary()[:120], d.effect(), ok and added > 0, None, op.aid or "",
                            {"how": how, "items": added}, toolkit=toolkit, role=("tab" if op.role == "tabitem" else "menu_item"), safety="safe")
            except Exception:
                pass
        # close it again and make sure the application is back where it was
        for tries in range(3):
            if op.role != "tabitem" and ok:
                collapse(op)
                time.sleep(0.25)
            else:
                try:
                    fx.key("escape")
                except Exception:
                    pass
                time.sleep(0.2)
            if op.role == "tabitem":
                break
            if tries >= 1:
                try:
                    fx.key("escape")
                except Exception:
                    pass
            snap = snapshot(hwnd)
            if delta(s0, snap).effect() == "no_effect" or len(snap.windows) <= len(s0.windows):
                break
        try:
            fx.close_popups(list(before_popups))
        except Exception:
            pass
    cat.sources["menu-expand"] = cat.sources.get("menu-expand", 0) + rep["items"]
    cat.verbs.sort(key=lambda v: (v.path, v.label.lower()))
    rep["seconds"] = round(time.time() - t0, 1)
    return rep
