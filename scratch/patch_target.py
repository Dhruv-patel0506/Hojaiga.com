import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
    (r'''    prefer: str = ""                # the route that worked last time (tried first)
''', r'''    prefer: str = ""                # the route that worked last time (tried first)
    target: str = ""                # the interface term the MANUAL named for this step (kept when the step could not be grounded yet, so it can be grounded just in time)
'''),
    (r'''            else:
                s = Step(0, st.raw, None, "", [], "unknown", safety="unknown", need_human=True, note=g.note or "the manual's step matches no control", source="guide", cite=gp["cite"])
            s.index = len(out)''', r'''            else:
                s = Step(0, st.raw, None, "", [], "unknown", safety="unknown", need_human=True, note=g.note or "the manual's step matches no control", source="guide", cite=gp["cite"], target=st.target)
                s.text = st.text
            s.index = len(out)'''),
    (r'''        gs = GS.parse_line(st.goal, st.index + 1, st.cite)
        if gs is None:
            return None''', r'''        gs = GS.parse_line(st.goal, st.index + 1, st.cite)
        if gs is None:
            return None
        if st.target:                                                     # a sentence that named several fields produced several steps: each keeps ITS term
            gs.target = st.target
            gs.path = [p for p in gs.path if fold(p) == fold(st.target)] if len(gs.path) < 2 else gs.path
            if st.text:
                gs.text = st.text'''),
])
print("ok")
