"""
popup_visual.py -- answer a popup that exposes NOTHING (P2-M)

A custom-drawn dialog, an owner-less child surface, a splash with painted buttons: no UIA tree, no Win32 child controls, so the tiers that
read buttons find none. This module reads such a window THE WAY A PERSON DOES - with the DAP perception pipeline (PrintWindow capture ->
OCR with word boxes) - and hands popup_policy the same neutral description it gets from any other dialog: the words (so an elevation /
credential / destructive prompt is still recognised and escalated, never answered) and the buttons (so the unchanged role policy picks the
safe one). Pressing a visual button is a POSTED click to the dialog's own window at the word's box: no pointer, no keyboard, no focus.

Nothing here knows an app, a title or a button caption in advance: roles come from popup_policy's lexicon (data), phrases from the screen.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from core_organs import headless_input as hin

logger = logging.getLogger("hojaiga.popup_visual")


class _Rect:
    def __init__(self, l: int, t: int, r: int, b: int):
        self.left, self.top, self.right, self.bottom = l, t, r, b


class VisualButton:
    """A button found by OCR, shaped like the UIA control popup_policy handles. Its press is a posted click at the word's box centre."""
    native = False
    via = "ocr-click"

    def __init__(self, hwnd: int, caption: str, box: Tuple[int, int, int, int]):
        self.hwnd, self.Name, self.AutomationId, self.NativeWindowHandle = hwnd, caption, "", hwnd
        self._box = box

    @property
    def BoundingRectangle(self):
        return _Rect(*self._box)

    def GetInvokePattern(self):
        return self

    def Invoke(self):
        l, t, r, b = self._box
        ok, note = hin.post_click(self.hwnd, (l + r) // 2, (t + b) // 2)
        if not ok and not hin.is_alive(self.hwnd):
            ok = True               # a dialog that closes on the button DOWN has no window left for the matching button-up: that is an answer
        if not ok:
            raise RuntimeError(note)


def _lines(words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group OCR words into phrases: same line, neighbours closer than about a character and a half of the text height."""
    out: List[Dict[str, Any]] = []
    for w in sorted(words, key=lambda w: (w["block"], w["line"], w["left"])):
        h = max(1, w["bottom"] - w["top"])
        cur = out[-1] if out else None
        if cur and cur["block"] == w["block"] and cur["line"] == w["line"] and w["left"] - cur["right"] <= 1.6 * h:
            cur["text"] += " " + w["text"]
            cur["right"], cur["top"], cur["bottom"] = w["right"], min(cur["top"], w["top"]), max(cur["bottom"], w["bottom"])
        else:
            out.append({"text": w["text"], "block": w["block"], "line": w["line"], "left": w["left"], "right": w["right"],
                        "top": w["top"], "bottom": w["bottom"]})
    return out


def read(hwnd: int) -> Dict[str, Any]:
    """OCR the window through the DAP perception pipeline. {'ok', 'lines': [...], 'why'}; never raises."""
    try:
        from core_organs import organ_24_dap as dap
        prov = dap.Win32Provider()
        node = prov.build_node(hwnd, None)
        pipe_cap = dap.CaptureEngine()
        ocr = dap.OCREngine()
        if not ocr.available:
            return {"ok": False, "lines": [], "why": "OCR backend (pytesseract) not installed"}
        words = ocr.words(node, pipe_cap)
        return {"ok": True, "lines": _lines(words), "words": len(words), "why": ""}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "lines": [], "why": f"{type(exc).__name__}: {str(exc)[:120]}"}


def describe(hwnd: int, role_words: Dict[str, Tuple[str, ...]]) -> Tuple[List[str], List[Tuple[str, str, object]], Dict[str, Any]]:
    """(texts, buttons, report): `buttons` use popup_policy's (name, automation_id, control) triple. A phrase is a BUTTON when its words are
    a known role word (ok / cancel / not now / later ...) or it is a short line (<= 3 words) sitting in the lower half of the window; every
    other phrase is message text."""
    rd = read(hwnd)
    rep = {"ocr": rd.get("ok"), "lines": len(rd.get("lines", [])), "why": rd.get("why", "")}
    if not rd.get("ok"):
        return [], [], rep
    r = hin.wt.RECT()
    hin._u32.GetWindowRect(hwnd, hin.ctypes.byref(r))
    mid = (r.top + r.bottom) // 2
    known = {w for ws in role_words.values() for w in ws}
    texts: List[str] = []
    buttons: List[Tuple[str, str, object]] = []
    for ln in rd["lines"]:
        t = re.sub(r"[^\w' ]+", "", ln["text"]).strip().lower()
        if not t:
            continue
        short_low = len(t.split()) <= 3 and ln["top"] >= mid
        if t in known or short_low:
            buttons.append((ln["text"].strip(), "", VisualButton(hwnd, ln["text"].strip(), (ln["left"], ln["top"], ln["right"], ln["bottom"]))))
        else:
            texts.append(ln["text"].strip())
    rep["buttons"] = [b[0] for b in buttons]
    return texts, buttons, rep
