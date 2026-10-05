import ctypes
import win32gui
import win32process
import uiautomation as auto

user32 = ctypes.windll.user32
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

print("Listing all OBS processes and windows:")
import psutil
obs_pids = []
for p in psutil.process_iter(['pid', 'name']):
    if 'obs' in (p.info['name'] or '').lower():
        obs_pids.append(p.info['pid'])
        print(f"Process: {p.info['name']} (PID: {p.info['pid']})")

def enum(hwnd, _):
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    if pid in obs_pids:
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
        vis = win32gui.IsWindowVisible(hwnd)
        print(f"HWND: {hwnd} | vis: {vis} | title: '{title}' | class: '{cls}'")
    return True

win32gui.EnumWindows(enum, None)

print("\nListing via uiautomation RootControl:")
for win in auto.GetRootControl().GetChildren():
    if win.ProcessId in obs_pids:
        print(f"UIA win: hwnd={win.NativeWindowHandle} name='{win.Name}' class='{win.ClassName}'")
