"""
professor.overlay_render -- how the Professor's guidance LOOKS: pure drawing, no windows, no OS calls.

Every function returns an RGBA picture (straight alpha) plus the offset of that picture's top-left corner from the anchor it describes, so the same
sprites can be (a) pushed into click-through layered windows by professor.overlay, or (b) composed onto a screenshot by `compose_preview` to SEE the result
without putting anything on the user's screen (tests, documentation, `hojaiga_professor.py preview`).

Style: Clicky's blue pointer and glow, a pulsing rounded outline around the target control, a dark speech bubble with a numbered step badge and a tail
pointing at the control, an optional spotlight that dims everything else. All supersampled 3x for smooth edges.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .grounding import _font
from .schema import Box

ACCENT = (59, 130, 246)
ACCENT_LIGHT = (147, 197, 253)
BUBBLE = (17, 24, 39)
WHITE = (255, 255, 255)
SS = 3                                       # supersampling factor


def _bold(px: int):
    for name in ("segoeuib.ttf", "arialbd.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except Exception:
            continue
    return ImageFont.load_default()


def _down(img: Image.Image) -> Image.Image:
    return img.resize((img.width // SS, img.height // SS), Image.LANCZOS)


# ------------------------------------------------------------------------------------------------------------ cursor
_ARROW = [(0, 0), (0, 26), (7, 20), (12, 31), (16, 29), (11, 18), (19, 18)]


def render_cursor(scale: float = 1.0, angle: float = 0.0, glow: float = 1.0) -> Tuple[Image.Image, Tuple[int, int]]:
    """Clicky-style pointer: blue arrow with a white edge and soft glow. The TIP is the hotspot -> returns offset (-tipx, -tipy) of the picture's origin."""
    pad = int(30 * scale)
    w = int((22 * scale)) + 2 * pad
    h = int((34 * scale)) + 2 * pad
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    pts = [((x * scale + pad) * SS, (y * scale + pad) * SS) for x, y in _ARROW]
    if angle:
        cx, cy = (pad + 10 * scale) * SS, (pad + 14 * scale) * SS
        a = math.radians(angle)
        pts = [(cx + (x - cx) * math.cos(a) - (y - cy) * math.sin(a), cy + (x - cx) * math.sin(a) + (y - cy) * math.cos(a)) for x, y in pts]
    if glow > 0:
        g = Image.new("L", big.size, 0)
        ImageDraw.Draw(g).polygon(pts, fill=255)
        g = g.filter(ImageFilter.GaussianBlur(9 * SS * scale / 1.0))
        g = g.point(lambda v: int(min(255, v * 1.6 * glow)))
        glow_img = Image.new("RGBA", big.size, ACCENT + (0,))
        glow_img.putalpha(g)
        big = Image.alpha_composite(big, glow_img)
    d = ImageDraw.Draw(big)
    d.polygon(pts, fill=ACCENT + (255,))
    d.line(pts + [pts[0]], fill=WHITE + (255,), width=int(2.6 * SS * scale), joint="curve")
    return _down(big), (-pad, -pad)


# --------------------------------------------------------------------------------------------------------- highlight
def render_highlight(w: int, h: int, pulse: float = 0.0, strength: float = 1.0, margin: int = 28) -> Tuple[Image.Image, Tuple[int, int]]:
    """Rounded outline + glow around a w x h control. pulse in [0,1] swells the glow/outline; strength in [0,1] is the fade. Offset = (-margin, -margin)."""
    r = int(max(6, min(14, min(w, h) * 0.22)))
    grow = 1.5 + 2.5 * pulse
    W, H = (int(w) + 2 * margin) * SS, (int(h) + 2 * margin) * SS
    box = (margin * SS, margin * SS, (margin + w) * SS, (margin + h) * SS)
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).rounded_rectangle(box, radius=r * SS, outline=255, width=int(5 * SS))
    glow = glow.filter(ImageFilter.GaussianBlur((6 + 5 * pulse) * SS))
    glow = glow.point(lambda v: int(min(255, v * (1.1 + 0.7 * pulse) * strength)))
    img = Image.new("RGBA", (W, H), ACCENT_LIGHT + (0,))
    img.putalpha(glow)
    d = ImageDraw.Draw(img)
    exp = int(grow * SS)
    d.rounded_rectangle((box[0] - exp, box[1] - exp, box[2] + exp, box[3] + exp), radius=r * SS + exp, outline=ACCENT + (int(255 * strength),), width=int(3 * SS))
    fill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(fill).rounded_rectangle(box, radius=r * SS, fill=ACCENT + (int(34 * strength),))
    img = Image.alpha_composite(fill, img)
    return _down(img), (-margin, -margin)


def render_ripple(radius: float, alpha: float, thick: float = 3.0) -> Tuple[Image.Image, Tuple[int, int]]:
    m = int(radius + 8)
    big = Image.new("RGBA", (2 * m * SS, 2 * m * SS), (0, 0, 0, 0))
    ImageDraw.Draw(big).ellipse((m * SS - radius * SS, m * SS - radius * SS, m * SS + radius * SS, m * SS + radius * SS),
                                outline=ACCENT + (int(255 * max(0.0, min(1.0, alpha))),), width=int(thick * SS))
    return _down(big), (-m, -m)


def render_circle(r: float = 22, pulse: float = 0.0, strength: float = 1.0) -> Tuple[Image.Image, Tuple[int, int]]:
    """Fallback marker for a guessed point (no measured box): a ring with a dot."""
    m = int(r + 24)
    big = Image.new("RGBA", (2 * m * SS, 2 * m * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    rr = (r + 3 * pulse) * SS
    d.ellipse((m * SS - rr, m * SS - rr, m * SS + rr, m * SS + rr), outline=ACCENT + (int(255 * strength),), width=int(4 * SS))
    d.ellipse((m * SS - 5 * SS, m * SS - 5 * SS, m * SS + 5 * SS, m * SS + 5 * SS), fill=ACCENT + (int(255 * strength),))
    return _down(big), (-m, -m)


# ----------------------------------------------------------------------------------------------------------- bubble
def _wrap(text: str, font, max_w: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    cur = ""
    for w in words:
        t = (cur + " " + w).strip()
        if font.getlength(t) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def hotkey_parts(hotkey: str) -> List[str]:
    """'Ctrl+Shift+S' -> ['Ctrl', 'Shift', 'S'] (the caps of the badge)."""
    return [p.strip() for p in (hotkey or "").replace(" + ", "+").split("+") if p.strip()] or ([hotkey.strip()] if (hotkey or "").strip() else [])


def render_bubble(text: str, step: Optional[int] = None, max_w: int = 340, tail: str = "up", strength: float = 1.0,
                  tail_x: Optional[float] = None, hotkey: str = "") -> Tuple[Image.Image, Tuple[int, int]]:
    """Speech bubble. `tail` = which side points at the target ('up' tail on top edge when the bubble sits BELOW the target, 'down', 'left', 'right', '' none).
    `hotkey` adds a row of key caps under the text (the shortcut the application itself prints for this command).
    Returns (picture, tail_tip) where tail_tip is the pixel inside the picture the tail points at (so the caller can align it to the target)."""
    f = _font(16)
    fb = _bold(15)
    pad_x, pad_y, gap = 16, 12, 8
    badge = 26 if step is not None else 0
    inner_w = max_w - 2 * pad_x - (badge + gap if badge else 0)
    lines = _wrap(text, f, inner_w) or [""]
    lh = 22
    tw = max(f.getlength(l) for l in lines)
    caps = hotkey_parts(hotkey)
    chip_h = 26 if caps else 0
    fc = _bold(14)
    cap_w = [int(fc.getlength(c)) + 18 for c in caps]
    chips_w = (sum(cap_w) + 6 * (len(caps) - 1) + 8) if caps else 0
    tw = max(tw, chips_w)
    bw = int(min(max(max_w, chips_w + 2 * pad_x + (badge + gap if badge else 0)), tw + 2 * pad_x + (badge + gap if badge else 0))) + 2
    bh = max(badge + 2 * pad_y - 6, len(lines) * lh + 2 * pad_y) + (chip_h + 6 if caps else 0)
    tl = 12                                                   # tail length
    ox = oy = 14                                              # room for the blurred shadow, so it is never cut off at the picture edge
    W = bw + 2 * ox + (tl if tail in ("left", "right") else 0)
    H = bh + 2 * oy + (tl if tail in ("up", "down") else 0)
    bx = ox + (tl if tail == "left" else 0)
    by = oy + (tl if tail == "up" else 0)
    big = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    shadow = Image.new("L", big.size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle(((bx + 1) * SS, (by + 4) * SS, (bx + bw + 1) * SS, (by + bh + 4) * SS), radius=14 * SS, fill=110)
    shadow = shadow.filter(ImageFilter.GaussianBlur(5 * SS))
    sh = Image.new("RGBA", big.size, (0, 0, 0, 0))
    sh.putalpha(shadow)
    big = Image.alpha_composite(big, sh)
    d = ImageDraw.Draw(big)
    col = BUBBLE + (int(240 * strength),)
    d.rounded_rectangle((bx * SS, by * SS, (bx + bw) * SS, (by + bh) * SS), radius=14 * SS, fill=col)
    tip = (bx + bw / 2.0, by + bh / 2.0)
    tx = (bx + bw / 2.0) if tail_x is None else min(max(bx + 22, tail_x), bx + bw - 22)
    if tail == "up":
        d.polygon([((tx - 9) * SS, by * SS + 1), ((tx + 9) * SS, by * SS + 1), (tx * SS, (by - tl) * SS)], fill=col)
        tip = (tx, by - tl)
    elif tail == "down":
        d.polygon([((tx - 9) * SS, (by + bh) * SS - 1), ((tx + 9) * SS, (by + bh) * SS - 1), (tx * SS, (by + bh + tl) * SS)], fill=col)
        tip = (tx, by + bh + tl)
    elif tail == "left":
        d.polygon([(bx * SS + 1, (by + bh / 2 - 9) * SS), (bx * SS + 1, (by + bh / 2 + 9) * SS), ((bx - tl) * SS, (by + bh / 2) * SS)], fill=col)
        tip = (bx - tl, by + bh / 2)
    elif tail == "right":
        d.polygon([((bx + bw) * SS - 1, (by + bh / 2 - 9) * SS), ((bx + bw) * SS - 1, (by + bh / 2 + 9) * SS), ((bx + bw + tl) * SS, (by + bh / 2) * SS)], fill=col)
        tip = (bx + bw + tl, by + bh / 2)
    small = _down(big)
    d2 = ImageDraw.Draw(small)
    x0 = bx + pad_x
    if badge:
        cx, cy = bx + pad_x + badge / 2, by + pad_y + badge / 2 - 2
        bimg = Image.new("RGBA", (badge * SS, badge * SS), (0, 0, 0, 0))
        ImageDraw.Draw(bimg).ellipse((0, 0, badge * SS - 1, badge * SS - 1), fill=ACCENT + (255,))
        small.alpha_composite(_down(bimg), (int(cx - badge / 2), int(cy - badge / 2)))
        s = str(step)
        d2.text((cx - fb.getlength(s) / 2, cy - 10), s, font=fb, fill=WHITE + (255,))
        x0 += badge + gap
    y = by + pad_y
    for l in lines:
        d2.text((x0, y), l, font=f, fill=WHITE + (int(255 * strength),))
        y += lh
    if caps:
        cx0 = x0
        cy0 = y + 4
        for c, w in zip(caps, cap_w):
            d2.rounded_rectangle((cx0, cy0, cx0 + w, cy0 + chip_h - 4), radius=5, fill=(34, 36, 48, 255), outline=(235, 235, 245, 255), width=1)
            d2.rounded_rectangle((cx0 + 1, cy0 + 1, cx0 + w - 1, cy0 + chip_h - 8), radius=4, fill=(58, 62, 80, 255))
            d2.text((cx0 + (w - fc.getlength(c)) / 2, cy0 + 2), c, font=fc, fill=WHITE + (255,))
            cx0 += w + 6
    if strength < 1.0:
        a = small.getchannel("A").point(lambda v: int(v * strength))
        small.putalpha(a)
    return small, (int(tip[0]), int(tip[1]))


def place_bubble(target: Box, size: Tuple[int, int], tail_tip: Tuple[int, int], screen: Box, gap: int = 14) -> Tuple[int, int, str]:
    """Top-left of the bubble picture and the tail side to use, so that the tail tip touches the target's edge and the bubble stays on screen.
    Preference: below the target, else above, else to the right, else to the left."""
    bw, bh = size
    options = []
    below_y = target.y2 + gap
    above_y = target.y1 - gap - bh
    options.append(("up", target.cx - bw / 2, below_y, below_y + bh <= screen.y2))
    options.append(("down", target.cx - bw / 2, above_y, above_y >= screen.y1))
    right_x = target.x2 + gap
    left_x = target.x1 - gap - bw
    options.append(("left", right_x, target.cy - bh / 2, right_x + bw <= screen.x2))
    options.append(("right", left_x, target.cy - bh / 2, left_x >= screen.x1))
    for side, x, y, ok in options:
        if ok:
            return int(min(max(x, screen.x1 + 6), screen.x2 - bw - 6)), int(min(max(y, screen.y1 + 6), screen.y2 - bh - 6)), side
    return int(min(max(target.cx - bw / 2, screen.x1 + 6), screen.x2 - bw - 6)), int(min(max(target.y2 + gap, screen.y1 + 6), screen.y2 - bh - 6)), "up"


# ---------------------------------------------------------------------------------------------------------- spotlight
def render_spotlight(size: Tuple[int, int], hole: Box, dim: float = 0.55, feather: int = 18) -> Image.Image:
    """Black veil over a monitor-sized area with a soft-edged hole around `hole` (picture coordinates)."""
    w, h = size
    veil = Image.new("L", (w, h), int(255 * dim))
    d = ImageDraw.Draw(veil)
    d.rounded_rectangle(hole.expand(6).ituple(), radius=14, fill=0)
    veil = veil.filter(ImageFilter.GaussianBlur(feather))
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.putalpha(veil)
    return out


# ------------------------------------------------------------------------------------------------------------ arrow
def render_arrow(p0: Tuple[float, float], p1: Tuple[float, float], strength: float = 1.0) -> Tuple[Image.Image, Tuple[int, int]]:
    """Curved arrow from p0 to p1 (screen px) with an arrow head at p1. Offset is the picture's top-left in screen px."""
    pad = 24
    x1, y1 = min(p0[0], p1[0]) - pad, min(p0[1], p1[1]) - pad
    x2, y2 = max(p0[0], p1[0]) + pad, max(p0[1], p1[1]) + pad
    W, H = int(x2 - x1), int(y2 - y1)
    big = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    a = (( p0[0] - x1) * SS, (p0[1] - y1) * SS)
    b = ((p1[0] - x1) * SS, (p1[1] - y1) * SS)
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    dx, dy = b[0] - a[0], b[1] - a[1]
    dist = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / dist, dx / dist
    cx, cy = mx + nx * dist * 0.18, my + ny * dist * 0.18
    pts = []
    for i in range(0, 25):
        t = i / 24.0
        u = 1 - t
        pts.append((u * u * a[0] + 2 * u * t * cx + t * t * b[0], u * u * a[1] + 2 * u * t * cy + t * t * b[1]))
    col = ACCENT + (int(255 * strength),)
    d.line(pts, fill=col, width=int(4 * SS), joint="curve")
    ex, ey = pts[-1][0] - pts[-4][0], pts[-1][1] - pts[-4][1]
    el = math.hypot(ex, ey) or 1.0
    ux, uy = ex / el, ey / el
    hl = 16 * SS
    left = (b[0] - ux * hl + uy * hl * 0.55, b[1] - uy * hl - ux * hl * 0.55)
    right = (b[0] - ux * hl - uy * hl * 0.55, b[1] - uy * hl + ux * hl * 0.55)
    d.polygon([b, left, right], fill=col)
    return _down(big), (int(x1), int(y1))


# -------------------------------------------------------------------------------------------------------- composing
def compose_preview(background: Image.Image, commands: Sequence[Dict], origin: Tuple[int, int] = (0, 0), dim: bool = False) -> Image.Image:
    """Paint the STEADY-STATE look of a list of overlay commands onto a screenshot. Commands (screen coordinates; `origin` = screen position of the picture):
       {"type":"highlight","box":[x1,y1,x2,y2],"pulse":0..1}  {"type":"cursor","x":..,"y":..}  {"type":"bubble","text":..,"step":n,"box":[..]}
       {"type":"arrow","from":[x,y],"to":[x,y]}  {"type":"circle","x":..,"y":..}  {"type":"spotlight","box":[..]}"""
    out = background.convert("RGBA")
    ox, oy = origin
    screen = Box(ox, oy, ox + out.width, oy + out.height)
    for c in commands:
        t = c.get("type")
        if t == "spotlight":
            hole = Box.of(c["box"]).shift(-ox, -oy)
            out = Image.alpha_composite(out, render_spotlight(out.size, hole, 0.5 if not dim else 0.65))
    for c in commands:
        t = c.get("type")
        if t == "highlight":
            b = Box.of(c["box"])
            img, (dx, dy) = render_highlight(int(b.w), int(b.h), c.get("pulse", 0.3))
            _paste(out, img, b.x1 - ox + dx, b.y1 - oy + dy)
        elif t == "circle":
            img, (dx, dy) = render_circle(22, c.get("pulse", 0.3))
            _paste(out, img, c["x"] - ox + dx, c["y"] - oy + dy)
        elif t == "arrow":
            img, (px, py) = render_arrow(tuple(c["from"]), tuple(c["to"]))
            _paste(out, img, px - ox, py - oy)
        elif t == "bubble":
            b = Box.of(c["box"])
            img, tip = render_bubble(c.get("text", ""), c.get("step"), 340, "up", hotkey=c.get("hotkey", ""))
            x, y, side = place_bubble(b, img.size, tip, screen)
            img, tip = render_bubble(c.get("text", ""), c.get("step"), 340, side, tail_x=(b.cx - x) if side in ("up", "down") else None, hotkey=c.get("hotkey", ""))
            x, y, _s = place_bubble(b, img.size, tip, screen)
            _paste(out, img, x - ox, y - oy)
    for c in commands:
        if c.get("type") == "cursor":
            img, (dx, dy) = render_cursor(1.0, 0.0, 1.0)
            _paste(out, img, c["x"] - ox + dx, c["y"] - oy + dy)
    return out.convert("RGB")


def _inside(img: Image.Image, x: float, y: float, bg: Image.Image) -> bool:
    return x >= 0 and y >= 0 and x + img.width <= bg.width and y + img.height <= bg.height


def _paste(bg: Image.Image, img: Image.Image, x: float, y: float) -> None:
    """alpha_composite with clipping (PIL refuses sprites that hang over the edge)."""
    x, y = int(round(x)), int(round(y))
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1, sy1 = min(img.width, bg.width - x), min(img.height, bg.height - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    bg.alpha_composite(img.crop((sx0, sy0, sx1, sy1)), (x + sx0, y + sy0))
