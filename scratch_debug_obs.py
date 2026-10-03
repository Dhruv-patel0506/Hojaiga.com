import ctypes
import time
import win32gui
import uiautomation as auto
import organ_30_app_scanner as s

hwnd = s.ensure_obs_running()
print("OBS HWND:", hwnd)
s.bring_to_foreground(hwnd)
time.sleep(1)

root = auto.ControlFromHandle(hwnd)
print("OBS window rect:", s.safe_bounding_rect(root))

settings_btn = root.ButtonControl(Name="Settings")
print("settings_btn:", settings_btn)
print("IsEnabled:", getattr(settings_btn, 'IsEnabled', None))
print("IsOffscreen:", getattr(settings_btn, 'IsOffscreen', None))
print("BoundingRect:", s.safe_bounding_rect(settings_btn))

user32 = ctypes.windll.user32
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

box = s.safe_bounding_rect(settings_btn)
cx, cy = s.center_of(box)
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

pt = POINT(cx, cy)
hwnd_at_pt = user32.WindowFromPoint(pt)
buf = ctypes.create_unicode_buffer(512)
user32.GetWindowTextW(hwnd_at_pt, buf, 512)
print(f"Window at point ({cx}, {cy}): hwnd={hwnd_at_pt}, title='{buf.value}'")

# Let's test setting focus and pressing Enter or Space
print("Setting focus to settings_btn...")
settings_btn.SetFocus()
time.sleep(0.5)
focused = auto.GetFocusedControl()
print("Focused control now:", focused.Name if focused else None)

# Press Space on focused control
print("Sending Space key to focused control...")
settings_btn.SendKeys('{SPACE}')
time.sleep(1.5)

print("Checking for Settings window...")
for win in auto.GetRootControl().GetChildren():
    if "settings" in (win.Name or "").lower():
        print("FOUND SETTINGS VIA SPACE KEY:", win.Name, win.NativeWindowHandle)
        traversal = s.DialogTraversal()
        traversal._close_safely(win, win.NativeWindowHandle)
        break
