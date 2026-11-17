"""
harvest.drag_trace -- follow a drag (or a stroke being drawn) through a screen recording and keep it as a VECTOR, not a guess.

A click is one frame pair; a drag is a path. For a window of frames around an event this module finds what moved and where it went:

    object moved   dense optical flow (Farneback) between consecutive frames; the largest coherent moving blob; its flow-weighted centre is followed frame to frame
    ink appeared   (a brush stroke, a connector being drawn) nothing moves, new pixels appear: the centre of the NEWLY CHANGED pixels, nearest to the previous point, is the tip of the stroke
The two are tried in that order per window; the method used is recorded. The raw track is smoothed (moving median), simplified with Ramer-Douglas-Peucker to a handful of points and described:

    start, end, length, net displacement, straightness (net / length), duration, mean and peak speed (all in the app's own normalised coordinates, 0..1 of the cropped screen)
    kind: 'straight' (>= 0.85), 'curved', or 'loop' (it came back near its start)

`GestureIndex` is a small vector store of such paths (each resampled to 16 points, normalised for position and for size): "have we seen a gesture shaped like this one?" by cosine nearest neighbour.

`looks_like_move(obs)` is the cheap test that decides which events deserve the video to be re-read (two similar changed blobs apart from each other = something moved; speech that says drag).
Everything is arithmetic on frames: no model, no network. Validated in si_tests_consolidate (AR57) against a path that is known exactly.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

MIN_FLOW = 1.0            # px (on the 384-wide canvas) of flow magnitude that counts as moving
MIN_BLOB_FRAC = 0.0015    # a moving blob must cover at least this share of the canvas
MAX_JUMP = 0.20           # a step between consecutive samples larger than this share of the width is a different blob, not the same drag
MIN_CHANGED_IN_BLOB = 0.12   # share of the moving blob's pixels that really changed value (> 25 grey levels) between the two frames
MIN_LENGTH = 0.03         # shorter than this share of the diagonal is not a drag
SAMPLE_FPS = 12.0


# ------------------------------------------------------------------------------------------------------------------ geometry
def rdp(points: Sequence[Tuple[float, float, float]], eps: float) -> List[Tuple[float, float, float]]:
    """Ramer-Douglas-Peucker on (t, x, y): keep the points that matter."""
    if len(points) < 3:
        return list(points)
    (_, x0, y0), (_, x1, y1) = points[0], points[-1]
    dx, dy = x1 - x0, y1 - y0
    norm = math.hypot(dx, dy) or 1e-9
    dmax, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        d = abs(dy * points[i][1] - dx * points[i][2] + x1 * y0 - y1 * x0) / norm
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return rdp(points[:idx + 1], eps)[:-1] + rdp(points[idx:], eps)
    return [points[0], points[-1]]


def metrics(points: Sequence[Tuple[float, float, float]]) -> Dict[str, Any]:
    pts = np.array(points, dtype=float)
    seg = np.hypot(np.diff(pts[:, 1]), np.diff(pts[:, 2]))
    length = float(seg.sum())
    net = float(math.hypot(pts[-1, 1] - pts[0, 1], pts[-1, 2] - pts[0, 2]))
    dt = np.maximum(np.diff(pts[:, 0]), 1e-6)
    speed = seg / dt
    straight = net / length if length > 1e-9 else 0.0
    kind = "loop" if length > 0.2 and net < 0.25 * length else ("straight" if straight >= 0.85 else "curved")
    return {"start": [round(float(pts[0, 1]), 4), round(float(pts[0, 2]), 4)], "end": [round(float(pts[-1, 1]), 4), round(float(pts[-1, 2]), 4)], "length": round(length, 4),
            "net": round(net, 4), "straightness": round(straight, 3), "duration": round(float(pts[-1, 0] - pts[0, 0]), 3), "mean_speed": round(float(speed.mean()), 3) if len(speed) else 0.0,
            "peak_speed": round(float(speed.max()), 3) if len(speed) else 0.0, "kind": kind}


def resample(points: Sequence[Tuple[float, float, float]], n: int = 16) -> np.ndarray:
    pts = np.array([(p[1], p[2]) for p in points], dtype=float)
    d = np.r_[0.0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
    if d[-1] < 1e-9:
        return np.repeat(pts[:1], n, axis=0)
    u = np.linspace(0, d[-1], n)
    return np.c_[np.interp(u, d, pts[:, 0]), np.interp(u, d, pts[:, 1])]


# ------------------------------------------------------------------------------------------------------------------ tracing frames
def _flow_point(prev: np.ndarray, cur: np.ndarray) -> Optional[Tuple[float, float, float]]:
    import cv2
    flow = cv2.calcOpticalFlowFarneback(prev, cur, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    mag = np.hypot(flow[..., 0], flow[..., 1])
    m = (mag > MIN_FLOW).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
    if n <= 1:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[i, cv2.CC_STAT_AREA] < MIN_BLOB_FRAC * m.size:
        return None
    changed = cv2.absdiff(prev, cur) > 25
    if float(changed[lab == i].mean()) < MIN_CHANGED_IN_BLOB:
        return None
    ys, xs = np.where(lab == i)
    w = mag[ys, xs]
    H, W = mag.shape
    both = (lab == i) & changed                                              # the centre of the pixels that REALLY changed inside the moving blob: unbiased by the flow aperture problem
    if both.sum() >= 4:
        cy, cx = np.where(both)
        return float(cx.mean() / W), float(cy.mean() / H), float(w.mean())
    return float((xs * w).sum() / w.sum() / W), float((ys * w).sum() / w.sum() / H), float(w.mean())


def _ink_point(prev: np.ndarray, cur: np.ndarray, last: Optional[Tuple[float, float]]) -> Optional[Tuple[float, float, float]]:
    import cv2
    d = (cv2.absdiff(prev, cur) > 25).astype(np.uint8)
    d = cv2.morphologyEx(d, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(d)
    H, W = d.shape
    best, bd = None, 1e9
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < 3:
            continue
        cx, cy = cent[i][0] / W, cent[i][1] / H
        dist = 0.0 if last is None else math.hypot(cx - last[0], cy - last[1])
        score = dist - 0.00002 * stats[i, cv2.CC_STAT_AREA]
        if score < bd:
            best, bd = (cx, cy, float(stats[i, cv2.CC_STAT_AREA])), score
    return best


def trace_frames(frames: Sequence[np.ndarray], times: Sequence[float]) -> Optional[Dict[str, Any]]:
    """A path from consecutive grey frames (all the same size), or None when nothing moved / drew a path longer than MIN_LENGTH."""
    for method in ("flow", "ink"):
        raw: List[Tuple[float, float, float]] = []
        last: Optional[Tuple[float, float]] = None
        for k in range(1, len(frames)):
            p = _flow_point(frames[k - 1], frames[k]) if method == "flow" else _ink_point(frames[k - 1], frames[k], last)
            if p is None:
                continue
            if last is not None and math.hypot(p[0] - last[0], p[1] - last[1]) > MAX_JUMP:
                continue                                                      # a different blob (the pointer elsewhere), not this track
            raw.append((float(times[k]), p[0], p[1]))
            last = (p[0], p[1])
        if len(raw) < 4:
            continue
        xs = np.array([p[1] for p in raw])
        ys = np.array([p[2] for p in raw])
        k = 2                                                                  # moving median over 5 samples: one wrong frame does not bend the path (the two end samples stay as measured)
        sx = [float(xs[i]) if (i < k or i >= len(xs) - k) else float(np.median(xs[i - k:i + k + 1])) for i in range(len(xs))]
        sy = [float(ys[i]) if (i < k or i >= len(ys) - k) else float(np.median(ys[i - k:i + k + 1])) for i in range(len(ys))]
        smooth = [(raw[i][0], sx[i], sy[i]) for i in range(len(raw))]
        if method == "flow" and len(smooth) >= 3:                              # a flow point sits half-way between two frames: reach half a step further at both ends
            (t0_, x0_, y0_), (t1_, x1_, y1_) = smooth[0], smooth[1]
            (t2_, x2_, y2_), (t3_, x3_, y3_) = smooth[-2], smooth[-1]
            smooth = [(t0_ - 0.5 * (t1_ - t0_), x0_ - 0.5 * (x1_ - x0_), y0_ - 0.5 * (y1_ - y0_))] + smooth + [(t3_ + 0.5 * (t3_ - t2_), x3_ + 0.5 * (x3_ - x2_), y3_ + 0.5 * (y3_ - y2_))]
        simple = rdp(smooth, 0.008)
        m = metrics(smooth)
        if m["length"] < MIN_LENGTH:
            continue
        return dict(m, method=method, points=[[round(t, 3), round(x, 4), round(y, 4)] for t, x, y in simple], samples=len(raw))
    return None


def looks_like_move(obs: Dict[str, Any]) -> bool:
    """Cheap test on an observation (consolidate): two changed blobs of similar size, clearly apart (something left one place and appeared in another), or the speaker said 'drag'."""
    if obs.get("kind") == "drag":
        return True
    comps = obs.get("comps") or []
    for i in range(len(comps)):
        for j in range(i + 1, len(comps)):
            a, b = comps[i], comps[j]
            ra = a["area"] / max(b["area"], 1e-9)
            ca = ((a["box"][0] + a["box"][2]) / 2, (a["box"][1] + a["box"][3]) / 2)
            cb = ((b["box"][0] + b["box"][2]) / 2, (b["box"][1] + b["box"][3]) / 2)
            if 0.6 <= ra <= 1.7 and math.hypot(ca[0] - cb[0], ca[1] - cb[1]) >= 0.05 and min(a["area"], b["area"]) >= 0.002:
                return True
    return False


def trace_window(video_path: str, t0: float, t1: float, crop_px: Optional[Sequence[int]] = None, mask: Optional[Sequence[float]] = None, fps: float = SAMPLE_FPS) -> Optional[Dict[str, Any]]:
    """Re-read [t0, t1] of a video at ~`fps`, bring every frame to the same letterbox-free grey canvas as the graph uses, and trace it."""
    import cv2
    from core_organs.harvest import consolidate as C
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    vfps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(vfps / fps)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(t0 * vfps)))
    frames: List[np.ndarray] = []
    times: List[float] = []
    box = tuple(crop_px) if crop_px else None
    idx = int(max(0, t0 * vfps))
    while idx <= int(t1 * vfps):
        ok, fr = cap.read()
        if not ok:
            break
        if (idx - int(max(0, t0 * vfps))) % step == 0:
            g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
            g = C._mask_inset(g, mask)
            if box is None:
                box = C.crop_box(g)                                         # fixed ONCE from the first frame: every frame of one trace must share the same canvas
            frames.append(C._canvas(g, box))
            times.append(idx / vfps)
        idx += 1
    cap.release()
    return trace_frames(frames, times) if len(frames) >= 5 else None


# ------------------------------------------------------------------------------------------------------------------ a vector store of gestures
class GestureIndex:
    """Paths as vectors: 16 points, the start moved to the origin (position-free) and scaled to unit length (size-free), plus the two raw ends so direction and place can be compared too."""

    def __init__(self, path: str):
        self.path = path
        self.vecs: List[np.ndarray] = []
        self.meta: List[Dict[str, Any]] = []
        if os.path.isfile(path):
            with contextlib.suppress(Exception):
                z = np.load(path, allow_pickle=True)
                self.vecs, self.meta = list(z["vecs"]), list(z["meta"])

    @staticmethod
    def vector(points: Sequence[Sequence[float]]) -> np.ndarray:
        r = resample([tuple(p) for p in points])
        r = r - r[0]
        sc = float(np.hypot(*r[-1:].T)) if np.hypot(*r[-1]) > 1e-6 else float(np.abs(r).max() or 1.0)
        r = r / (max(float(np.abs(r).max()), 1e-6))
        v = r.ravel()
        return v / (np.linalg.norm(v) or 1.0)

    def add(self, points: Sequence[Sequence[float]], meta: Dict[str, Any]) -> None:
        self.vecs.append(self.vector(points))
        self.meta.append(meta)

    def query(self, points: Sequence[Sequence[float]], k: int = 3) -> List[Tuple[float, Dict[str, Any]]]:
        if not self.vecs:
            return []
        q = self.vector(points)
        sims = np.array([float(np.dot(q, v)) for v in self.vecs])
        order = np.argsort(-sims)[:k]
        return [(round(float(sims[i]), 3), self.meta[i]) for i in order]

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        np.savez(self.path, vecs=np.array(self.vecs), meta=np.array(self.meta, dtype=object))
