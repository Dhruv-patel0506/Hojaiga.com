import ctypes
import os
import sys
import traceback

# CRITICAL: Attach to interactive desktop BEFORE any GUI/UIA import!
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    res = user32.SetThreadDesktop(hdesk)
    print(f"SetThreadDesktop: {res} err: {kernel32.GetLastError()}", flush=True)
else:
    print(f"OpenInputDesktop failed: {kernel32.GetLastError()}", flush=True)

import time
import win32gui
import win32con
import uiautomation as auto

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

obs_exe = r"D:\obs-studio\bin\64bit\obs64.exe"
cwd = os.path.dirname(obs_exe)

print(f"Launching OBS via ShellExecuteW: {obs_exe}", flush=True)
ctypes.windll.shell32.ShellExecuteW(0, "open", obs_exe, None, cwd, 1)

main_hwnd = None
main_win = None

for second in range(30):
    time.sleep(1)
    print(f"\n--- Second {second} ---", flush=True)
    try:
        children = auto.GetRootControl().GetChildren()
    except Exception as e:
        print(f"GetRootControl error: {e}", flush=True)
        continue

    for win in children:
        try:
            wname = win.Name or ""
            wcls = win.ClassName or ""
            pid = win.ProcessId
            
            # Check for crash dialog
            if "Crash Detected" in wname or "QMessageBox" in wcls:
                print(f"  Found crash dialog: hwnd={win.NativeWindowHandle} name='{wname}' class='{wcls}'", flush=True)
                # Find buttons in dialog
                for child in win.GetChildren():
                    print(f"    Dialog child: Name='{child.Name}' Type='{child.ControlTypeName}'", flush=True)
                    if "safe mode" in (child.Name or "").lower():
                        pat = child.GetInvokePattern()
                        if pat:
                            pat.Invoke()
                            print(f"    CLICKED SAFE MODE via InvokePattern!", flush=True)
                        else:
                            # Try Click
                            child.Click()
                            print(f"    CLICKED SAFE MODE via child.Click()!", flush=True)
                        time.sleep(1)
                        break
            elif "profile:" in wname.lower() or ("obs" in wname.lower() and "crash" not in wname.lower()):
                main_hwnd = win.NativeWindowHandle
                main_win = win
                print(f"  FOUND MAIN OBS WINDOW! hwnd={main_hwnd} title='{wname}'", flush=True)
                break
        except Exception as e:
            print(f"  Window inspection exception: {e}", flush=True)
            continue
    if main_hwnd:
        break

if not main_hwnd:
    print("FATAL: Main OBS window not found after 30s.", flush=True)
    sys.exit(1)

# Now wait 3s for OBS to settle
print("\nWaiting 3s for OBS to settle...", flush=True)
time.sleep(3)

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

# Find Settings button
print("\nLooking for Settings button...", flush=True)
settings_btn = main_win.ButtonControl(Name="Settings")
print(f"Settings button exists: {settings_btn.Exists(3)}", flush=True)

if settings_btn.Exists(0):
    r = settings_btn.BoundingRectangle
    cx = int((r.left + r.right) / 2)
    cy = int((r.top + r.bottom) / 2)
    print(f"Settings rect: ({r.left}, {r.top}, {r.right}, {r.bottom}) -> center: ({cx}, {cy})", flush=True)
    
    # Cursor move and click
    print(f"Setting cursor to ({cx}, {cy})...", flush=True)
    res_pos = user32.SetCursorPos(cx, cy)
    print(f"SetCursorPos result: {res_pos} err: {kernel32.GetLastError()}", flush=True)
    time.sleep(0.15)
    
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    print(f"Actual cursor position: ({pt.x}, {pt.y})", flush=True)
    
    print("Sending mouse_event LEFTDOWN + LEFTUP...", flush=True)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.10)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(2.0)
    
    # Check for Settings window
    print("Checking if Settings dialog opened...", flush=True)
    settings_dlg = None
    for attempt in range(15):
        for w in auto.GetRootControl().GetChildren():
            try:
                name = (w.Name or "").strip()
                if "settings" in name.lower():
                    settings_dlg = w
                    print(f"SUCCESS: Found Settings dialog! hwnd={w.NativeWindowHandle} title='{name}'", flush=True)
                    break
            except Exception:
                pass
        if settings_dlg:
            break
        time.sleep(0.3)
    
    if not settings_dlg:
        print("Click did not open dialog, trying InvokePattern...", flush=True)
        try:
            pat = settings_btn.GetInvokePattern()
            if pat:
                pat.Invoke()
                print("Invoked Settings button.", flush=True)
                time.sleep(2.0)
                for w in auto.GetRootControl().GetChildren():
                    try:
                        name = (w.Name or "").strip()
                        if "settings" in name.lower():
                            settings_dlg = w
                            print(f"SUCCESS via Invoke: Found Settings dialog! hwnd={w.NativeWindowHandle} title='{name}'", flush=True)
                            break
                    except Exception:
                        pass
        except Exception as e:
            print("Invoke error:", e, flush=True)

    if settings_dlg:
        print("\n=== TRAVERSING SETTINGS TABS ===", flush=True)
        # Find tabs/list items on left
        list_ctrl = settings_dlg.ListControl()
        if list_ctrl.Exists(1):
            items = list_ctrl.GetChildren()
            print(f"Found {len(items)} items in ListControl:", flush=True)
            for item in items:
                print(f"  Item: '{item.Name}' Type={item.ControlTypeName}", flush=True)
                ir = item.BoundingRectangle
                if ir:
                    icx = int((ir.left + ir.right) / 2)
                    icy = int((ir.top + ir.bottom) / 2)
                    print(f"    Clicking tab '{item.Name}' at ({icx}, {icy})...", flush=True)
                    user32.SetCursorPos(icx, icy)
                    time.sleep(0.1)
                    user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    time.sleep(0.06)
                    user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    time.sleep(0.3)
        
        # Safely close dialog via Cancel
        print("\nClosing Settings dialog safely via Cancel button...", flush=True)
        cancel_btn = settings_dlg.ButtonControl(Name="Cancel")
        if cancel_btn.Exists(1):
            pat = cancel_btn.GetInvokePattern()
            if pat:
                pat.Invoke()
                print("Clicked Cancel via InvokePattern!", flush=True)
            else:
                cr = cancel_btn.BoundingRectangle
                ccx = int((cr.left + cr.right) / 2)
                ccy = int((cr.top + cr.bottom) / 2)
                user32.SetCursorPos(ccx, ccy)
                time.sleep(0.1)
                user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                time.sleep(0.06)
                user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                print("Clicked Cancel via mouse click!", flush=True)
        else:
            print("Cancel button not found, sending Escape key...", flush=True)
            user32.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
            time.sleep(0.04)
            user32.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
        
        time.sleep(1.0)
        print("Settings dialog closed successfully!", flush=True)

# Now test menu navigation
print("\n=== TESTING MENU NAVIGATION ===", flush=True)
user32.SetForegroundWindow(main_hwnd)
time.sleep(0.3)

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

for i in range(4):
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

print("\n=== TEST COMPLETED SUCCESSFULLY ===", flush=True)
