"""Is the window that poisoned Word's catalog still on the machine (hidden / on another desktop)?
If a hidden top-level still carries the title, the load-time scrub can recognize those verbs without the window ever being shown."""
import ctypes
import ctypes.wintypes as wt
import sys

sys.path.insert(0, r"d:\new_automation\All codes")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core_organs import headless_input as hin
from core_organs.professor import harvest as HV

u = ctypes.windll.user32
k32 = ctypes.windll.kernel32


def name_of(pid: int) -> str:
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(1024)
        if k32.QueryFullProcessImageNameW(int(h), 0, buf, ctypes.byref(n)):
            return buf.value.rsplit("\\", 1)[-1]
    except Exception:
        pass
    finally:
        k32.CloseHandle(h)
    return ""


rows = []
PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


def cb(h, _l):
    try:
        n = u.GetWindowTextLengthW(h)
        if n >= 12:
            buf = ctypes.create_unicode_buffer(n + 2)
            u.GetWindowTextW(h, buf, n + 2)
            rows.append((int(h), bool(u.IsWindowVisible(h)), buf.value, name_of(hin.window_pid(int(h))), hin._class_name(int(h))))
    except Exception as exc:
        print("cb", type(exc).__name__)
    return True


u.EnumWindows(PROC(cb), 0)
print(f"{len(rows)} titled top-levels (visible or not)")
for r in rows:
    if "opencode" in r[2].lower() or "chrome" in (r[3] or "").lower() or r[4].lower() in ("chrome_windows_widget", "wpadfilehostwindow"):
        print(f"  hwnd={r[0]} visible={r[1]} proc={r[3]:<16} class={r[4]:<26} title={r[2][:70]}")
print("\nforeign_titles('WINWORD.EXE') with visible only:", len(HV.foreign_titles("WINWORD.EXE")))
