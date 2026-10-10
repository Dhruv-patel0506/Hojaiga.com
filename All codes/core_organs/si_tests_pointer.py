"""
si_tests_pointer -- tests for the VIRTUAL MOUSE (professor.pointer) - registered into the Professor suite through si_tests_apprun.TESTS:

  PR72  the event scripts of every verb (click x1/x2/x3, right / middle, hold, drag, drag-select, lasso, flick, drop, wheel both axes, modifiers): order, buttons, timing, geometry - pure
  PR73  delivery of posted messages to a real classic-toolkit window (WinForms lab target): what the window RECEIVED matches what was sent, the person's cursor never moved
  PR74  the in-process pointer agent: a WPF window that ignores posted messages accepts them once its polling answers with the virtual pointer; OLE drag-and-drop between two controls; the
        agent swallows SetCursorPos / ClipCursor / mouse SendInput (the application can never move the person's cursor)
  PR75  route policy: learned order, routes closed after failure, touch only for pointer-aware toolkits, shim only for owned instances, nothing delivered when input is not allowed, the
        gesture driver compiles each guide gesture to the right verb
The lab targets (professor/lab/*.cs) are compiled with the .NET Framework compiler that ships with Windows and run PARKED far off-screen (never shown, never activated). A test that needs
a missing piece (compiler, frida) reports ENV-BLOCKED, never a pass.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from types import SimpleNamespace as NS

for _p in (r"D:\new_automation", r"D:\new_automation\All codes", r"D:\new_automation\All codes\core_organs"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from si_tests_apprun import _verdict, TestOutcome  # type: ignore
except Exception:                                        # pragma: no cover
    from core_organs.si_tests_apprun import _verdict, TestOutcome  # type: ignore


class _Fx:
    allowed = True
    owned = True

    def why_not(self) -> str:
        return ""


class _Closed:
    allowed = False
    owned = False

    def why_not(self) -> str:
        return "input not enabled (allow_input is off)"


def _env_blocked(why: str) -> "TestOutcome":
    o = TestOutcome(False, "ENV-BLOCKED: " + why)
    o.env_blocked = True
    return o


def _scratch_traits():
    """Point the pointer's learned-route file at a scratch folder for the length of a test."""
    from core_organs.professor import config as CFG
    old = CFG.DATA_DIR
    CFG.DATA_DIR = tempfile.mkdtemp(prefix="hojaiga_ptr_")
    return old


def _kinds(ev):
    out = {}
    for e in ev:
        k = e["kind"].split(":")[0]
        if k in ("down", "up"):
            k += ":" + (e.get("btn") or e["kind"].split(":")[-1])
        out[k] = out.get(k, 0) + 1
    return out


# ------------------------------------------------------------------------------------------------------------------------------------------ PR72
def run_pr72() -> "TestOutcome":
    """PR72: every mouse verb compiles to an ordered event script - buttons pressed before they are released, moves only while held for drags, double clicks marked, a drop rests over its target"""
    from core_organs.professor import pointer as PT
    c1 = PT.s_click(100, 100)
    c2 = PT.s_click(100, 100, count=2)
    c3 = PT.s_click(100, 100, "right", count=3)
    mid = PT.s_click(5, 5, "middle")
    mods = PT.s_click(5, 5, mods=("shift", "ctrl"))
    hold = PT.s_hold(10, 10, 0.8)
    drag = PT.s_drag([(0, 0), (300, 100)], "left", duration=0.5)
    path = PT.s_drag([(0, 0), (50, 10), (100, 40), (150, 90)], "middle", ("shift",))
    sel = PT.s_drag_select((10, 10), (200, 120))
    flick = PT.s_flick(50, 50, "left", 200, 80)
    drop = PT.s_drop((20, 20), (400, 200), hover=0.4)
    wheel = PT.s_wheel(30, 30, -3)
    hwheel = PT.s_wheel(30, 30, 2, horizontal=True)
    hover = PT.s_hover(7, 7, 0.5)

    def order_ok(sc):
        held = set()
        for e in sc:
            if e.kind == "down":
                if e.button in held:
                    return False
                held.add(e.button)
            elif e.kind == "up":
                if e.button not in held:
                    return False
                held.discard(e.button)
        return not held

    def moves_between(sc, held_button):
        inside, bad = False, 0
        for e in sc:
            if e.kind == "down":
                inside = True
            elif e.kind == "up":
                inside = False
            elif e.kind == "move" and inside and e.button != held_button:
                bad += 1
        return bad == 0

    g = PT.glide((0, 0), (300, 0), 10.0)
    gaps = [g[0][0]] + [g[i][0] - g[i - 1][0] for i in range(1, len(g))]
    x0, y0, x1, y1 = PT.script_bbox(drag, 0)
    checks = {"every_script_balanced": all(order_ok(s) for s in (c1, c2, c3, mid, mods, hold, drag, path, sel, flick, drop)),
              "click_is_move_down_up": [e.kind for e in c1][-2:] == ["down", "up"] and sum(1 for e in c1 if e.kind == "down") == 1,
              "double_click_second_press_marked": [e.dbl for e in c2 if e.kind == "down"] == [False, True],
              "triple_click_alternates": [e.dbl for e in PT.s_click(1, 1, count=3) if e.kind == "down"] == [False, True, False],
              "right_and_middle_buttons": all(e.button == "right" for e in c3 if e.kind in ("down", "up")) and all(e.button == "middle" for e in mid if e.kind in ("down", "up")),
              "modifiers_on_every_event": all(set(e.mods) == {"shift", "ctrl"} for e in mods) and all(e.mods == ("shift",) for e in path),
              "hold_lasts": PT.script_duration(hold) >= 0.8 and hold[-1].kind == "up",
              "drag_follows_straight_line": len(drag) > 20 and PT.script_points(drag)[0] == (0.0, 0.0) and PT.script_points(drag)[-1] == (300.0, 100.0) and (x0, y0, x1, y1) == (0, 0, 300, 100),
              "drag_moves_carry_the_held_button": moves_between(drag, "left") and moves_between(path, "middle") and moves_between(drop, "left"),
              "path_drag_visits_every_point": [(e.x, e.y) for e in path if e.kind == "move" and e.button][-1] == (150.0, 90.0) and len([e for e in path if e.kind == "move" and e.button]) == 3,
              "drag_select_is_a_left_drag": all(e.button == "left" for e in sel if e.kind in ("down", "up")) and PT.script_points(sel)[-1] == (200.0, 120.0),
              "flick_is_short_and_released_moving": PT.script_duration(flick) <= 0.12 and flick[-1].kind == "up" and flick[-1].x < flick[1].x,
              "drop_passes_threshold_then_rests_on_target": abs(drop[2].x - drop[1].x) >= 6 and drop[-2].dt >= 0.4 and (drop[-2].x, drop[-2].y) == (400.0, 200.0) and (drop[-1].x, drop[-1].y) == (400.0, 200.0),
              "wheel_notches": [e.delta for e in wheel if e.kind == "wheel"] == [-120, -120, -120] and [e.delta for e in hwheel if e.kind == "hwheel"] == [120, 120],
              "hover_rests": PT.script_duration(hover) >= 0.5 and all(e.kind == "move" for e in hover),
              "glide_eases_and_ends_on_target": g[-1] == (300.0, 0.0) and gaps[0] < max(gaps) and len(g) >= 20}
    return _verdict(checks, f"click={len(c1)} events, drag={len(drag)}, drop={len(drop)}, glide gaps {min(gaps):.1f}..{max(gaps):.1f}px")


# ------------------------------------------------------------------------------------------------------------------------------------------ PR73
def run_pr73() -> "TestOutcome":
    """PR73: posted delivery to a classic-toolkit window (WinForms): click / right / middle / double / drag / flick / wheel (with Ctrl) arrive as sent; the person's cursor is not moved"""
    from core_organs.professor.lab import labkit as LK
    ok, why = LK.ensure_built(("winforms_aware",))
    if not ok:
        return _env_blocked(why)
    old = _scratch_traits()
    from core_organs.professor import pointer as PT, config as CFG
    lab = None
    try:
        lab = LK.Lab("winforms_aware")
        if not lab.hwnd:
            return _env_blocked("the lab window did not start")
        ox, oy = LK.client_origin(lab.hwnd)
        cx, cy = ox + 200, oy + 160
        vp = PT.VirtualPointer(lab.hwnd, "lab_wf", _Fx(), only=["posted"])
        got = {}
        moved = False
        for verb, fn in (("click", lambda: vp.click(cx, cy)), ("right", lambda: vp.right_click(cx, cy)), ("middle", lambda: vp.middle_click(cx, cy)), ("double", lambda: vp.double_click(cx, cy)),
                         ("drag", lambda: vp.drag((cx, cy), (cx + 250, cy + 120))), ("flick", lambda: vp.flick(cx, cy, "right", 200)), ("wheel", lambda: vp.wheel(cx, cy, 2)),
                         ("ctrl_wheel", lambda: vp.wheel(cx, cy, 1, mods=("ctrl",)))):
            m = lab.mark()
            with PT.CursorWatch() as cw:
                r = fn()
            time.sleep(0.25)
            got[verb] = (r, lab.since(m))
            moved = moved or (cw.moved and not cw.real_input_seen)
        k = {v: _kinds(ev) for v, (_r, ev) in got.items()}
        checks = {"left_click": k["click"].get("down:Left") == 1 and k["click"].get("up:Left") == 1 and k["click"].get("click", 0) >= 1,
                  "right_click": k["right"].get("down:Right") == 1 and k["right"].get("up:Right") == 1,
                  "middle_click": k["middle"].get("down:Middle") == 1,
                  "double_click": k["double"].get("dblclick", 0) >= 1,
                  "drag_moves_arrive": k["drag"].get("move", 0) >= 8 and k["drag"].get("down:Left") == 1 and k["drag"].get("up:Left") == 1,
                  "flick_released_moving": k["flick"].get("move", 0) >= 4 and k["flick"].get("up:Left") == 1,
                  "wheel_arrives": k["wheel"].get("wheel", 0) == 2 and all(e["delta"] > 0 for e in got["wheel"][1] if e["kind"].startswith("wheel")),
                  "ctrl_held_during_wheel": any("Control" in e.get("mods", "") for e in got["ctrl_wheel"][1] if e["kind"].startswith("wheel")),
                  "positions_match": all(abs(e["x"] - 192) < 25 for e in got["click"][1] if e["kind"].startswith("down")),
                  "cursor_never_moved": not moved,
                  "route_remembered": PT.load_traits("lab_wf").get("posted") in ("ok", "delivered")}
        vp.close()
        return _verdict(checks, f"received: click={k['click']}, drag moves={k['drag'].get('move', 0)}, wheel={k['wheel']}")
    finally:
        CFG.DATA_DIR = old
        if lab is not None:
            lab.close()


# ------------------------------------------------------------------------------------------------------------------------------------------ PR74
def run_pr74() -> "TestOutcome":
    """PR74: the in-process pointer agent - a WPF window gets nothing from posted messages and everything once its polling is answered; OLE drag-and-drop runs; the application cannot move the cursor"""
    from core_organs.professor.lab import labkit as LK
    from core_organs.professor import pointer as PT, config as CFG
    ok_f, why_f = PT.InprocAgent.available()
    if not ok_f:
        return _env_blocked(why_f)
    ok, why = LK.ensure_built(("wpf", "winforms_aware"))
    if not ok:
        return _env_blocked(why)
    old = _scratch_traits()
    wpf = wf = None
    try:
        wpf = LK.Lab("wpf")
        wf = LK.Lab("winforms_aware")
        if not (wpf.hwnd and wf.hwnd):
            return _env_blocked("a lab window did not start")
        ox, oy = LK.client_origin(wpf.hwnd)
        cx, cy = ox + 200, oy + 160
        # 1 posted alone: WPF ignores it
        vp = PT.VirtualPointer(wpf.hwnd, "lab_wpf", _Fx(), only=["posted"])
        m = wpf.mark()
        vp.click(cx, cy)
        vp.drag((cx, cy), (cx + 200, cy + 80))
        time.sleep(0.3)
        posted_events = len(wpf.since(m))
        vp.close()
        # 2 with the agent: all arrives, the app's own polling sees the virtual pointer
        vp = PT.VirtualPointer(wpf.hwnd, "lab_wpf", _Fx(), only=["shim"])
        m = wpf.mark()
        with PT.CursorWatch() as cw:
            vp.click(cx, cy)
            vp.right_click(cx, cy)
            vp.drag((cx, cy), (cx + 250, cy + 120))
        time.sleep(0.3)
        ev = wpf.since(m)
        k = _kinds(ev)
        polled = [(e["poll_x"], e["poll_y"]) for e in ev if e["kind"].startswith("down")]
        agent = vp.agent
        hooked = list(agent.hooked) if agent else []
        # 3 modifiers through the agent
        m = wpf.mark()
        vp.click(cx, cy, mods=("shift",))
        time.sleep(0.2)
        mod_seen = any("Shift" in e.get("mods", "") for e in wpf.since(m) if e["kind"].startswith("down"))
        vp.close()
        # 4 OLE drag and drop in WinForms
        ox2, oy2 = LK.client_origin(wf.hwnd)
        vp2 = PT.VirtualPointer(wf.hwnd, "lab_wf2", _Fx(), only=["shim"])
        m2 = wf.mark()
        vp2.drag_drop((ox2 + 80, oy2 + 40), (ox2 + 750, oy2 + 200))
        time.sleep(0.4)
        dd = [e["kind"] for e in wf.since(m2) if not e["kind"].startswith("move")]
        vp2.close()
        checks = {"posted_alone_is_ignored_by_wpf": posted_events == 0,
                  "agent_hooks_polling_calls": all(h in hooked for h in ("GetCursorPos", "GetAsyncKeyState", "GetKeyState", "GetMessagePos")),
                  "agent_guards_the_persons_cursor": all(h in hooked for h in ("SetCursorPos", "ClipCursor", "SendInput")),
                  "wpf_receives_click_right_drag": k.get("down:Left", 0) >= 2 and k.get("down:Right", 0) == 1 and k.get("move", 0) >= 8,
                  "app_polls_the_virtual_pointer": bool(polled) and all(abs(px - (cx)) < 300 and py != 0 for px, py in polled),
                  "modifier_seen_by_wpf": mod_seen,
                  "ole_drag_and_drop_completed": "dragenter" in dd and "drop" in dd,
                  "cursor_never_moved": not (cw.moved and not cw.real_input_seen)}
        return _verdict(checks, f"wpf posted-only events={posted_events}; with agent={k}; hooked={len(hooked)}; drop events={dd}")
    finally:
        CFG.DATA_DIR = old
        for lab in (wpf, wf):
            if lab is not None:
                lab.close()


# ------------------------------------------------------------------------------------------------------------------------------------------ PR75
def run_pr75() -> "TestOutcome":
    """PR75: route policy - learned order, a route closed after failure, touch only for pointer-aware toolkits, nothing sent when input is not allowed, the agent only into owned processes, guide gestures -> verbs"""
    from core_organs.professor import pointer as PT, gestures as GE, config as CFG
    old = _scratch_traits()
    try:
        PT.save_trait("app_a", "posted", "ignored")
        PT.save_trait("app_a", "shim", "ok")
        PT.save_trait("app_b", "touch", "moves_cursor")
        PT.save_trait("app_c", "touch", "ok")
        sc = PT.s_click(1, 1)
        wheel = PT.s_wheel(1, 1, 2)

        def vp(key, owned=True, **kw):
            fx = NS(allowed=True, owned=owned, why_not=lambda: "")
            return PT.VirtualPointer(0, key, fx, **kw)
        a, b, c, d = vp("app_a"), vp("app_b"), vp("app_c"), vp("app_d")
        d.hwnd = 0
        not_owned = vp("app_e", owned=False)
        a_order, c_order = a.order(sc), c.order(sc)
        real_aware = PT.pointer_aware
        PT.pointer_aware = lambda h: (False, "classic")
        try:
            plain_order = d.order(sc)
            probe_order = vp("app_f", probe_touch=True).order(sc)
        finally:
            PT.pointer_aware = real_aware
        PT.pointer_aware = lambda h: (True, "xaml")
        try:
            aware_order = vp("app_g").order(sc)
        finally:
            PT.pointer_aware = real_aware
        closed = PT.VirtualPointer(0, "app_h", _Closed())
        r_closed = closed.click(10, 10)
        # a refusing effector sends nothing and says why
        sent = []
        real_post = PT._u
        # the gesture driver: kind -> verb on a recording pointer
        calls = []

        class _Rec:
            def __getattr__(self, name):
                def fn(*a, **k):
                    calls.append((name, a[:2] if name in ("drag", "wheel") else (), a[3] if (name == "drag" and len(a) > 3) else k.get("mods", ())))
                    return PT.PointerResult(True, "posted", "recorded", 0.0, True, False, [])
                return fn
        node = NS(role="pane", ctype="PaneControl", name="canvas", offscreen=False, rect=(0, 0, 800, 600), enabled=True)
        drv = GE.GestureDriver("app_x", 1, NS(allowed=True, owned=True, why_not=lambda: ""), lambda: [node])
        drv.vp = _Rec()
        real_rect = GE._u
        GE._u = NS(GetWindowRect=lambda h, ref: 0, GetAncestor=real_rect.GetAncestor, WindowFromPoint=real_rect.WindowFromPoint)
        try:
            for kind in ("orbit", "pan", "zoom", "scroll", "stroke", "select_area", "drop", "flick", "double_click", "right_click", "hover", "drag"):
                drv.perform(kind)
        finally:
            GE._u = real_rect
        verbs = [c_[0] for c_ in calls]
        mods_pan = [c_[2] for c_ in calls if c_[0] == "drag"][1]
        checks = {"learned_shim_first_when_posted_ignored": a_order[0] == "shim" and "posted" not in a_order,
                  "touch_closed_after_it_moved_the_cursor": "touch" not in b.order(sc),
                  "touch_kept_when_measured_ok": "touch" in c_order,
                  "touch_not_tried_on_unknown_toolkit": "touch" not in plain_order,
                  "touch_probe_is_explicit": "touch" in probe_order,
                  "touch_offered_for_pointer_aware_toolkit": "touch" in aware_order,
                  "shim_never_into_a_borrowed_window": "shim" not in not_owned.order(sc) and "shim" in a.order(sc),
                  "wheel_gets_the_uia_scroll_route": "uia" in a.order(wheel) and "uia" not in a.order(sc),
                  "refused_when_input_is_off": (not r_closed.ok) and "refused" in r_closed.note,
                  "guide_gestures_become_verbs": verbs == ["drag", "drag", "wheel", "wheel", "stroke", "drag_select", "drag_drop", "flick", "double_click", "right_click", "hover", "drag"],
                  "pan_holds_shift": mods_pan == ("shift",),
                  "gesture_words_cover_the_verbs": [GE.kind_of(t) for t in ("Right-click the cube", "Double-click the title", "Drag and drop the file", "Swipe left", "Hover over the icon", "Scroll down")]
                  == ["right_click", "double_click", "drop", "flick", "hover", "scroll"]}
        return _verdict(checks, f"a={a_order} c={c_order} plain={plain_order} verbs={verbs}")
    finally:
        CFG.DATA_DIR = old




# ------------------------------------------------------------------------------------------------------------------------------------------ PR76
def run_pr76() -> "TestOutcome":
    """PR76: what the virtual mouse learns - a route is recorded as ignored only by CONTRAST (another route made the effect twice), never because a gesture changed nothing; legacy facts are honoured"""
    import json
    from core_organs.professor import pointer as PT, config as CFG
    old = _scratch_traits()
    try:
        class _R:
            def __init__(self, name):
                self.name = name

            def deliver(self, script):
                return PT.Delivery(True, f"{self.name} delivered")

        def make(key, effects, order=("posted", "shim"), fixed=True):
            """A pointer whose routes always deliver; `effects[route]` is what the effect check says for that route (True / False)."""
            fx = NS(allowed=True, owned=True, why_not=lambda: "")
            vp = PT.VirtualPointer(0, key, fx, only=list(order) if fixed else ())
            vp.allowed = lambda: (True, "")
            state = {"route": ""}
            vp._route_obj = lambda name: (_R(name), "")
            vp._glide = lambda s: None
            orig_perform = vp.perform

            def verify_for():
                return lambda: effects.get(state["route"])
            # the verdict is taken per delivered route: wrap deliver so the verifier knows which route ran
            vp._route_obj = lambda name: (type("RR", (), {"deliver": lambda s_, sc, n=name: (state.__setitem__("route", n) or PT.Delivery(True, f"{n} delivered"))})(), "")
            return vp, verify_for()
        sc = PT.s_click(10, 10)
        # 1 nothing has an effect: nothing is learned
        vp, ver = make("n1", {"posted": False, "shim": False})
        r1 = vp.perform(sc, "click", verify=ver)
        r1b = vp.perform(sc, "click", verify=ver)
        learned_none = PT.load_traits("n1")
        # 2 shim works where posted does not: first time not persisted, second time posted becomes 'ignored'
        vp, ver = make("n2", {"posted": False, "shim": True})
        a = vp.perform(sc, "click", verify=ver)
        after_one = dict(PT.load_traits("n2"))
        b = vp.perform(sc, "click", verify=ver)
        after_two = dict(PT.load_traits("n2"))
        # 3 a route that has worked is never downgraded by a gesture that did nothing
        PT.save_trait("n3", "posted", "ok")
        vp, ver = make("n3", {"posted": False, "shim": False})
        vp.perform(sc, "click", verify=ver)
        vp.perform(sc, "click", verify=ver)
        n3 = PT.load_traits("n3")
        # 4 the caller's 'no effect' demotes a route for the session only
        vp, ver = make("n4", {"posted": True, "shim": True}, fixed=False)
        vp.perform(sc, "click", verify=ver)
        vp.note_ineffective()
        order_after = vp.order(sc)
        persisted_n4 = PT.load_traits("n4")
        # 5 legacy facts
        path = os.path.join(CFG.DATA_DIR, "app_traits.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"old_a": {"posted_pointer": False, "touch_moves_cursor": False}, "old_b": {"touch_moves_cursor": True}}, fh)
        la, lb = PT.load_traits("old_a"), PT.load_traits("old_b")
        # 6 an empty ladder says WHY
        PT.save_trait("n6", "posted", "ignored")
        PT.save_trait("n6", "shim", "unavailable")
        v6 = PT.VirtualPointer(0, "n6", NS(allowed=True, owned=True, why_not=lambda: ""), allow_touch=False)
        v6.allowed = lambda: (True, "")
        r6 = v6.perform(sc, "click", verify=lambda: True)
        checks = {"no_effect_anywhere_teaches_nothing": r1.ok is False and r1b.ok is False and learned_none == {},
                  "contrast_needs_two_observations": a.ok and a.route == "shim" and after_one.get("posted") is None and b.ok and after_two.get("posted") == "ignored" and after_two.get("shim") == "ok",
                  "a_route_that_worked_is_kept": n3.get("posted") == "ok",
                  "caller_no_effect_demotes_for_the_session": order_after[:2] == ["shim", "posted"],
                  "session_demotion_is_not_persisted": persisted_n4.get("posted") in (None, "delivered", "ok") and "ignored" not in persisted_n4.values(),
                  "legacy_facts_honoured": la.get("posted") == "ignored" and la.get("touch") == "ok" and lb.get("touch") == "moves_cursor",
                  "empty_ladder_gives_the_reason": (not r6.ok) and "posted: ignored" in r6.note and "shim: unavailable" in r6.note}
        return _verdict(checks, f"a.tried={a.tried}; after_two={after_two}; r6={r6.note[:100]}")
    finally:
        CFG.DATA_DIR = old




# ------------------------------------------------------------------------------------------------------------------------------------------ PR77
def run_pr77() -> "TestOutcome":
    """PR77: where a drawing area is when the tree does not name it - the largest block of the window no control covers; a tiny pane is not mistaken for the canvas"""
    from core_organs.professor import gestures as GE

    def ctl(role, l, t, r, b):
        return NS(role=role, offscreen=False, rect=(l, t, r, b), name="c")
    win = (0, 0, 1000, 700)
    bars = [ctl("button", 0, 0, 1000, 100), ctl("listitem", 0, 100, 200, 700)]
    surf, how = GE.surface_of(bars, win)
    tiny = NS(role="pane", offscreen=False, rect=(500, 300, 532, 330), name="")
    surf_t, _ = GE.surface_of(bars + [tiny], win)
    big_node = NS(role="pane", offscreen=False, rect=(220, 120, 980, 690), name="canvas")
    surf_n, how_n = GE.surface_of(bars + [big_node], win)
    right_bar = bars + [ctl("button", 800, 100, 1000, 700)]
    surf_r, _ = GE.surface_of(right_bar, win)
    free = GE.free_rect([], win)
    checks = {"canvas_is_the_empty_block": surf is not None and surf[0] >= 200 and surf[1] >= 100 and surf[2] >= 950 and surf[3] >= 650 and "no control covers" in how,
              "a_tiny_pane_is_not_the_canvas": surf_t == surf,
              "a_real_canvas_node_wins": surf_n == (220, 120, 980, 690) and "tree" in how_n,
              "a_second_bar_shrinks_it": surf_r is not None and surf_r[2] <= 800 and surf_r[0] >= 200,
              "an_empty_window_is_all_canvas": free is not None and free[2] - free[0] > 900 and free[3] - free[1] > 600}
    return _verdict(checks, f"surface={surf} ({how}); with a right bar={surf_r}")


TESTS = [("PR72", run_pr72), ("PR73", run_pr73), ("PR74", run_pr74), ("PR75", run_pr75), ("PR76", run_pr76), ("PR77", run_pr77)]
