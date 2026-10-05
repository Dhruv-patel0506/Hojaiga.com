"""Debug: Test keyboard navigation in OBS menus."""
import sys, time
import win32gui, win32api, win32con
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

try:
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)
except:
    win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
    win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.1)
    win32gui.SetForegroundWindow(hwnd)
time.sleep(0.5)

print("=== Opening File menu via Alt+F ===")
# Send Alt+F
win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
time.sleep(0.05)
vk_f = win32api.VkKeyScan('f') & 0xFF
win32api.keybd_event(vk_f, 0, 0, 0)
time.sleep(0.03)
win32api.keybd_event(vk_f, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.03)
win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(1.0)

print("=== Reading focused control BEFORE Down ===")
try:
    fc = auto.GetFocusedControl()
    if fc:
        print(f"  Focused: Type={fc.ControlTypeName} Name='{fc.Name}'")
        try:
            r = fc.BoundingRectangle
            if r:
                print(f"  BoundingRect: ({r.left},{r.top},{r.right},{r.bottom})")
        except Exception as e:
            print(f"  BoundingRect error: {e}")
    else:
        print("  No focused control")
except Exception as e:
    print(f"  Error: {e}")

for i in range(10):
    print(f"\n=== Pressing Down arrow #{i+1} ===")
    win32api.keybd_event(win32con.VK_DOWN, 0, 0, 0)
    time.sleep(0.03)
    win32api.keybd_event(win32con.VK_DOWN, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.3)

    try:
        fc = auto.GetFocusedControl()
        if fc:
            print(f"  Focused: Type={fc.ControlTypeName} Name='{fc.Name}'")
            try:
                r = fc.BoundingRectangle
                if r:
                    print(f"  BoundingRect: ({r.left},{r.top},{r.right},{r.bottom})")
            except Exception as e:
                print(f"  BoundingRect error: {e}")
        else:
            print("  No focused control")
    except Exception as e:
        print(f"  Error: {e}")

print("\n=== Pressing Escape ===")
win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.03)
win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.3)
print("Done")
