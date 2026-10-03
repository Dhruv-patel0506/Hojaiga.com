import ctypes
import time
import win32gui
import win32con
import uiautomation as auto

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

hwnd = 8325072
if not win32gui.IsWindow(hwnd):
    for w in auto.GetRootControl().GetChildren():
        wname = w.Name or ""
        if "obs" in wname.lower() and "crash" not in wname.lower():
            hwnd = w.NativeWindowHandle
            break

print(f"Using OBS HWND: {hwnd}")

# Bring to foreground
user32.ShowWindow(hwnd, win32con.SW_RESTORE)
time.sleep(0.1)
user32.SetForegroundWindow(hwnd)
time.sleep(0.5)

root = auto.ControlFromHandle(hwnd)
settings_btn = root.ButtonControl(Name="Settings")
print("Settings btn exists:", settings_btn.Exists(2))

r = settings_btn.BoundingRectangle
cx = int((r.left + r.right) / 2)
cy = int((r.top + r.bottom) / 2)
print(f"Settings at ({cx}, {cy})")

# Move cursor and click
user32.SetCursorPos(cx, cy)
time.sleep(0.15)
user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
time.sleep(0.10)
user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
time.sleep(2.0)

# Check for Settings dialog
settings_dlg = None
for w in auto.GetRootControl().GetChildren():
    name = (w.Name or "").strip()
    if "settings" in name.lower():
        settings_dlg = w
        print(f"SUCCESS: Found Settings dialog! hwnd={w.NativeWindowHandle} title='{name}'")
        break

if not settings_dlg:
    print("Click did not open dialog, trying InvokePattern...")
    try:
        pat = settings_btn.GetInvokePattern()
        if pat:
            pat.Invoke()
            print("Invoked Settings button.")
            time.sleep(2.0)
            for w in auto.GetRootControl().GetChildren():
                name = (w.Name or "").strip()
                if "settings" in name.lower():
                    settings_dlg = w
                    print(f"SUCCESS via Invoke: Found Settings dialog! hwnd={w.NativeWindowHandle} title='{name}'")
                    break
    except Exception as e:
        print("Invoke error:", e)

if settings_dlg:
    list_ctrl = settings_dlg.ListControl()
    if list_ctrl.Exists(2):
        tabs = list_ctrl.GetChildren()
        print(f"Found {len(tabs)} tabs in Settings:")
        for t in tabs:
            print(f"  Tab: '{t.Name}'")
            tr = t.BoundingRectangle
            tcx = int((tr.left + tr.right) / 2)
            tcy = int((tr.top + tr.bottom) / 2)
            user32.SetCursorPos(tcx, tcy)
            time.sleep(0.1)
            user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.06)
            user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.2)
    
    # Close via Cancel
    cancel_btn = settings_dlg.ButtonControl(Name="Cancel")
    if cancel_btn.Exists(1):
        pat = cancel_btn.GetInvokePattern()
        if pat:
            pat.Invoke()
            print("Closed Settings via Cancel InvokePattern!")
        else:
            cr = cancel_btn.BoundingRectangle
            ccx = int((cr.left + cr.right) / 2)
            ccy = int((cr.top + cr.bottom) / 2)
            user32.SetCursorPos(ccx, ccy)
            time.sleep(0.1)
            user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.06)
            user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            print("Closed Settings via Cancel Click!")

# Test Menu navigation
print("\nTesting Alt+F Menu:")
user32.SetForegroundWindow(hwnd)
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
print(f"Focused after Alt+F: Name='{fc.Name if fc else None}' Type='{fc.ControlTypeName if fc else None}'")

for i in range(5):
    user32.keybd_event(win32con.VK_DOWN, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(win32con.VK_DOWN, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.15)
    fc = auto.GetFocusedControl()
    print(f"  Down #{i+1}: Name='{fc.Name if fc else None}' Type='{fc.ControlTypeName if fc else None}'")

user32.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.2)
user32.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.04)
user32.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)

print("\nDone!")
