"""Does drag_trace recover a KNOWN path? (object moved along a Bezier curve; a stroke drawn along one; nothing moving)"""
import sys, math
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
    for k in range(5):
        cv2.putText(im, f"Tool{k}", (4, 44 + 22 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (60,), 1)
    return im


P0, P1, P2 = (110, 170), (170, 50), (320, 80)
truth = np.array([bez(P0, P1, P2, u) for u in np.linspace(0, 1, 400)])
truth_n = truth / np.array([W, H])


def err(path):
    pts = np.array([(p[1], p[2]) for p in path])
    d = [np.min(np.hypot(*(truth_n - q).T)) for q in pts]
    return float(np.mean(d)), float(max(d))


# 1) an object dragged along the curve
frames, times = [], []
n = 18
for i in range(n):
    u = i / (n - 1)
    cx, cy = bez(P0, P1, P2, u)
    im = base()
    cv2.rectangle(im, (int(cx - 22), int(cy - 14)), (int(cx + 22), int(cy + 14)), (90,), -1)
    cv2.rectangle(im, (int(cx - 22), int(cy - 14)), (int(cx + 22), int(cy + 14)), (20,), 2)
    frames.append(im)
    times.append(i / 12.0)
r = DT.trace_frames(frames, times)
print("OBJECT  ->", None if r is None else {k: r[k] for k in ("method", "kind", "length", "straightness", "duration", "samples")})
if r:
    print("   start", r["start"], "truth", (truth_n[0] if True else ""), "| end", r["end"], "truth", truth_n[-1], "| mean/max err (norm.)", err(r["points"]), "points", len(r["points"]))

# 2) a stroke drawn along the curve (nothing moves: ink appears)
frames, times = [], []
im = base()
canvas = im.copy()
for i in range(n):
    u0, u1 = max(0, (i - 1)) / (n - 1), i / (n - 1)
    a, b = bez(P0, P1, P2, u0), bez(P0, P1, P2, u1)
    cv2.line(canvas, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), (30,), 4)
    frames.append(canvas.copy())
    times.append(i / 12.0)
r2 = DT.trace_frames(frames, times)
print("STROKE  ->", None if r2 is None else {k: r2[k] for k in ("method", "kind", "length", "straightness", "duration", "samples")})
if r2:
    print("   start", r2["start"], "| end", r2["end"], "truth end", truth_n[-1], "| mean/max err", err(r2["points"]))

# 3) nothing moves, small noise
rng = np.random.default_rng(0)
frames = [np.clip(base().astype(int) + rng.integers(-3, 4, (H, W)), 0, 255).astype(np.uint8) for _ in range(14)]
print("STILL   ->", DT.trace_frames(frames, [i / 12 for i in range(14)]))
# 4) pointer jitters in place (a tiny arrow)
frames = []
for i in range(14):
    im = base()
    x = 200 + (i % 3)
    cv2.fillConvexPoly(im, np.array([[x, 100], [x, 114], [x + 8, 108]]), (0,))
    frames.append(im)
print("JITTER  ->", DT.trace_frames(frames, [i / 12 for i in range(14)]))
