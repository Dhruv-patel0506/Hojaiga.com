"""Debug: Quick test of keyboard nav in OBS File menu."""
import sys, time
import win32gui, win32api, win32con
import uiautomation as auto

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

if win32gui.IsIconic(hwnd):
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
try: win32gui.SetForegroundWindow(hwnd)
except: pass
time.sleep(0.5)

# Open File menu
print("Opening File menu...")
auto.SendKeys("%f")
time.sleep(1.0)

# Read focused element
print("Reading focused control...")
try:
    fc = auto.GetFocusedControl()
    if fc:
        print(f"  Focused: Type={fc.ControlTypeName} Name='{fc.Name}'")
    else:
        print("  No focused control")
except Exception as e:
    print(f"  Error: {e}")

# Press Down once
auto.SendKey(auto.Keys.VK_DOWN)
time.sleep(0.5)

try:
    fc = auto.GetFocusedControl()
    if fc:
        print(f"  After Down: Type={fc.ControlTypeName} Name='{fc.Name}'")
except Exception as e:
    print(f"  Error: {e}")

auto.SendKey(auto.Keys.VK_ESCAPE)
time.sleep(0.3)
print("Done")
