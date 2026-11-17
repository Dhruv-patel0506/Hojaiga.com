import ast, io
P = "D:/new_automation/All codes/core_organs/professor/executor.py"
s = io.open(P, "r", encoding="utf-8").read()
i0 = s.index("    def _settle(self, before: Any, max_s: float) -> Any:")
i1 = s.index("def milestone_checker")
new = '''    def _settle(self, before: Any, max_s: float, expect_change: bool = False) -> Any:
        """Wait until the application stops changing. With expect_change (the step opens a flyout / dialog: those take a moment, a first-time XAML flyout up to a second or more) a snapshot that
        still equals the one taken BEFORE the action is not 'nothing happened yet' - keep looking for up to max_s."""
        from .probe import snapshot
        end = time.time() + max_s
        last = None
        time.sleep(0.3)
        while time.time() < end:
            s = snapshot(self.hwnd)
            if expect_change and before is not None and s.sig == before.sig and len(s.windows) == len(before.windows):
                last = s
                time.sleep(0.3)
                continue
            if last is not None and s.sig == last.sig:
                return s
            last = s
            time.sleep(0.25)
        return last or snapshot(self.hwnd)


'''
s = s[:i0] + new + s[i1:]
old = '''                s1 = self._settle(s0, settle_s)
                d = delta(s0, s1)
                tried[-1] += f" => {d.effect()}"'''
new2 = '''                s1 = self._settle(s0, max(settle_s, 3.5) if r.kind in ("expand", "control") and (self._is_opener(v) or "menu" in (v.leads_to or "")) else settle_s,
                                  expect_change=r.kind in ("expand", "control") and (self._is_opener(v) or "menu" in (v.leads_to or "")))
                d = delta(s0, s1)
                tried[-1] += f" => {d.effect()}"'''
assert old in s
s = s.replace(old, new2, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
