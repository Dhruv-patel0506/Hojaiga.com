import ctypes, time, win32gui, win32con
from ctypes import wintypes

u32 = ctypes.windll.user32
hdesk = u32.OpenDesktopW('default', 0, False, 0x01FF)
if hdesk: u32.SetThreadDesktop(hdesk)

hwnd = 720934
if win32gui.IsWindow(hwnd):
    u32.ShowWindow(hwnd, 9) # SW_RESTORE
    u32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    r = win32gui.GetWindowRect(hwnd)
    print("Paint rect:", r)
    
    # White canvas center is around:
    cx = r[0] + 500
    cy = r[1] + 400
    print(f"Canvas point: ({cx}, {cy})")
    
    # Let's test PostMessageW to hwnd
    pt = wintypes.POINT(cx, cy)
    u32.ScreenToClient(hwnd, ctypes.byref(pt))
    lp = (pt.y << 16) | (pt.x & 0xFFFF)
    
    print(f"Client point: ({pt.x}, {pt.y}), lparam={hex(lp)}")
    u32.PostMessageW(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
    time.sleep(0.05)
    for i in range(1, 30):
        pt2 = wintypes.POINT(cx + i * 5, cy + i * 5)
        u32.ScreenToClient(hwnd, ctypes.byref(pt2))
        lp2 = (pt2.y << 16) | (pt2.x & 0xFFFF)
        u32.PostMessageW(hwnd, win32con.WM_MOUSEMOVE, win32con.MK_LBUTTON, lp2)
        time.sleep(0.015)
    u32.PostMessageW(hwnd, win32con.WM_LBUTTONUP, 0, lp2)
    print("Done sending PostMessage strokes")
