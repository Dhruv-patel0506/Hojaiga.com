"""
canvas_colour -- colouring, custom colour mixing and multi-pass tonal shading as planned geometry + a measurable simulation.

From a reference image: k-means colour quantisation gives the dominant colours and a label map; each colour's connected regions become contained BASE fills; each region is split into four luminance bands
(deep shadow -> midtone -> base -> highlight) that are laid down in that order with different brushes and sizes; a region is filled with Paint's Fill bucket ONLY when its outline is closed (simulated on the
drawn outline first); otherwise it is filled with clipped hatch strokes so colour never bleeds outside its boundary. `FakeColourPainter` runs the same plan on a numpy colour canvas so the bleed, coverage and
band order are measured offline; `canvas_live` runs it on Paint (Edit colours dialog for exact RGB, Brushes / Size flyouts, Fill, Pencil).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from core_organs import canvas_artist as CA
from core_organs.canvas_artist import Box, Pt, Stroke

RGB = Tuple[int, int, int]
BAND_NAMES = ("deep_shadow", "midtone", "base", "highlight")
# brushes the Paint Brushes flyout offers (names as the application lists them); the plan asks for a CLASS of effect, the live painter maps it to what the flyout really contains
BRUSH_FOR_BAND = {"deep_shadow": ("Marker", 9), "midtone": ("Watercolour", 7), "base": ("Oil", 5), "highlight": ("Pencil", 2)}


# ------------------------------------------------------------------------------------------------------------------------------------ palette and regions
def kmeans_palette(img_bgr: np.ndarray, k: int = 8, seed: int = 3) -> Tuple[List[RGB], np.ndarray, List[int]]:
    """(colours as RGB, label map HxW, pixel counts) from k-means on a downsampled copy of the image, ordered from the most to the least common colour."""
    import cv2
    h, w = img_bgr.shape[:2]
    small = cv2.resize(img_bgr, (max(1, w // 3), max(1, h // 3)), interpolation=cv2.INTER_AREA)
    data = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    cv2.setRNGSeed(seed)
    _c, lab_s, centers = cv2.kmeans(data, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 25, 0.5), 3, cv2.KMEANS_PP_CENTERS)
    full = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB).astype(np.float32).reshape(-1, 3)
    d = ((full[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    labels = np.argmin(d, axis=1).reshape(h, w)
    counts = [int((labels == i).sum()) for i in range(k)]
    order = sorted(range(k), key=lambda i: -counts[i])
    remap = {old: new for new, old in enumerate(order)}
    labels = np.vectorize(remap.get)(labels).astype(np.int32)
    cols = []
    for i in order:
        bgr = cv2.cvtColor(np.uint8([[centers[i]]]), cv2.COLOR_LAB2BGR)[0, 0]
        cols.append((int(bgr[2]), int(bgr[1]), int(bgr[0])))
    return cols, labels, [counts[i] for i in order]


def regions(labels: np.ndarray, min_area: int = 400) -> List[Dict[str, Any]]:
    """Connected regions of each colour label: {label, mask, area, centroid}. Small specks are dropped."""
    import cv2
    out = []
    for lab in np.unique(labels):
        m = (labels == lab).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        n, cc, st, cen = cv2.connectedComponentsWithStats(m, connectivity=4)
        for i in range(1, n):
            if st[i, cv2.CC_STAT_AREA] >= min_area:
                out.append({"label": int(lab), "mask": (cc == i), "area": int(st[i, cv2.CC_STAT_AREA]), "centroid": (float(cen[i][0]), float(cen[i][1]))})
    return sorted(out, key=lambda r: -r["area"])


def to_canvas_mask(mask: np.ndarray, stats: Dict[str, Any], size: Tuple[int, int]) -> np.ndarray:
    """A mask in reference-image pixels -> a boolean mask in canvas-picture pixels, through the same map the tracer used (scale, offset)."""
    import cv2
    sc = stats["map"]["scale"]
    (ox, oy), (W, H) = stats["map"]["offset"], stats["map"]["size"]
    m = cv2.resize(mask.astype(np.uint8), (max(1, int(W * sc)), max(1, int(H * sc))), interpolation=cv2.INTER_NEAREST)
    full = np.zeros((size[1], size[0]), np.uint8)
    x0, y0 = int(round(ox)), int(round(oy))
    h, w = m.shape
    full[y0:y0 + h, x0:x0 + w] = m[:size[1] - y0, :size[0] - x0]
    return full > 0


def luminance_bands(gray: np.ndarray, mask: np.ndarray, n: int = 4) -> List[np.ndarray]:
    """Split `mask` into n bands by luminance quantiles, DARKEST FIRST: deep shadow, midtone, base, highlight."""
    vals = gray[mask]
    if vals.size < n:
        return [mask.copy()] + [np.zeros_like(mask) for _ in range(n - 1)]
    qs = np.quantile(vals, [i / n for i in range(1, n)])
    edges = [-1.0] + list(qs) + [256.0]
    return [mask & (gray > edges[i]) & (gray <= edges[i + 1]) for i in range(n)]


def shade_colours(base: RGB) -> Dict[str, RGB]:
    """The four tones of one base colour, mixed (not picked from a swatch): a cooler, darker shadow; a darker mid; the base; a lighter, slightly desaturated highlight."""
    import colorsys
    r, g, b = (c / 255.0 for c in base)
    h, l, s = colorsys.rgb_to_hls(r, g, b)

    def mk(dl: float, ds: float, dh: float = 0.0) -> RGB:
        rr, gg, bb = colorsys.hls_to_rgb((h + dh) % 1.0, max(0.0, min(1.0, l * dl)), max(0.0, min(1.0, s * ds)))
        return int(round(rr * 255)), int(round(gg * 255)), int(round(bb * 255))
    return {"deep_shadow": mk(0.45, 1.05, -0.02), "midtone": mk(0.75, 1.0), "base": mk(1.0, 1.0), "highlight": mk(1.0 + (1.0 - l) * 0.45 + 0.08, 0.8)}


# ------------------------------------------------------------------------------------------------------------------------------------ closure test and fills
def flood_area(outline: np.ndarray, seed: Pt, cap: int) -> Tuple[int, bool]:
    """Simulate Paint's bucket on the drawn outline: (pixels it would fill, leaks) -- leaks if it reaches the picture border or fills more than `cap` pixels (the region is not closed)."""
    import cv2
    h, w = outline.shape
    m = np.zeros((h + 2, w + 2), np.uint8)
    img = (outline > 0).astype(np.uint8) * 255
    sx, sy = int(round(seed[0])), int(round(seed[1]))
    if not (0 <= sx < w and 0 <= sy < h) or img[sy, sx]:
        return 0, True
    cv2.floodFill(img, m, (sx, sy), 128, flags=4 | (255 << 8))
    filled = m[1:-1, 1:-1] > 0
    area = int(filled.sum())
    touches = bool(filled[0, :].any() or filled[-1, :].any() or filled[:, 0].any() or filled[:, -1].any())
    return area, touches or area > cap


def hatch(mask: np.ndarray, spacing: float = 4.0, angle: float = 45.0, min_run: int = 3) -> List[List[Pt]]:
    """Parallel hatch lines CLIPPED to `mask` (2-point polylines, one per run of the line inside the region): strokes exist only where the region is, so colour cannot leave it. Vectorised per line, and
    limited to the mask's bounding box."""
    ys, xs = np.where(mask)
    if not len(xs):
        return []
    h, w = mask.shape
    x0, x1, y0, y1 = float(xs.min()), float(xs.max()), float(ys.min()), float(ys.max())
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    diag = math.hypot(x1 - x0, y1 - y0) + 4
    th = math.radians(angle)
    dx, dy = math.cos(th), math.sin(th)
    nx, ny = -dy, dx
    t = np.arange(-diag / 2, diag / 2, 1.0)
    out: List[List[Pt]] = []
    for k in np.arange(-diag / 2, diag / 2 + spacing, spacing):
        px, py = cx + nx * k + dx * t, cy + ny * k + dy * t
        ix, iy = np.rint(px).astype(int), np.rint(py).astype(int)
        ok = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h)
        inside = np.zeros(len(t), bool)
        inside[ok] = mask[iy[ok], ix[ok]]
        if not inside.any():
            continue
        d = np.diff(np.concatenate(([0], inside.astype(np.int8), [0])))
        for st_, en_ in zip(np.where(d == 1)[0], np.where(d == -1)[0]):
            if en_ - st_ >= min_run:
                out.append([(float(px[st_]), float(py[st_])), (float(px[en_ - 1]), float(py[en_ - 1]))])
    return out


@dataclass
class Op:
    kind: str                       # colour | brush | size | fill | stroke
    args: Dict[str, Any] = field(default_factory=dict)


def plan_colouring(img_bgr: np.ndarray, stats: Dict[str, Any], canvas_size: Tuple[int, int], outline: np.ndarray, k: int = 6, min_area: int = 900, max_regions: int = 10,
                   shade: bool = True, shade_top: int = 99) -> Tuple[List[Op], Dict[str, Any]]:
    """A multi-pass colouring plan: for each region (largest first) the BASE colour (bucket when the outline is closed, else clipped hatching), then the four tonal bands darkest-first with their brush and size.
    `outline` is the drawn line art as a canvas-sized mask (what Paint would see)."""
    import cv2
    cols, labels, counts = kmeans_palette(img_bgr, k)
    regs = regions(labels, int(min_area / max(stats["map"]["scale"] ** 2, 1e-6)))[:max_regions]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    ops: List[Op] = []
    info = {"palette": cols, "regions": [], "bucket": 0, "hatched": 0}
    for ri, r in enumerate(regs):
        cmask = to_canvas_mask(r["mask"], stats, (canvas_size[0], canvas_size[1]))
        cmask &= ~(cv2.dilate(outline.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
        area = int(cmask.sum())
        if area < min_area:
            continue
        base = cols[r["label"]]
        tones = shade_colours(base)
        ys, xs = np.where(cmask)
        seed = (float(np.median(xs)), float(np.median(ys)))
        if not cmask[int(seed[1]), int(seed[0])]:                                           # the median can fall outside a ring-shaped region: take the mask pixel nearest the centroid
            i = int(np.argmin((xs - xs.mean()) ** 2 + (ys - ys.mean()) ** 2))
            seed = (float(xs[i]), float(ys[i]))
        filled, leaks = flood_area(outline, seed, int(area * 1.6))
        ops.append(Op("colour", {"rgb": tones["base"], "role": "base", "region": ri}))
        if not leaks:
            ops.append(Op("fill", {"seed": seed, "expected_area": area, "region": ri, "mask": cmask}))
            info["bucket"] += 1
        else:
            ops.append(Op("brush", {"name": "Pencil", "size": 4}))
            for line in hatch(cmask, 4.0, 45.0):
                ops.append(Op("stroke", {"points": line, "region": ri, "mask_checked": True}))
            info["hatched"] += 1
        if shade and ri < shade_top:
            bands = luminance_bands(gray_in_canvas(gray, stats, canvas_size), cmask, 4)
            for bi, bname in enumerate(BAND_NAMES):
                if bname == "base" or int(bands[bi].sum()) < 120:
                    continue
                brush, size = BRUSH_FOR_BAND[bname]
                ops.append(Op("colour", {"rgb": tones[bname], "role": bname, "region": ri}))
                ops.append(Op("brush", {"name": brush, "size": size}))
                for line in hatch(bands[bi], 5.0 if bname != "highlight" else 4.0, 45.0 + 20 * bi):
                    ops.append(Op("stroke", {"points": line, "region": ri, "band": bname, "mask_checked": True}))
        info["regions"].append({"region": ri, "label": r["label"], "area": area, "base": tones["base"], "bucket": not leaks, "seed": seed})
        info.setdefault("masks", {})[ri] = cmask
    return ops, info


def gray_in_canvas(gray: np.ndarray, stats: Dict[str, Any], size: Tuple[int, int]) -> np.ndarray:
    import cv2
    sc = stats["map"]["scale"]
    (ox, oy), (W, H) = stats["map"]["offset"], stats["map"]["size"]
    g = cv2.resize(gray, (max(1, int(W * sc)), max(1, int(H * sc))), interpolation=cv2.INTER_AREA)
    full = np.full((size[1], size[0]), 255, np.uint8)
    x0, y0 = int(round(ox)), int(round(oy))
    h, w = g.shape
    full[y0:y0 + h, x0:x0 + w] = g[:size[1] - y0, :size[0] - x0]
    return full


# ------------------------------------------------------------------------------------------------------------------------------------ painters
class FakeColourPainter:
    """A numpy BGR canvas with Paint's colour behaviours (a current colour, a brush with a size, a bucket fill that stops at non-white-equal boundaries): the offline stand-in for the live painter."""

    def __init__(self, size: Tuple[int, int] = (1536, 864), canvas: Box = (190, 125, 1343, 771)):
        import cv2
        self.cv2 = cv2
        self.size, self.box = size, canvas
        self.img = np.full((size[1], size[0], 3), 243, np.uint8)
        x0, y0, x1, y1 = [int(v) for v in canvas]
        self.img[y0:y1 + 1, x0:x1 + 1] = 255
        self.rgb: RGB = (0, 0, 0)
        self.brush, self.width = "Pencil", 2
        self.log: List[Tuple[str, Any]] = []

    def grab(self):
        from PIL import Image
        return Image.fromarray(self.cv2.cvtColor(self.img, self.cv2.COLOR_BGR2RGB))

    def canvas(self) -> Box:
        return CA.find_canvas(self.grab())

    def select(self, name: str) -> bool:
        self.log.append(("select", name))
        return True

    def set_colour(self, rgb: RGB) -> bool:
        self.rgb = tuple(int(v) for v in rgb)
        self.log.append(("colour", self.rgb))
        return True

    def set_brush(self, name: str, size: int) -> bool:
        self.brush, self.width = name, max(1, int(size))
        self.log.append(("brush", (name, size)))
        return True

    def stroke(self, points: Sequence[Pt], width: int = 0) -> bool:
        pts = np.array([[int(round(x)), int(round(y))] for x, y in points], np.int32).reshape(-1, 1, 2)
        if len(pts) >= 2:
            self.cv2.polylines(self.img, [pts], False, (self.rgb[2], self.rgb[1], self.rgb[0]), width or self.width)
        return True

    def fill_at(self, x: float, y: float) -> bool:
        """Bucket: spreads over the connected area of (nearly) the clicked pixel's colour, like Paint's Fill with its default tolerance."""
        h, w = self.img.shape[:2]
        m = np.zeros((h + 2, w + 2), np.uint8)
        self.cv2.floodFill(self.img, m, (int(round(x)), int(round(y))), (self.rgb[2], self.rgb[1], self.rgb[0]), (6, 6, 6), (6, 6, 6), flags=4)
        self.log.append(("fill", (x, y)))
        return True


def apply_ops(painter: Any, ops: Sequence[Op]) -> Dict[str, int]:
    """Run a colouring plan on a painter (fake or live): colour / brush / size changes, bucket fills, strokes. Returns counts. Consecutive strokes go out as one batch when the painter can (the live one)."""
    n = {"colour": 0, "brush": 0, "fill": 0, "stroke": 0}
    pending: List[Any] = []

    def flush() -> None:
        if pending:
            if hasattr(painter, "stroke_batch"):
                for i in range(0, len(pending), 12):
                    painter.stroke_batch(pending[i:i + 12])
            else:
                for pts in pending:
                    painter.stroke(pts)
            pending.clear()
    t_start = time.time()
    for oi, op in enumerate(ops):
        a = op.args
        if oi % 40 == 0:
            print(f"[colour] op {oi}/{len(ops)} {op.kind} t={time.time() - t_start:.0f}s", flush=True)
        if op.kind == "stroke":
            pending.append(a["points"])
            n["stroke"] += 1
            continue
        flush()
        if op.kind == "colour":
            painter.set_colour(a["rgb"])
        elif op.kind == "brush":
            painter.set_brush(a["name"], a["size"])
        elif op.kind == "fill":
            ok = painter.fill_at(*a["seed"])
            if ok is False and a.get("mask") is not None:            # the bucket did not take (verified on the pixel): the same region is covered by strokes clipped to its mask
                n["fill_fallback"] = n.get("fill_fallback", 0) + 1
                lines = hatch(a["mask"], 4.0, 45.0)
                if hasattr(painter, "stroke_batch"):
                    for i in range(0, len(lines), 12):
                        painter.stroke_batch(lines[i:i + 12])
                else:
                    for ln in lines:
                        painter.stroke(ln)
        n[op.kind] = n.get(op.kind, 0) + 1
    flush()
    return n


def colour_metrics(before: Any, after: Any, ops: Sequence[Op], info: Dict[str, Any], canvas: Box, region_masks: Dict[int, np.ndarray]) -> Dict[str, Any]:
    """Coverage: % of each planned region that changed colour. Bleed: % of changed pixels that lie OUTSIDE every planned region (colour that escaped its boundary)."""
    a = np.asarray(before.convert("RGB")).astype(np.int16)
    b = np.asarray(after.convert("RGB")).astype(np.int16)
    changed = (np.abs(a - b).sum(axis=2) > 30)
    x0, y0, x1, y1 = [int(v) for v in canvas]
    inside = np.zeros_like(changed)
    inside[y0:y1 + 1, x0:x1 + 1] = True
    changed &= inside
    union = np.zeros_like(changed)
    cov = {}
    for ri, m in region_masks.items():
        union |= m
        cov[ri] = round(100.0 * float((changed & m).sum()) / max(float(m.sum()), 1.0), 1)
    import cv2
    near = cv2.dilate(union.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    bleed = float((changed & ~near).sum()) / max(float(changed.sum()), 1.0)
    return {"coverage_pct": cov, "mean_coverage_pct": round(sum(cov.values()) / max(len(cov), 1), 1), "bleed_pct": round(100.0 * bleed, 2), "changed_px": int(changed.sum())}
