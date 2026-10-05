import threading
import ctypes
import time
import win32gui
import uiautomation as auto
import organ_30_app_scanner as s

hwnd = s.ensure_obs_running()
print("OBS HWND:", hwnd)

def test_zorder(target_hwnd):
    user32 = ctypes.windll.user32
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    if hdesk:
        user32.SetThreadDesktop(hdesk)

    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_SHOWWINDOW = 0x0040

    user32.ShowWindow(target_hwnd, 9) # SW_RESTORE
    time.sleep(0.1)

    # Bring to topmost
    user32.SetWindowPos(target_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    time.sleep(0.1)
    # Remove topmost status so it behaves normally
    user32.SetWindowPos(target_hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    time.sleep(0.1)
    res = user32.SetForegroundWindow(target_hwnd)
    print("SetForegroundWindow res:", res)

    time.sleep(0.3)
    fg = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(fg, buf, 512)
    print(f"Foreground now: hwnd={fg} title='{buf.value}'")

t = threading.Thread(target=test_zorder, args=(hwnd,))
t.start()
t.join()
