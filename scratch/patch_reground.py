import ast
import io


def patch(path, edits):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in edits:
        assert old in s, (path[-34:], old[:90])
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


B = "D:/new_automation/All codes/core_organs/professor/"
patch(B + "executor.py", [
    # live nodes: the main window AND the popups of the same process (open menus, flyouts, dialogs)
    ('''    def _live_node(self, v: Verb) -> Any:
        from core_organs import fast_uia
        nodes = fast_uia.snapshot(self.hwnd, timeout_ms=4000) or []
        return next((n for n in nodes if v.aid and n.aid == v.aid), None) or next((n for n in nodes if fold(n.name) == fold(v.label) and not n.offscreen), None)''',
     '''    def _all_nodes(self) -> List[Any]:
        """The window's tree PLUS the trees of its process's popups (an open menu, a flyout or a dialog is a separate top-level window that the main tree does not contain)."""
        from core_organs import fast_uia
        nodes = list(fast_uia.snapshot(self.hwnd, timeout_ms=4000) or [])
        try:
            from core_organs import headless_input as hin
            for w in hin.popup_windows(self.hwnd)[:6]:
                nodes += fast_uia.snapshot(w, timeout_ms=3000) or []
        except Exception:
            pass
        return nodes

    def _live_node(self, v: Verb) -> Any:
        nodes = self._all_nodes()
        return next((n for n in nodes if v.aid and n.aid == v.aid and not n.offscreen), None) or next((n for n in nodes if fold(n.name) == fold(v.label) and not n.offscreen), None)

    def refresh_catalog(self) -> int:
        """Add what is on screen NOW (including open menus / dialogs) to the catalog. Returns how many verbs were new."""
        from .harvest import harvest_tree
        try:
            fresh = harvest_tree(self.hwnd, self.app_key, nodes=self._all_nodes())
        except Exception:
            return 0
        have = {(tuple(v.path), fold(v.label)) for v in self.catalog.verbs}
        new = [v for v in fresh.verbs if (tuple(v.path), fold(v.label)) not in have]
        self.catalog.verbs += new
        return len(new)

    def _reground(self, st: Step) -> Optional[Step]:
        """A guide step that named a control which was not in the catalog when the plan was made (it lives in a menu / dialog that opens only after an earlier step): look again NOW."""
        from .knowledge import guide_steps as GS
        self.refresh_catalog()
        gs = GS.parse_line(st.goal, st.index + 1, st.cite)
        if gs is None:
            return None
        g = GS.ground_step(gs, self.catalog)
        if g.how in ("path", "label", "chord") and g.verb is not None:
            ns = self._step_for_verb(g.verb, st.goal, g.conf, "guide", st.cite, gs.action if gs.action in ("on", "off") else "", gs.text if (gs.action == "type" and gs.text) else "")
            ns.index = st.index
            ns.note = "grounded just in time (the control appeared after an earlier step)"
            return ns
        return None'''),
    # the run loop: unknown guide steps get one fresh look before the plan stops
    ('''        for st in rep.steps:
            t0 = time.time()
            label = st.verb or st.text or st.goal
            if st.kind == "unknown":
                rep.results.append(StepResult(st.index, label, "unknown", summary=st.note))''', '''        for si, st in enumerate(list(rep.steps)):
            t0 = time.time()
            if st.kind == "unknown" and st.source == "guide" and not rep.dry_run and st.goal:
                fresh = self._reground(st)
                if fresh is not None:
                    rep.steps[si] = st = fresh
            label = st.verb or st.text or st.goal
            if st.kind == "unknown":
                rep.results.append(StepResult(st.index, label, "unknown", summary=st.note))'''),
])
print("regrounding + popup-aware live nodes")
