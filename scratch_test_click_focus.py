import threading
import ctypes
import time
import win32gui
import uiautomation as auto
import organ_30_app_scanner as s

hwnd = s.ensure_obs_running()
print("OBS HWND:", hwnd)

def focus_via_click(target_hwnd):
    user32 = ctypes.windll.user32
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    if hdesk:
        user32.SetThreadDesktop(hdesk)

    # Get rect of window
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    r = RECT()
    user32.GetWindowRect(target_hwnd, ctypes.byref(r))
    print(f"Target window rect: ({r.left}, {r.top}, {r.right}, {r.bottom})")

    # Click on the title bar (e.g. 50 px below top, 200 px from left)
    cx = r.left + 200
    cy = r.top + 15
    print(f"Clicking at ({cx}, {cy}) to activate window...")

    user32.SetCursorPos(cx, cy)
    time.sleep(0.1)
    user32.mouse_event(0x0002, 0, 0, 0, 0) # LEFTDOWN
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0) # LEFTUP
    time.sleep(0.2)

    fg = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(fg, buf, 512)
    print(f"Foreground after click: hwnd={fg} title='{buf.value}'")

t = threading.Thread(target=focus_via_click, args=(hwnd,))
t.start()
t.join()
