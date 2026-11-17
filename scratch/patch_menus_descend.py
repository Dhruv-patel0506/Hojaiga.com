import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/menus.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new, count=1):
    global s
    assert old in s, old[:80]
    s = s.replace(old, new, count)


# ------------------------------------------------------------------ module docs + constants
rep('''Each opener is one row in the history database (source 'menu-expand'), so the ML models also learn how openers behave per toolkit.
"""''', '''  descend(...)        inside an OPEN flyout, an item that is itself an opener (View > Zoom, Tools > Options > ...) is expanded, read and collapsed again - to a bounded depth.
Each opener is one row in the history database (source 'menu-expand'), so the ML models also learn how openers behave per toolkit.
"""''')

rep('''SKIP_OPENER_RX = re.compile(r"\\b(close|minimi[sz]e|maximi[sz]e|restore|system|exit|quit|sign|account|profile)\\b", re.I)
''', '''SKIP_OPENER_RX = re.compile(r"\\b(close|minimi[sz]e|maximi[sz]e|restore|system|exit|quit|sign|account|profile)\\b", re.I)
# a submenu that lists the USER'S OWN things (recent files, history, pinned items): reading it would copy file names out of the person's life into a catalog - it is named in the report and left closed
PRIVATE_RX = re.compile(r"\\b(recent|history|frequent|most used|jump ?list|pinned|last (?:opened|used)|favou?rites?|bookmarks?)\\b", re.I)
VERB_ROLE = {"menuitem": "menu_item", "tabitem": "tab", "listitem": "list_item", "radiobutton": "radio", "splitbutton": "dropdown", "combobox": "dropdown", "edit": "field", "treeitem": "tree_item"}
''')

# ------------------------------------------------------------------ helpers: add a verb, is a submenu
rep('''def _item_label(n: Any) -> Tuple[str, str]:''', '''def is_submenu(n: Any) -> bool:
    """An item inside an open flyout that opens another flyout (it offers ExpandCollapse)."""
    return n.role in ("menuitem", "button", "splitbutton", "combobox") and ("expand" in (n.pats or []) or getattr(n, "expand_state", None) in (0, 1, 2))


def add_item_verb(cat: Catalog, have: Set[Tuple[Tuple[str, ...], str]], vpath: Sequence[str], n: Any, source: str = "menu-expand") -> bool:
    """File one control read out of a flyout / dialog / page into the catalog under its path. False when it was filed already."""
    label, chord = _item_label(n)
    if not label or len(label) > 80:
        return False
    key = (tuple(vpath), fold(label))
    if key in have:
        return False
    have.add(key)
    nm, desc, tchord = split_tooltip(n.help) if n.help else ("", "", "")
    leads = "opens a dialog" if re.search(r"(\\.\\.\\.|…)\\s*$", n.name or "") else ("opens a submenu" if is_submenu(n) else "")
    cat.verbs.append(Verb(verb_id(list(vpath), label), re.sub(r"(\\.\\.\\.|…)\\s*$", "", label).strip(), list(vpath), chord or tchord, (desc or n.help or "").strip(), bool(n.enabled),
                          bool(n.selected) or n.toggle_state == 1, leads, 0, n.aid or "", VERB_ROLE.get(n.role, n.role), [source], "measured", safety.classify(label, " ".join(vpath))))
    return True


def _item_label(n: Any) -> Tuple[str, str]:''')

# ------------------------------------------------------------------ the descent
rep('''def expand_menus(fx: Any, hwnd: int, cat: Catalog,''', '''def _descend(fx: Any, all_nodes: Callable[[], List[Any]], cat: Catalog, have: Set[Tuple[Tuple[str, ...], str]], parent: Any, items: Sequence[Any], vpath: List[str], depth: int, max_depth: int,
             t_end: float, on_items: Optional[Callable[[Any, List[Any]], None]], rep: Dict[str, Any], reopen: Callable[[], None]) -> None:
    """The flyout of `parent` is open and shows `items`. Every item that opens a flyout of its own is expanded, read, drawn and collapsed - recursively, up to `max_depth` levels."""
    for it in list(items):
        if depth > max_depth or time.time() > t_end:
            return
        if not is_submenu(it) or not it.enabled or it.offscreen:
            continue
        label, _ = _item_label(it)
        if not label or fold(label) == fold(parent.name):
            continue
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


def expand_menus(fx: Any, hwnd: int, cat: Catalog,''')

rep('''log: Callable[[str], None] = lambda s: None, restore_popups: Optional[List[int]] = None, on_items: Optional[Callable[[Any, List[Any]], None]] = None) -> Dict[str, Any]:''',
    '''log: Callable[[str], None] = lambda s: None, restore_popups: Optional[List[int]] = None, on_items: Optional[Callable[[Any, List[Any]], None]] = None,
                 max_depth: int = 3) -> Dict[str, Any]:''')

rep('''    rep: Dict[str, Any] = {"openers": 0, "opened": 0, "items": 0, "dialog_openers": 0, "failed": [], "seconds": 0.0, "by_opener": {}}''',
    '''    rep: Dict[str, Any] = {"openers": 0, "opened": 0, "items": 0, "dialog_openers": 0, "submenus": 0, "failed": [], "skipped": [], "seconds": 0.0, "by_opener": {}, "read": []}''')

# the per-item loop becomes add_item_verb
old_start = s.index("        added = 0\n        for n in new:\n            label, chord = _item_label(n)")
old_end = s.index("        if on_items is not None and new:")
s = s[:old_start] + '''        added = 0
        vpath: List[str] = []
        for n in new:
            label, _chord = _item_label(n)
            if not label or fold(label) == fold(op.name):
                continue
            grp = next((g.name for g in groups if g.rect[0] <= op.rect[0] and g.rect[1] <= op.rect[1] and op.rect[2] <= g.rect[2] and op.rect[3] <= g.rect[3] and g.name != op.name), "")
            vpath = ([grp] if grp else []) + [op.name]                          # 'Selection > More Options > Rectangle': the group keeps two openers of the same name apart
            if add_item_verb(cat, have, vpath, n):
                added += 1
                rep["dialog_openers"] += 1 if re.search(r"(\\.\\.\\.|…)\\s*$", n.name or "") else 0
                rep["read"].append({"path": list(vpath), "label": label, "role": n.role, "pats": list(n.pats or []), "aid": n.aid or "", "enabled": bool(n.enabled)})
''' + s[old_end:]

# descend while the opener's flyout is open (just before the history row is written)
rep('''        rep["by_opener"][op.name] = added
        rep["items"] += added''', '''        rep["by_opener"][op.name] = added
        rep["items"] += added
        if ok and new and max_depth > 0:                                         # the flyout is still open: go into the items that open flyouts of their own
            def reopen(op=op, base=base) -> None:
                _expand(fx, op)
                _await_items(all_nodes, base, wait_s=2.0)
            try:
                with fx.holding():
                    _descend(fx, all_nodes, cat, have, op, new, vpath or [op.name], 1, max_depth, t0 + budget_s, on_items, rep, reopen)
            except Exception as exc:
                rep["failed"].append(f"{op.name}: submenu descent {type(exc).__name__}")''')

ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
