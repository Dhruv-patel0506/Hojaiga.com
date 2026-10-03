"""Temporary probe v3: dxcam new_frame_only=False + channel verify + cv2 pipeline."""
import time, io, base64
import numpy as np
import cv2
import dxcam
from PIL import Image, ImageGrab

pil = np.asarray(ImageGrab.grab())
print("PIL RGB means   : R=%.1f G=%.1f B=%.1f" % (pil[..., 0].mean(), pil[..., 1].mean(), pil[..., 2].mean()))

cam = dxcam.create(output_idx=0, output_color="BGR")
print("camera region:", getattr(cam, "region", None), "color:", getattr(cam, "output_color", "?"))

# Warmup with forced screen activity (our own prints repaint the console)
last = None
for i in range(8):
    print("warmup line", i)
    f = cam.grab(new_frame_only=False)
    if f is not None:
        last = f

N = 10
ts, none_count = [], 0
for i in range(N):
    print("probe line", i)          # repaint console -> new frame
    t0 = time.perf_counter()
    f = cam.grab(new_frame_only=False)
    ts.append((time.perf_counter() - t0) * 1000)
    if f is None:
        none_count += 1
    else:
        last = f
print("dxcam.grab(nfo=False) : %6.1f ms avg  (None frames: %d/%d)" % (sum(ts) / N, none_count, N))

if last is None:
    print("NO FRAME AT ALL -- dxcam unusable here")
    raise SystemExit(1)

print("frame shape:", last.shape, last.dtype)
print("dxcam ch means  : c0=%.1f c1=%.1f c2=%.1f" % (last[..., 0].mean(), last[..., 1].mean(), last[..., 2].mean()))
print("=> compare against PIL line above; PIL is RGB ground truth")

ts = []
for _ in range(N):
    t0 = time.perf_counter()
    ok, enc = cv2.imencode(".jpg", last, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    ts.append((time.perf_counter() - t0) * 1000)
print("cv2.imencode q85      : %6.1f ms avg  (%d KB)" % (sum(ts) / N, enc.nbytes // 1024))

img_pil = Image.fromarray(last)
ts = []
for _ in range(N):
    t0 = time.perf_counter()
    buf = io.BytesIO(); img_pil.save(buf, format="JPEG", quality=85); b = buf.getvalue()
    ts.append((time.perf_counter() - t0) * 1000)
print("PIL JPEG q85 same frm : %6.1f ms avg  (%d KB)" % (sum(ts) / N, len(b) // 1024))

ts = []
for _ in range(N):
    t0 = time.perf_counter()
    f = cam.grab(new_frame_only=False)
    if f is None:
        f = last
    ok, enc = cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    s = base64.b64encode(enc.tobytes()).decode("utf-8")
    ts.append((time.perf_counter() - t0) * 1000)
print("FULL dxcam+cv2+b64    : %6.1f ms avg" % (sum(ts) / N))

cv2.imwrite(r"D:\new_automation\All codes\_dxcam_sample.png", last)
print("sample saved")
del cam
