"""Debug: Test physical click + screenshot OCR for OBS menus."""
import sys, time
import win32gui, win32api, win32con
from PIL import ImageGrab
import pytesseract
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
    pass
time.sleep(0.5)

# Find File menu header coordinates
main_win = auto.ControlFromHandle(hwnd)
file_rect = None
for ctrl, depth in auto.WalkControl(main_win, includeTop=False, maxDepth=3):
    if ctrl.Name == 'File' and ctrl.ControlTypeName == 'MenuItemControl':
        r = ctrl.BoundingRectangle
        if r:
            file_rect = (r.left, r.top, r.right, r.bottom)
            print(f"File menu header at: {file_rect}")
            break

if not file_rect:
    print("File menu not found"); sys.exit(1)

# Physical click on File menu
cx = (file_rect[0] + file_rect[2]) // 2
cy = (file_rect[1] + file_rect[3]) // 2
print(f"Clicking File at ({cx}, {cy})")
win32api.SetCursorPos((cx, cy))
time.sleep(0.12)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, cx, cy, 0, 0)
time.sleep(0.04)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, cx, cy, 0, 0)
time.sleep(0.8)

# Take screenshot of the menu area
# Menu typically appears below the menu bar, left-aligned
menu_x = file_rect[0]
menu_y = file_rect[3]  # below the menu bar
menu_w = 300  # approximate width
menu_h = 400  # approximate height

print(f"Taking screenshot of menu area: ({menu_x}, {menu_y}, {menu_x+menu_w}, {menu_y+menu_h})")
screenshot = ImageGrab.grab(bbox=(menu_x, menu_y, menu_x+menu_w, menu_y+menu_h))
screenshot.save(r"D:\new_automation\All codes\menu_screenshot.png")
print(f"Screenshot saved")

# OCR the screenshot
text = pytesseract.image_to_string(screenshot)
print(f"\n=== OCR Result ===")
print(text)

# Also try to find text positions
data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
print(f"\n=== OCR Words Found ===")
for i, word in enumerate(data['text']):
    if word.strip():
        x = data['left'][i] + menu_x
        y = data['top'][i] + menu_y
        w = data['width'][i]
        h = data['height'][i]
        conf = data['conf'][i]
        print(f"  '{word}' at ({x},{y}) size ({w}x{h}) conf={conf}")

# Escape to close menu
win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.03)
win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.3)
print("\nDone")
