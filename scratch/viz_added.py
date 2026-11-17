import sys
import numpy as np
from PIL import Image, ImageDraw
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import candidates as CD, icon_detector as ID

img = Image.open("D:/new_automation/scratch/blender_cap_0.png").convert("RGB")
cs = CD.detect(img, 1.0, ocr=True, budget_s=40)
n0 = len(cs.candidates)
ink = CD.ink_mask(np.asarray(img.convert("L")), 1.0)
rep = ID.augment(cs, img, 1.0, ink, conf=0.3, budget_s=120)
new = cs.candidates[n0:]
print("cv", n0, "added", rep)
vis = img.copy()
d = ImageDraw.Draw(vis)
for c in cs.candidates[:n0]:
    d.rectangle([c.box.x1, c.box.y1, c.box.x2, c.box.y2], outline=(0, 200, 0), width=1)
for c in new:
    d.rectangle([c.box.x1, c.box.y1, c.box.x2, c.box.y2], outline=(255, 40, 40), width=2)
vis.save("D:/new_automation/scratch/viz_added.png")
# stats of the added ones vs nearest existing candidate
import statistics
ious = []
for c in new:
    best = max((c.box.iou(o.box) for o in cs.candidates[:n0]), default=0)
    ious.append(best)
print("max IoU of added boxes with an existing candidate: median %.2f, >0.15: %d, >0.2: %d" % (statistics.median(ious), sum(i > 0.15 for i in ious), sum(i > 0.2 for i in ious)))
