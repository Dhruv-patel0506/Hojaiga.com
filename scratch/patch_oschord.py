import ast, io
P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py"
s = io.open(P, "r", encoding="utf-8").read()
old = 'if st.chord and re.match(r"(?i)^(?:win|windows|cmd|meta)\b", st.chord):'
assert old in s, "not found"
s = s.replace(old, 'if st.chord and re.search(r"(?i)(?:^|\+)(?:win|windows|cmd|meta|super)(?:\+|$)", st.chord):', 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
