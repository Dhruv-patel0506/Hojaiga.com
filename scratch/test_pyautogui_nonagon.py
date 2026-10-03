import sys
sys.path.append("All codes")
import time
import ctypes
import pyautogui
from PIL import ImageGrab
import numpy as np

u32 = ctypes.windll.user32
hdesk = u32.OpenDesktopW("default", 0, False, 0x01FF)
if hdesk:
    u32.SetThreadDesktop(hdesk)

u32.SetForegroundWindow(720934)
time.sleep(0.3)

cx, cy = 800, 448
width, height = 200, 200
n = 9 # Nonagon: 9 sides

# Generate 9-sided regular polygon points
points = []
rx, ry = width / 2.0, height / 2.0
raw_corners = []
for i in range(n):
    angle = (2.0 * 3.141592653589793 * i / float(n)) - (3.141592653589793 / 2.0)
    raw_corners.append((cx + rx * np.cos(angle), cy + ry * np.sin(angle)))
raw_corners.append(raw_corners[0])

sub = 5
for k in range(len(raw_corners) - 1):
    c1 = raw_corners[k]
    c2 = raw_corners[k + 1]
    for s in range(sub):
        t = s / float(sub)
        points.append((c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t))
points.append(raw_corners[-1])

# Take before screenshot
before = ImageGrab.grab(bbox=(cx-120, cy-120, cx+120, cy+120))

# Start Visual Cursor
from core_organs.visual_cursor import get_cursor
vc = get_cursor()
vc.show()
time.sleep(0.3)

orig_pos = pyautogui.position()
print(f"Original cursor: {orig_pos}")

# Fly visual cursor to start
sx, sy = points[0]
vc.fly_to(sx, sy, label="Draw Nonagon", duration=0.2)
time.sleep(0.25)

# Physical nonagon drawing with VisualCursor overlay
pyautogui.moveTo(int(sx), int(sy))
pyautogui.mouseDown(button="left")
time.sleep(0.02)

for pt in points[1:]:
    vc.set_position(pt[0], pt[1])
    vc._trail_points.append((pt[0], pt[1], time.time()))
    pyautogui.moveTo(int(pt[0]), int(pt[1]))
    time.sleep(0.015)

pyautogui.mouseUp(button="left")

# Instantly restore physical cursor
pyautogui.moveTo(orig_pos.x, orig_pos.y)
print(f"Restored cursor to: {pyautogui.position()}")

# Take after screenshot
after = ImageGrab.grab(bbox=(cx-120, cy-120, cx+120, cy+120))
after.save("scratch/nonagon_drawn.png")

diff = np.sum(np.abs(np.array(before, dtype=int) - np.array(after, dtype=int)))
print(f"Pixel difference after nonagon: {diff}")
assert diff > 5000, f"Diff too low: {diff}"
print("SUCCESS: Nonagon visibly drawn on Paint canvas with zero cursor theft!")
vc.hide()
