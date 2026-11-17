import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py"
s = io.open(P, "r", encoding="utf-8").read()
old = r'''    if not act and not target and not chord and not path:
        return None
    if not act:
        act = "press" if chord else "click"'''
new = r'''    if not act and not target and not chord and not path:
        return None
    if not act and not (emph or _QUOTED.findall(txt) or path or chord or typed):
        return None                                                        # a clause with no action word and no marked-up interface term ('At the bottom right of a New Tab page') is context, not a step
    if not act:
        act = "press" if chord else "click"'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
