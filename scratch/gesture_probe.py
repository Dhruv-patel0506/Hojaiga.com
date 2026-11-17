"""Which pointer-delivery routes does an app accept on an OWNED parked window? Posted messages to the child window under the point; measured by pixels (PrintWindow)."""
import sys, time, ctypes
import numpy as np
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs.professor import apprun as AR, capture as CAP
from core_organs.atlas import gestures as G
from core_organs import headless_input as hin

name = sys.argv[1] if len(sys.argv) > 1 else "paint"
u = ctypes.windll.user32
fg0 = u.GetForegroundWindow()
cur0 = (ctypes.c_long * 2)()
u.GetCursorPos(ctypes.byref(cur0))
run = AR.AppRun(AR.spec_for(name), echo=True, vision=False)


def shot():
    fr = CAP.grab_window(run.hwnd, isolated=True)
    return (np.asarray(fr.image.convert("L"), dtype=np.int16), fr.origin) if fr is not None else (None, (0, 0))


def diff(a, b):
    if a is None or b is None or a.shape != b.shape:
        return -1.0
    return float((np.abs(a - b) > 24).mean())


try:
    print("start", run.start(), run.hwnd, run.report["phases"].get("park"))
    time.sleep(2.0)
    from core_organs import background_window as bw
    l, t, r, b = bw._rect(run.hwnd)
    W, H = r - l, b - t
    cx, cy = l + W // 2, t + int(H * 0.62)
    print("window", (l, t, r, b), "target", (cx, cy), "child", hin._class_name(hin.child_at(run.hwnd, cx, cy)))
    P = G.Pointer(run.hwnd)
    P.click(l + 40, t + int(H * 0.5)); time.sleep(1.5)                       # dismiss a start-up splash first
    tests = [("wheel 3 (zoom) first", lambda: P.wheel(cx, cy, 3)), ("middle-drag first", lambda: P.drag((cx - 120, cy), (cx + 120, cy), "middle", steps=20, duration_s=0.4)),("left-drag stroke", lambda: P.drag((cx - 150, cy - 40), (cx + 150, cy + 40), "left", steps=30, duration_s=0.5)),
             ("middle-drag (orbit/pan)", lambda: P.drag((cx - 120, cy), (cx + 120, cy), "middle", steps=20, duration_s=0.4)),
             ("wheel 3 (zoom)", lambda: P.wheel(cx, cy, 3)),
             ("right-drag", lambda: P.drag((cx, cy - 80), (cx, cy + 80), "right", steps=20, duration_s=0.4))]
    for label, fn in tests:
        a, _ = shot()
        ok, note = fn()
        time.sleep(1.2)
        b2, _ = shot()
        print(f"  {label:26s} delivered={ok} changed={diff(a, b2):.4f}  {note}")
        with __import__("contextlib").suppress(Exception):
            run.fx = None
            hin.post_key(run.hwnd, "escape") if hasattr(hin, "post_key") else None
finally:
    cur1 = (ctypes.c_long * 2)()
    u.GetCursorPos(ctypes.byref(cur1))
    print("fg changed?", u.GetForegroundWindow() != fg0, "| real mouse moved?", tuple(cur0) != tuple(cur1))
    run._teardown()
    print("closed")
