import ctypes
import os
import sys

# CRITICAL: Attach to interactive desktop BEFORE importing any COM/GUI
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    res = user32.SetThreadDesktop(hdesk)
    print(f"SetThreadDesktop: {res} err: {kernel32.GetLastError()}")
else:
    print(f"OpenInputDesktop failed: {kernel32.GetLastError()}")

import time
import win32gui
import win32con
import uiautomation as auto
import organ_30_app_scanner as s

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Find OBS window via UIA
hwnd = None
for win in auto.GetRootControl().GetChildren():
    wname = win.Name or ""
    if "obs" in wname.lower() and "crash" not in wname.lower():
        hwnd = win.NativeWindowHandle
        print(f"Found running OBS via UIA: hwnd={hwnd} title='{wname}'")
        break

if not hwnd:
    print("OBS not found running via UIA!")
    sys.exit(1)

# Bring OBS to foreground
print("Bringing OBS to foreground...")
user32.ShowWindow(hwnd, win32con.SW_RESTORE)
time.sleep(0.1)
user32.SetForegroundWindow(hwnd)
time.sleep(0.5)

fg = user32.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(512)
user32.GetWindowTextW(fg, buf, 512)
print(f"Foreground now: hwnd={fg} title='{buf.value}'")

# Test 1: Settings button click via ctypes
print("\n--- TEST 1: SETTINGS BUTTON ---")
root = auto.ControlFromHandle(hwnd)
settings_btn = root.ButtonControl(Name="Settings")
print(f"Settings btn exists: {settings_btn.Exists(3)}")
if settings_btn.Exists(0):
    box = s.safe_bounding_rect(settings_btn)
    cx, cy = s.center_of(box)
    print(f"Settings coords: ({cx}, {cy}) box={box}")
    
    # Click with ctypes
    user32.SetCursorPos(cx, cy)
    time.sleep(0.12)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(1.5)
    
    # Check if Settings opened
    found_settings = False
    for win in auto.GetRootControl().GetChildren():
        wname = (win.Name or "").strip()
        if "settings" in wname.lower():
            print(f"SUCCESS: Found Settings window: '{wname}' hwnd={win.NativeWindowHandle}")
            found_settings = True
            trav = s.DialogTraversal()
            tabs = trav._find_tabs(win)
            print(f"Found {len(tabs)} tabs: {[t.Name for t in tabs]}")
            for tab in tabs:
                tbox = s.safe_bounding_rect(tab)
                if tbox and s.is_onscreen(tbox):
                    tcx, tcy = s.center_of(tbox)
                    print(f"  Clicking tab '{tab.Name}' at ({tcx}, {tcy})...")
                    user32.SetCursorPos(tcx, tcy)
                    time.sleep(0.1)
                    user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    time.sleep(0.06)
                    user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    time.sleep(0.3)
                    ctrls = trav._collect_controls(win, parent_tab=tab.Name)
                    print(f"    Tab '{tab.Name}' controls: {len(ctrls)}")
            trav._close_safely(win, win.NativeWindowHandle)
            print("Settings window closed safely.")
            break
    
    if not found_settings:
        print("Settings window did not open via click. Trying InvokePattern...")
        try:
            pat = settings_btn.GetInvokePattern()
            if pat:
                pat.Invoke()
                print("Invoked Settings button.")
                time.sleep(2)
                for win in auto.GetRootControl().GetChildren():
                    wname = (win.Name or "").strip()
                    if "settings" in wname.lower():
                        print(f"SUCCESS via Invoke: '{wname}'")
                        trav = s.DialogTraversal()
                        tabs = trav._find_tabs(win)
                        print(f"Tabs: {[t.Name for t in tabs]}")
                        trav._close_safely(win, win.NativeWindowHandle)
                        break
        except Exception as e:
            print("Invoke error:", e)

# Test 2: Menu interaction
print("\n--- TEST 2: MENU NAVIGATION ---")
user32.SetForegroundWindow(hwnd)
time.sleep(0.3)

# Test Alt+F
user32.keybd_event(win32con.VK_MENU, 0, 0, 0)
time.sleep(0.06)
user32.keybd_event(ord('F'), 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(ord('F'), 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.04)
user32.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.5)

fc = auto.GetFocusedControl()
print(f"Focused after Alt+F: Name='{fc.Name if fc else None}' Type='{fc.ControlTypeName if fc else None}'")

# Close menu with Escape
user32.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)

print("\nDone testing.")
