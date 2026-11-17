import ast, io, re
P = "D:/new_automation/All codes/core_organs/professor/adapters/cdp.py"
s = io.open(P, "r", encoding="utf-8").read()
i0 = s.index("    def new_tab(")
i1 = s.index("    def close(self) -> None:\n        for p in list(self.pages.values()):")
blk = s[i0:i1].replace("except CdpError as exc:", "except Exception as exc:")
s = s[:i0] + blk + s[i1:]
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)

P = "D:/new_automation/All codes/core_organs/professor/adapters/chromium.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''            ok, _h = self.b.new_tab(url)
            if not ok:
                continue
            tg = self._await_target(url.rstrip("/"), need_title=True, seconds=4.0)'''
new = '''            ok, _h = self.b.new_tab(url)
            if not ok:
                if not self.b.alive():
                    raise BrowserGone(url)
                continue
            tg = self._await_target(url.rstrip("/"), need_title=True, seconds=4.0)'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
