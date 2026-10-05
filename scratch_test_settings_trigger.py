import time
import os
import sys
import ctypes

# 1. ATTACH TO INTERACTIVE DESKTOP BEFORE ANY COM/GUI IMPORT
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    res = user32.SetThreadDesktop(hdesk)
    print(f"SetThreadDesktop: {res} (err: {kernel32.GetLastError()})", flush=True)

import win32gui
import win32con
import win32process
import uiautomation as auto

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
auto.SetGlobalSearchTimeout(1.5)

obs_exe = r"D:\obs-studio\bin\64bit\obs64.exe"
cwd = os.path.dirname(obs_exe)

print(f"Launching {obs_exe}...", flush=True)
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
                        print(f"[{second}s] Auto-dismissed Safe Mode prompt!", flush=True)
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

print("\nWaiting 3s for OBS to settle...", flush=True)
time.sleep(3)

# Find Settings button in UIA tree
settings_btn = main_win.ButtonControl(Name="Settings")
print(f"Settings btn exists: {settings_btn.Exists(3)}", flush=True)
print(f"Settings btn IsEnabled: {settings_btn.IsEnabled}", flush=True)
print(f"Settings btn IsOffscreen: {settings_btn.IsOffscreen}", flush=True)
print(f"Settings btn ClassName: {settings_btn.ClassName}", flush=True)
print(f"Settings btn AutomationId: {settings_btn.AutomationId}", flush=True)
r = settings_btn.BoundingRectangle
cx = int((r.left + r.right) / 2)
cy = int((r.top + r.bottom) / 2)
print(f"Settings btn BoundingRect: {r} -> center: ({cx}, {cy})", flush=True)

def check_settings_opened():
    for w in auto.GetRootControl().GetChildren():
        try:
            name = (w.Name or "").strip()
            if "settings" in name.lower() and "obs" not in name.lower():
                return w
        except Exception:
            pass
    return None

# METHOD 1: InvokePattern
print("\n--- ATTEMPT 1: InvokePattern.Invoke() ---", flush=True)
try:
    pat = settings_btn.GetInvokePattern()
    if pat:
        pat.Invoke()
        print("pat.Invoke() called.", flush=True)
    else:
        print("No InvokePattern!", flush=True)
except Exception as e:
    print("InvokePattern error:", e, flush=True)

time.sleep(2.0)
dlg = check_settings_opened()
if dlg:
    print(f"SUCCESS via Method 1! Found dialog: '{dlg.Name}' hwnd={dlg.NativeWindowHandle}", flush=True)
else:
    print("Method 1 failed. Dialog not opened.", flush=True)

# METHOD 2: UIA Click
if not dlg:
    print("\n--- ATTEMPT 2: auto.Click(cx, cy) ---", flush=True)
    try:
        auto.Click(cx, cy)
        print("auto.Click(cx, cy) called.", flush=True)
    except Exception as e:
        print("auto.Click error:", e, flush=True)
    time.sleep(2.0)
    dlg = check_settings_opened()
    if dlg:
        print(f"SUCCESS via Method 2! Found dialog: '{dlg.Name}' hwnd={dlg.NativeWindowHandle}", flush=True)
    else:
        print("Method 2 failed.", flush=True)

# METHOD 3: AttachThreadInput + SetForegroundWindow + ctypes mouse_event
if not dlg:
    print("\n--- ATTEMPT 3: AttachThreadInput + Foreground + ctypes mouse click ---", flush=True)
    cur_tid = kernel32.GetCurrentThreadId()
    obs_tid, obs_pid = win32process.GetWindowThreadProcessId(main_hwnd)
    print(f"Current TID: {cur_tid}, OBS TID: {obs_tid}", flush=True)
    
    # Attach thread input
    user32.AttachThreadInput(cur_tid, obs_tid, True)
    user32.ShowWindow(main_hwnd, win32con.SW_RESTORE)
    user32.SetForegroundWindow(main_hwnd)
    user32.BringWindowToTop(main_hwnd)
    user32.SetFocus(main_hwnd)
    time.sleep(0.3)
    
    fg = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(fg, buf, 512)
    print(f"Foreground window after attach: hwnd={fg} title='{buf.value}'", flush=True)
    
    user32.SetCursorPos(cx, cy)
    time.sleep(0.15)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.10)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(2.0)
    
    dlg = check_settings_opened()
    user32.AttachThreadInput(cur_tid, obs_tid, False)
    if dlg:
        print(f"SUCCESS via Method 3! Found dialog: '{dlg.Name}' hwnd={dlg.NativeWindowHandle}", flush=True)
    else:
        print("Method 3 failed.", flush=True)

# METHOD 4: Menu Navigation: Alt+F, then 'S'
if not dlg:
    print("\n--- ATTEMPT 4: Menu Alt+F then 'S' ---", flush=True)
    cur_tid = kernel32.GetCurrentThreadId()
    obs_tid, obs_pid = win32process.GetWindowThreadProcessId(main_hwnd)
    user32.AttachThreadInput(cur_tid, obs_tid, True)
    user32.SetForegroundWindow(main_hwnd)
    time.sleep(0.2)
    
    # Alt+F
    user32.keybd_event(win32con.VK_MENU, 0, 0, 0)
    time.sleep(0.06)
    user32.keybd_event(ord('F'), 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(ord('F'), 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.04)
    user32.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.5)
    
    fc = auto.GetFocusedControl()
    print(f"Focused control after Alt+F: Name='{fc.Name if fc else None}' Type='{fc.ControlTypeName if fc else None}'", flush=True)
    
    # Press 'S' (Settings accelerator in File menu)
    user32.keybd_event(ord('S'), 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(ord('S'), 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(2.0)
    
    dlg = check_settings_opened()
    user32.AttachThreadInput(cur_tid, obs_tid, False)
    if dlg:
        print(f"SUCCESS via Method 4! Found dialog: '{dlg.Name}' hwnd={dlg.NativeWindowHandle}", flush=True)
    else:
        print("Method 4 failed.", flush=True)
        # Clean up menu
        user32.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
        time.sleep(0.04)
        user32.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)

if dlg:
    print("\n=== SETTINGS DIALOG INSPECTION ===", flush=True)
    print(f"Dialog Name: '{dlg.Name}' Class: '{dlg.ClassName}' HWND: {dlg.NativeWindowHandle}", flush=True)
    list_ctrl = dlg.ListControl()
    if list_ctrl.Exists(2):
        tabs = list_ctrl.GetChildren()
        print(f"Tabs discovered ({len(tabs)}):", flush=True)
        for t in tabs:
            print(f"  Tab: '{t.Name}'", flush=True)
    
    # Close safely
    cancel_btn = dlg.ButtonControl(Name="Cancel")
    if cancel_btn.Exists(1):
        pat = cancel_btn.GetInvokePattern()
        if pat:
            pat.Invoke()
            print("Closed via Cancel InvokePattern!", flush=True)
        else:
            cancel_btn.Click()
            print("Closed via Cancel Click!", flush=True)
    else:
        user32.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
        time.sleep(0.04)
        user32.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
        print("Closed via Escape key!", flush=True)
    time.sleep(1.0)

print("\n=== FINISHED ===", flush=True)
