import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch("D:/new_automation/All codes/core_organs/professor/skills.py", [
    (r'''        if any(s.kind not in ("verb", "text") for s in steps):''', r'''        if any(s.kind not in ("verb", "text", "key") for s in steps):'''),
    (r'''    kind: str = "verb"                    # verb | text''', r'''    kind: str = "verb"                    # verb | text | key'''),
])
patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
    (r'''        for st in sk.steps:
            if st.kind == "text":''', r'''        for st in sk.steps:
            if st.kind == "key":
                out.append(Step(len(out), goal, None, "", [], "key", text=st.text, safety="safe", routes=[f"key:{st.text}"], expected=f"the {st.text} key is delivered", source=f"skill:{sk.id}"))
                continue
            if st.kind == "text":'''),
])
patch("D:/new_automation/All codes/core_organs/professor/apprun.py", [
    (r'''            if not ok or cover < 0.5:
                continue
            if g[0].how == "none" and not any(s.path for s in steps[:1]):
                pass                                                     # the first control may be in a closed menu: the executor re-grounds just in time''', r'''            if not ok or (cover < 0.5 and g[0].how == "none"):               # a procedure whose FIRST step grounds can ground the rest just in time (dialog fields appear only after the dialog opens)
                continue'''),
])
print("ok")
