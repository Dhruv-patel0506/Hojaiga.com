"""Debug: Test keyboard navigation to enumerate dropdown items."""
import sys, time, ctypes
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

def bring_front(hwnd):
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try: win32gui.SetForegroundWindow(hwnd)
    except: pass
    time.sleep(0.3)

hwnd = find_obs()
if not hwnd:
    print('OBS not found'); sys.exit(1)

bring_front(hwnd)
main_win = auto.ControlFromHandle(hwnd)
pid = main_win.ProcessId

user32 = ctypes.windll.user32

# Open File menu via keyboard shortcut
print("=== Opening File menu via Alt+F ===")
auto.SendKeys("%f")
time.sleep(1.0)

# Now read the currently highlighted menu item using accessibility
# Each Down arrow moves selection; we can read the focused element
menu_items = []
for i in range(20):  # Max 20 items
    # Read focused element
    try:
        focused = auto.GetFocusedControl()
        if focused:
            name = focused.Name or ''
            ctype = focused.ControlTypeName or ''
            if name and name not in menu_items and ctype != 'MenuBarControl':
                menu_items.append(name)
                print(f"  [{i}] Focused: Type={ctype} Name='{name}'")
    except:
        pass

    # Press Down
    auto.SendKey(auto.Keys.VK_DOWN)
    time.sleep(0.3)

    # Check if we wrapped back to the top (menu closed or looped)
    try:
        focused = auto.GetFocusedControl()
        if focused and focused.Name in ('File', 'MenuBarControl'):
            print(f"  -> Wrapped back to '{focused.Name}', stopping.")
            break
    except:
        pass

auto.SendKey(auto.Keys.VK_ESCAPE)
time.sleep(0.3)

print(f"\nFile menu items discovered via keyboard: {menu_items}")
print(f"Count: {len(menu_items)}")

# === Now test Scene Collection ===
print("\n=== Opening Scene Collection menu ===")
bring_front(hwnd)
auto.SendKeys("%p")  # Actually Scene Collection doesn't have a standard shortcut
time.sleep(0.3)

# Find Scene Collection menu header and click it
for c in main_win.GetChildren():
    try:
        if c.Name == 'Scene Collection' and 'MenuItem' in c.ControlTypeName:
            rect = c.BoundingRectangle
            cx = (rect.left + rect.right) // 2
            cy = (rect.top + rect.bottom) // 2
            win32api.SetCursorPos((cx, cy))
            time.sleep(0.1)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, cx, cy, 0, 0)
            time.sleep(0.04)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, cx, cy, 0, 0)
            time.sleep(0.8)
            break
    except:
        pass

sc_items = []
for i in range(20):
    try:
        focused = auto.GetFocusedControl()
        if focused:
            name = focused.Name or ''
            ctype = focused.ControlTypeName or ''
            if name and name not in sc_items and ctype not in ('MenuBarControl', 'MenuItemControl'):
                sc_items.append(name)
                print(f"  [{i}] Focused: Type={ctype} Name='{name}'")
    except:
        pass

    auto.SendKey(auto.Keys.VK_DOWN)
    time.sleep(0.3)

    try:
        focused = auto.GetFocusedControl()
        if focused and focused.Name == 'Scene Collection':
            print(f"  -> Wrapped back, stopping.")
            break
    except:
        pass

auto.SendKey(auto.Keys.VK_ESCAPE)
time.sleep(0.3)

print(f"\nScene Collection items: {sc_items}")
print(f"Count: {len(sc_items)}")
