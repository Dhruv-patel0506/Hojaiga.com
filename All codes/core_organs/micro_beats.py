"""
micro_beats -- teaching as a sequence of ATOMIC BEATS, for any program, website or screen.

A beat is the smallest thing a tutor says and shows at once:

    (speech, what to draw, where, a short label, what to wait for)

The plan for 'how do I find a word?' is not a paragraph. It is: the toolbar lit (no wait) -> the one control to use, boxed, labelled, with its key -> wait for the person to click it (or press its key) ->
the next one. Where the thing to click is one of many look-alike cells in a panel the accessibility tree sees as a single box (a step grid, a palette, a timeline), the cell is found by dividing the panel with
OpenCV, never by a table of known apps.

Three ways to find WHERE, from cheapest and most exact to the most general:
    1. the accessibility tree      a control whose name the step mentions (boxes are exact)
    2. grid subdivision (OpenCV)   a cell of a repeated-cell panel: 'step 5', 'row 2'
    3. a vision model              handed in by the caller as `ground(text) -> box` when the first two find nothing (never required)

The wording of every beat is built here from structure (what kind of action, which control, which keys), not copied from the source of the step.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

STOP = {"the", "a", "an", "to", "of", "in", "on", "and", "or", "button", "tab", "menu", "click", "press", "select", "choose", "open", "then", "your", "this", "that", "with", "for", "it", "is", "will", "you",
        "can", "from", "into", "at", "by", "use", "using", "now", "next", "item", "option", "dialog", "box", "window", "icon", "field"}
UNSAFE = re.compile(r"\b(close|exit|quit|delete|remove|uninstall|erase|format|shutdown|sign out|log out|purchase|buy|pay|send|submit|publish)\b", re.I)
ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "last": -1}
ROW_TYPES = {"Button", "SplitButton", "MenuItem", "TabItem", "ToggleButton", "CheckBox", "RadioButton", "ListItem", "Hyperlink"}


@dataclass
class Beat:
    speech: str
    primitive: str = "none"                       # box_pointer | region | shape | none
    box: Optional[Tuple[float, float, float, float]] = None       # x1, y1, x2, y2 on the screen
    points: List[Tuple[float, float]] = field(default_factory=list)
    shape: str = ""                               # polygon | line | curve | arrow
    pill: str = ""
    wait: str = "next"                            # click | key:<k> | next | none
    keys: str = ""
    target: str = ""
    layer: str = ""                               # uia | grid | model | none
    expect: str = ""
    late: Optional[Dict[str, Any]] = None         # the step, kept when its control was not on screen at planning time (a dialog the earlier beat opens): it is looked for again when the beat comes up

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def tokens(s: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in STOP and len(w) > 1]


def name_score(want: Sequence[str], name: str) -> float:
    have = set(tokens(name))
    w = set(want)
    if not w or not have:
        return 0.0
    hit = len(w & have)
    return hit / max(len(w), len(have)) if hit else 0.0


def box_of(c: Dict[str, Any]) -> Tuple[float, float, float, float]:
    x, y, w, h = c["box"]
    return (float(x), float(y), float(x + w), float(y + h))


def locate(controls: Sequence[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    """The control a step names: exact name first, else the best overlap of meaningful words (needs a clear winner)."""
    if not name:
        return None
    low = name.strip().lower()
    exact = [c for c in controls if c["name"].strip().lower() == low]
    if len(exact) >= 1:
        return min(exact, key=lambda c: c["box"][2] * c["box"][3])
    want = tokens(name)
    scored = sorted(((name_score(want, c["name"]), c) for c in controls if c.get("name")), key=lambda x: -x[0])
    if scored and scored[0][0] >= 0.5 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1]
    return None


def find_in_text(controls: Sequence[Dict[str, Any]], text: str) -> Optional[Dict[str, Any]]:
    """The visible control whose whole name appears in the sentence (the longest such name wins)."""
    low = " " + re.sub(r"[^a-z0-9 ]+", " ", text.lower()) + " "
    best: Optional[Dict[str, Any]] = None
    for c in controls:
        n = re.sub(r"[^a-z0-9 ]+", " ", (c.get("name") or "").lower()).strip()
        if len(n) >= 3 and (" " + n + " ") in low and (best is None or len(n) > len(re.sub(r"[^a-z0-9 ]+", " ", best["name"].lower()).strip())):
            best = c
    return best


def region_of(controls: Sequence[Dict[str, Any]], c: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
    """The row of look-alike controls the control sits in (a toolbar, a ribbon group, a menu bar), as one box; None when it stands alone."""
    x1, y1, x2, y2 = box_of(c)
    cy, h = (y1 + y2) / 2.0, max(y2 - y1, 12.0)
    sib = [d for d in controls if d.get("type") in ROW_TYPES and abs(((box_of(d)[1] + box_of(d)[3]) / 2.0) - cy) <= max(10.0, 0.6 * h) and abs(d["box"][3] - c["box"][3]) <= 0.6 * max(c["box"][3], 14)]
    sib.sort(key=lambda d: box_of(d)[0])
    avg_w = sum(d["box"][2] for d in sib) / max(len(sib), 1)
    groups: List[List[Dict[str, Any]]] = []
    for d in sib:                                                           # a row is controls that follow each other; a far-away one (the window's own Close) is another row
        if groups and box_of(d)[0] - box_of(groups[-1][-1])[2] <= 1.5 * avg_w:
            groups[-1].append(d)
        else:
            groups.append([d])
    sib = next((g for g in groups if any(d is c for d in g)), [])
    if len(sib) < 3:
        return None
    return (min(box_of(d)[0] for d in sib) - 6, min(box_of(d)[1] for d in sib) - 5, max(box_of(d)[2] for d in sib) + 6, max(box_of(d)[3] for d in sib) + 5)


# ------------------------------------------------------------------------------------------------------------------------------------------------ grids
def detect_grid(image: Any, box: Tuple[float, float, float, float], min_cells: int = 6) -> Optional[List[List[Tuple[float, float, float, float]]]]:
    """Find the repeated cells inside a panel (a picture: BGR array or PIL image; `box` = the panel on it, x1 y1 x2 y2). Cells = contours of nearly the same, nearly square size; rows = cells whose centres
    share a height. Returns rows of cell boxes in the picture's coordinates (left to right, top to bottom), or None when no repeated-cell structure is there."""
    import cv2
    import numpy as np
    img = np.asarray(image.convert("RGB"))[:, :, ::-1] if hasattr(image, "convert") else image
    x1, y1, x2, y2 = [int(v) for v in box]
    crop = img[max(0, y1):y2, max(0, x1):x2]
    if crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    cells_all: List[Tuple[int, int, int, int]] = []
    for mode in (0, 1):                                                   # light cells on dark, then dark cells on light
        th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY if mode == 0 else cv2.THRESH_BINARY_INV, 21, -3 if mode == 0 else 3)
        cnts, _ = cv2.findContours(th, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        cand = []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            if w >= 8 and h >= 8 and 0.55 <= w / float(h) <= 1.8 and w * h < 0.2 * crop.shape[0] * crop.shape[1] and cv2.contourArea(c) >= 0.6 * w * h:
                cand.append((x, y, w, h))
        if len(cand) >= min_cells:
            ws = sorted(c[2] for c in cand)
            med = ws[len(ws) // 2]
            cand = [c for c in cand if 0.75 * med <= c[2] <= 1.3 * med]
            uniq: List[Tuple[int, int, int, int]] = []
            for c in sorted(cand, key=lambda c: (c[1], c[0])):               # a cell's outer and inner edge are two contours: one cell
                if not any(abs((c[0] + c[2] / 2.0) - (u[0] + u[2] / 2.0)) < 0.5 * c[2] and abs((c[1] + c[3] / 2.0) - (u[1] + u[3] / 2.0)) < 0.5 * c[3] for u in uniq):
                    uniq.append(c)
            cand = uniq
            if len(cand) >= min_cells:
                cells_all = cand
                break
    if len(cells_all) < min_cells:
        return None
    cells_all.sort(key=lambda c: (c[1] + c[3] / 2.0, c[0]))
    rows: List[List[Tuple[int, int, int, int]]] = []
    for c in cells_all:
        cy = c[1] + c[3] / 2.0
        if rows and abs(cy - (rows[-1][0][1] + rows[-1][0][3] / 2.0)) <= 0.6 * c[3]:
            rows[-1].append(c)
        else:
            rows.append([c])
    rows = [sorted(r, key=lambda c: c[0]) for r in rows if len(r) >= 2]
    if not rows or sum(len(r) for r in rows) < min_cells:
        return None
    return [[(float(x + x1), float(y + y1), float(x + w + x1), float(y + h + y1)) for (x, y, w, h) in r] for r in rows]


def uniform_grid(box: Tuple[float, float, float, float], rows: int, cols: int) -> List[List[Tuple[float, float, float, float]]]:
    """When the picture shows no cell borders but the person (or the step) says how many there are: an even split of the panel."""
    x1, y1, x2, y2 = box
    cw, ch = (x2 - x1) / cols, (y2 - y1) / rows
    return [[(x1 + c * cw, y1 + r * ch, x1 + (c + 1) * cw, y1 + (r + 1) * ch) for c in range(cols)] for r in range(rows)]


def cell_request(text: str) -> Tuple[Optional[int], Optional[int]]:
    """(row, column), 1-based, from a sentence like 'click step 5 on the second row'; None where the sentence does not say."""
    low = text.lower()
    row = col = None
    m = re.search(r"\brow\s*(\d+)\b", low)
    if m:
        row = int(m.group(1))
    m = re.search(r"\b(?:step|column|cell|square|beat|slot)\s*(\d+)\b", low)
    if m:
        col = int(m.group(1))
    for w, n in ORD.items():
        if re.search(r"\b" + w + r"\s+(?:row)\b", low):
            row = n
        if re.search(r"\b" + w + r"\s+(?:step|column|cell|square|beat|slot)\b", low):
            col = n
    return row, col


def pick_cell(grid: List[List[Tuple[float, float, float, float]]], row: Optional[int], col: Optional[int]) -> Optional[Tuple[float, float, float, float]]:
    r = (row - 1 if row and row > 0 else (len(grid) - 1 if row == -1 else 0))
    if r >= len(grid):
        return None
    cells = grid[r]
    if not col:
        return None
    c = col - 1 if col > 0 else len(cells) - 1
    return cells[c] if 0 <= c < len(cells) else None


# ------------------------------------------------------------------------------------------------------------------------------------------------ wording
DOMAIN_RX = re.compile(r"\s*\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|io|co|edu|gov|info|app|dev)\b", re.I)
REVEAL_RX = re.compile(r"^(show|expand|open|reveal|more)\b.*\b(toolbar|ribbon|tools|menu|panel|options|commands)\b|^(show|expand) ", re.I)
PHRASE_RX = re.compile(r"\b([A-Z][\w-]*(?:\s+[A-Za-z][\w-]*){0,3}?)\s+(?:tool|button|icon|tab|menu|option|command|field|box|dropdown|slider|checkbox|swatch)\b")


def clean_text(text: str) -> str:
    """A step's words without the source's attribution (a site's name tacked on after the sentence)."""
    return re.sub(r"\s{2,}", " ", DOMAIN_RX.sub("", text or "")).strip()


def group_name(raw: str) -> str:
    """A matched phrase without the verbs and articles in front of the name ('Use the Rectangle' -> 'Rectangle')."""
    prev = None
    while prev != raw:
        prev = raw
        raw = re.sub(r"^(?:the|a|an|your|this|that|click|use|select|choose|press|open|then|and|also)\s+", "", raw.strip(), flags=re.I)
    return raw.strip()


def phrases_in(text: str) -> List[str]:
    """Control names a sentence mentions: quoted names, and a capitalised name before 'tool / button / tab ...' ('the Rectangle tool' -> 'Rectangle')."""
    out = list(re.findall(r"[\"\u201c']([^\"\u201d']{2,32})[\"\u201d']", text))
    for m in PHRASE_RX.finditer(text):
        w = group_name(m.group(1))
        if w and w.lower() not in ("the", "a") and w not in out:
            out.append(w)
    return out


def starts_app(text: str, app: str) -> bool:
    """A step that only tells the person to start the program they are already in."""
    t = text.lower()
    return bool(app) and bool(re.match(r"\s*(?:open|launch|start|run)\b", t)) and any(w in t for w in tokens(app))


def reveal_control(controls: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """A control whose job is to show the rest of the interface (a collapsed toolbar / ribbon)."""
    for c in controls:
        if c.get("type") in ("Button", "MenuItem", "SplitButton", "TabItem") and REVEAL_RX.search(c.get("name", "")) and not UNSAFE.search(c.get("name", "")):
            return c
    return None


def first_sentence(text: str, cap: int = 130) -> str:
    s = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())[0]
    return s if len(s) <= cap else s[:cap].rsplit(" ", 1)[0] + "..."


def say_click(name: str, first_in_region: bool = False) -> str:
    return f"Click {name}." if name else "Click the highlighted control."


def say_keys(keys: str) -> str:
    return "Press " + keys.replace("+", " plus ") + "."


def last_key(keys: str) -> str:
    return keys.split("+")[-1].strip().lower() if keys else ""


# ------------------------------------------------------------------------------------------------------------------------------------------------ the plan
def plan_beats(steps: Sequence[Dict[str, Any]], controls: Sequence[Dict[str, Any]], image: Any = None, ground: Optional[Callable[[str], Optional[Tuple[float, float, float, float]]]] = None,
               max_beats: int = 24, app: str = "") -> List[Beat]:
    """Steps ({text, names, keys}) -> beats. Each step becomes at most: a region beat (the first time a row of controls is used), then ONE beat for the control / key. Steps that cannot be shown on this
    screen are still said (and waited for), never invented."""
    beats: List[Beat] = []
    shown_regions: set = set()
    revealed = False
    for st in steps:
        if len(beats) >= max_beats:
            break
        text = clean_text(str(st.get("text") or ""))
        if starts_app(text, app):
            continue
        names = [n for n in (st.get("names") or []) if n] or phrases_in(text)
        keys = (st.get("keys") or [""])[0] if st.get("keys") else ""
        ctl = None
        for n in names:
            ctl = locate(controls, n)
            if ctl:
                break
        if ctl is None:
            ctl = find_in_text(controls, text)
        if ctl is not None and UNSAFE.search(ctl.get("name", "")):
            ctl = None                                                    # a control that closes / deletes / sends is described, never pointed at as the next thing to click
        if ctl is not None:
            reg = region_of(controls, ctl)
            if reg is not None and tuple(round(v) for v in reg) not in shown_regions:
                shown_regions.add(tuple(round(v) for v in reg))
                beats.append(Beat(speech="Here is the row this is in.", primitive="region", box=reg, pill="here", wait="none", layer="uia"))
            nm = ctl["name"].strip()
            beats.append(Beat(speech=say_click(nm) + ((" Or press " + keys.replace("+", " plus ") + ".") if keys else ""), primitive="box_pointer", box=box_of(ctl), pill=nm[:28], wait="click",
                              keys=keys, target=nm, layer="uia", expect=f"{nm} was used"))
            continue
        rv = reveal_control(controls) if (names and not revealed) else None
        if rv is not None:                                                    # the thing is not on screen but the interface has a control that shows more of itself: that comes first
            revealed = True
            beats.append(Beat(speech=f"Some tools are hidden. Click {rv['name']} first.", primitive="box_pointer", box=box_of(rv), pill=rv["name"][:28], wait="click", target=rv["name"], layer="uia"))
        # a cell of a repeated-cell panel ('step 5', 'second row')
        row, col = cell_request(text)
        if (row or col) and image is not None and controls:
            panel = None
            for c in sorted(controls, key=lambda c: -(c["box"][2] * c["box"][3])):
                if c.get("type") in ("Pane", "Group", "Custom", "Document", "List", "Table", "Image") and c["box"][2] * c["box"][3] > 6000:
                    g = detect_grid(image, box_of(c))
                    if g:
                        panel = (c, g)
                        break
            if panel:
                cell = pick_cell(panel[1], row, col)
                if cell:
                    label = (f"row {row} " if row else "") + (f"step {col}" if col else "cell")
                    beats.append(Beat(speech=f"Click this one: {label}.", primitive="box_pointer", box=cell, pill=label, wait="click", target=label, layer="grid"))
                    continue
        if ground is not None and names:
            with __import__("contextlib").suppress(Exception):
                gb = ground(names[0])
                if gb:
                    beats.append(Beat(speech=say_click(names[0]), primitive="box_pointer", box=tuple(gb), pill=names[0][:28], wait="click", target=names[0], layer="model"))
                    continue
        quoted = names or list(re.findall(r"[\"“']([^\"”']{2,32})[\"”']", text))
        late = dict(st, names=quoted) if quoted else None
        if keys:
            beats.append(Beat(speech=say_keys(keys), primitive="none", pill=keys, wait=f"key:{last_key(keys)}", keys=keys, layer="none", expect=keys, late=late))
        elif text:
            beats.append(Beat(speech=first_sentence(text), primitive="none", wait="next", layer="none", late=late))
    return beats
