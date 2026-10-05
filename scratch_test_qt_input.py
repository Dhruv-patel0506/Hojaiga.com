import ctypes
import time
import win32con
import win32gui
import win32process
import uiautomation as auto
import organ_30_app_scanner as s

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

hwnd = s.ensure_obs_running()
print("OBS HWND:", hwnd)
time.sleep(1)

root = auto.ControlFromHandle(hwnd)
settings_btn = root.ButtonControl(Name="Settings")
print("settings_btn:", settings_btn)

box = s.safe_bounding_rect(settings_btn)
cx, cy = s.center_of(box)
print("Screen center:", (cx, cy))

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

pt = POINT(cx, cy)
target_hwnd = user32.WindowFromPoint(pt)
print("Target HWND under point:", target_hwnd)

# Convert to client coords
client_pt = POINT(cx, cy)
user32.ScreenToClient(target_hwnd, ctypes.byref(client_pt))
print(f"Client coords: ({client_pt.x}, {client_pt.y})")

# Let's attach thread input
cur_tid = kernel32.GetCurrentThreadId()
obs_tid, obs_pid = win32process.GetWindowThreadProcessId(hwnd)
print(f"Attaching tid {cur_tid} -> {obs_tid}...")
user32.AttachThreadInput(cur_tid, obs_tid, True)

# Set foreground
user32.SetForegroundWindow(hwnd)
user32.BringWindowToTop(hwnd)
time.sleep(0.2)

# Method A: Send WM_LBUTTONDOWN and WM_LBUTTONUP to target_hwnd
lparam = (client_pt.y << 16) | (client_pt.x & 0xFFFF)
print(f"Posting WM_LBUTTONDOWN/UP with lparam={hex(lparam)}...")
user32.PostMessageW(target_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
time.sleep(0.08)
user32.PostMessageW(target_hwnd, win32con.WM_LBUTTONUP, 0, lparam)

print("Checking for Settings window...")
found = False
for i in range(15):
    time.sleep(0.3)
    for win in auto.GetRootControl().GetChildren():
        wname = (win.Name or "").lower()
        if "settings" in wname:
            print("SUCCESS: Settings window opened via PostMessage!", win.Name, win.NativeWindowHandle)
            traversal = s.DialogTraversal()
            tabs = traversal._find_tabs(win)
            print("Settings Tabs discovered:", [t.Name for t in tabs])
            traversal._close_safely(win, win.NativeWindowHandle)
            found = True
            break
    if found:
        break

if not found:
    print("PostMessage did not open settings, testing Menu File -> Settings...")
    # OBS has File -> Settings. Alt+F, then 's' or Down arrow
    # Let's test accelerator
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.2)
    s.send_alt_sequence("%f")
    time.sleep(0.3)
    # in File menu, let's see what is focused
    fc = auto.GetFocusedControl()
    print("Focused in menu:", fc.Name if fc else None)
    s.send_keys(win32con.VK_ESCAPE)

user32.AttachThreadInput(cur_tid, obs_tid, False)
