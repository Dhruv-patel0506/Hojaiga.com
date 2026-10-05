import threading
import ctypes
import time
import win32gui
import uiautomation as auto
import organ_30_app_scanner as s

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

hwnd = s.ensure_obs_running()
print("OBS HWND:", hwnd)

def worker_focus(target_hwnd):
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    if hdesk:
        user32.SetThreadDesktop(hdesk)

    fg_hwnd = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(fg_hwnd, buf, 512)
    print(f"Worker initial foreground: hwnd={fg_hwnd} title='{buf.value}'")

    cur_tid = kernel32.GetCurrentThreadId()
    target_tid = user32.GetWindowThreadProcessId(target_hwnd, None)
    fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0

    print(f"tids: cur={cur_tid}, target={target_tid}, fg={fg_tid}")

    # AllowSetForegroundWindow
    user32.AllowSetForegroundWindow(0xFFFFFFFF) # ASFW_ANY

    if fg_tid and fg_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, fg_tid, True)
    if target_tid and target_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, target_tid, True)

    # Pulse Alt key
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)

    # Bring to foreground
    user32.ShowWindow(target_hwnd, 9) # SW_RESTORE
    user32.BringWindowToTop(target_hwnd)
    res = user32.SetForegroundWindow(target_hwnd)
    print("Worker SetForegroundWindow result:", res)

    if fg_tid and fg_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, fg_tid, False)
    if target_tid and target_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, target_tid, False)

    time.sleep(0.3)
    new_fg = user32.GetForegroundWindow()
    user32.GetWindowTextW(new_fg, buf, 512)
    print(f"Worker new foreground: hwnd={new_fg} title='{buf.value}'")

t = threading.Thread(target=worker_focus, args=(hwnd,))
t.start()
t.join()
