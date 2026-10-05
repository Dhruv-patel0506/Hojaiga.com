import threading
import ctypes
import time
import win32con
import win32gui
import uiautomation as auto
import organ_30_app_scanner as s

hwnd = s.ensure_obs_running()
print("OBS HWND:", hwnd)

# Allow OBS to complete its internal startup
print("Waiting 4s for OBS to settle...")
time.sleep(4)

s.bring_to_foreground(hwnd)
time.sleep(1)

root = auto.ControlFromHandle(hwnd)
settings_btn = root.ButtonControl(Name="Settings")
print("Settings btn exists:", settings_btn.Exists(3))
box = s.safe_bounding_rect(settings_btn)
print("Settings box:", box)
cx, cy = s.center_of(box)

def click_worker(x, y):
    user32 = ctypes.windll.user32
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    if hdesk:
        user32.SetThreadDesktop(hdesk)
    user32.SetCursorPos(x, y)
    time.sleep(0.12)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.2)

print(f"Clicking Settings at ({cx}, {cy})...")
t = threading.Thread(target=click_worker, args=(cx, cy))
t.start()
t.join()

print("Checking for Settings window for up to 10 seconds...")
found_dlg = None
for i in range(25):
    time.sleep(0.4)
    # Check via UIA root control
    for win in auto.GetRootControl().GetChildren():
        try:
            wname = win.Name or ""
            if "settings" in wname.lower():
                found_dlg = win
                print(f"Found Settings window via UIA: '{wname}' hwnd={win.NativeWindowHandle}")
                break
        except Exception:
            pass
    if found_dlg:
        break

if found_dlg:
    traversal = s.DialogTraversal()
    tabs = traversal._find_tabs(found_dlg)
    print(f"Found {len(tabs)} tabs in Settings dialog:")
    for tab in tabs:
        print(f" - Tab: {tab.Name}")
    traversal._close_safely(found_dlg, found_dlg.NativeWindowHandle)
    print("Safely closed Settings dialog.")
else:
    print("Settings dialog not found.")
