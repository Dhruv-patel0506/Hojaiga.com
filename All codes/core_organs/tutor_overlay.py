"""
tutor_overlay -- the "plastic wrapper": red vector teaching marks on a transparent, click-through layer above any program, website or video.

It is built ON the Professor's overlay (professor.overlay: per-pixel-alpha layered windows that are click-through, never take focus and are left out of screenshots), and adds a second visual language
for teaching - thin red marks that show WHERE and WHAT, one beat at a time:

    box       a thin red rounded outline around a control, a row or a whole panel
    pointer   a tiny red diagonal arrow that glides to the bottom-right corner of the active box
    pill      a solid red rounded badge with white bold text ('kick step five', 'leg A equals 4'), put beside the box so it never covers the thing to click
    polygon / line / curve / arrow   multi-point shapes drawn stroke by stroke over the screen (a square on a triangle's side, a leader arrow, a freehand wave)
    status    a tiny dark pill at the top centre of the screen: Idle / Scanning / Listening / Thinking / Speaking

Pure drawing lives in the render_* functions (no windows): the same sprites are pushed into layered windows by RedOverlay and composed onto a screenshot by `compose_red_preview`, which is how the marks
are tested and looked at without putting a pixel on anyone's screen.
"""
from __future__ import annotations

import math
import queue
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from core_organs.professor import overlay as OV, overlay_render as R, pointing
from core_organs.professor.schema import Box

RED = (255, 42, 42)
RED_DARK = (190, 20, 20)
WHITE = (255, 255, 255)
INK = (17, 24, 39)
SS = 3
STATES = {"Idle": (156, 163, 175), "Scanning": (250, 204, 21), "Listening": (74, 222, 128), "Thinking": (96, 165, 250), "Speaking": (255, 42, 42)}


def _down(img: Image.Image) -> Image.Image:
    return img.resize((img.width // SS, img.height // SS), Image.LANCZOS)


def _glow(base: Image.Image, mask: Image.Image, radius: float, color: Tuple[int, int, int], strength: float = 0.9) -> Image.Image:
    g = mask.filter(ImageFilter.GaussianBlur(radius * SS)).point(lambda v: int(min(255, v * strength)))
    layer = Image.new("RGBA", base.size, color + (0,))
    layer.putalpha(g)
    return Image.alpha_composite(layer, base)


# ---------------------------------------------------------------------------------------------------------------------------------------------- sprites
def render_red_box(w: int, h: int, pulse: float = 0.0) -> Tuple[Image.Image, Tuple[int, int]]:
    """A thin rounded red outline of w x h with a soft glow. Returns the picture and the offset of its top-left from the box's top-left."""
    pad = 14
    W, H = (int(w) + 2 * pad) * SS, (int(h) + 2 * pad) * SS
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    r = max(4, min(10, int(min(w, h) / 4))) * SS
    box = (pad * SS, pad * SS, W - pad * SS, H - pad * SS)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, r, outline=255, width=int((3.0 + 1.2 * pulse) * SS))
    img = _glow(img, mask, 5 + 2 * pulse, RED, 0.9)
    ImageDraw.Draw(img).rounded_rectangle(box, r, outline=RED + (255,), width=int(2.6 * SS))
    return _down(img), (-pad, -pad)


def render_pill(text: str, size: int = 15) -> Image.Image:
    """A solid red rounded badge, white bold text."""
    font = R._bold(size * SS)
    probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    l, t, r_, b = probe.textbbox((0, 0), text, font=font)
    tw, th = r_ - l, b - t
    padx, pady = 11 * SS, 6 * SS
    W, H = tw + 2 * padx, th + 2 * pady + 2 * SS
    img = Image.new("RGBA", (W + 12 * SS, H + 12 * SS), (0, 0, 0, 0))
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((6 * SS, 6 * SS, 6 * SS + W, 6 * SS + H), H // 2, fill=255)
    img = _glow(img, m, 3, (0, 0, 0), 0.5)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6 * SS, 6 * SS, 6 * SS + W, 6 * SS + H), H // 2, fill=RED + (255,))
    d.text((6 * SS + padx - l, 6 * SS + pady - t + SS), text, font=font, fill=WHITE + (255,))
    return _down(img)


def place_pill(target: Box, size: Tuple[int, int], screen: Box, gap: int = 8) -> Tuple[int, int]:
    """Where the badge goes: beside the box (right, below, above, then left), inside the screen, never over the box."""
    w, h = size
    tries = [(target.x2 + gap, target.cy - h / 2), (target.cx - w / 2, target.y2 + gap), (target.cx - w / 2, target.y1 - h - gap), (target.x1 - w - gap, target.cy - h / 2)]
    for x, y in tries:
        if x >= screen.x1 + 2 and y >= screen.y1 + 2 and x + w <= screen.x2 - 2 and y + h <= screen.y2 - 2:
            return int(x), int(y)
    x, y = tries[1]
    return int(min(max(x, screen.x1 + 2), screen.x2 - w - 2)), int(min(max(y, screen.y1 + 2), screen.y2 - h - 2))


_ARROW = [(0, 0), (0, 25), (6, 19.5), (10.5, 29), (14.5, 27.4), (10.2, 18), (18, 18)]


def render_red_cursor(scale: float = 1.0, angle: float = 0.0, glow: float = 1.0) -> Tuple[Image.Image, Tuple[int, int]]:
    """The tiny red diagonal pointer; its TIP is the hotspot."""
    pad = int(14 * scale)
    w = int(19 * scale) + 2 * pad
    h = int(30 * scale) + 2 * pad
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    pts = [((x * scale + pad) * SS, (y * scale + pad) * SS) for x, y in _ARROW]
    if angle:
        cx, cy = (pad + 9 * scale) * SS, (pad + 14 * scale) * SS
        a = math.radians(angle)
        pts = [(cx + (x - cx) * math.cos(a) - (y - cy) * math.sin(a), cy + (x - cx) * math.sin(a) + (y - cy) * math.cos(a)) for x, y in pts]
    if glow > 0:
        m = Image.new("L", big.size, 0)
        ImageDraw.Draw(m).polygon(pts, fill=255)
        big = _glow(big, m, 4 * scale, RED, 1.2 * glow)
    d = ImageDraw.Draw(big)
    d.polygon(pts, fill=RED + (255,))
    d.line(pts + [pts[0]], fill=WHITE + (255,), width=int(2.0 * SS * scale), joint="curve")
    return _down(big), (-pad, -pad)


def smooth(points: Sequence[Tuple[float, float]], rounds: int = 3) -> List[Tuple[float, float]]:
    """Chaikin corner cutting: a few control points become a smooth curve."""
    pts = [tuple(p) for p in points]
    for _ in range(rounds):
        if len(pts) < 3:
            break
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            out += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]), (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        out.append(pts[-1])
        pts = out
    return pts


def _path(kind: str, points: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    pts = [tuple(map(float, p)) for p in points]
    if kind == "curve":
        return smooth(pts)
    if kind == "polygon" and pts and pts[0] != pts[-1]:
        return pts + [pts[0]]
    return pts


def path_length(pts: Sequence[Tuple[float, float]]) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def render_shape(kind: str, points: Sequence[Tuple[float, float]], fraction: float = 1.0, width: float = 4.5, fill: bool = True) -> Tuple[Image.Image, Tuple[int, int]]:
    """A red polygon / line / curve / arrow drawn up to `fraction` of its length (stroke animation). Returns the picture and the screen position of its top-left."""
    path = _path(kind, points)
    xs, ys = [p[0] for p in path], [p[1] for p in path]
    pad = int(width * 3 + 14)
    x0, y0 = int(min(xs)) - pad, int(min(ys)) - pad
    W, H = (int(max(xs)) - x0 + pad) * SS, (int(max(ys)) - y0 + pad) * SS
    img = Image.new("RGBA", (max(W, SS), max(H, SS)), (0, 0, 0, 0))
    total = path_length(path)
    goal = total * max(0.0, min(1.0, fraction))
    shown: List[Tuple[float, float]] = [path[0]]
    run = 0.0
    for a, b in zip(path, path[1:]):
        seg = math.dist(a, b)
        if run + seg <= goal:
            shown.append(b)
            run += seg
        else:
            t = (goal - run) / seg if seg else 0.0
            shown.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            break
    sp = [((x - x0) * SS, (y - y0) * SS) for x, y in shown]
    if len(sp) >= 2:
        m = Image.new("L", img.size, 0)
        ImageDraw.Draw(m).line(sp, fill=255, width=int(width * SS), joint="curve")
        img = _glow(img, m, 4, RED, 0.8)
        d = ImageDraw.Draw(img)
        if kind == "polygon" and fill and fraction >= 1.0:
            d.polygon([((x - x0) * SS, (y - y0) * SS) for x, y in path[:-1]], fill=RED + (34,))
        d.line(sp, fill=RED + (255,), width=int(width * SS), joint="curve")
        for p in (sp[0], sp[-1]) if kind in ("line", "curve") else ():
            r = width * SS * 0.7
            d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=RED + (255,))
        if kind == "arrow" and fraction >= 1.0 and len(path) >= 2:
            (ax, ay), (bx, by) = path[-2], path[-1]
            ang = math.atan2(by - ay, bx - ax)
            L = 16 * SS
            tip = ((bx - x0) * SS, (by - y0) * SS)
            wing = [(tip[0] - L * math.cos(ang - 0.45), tip[1] - L * math.sin(ang - 0.45)), tip, (tip[0] - L * math.cos(ang + 0.45), tip[1] - L * math.sin(ang + 0.45))]
            d.line(wing, fill=RED + (255,), width=int(width * SS), joint="curve")
    return _down(img), (x0, y0)


def render_status(text: str) -> Image.Image:
    """The tiny dark pill at the top centre: a coloured dot and one word."""
    color = STATES.get(text, STATES["Idle"])
    font = R._bold(13 * SS)
    probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    l, t, r_, b = probe.textbbox((0, 0), text, font=font)
    tw, th = r_ - l, b - t
    W, H = tw + 46 * SS, th + 14 * SS
    img = Image.new("RGBA", (W + 8 * SS, H + 8 * SS), (0, 0, 0, 0))
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((4 * SS, 4 * SS, 4 * SS + W, 4 * SS + H), H // 2, fill=255)
    img = _glow(img, m, 3, (0, 0, 0), 0.6)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4 * SS, 4 * SS, 4 * SS + W, 4 * SS + H), H // 2, fill=INK + (235,))
    cy = 4 * SS + H // 2
    d.ellipse((4 * SS + 12 * SS, cy - 4 * SS, 4 * SS + 20 * SS, cy + 4 * SS), fill=color + (255,))
    d.text((4 * SS + 28 * SS - l, 4 * SS + 7 * SS - t), text, font=font, fill=WHITE + (255,))
    return _down(img)


# ---------------------------------------------------------------------------------------------------------------------------------------------- headless composition
def compose_red_preview(background: Image.Image, commands: Sequence[Dict[str, Any]], origin: Tuple[int, int] = (0, 0)) -> Image.Image:
    """The marks as they would look over `background` (a screenshot whose top-left is at screen position `origin`), without any window."""
    out = background.convert("RGBA")
    screen = Box.xywh(origin[0], origin[1], out.width, out.height)

    def paste(img: Image.Image, x: float, y: float) -> None:
        out.alpha_composite(img, (int(x - origin[0]), int(y - origin[1]))) if (0 <= int(x - origin[0]) and 0 <= int(y - origin[1]) and int(x - origin[0]) + img.width <= out.width
                                                                                and int(y - origin[1]) + img.height <= out.height) else out.paste(img, (int(x - origin[0]), int(y - origin[1])), img)
    for c in commands:
        k = c["cmd"]
        if k == "box":
            b: Box = c["box"]
            img, off = render_red_box(int(b.w), int(b.h))
            paste(img, b.x1 + off[0], b.y1 + off[1])
            if c.get("pill"):
                pill = render_pill(c["pill"])
                px, py = place_pill(b, pill.size, screen)
                paste(pill, px, py)
            if c.get("pointer", True):
                cur, off = render_red_cursor(1.0, 0.0, 0.8)
                paste(cur, b.x2 + off[0], b.y2 + off[1])
        elif k == "shape":
            img, off = render_shape(c["kind"], c["points"], 1.0)
            paste(img, off[0], off[1])
            if c.get("pill"):
                pts = c["points"]
                anchor = Box(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
                pill = render_pill(c["pill"])
                px, py = place_pill(anchor, pill.size, screen)
                paste(pill, px, py)
        elif k == "badge":
            pill = render_pill(c["text"])
            paste(pill, c["x"] - pill.width / 2, c["y"] - pill.height / 2)
        elif k == "status":
            st = render_status(c["text"])
            paste(st, origin[0] + (out.width - st.width) / 2, origin[1] + 6)
    return out


# ---------------------------------------------------------------------------------------------------------------------------------------------- actors
def _np(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGBA"))


class RedBoxActor(OV.Actor):
    def __init__(self, box: Box) -> None:
        super().__init__()
        self.box = box
        w, h = max(10, int(box.w)), max(10, int(box.h))
        self.frames: List[np.ndarray] = []
        self.off = (0, 0)
        for p in (0.0, 0.5, 1.0):
            img, self.off = render_red_box(w, h, p)
            self.frames.append(_np(img))
        self._last = -1

    def draw(self, now: float) -> None:
        k = abs(((now - self.born) * 0.9) % 2.0 - 1.0)
        idx = int(round(k * (len(self.frames) - 1)))
        win = self._win()
        if idx != self._last or not win.visible:
            win.set_bitmap(self.frames[idx])
            self._last = idx
        win.show(int(self.box.x1 + self.off[0]), int(self.box.y1 + self.off[1]), int(255 * self.alpha(now)))


class PillActor(OV.Actor):
    def __init__(self, text: str, target: Box, screen: Box) -> None:
        super().__init__()
        img = render_pill(text)
        self.xy = place_pill(target, img.size, screen)
        self.bitmap = _np(img)

    def draw(self, now: float) -> None:
        win = self._win()
        if not win.hbm:
            win.set_bitmap(self.bitmap)
        win.show(self.xy[0], self.xy[1], int(255 * self.alpha(now)))


class RedCursorActor(OV.CursorActor):
    """The tiny red pointer: same flight as the Professor's pointer, red sprite."""

    def __init__(self, start: Tuple[float, float]) -> None:
        super().__init__(start)
        self.sprites = {}
        for sc in (0.8, 0.92, 1.05):
            img, off = render_red_cursor(sc, 0.0, 0.9)
            self.sprites[{0.8: 1.0, 0.92: 1.15, 1.05: 1.3}[sc]] = (_np(img), off)
        self.spin = []
        for ang in range(0, 360, 30):
            img, off = render_red_cursor(0.8, float(ang), 0.7)
            self.spin.append((_np(img), off))


class ShapeActor(OV.Actor):
    """A polygon / line / curve / arrow that DRAWS itself, stroke by stroke, then stays."""

    def __init__(self, kind: str, points: Sequence[Tuple[float, float]], seconds: float = 0.9) -> None:
        super().__init__()
        self.fade_in = 0.05
        self.seconds = max(0.1, seconds)
        self.n = 18
        self.frames: List[Tuple[np.ndarray, Tuple[int, int]]] = []
        for i in range(1, self.n + 1):
            img, off = render_shape(kind, points, i / self.n)
            self.frames.append((_np(img), off))
        self._last = -1

    def settled(self, now: float) -> bool:
        return now - self.born >= self.seconds

    def draw(self, now: float) -> None:
        idx = min(self.n - 1, int((now - self.born) / self.seconds * self.n))
        win = self._win()
        if idx != self._last or not win.visible:
            win.set_bitmap(self.frames[idx][0])
            self._last = idx
        win.show(self.frames[idx][1][0], self.frames[idx][1][1], int(255 * self.alpha(now)))


class StatusActor(OV.Actor):
    def __init__(self, text: str, screen: Box) -> None:
        super().__init__()
        self.screen = screen
        self.text = ""
        self.bitmap: Optional[np.ndarray] = None
        self.size = (0, 0)
        self.set(text)

    def set(self, text: str) -> None:
        if text != self.text:
            img = render_status(text)
            self.bitmap, self.size, self.text = _np(img), img.size, text
            if self.win is not None:
                self.win.set_bitmap(self.bitmap)

    def draw(self, now: float) -> None:
        win = self._win()
        if not win.hbm:
            win.set_bitmap(self.bitmap)
        win.show(int(self.screen.cx - self.size[0] / 2), int(self.screen.y1 + 6), int(255 * self.alpha(now)))


# ---------------------------------------------------------------------------------------------------------------------------------------------- the overlay
class RedOverlay(OV.Overlay):
    """The Professor's overlay plus the red teaching marks. Every method returns at once; drawing happens on the overlay thread."""
    kind = "red-layered-window"

    def __init__(self) -> None:
        super().__init__()
        self.red_cursor: Optional[RedCursorActor] = None
        self.status_actor: Optional[StatusActor] = None
        self._box_actors: List[OV.Actor] = []

    def box(self, box: Box, pill: str = "", pointer: bool = True) -> None:
        """A thin red box around `box`, a red badge beside it, and the tiny red pointer gliding to its bottom-right corner."""
        self._idle.clear()
        self._q.put(("r_box", (box, pill, pointer)))

    def shape(self, kind: str, points: Sequence[Tuple[float, float]], pill: str = "", seconds: float = 0.9) -> None:
        self._idle.clear()
        self._q.put(("r_shape", (kind, [tuple(p) for p in points], pill, seconds)))

    def status(self, text: str) -> None:
        self._q.put(("r_status", (text,)))

    def badge(self, text: str, x: float, y: float) -> None:
        """A red badge on its own (a key combination to press, a name for a whole region), centred on (x, y)."""
        self._idle.clear()
        self._q.put(("r_badge", (text, x, y)))

    def wipe(self) -> None:
        """Take away every red mark (the status pill stays)."""
        self._q.put(("r_wipe", ()))

    def _primary(self) -> Box:
        try:
            return OV.virtual_screen() if False else OV.monitor_at(0, 0).box
        except Exception:
            return OV.virtual_screen()

    def _handle(self, cmd: str, a: tuple, now: float) -> None:
        if cmd == "r_box":
            box, pill, pointer = a
            for ac in self._box_actors:                                           # the previous box and its badge go; drawn shapes stay until wipe()
                ac.kill(now)
            self._box_actors = [RedBoxActor(box)]
            if pill:
                self._box_actors.append(PillActor(pill, box, self._screen_for(box)))
            self.actors += self._box_actors
            if pointer:
                if self.red_cursor is None or not self.red_cursor.alive(now):
                    self.red_cursor = RedCursorActor(OV.cursor_pos())
                    self.actors.append(self.red_cursor)
                self.red_cursor.fly_to(box.x2 - 2, box.y2 - 2)
        elif cmd == "r_shape":
            kind, pts, pill, secs = a
            self.actors.append(ShapeActor(kind, pts, secs))
            if pill:
                anchor = Box(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
                self.actors.append(PillActor(pill, anchor, self._screen_for(anchor)))
        elif cmd == "r_badge":
            text, x, y = a
            for ac in self._box_actors:
                ac.kill(now)
            at = Box(x, y, x, y)
            self._box_actors = [PillActor(text, at, self._screen_for(at))]
            self.actors += self._box_actors
        elif cmd == "r_status":
            if self.status_actor is None or not self.status_actor.alive(now):
                self.status_actor = StatusActor(a[0], self._primary())
                self.actors.append(self.status_actor)
            else:
                self.status_actor.set(a[0])
        elif cmd == "r_wipe":
            for ac in self.actors:
                if ac is not self.status_actor:
                    ac.kill(now)
            self.red_cursor = None
            self._box_actors = []
        else:
            super()._handle(cmd, a, now)


class RecordingRedOverlay:
    """The headless twin: records every mark as data, composes a preview, never opens a window."""
    kind = "recording-red"

    def __init__(self, reason: str = "") -> None:
        self.error = reason
        self.commands: List[Dict[str, Any]] = []

    def start(self) -> bool:
        return True

    def stop(self) -> None:
        pass

    def box(self, box: Box, pill: str = "", pointer: bool = True) -> None:
        self.commands = [c for c in self.commands if c["cmd"] != "box"] + [{"cmd": "box", "box": box, "pill": pill, "pointer": pointer}]

    def shape(self, kind: str, points: Sequence[Tuple[float, float]], pill: str = "", seconds: float = 0.9) -> None:
        self.commands.append({"cmd": "shape", "kind": kind, "points": [tuple(p) for p in points], "pill": pill})

    def status(self, text: str) -> None:
        self.commands = [c for c in self.commands if c["cmd"] != "status"] + [{"cmd": "status", "text": text}]

    def badge(self, text: str, x: float, y: float) -> None:
        self.commands = [c for c in self.commands if c["cmd"] not in ("box", "badge")] + [{"cmd": "badge", "text": text, "x": x, "y": y}]

    def wipe(self) -> None:
        self.commands = [c for c in self.commands if c["cmd"] == "status"]

    def clear(self) -> None:
        self.wipe()

    def wait_idle(self, timeout: float = 5.0) -> bool:
        return True

    def preview(self, background: Image.Image, origin: Tuple[int, int] = (0, 0)) -> Image.Image:
        return compose_red_preview(background, self.commands, origin)


def make_red_overlay(kind: str = "auto") -> Any:
    """'auto' = the real overlay when this machine can create one, else the recording twin."""
    if kind == "recording":
        return RecordingRedOverlay("requested")
    ov = RedOverlay()
    if kind in ("auto", "real") and ov.start():
        return ov
    return ov if kind == "real" else RecordingRedOverlay(ov.error or "overlay unavailable")
