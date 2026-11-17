import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch("D:/new_automation/All codes/core_organs/professor/effectors.py", [
    (r'''                cands = [n for n in nodes if "value" in (n.pats or []) and n.ctype in ("EditControl", "DocumentControl") and n.enabled and not n.offscreen and n.rect[2] > n.rect[0]]
                if not cands:
                    result["how"] = "no editable control with a value pattern"
                    return
''', r'''                def is_editor(n) -> bool:                                   # a DOCUMENT, or an edit big enough to be an editing surface (a 'Zoom' or 'Find' box is a field, not where text goes)
                    w, h = n.rect[2] - n.rect[0], n.rect[3] - n.rect[1]
                    return n.ctype == "DocumentControl" or (n.ctype == "EditControl" and w * h >= 40000 and h >= 60)
                cands = [n for n in nodes if "value" in (n.pats or []) and is_editor(n) and n.enabled and not n.offscreen and n.rect[2] > n.rect[0]]
                if not cands:
                    result["how"] = "no document / editor surface with a value pattern"
                    return
'''),
])

patch("D:/new_automation/All codes/core_organs/professor/apprun.py", [
    (r'''        for p in procs:
            steps = [s for s in p["steps"] if not (s.action == "open" and s.target and {w for w in re.findall(r"[a-z0-9]+", s.target.lower())} <= name_words)]
            if not steps:
                skip(p, "only says to open the application")
                continue''', r'''        for p in procs:
            steps = [s for s in p["steps"] if not (s.action == "open" and s.target and {w for w in re.findall(r"[a-z0-9]+", s.target.lower())} <= name_words)]
            if not steps:
                skip(p, "only says to open the application")
                continue
            if len(steps) < len(p["steps"]) and all(s.chord or s.action in ("press", "type") for s in steps):
                skip(p, "describes starting the application (Start menu), not using it")
                continue'''),
])
print("ok")
