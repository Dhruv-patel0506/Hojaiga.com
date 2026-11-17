import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/reveal.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


# ---- simpler, fresher leave-button search over the live tree
rep('''        best = None
        for n in list(new) + [x for x in self.ex._all_nodes() if x not in new]:''', '''        best = None
        for n in self.ex._all_nodes():''')

# ---- _leave: re-select the tabs that were selected at home
rep('''    def _leave(self, new: Sequence[Any], s0: Any, home_ids: Set[Tuple[str, str, str]]) -> Tuple[str, bool, str]:
        """Go away from the surface and prove the application is back where it started. Returns (how, restored, what still differs)."""
        tol = 0.02 if len(s0.names) + len(s0.texts) >= 8 else 0.003
        tried: List[str] = []
        why: List[str] = []
        for how in ("button", "escape", "popups", "escape2"):''', '''    def _reselect(self, selected0: Sequence[Tuple[str, str, str]]) -> int:
        """Opening a path through a ribbon tab selects that tab: select the tab(s) that were selected at home again."""
        n_done = 0
        if not selected0:
            return 0
        for n in self.ex._all_nodes():
            if n.role == "tabitem" and MN._ident(n) in selected0 and n.selected is not True and n.enabled and not n.offscreen:
                ok, _how = self.fx.node(n)
                n_done += 1 if ok else 0
        return n_done

    def _leave(self, new: Sequence[Any], s0: Any, home_ids: Set[Tuple[str, str, str]], selected0: Sequence[Tuple[str, str, str]] = ()) -> Tuple[str, bool, str]:
        """Go away from the surface and prove the application is back where it started. Returns (how, restored, what still differs)."""
        tol = 0.02 if len(s0.names) + len(s0.texts) >= 8 else 0.003
        tried: List[str] = []
        why: List[str] = []
        for how in ("button", "escape", "popups", "reselect", "escape2"):''')
rep('''            elif how.startswith("escape"):
                self.fx.key("escape")
                tried.append("Escape")
            else:''', '''            elif how.startswith("escape"):
                self.fx.key("escape")
                tried.append("Escape")
            elif how == "reselect":
                if not self._reselect(selected0):
                    continue
                tried.append("re-selected the starting tab")
            else:''')

# ---- _try: tabs at home, fallback without the menu-expand source, kind by popup membership
rep('''        home_ids = {MN._ident(n) for n in self.ex._all_nodes()}
        v = Verb(''', '''        home_nodes = self.ex._all_nodes()
        home_ids = {MN._ident(n) for n in home_nodes}
        selected0 = {MN._ident(n) for n in home_nodes if n.role == "tabitem" and n.selected is True}
        v = Verb(''')
rep('''            node = self.ex._live_node(v)
            if node is None:
                out["kind"], out["how"] = "unreachable"''', '''            node = self.ex._live_node(v)
            if node is None and v.sources:                                        # a ribbon item read through its tab lives in the window, not in a flyout
                v.sources = []
                node = self.ex._live_node(v)
            if node is None:
                out["kind"], out["how"] = "unreachable"''')
rep('''        nodes1 = self.ex._all_nodes()
        new = [n for n in nodes1 if MN._ident(n) not in pre_ids and MN._ident(n) not in home_ids and n.name and not n.offscreen and n.rect[2] > n.rect[0] and n.role in SURFACE_ROLES]
        actionable = [n for n in new if n.role in MN.ITEM_ROLES]
        if d.new_windows or (len(self.ex._all_nodes()) > self.ex._main_n and actionable and any(n for n in nodes1[self.ex._main_n:] if MN._ident(n) in {MN._ident(a) for a in actionable})):
            kind = "dialog"''', '''        nodes1 = self.ex._all_nodes()
        main_n = self.ex._main_n
        fresh = [(i, n) for i, n in enumerate(nodes1) if MN._ident(n) not in pre_ids and MN._ident(n) not in home_ids and n.name and not n.offscreen and n.rect[2] > n.rect[0] and n.role in SURFACE_ROLES]
        new = [n for _i, n in fresh]
        actionable = [n for n in new if n.role in MN.ITEM_ROLES]
        in_popup = any(i >= main_n and n.role in MN.ITEM_ROLES for i, n in fresh)                    # its controls live in a window of their own: a dialog
        if d.new_windows or in_popup:
            kind = "dialog"''')
rep('''        how_left, restored, still = self._leave(new, s0, home_ids)''', '''        how_left, restored, still = self._leave(new, s0, home_ids, selected0)''')

ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
