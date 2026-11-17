"""
atlas.motion -- tell WHAT a gesture did from two (or three) pictures of the same region.

Nothing here knows an application. It answers a physical question: "how did the pixels move?"

    none            nothing changed
    pan             the content translated (rigid, scale ~ 1, rotation ~ 0)
    scroll          pan along one axis only, for a wheel gesture
    zoom            the content scaled about a point
    rotate          the content rotated in the plane
    nonrigid        a lot changed and no rigid motion explains it (3-D orbit/tumble, re-render, new content)
    rubber_band     an outlined rectangle that follows the drag (visible while the button is held)
    shape_draw      a rectangle that stays after release
    stroke          pixels changed along the dragged path (painting / ink)
    translate_object a blob moved by about the drag vector
    local_change    something small changed (selection highlight, hover state, a value)

Every rigid estimate is VERIFIED: the first picture is warped by the estimated transform and compared with the second; an
estimate that does not explain the change is discarded (so a bad feature match can never be reported as "zoom").
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def available() -> bool:
    return cv2 is not None


# --------------------------------------------------------------------------------------------------
# basics
# --------------------------------------------------------------------------------------------------

def to_gray(img: Any, max_side: int = 0) -> Tuple[np.ndarray, float]:
    """PIL image | ndarray -> uint8 gray (optionally downscaled so the longest side <= max_side). Returns (gray, scale)."""
    arr = np.asarray(img)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr[:, :, :3].astype(np.uint8), cv2.COLOR_RGB2GRAY)
    arr = arr.astype(np.uint8)
    scale = 1.0
    if max_side and max(arr.shape[:2]) > max_side:
        scale = max_side / float(max(arr.shape[:2]))
        arr = cv2.resize(arr, (max(1, int(arr.shape[1] * scale)), max(1, int(arr.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    return arr, scale


def diff_mask(a: np.ndarray, b: np.ndarray, thr: int = 24) -> np.ndarray:
    d = cv2.absdiff(cv2.GaussianBlur(a, (3, 3), 0), cv2.GaussianBlur(b, (3, 3), 0))
    return (d > thr).astype(np.uint8) * 255


def painted_box(img: Any, margin: int = 2) -> Optional[Tuple[int, int, int, int]]:
    """Bounding box of the part of a captured picture an application actually painted. A window that is DPI-virtualised, parked at
    another size or only partly laid out is captured with an unpainted (pure black) margin; analysing that margin would dilute every
    measurement. Returns None when (nearly) the whole picture is painted."""
    arr = np.asarray(img)
    if arr.ndim == 3:
        arr = arr[:, :, :3].max(axis=2)
    h, w = arr.shape[:2]
    cols = np.nonzero((arr > 6).any(axis=0))[0]
    rows = np.nonzero((arr > 6).any(axis=1))[0]
    if len(cols) == 0 or len(rows) == 0:
        return None
    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    if (x1 - x0) * (y1 - y0) >= 0.93 * w * h:
        return None
    return max(0, x0 - margin), max(0, y0 - margin), min(w, x1 + margin), min(h, y1 + margin)


def volatility_mask(frames: Sequence[Any], thr: int = 18, grow: int = 7) -> np.ndarray:
    """Pixels that change BY THEMSELVES (blinking caret, clock, video preview, animation): union of frame-to-frame differences, grown."""
    g = [to_gray(f)[0] for f in frames]
    m = np.zeros(g[0].shape, np.uint8)
    for i in range(len(g) - 1):
        if g[i].shape == g[i + 1].shape:
            m |= diff_mask(g[i], g[i + 1], thr)
    return cv2.dilate(m, np.ones((grow, grow), np.uint8)) if m.any() else m


def diff_stats(a: np.ndarray, b: np.ndarray, thr: int = 24, ignore: Optional[np.ndarray] = None) -> Dict[str, Any]:
    m = diff_mask(a, b, thr)
    if ignore is not None and ignore.shape == m.shape:
        m = np.where(ignore > 0, 0, m).astype(np.uint8)
    n = int(np.count_nonzero(m))
    ys, xs = np.nonzero(m)
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if n else None
    return {"changed_px": n, "changed_ratio": n / float(m.size), "bbox": bbox, "mask": m}


def crop(img: Any, box: Tuple[int, int, int, int]):
    x0, y0, x1, y1 = [int(v) for v in box]
    arr = np.asarray(img)
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    return arr[y0:y1, x0:x1]


# --------------------------------------------------------------------------------------------------
# registration
# --------------------------------------------------------------------------------------------------

def _decompose(M: np.ndarray, size: Tuple[int, int]) -> Dict[str, float]:
    """Similarity matrix -> scale, rotation (deg), centre displacement (px), where 'centre' is the middle of the region."""
    s = math.sqrt(float(M[0, 0]) ** 2 + float(M[1, 0]) ** 2)
    th = math.degrees(math.atan2(float(M[1, 0]), float(M[0, 0])))
    w, h = size
    c = np.array([w / 2.0, h / 2.0, 1.0])
    c2 = M @ c
    dx, dy = float(c2[0] - c[0]), float(c2[1] - c[1])
    return {"scale": s, "rot_deg": th, "dx": dx, "dy": dy, "shift": math.hypot(dx, dy)}


def residual(a: np.ndarray, b: np.ndarray, M: np.ndarray) -> float:
    """Mean absolute difference (0..1) between warp(a, M) and b over the area both cover."""
    h, w = b.shape[:2]
    wa = cv2.warpAffine(a, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    valid = cv2.warpAffine(np.full(a.shape[:2], 255, np.uint8), M, (w, h), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    valid = cv2.erode(valid, np.ones((5, 5), np.uint8))
    n = int(np.count_nonzero(valid))
    if n < 0.25 * valid.size:
        return 1.0
    d = cv2.absdiff(cv2.GaussianBlur(wa, (3, 3), 0), cv2.GaussianBlur(b, (3, 3), 0))
    return float(d[valid > 0].mean()) / 255.0


def _orb_candidates(a: np.ndarray, b: np.ndarray) -> List[Tuple[str, np.ndarray, float]]:
    out: List[Tuple[str, np.ndarray, float]] = []
    try:
        orb = cv2.ORB_create(nfeatures=2500, scaleFactor=1.2, nlevels=8, edgeThreshold=15, fastThreshold=8)
        k1, d1 = orb.detectAndCompute(a, None)
        k2, d2 = orb.detectAndCompute(b, None)
        if d1 is None or d2 is None or len(k1) < 10 or len(k2) < 10:
            return out
        bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        good = []
        for pr in bf.knnMatch(d1, d2, k=2):
            if len(pr) == 2 and pr[0].distance < 0.8 * pr[1].distance:
                good.append(pr[0])
        sets = [good]
        bf2 = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        cc = sorted(bf2.match(d1, d2), key=lambda m: m.distance)[:300]
        sets.append(cc)
        for ms in sets:
            if len(ms) < 8:
                continue
            p1 = np.float32([k1[m.queryIdx].pt for m in ms])
            p2 = np.float32([k2[m.trainIdx].pt for m in ms])
            M, inl = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC, ransacReprojThreshold=2.5, maxIters=3000, confidence=0.995)
            if M is not None and inl is not None:
                ratio = float(inl.sum()) / len(ms)
                out.append((f"orb(n={len(ms)},in={int(inl.sum())})", M.astype(np.float64), ratio))
    except Exception:
        pass
    return out


def _fourier_mellin(a: np.ndarray, b: np.ndarray) -> List[Tuple[str, np.ndarray, float]]:
    """Scale/rotation from log-polar phase correlation of the FFT magnitudes, then translation. Several sign candidates."""
    out: List[Tuple[str, np.ndarray, float]] = []
    try:
        h, w = a.shape[:2]
        n = min(h, w)
        n = n - (n % 2)
        ca = a[(h - n) // 2:(h - n) // 2 + n, (w - n) // 2:(w - n) // 2 + n].astype(np.float32)
        cb = b[(h - n) // 2:(h - n) // 2 + n, (w - n) // 2:(w - n) // 2 + n].astype(np.float32)
        win = cv2.createHanningWindow((n, n), cv2.CV_32F)

        def logpolar(img):
            f = np.fft.fftshift(np.fft.fft2(img * win))
            mag = np.log1p(np.abs(f)).astype(np.float32)
            return cv2.warpPolar(mag, (n, n), (n / 2, n / 2), n / 2, cv2.WARP_POLAR_LOG | cv2.INTER_LINEAR)
        la, lb = logpolar(ca), logpolar(cb)
        (sx, sy), resp = cv2.phaseCorrelate(la, lb)
        klog = n / math.log(n / 2.0)
        scale = math.exp(sx / klog)
        for sign in (1, -1):
            for inv in (False, True):
                ang = sign * (sy * 360.0 / n)
                sc = (1.0 / scale) if inv else scale
                cx, cy = w / 2.0, h / 2.0
                R = cv2.getRotationMatrix2D((cx, cy), ang, sc)
                wa = cv2.warpAffine(a, R, (w, h), flags=cv2.INTER_LINEAR)
                (tx, ty), r2 = cv2.phaseCorrelate(wa.astype(np.float32), b.astype(np.float32))
                M = R.copy()
                M[0, 2] += tx
                M[1, 2] += ty
                out.append((f"fmt(sign={sign},inv={int(inv)},resp={resp:.2f})", M.astype(np.float64), float(r2)))
    except Exception:
        pass
    return out


def _pure_shift(a: np.ndarray, b: np.ndarray) -> List[Tuple[str, np.ndarray, float]]:
    try:
        (tx, ty), resp = cv2.phaseCorrelate(a.astype(np.float32), b.astype(np.float32), cv2.createHanningWindow(a.shape[::-1], cv2.CV_32F))
        return [(f"phase(resp={resp:.2f})", np.array([[1, 0, tx], [0, 1, ty]], np.float64), float(resp))]
    except Exception:
        return []


def register(a: np.ndarray, b: np.ndarray, max_side: int = 640) -> Dict[str, Any]:
    """Best VERIFIED rigid+scale transform taking `a` to `b`, or {'ok': False}. Works at reduced resolution."""
    ga, s = to_gray(a, max_side)
    gb, _ = to_gray(b, max_side)
    if ga.shape != gb.shape:
        gb = cv2.resize(gb, (ga.shape[1], ga.shape[0]), interpolation=cv2.INTER_AREA)
    base = residual(ga, gb, np.array([[1, 0, 0], [0, 1, 0]], np.float64))
    if base < 0.002:
        return {"ok": True, "scale": 1.0, "rot_deg": 0.0, "dx": 0.0, "dy": 0.0, "shift": 0.0, "residual": base, "base_residual": base,
                "method": "identity", "downscale": s}
    cands = _orb_candidates(ga, gb) + _fourier_mellin(ga, gb) + _pure_shift(ga, gb)
    best = None
    for name, M, q in cands:
        if not np.isfinite(M).all():
            continue
        dec = _decompose(M, (ga.shape[1], ga.shape[0]))
        if not (0.3 < dec["scale"] < 3.5):
            continue
        r = residual(ga, gb, M)
        if best is None or r < best[0]:
            best = (r, name, M, q, dec)
    if best is None:
        return {"ok": False, "base_residual": base, "why": "no candidate transform"}
    r, name, M, q, dec = best
    explained = r < 0.6 * base
    out = {"ok": bool(explained), "scale": dec["scale"], "rot_deg": dec["rot_deg"], "dx": dec["dx"] / s, "dy": dec["dy"] / s,
           "shift": dec["shift"] / s, "residual": r, "base_residual": base, "method": name, "quality": q, "downscale": s,
           "explained_fraction": 1.0 - (r / base if base > 0 else 1.0)}
    if not explained:
        out["why"] = f"best candidate left {r / base:.2f} of the change unexplained"
    return out


# --------------------------------------------------------------------------------------------------
# higher-level shapes: rubber band, stroke, object translation
# --------------------------------------------------------------------------------------------------

def _components(mask: np.ndarray, min_area: int = 12) -> List[Dict[str, Any]]:
    n, lab, stats, cent = cv2.connectedComponentsWithStats(cv2.dilate(mask, np.ones((3, 3), np.uint8)), connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = [int(v) for v in stats[i]]
        if area < min_area:
            continue
        fill = float(np.count_nonzero(mask[y:y + h, x:x + w])) / max(1, w * h)
        out.append({"bbox": (x, y, x + w, y + h), "area": area, "fill": fill, "centroid": (float(cent[i][0]), float(cent[i][1]))})
    return out


def _iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / float(ua) if ua > 0 else 0.0


def detect_band(before: np.ndarray, during: np.ndarray, drag_box: Any) -> Dict[str, Any]:
    """Is there an OUTLINED rectangle matching a drag box in `during` that was not in `before`? `drag_box` may be one box or a list of
    candidates (the capture happens mid-drag, so the rectangle may span only part of the final drag)."""
    boxes = drag_box if isinstance(drag_box, list) else [drag_box]
    m = diff_mask(before, during, 20)
    best = None
    for c in _components(m, 20):
        iou = max(_iou(c["bbox"], tuple(b)) for b in boxes)
        if best is None or iou > best[0]:
            best = (iou, c)
    if best and best[0] >= 0.5 and best[1]["fill"] <= 0.4:
        return {"found": True, "iou": best[0], "fill": best[1]["fill"], "bbox": best[1]["bbox"]}
    return {"found": False, "iou": best[0] if best else 0.0, "fill": best[1]["fill"] if best else 0.0}


def detect_stroke(before: np.ndarray, after: np.ndarray, path: Sequence[Tuple[int, int]]) -> Dict[str, Any]:
    """Did the change land ALONG the dragged path (a stroke)? Fraction of changed pixels within a few px of the path."""
    m = diff_mask(before, after, 16)
    n = int(np.count_nonzero(m))
    if n < 20 or len(path) < 2:
        return {"found": False, "changed_px": n}
    pm = np.zeros(m.shape, np.uint8)
    pts = np.array([[int(x), int(y)] for x, y in path], np.int32).reshape(-1, 1, 2)
    cv2.polylines(pm, [pts], False, 255, 1)
    dist = cv2.distanceTransform(255 - pm, cv2.DIST_L2, 3)
    tol = max(6.0, 0.012 * math.hypot(*m.shape[::-1]))
    near = float(np.count_nonzero((dist <= tol) & (m > 0))) / n
    plen = float(sum(math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1]) for i in range(len(path) - 1)))
    cover = float(np.count_nonzero((dist <= 1.5) & (cv2.dilate(m, np.ones((5, 5), np.uint8)) > 0))) / max(1.0, float(np.count_nonzero(pm)))
    return {"found": near >= 0.8 and cover >= 0.55 and n >= 0.3 * plen, "near_fraction": near, "path_coverage": cover, "changed_px": n, "path_len": plen}


def detect_translation_of_blob(before: np.ndarray, after: np.ndarray, drag_vec: Tuple[float, float]) -> Dict[str, Any]:
    """Did something move by about the drag vector? Tested as a HYPOTHESIS: shift `before` by candidate vectors near the drag
    vector and see whether that explains the change inside the changed region (a moved object leaves two overlapping or
    separate blobs; shifting the old picture lands the object exactly on its new place)."""
    m = diff_mask(before, after, 24)
    if int(np.count_nonzero(m)) < 40:
        return {"found": False, "why": "too little change"}
    region = cv2.dilate(m, np.ones((9, 9), np.uint8)) > 0
    h, w = before.shape[:2]
    res0 = float(cv2.absdiff(before, after)[region].mean()) / 255.0
    if res0 <= 0:
        return {"found": False, "why": "no residual"}
    best = (res0, None)
    for ddx in range(-12, 13, 3):
        for ddy in range(-12, 13, 3):
            vx, vy = drag_vec[0] + ddx, drag_vec[1] + ddy
            M = np.array([[1, 0, vx], [0, 1, vy]], np.float64)
            shifted = cv2.warpAffine(before, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            r = float(cv2.absdiff(shifted, after)[region].mean()) / 255.0
            if r < best[0]:
                best = (r, (vx, vy))
    if best[1] is not None and best[0] < 0.45 * res0:
        return {"found": True, "vector": best[1], "residual_ratio": best[0] / res0}
    return {"found": False, "residual_ratio": best[0] / res0}


# --------------------------------------------------------------------------------------------------
# the one call the gesture prober uses
# --------------------------------------------------------------------------------------------------

def describe(before: Any, after: Any, *, hint: str = "", drag: Optional[Dict[str, Any]] = None, during: Any = None,
             ignore: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """Classify the visual effect of a gesture on one region.

    before/after/during: images of the SAME region (PIL or ndarray). `hint`: 'wheel' | 'drag' | 'click' | 'hover' | 'hold' ...
    `drag`: {'box': (x0,y0,x1,y1) in region px, 'path': [(x,y)..], 'vec': (dx,dy), 'button': 'left'|...}
    Returns {'class', 'confidence', 'params', 'evidence'}."""
    if cv2 is None:
        return {"class": "unknown", "confidence": 0.0, "params": {}, "evidence": {"why": "opencv not available"}}
    a, _ = to_gray(before)
    b, _ = to_gray(after)
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
    st = diff_stats(a, b, ignore=ignore)
    ev: Dict[str, Any] = {"changed_ratio": round(st["changed_ratio"], 5), "changed_px": st["changed_px"], "bbox": st["bbox"]}
    if ignore is not None:
        ev["volatile_px_ignored"] = int(np.count_nonzero(ignore))
    band = None
    if during is not None and drag and drag.get("box"):
        d, _ = to_gray(during)
        if d.shape != a.shape:
            d = cv2.resize(d, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
        band = detect_band(a, d, [tuple(b) for b in (drag.get("boxes") or [drag["box"]])])
        ev["band_while_held"] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in band.items()}
    if st["changed_px"] < max(30, int(4e-5 * a.size)):
        if band and band["found"]:
            return {"class": "rubber_band", "confidence": 0.9, "params": {"bbox": band["bbox"]}, "evidence": ev}
        return {"class": "none", "confidence": 0.9, "params": {}, "evidence": ev}
    reg = register(a, b) if st["changed_ratio"] >= 0.004 else {"ok": False, "why": "change too small for a rigid explanation"}
    ev["registration"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in reg.items() if k in ("ok", "scale", "rot_deg", "dx", "dy", "shift", "residual", "base_residual", "method", "explained_fraction", "why")}
    h, w = a.shape[:2]
    if reg.get("ok") and reg.get("method") != "identity":
        s, th, shift = reg["scale"], reg["rot_deg"], reg["shift"]
        zs = abs(math.log(s)) / 0.03
        rs = abs(th) / 1.0
        ps = shift / max(2.0, 0.006 * max(w, h))
        params = {"scale": round(s, 4), "rot_deg": round(th, 2), "dx": round(reg["dx"], 1), "dy": round(reg["dy"], 1)}
        conf = max(0.55, min(0.97, 0.5 + 0.5 * float(reg.get("explained_fraction", 0.5))))
        if zs >= 1 and zs >= rs * 0.6:
            return {"class": "zoom", "confidence": conf, "params": params, "evidence": ev}
        if rs >= 1:
            return {"class": "rotate", "confidence": conf, "params": params, "evidence": ev}
        if ps >= 1:
            if hint == "wheel" and min(abs(reg["dx"]), abs(reg["dy"])) < 0.2 * max(abs(reg["dx"]), abs(reg["dy"]), 1e-6):
                return {"class": "scroll", "confidence": conf, "params": params, "evidence": ev}
            return {"class": "pan", "confidence": conf, "params": params, "evidence": ev}
    if band and band["found"]:
        # an outlined rectangle that followed the drag while the button was held is the strongest evidence there is
        persisted = False
        if drag and drag.get("box"):
            x0, y0, x1, y1 = [int(v) for v in drag["box"]]
            edge = np.zeros_like(st["mask"])
            cv2.rectangle(edge, (x0, y0), (x1, y1), 255, 3)
            persisted = float(np.count_nonzero((edge > 0) & (st["mask"] > 0))) / max(1, int(np.count_nonzero(edge))) > 0.5
        if persisted:
            return {"class": "shape_draw", "confidence": 0.75, "params": {"bbox": band["bbox"]}, "evidence": ev}
        return {"class": "rubber_band_with_selection", "confidence": 0.85, "params": {"bbox": band["bbox"], "changed_ratio": round(st["changed_ratio"], 4)}, "evidence": ev}
    if drag:
        if drag.get("path"):
            sk = detect_stroke(a, b, drag["path"])
            ev["stroke"] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in sk.items()}
            if sk["found"]:
                return {"class": "stroke", "confidence": 0.85, "params": {"changed_px": sk["changed_px"]}, "evidence": ev}
        if drag.get("vec") and math.hypot(*drag["vec"]) >= 25:
            tr = detect_translation_of_blob(a, b, drag["vec"])
            ev["translation"] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in tr.items() if k != "vector"}
            if tr["found"]:
                return {"class": "translate_object", "confidence": 0.75, "params": {"vector": tuple(round(x, 1) for x in tr["vector"])}, "evidence": ev}
    if st["changed_ratio"] >= 0.04:
        return {"class": "nonrigid", "confidence": 0.65, "params": {"changed_ratio": round(st["changed_ratio"], 4)}, "evidence": ev}
    return {"class": "local_change", "confidence": 0.7, "params": {"changed_ratio": round(st["changed_ratio"], 4), "bbox": st["bbox"]}, "evidence": ev}
