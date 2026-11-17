import ast, io
P = "D:/new_automation/All codes/core_organs/professor/viz.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''        if n.role == "text" and not n.pats:
            continue
'''
new = '''        if n.role in ("text", "pane", "window", "group", "image", "custom", "menu", "document") or not (n.pats or n.role in ("button", "menuitem", "listitem", "checkbox", "radiobutton", "tabitem", "edit", "combobox")):
            continue                                    # a label inside a control repeats the control's own name: draw the control
'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
