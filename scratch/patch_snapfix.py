import ast, io
P = "D:/new_automation/All codes/core_organs/professor/executor.py"
s = io.open(P, "r", encoding="utf-8").read()
old = "        return snapshot(self.hwnd, extra=extra, **kw)"
new = "        if extra:\n            return snapshot(self.hwnd, extra=extra, **kw)\n        return snapshot(self.hwnd, **kw)"
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
