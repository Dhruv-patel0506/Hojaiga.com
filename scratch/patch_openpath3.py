import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/executor.py"
s = io.open(P, "r", encoding="utf-8").read()
i0 = s.index("    def _open_path(self, v: Verb) -> bool:")
i1 = s.index("    def _deliver(self, v: Verb, r: Route)")
new = r'''    def _flyout_has(self, label: str) -> bool:
        """Is an item of that name present in a POP-UP window right now (a flyout that is already open)?"""
        nodes = self._all_nodes()
        return any(fold(x.name) == label and not x.offscreen and x.name for x in nodes[self._main_n:])

    def _open_path(self, v: Verb) -> bool:
        """Open the menu / drop-down / tab chain a verb lives under, outermost first, so that its item exists in the live tree. A flyout that is already open is left alone (expanding it again
        toggles it shut); one that does not appear is collapsed and asked once more. Returns whether anything was opened."""
        from . import menus as MN
        opened = False
        chain = list(v.path) + [v.label]
        for i, name in enumerate(chain[:-1]):
            nxt = fold(chain[i + 1])
            if self._flyout_has(nxt):
                opened = True                                                  # already open (the previous step opened it and the foreground is held)
                continue
            nodes = self._all_nodes()
            cand = [n for n in nodes if fold(n.name) == fold(name) and not n.offscreen and n.enabled and n.rect[2] > n.rect[0]]
            if not cand:
                continue
            if i > 0 and len(cand) > 1:                                      # two openers may carry the same name ('More Options' of the Selection AND the Brushes group): take the one inside the group named before it
                grp = [n for n in nodes if fold(n.name) == fold(chain[i - 1]) and n.rect[2] > n.rect[0]]
                inside = [c for c in cand if any(g.rect[0] <= c.rect[0] and g.rect[1] <= c.rect[1] and c.rect[2] <= g.rect[2] and c.rect[3] <= g.rect[3] for g in grp)]
                cand = inside or cand
            cand = [c for c in cand if c.role in ("menuitem", "button", "splitbutton", "combobox", "tabitem", "listitem", "radiobutton") or "expand" in (c.pats or [])] or cand
            for attempt in (1, 2):
                ok, how = MN._expand(self.fx, cand[0])
                opened = opened or ok
                end = time.time() + 2.5
                while ok and time.time() < end:                                  # wait for the flyout's items to exist
                    time.sleep(0.25)
                    if self._flyout_has(nxt) or any(fold(x.name) == nxt and x.idx != cand[0].idx and not x.offscreen and x.rect[2] > x.rect[0] for x in self._all_nodes()):
                        break
                if self._flyout_has(nxt) or not ok:
                    break
                MN.collapse(cand[0], deadline_s=1.0)                              # it never showed: it may have been toggled shut - close it properly and ask once more
                time.sleep(0.4)
        return opened

'''
s = s[:i0] + new + s[i1:]
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
