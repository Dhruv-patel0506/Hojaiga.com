"""The live Word instance: which of its top-level windows answer a UIA snapshot, and how long does each take?
(A run is stuck on one procedure; the suspicion is a window whose UIA provider stalls every tree read.)"""
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
frames = [w for w in hwnds if "Word" in (w[3] or "") or w[2] == "OpusApp"]
print("Word frames:", frames)
pids = {w[1] for w in frames}
mine = [w for w in hwnds if w[1] in pids]
print(f"{len(mine)} visible windows in those processes:")
for h, pid, cls, t in mine[:20]:
    a = time.time()
    nodes = fast_uia.snapshot(h, timeout_ms=6000) or []
    print(f"   {h} pid={pid} cls={cls[:20]:20} nodes={len(nodes):5} in {time.time()-a:5.2f}s  title={t[:42]!r}")
