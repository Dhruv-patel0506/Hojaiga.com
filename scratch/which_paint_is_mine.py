"""Are the running mspaint processes MINE (leftover probe windows) or the USER'S? Lists every top-level window
per pid with its visibility, and whether the ownership registry claims it. Read-only - kills nothing."""
import sys, ctypes, ctypes.wintypes as wt
sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import background_window as bw

u = ctypes.windll.user32
rows = []
_CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, wt.LPARAM)  # ints, not bytes


@_CB
def cb(h, _l):
    pid = wt.DWORD()
    u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    cls = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(h, cls, 256)
    n = u.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, b, n + 1)
    r = wt.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    if "paint" in (b.value or "").lower() or "paint" in cls.value.lower() or "mspaint" in cls.value.lower():
        rows.append((int(pid.value), int(h), b.value, cls.value, bool(u.IsWindowVisible(h)), bool(u.IsIconic(h)),
                     (r.left, r.top, r.right, r.bottom)))
    return True


u.EnumWindows(cb, 0)
print(f"{'pid':>7} {'hwnd':>9}  visible  iconic  rect                        class / title            ours")
for pid, h, t, c, vis, ico, rc in rows:
    print(f"{pid:>7} {h:>9}  {str(vis):>7}  {str(ico):>6}  {str(rc):>26}  {c[:14]:>14} {t[:26]!r:28} {bw.is_ours(h)}")
if not rows:
    print("  (no Paint windows exist - the processes are headless leftovers)")
print("\nlive windows the registry owns (ours_alive):", bw.ours_alive())
print("parked journal rects:", bw.parked_rects())
