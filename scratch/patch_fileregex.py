import ast, io
P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py"
s = io.open(P, "r", encoding="utf-8").read()
old = s[s.index("    (re.compile(r\"(?i)\b(choose|select|pick|browse|open)"):s.index("     \"policy: the Professor never chooses the user's own files\"),")]
new = '''    (re.compile(r"(?i)(\b(choose|select|pick|browse|open)\b[^.>]{0,30}\b(a|an|the|your|any)\s+(file|files|image|images|picture|photo|document|folder)\b|\bfrom\s+(your|this)\s+(pc|computer|device|drive))"),
'''
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
