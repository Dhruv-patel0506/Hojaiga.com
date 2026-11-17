import sys, os, tempfile, math
sys.path.insert(0, r"D:\new_automation\All codes")
import numpy as np, cv2
from core_organs.harvest import drag_trace as DT

W, H = 384, 216
def bez(p0, p1, p2, u):
    return ((1 - u) ** 2) * np.array(p0) + 2 * (1 - u) * u * np.array(p1) + (u ** 2) * np.array(p2)
def base():
    im = np.full((H, W), 245, np.uint8)
    cv2.rectangle(im, (0, 0), (W, 22), (200,), -1)
    cv2.rectangle(im, (0, 22), (60, H), (225,), -1)
    return im
P0, P1, P2 = (110, 170), (170, 50), (320, 80)
frames = []
for i in range(18):
    cx, cy = bez(P0, P1, P2, i / 17)
    im = base()
    cv2.rectangle(im, (int(cx - 22), int(cy - 14)), (int(cx + 22), int(cy + 14)), (90,), -1)
    frames.append(im)
tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "drag.mp4")
vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 12, (768, 432))
for f in [base()] * 6 + frames + [frames[-1]] * 6:
    vw.write(cv2.resize(cv2.cvtColor(f, cv2.COLOR_GRAY2BGR), (768, 432)))
vw.release()
cap = cv2.VideoCapture(path)
print("fps", cap.get(cv2.CAP_PROP_FPS), "frames", cap.get(cv2.CAP_PROP_FRAME_COUNT))
cap.release()
r = DT.trace_window(path, 0.3, 2.6)
print("trace_window ->", None if r is None else {k: r[k] for k in ("method", "length", "straightness", "start", "end", "samples")})
# what the pure frames give after the same canvas pipeline
from core_organs.harvest import consolidate as C
cap = cv2.VideoCapture(path)
fr = []
while True:
    ok, f = cap.read()
    if not ok: break
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    fr.append(C._canvas(g, None))
print("n canvases", len(fr), fr[0].shape)
r2 = DT.trace_frames(fr[3:], [i / 12 for i in range(3, 3 + len(fr[3:]))])
print("trace_frames on decoded canvases ->", None if r2 is None else {k: r2[k] for k in ("method", "length", "start", "end", "samples")})
print("crop_box of the first frame:", C.crop_box(cv2.cvtColor(cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2GRAY)) if False else "")
print("points:", r["points"])
print("truth end", (np.array(P2) / np.array([W, H])).round(3), "truth start", (np.array(P0) / np.array([W, H])).round(3))
# raw per-pair points on decoded canvases
raw = []
for k in range(4, len(fr)):
    p = DT._flow_point(fr[k - 1], fr[k])
    raw.append(None if p is None else (round(p[0], 3), round(p[1], 3), round(p[2], 2)))
print("raw flow points per frame pair:", raw)
