import ctypes
import os
import sys

# 1. Attach to interactive desktop FIRST before ANY other import!
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

obs_exe = r"D:\obs-studio\bin\64bit\obs64.exe"
cwd = os.path.dirname(obs_exe)

# Step 1: Find or Launch OBS
hwnd = None
for win in auto.GetRootControl().GetChildren():
    try:
        wname = win.Name or ""
        if "profile:" in wname.lower() or ("obs" in wname.lower() and "crash" not in wname.lower() and "running" not in wname.lower()):
            hwnd = win.NativeWindowHandle
            print(f"Found running OBS window: hwnd={hwnd} title='{wname}'")
            break
    except Exception:
        continue

if not hwnd:
    print(f"Launching OBS from: {obs_exe}")
    ctypes.windll.shell32.ShellExecuteW(0, "open", obs_exe, None, cwd, 1)
    
    # Wait for window
    for second in range(30):
        time.sleep(1)
        for win in auto.GetRootControl().GetChildren():
            try:
                wname = win.Name or ""
                wcls = win.ClassName or ""
                if "Crash Detected" in wname or "QMessageBox" in wcls:
                    btn = win.ButtonControl(Name="Run in Safe Mode")
                    if btn.Exists(0.5):
                        pat = btn.GetInvokePattern()
                        if pat:
                            pat.Invoke()
                            print(f"[{second}s] Clicked Run in Safe Mode via InvokePattern!")
                            time.sleep(1)
                            break
                elif "Already Running" in wname:
                    btn = win.ButtonControl(Name="Launch Anyway")
                    if btn.Exists(0.5):
                        pat = btn.GetInvokePattern()
                        if pat:
                            pat.Invoke()
                            print(f"[{second}s] Clicked Launch Anyway!")
                            time.sleep(1)
                            break
                elif "profile:" in wname.lower() or ("obs" in wname.lower() and "crash" not in wname.lower()):
                    hwnd = win.NativeWindowHandle
                    print(f"[{second}s] FOUND MAIN OBS WINDOW! hwnd={hwnd} title='{wname}'")
                    break
            except Exception:
                continue
        if hwnd:
            break

if not hwnd:
    print("FATAL: OBS main window not found!")
    sys.exit(1)

# Step 2: Settle and Bring to Foreground
print("Waiting 3s for OBS to settle...")
time.sleep(3)

print("Bringing OBS to foreground...")
user32.ShowWindow(hwnd, win32con.SW_RESTORE)
time.sleep(0.1)
user32.SetForegroundWindow(hwnd)
time.sleep(0.5)

fg = user32.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(512)
user32.GetWindowTextW(fg, buf, 512)
print(f"Foreground now: hwnd={fg} title='{buf.value}'")

# Step 3: Find and Click Settings Button
print("\n=== STEP 3: CLICK SETTINGS BUTTON ===")
root = auto.ControlFromHandle(hwnd)
settings_btn = root.ButtonControl(Name="Settings")
print(f"Settings btn exists: {settings_btn.Exists(3)}")

if settings_btn.Exists(0):
    box = s.safe_bounding_rect(settings_btn)
    cx, cy = s.center_of(box)
    print(f"Settings coords: ({cx}, {cy}) box={box}")
    
    # Click with ctypes
    print(f"Clicking at ({cx}, {cy})...")
    user32.SetCursorPos(cx, cy)
    time.sleep(0.15)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.10)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(2.0)
    
    # Check if Settings opened
    found_settings = False
    for win in auto.GetRootControl().GetChildren():
        try:
            wname = (win.Name or "").strip()
            if "settings" in wname.lower():
                print(f"\nSUCCESS! FOUND SETTINGS DIALOG! hwnd={win.NativeWindowHandle} title='{wname}'")
                found_settings = True
                trav = s.DialogTraversal()
                tabs = trav._find_tabs(win)
                print(f"Found {len(tabs)} tabs in Settings dialog:")
                for tab in tabs:
                    tbox = s.safe_bounding_rect(tab)
                    print(f"  Tab: '{tab.Name}' box={tbox}")
                    if tbox and s.is_onscreen(tbox):
                        tcx, tcy = s.center_of(tbox)
                        user32.SetCursorPos(tcx, tcy)
                        time.sleep(0.1)
                        user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                        time.sleep(0.06)
                        user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        time.sleep(0.3)
                        ctrls = trav._collect_controls(win, parent_tab=tab.Name)
                        print(f"    Tab '{tab.Name}' controls: {len(ctrls)}")
                
                # Safely close dialog via Cancel
                trav._close_safely(win, win.NativeWindowHandle)
                print("Settings dialog safely closed.")
                break
        except Exception as e:
            print("Settings traversal error:", e)
    
    if not found_settings:
        print("Settings dialog did not open via click. Testing InvokePattern...")
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

# Step 4: Test Menu Navigation
print("\n=== STEP 4: TEST MENU NAVIGATION ===")
user32.SetForegroundWindow(hwnd)
time.sleep(0.3)

# Send Alt+F
user32.keybd_event(win32con.VK_MENU, 0, 0, 0)
time.sleep(0.06)
user32.keybd_event(ord('F'), 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(ord('F'), 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.04)
user32.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.5)

fc = auto.GetFocusedControl()
print(f"Focused control after Alt+F: Name='{fc.Name if fc else None}' Type='{fc.ControlTypeName if fc else None}'")

# Press Down 3 times and read focus
for step in range(3):
    user32.keybd_event(win32con.VK_DOWN, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(win32con.VK_DOWN, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.2)
    fc = auto.GetFocusedControl()
    print(f"  Down #{step+1}: Name='{fc.Name if fc else None}' Type='{fc.ControlTypeName if fc else None}'")

# Close menu
user32.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.2)
user32.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)

print("\n=== ALL TESTS FINISHED ===")
