import ctypes
import os
import sys

# 1. OpenInputDesktop + SetThreadDesktop MUST BE THE VERY FIRST THING!
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    res = user32.SetThreadDesktop(hdesk)
    print(f"SetThreadDesktop: {res} (err: {kernel32.GetLastError()})")
else:
    print(f"OpenInputDesktop failed: {kernel32.GetLastError()}")

# 2. NOW import other modules
import time
import uiautomation as auto

obs_exe = r"D:\obs-studio\bin\64bit\obs64.exe"
cwd = os.path.dirname(obs_exe)

print(f"Launching OBS via ShellExecuteW...")
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
                        print(f"[{second}s] Auto-dismissed Safe Mode!")
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

# Check Settings button
settings_btn = main_win.ButtonControl(Name="Settings")
print(f"Settings btn exists: {settings_btn.Exists(2)}")

r = settings_btn.BoundingRectangle
cx = int((r.left + r.right) / 2)
cy = int((r.top + r.bottom) / 2)
print(f"Settings target coords: ({cx}, {cy}) rect={r}")

# Check cursor movement
pos_res = user32.SetCursorPos(cx, cy)
print(f"SetCursorPos({cx}, {cy}) result: {pos_res} (err: {kernel32.GetLastError()})")

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
pt = POINT()
user32.GetCursorPos(ctypes.byref(pt))
print(f"Actual cursor position before click: ({pt.x}, {pt.y})")

# Send genuine physical click
print("Sending physical left click via mouse_event...")
user32.mouse_event(0x0002, 0, 0, 0, 0) # LEFTDOWN
time.sleep(0.12)
user32.mouse_event(0x0004, 0, 0, 0, 0) # LEFTUP
time.sleep(2.0)

# Check if Settings opened
dlg = None
for w in auto.GetRootControl().GetChildren():
    try:
        wname = (w.Name or "").strip()
        if "settings" in wname.lower() and "obs" not in wname.lower():
            dlg = w
            print(f"\nSUCCESS: FOUND SETTINGS DIALOG! hwnd={w.NativeWindowHandle} title='{wname}'")
            break
    except Exception:
        pass

if not dlg:
    print("\nClick did not open dialog, trying auto.Click(cx, cy)...")
    try:
        auto.Click(cx, cy)
        time.sleep(2.0)
        for w in auto.GetRootControl().GetChildren():
            wname = (w.Name or "").strip()
            if "settings" in wname.lower() and "obs" not in wname.lower():
                dlg = w
                print(f"SUCCESS via auto.Click! hwnd={w.NativeWindowHandle} title='{wname}'")
                break
    except Exception as e:
        print("auto.Click error:", e)

if dlg:
    print("\n=== ENUMERATING SETTINGS TABS ===")
    list_ctrl = dlg.ListControl()
    if list_ctrl.Exists(2):
        tabs = list_ctrl.GetChildren()
        print(f"Discovered {len(tabs)} tabs in Settings:")
        for t in tabs:
            print(f"  Tab: '{t.Name}'")
            tr = t.BoundingRectangle
            if tr:
                tcx = int((tr.left + tr.right) / 2)
                tcy = int((tr.top + tr.bottom) / 2)
                user32.SetCursorPos(tcx, tcy)
                time.sleep(0.1)
                user32.mouse_event(0x0002, 0, 0, 0, 0)
                time.sleep(0.06)
                user32.mouse_event(0x0004, 0, 0, 0, 0)
                time.sleep(0.2)
    
    # Close safely
    cancel_btn = dlg.ButtonControl(Name="Cancel")
    if cancel_btn.Exists(1):
        pat = cancel_btn.GetInvokePattern()
        if pat:
            pat.Invoke()
            print("Closed Settings via Cancel InvokePattern!")
        else:
            cancel_btn.Click()
            print("Closed Settings via Click!")
    time.sleep(1.0)

print("\nDone testing!")
