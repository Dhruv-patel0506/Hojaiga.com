"""Probe: does a fresh, minimized Notepad put ITSELF back on screen, and when?

Why this exists: MIN1/LM1/S1 all degraded together on notepad legs with the target window reported VISIBLE
for 10-22 s during the scan's `layout` phase (f5 showed 63 ms). The window titles in that evidence -
'poem1.txt', 'poem2.txt', '*again-two' - are documents from earlier test runs, and Windows Notepad restores
its previous session's tabs when it starts. This script asks the machine, not the log: launch exactly the
way the harness does (minimized, never activated) and sample the window for 40 s. It never clicks, types or
raises anything.
"""
import ctypes
import ctypes.wintypes as w
import subprocess
import sys
import time

sys.path.insert(0, r"D:\new_automation\All codes")

u = ctypes.windll.user32


def state(h):
    r = w.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    t = ctypes.create_unicode_buffer(200)
    u.GetWindowTextW(h, t, 200)
    return int(bool(u.IsIconic(h))), int(bool(u.IsWindowVisible(h))), (r.left, r.top, r.right, r.bottom), t.value


def top_windows(cls_sub: str):
    out = []
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)

    def cb(h, _):
        b = ctypes.create_unicode_buffer(128)
        u.GetClassNameW(h, b, 128)
        if cls_sub in b.value.lower() and u.IsWindow(h):
            out.append(h)
        return True

    u.EnumWindows(CB(cb), 0)
    return out


before = set(top_windows("notepad"))
si = subprocess.STARTUPINFO()
si.dwFlags = 1
si.wShowWindow = 7                                          # SW_SHOWMINNOACTIVE
p = subprocess.Popen(["notepad.exe"], startupinfo=si)
print(f"launched notepad pid={p.pid} (minimized, never activated)")

hwnd = 0
end = time.time() + 25
while time.time() < end:
    time.sleep(0.3)
    new = [h for h in top_windows("notepad") if h not in before]
    if new:
        hwnd = new[0]
        break
if not hwnd:
    print("no window appeared")
    sys.exit(1)

from core_organs import background_window as bw
bw.mark_ours(hwnd)                                          # ours to close; never the user's
print(f"hwnd={hwnd} marked ours; minimizing without activating")
u.ShowWindow(hwnd, 7)
last = None
t0 = time.time()
while time.time() - t0 < 40:
    icon, vis, rect, title = state(hwnd)
    fg = u.GetForegroundWindow()
    sig = (icon, vis, rect[0] > -20000 and rect[0] < 4000 and rect[2] > 0)
    if sig != last:
        print(f"  t={time.time()-t0:5.1f}s iconic={icon} visible={vis} on_screen={sig[2]} rect={rect} "
              f"fg={'ours' if fg == hwnd else fg} title={title!r}")
        last = sig
    time.sleep(0.25)

print(f"sampling done; idle_ms={bw.user_idle_ms()}")
u.PostMessageW(hwnd, 0x0010, 0, 0)                          # WM_CLOSE, only our own window
end = time.time() + 5
while time.time() < end and u.IsWindow(hwnd):
    time.sleep(0.2)
for d in [h for h in top_windows("#32770")]:
    u.PostMessageW(d, 0x0010, 0, 0)
print(f"closed our window; still_alive={u.IsWindow(hwnd)}")
