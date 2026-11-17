"""Visible-mode probe: owned Paint shown WITHOUT activation, a synthetic touch / pen stroke on its canvas, pixels compared; the person's mouse must not move."""
import sys, time, ctypes
import numpy as np
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs.professor import apprun as AR, capture as CAP
from core_organs.professor.pointer_inject import PointerInjector

name = sys.argv[1] if len(sys.argv) > 1 else "paint"
u = ctypes.windll.user32
cur0 = (ctypes.c_long * 2)(); u.GetCursorPos(ctypes.byref(cur0))
run = AR.AppRun(AR.spec_for(name), echo=True, vision=False, visible=True)


def shot():
    fr = CAP.grab_window(run.hwnd, isolated=True)
    return np.asarray(fr.image.convert("L"), dtype=np.int16) if fr is not None else None


try:
    print("start", run.start(), run.hwnd)
    time.sleep(2.5)
    r = (ctypes.c_long * 4)(); u.GetWindowRect(run.hwnd, ctypes.byref(r))
    l, t, rr, b = r[0], r[1], r[2], r[3]
    cx, cy = (l + rr) // 2, t + int((b - t) * 0.62)
    under = u.WindowFromPoint(ctypes.wintypes.POINT(cx, cy)) if hasattr(ctypes, "wintypes") else 0
    import ctypes.wintypes as wt
    top = u.GetAncestor(u.WindowFromPoint(wt.POINT(cx, cy)), 2)
    print("window", (l, t, rr, b), "point", (cx, cy), "top window at point is ours:", top == run.hwnd)
    for kind in (sys.argv[2:] or ["touch"]):
        a = shot()
        with PointerInjector(kind) as pi:
            pts = [(cx - 160 + i * 10, cy + int(40 * np.sin(i / 4))) for i in range(33)]
            ok, note = pi.stroke(pts, 10)
        time.sleep(1.2)
        b2 = shot()
        ch = float((np.abs(a - b2) > 24).mean()) if a is not None and b2 is not None and a.shape == b2.shape else -1
        c1 = (ctypes.c_long * 2)(); u.GetCursorPos(ctypes.byref(c1))
        print(f"  {kind:6s} delivered={ok} changed={ch:.4f}  {note}  mouse moved by this stroke: {tuple(c1) != tuple(cur0)}")
        from PIL import Image
        Image.fromarray(np.clip(b2, 0, 255).astype("uint8")).save(f"D:/new_automation/scratch/inject_{kind}.png")
        cy += 60
finally:
    cur1 = (ctypes.c_long * 2)(); u.GetCursorPos(ctypes.byref(cur1))
    print("real mouse moved?", tuple(cur0) != tuple(cur1))
    run._teardown()
    print("closed")
