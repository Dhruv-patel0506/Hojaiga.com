import ctypes
import time
import win32gui
import uiautomation as auto
import organ_30_app_scanner as s

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def force_foreground_window(hwnd: int) -> bool:
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    if hdesk:
        user32.SetThreadDesktop(hdesk)

    fg_hwnd = user32.GetForegroundWindow()
    if fg_hwnd == hwnd:
        return True

    cur_thread = kernel32.GetCurrentThreadId()
    fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)

    # Attach input to foreground thread
    if fg_thread and fg_thread != cur_thread:
        user32.AttachThreadInput(cur_thread, fg_thread, True)
    if target_thread and target_thread != cur_thread:
        user32.AttachThreadInput(cur_thread, target_thread, True)

    # Simulate Alt key press to unlock foreground
    user32.keybd_event(0x12, 0, 0, 0) # VK_MENU
    user32.keybd_event(0x12, 0, 2, 0) # KEYEVENTF_KEYUP

    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.BringWindowToTop(hwnd)
    res = user32.SetForegroundWindow(hwnd)

    if fg_thread and fg_thread != cur_thread:
        user32.AttachThreadInput(cur_thread, fg_thread, False)
    if target_thread and target_thread != cur_thread:
        user32.AttachThreadInput(cur_thread, target_thread, False)

    return bool(res)

hwnd = s.ensure_obs_running()
print("OBS HWND:", hwnd)

res = force_foreground_window(hwnd)
print("force_foreground_window result:", res)
time.sleep(0.5)

# Check active foreground window
fg = user32.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(512)
user32.GetWindowTextW(fg, buf, 512)
print(f"Active foreground window now: hwnd={fg} title='{buf.value}'")

# Now let's test Alt+F menu navigation
print("Sending Alt+F...")
s.send_alt_sequence("%f")
time.sleep(0.4)
fc = auto.GetFocusedControl()
print("Focused in menu:", fc.Name if fc else None)
s.send_keys(0x1B) # Escape
