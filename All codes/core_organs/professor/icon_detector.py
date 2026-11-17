"""
professor.icon_detector -- OPTIONAL extra candidate source: OmniParser's icon detector (a YOLO model that is already on disk with the repo's OmniParser weights).

MEASURED before it was added (RTX 3050 laptop, CPU only - torch here is a CPU build): on a real UIA-blind editor (Blender, 1938x1029) the detector took 0.8 s, agreed with the CV
candidates on ~90 % of its boxes and ADDED 16 real controls (conf >= 0.3) the CV tier had merged or missed - header drop-down carets, visibility toggles, selection-mode and shading
buttons, timeline transport buttons - about +9 % on 195 candidates. On an application that has an accessibility tree (or the synthetic app, where CV already finds 45/45) it adds nothing,
so the sweeper only runs it where the tree is sparse or absent. It proposes BOXES only; names still come from the tree, OCR, icon memory or the vision model's contact sheets.

Guards: boxes that are already candidates (overlap) are dropped; a box must be control-sized and contain ink (no empty cells); confidence >= 0.3. Weights path: HOJAIGA_PROF_YOLO_WEIGHTS
or the OmniParser repo's `weights/icon_detect/model.pt` for the legacy model. Switch off with HOJAIGA_PROF_YOLO=0. DEFAULT: the ultralytics icon_detect model
(AGPL-3.0; local use) when installed, else icon_detect_v3 (MIT, plain PyTorch); HOJAIGA_PROF_YOLO_LEGACY=0 / 1 forces one.
"""

from __future__ import annotations

import importlib.util
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from . import candidates as CV
from .schema import Box

DEFAULT_WEIGHTS = r"D:\new_automation\OmniParser\weights\icon_detect\model.pt"
_MODEL: Any = None
_ERR = ""


def weights_path() -> str:
    return os.environ.get("HOJAIGA_PROF_YOLO_WEIGHTS", DEFAULT_WEIGHTS)


def enabled() -> bool:
    return os.environ.get("HOJAIGA_PROF_YOLO", "1") != "0"


# OmniParser v2's icon_detect_v3 (MIT): a TorchScript export of MultimediaTechLab's YOLO, run by plain PyTorch + OpenCV NMS - no ultralytics, no AGPL code or weights.
# The ultralytics icon_detect (AGPL-3.0) is preferred when installed (see legacy()); v3 is the fallback. Measured Oct-28: 2.5 s a screen on this CPU, tight boxes on
# PowerPoint's start screen (Home / New / Open / Options, template cards, search box, tabs).
V3_WEIGHTS = r"D:\new_automation\OmniParser\weights\icon_detect_v3\model.pt"


def legacy() -> bool:
    """The ultralytics model is the default when it is installed and its weights are on disk (the owner's choice, Oct-28: measured on the same PowerPoint capture it found
    110 boxes in 1.2 s against v3's 43 in 11.6 s); HOJAIGA_PROF_YOLO_LEGACY=0 forces the MIT v3 model, which is also the fallback when ultralytics is missing."""
    flag = os.environ.get("HOJAIGA_PROF_YOLO_LEGACY", "")
    if flag in ("0", "1"):
        return flag == "1"
    return os.path.isfile(weights_path()) and importlib.util.find_spec("ultralytics") is not None


def available() -> Tuple[bool, str]:
    """(usable, why not)."""
    if not enabled():
        return False, "switched off (HOJAIGA_PROF_YOLO=0)"
    if not legacy():
        return (True, "") if os.path.isfile(os.environ.get("HOJAIGA_PROF_YOLO_V3", V3_WEIGHTS)) else (False, f"v3 weights not found: {V3_WEIGHTS}")
    if not os.path.isfile(weights_path()):
        return False, f"weights not found: {weights_path()}"
    if importlib.util.find_spec("ultralytics") is None:
        return False, "the `ultralytics` package is not installed"
    return True, ""


def _load() -> Any:
    global _MODEL, _ERR
    if _MODEL is None and not _ERR:
        try:
            if legacy():
                from ultralytics import YOLO
                _MODEL = YOLO(weights_path())
            else:
                import torch
                _MODEL = torch.jit.load(os.environ.get("HOJAIGA_PROF_YOLO_V3", V3_WEIGHTS), map_location="cpu").eval()
        except Exception as exc:
            _ERR = f"{type(exc).__name__}: {str(exc)[:100]}"
    return _MODEL


def decode_v3(outs: Any, size: int, conf: float) -> Tuple[List[List[float]], List[float]]:
    """The v3 head: per scale, an icon score map (1 x g x g) and the box's distances to the cell centre (4 x g x g: left, top, right, bottom) in units of the stride."""
    import torch
    boxes: List[List[float]] = []
    scores: List[float] = []
    for k in range(0, len(outs), 2):
        sc = torch.sigmoid(outs[k][0, 0])
        reg = outs[k + 1][0]
        stride = size / sc.shape[0]
        ys, xs = torch.nonzero(sc >= conf, as_tuple=True)
        for yy, xx in zip(ys.tolist(), xs.tolist()):
            cx, cy = (xx + 0.5) * stride, (yy + 0.5) * stride
            l, t, r, b = reg[:, yy, xx].tolist()
            boxes.append([cx - l * stride, cy - t * stride, cx + r * stride, cy + b * stride])
            scores.append(float(sc[yy, xx]))
    return boxes, scores


def detect(img: Image.Image, conf: float = 0.3, imgsz: int = 1280) -> List[Tuple[Box, float]]:
    """Raw detector boxes [(box, confidence)] in picture pixels. [] when the model cannot load."""
    m = _load()
    if m is None:
        return []
    if legacy():
        r = m.predict(np.asarray(img.convert("RGB")), conf=conf, iou=0.7, imgsz=imgsz, device="cpu", verbose=False)[0]
        return [(Box(float(b[0]), float(b[1]), float(b[2]), float(b[3])), float(c)) for b, c in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy())]
    import cv2
    import torch
    rgb = img.convert("RGB")
    size = 640 if imgsz <= 640 else (imgsz // 32) * 32
    s = min(size / rgb.width, size / rgb.height)
    canvas = Image.new("RGB", (size, size), (114, 114, 114))                 # letterbox: keep the proportions, pad the rest
    canvas.paste(rgb.resize((max(1, int(rgb.width * s)), max(1, int(rgb.height * s)))), (0, 0))
    x = torch.from_numpy(np.asarray(canvas, np.float32) / 255.0).permute(2, 0, 1)[None]
    with torch.no_grad():
        outs = m(x)
    boxes, scores = decode_v3(outs, size, conf)
    if not boxes:
        return []
    keep = cv2.dnn.NMSBoxes([[b[0], b[1], b[2] - b[0], b[3] - b[1]] for b in boxes], scores, conf, 0.45)
    return [(Box(*(float(v) / s for v in boxes[i])), scores[i]) for i in np.array(keep).flatten()]


def _covered(b: Box, cands: List[Any]) -> bool:
    """Is this detector box already a candidate (the same control)? Kind-aware: against a TEXT candidate the box is covered when it lies inside the text or when the text is the label
    INSIDE this box (a tab / button around its caption); an icon merely NEXT to a label is not covered. Against icon / shape candidates any real overlap (offset duplicate) counts."""
    for c in cands:
        o = c.box
        if c.kind == "text":
            if b.overlap_frac(o) >= 0.7 or (o.overlap_frac(b) >= 0.85 and b.area <= 4.0 * o.area):
                return True
        elif b.iou(o) >= 0.15 or b.overlap_frac(o) >= 0.5 or o.overlap_frac(b) >= 0.5:
            return True
    return False


def augment(cs: Any, img: Image.Image, scale: float = 1.0, ink: Optional[np.ndarray] = None, conf: float = 0.3, budget_s: float = 60.0,
            detector: Optional[Any] = None) -> Dict[str, Any]:
    """Add detector boxes that are not yet candidates to `cs` (a CandidateSet). Returns {added, seen, seconds} or {skipped: why}. `detector` lets tests supply boxes."""
    t0 = time.time()
    if detector is None:
        ok, why = available()
        if not ok:
            return {"added": 0, "skipped": why}
        if _MODEL is None and budget_s < 15.0:
            return {"added": 0, "skipped": "not enough time budget left to load the detector"}
        det = detect(img, conf)
        if _ERR and not det:
            return {"added": 0, "skipped": _ERR}
    else:
        det = detector(img)
    if ink is None:
        ink = CV.ink_mask(np.asarray(img.convert("L")), scale)
    existing = list(cs.candidates)
    lo, hi = 8.0 * scale, 140.0 * scale
    added = 0
    for b, c in sorted(det, key=lambda t: -t[1]):
        if c < conf or b.w < lo or b.h < lo or b.w > hi or b.h > hi:
            continue
        if _covered(b, existing) or CV.ink_density(ink, b) < 0.03:
            continue
        cand = CV.Candidate(b, "icon", round(float(c), 3), flags=["yolo"])
        cs.candidates.append(cand)
        existing.append(cand)
        added += 1
    return {"added": added, "seen": len(det), "seconds": round(time.time() - t0, 2)}
