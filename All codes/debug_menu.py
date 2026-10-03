"""Debug: Check what UIA elements appear when OBS menu is opened."""
import sys, time, json
import win32gui, win32api, win32con, win32process
import uiautomation as auto

sys.path.insert(0, r"D:\new_automation\All codes")

def find_obs():
    found = []
    def cb(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            if 'OBS' in t and 'Profile:' in t:
                extra.append(hwnd)
        return True
    win32gui.EnumWindows(cb, found)
    return found[0] if found else 0

hwnd = find_obs()
if not hwnd:
    print('OBS not found'); sys.exit(1)

# Bring to front
if win32gui.IsIconic(hwnd):
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
try:
    win32gui.SetForegroundWindow(hwnd)
except:
    pass
time.sleep(0.5)

main_win = auto.ControlFromHandle(hwnd)
pid = main_win.ProcessId
print(f"OBS hwnd={hwnd} pid={pid}")

# Open File menu via keyboard shortcut
auto.SendKeys("%f")
time.sleep(1.0)

print("\n=== Desktop root children (floating windows) ===")
for c in auto.GetRootControl().GetChildren():
    try:
        h = c.NativeWindowHandle
        name = c.Name or ''
        ctype = c.ControlTypeName or ''
        p = c.ProcessId
        vis = c.IsOffscreen
        if p == pid and not vis and h != hwnd:
            print(f"  HWND={h} Type={ctype} Name='{name}'")
            for ch in c.GetChildren():
                cn = ch.Name or ''
                ct = ch.ControlTypeName or ''
                try:
                    rect = ch.BoundingRectangle
                    r = f"({rect.left},{rect.top},{rect.right},{rect.bottom})" if rect else "None"
                except:
                    r = "Error"
                print(f"    Child: Type={ct} Name='{cn}' Rect={r}")
    except:
        pass

print("\n=== All menu items in main window tree ===")
def walk(ctrl, depth=0):
    if depth > 10: return
    try:
        name = ctrl.Name or ''
        ctype = ctrl.ControlTypeName or ''
        if 'menu' in ctype.lower() or 'menuitem' in ctype.lower():
            try:
                rect = ctrl.BoundingRectangle
                r = f"({rect.left},{rect.top},{rect.right},{rect.bottom})" if rect else "None"
            except:
                r = "Error"
            print(f"  {'  '*depth}Type={ctype} Name='{name}' Rect={r}")
        for ch in ctrl.GetChildren():
            walk(ch, depth+1)
    except:
        pass

walk(main_win)

auto.SendKey(auto.Keys.VK_ESCAPE)
time.sleep(0.3)
