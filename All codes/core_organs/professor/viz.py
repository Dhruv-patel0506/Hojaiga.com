"""
professor.viz -- pictures of what the Professor saw: numbered, colour-coded boxes over the screenshot (the evidence behind a ScreenModel).

Colour = who found it.  green: accessibility tree   blue: printed text   orange: shape only   purple: vision model   teal: remembered icon
Red outline = a control nobody could name.  Region frames are drawn thin and labelled at their top-left corner.
"""

from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw

from .grounding import _font
from .schema import Box, ScreenModel

_COL = {"uia": (30, 170, 60), "ocr": (40, 110, 230), "cv": (240, 140, 20), "vlm": (150, 60, 200), "icon_memory": (0, 160, 160), "convention": (120, 120, 40)}
_REGION = (90, 90, 90)


def _pick(sources) -> tuple:
    for s in ("uia", "convention", "icon_memory", "vlm", "ocr", "cv"):
        if s in sources:
            return _COL[s]
    return (120, 120, 120)


def annotate(image: Image.Image, model: ScreenModel, show_regions: bool = True, show_ids: bool = True, only_named: bool = False) -> Image.Image:
    """`image` is the captured picture (origin = model.origin); boxes are shifted back into picture space."""
    out = image.convert("RGB").copy()
    d = ImageDraw.Draw(out, "RGBA")
    ox, oy = model.origin
    small = _font(11)
    mid = _font(13)
    if show_regions:
        for r in model.regions:
            b = r.bbox.shift(-ox, -oy)
            d.rectangle(b.ituple(), outline=_REGION + (200,), width=1)
            tag = f"{r.kind}: {r.label}" if r.label and r.label != r.kind else r.kind
            d.text((b.x1 + 3, max(0, b.y1 - 13)), tag[:40], fill=(70, 70, 70, 255), font=small)
    for e in model.elements:
        if only_named and not e.label:
            continue
        b = e.bbox.shift(-ox, -oy)
        col = (220, 20, 20) if (not e.label and e.role != "text") else _pick(e.sources)
        d.rectangle(b.ituple(), outline=col + (255,), width=2 if e.label else 1)
        if show_ids:
            t = str(e.id)
            tw = d.textlength(t, font=small)
            d.rectangle((b.x1, b.y1 - 12, b.x1 + tw + 4, b.y1), fill=col + (230,))
            d.text((b.x1 + 2, b.y1 - 12), t, fill=(255, 255, 255, 255), font=small)
    return out


def legend(width: int = 520) -> Image.Image:
    img = Image.new("RGB", (width, 26), (250, 250, 250))
    d = ImageDraw.Draw(img)
    f = _font(12)
    x = 6
    for name, key in (("tree", "uia"), ("text", "ocr"), ("shape", "cv"), ("model", "vlm"), ("memory", "icon_memory")):
        d.rectangle((x, 7, x + 12, 19), outline=_COL[key], width=2)
        d.text((x + 16, 6), name, fill=(40, 40, 40), font=f)
        x += 86
    d.rectangle((x, 7, x + 12, 19), outline=(220, 20, 20), width=2)
    d.text((x + 16, 6), "unnamed", fill=(40, 40, 40), font=f)
    return img


_DEPTH_COL = [(200, 0, 0), (230, 120, 0), (200, 180, 0), (60, 160, 40), (0, 150, 150), (30, 100, 220), (110, 60, 200), (190, 50, 160)]


def tree_overlay(image: Image.Image, origin, nodes, min_size: int = 3) -> Image.Image:
    """The accessibility tree DRAWN: every node of every depth as a thin box, coloured by depth (red = the frame, then orange, yellow, green, teal, blue, violet, magenta ...), with a depth histogram
    underneath. A flat tree is a window the application never described; a deep one is what a guide's 'Home > Font > Bold' can be found in."""
    out = image.convert("RGB").copy()
    d = ImageDraw.Draw(out, "RGBA")
    ox, oy = origin
    hist = {}
    for n in nodes:
        x1, y1, x2, y2 = n.rect
        if x2 - x1 < min_size or y2 - y1 < min_size or getattr(n, "offscreen", False):
            continue
        hist[n.depth] = hist.get(n.depth, 0) + 1
        col = _DEPTH_COL[n.depth % len(_DEPTH_COL)]
        d.rectangle((x1 - ox, y1 - oy, x2 - ox, y2 - oy), outline=col + (230,), width=1)
    bar = Image.new("RGB", (out.width, 34), (250, 250, 250))
    bd = ImageDraw.Draw(bar)
    f = _font(12)
    x = 6
    total = sum(hist.values())
    bd.text((x, 9), f"accessibility tree: {total} visible nodes, {len(hist)} levels deep", fill=(30, 30, 30), font=f)
    x = 330
    for dep in sorted(hist):
        col = _DEPTH_COL[dep % len(_DEPTH_COL)]
        bd.rectangle((x, 10, x + 12, 22), outline=col, width=2)
        bd.text((x + 16, 9), f"{dep}:{hist[dep]}", fill=(40, 40, 40), font=f)
        x += 62
        if x > out.width - 60:
            break
    res = Image.new("RGB", (out.width, out.height + bar.height), (255, 255, 255))
    res.paste(out, (0, 0))
    res.paste(bar, (0, out.height))
    return res


def with_legend(img: Image.Image) -> Image.Image:
    lg = legend(min(img.width, 520))
    res = Image.new("RGB", (img.width, img.height + lg.height), (255, 255, 255))
    res.paste(img, (0, 0))
    res.paste(lg, (0, img.height))
    return res


def render_popup(nodes, size, title: str = "", origin=(0, 0)) -> Image.Image:
    """A pop-up that cannot be photographed (a WinUI flyout of a window parked off-screen paints nothing for PrintWindow or the compositor capture) DRAWN from what its accessibility tree reports:
    every named control at its reported rectangle with its name, role colour-coded like the scans. Coordinates that are relative to the pop-up (x < size) are used as they are."""
    w, h = max(220, int(size[0])), max(80, int(size[1]))
    img = Image.new("RGB", (w, h + 22), (34, 34, 38))
    d = ImageDraw.Draw(img, "RGBA")
    f, s = _font(13), _font(10)
    d.text((6, 3), (title or "pop-up") + f"  -  {sum(1 for n in nodes if n.name)} named controls (read from the accessibility tree)", fill=(190, 190, 200), font=s)
    ox, oy = origin
    for n in nodes:
        if not n.name or n.rect[2] <= n.rect[0]:
            continue
        x1, y1, x2, y2 = n.rect
        if x1 < -2000 or x1 > 4000:                      # screen coordinates of a parked window: shift to the pop-up's own corner
            x1, x2, y1, y2 = x1 - ox, x2 - ox, y1 - oy, y2 - oy
        y1, y2 = y1 + 22, y2 + 22
        if n.role in ("text", "pane", "window", "group", "image", "custom", "menu", "document") or not (n.pats or n.role in ("button", "menuitem", "listitem", "checkbox", "radiobutton", "tabitem", "edit", "combobox")):
            continue                                    # a label inside a control repeats the control's own name: draw the control
        col = (60, 190, 90) if n.pats else (120, 140, 220)
        d.rectangle((x1, y1, x2, y2), outline=col + (230,), width=1)
        d.text((x1 + 6, y1 + max(1, (y2 - y1 - 14) // 2)), n.name[:46], fill=(235, 235, 240), font=f)
        if n.accel:
            tw = d.textlength(n.accel, font=s)
            d.text((max(x1 + 8, x2 - tw - 8), y1 + max(1, (y2 - y1 - 11) // 2)), n.accel, fill=(150, 200, 255), font=s)
    return img
