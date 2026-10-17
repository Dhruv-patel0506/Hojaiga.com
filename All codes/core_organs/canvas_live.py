"""
canvas_live -- canvas_artist's plans executed on an OWNED, parked MS Paint, with the quality checks measured on the real pixels and a contact sheet per stage.

`LivePainter` has the same interface as canvas_artist.FakePainter (grab / canvas / select / stroke) plus `colour`, `brush`, `size` helpers that drive Paint's own controls through UI Automation. Strokes go through the
virtual pointer: on a parked WinUI window it uses a synthetic touch on a hidden helper window (MEASURED: it draws; posted mouse messages are ignored by this canvas). Tool / colour / brush / size choices are UIA
pattern calls on the named controls. Every UIA action can be reported to a `hook` (pre picture, post picture, control name and box) so that it becomes a training pair.
"""
from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from core_organs import canvas_artist as CA

PaintHook = Callable[[Dict[str, Any]], None]


class LivePainter:
    def __init__(self, session: Any, hook: Optional[PaintHook] = None, speed_px_s: float = 500.0):
        self.s = session
        self.hook = hook
        self.speed = speed_px_s
        self.origin: Tuple[int, int] = (0, 0)
        self.strokes_done = 0
        self.stroke_seconds = 0.0
        self.log: List[Dict[str, Any]] = []
        self.fails: List[Dict[str, Any]] = []
        self.waited_s = 0.0

    # ---------------------------------------------------------------- eyes
    def grab(self):
        img, origin = self.s.app.grab(popups=True)
        if img is None:
            raise RuntimeError("no picture of Paint")
        self.origin = origin
        return img

    def canvas(self) -> CA.Box:
        return CA.find_canvas(self.grab())

    def _controls(self) -> List[Dict[str, Any]]:
        img = self.grab()
        return self.s.app.controls(self.origin, img.size)

    def has(self, name: str) -> bool:
        return any(c["name"].lower() == name.lower() for c in self._controls())

    # ---------------------------------------------------------------- UIA actions (each one can become a training pair)
    def press(self, name: str, kind: str = "select", exact: bool = True, wait: float = 0.5) -> bool:
        """Operate the control called `name` through its UIA pattern. Reports (pre, post, control, controls) to the hook."""
        pre = self.grab()
        controls = self.s.app.controls(self.origin, pre.size)
        hit = [c for c in controls if (c["name"].lower() == name.lower() if exact else name.lower() in c["name"].lower())]
        if not hit:
            self.log.append({"kind": kind, "name": name, "ok": False, "why": "control not found"})
            return False
        c = hit[0]
        how = self.s.app.act(c["ctl"])
        self.s._repark()
        time.sleep(wait)
        post = self.grab()
        ok = bool(how)
        self.log.append({"kind": kind, "name": c["name"], "ok": ok, "how": how})
        if self.hook is not None and ok:
            self.hook({"kind": kind, "name": c["name"], "type": c["type"], "box": c["box"], "pre": pre, "post": post, "controls": controls, "origin": self.origin})
        return ok

    def ensure_toolbar(self) -> bool:
        """Paint starts in compact mode when the person last hid the toolbar: show it (idempotent: if the ribbon is there already nothing is pressed)."""
        if self.has("Pencil"):
            return True
        return self.press("Show toolbar", "reveal", wait=1.5) and self.has("Pencil")

    def close_toolbar(self) -> bool:
        """MEASURED: Paint's toolbar opened with 'Show toolbar' is a flyout over the top of the canvas and closes itself on the first stroke. It is closed on purpose before the 'before' picture is taken, so that
        the picture and the drawing are taken with the same layout (otherwise the flyout disappearing counts as pixels that changed)."""
        if self.has("Hide toolbar"):
            return self.press("Hide toolbar", "reveal", wait=1.0)
        return True

    def select(self, name: str) -> bool:
        """Select a tool / swatch / option by name, opening the toolbar if the control is not on screen and closing it again afterwards."""
        opened = False
        if not self.has(name):
            opened = self.press("Show toolbar", "reveal", wait=1.5)
        ok = self.press(name, "tool")
        if opened:
            self.close_toolbar()
        return ok

    def _find(self, name: str, kinds: Tuple[str, ...], max_nodes: int = 2200) -> Any:
        """The UIA control called `name` of one of `kinds`, by a capped walk of the whole window (the colour overlay's edit boxes and the sliders are not in `controls()`, which lists clickable things only)."""
        import uiautomation as auto
        n = 0
        for c, _d in auto.WalkControl(auto.ControlFromHandle(self.s.app.hwnd), maxDepth=14):
            n += 1
            if n > max_nodes:
                break
            try:
                if c.ControlTypeName in kinds and (c.Name or "").strip().lower() == name.lower():
                    return c
            except Exception:
                continue
        return None

    def _value(self, name: str, value: str, kind: str = "colour") -> bool:
        """Set an edit box / slider through its UIA value pattern (reported to the hook like any other action)."""
        pre = self.grab()
        controls = self.s.app.controls(self.origin, pre.size)
        ctl = self._find(name, ("EditControl", "SliderControl", "SpinnerControl"))
        if ctl is None:
            self.log.append({"kind": kind, "name": name, "ok": False, "why": "control not found"})
            return False
        try:
            if ctl.ControlTypeName == "SliderControl":
                ctl.GetRangeValuePattern().SetValue(float(value))
            else:
                ctl.GetValuePattern().SetValue(str(value))
            r = ctl.BoundingRectangle
            box = (r.left - self.origin[0], r.top - self.origin[1], r.width(), r.height())
        except Exception as e:
            self.log.append({"kind": kind, "name": name, "ok": False, "why": str(e)[:80]})
            return False
        time.sleep(0.3)
        post = self.grab()
        self.log.append({"kind": kind, "name": name, "ok": True, "value": value})
        if self.hook is not None:
            self.hook({"kind": kind, "name": name, "type": ctl.ControlTypeName, "box": box, "pre": pre, "post": post, "controls": controls, "origin": self.origin, "value": value})
        return True

    def _invoke(self, name: str, kind: str = "dialog", kinds: Tuple[str, ...] = ("ButtonControl",)) -> bool:
        """Operate a control found by the capped whole-window walk (for buttons `controls()` leaves out, e.g. the colour overlay's OK)."""
        pre = self.grab()
        ctl = self._find(name, kinds)
        if ctl is None:
            self.log.append({"kind": kind, "name": name, "ok": False, "why": "control not found"})
            return False
        how = self.s.app.act(ctl)
        self.s._repark()
        time.sleep(0.8)
        self.log.append({"kind": kind, "name": name, "ok": bool(how), "how": how})
        return bool(how)

    def tap(self, x: float, y: float, patience_s: float = 60.0) -> bool:
        """A touch tap at picture pixel (x, y): the route that works on a parked WinUI window (used for the one control UIA does not expose, the overlay's OK)."""
        from core_organs.professor.pointer import s_click
        return self._deliver(s_click(self.origin[0] + x, self.origin[1] + y), 1, patience_s)

    def _accent_button(self, region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Tuple[int, int]]:
        """Centre of the widest flat, saturated button in the lower part of the overlay (the default / accent-coloured OK), found from the pixels."""
        import cv2
        img = np.array(self.grab().convert("RGB"))
        H, W = img.shape[:2]
        x0, y0, x1, y1 = region or (0, int(H * 0.8), W, H)
        sub = img[y0:y1, x0:x1].astype(int)
        mx, mn = sub.max(axis=2), sub.min(axis=2)
        mask = ((mx - mn) > 90).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        n, lab, st, cen = cv2.connectedComponentsWithStats(mask)
        best = None
        for i in range(1, n):
            w, h, area = st[i, 2], st[i, 3], st[i, 4]
            if w >= 80 and 18 <= h <= 90 and area > 0.6 * w * h and (best is None or area > best[0]):
                best = (area, int(x0 + cen[i][0]), int(y0 + cen[i][1]))
        return None if best is None else (best[1], best[2])

    def _confirm(self) -> bool:
        """Confirm the colour overlay. MEASURED: its OK is not in the UIA tree and posted keys are ignored, so the accent-coloured button is found on the picture and tapped."""
        pt = self._accent_button()
        if pt is None:
            self.log.append({"kind": "dialog", "name": "OK", "ok": False, "why": "no accent button on the picture"})
            return False
        self.tap(*pt)
        self.s._repark()
        time.sleep(1.0)
        ok = self._find("RGB hex", ("EditControl",), 1500) is None
        self.log.append({"kind": "dialog", "name": "OK", "ok": ok, "how": "tap", "at": pt})
        return ok

    def set_colour(self, rgb: Tuple[int, int, int]) -> bool:
        """Exact colour: Edit colours -> 'RGB hex' -> 'Add colour' (MEASURED structure of Paint's in-window colour overlay). Colour 1 becomes the new custom colour."""
        r, g, b = [max(0, min(255, int(v))) for v in rgb]
        opened = False
        if not self.has("Edit colours"):
            opened = self.press("Show toolbar", "reveal", wait=1.5)
        ok = self.press("Edit colours", "dialog", wait=1.5)
        if ok:
            ok = self._value("RGB hex", "#%02X%02X%02X" % (r, g, b))
            time.sleep(0.4)
            ok = ok and self.press("Add colour", "dialog", wait=1.0)
            ok = ok and self._confirm()                              # MEASURED: the overlay stays open after 'Add colour'; its OK button is not in the UIA tree, so Enter confirms it
        if opened:
            self.close_toolbar()
        return ok

    def set_size(self, value: float) -> bool:
        """Brush size through the 'Size' slider's range pattern (opened with the Size button when it is a flyout)."""
        if not self.has("Size"):
            self.press("Show toolbar", "reveal", wait=1.2)
        if self._find("Size", ("SliderControl",)) is None:
            self.press("Size", "flyout", wait=1.0)
        return self._value("Size", str(value), kind="size")

    def set_opacity(self, frac: float) -> bool:
        """Opacity as a fraction of the slider's own range (read from its range pattern, not assumed)."""
        ctl = self._find("Opacity", ("SliderControl",))
        if ctl is None:
            return False
        try:
            rv = ctl.GetRangeValuePattern()
            lo, hi = float(rv.Minimum), float(rv.Maximum)
        except Exception:
            lo, hi = 0.0, 100.0
        return self._value("Opacity", str(lo + (hi - lo) * max(0.0, min(1.0, frac))), kind="opacity")

    # what Paint's own brush-type chooser would add is not reachable through UIA on this build (MEASURED: 'Brushes' is a tool radio, the type list never appeared as controls); the CLASS of effect the plan asks for
    # is therefore produced with the controls that ARE reachable: the tool (Pencil / Brushes), the Size slider and the Opacity slider.
    OPACITY_FOR = {"Marker": 1.0, "Watercolour": 0.55, "Oil": 0.8, "Pencil": 1.0}

    def set_brush(self, name: str, size: int) -> bool:
        ok = self.select("Pencil" if name == "Pencil" else "Brushes")
        ok = self.set_size(size) and ok
        self.set_opacity(self.OPACITY_FOR.get(name, 1.0))
        return ok

    def fill_at(self, x: float, y: float, tries: int = 2) -> bool:
        """The Fill bucket tapped at picture pixel (x, y), with the touch route (the one that reaches this canvas). VERIFIED: the pixel under the tap must change; if it did not (the tap was lost, the tool was
        not the bucket) the tool is chosen again and the tap repeated, `tries` times. False = the region is still unfilled (the caller falls back to clipped strokes)."""
        def px() -> Any:
            img = np.asarray(self.grab().convert("RGB")).astype(int)
            xi, yi = int(round(x)), int(round(y))
            return img[max(yi - 1, 0):yi + 2, max(xi - 1, 0):xi + 2].reshape(-1, 3).mean(axis=0)
        for _ in range(tries):
            before = px()
            if not (self.select("Fill") and self.tap(x, y)):
                continue
            time.sleep(0.8)
            if float(np.abs(px() - before).sum()) > 30:
                return True
        return False

    # ---------------------------------------------------------------- hands
    def _deliver(self, script: Any, n_strokes: int, patience_s: float) -> bool:
        """One delivery through the pointer. The touch route refuses while the person is using the mouse / keyboard, or when another window covers the gesture's start: both are respected, not bypassed --
        the delivery waits for the person to be idle (>= 1.2 s) / for the cover to go, and is retried up to `patience_s`."""
        from core_organs import background_window as bw
        t_start = time.time()
        while True:
            t0 = time.time()
            ptr = self.s.eff.pointer()
            ptr.only = ("touch",)                                   # MEASURED on this canvas: posted messages are ignored; touch draws. Without a pixel check per stroke the ladder would accept the first route that merely 'delivers'
            r = ptr.perform(script, "stroke", verify=lambda: None)
            self.stroke_seconds += time.time() - t0
            ok = bool(getattr(r, "ok", r))
            why = str(getattr(r, "why", "") or getattr(r, "note", "") or " ".join(getattr(r, "tried", []) or []))
            if ok:
                self.strokes_done += n_strokes
                return True
            if ("using the mouse" in why or "another window is on top" in why) and time.time() - t_start < patience_s:
                t_w = time.time()
                while time.time() - t_w < 6.0 and bw.user_idle_ms() < 1200:
                    time.sleep(0.4)
                time.sleep(0.5)
                self.waited_s += time.time() - t_w
                continue
            self.fails.append({"strokes": n_strokes, "route": getattr(r, "route", ""), "why": why[:140]})
            return False

    def stroke(self, points: Sequence[CA.Pt], width: int = 0, patience_s: float = 120.0) -> bool:
        return bool(self.stroke_batch([points], patience_s))

    def stroke_batch(self, batch: Sequence[Sequence[CA.Pt]], patience_s: float = 120.0) -> int:
        """Several strokes in ONE delivery: [move, press, follow..., release] per stroke, concatenated, so the ghost window, the idle check and the cover check happen once. Returns how many were delivered
        (all or none; a failed batch is retried stroke by stroke so one bad stroke does not lose the rest)."""
        from core_organs.professor.pointer import s_drag
        script: List[Any] = []
        n = 0
        for pts in batch:
            sp = [(self.origin[0] + x, self.origin[1] + y) for x, y in pts]
            if len(sp) < 2:
                continue
            dur = max(0.25, min(3.0, CA.path_length(sp) / self.speed))
            script += s_drag(sp, "left", (), dur, press_dwell=0.04, end_dwell=0.04)
            n += 1
        if not script:
            return 0
        if self._deliver(script, n, patience_s):
            return n
        if len(batch) > 1:                                          # isolate the failure
            return sum(self.stroke_batch([b], patience_s) for b in batch)
        return 0


# ------------------------------------------------------------------------------------------------------------------------------------ contact sheets
def contact_sheet(before: Any, after: Any, canvas: CA.Box, strokes: Sequence[CA.Stroke], path: str, title: str, reference: Any = None) -> str:
    """[reference] | the plan over the empty canvas | what Paint actually drew. Saved as one picture."""
    import cv2
    from PIL import Image
    x0, y0, x1, y1 = [int(v) for v in canvas]
    a = np.asarray(before.convert("RGB"))[y0:y1 + 1, x0:x1 + 1].copy()
    plan = CA.raster(strokes, (before.size[0], before.size[1]), 2)[y0:y1 + 1, x0:x1 + 1]
    a[plan > 0] = (220, 40, 40)
    b = np.asarray(after.convert("RGB"))[y0:y1 + 1, x0:x1 + 1].copy()
    panels = [a, b]
    if reference is not None:
        ref = np.asarray(reference.convert("RGB")) if hasattr(reference, "convert") else cv2.cvtColor(reference, cv2.COLOR_BGR2RGB)
        f = a.shape[0] / ref.shape[0]
        panels.insert(0, cv2.resize(ref, (max(1, int(ref.shape[1] * f)), a.shape[0])))
    h = max(p.shape[0] for p in panels)
    w = sum(p.shape[1] for p in panels) + 12 * (len(panels) - 1)
    sheet = np.full((h + 28, w, 3), 235, np.uint8)
    x = 0
    for p in panels:
        sheet[28:28 + p.shape[0], x:x + p.shape[1]] = p
        x += p.shape[1] + 12
    label = "reference | plan | drawn" if reference is not None else "plan | drawn"
    cv2.putText(sheet, f"{title}  |  {label}", (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1, cv2.LINE_AA)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(sheet).save(path, quality=88)
    return path
