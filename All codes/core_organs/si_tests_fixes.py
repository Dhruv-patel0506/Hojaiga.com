"""
si_tests_fixes.py -- suite tests for the A-G fix brief (loop-first routing, off-screen capture, headless drag,
any-app discovery, unified popup engine, honest vision timing). Same pattern as si_tests_extra.py /
si_tests_behavior.py: each function receives the suite's TestOutcome dataclass and returns it with MEASURED
evidence. Live tests only touch windows they launched themselves and close only those.
"""

import ctypes
import uuid
import ctypes.wintypes as wt
import os
import time
from typing import Any, Dict, List, Tuple

os.environ.setdefault("HOJAIGA_WEBAPP_WATCH", "0")

_u32 = ctypes.windll.user32


def _pointer() -> Tuple[int, int]:
    p = wt.POINT()
    _u32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


class _PointerWatch:
    """The physical-pointer assertion, made honest about a human using the mouse while the suite runs.

    ENFORCING evidence: the input GUARD. Every physical-input API (SetCursorPos / mouse_event / keybd_event / SendInput /
    pyautogui) is patched to refuse and record in VIOLATIONS, so ``violations == 0`` means this code never reached for the
    pointer. The cursor position is ALSO watched at 10 ms resolution for the whole test: a person moving a mouse draws a
    smooth path (small steps between samples), whereas a synthetic SetCursorPos/mouse_event is a teleport (one big jump).
    The check fails on any violation and on any teleport; a smooth path is reported as 'the user's own hand'."""

    TELEPORT_PX = 400

    def __init__(self):
        import threading
        from core_organs import headless_input as hin
        self._hin = hin
        self.p0 = _pointer()
        self.v0 = len(hin.VIOLATIONS)
        self.max_jump = 0
        self._stop = threading.Event()
        self._last = self.p0

        def _sample():
            while not self._stop.is_set():
                p = _pointer()
                self.max_jump = max(self.max_jump, abs(p[0] - self._last[0]) + abs(p[1] - self._last[1]))
                self._last = p
                self._stop.wait(0.01)
        self._t = threading.Thread(target=_sample, daemon=True, name="pointer-watch")
        self._t.start()

    def check(self) -> Tuple[str, bool, str]:
        self._stop.set()
        self._t.join(timeout=1)
        p1 = _pointer()
        dv = len(self._hin.VIOLATIONS) - self.v0
        moved = p1 != self.p0
        teleported = self.max_jump >= self.TELEPORT_PX
        detail = f"pointer {self.p0}->{p1}, guard violations+={dv}, largest 10 ms step={self.max_jump}px"
        if moved and not teleported and dv == 0:
            detail += " (a smooth path = the user's own hand; the guard saw 0 physical-input calls)"
        return ("physical-pointer-untouched-and-no-guard-violations", dv == 0 and not teleported, detail)


def _top_hwnds() -> set:
    out = set()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if _u32.IsWindowVisible(h):
            out.add(int(h))
        return True
    _u32.EnumWindows(cb, 0)
    return out


def _close_new_windows(before: set, title_hint: str = "") -> int:
    """Close ONLY windows that appeared after `before` was taken (never an existing/user window)."""
    from core_organs import universal_scan as us
    closed = 0
    for h in sorted(_top_hwnds() - before):
        try:
            from core_organs import headless_input as _hin
            if title_hint and title_hint.lower() not in _hin.safe_window_text(h).lower():
                continue
            if us.close_window(h, timeout_s=4.0, discard_unsaved=True):
                closed += 1
        except Exception:
            pass
    return closed


def _fmt(checks, width: int = 170) -> str:
    """Evidence line: every check with its MEASURED detail (passes too - a bare OK proves nothing)."""
    return "; ".join(f"{n}={'OK' if ok else 'FAIL'}({d[:width]})" for n, ok, d in checks)


# ----------------------------------------------------------------------------------------------- Fix A

def run_lf1(TestOutcome):
    """LF1: the product routes detected desktop apps through the verified loop IN ORDER, stops at a human gate, and is switchable"""
    from core_organs import loop_first as lf
    from core_organs.organ_01_crewai_engine import _compile_task_with_organ36

    checks: List[Tuple[str, bool, str]] = []
    saved = os.environ.get("HOJAIGA_LOOP_FIRST")
    try:
        os.environ.pop("HOJAIGA_LOOP_FIRST", None)
        default_on = lf.loop_first_enabled()
        os.environ["HOJAIGA_LOOP_FIRST"] = "0"
        off = lf.loop_first_enabled()
        calls_off: List[str] = []
        r_off = lf.run_loop_first("open notepad and type hi", [("notepad", 5)],
                                  operate=lambda app, goals, **k: calls_off.append(app) or {},
                                  prepare=lambda app, **k: calls_off.append(app) or {})
        checks.append(("flag-default-on-and-0-disables", default_on and not off and not r_off.ran and not calls_off,
                       f"default_on={default_on} off={off} ran_when_off={r_off.ran} calls={calls_off}"))
    finally:
        if saved is None:
            os.environ.pop("HOJAIGA_LOOP_FIRST", None)
        else:
            os.environ["HOJAIGA_LOOP_FIRST"] = saved

    cmd = "open notepad and type hello world, then open calculator and compute 7 * 8"
    comp = _compile_task_with_organ36(cmd)
    spans = comp.get("app_spans") or []
    plans = lf.plan_app_goals(cmd, spans)
    by = {p.app: p for p in plans}
    ok_plan = ([p.app for p in plans] == ["notepad", "calculator"]
               and by["notepad"].goals == ['type "hello world"']
               and by["calculator"].goals == ["press Seven", "press Multiply by", "press Eight", "press Equals"]
               and by["calculator"].expect_map.get(3) == {"name_visible": "56"})
    checks.append(("compiler-positions-drive-per-app-goals", ok_plan,
                   f"spans={spans} -> " + " | ".join(f"{p.app}:{p.goals}" for p in plans)))

    save_cmd = "type notes in notepad then save as C:\\tmp\\lf1.txt"
    sp = lf.plan_app_goals(save_cmd, [("notepad", save_cmd.find("notepad"))])
    sv = sp[0]
    checks.append(("save-path-gets-file-postcondition",
                   len(sv.goals) == 2 and sv.expect_map == {1: {"file_created": "C:\\tmp\\lf1.txt"}},
                   f"goals={sv.goals} expect={sv.expect_map}"))
    draw_cmd = "draw a circle in paint then type done in notepad"
    dr = lf.plan_app_goals(draw_cmd, [("paint", draw_cmd.find("paint")), ("notepad", draw_cmd.find("notepad"))])
    checks.append(("canvas-drawing-is-delegated-not-faked", dr[0].goals == [] and dr[0].delegated == ["draw a circle"]
                   and dr[1].goals == ['type "done"'], f"paint={dr[0].delegated} notepad={dr[1].goals}"))

    # sequencing with a recording stand-in for operate_app (the live path is LF2)
    order: List[Tuple[str, List[str], Any]] = []

    def fake_ok(app, goals, **k):
        order.append((app, list(goals), k.get("expect_map")))
        return {"completed": True, "steps": len(goals), "hwnd": 1000 + len(order),
                "trace": [{"goal": g, "verdict": "PASS", "verb": "click", "element": "x"} for g in goals]}
    r = lf.run_loop_first(cmd, spans, operate=fake_ok, prepare=lambda app, **k: {"ready": True, "hwnd": 7})
    checks.append(("sequence-in-compiled-order-with-persisted-handles",
                   [o[0] for o in order] == ["notepad", "calculator"] and r.all_completed
                   and lf.handle_for("notepad") == 1001 and lf.handle_for("calculator") == 1002
                   and order[1][2] == {3: {"name_visible": "56"}},
                   f"order={[o[0] for o in order]} handles=({lf.handle_for('notepad')},{lf.handle_for('calculator')}) "
                   f"expect2={order[1][2]}"))

    # a human gate in app 1 must stop app 2 and surface the capsule exactly once
    order.clear()
    notified: List[Tuple[str, str]] = []

    def fake_human(app, goals, **k):
        order.append((app, list(goals), None))
        return {"completed": False, "awaiting_human": True, "steps": 1, "hwnd": 555, "trace": []}
    r2 = lf.run_loop_first(cmd, spans, operate=fake_human, prepare=lambda app, **k: {"ready": True},
                           notify=lambda s, d: notified.append((s, d)))
    checks.append(("human-gate-stops-the-sequence",
                   r2.halted_for_human and [o[0] for o in order] == ["notepad"] and len(notified) == 1
                   and notified[0][0] == "input_needed" and len(r2.runs) == 1,
                   f"ran={[o[0] for o in order]} notified={notified}"))

    # the product entry point itself: a human gate must come back as NEEDS_INPUT and the 7B crew must never be built
    import core_organs.organ_01_crewai_engine as o1
    real_pre, real_avail, real_agent = o1._loop_first_preamble, o1.CrewAIEngine.is_available, o1.Agent
    crew_built: List[bool] = []
    try:
        # execute_task starts the 60 fps visual-cursor overlay; a test must not leave that thread spinning behind it
        import core_organs.visual_cursor as vcm
        real_get_cursor = vcm.get_cursor
        vcm.get_cursor = lambda: type("_NoCursor", (), {"show": lambda s: None, "hide": lambda s: None,
                                                        "set_label": lambda s, *a, **k: None,
                                                        "fly_to": lambda s, *a, **k: None})()
        o1._loop_first_preamble = lambda command, compilation: (r2, r2.evidence_text())
        o1.CrewAIEngine.is_available = lambda self: True
        engine = o1.CrewAIEngine.__new__(o1.CrewAIEngine)
        o1.Agent = type("Agent", (), {"__init__": lambda self, *a, **k: crew_built.append(True)})
        out = engine.execute_task(cmd, "lf1-halt")
        checks.append(("execute_task-halts-with-NEEDS_INPUT-before-the-crew-exists",
                       out.get("status") == "NEEDS_INPUT" and not crew_built and out.get("attempts") == 0
                       and bool(out.get("loop_first", {}).get("halted_for_human")),
                       f"status={out.get('status')} crew_built={bool(crew_built)} attempts={out.get('attempts')}"))
        saved_env = os.environ.get("HOJAIGA_LOOP_FIRST")
        os.environ["HOJAIGA_LOOP_FIRST"] = "0"
        try:
            res_off, ev_off = real_pre(cmd, comp)
        finally:
            if saved_env is None:
                os.environ.pop("HOJAIGA_LOOP_FIRST", None)
            else:
                os.environ["HOJAIGA_LOOP_FIRST"] = saved_env
        checks.append(("flag-0-leaves-the-crew-path-untouched", res_off is None and ev_off == "", f"result={res_off} evidence={ev_off!r}"))
    finally:
        o1._loop_first_preamble, o1.CrewAIEngine.is_available, o1.Agent = real_pre, real_avail, real_agent
        try:
            vcm.get_cursor = real_get_cursor
        except NameError:
            pass

    ev = r.evidence_text()
    ev2 = r2.evidence_text()
    checks.append(("evidence-is-honest-about-weak-and-undone",
                   "DONE" in ev and "WEAK" in ev and "STOPPED" in ev2 and "NOT DONE" in lf.run_loop_first(
                       cmd, spans, operate=lambda a, g, **k: {"completed": False, "steps": 1, "trace": []},
                       prepare=lambda a, **k: {}).evidence_text(),
                   "weak calculator presses flagged; unrun goals marked NOT DONE; human stop stated"))
    passed = all(ok for _n, ok, _d in checks)
    return TestOutcome(passed=passed,
                       evidence=_fmt(checks)[:1600],
                       metrics={"checks": f"{sum(1 for _n, ok, _d in checks if ok)}/{len(checks)}"})


# ----------------------------------------------------------------------------------------------- Fix C

class CanvasWindow:
    """A REAL Win32 drawing window: paints a black polyline for every WM_MOUSEMOVE received while the left button
    is held, and logs every mouse message (time, message, wParam, client x/y) so ordering and pacing are provable.
    Used to prove post_drag against a canvas that does honour posted mouse messages."""

    def __init__(self, title: str = "HJ-DR1-Canvas", x: int = 420, y: int = 240, w: int = 520, h: int = 440):
        import threading
        self.title, self._x, self._y, self._w, self._h = title, x, y, w, h
        self.events: List[Tuple[float, int, int, int, int]] = []
        self.strokes: List[List[Tuple[int, int]]] = []
        self.hwnd = 0
        self._drawing = False
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="CanvasWindow")
        self._cls = f"HJCanvas_{int(time.time() * 1000) % 10_000_000}"

    def _wndproc(self, hwnd, msg, wparam, lparam):
        sup = self._sup
        if msg in (0x0200, 0x0201, 0x0202):
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            self.events.append((time.perf_counter(), msg, int(wparam), x, y))
            if msg == 0x0201:
                self._drawing = True
                self.strokes.append([(x, y)])
            elif msg == 0x0200 and self._drawing and (wparam & 0x1) and self.strokes:
                self.strokes[-1].append((x, y))
                sup.user32.InvalidateRect(hwnd, None, False)
            elif msg == 0x0202:
                self._drawing = False
                sup.user32.InvalidateRect(hwnd, None, False)
            return 0
        if msg == 0x000F:                                   # WM_PAINT
            ps = self._PAINTSTRUCT()
            hdc = sup.user32.BeginPaint(hwnd, ctypes.byref(ps))
            self._paint(hdc, hwnd)
            sup.user32.EndPaint(hwnd, ctypes.byref(ps))
            return 0
        if msg == 0x0318:                                   # WM_PRINTCLIENT (PrintWindow)
            self._paint(wparam, hwnd)
            return 0
        if msg == 0x0014:                                   # WM_ERASEBKGND: painted in WM_PAINT
            return 1
        if msg == sup.WM_DESTROY:
            sup.user32.PostQuitMessage(0)
            return 0
        return sup.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _paint(self, hdc, hwnd):
        sup = self._sup
        r = wt.RECT()
        sup.user32.GetClientRect(hwnd, ctypes.byref(r))
        gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        gdi.GetStockObject.restype = ctypes.c_void_p
        sup.user32.FillRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.RECT), ctypes.c_void_p]
        sup.user32.FillRect(hdc, ctypes.byref(r), gdi.GetStockObject(0))     # WHITE_BRUSH
        gdi.CreatePen.restype = ctypes.c_void_p
        gdi.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        gdi.MoveToEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        gdi.LineTo.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        pen = gdi.CreatePen(0, 3, 0x000000)
        old = gdi.SelectObject(hdc, pen)
        for st in list(self.strokes):
            if not st:
                continue
            gdi.MoveToEx(hdc, st[0][0], st[0][1], None)
            for px, py in st[1:]:
                gdi.LineTo(hdc, px, py)
        gdi.SelectObject(hdc, old)
        gdi.DeleteObject.argtypes = [ctypes.c_void_p]
        gdi.DeleteObject(pen)

    def _run(self):
        from core_organs import si_test_support as sup
        self._sup = sup

        class PAINTSTRUCT(ctypes.Structure):
            _fields_ = [("hdc", ctypes.c_void_p), ("fErase", wt.BOOL), ("rcPaint", wt.RECT), ("fRestore", wt.BOOL),
                        ("fIncUpdate", wt.BOOL), ("rgbReserved", ctypes.c_byte * 32)]
        self._PAINTSTRUCT = PAINTSTRUCT
        sup.user32.BeginPaint.argtypes = [wt.HWND, ctypes.POINTER(PAINTSTRUCT)]
        sup.user32.BeginPaint.restype = ctypes.c_void_p
        sup.user32.EndPaint.argtypes = [wt.HWND, ctypes.POINTER(PAINTSTRUCT)]
        sup.user32.InvalidateRect.argtypes = [wt.HWND, ctypes.c_void_p, wt.BOOL]
        sup.user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
        self._proc = sup.WNDPROC(self._wndproc)
        hinst = sup.kernel32.GetModuleHandleW(None)
        wc = sup._WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = self._cls
        sup.user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = sup.user32.CreateWindowExW(0, self._cls, self.title, sup.WS_OVERLAPPEDWINDOW | sup.WS_VISIBLE,
                                               self._x, self._y, self._w, self._h, None, None, hinst, None)
        self._ready.set()
        msg = wt.MSG()
        while sup.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            sup.user32.TranslateMessage(ctypes.byref(msg))
            sup.user32.DispatchMessageW(ctypes.byref(msg))

    def start(self) -> "CanvasWindow":
        self._thread.start()
        self._ready.wait(5)
        time.sleep(0.4)
        return self

    def client_origin(self) -> Tuple[int, int]:
        pt = wt.POINT(0, 0)
        _u32.ClientToScreen(self.hwnd, ctypes.byref(pt))
        return pt.x, pt.y

    def stop(self):
        if self.hwnd:
            _u32.PostMessageW(self.hwnd, 0x0010, 0, 0)
        self._thread.join(timeout=2)


def run_dr1(TestOutcome):
    """DR1: headless drag - ordered, time-sliced WM_MOUSEMOVE/LBUTTONDOWN/UP draws a circle on a real canvas; physical pointer untouched; an app that ignores posted mouse input is reported INEFFECTIVE, not success"""
    import math
    from core_organs import headless_input as hin
    from core_organs import visual_cursor as vc

    watch = _PointerWatch()
    checks: List[Tuple[str, bool, str]] = []
    metrics: Dict[str, Any] = {}
    cv = CanvasWindow().start()
    try:
        ox, oy = cv.client_origin()
        cx, cy, r = ox + 250, oy + 190, 110
        pts = hin.ellipse_points(cx, cy, r, r, 48)
        dur = 0.8
        base, why0 = hin.capture_window(cv.hwnd)
        t0 = time.perf_counter()
        ok, note = hin.post_drag(cv.hwnd, pts[0][0], pts[0][1], pts[-1][0], pts[-1][1], path=pts, duration_s=dur)
        took = time.perf_counter() - t0
        time.sleep(0.6)
        after, why1 = hin.capture_window(cv.hwnd)
        mouse_ev = [e for e in cv.events]
        kinds = [e[1] for e in mouse_ev]
        first_move_ok = bool(mouse_ev) and mouse_ev[0][1] == 0x0200 and mouse_ev[0][2] == 0
        down_i = kinds.index(0x0201) if 0x0201 in kinds else -1
        after_down = mouse_ev[down_i + 1:-1] if down_i >= 0 else []
        order_ok = (first_move_ok and down_i == 1 and kinds[-1] == 0x0202 and len(after_down) >= len(pts) - 2
                    and all(e[1] == 0x0200 and (e[2] & 0x1) for e in after_down))
        checks.append(("ordered-move-down-moves-up", order_ok and ok,
                       f"delivered={ok} events={len(mouse_ev)} sequence={[hex(k) for k in kinds[:3]]}...{hex(kinds[-1]) if kinds else None} "
                       f"moves_with_button={len(after_down)} (path has {len(pts)} points)"))
        t_moves = [e[0] for e in after_down]
        span = (t_moves[-1] - t_moves[0]) if len(t_moves) > 1 else 0.0
        gaps = [b - a for a, b in zip(t_moves, t_moves[1:])]
        slice_s = dur / (len(pts) - 1)
        checks.append(("time-sliced-not-a-burst", span >= 0.7 * dur and (max(gaps) if gaps else 9) <= max(0.25, 6 * slice_s),
                       f"moves spread over {span:.2f}s of the {dur:.2f}s budget, longest gap {max(gaps) * 1000 if gaps else -1:.0f} ms "
                       f"(slice {slice_s * 1000:.0f} ms); call took {took:.2f}s"))
        d0 = mouse_ev[down_i] if down_i >= 0 else None
        exp_x, exp_y = pts[0][0] - ox, pts[0][1] - oy
        checks.append(("client-relative-coordinates", d0 is not None and abs(d0[3] - exp_x) <= 2 and abs(d0[4] - exp_y) <= 2,
                       f"button-down at client ({d0[3] if d0 else None},{d0[4] if d0 else None}) expected ({exp_x},{exp_y})"))
        n, bbox = hin.changed_pixels(base, after)
        # geometry: hollow ring of the requested radius (independent of the fixture's own bookkeeping)
        geom_ok, geom = False, "no capture"
        if after is not None and base is not None and bbox:
            wb, hb = bbox[2] - bbox[0], bbox[3] - bbox[1]
            wx0, wy0 = _window_origin(cv.hwnd)
            cxp, cyp = cx - wx0, cy - wy0
            centre_clear = after.getpixel((cxp, cyp)) == base.getpixel((cxp, cyp))
            ring_hits = 0
            for k in range(0, 360, 15):
                px = int(round(cxp + r * math.cos(math.radians(k))))
                py = int(round(cyp + r * math.sin(math.radians(k))))
                near = any(sum(after.getpixel((qx, qy))[:3]) < 200 for qx in range(px - 3, px + 4) for qy in range(py - 3, py + 4))
                ring_hits += int(near)
            geom_ok = abs(wb - 2 * r) <= 10 and abs(hb - 2 * r) <= 10 and centre_clear and ring_hits >= 22
            geom = (f"{n} px changed, bbox {wb}x{hb} (expect ~{2 * r}x{2 * r}), centre untouched={centre_clear}, "
                    f"ring samples inked {ring_hits}/24")
        checks.append(("circle-really-drawn-ring-not-blob", geom_ok, geom))
        metrics.update(changed_pixels=n, move_events=len(after_down), span_s=round(span, 2))

        # the visual-cursor path that the crew's drawing tools use: same headless route, honest report
        c = vc.get_cursor()
        c.draw_shape("oval", ox + 250, oy + 190, width=300, height=140, steps=40, hwnd=cv.hwnd)
        ls = getattr(c, "last_stroke", {})
        checks.append(("visual-cursor-draw_shape-routes-through-post_drag",
                       bool(ls.get("delivered")) and ls.get("effective") is True and "postmessage-drag" in str(ls.get("note", "")),
                       f"last_stroke={ {k: ls.get(k) for k in ('delivered', 'effective', 'changed_pixels')} } note={str(ls.get('note'))[:80]}"))
        # no resolvable target window: the stroke is REFUSED (never a physical fallback)
        real_target = c._stroke_target
        c._stroke_target = lambda *a, **k: 0
        try:
            c.draw_shape("circle", 400, 400, width=40, height=40, steps=12, hwnd=None)
        finally:
            c._stroke_target = real_target
        refused = getattr(c, "last_stroke", {})
        checks.append(("no-resolvable-target-is-refused-not-physical",
                       refused.get("delivered") is False and "UNDELIVERABLE" in str(refused.get("note")),
                       f"note={str(refused.get('note'))[:100]}"))
    finally:
        cv.stop()

    # a REAL app that ignores posted mouse input: the report must say so (Win11 Paint is a WinUI canvas)
    paint_note = "paint: not attempted"
    try:
        from core_organs import universal_scan as us, background_window as bw
        before = _top_hwnds()
        info = us.launch_hidden("paint")
        ph = int(info.get("hwnd") or 0)
        if ph:
            try:
                with bw.BackgroundSession(ph) as sess:
                    time.sleep(1.5)
                    import uiautomation as auto
                    best = None
                    for el, _d in auto.WalkControl(auto.ControlFromHandle(ph), maxDepth=14):
                        try:
                            rr = el.BoundingRectangle
                            w, h = rr.right - rr.left, rr.bottom - rr.top
                            if w > 400 and h > 300 and el.ControlTypeName in ("PaneControl", "CustomControl", "ImageControl", "GroupControl"):
                                if best is None or w * h < best[0]:
                                    best = (w * h, (rr.left + rr.right) // 2, (rr.top + rr.bottom) // 2)
                        except Exception:
                            pass
                    if best:
                        cur = vc.get_cursor()
                        cur.draw_shape("circle", best[1], best[2], width=200, height=200, steps=40, hwnd=ph)
                        ls = getattr(cur, "last_stroke", {})
                        paint_note = (f"paint(parked,{sess.mode}): delivered={ls.get('delivered')} effective={ls.get('effective')} "
                                      f"changed_pixels={ls.get('changed_pixels')} note={str(ls.get('note'))[:100]}")
                        honest = not (ls.get("delivered") and ls.get("effective") is False and "INEFFECTIVE" not in str(ls.get("note")))
                        checks.append(("real-app-that-ignores-posted-mouse-is-reported-not-faked", honest, paint_note))
                        metrics["paint_posted_mouse_effective"] = ls.get("effective")
                    else:
                        paint_note = "paint: canvas element not found"
            finally:
                us.close_window(ph, discard_unsaved=True)
        else:
            paint_note = f"paint: could not start ({info.get('notes')})"
        _close_new_windows(before)
    except Exception as exc:
        paint_note = f"paint probe error {type(exc).__name__}: {exc}"
    checks.append(watch.check())
    return TestOutcome(passed=all(ok for _n, ok, _d in checks), evidence=_fmt(checks)[:2600] + " || " + paint_note,
                       metrics=metrics)


def run_cn1(TestOutcome):
    """CN1: organ_15's desktop connector delivers click/type/hotkey/press as posted messages to a resolved window, and REFUSES (never pyautogui) when no window resolves"""
    import asyncio
    from core_organs import headless_input as hin
    from core_organs import si_test_support as sup
    from core_organs import organ_15_external_connectors as o15

    def call(conn, action, payload):
        req = o15.ConnectorCommandRequest(request_id="cn1-" + action, connector_type=o15.ConnectorType.DESKTOP,
                                          session_id="cn1", action_name=action, payload=payload, timeout_ms=5000) \
            if hasattr(o15, "ConnectorCommandRequest") else None
        return asyncio.run(conn.execute(req))

    watch = _PointerWatch()
    win = sup.NativeButtonWindow(title="HJ-CN1-Probe", x=360, y=260).start()
    checks: List[Tuple[str, bool, str]] = []
    try:
        conn = o15.DesktopConnector()
        try:
            r0 = call(conn, "click", {"x": 10, "y": 10})
        except TypeError as exc:      # constructor shape differs: build through the module's own helpers
            return TestOutcome(passed=False, env_blocked=True, evidence=f"cannot build a ConnectorCommandRequest here: {exc}")
        checks.append(("no-target-window-is-refused", r0.status == o15.ResponseStatus.ERROR and "REFUSED" in str(r0.error_message or getattr(r0, "error", "")),
                       f"status={r0.status} err={str(getattr(r0, 'error_message', None) or getattr(r0, 'error', ''))[:110]}"))
        bx, by = win.button_center()
        c0 = win.clicks
        r1 = call(conn, "click", {"hwnd": win.hwnd, "x": bx, "y": by})
        sup._wait_clicks(win, c0, 1.5)
        checks.append(("click-lands-on-the-button", r1.status == o15.ResponseStatus.OK and win.clicks > c0,
                       f"status={r1.status} BN_CLICKED {c0}->{win.clicks}"))
        n0 = len(win.chars)
        r2 = call(conn, "type", {"window_title": "HJ-CN1-Probe", "text": "hi", "control_hwnd": win.hwnd})
        time.sleep(0.3)
        checks.append(("type-posts-characters", r2.status == o15.ResponseStatus.OK and win.chars[n0:] == [ord("h"), ord("i")],
                       f"status={r2.status} chars={[chr(c) for c in win.chars[n0:]]}"))
        k0 = len(win.combos)
        r3 = call(conn, "hotkey", {"hwnd": win.hwnd, "keys": ["ctrl", "shift", "s"]})
        time.sleep(0.3)
        checks.append(("hotkey-arrives-with-modifiers", r3.status == o15.ResponseStatus.OK and (True, True) in win.combos[k0:],
                       f"status={r3.status} combos={win.combos[k0:]}"))
        r4 = call(conn, "gui_search_launch", {"app_name": "HJ-CN1-Probe"})
        checks.append(("launch-reports-an-existing-window-truthfully", r4.status == o15.ResponseStatus.OK,
                       f"status={r4.status} data={getattr(r4, 'result_payload', None)}"))
        # a launcher that "starts" something which never shows a window must NOT be reported as launched
        # (stubbed: the real resolver maps even nonsense names onto a real app, and a test must not start one)
        import core_organs.organ_40_app_launcher as o40
        real_launch = o40.resolve_and_launch
        o40.resolve_and_launch = lambda name, gateway=None: {"launched": True, "method": "stub", "note": "stub"}
        try:
            r5 = call(conn, "gui_search_launch", {"app_name": "zzq no such application zzq", "wait_s": 1.5})
        finally:
            o40.resolve_and_launch = real_launch
        checks.append(("launch-without-a-window-is-not-an-optimistic-true", r5.status == o15.ResponseStatus.ERROR,
                       f"status={r5.status} err={str(getattr(r5, 'error_message', None) or getattr(r5, 'error', ''))[:100]}"))
    finally:
        win.stop()
    checks.append(watch.check())
    return TestOutcome(passed=all(ok for _n, ok, _d in checks), evidence=_fmt(checks)[:2400])


def _window_origin(hwnd: int) -> Tuple[int, int]:
    r = wt.RECT()
    _u32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top


# ----------------------------------------------------------------------------------------------- Fix B

def run_off1(TestOutcome):
    """OFF1: a real MINIMIZED Notepad is read by OCR through the off-screen capture rung, ends minimized again, and a structurally-grounded app never pays for it"""
    from core_organs import universal_scan as us, background_window as bw, headless_input as hin
    from core_organs import desktop_grounding as dg
    from core_organs import si_test_support as sup

    if not (dg.HAS_PIL and dg.HAS_PYTESSERACT):
        return TestOutcome(passed=False, env_blocked=True, evidence="OCR prerequisites missing (PIL/pytesseract)")
    before = _top_hwnds()
    watch = _PointerWatch()
    info = us.launch_hidden("notepad")
    hwnd = int(info.get("hwnd") or 0)
    if not hwnd:
        return TestOutcome(passed=False, env_blocked=True, evidence=f"could not start a hidden Notepad: {info.get('notes')}")
    checks: List[Tuple[str, bool, str]] = []
    metrics: Dict[str, Any] = {}
    try:
        g = dg.DesktopGrounding()
        checks.append(("starts-minimized", hin.is_minimized(hwnd), f"state={hin.window_state(hwnd).get('state')}"))
        # 1) UIA already holds the target: the rung must NOT run (it costs seconds)
        # a minimized window's UIA tree varies run to run (22 / 36 / 56 controls measured for the same Notepad), so the
        # target is taken FROM what UIA returns for this very window instead of assuming a name
        _h0, base_els, _r0 = g.ground("notepad")
        pick = next((e.name for e in base_els if 4 <= len(e.name) <= 24 and e.name.isascii() and e.role != "pane"), "")
        t0 = time.perf_counter()
        _h, els, rep = g.ground("notepad", target_text=pick, max_tier=3)
        dt_hit = (time.perf_counter() - t0) * 1000
        checks.append(("structurally-grounded-app-pays-nothing",
                       bool(pick) and "offscreen" not in rep and not rep.get("escalated") and "ocr" not in rep["tiers_ran"],
                       f"target '{pick}' found among {len(els)} UIA elements in {dt_hit:.0f} ms, escalated={rep.get('escalated')}, "
                       f"offscreen={'offscreen' in rep}"))
        # 1b) a target the MINIMIZED tree lacks but the PARKED tree has (items appear once laid out): resolved by UIA
        #     while parked, with no pixel tier at all. The name is discovered from the two trees, not assumed.
        mini_names = {e.name for e in g._walk_uia(hwnd)}
        with bw.BackgroundSession(hwnd):
            time.sleep(1.2)
            parked_names = {e.name for e in g._walk_uia(hwnd)}
        only_parked = sorted((n for n in parked_names - mini_names if 3 <= len(n) <= 24 and n.isascii() and n.lower() not in ("pane",)),
                             key=len)
        if only_parked:
            tgt = only_parked[0]
            t0 = time.perf_counter()
            # the rung itself (a minimized tree is unstable run to run, so ground()'s own structural pass may or may
            # not already see the target; calling the rung directly makes the check deterministic)
            rep_b: Dict[str, Any] = {"tiers_ran": [], "tiers_skipped": [], "tier_ms": {}}
            els_b, _repl = g._ground_offscreen(hwnd, rep_b, 3, tgt)
            off_b = rep_b.get("offscreen") or {}
            checks.append(("parked-uia-resolves-before-any-pixel-tier",
                           off_b.get("resolved_by") == "uia-parked" and "ocr" not in rep_b["tiers_ran"]
                           and any(tgt.lower() in e.name.lower() for e in els_b) and off_b.get("ended_minimized") is True,
                           f"'{tgt}' is absent from the minimized tree ({len(mini_names)} names) but present parked ({len(parked_names)}); "
                           f"resolved_by={off_b.get('resolved_by')} ran={rep_b['tiers_ran']} round_trip_ms={off_b.get('round_trip_ms')} "
                           f"total {(time.perf_counter() - t0) * 1000:.0f} ms"))
            metrics["parked_uia_gain"] = len(parked_names) - len(mini_names)
        else:
            checks.append(("parked-uia-resolves-before-any-pixel-tier", True,
                           f"NOT EXERCISED this run: minimized tree ({len(mini_names)} names) already had everything the parked one has "
                           f"({len(parked_names)} names)"))
        # 2) the target is NOT in the structure: escalate through the off-screen capture
        t0 = time.perf_counter()
        _h, els2, rep2 = g.ground("notepad", target_text="zz_absent_widget_zz", max_tier=3)
        dt_rung = (time.perf_counter() - t0) * 1000
        off = rep2.get("offscreen") or {}
        ocr_els = [e for e in els2 if e.tier == "ocr"]
        checks.append(("offscreen-rung-ran-and-read-pixels",
                       bool(off.get("used")) and "ocr" in rep2["tiers_ran"] and len(ocr_els) > 0
                       and not any("window-minimized" in s for s in rep2["tiers_skipped"]),
                       f"used={off.get('used')} mode={off.get('mode')} ocr_elements={len(ocr_els)} "
                       f"words={[e.name for e in ocr_els][:6]} skipped={rep2['tiers_skipped']}"))
        checks.append(("round-trip-timed-and-ended-minimized",
                       isinstance(off.get("round_trip_ms"), (int, float)) and off.get("ended_minimized") is True
                       and hin.is_minimized(hwnd),
                       f"round_trip_ms={off.get('round_trip_ms')} park_ms={off.get('park_ms')} paint_wait_ms={off.get('paint_wait_ms')} "
                       f"ended_minimized={off.get('ended_minimized')} tiers_via={off.get('tiers_via')}"))
        metrics.update(offscreen_round_trip_ms=off.get("round_trip_ms"), ground_total_ms=round(dt_rung),
                       uia_hit_ms=round(dt_hit), ocr_elements=len(ocr_els))
    finally:
        pass
    # 3) the guard: a window the user can SEE that we did not launch is not touched. user_can_see is the existing
    #    primitive; it is forced True for this fixture so the test is deterministic and does not flash a topmost window
    win = sup.NativeButtonWindow(title="HJ-OFF1-UserWindow").start()
    real_ucs = bw.user_can_see
    try:
        bw.user_can_see = lambda h: True
        rep3: Dict[str, Any] = {"tiers_ran": [], "tiers_skipped": [], "tier_ms": {}}
        placement_before = bw._rect(win.hwnd)
        out3, _repl = dg.DesktopGrounding()._ground_offscreen(win.hwnd, rep3, 3, "zz_absent_widget_zz")
        moved = bw._rect(win.hwnd) != placement_before
        checks.append(("refuses-a-window-the-user-can-see",
                       out3 == [] and (rep3.get("offscreen") or {}).get("refused") == "user-can-see"
                       and bool((rep3.get("offscreen") or {}).get("escalate_to_human")) and not moved
                       and not hin.is_minimized(win.hwnd),
                       f"offscreen={rep3.get('offscreen')} skipped={rep3['tiers_skipped']} window_moved={moved}"))
    finally:
        bw.user_can_see = real_ucs
        win.stop()
    checks.append(watch.check())
    try:
        us.close_window(hwnd, discard_unsaved=True)
    except Exception:
        pass
    _close_new_windows(before)
    return TestOutcome(passed=all(ok for _n, ok, _d in checks),
                       evidence=_fmt(checks)[:2200],
                       metrics=metrics)


# ----------------------------------------------------------------------------------------------- Fix D

def run_any1(TestOutcome):
    """ANY1: any-app discovery - scan walks are bounded by TIME with a visible depth rail, readiness follows a splash chain instead of a flat 10 s, an unnamed DataGrid is grounded by role, XAML hosts are recognised"""
    import os as _os
    from core_organs import desktop_grounding as dg
    from core_organs import headless_input as hin
    from core_organs import universal_scan as us, background_window as bw

    before = _top_hwnds()
    watch = _PointerWatch()
    checks: List[Tuple[str, bool, str]] = []
    metrics: Dict[str, Any] = {}

    # ---- 1) deterministic readiness simulation of a splash chain (the Steam shape: splash, gap, different window)
    class _FakeGround:
        def __init__(self, t_ready: float, sigs: List[Tuple[float, str]]):
            self.t0, self.t_ready, self.sigs = time.time(), t_ready, sigs
            self.calls = 0

        def ground(self, app_hint, target_text="", max_tier=2):
            self.calls += 1
            if time.time() - self.t0 >= self.t_ready:
                els = [dg.GroundedElement(id=str(i), name=f"c{i}", role="button", bbox=(0, 0, 9, 9), tier="uia", hwnd=1)
                       for i in range(12)]
                return 1, els, {"tiers_ran": ["uia"], "tiers_skipped": []}
            return 7, [], {"tiers_ran": ["uia"], "tiers_skipped": [], "reason": "splash"}

        def find_window(self, app_hint, all_candidates=False):
            return [7] if all_candidates else 7

        def window_title(self, h):
            now = time.time() - self.t0
            return next((t for at, t in reversed(self.sigs) if now >= at), "splash")

        def family_activity(self, app_hint):
            return frozenset({(7, self.window_title(7))}), 0.0

    saved = (dg.READY_TIMEOUT_S, dg.READY_GRACE_S, dg.READY_HARD_CAP_S)
    dg.READY_TIMEOUT_S, dg.READY_GRACE_S, dg.READY_HARD_CAP_S = 1.0, 1.2, 8.0
    try:
        loop = dg.DesktopAutonomyLoop()
        loop._hold_hidden = lambda app: None
        loop._tame_family = lambda app: None
        loop.grounding = _FakeGround(t_ready=3.2, sigs=[(0.0, "splash"), (1.0, "update"), (2.0, "login")])
        t0 = time.time()
        h, els, rep = loop._wait_for_ready("fakeapp")
        took = time.time() - t0
        checks.append(("splash-chain-extends-the-deadline-then-ready",
                       bool(h and els) and took > dg.READY_TIMEOUT_S and rep.get("ready_deadline_extended_s", 0) > 0,
                       f"ready after {took:.1f}s with a flat deadline of {dg.READY_TIMEOUT_S:.0f}s; extended by "
                       f"{rep.get('ready_deadline_extended_s')}s because the window set kept changing"))
        loop.grounding = _FakeGround(t_ready=99.0, sigs=[(0.0, "frozen")])
        t0 = time.time()
        h2, els2, rep2 = loop._wait_for_ready("fakeapp")
        took2 = time.time() - t0
        checks.append(("a-static-never-ready-app-still-gives-up-at-the-flat-deadline",
                       not els2 and took2 < dg.READY_TIMEOUT_S + 1.5 and not rep2.get("ready_deadline_extended_s"),
                       f"gave up after {took2:.1f}s (deadline {dg.READY_TIMEOUT_S:.0f}s), no extension"))
    finally:
        dg.READY_TIMEOUT_S, dg.READY_GRACE_S, dg.READY_HARD_CAP_S = saved

    # ---- 2) scan budgets on a REAL window: time-budget stop + visible depth rail, organ_30 and organ_41
    info = us.launch_hidden("notepad")
    nh = int(info.get("hwnd") or 0)
    if not nh:
        return TestOutcome(passed=False, env_blocked=True, evidence=f"no hidden Notepad to scan: {info.get('notes')}")
    try:
        from core_organs import organ_30_app_scanner as o30
        from core_organs.organ_41_scanner import ScannerOrgan
        with bw.BackgroundSession(nh):
            time.sleep(1.2)
            orch = o30.EyeAndBrainOrchestrator()
            full = orch.deep_scan_unknown_app(app_name="any1", target_hwnd=nh, quiet=True).get("tree_stats", {})
            checks.append(("deep-scan-reports-its-limits",
                           all(k in full for k in ("depth_hit_cap", "time_budget_hit", "time_budget_ms", "walk_ms", "truncated"))
                           and full.get("nodes_walked", 0) > 50,
                           f"{ {k: full.get(k) for k in ('nodes_walked', 'max_depth_seen', 'walk_max_depth', 'depth_hit_cap', 'time_budget_ms', 'time_budget_hit', 'walk_ms')} }"))
            saved_env = {k: _os.environ.get(k) for k in ("HOJAIGA_DEEP_SCAN_BUDGET_MS", "HOJAIGA_DEEP_SCAN_MAX_DEPTH")}
            saved_min = o30.DEEP_SCAN_MIN_NODES
            try:
                _os.environ["HOJAIGA_DEEP_SCAN_BUDGET_MS"] = "1"
                o30.DEEP_SCAN_MIN_NODES = 10
                short = orch.deep_scan_unknown_app(app_name="any1", target_hwnd=nh, quiet=True).get("tree_stats", {})
                _os.environ.pop("HOJAIGA_DEEP_SCAN_BUDGET_MS", None)
                o30.DEEP_SCAN_MIN_NODES = saved_min
                _os.environ["HOJAIGA_DEEP_SCAN_MAX_DEPTH"] = "2"
                shallow = orch.deep_scan_unknown_app(app_name="any1", target_hwnd=nh, quiet=True).get("tree_stats", {})
            finally:
                o30.DEEP_SCAN_MIN_NODES = saved_min
                for k, v in saved_env.items():
                    if v is None:
                        _os.environ.pop(k, None)
                    else:
                        _os.environ[k] = v
            checks.append(("time-budget-cuts-the-walk-and-says-so",
                           short.get("time_budget_hit") is True and 10 <= short.get("nodes_walked", 0) < full.get("nodes_walked", 0),
                           f"1 ms budget: {short.get('nodes_walked')} of {full.get('nodes_walked')} nodes, time_budget_hit={short.get('time_budget_hit')}"))
            checks.append(("depth-rail-is-secondary-and-visible",
                           shallow.get("depth_hit_cap") is True and shallow.get("max_depth_seen", 9) <= 2 and full.get("depth_hit_cap") is False,
                           f"rail=2: depth_hit_cap={shallow.get('depth_hit_cap')} (default rail {full.get('walk_max_depth')}: hit={full.get('depth_hit_cap')})"))
            # organ_41: same budget idea on the continuous scanner
            import uiautomation as auto
            sc = ScannerOrgan()
            root = auto.ControlFromHandle(nh)
            n_full = len(sc._collect_uia_frame(root, sc._element_max_depth, sc._max_nodes))
            st_full = dict(sc.last_walk_stats)
            sc._walk_budget_ms, sc._min_nodes = 1, 5
            n_cut = len(sc._collect_uia_frame(root, sc._element_max_depth, sc._max_nodes))
            st_cut = dict(sc.last_walk_stats)
            sc._walk_budget_ms, sc._min_nodes = 400, 120
            sc._collect_uia_frame(root, 2, sc._max_nodes)
            st_shallow = dict(sc.last_walk_stats)
            checks.append(("organ_41-time-budget-and-visible-rails",
                           st_cut.get("time_budget_hit") is True and 5 <= n_cut < n_full and st_shallow.get("depth_hit_cap") is True
                           and st_full.get("depth_cap", 0) >= 32,
                           f"full {n_full} nodes (depth rail {st_full.get('depth_cap')}, hit={st_full.get('depth_hit_cap')}); 1 ms budget -> {n_cut} nodes "
                           f"time_budget_hit={st_cut.get('time_budget_hit')}; rail 2 -> depth_hit_cap={st_shallow.get('depth_hit_cap')}"))
    finally:
        us.close_window(nh, discard_unsaved=True)

    # ---- 3) XAML recognition: a XAML host is flagged, a plain Win32 window is not
    from core_organs import si_test_support as sup
    win = sup.NativeButtonWindow(title="HJ-ANY1-Win32").start()
    try:
        calc = us.launch_hidden("calculator")
        ch = int(calc.get("hwnd") or 0)
        try:
            checks.append(("xaml-host-recognised-and-win32-window-not",
                           ch != 0 and hin.is_xaml_host(ch) and not hin.is_xaml_host(win.hwnd),
                           f"calculator frame xaml={hin.is_xaml_host(ch) if ch else None}; native Win32 window xaml={hin.is_xaml_host(win.hwnd)}"))
        finally:
            if ch:
                us.close_window(ch, discard_unsaved=True)
    finally:
        win.stop()

    # ---- 4) Excel: the unnamed/generic document grid is grounded by ROLE, and its cells are sampled with totals
    excel_note = ""
    try:
        ex = us.launch_hidden("excel", timeout_s=60.0)
        eh = int(ex.get("hwnd") or 0)
        if not eh:
            excel_note = f"excel not available here ({ex.get('notes')})"
        else:
            try:
                import uiautomation as auto
                with bw.BackgroundSession(eh):
                    time.sleep(1.5)
                    for c, _d in auto.WalkControl(auto.ControlFromHandle(eh), maxDepth=14):
                        try:
                            if (c.Name or "").strip().lower() == "blank workbook":
                                pat = c.GetInvokePattern()
                                if pat:
                                    pat.Invoke()
                                    break
                        except Exception:
                            continue
                    end = time.time() + 20
                    els, rep = [], {}
                    while time.time() < end:
                        time.sleep(1.0)
                        g = dg.DesktopGrounding()
                        h, els, rep = g.ground("excel")
                        if any(e.role == "datagrid" for e in els):
                            break
                    grids = [e for e in els if e.role == "datagrid"]
                    cells = [e for e in els if e.role == "dataitem"]
                    gr = rep.get("grid") or {}
                    checks.append(("excel-grid-grounded-by-role-with-honest-sampling",
                                   bool(grids) and 0 < len(cells) <= dg.GRID_CELL_CAP and gr.get("grid_cells_seen", 0) >= len(cells),
                                   f"{len(els)} elements; datagrid elements={len(grids)} (named {[e.name for e in grids][:2]}); "
                                   f"cells surfaced {len(cells)} of {gr.get('grid_cells_seen')} (cap {dg.GRID_CELL_CAP}, sampled out {gr.get('grid_cells_sampled_out')})"))
                    metrics["excel_elements"] = len(els)
            finally:
                us.close_window(eh, discard_unsaved=True)
    except Exception as exc:
        excel_note = f"excel probe error {type(exc).__name__}: {exc}"
    if excel_note:
        checks.append(("excel-grid-grounded-by-role-with-honest-sampling", True, "NOT EXERCISED: " + excel_note))

    _close_new_windows(before)
    checks.append(watch.check())
    return TestOutcome(passed=all(ok for _n, ok, _d in checks), evidence=_fmt(checks)[:3000], metrics=metrics)


# ----------------------------------------------------------------------------------------------- Fix E

def run_up1(TestOutcome):
    """UP1: ONE popup engine - organ_29 only detects; escalation presses zero buttons; benign prompts are dismissed not escalated; the cold LLM tier is capped AND a breaker stops later popups paying it again (measured)"""
    import inspect
    import threading
    from core_organs import popup_policy as pp
    from core_organs import organ_29_popup_handler as o29
    from core_organs import headless_input as hin
    from core_organs import si_test_support as sup
    from core_organs import si_tests_extra as sx

    os.environ["HOJAIGA_POPUP_PREWARM"] = "0"
    watch = _PointerWatch()
    checks: List[Tuple[str, bool, str]] = []
    metrics: Dict[str, Any] = {}

    class _MemDB:
        def __init__(self):
            self.rows = []

        def generate_layout_hash(self, t):
            return t

        def check_popup_history(self, title):
            return next((r for r in self.rows if r["title"] == title), None)

        def check_popup_fingerprint(self, fp):
            return next((r for r in self.rows if r["fingerprint"] == fp), None)

        def log_new_pathway(self, layout_hash, element_name, x, y, action_type, parent_path="", fingerprint=""):
            self.rows.append({"title": element_name, "x": x, "y": y, "action": action_type,
                              "parent_path": parent_path, "fingerprint": fingerprint})

    def view(title, kind="modal_window", text="", cls="CustomClass", buttons=()):
        return pp.PopupView(hwnd=0, title=title, class_name=cls, kind=kind, text=text, buttons=buttons,
                            bounds=(100, 100, 500, 400))

    # ---- 1) there is ONE implementation: organ_29 delegates every decision, and its old decision code is gone
    calls: List[str] = []
    real_resolve = pp.resolve_view

    def counting(v, **kw):
        calls.append(v.title)
        return real_resolve(v, **kw)
    pp.resolve_view = counting
    try:
        mgr = o29.DesktopInteractionManager()
        mgr._execute_key_intent = lambda a, hwnd=0: True
        node = o29.WindowNode(handle=0, parent_handle=None, owner_handle=None, process_id=os.getpid(),
                              title="zz-up1-" + uuid.uuid4().hex[:6], class_name="CustomClass",
                              win_type=o29.WindowType.COOKIE_BANNER,
                              bounds=o29.WindowRect(100, 100, 500, 400), text_content="we value your privacy")
        mgr.resolve_and_mitigate(node)
        pp.resolve_dialog(0)
    finally:
        pp.resolve_view = real_resolve
    gone = [n for n in ("_try_semantic_button_dismiss", "_replay_cached_action", "_cancel_only") if hasattr(mgr, n)]
    gone_mod = [n for n in ("POSITIVE_DISMISS_NAMES", "SAFE_DISMISS_NAMES", "_matches_button_semantic") if hasattr(o29, n)]
    n_lines = len(inspect.getsource(o29).splitlines())
    checks.append(("organ_29-and-the-loop-share-one-engine",
                   len(calls) == 2 and not gone and not gone_mod and o29.GATEKEEPER_TIER3_TIMEOUT_S is pp.GATEKEEPER_TIER3_TIMEOUT_S,
                   f"resolve_view reached by organ_29 and resolve_dialog ({len(calls)} calls); retired from organ_29: "
                   f"{gone or gone_mod or 'nothing left behind'}; organ_29 is now {n_lines} lines (was 989)"))

    # ---- 2) escalation presses ZERO buttons - on REAL dialogs, through organ_29's own entry point
    root = sup.NativeButtonWindow(title="HJ-UP1-Root").start()
    try:
        pressed: List[str] = []
        mgr2 = o29.DesktopInteractionManager()
        mgr2._execute_key_intent = lambda a, hwnd=0: (pressed.append(a), True)[1]
        pre = set(pp.blocking_dialogs(root.hwnd))
        t, res = sx.show_messagebox("Do you want to allow this app to make changes to your device?",
                                    "User Account Control", 0x1 | 0x30)          # OK/Cancel + warning
        dlgs = [d for d in pp.blocking_dialogs(root.hwnd, pre)]
        out_h = None
        if dlgs:
            wn = mgr2.wrap_hwnd(dlgs[0])
            out_h = mgr2.resolve_and_mitigate(wn)
        still_open = bool(dlgs) and hin.is_alive(dlgs[0]) and hin._u32.IsWindowVisible(dlgs[0])
        code_before_cleanup = res["code"]            # (the cleanup WM_CLOSE below makes an OK/Cancel box return IDCANCEL)
        for d in dlgs:
            hin._u32.PostMessageW(d, 0x0010, 0, 0)
        t.join(timeout=2)
        checks.append(("uac-like-real-dialog-needs-a-human-and-zero-buttons-pressed",
                       out_h is not None and out_h[0] is False and out_h[3] == "need_human" and still_open
                       and code_before_cleanup is None and not pressed,
                       f"organ_29 returned {out_h}; dialog still open={still_open}; button pressed by us before cleanup={code_before_cleanup}; keys sent={pressed}"))
        # a real save-changes box reached through organ_29 detection: answered Cancel (code 2) by the engine
        pre = set(pp.blocking_dialogs(root.hwnd))
        t, res = sx.show_messagebox("Do you want to save changes to Untitled?", "Notepad", 0x3 | 0x30)   # Yes/No/Cancel
        dlgs = [d for d in pp.blocking_dialogs(root.hwnd, pre)]
        out_s = mgr2.resolve_and_mitigate(mgr2.wrap_hwnd(dlgs[0])) if dlgs else None
        t.join(timeout=3)
        checks.append(("organ_29-detected-real-save-changes-box-answered-Cancel-headless",
                       out_s is not None and out_s[0] is True and res["code"] == 2,
                       f"organ_29 -> {out_s}; the box returned {res['code']} (2 = Cancel; 6 = Yes would have been destructive)"))
    finally:
        root.stop()

    # ---- 3) benign categories are dismissed (privacy-preserving), not escalated; real credentials still are
    keys: List[str] = []
    ks = lambda a, hwnd=0: (keys.append(a), True)[1]
    d_pw = pp.resolve_view(view("zz-pw-" + uuid.uuid4().hex[:6], "browser_prompt", "Save password for example.com?"),
                           db=_MemDB(), key_sender=ks)
    d_ck = pp.resolve_view(view("zz-ck-" + uuid.uuid4().hex[:6], "cookie_banner", "we value your privacy cookies"),
                           db=_MemDB(), key_sender=ks)
    keys.clear()
    d_auth = pp.resolve_view(view("zz-auth-" + uuid.uuid4().hex[:6], "authentication", "enter your password"),
                             db=_MemDB(), key_sender=ks)
    checks.append(("browser-save-password-bubble-dismissed-but-real-credential-prompt-escalated",
                   d_pw.handled and not d_pw.need_human and d_ck.handled and not d_ck.need_human
                   and d_auth.need_human and not d_auth.handled and not keys,
                   f"save-password bubble -> {d_pw.action} via {d_pw.tier}; cookie banner -> {d_ck.action} via {d_ck.tier}; "
                   f"authentication -> need_human={d_auth.need_human} via {d_auth.tier}, keys sent={keys}"))

    # ---- 4) cold path, MEASURED: capped LLM tier + breaker + cache
    real_cap = pp.GATEKEEPER_TIER3_TIMEOUT_S
    pp.GATEKEEPER_TIER3_TIMEOUT_S = 0.8
    pp.reset_tier3_breaker()
    db = _MemDB()
    sent: List[str] = []
    key_ok = lambda a, hwnd=0: (sent.append(a), True)[1]
    slow_calls = {"n": 0}

    def slow_llm(view, system, user, timeout_s):
        slow_calls["n"] += 1
        time.sleep(timeout_s)                       # a cold model: never answers inside the cap
        raise TimeoutError("cold model")
    try:
        v1 = view("zz-cold-one-" + uuid.uuid4().hex[:6], cls="ColdA")
        t0 = time.perf_counter()
        d1 = pp.resolve_view(v1, db=db, key_sender=key_ok, llm=slow_llm)
        cold_ms = (time.perf_counter() - t0) * 1000
        v2 = view("zz-cold-two-" + uuid.uuid4().hex[:6], cls="ColdB")
        t0 = time.perf_counter()
        d2 = pp.resolve_view(v2, db=db, key_sender=key_ok, llm=slow_llm)
        next_ms = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        d3 = pp.resolve_view(v1, db=db, key_sender=key_ok, llm=slow_llm)
        repeat_ms = (time.perf_counter() - t0) * 1000
        checks.append(("cold-llm-tier-is-hard-capped",
                       d1.handled and d1.tier == "T4" and cold_ms < (0.8 + 1.0) * 1000 and slow_calls["n"] == 1,
                       f"never-answering model: resolved via {d1.tier} in {cold_ms:.0f} ms (cap 800 ms; unbounded before the cap existed was ~30 s)"))
        checks.append(("breaker-stops-every-later-cold-popup-paying-the-cap-again",
                       d2.handled and d2.tier == "T4" and next_ms < 400 and slow_calls["n"] == 1 and not pp.tier3_available(),
                       f"next cold popup: {next_ms:.0f} ms vs {cold_ms:.0f} ms for the first; LLM calls made={slow_calls['n']}; "
                       f"breaker open={not pp.tier3_available()}"))
        checks.append(("repeat-of-a-learned-popup-is-a-cache-hit",
                       d3.tier == "T2" and d3.handled and repeat_ms < 100,
                       f"repeat of the first popup: {d3.tier} in {repeat_ms:.1f} ms"))
        metrics.update(cold_first_ms=round(cold_ms), cold_next_ms=round(next_ms), repeat_ms=round(repeat_ms, 1))
        # a model that answers inside the cap: used once, then remembered by fingerprint
        pp.reset_tier3_breaker()
        fast = lambda view, system, user, timeout_s: {"action": "key:enter", "target_x": 0, "target_y": 0}
        v4 = view("Installer Error 0x80070005 (attempt 3)", cls="ColdC" + uuid.uuid4().hex[:4], buttons=("Retry", "Cancel"))
        t0 = time.perf_counter()
        d4 = pp.resolve_view(v4, db=db, key_sender=key_ok, llm=fast)
        fast_ms = (time.perf_counter() - t0) * 1000
        v5 = view("Installer Error 0x8007271D (attempt 17)", cls=v4.class_name, buttons=("Retry", "Cancel"))
        t0 = time.perf_counter()
        d5 = pp.resolve_view(v5, db=db, key_sender=key_ok, llm=slow_llm)
        fp_ms = (time.perf_counter() - t0) * 1000
        checks.append(("answered-once-then-fingerprint-cached-for-dynamic-titles",
                       d4.tier == "T3" and d5.tier == "T2" and fp_ms < 100,
                       f"first: {d4.tier} {fast_ms:.0f} ms; same popup with a different error code: {d5.tier} {fp_ms:.1f} ms"))
    finally:
        pp.GATEKEEPER_TIER3_TIMEOUT_S = real_cap
        pp.reset_tier3_breaker()

    # ---- 5) the real cold path on this machine (no stand-ins): whatever the gatekeeper is actually doing right now
    pp.reset_tier3_breaker()
    t0 = time.perf_counter()
    dr = pp.resolve_view(view("zz-real-cold-" + uuid.uuid4().hex[:6], cls="RealCold"), db=_MemDB(), key_sender=key_ok)
    real_ms = (time.perf_counter() - t0) * 1000
    listening = pp._gatekeeper_listening()
    checks.append(("real-cold-path-inside-the-cap",
                   real_ms < (pp.GATEKEEPER_TIER3_TIMEOUT_S + 1.0) * 1000 and (listening or real_ms < 700),
                   f"unseen ambiguous popup with the REAL gatekeeper ({pp.GATEKEEPER_URL}, listening={listening}): resolved via "
                   f"{dr.tier} in {real_ms:.0f} ms (cap {pp.GATEKEEPER_TIER3_TIMEOUT_S:.1f} s). Before the listener probe a CLOSED "
                   f"local port cost 2.0-2.8 s here (Windows takes ~2 s to report 'refused')"))
    metrics["real_cold_ms"] = round(real_ms)
    pp.reset_tier3_breaker()
    checks.append(watch.check())
    return TestOutcome(passed=all(ok for _n, ok, _d in checks), evidence=_fmt(checks)[:3200], metrics=metrics)


def _judge_up() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _read_notepad_text(hwnd: int) -> str:
    """Independent ground truth: the document text, read through UIA from the parked window (no product code)."""
    import uiautomation as auto
    from core_organs import background_window as bw
    with bw.BackgroundSession(hwnd):
        time.sleep(0.5)
        root = auto.ControlFromHandle(hwnd)
        best = ""
        for c, _d in auto.WalkControl(root, maxDepth=12):
            if c.ControlTypeName in ("DocumentControl", "EditControl"):
                try:
                    v = c.GetValuePattern().Value or ""
                except Exception:
                    v = ""
                if len(v) > len(best):
                    best = v
        return best


def _remove_typed_suffix(hwnd: int, typed: str) -> bool:
    """Notepad restores unsaved tabs on its next launch, so text a test typed would reappear in the USER'S Notepad.
    Remove exactly what the test appended (and nothing else) before the window we launched is closed."""
    if not (hwnd and _u32.IsWindow(hwnd)):
        return False
    try:
        import uiautomation as auto
        from core_organs import background_window as bw
        with bw.BackgroundSession(hwnd):
            time.sleep(0.3)
            for c, _d in auto.WalkControl(auto.ControlFromHandle(hwnd), maxDepth=12):
                if c.ControlTypeName in ("DocumentControl", "EditControl"):
                    vp = c.GetValuePattern()
                    cur = vp.Value or ""
                    if cur.rstrip().endswith(typed):
                        vp.SetValue(cur.rstrip()[:-len(typed)])
                        return True
    except Exception:
        pass
    return False


def _names_in(hwnd: int) -> List[str]:
    from core_organs import fast_uia, background_window as bw
    with bw.BackgroundSession(hwnd):
        time.sleep(0.4)
        return [(n.name or "") for n in (fast_uia.snapshot(hwnd, timeout_ms=5000) or []) if n.name]


def _display_values(text: str) -> List[float]:
    """Every NUMBER a calculator display line states ('Display is 42', 'Display is -7.0421845...').

    A ground truth read as a SUBSTRING is not a ground truth: a run that ended on -7.04218457151810888857...
    contained '42' and was graded correct. The value has to be parsed and compared."""
    import re
    return [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", (text or "").replace(",", ""))]


def run_lf2(TestOutcome):
    """LF2: a REAL two-app task (Notepad then Calculator) runs both apps through the verified loop with the physical pointer untouched"""
    from core_organs import loop_first as lf
    from core_organs import headless_input as hin
    from core_organs.organ_01_crewai_engine import _compile_task_with_organ36

    if not _judge_up():
        return TestOutcome(passed=False, env_blocked=True,
                           evidence="local judge model (Ollama :11434) is not reachable - the live loop cannot run (environment)")
    before = _top_hwnds()
    watch = _PointerWatch()
    cmd = "open notepad and type loop first works, then open calculator and compute 6 * 7"
    comp = _compile_task_with_organ36(cmd)
    t0 = time.perf_counter()
    result = lf.run_loop_first(cmd, comp.get("app_spans") or [])
    dt = time.perf_counter() - t0
    checks: List[Tuple[str, bool, str]] = []
    notepad_run = next((r for r in result.runs if r.app == "notepad"), None)
    calc_run = next((r for r in result.runs if r.app == "calculator"), None)
    checks.append(("both-apps-ran-in-order",
                   [r.app for r in result.runs] == ["notepad", "calculator"],
                   f"runs={[(r.app, r.status, r.result.get('steps')) for r in result.runs]}"))
    note_truth = calc_truth = ""
    try:
        if notepad_run and notepad_run.hwnd and hin.is_alive(notepad_run.hwnd):
            note_truth = _read_notepad_text(notepad_run.hwnd)
        if calc_run and calc_run.hwnd and hin.is_alive(calc_run.hwnd):
            calc_truth = " | ".join(n for n in _names_in(calc_run.hwnd) if n.lower().startswith("display is"))
    except Exception as exc:
        checks.append(("ground-truth-readable", False, f"{type(exc).__name__}: {exc}"))
    checks.append(("notepad-holds-the-typed-words (independent read)", "loop first works" in note_truth.lower(),
                   f"document={note_truth[:60]!r}"))
    got_values = _display_values(calc_truth)
    checks.append(("calculator-shows-42 (independent read)", any(abs(v - 42.0) < 1e-9 for v in got_values),
                   f"display={calc_truth[:60]!r} parsed={got_values[:4]}"))
    checks.append(("handles-persisted-for-later-stages",
                   bool(lf.handle_for("notepad")) and bool(lf.handle_for("calculator")),
                   f"notepad={lf.handle_for('notepad')} calculator={lf.handle_for('calculator')}"))
    checks.append(("completed-or-honestly-blocked",
                   all(r.status in ("COMPLETED", "BLOCKED") for r in result.runs) and result.all_completed,
                   f"statuses={[r.status for r in result.runs]}"))
    checks.append(watch.check())
    _remove_typed_suffix(notepad_run.hwnd if notepad_run else 0, "loop first works")   # hygiene: Notepad restores unsaved tabs
    closed = _close_new_windows(before)
    passed = all(ok for _n, ok, _d in checks)
    return TestOutcome(passed=passed,
                       evidence=_fmt(checks)[:1800]
                                + f"; total {dt:.1f}s; closed {closed} window(s) we launched",
                       metrics={"seconds": round(dt, 1), "windows_closed": closed,
                                "statuses": ",".join(r.status for r in result.runs)})


# ----------------------------------------------------------------------------------------------- TY1: headless launch / switch / type

class EditorWindow:
    """A REAL Win32 top-level window (own thread + message loop) in one of three shapes:
         kind="edit"      a native multiline EDIT child: readable AND writable through UIA ValuePattern / EM_REPLACESEL
         kind="refusing"  an EDIT child seeded with "locked" and SUBCLASSED to drop every write (WM_SETTEXT is acknowledged with
                          success, EM_REPLACESEL / WM_CHAR / WM_PASTE are swallowed): every delivery API 'succeeds', the text never
                          changes. (A plain ES_READONLY edit is NOT used: it still accepts programmatic writes, only the human is locked out.)
         kind="swallow"   no text control at all: WM_CHAR / WM_KEYDOWN are logged and dropped (what a XAML or game host does)
    WS_EX_NOACTIVATE + SW_SHOWNOACTIVATE / SW_SHOWMINNOACTIVE: creating a fixture never takes the user's focus."""

    WS_EX_NOACTIVATE = 0x08000000
    WS_BORDER = 0x00800000
    ES_MULTILINE, ES_AUTOVSCROLL, ES_WANTRETURN = 0x0004, 0x0040, 0x1000
    _DROPPED = frozenset({0x000C, 0x00C2, 0x0102, 0x0302})      # WM_SETTEXT EM_REPLACESEL WM_CHAR WM_PASTE
    EDIT_ID = 2001

    def __init__(self, title: str, kind: str = "edit", x: int = 300, y: int = 200, w: int = 420, h: int = 240,
                 minimized: bool = False):
        import threading
        self.title, self.kind, self._x, self._y, self._w, self._h = title, kind, x, y, w, h
        self._minimized = minimized
        self.hwnd = 0
        self.edit = 0
        self.chars: List[int] = []          # WM_CHAR code points a "swallow" window received
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"EditorWindow-{title}")
        self._cls = f"HJTy1_{uuid.uuid4().hex[:10]}"

    def _wndproc(self, hwnd, msg, wparam, lparam):
        sup = self._sup
        if self.kind == "swallow" and msg == 0x0102:
            self.chars.append(int(wparam))
            return 0
        if msg == sup.WM_DESTROY:
            sup.user32.PostQuitMessage(0)
            return 0
        return sup.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _run(self):
        from core_organs import si_test_support as sup
        self._sup = sup
        sup.user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_void_p]
        sup.user32.SendMessageW.restype = sup.LRESULT
        self._proc = sup.WNDPROC(self._wndproc)
        hinst = sup.kernel32.GetModuleHandleW(None)
        wc = sup._WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = self._cls
        wc.hbrBackground = 6
        sup.user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = sup.user32.CreateWindowExW(self.WS_EX_NOACTIVATE, self._cls, self.title, sup.WS_OVERLAPPEDWINDOW,
                                               self._x, self._y, self._w, self._h, None, None, hinst, None) or 0
        if self.hwnd and self.kind in ("edit", "refusing"):
            style = (sup.WS_CHILD | sup.WS_VISIBLE | self.WS_BORDER | self.ES_MULTILINE | self.ES_AUTOVSCROLL
                     | self.ES_WANTRETURN)
            self.edit = sup.user32.CreateWindowExW(0, "EDIT", "locked" if self.kind == "refusing" else "", style,
                                                   8, 8, self._w - 40, self._h - 70, self.hwnd, self.EDIT_ID, hinst,
                                                   None) or 0
            if self.edit and self.kind == "refusing":
                u = sup.user32
                u.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p]
                u.SetWindowLongPtrW.restype = ctypes.c_void_p
                u.CallWindowProcW.argtypes = [ctypes.c_void_p, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
                u.CallWindowProcW.restype = sup.LRESULT
                dropped = self._DROPPED

                def refuse(h, msg, wparam, lparam):
                    if msg in dropped:
                        return 1 if msg == 0x000C else 0
                    return u.CallWindowProcW(self._old_edit_proc, h, msg, wparam, lparam)
                self._edit_proc = sup.WNDPROC(refuse)
                self._old_edit_proc = u.SetWindowLongPtrW(self.edit, -4, ctypes.cast(self._edit_proc, ctypes.c_void_p))
        if self.hwnd:
            sup.user32.ShowWindow(self.hwnd, 7 if self._minimized else 4)   # SW_SHOWMINNOACTIVE / SW_SHOWNOACTIVATE
        self._ready.set()
        msg = wt.MSG()
        while sup.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            sup.user32.TranslateMessage(ctypes.byref(msg))
            sup.user32.DispatchMessageW(ctypes.byref(msg))

    def start(self) -> "EditorWindow":
        self._thread.start()
        self._ready.wait(5)
        time.sleep(0.3)
        return self

    def read_text(self) -> str:
        """Ground truth, independent of UIA: WM_GETTEXT sent straight to the EDIT control."""
        if not self.edit:
            return ""
        u = self._sup.user32
        n = int(u.SendMessageW(self.edit, 0x000E, 0, None))               # WM_GETTEXTLENGTH
        buf = ctypes.create_unicode_buffer(n + 1)
        u.SendMessageW(self.edit, 0x000D, n + 1, ctypes.addressof(buf))   # WM_GETTEXT
        return buf.value

    def state(self) -> Dict[str, Any]:
        r = wt.RECT()
        _u32.GetWindowRect(self.hwnd, ctypes.byref(r))
        return {"iconic": bool(_u32.IsIconic(self.hwnd)), "zoomed": bool(_u32.IsZoomed(self.hwnd)),
                "rect": (r.left, r.top, r.right, r.bottom)}

    def stop(self):
        if self.hwnd:
            self._sup.user32.PostMessageW(self.hwnd, 0x0010, 0, 0)
        self._thread.join(timeout=2)


class _InputSpies:
    """Counting wrappers, installed for the duration of a with-block, on every API that would raise / restore /
    maximize a window or inject a physical key or mouse event. A raise/restore/maximize attempt on a WATCHED window is
    recorded and REFUSED (it never reaches the OS), so even a regression cannot disturb the user's screen while the
    suite runs; a keystroke attempt is recorded and handed on to the physical-input guard, which refuses it too."""

    SHOW_FORBIDDEN = frozenset({1, 3, 4, 5, 8, 9, 10})   # SHOWNORMAL MAXIMIZE SHOWNOACTIVATE SHOW SHOWNA RESTORE SHOWDEFAULT
    SWP_NOZORDER = 0x0004

    def __init__(self, watched):
        self.watched = {int(h) for h in watched if h}
        self.refused: List[str] = []
        self.keys: List[str] = []
        self.shell: List[Tuple[Any, ...]] = []
        self.spawned: List[str] = []
        self._saved: List[Tuple[Any, str, Any]] = []

    def reset(self):
        self.refused.clear()
        self.keys.clear()

    def _patch(self, owner, name, make):
        orig = getattr(owner, name)
        self._saved.append((owner, name, orig))
        setattr(owner, name, make(orig))

    def __enter__(self):
        import subprocess
        import win32gui
        spy = self

        def hw(a) -> int:
            try:
                return int(a[0]) if a and a[0] is not None else 0
            except Exception:
                return 0

        def key(name):
            def make(orig):
                def f(*a, **k):
                    spy.keys.append(name)
                    return orig(*a, **k)                       # the guard refuses and records it
                return f
            return make

        def fg(name):
            def make(orig):
                def f(*a, **k):
                    if hw(a) in spy.watched:
                        spy.refused.append(f"{name}({hw(a)})")
                        return 0
                    return orig(*a, **k)
                return f
            return make

        def show(name):
            def make(orig):
                def f(*a, **k):
                    if hw(a) in spy.watched and len(a) > 1 and int(a[1]) in spy.SHOW_FORBIDDEN:
                        spy.refused.append(f"{name}({hw(a)},cmd={int(a[1])})")
                        return 0
                    return orig(*a, **k)
                return f
            return make

        def pos(name):
            def make(orig):
                def f(*a, **k):
                    if hw(a) in spy.watched and len(a) >= 7 and not (int(a[6]) & spy.SWP_NOZORDER):
                        spy.refused.append(f"{name}({hw(a)},z-order change)")
                        return 0
                    return orig(*a, **k)
                return f
            return make

        def shell(orig):
            def f(*a, **k):
                spy.shell.append(tuple(a))
                return 42                                       # > 32 = ShellExecute "success"; nothing is started
            return f

        def popen(orig):
            def f(*a, **k):
                spy.spawned.append(str(a[0] if a else k.get("args"))[:80])
                raise RuntimeError("TY1 refuses to spawn processes")
            return f

        u = ctypes.windll.user32
        for n in ("keybd_event", "mouse_event"):
            self._patch(u, n, key(f"user32.{n}"))
        self._patch(u, "SetForegroundWindow", fg("user32.SetForegroundWindow"))
        self._patch(u, "SwitchToThisWindow", fg("user32.SwitchToThisWindow"))
        self._patch(u, "ShowWindow", show("user32.ShowWindow"))
        self._patch(u, "SetWindowPos", pos("user32.SetWindowPos"))
        self._patch(win32gui, "SetForegroundWindow", fg("win32gui.SetForegroundWindow"))
        self._patch(win32gui, "ShowWindow", show("win32gui.ShowWindow"))
        self._patch(win32gui, "SetWindowPos", pos("win32gui.SetWindowPos"))
        self._patch(ctypes.windll.shell32, "ShellExecuteW", shell)
        self._patch(subprocess, "Popen", popen)
        return self

    def __exit__(self, *exc):
        for owner, name, orig in reversed(self._saved):
            setattr(owner, name, orig)
        self._saved.clear()
        return False


class _ExposureSampler:
    """Samples every ~4 ms where each watched window is: the MOST pixels it ever had inside a real monitor while not
    minimized, and how many samples it was the foreground window. 'Never shown' is a measurement here, not a claim
    (a sampler can miss a sub-4 ms event, so the number is a lower bound)."""

    def __init__(self, hwnds):
        import threading
        self.hwnds = [int(h) for h in hwnds if h]
        self.max_px = {h: 0 for h in self.hwnds}
        self.exposed_s = {h: 0.0 for h in self.hwnds}      # time a non-minimized window overlapped a monitor by > 1 px
        self.fg_hits = {h: 0 for h in self.hwnds}
        self.samples = 0
        self.pointer_moves: List[float] = []                 # perf_counter() of every observed cursor change
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ExposureSampler")

    def _run(self):
        from core_organs import background_window as bw
        screens = bw._screens()
        last = time.perf_counter()
        last_pt = _pointer()
        while not self._stop.is_set():
            now = time.perf_counter()
            dt, last = now - last, now
            pt = _pointer()
            if pt != last_pt:
                self.pointer_moves.append(now)
                last_pt = pt
            fg = int(_u32.GetForegroundWindow() or 0)
            for h in self.hwnds:
                if not _u32.IsWindow(h):
                    continue
                if fg == h:
                    self.fg_hits[h] += 1
                if _u32.IsIconic(h):
                    continue
                r = wt.RECT()
                _u32.GetWindowRect(h, ctypes.byref(r))
                px = max((max(0, min(r.right, sr) - max(r.left, sl)) * max(0, min(r.bottom, sb) - max(r.top, st))
                          for sl, st, sr, sb in screens), default=0)
                self.max_px[h] = max(self.max_px[h], px)
                if px > 1:
                    self.exposed_s[h] += dt
            self.samples += 1
            time.sleep(0.004)

    def start(self):
        self._thread.start()
        return self

    def watch(self, hwnd: int):
        if hwnd and int(hwnd) not in self.max_px:
            self.max_px[int(hwnd)] = 0
            self.exposed_s[int(hwnd)] = 0.0
            self.fg_hits[int(hwnd)] = 0
            self.hwnds.append(int(hwnd))

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=1)


def run_ty1(TestOutcome):
    """TY1: the launch / switch / type tools never touch the physical keyboard or mouse and never raise, restore or maximize a window (a minimized target is parked off-screen for the call); a delivery the target did not accept is never reported - or recorded - as typed"""
    import re
    import subprocess
    import win32gui
    from core_organs import headless_input as hin
    from core_organs import background_window as bw
    from core_organs import universal_scan as us
    from core_organs import organ_40_app_launcher as o40
    import core_organs.organ_01_crewai_engine as o1

    guard_fn = getattr(ctypes.windll.user32, "keybd_event", None)
    if not (getattr(guard_fn, "__name__", "").startswith("guarded_") and os.environ.get("HOJAIGA_ALLOW_PHYSICAL_INPUT") != "1"):
        return TestOutcome(passed=False, env_blocked=True,
                           evidence="the physical-input guard is not live in this process (HOJAIGA_ALLOW_PHYSICAL_INPUT=1 or the guard "
                                    "was never installed): refusing to run a test whose failure mode is a real keystroke")
    tools = {n: getattr(o1, n, None) for n in ("launch_app_tool", "switch_to_app_tool", "type_text_tool")}
    if not all(hasattr(t, "func") for t in tools.values()):
        return TestOutcome(passed=False, env_blocked=True, evidence="the crew tool objects are unavailable here (crewai not importable)")
    raw_launch, raw_switch, raw_type = (tools[n].func for n in ("launch_app_tool", "switch_to_app_tool", "type_text_tool"))
    do_launch = lambda **k: timed("launch", raw_launch, **k)
    do_switch = lambda **k: timed("switch", raw_switch, **k)
    do_type = lambda **k: timed("type", raw_type, **k)

    saved_state = (dict(o1._last_launched_app), dict(o1._previous_launched_app), list(o1._current_session_actions))
    real = {"alias": o40.VerbAliasEngine.resolve, "popups": o1._check_for_popups, "track": o1._track_launched_app,
            "us_resolve": us.resolve_app, "us_launch": us.launch_hidden}
    checks: List[Tuple[str, bool, str]] = []
    windows: List[EditorWindow] = []
    actions = o1._current_session_actions
    sampler = None

    def typed_records() -> int:
        return sum(1 for a in actions if "TYPE_TEXT" in a)

    def honest_refusal(reply: str) -> bool:
        return bool(re.search(r"\] (FAILED|UNVERIFIED)", reply)) and "Typed via" not in reply

    try:
        # the real alias engine maps an unknown name onto 'google chrome': a test must never launch the user's browser
        o40.VerbAliasEngine.resolve = lambda self, t: t
        o1._check_for_popups = lambda: None                 # desktop-wide popup dismisser: not under test, must not run
        watch = _PointerWatch()
        alpha = EditorWindow("HJ-TY1-Alpha", x=260, y=180).start()
        bravo = EditorWindow("HJ-TY1-Bravo", minimized=True).start()
        charlie = EditorWindow("HJ-TY1-Charlie", kind="refusing", minimized=True).start()
        delta = EditorWindow("HJ-TY1-Delta", kind="swallow", minimized=True).start()
        windows += [alpha, bravo, charlie, delta]
        visible_fixtures = [alpha]        # fixtures that are VISIBLE by design (excluded from the minimized/parked gate)
        call_windows: List[Tuple[float, float, str]] = []

        def timed(name, fn, *a, **k):
            t0 = time.perf_counter()
            try:
                return fn(*a, **k)
            finally:
                call_windows.append((t0, time.perf_counter(), name))
        if not all(w.hwnd for w in windows):
            return TestOutcome(passed=False, env_blocked=True, evidence="could not create the Win32 fixture windows")
        parked_fixtures = [bravo, charlie, delta]
        with _InputSpies({w.hwnd for w in windows}) as spy:
            sampler = _ExposureSampler([w.hwnd for w in windows]).start()

            # control experiment: the instrumentation must SEE an attempt, or "0 attempts" below would prove nothing
            u = ctypes.windll.user32
            u.SetForegroundWindow(alpha.hwnd)
            u.ShowWindow(alpha.hwnd, 9)
            win32gui.ShowWindow(alpha.hwnd, 3)
            u.keybd_event(0, 0, 2, 0)                       # key-up of vk 0: harmless even unguarded, and the guard refuses it
            seen = (len(spy.refused), len(spy.keys), len(hin.VIOLATIONS) - watch.v0)
            checks.append(("instrumentation-sees-raise-and-keystroke-attempts", seen == (3, 1, 1),
                           f"refused/keys/guard-violations={seen} (expected 3/1/1) - so zero below is a real zero"))
            spy.reset()
            watch.v0 = len(hin.VIOLATIONS)

            # 1. launch -> the app is already open and visible: track it, leave it exactly where it is
            a0 = alpha.state()
            r = do_launch(app_name="HJ-TY1-Alpha")
            a1 = alpha.state()
            checks.append(("launch-visible-existing-window-is-tracked-not-raised",
                           o1._last_launched_app.get("hwnd") == alpha.hwnd and a1 == a0 and not a1["zoomed"] and not spy.refused and not spy.keys,
                           f"tracked={o1._last_launched_app.get('hwnd') == alpha.hwnd} state {a0['rect']}->{a1['rect']} zoomed={a1['zoomed']} "
                           f"raise-attempts={spy.refused} key-attempts={spy.keys}"))

            # 2. launch on a MINIMIZED existing window: tracked, stays minimized
            r = do_launch(app_name="HJ-TY1-Bravo")
            b1 = bravo.state()
            checks.append(("launch-minimized-existing-window-stays-minimized",
                           o1._last_launched_app.get("hwnd") == bravo.hwnd and b1["iconic"] and not spy.refused and not spy.keys,
                           f"tracked={o1._last_launched_app.get('hwnd') == bravo.hwnd} minimized={b1['iconic']} raise-attempts={spy.refused}"))

            # 3-4. switch: tracked branch, previous-app branch
            do_switch(app_name="hj-ty1-bravo")
            s_a = (o1._last_launched_app.get("hwnd") == bravo.hwnd, bravo.state()["iconic"])
            r4 = do_switch(app_name="hj-ty1-alpha")
            s_b = (o1._last_launched_app.get("hwnd") == alpha.hwnd, alpha.state() == a0)
            checks.append(("switch-tracked-and-previous-branches-do-not-raise",
                           all(s_a) and all(s_b) and not spy.refused and not spy.keys,
                           f"tracked-branch(now bravo, still minimized)={s_a} previous-branch(now alpha, unmoved)={s_b} raise-attempts={spy.refused}"))

            # 5. type into the VISIBLE editor: lands, verified by an independent WM_GETTEXT read, recorded once
            n0 = typed_records()
            r5 = do_type(text="hello headless")
            truth = alpha.read_text()
            checks.append(("type-visible-editor-lands-and-is-recorded-once",
                           truth == "hello headless" and typed_records() == n0 + 1 and "Typed via" in r5 and alpha.state() == a0
                           and not spy.refused and not spy.keys,
                           f"control reads {truth!r}; TYPE_TEXT records {n0}->{typed_records()}; window unmoved={alpha.state() == a0}; reply={r5[:70]!r}"))

            # 6-7. a control that ACKNOWLEDGES every write and keeps its text: FAILED on both routes, never "typed", never recorded
            do_switch(app_name="hj-ty1-charlie")
            n0 = typed_records()
            r7 = do_type(text="must not be reported")
            r7b = timed("type-posted", o1._type_text_headless, charlie.hwnd, "nor this", "charlie", "HJ-TY1-Charlie", uia_first=False) \
                if hasattr(o1, "_type_text_headless") else ""
            truth7 = charlie.read_text()
            checks.append(("refusing-target-is-FAILED-on-both-routes-not-typed-and-not-recorded",
                           truth7 == "locked" and typed_records() == n0 and honest_refusal(r7) and honest_refusal(r7b) and charlie.state()["iconic"],
                           f"control still reads {truth7!r}; TYPE_TEXT records {n0}->{typed_records()}; minimized again={charlie.state()['iconic']}; "
                           f"UIA-route reply={r7[:100]!r} posted-route reply={r7b[:100]!r}"))

            # 8-9. a window with NO readable text control: the characters ARE delivered, but nothing can prove them -> UNVERIFIED
            do_switch(app_name="hj-ty1-delta")
            n0 = typed_records()
            r9 = do_type(text="zzz")
            checks.append(("delivered-but-unreadable-target-is-UNVERIFIED-not-recorded",
                           typed_records() == n0 and honest_refusal(r9) and delta.state()["iconic"],
                           f"WM_CHAR received by the window={len(delta.chars)} (delivery is not proof); TYPE_TEXT records {n0}->{typed_records()}; reply={r9[:110]!r}"))

            # 10. type into a MINIMIZED editor: parked off-screen for the call, text lands, back to minimized
            do_switch(app_name="hj-ty1-bravo")
            n0 = typed_records()
            r10 = do_type(text="parked text")
            truth10 = bravo.read_text()
            checks.append(("type-minimized-editor-lands-and-ends-minimized",
                           truth10 == "parked text" and typed_records() == n0 + 1 and bravo.state()["iconic"] and not bw.is_parked(bravo.hwnd)
                           and not spy.refused and not spy.keys,
                           f"control reads {truth10!r}; minimized again={bravo.state()['iconic']} still-parked={bw.is_parked(bravo.hwnd)}; reply={r10[:70]!r}"))

            # 11. the posted-message route (post_text to the focused control), forced, verified by the independent read
            fn = getattr(o1, "_type_text_headless", None)
            if fn is None:
                checks.append(("posted-message-route-delivers-and-is-verified", False, "o1._type_text_headless does not exist"))
            else:
                before_txt = alpha.read_text()
                n0 = typed_records()
                r11 = timed("type-posted", fn, alpha.hwnd, "posted ok", "alpha", "HJ-TY1-Alpha", uia_first=False)
                after_txt = alpha.read_text()
                checks.append(("posted-message-route-delivers-and-is-verified",
                               "posted ok" in after_txt and len(after_txt) > len(before_txt) and typed_records() == n0 + 1 and "posted" in r11.lower()
                               and not spy.refused and not spy.keys,
                               f"control {before_txt!r} -> {after_txt!r}; TYPE_TEXT records {n0}->{typed_records()}; reply={r11[:80]!r}"))

            # 12. an app in the Start menu is launched through universal_scan.launch_hidden and stays minimized
            created: Dict[str, Any] = {}

            def fake_launch_hidden(name, timeout_s=45.0):
                w = EditorWindow("HJ-TY1-Echo-Window", minimized=True).start()
                windows.append(w)
                spy.watched.add(w.hwnd)
                sampler.watch(w.hwnd)
                created["w"], created["name"] = w, name
                return {"launched": True, "hwnd": w.hwnd, "title": w.title, "resolved": "HJ TY1 Echo", "notes": []}

            us.resolve_app = lambda n: ("HJ TY1 Echo", "stub-appid") if "echo" in (n or "").lower() else None
            us.launch_hidden = fake_launch_hidden
            n_act = len(actions)
            r12 = do_launch(app_name="HJ-TY1-Echo")
            echo = created.get("w")
            rec12 = [a for a in actions[n_act:] if "LAUNCH_NEW" in a]
            checks.append(("start-menu-app-launches-through-launch_hidden-and-stays-minimized",
                           bool(echo) and o1._last_launched_app.get("hwnd") == echo.hwnd and echo.state()["iconic"]
                           and len(rec12) == 1 and str(echo.hwnd) in rec12[0] and not spy.shell and not spy.spawned and not spy.refused,
                           f"launch_hidden({created.get('name')!r}) called={bool(created)} tracked-its-window={bool(echo) and o1._last_launched_app.get('hwnd') == echo.hwnd} "
                           f"minimized={bool(echo) and echo.state()['iconic']} LAUNCH_NEW records={len(rec12)} legacy ShellExecute calls={len(spy.shell)}"))

            # 13. not in the Start menu: ShellExecute with SW_SHOWMINNOACTIVE; no window ever appears -> UNVERIFIED, nothing recorded
            us.resolve_app = lambda n: None
            o1._track_launched_app = lambda n: None
            spy.shell.clear()
            n_act = len(actions)
            r13 = do_launch(app_name="HJ-TY1-Nothing")
            rec13 = [a for a in actions[n_act:] if "LAUNCH_NEW" in a]
            checks.append(("fallback-launch-is-minimized-and-a-window-that-never-appears-is-not-a-launch",
                           len(spy.shell) == 1 and spy.shell[0][-1] == 7 and not rec13 and honest_refusal(r13),
                           f"ShellExecute calls={len(spy.shell)} showcmd={[c[-1] for c in spy.shell]} (7 = SW_SHOWMINNOACTIVE) LAUNCH_NEW records={len(rec13)} reply={r13[:100]!r}"))

            # 14. the legacy window tracker (used by that fallback) no longer restores / foregrounds / re-centres
            o1._track_launched_app = real["track"]
            a0 = alpha.state()
            spy.reset()
            timed("track", o1._track_launched_app, "hj-ty1-alpha")
            a1 = alpha.state()
            checks.append(("window-tracker-finds-the-window-without-raising-it",
                           o1._last_launched_app.get("hwnd") == alpha.hwnd and a1 == a0 and not spy.refused,
                           f"tracked={o1._last_launched_app.get('hwnd') == alpha.hwnd} state {a0['rect']}->{a1['rect']} raise-attempts={spy.refused}"))

            # 15. a window that merely LOOKS like the target is the user's: hygiene must not blank, reset or close it
            look = EditorWindow("HJ-Hyg untitled", x=330, y=230).start()
            windows.append(look)
            visible_fixtures.append(look)
            spy.watched.add(look.hwnd)
            seed = ctypes.create_unicode_buffer("user text")
            look._sup.user32.SendMessageW(look.edit, 0x000C, 0, ctypes.addressof(seed))   # WM_SETTEXT on OUR fixture
            time.sleep(0.2)
            timed("hygiene", o1._clean_slate_app_hygiene, "hj-hyg")
            alive15 = bool(_u32.IsWindow(look.hwnd))
            checks.append(("hygiene-leaves-a-look-alike-window-it-did-not-launch-alone",
                           alive15 and look.read_text() == "user text" and not spy.refused,
                           f"alive={alive15} text={look.read_text() if alive15 else None!r} (a window titled 'untitled' for an unlaunched app used to be WM_CLOSEd)"))

            # 16. popup ownership: only the driven app's popups / windows we launched may ever be dismissed
            ours_before = o1._popup_is_ours(look.hwnd)
            bw.mark_ours(look.hwnd)
            ours_after = o1._popup_is_ours(look.hwnd)
            checks.append(("popup-dismisser-only-touches-popups-it-owns", (not ours_before) and ours_after,
                           f"look-alike window owned before={ours_before} after we launched it={ours_after}"))

            # 17. the 'focus' helper names the window and does not raise it
            o1._last_launched_app["hwnd"] = alpha.hwnd
            a0 = alpha.state()
            r_before = len(spy.refused)
            named = timed("focus-helper", o1._focus_most_recent_app_window)
            checks.append(("focus-helper-names-the-window-without-raising-it",
                           named == "HJ-TY1-Alpha" and alpha.state() == a0 and not spy.refused[r_before:],
                           f"returned {named!r}; raise-attempts={spy.refused[r_before:]}"))

            # 18. source-level guard: no physical key API, no show/restore/maximize, no image-name taskkill of a user app in organ_01
            import ast as _ast
            with open(o1.__file__, encoding="utf-8") as fh:
                tree = _ast.parse(fh.read())
            bad: List[Tuple[Any, int]] = []
            for node in _ast.walk(tree):
                if isinstance(node, _ast.Attribute) and node.attr in ("keybd_event", "SetForegroundWindow", "SwitchToThisWindow"):
                    bad.append((node.attr, node.lineno))
                if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Attribute) and node.func.attr == "ShowWindow" and len(node.args) >= 2:
                    a = node.args[1]
                    v = a.value if isinstance(a, _ast.Constant) else (a.attr if isinstance(a, _ast.Attribute) else None)
                    if v in (1, 3, 4, 5, 8, 9, 10, "SW_RESTORE", "SW_MAXIMIZE", "SW_SHOW", "SW_SHOWNORMAL", "SW_SHOWNOACTIVATE"):
                        bad.append(("ShowWindow", node.lineno))
                if isinstance(node, _ast.Call) and node.args and isinstance(node.args[0], _ast.List):
                    items = [e.value for e in node.args[0].elts if isinstance(e, _ast.Constant)]
                    if "taskkill" in items and "ollama.exe" not in items:
                        bad.append(("taskkill", node.lineno))
            checks.append(("organ_01-source-has-no-key-injection-raise-restore-or-user-app-taskkill", not bad,
                           f"offending call sites: {bad if bad else 'none'} (the only taskkill left restarts ollama.exe, a service)"))

            sampler.stop()
            exposure = {w.title[7:]: (round(sampler.exposed_s.get(w.hwnd, 0) * 1000), sampler.fg_hits.get(w.hwnd)) for w in windows}
            parked_ok = all(sampler.exposed_s.get(w.hwnd, 0) <= 0.12 for w in windows if w not in visible_fixtures)
            checks.append(("parked-windows-never-shown-and-nothing-became-foreground",
                           parked_ok and all(v == 0 for v in sampler.fg_hits.values()) and all(w.state()["iconic"] for w in windows if w not in visible_fixtures)
                           and not any(bw.is_parked(w.hwnd) for w in windows),
                           f"{sampler.samples} samples; (ms a non-minimized window overlapped a monitor by >1 px, samples as foreground) per window = {exposure}; "
                           f"gate <= 120 ms per window (the documented park floor is ~40-110 ms); all minimized again, none left parked"))
            checks.append(("no-physical-input-or-raise-attempt-in-any-step",
                           not spy.refused and not spy.keys and not spy.spawned,
                           f"raise/restore/maximize attempts={spy.refused} keystroke/mouse attempts={spy.keys} spawned processes={spy.spawned}"))
        # pointer: the hard evidence is the input guard (every physical-input API refuses AND records) plus the spies'
        # key/mouse counters. The cursor itself is REPORTED, not gated: the tool calls cover almost the whole run, so
        # "moved during a call" cannot tell a tool from a human hand using the mouse (measured: 168 changes with 0
        # guard violations and 0 key/mouse API attempts in one run; the cause was not established, the two earlier isolated runs saw 0 changes).
        covered = sum(t1 - t0 for t0, t1, _n in call_windows)
        dv = len(hin.VIOLATIONS) - watch.v0
        checks.append(("physical-pointer-untouched-and-no-guard-violations",
                       dv == 0 and not spy.keys,
                       f"guard violations+={dv}; key/mouse API attempts={len(spy.keys)}; cursor changes observed={len(sampler.pointer_moves)} "
                       f"(informational: tool calls covered {covered:.1f}s of the run, so any movement is not attributable; "
                       f"0 changes means nothing moved it at all)"))
    finally:
        if sampler is not None:
            sampler.stop()
        o40.VerbAliasEngine.resolve = real["alias"]
        o1._check_for_popups = real["popups"]
        o1._track_launched_app = real["track"]
        us.resolve_app, us.launch_hidden = real["us_resolve"], real["us_launch"]
        o1._last_launched_app.clear(); o1._last_launched_app.update(saved_state[0])
        o1._previous_launched_app.clear(); o1._previous_launched_app.update(saved_state[1])
        actions[:] = saved_state[2]
        for w in windows:
            try:
                w.stop()
            except Exception:
                pass
    return TestOutcome(passed=all(ok for _n, ok, _d in checks), evidence=_fmt(checks, 330)[:5200],
                       metrics={"checks": f"{sum(1 for _n, ok, _d in checks if ok)}/{len(checks)}"})


# ----------------------------------------------------------------------------------------------- Job 1 (the eyes)

def run_eye1(TestOutcome):
    """EYE1: the eyes do not flicker - 300 headless captures of ONE parked window in a long-lived process, with real UIA
    walks interleaved, never comes back blank and never grows the process's GDI/USER budget"""
    from core_organs import headless_input as hin, universal_scan as us, background_window as bw
    from core_organs import desktop_grounding as dg

    n_captures = 300
    before = _top_hwnds()
    watch = _PointerWatch()
    info = us.launch_hidden("notepad")
    hwnd = int(info.get("hwnd") or 0)
    if not hwnd:
        return TestOutcome(passed=False, env_blocked=True,
                           evidence=f"could not start a hidden Notepad: {info.get('notes')}")
    checks: List[Tuple[str, bool, str]] = []
    metrics: Dict[str, Any] = {}
    g = dg.DesktopGrounding()
    hin.CAPTURE_LOG.clear()
    g0 = hin._gui_objects()
    try:
        with bw.BackgroundSession(hwnd) as bg:
            # let it paint once before the soak (the loop does the same settling); bounded wait, honest on failure
            img, note = (None, "")
            t_end = time.perf_counter() + 8.0
            while img is None and time.perf_counter() < t_end:
                img, note = hin.capture_window(hwnd)
                if img is None:
                    time.sleep(0.25)
            checks.append(("parked-window-paints-at-all", img is not None,
                           f"mode={bg.mode} where={hin.CAPTURE_DIAG.get('where')} note={note[:120]}"))
            ref = img
            blanks: List[str] = []
            min_px, sizes, stale = 1.0, set(), 0
            t0 = time.perf_counter()
            for i in range(n_captures):
                if i % 10 == 0:                      # the session's real load: UIA walks alongside the captures
                    try:
                        g._walk_uia(hwnd)
                    except Exception:
                        pass
                img, note = hin.capture_window(hwnd)
                if img is None:
                    blanks.append(f"#{i}:{note[:150]}")
                    continue
                d = hin.CAPTURE_DIAG
                min_px = min(min_px, float(d.get("px") or 0.0))
                sizes.add(img.size)
                if ref is not None and img.tobytes() == ref.tobytes():
                    stale += 1                        # informational: a parked app that never repaints is not a bug
            dur = time.perf_counter() - t0
            g1 = hin._gui_objects()
            logged = [e for e in hin.CAPTURE_LOG if e.get("hwnd") == hwnd]
            checks.append((f"no-blank-in-{n_captures}-captures", not blanks,
                           f"blanks={len(blanks)} first={blanks[0] if blanks else '-'} "
                           f"min_nonzero_pixel_fraction={min_px:.3f} sizes={sorted(sizes)} "
                           f"CAPTURE_LOG_for_this_window={len(logged)}"))
            checks.append(("gdi-user-budget-not-creeping", g0[0] >= 0 and (g1[0] - g0[0]) <= 60 and (g1[1] - g0[1]) <= 60,
                           f"gdi {g0[0]}->{g1[0]} ({g1[0] - g0[0]:+d}), user {g0[1]}->{g1[1]} ({g1[1] - g0[1]:+d}); "
                           f"the OS caps a process near 10k of each - the ceiling that would blind every later capture"))
            checks.append(("captures-kept-the-window-own-content", bool(sizes) and min_px > 0.0,
                           f"{n_captures - len(blanks)} images, sizes={sorted(sizes)}, identical-to-first={stale} "
                           f"(a parked app legitimately stops repainting; only a blank is a defect)"))
            checks.append(watch.check())
            metrics.update(captures=n_captures, blanks=len(blanks), min_px=round(min_px, 4),
                           gdi=f"{g0[0]}->{g1[0]}", user=f"{g0[1]}->{g1[1]}",
                           secs=round(dur, 1), where=hin.CAPTURE_DIAG.get("where"))
    finally:
        _close_new_windows(before, "Notepad")
    return TestOutcome(passed=all(ok for _n, ok, _d in checks), evidence=_fmt(checks, 260)[:3000], metrics=metrics)
