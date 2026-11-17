"""
professor.labeler -- NAMING the controls that candidates.py found, with the vision model, cheaply.

The trick that makes a 7B local model usable for "name every button": a SET-OF-MARK CONTACT SHEET. Up to 20 candidate crops (each upscaled, the control
marked by a thin magenta frame, a big number in the corner) are tiled into ONE small picture (~250 image tokens) and the model answers with
`number: name` lines under a grammar that forbids anything else (~6 tokens per control, no JSON boilerplate, no coordinates to hallucinate).
Order of trust for a name:  accessibility tree / printed caption  >  icon memory (seen before)  >  this model  >  nothing (honest '').
Optional second pass with a shuffled sheet: two agreeing names -> high confidence, disagreeing -> kept but flagged `ambiguous`.
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from . import config as CFG
from .grounding import _font
from .icon_memory import IconMemory, fingerprint
from .schema import Box, fold
from .vlm import VisionClient

GRAMMAR = r'''root ::= line+
line ::= num ": " name "\n"
num ::= [0-9]+
name ::= [^\n:]{1,32}
'''

SHEET_PROMPT = (
    "This picture is a contact sheet of {n} numbered cells. Each cell is a close-up of one part of a software window; "
    "the control to identify is the one inside the thin MAGENTA rectangle. For every number write the control's name the way the application would "
    "label it (examples: Save, Undo, Bold, Zoom In, Search, Settings, Close, Insert Table). Use 1-3 words. If the control shows text, copy the text. "
    "If it is not a control or you cannot tell, write ?.\nAnswer with exactly {n} lines in the form `number: name`."
)

WHERE_LINE = "\nWhere each control sits in its window: {where}. Use that: a mark at the far right of a title bar is a window button, a mark in a status bar near a slider changes the view."


@dataclass
class Label:
    text: str = ""
    conf: float = 0.0
    via: str = ""                               # memory | vlm | vlm2
    flags: List[str] = field(default_factory=list)


PANEL_PROMPT = (
    "This picture is a contact sheet of {n} numbered cells. Each cell is a screenshot of one AREA (an editor, panel or pane) of a software window. "
    "For every number write the area's name the way the application would label it (examples: Outliner, Properties, Timeline, 3D Viewport, File Explorer, Terminal, "
    "Slide Thumbnails, Notes, Layers). Use 1-3 words, or ? if you cannot tell.\nAnswer with exactly {n} lines in the form `number: name`."
)


def _cell(img: Image.Image, box: Box, number: int, cell: int, font, pad_ratio: float = 0.6, mark: bool = True) -> Image.Image:
    pad = int(max(8, pad_ratio * max(box.w, box.h))) if pad_ratio > 0.05 else 0
    ctx = Box(box.x1 - pad, box.y1 - pad, box.x2 + pad, box.y2 + pad).clip(img.width, img.height)
    crop = img.crop(ctx.ituple()).convert("RGB")
    d = ImageDraw.Draw(crop)
    local = Box(box.x1 - ctx.x1, box.y1 - ctx.y1, box.x2 - ctx.x1, box.y2 - ctx.y1).expand(1.5)
    if mark:
        d.rectangle(local.ituple(), outline=(255, 0, 255), width=1)
    s = min((cell - 4) / max(1, crop.width), (cell - 4) / max(1, crop.height))
    s = min(s, 6.0)
    crop = crop.resize((max(1, int(crop.width * s)), max(1, int(crop.height * s))), Image.LANCZOS)
    out = Image.new("RGB", (cell, cell), (128, 128, 128))
    out.paste(crop, ((cell - crop.width) // 2, (cell - crop.height) // 2))
    d = ImageDraw.Draw(out)
    tag = str(number)
    tw = d.textlength(tag, font=font)
    d.rectangle((0, 0, tw + 8, 22), fill=(190, 0, 0))
    d.text((4, 1), tag, fill=(255, 255, 255), font=font)
    d.rectangle((0, 0, cell - 1, cell - 1), outline=(60, 60, 60))
    return out


def make_sheet(img: Image.Image, boxes: Sequence[Box], cell: int = 112, cols: int = 5, pad_ratio: float = 0.6, mark: bool = True) -> Image.Image:
    font = _font(16)
    n = len(boxes)
    rows = (n + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), (96, 96, 96))
    for i, b in enumerate(boxes):
        c = _cell(img, b, i + 1, cell, font, pad_ratio, mark)
        sheet.paste(c, ((i % cols) * cell, (i // cols) * cell))
    return sheet


_LINE = re.compile(r"^\s*(\d+)\s*[:.)-]\s*(.+?)\s*$")


def parse_lines(text: str, n: int) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for ln in (text or "").splitlines():
        m = _LINE.match(ln)
        if not m:
            continue
        k = int(m.group(1))
        name = m.group(2).strip().strip("`'\" ")
        if 1 <= k <= n and name:
            out[k] = "" if name in ("?", "??", "unknown", "Unknown", "none", "None") else name[:32]
    return out


def _same(a: str, b: str) -> bool:
    fa, fb = fold(a), fold(b)
    return bool(fa and fb and (fa == fb or fa in fb or fb in fa))


class Labeler:
    def __init__(self, vlm: VisionClient, memory: Optional[IconMemory] = None):
        self.vlm = vlm
        self.memory = memory
        self.calls = 0
        self.sheets = 0
        self.cancel: Optional[Callable[[], bool]] = None          # background scans yield to a waiting question by returning True here

    def from_memory(self, img: Image.Image, boxes: Sequence[Box]) -> List[Optional[Label]]:
        out: List[Optional[Label]] = []
        for b in boxes:
            if self.memory is None or not len(self.memory):
                out.append(None)
                continue
            fp = fingerprint(img.crop(b.clip(img.width, img.height).ituple()))
            hit = self.memory.lookup(fp)
            if hit and float(hit["conf"]) >= 0.62:
                out.append(Label(str(hit["label"]), float(hit["conf"]), "memory"))
            else:
                out.append(None)
        return out

    def label_boxes(self, img: Image.Image, boxes: Sequence[Box], budget_s: float, consistency: int = 1, per_sheet: Optional[int] = None,
                    order: Optional[Sequence[int]] = None, hints: Optional[Sequence[str]] = None, areas: bool = False) -> Tuple[List[Optional[Label]], Dict[str, object]]:
        """Names for `boxes` (picture pixels), same order. None = could not be named (no model, out of time, or the model said '?')."""
        t0 = time.time()
        n_all = len(boxes)
        result: List[Optional[Label]] = [None] * n_all
        meta: Dict[str, object] = {"sheets": 0, "asked": 0, "named": 0, "skipped": "", "seconds": 0.0}
        if not self.vlm.available():
            meta["skipped"] = "vlm:unreachable"
            return result, meta
        per = per_sheet or CFG.BUDGETS.sheet_cells
        idxs = list(order) if order is not None else list(range(n_all))
        passes = 2 if consistency >= 2 else 1
        first: Dict[int, str] = {}
        for p in range(passes):
            seq = idxs[:]
            if p == 1:
                random.Random(11).shuffle(seq)
            for k in range(0, len(seq), per):
                if self.cancel is not None and self.cancel():
                    meta["skipped"] = "vlm:yielded-to-question"
                    break
                if time.time() - t0 > budget_s:
                    meta["skipped"] = "vlm:budget"
                    break
                chunk = seq[k:k + per]
                if areas:                                      # whole editor areas: big cells, no frame, the question is about the AREA
                    sheet = make_sheet(img, [boxes[i] for i in chunk], 240, 3, 0.0, False)
                    prompt = PANEL_PROMPT.format(n=len(chunk))
                else:
                    sheet = make_sheet(img, [boxes[i] for i in chunk], CFG.BUDGETS.cell_px)
                    prompt = SHEET_PROMPT.format(n=len(chunk))
                if hints is not None and not areas:
                    where = "; ".join(f"{pos} = {hints[i]}" for pos, i in enumerate(chunk, 1) if hints[i])
                    if where:
                        prompt += WHERE_LINE.format(where=where)
                r = self.vlm.chat(prompt, [sheet], max_tokens=len(chunk) * 10 + 12, grammar=GRAMMAR,
                                  timeout=min(CFG.BUDGETS.vlm_label_sheet_s, max(20.0, budget_s - (time.time() - t0) + 20)), image_budget=900, min_side=0)
                self.sheets += 1
                self.calls += 1
                meta["sheets"] = int(meta["sheets"]) + 1                    # type: ignore[arg-type]
                if not r.ok:
                    meta["skipped"] = f"vlm:{r.error[:60]}"
                    break
                names = parse_lines(r.text, len(chunk))
                for pos, i in enumerate(chunk, 1):
                    nm = names.get(pos, "")
                    meta["asked"] = int(meta["asked"]) + 1                  # type: ignore[arg-type]
                    if not nm:
                        continue
                    if p == 0:
                        first[i] = nm
                        result[i] = Label(nm, 0.6, "vlm")
                    else:
                        prev = first.get(i)
                        if prev and _same(prev, nm):
                            result[i] = Label(prev if len(prev) <= len(nm) else nm, 0.86, "vlm2")
                        elif prev:
                            result[i] = Label(prev, 0.4, "vlm", ["ambiguous"])
                        else:
                            result[i] = Label(nm, 0.5, "vlm2")
        meta["named"] = sum(1 for x in result if x is not None)
        meta["seconds"] = round(time.time() - t0, 2)
        return result, meta
