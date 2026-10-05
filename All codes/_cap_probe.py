"""Temporary probe: capture backend timings (ImageGrab vs mss, JPEG, base64)."""
import time, io, base64
from PIL import Image, ImageGrab

N = 6

ts = []
for _ in range(N):
    t0 = time.perf_counter(); img = ImageGrab.grab(); ts.append((time.perf_counter() - t0) * 1000)
print("ImageGrab.grab        : %6.1f ms avg  (size %s)" % (sum(ts) / N, img.size))

import mss
sct = mss.mss()
mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

ts = []
for _ in range(N):
    t0 = time.perf_counter(); raw = sct.grab(mon); ts.append((time.perf_counter() - t0) * 1000)
print("mss.grab              : %6.1f ms avg  (size %s)" % (sum(ts) / N, raw.size))

ts = []
for _ in range(N):
    t0 = time.perf_counter()
    raw = sct.grab(mon)
    img2 = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    ts.append((time.perf_counter() - t0) * 1000)
print("mss.grab -> PIL Image : %6.1f ms avg" % (sum(ts) / N))

img = ImageGrab.grab()
ts = []
for _ in range(N):
    t0 = time.perf_counter()
    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=85); b = buf.getvalue()
    ts.append((time.perf_counter() - t0) * 1000)
print("JPEG encode q85       : %6.1f ms avg  (file %d KB)" % (sum(ts) / N, len(b) // 1024))

ts = []
for _ in range(N):
    t0 = time.perf_counter(); s = base64.b64encode(b).decode("utf-8"); ts.append((time.perf_counter() - t0) * 1000)
print("base64 encode         : %6.1f ms avg" % (sum(ts) / N))

# Full pipeline variants
ts = []
for _ in range(N):
    t0 = time.perf_counter()
    img = ImageGrab.grab()
    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=85)
    s = base64.b64encode(buf.getvalue()).decode("utf-8")
    ts.append((time.perf_counter() - t0) * 1000)
print("FULL ImageGrab+JPEG+b64: %6.1f ms avg" % (sum(ts) / N))

ts = []
for _ in range(N):
    t0 = time.perf_counter()
    raw = sct.grab(mon)
    img3 = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    buf = io.BytesIO(); img3.save(buf, format="JPEG", quality=85)
    s = base64.b64encode(buf.getvalue()).decode("utf-8")
    ts.append((time.perf_counter() - t0) * 1000)
print("FULL mss+PIL+JPEG+b64 : %6.1f ms avg" % (sum(ts) / N))
