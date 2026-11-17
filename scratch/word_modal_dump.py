"""Read what the small Word windows actually say: a modal Office dialog (NUIDialog) parked over the
frame explains both the 174-node frame and the ~22s per read. Dump their trees."""
import sys, time, ctypes
import ctypes.wintypes as wt
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs import headless_input as hin, fast_uia

u32 = ctypes.windll.user32
hwnds = []


@ctypes.WINFUNCTYPE(wt.BOOL, ctypes.c_void_p, wt.LPARAM)
def _cb(h, _l):
    try:
        w = int(h)
        if u32.IsWindowVisible(w):
            hwnds.append((w, hin.window_pid(w), hin._class_name(w) or "", hin.safe_window_text(w, 120) or ""))
    except Exception:
        pass
    return True


u32.EnumWindows(_cb, 0)
frames = [w for w in hwnds if w[2] in ("OpusApp", "NUIDialog")]
pids = {w[1] for w in frames}
print("Word-side processes:", pids)
for h, pid, cls, t in [w for w in hwnds if w[1] in pids]:
    a = time.time()
    nodes = fast_uia.snapshot(h, timeout_ms=6000) or []
    dt = time.time() - a
    print(f"\n=== hwnd={h} pid={pid} cls={cls} title={t!r} nodes={len(nodes)} in {dt:.2f}s")
    if len(nodes) > 60:                                                       # the frame itself: only the small windows get a full dump
        continue
    for n in nodes[:80]:
        print(f"   [{getattr(n,'role','')}] {str(getattr(n,'name',''))[:70]!r} aid={str(getattr(n,'automation_id',''))[:28]!r} "
              f"rect={tuple(getattr(n,'rect',(0,0,0,0)))} en={getattr(n,'enabled',None)}")
