import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/icon_detector.py"
s = io.open(P, "r", encoding="utf-8").read()
old = s[s.index("def _covered("):s.index("def augment(")]
new = '''def _covered(b: Box, cands: List[Any]) -> bool:
    """Is this detector box already a candidate? Kind-aware: a TEXT candidate next to an icon (a label) does not cover the icon, only a text box that (almost) contains it does;
    against icon / shape candidates an overlap or an offset duplicate (IoU >= 0.3) counts."""
    for c in cands:
        o = c.box
        if c.kind == "text":
            if b.overlap_frac(o) >= 0.7 or (o.overlap_frac(b) >= 0.85 and o.area >= 0.6 * b.area):
                return True
        elif b.iou(o) >= 0.3 or b.overlap_frac(o) >= 0.7 or (o.overlap_frac(b) >= 0.85 and o.area >= 0.4 * b.area):
            return True
    return False


'''
s = s.replace(old, new, 1)
s = s.replace("    existing = [c.box for c in cs.candidates]\n", "    existing = list(cs.candidates)\n", 1)
s = s.replace("        cs.candidates.append(CV.Candidate(b, \"icon\", round(float(c), 3), flags=[\"yolo\"]))\n        existing.append(b)\n",
              "        cand = CV.Candidate(b, \"icon\", round(float(c), 3), flags=[\"yolo\"])\n        cs.candidates.append(cand)\n        existing.append(cand)\n", 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("coverage rule is kind-aware")
