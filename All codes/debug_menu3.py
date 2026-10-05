"""Debug: Compare UIA tree BEFORE and AFTER clicking a menu header physically."""
import sys, time, hashlib, json
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

def collect_all(ctrl, depth=0, max_d=15):
    items = []
    def _walk(c, d):
        if d > max_d: return
        try:
            name = c.Name or ''
            ctype = c.ControlTypeName or ''
            rect = c.BoundingRectangle
            aid = c.AutomationId or ''
            items.append({
                'name': name, 'type': ctype, 'aid': aid,
                'rect': (rect.left, rect.top, rect.right, rect.bottom) if rect else None,
                'hash': hashlib.md5(f"{ctype}|{name}|{aid}".encode()).hexdigest()[:12]
            })
            for ch in c.GetChildren():
                _walk(ch, d+1)
        except:
            pass
    _walk(ctrl, 0)
    return items

hwnd = find_obs()
if not hwnd:
    print('OBS not found'); sys.exit(1)

bring_front(hwnd)
main_win = auto.ControlFromHandle(hwnd)
pid = main_win.ProcessId

# Step 1: Collect BEFORE
before = collect_all(main_win)
before_hashes = {i['hash'] for i in before}
print(f"BEFORE: {len(before)} elements")

# Step 2: Find File menu header and physical click it
file_rect = None
for item in before:
    if item['name'] == 'File' and item['type'] == 'MenuItemControl':
        file_rect = item['rect']
        break

if not file_rect:
    print("File menu not found"); sys.exit(1)

cx = (file_rect[0] + file_rect[2]) // 2
cy = (file_rect[1] + file_rect[3]) // 2
print(f"Physical clicking File at ({cx}, {cy})")

win32api.SetCursorPos((cx, cy))
time.sleep(0.12)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, cx, cy, 0, 0)
time.sleep(0.04)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, cx, cy, 0, 0)
time.sleep(0.8)

# Step 3: Collect AFTER
after = collect_all(main_win)
after_hashes = {i['hash'] for i in after}
print(f"AFTER: {len(after)} elements")

# Step 4: Show NEW elements (appeared after menu click)
new_hashes = after_hashes - before_hashes
print(f"\nNEW elements after clicking File ({len(new_hashes)}):")
for item in after:
    if item['hash'] in new_hashes:
        r = item['rect']
        rect_str = f"({r[0]},{r[1]},{r[2]},{r[3]})" if r else "None"
        print(f"  Type={item['type']} Name='{item['name']}' Rect={rect_str}")

# Step 5: Check desktop root for floating windows
print(f"\nDesktop root children (pid={pid}):")
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
                except: r = "Err"
                print(f"    {ct}: '{cn}' Rect={r}")
    except:
        pass

auto.SendKey(auto.Keys.VK_ESCAPE)
time.sleep(0.3)
