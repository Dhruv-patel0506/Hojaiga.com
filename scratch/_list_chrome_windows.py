import win32gui
import win32process


def cb(h, _):
    c = win32gui.GetClassName(h)
    if c.startswith("Chrome_") and win32gui.IsWindowVisible(h):
        t = win32gui.GetWindowText(h) or ""
        if t:
            pid = win32process.GetWindowThreadProcessId(h)[1]
            print(f"hwnd={h} pid={pid} class={c} title={t!r}")
    return True


win32gui.EnumWindows(cb, None)
