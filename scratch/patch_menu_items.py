import re
base = r"D:\new_automation\All codes\core_organs\atlas"

# ---------------------------------------------------------------- explorer.py
p = base + r"\explorer.py"
s = open(p, encoding="utf-8").read()
old = '''    def learn_dialog(self, dlg: int, title: str, *, via: str, depth: int = 0, uia_blocked: bool = False) -> Dict[str, Any]:
        ctrls, how, nodes = self.read_surface(dlg, uia_first=not uia_blocked)'''
new = '''    FILE_DLG_RX = re.compile(r"^(file ?name|folder|save as type|files of type|file type)", re.I)

    def learn_dialog(self, dlg: int, title: str, *, via: str, depth: int = 0, uia_blocked: bool = False) -> Dict[str, Any]:
        ctrls, how, nodes = self.read_surface(dlg, uia_first=not uia_blocked)
        file_dlg = any(self.FILE_DLG_RX.search(c.get("name") or "") for c in ctrls)
        if file_dlg:                                      # a file chooser lists the USER'S files and folders: the structure (fields, buttons) is knowledge, the contents are personal
            ctrls = [c for c in ctrls if c["kind"] not in ("listitem", "treeitem", "grid", "tree", "list")]'''
assert old in s
s = s.replace(old, new, 1)
old = '''        info["cancel"] = next((c["name"] for c in ctrls if c["kind"] == "button" and CANCEL_RX.search(c["name"] or "")), None)'''
new = '''        info["file_dialog"] = file_dlg
        info["fields"] = [{"name": c["name"], "kind": c["kind"]} for c in all_ctrls if c.get("name") and c["kind"] not in ("listitem", "treeitem", "grid", "document") and not (file_dlg and c["kind"] == "list")][:80]
        info["cancel"] = next((c["name"] for c in ctrls if c["kind"] == "button" and CANCEL_RX.search(c["name"] or "")), None)'''
assert old in s
s = s.replace(old, new, 1)
old = '''rec.update(effect="dialog", dialog=title, **{k: v for k, v in info.items() if k in ("controls", "pages", "wizard", "master_detail")})'''
new = '''rec.update(effect="dialog", dialog=title, **{k: v for k, v in info.items() if k in ("controls", "pages", "wizard", "master_detail", "fields", "file_dialog", "commit", "cancel")})'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)

# ---------------------------------------------------------------- uimap.py
p = base + r"\uimap.py"
s = open(p, encoding="utf-8").read()
old = '''                    for k in ("dialog", "controls", "pages", "wizard", "master_detail"):
                        if rec.get(k) is not None:
                            lt[k] = rec[k]'''
new = '''                    for k in ("dialog", "controls", "pages", "wizard", "master_detail", "fields", "file_dialog", "commit", "cancel"):
                        if rec.get(k) is not None:
                            lt[k] = rec[k]'''
assert old in s
s = s.replace(old, new, 1)

new_methods = '''    def open_menu_items(self, surface: Dict[str, Any], tab_name: str) -> None:
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
                    self.act("open menu item %r > %r" % (c["name"], it["name"]))
                    try:
                        rec = self._reach_and_invoke(c, it["name"])
                    except Exception as exc:
                        rec = {"effect": "error", "why": "%s: %s" % (type(exc).__name__, str(exc)[:60])}
                    if rec:
                        it["leads_to"] = {k: v for k, v in rec.items() if k in ("effect", "dialog", "controls", "pages", "wizard", "master_detail", "fields", "file_dialog", "commit", "cancel", "why")}
                        it["leads_to"]["type"] = "dialog" if rec.get("effect") == "dialog" else "command"
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

    def restore_inline(self, node) -> None:'''
old = "    def restore_inline(self, node) -> None:"
assert old in s
s = s.replace(old, new_methods, 1)
old = '''                self.open_pending_dialogs(surf, None)
                self.map["surfaces"].append(surf)'''
new = '''                self.open_pending_dialogs(surf, None)
                self.open_menu_items(surf, tab.name)
                self.map["surfaces"].append(surf)'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
print("patched")
