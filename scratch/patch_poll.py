import ast, io

def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:80]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)

patch("D:/new_automation/All codes/core_organs/professor/menus.py", [
('''        ok, how = _expand(fx, op)
        time.sleep(0.55)
        nodes = all_nodes()
        new = [n for n in nodes if _ident(n) not in base and n.name and not n.offscreen and n.role in ITEM_ROLES]
''', '''        ok, how = _expand(fx, op)
        nodes, new = _await_items(all_nodes, base)
        if ok and not new:                                                       # a first-time flyout can be slow: ask once more
            ok, how = _expand(fx, op)
            nodes, new = _await_items(all_nodes, base, wait_s=2.5)
'''),
('''def _item_label(n: Any)''', '''def _await_items(all_nodes: Callable[[], List[Any]], base: Set[Tuple[str, str, str]], wait_s: float = 2.0, step_s: float = 0.25) -> Tuple[List[Any], List[Any]]:
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


def _item_label(n: Any)'''),
])
patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
('''            ok, how = MN._expand(self.fx, cand[0])
            opened = opened or ok
            time.sleep(0.55)
        return opened''', '''            ok, how = MN._expand(self.fx, cand[0])
            opened = opened or ok
            end = time.time() + 2.5
            while time.time() < end and ok:                                  # wait for the flyout's items to exist
                time.sleep(0.25)
                if self._live_node(v) is not None or any(fold(x.name) == fold(v.path[min(len(v.path) - 1, v.path.index(name) + 1)]) for x in self._all_nodes() if x.name and x.rect[2] > x.rect[0]):
                    break
        return opened'''),
])
print("ok")
