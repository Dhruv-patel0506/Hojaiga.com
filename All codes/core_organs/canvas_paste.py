"""
canvas_paste.py -- put pixels on an app's canvas with ZERO physical input (P1-F)

A XAML / WinUI canvas (Paint) does not accept posted pointer messages and exposes no UIA pattern that can stroke a line, so a shape cannot be
DRAGGED onto it headlessly (measured). What every canvas app does accept is its own Paste command, driven through UIA like any other command.
So the shape is rendered off-screen (PIL), placed on the CLIPBOARD (a data transfer, not input), the app's 'Paste' command is invoked through the
actuation backbone, and the result is verified from the saved file's pixels.

The clipboard is the user's: it is read first, and the image is only placed when the clipboard is EMPTY or holds plain TEXT (which is put back
afterwards). Any other content (an image, files, rich data) is never overwritten: the call reports that and does nothing.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct
import time
from typing import Any, Dict, Optional, Tuple

_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_H = ctypes.c_void_p
_u32.OpenClipboard.argtypes = [_H]
_u32.OpenClipboard.restype = wt.BOOL
_u32.CloseClipboard.restype = wt.BOOL
_u32.EmptyClipboard.restype = wt.BOOL
_u32.SetClipboardData.argtypes = [wt.UINT, _H]
_u32.SetClipboardData.restype = _H
_u32.GetClipboardData.argtypes = [wt.UINT]
_u32.GetClipboardData.restype = _H
_u32.EnumClipboardFormats.argtypes = [wt.UINT]
_u32.EnumClipboardFormats.restype = wt.UINT
_k32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
_k32.GlobalAlloc.restype = _H
_k32.GlobalLock.argtypes = [_H]
_k32.GlobalLock.restype = _H
_k32.GlobalUnlock.argtypes = [_H]
_k32.GlobalSize.argtypes = [_H]
_k32.GlobalSize.restype = ctypes.c_size_t

CF_UNICODETEXT, CF_DIB = 13, 8
GMEM_MOVEABLE = 0x0002
_SAFE_PLAIN = {1, 13, 16, 7}          # CF_TEXT, CF_UNICODETEXT, CF_LOCALE, CF_OEMTEXT: plain text (and its locale tag)


def _open(retries: int = 20) -> bool:
    for _ in range(retries):
        if _u32.OpenClipboard(None):
            return True
        time.sleep(0.05)
    return False


def clipboard_formats() -> Tuple[Optional[list], str]:
    """(list of formats, '') or (None, why)."""
    if not _open():
        return None, "clipboard busy"
    try:
        fmts, f = [], 0
        while True:
            f = _u32.EnumClipboardFormats(f)
            if not f:
                break
            fmts.append(int(f))
        return fmts, ""
    finally:
        _u32.CloseClipboard()


def _read_text() -> Optional[str]:
    if not _open():
        return None
    try:
        h = _u32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = _k32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p)
        finally:
            _k32.GlobalUnlock(h)
    finally:
        _u32.CloseClipboard()


def _write(fmt: int, data: bytes) -> bool:
    h = _k32.GlobalAlloc(GMEM_MOVEABLE, len(data) + 2)
    if not h:
        return False
    p = _k32.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    _k32.GlobalUnlock(h)
    return bool(_u32.SetClipboardData(fmt, h))


def set_clipboard_image(img, allow_overwrite: bool = False) -> Tuple[bool, str]:
    """Place `img` (PIL) on the clipboard as a DIB. Without `allow_overwrite` only when that cannot destroy anything the user put there; the
    caller sets it ONLY when the user said the clipboard may be overwritten (the plain text is still put back by restore_clipboard)."""
    fmts, why = clipboard_formats()
    if fmts is None:
        return False, why
    if fmts and not set(fmts) <= _SAFE_PLAIN and not allow_overwrite:
        return False, f"the clipboard holds the user's non-text data (formats {fmts[:6]}): not overwritten"
    saved = _read_text() if fmts else None
    rgb = img.convert("RGB")
    w, h = rgb.size
    raw = rgb.tobytes("raw", "BGR", (w * 3 + 3) & ~3, -1)                        # bottom-up, rows padded to 4 bytes
    header = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(raw), 2835, 2835, 0, 0)
    if not _open():
        return False, "clipboard busy"
    try:
        _u32.EmptyClipboard()
        ok = _write(CF_DIB, header + raw)
    finally:
        _u32.CloseClipboard()
    set_clipboard_image.saved_text = saved
    return ok, "image on the clipboard" if ok else "SetClipboardData failed"


def restore_clipboard() -> None:
    """Put back the plain text that was there (or leave the clipboard empty when it was empty)."""
    saved = getattr(set_clipboard_image, "saved_text", None)
    if not _open():
        return
    try:
        _u32.EmptyClipboard()
        if saved:
            _write(CF_UNICODETEXT, (saved + "\x00").encode("utf-16-le"))
    finally:
        _u32.CloseClipboard()


def render_shape(shape: str = "rectangle", size: Tuple[int, int] = (240, 150), color: Tuple[int, int, int] = (220, 30, 30), width: int = 8):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(img)
    box = (width, width, size[0] - width, size[1] - width)
    if shape == "ellipse":
        d.ellipse(box, outline=color, width=width)
    elif shape == "line":
        d.line((width, size[1] - width, size[0] - width, width), fill=color, width=width)
    else:
        d.rectangle(box, outline=color, width=width)
    return img


def render_drawing(spec: Dict[str, Any]):
    """ANY drawing, from data: {'size': (w, h), 'background': (r, g, b), 'items': [primitive, ...]} with primitives
         {'type': 'line' | 'polyline' | 'polygon', 'points': [(x, y), ...], 'color': (r, g, b), 'width': n, 'fill': (r, g, b) | None}
         {'type': 'rectangle' | 'ellipse' | 'rounded_rectangle', 'box': (x0, y0, x1, y1), 'color': ..., 'width': n, 'fill': ...}
         {'type': 'arc' | 'pieslice', 'box': ..., 'start': deg, 'end': deg, ...}
         {'type': 'text', 'xy': (x, y), 'text': '...', 'color': ..., 'size': n}
         {'type': 'image', 'path': 'file.png', 'xy': (x, y)}            (any picture is just another primitive)
       Nothing here knows what is being drawn: a house, a chart, a signature, a logo is a list of primitives."""
    from PIL import Image, ImageDraw, ImageFont
    w, h = spec.get("size", (400, 300))
    img = Image.new("RGB", (int(w), int(h)), tuple(spec.get("background", (255, 255, 255))))
    d = ImageDraw.Draw(img)
    for it in spec.get("items", []):
        t = it.get("type", "")
        col = tuple(it.get("color", (0, 0, 0)))
        wd = int(it.get("width", 3))
        fill = tuple(it["fill"]) if it.get("fill") else None
        if t in ("line", "polyline"):
            d.line([tuple(p) for p in it["points"]], fill=col, width=wd, joint="curve")
        elif t == "polygon":
            d.polygon([tuple(p) for p in it["points"]], outline=col, fill=fill, width=wd)
        elif t == "rectangle":
            d.rectangle(tuple(it["box"]), outline=col, fill=fill, width=wd)
        elif t == "rounded_rectangle":
            d.rounded_rectangle(tuple(it["box"]), radius=int(it.get("radius", 12)), outline=col, fill=fill, width=wd)
        elif t == "ellipse":
            d.ellipse(tuple(it["box"]), outline=col, fill=fill, width=wd)
        elif t == "arc":
            d.arc(tuple(it["box"]), it.get("start", 0), it.get("end", 180), fill=col, width=wd)
        elif t == "pieslice":
            d.pieslice(tuple(it["box"]), it.get("start", 0), it.get("end", 90), outline=col, fill=fill, width=wd)
        elif t == "text":
            try:
                font = ImageFont.truetype("arial.ttf", int(it.get("size", 20)))
            except Exception:  # noqa: BLE001
                font = ImageFont.load_default()
            d.text(tuple(it["xy"]), it.get("text", ""), fill=col, font=font)
        elif t == "image":
            pic = Image.open(it["path"]).convert("RGB")
            img.paste(pic, tuple(it.get("xy", (0, 0))))
    return img


def draw(app: str, drawing, save_as: str, *, allow_clipboard_overwrite: bool = False, max_steps: int = 8) -> Dict[str, Any]:
    """Draw ANYTHING in `app`'s canvas and save it, headless: `drawing` is a spec dict (render_drawing), a PIL image, or a file path.
    render -> clipboard -> the app's own Paste (through the loop / actuation backbone) -> save -> the caller verifies from the file."""
    from core_organs import desktop_grounding as dg
    from PIL import Image
    if isinstance(drawing, dict):
        img = render_drawing(drawing)
    elif isinstance(drawing, str):
        img = Image.open(drawing)
    else:
        img = drawing
    ok, note = set_clipboard_image(img, allow_overwrite=allow_clipboard_overwrite)
    if not ok:
        return {"completed": False, "reason": note}
    try:
        r = dg.operate_app(app, ["paste the image from the clipboard", f"save the document as {save_as}"],
                           expect_map={0: {"region_changed": True}, 1: {"file_created": save_as}}, max_steps_per_goal=max_steps)
    finally:
        restore_clipboard()
    r["image_size"] = img.size
    return r


def shape_pixels(path: str, color: Tuple[int, int, int] = (220, 30, 30), tol: int = 40) -> Dict[str, Any]:
    """Independent proof from the SAVED FILE: how many pixels are the shape's colour, and where they are."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    px = im.load()
    w, h = im.size
    hits = [(x, y) for y in range(0, h, 2) for x in range(0, w, 2) if all(abs(px[x, y][i] - color[i]) <= tol for i in range(3))]
    return {"size": (w, h), "shape_pixels": len(hits), "bbox": (min(p[0] for p in hits), min(p[1] for p in hits), max(p[0] for p in hits), max(p[1] for p in hits)) if hits else None}
