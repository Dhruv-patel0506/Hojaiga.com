import time
import os
import ctypes
import uiautomation as auto

user32 = ctypes.windll.user32
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

obs_exe = r"D:\obs-studio\bin\64bit\obs64.exe"
cwd = os.path.dirname(obs_exe)

print(f"Launching {obs_exe} via ShellExecuteW...")
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
                        print(f"[{second}s] Clicked Run in Safe Mode via InvokePattern!")
                        time.sleep(1)
                        break
            elif "profile:" in wname.lower() or ("obs" in wname.lower() and "crash" not in wname.lower()):
                main_hwnd = win.NativeWindowHandle
                main_win = win
                print(f"[{second}s] FOUND MAIN OBS WINDOW! hwnd={main_hwnd} title='{wname}'")
                break
        except Exception:
            continue
    if main_hwnd:
        break

print(f"Result main_hwnd: {main_hwnd}")
if not main_hwnd:
    sys.exit(1)

print("\nWaiting 4s for OBS to settle...")
time.sleep(4)

# Bring to foreground
user32.ShowWindow(main_hwnd, 9)
time.sleep(0.1)
user32.SetForegroundWindow(main_hwnd)
time.sleep(0.5)

fg = user32.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(512)
user32.GetWindowTextW(fg, buf, 512)
print(f"Foreground: hwnd={fg} title='{buf.value}'")

# Look for Settings button
settings_btn = main_win.ButtonControl(Name="Settings")
print(f"Settings btn exists: {settings_btn.Exists(2)}")

r = settings_btn.BoundingRectangle
cx = int((r.left + r.right) / 2)
cy = int((r.top + r.bottom) / 2)
print(f"Settings coords: ({cx}, {cy}) rect={r}")

# Click settings
print(f"Clicking Settings at ({cx}, {cy})...")
user32.SetCursorPos(cx, cy)
time.sleep(0.15)
user32.mouse_event(0x0002, 0, 0, 0, 0) # LEFTDOWN
time.sleep(0.10)
user32.mouse_event(0x0004, 0, 0, 0, 0) # LEFTUP
time.sleep(2.0)

# Check if Settings opened
dlg = None
for w in auto.GetRootControl().GetChildren():
    try:
        wname = (w.Name or "").strip()
        if "settings" in wname.lower() and "obs" not in wname.lower():
            dlg = w
            print(f"SUCCESS: Found Settings dialog via Click! hwnd={w.NativeWindowHandle} title='{wname}'")
            break
    except Exception:
        pass

if not dlg:
    print("Click did not open dialog, trying InvokePattern...")
    try:
        pat = settings_btn.GetInvokePattern()
        if pat:
            pat.Invoke()
            print("Called pat.Invoke() on Settings button.")
            time.sleep(2.0)
            for w in auto.GetRootControl().GetChildren():
                try:
                    wname = (w.Name or "").strip()
                    if "settings" in wname.lower() and "obs" not in wname.lower():
                        dlg = w
                        print(f"SUCCESS via Invoke: Found Settings dialog! hwnd={w.NativeWindowHandle} title='{wname}'")
                        break
                except Exception:
                    pass
    except Exception as e:
        print("Invoke error:", e)

if dlg:
    print(f"\nDiscovered Settings dialog! Listing its children:")
    for c in dlg.GetChildren():
        print(f"  Child: Name='{c.Name}' Type={c.ControlTypeName} Class={c.ClassName}")
    
    # Check ListControl
    list_ctrl = dlg.ListControl()
    if list_ctrl.Exists(2):
        tabs = list_ctrl.GetChildren()
        print(f"\nSettings Tabs ({len(tabs)}):")
        for t in tabs:
            print(f"  - Tab: '{t.Name}'")
            tr = t.BoundingRectangle
            if tr:
                tcx = int((tr.left + tr.right) / 2)
                tcy = int((tr.top + tr.bottom) / 2)
                user32.SetCursorPos(tcx, tcy)
                time.sleep(0.1)
                user32.mouse_event(0x0002, 0, 0, 0, 0)
                time.sleep(0.06)
                user32.mouse_event(0x0004, 0, 0, 0, 0)
                time.sleep(0.25)
    
    # Close safely
    cancel_btn = dlg.ButtonControl(Name="Cancel")
    if cancel_btn.Exists(1):
        pat = cancel_btn.GetInvokePattern()
        if pat:
            pat.Invoke()
            print("Closed Settings dialog via Cancel InvokePattern!")
        else:
            cancel_btn.Click()
            print("Closed Settings dialog via Click!")
    time.sleep(1.0)

# Test Alt+F menu
print("\nTesting Alt+F menu:")
user32.SetForegroundWindow(main_hwnd)
time.sleep(0.3)
user32.keybd_event(0x12, 0, 0, 0) # VK_MENU
time.sleep(0.06)
user32.keybd_event(ord('F'), 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(ord('F'), 0, 2, 0) # KEYUP
time.sleep(0.04)
user32.keybd_event(0x12, 0, 2, 0)
time.sleep(0.5)

fc = auto.GetFocusedControl()
print(f"Focused after Alt+F: Name='{fc.Name if fc else None}' Type='{fc.ControlTypeName if fc else None}'")

for i in range(5):
    user32.keybd_event(0x28, 0, 0, 0) # VK_DOWN
    time.sleep(0.04)
    user32.keybd_event(0x28, 0, 2, 0)
    time.sleep(0.15)
    fc = auto.GetFocusedControl()
    print(f"  Down #{i+1}: Name='{fc.Name if fc else None}' Type='{fc.ControlTypeName if fc else None}'")

user32.keybd_event(0x1B, 0, 0, 0) # VK_ESCAPE
time.sleep(0.04)
user32.keybd_event(0x1B, 0, 2, 0)
time.sleep(0.2)
user32.keybd_event(0x1B, 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(0x1B, 0, 2, 0)

print("\nDone testing!")
