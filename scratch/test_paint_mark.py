import ctypes, time, win32gui, win32con
from ctypes import wintypes
from PIL import ImageGrab

u32 = ctypes.windll.user32
hdesk = u32.OpenDesktopW("default", 0, False, 0x01FF)
if hdesk: u32.SetThreadDesktop(hdesk)

# Find Paint
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

print("paint_hwnd:", paint_hwnd)
if not paint_hwnd:
    import subprocess
    subprocess.Popen(['explorer.exe', r'shell:AppsFolder\Microsoft.Paint_8wekyb3d8bbwe!App'])
    time.sleep(2.5)
    win32gui.EnumWindows(cb, None)
    print("Launched Paint, hwnd:", paint_hwnd)

u32.ShowWindowAsync(paint_hwnd, 9) # SW_RESTORE
u32.SetForegroundWindow(paint_hwnd)
time.sleep(0.5)

r = win32gui.GetWindowRect(paint_hwnd)
print("Paint rect:", r)
cx = r[0] + 500
cy = r[1] + 350

# Take before screenshot of canvas
before = ImageGrab.grab(bbox=(cx-50, cy-50, cx+150, cy+150))
before.save("scratch/before_draw.png")

# TEST 1: PostMessageW
print("Testing PostMessageW...")
pt = wintypes.POINT(cx, cy)
u32.ScreenToClient(paint_hwnd, ctypes.byref(pt))
lp0 = (pt.y << 16) | (pt.x & 0xFFFF)
u32.PostMessageW(paint_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp0)
time.sleep(0.02)
for i in range(1, 20):
    pt2 = wintypes.POINT(cx + i * 5, cy + i * 5)
    u32.ScreenToClient(paint_hwnd, ctypes.byref(pt2))
    lp = (pt2.y << 16) | (pt2.x & 0xFFFF)
    u32.PostMessageW(paint_hwnd, win32con.WM_MOUSEMOVE, win32con.MK_LBUTTON, lp)
    time.sleep(0.015)
u32.PostMessageW(paint_hwnd, win32con.WM_LBUTTONUP, 0, lp)
time.sleep(0.5)

after_post = ImageGrab.grab(bbox=(cx-50, cy-50, cx+150, cy+150))
after_post.save("scratch/after_post.png")

# Check difference
import numpy as np
diff_post = np.sum(np.abs(np.array(before, dtype=int) - np.array(after_post, dtype=int)))
print("Difference after PostMessageW:", diff_post)
