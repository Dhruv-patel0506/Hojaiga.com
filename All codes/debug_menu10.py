"""Debug: Full screenshot to locate Qt dropdown position."""
import sys, time
import win32gui, win32api, win32con
from PIL import ImageGrab
import pytesseract

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

# Click File menu at (39, 48)
print("Clicking File at (39, 48)...")
win32api.SetCursorPos((39, 48))
time.sleep(0.12)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 39, 48, 0, 0)
time.sleep(0.04)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 39, 48, 0, 0)
time.sleep(1.0)

# Full screen screenshot
full = ImageGrab.grab()
full.save(r"D:\new_automation\All codes\full_after_click.png")
print("Full screenshot saved")

# OCR full screen
text = pytesseract.image_to_string(full)
print(f"\n=== Full OCR ===")
print(text[:2000])

# Find all menu-like text
data = pytesseract.image_to_data(full, output_type=pytesseract.Output.DICT)
print(f"\n=== Menu-like words ===")
menu_words = ["File", "Edit", "View", "New", "Open", "Save", "Close", "Exit", 
              "Scene", "Profile", "Import", "Export", "Duplicate", "Rename",
              "Undo", "Redo", "Cut", "Copy", "Paste", "Settings", "Properties"]
for i, word in enumerate(data['text']):
    if word.strip() and any(mw.lower() in word.lower() for mw in menu_words):
        x = data['left'][i]
        y = data['top'][i]
        w = data['width'][i]
        h = data['height'][i]
        print(f"  '{word}' at ({x},{y}) size ({w}x{h})")

# Escape
win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
time.sleep(0.03)
win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
time.sleep(0.3)
print("\nDone")
