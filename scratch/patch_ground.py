import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py"
s = io.open(P, "r", encoding="utf-8").read()
old = r'''        return Grounded(st, None, c, "none", f"the manual says '{st.target}'; no such control is in the application's catalog (it may sit in a menu or dialog that is not open)")'''
new = r'''        if st.action == "type" and st.text:                                   # 'type Report': the typed literal needs no control of its own (it goes where the focus is - the field the previous step chose)
            return Grounded(st, None, 1.0, "typed", "text entry (the target word is the text itself)")
        return Grounded(st, None, c, "none", f"the manual says '{st.target}'; no such control is in the application's catalog (it may sit in a menu or dialog that is not open)")'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
