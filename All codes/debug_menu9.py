"""Debug: Targeted screenshot of menu dropdown area."""
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

# Find File menu
main_win = auto.ControlFromHandle(hwnd)
file_rect = None
for ctrl, depth in auto.WalkControl(main_win, includeTop=False, maxDepth=3):
    if ctrl.Name == 'File' and ctrl.ControlTypeName == 'MenuItemControl':
        r = ctrl.BoundingRectangle
        if r:
            file_rect = (r.left, r.top, r.right, r.bottom)
            print(f"File menu at: {file_rect}")
            break

if not file_rect:
    print("File not found"); sys.exit(1)

# Click File
cx = (file_rect[0] + file_rect[2]) // 2
cy = (file_rect[1] + file_rect[3]) // 2
win32api.SetCursorPos((cx, cy))
time.sleep(0.12)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, cx, cy, 0, 0)
time.sleep(0.04)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, cx, cy, 0, 0)
time.sleep(1.0)

# Screenshot the area right below the menu bar, starting from File menu x position
# Qt dropdowns typically appear directly below the menu header
menu_left = file_rect[0]
menu_top = file_rect[3]  # Below the menu bar
menu_right = menu_left + 250  # Width of dropdown
menu_bottom = menu_top + 400  # Height of dropdown

print(f"Screenshot area: ({menu_left},{menu_top}) to ({menu_right},{menu_bottom})")
crop = ImageGrab.grab(bbox=(menu_left, menu_top, menu_right, menu_bottom))
crop.save(r"D:\new_automation\All codes\menu_crop.png")

# OCR
text = pytesseract.image_to_string(crop)
print(f"\n=== OCR ===")
print(text)

data = pytesseract.image_to_data(crop, output_type=pytesseract.Output.DICT)
print(f"\n=== Words with positions ===")
for i, word in enumerate(data['text']):
    if word.strip() and int(data['conf'][i]) > 30:
        x = data['left'][i] + menu_left
        y = data['top'][i] + menu_top
        print(f"  '{word}' at screen ({x},{y})")

# Also try with different config
text2 = pytesseract.image_to_string(crop, config='--psm 6')
print(f"\n=== OCR (psm 6) ===")
print(text2)

win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.03)
win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.3)
print("\nDone")
