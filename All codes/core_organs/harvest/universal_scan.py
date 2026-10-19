"""
universal_scan -- scan an application ONCE, then load it from the registry in milliseconds.

    fingerprint(app)                 -> "exe-name|file_version"          (desktop)    or  "domain|layout_signature"  (web, via web_fingerprint)
    known(app_key, fp)               -> entry | None                      data/app_registry.json, read in <10 ms; None = never scanned / version changed / marked stale
    register(app_key, fp, controls)  -> entry                             after a deep scan: control names + the sources that found them
    mark_stale(app_key, fp, name)    -> None                              a control stopped matching: the next run diff-scans instead of rescanning everything
    diff(app_key, fp, controls)      -> {"new": [...], "gone": [...]}     what a diff-scan found; the entry is updated, only the new ones need learning
    scan_image(img)                  -> controls                          first-touch deep scan of a picture: OpenCV panel / icon contours + RapidOCR text (the 14.8 % of controls UIA does not name)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from typing import Any, Dict, List, Optional, Sequence

DATA = os.environ.get("HOJAIGA_DATA", os.path.join("D:" + os.sep, "new_automation", "data"))
REGISTRY = os.path.join(DATA, "app_registry.json")
_LOCK = threading.Lock()
_OCR: Any = None


def _exe_path(app: str) -> str:
    name = re.sub(r"\.exe$", "", app.strip(), flags=re.I)
    p = shutil.which(name + ".exe") or shutil.which(name) or ""
    if p:
        return p
    with __import__("contextlib").suppress(Exception):
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{name}.exe") as k:
                return winreg.QueryValueEx(k, "")[0].strip('"')
    return ""


def _file_version(path: str) -> str:
    if not path or not os.path.exists(path):
        return "unknown"
    with __import__("contextlib").suppress(Exception):
        import win32api
        info = win32api.GetFileVersionInfo(path, "\\")
        return "%d.%d.%d.%d" % (info["FileVersionMS"] >> 16, info["FileVersionMS"] & 0xFFFF, info["FileVersionLS"] >> 16, info["FileVersionLS"] & 0xFFFF)
    st = os.stat(path)
    return f"m{int(st.st_mtime)}s{st.st_size}"


def fingerprint(app: str, exe_path: str = "") -> str:
    path = exe_path or _exe_path(app)
    exe = os.path.basename(path).lower() if path else re.sub(r"\.exe$", "", app.strip().lower()) + ".exe"
    return f"{exe}|{_file_version(path)}"


def web_fingerprint(domain: str, controls: Sequence[str]) -> str:
    import hashlib
    sig = hashlib.sha1("|".join(sorted({c.lower() for c in controls if c})[:60]).encode("utf-8")).hexdigest()[:10]
    return f"{domain.lower()}|{sig}"


def _load() -> Dict[str, Any]:
    try:
        return json.load(open(REGISTRY, encoding="utf-8"))
    except Exception:
        return {}


def _save(d: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(REGISTRY), exist_ok=True)
    tmp = REGISTRY + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    os.replace(tmp, REGISTRY)


def known(app_key: str, fp: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        e = _load().get(f"{app_key}|{fp}")
    return e if e and not e.get("stale") else None


def register(app_key: str, fp: str, controls: Sequence[Dict[str, Any]], seconds: float = 0.0) -> Dict[str, Any]:
    names = sorted({str(c.get("name", "")).strip() for c in controls if c.get("name")})
    sources: Dict[str, int] = {}
    for c in controls:
        sources[c.get("source", "uia")] = sources.get(c.get("source", "uia"), 0) + 1
    e = {"app_key": app_key, "fingerprint": fp, "controls": names[:600], "n_controls": len(names), "sources": sources, "scan_seconds": round(seconds, 1), "ts": time.time(), "stale": False, "missed": []}
    with _LOCK:
        d = _load()
        d[f"{app_key}|{fp}"] = e
        _save(d)
    return e


def mark_stale(app_key: str, fp: str, name: str = "") -> None:
    with _LOCK:
        d = _load()
        e = d.get(f"{app_key}|{fp}")
        if e is not None:
            e["stale"] = True
            if name:
                e["missed"] = sorted(set(e.get("missed", [])) | {name})[:50]
            _save(d)


def diff(app_key: str, fp: str, controls: Sequence[Dict[str, Any]]) -> Dict[str, List[str]]:
    names = {str(c.get("name", "")).strip() for c in controls if c.get("name")}
    with _LOCK:
        d = _load()
        e = d.get(f"{app_key}|{fp}") or {}
        old = set(e.get("controls", []))
        new, gone = sorted(names - old), sorted(old - names)
        if e:
            e["controls"] = sorted(old | names)[:600]
            e["n_controls"] = len(e["controls"])
            e["stale"], e["missed"], e["ts"] = False, [], time.time()
            _save(d)
    return {"new": new, "gone": gone}


# ------------------------------------------------------------------------------------------------------------------------------ picture scan (first touch only)
def _ocr() -> Any:
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    return _OCR


def ocr_words(img: Any) -> List[Dict[str, Any]]:
    """RapidOCR text boxes of a picture (numpy BGR/RGB array or a path): [{name, bbox(x,y,w,h), score, source}]."""
    res, _t = _ocr()(img)
    out = []
    for box, text, score in res or []:
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        out.append({"name": str(text).strip(), "bbox": [int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys))], "score": float(score), "source": "ocr"})
    return [w for w in out if w["name"]]


def icon_boxes(img: Any, min_side: int = 14, max_side: int = 96) -> List[Dict[str, Any]]:
    """Small square-ish edge-dense blobs = toolbar icons / glyph buttons that carry no readable text (OpenCV contours)."""
    import cv2
    import numpy as np
    arr = np.asarray(img)
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY) if arr.ndim == 3 else arr
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=2)
    cnts, _h = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if min_side <= w <= max_side and min_side <= h <= max_side and 0.6 <= w / h <= 1.7:
            density = float(edges[y:y + h, x:x + w].mean()) / 255.0
            if 0.08 <= density <= 0.85:
                out.append({"name": "", "bbox": [x, y, w, h], "score": density, "source": "icon"})
    return out


def panel_boxes(img: Any, min_area_frac: float = 0.01) -> List[Dict[str, Any]]:
    """Large rectangles = panes, ribbons, dialogs (OpenCV contour of long straight edges)."""
    import cv2
    import numpy as np
    arr = np.asarray(img)
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY) if arr.ndim == 3 else arr
    edges = cv2.dilate(cv2.Canny(gray, 30, 90), np.ones((3, 3), np.uint8), iterations=1)
    cnts, _h = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = gray.shape[:2]
    out = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if w * h >= min_area_frac * W * H and w > 60 and h > 30:
            out.append({"name": "", "bbox": [x, y, w, h], "score": 1.0, "source": "panel"})
    return out


def scan_image(img: Any, uia_controls: Sequence[Dict[str, Any]] = ()) -> List[Dict[str, Any]]:
    """UIA/DOM controls + OCR words + icon / panel contours; an icon that sits inside an OCR word or a UIA control's box is dropped as already named."""
    words = ocr_words(img)
    named = [c.get("bbox") for c in list(uia_controls) + words if c.get("bbox")]

    def inside(b: Sequence[int]) -> bool:
        cx, cy = b[0] + b[2] / 2, b[1] + b[3] / 2
        return any(n[0] <= cx <= n[0] + n[2] and n[1] <= cy <= n[1] + n[3] for n in named)
    icons = [i for i in icon_boxes(img) if not inside(i["bbox"])]
    return [dict(c, source=c.get("source", "uia")) for c in uia_controls] + words + icons + panel_boxes(img)
