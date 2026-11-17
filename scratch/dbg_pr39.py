import sys
import numpy as np
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import candidates as CD, synth, icon_detector as ID
img, truth, _ = synth.render_app("light", 1.0)
cs = CD.detect(img, 1.0, ocr=True, budget_s=30)
icons = [c for c in cs.candidates if c.kind == "icon" and 14 <= c.box.w <= 60]
victim = icons[len(icons) // 3]
rest = [c for c in cs.candidates if c is not victim]
ink = CD.ink_mask(np.asarray(img.convert("L")), 1.0)
print("victim", victim.box.to_list(), victim.kind, "ink", round(CD.ink_density(ink, victim.box), 3))
for c in rest:
    b = victim.box
    if b.iou(c.box) >= 0.25 or b.overlap_frac(c.box) >= 0.6 or c.box.overlap_frac(b) >= 0.6:
        print("  covered by", c.kind, c.box.to_list(), "iou", round(b.iou(c.box), 2), "ov", round(b.overlap_frac(c.box), 2), round(c.box.overlap_frac(b), 2))
print("n icons", len(icons), "total cands", len(cs.candidates))
