import sys
import time
import ctypes
import win32api
import win32con
import win32gui
import uiautomation as auto
import organ_30_app_scanner as s

user32 = ctypes.windll.user32
s.ensure_interactive_desktop()

# Find running OBS
hwnd = s.ensure_obs_running()
print("OBS HWND:", hwnd)
s.bring_to_foreground(hwnd)
time.sleep(1)

root = auto.ControlFromHandle(hwnd)
settings_btn = root.ButtonControl(Name="Settings")
print("Settings btn exists:", settings_btn.Exists(3))
box = s.safe_bounding_rect(settings_btn)
print("Settings box:", box)

cx, cy = s.center_of(box)
print(f"Center: ({cx}, {cy})")

# Test win32api.SetCursorPos
try:
    win32api.SetCursorPos((cx, cy))
    print("win32api.SetCursorPos succeeded")
except Exception as e:
    print("win32api.SetCursorPos exception:", type(e), e)

# Test ctypes SetCursorPos
res = user32.SetCursorPos(cx, cy)
print("user32.SetCursorPos result:", res)

# Get current cursor pos
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
pt = POINT()
user32.GetCursorPos(ctypes.byref(pt))
print(f"Current cursor pos: ({pt.x}, {pt.y})")

# Perform ctypes mouse click
print("Sending ctypes mouse click...")
user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
time.sleep(0.1)
user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
time.sleep(1.0)

print("Checking windows...")
def enum_cb(h, _):
    if win32gui.IsWindowVisible(h):
        t = win32gui.GetWindowText(h)
        if t:
            print(f"Window: hwnd={h} title='{t}'")
    return True
win32gui.EnumWindows(enum_cb, None)
