import threading
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
settings_btn = root.ButtonControl(Name="Settings")
print("settings_btn exists:", settings_btn.Exists(3))
box = s.safe_bounding_rect(settings_btn)
print("settings_btn box:", box)
cx, cy = s.center_of(box)
print(f"Center: ({cx}, {cy})")

def worker_click(x, y):
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    print("worker OpenInputDesktop:", hdesk)
    if hdesk:
        res = user32.SetThreadDesktop(hdesk)
        print("worker SetThreadDesktop:", res)
    
    # Check cursor position before
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    print(f"Before click: cursor at ({pt.x}, {pt.y})")
    
    # Use auto.Click inside the worker thread attached to input desktop
    auto.Click(x, y)
    
    user32.GetCursorPos(ctypes.byref(pt))
    print(f"After click: cursor at ({pt.x}, {pt.y})")

t = threading.Thread(target=worker_click, args=(cx, cy))
t.start()
t.join()

print("Checking for Settings window for 8 seconds...")
found = None
for i in range(20):
    time.sleep(0.4)
    for win in auto.GetRootControl().GetChildren():
        name = (win.Name or "").lower()
        if "settings" in name and win.NativeWindowHandle != hwnd:
            found = win
            print(f"SUCCESS: Found Settings window: '{win.Name}' hwnd={win.NativeWindowHandle}")
            break
    if found:
        break

if found:
    traversal = s.DialogTraversal()
    tabs = traversal._find_tabs(found)
    print(f"Settings Tabs ({len(tabs)}): {[t.Name for t in tabs]}")
    traversal._close_safely(found, found.NativeWindowHandle)
    print("Safely closed Settings dialog.")
else:
    print("Settings dialog not found.")
