import ast, io
P = "D:/new_automation/All codes/core_organs/professor/executor.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''        node = self._live_node(v)
        if node is None:
            return False, "control not found in the live tree"
        if r.kind == "value":'''
new = '''        node = self._live_node(v)
        if node is None and v.path:                                             # the control lives in a closed menu / drop-down: open its path first (File > Page setup)
            opened = self._open_path(v)
            node = self._live_node(v) if opened else None
        if node is None:
            return False, "control not found in the live tree"
        if r.kind == "value":'''
assert old in s
s = s.replace(old, new, 1)
old = '''    def _deliver(self, v: Verb, r: Route) -> Tuple[bool, str]:'''
new = '''    def _open_path(self, v: Verb) -> bool:
        """Open the menu / drop-down / tab chain a verb lives under, outermost first, so that its item exists in the live tree. Returns whether anything was opened."""
        from . import menus as MN
        opened = False
        for name in v.path:
            nodes = self._all_nodes()
            cand = [n for n in nodes if fold(n.name) == fold(name) and not n.offscreen and n.enabled and n.rect[2] > n.rect[0]]
            if not cand:
                continue
            ok, how = MN._expand(self.fx, cand[0])
            opened = opened or ok
            time.sleep(0.55)
        return opened

    def _deliver(self, v: Verb, r: Route) -> Tuple[bool, str]:'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
