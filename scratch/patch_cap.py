import ast, io
P = "D:/new_automation/All codes/core_organs/professor/capture.py"
s = io.open(P, "r", encoding="utf-8").read()
old = "    if isolated or info.minimized or not info.visible:\n"
new = "    if isolated or info.minimized or not info.visible or info.box.overlap_frac(virtual_screen()) < 0.5:        # parked off-screen = not on a monitor: its own surface, never a screen grab\n"
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
