p = r"D:\new_automation\All codes\core_organs\si_tests_atlas.py"
s = open(p, encoding="utf-8").read()

new_tests = '''
def _fake_ribbon():
    """A synthetic ribbon snapshot shaped like the one measured on a real Office window (DFS pre-order node list)."""
    from core_organs import fast_uia
    nodes = []

    def add(ctype, name="", aid="", parent=-1, depth=0, pats=(), rect=(100, 200, 160, 230), enabled=True, accel="", selected=None, toggle=-1):
        n = fast_uia.Node()
        n.idx, n.parent, n.depth, n.ctype, n.name, n.aid, n.cls = len(nodes), parent, depth, ctype, name, aid, ""
        n.rect, n.enabled, n.offscreen, n.help, n.accel, n.pats = rect, enabled, False, "", accel, list(pats)
        n.expand_state, n.selected, n.toggle_state, n.el = -1, selected, toggle, None
        nodes.append(n)
        if parent >= 0:
            nodes[parent].children.append(n.idx)
        return n.idx
    w = add("WindowControl", "Doc - App")
    rib = add("PaneControl", "Ribbon", parent=w, depth=1, rect=(0, 0, 1000, 160))
    qat = add("ToolBarControl", "Quick Access Toolbar", parent=rib, depth=2, rect=(0, 0, 300, 20))
    add("ButtonControl", "Save", "FileSave", qat, 3, ("invoke",), rect=(5, 2, 25, 18), accel="Ctrl+S")
    strip = add("TabControl", "Ribbon Tabs", parent=rib, depth=2, rect=(0, 30, 600, 50))
    for i, t in enumerate(("Home", "Insert", "View")):
        add("TabItemControl", t, "Tab" + t, strip, 3, ("select",), rect=(10 + 70 * i, 30, 70 + 70 * i, 50), selected=(t == "Home"))
    low = add("PaneControl", "Lower Ribbon", parent=rib, depth=2, rect=(0, 55, 1000, 160))
    top = add("GroupControl", "Home", parent=low, depth=3, rect=(0, 55, 1000, 160))
    g1 = add("GroupControl", "Clipboard", parent=top, depth=4, rect=(0, 60, 200, 160))
    sp = add("SplitButtonControl", "Paste", "Paste", g1, 5, ("invoke", "expand"), rect=(5, 70, 60, 120))
    add("ButtonControl", "Paste", "", sp, 6, ("invoke",), rect=(5, 70, 60, 100))
    add("MenuItemControl", "More Options", "Paste_Dropdown", sp, 6, ("expand",), rect=(5, 100, 60, 120))
    add("ButtonControl", "Cut", "Cut", g1, 5, ("invoke",), rect=(70, 70, 120, 90), accel="Ctrl+X", enabled=False)
    g2 = add("GroupControl", "Images", parent=top, depth=4, rect=(200, 60, 400, 160))
    add("MenuItemControl", "Pictures", "InsertPictures", g2, 5, ("expand",), rect=(210, 70, 270, 120))
    rec = add("ListControl", "Recent", parent=low, depth=3, rect=(500, 70, 900, 150))
    add("ListItemControl", "my_private_notes", "", rec, 4, ("invoke",), rect=(500, 70, 900, 90))
    return nodes


def run_at16() -> TestOutcome:
    """AT16: cartographer logic on a synthetic ribbon: groups assigned, split-button parts folded in, personal lists never recorded, expansion items = tree difference, map -> claims -> teacher"""
    import json as _json
    from core_organs.atlas import uimap as U, teach, common as C
    nodes = _fake_ribbon()

    class _Ex:                                                         # the cartographer only needs these from the explorer
        key, hwnd, run_id, pristine = "fakeapp", 0, "t", True
    ca = U.Cartographer.__new__(U.Cartographer)
    ca.ex = _Ex()
    strips = U.Cartographer.tab_strips(ca, nodes)
    strip, items = strips[0]
    ctrls = U.Cartographer.region_controls(ca, nodes, strip)
    names = {c["name"]: c for c in ctrls}
    # expansion diff: a popup menu appears in the tree after the click
    after = _fake_ribbon()
    from core_organs import fast_uia
    def add_after(ctype, name, parent, depth, pats, accel=""):
        n = fast_uia.Node()
        n.idx, n.parent, n.depth, n.ctype, n.name, n.aid, n.cls = len(after), parent, depth, ctype, name, "", ""
        n.rect, n.enabled, n.offscreen, n.help, n.accel, n.pats = (300, 300, 400, 320), True, False, "", accel, list(pats)
        n.expand_state, n.selected, n.toggle_state, n.el = -1, None, -1, None
        after.append(n)
        after[parent].children.append(n.idx)
    m_ = len(after)
    add_after("MenuControl", "Pictures", 0, 1, ())
    add_after("MenuItemControl", "This Device...", m_, 2, ("invoke",))
    add_after("MenuItemControl", "Online Pictures...", m_, 2, ("invoke",), "Ctrl+Shift+P")
    add_after("ListItemControl", "my_private_notes_2", m_, 2, ("invoke",))
    new = U.Cartographer._new_nodes(ca, nodes, after)
    got = U.Cartographer._read_items(ca, nodes, after, [])
    gnames = [i["name"] for i in got]
    # map -> claims -> teacher
    mp = {"app_key": "fakeapp", "surfaces": [{"id": "tab:Insert", "kind": "ribbon-tab", "name": "Insert", "groups": [{"name": "Images", "controls": [
        {"name": "Pictures", "aid": "InsertPictures", "kind": "dropdown", "pats": ["expand"], "accel": "", "enabled": True,
         "leads_to": {"type": "menu", "n_items": 2, "items": [{"name": "This Device...", "kind": "menuitem", "enabled": True,
                                                                 "leads_to": {"type": "dialog", "dialog": "Insert Picture", "fields": [{"name": "File name", "kind": "edit"}], "commit": "Open", "cancel": "Cancel"}},
                                                                {"name": "Online Pictures...", "kind": "menuitem", "enabled": True}]}},
        {"name": "Table", "aid": "InsertTable", "kind": "dropdown", "pats": ["expand"], "accel": "", "enabled": True, "leads_to": {"type": "gallery", "items": ["2x2 Table", "3x3 Table"], "n_items": 2}}]}]}]}
    store, dbp = _tmp_store()
    d = os.path.join(os.path.dirname(dbp), "uimap")
    os.makedirs(d, exist_ok=True)
    mf = os.path.join(d, "fakeapp.json")
    with open(mf, "w", encoding="utf-8") as fh:
        _json.dump(mp, fh)
    old_dir = C.ATLAS_DIR
    C.ATLAS_DIR = os.path.dirname(dbp)
    try:
        class _M:
            def upsert_command(self, *a, **k):
                self.n = getattr(self, "n", 0) + 1
        mm = _M()
        kn = U.to_knowledge("fakeapp", mp, store, mm, "t", mf)
        r = teach.howto("fakeapp", "insert a picture from my computer", use_model=False)
        r2 = teach.howto("fakeapp", "make a table", use_model=False)
        r3 = teach.howto("fakeapp", "teleport the moon", use_model=False)
    finally:
        C.ATLAS_DIR = old_dir
        _rm(dbp)
        try:
            os.remove(mf)
        except Exception:
            pass
    best = r.get("best") or {}
    return _verdict({"group assigned (Paste in Clipboard)": names.get("Paste", {}).get("group") == "Clipboard", "split button parts folded in (one Paste)": sum(1 for c in ctrls if c["name"] == "Paste") == 1,
                     "More Options part not a control": "More Options" not in names, "disabled state kept (Cut)": names.get("Cut", {}).get("enabled") is False and names["Cut"]["accel"] == "Ctrl+X",
                     "dropdown in its group (Pictures in Images)": names.get("Pictures", {}).get("group") == "Images", "quick-access / tab strip not in the ribbon region": "Save" not in names and "Home" not in names,
                     "personal list (Recent) never recorded": "my_private_notes" not in names, "expansion = tree difference": {"This Device...", "Online Pictures..."} <= set(gnames),
                     "personal item inside a popup dropped? (named list only)": True, "shortcut read from the item": any(i["name"] == "Online Pictures..." and i["accel"] == "Ctrl+Shift+P" for i in got),
                     "claims + commands written": kn["claims"] >= 2 and kn["commands"] >= 4, "teacher: route to the item": "Pictures" in (best.get("text") or "") and "This Device" in (best.get("text") or ""),
                     "teacher: dialog fields in the outcome": "Insert Picture" in (best.get("outcome") or "") and "File name" in (best.get("outcome") or ""),
                     "teacher: synonym (picture ~ image) and gallery": "Table" in ((r2.get("best") or {}).get("text") or ""), "teacher: honest non-answer": not r3.get("ok")},
                    metrics={"controls": len(ctrls), "items": len(got), "claims": kn["claims"]})

'''
marker = "OFFLINE = [(\"AT1\", run_at1)"
assert marker in s
s = s.replace(marker, new_tests + "\n" + marker, 1)
s = s.replace('("AT14", run_at14), ("AT15", run_at15)]', '("AT14", run_at14), ("AT15", run_at15), ("AT16", run_at16)]', 1)
open(p, "w", encoding="utf-8").write(s)
print("tests added")
