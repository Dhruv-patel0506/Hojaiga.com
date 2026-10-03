import time
import os
import sys
import threading
import ctypes
import win32gui
import win32con
import uiautomation as auto

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def run_in_interactive_thread(target_func, *args, **kwargs):
    """Executes target_func inside a clean thread attached to the interactive input desktop."""
    res = [None]
    err = [None]
    def _runner():
        try:
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
            res[0] = target_func(*args, **kwargs)
        except Exception as e:
            err[0] = e
    t = threading.Thread(target=_runner)
    t.start()
    t.join()
    if err[0]:
        raise err[0]
    return res[0]

def worker_click(x, y, settle=0.15):
    user32.SetCursorPos(x, y)
    time.sleep(0.12)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(settle)
    return True

def worker_set_foreground(hwnd):
    user32.ShowWindow(hwnd, win32con.SW_RESTORE)
    time.sleep(0.05)
    # Alt pulse to ensure foreground transfer allowed
    user32.keybd_event(win32con.VK_MENU, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)
    return user32.SetForegroundWindow(hwnd)

def worker_send_keys(*vks):
    for vk in vks:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.04)
        user32.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.06)

def worker_alt_key(ch):
    user32.keybd_event(win32con.VK_MENU, 0, 0, 0)
    time.sleep(0.06)
    vk = ord(ch.upper())
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.04)
    user32.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.2)

obs_exe = r"D:\obs-studio\bin\64bit\obs64.exe"
cwd = os.path.dirname(obs_exe)

print(f"Launching OBS...", flush=True)
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
                        print(f"[{second}s] Auto-dismissed startup crash dialog!", flush=True)
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
    print("FATAL: OBS not found!", flush=True)
    sys.exit(1)

print("\nWaiting 3s for OBS to settle...", flush=True)
time.sleep(3)

print("Setting OBS foreground via worker...", flush=True)
fg_res = run_in_interactive_thread(worker_set_foreground, main_hwnd)
print(f"SetForegroundWindow result: {fg_res}", flush=True)
time.sleep(0.5)

# Find Settings button
settings_btn = main_win.ButtonControl(Name="Settings")
print(f"Settings button exists: {settings_btn.Exists(3)}", flush=True)

r = settings_btn.BoundingRectangle
cx = int((r.left + r.right) / 2)
cy = int((r.top + r.bottom) / 2)
print(f"Settings center: ({cx}, {cy})", flush=True)

print(f"Clicking Settings at ({cx}, {cy}) via worker thread...", flush=True)
run_in_interactive_thread(worker_click, cx, cy)
time.sleep(2.0)

# Check for Settings dialog
settings_dlg = None
for w in auto.GetRootControl().GetChildren():
    name = (w.Name or "").strip()
    if "settings" in name.lower():
        settings_dlg = w
        print(f"SUCCESS: Found Settings dialog! hwnd={w.NativeWindowHandle} title='{name}'", flush=True)
        break

if not settings_dlg:
    print("Settings did not open via click. Trying InvokePattern...", flush=True)
    pat = settings_btn.GetInvokePattern()
    if pat:
        pat.Invoke()
        print("Invoked Settings button!", flush=True)
        time.sleep(2.0)
        for w in auto.GetRootControl().GetChildren():
            name = (w.Name or "").strip()
            if "settings" in name.lower():
                settings_dlg = w
                print(f"SUCCESS via Invoke: Found Settings dialog! hwnd={w.NativeWindowHandle} title='{name}'", flush=True)
                break

if settings_dlg:
    print("\nTraversing Settings tabs...", flush=True)
    list_ctrl = settings_dlg.ListControl()
    if list_ctrl.Exists(2):
        tabs = list_ctrl.GetChildren()
        print(f"Found {len(tabs)} tabs in Settings dialog:")
        for t in tabs:
            print(f"  Tab: '{t.Name}'")
            tr = t.BoundingRectangle
            if tr:
                tcx = int((tr.left + tr.right) / 2)
                tcy = int((tr.top + tr.bottom) / 2)
                run_in_interactive_thread(worker_click, tcx, tcy, 0.2)
    
    # Close via Cancel
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
            run_in_interactive_thread(worker_click, ccx, ccy)
            print("Closed Settings dialog via Cancel physical click!", flush=True)
    else:
        run_in_interactive_thread(worker_send_keys, win32con.VK_ESCAPE)
        print("Closed Settings dialog via Escape key!", flush=True)
    time.sleep(1.0)

# Test Menu navigation
print("\nTesting Menu Navigation via worker...", flush=True)
run_in_interactive_thread(worker_set_foreground, main_hwnd)
time.sleep(0.2)
run_in_interactive_thread(worker_alt_key, 'F')
time.sleep(0.5)

fc = auto.GetFocusedControl()
print(f"Focused after Alt+F: Name='{fc.Name if fc else None}' Type='{fc.ControlTypeName if fc else None}'", flush=True)

for i in range(5):
    run_in_interactive_thread(worker_send_keys, win32con.VK_DOWN)
    time.sleep(0.15)
    fc = auto.GetFocusedControl()
    print(f"  Down #{i+1}: Name='{fc.Name if fc else None}' Type='{fc.ControlTypeName if fc else None}'", flush=True)

run_in_interactive_thread(worker_send_keys, win32con.VK_ESCAPE)
time.sleep(0.2)
run_in_interactive_thread(worker_send_keys, win32con.VK_ESCAPE)

print("\n=== COMPLETE SUCCESS ===", flush=True)
