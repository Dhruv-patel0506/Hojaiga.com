"""Owned Paint (WinUI 3) instance, parked the way the harness parks it; the virtual mouse's touch route on a ghost window drawn on the canvas, checked by pixels. Diagnostics for the touch route."""
import os, sys, tempfile, time, ctypes, ctypes.wintypes as wt, json
os.environ["HOJAIGA_PROF_DIR"] = os.path.join(tempfile.gettempdir(), "hojaiga_prof_paint")
sys.path.insert(0, r"D:\new_automation"); sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import background_window as bw
from core_organs.atlas import scanner as SC
from core_organs.professor import launcher as LN, state_protect as SPT, pointer as PT, capture as CAP
from core_organs.professor.lab.lab_matrix import Fx
u = ctypes.WinDLL("user32", use_last_error=True)

target = LN.resolve("paint")
guard = SPT.StateGuard("paint", target.appid)
guard.before()
info = LN.launch_owned(target, guard)
hwnd = int(info.get("hwnd") or 0)
print("launched", info.get("launched"), hwnd, info.get("title"))
bg = bw.BackgroundSession(hwnd)
bg.__enter__()
time.sleep(2.0)
try:
    r = wt.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r)); print("parked rect", r.left, r.top, r.right, r.bottom, "iconic", u.IsIconic(hwnd))
    aware = PT.pointer_aware(hwnd)
    print("pointer_aware", aware)
    # canvas: the lower-middle of the window
    l, t, rr, b = r.left, r.top, r.right, r.bottom
    surf = (l + (rr - l) // 4, t + (b - t) // 2, l + 3 * (rr - l) // 4, b - (b - t) // 6)
    vp = PT.VirtualPointer(hwnd, "paint_probe", Fx(), only=["touch"], probe_touch=True)
    before = PT.pixels(hwnd, surf)
    pts = [(surf[0] + 60 + i * 12, surf[1] + 80 + (i % 6) * 6) for i in range(30)]
    with PT.CursorWatch() as cw:
        res = vp.stroke(pts, duration=0.8)
    time.sleep(0.8)
    after = PT.pixels(hwnd, surf)
    print("stroke ->", res.ok, res.route, res.tried)
    print("changed fraction", PT.changed(before, after), "cursor moved", cw.moved, cw.max_dev, "real input", cw.real_input_seen)
    print("rect after", [x for x in PT.window_rect(hwnd)], "iconic", u.IsIconic(hwnd))
    from core_organs import fast_uia
    from core_organs.professor import gestures as GE
    nodes_fn = lambda: fast_uia.snapshot(hwnd, timeout_ms=3000) or []
    nodes = nodes_fn()
    r0 = PT.window_rect(hwnd)
    surf2, how = GE.surface_of(nodes, r0)
    print("surface_of ->", surf2, how, "window", r0, "nodes", len(nodes))
    big = sorted([(n.rect[2]-n.rect[0])*(n.rect[3]-n.rect[1]), n.role, n.name[:30], n.rect] for n in nodes if n.role in GE.SURFACE_ROLES and not n.offscreen)[-5:]
    print("largest surface-like nodes", big)
    drv = GE.GestureDriver("paint_probe", hwnd, Fx(), nodes_fn)
    for kind in ("stroke", "select_area"):
        res = drv.perform(kind)
        print(kind, "->", res.ok, res.route, res.why[:300], res.tried)
finally:
    try:
        bg.__exit__(None, None, None)
    except Exception:
        pass
    try:
        SC.close_owned(hwnd)
    except Exception as exc:
        print("close", exc)
    guard.after() if hasattr(guard, "after") else None
