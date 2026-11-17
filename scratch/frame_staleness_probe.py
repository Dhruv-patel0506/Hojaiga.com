"""WHY does the run's frame read only 7 nodes while the catalog holds 5119 verbs?
List EVERY top-level window of the process, its node count and whether it is enabled: if a big live tree sits on a DIFFERENT hwnd than the one the run owns,
the owned handle went stale (the application re-made its frame) and every 'control not found in the live tree' is really 'we are reading a dead shell'."""
import sys, time, ctypes
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs import headless_input as hin
from core_organs import fast_uia

target = sys.argv[1] if len(sys.argv) > 1 else "winword"
user32 = ctypes.windll.user32
wins = []


import ctypes.wintypes as wt
EnumProc = wt.HWND, wt.LPARAM
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_ssize_t)


def walk(h, _l):
    try:
        if not user32.IsWindowVisible(h):
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        cls = hin._class_name(int(h))
        txt = hin.safe_window_text(int(h))
        if pid.value and txt and (target in (cls or "").lower() or "word" in (txt or "").lower() or target in (txt or "").lower()):
            wins.append((int(h), pid.value, cls, txt))
    except Exception:
        pass
    return True


user32.EnumWindows(CB(walk), 0)
print(f"{len(wins)} candidate windows")
for h, pid, cls, txt in wins:
    t0 = time.time()
    try:
        nodes = fast_uia.snapshot(h, max_nodes=20000, timeout_ms=25000) or []
    except Exception as exc:
        nodes = []
        print("  err", type(exc).__name__)
    en = bool(user32.IsWindowEnabled(h))
    print(f"hwnd={h} pid={pid} en={en} nodes={len(nodes)} in {time.time()-t0:.2f}s class={cls!r} title={txt[:60]!r}")
