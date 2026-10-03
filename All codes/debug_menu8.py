"""Debug: Full screenshot to find where Qt menu appears."""
import sys, time
import win32gui, win32api, win32con
from PIL import ImageGrab
import pytesseract
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

try:
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)
except:
    pass
time.sleep(0.5)

# Take BEFORE screenshot
before = ImageGrab.grab()
before.save(r"D:\new_automation\All codes\before_menu.png")

# Find File menu and click it
main_win = auto.ControlFromHandle(hwnd)
file_rect = None
for ctrl, depth in auto.WalkControl(main_win, includeTop=False, maxDepth=3):
    if ctrl.Name == 'File' and ctrl.ControlTypeName == 'MenuItemControl':
        r = ctrl.BoundingRectangle
        if r:
            file_rect = (r.left, r.top, r.right, r.bottom)
            break

if not file_rect:
    print("File menu not found"); sys.exit(1)

cx = (file_rect[0] + file_rect[2]) // 2
cy = (file_rect[1] + file_rect[3]) // 2
print(f"Clicking File at ({cx}, {cy})")
win32api.SetCursorPos((cx, cy))
time.sleep(0.12)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, cx, cy, 0, 0)
time.sleep(0.04)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, cx, cy, 0, 0)
time.sleep(1.0)

# Take AFTER screenshot (full screen)
after = ImageGrab.grab()
after.save(r"D:\new_automation\All codes\after_menu.png")
print("Full screenshot saved after clicking File")

# Find differences between before and after
before_data = list(before.getdata())
after_data = list(after.getdata())
diff_pixels = 0
diff_regions = []
w, h = before.size
for i, (b, a) in enumerate(zip(before_data, after_data)):
    if abs(b[0]-a[0]) > 20 or abs(b[1]-a[1]) > 20 or abs(b[2]-a[2]) > 20:
        diff_pixels += 1
        x = i % w
        y = i // w
        if diff_regions:
            last = diff_regions[-1]
            if abs(y - last[1]) < 5:
                continue
        diff_regions.append((x, y))

print(f"Changed pixels: {diff_pixels}")
print(f"First 20 diff regions (x, y): {diff_regions[:20]}")

# Crop the diff region if significant
if diff_pixels > 100:
    # Find bounding box of changes
    min_x = min_y = 99999
    max_x = max_y = 0
    for i, (b, a) in enumerate(zip(before_data, after_data)):
        if abs(b[0]-a[0]) > 20 or abs(b[1]-a[1]) > 20 or abs(b[2]-a[2]) > 20:
            x = i % w
            y = i // w
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    
    print(f"Diff bounding box: ({min_x},{min_y}) to ({max_x},{max_y})")
    crop = after.crop((max(0,min_x-10), max(0,min_y-10), min(w,max_x+10), min(h,max_y+10)))
    crop.save(r"D:\new_automation\All codes\menu_diff.png")
    print("Cropped diff saved")
    
    # OCR the diff region
    text = pytesseract.image_to_string(crop)
    print(f"\n=== OCR of menu region ===")
    print(text)

# Escape
win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.03)
win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.3)
print("\nDone")
