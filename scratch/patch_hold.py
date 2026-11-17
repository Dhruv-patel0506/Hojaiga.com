import ast, io

def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:80]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)

patch("D:/new_automation/All codes/core_organs/professor/effectors.py", [
('''        self.focus_returns = 0                             # how many times the target took the foreground and it was handed back
''', '''        self.focus_returns = 0                             # how many times the target took the foreground and it was handed back
        self._hold = 0                                     # >0 while a menu path is being opened and used: a flyout is dismissed the moment its window loses activation
'''),
('''    def restore_user_focus(self) -> bool:
        """Hand the foreground back to the user's window if the target's process holds it right now. True when it was handed back."""
        try:''', '''    @contextlib.contextmanager
    def holding(self, max_s: float = 6.0):
        """For the few seconds a flyout menu is open and being used: the foreground is NOT handed back (that would close the menu). It is handed back the moment this block ends."""
        self._hold += 1
        t0 = time.time()
        try:
            yield self
        finally:
            self._hold -= 1
            if self._hold <= 0:
                self._hold = 0
                time.sleep(0.15)
                self.restore_user_focus()
                self.log.append((time.time(), "hold released", True, f"held {time.time() - t0:.1f}s"))

    def restore_user_focus(self) -> bool:
        """Hand the foreground back to the user's window if the target's process holds it right now. True when it was handed back."""
        if self._hold:
            return False
        try:'''),
('''                    if cur and self._pid(cur) == self._pid(self.hwnd):
                        if time.time() - last > 0.2 and not self._user_busy():''', '''                    if cur and self._pid(cur) == self._pid(self.hwnd):
                        if time.time() - last > 0.2 and not self._user_busy() and not self._hold:'''),
('''        if not self.keep_focus:
            return
        try:
            time.sleep(0.12)                                # let the application react''', '''        if not self.keep_focus or self._hold:
            return
        try:
            time.sleep(0.12)                                # let the application react'''),
])

patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
('''        node = self._live_node(v)
        if node is None and v.path:                                             # the control lives in a closed menu / drop-down: open its path first (File > Page setup)
            opened = self._open_path(v)
            node = self._live_node(v) if opened else None
        if node is None:
            return False, "control not found in the live tree"
        if r.kind == "value":
            return self.fx.set_value(node, str(r.arg))
        return self.fx.node(node)''', '''        node = self._live_node(v)
        if node is None and v.path:                                             # the control lives in a closed menu / drop-down: open its path first (File > Page setup)
            with self.fx.holding():                                             # ...and use it before the foreground is handed back (that would close the flyout)
                opened = self._open_path(v)
                node = self._live_node(v) if opened else None
                if node is None:
                    return False, "control not found in the live tree (menu path opened: " + str(bool(opened)) + ")"
                if r.kind == "value":
                    return self.fx.set_value(node, str(r.arg))
                return self.fx.node(node)
        if node is None:
            return False, "control not found in the live tree"
        if r.kind == "value":
            return self.fx.set_value(node, str(r.arg))
        return self.fx.node(node)'''),
])
print("ok")
