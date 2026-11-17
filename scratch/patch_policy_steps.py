import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch("D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py", [
    (r'''GESTURE_TARGETS = {''', r'''HUMAN_STEP_RX = [
    (re.compile(r"(?i)\b(choose|select|pick|browse|open)\b[^.]{0,40}\b(file|files|image|images|picture|photo|document|folder|your pc|your computer|from your (?:pc|computer|device)|this pc)\b"),
     "policy: the Professor never chooses the user's own files"),
    (re.compile(r"(?i)\b(sign in|log in|microsoft account|subscription|credits|upgrade|purchase|buy|premium)\b"), "policy: needs the user's account / subscription"),
]
GESTURE_TARGETS = {'''),
    (r'''    if st.action == "drag" or (not st.path and fold(st.target) in GESTURE_TARGETS):''', r'''    if st.chord and re.match(r"(?i)^(?:win|windows|cmd|meta)\b", st.chord):
        return Grounded(st, None, 0.0, "human", f"policy: {st.chord} is an operating-system shortcut, not one of the application's")
    for rx, why in HUMAN_STEP_RX:
        if rx.search(st.raw or ""):
            return Grounded(st, None, 0.0, "human", why)
    if st.action == "drag" or (not st.path and fold(st.target) in GESTURE_TARGETS):'''),
])
patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
    (r'''            elif g.how == "gesture":''', r'''            elif g.how == "human":
                s = Step(0, st.raw, None, "", [], "unknown", safety="sensitive", need_human=True, note=g.note, source="guide", cite=gp["cite"], target=st.target)
            elif g.how == "gesture":'''),
])
patch("D:/new_automation/All codes/core_organs/professor/apprun.py", [
    (r'''            if "pointer gesture" in (last.summary or ""):
                return "blocked", last.summary''', r'''            if "pointer gesture" in (last.summary or "") or (last.summary or "").startswith("policy:"):
                return "blocked", last.summary'''),
])
print("ok")
