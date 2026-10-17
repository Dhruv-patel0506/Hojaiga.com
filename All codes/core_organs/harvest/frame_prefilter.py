"""
harvest.frame_prefilter -- a millisecond test for "is this frame a screencast, not a presenter", run BEFORE Set-of-Marks (seconds of OCR) and before the VLM gate (seconds on the GPU).

The visual audit of the first real footage found ~40% of "pre" frames were not software UI at all (presenters, webcam insets, title cards, stock footage). Three cheap signals separate them:
  * a face: OpenCV's frontal-face cascade finds a face covering a real part of the frame (a webcam bubble in a corner is small and is allowed: the UI is still there);
  * skin tone: the fraction of pixels in the skin range of YCrCb (a close-up of a person, a hand on a keyboard);
  * edge density: an interface is made of text, lines and boxes (many edges); a title card, a gradient, a photograph or a blur is not.
Thresholds were calibrated on this project's own hand-judged frames (the UI-frame gate's verdicts), see DESIGN.md 19d. A frame that passes is still checked by the gate; this only removes the obvious ones cheaply.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Tuple

import numpy as np

MAX_FACE_FRAC = 0.10            # a face covering > 10% of the frame = a presenter close-up (a webcam bubble is ~1-4%)
MAX_SKIN_FRAC = 0.60
MIN_EDGE_DENSITY = 0.008        # < 0.8% edge pixels at 640 px wide = a flat card or gradient
_CASCADE = None


def _gray_and_ycrcb(img) -> Tuple[np.ndarray, np.ndarray]:
    import cv2
    arr = np.asarray(img.convert("RGB"))
    h, w = arr.shape[:2]
    if w > 640:
        arr = cv2.resize(arr, (640, int(h * 640 / w)), interpolation=cv2.INTER_AREA)
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)


def measure(img) -> Dict[str, float]:
    """{edge, skin, face}: edge-pixel fraction, skin-tone fraction, largest face area / frame area."""
    import cv2
    global _CASCADE
    gray, ycc = _gray_and_ycrcb(img)
    edge = float((cv2.Canny(gray, 80, 200) > 0).mean())
    cr, cb = ycc[..., 1], ycc[..., 2]
    skin = float(((cr >= 133) & (cr <= 173) & (cb >= 77) & (cb <= 127)).mean())
    face = 0.0
    try:
        if _CASCADE is None:
            _CASCADE = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
        faces = _CASCADE.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=6, minSize=(32, 32))
        if len(faces):
            face = max(w * h for (_x, _y, w, h) in faces) / float(gray.shape[0] * gray.shape[1])
    except Exception:
        pass
    return {"edge": edge, "skin": skin, "face": float(face)}


def looks_like_screencast(image, max_face: float = MAX_FACE_FRAC, max_skin: float = MAX_SKIN_FRAC, min_edge: float = MIN_EDGE_DENSITY) -> Tuple[bool, str]:
    """(keep, why). `image` is a path or a PIL image. An unreadable image is rejected."""
    from PIL import Image
    try:
        img = Image.open(image) if isinstance(image, (str, os.PathLike)) else image
        m = measure(img)
    except Exception as exc:
        return False, f"unreadable ({type(exc).__name__})"
    if m["face"] > max_face:
        return False, f"face covers {m['face']:.0%} of the frame"
    if m["skin"] > max_skin:
        return False, f"skin tone covers {m['skin']:.0%} of the frame"
    if m["edge"] < min_edge:
        return False, f"too few edges ({m['edge']:.1%}) for an interface"
    return True, ""
