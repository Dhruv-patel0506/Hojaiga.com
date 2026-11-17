import win32gui
import win32process

def cb(h, _):
    if not win32gui.IsWindowVisible(h):
        return True
    t = win32gui.GetWindowText(h) or ""
    if not t:
        return True
    low = t.lower()
    if "powerpoint" in low or "ppt" in low or "save" in low or "license" in low or "microsoft" in low:
        pid = win32process.GetWindowThreadProcessId(h)[1]
        print(f"hwnd={h} pid={pid} class={win32gui.GetClassName(h)} title={t!r}")
    return True

win32gui.EnumWindows(cb, None)
import subprocess
print(subprocess.run(["tasklist", "/FI", "IMAGENAME eq POWERPNT.EXE"], capture_output=True, text=True).stdout)
