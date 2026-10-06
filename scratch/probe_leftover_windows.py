"""What's on the desktop right now that our harness would call 'the user's app'?"""
import ctypes
from ctypes import wintypes as wt

u32 = ctypes.windll.user32
rows = []


@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(h, _):
    if not u32.IsWindowVisible(h):
        return True
    n = u32.GetWindowTextLengthW(h)
    if not n:
        return True
    buf = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(h, buf, n + 1)
    cls = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(h, cls, 256)
    pid = wt.DWORD()
    u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    t = buf.value.lower()
    if ("notepad" in cls.value.lower() or "notepad" in t or "mspaint" in cls.value.lower()
            or "paint" in t or "hj_" in t or "excel" in t or "NUIDialog" == cls.value):
        rows.append((h, pid.value, cls.value, buf.value, bool(u32.IsIconic(h))))
    return True


u32.EnumWindows(cb, 0)
for r in rows:
    print(r)
print("total matched:", len(rows))
