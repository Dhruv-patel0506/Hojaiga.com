import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py"
s = io.open(P, "r", encoding="utf-8").read()
block = r'''    if st.chord and re.match(r"(?i)^(?:win|windows|cmd|meta)\b", st.chord):
        return Grounded(st, None, 0.0, "human", f"policy: {st.chord} is an operating-system shortcut, not one of the application's")
    for rx, why in HUMAN_STEP_RX:
        if rx.search(st.raw or ""):
            return Grounded(st, None, 0.0, "human", why)
'''
assert block in s
s = s.replace(block, "", 1)
anchor = r'''def ground_step(st: GuideStep, catalog: Any, near: Sequence[str] = ()) -> Grounded:
'''
assert anchor in s
s = s.replace(anchor, anchor + block, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
