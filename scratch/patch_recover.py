p = r"D:\new_automation\All codes\core_organs\atlas\uimap.py"
s = open(p, encoding="utf-8").read()

old = "    def group_signature(self, nodes, strip) -> Tuple[str, ...]:"
new = '''    def recover(self, why: str = "") -> bool:
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

    def group_signature(self, nodes, strip) -> Tuple[str, ...]:'''
assert old in s
s = s.replace(old, new, 1)

old = '''            cur = ex.snap(ms=6000)
            tab = next((n for n in cur if n.ctype == "TabItemControl" and n.name == name and "select" in n.pats), None)
            if tab is None:
                return cur, None, False'''
new = '''            cur = ex.snap(ms=6000)
            tab = next((n for n in cur if n.ctype == "TabItemControl" and n.name == name and "select" in n.pats), None)
            if tab is None and attempt == 0:
                self.recover(f"tab {name!r} not found ({len(cur)} nodes)")
                cur = ex.snap(ms=6000)
                tab = next((n for n in cur if n.ctype == "TabItemControl" and n.name == name and "select" in n.pats), None)
            if tab is None:
                self.map.setdefault("tab_diagnostics", []).append({"tab": name, "nodes": len(cur), "during": self.last_action,
                                                                   "windows": [X.Explorer._class_of(w) for w in ex.hin.process_windows(ex.hwnd, include_hidden=False)][:8]})
                return cur, None, False'''
assert old in s
s = s.replace(old, new, 1)

old = '''        self._item_cache: Dict[str, Dict[str, Any]] = {}
'''
new = '''        self._item_cache: Dict[str, Dict[str, Any]] = {}
        self.base_windows: Set[int] = set()
        self.base_popups: List[int] = []
'''
assert old in s
s = s.replace(old, new, 1)

old = '''        ex = self.ex
        self.map["workspace"] = self.ensure_workspace()'''
new = '''        ex = self.ex
        try:
            self.base_windows = set(ex.hin.process_windows(ex.hwnd, include_hidden=True))
            self.base_popups = ex.popups()
        except Exception:
            pass
        self.map["workspace"] = self.ensure_workspace()'''
assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
print("recover ok")
