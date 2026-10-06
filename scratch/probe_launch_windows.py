"""Launch an app the way the scanner does and list EVERY top-level window of its process tree after settling (what popups appear?)."""
import sys, os, time, json, ctypes
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import universal_scan as us, background_window as bw
import ctypes.wintypes as wt
u32 = ctypes.windll.user32
name = sys.argv[1]
t0 = time.time()
info = us.launch_hidden(name, timeout_s=60.0, fast=False)
print("launch:", {k: (v if k != "notes" else v[:6]) for k, v in info.items() if k in ("launched", "hwnd", "pid", "resolved", "notes", "title")}, f"{time.time()-t0:.1f}s")
time.sleep(4)
pids = set()
if info.get("pid"):
    pids.add(info["pid"])
rows = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(h, _):
    pid = wt.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    buf = ctypes.create_unicode_buffer(200); u32.GetWindowTextW(h, buf, 200)
    cl = ctypes.create_unicode_buffer(100); u32.GetClassNameW(h, cl, 100)
    if buf.value or u32.IsWindowVisible(h):
        rows.append((int(h), pid.value, cl.value, buf.value, bool(u32.IsWindowVisible(h)), bool(u32.IsIconic(h))))
    return True
u32.EnumWindows(cb, 0)
import subprocess
want = name.split()[0].lower()
for r in rows:
    try:
        exe = subprocess.check_output(["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {r[1]} -ErrorAction SilentlyContinue).ProcessName"], text=True).strip()
    except Exception:
        exe = "?"
    if want in exe.lower() or r[1] in pids:
        print(r, exe)
print("hwnd chosen:", info.get("hwnd"))
if "--close" in sys.argv:
    try:
        bw.exit if False else None
    except Exception:
        pass
