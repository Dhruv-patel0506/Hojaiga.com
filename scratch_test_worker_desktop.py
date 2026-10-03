import uiautomation as auto # Import uiautomation FIRST on main thread
import win32gui
import threading
import ctypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

print("Main thread SetThreadDesktop test (expected to fail since UIA imported):")
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    res = user32.SetThreadDesktop(hdesk)
    print(f"Main thread: res={res} err={kernel32.GetLastError()}")

def worker():
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    if hdesk:
        res = user32.SetThreadDesktop(hdesk)
        print(f"Worker thread: res={res} err={kernel32.GetLastError()}")
        pos_res = user32.SetCursorPos(700, 700)
        print(f"Worker SetCursorPos(700, 700): res={pos_res} err={kernel32.GetLastError()}")
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        print(f"Worker Cursor pos: ({pt.x}, {pt.y})")
        fg = user32.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(fg, buf, 512)
        print(f"Worker Foreground: hwnd={fg} title='{buf.value}'")

t = threading.Thread(target=worker)
t.start()
t.join()
