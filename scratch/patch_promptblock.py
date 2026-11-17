import ast, io
P = "D:/new_automation/All codes/core_organs/professor/knowledge/manual_rag.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''    ap = app if app in ix.apps() else ""
    res = ix.retrieve(question, ap, k, brain)'''
new = '''    if app not in ix.apps():
        return "", []                       # an application with no guide of its own gets NO excerpts: with 90 manuals indexed, a global search would quote some other program's manual at the learner
    res = ix.retrieve(question, app, k, brain)'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
