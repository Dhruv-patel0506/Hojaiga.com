import ast, io
P = "D:/new_automation/All codes/core_organs/professor/executor.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''        if (v.role != "menu_item" or not v.command_id) and not (text and v.role in FIELD_ROLES):
            out.append(Route("control", v.label, 3, v.aid or v.label))
        if not text and (v.role in ("dropdown", "menu_item") or "menu" in (v.leads_to or "")):
            out.append(Route("expand", f"open '{v.label}' (ExpandCollapse)", 3, v.aid or v.label))'''
new = '''        opener = not text and (v.role in ("dropdown", "menu_item") or "menu" in (v.leads_to or ""))
        if opener and "menu" in (v.leads_to or ""):                                       # a control that EXPANDS (drop-down, split button): Expand opens it; Invoke may do nothing or perform its main action (measured on Paint's Rotate)
            out.append(Route("expand", f"open '{v.label}' (ExpandCollapse)", 3, v.aid or v.label))
        if (v.role != "menu_item" or not v.command_id) and not (text and v.role in FIELD_ROLES):
            out.append(Route("control", v.label, 3, v.aid or v.label))
        if opener and "menu" not in (v.leads_to or ""):
            out.append(Route("expand", f"open '{v.label}' (ExpandCollapse)", 3, v.aid or v.label))'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
