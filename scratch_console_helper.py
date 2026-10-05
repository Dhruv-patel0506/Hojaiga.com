"""
Helper script that runs in its own console window (launched via `start`).
Tests whether a process with its own console can inject input into OBS.
"""
import ctypes
import time
import sys
import json
import win32gui
import win32con
import uiautomation as auto

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Attach to interactive desktop
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

print("Helper PID:", __import__('os').getpid())

# Find OBS window
import organ_30_app_scanner as s
hwnd = s.find_hwnd_by_title_substring("OBS")
if not hwnd:
    hwnd = s.ensure_obs_running()
print("OBS HWND:", hwnd)
time.sleep(1)

# Try SetForegroundWindow from this console process
fg_before = user32.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(512)
user32.GetWindowTextW(fg_before, buf, 512)
print(f"Foreground before: hwnd={fg_before} title='{buf.value}'")

# This process has its own console, so it should be able to call SetForegroundWindow
user32.ShowWindow(hwnd, 9) # SW_RESTORE
time.sleep(0.1)
res = user32.SetForegroundWindow(hwnd)
print(f"SetForegroundWindow result: {res}")
time.sleep(0.3)

fg_after = user32.GetForegroundWindow()
user32.GetWindowTextW(fg_after, buf, 512)
print(f"Foreground after: hwnd={fg_after} title='{buf.value}'")

# Now try clicking Settings
root = auto.ControlFromHandle(hwnd)
settings_btn = root.ButtonControl(Name="Settings")
print(f"Settings btn exists: {settings_btn.Exists(3)}")
box = s.safe_bounding_rect(settings_btn)
cx, cy = s.center_of(box)
print(f"Settings center: ({cx}, {cy})")

# Try auto.Click
print("Clicking via auto.Click...")
auto.Click(cx, cy)
time.sleep(2.0)

# Check for Settings window
found = False
for win in auto.GetRootControl().GetChildren():
    wname = (win.Name or "").lower()
    if "settings" in wname:
        print(f"SUCCESS: Found Settings window: {win.Name} hwnd={win.NativeWindowHandle}")
        found = True
        # Enumerate tabs
        trav = s.DialogTraversal()
        tabs = trav._find_tabs(win)
        print(f"Tabs ({len(tabs)}): {[t.Name for t in tabs]}")
        trav._close_safely(win, win.NativeWindowHandle)
        print("Settings dialog safely closed.")
        break

if not found:
    print("Settings dialog NOT found after auto.Click")
    # Try InvokePattern
    print("Trying InvokePattern.Invoke()...")
    try:
        pat = settings_btn.GetInvokePattern()
        if pat:
            pat.Invoke()
            time.sleep(2.0)
            for win in auto.GetRootControl().GetChildren():
                wname = (win.Name or "").lower()
                if "settings" in wname:
                    print(f"SUCCESS via Invoke: {win.Name}")
                    found = True
                    trav = s.DialogTraversal()
                    tabs = trav._find_tabs(win)
                    print(f"Tabs ({len(tabs)}): {[t.Name for t in tabs]}")
                    trav._close_safely(win, win.NativeWindowHandle)
                    break
    except Exception as e:
        print(f"InvokePattern error: {e}")

if not found:
    print("FAILED: Could not open Settings from console helper either.")

# Write result for parent process to read
result = {"found": found, "fg_after": fg_after, "set_fg_res": res}
with open("scratch_helper_result.json", "w") as f:
    json.dump(result, f)

print("Helper done.")
input("Press Enter to close...")
