import threading
import ctypes
import time
import win32con
import win32gui
import uiautomation as auto
import organ_30_app_scanner as s

# First, let's find OBS HWND
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

def click_worker(x, y):
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    print("click_worker OpenInputDesktop:", hdesk)
    if hdesk:
        res = user32.SetThreadDesktop(hdesk)
        print("click_worker SetThreadDesktop:", res, "err:", kernel32.GetLastError())
    
    pos_res = user32.SetCursorPos(x, y)
    print(f"click_worker SetCursorPos({x}, {y}): {pos_res}, err: {kernel32.GetLastError()}")
    time.sleep(0.12)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.2)

t = threading.Thread(target=click_worker, args=(cx, cy))
t.start()
t.join()

print("Checking if settings dialog appears...")
for i in range(15):
    time.sleep(0.3)
    fg = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(fg)
    print(f"Check {i}: fg={fg} title='{title}'")
    if "settings" in title.lower():
        print("SUCCESS: Settings window opened!")
        break
