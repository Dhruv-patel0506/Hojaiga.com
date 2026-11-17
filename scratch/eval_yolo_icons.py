"""Does OmniParser's icon_detect (YOLO, already on disk) find controls that the Professor's own CV candidates miss?  Measure, do not assume."""
import sys, time, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
import numpy as np
from PIL import Image, ImageDraw

W = "D:/new_automation/OmniParser/weights/icon_detect/model.pt"
t0 = time.time()
from ultralytics import YOLO
model = YOLO(W)
print(f"model loaded in {time.time() - t0:.1f}s (device cpu); names={model.names}")

from core_organs.professor import candidates as CD, synth
from core_organs.professor.schema import Box


def yolo(img, conf=0.05, imgsz=1280):
    t = time.time()
    r = model.predict(np.asarray(img.convert("RGB")), conf=conf, iou=0.7, imgsz=imgsz, device="cpu", verbose=False)[0]
    out = []
    for b, c in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()):
        out.append((Box(float(b[0]), float(b[1]), float(b[2]), float(b[3])), float(c)))
    return out, time.time() - t


def hit(t, boxes, thr=0.3):
    return any(b.iou(t) >= thr or b.overlap_frac(t) >= 0.6 or t.overlap_frac(b) >= 0.6 for b in boxes)


# ---------------------------------------------------------------- A: synthetic app, exact truth (45 controls)
rows = []
for theme, scale in (("light", 1.0), ("dark", 1.0), ("light", 1.5)):
    img, truth, _ = synth.render_app(theme, scale)
    tb = [Box(*t["box"]) for t in truth if t["label"]]
    det, dt = yolo(img)
    cv = CD.detect(img, scale=scale, ocr=True, budget_s=30)
    cvb = [c.box for c in cv.candidates]
    for conf_floor in (0.05, 0.25):
        yb = [b for b, c in det if c >= conf_floor]
        r_y = sum(hit(t, yb) for t in tb) / len(tb)
        rows.append((theme, scale, conf_floor, len(yb), round(r_y, 3), round(dt, 1)))
    r_cv = sum(hit(t, cvb) for t in tb) / len(tb)
    both = [b for b, c in det if c >= 0.05] + cvb
    r_both = sum(hit(t, both) for t in tb) / len(tb)
    print(f"[synthetic {theme}@{scale}] truth {len(tb)}  CV recall {r_cv:.2f} ({len(cvb)} cands)  YOLO recall@0.05 {rows[-2][4]} ({rows[-2][3]} boxes) @0.25 {rows[-1][4]} ({rows[-1][3]})  union {r_both:.2f}   yolo {dt:.1f}s")

# ---------------------------------------------------------------- B: UIA-blind real editor (Blender capture)
shot = "D:/new_automation/scratch/blender_cap_0.png"
img = Image.open(shot).convert("RGB")
print(f"\n[blender capture] {img.size}")
det, dt = yolo(img, conf=0.05)
cv = CD.detect(img, scale=1.0, ocr=True, budget_s=40)
cvb = [c.box for c in cv.candidates if c.kind != "text"]
cvall = [c.box for c in cv.candidates]
for floor in (0.05, 0.15, 0.3):
    yb = [(b, c) for b, c in det if c >= floor]
    new = [b for b, c in yb if not any(b.iou(x) >= 0.25 or b.overlap_frac(x) >= 0.6 or x.overlap_frac(b) >= 0.6 for x in cvall)]
    covered = sum(1 for x in cvb if any(x.iou(b) >= 0.25 or x.overlap_frac(b) >= 0.6 or b.overlap_frac(x) >= 0.6 for b, _c in yb))
    print(f"  yolo conf>={floor}: {len(yb)} boxes; {len(yb) - len(new)} already among CV candidates, {len(new)} NEW;  CV non-text candidates {len(cvb)} of which {covered} also seen by yolo")
print(f"  yolo inference {dt:.1f}s on {img.size}; CV detect timings {cv.timings}")

# overlay: green = CV candidate, red = yolo-only (conf>=0.15)
yb = [b for b, c in det if c >= 0.15]
new = [b for b in yb if not any(b.iou(x) >= 0.25 or b.overlap_frac(x) >= 0.6 or x.overlap_frac(b) >= 0.6 for x in cvall)]
vis = img.copy()
d = ImageDraw.Draw(vis)
for b in cvall:
    d.rectangle([b.x1, b.y1, b.x2, b.y2], outline=(0, 200, 0), width=1)
for b in new:
    d.rectangle([b.x1, b.y1, b.x2, b.y2], outline=(255, 0, 0), width=2)
vis.save("D:/new_automation/scratch/eval_yolo_blender.png")
print("saved scratch/eval_yolo_blender.png  (green = CV candidates, red = YOLO-only)")
