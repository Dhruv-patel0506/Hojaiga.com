"""
Minimal test: runs in its OWN visible console window.
Writes results to a file for the parent to read.
"""
import ctypes
import time
import sys
import json
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Attach to interactive desktop
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

results = {}
results["pid"] = os.getpid()

# Check foreground
fg = user32.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(512)
user32.GetWindowTextW(fg, buf, 512)
results["fg_hwnd"] = fg
results["fg_title"] = buf.value
print(f"Foreground: hwnd={fg} title='{buf.value}'")

# Check if we have a console window
console_hwnd = kernel32.GetConsoleWindow()
results["console_hwnd"] = console_hwnd
print(f"Console HWND: {console_hwnd}")

# Try to set cursor
res = user32.SetCursorPos(960, 540)
results["setcursorpos_res"] = res
print(f"SetCursorPos(960,540): {res}")

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
pt = POINT()
user32.GetCursorPos(ctypes.byref(pt))
results["cursor_pos"] = (pt.x, pt.y)
print(f"Cursor at: ({pt.x}, {pt.y})")

# Check window station
hwinsta = user32.GetProcessWindowStation()
results["hwinsta"] = hwinsta
print(f"Window Station handle: {hwinsta}")

# Get window station name
name_buf = ctypes.create_unicode_buffer(256)
needed = ctypes.c_ulong()
user32.GetUserObjectInformationW(hwinsta, 2, name_buf, 256*2, ctypes.byref(needed))
results["winsta_name"] = name_buf.value
print(f"Window Station name: '{name_buf.value}'")

# Desktop name
hdesk2 = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
user32.GetUserObjectInformationW(hdesk2, 2, name_buf, 256*2, ctypes.byref(needed))
results["desktop_name"] = name_buf.value
print(f"Desktop name: '{name_buf.value}'")

with open(os.path.join(os.path.dirname(__file__), "scratch_winsta_result.json"), "w") as f:
    json.dump(results, f, indent=2, default=str)

print("Done. Results written.")
time.sleep(2)
