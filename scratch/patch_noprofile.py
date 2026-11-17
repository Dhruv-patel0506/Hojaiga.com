import ast, io
P = "D:/new_automation/All codes/core_organs/professor/adapters/chromium.py"
s = io.open(P, "r", encoding="utf-8").read()
i0 = s.index("        # the profile picker is the browser's own 'Profile' bubble content")
i1 = s.index("        cat.sources[\"cdp\"] = cat.sources.get(\"cdp\", 0) + added\n        cat.verbs.sort(key=lambda v: (v.path, v.label.lower()))\n        return {\"destinations\"")
s = s[:i0] + s[i1:]
old = '''    def current(self) -> Optional[CdpPage]:
        t = self._target()
        if t is None:
            return None'''
new = '''    def current(self) -> Optional[CdpPage]:
        t = self._target()
        if t is None:                                                      # every tab is gone (a step closed them): the browser needs one to live - open a blank one
            try:
                self.b.new_tab("about:blank")
                t = self._target()
            except Exception:
                t = None
        if t is None:
            return None'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
