"""Debug: Test keyboard navigation inside OBS menus."""
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

def bring_front(hwnd):
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except:
        pass
    time.sleep(0.3)

def dump_tree(ctrl, depth=0, max_d=8):
    if depth > max_d:
        return
    try:
        name = ctrl.Name or ''
        ctype = ctrl.ControlTypeName or ''
        rect = ctrl.BoundingRectangle
        r = f"({rect.left},{rect.top},{rect.right},{rect.bottom})" if rect else "None"
        if name or 'menu' in ctype.lower():
            print(f"{'  '*depth}{ctype}: '{name}' {r}")
        for ch in ctrl.GetChildren():
            dump_tree(ch, depth+1, max_d)
    except:
        pass

hwnd = find_obs()
if not hwnd:
    print('OBS not found'); sys.exit(1)

bring_front(hwnd)
main_win = auto.ControlFromHandle(hwnd)
pid = main_win.ProcessId
print(f"OBS pid={pid}")

# === Test 1: Open File menu via keyboard, navigate with arrows ===
print("\n=== Opening File menu via Alt+F ===")
auto.SendKeys("%f")
time.sleep(1.0)

print("Desktop root children:")
for c in auto.GetRootControl().GetChildren():
    try:
        h = c.NativeWindowHandle
        name = c.Name or ''
        ctype = c.ControlTypeName or ''
        p = c.ProcessId
        vis = c.IsOffscreen
        if p == pid and h != hwnd:
            print(f"  HWND={h} Type={ctype} Name='{name}' Offscreen={vis}")
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

# Press Down arrow to move into dropdown
print("\nPressing Down arrow...")
auto.SendKey(auto.Keys.VK_DOWN)
time.sleep(0.5)

print("Desktop root after Down arrow:")
for c in auto.GetRootControl().GetChildren():
    try:
        h = c.NativeWindowHandle
        name = c.Name or ''
        ctype = c.ControlTypeName or ''
        p = c.ProcessId
        vis = c.IsOffscreen
        if p == pid and h != hwnd:
            print(f"  HWND={h} Type={ctype} Name='{name}' Offscreen={vis}")
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

# Press Down a few more times
for i in range(3):
    auto.SendKey(auto.Keys.VK_DOWN)
    time.sleep(0.3)

print("\nAfter 3 more Down arrows:")
for c in auto.GetRootControl().GetChildren():
    try:
        h = c.NativeWindowHandle
        name = c.Name or ''
        ctype = c.ControlTypeName or ''
        p = c.ProcessId
        vis = c.IsOffscreen
        if p == pid and h != hwnd:
            print(f"  HWND={h} Type={ctype} Name='{name}' Offscreen={vis}")
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

auto.SendKey(auto.Keys.VK_ESCAPE)
time.sleep(0.3)

# === Test 2: Check win32 accessibility ===
print("\n=== Checking MSAA (Win32 Accessibility) ===")
import ctypes
from ctypes import wintypes

oleacc = ctypes.windll.oleacc
user32 = ctypes.windll.user32

try:
    import comtypes
    from comtypes import GUID
    IID_IAccessible = GUID('{618736E0-3C3D-11CF-810C-00AA00389B71}')

    pacc = ctypes.c_void_p()
    hr = oleacc.AccessibleObjectFromWindow(hwnd, 0xFFFFFFFC, ctypes.byref(IID_IAccessible), ctypes.byref(pacc))
    if hr == 0 and pacc:
        print(f"MSAA accessible object found: {pacc}")
    else:
        print(f"MSAA hr={hr}")
except Exception as e:
    print(f"MSAA error: {e}")

# === Test 3: Use win32api GetMenu ===
print("\n=== Checking Win32 Menu handles ===")
hmenu = user32.GetMenu(hwnd)
print(f"GetMenu(hwnd) = {hmenu}")

if hmenu:
    count = user32.GetMenuItemCount(hmenu)
    print(f"Menu item count: {count}")
    for i in range(count):
        text_len = user32.GetMenuStringW(hmenu, i, None, 0, 0x0400)  # MF_BYPOSITION
        buf = ctypes.create_unicode_buffer(text_len + 1)
        user32.GetMenuStringW(hmenu, i, buf, text_len + 1, 0x0400)
        sub = user32.GetSubMenu(hmenu, i)
        sub_count = user32.GetMenuItemCount(sub) if sub else -1
        print(f"  [{i}] '{buf.value}' submenu_items={sub_count}")

        if sub and sub_count > 0:
            for j in range(sub_count):
                sub_text_len = user32.GetMenuStringW(sub, j, None, 0, 0x0400)
                sub_buf = ctypes.create_unicode_buffer(sub_text_len + 1)
                user32.GetMenuStringW(sub, j, sub_buf, sub_text_len + 1, 0x0400)
                print(f"    [{j}] '{sub_buf.value}'")

print("\nDone.")
