import sys
sys.path.append("All codes")
import time
import win32gui
import win32con
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

# Find Paint
paint_hwnd = 0
def cb(h, _):
    global paint_hwnd
    if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
        t = win32gui.GetWindowText(h)
        c = win32gui.GetClassName(h)
        if "paint" in t.lower() or c == "MSPaintApp":
            paint_hwnd = h
            return False
    return True
win32gui.EnumWindows(cb, None)

print(f"Paint HWND: {paint_hwnd}")
if paint_hwnd:
    user32.ShowWindow(paint_hwnd, 9) # SW_RESTORE
    user32.SetForegroundWindow(paint_hwnd)
    time.sleep(0.5)
    r = win32gui.GetWindowRect(paint_hwnd)
    print(f"Paint rect: {r}")
    
    # Center of canvas
    cx = r[0] + (r[2] - r[0]) // 2
    cy = r[1] + (r[3] - r[1]) // 2 + 50
    print(f"Testing PostMessage draw at ({cx}, {cy})...")
    
    pt = wintypes.POINT(cx, cy)
    user32.ScreenToClient(paint_hwnd, ctypes.byref(pt))
    lp = (pt.y << 16) | (pt.x & 0xFFFF)
    
    res1 = user32.PostMessageW(paint_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
    time.sleep(0.05)
    for i in range(10):
        pt = wintypes.POINT(cx + i*10, cy + i*10)
        user32.ScreenToClient(paint_hwnd, ctypes.byref(pt))
        lp = (pt.y << 16) | (pt.x & 0xFFFF)
        user32.PostMessageW(paint_hwnd, win32con.WM_MOUSEMOVE, win32con.MK_LBUTTON, lp)
        time.sleep(0.02)
    user32.PostMessageW(paint_hwnd, win32con.WM_LBUTTONUP, 0, lp)
    print("PostMessage sequence sent, result:", res1)
