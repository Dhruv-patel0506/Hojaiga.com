import threading
import ctypes
import time
import win32gui
import win32con
import uiautomation as auto

def inspect_worker():
    user32 = ctypes.windll.user32
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    if hdesk:
        user32.SetThreadDesktop(hdesk)
    
    fg = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(fg, buf, 512)
    print(f"Worker GetForegroundWindow: hwnd={fg} title='{buf.value}'")
    
    def enum_cb(h, _):
        if user32.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(h, buf, 512)
            t = buf.value
            if t and ("obs" in t.lower() or "setting" in t.lower()):
                print(f"Visible window: hwnd={h} title='{t}'")
        return True
    
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

t = threading.Thread(target=inspect_worker)
t.start()
t.join()
