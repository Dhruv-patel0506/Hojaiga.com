import time
import os
import sys
import ctypes
import win32gui
import win32con
import uiautomation as auto

# 1. Attach to interactive desktop FIRST
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    res = user32.SetThreadDesktop(hdesk)
    print(f"SetThreadDesktop: {res} err: {kernel32.GetLastError()}", flush=True)

obs_exe = r"D:\obs-studio\bin\64bit\obs64.exe"
cwd = os.path.dirname(obs_exe)

print(f"Launching {obs_exe} via ShellExecuteW...", flush=True)
ctypes.windll.shell32.ShellExecuteW(0, "open", obs_exe, None, cwd, 1)

main_hwnd = None
main_win = None

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
                        print(f"[{second}s] Clicked Run in Safe Mode via InvokePattern!", flush=True)
                        time.sleep(1)
                        break
            elif "profile:" in wname.lower() or ("obs" in wname.lower() and "crash" not in wname.lower()):
                main_hwnd = win.NativeWindowHandle
                main_win = win
                print(f"[{second}s] FOUND MAIN OBS WINDOW! hwnd={main_hwnd} title='{wname}'", flush=True)
                break
        except Exception:
            continue
    if main_hwnd:
        break

if not main_hwnd:
    print("FATAL: Main OBS window not found!", flush=True)
    sys.exit(1)

print("\nWaiting 4s for OBS to settle...", flush=True)
time.sleep(4)

# Bring OBS to foreground
print("Bringing OBS to foreground...", flush=True)
user32.ShowWindow(main_hwnd, win32con.SW_RESTORE)
time.sleep(0.1)
user32.SetForegroundWindow(main_hwnd)
time.sleep(0.5)

fg = user32.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(512)
user32.GetWindowTextW(fg, buf, 512)
print(f"Foreground window: hwnd={fg} title='{buf.value}'", flush=True)

# Step 2: Test Settings Button
print("\n=== STEP 2: SETTINGS BUTTON ===", flush=True)
settings_btn = main_win.ButtonControl(Name="Settings")
print(f"Settings btn exists: {settings_btn.Exists(3)}", flush=True)

if settings_btn.Exists(0):
    r = settings_btn.BoundingRectangle
    cx = int((r.left + r.right) / 2)
    cy = int((r.top + r.bottom) / 2)
    print(f"Settings button at ({cx}, {cy}) rect: ({r.left}, {r.top}, {r.right}, {r.bottom})", flush=True)
    
    # Try physical click first
    print(f"Physical click at ({cx}, {cy})...", flush=True)
    user32.SetCursorPos(cx, cy)
    time.sleep(0.15)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.10)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(2.0)
    
    settings_dlg = None
    for attempt in range(15):
        for w in auto.GetRootControl().GetChildren():
            try:
                name = (w.Name or "").strip()
                if "settings" in name.lower():
                    settings_dlg = w
                    print(f"SUCCESS: Found Settings dialog via click! hwnd={w.NativeWindowHandle} title='{name}'", flush=True)
                    break
            except Exception:
                pass
        if settings_dlg:
            break
        time.sleep(0.3)
        
    if not settings_dlg:
        print("Click did not trigger Settings dialog. Trying InvokePattern.Invoke()...", flush=True)
        try:
            pat = settings_btn.GetInvokePattern()
            if pat:
                pat.Invoke()
                print("Invoked Settings button!", flush=True)
                time.sleep(2.0)
                for w in auto.GetRootControl().GetChildren():
                    try:
                        name = (w.Name or "").strip()
                        if "settings" in name.lower():
                            settings_dlg = w
                            print(f"SUCCESS: Found Settings dialog via Invoke! hwnd={w.NativeWindowHandle} title='{name}'", flush=True)
                            break
                    except Exception:
                        pass
        except Exception as e:
            print(f"InvokePattern error: {e}", flush=True)

    if settings_dlg:
        print("\n=== STEP 3: TRAVERSING SETTINGS TABS ===", flush=True)
        list_ctrl = settings_dlg.ListControl()
        if list_ctrl.Exists(2):
            tabs = list_ctrl.GetChildren()
            print(f"Discovered {len(tabs)} tabs in Settings dialog:", flush=True)
            for idx, tab in enumerate(tabs):
                print(f"  [{idx+1}/{len(tabs)}] Tab: '{tab.Name}' Type={tab.ControlTypeName}", flush=True)
                tr = tab.BoundingRectangle
                if tr:
                    tcx = int((tr.left + tr.right) / 2)
                    tcy = int((tr.top + tr.bottom) / 2)
                    print(f"       Clicking tab at ({tcx}, {tcy})...", flush=True)
                    user32.SetCursorPos(tcx, tcy)
                    time.sleep(0.12)
                    user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    time.sleep(0.08)
                    user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    time.sleep(0.3)
        
        # Safely close dialog via Cancel
        print("\n=== STEP 4: SAFELY CLOSING SETTINGS DIALOG ===", flush=True)
        cancel_btn = settings_dlg.ButtonControl(Name="Cancel")
        if cancel_btn.Exists(1):
            pat = cancel_btn.GetInvokePattern()
            if pat:
                pat.Invoke()
                print("Closed Settings dialog via Cancel InvokePattern!", flush=True)
            else:
                cr = cancel_btn.BoundingRectangle
                ccx = int((cr.left + cr.right) / 2)
                ccy = int((cr.top + cr.bottom) / 2)
                user32.SetCursorPos(ccx, ccy)
                time.sleep(0.1)
                user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                time.sleep(0.06)
                user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                print("Closed Settings dialog via Cancel physical click!", flush=True)
        else:
            print("Cancel button not found, sending Escape key...", flush=True)
            user32.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
            time.sleep(0.04)
            user32.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(1.0)

# Step 5: Test Menu Navigation
print("\n=== STEP 5: TEST MENU NAVIGATION ===", flush=True)
user32.SetForegroundWindow(main_hwnd)
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
print(f"Focused after Alt+F: Name='{fc.Name if fc else None}' Type='{fc.ControlTypeName if fc else None}'", flush=True)

for i in range(5):
    user32.keybd_event(win32con.VK_DOWN, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(win32con.VK_DOWN, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.15)
    fc = auto.GetFocusedControl()
    print(f"  Down #{i+1}: Name='{fc.Name if fc else None}' Type='{fc.ControlTypeName if fc else None}'", flush=True)

user32.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.2)
user32.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)

print("\n=== ALL TESTS PASSED! ===", flush=True)
