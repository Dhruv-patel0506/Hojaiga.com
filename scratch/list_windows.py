import ctypes
import sys

sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import headless_input as hin  # noqa: E402

u = ctypes.windll.user32
rows = []


@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
def _cb(h, _l):
    if not u.IsWindowVisible(h):
        return True
    buf = ctypes.create_unicode_buffer(512)
    u.GetWindowTextW(h, buf, 512)
    title = buf.value
    if not title:
        return True
    pid = ctypes.c_ulong()
    u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    rows.append((int(h), hin._class_name(h), title[:70], pid.value))


u.EnumWindows(_cb, 0)
for r in rows:
    print(*r, sep=" | ")
