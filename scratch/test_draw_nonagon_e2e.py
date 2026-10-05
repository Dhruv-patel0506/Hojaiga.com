import sys
sys.path.append("All codes")
import time
import ctypes
from ctypes import wintypes
import win32gui
import win32con
from PIL import ImageGrab

u32 = ctypes.windll.user32
hdesk = u32.OpenDesktopW("default", 0, False, 0x01FF)
if hdesk:
    u32.SetThreadDesktop(hdesk)

# 1. Find or Launch Paint
paint_hwnd = 0
def cb(h, _):
    global paint_hwnd
    if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
        t = win32gui.GetWindowText(h)
        if "paint" in t.lower():
            paint_hwnd = h
            return False
    return True

win32gui.EnumWindows(cb, None)
if not paint_hwnd:
    import subprocess
    subprocess.Popen(['explorer.exe', r'shell:AppsFolder\Microsoft.Paint_8wekyb3d8bbwe!App'])
    time.sleep(2.5)
    win32gui.EnumWindows(cb, None)

print(f"Paint HWND: {paint_hwnd}")
assert paint_hwnd != 0, "Paint window not found!"

# Restore & foreground Paint
u32.ShowWindowAsync(paint_hwnd, win32con.SW_RESTORE)
u32.SetForegroundWindow(paint_hwnd)
time.sleep(0.6)

win_rect = win32gui.GetWindowRect(paint_hwnd)
print(f"Paint Window Rect: {win_rect}")

# 2. Select Pencil tool in Paint via UIA
import uiautomation as auto
root_ctrl = auto.ControlFromHandle(paint_hwnd)
if root_ctrl:
    for c, _ in auto.WalkControl(root_ctrl, maxDepth=12):
        if c.Name and c.Name.strip().lower() == "pencil":
            try:
                ip = c.GetSelectionItemPattern() or c.GetInvokePattern()
                if hasattr(ip, "Select"):
                    ip.Select()
                elif hasattr(ip, "Invoke"):
                    ip.Invoke()
                print("Selected Pencil tool in Paint!")
                break
            except Exception as e:
                print("Pencil select err:", e)
time.sleep(0.3)

# 3. Detect white canvas center
canvas_box = None
if root_ctrl:
    for c, _ in auto.WalkControl(root_ctrl, maxDepth=12):
        b = c.BoundingRectangle
        if b and (b.right - b.left > 250) and (b.bottom - b.top > 200):
            if c.AutomationId == "scrollViewer" or c.ControlTypeName in ("PaneControl", "CustomControl", "ImageControl"):
                canvas_box = (b.left, b.top, b.right, b.bottom)
                break

if canvas_box:
    cx = (canvas_box[0] + canvas_box[2]) // 2
    cy = (canvas_box[1] + canvas_box[3]) // 2
    print(f"Canvas box: {canvas_box}, Center: ({cx}, {cy})")
else:
    cx = win_rect[0] + int((win_rect[2] - win_rect[0]) * 0.5)
    cy = win_rect[1] + int((win_rect[3] - win_rect[1]) * 0.55)
    print(f"Fallback center: ({cx}, {cy})")

# 4. Take before screenshot of canvas
before_im = ImageGrab.grab(bbox=(cx-120, cy-120, cx+120, cy+120))
before_im.save("scratch/nonagon_before.png")

# 5. Draw Nonagon using VisualCursor (physical=True with auto-restore)
from core_organs.visual_cursor import get_cursor
vc = get_cursor()
vc.show()
time.sleep(0.5)

print("Drawing 9-sided nonagon on Paint canvas...")
vc.draw_shape("nonagon", cx, cy, width=180, height=180, steps=54, label="Nonagon", physical=True, hwnd=paint_hwnd)
time.sleep(0.5)

# 6. Take after screenshot of canvas
after_im = ImageGrab.grab(bbox=(cx-120, cy-120, cx+120, cy+120))
after_im.save("scratch/nonagon_after.png")

import numpy as np
diff = np.sum(np.abs(np.array(before_im, dtype=int) - np.array(after_im, dtype=int)))
print(f"Canvas pixel difference after nonagon drawing: {diff}")
if diff > 10000:
    print("SUCCESS: Nonagon physically and visibly drawn on Paint canvas!")
else:
    print("WARNING: Low pixel difference, check screenshot!")

vc.hide()
