import ctypes
import os
import sys

# 1. Attach to input desktop FIRST before ANY other import!
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    res = user32.SetThreadDesktop(hdesk)
    print(f"SetThreadDesktop: {res} (err: {kernel32.GetLastError()})")
else:
    print(f"OpenInputDesktop failed: {kernel32.GetLastError()}")

import time
import win32gui
import win32con
import uiautomation as auto
import organ_30_app_scanner as s

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("Launching/ensuring OBS...")
obs_exe = r"D:\obs-studio\bin\64bit\obs64.exe"
hwnd = None

# Check if already running
hwnd = s.find_hwnd_by_title_substring("OBS")
if not hwnd:
    working_dir = os.path.dirname(obs_exe)
    ctypes.windll.shell32.ShellExecuteW(0, "open", obs_exe, None, working_dir, 1)
    print("Launched obs64.exe, waiting for window...")

    for attempt in range(25):
        time.sleep(1)
        # Check for crash dialog
        for win in auto.GetRootControl().GetChildren():
            wname = win.Name or ""
            if "Crash Detected" in wname:
                btn = win.ButtonControl(Name="Run in Safe Mode")
                if btn.Exists(1):
                    pat = btn.GetInvokePattern()
                    if pat:
                        pat.Invoke()
                        print("Auto-dismissed startup crash dialog (Run in Safe Mode).")
            elif "profile:" in wname.lower() or ("obs" in wname.lower() and "crash" not in wname.lower()):
                hwnd = win.NativeWindowHandle
                print(f"Found OBS window: hwnd={hwnd} title='{wname}'")
                break
        if hwnd:
            break

if not hwnd:
    hwnd = s.find_hwnd_by_title_substring("OBS")

print(f"Final OBS HWND: {hwnd}")
if not hwnd:
    sys.exit(1)

# Allow OBS to fully settle
print("Waiting 4s for OBS to settle...")
time.sleep(4)

# Bring OBS to foreground
print("Bringing OBS to foreground...")
s.bring_to_foreground(hwnd)
time.sleep(0.5)

fg = user32.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(512)
user32.GetWindowTextW(fg, buf, 512)
print(f"Foreground now: hwnd={fg} title='{buf.value}'")

root = auto.ControlFromHandle(hwnd)
settings_btn = root.ButtonControl(Name="Settings")
print(f"Settings btn exists: {settings_btn.Exists(3)}")

box = s.safe_bounding_rect(settings_btn)
cx, cy = s.center_of(box)
print(f"Settings center: ({cx}, {cy})")

# Test physical click
print(f"Physical click at ({cx}, {cy})...")
user32.SetCursorPos(cx, cy)
time.sleep(0.12)
user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
time.sleep(0.08)
user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
time.sleep(2.0)

# Check for Settings dialog
print("Checking for Settings dialog...")
found = False
for i in range(15):
    for win in auto.GetRootControl().GetChildren():
        wname = (win.Name or "").strip()
        if "settings" in wname.lower():
            print(f"SUCCESS: FOUND SETTINGS DIALOG! hwnd={win.NativeWindowHandle} title='{wname}'")
            found = True
            trav = s.DialogTraversal()
            tabs = trav._find_tabs(win)
            print(f"Found {len(tabs)} tabs in Settings dialog:")
            for tab in tabs:
                print(f"  Tab: '{tab.Name}'")
            trav._close_safely(win, win.NativeWindowHandle)
            print("Settings dialog safely closed.")
            break
    if found:
        break
    time.sleep(0.3)

if not found:
    print("Settings dialog NOT found via mouse click. Testing InvokePattern...")
    try:
        pat = settings_btn.GetInvokePattern()
        if pat:
            pat.Invoke()
            print("Invoke called.")
            time.sleep(2)
            for win in auto.GetRootControl().GetChildren():
                wname = (win.Name or "").strip()
                if "settings" in wname.lower():
                    print(f"SUCCESS via Invoke: FOUND SETTINGS DIALOG! hwnd={win.NativeWindowHandle}")
                    found = True
                    trav = s.DialogTraversal()
                    tabs = trav._find_tabs(win)
                    print(f"Found {len(tabs)} tabs in Settings dialog:")
                    for tab in tabs:
                        print(f"  Tab: '{tab.Name}'")
                    trav._close_safely(win, win.NativeWindowHandle)
                    print("Settings dialog safely closed.")
                    break
    except Exception as e:
        print("InvokePattern error:", e)

print("Testing Alt+F menu...")
s.bring_to_foreground(hwnd)
time.sleep(0.3)
s.send_alt_sequence("%f")
time.sleep(0.5)
fc = auto.GetFocusedControl()
print("Focused in menu:", fc.Name if fc else None)
s.send_keys(win32con.VK_ESCAPE)
print("Done!")
