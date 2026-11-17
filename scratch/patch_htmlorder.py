import ast, io
P = "D:/new_automation/All codes/core_organs/professor/runui.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '    pics = sorted(f for f in os.listdir(run_dir) if f.lower().endswith(".png") and not f.startswith("fail_"))'
new = '    pics = sorted((f for f in os.listdir(run_dir) if f.lower().endswith(".png")), key=lambda f: (0 if f.startswith("scan_") else 1, f))        # the scans first, then every flyout'
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
