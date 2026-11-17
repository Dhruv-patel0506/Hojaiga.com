"""
try_app_show_desktop -- the desktop half of `try_app --show`: the first-contact scan done WITH the window visible, then the virtual cursor shows you what was found.

  1 LAUNCH + SCAN   the app opens on the left of your screen (not minimized, not parked); its control tree is read and its menus / ribbon tabs are expanded where you can see them
  2 WALKTHROUGH     the VIRTUAL CURSOR (the Professor's click-through pointer: it never takes focus, never moves your real mouse, never appears in screenshots) glides to each region and then to
                    its most informative controls - those with a shortcut, a tooltip, then the rest. NOTHING is outlined, boxed or highlighted; the cursor is the only pointing aid and the names
                    are printed in the terminal.
  3 CLOSE           the app is closed again if THIS run launched it; an app that was already open is left alone

Where the cursor goes comes from a FRESH accessibility read of the live window taken just before the walkthrough (not from rectangles stored at scan time), so it lands on the control
where the control is now, whatever the window did in between.
"""
from __future__ import annotations

import contextlib
import time
from typing import Any, Callable, Dict, List, Tuple

CHROME = {"minimize", "maximize", "restore", "close", "system", "scrollbar", "thumb", "page left", "page right", "page up", "page down", "column left", "column right", "line up", "line down"}
POINTABLE = {"button", "menu_item", "tab", "dropdown", "field", "checkbox", "radio", "list_item", "tree_item", "link", "slider"}


def raise_window(hwnd: int, frac_w: float = 0.58, frac_h: float = 0.86) -> None:
    """Restore a (minimized / parked) window, put it on the left of the screen and bring it to the front."""
    import ctypes
    u = ctypes.windll.user32
    with contextlib.suppress(Exception):
        u.ShowWindow(hwnd, 9)                                                    # SW_RESTORE
        sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
        u.MoveWindow(hwnd, 20, 20, int(sw * frac_w), int(sh * frac_h), True)
        u.SetForegroundWindow(hwnd)


def pick_live(elements: List[Any], regions: List[Any], max_points: int = 36, per_region: int = 5) -> List[Dict[str, Any]]:
    """What to point at, in order, from a live read: each region (top to bottom), then its most informative controls (shortcut, tooltip, then reading order). Window chrome and scroll bars last."""
    rid = {r.id: r for r in regions}
    by: Dict[str, List[Any]] = {}
    for e in elements:
        b = e.bbox
        if not e.enabled or b.w < 8 or b.h < 8 or not (e.label or "").strip() or e.role not in POINTABLE:
            continue
        by.setdefault(e.region_id, []).append(e)
    order = sorted(by, key=lambda k: (round(rid[k].bbox.y1 / 40) if k in rid else 9999, rid[k].bbox.x1 if k in rid else 0))
    steps: List[Dict[str, Any]] = []
    n = 0
    for k in order:
        cs = by[k]
        rank = lambda e: (9 if e.label.lower() in CHROME else 0 if e.shortcut else 1 if e.hint else 3, e.bbox.y1, e.bbox.x1)
        seen, picked = set(), []
        for e in sorted(cs, key=rank):
            if e.label in seen:
                continue
            seen.add(e.label)
            picked.append(e)
            if len(picked) >= per_region:
                break
        picked.sort(key=lambda e: (round(e.bbox.y1 / 30), e.bbox.x1))                # visit in reading order
        g = rid.get(k)
        steps.append({"type": "region", "kind": g.kind if g else "?", "name": (g.label if g else "") or "", "n": len(cs), "box": g.bbox if g else None})
        for e in picked:
            steps.append({"type": "control", "e": e})
            n += 1
            if n >= max_points:
                return steps
    return steps


def scan_desktop_show(target: str, budget: float = 25.0, vision: bool = False, pace: float = 0.9, hold_s: float = 5.0, max_points: int = 36,
                      say: Callable[[str], None] = print) -> Dict[str, Any]:
    from core_organs import background_window as bw, fast_scan
    from core_organs import universal_scan as us
    from core_organs.professor import uia_source
    from core_organs.professor.overlay import Overlay
    bw.ENABLED = False                                     # do not park / minimize the window
    bw.CONCEAL_FLYOUTS = False                             # let the menus be seen
    orig_launch, orig_scan = us.launch_hidden, us.scan_desktop
    state: Dict[str, Any] = {"hwnd": 0}

    def launch_visible(*a: Any, **k: Any) -> Dict[str, Any]:
        info = orig_launch(*a, **k)
        if info.get("hwnd"):
            state["hwnd"] = int(info["hwnd"])
            raise_window(state["hwnd"])
        return info

    def scan_visible(*a: Any, **k: Any) -> Dict[str, Any]:
        k["allow_visible"] = True
        return orig_scan(*a, **k)
    us.launch_hidden, us.scan_desktop = launch_visible, scan_visible
    ov = Overlay()
    rep: Dict[str, Any] = {}
    t0 = time.perf_counter()
    try:
        ov_ok = ov.start()
        say(f"  [show] 1 LAUNCH+SCAN  '{target}' opens on the left of your screen; its control tree and menus are read in front of you (virtual cursor {'ready' if ov_ok else 'unavailable: ' + str(ov.error)})")
        rep = fast_scan.deep_scan(target, budget_s=budget, vision=vision, close_if_launched=False)
        hwnd = int(rep.get("hwnd") or state["hwnd"] or 0)
        rep["_wall_ms"] = int((time.perf_counter() - t0) * 1000)
        if hwnd:
            raise_window(hwnd)
            time.sleep(0.8)
            els, regs, meta = uia_source.snapshot_window(hwnd, budget_s=6.0)
            steps = pick_live(els, regs, max_points)
            n_ctl = sum(1 for s in steps if s["type"] == "control")
            say(f"  [show] 2 WALKTHROUGH  live read: {len(els)} controls in {len(regs)} regions; the cursor visits {n_ctl} of them (nothing is highlighted)")
            for s in steps:
                if s["type"] == "region":
                    b = s["box"]
                    say(f"      REGION {s['kind']}: {s['name'] or '(unnamed)'}  -  {s['n']} controls")
                    if ov_ok and b is not None and b.w > 4 and b.h > 4:
                        dur = ov.glide([(b.x1 + min(14.0, b.w / 4), b.y1 + min(10.0, b.h / 4)), (b.x2 - min(14.0, b.w / 4), b.y2 - min(10.0, b.h / 4))])         # sweep the region's extent
                        time.sleep(dur + 0.15)
                else:
                    e = s["e"]
                    say(f"        - {e.role}: {e.label}" + (f"  [{e.shortcut}]" if e.shortcut else "") + (f"   {e.hint[:60]}" if e.hint else ""))
                    if ov_ok:
                        dur = ov.glide([(e.bbox.cx, e.bbox.cy)])
                        time.sleep(dur + pace * 0.5)
            rep["walkthrough"] = {"regions": len(regs), "controls_pointed": n_ctl, "live_controls": len(els)}
            if ov_ok:
                with contextlib.suppress(Exception):
                    ov.release_cursor()
            time.sleep(hold_s)
    finally:
        us.launch_hidden, us.scan_desktop = orig_launch, orig_scan
        with contextlib.suppress(Exception):
            ov.stop()
        hw = int(rep.get("hwnd") or state["hwnd"] or 0)
        if hw:
            with contextlib.suppress(Exception):
                rep["closed"] = bool(us.close_window(hw)) if bw.is_ours(hw) else False
    return rep
