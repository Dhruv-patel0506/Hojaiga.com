"""Read-only: every top-level window of a given pid, with title, class, visibility and rect.

Used to answer "whose window is this?" without guessing - the suite refuses to drive a window the user
opened, and that refusal is only honest if the ownership question is answered from the desktop, not from
a log line.
"""
import ctypes
import ctypes.wintypes as w
import sys

u = ctypes.windll.user32
want = {int(a) for a in sys.argv[1:]}

CB = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
rows = []


def cb(h, _):
    pid = w.DWORD()
    u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    if want and pid.value not in want:
        return True
    t = ctypes.create_unicode_buffer(512)
    u.GetWindowTextW(h, t, 512)
    c = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(h, c, 256)
    if not t.value:
        return True
    r = w.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    rows.append((pid.value, h, t.value[:60], c.value[:30], int(bool(u.IsWindowVisible(h))),
                 int(bool(u.IsIconic(h))), (r.left, r.top, r.right, r.bottom)))
    return True


u.EnumWindows(CB(cb), 0)
for x in sorted(rows):
    print(f"pid={x[0]:<7} hwnd={x[1]:<10} vis={x[4]} min={x[5]} {str(x[6]):<26} {x[3]:<30} {x[2]}")
print(f"{len(rows)} window(s)")
