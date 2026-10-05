import win32gui, win32process, win32con

def callback(hwnd, _):
    if win32gui.IsWindow(hwnd):
        title = win32gui.GetWindowText(hwnd)
        cname = win32gui.GetClassName(hwnd)
        if "paint" in title.lower() or cname == "MSPaintApp":
            vis = win32gui.IsWindowVisible(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            print(f"FOUND: hwnd={hwnd} title='{title}' class='{cname}' visible={vis} rect={rect}")

win32gui.EnumWindows(callback, None)
