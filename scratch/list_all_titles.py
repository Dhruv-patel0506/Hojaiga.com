import win32gui, win32process

def cb(hwnd, _):
    if win32gui.IsWindow(hwnd):
        t = win32gui.GetWindowText(hwnd)
        c = win32gui.GetClassName(hwnd)
        if t:
            print(f"HWND={hwnd} class={c} title={t}")

win32gui.EnumWindows(cb, None)
