import ctypes, time, win32gui, win32con
from ctypes import wintypes
from PIL import ImageGrab

u32 = ctypes.windll.user32
hdesk = u32.OpenDesktopW("default", 0, False, 0x01FF)
if hdesk:
    u32.SetThreadDesktop(hdesk)

hwnd = 720934
u32.ShowWindowAsync(hwnd, 9)
u32.SetForegroundWindow(hwnd)
time.sleep(0.5)

cx, cy = 958, 640

# Check color before
im_before = ImageGrab.grab(bbox=(cx-50, cy-50, cx+50, cy+50))
im_before.save("scratch/test_stroke_before.png")

# Method: Move cursor, mouse down, mouse move with MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, mouse up
print(f"Testing drag from ({cx-40}, {cy}) to ({cx+40}, {cy})...")
u32.SetCursorPos(cx - 40, cy)
time.sleep(0.05)
u32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
time.sleep(0.05)

for step in range(1, 40):
    cur_x = cx - 40 + step * 2
    u32.SetCursorPos(cur_x, cy)
    # Also send MOUSEEVENTF_MOVE
    u32.mouse_event(win32con.MOUSEEVENTF_MOVE, 2, 0, 0, 0)
    time.sleep(0.015)

time.sleep(0.05)
u32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
time.sleep(0.2)

im_after = ImageGrab.grab(bbox=(cx-50, cy-50, cx+50, cy+50))
im_after.save("scratch/test_stroke_after.png")

import numpy as np
diff = np.sum(np.abs(np.array(im_before, dtype=int) - np.array(im_after, dtype=int)))
print(f"Diff: {diff}")
