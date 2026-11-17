import ast, io
P = "D:/new_automation/All codes/core_organs/professor/apprun.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''                shutil.copytree(self.src, os.path.join(self.backup, "LocalState"))
                return {"backed_up": self.src}'''
new = '''                shutil.copytree(self.src, os.path.join(self.backup, "LocalState"))
                cleared = 0
                for sub in ("TabState", "WindowState"):                       # a fresh instance must not reopen the user's tabs: they are put back in after()
                    d = os.path.join(self.src, sub)
                    if os.path.isdir(d):
                        for f in os.listdir(d):
                            try:
                                os.remove(os.path.join(d, f))
                                cleared += 1
                            except OSError:
                                pass
                return {"backed_up": self.src, "cleared_for_a_fresh_instance": cleared}'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
