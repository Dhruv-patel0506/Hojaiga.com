import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/apprun.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep(r'''            if at.status in ("ok", "blocked"):
                break
            at.remedy = self._remedy(at.status)
            if at.remedy:
                self.say(f"    remedy: {at.remedy}")''', r'''            if at.status in ("ok", "blocked"):
                break
            at.remedy = self._remedy(at.status)
            if at.remedy:
                self.say(f"    remedy: {at.remedy}")
            prev = tr.attempts[-2] if len(tr.attempts) >= 2 else None
            if prev is not None and prev.status == at.status and prev.done == at.done and prev.why[:80] == at.why[:80]:
                self.say("    the same failure twice after a remedy: stopping (see the diagnosis)")
                at.remedy += " | repeated identically: no further attempts"
                break''')
rep(r'''    max_tasks: int = 14''', r'''    max_tasks: int = 30''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
