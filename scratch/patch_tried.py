import ast, io
P = "D:/new_automation/All codes/core_organs/professor/executor.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''                s1 = self._settle(s0, settle_s)
                d = delta(s0, s1)
                self._log_attempt(st, v, r, how, s0, s1, d)
                if d.effect() == "no_effect":
                    continue'''
new = '''                s1 = self._settle(s0, settle_s)
                d = delta(s0, s1)
                tried[-1] += f" => {d.effect()}" + (f" ({d.summary()[:80]})" if d.effect() == "no_effect" else "")
                self._log_attempt(st, v, r, how, s0, s1, d)
                if d.effect() == "no_effect":
                    continue'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
