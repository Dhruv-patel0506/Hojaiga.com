"""
picture_tier -- the controls the accessibility tree does not name (a Calculator keypad, Paint's canvas and palette, a chat list, emoji, unlabeled icons) are found in the PICTURE and join the candidate set.

    needs_picture_tier(controls, size, min_controls=15) -> reason | ""    'few_controls' (the tree names fewer than `min_controls` real controls) or 'empty_viewport' (the central work area is covered by no control)
    picture_controls(img, uia_controls)  -> [control dicts]               OCR words + icon / panel contours from harvest.universal_scan.scan_image, minus anything the tree already names and minus window frame
    augment(img, controls, min_controls) -> (controls, info)              the tree's controls + the picture's, each picture control with name / type / box / source, ctl None (operated by its box)
    som_with_marks(controls, size)       -> Set-of-Marks                  one numbered element per control (the dot overlay '● [id]' is drawn from these ids by label_elements)

A control found only by picture is tagged source 'ocr' (a readable word) or 'icon' (no text: named 'icon at (x,y)' so the prompt can still choose it by position). The time cost (one OCR pass, ~1-3 s) is paid only when the tree is thin.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from core_organs import chrome_filter as CF

MIN_CONTROLS = 15
MAX_EXTRA = 120


def _real(controls: Sequence[Dict[str, Any]], size: Tuple[int, int]) -> List[Dict[str, Any]]:
    return [c for c in CF.drop_chrome(controls, size) if c.get("box") and c["box"][2] >= 4 and c["box"][3] >= 4]


def needs_picture_tier(controls: Sequence[Dict[str, Any]], size: Tuple[int, int], min_controls: int = MIN_CONTROLS) -> str:
    real = _real(controls, size)
    if len(real) < min_controls:
        return "few_controls"
    W, H = size
    cx0, cx1, cy0, cy1 = 0.25 * W, 0.75 * W, 0.30 * H, 0.80 * H                         # the central work area
    area = (cx1 - cx0) * (cy1 - cy0)
    covered = 0.0
    for c in real:
        x, y, w, h = c["box"]
        ox, oy = max(0.0, min(x + w, cx1) - max(x, cx0)), max(0.0, min(y + h, cy1) - max(y, cy0))
        if w * h < 0.9 * W * H:                                                         # a control as big as the window (the pane / the window itself) says nothing about its content
            covered += ox * oy
    return "empty_viewport" if covered < 0.04 * area else ""


def tile_boxes(arr: Any, min_members: int = 4) -> List[List[int]]:
    """Button tiles: repeated mid-size rectangles on a grid (a keypad, a palette, a row of keys) found from edges and the repetition itself. A lone rectangle is never a tile; four alike and aligned are."""
    import cv2
    import numpy as np
    gray = cv2.cvtColor(np.asarray(arr), cv2.COLOR_RGB2GRAY)
    edges = cv2.dilate(cv2.Canny(gray, 18, 55), np.ones((3, 3), np.uint8), iterations=1)
    cnts, _h = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    H, W = gray.shape[:2]
    cand: List[List[int]] = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if 26 <= w <= min(240, 0.6 * W) and 20 <= h <= min(140, 0.4 * H) and 0.45 <= w / h <= 4.5:
            if not any(abs(x - o[0]) < 5 and abs(y - o[1]) < 5 and abs(w - o[2]) < 8 and abs(h - o[3]) < 8 for o in cand):
                cand.append([x, y, w, h])
    keep: List[List[int]] = []
    for b in cand:
        like = [o for o in cand if abs(o[2] - b[2]) <= 0.15 * b[2] and abs(o[3] - b[3]) <= 0.15 * b[3]]
        aligned = [o for o in like if abs(o[1] - b[1]) <= 6 or abs(o[0] - b[0]) <= 6]
        if len(like) >= min_members and len(aligned) >= 2:
            keep.append(b)
    return keep


def _name_tile(ocr: Any, arr: Any, b: Sequence[int]) -> str:
    """The glyph on a tile: its crop, enlarged 4x, read on its own with the detector off and the score floor at 0 (a single digit on a dark key is missed when the window is read as a whole, and the engine's own
    0.5 floor drops it: measured on a Calculator keypad, '7' 0.38, '8' 0.29, '9' 0.50 - all right). A read below 0.25 is not a name."""
    import cv2
    x, y, w, h = b
    cx, cy = x + w // 2, y + h // 2
    half_w, half_h = min(w // 2 - 3, 28), min(h // 2 - 3, 16)
    crop = arr[max(0, cy - half_h):cy + half_h, max(0, cx - half_w):cx + half_w]
    if crop.size == 0:
        return ""
    big = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    try:
        res, _t = ocr(big, use_det=False, use_cls=False, use_rec=True, text_score=0.0)
    except Exception:
        return ""
    best = max(res or [], key=lambda r: float(r[2]), default=None)
    if best and float(best[2]) >= 0.25 and 0 < len(str(best[1]).strip()) <= 6:
        return str(best[1]).strip()
    return ""


def picture_controls(img: Any, uia_controls: Sequence[Dict[str, Any]], max_extra: int = MAX_EXTRA) -> List[Dict[str, Any]]:
    from core_organs.harvest import universal_scan as US
    import numpy as np
    arr = np.asarray(img.convert("RGB"))
    named = [{"bbox": list(c["box"])} for c in uia_controls if c.get("box")]
    found = US.scan_image(arr, named)
    out: List[Dict[str, Any]] = []
    size = (arr.shape[1], arr.shape[0])
    tiles = [t for t in tile_boxes(arr) if not any(abs(t[0] - n["bbox"][0]) < 6 and abs(t[1] - n["bbox"][1]) < 6 for n in named)]
    inside_tile = lambda b: any(t[0] - 2 <= b[0] + b[2] / 2 <= t[0] + t[2] + 2 and t[1] - 2 <= b[1] + b[3] / 2 <= t[1] + t[3] + 2 for t in tiles)
    ocr = US._ocr()
    for t in tiles:                                                                    # a tile takes the name of the word inside it, else the glyph read from its own crop
        words = [f for f in found if f.get("source") == "ocr" and t[0] <= f["bbox"][0] + f["bbox"][2] / 2 <= t[0] + t[2] and t[1] <= f["bbox"][1] + f["bbox"][3] / 2 <= t[1] + t[3]]
        nm = words[0]["name"] if words else _name_tile(ocr, arr, t)
        nm = nm or f"key at ({int(t[0] + t[2] / 2)},{int(t[1] + t[3] / 2)})"
        out.append({"name": nm, "type": "ButtonControl", "box": (int(t[0]), int(t[1]), int(t[2]), int(t[3])), "toggle": None, "ctl": None, "source": "tile"})
    found = [f for f in found if not inside_tile(f["bbox"])]
    for f in found:
        if f.get("source") not in ("ocr", "icon"):
            continue
        x, y, w, h = f["bbox"]
        if w < 4 or h < 4 or w > 0.5 * size[0] or h > 0.5 * size[1]:
            continue
        name = f.get("name") or f"icon at ({int(x + w / 2)},{int(y + h / 2)})"
        if CF.is_window_chrome(name, "", (x, y, w, h), size):
            continue
        out.append({"name": name, "type": "TextControl" if f["source"] == "ocr" else "IconControl", "box": (int(x), int(y), int(w), int(h)), "toggle": None, "ctl": None, "source": f["source"]})
    out.sort(key=lambda c: (c["box"][1] // 12, c["box"][0]))                           # reading order
    return out[:max_extra]


def augment(img: Any, controls: Sequence[Dict[str, Any]], min_controls: int = MIN_CONTROLS) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    size = img.size
    reason = needs_picture_tier(controls, size, min_controls)
    info: Dict[str, Any] = {"reason": reason, "added": 0, "uia": len(controls)}
    if not reason:
        return list(controls), info
    try:
        extra = picture_controls(img, controls)
    except Exception as exc:                                                            # a missing OCR engine must not break the cheap path: say so
        info["error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
        return list(controls), info
    info["added"] = len(extra)
    info["tiles"] = sum(1 for c in extra if c["source"] == "tile")
    info["ocr"] = sum(1 for c in extra if c["source"] == "ocr")
    info["icons"] = sum(1 for c in extra if c["source"] == "icon")
    return list(controls) + extra, info
