"""Debug: Use mss for faster capture + try clicking a specific menu item."""
import sys, time
import win32gui, win32api, win32con
import mss
import mss.tools
from PIL import Image
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

# Click File menu
print("Clicking File menu...")
win32api.SetCursorPos((39, 48))
time.sleep(0.12)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 39, 48, 0, 0)
time.sleep(0.04)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 39, 48, 0, 0)
time.sleep(0.5)

# Capture with mss (much faster than PIL ImageGrab)
with mss.mss() as sct:
    # Capture full screen
    monitor = sct.monitors[1]  # Primary monitor
    screenshot = sct.grab(monitor)
    raw = mss.tools.to_png(screenshot.rgb, screenshot.size)
    img = Image.open(__import__('io').BytesIO(raw))
    img.save(r"D:\new_automation\All codes\mss_full.png")
    print("MSS full screenshot saved")
    
    # Crop to menu area (File is at x=18-61, menu opens below at y=64)
    # Let's capture a wider area
    crop_region = {"left": 0, "top": 28, "width": 600, "height": 500}
    crop = sct.grab(crop_region)
    crop_raw = mss.tools.to_png(crop.rgb, crop.size)
    crop_img = Image.open(__import__('io').BytesIO(crop_raw))
    crop_img.save(r"D:\new_automation\All codes\mss_crop.png")
    print("MSS crop saved")
    
    # OCR the crop
    text = pytesseract.image_to_string(crop_img)
    print(f"\n=== OCR of mss crop ===")
    print(repr(text))

# Check focused control
print("\n=== Focused control ===")
try:
    fc = auto.GetFocusedControl()
    if fc:
        print(f"  Type={fc.ControlTypeName} Name='{fc.Name}'")
except Exception as e:
    print(f"  Error: {e}")

# Try clicking in the menu area where "New..." would be
# File menu dropdown typically starts at same x as menu header, y below it
# Items are ~20px apart
print("\n=== Trying to click at estimated menu item positions ===")
for y_offset in [80, 100, 120, 140, 160, 180, 200]:
    x, y = 39, y_offset
    print(f"  Moving cursor to ({x}, {y})...")
    win32api.SetCursorPos((x, y))
    time.sleep(0.2)
    
    # Check what's under cursor
    try:
        ctrl = auto.ControlFromPoint(x, y)
        if ctrl:
            print(f"    Under cursor: Type={ctrl.ControlTypeName} Name='{ctrl.Name}'")
    except:
        pass

# Escape
win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.03)
win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.3)
print("\nDone")
