import sys
import win32con
import win32gui

hwnd = int(sys.argv[1])
print("before:", bool(win32gui.IsWindow(hwnd)), (win32gui.GetWindowText(hwnd) or "")[:60])
win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
import time
time.sleep(1.5)
print("after close msg sent; alive:", bool(win32gui.IsWindow(hwnd)))
