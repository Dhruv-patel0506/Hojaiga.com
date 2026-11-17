import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch("D:/new_automation/All codes/core_organs/professor/knowledge/guide_card.py", [
    (r'''                seq["grounded"] = round(sum(1 for x in g if x.how != "none") / len(g), 3)
                seq["unmatched"] = [x.step.target or x.step.raw[:40] for x in g if x.how == "none"]''', r'''                seq["grounded"] = round(sum(1 for x in g if x.how in GS.GROUNDED_HOW) / len(g), 3)
                seq["unmatched"] = [x.step.target or x.step.raw[:40] for x in g if x.how not in GS.GROUNDED_HOW]'''),
])
patch("D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py", [
    (r'''HUMAN_STEP_RX = [''', r'''GROUNDED_HOW = ("path", "label", "chord", "typed", "key")                    # 'none' / 'gesture' / 'human' are NOT grounded: nothing in the application answers them
HUMAN_STEP_RX = ['''),
    (r'''        ok = [x for x in g if x.how != "none"]
        cover = len(ok) / len(g)
        if not ok or cover < min_cover:''', r'''        ok = [x for x in g if x.how in GROUNDED_HOW]
        cover = len(ok) / len(g)
        if not ok or cover < min_cover:'''),
])
patch("D:/new_automation/All codes/core_organs/professor/apprun.py", [
    (r'''            g = GS.ground(steps, self.cat)
            ok = [x for x in g if x.how != "none"]''', r'''            g = GS.ground(steps, self.cat)
            ok = [x for x in g if x.how in GS.GROUNDED_HOW]'''),
])
print("ok")
