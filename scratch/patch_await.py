import ast, io
P = "D:/new_automation/All codes/core_organs/professor/adapters/chromium.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''        while time.time() < end:
            for x in self.b.targets():
                if url_part in x.get("url", ""):'''
new = '''        while time.time() < end:
            try:
                targets = self.b.targets()
            except Exception:
                return last                                                # the browser stopped answering: the caller decides whether it is gone
            for x in targets:
                if url_part in x.get("url", ""):'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
