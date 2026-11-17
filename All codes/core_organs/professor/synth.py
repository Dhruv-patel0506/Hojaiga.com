"""
professor.synth -- synthetic application screenshots WITH EXACT GROUND TRUTH, for tests and documentation.

Why: the scanner's claim is "every control found, with its section". That has to be MEASURED against something that knows the answer. A synthetic
window (title bar + quick-access icons, menu bar, tab strip, ribbon with captioned groups, big icon+caption buttons, drop-downs, a sidebar of icon buttons, a
document canvas, a status bar) and a dialog (fields, check boxes, radios, buttons) are drawn with PIL; every control's box and name is recorded as it is drawn.
Light and dark themes, any display scale. Nothing is shown on the real screen and no real application is touched.
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from .schema import Box

Truth = Dict[str, Any]

# What else a person (or a model) would reasonably call each synthetic glyph. Strict scoring uses the one name; lenient scoring accepts these too.
ALIASES: Dict[str, Tuple[str, ...]] = {
    "Search": ("find", "magnifier", "magnify", "zoom", "search"), "Settings": ("gear", "options", "preferences", "cog", "setting"),
    "Open": ("folder", "open file", "new folder", "browse"), "New Document": ("document", "page", "file", "new file"), "Save": ("floppy", "save as", "disk"),
    "Undo": ("back", "undo typing"), "Redo": ("forward", "redo typing"), "Cut": ("scissors", "scissor"), "Copy": ("duplicate", "copy"), "Paste": ("clipboard",),
    "Picture": ("image", "photo", "pictures", "insert picture"), "Table": ("grid", "insert table"), "Chart": ("graph", "bar chart", "insert chart"),
    "Shapes": ("shape", "insert shapes"), "Print": ("printer",), "Home": ("house", "start"), "Account": ("user", "profile", "person", "people", "contact"),
    "Mail": ("email", "envelope", "message", "inbox"), "Lock": ("padlock", "secure", "security"), "Favorite": ("star", "favorites", "bookmark"),
    "Highlight": ("star", "favorites", "favorite", "highlighter", "font color"), "Delete": ("trash", "bin", "remove"), "Close": ("x", "exit", "cross"),
    "Minimize": ("minus", "minimise", "hide"), "Maximize": ("restore", "square", "maximise", "square frame", "window"), "Zoom Out": ("minus", "zoom minus", "decrease zoom", "smaller"),
    "Zoom In": ("add", "plus", "zoom plus", "increase zoom", "larger"), "Add": ("plus", "new"), "Bold": ("b",), "Italic": ("i",), "Underline": ("u",), "Strikethrough": ("s", "strike"),
}

THEMES = {
    "light": {"bg": (243, 243, 243), "bar": (230, 230, 232), "ribbon": (250, 250, 250), "canvas": (255, 255, 255), "fg": (32, 32, 32), "muted": (110, 110, 110),
              "line": (205, 205, 205), "accent": (30, 100, 200), "field": (255, 255, 255)},
    "dark": {"bg": (30, 30, 32), "bar": (40, 40, 44), "ribbon": (46, 46, 50), "canvas": (62, 62, 66), "fg": (235, 235, 235), "muted": (160, 160, 165),
             "line": (78, 78, 84), "accent": (96, 160, 255), "field": (30, 30, 34)},
}


def _font(px: int, bold: bool = False):
    for n in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(n, px)
        except Exception:
            continue
    return ImageFont.load_default()


# ------------------------------------------------------------------------------------------------------------ glyphs
def _g_plus(d, b, c):
    cx, cy, r = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, (b[2] - b[0]) * 0.32
    d.line((cx - r, cy, cx + r, cy), fill=c, width=2)
    d.line((cx, cy - r, cx, cy + r), fill=c, width=2)


def _g_search(d, b, c):
    w = b[2] - b[0]
    d.ellipse((b[0] + w * .15, b[1] + w * .12, b[0] + w * .62, b[1] + w * .59), outline=c, width=2)
    d.line((b[0] + w * .56, b[1] + w * .55, b[0] + w * .88, b[1] + w * .88), fill=c, width=3)


def _g_gear(d, b, c):
    cx, cy, r = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, (b[2] - b[0]) * 0.28
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=c, width=2)
    for k in range(8):
        a = k * math.pi / 4
        d.line((cx + math.cos(a) * r, cy + math.sin(a) * r, cx + math.cos(a) * (r + 5), cy + math.sin(a) * (r + 5)), fill=c, width=3)
    d.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=c)


def _g_folder(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.polygon([(b[0] + w * .1, b[1] + h * .3), (b[0] + w * .4, b[1] + h * .3), (b[0] + w * .48, b[1] + h * .42), (b[0] + w * .9, b[1] + h * .42),
               (b[0] + w * .9, b[1] + h * .82), (b[0] + w * .1, b[1] + h * .82)], outline=c, width=2)


def _g_doc(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.polygon([(b[0] + w * .22, b[1] + h * .1), (b[0] + w * .62, b[1] + h * .1), (b[0] + w * .8, b[1] + h * .28), (b[0] + w * .8, b[1] + h * .9),
               (b[0] + w * .22, b[1] + h * .9)], outline=c, width=2)
    for k in range(3):
        y = b[1] + h * (.46 + .13 * k)
        d.line((b[0] + w * .32, y, b[0] + w * .7, y), fill=c, width=1)


def _g_save(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.rectangle((b[0] + w * .15, b[1] + h * .15, b[0] + w * .85, b[1] + h * .85), outline=c, width=2)
    d.rectangle((b[0] + w * .3, b[1] + h * .15, b[0] + w * .7, b[1] + h * .4), outline=c, width=1)
    d.rectangle((b[0] + w * .3, b[1] + h * .55, b[0] + w * .7, b[1] + h * .85), fill=c)


def _g_undo(d, b, c, flip=False):
    w, h = b[2] - b[0], b[3] - b[1]
    x0, x1 = (b[0] + w * .2, b[0] + w * .8) if not flip else (b[0] + w * .8, b[0] + w * .2)
    d.arc((b[0] + w * .2, b[1] + h * .3, b[0] + w * .85, b[1] + h * .9), 200 if not flip else 340, 360 if not flip else 520 - 360 + 160, fill=c, width=2)
    d.line((x0, b[1] + h * .4, x0, b[1] + h * .22), fill=c, width=2)
    d.polygon([(x0, b[1] + h * .22), (x0 + (w * .22 if not flip else -w * .22), b[1] + h * .42), (x0 - (w * .05 if not flip else -w * .05), b[1] + h * .45)], fill=c)


def _g_redo(d, b, c):
    _g_undo(d, b, c, True)


def _g_cut(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.ellipse((b[0] + w * .15, b[1] + h * .6, b[0] + w * .4, b[1] + h * .85), outline=c, width=2)
    d.ellipse((b[0] + w * .6, b[1] + h * .6, b[0] + w * .85, b[1] + h * .85), outline=c, width=2)
    d.line((b[0] + w * .27, b[1] + h * .6, b[0] + w * .65, b[1] + h * .12), fill=c, width=2)
    d.line((b[0] + w * .73, b[1] + h * .6, b[0] + w * .35, b[1] + h * .12), fill=c, width=2)


def _g_copy(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.rectangle((b[0] + w * .15, b[1] + h * .25, b[0] + w * .6, b[1] + h * .85), outline=c, width=2)
    d.rectangle((b[0] + w * .4, b[1] + h * .1, b[0] + w * .85, b[1] + h * .7), outline=c, width=2)


def _g_paste(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.rectangle((b[0] + w * .2, b[1] + h * .2, b[0] + w * .8, b[1] + h * .9), outline=c, width=2)
    d.rectangle((b[0] + w * .36, b[1] + h * .08, b[0] + w * .64, b[1] + h * .3), fill=c)


def _g_picture(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.rectangle((b[0] + w * .1, b[1] + h * .18, b[0] + w * .9, b[1] + h * .82), outline=c, width=2)
    d.polygon([(b[0] + w * .15, b[1] + h * .78), (b[0] + w * .4, b[1] + h * .45), (b[0] + w * .6, b[1] + h * .66), (b[0] + w * .72, b[1] + h * .55), (b[0] + w * .88, b[1] + h * .78)], fill=c)
    d.ellipse((b[0] + w * .66, b[1] + h * .26, b[0] + w * .8, b[1] + h * .4), fill=c)


def _g_table(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    x0, y0, x1, y1 = b[0] + w * .12, b[1] + h * .2, b[0] + w * .88, b[1] + h * .8
    d.rectangle((x0, y0, x1, y1), outline=c, width=2)
    for k in (1, 2):
        d.line((x0 + (x1 - x0) * k / 3, y0, x0 + (x1 - x0) * k / 3, y1), fill=c, width=1)
        d.line((x0, y0 + (y1 - y0) * k / 3, x1, y0 + (y1 - y0) * k / 3), fill=c, width=1)


def _g_chart(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    for k, hh in enumerate((.35, .6, .85)):
        d.rectangle((b[0] + w * (.18 + k * .25), b[1] + h * (.9 - hh), b[0] + w * (.34 + k * .25), b[1] + h * .9), fill=c)


def _g_shapes(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.ellipse((b[0] + w * .1, b[1] + h * .1, b[0] + w * .5, b[1] + h * .5), outline=c, width=2)
    d.rectangle((b[0] + w * .5, b[1] + h * .5, b[0] + w * .9, b[1] + h * .9), outline=c, width=2)
    d.polygon([(b[0] + w * .1, b[1] + h * .9), (b[0] + w * .3, b[1] + h * .55), (b[0] + w * .5, b[1] + h * .9)], outline=c, width=2)


def _g_print(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.rectangle((b[0] + w * .15, b[1] + h * .35, b[0] + w * .85, b[1] + h * .75), outline=c, width=2)
    d.rectangle((b[0] + w * .3, b[1] + h * .12, b[0] + w * .7, b[1] + h * .35), outline=c, width=2)
    d.rectangle((b[0] + w * .3, b[1] + h * .6, b[0] + w * .7, b[1] + h * .9), outline=c, width=2)


def _g_home(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.polygon([(b[0] + w * .5, b[1] + h * .12), (b[0] + w * .9, b[1] + h * .5), (b[0] + w * .78, b[1] + h * .5), (b[0] + w * .78, b[1] + h * .85),
               (b[0] + w * .22, b[1] + h * .85), (b[0] + w * .22, b[1] + h * .5), (b[0] + w * .1, b[1] + h * .5)], outline=c, width=2)


def _g_user(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.ellipse((b[0] + w * .33, b[1] + h * .12, b[0] + w * .67, b[1] + h * .46), outline=c, width=2)
    d.arc((b[0] + w * .15, b[1] + h * .5, b[0] + w * .85, b[1] + h * 1.2), 180, 360, fill=c, width=2)


def _g_mail(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.rectangle((b[0] + w * .1, b[1] + h * .25, b[0] + w * .9, b[1] + h * .75), outline=c, width=2)
    d.line((b[0] + w * .1, b[1] + h * .25, b[0] + w * .5, b[1] + h * .55, b[0] + w * .9, b[1] + h * .25), fill=c, width=2)


def _g_lock(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.rectangle((b[0] + w * .22, b[1] + h * .45, b[0] + w * .78, b[1] + h * .88), outline=c, width=2)
    d.arc((b[0] + w * .3, b[1] + h * .1, b[0] + w * .7, b[1] + h * .7), 180, 360, fill=c, width=2)


def _g_star(d, b, c):
    cx, cy, r = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, (b[2] - b[0]) * .42
    pts = []
    for k in range(10):
        rr = r if k % 2 == 0 else r * .45
        a = -math.pi / 2 + k * math.pi / 5
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    d.polygon(pts, outline=c, width=2)


def _g_trash(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.rectangle((b[0] + w * .25, b[1] + h * .3, b[0] + w * .75, b[1] + h * .88), outline=c, width=2)
    d.line((b[0] + w * .15, b[1] + h * .26, b[0] + w * .85, b[1] + h * .26), fill=c, width=2)
    d.rectangle((b[0] + w * .4, b[1] + h * .12, b[0] + w * .6, b[1] + h * .26), outline=c, width=2)


def _g_close(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.line((b[0] + w * .3, b[1] + h * .3, b[0] + w * .7, b[1] + h * .7), fill=c, width=2)
    d.line((b[0] + w * .7, b[1] + h * .3, b[0] + w * .3, b[1] + h * .7), fill=c, width=2)


def _g_min(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.line((b[0] + w * .3, b[1] + h * .55, b[0] + w * .7, b[1] + h * .55), fill=c, width=2)


def _g_max(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.rectangle((b[0] + w * .3, b[1] + h * .3, b[0] + w * .7, b[1] + h * .7), outline=c, width=2)


def _g_minus(d, b, c):
    w, h = b[2] - b[0], b[3] - b[1]
    d.line((b[0] + w * .25, b[1] + h * .5, b[0] + w * .75, b[1] + h * .5), fill=c, width=2)


GLYPHS: Dict[str, Callable] = {
    "Search": _g_search, "Settings": _g_gear, "Open": _g_folder, "New Document": _g_doc, "Save": _g_save, "Undo": _g_undo, "Redo": _g_redo, "Cut": _g_cut,
    "Copy": _g_copy, "Paste": _g_paste, "Picture": _g_picture, "Table": _g_table, "Chart": _g_chart, "Shapes": _g_shapes, "Print": _g_print, "Home": _g_home,
    "Account": _g_user, "Mail": _g_mail, "Lock": _g_lock, "Favorite": _g_star, "Delete": _g_trash, "Close": _g_close, "Minimize": _g_min, "Maximize": _g_max,
    "Zoom Out": _g_minus, "Zoom In": _g_plus, "Add": _g_plus,
}


# ------------------------------------------------------------------------------------------------------------ scenes
class _Scene:
    def __init__(self, size: Tuple[int, int], theme: str, scale: float):
        self.p = THEMES[theme]
        self.theme = theme
        self.s = scale
        self.img = Image.new("RGB", size, self.p["bg"])
        self.d = ImageDraw.Draw(self.img)
        self.truth: List[Truth] = []
        self.regions: List[Truth] = []

    def px(self, v: float) -> int:
        return int(round(v * self.s))

    def f(self, px: int, bold: bool = False):
        return _font(self.px(px), bold)

    def rec(self, label: str, box: Tuple[float, float, float, float], kind: str, region: str, **kw: Any) -> None:
        self.truth.append({"label": label, "box": [int(box[0]), int(box[1]), int(box[2]), int(box[3])], "kind": kind, "region": region, "aliases": list(ALIASES.get(label, ())), **kw})

    def text(self, xy: Tuple[float, float], s: str, size: int = 13, color=None, bold: bool = False) -> Tuple[int, int, int, int]:
        f = self.f(size, bold)
        self.d.text(xy, s, font=f, fill=color or self.p["fg"])
        bb = self.d.textbbox(xy, s, font=f)
        return bb

    def icon(self, name: str, x: float, y: float, size: int, region: str, caret: bool = False, record: bool = True, pad: int = 3) -> Tuple[int, int, int, int]:
        sz = self.px(size)
        box = (x, y, x + sz, y + sz)
        GLYPHS[name](self.d, box, self.p["fg"])
        full = box
        if caret:
            cx, cy = x + sz + self.px(3), y + sz * 0.45
            self.d.polygon([(cx, cy), (cx + self.px(7), cy), (cx + self.px(3.5), cy + self.px(4))], fill=self.p["fg"])
            full = (x, y, cx + self.px(7), y + sz)
        if record:
            self.rec(name, (full[0] - pad, full[1] - pad, full[2] + pad, full[3] + pad), "icon", region, has_dropdown=caret)
        return full


def render_app(theme: str = "light", scale: float = 1.0, size: Tuple[int, int] = (1600, 900), selected_tab: str = "Home") -> Tuple[Image.Image, List[Truth], List[Truth]]:
    """(image, controls, regions). Controls: {label, box, kind(icon|text|icon_label|field), region, has_dropdown}. Regions: {kind, label, box}."""
    sc = _Scene((int(size[0] * scale), int(size[1] * scale)), theme, scale)
    d, p, S = sc.d, sc.p, sc.px
    W, H = sc.img.size
    # ---- title bar
    d.rectangle((0, 0, W, S(32)), fill=p["bar"])
    sc.regions.append({"kind": "titlebar", "label": "title bar", "box": [0, 0, W, S(32)]})
    x = S(10)
    for nm in ("Save", "Undo", "Redo"):
        sc.icon(nm, x, S(5), 22, "titlebar", pad=4)
        x += S(34)
    sc.text((S(130), S(7)), "Quarterly Report - DocWriter", 13)
    for i, nm in enumerate(("Minimize", "Maximize", "Close")):
        cx = W - S(46) * (3 - i)
        GLYPHS[nm](d, (cx + S(12), S(6), cx + S(34), S(28)), p["fg"])
        sc.rec(nm, (cx, 0, cx + S(46), S(32)), "icon", "titlebar")
    # ---- menu bar
    d.rectangle((0, S(32), W, S(60)), fill=p["ribbon"])
    sc.regions.append({"kind": "menubar", "label": "menu bar", "box": [0, S(32), W, S(60)]})
    x = S(12)
    for w in ("File", "Edit", "View", "Insert", "Format", "Tools", "Window", "Help"):
        bb = sc.text((x, S(37)), w, 13)
        sc.rec(w, (bb[0] - S(5), S(34), bb[2] + S(5), S(58)), "text", "menubar")
        x = bb[2] + S(22)
    # ---- tab strip
    d.rectangle((0, S(60), W, S(88)), fill=p["bar"])
    sc.regions.append({"kind": "tab_strip", "label": "ribbon tabs", "box": [0, S(60), W, S(88)]})
    x = S(14)
    for t in ("Home", "Insert", "Layout", "Review", "View"):
        bb = sc.text((x, S(65)), t, 13, p["accent"] if t == selected_tab else p["fg"], bold=(t == selected_tab))
        if t == selected_tab:
            d.line((bb[0], S(86), bb[2], S(86)), fill=p["accent"], width=S(3))
        sc.rec(t, (bb[0] - S(8), S(62), bb[2] + S(8), S(88)), "text", "tab_strip")
        x = bb[2] + S(30)
    # ---- ribbon
    ry0, ry1 = S(88), S(198)
    d.rectangle((0, ry0, W, ry1), fill=p["ribbon"])
    d.line((0, ry1, W, ry1), fill=p["line"], width=1)
    sc.regions.append({"kind": "ribbon", "label": "ribbon", "box": [0, ry0, W, ry1]})
    groups = [("Clipboard", S(8), S(236)), ("Font", S(244), S(530)), ("Insert", S(538), S(900))]
    for gname, gx0, gx1 in groups:
        d.line((gx1, ry0 + S(8), gx1, ry1 - S(8)), fill=p["line"], width=1)
        bb = sc.text(((gx0 + gx1) / 2 - S(len(gname) * 3.2), ry1 - S(22)), gname, 11, p["muted"])
        sc.regions.append({"kind": "toolbar", "label": f"ribbon > {gname}", "box": [gx0, ry0, gx1, ry1]})
    # group 1: big Paste (icon + caption), Cut / Copy small icon+caption rows
    ix, iy = S(22), S(96)
    sc.icon("Paste", ix, iy, 34, "ribbon", record=False)
    bb = sc.text((ix - S(2), iy + S(42)), "Paste", 12)
    sc.rec("Paste", (min(ix, bb[0]) - S(4), iy - S(4), max(ix + S(34), bb[2]) + S(4), bb[3] + S(3)), "icon_label", "ribbon:Clipboard")
    sx, sy = S(100), S(98)
    for nm in ("Cut", "Copy"):
        sc.icon(nm, sx, sy, 20, "ribbon", record=False)
        bb = sc.text((sx + S(28), sy + S(2)), nm, 12)
        sc.rec(nm, (sx - S(4), sy - S(3), bb[2] + S(5), sy + S(24)), "icon_label", "ribbon:Clipboard")
        sy += S(30)
    # group 2: font name field, size field, B I U S
    for lab, fx, fw in (("Calibri", S(256), S(130)), ("11", S(394), S(44))):
        d.rectangle((fx, S(98), fx + fw, S(122)), fill=p["field"], outline=p["line"])
        sc.text((fx + S(6), S(102)), lab, 12)
        d.polygon([(fx + fw - S(14), S(108)), (fx + fw - S(6), S(108)), (fx + fw - S(10), S(113))], fill=p["fg"])
        sc.rec("Font name" if lab == "Calibri" else "Font size", (fx, S(98), fx + fw, S(122)), "field", "ribbon:Font", has_dropdown=True)
    bx = S(256)
    for lab in ("B", "I", "U", "S"):
        d.rectangle((bx, S(134), bx + S(30), S(162)), outline=p["line"])
        f = sc.f(15, bold=(lab == "B"))
        w = d.textlength(lab, font=f)
        d.text((bx + S(15) - w / 2, S(138)), lab, font=f, fill=p["fg"])
        sc.rec({"B": "Bold", "I": "Italic", "U": "Underline", "S": "Strikethrough"}[lab], (bx, S(134), bx + S(30), S(162)), "icon", "ribbon:Font")
        bx += S(38)
    sc.icon("Favorite", bx + S(8), S(138), 22, "ribbon", caret=True, record=False)
    sc.rec("Highlight", (bx + S(2), S(134), bx + S(52), S(162)), "icon", "ribbon:Font", has_dropdown=True)
    # group 3: Table, Picture, Shapes (caret), Chart -- big icon + caption
    bx = S(552)
    for nm in ("Table", "Picture", "Shapes", "Chart"):
        sc.icon(nm, bx, S(96), 34, "ribbon", record=False)
        bb = sc.text((bx - S(4), S(138)), nm, 12)
        has_dd = nm in ("Shapes", "Table")
        if has_dd:
            cx = (bb[0] + bb[2]) / 2 - S(3)
            d.polygon([(cx, S(156)), (cx + S(7), S(156)), (cx + S(3.5), S(160))], fill=p["fg"])
        sc.rec(nm, (min(bx, bb[0]) - S(5), S(92), max(bx + S(34), bb[2]) + S(5), S(164) if has_dd else bb[3] + S(3)), "icon_label", "ribbon:Insert", has_dropdown=has_dd)
        bx += S(84)
    # ---- left sidebar of icons
    d.rectangle((0, ry1 + 1, S(48), H - S(24)), fill=p["bar"])
    sc.regions.append({"kind": "sidebar", "label": "tool strip", "box": [0, ry1 + 1, S(48), H - S(24)]})
    y = ry1 + S(14)
    for nm in ("Home", "Search", "Open", "Mail", "Account", "Lock", "Settings"):
        sc.icon(nm, S(12), y, 24, "sidebar", pad=6)
        y += S(54)
    # ---- canvas (document page)
    d.rectangle((S(48), ry1 + 1, W, H - S(24)), fill=p["canvas"])
    sc.regions.append({"kind": "canvas", "label": "document", "box": [S(48), ry1 + 1, W, H - S(24)]})
    rnd = random.Random(7)
    pg = (S(300), ry1 + S(30), W - S(300), H - S(40))
    d.rectangle(pg, fill=(255, 255, 255) if theme == "light" else (84, 84, 90), outline=p["line"])
    words = "the quick brown fox jumps over the lazy dog while students read the quarterly numbers aloud".split()
    ty = pg[1] + S(24)
    for _ in range(9):
        line = " ".join(rnd.choice(words) for _ in range(9))
        d.text((pg[0] + S(30), ty), line, font=sc.f(13), fill=p["fg"])
        ty += S(22)
    d.rectangle((pg[0] + S(30), ty + S(10), pg[0] + S(330), ty + S(190)), fill=(120, 160, 210) if theme == "light" else (70, 100, 140))
    d.polygon([(pg[0] + S(30), ty + S(190)), (pg[0] + S(130), ty + S(100)), (pg[0] + S(230), ty + S(190))], fill=(70, 120, 90))
    # ---- status bar
    d.rectangle((0, H - S(24), W, H), fill=p["bar"])
    sc.regions.append({"kind": "statusbar", "label": "status bar", "box": [0, H - S(24), W, H]})
    x = S(14)
    for t in ("Page 1 of 3", "Words: 1,204", "English (US)"):
        bb = sc.text((x, H - S(19)), t, 11)
        sc.rec(t, (bb[0] - S(3), H - S(22), bb[2] + S(3), H - S(2)), "text", "statusbar")
        x = bb[2] + S(30)
    zx = W - S(200)
    sc.icon("Zoom Out", zx, H - S(21), 18, "statusbar", pad=3)
    d.line((zx + S(30), H - S(12), zx + S(130), H - S(12)), fill=p["muted"], width=2)
    d.rectangle((zx + S(76), H - S(18), zx + S(82), H - S(6)), fill=p["accent"])
    sc.icon("Zoom In", zx + S(140), H - S(21), 18, "statusbar", pad=3)
    return sc.img, sc.truth, sc.regions


def render_dialog(theme: str = "light", scale: float = 1.0, size: Tuple[int, int] = (1280, 800)) -> Tuple[Image.Image, List[Truth], List[Truth]]:
    """A modal dialog on a dimmed window: labelled fields, a drop-down, check boxes, radio buttons and three push buttons."""
    sc = _Scene((int(size[0] * scale), int(size[1] * scale)), theme, scale)
    d, p, S = sc.d, sc.p, sc.px
    W, H = sc.img.size
    d.rectangle((0, 0, W, H), fill=tuple(int(c * 0.55) for c in p["bg"]))
    dx0, dy0, dx1, dy1 = (W - S(560)) // 2, (H - S(380)) // 2, (W + S(560)) // 2, (H + S(380)) // 2
    d.rectangle((dx0, dy0, dx1, dy1), fill=p["bg"], outline=p["line"], width=2)
    d.rectangle((dx0, dy0, dx1, dy0 + S(34)), fill=p["bar"])
    sc.text((dx0 + S(14), dy0 + S(8)), "Page Setup", 14, bold=True)
    sc.regions.append({"kind": "dialog", "label": "Page Setup", "box": [dx0, dy0, dx1, dy1]})
    gm_close = (dx1 - S(40), dy0, dx1, dy0 + S(34))
    GLYPHS["Close"](d, (gm_close[0] + S(8), gm_close[1] + S(6), gm_close[2] - S(8), gm_close[3] - S(6)), p["fg"])
    sc.rec("Close", gm_close, "icon", "dialog")
    y = dy0 + S(58)
    for lab, val in (("Top margin", "1.0"), ("Bottom margin", "1.0"), ("Left margin", "1.25"), ("Right margin", "1.25")):
        sc.text((dx0 + S(24), y + S(3)), lab + ":", 13)
        d.rectangle((dx0 + S(160), y, dx0 + S(260), y + S(26)), fill=p["field"], outline=p["line"])
        sc.text((dx0 + S(168), y + S(4)), val, 13)
        sc.rec(lab, (dx0 + S(160), y, dx0 + S(260), y + S(26)), "field", "dialog")
        y += S(38)
    sc.text((dx0 + S(300), dy0 + S(61)), "Paper size:", 13)
    d.rectangle((dx0 + S(390), dy0 + S(58), dx1 - S(24), dy0 + S(86)), fill=p["field"], outline=p["line"])
    sc.text((dx0 + S(398), dy0 + S(63)), "Letter", 13)
    d.polygon([(dx1 - S(46), dy0 + S(68)), (dx1 - S(36), dy0 + S(68)), (dx1 - S(41), dy0 + S(75))], fill=p["fg"])
    sc.rec("Paper size", (dx0 + S(390), dy0 + S(58), dx1 - S(24), dy0 + S(86)), "field", "dialog", has_dropdown=True)
    y += S(14)
    for k, lab in enumerate(("Mirror margins", "Different first page", "Gutter at top")):
        cy = y + k * S(34)
        d.rectangle((dx0 + S(26), cy, dx0 + S(44), cy + S(18)), fill=p["field"], outline=p["fg"], width=2)
        if k == 1:
            _g_check = [(dx0 + S(29), cy + S(9)), (dx0 + S(34), cy + S(14)), (dx0 + S(42), cy + S(4))]
            d.line(_g_check, fill=p["accent"], width=3)
        bb = sc.text((dx0 + S(54), cy), lab, 13)
        sc.rec(lab, (dx0 + S(22), cy - S(3), bb[2] + S(6), cy + S(22)), "checkbox", "dialog")
    ry = y
    sc.text((dx0 + S(330), ry - S(4)), "Orientation", 13, bold=True)
    for k, lab in enumerate(("Portrait", "Landscape")):
        cy = ry + S(26) + k * S(34)
        d.ellipse((dx0 + S(332), cy, dx0 + S(350), cy + S(18)), fill=p["field"], outline=p["fg"], width=2)
        if k == 0:
            d.ellipse((dx0 + S(337), cy + S(5), dx0 + S(345), cy + S(13)), fill=p["accent"])
        bb = sc.text((dx0 + S(360), cy), lab, 13)
        sc.rec(lab, (dx0 + S(328), cy - S(3), bb[2] + S(6), cy + S(22)), "radio", "dialog")
    bx = dx1 - S(24)
    for lab in ("Apply", "Cancel", "OK"):
        bw = S(92)
        bx0 = bx - bw
        d.rounded_rectangle((bx0, dy1 - S(56), bx, dy1 - S(24)), radius=S(5), fill=p["accent"] if lab == "OK" else p["field"], outline=p["line"])
        f = sc.f(13, bold=(lab == "OK"))
        w = d.textlength(lab, font=f)
        d.text((bx0 + (bw - w) / 2, dy1 - S(48)), lab, font=f, fill=(255, 255, 255) if lab == "OK" else p["fg"])
        sc.rec(lab, (bx0, dy1 - S(56), bx, dy1 - S(24)), "rect_button", "dialog")
        bx = bx0 - S(12)
    return sc.img, sc.truth, sc.regions


def with_popup_menu(img: Image.Image, anchor: Tuple[int, int], items: Tuple[str, ...] = ("Picture from file", "Online pictures", "Screenshot", "Photo album"),
                    theme: str = "light", scale: float = 1.0) -> Tuple[Image.Image, List[Truth], Box]:
    """A drop-down menu opened under `anchor` (as after the learner clicked a ribbon button). Returns (new image, menu item truth, changed rectangle)."""
    p = THEMES[theme]
    out = img.copy()
    d = ImageDraw.Draw(out)
    f = _font(int(round(13 * scale)))
    iw = int(max(d.textlength(t, font=f) for t in items)) + int(46 * scale)
    ih = int(30 * scale)
    x0, y0 = anchor
    box = (x0, y0, x0 + iw, y0 + ih * len(items) + int(8 * scale))
    d.rectangle(box, fill=p["field"], outline=p["line"], width=1)
    truth: List[Truth] = []
    for k, t in enumerate(items):
        ty = y0 + int(4 * scale) + k * ih
        d.text((x0 + int(34 * scale), ty + int(6 * scale)), t, font=f, fill=p["fg"])
        bb = d.textbbox((x0 + int(34 * scale), ty + int(6 * scale)), t, font=f)
        d.rectangle((x0 + int(8 * scale), ty + int(7 * scale), x0 + int(24 * scale), ty + int(23 * scale)), outline=p["muted"])
        truth.append({"label": t, "box": [x0 + 1, ty, x0 + iw - 1, ty + ih], "kind": "text", "region": "menu"})
    return out, truth, Box(*box)


def match_truth(truth: List[Truth], elements: List[Any], min_overlap: float = 0.5) -> Dict[str, Any]:
    """Score a scan against the truth: found (box matched), named (box matched AND label agrees), per truth kind. `elements` are UIElement-like (bbox, label)."""
    from .schema import fold
    found = named = lenient = 0
    miss: List[Truth] = []
    wrong: List[Tuple[str, str]] = []
    by_kind: Dict[str, List[int]] = {}
    used: set = set()
    for t in truth:
        tb = Box(*t["box"])
        best, bs = None, 0.0
        for i, e in enumerate(elements):
            ov = max(e.bbox.overlap_frac(tb), tb.overlap_frac(e.bbox))
            iou = e.bbox.iou(tb)
            s = max(iou, 0.6 * ov)
            if ov >= min_overlap and s > bs and (e.bbox.area <= 4.0 * tb.area):
                best, bs = i, s
        k = by_kind.setdefault(t["kind"], [0, 0, 0])
        k[0] += 1
        if best is None:
            miss.append(t)
            continue
        found += 1
        k[1] += 1
        e = elements[best]
        a, b = fold(t["label"]), fold(e.label)
        if a and b and (a == b or a in b or b in a):
            named += 1
            lenient += 1
            k[2] += 1
        elif b and any(fold(al) == b or (len(fold(al)) > 2 and (fold(al) in b or b in fold(al))) for al in t.get("aliases", ())):
            lenient += 1                                     # a different but accepted name for the same glyph (Find for Search)
            k[2] += 1
        else:
            wrong.append((t["label"], e.label))
    n = len(truth)
    return {"truth": n, "found": found, "named": named, "named_lenient": lenient, "found_rate": round(found / n, 3) if n else None, "named_rate": round(named / n, 3) if n else None,
            "named_lenient_rate": round(lenient / n, 3) if n else None,
            "missed": [(m["label"], m["kind"]) for m in miss], "mislabeled": wrong[:30],
            "by_kind": {k: {"truth": v[0], "found": v[1], "named": v[2]} for k, v in by_kind.items()}}


def render_editor(scale: float = 1.0, size: Tuple[int, int] = (1600, 900)) -> Tuple[Image.Image, List[Truth], List[Truth]]:
    """A dense DOCKED editor (Blender / IDE style, dark): top bar with workspace tabs, a big viewport, a timeline underneath, and a right column split into two
    stacked editors (Outliner over Properties), all divided by thin dark gutters. Truth `regions` are the editor AREAS with their printed names."""
    sc = _Scene((int(size[0] * scale), int(size[1] * scale)), "dark", scale)
    d, S = sc.d, sc.px
    W, H = sc.img.size
    gut = (18, 18, 20)
    d.rectangle((0, 0, W, H), fill=gut)
    d.rectangle((0, 0, W, S(40)), fill=(44, 44, 48))
    sc.regions.append({"kind": "ribbon", "label": "top bar", "box": [0, 0, W, S(40)]})
    x = S(14)
    for t in ("Layout", "Modeling", "Sculpting", "Shading", "Animation"):
        bb = sc.text((x, S(11)), t, 13)
        sc.rec(t, (bb[0] - S(6), S(6), bb[2] + S(6), S(34)), "text", "top bar")
        x = bb[2] + S(28)
    areas = {"3D Viewport": (0, 46, 1100, 640), "Timeline": (0, 646, 1100, 860), "Outliner": (1106, 46, 1600, 400), "Properties": (1106, 406, 1600, 860)}
    fills = {"3D Viewport": (62, 62, 66), "Timeline": (36, 36, 40), "Outliner": (40, 40, 44), "Properties": (40, 40, 44)}
    for name, (x1, y1, x2, y2) in areas.items():
        box = (S(x1), S(y1), S(x2), S(y2))
        d.rectangle(box, fill=fills[name])
        sc.regions.append({"kind": "canvas" if name == "3D Viewport" else "panel", "label": name, "box": list(box)})
        if name != "3D Viewport":
            d.rectangle((box[0], box[1], box[2], box[1] + S(26)), fill=(52, 52, 58))
            bb = sc.text((box[0] + S(36), box[1] + S(5)), name, 13)
            sc.icon("Settings", box[0] + S(6), box[1] + S(3), 20, name, record=False)
            sc.rec(name + " header", (bb[0] - S(4), box[1] + S(2), bb[2] + S(4), box[1] + S(24)), "text", name)
    # viewport grid lines (must NOT be mistaken for dividers)
    for gx in range(0, 1100, 80):
        d.line((S(gx), S(46), S(gx), S(640)), fill=(76, 76, 80), width=1)
    for gy in range(46, 640, 60):
        d.line((0, S(gy), S(1100), S(gy)), fill=(76, 76, 80), width=1)
    d.polygon([(S(500), S(420)), (S(620), S(300)), (S(740), S(420)), (S(620), S(500))], fill=(120, 120, 124))
    # viewport header icons
    xx = S(10)
    for nm in ("Home", "Search", "Settings", "Open"):
        sc.icon(nm, xx, S(52), 22, "3D Viewport")
        xx += S(34)
    # timeline: transport icons + frame numbers
    xx = S(10)
    for nm in ("Zoom Out", "Add", "Zoom In"):
        sc.icon(nm, xx, S(676), 22, "Timeline")
        xx += S(36)
    for k, n in enumerate(range(0, 250, 25)):
        bb = sc.text((S(140 + k * 90), S(830)), str(n), 11)
    # outliner rows
    for k, nm in enumerate(("Scene Collection", "Collection", "Camera", "Cube", "Light")):
        bb = sc.text((S(1150 + (24 if k > 1 else 0)), S(88 + 34 * k)), nm, 13)
        sc.rec(nm, (bb[0] - S(4), bb[1] - S(3), bb[2] + S(4), bb[3] + S(3)), "text", "Outliner")
    # properties: label + value field rows
    for k, nm in enumerate(("Location X", "Location Y", "Location Z", "Rotation X", "Scale X")):
        yy = S(450 + 44 * k)
        sc.text((S(1130), yy + S(4)), nm, 13)
        d.rectangle((S(1330), yy, S(1560), yy + S(28)), fill=(30, 30, 34), outline=(80, 80, 84))
        sc.text((S(1340), yy + S(5)), "0 m" if k < 3 else "1.000", 13)
        sc.rec(nm, (S(1330), yy, S(1560), yy + S(28)), "field", "Properties")
    return sc.img, sc.truth, sc.regions
