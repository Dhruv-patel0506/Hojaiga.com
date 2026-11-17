import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
    (r'''        from core_organs import fast_uia
        nodes = list(fast_uia.snapshot(self.hwnd, timeout_ms=4000) or [])
        try:
            from core_organs import headless_input as hin
            for w in hin.popup_windows(self.hwnd)[:6]:
                nodes += fast_uia.snapshot(w, timeout_ms=3000) or []
        except Exception:
            pass
        return nodes''', r'''        from core_organs import fast_uia
        nodes = list(fast_uia.snapshot(self.hwnd, timeout_ms=4000) or [])
        self._main_n = len(nodes)                                          # nodes[_main_n:] belong to pop-up windows (flyouts, dialogs)
        try:
            from core_organs import headless_input as hin
            for w in hin.popup_windows(self.hwnd)[:6]:
                nodes += fast_uia.snapshot(w, timeout_ms=3000) or []
        except Exception:
            pass
        return nodes'''),
    (r'''    def _live_node(self, v: Verb) -> Any:
        nodes = self._all_nodes()
        return next(''', r'''    def _live_node(self, v: Verb) -> Any:
        nodes = self._all_nodes()
        if "menu-expand" in (v.sources or []):                           # an item read out of a flyout lives in the FLYOUT's window, never in the main window's gallery of the same name
            nodes = nodes[self._main_n:]
        return next('''),
    (r'''        self._last_verb: Optional[Verb] = None''', r'''        self._main_n = 0
        self._last_verb: Optional[Verb] = None'''),
])
patch("D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py", [
    (r'''        exact.sort(key=lambda v: (not v.enabled, v.safety != "safe", not (nearset and any(fold(p) in nearset for p in v.path)), len(v.path)))''',
     r'''        exact.sort(key=lambda v: (not v.enabled, v.safety != "safe", getattr(v, "trust", "measured") != "measured", not (nearset and any(fold(p) in nearset for p in v.path)), len(v.path)))'''),
])
patch("D:/new_automation/All codes/core_organs/professor/apprun.py", [
    (r'''        if st == "unknown":
            return "ungrounded", last.summary or rep.stopped''', r'''        if st == "unknown":
            if "pointer gesture" in (last.summary or ""):
                return "blocked", last.summary
            return "ungrounded", last.summary or rep.stopped'''),
])
print("ok")
