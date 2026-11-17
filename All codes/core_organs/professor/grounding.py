"""
professor.grounding -- turning what a vision-language model WRITES about positions into real pixels.

Models disagree about coordinates: Qwen3-VL answers on a 0..1000 relative grid, Qwen2.5-VL in absolute pixels of the picture it was shown,
others in 0..1. `qwen_vl_scanner.locate` once read the 0..1000 grid as pixels, so every box was ~2x off on a 1920 px screen. This module
  * parses every common answer shape (JSON bbox_2d / box / point_2d, <box>(x1,y1),(x2,y2)</box>, bare [x1,y1,x2,y2], truncated arrays),
  * converts through a CoordMap that is MEASURED once per model (calibration scene with known buttons) instead of assumed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from .schema import Box

_NUM = r"(-?\d+(?:\.\d+)?)"
_RE_BOX_TAG = re.compile(r"\(\s*" + _NUM + r"\s*,\s*" + _NUM + r"\s*\)\s*,?\s*\(\s*" + _NUM + r"\s*,\s*" + _NUM + r"\s*\)")
_RE_ARRAY4 = re.compile(r"\[\s*" + _NUM + r"\s*,\s*" + _NUM + r"\s*,\s*" + _NUM + r"\s*,\s*" + _NUM + r"\s*\]")
_RE_POINT = re.compile(r"[\[\(]\s*" + _NUM + r"\s*,\s*" + _NUM + r"\s*[\]\)]")
_LABEL_KEYS = ("label", "name", "text", "description", "element", "title", "caption", "object")
_BOX_KEYS = ("bbox_2d", "bbox", "box_2d", "box", "rect", "bounding_box")
_POINT_KEYS = ("point_2d", "point", "center", "click_point", "xy")


@dataclass
class Detection:
    label: str = ""
    box: Optional[Tuple[float, float, float, float]] = None      # RAW model coordinates (not yet pixels)
    point: Optional[Tuple[float, float]] = None
    extra: Dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------------------------------------------------ JSON
def strip_fences(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
    t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def extract_json(text: str) -> Any:
    """Parse the first JSON value in a model answer; None if nothing parses. Handles code fences and chatter around the JSON."""
    t = strip_fences(text)
    try:
        return json.loads(t)
    except Exception:
        pass
    for oc, cc in (("{", "}"), ("[", "]")):
        a, b = t.find(oc), t.rfind(cc)
        if a >= 0 and b > a:
            try:
                return json.loads(t[a:b + 1])
            except Exception:
                continue
    return None


def salvage_objects(text: str) -> List[Dict[str, Any]]:
    """Every COMPLETE {...} object inside a (possibly truncated) JSON array: a token cap must not throw away the items already written."""
    t = strip_fences(text)
    out: List[Dict[str, Any]] = []
    depth, start, in_str, esc = 0, -1, False, False
    for i, ch in enumerate(t):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    o = json.loads(t[start:i + 1])
                    if isinstance(o, dict):
                        out.append(o)
                except Exception:
                    pass
                start = -1
    return out


def _first(d: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _as_box(v: Any) -> Optional[Tuple[float, float, float, float]]:
    try:
        if isinstance(v, (list, tuple)) and len(v) == 4 and not any(isinstance(x, (list, tuple, dict)) for x in v):
            a = [float(x) for x in v]
            return (a[0], a[1], a[2], a[3])
        if isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(p, (list, tuple)) and len(p) == 2 for p in v):
            return (float(v[0][0]), float(v[0][1]), float(v[1][0]), float(v[1][1]))
        if isinstance(v, dict):
            for ks in (("x1", "y1", "x2", "y2"), ("left", "top", "right", "bottom")):
                if all(k in v for k in ks):
                    return tuple(float(v[k]) for k in ks)          # type: ignore[return-value]
            if all(k in v for k in ("x", "y", "width", "height")):
                return (float(v["x"]), float(v["y"]), float(v["x"]) + float(v["width"]), float(v["y"]) + float(v["height"]))
    except Exception:
        return None
    return None


def _as_point(v: Any) -> Optional[Tuple[float, float]]:
    try:
        if isinstance(v, (list, tuple)) and len(v) == 2 and not any(isinstance(x, (list, tuple, dict)) for x in v):
            return (float(v[0]), float(v[1]))
    except Exception:
        return None
    return None


def _from_obj(o: Dict[str, Any]) -> Optional[Detection]:
    label = _first(o, _LABEL_KEYS)
    box = None
    for k in _BOX_KEYS:
        if k in o:
            box = _as_box(o[k])
            if box:
                break
    pt = None
    for k in _POINT_KEYS:
        if k in o:
            pt = _as_point(o[k])
            if pt:
                break
    if box is None and pt is None:
        return None
    extra = {k: v for k, v in o.items() if k not in _LABEL_KEYS + _BOX_KEYS + _POINT_KEYS}
    return Detection(str(label).strip() if label is not None else "", box, pt, extra)


def parse_detections(text: str) -> List[Detection]:
    """All boxes/points a model wrote, in order, with whatever label it gave. Never raises."""
    out: List[Detection] = []
    if not text:
        return out
    data = extract_json(text)
    objs: List[Dict[str, Any]] = []
    if isinstance(data, list):
        objs = [o for o in data if isinstance(o, dict)]
    elif isinstance(data, dict):
        inner = None
        for k in ("elements", "items", "controls", "buttons", "detections", "objects", "results", "boxes"):
            if isinstance(data.get(k), list):
                inner = data[k]
                break
        objs = [o for o in (inner if inner is not None else [data]) if isinstance(o, dict)]
    if not objs:
        objs = salvage_objects(text)
    for o in objs:
        d = _from_obj(o)
        if d:
            out.append(d)
    if out:
        return out
    # tag forms: <|object_ref_start|>save<|object_ref_end|><|box_start|>(x1,y1),(x2,y2)<|box_end|>
    for m in _RE_BOX_TAG.finditer(text):
        a = [float(g) for g in m.groups()]
        pre = text[max(0, m.start() - 80):m.start()]
        lab = re.findall(r"<\|object_ref_start\|>(.*?)<\|object_ref_end\|>", pre)
        out.append(Detection(lab[-1].strip() if lab else "", (a[0], a[1], a[2], a[3])))
    if out:
        return out
    for m in _RE_ARRAY4.finditer(text):
        a = [float(g) for g in m.groups()]
        out.append(Detection("", (a[0], a[1], a[2], a[3])))
    if out:
        return out
    for m in _RE_POINT.finditer(text):
        out.append(Detection("", None, (float(m.group(1)), float(m.group(2)))))
    return out


# --------------------------------------------------------------------------------------------------------- CoordMap
@dataclass
class CoordMap:
    """How a model's raw numbers map onto the picture it was shown.
    kind: norm1000 | unit | pixels (of the SENT picture) | linear (fraction = ax*x+bx, resolution-relative)."""
    kind: str = "norm1000"
    ax: float = 0.001
    bx: float = 0.0
    ay: float = 0.001
    by: float = 0.0
    measured: bool = False
    residual_px: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CoordMap":
        return CoordMap(**{k: d[k] for k in CoordMap.__dataclass_fields__ if k in d})

    def x(self, v: float, sent_w: float, orig_w: float) -> float:
        if self.kind == "pixels":
            return v * (orig_w / sent_w)
        if self.kind == "unit":
            return v * orig_w
        if self.kind == "norm1000":
            return v / 1000.0 * orig_w
        return (self.ax * v + self.bx) * orig_w

    def y(self, v: float, sent_h: float, orig_h: float) -> float:
        if self.kind == "pixels":
            return v * (orig_h / sent_h)
        if self.kind == "unit":
            return v * orig_h
        if self.kind == "norm1000":
            return v / 1000.0 * orig_h
        return (self.ay * v + self.by) * orig_h

    def box_to_px(self, raw: Tuple[float, float, float, float], sent: Tuple[int, int], orig: Tuple[int, int]) -> Optional[Box]:
        x1, y1, x2, y2 = raw
        b = Box(self.x(x1, sent[0], orig[0]), self.y(y1, sent[1], orig[1]), self.x(x2, sent[0], orig[0]), self.y(y2, sent[1], orig[1]))
        if b.x2 < b.x1:
            b = Box(b.x2, b.y1, b.x1, b.y2)
        if b.y2 < b.y1:
            b = Box(b.x1, b.y2, b.x2, b.y1)
        b = b.clip(orig[0], orig[1])
        return b if b.valid and b.w >= 1 and b.h >= 1 else None

    def point_to_px(self, raw: Tuple[float, float], sent: Tuple[int, int], orig: Tuple[int, int]) -> Tuple[float, float]:
        return (min(max(self.x(raw[0], sent[0], orig[0]), 0), orig[0]), min(max(self.y(raw[1], sent[1], orig[1]), 0), orig[1]))


def default_map(coord: str) -> CoordMap:
    if coord == "pixels":
        return CoordMap("pixels", 1.0, 0.0, 1.0, 0.0)
    if coord == "unit":
        return CoordMap("unit", 1.0, 0.0, 1.0, 0.0)
    return CoordMap("norm1000", 0.001, 0.0, 0.001, 0.0)


def fit_map(pairs_x: List[Tuple[float, float]], pairs_y: List[Tuple[float, float]], w: int, h: int) -> CoordMap:
    """Least-squares fit of (raw model value -> true pixel) per axis, then classified. pairs are (raw, true_px)."""
    import numpy as np

    def fit(p: List[Tuple[float, float]]) -> Tuple[float, float, float]:
        a = np.array([[r, 1.0] for r, _ in p], dtype=float)
        y = np.array([t for _, t in p], dtype=float)
        sol, *_ = np.linalg.lstsq(a, y, rcond=None)
        res = float(np.abs(a @ sol - y).mean())
        return float(sol[0]), float(sol[1]), res

    sx, ox, rx = fit(pairs_x)
    sy, oy, ry = fit(pairs_y)
    res = (rx + ry) / 2
    if abs(sx - 1.0) < 0.08 and abs(sy - 1.0) < 0.08 and abs(ox) < 0.05 * w:
        m = CoordMap("pixels", 1.0, 0.0, 1.0, 0.0)
    elif abs(sx * 1000.0 / w - 1.0) < 0.08 and abs(sy * 1000.0 / h - 1.0) < 0.08 and abs(ox) < 0.05 * w:
        m = CoordMap("norm1000", 0.001, 0.0, 0.001, 0.0)
    elif abs(sx * 1.0 / w - 1.0) < 0.08 and abs(sy * 1.0 / h - 1.0) < 0.08:
        m = CoordMap("unit", 1.0, 0.0, 1.0, 0.0)
    else:
        m = CoordMap("linear", sx / w, ox / w, sy / h, oy / h)
    m.measured, m.residual_px = True, res
    return m


# ----------------------------------------------------------------------------------------------- calibration scene
def _font(px: int):
    for name in ("segoeui.ttf", "arial.ttf", "tahoma.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except Exception:
            continue
    return ImageFont.load_default()


CALIBRATION_BUTTONS = [("Alpha", (90, 70, 330, 150), (210, 60, 60)), ("Bravo", (930, 90, 1190, 170), (40, 120, 200)),
                       ("Charlie", (140, 520, 420, 610), (40, 150, 80)), ("Delta", (700, 400, 1000, 500), (150, 90, 190))]


def calibration_scene(w: int = 1280, h: int = 720) -> Tuple[Image.Image, Dict[str, Tuple[int, int, int, int]]]:
    """A flat grey picture with four big, distinctly coloured, labelled buttons at known places (truth in picture pixels)."""
    img = Image.new("RGB", (w, h), (232, 232, 232))
    d = ImageDraw.Draw(img)
    truth: Dict[str, Tuple[int, int, int, int]] = {}
    f = _font(34)
    for name, (x1, y1, x2, y2), col in CALIBRATION_BUTTONS:
        x1, y1, x2, y2 = int(x1 * w / 1280), int(y1 * h / 720), int(x2 * w / 1280), int(y2 * h / 720)
        d.rounded_rectangle((x1, y1, x2, y2), radius=14, fill=col, outline=(30, 30, 30), width=3)
        tw = d.textlength(name, font=f)
        d.text(((x1 + x2) / 2 - tw / 2, (y1 + y2) / 2 - 20), name, fill=(255, 255, 255), font=f)
        truth[name] = (x1, y1, x2, y2)
    return img, truth


CALIBRATION_PROMPT = ("Locate every button in this picture. Reply ONLY with a JSON list of objects "
                      '{"label": "<text on the button>", "bbox_2d": [x1, y1, x2, y2]}.')


def calibrate_from_answer(answer: str, truth: Dict[str, Tuple[int, int, int, int]], sent: Tuple[int, int]) -> Optional[CoordMap]:
    """Match the model's answer to the known buttons by label and fit the CoordMap. None when fewer than 2 buttons were answered."""
    dets = parse_detections(answer)
    px: List[Tuple[float, float]] = []
    py: List[Tuple[float, float]] = []
    n = 0
    for d in dets:
        if not d.box or not d.label:
            continue
        key = next((k for k in truth if k.lower() == d.label.strip().lower()), None)
        if key is None:
            key = next((k for k in truth if k.lower() in d.label.lower()), None)
        if key is None:
            continue
        tx1, ty1, tx2, ty2 = truth[key]
        rx1, ry1, rx2, ry2 = d.box
        px += [(rx1, tx1), (rx2, tx2)]
        py += [(ry1, ty1), (ry2, ty2)]
        n += 1
    if n < 2:
        return None
    return fit_map(px, py, sent[0], sent[1])
