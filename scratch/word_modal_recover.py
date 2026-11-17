"""Word is parked in a modal chain (a save-backstage dialog plus 'You cannot close Word because a
dialog box is open'). Answer it through UIA (the dialogs read in 0.3 s), then measure what the frame
costs to read WITH and WITHOUT the modal - the test that decides whether the ~22 s per read is the
dialog's fault or just Office's provider being slow per element."""
import sys, time, ctypes
import ctypes.wintypes as wt
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs import headless_input as hin, fast_uia
from core_organs.professor.effectors import Effector

u32 = ctypes.windll.user32
wins = []


@ctypes.WINFUNCTYPE(wt.BOOL, ctypes.c_void_p, wt.LPARAM)
def _cb(h, _l):
    try:
        w = int(h)
        if u32.IsWindowVisible(w) and hin.window_pid(w) in (1296,):
            wins.append((w, hin._class_name(w) or "", hin.safe_window_text(w, 80) or ""))
    except Exception:
        pass
    return True


u32.EnumWindows(_cb, 0)
print("word windows:", wins)
FRAME = next((w[0] for w in wins if w[1] == "OpusApp"), None)


def answer(h, words):
    nodes = fast_uia.snapshot(h, timeout_ms=4000) or []
    fx = Effector(h, allow_input=True, owned=True)
    for want in words:
        n = next((x for x in nodes if (getattr(x, "role", "") in ("button",)) and str(getattr(x, "name", "")).strip().lower() == want), None)
        if n is not None:
            print(f"  pressing {want!r} on {h}: {fx.node(n)}")
            return True
    return False


for h, cls, t in wins:
    if cls == "OpusApp":
        continue
    print(f"dialog {h} ({cls}) {t!r} enabled={bool(u32.IsWindowEnabled(h))}")
    answer(h, ["ok", "cancel", "don't save", "close"])

time.sleep(2.0)
print("\nframe enabled now:", bool(u32.IsWindowEnabled(FRAME)))
for label, kw in (("full 60s", dict(timeout_ms=60000)), ("cheap 60s", dict(timeout_ms=60000, cheap=True)),
                  ("full 12s (what the run uses)", dict(timeout_ms=12000))):
    a = time.time()
    n = fast_uia.snapshot(FRAME, max_nodes=20000, **kw)
    print(f"  frame {label:26} -> {0 if n is None else len(n):5} nodes in {time.time()-a:6.2f}s")
