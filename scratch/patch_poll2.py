import ast, io
P = "D:/new_automation/All codes/core_organs/professor/executor.py"
s = io.open(P, "r", encoding="utf-8").read()
i0 = s.index("    def _open_path(self, v: Verb) -> bool:")
i1 = s.index("    def _deliver(self, v: Verb, r: Route)")
new = '''    def _open_path(self, v: Verb) -> bool:
        """Open the menu / drop-down / tab chain a verb lives under, outermost first, so that its item exists in the live tree. Returns whether anything was opened."""
        from . import menus as MN
        opened = False
        chain = list(v.path) + [v.label]
        for i, name in enumerate(chain[:-1]):
            nodes = self._all_nodes()
            cand = [n for n in nodes if fold(n.name) == fold(name) and not n.offscreen and n.enabled and n.rect[2] > n.rect[0]]
            if not cand:
                continue
            ok, how = MN._expand(self.fx, cand[0])
            opened = opened or ok
            nxt = fold(chain[i + 1])
            end = time.time() + 2.5
            while ok and time.time() < end:                                  # wait for the flyout's items to exist
                time.sleep(0.25)
                if any(fold(x.name) == nxt and not x.offscreen and x.rect[2] > x.rect[0] and x.ctype != cand[0].ctype or (fold(x.name) == nxt and x.idx != cand[0].idx and x.rect[0] >= 0) for x in self._all_nodes() if x.name):
                    break
        return opened

'''
s = s[:i0] + new + s[i1:]
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
