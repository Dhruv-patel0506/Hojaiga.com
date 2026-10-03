import ctypes
import time
import os
import sys
import uiautomation as auto

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Attach input desktop
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

print(f"PID: {os.getpid()}")
fg = user32.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(512)
user32.GetWindowTextW(fg, buf, 512)
print(f"Foreground: hwnd={fg} title='{buf.value}'")

import organ_30_app_scanner as s

hwnd = s.ensure_obs_running()
print(f"OBS HWND: {hwnd}")
time.sleep(2)

# Set OBS foreground
print("Bringing OBS to foreground...")
s.bring_to_foreground(hwnd)
time.sleep(0.5)

fg = user32.GetForegroundWindow()
user32.GetWindowTextW(fg, buf, 512)
print(f"Foreground now: hwnd={fg} title='{buf.value}'")

root = auto.ControlFromHandle(hwnd)
settings_btn = root.ButtonControl(Name="Settings")
print(f"Settings btn exists: {settings_btn.Exists(3)}")

if settings_btn.Exists(0):
    box = s.safe_bounding_rect(settings_btn)
    cx, cy = s.center_of(box)
    print(f"Settings center: ({cx}, {cy})")
    
    # Test cursor move
    res = user32.SetCursorPos(cx, cy)
    print(f"SetCursorPos({cx}, {cy}): res={res}")
    
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    print(f"Cursor currently at: ({pt.x}, {pt.y})")
    
    # Click using ctypes mouse_event
    print("Sending mouse_event LEFTDOWN + LEFTUP...")
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.12)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(1.5)
    
    # Check if Settings opened
    print("Checking for Settings dialog...")
    found = False
    for i in range(10):
        for win in auto.GetRootControl().GetChildren():
            wname = (win.Name or "").strip()
            if "settings" in wname.lower():
                print(f"FOUND SETTINGS DIALOG! hwnd={win.NativeWindowHandle} title='{wname}'")
                found = True
                trav = s.DialogTraversal()
                tabs = trav._find_tabs(win)
                print(f"Tabs ({len(tabs)}): {[t.Name for t in tabs]}")
                trav._close_safely(win, win.NativeWindowHandle)
                print("Dialog closed.")
                break
        if found:
            break
        time.sleep(0.3)
    
    if not found:
        print("Settings dialog NOT found.")
        # List all windows belonging to OBS process
        obs_pid = s.get_pid_for_hwnd(hwnd)
        print(f"Listing all windows for OBS PID {obs_pid}:")
        for win in auto.GetRootControl().GetChildren():
            if win.ProcessId == obs_pid:
                print(f"  obs win: hwnd={win.NativeWindowHandle} name='{win.Name}' class='{win.ClassName}' is_visible={win.IsWindowVisible()}")
