import threading
import ctypes

def worker():
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    print("worker OpenInputDesktop:", hdesk)
    if hdesk:
        res = user32.SetThreadDesktop(hdesk)
        print("worker SetThreadDesktop:", res, "err:", kernel32.GetLastError())
        pos_res = user32.SetCursorPos(500, 500)
        print("worker SetCursorPos:", pos_res, "err:", kernel32.GetLastError())
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        print(f"Cursor pos: ({pt.x}, {pt.y})")

t = threading.Thread(target=worker)
t.start()
t.join()
