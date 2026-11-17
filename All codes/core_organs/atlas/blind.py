"""
atlas.blind -- learning an application that gives the accessibility tree NOTHING (games, 3-D/DAW/DJ tools, GPU-drawn UIs).

When UI Automation sees a handful of frame buttons and the screen is full of widgets, the only honest evidence is PIXELS plus what
the pointer does. This module turns pixels into knowledge with three universal moves:

  PERCEIVE   OCR the captured window (Tesseract; the engine's OmniParser is an optional second source for icon-only widgets) ->
             labelled boxes: menu bars, tabs, section headers, field labels, values.
  HOVER      move the (posted) pointer over each box. Two measurements: does the picture react (hover highlight => the box is a
             real control, not a caption) and does a TOOLTIP appear (its text is recovered by OCR of the changed region). A tooltip
             is the program describing its own control -- often with the shortcut and even the scripting call behind it.
  OPEN       click ONLY the menu-bar cluster (found by gap analysis of the first text row), read the opened list by OCR, close it with
             Escape and PROVE the screen is back. Nothing else is ever clicked in a window the user owns.

No per-app code; every threshold is relative to the picture. Everything is reversible and verified by pixels.
"""

from __future__ import annotations

import re
import statistics
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import common as C
from . import motion

try:
    import pytesseract
    from PIL import Image
except Exception:  # pragma: no cover
    pytesseract = None
    Image = None


def available() -> bool:
    return pytesseract is not None


# --------------------------------------------------------------------------------------------------
# OCR -> labels
# --------------------------------------------------------------------------------------------------

def ocr_words(img: Any, *, psm: int = 11, min_conf: float = 50.0, scale: float = 1.0) -> List[Dict[str, Any]]:
    if pytesseract is None:
        return []
    im = Image.fromarray(np.asarray(img)) if not hasattr(img, "convert") else img
    if scale != 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)))
    d = pytesseract.image_to_data(im, output_type=pytesseract.Output.DICT, config=f"--psm {psm}")
    out = []
    for i in range(len(d["text"])):
        t = d["text"][i].strip()
        try:
            conf = float(d["conf"][i])
        except Exception:
            conf = -1
        if not t or conf < min_conf:
            continue
        x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        out.append({"text": t, "conf": conf, "box": (int(x / scale), int(y / scale), int((x + w) / scale), int((y + h) / scale)),
                    "line": (d["block_num"][i], d["par_num"][i], d["line_num"][i])})
    return out


def merge_labels(words: List[Dict[str, Any]], gap_factor: float = 0.9) -> List[Dict[str, Any]]:
    """Words on one line that sit close together become one label ('Texture Paint', 'Geometry Nodes')."""
    by_line: Dict[Tuple[int, int, int], List[Dict[str, Any]]] = {}
    for w in words:
        by_line.setdefault(w["line"], []).append(w)
    labels: List[Dict[str, Any]] = []
    for ws in by_line.values():
        ws.sort(key=lambda w: w["box"][0])
        cur = [ws[0]]
        for w in ws[1:]:
            prev = cur[-1]
            h = max(6, prev["box"][3] - prev["box"][1])
            if w["box"][0] - prev["box"][2] <= gap_factor * h:
                cur.append(w)
            else:
                labels.append(_label(cur))
                cur = [w]
        labels.append(_label(cur))
    return [l for l in labels if len(l["text"]) >= 1]


def _label(ws: List[Dict[str, Any]]) -> Dict[str, Any]:
    x0 = min(w["box"][0] for w in ws)
    y0 = min(w["box"][1] for w in ws)
    x1 = max(w["box"][2] for w in ws)
    y1 = max(w["box"][3] for w in ws)
    return {"text": " ".join(w["text"] for w in ws), "box": (x0, y0, x1, y1), "conf": round(sum(w["conf"] for w in ws) / len(ws), 1)}


def _iou(a, b) -> float:
    ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _contained(a, b) -> float:
    """Share of box `a` that lies inside box `b` (a cut-off native-scale fragment of a word the larger scale already read)."""
    ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    area = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    return inter / area


def ocr_multi(img: Any, *, scales: Sequence[float] = (1.0, 3.0)) -> List[Dict[str, Any]]:
    """Words from several scales, merged (the larger scale wins where both read the same place): measured on a 1938x1038 GPU-drawn UI, native size
    found 8 of 21 known menu words, x3 found 20 of 21."""
    out: List[Dict[str, Any]] = []
    for sc in sorted(scales, reverse=True):
        for w in ocr_words(img, psm=11, min_conf=45 if sc > 1 else 50, scale=sc):
            if not any(_iou(w["box"], o["box"]) > 0.4 or _contained(w["box"], o["box"]) > 0.5 for o in out):
                out.append(dict(w, line=(sc,) + tuple(w["line"])))
    return out


def perceive(img: Any, *, deep: bool = True) -> Dict[str, Any]:
    """Labelled boxes of everything readable in a captured window."""
    t0 = time.time()
    words = ocr_multi(img) if deep else ocr_words(img)
    labels = merge_labels(words)
    h, w = np.asarray(img).shape[:2]
    keep = [l for l in labels if re.search(r"[A-Za-z0-9]", l["text"]) and (l["box"][3] - l["box"][1]) <= 0.08 * h]
    for i, l in enumerate(sorted(keep, key=lambda l: (l["box"][1] // 12, l["box"][0]))):
        l["id"] = f"w{i}"
    return {"size": (w, h), "labels": sorted(keep, key=lambda l: (l["box"][1] // 12, l["box"][0])), "n_words": len(words), "seconds": round(time.time() - t0, 2)}


# --------------------------------------------------------------------------------------------------
# structure of the first text rows: menu bar / tab strip clusters
# --------------------------------------------------------------------------------------------------

def rows(labels: List[Dict[str, Any]], tol: int = 10) -> List[List[Dict[str, Any]]]:
    rs: List[List[Dict[str, Any]]] = []
    for l in sorted(labels, key=lambda l: (l["box"][1] + l["box"][3]) / 2):
        cy = (l["box"][1] + l["box"][3]) / 2
        for r in rs:
            if abs(sum((x["box"][1] + x["box"][3]) / 2 for x in r) / len(r) - cy) <= tol:
                r.append(l)
                break
        else:
            rs.append([l])
    for r in rs:
        r.sort(key=lambda l: l["box"][0])
    return rs


def menu_cluster(labels: List[Dict[str, Any]], window_h: int) -> List[Dict[str, Any]]:
    """The menu bar: on the text row (within the top 12%) holding the MOST short alphabetic entries, the leftmost run that ends at the first unusually wide
    gap (workspace tabs, tool strips and caption buttons sit beyond it). The title bar (one long text, a few fragments) is never the row."""
    short = lambda l: 2 <= len(l["text"]) <= 14 and l["text"][:1].isalpha() and l["text"][:1].isupper() and not re.search(r"[()\[\]{}|]", l["text"])
    cands = [r for r in rows(labels) if (sum(l["box"][1] for l in r) / len(r)) < 0.12 * window_h]
    best, best_n = None, 0
    for r in sorted(cands, key=lambda r: sum(l["box"][1] for l in r) / len(r)):
        n = sum(1 for l in r if short(l))
        if n > best_n:
            best, best_n = r, n
    if best is None or best_n < 3:
        return []
    row = [l for l in best if short(l)]
    gaps = [row[i + 1]["box"][0] - row[i]["box"][2] for i in range(len(row) - 1)]
    if not gaps:
        return row
    ref = statistics.median(gaps[:3]) if len(gaps) >= 3 else statistics.median(gaps)
    out = [row[0]]
    for i, g in enumerate(gaps):
        if g > max(1.9 * ref, ref + 14) and len(out) >= 3:
            break
        out.append(row[i + 1])
    return out


PY_CALL = re.compile(r"(?:Python|API)\s*:?\s*([A-Za-z_][\w.]*(?:\([^)\n]{0,60}\))?)")
SHORTCUT = re.compile(r"\(\s*((?:Ctrl|Shift|Alt|Cmd|Win|Tab|F\d+|Enter|Esc|Del|[A-Z])[^()]{0,24})\)")


# --------------------------------------------------------------------------------------------------
# the prober
# --------------------------------------------------------------------------------------------------

class BlindProber:
    def __init__(self, hwnd: int, app_key: str, *, store: Optional[C.AtlasStore] = None, run_id: str = "", budget_s: float = 60.0,
                 log: Optional[Callable[[str], None]] = None, evidence_dir: str = "", observer=None):
        from core_organs import headless_input as hin
        from . import gestures as G
        self.hin, self.G = hin, G
        self.hwnd, self.app_key = hwnd, app_key
        self.store = store or C.get_store()
        self.run_id = run_id or f"blind_{int(time.time())}"
        self.budget_s = budget_s
        self.t0 = time.time()
        self.log = log or (lambda s: None)
        self.ptr = G.Pointer(hwnd)
        self.evidence_dir = evidence_dir
        self.observer = observer
        self.widgets: List[Dict[str, Any]] = []
        self.menus: Dict[str, Any] = {}
        self.neutral: Optional[Tuple[int, int]] = None

    def left(self) -> float:
        return self.budget_s - (time.time() - self.t0)

    def grab(self):
        img, _ = self.hin.capture_window(self.hwnd)
        return None if img is None else np.asarray(img)

    def screen(self, x: float, y: float) -> Tuple[int, int]:
        wl, wt, _, _ = self.G.win_rect(self.hwnd)
        return int(wl + x), int(wt + y)

    def _park_pointer(self) -> None:
        """Move the posted pointer to a dead spot so no widget keeps its hover state."""
        if self.neutral:
            self.ptr.move(*self.neutral)
            time.sleep(0.12)

    # ---- perceive
    def perceive(self) -> Dict[str, Any]:
        img = self.grab()
        if img is None:
            return {"labels": [], "why": "capture unavailable"}
        pb = motion.painted_box(img)
        per = perceive(img)
        h, w = img.shape[:2]
        self.size = (w, h)
        # neutral spot: the largest label-free rectangle centre (coarse grid)
        occ = np.zeros((12, 20), bool)
        for l in per["labels"]:
            x0, y0, x1, y1 = l["box"]
            occ[max(0, y0 * 12 // h):min(12, y1 * 12 // h + 1), max(0, x0 * 20 // w):min(20, x1 * 20 // w + 1)] = True
        free = [(abs(r - 6) + abs(c - 10), r, c) for r in range(2, 10) for c in range(2, 18) if not occ[r, c]]
        if free:
            _, r, c = min(free)
            self.neutral = self.screen((c + 0.5) * w / 20, (r + 0.5) * h / 12)
        per["painted_box"] = pb
        self.base_img = img
        self.widgets = [{"id": l["id"], "label": l["text"], "box": l["box"], "conf": l["conf"], "interactive": None, "tooltip": ""} for l in per["labels"]]
        return per

    # ---- hover
    def hover(self, wd: Dict[str, Any]) -> Dict[str, Any]:
        x0, y0, x1, y1 = wd["box"]
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        self._park_pointer()
        before = self.grab()
        self.ptr.move(*self.screen(cx, cy))
        time.sleep(0.12)
        self.ptr.move(*self.screen(cx + 1, cy))
        time.sleep(0.15)
        mid = self.grab()
        time.sleep(0.8)
        after = self.grab()
        out: Dict[str, Any] = {"interactive": False, "tooltip": ""}
        if before is None or mid is None or after is None or before.shape != mid.shape:
            out["interactive"] = None
            return out
        gb, gm, ga = (motion.to_gray(im)[0] for im in (before, mid, after))
        pad = 6
        bx0, by0, bx1, by1 = max(0, x0 - pad), max(0, y0 - pad), min(gb.shape[1], x1 + pad), min(gb.shape[0], y1 + pad)
        hl = motion.diff_stats(gb[by0:by1, bx0:bx1], gm[by0:by1, bx0:bx1], thr=10)
        out["hover_px"] = hl["changed_px"]
        out["interactive"] = hl["changed_px"] >= max(12, int(0.03 * (bx1 - bx0) * (by1 - by0)))
        tt = motion.diff_stats(gm, ga, thr=14)
        if tt["changed_px"] >= 120 and tt["bbox"] is not None:
            tx0, ty0, tx1, ty1 = tt["bbox"]
            if (tx1 - tx0) * (ty1 - ty0) <= 0.25 * gb.size and (tx1 - tx0) >= 40:
                crop = after[max(0, ty0 - 4):ty1 + 4, max(0, tx0 - 4):tx1 + 4]
                words = ocr_words(crop, psm=6, min_conf=45, scale=2.0)
                text = " ".join(w["text"] for w in sorted(words, key=lambda w: (w["line"], w["box"][0])))
                if len(text) >= 3:
                    out["tooltip"] = text[:400]
                    out["tooltip_box"] = (tx0, ty0, tx1, ty1)
        self._park_pointer()
        time.sleep(0.2)
        back = self.grab()
        if back is not None and back.shape == before.shape:
            rest = motion.diff_stats(gb, motion.to_gray(back)[0], thr=14)
            out["restored"] = rest["changed_px"] < max(60, int(2e-5 * gb.size))
            if not out["restored"]:
                self.hin.post_key_combo(self.hwnd, "escape")
                time.sleep(0.25)
        return out

    def hover_scan(self, *, max_s: float = 40.0, limit: int = 120) -> Dict[str, Any]:
        t_end = time.time() + max_s
        n = 0
        # widgets that look like controls first: short labels, then the rest
        order = sorted(self.widgets, key=lambda w: (len(w["label"]) > 18, w["box"][1] // 40, w["box"][0]))
        for wd in order:
            if n >= limit or time.time() > t_end or self.left() < 2:
                break
            if not self.ptr.alive():
                break
            r = self.hover(wd)
            wd.update(r)
            n += 1
            if r.get("tooltip"):
                py = PY_CALL.search(r["tooltip"])
                sc = SHORTCUT.search(r["tooltip"])
                if py:
                    wd["api_call"] = py.group(1)
                if sc:
                    wd["shortcut"] = sc.group(1).strip()
            if self.observer:
                try:
                    self.observer("blind.hover", {"label_len": len(wd["label"]), "row": wd["box"][1] // 40}, "", "interactive" if wd.get("interactive") else "caption")
                except Exception:
                    pass
        react = sum(1 for w in self.widgets if w.get("interactive"))
        tips = sum(1 for w in self.widgets if w.get("tooltip"))
        return {"hovered": n, "interactive": react, "tooltips": tips, "seconds": round(time.time() - (t_end - max_s), 1)}

    # ---- open menu-bar entries (click, read, Escape, prove)
    def open_menus(self, cluster: Sequence[Dict[str, Any]], *, max_s: float = 25.0) -> Dict[str, Any]:
        t_end = time.time() + max_s
        res: Dict[str, Any] = {}
        for l in cluster:
            if time.time() > t_end or self.left() < 3 or not self.ptr.alive():
                break
            x0, y0, x1, y1 = l["box"]
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            self._park_pointer()
            before = self.grab()
            self.ptr.click(*self.screen(cx, cy), "left")
            time.sleep(0.45)
            opened = self.grab()
            rec: Dict[str, Any] = {"opened": False, "items": []}
            if before is not None and opened is not None and before.shape == opened.shape:
                st = motion.diff_stats(motion.to_gray(before)[0], motion.to_gray(opened)[0], thr=18)
                frac = st["changed_ratio"]
                rec["changed_ratio"] = round(frac, 4)
                if 0.004 <= frac <= 0.35 and st["bbox"] is not None:
                    bx0, by0, bx1, by1 = st["bbox"]
                    crop = opened[by0:by1, bx0:bx1]
                    words = ocr_words(crop, psm=6, min_conf=45, scale=1.6)
                    lines: Dict[Tuple[int, int, int], List[Dict[str, Any]]] = {}
                    for w in words:
                        lines.setdefault(w["line"], []).append(w)
                    items = []
                    for ws in sorted(lines.values(), key=lambda ws: ws[0]["box"][1]):
                        ws.sort(key=lambda w: w["box"][0])
                        txt = " ".join(w["text"] for w in ws)
                        if re.search(r"[A-Za-z]{2}", txt):
                            items.append(txt)
                    rec.update(opened=len(items) >= 2, items=items[:60], region=(bx0, by0, bx1, by1))
                elif frac > 0.35:
                    rec["effect"] = "layout_change"
            self.hin.post_key_combo(self.hwnd, "escape")
            time.sleep(0.35)
            back = self.grab()
            if before is not None and back is not None and back.shape == before.shape:
                rest = motion.diff_stats(motion.to_gray(before)[0], motion.to_gray(back)[0], thr=18)
                rec["restored"] = rest["changed_px"] < max(80, int(3e-5 * rest["mask"].size))
                if not rec["restored"]:
                    self.ptr.click(*self.neutral, "left") if False else None
                    self.hin.post_key_combo(self.hwnd, "escape")
                    time.sleep(0.3)
                    back = self.grab()
                    rest = motion.diff_stats(motion.to_gray(before)[0], motion.to_gray(back)[0], thr=18)
                    rec["restored"] = rest["changed_px"] < max(80, int(3e-5 * rest["mask"].size))
            res[l["text"]] = rec
            if not rec.get("restored", True):
                self.log(f"menu '{l['text']}' did not close cleanly: stopping menu probes")
                break
        self.menus.update(res)
        return res

    # ---- knowledge
    def persist(self) -> int:
        n = 0
        for wd in self.widgets:
            if wd.get("interactive") is None and not wd.get("tooltip"):
                continue
            ev = [C.Evidence("probe", f"{self.run_id}:hover:{wd['id']}", f"hover_px={wd.get('hover_px')}")]
            if wd.get("interactive"):
                self.store.claim(self.app_key, "ui.widget", f"'{wd['label']}' reacts to the pointer (a control, not a caption)", trust="measured", confidence=0.8, evidence=ev,
                                 value={"label": wd["label"], "box": wd["box"]}, source="atlas.blind")
                n += 1
            if wd.get("tooltip"):
                st = f"Tooltip of '{wd['label']}': {wd['tooltip']}"
                if wd.get("api_call"):
                    st += f"  [scripting call: {wd['api_call']}]"
                self.store.claim(self.app_key, "ui.tooltip", st, trust="measured", confidence=0.85,
                                 evidence=[C.Evidence("probe", f"{self.run_id}:tooltip:{wd['id']}", wd["tooltip"][:200])], value={k: wd.get(k) for k in ("label", "tooltip", "api_call", "shortcut")}, source="atlas.blind")
                n += 1
        for name, rec in self.menus.items():
            if rec.get("opened") and rec.get("items"):
                self.store.claim(self.app_key, "ui.menu", f"Menu '{name}' contains: " + "; ".join(rec["items"][:40]), trust="measured", confidence=0.8,
                                 evidence=[C.Evidence("probe", f"{self.run_id}:menu:{name}", " | ".join(rec["items"][:6]))], value={"menu": name, "items": rec["items"]}, source="atlas.blind")
                n += 1
        return n

    def run(self, *, hover_s: float = 35.0, menu_s: float = 25.0, open_menus: bool = True) -> Dict[str, Any]:
        per = self.perceive()
        out: Dict[str, Any] = {"labels": len(per.get("labels", [])), "ocr_s": per.get("seconds"), "painted_box": per.get("painted_box")}
        cluster = menu_cluster(per.get("labels", []), self.size[1]) if per.get("labels") else []
        out["menu_cluster"] = [l["text"] for l in cluster]
        out["hover"] = self.hover_scan(max_s=hover_s)
        if open_menus and cluster:
            out["menus"] = {k: {"opened": v.get("opened"), "items": len(v.get("items", [])), "restored": v.get("restored")} for k, v in self.open_menus(cluster, max_s=menu_s).items()}
        out["claims"] = self.persist()
        out["seconds"] = round(time.time() - self.t0, 1)
        return out
