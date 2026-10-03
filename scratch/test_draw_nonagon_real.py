import sys
sys.path.append("All codes")
import time
import ctypes
import win32gui
import win32con
from PIL import ImageGrab
import numpy as np

u32 = ctypes.windll.user32
hdesk = u32.OpenDesktopW("default", 0, False, 0x01FF)
if hdesk:
    u32.SetThreadDesktop(hdesk)

paint_hwnd = 720934
u32.ShowWindowAsync(paint_hwnd, win32con.SW_RESTORE)
u32.SetForegroundWindow(paint_hwnd)
time.sleep(0.5)

import uiautomation as auto
root_ctrl = auto.ControlFromHandle(paint_hwnd)

# 1. Click Pencil tool
pencil = root_ctrl.ButtonControl(AutomationId="PencilTool")
if pencil.Exists(1):
    ip = pencil.GetInvokePattern()
    if ip:
        ip.Invoke()
    else:
        pencil.Click()
    print("Successfully selected Pencil tool via UIA!")
time.sleep(0.3)

# 2. Find canvas element
canvas_ctrl = root_ctrl.GroupControl(AutomationId="image")
if canvas_ctrl.Exists(1):
    rect = canvas_ctrl.BoundingRectangle
    cx = (rect.left + rect.right) // 2
    cy = (rect.top + rect.bottom) // 2
    print(f"Canvas detected: {rect}, Center: ({cx}, {cy})")
else:
    cx, cy = 959, 592
    print(f"Using known canvas center: ({cx}, {cy})")

# 3. Take before screenshot of canvas center
before_im = ImageGrab.grab(bbox=(cx-150, cy-150, cx+150, cy+150))
before_im.save("scratch/canvas_before_nonagon.png")

# 4. Draw Nonagon using VisualCursor with physical=True
from core_organs.visual_cursor import get_cursor
vc = get_cursor()
vc.show()
time.sleep(0.5)

print(f"Drawing nonagon at ({cx}, {cy}) with width=220, height=220...")
vc.draw_shape("nonagon", cx, cy, width=220, height=220, steps=54, label="Nonagon", physical=True, hwnd=paint_hwnd)
time.sleep(0.5)

# 5. Take after screenshot
after_im = ImageGrab.grab(bbox=(cx-150, cy-150, cx+150, cy+150))
after_im.save("scratch/canvas_after_nonagon.png")

diff = np.sum(np.abs(np.array(before_im, dtype=int) - np.array(after_im, dtype=int)))
print(f"Pixel difference after drawing nonagon: {diff}")
if diff > 1000:
    print("SUCCESS: Nonagon physically visible on Paint canvas!")
else:
    print("FAILED: No marks on canvas.")

vc.hide()
