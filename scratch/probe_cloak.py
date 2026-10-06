import ctypes, ctypes.wintypes as wt, subprocess, time, sys
u32 = ctypes.windll.user32; dwm = ctypes.windll.dwmapi
si = subprocess.STARTUPINFO(); si.dwFlags = 1; si.wShowWindow = 4   # SW_SHOWNOACTIVATE (visible but not active)
before = set()
@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb0(h, _):
    before.add(int(h)); return True
u32.EnumWindows(cb0, 0)
p = subprocess.Popen(["notepad.exe"], startupinfo=si)
time.sleep(3)
found = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(h, _):
    b = ctypes.create_unicode_buffer(100); u32.GetClassNameW(h, b, 100)
    if b.value == "Notepad" and int(h) not in before and u32.IsWindowVisible(h): found.append(int(h))
    return True
u32.EnumWindows(cb, 0)
print("new notepad windows:", found)
if not found: sys.exit()
h = found[0]
v = ctypes.c_int(1)
hr = dwm.DwmSetWindowAttribute(h, 13, ctypes.byref(v), 4)
print("cloak hr=0x%08x" % (hr & 0xffffffff))
c = ctypes.c_int(0); dwm.DwmGetWindowAttribute(h, 14, ctypes.byref(c), 4); print("cloaked state:", c.value)
import ctypes as C
print("IsWindowVisible:", bool(u32.IsWindowVisible(h)))
time.sleep(1.5)
v = ctypes.c_int(0); hr2 = dwm.DwmSetWindowAttribute(h, 13, ctypes.byref(v), 4); print("uncloak hr=0x%08x" % (hr2 & 0xffffffff))
u32.PostMessageW(h, 0x0010, 0, 0)
