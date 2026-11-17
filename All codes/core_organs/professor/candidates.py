"""
professor.candidates -- find EVERY place on a picture that could be a control, without asking a language model.

Why this exists: a 7B vision model needs minutes to enumerate a screen by writing boxes (generation is the cost), and it forgets small icons. Seeing is cheap,
naming is the expensive part -- so the enumeration is classical computer vision + OCR, and the VLM only NAMES what was found (professor.labeler) and
re-checks what is left over (professor.coverage). Stages:

  ink_mask      pixels that differ from their local background, either polarity (dark themes and light themes alike) + edges
  icon_blobs    connected glyph shapes, strokes merged into whole icons, text fragments removed
  ocr_phrases   Tesseract words per tile (auto polarity, 2x upscale), grouped into phrases = menu items / tab names / button captions
  strips        rows (and columns) of tokens with uniform size and generous gaps = toolbars, menu bars, tab strips, ribbon groups;
                adjacent rows merge into one band (a ribbon)  -- "the whole button section"
  stack/merge   icon + caption below it, icon + drop-down caret  -> ONE candidate
  rect shapes   boxed buttons (OK / Cancel / web buttons), checkboxes / radios, text fields
All sizes scale with the display scale factor. Pure numpy/OpenCV/PIL; every stage is time-boxed and reports what it skipped.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from .schema import Box, fold

try:
    import cv2
except Exception:                                                                       # pragma: no cover
    cv2 = None

try:
    import pytesseract
except Exception:                                                                       # pragma: no cover
    pytesseract = None


@dataclass
class Candidate:
    box: Box
    kind: str                                  # icon | text | icon_label | rect_button | checkbox | radio | field | caret
    score: float = 0.5
    text: str = ""
    ocr_conf: float = 0.0
    in_strip: int = -1                         # index into CandidateSet.strips, -1 = outside every strip
    has_dropdown: bool = False
    flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"box": self.box.to_list(), "kind": self.kind, "score": round(self.score, 3), "text": self.text, "in_strip": self.in_strip,
                "has_dropdown": self.has_dropdown, "flags": self.flags}


@dataclass
class Strip:
    """A row or column of controls: a toolbar, menu bar, tab strip or one ribbon row. `band` groups rows that touch (a ribbon)."""
    box: Box
    orient: str                                # row | col
    members: List[int] = field(default_factory=list)      # indexes into CandidateSet.candidates
    band: int = -1
    word_frac: float = 0.0                     # share of members that are text (menu bar / tabs vs. icon toolbar)


@dataclass
class CandidateSet:
    candidates: List[Candidate] = field(default_factory=list)
    strips: List[Strip] = field(default_factory=list)
    bands: List[Box] = field(default_factory=list)
    timings: Dict[str, float] = field(default_factory=dict)
    skipped: List[str] = field(default_factory=list)
    size: Tuple[int, int] = (0, 0)


# ------------------------------------------------------------------------------------------------------------ ink
def _gray(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L"))


def ink_mask(gray: np.ndarray, scale: float = 1.0, thresh: int = 22) -> np.ndarray:
    """uint8 mask (0/255) of pixels that stand out from their local surroundings OR sit on a strong edge. Works for dark-on-light and light-on-dark."""
    if cv2 is None:
        raise RuntimeError("OpenCV missing")
    k = int(max(9, round(11 * scale))) | 1
    local = cv2.blur(gray, (k, k))
    diff = cv2.absdiff(gray, local) > thresh
    edges = cv2.Canny(gray, 50, 140) > 0
    return ((diff | edges).astype(np.uint8)) * 255


def _components(mask: np.ndarray, min_area: int = 4) -> List[Tuple[int, int, int, int, int]]:
    n, _lab, stats, _c = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = (int(v) for v in stats[i])
        if a >= min_area:
            out.append((x, y, x + w, y + h, a))
    return out


def icon_blobs(ink: np.ndarray, scale: float = 1.0, max_side: float = 72.0) -> List[Box]:
    """Glyph-sized connected shapes. Strokes of one icon (a magnifier ring + handle, a gear's teeth) are merged by closing and by box proximity."""
    k = max(3, int(round(3 * scale)) | 1)
    closed = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)), iterations=1)
    comps = _components(closed, min_area=int(6 * scale))
    boxes = [Box(x1, y1, x2, y2) for x1, y1, x2, y2, _a in comps]
    boxes = _merge_close(boxes, gap=2.0 * scale, max_side=max_side * scale)
    lim = max_side * scale
    out = []
    for b in boxes:
        w, h = b.w, b.h
        if w > lim or h > lim:
            continue
        if min(w, h) < 7 * scale:
            if max(w, h) >= 8 * scale and min(w, h) >= 1.0 and max(w, h) <= 34 * scale and max(w, h) / max(1.0, min(w, h)) <= 14:
                out.append(Box(b.x1, b.y1 - (7 * scale - h) / 2 if h < 7 * scale else b.y1, b.x2, b.y2 + (7 * scale - h) / 2 if h < 7 * scale else b.y2))   # thin: kept as a flagged candidate
            continue
        if max(w, h) / max(1.0, min(w, h)) > 4.5:
            continue
        out.append(b)
    return out


def _merge_close(boxes: List[Box], gap: float, max_side: float) -> List[Box]:
    """Union-find merge of boxes closer than `gap` pixels, refusing merges that would exceed max_side."""
    n = len(boxes)
    if n < 2:
        return boxes
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(n), key=lambda i: boxes[i].x1)
    for ai, i in enumerate(order):
        bi = boxes[i]
        for j in order[ai + 1:]:
            bj = boxes[j]
            if bj.x1 > bi.x2 + gap:
                break
            if bj.y1 > bi.y2 + gap or bj.y2 < bi.y1 - gap:
                continue
            u = boxes[find(i)].union(boxes[find(j)])
            if u.w <= max_side and u.h <= max_side:
                parent[find(j)] = find(i)
    groups: Dict[int, Box] = {}
    for i in range(n):
        r = find(i)
        groups[r] = boxes[i] if r not in groups else groups[r].union(boxes[i])
    return list(groups.values())


# ------------------------------------------------------------------------------------------------------------ OCR
@dataclass
class Word:
    text: str
    box: Box
    conf: float


def tesseract_ok() -> bool:
    if pytesseract is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _ocr_tile(tile: Image.Image, invert: bool, up: float) -> List[Word]:
    g = tile.convert("L")
    if invert:
        g = Image.eval(g, lambda v: 255 - v)
    if up != 1.0:
        g = g.resize((max(8, int(g.width * up)), max(8, int(g.height * up))), Image.LANCZOS)
    d = pytesseract.image_to_data(g, config="--psm 11 --oem 1", output_type=pytesseract.Output.DICT)
    out: List[Word] = []
    for i, t in enumerate(d["text"]):
        t = (t or "").strip()
        try:
            c = float(d["conf"][i])
        except Exception:
            c = -1.0
        if not t or c < 30:
            continue
        x, y, w, h = d["left"][i] / up, d["top"][i] / up, d["width"][i] / up, d["height"][i] / up
        if w < 3 or h < 5:
            continue
        out.append(Word(t, Box(x, y, x + w, y + h), c))
    return out


def _gap_cuts(profile: np.ndarray, size: int, search: int = 110, min_gap: int = 3) -> List[int]:
    """Positions along an axis where to cut a long strip into pieces of about `size`: at the middle of the widest ink-free run near each nominal position,
    so a cut falls between words/lines, not through a word."""
    n = len(profile)
    if n <= size * 1.25:
        return [0, n]
    cuts = [0]
    nominal = size
    while nominal < n - size // 3:
        lo, hi = max(cuts[-1] + size // 2, nominal - search), min(n - 1, nominal + search)
        best, best_len = None, 0
        run_start = None
        for i in range(lo, hi + 1):
            if profile[i] == 0:
                if run_start is None:
                    run_start = i
            else:
                if run_start is not None and i - run_start > best_len:
                    best, best_len = (run_start + i) // 2, i - run_start
                run_start = None
        if run_start is not None and hi + 1 - run_start > best_len:
            best, best_len = (run_start + hi + 1) // 2, hi + 1 - run_start
        if best is None or best_len < min_gap:
            best = lo + int(np.argmin(profile[lo:hi + 1]))
        cuts.append(int(best))
        nominal = int(best) + size
    cuts.append(n)
    return cuts


def plan_tiles(ink: np.ndarray, tile: Tuple[int, int] = (1200, 520)) -> List[Tuple[int, int, int, int]]:
    """OCR windows (x1, y1, x2, y2): rows are cut in ink-free stripes between bands/lines, then each row chunk is cut in ink-free columns."""
    H, W = ink.shape
    rows = (ink > 0).sum(axis=1)
    out: List[Tuple[int, int, int, int]] = []
    ys = _gap_cuts(rows, tile[1], search=70, min_gap=1)
    for a, b in zip(ys[:-1], ys[1:]):
        cols = (ink[a:b] > 0).sum(axis=0)
        xs = _gap_cuts(cols, tile[0], search=140, min_gap=4)
        for c, d in zip(xs[:-1], xs[1:]):
            out.append((max(0, c - 4), max(0, a - 4), min(W, d + 4), min(H, b + 4)))
    return out


def ocr_words(img: Image.Image, budget_s: float = 25.0, tile: Tuple[int, int] = (1200, 520), ink: Optional[np.ndarray] = None) -> Tuple[List[Word], Dict[str, Any]]:
    """Tesseract over windows whose edges fall in ink-free gaps. Polarity is decided per window (both are run on mixed ones). Returns (words in picture px, meta)."""
    meta: Dict[str, Any] = {"engine": "tesseract", "tiles": 0, "seconds": 0.0, "truncated": False}
    if not tesseract_ok():
        meta["engine"] = "missing"
        return [], meta
    t0 = time.time()
    g = _gray(img)
    H, W = g.shape
    if ink is None:
        ink = ink_mask(g, 1.0)
    words: List[Word] = []
    for (x, y, x2, y2) in plan_tiles(ink, tile):
        if time.time() - t0 > budget_s:
            meta["truncated"] = True
            break
        sub = g[y:y2, x:x2]
        if sub.size == 0 or float(sub.std()) < 4.0 or float((ink[y:y2, x:x2] > 0).mean()) < 0.002:
            continue
        dark = float((sub < 110).mean())
        pil = img.crop((x, y, x2, y2))
        small_text = (y2 - y) < 200
        up = 3.0 if small_text and (x2 - x) * (y2 - y) < 700_000 else (2.0 if (y2 - y) * (x2 - x) < 1_300_000 else 1.5)
        runs = [dark > 0.5] if (dark < 0.25 or dark > 0.75) else [False, True]
        for inv in runs:
            for w in _ocr_tile(pil, inv, up):
                words.append(Word(w.text, w.box.shift(x, y), w.conf))
        meta["tiles"] += 1
    words = _dedupe_words(words)
    meta["seconds"] = round(time.time() - t0, 2)
    return words, meta


def ocr_inside(img: Image.Image, box: Box) -> Tuple[str, float]:
    """Read the caption INSIDE one boxed control with both polarities (white-on-accent buttons defeat a tile-level polarity choice). ('', 0) if unreadable."""
    if not tesseract_ok():
        return "", 0.0
    inner = box.expand(-3).clip(img.width, img.height)
    if not inner.valid or inner.w < 8 or inner.h < 6:
        return "", 0.0
    crop = img.crop(inner.ituple())
    best, best_score, best_conf = "", 0.0, 0.0
    for inv in (False, True):
        try:
            ws = _ocr_tile(crop, inv, 3.0)
        except Exception:
            continue
        if not ws:
            continue
        txt = " ".join(w.text for w in sorted(ws, key=lambda q: (round(q.box.cy / 8), q.box.x1)))
        conf = float(np.mean([w.conf for w in ws]))
        score = conf * sum(ch.isalnum() for ch in txt)
        if score > best_score:
            best, best_score, best_conf = txt, score, conf
    return best, best_conf


def _dedupe_words(words: List[Word]) -> List[Word]:
    words = sorted(words, key=lambda w: -w.conf)
    keep: List[Word] = []
    for w in words:
        dup = False
        for k in keep:
            if w.box.iou(k.box) > 0.5 or (w.box.overlap_frac(k.box) > 0.8 and len(w.text) <= len(k.text)):
                dup = True
                break
        if not dup:
            keep.append(w)
    return keep


def group_phrases(words: Sequence[Word], gap_ratio: float = 0.9) -> List[Word]:
    """Words on one line closer than gap_ratio x line height form one phrase (a menu item 'Save As', a tab 'Page Layout')."""
    ws = sorted(words, key=lambda w: (round(w.box.cy / 6), w.box.x1))
    phrases: List[Word] = []
    used = [False] * len(ws)
    for i, w in enumerate(ws):
        if used[i]:
            continue
        cur = Word(w.text, w.box, w.conf)
        n = 1
        used[i] = True
        changed = True
        while changed:
            changed = False
            for j, o in enumerate(ws):
                if used[j]:
                    continue
                h = max(cur.box.h, o.box.h)
                if abs(o.box.cy - cur.box.cy) <= 0.45 * h and 0 <= o.box.x1 - cur.box.x2 <= gap_ratio * h:
                    cur = Word(cur.text + " " + o.text, cur.box.union(o.box), (cur.conf * n + o.conf) / (n + 1))
                    n += 1
                    used[j] = True
                    changed = True
        phrases.append(cur)
    return phrases


def _plausible_text(w: Word) -> bool:
    t = w.text.strip()
    if len(t) == 1:
        return t.isalnum() and w.conf >= 70
    alnum = sum(ch.isalnum() for ch in t)
    return alnum >= max(1, len(t) // 2) and w.conf >= 35


def _glyph_noise(p: Word, blobs: Sequence[Box]) -> bool:
    """Short low-confidence 'text' that is really the OCR misreading one or more icon glyphs (a picture icon read as 'fal')."""
    t = p.text.replace(" ", "")
    inside = [b for b in blobs if b.overlap_frac(p.box) >= 0.6]
    if len(inside) >= 2 and len(t) <= 6:
        return True
    return len(t) <= 3 and p.conf < 80 and bool(inside) and not t.isdigit()


# ----------------------------------------------------------------------------------------------------- strips
@dataclass
class _Tok:
    box: Box
    is_text: bool
    ref: int                                   # index into the candidate list


def _rows(toks: List[_Tok], scale: float) -> List[List[_Tok]]:
    toks = sorted(toks, key=lambda t: t.box.cy)
    rows: List[List[_Tok]] = []
    for t in toks:
        placed = False
        for r in rows:
            mcy = sum(x.box.cy for x in r) / len(r)
            mh = float(np.median([x.box.h for x in r]))
            if abs(t.box.cy - mcy) <= max(5 * scale, 0.45 * max(mh, t.box.h)):
                r.append(t)
                placed = True
                break
        if not placed:
            rows.append([t])
    return rows


def _split_runs(row: List[_Tok], scale: float) -> List[List[_Tok]]:
    row = sorted(row, key=lambda t: t.box.x1)
    runs: List[List[_Tok]] = [[row[0]]]
    for t in row[1:]:
        prev = runs[-1][-1]
        mh = float(np.median([x.box.h for x in runs[-1]] + [t.box.h]))
        if t.box.x1 - prev.box.x2 > max(7.0 * mh, 140 * scale):
            runs.append([t])
        else:
            runs[-1].append(t)
    return runs


def _run_ok(run: List[_Tok], scale: float, width: int = 0) -> bool:
    if len(run) == 2 and width and all(not t.is_text for t in run):
        xs = [t.box.cx for t in run]
        if (min(xs) > 0.86 * width or max(xs) < 0.14 * width) and max(t.box.h for t in run) <= 64 * scale:
            return True                                                        # window controls / a short toolbar stuck to a window edge
    if len(run) < 3:
        return False
    hs = sorted(t.box.h for t in run)
    if hs[-1] / max(1.0, hs[0]) > 4.0 and (hs[-2] / max(1.0, hs[0])) > 3.2:
        return False
    run = sorted(run, key=lambda t: t.box.x1)
    gaps = [run[i + 1].box.x1 - run[i].box.x2 for i in range(len(run) - 1)]
    mh = float(np.median([t.box.h for t in run]))
    # controls are padded apart; running text has tight word gaps (< ~0.35 x height)
    if float(np.median(gaps)) < 0.4 * mh and sum(t.is_text for t in run) / len(run) > 0.7:
        return False
    return True


def find_strips(cands: List[Candidate], scale: float, width: int = 0) -> Tuple[List[Strip], List[Box]]:
    """Rows then columns of control-like candidates. Rows that touch vertically (ribbon: 2-3 rows of buttons) are merged into one band."""
    toks = [_Tok(c.box, c.kind == "text", i) for i, c in enumerate(cands) if c.kind in ("icon", "text", "icon_label", "rect_button")]
    strips: List[Strip] = []
    for row in _rows(toks, scale):
        if len(row) < 2:
            continue
        for run in _split_runs(row, scale):
            if _run_ok(run, scale, width):
                from .schema import boxes_union
                bx = boxes_union(t.box for t in run)
                strips.append(Strip(bx.expand(3 * scale), "row", [t.ref for t in run], word_frac=sum(t.is_text for t in run) / len(run)))   # type: ignore[union-attr]
    # columns of icons (vertical toolbars / activity bars)
    icons = [t for t in toks if not t.is_text]
    cols: List[List[_Tok]] = []
    for t in sorted(icons, key=lambda t: t.box.cx):
        for c in cols:
            mcx = sum(x.box.cx for x in c) / len(c)
            if abs(t.box.cx - mcx) <= max(6 * scale, 0.5 * t.box.w):
                c.append(t)
                break
        else:
            cols.append([t])
    for c in cols:
        if len(c) < 4:
            continue
        c = sorted(c, key=lambda t: t.box.y1)
        gaps = [c[i + 1].box.y1 - c[i].box.y2 for i in range(len(c) - 1)]
        mh = float(np.median([t.box.h for t in c]))
        # a vertical toolbar: similar sizes, regular pitch, no huge holes
        pitch = [c[i + 1].box.cy - c[i].box.cy for i in range(len(c) - 1)]
        if max(gaps) > 3.5 * mh and len(c) < 6:
            continue
        if float(np.std(pitch)) > 0.6 * float(np.mean(pitch)) and len(c) < 6:
            continue
        from .schema import boxes_union
        bx = boxes_union(t.box for t in c)
        strips.append(Strip(bx.expand(3 * scale), "col", [t.ref for t in c], word_frac=0.0))              # type: ignore[union-attr]
    # bands: row strips that touch vertically and overlap horizontally
    order = sorted(range(len(strips)), key=lambda i: strips[i].box.y1)
    band_of: Dict[int, int] = {}
    bands: List[Box] = []
    for i in order:
        s = strips[i]
        if s.orient != "row":
            continue
        joined = -1
        for bi, bb in enumerate(bands):
            vgap = max(s.box.y1 - bb.y2, bb.y1 - s.box.y2)
            xo = min(s.box.x2, bb.x2) - max(s.box.x1, bb.x1)
            if vgap <= max(8 * scale, 0.9 * s.box.h) and xo >= 0.4 * min(s.box.w, bb.w):
                joined = bi
                break
        if joined < 0:
            bands.append(s.box)
            band_of[i] = len(bands) - 1
        else:
            bands[joined] = bands[joined].union(s.box)
            band_of[i] = joined
    for i, s in enumerate(strips):
        s.band = band_of.get(i, -1)
    return strips, bands


# ------------------------------------------------------------------------------------------ merge icon + caption
def _stack_merge(icons: List[Candidate], texts: List[Candidate], scale: float) -> Tuple[List[Candidate], List[Candidate]]:
    """Ribbon-style big buttons: an icon with its caption right below (centred) is ONE control. Returns (merged, remaining texts)."""
    used_t = set()
    out: List[Candidate] = []
    for ic in icons:
        best, bj = None, -1
        for j, t in enumerate(texts):
            if j in used_t:
                continue
            dx = abs(t.box.cx - ic.box.cx)
            vgap = t.box.y1 - ic.box.y2
            if ic.box.h >= 26 * scale and -2 * scale <= vgap <= (0.3 * ic.box.h + 3 * scale) and dx <= max(0.75 * max(ic.box.w, t.box.w), 10 * scale) and t.box.w <= 2.6 * max(ic.box.w, 24 * scale):
                if best is None or vgap < best:
                    best, bj = vgap, j
        if bj >= 0:
            t = texts[bj]
            used_t.add(bj)
            out.append(Candidate(ic.box.union(t.box), "icon_label", 0.8, t.text, t.ocr_conf, flags=["stacked"]))
        else:
            out.append(ic)
    rest = [t for j, t in enumerate(texts) if j not in used_t]
    return out, rest


def _caret_merge(cands: List[Candidate], scale: float) -> List[Candidate]:
    """A tiny glyph hugging the right/bottom edge of a larger control is its drop-down arrow: fold it in and flag has_dropdown."""
    out: List[Candidate] = []
    carets = [c for c in cands if c.kind == "icon" and c.box.w <= 11 * scale and c.box.h <= 11 * scale]
    big = [c for c in cands if c not in carets]
    used = set()
    for b in big:
        for k, c in enumerate(carets):
            if k in used:
                continue
            near_right = 0 <= c.box.x1 - b.box.x2 <= 5 * scale and abs(c.box.cy - b.box.cy) <= 0.6 * b.box.h
            near_below = 0 <= c.box.y1 - b.box.y2 <= 5 * scale and abs(c.box.cx - b.box.cx) <= 0.6 * b.box.w
            inside = b.box.expand(2 * scale).contains(c.box) and c.box.cx > b.box.cx + 0.2 * b.box.w
            if near_right or near_below or inside:
                b.box = b.box.union(c.box)
                b.has_dropdown = True
                used.add(k)
                break
        out.append(b)
    out.extend(c for k, c in enumerate(carets) if k not in used)           # lone carets stay (an expand arrow can be a control)
    return out


# ----------------------------------------------------------------------------------------------- rect shapes
def _line_segments(mask: np.ndarray, horizontal: bool, min_len: int) -> List[Tuple[float, float, float]]:
    """Straight edge segments as (start, end, position): horizontals (x1, x2, y), verticals (y1, y2, x). Thin connected components of the opened edge map."""
    n, _lab, stats, _c = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out: List[Tuple[float, float, float]] = []
    for i in range(1, n):
        x, y, w, h, _a = (int(v) for v in stats[i])
        if horizontal and w >= min_len and h <= 5:
            out.append((float(x), float(x + w), y + h / 2.0))
        elif not horizontal and h >= min_len and w <= 5:
            out.append((float(y), float(y + h), x + w / 2.0))
    return out


def _rectangles(hs: List[Tuple[float, float, float]], vs: List[Tuple[float, float, float]], scale: float, max_w: float, max_h: float) -> List[Box]:
    """Closed outlines from straight segments: a top and a bottom segment of about the same extent, joined by a left and a right segment. Rounded corners are
    fine (sides need only come within a corner radius of the ends); neighbouring controls cannot fuse because nothing is dilated."""
    tol = 6.0 * scale + 4.0
    rects: List[Box] = []
    hs = sorted(hs, key=lambda s: s[2])
    for i, top in enumerate(hs):
        for bot in hs[i + 1:]:
            hgt = bot[2] - top[2]
            if hgt < 10 * scale:
                continue
            if hgt > max_h:
                break
            if abs(top[0] - bot[0]) > tol or abs(top[1] - bot[1]) > tol:
                continue
            x1, x2 = min(top[0], bot[0]), max(top[1], bot[1])
            if x2 - x1 > max_w:
                continue
            left = [v for v in vs if abs(v[2] - x1) <= tol and v[0] <= top[2] + tol and v[1] >= bot[2] - tol]
            right = [v for v in vs if abs(v[2] - x2) <= tol and v[0] <= top[2] + tol and v[1] >= bot[2] - tol]
            if left and right:
                lx = min(v[2] for v in left)
                rx = max(v[2] for v in right)
                if rx - lx >= 10 * scale:
                    rects.append(Box(lx, top[2], rx, bot[2]))
    return rects


def rect_shapes(gray: np.ndarray, words: Sequence[Word], scale: float, ink: np.ndarray) -> List[Candidate]:
    """Boxed buttons (OK/Cancel/web buttons), text fields, check boxes and radios: CLOSED OUTLINES of control size, built from straight edge segments
    (top + bottom + left + right). Text, underlines, separators and icon strokes never close a box, so a paragraph does not turn into a hundred 'buttons',
    and two buttons a few pixels apart stay two buttons."""
    out: List[Candidate] = []
    H, W = gray.shape
    edges = cv2.Canny(gray, 40, 120)
    L = max(9, int(round(10 * scale)))
    hl = cv2.morphologyEx(edges, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (L, 1)))
    vl = cv2.morphologyEx(edges, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, L)))
    rects = _rectangles(_line_segments(hl, True, L), _line_segments(vl, False, L), scale, 460 * scale, 90 * scale)
    seen: List[Box] = []
    for b in sorted(rects, key=lambda r: r.area):
        x, y, w, h = int(b.x1), int(b.y1), int(b.w), int(b.h)
        if w < L + 4 or h < L + 2 or w >= W * 0.95 or h >= H * 0.95:
            continue
        if any(b.iou(s) > 0.6 for s in seen):
            continue
        seen.append(b)
        inside = [wd for wd in words if wd.box.overlap_frac(b) > 0.7]
        ar = w / max(1.0, h)
        inner = ink[y + 3:max(y + 4, y + h - 3), x + 3:max(x + 4, x + w - 3)]
        fill = float((inner > 0).mean()) if inner.size else 0.0
        if 0.8 <= ar <= 1.25 and w <= 26 * scale and not inside:
            out.append(Candidate(b, "checkbox", 0.65, flags=["shape"]))
        elif inside and 1.2 <= ar <= 14 and h <= 64 * scale:
            txt = " ".join(wd.text for wd in sorted(inside, key=lambda q: (round(q.box.cy / 8), q.box.x1)))
            out.append(Candidate(b, "rect_button", 0.75, txt, float(np.mean([q.conf for q in inside])), flags=["shape"]))
        elif ar >= 3.2 and 18 * scale <= h <= 48 * scale and w >= 70 * scale and fill < 0.4:
            out.append(Candidate(b, "field", 0.6, flags=["shape"]))
        elif 0.5 <= ar <= 4.2 and fill < 0.5 and max(w, h) <= 140 * scale and not inside:
            out.append(Candidate(b, "rect_button", 0.5, flags=["shape", "icon-button"]))
    # radios: small round outlines (no straight segments, so a separate circularity test on small edge blobs)
    if cv2 is not None:
        e2 = cv2.dilate(edges, np.ones((2, 2), np.uint8))
        cnts, _h = cv2.findContours(e2, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            if not (10 * scale <= w <= 26 * scale and 10 * scale <= h <= 26 * scale) or not (0.85 <= w / max(1, h) <= 1.18):
                continue
            peri = cv2.arcLength(c, True)
            area = cv2.contourArea(c)
            if peri <= 0 or 4 * np.pi * area / (peri * peri) < 0.82:
                continue
            b = Box(x, y, x + w, y + h)
            if any(b.iou(s) > 0.3 for s in seen) or any(wd.box.overlap_frac(b) > 0.3 for wd in words):
                continue
            seen.append(b)
            out.append(Candidate(b, "radio", 0.55, flags=["shape"]))
    return out


# ------------------------------------------------------------------------------------------------------- driver
def detect(img: Image.Image, scale: float = 1.0, ocr: bool = True, budget_s: float = 25.0, roi: Optional[Box] = None) -> CandidateSet:
    """All candidate controls on `img` (picture pixels). `roi` restricts the search (used when re-probing a changed area)."""
    t0 = time.time()
    res = CandidateSet(size=img.size)
    if cv2 is None:
        res.skipped.append("cv:opencv-missing")
        return res
    ox, oy = 0, 0
    work = img
    if roi is not None:
        r = roi.clip(img.width, img.height)
        if not r.valid:
            return res
        ox, oy = int(r.x1), int(r.y1)
        work = img.crop(r.ituple())
    gray = _gray(work)
    ts = time.time()
    ink = ink_mask(gray, scale)
    res.timings["ink"] = round(time.time() - ts, 3)

    ts = time.time()
    blobs = icon_blobs(ink, scale)
    res.timings["blobs"] = round(time.time() - ts, 3)

    words: List[Word] = []
    if ocr:
        remaining = max(2.0, budget_s - (time.time() - t0))
        words, meta = ocr_words(work, remaining, ink=ink)
        res.timings["ocr"] = meta.get("seconds", 0.0)
        if meta["engine"] == "missing":
            res.skipped.append("ocr:engine-missing")
        elif meta.get("truncated"):
            res.skipped.append("ocr:budget-truncated")
    words = [w for w in words if _plausible_text(w)]
    phrases = [p for p in group_phrases(words) if not _glyph_noise(p, blobs)]

    # glyph fragments that belong to text are not icons
    icons: List[Candidate] = []
    for b in blobs:
        if any(p.box.overlap_frac(b) >= 0.55 or (b.overlap_frac(p.box) >= 0.55) for p in phrases):
            continue
        thin = min(b.w, b.h) < 12 * scale and max(b.w, b.h) / max(1.0, min(b.w, b.h)) > 2.2
        icons.append(Candidate(b, "icon", 0.4 if thin else 0.5, flags=["thin"] if thin else []))
    texts = [Candidate(p.box.expand(1), "text", min(0.95, 0.4 + p.conf / 200.0), p.text, p.conf) for p in phrases]

    ts = time.time()
    icons, texts = _stack_merge(icons, texts, scale)
    icons = _caret_merge(icons, scale)
    shapes = rect_shapes(gray, words, scale, ink)
    if ocr:
        for sh in shapes:
            if sh.kind == "rect_button" and not sh.text and time.time() - t0 < budget_s:
                txt, cf = ocr_inside(work, sh.box)
                if sum(ch.isalnum() for ch in txt) >= 2 and cf >= 45:
                    sh.text, sh.ocr_conf = txt, cf
                    sh.flags = [f for f in sh.flags if f != "icon-button"]
                    sh.score = 0.75
    res.timings["merge+shapes"] = round(time.time() - ts, 3)

    allc = icons + texts
    # shape-derived boxed buttons replace the bare text candidate inside them
    for s in shapes:
        if s.kind == "rect_button":
            allc = [c for c in allc if not (c.kind == "text" and c.box.overlap_frac(s.box) > 0.7)]
        allc.append(s)

    # strips: only controls inside a strip keep icon status; stray icons survive only if they look like a control (big enough, boxed, or near a strip)
    ts = time.time()
    strips, bands = find_strips(allc, scale, work.width)
    in_strip = {}
    for si, s in enumerate(strips):
        for m in s.members:
            in_strip.setdefault(m, si)
    for i, c in enumerate(allc):
        c.in_strip = in_strip.get(i, -1)
        if c.in_strip >= 0:
            c.score = min(0.95, c.score + 0.25)
    res.timings["strips"] = round(time.time() - ts, 3)

    # shift back to picture coordinates and drop weak strays (icons outside any strip that are tiny)
    final: List[Candidate] = []
    remap: Dict[int, int] = {}
    for i, c in enumerate(allc):
        if c.kind == "icon" and c.in_strip < 0 and (max(c.box.w, c.box.h) < 12 * scale or "thin" in c.flags):
            continue
        c.box = c.box.shift(ox, oy)
        remap[i] = len(final)
        final.append(c)
    for s in strips:
        s.members = [remap[m] for m in s.members if m in remap]
        s.box = s.box.shift(ox, oy)
    res.candidates = final
    res.strips = strips
    res.bands = [b.shift(ox, oy) for b in bands]
    res.timings["total"] = round(time.time() - t0, 3)
    return res


def ink_density(ink: np.ndarray, box: Box) -> float:
    b = box.clip(ink.shape[1], ink.shape[0])
    if not b.valid:
        return 0.0
    x1, y1, x2, y2 = b.ituple()
    return float((ink[y1:y2, x1:x2] > 0).mean())
