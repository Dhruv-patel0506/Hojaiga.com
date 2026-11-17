import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/icon_detector.py"
s = io.open(P, "r", encoding="utf-8").read()
old = s[s.index("def _covered("):s.index("def augment(")]
new = '''def _covered(b: Box, cands: List[Any]) -> bool:
    """Is this detector box already a candidate (the same control)? Kind-aware: against a TEXT candidate the box is covered when it lies inside the text or when the text is the label
    INSIDE this box (a tab / button around its caption); an icon merely NEXT to a label is not covered. Against icon / shape candidates any real overlap (offset duplicate) counts."""
    for c in cands:
        o = c.box
        if c.kind == "text":
            if b.overlap_frac(o) >= 0.7 or (o.overlap_frac(b) >= 0.85 and b.area <= 4.0 * o.area):
                return True
        elif b.iou(o) >= 0.15 or b.overlap_frac(o) >= 0.5 or o.overlap_frac(b) >= 0.5:
            return True
    return False


'''
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("coverage rule v2")
