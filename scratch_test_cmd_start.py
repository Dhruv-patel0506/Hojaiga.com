import ctypes
import time
import os
import sys
import json
import win32gui
import win32con
import uiautomation as auto

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

result = {}
result["pid"] = os.getpid()
result["console_hwnd"] = kernel32.GetConsoleWindow()

fg_init = user32.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(512)
user32.GetWindowTextW(fg_init, buf, 512)
result["fg_init"] = {"hwnd": fg_init, "title": buf.value}
print(f"Initial FG: hwnd={fg_init} title='{buf.value}'")

obs_exe = r"D:\obs-studio\bin\64bit\obs64.exe"
cwd = os.path.dirname(obs_exe)

# Check if OBS is running or launch it
main_hwnd = None
for win in auto.GetRootControl().GetChildren():
    try:
        wname = win.Name or ""
        if "profile:" in wname.lower() or ("obs" in wname.lower() and "crash" not in wname.lower()):
            main_hwnd = win.NativeWindowHandle
            break
    except Exception:
        pass

if not main_hwnd:
    print("Launching OBS...")
    ctypes.windll.shell32.ShellExecuteW(0, "open", obs_exe, None, cwd, 1)
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
                            time.sleep(1)
                            break
                elif "profile:" in wname.lower() or ("obs" in wname.lower() and "crash" not in wname.lower()):
                    main_hwnd = win.NativeWindowHandle
                    break
            except Exception:
                continue
        if main_hwnd:
            break

result["obs_hwnd"] = main_hwnd
print(f"OBS HWND: {main_hwnd}")
if not main_hwnd:
    with open("scratch_test_cmd_result.json", "w") as f:
        json.dump(result, f, indent=2)
    sys.exit(1)

time.sleep(3)

# Test SetForegroundWindow
user32.ShowWindow(main_hwnd, win32con.SW_RESTORE)
time.sleep(0.1)

# Alt pulse to unlock foreground
user32.keybd_event(win32con.VK_MENU, 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.04)

set_fg_res = user32.SetForegroundWindow(main_hwnd)
result["set_fg_res"] = set_fg_res
time.sleep(0.5)

fg_after = user32.GetForegroundWindow()
user32.GetWindowTextW(fg_after, buf, 512)
result["fg_after"] = {"hwnd": fg_after, "title": buf.value}
print(f"SetForegroundWindow result: {set_fg_res} | FG now: hwnd={fg_after} title='{buf.value}'")

# Test Menu Alt+F
user32.keybd_event(win32con.VK_MENU, 0, 0, 0)
time.sleep(0.06)
user32.keybd_event(ord('F'), 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(ord('F'), 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.04)
user32.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.5)

fc = auto.GetFocusedControl()
result["menu_focused_init"] = fc.Name if fc else None
print(f"Focused after Alt+F: {result['menu_focused_init']}")

down_items = []
for i in range(5):
    user32.keybd_event(win32con.VK_DOWN, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(win32con.VK_DOWN, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.15)
    fc = auto.GetFocusedControl()
    item_name = fc.Name if fc else None
    down_items.append(item_name)
    print(f"  Down #{i+1}: {item_name}")
result["down_items"] = down_items

user32.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.2)
user32.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)

# Now test Settings Click
root = auto.ControlFromHandle(main_hwnd)
settings_btn = root.ButtonControl(Name="Settings")
if settings_btn.Exists(2):
    r = settings_btn.BoundingRectangle
    cx = int((r.left + r.right) / 2)
    cy = int((r.top + r.bottom) / 2)
    print(f"Clicking Settings at ({cx}, {cy})...")
    user32.SetCursorPos(cx, cy)
    time.sleep(0.12)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(2.0)
    
    settings_dlg = None
    for w in auto.GetRootControl().GetChildren():
        wname = (w.Name or "").strip()
        if "settings" in wname.lower():
            settings_dlg = w
            break
            
    if not settings_dlg:
        print("Click did not open Settings, trying Invoke...")
        pat = settings_btn.GetInvokePattern()
        if pat:
            pat.Invoke()
            time.sleep(2.0)
            for w in auto.GetRootControl().GetChildren():
                wname = (w.Name or "").strip()
                if "settings" in wname.lower():
                    settings_dlg = w
                    break

    result["settings_dlg_found"] = settings_dlg is not None
    if settings_dlg:
        print(f"SUCCESS: Found Settings dialog! hwnd={settings_dlg.NativeWindowHandle}")
        list_ctrl = settings_dlg.ListControl()
        if list_ctrl.Exists(2):
            tabs = [t.Name for t in list_ctrl.GetChildren()]
            result["tabs"] = tabs
            print(f"Tabs ({len(tabs)}): {tabs}")
            
        # Cancel
        cancel_btn = settings_dlg.ButtonControl(Name="Cancel")
        if cancel_btn.Exists(1):
            pat = cancel_btn.GetInvokePattern()
            if pat:
                pat.Invoke()
                print("Closed dialog via Cancel Invoke.")

with open("scratch_test_cmd_result.json", "w") as f:
    json.dump(result, f, indent=2)

print("Results written to scratch_test_cmd_result.json")
