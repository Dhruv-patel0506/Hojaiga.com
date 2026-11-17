import ctypes, ctypes.wintypes as wt, threading, time, json, gc, sys
if len(sys.argv) > 1 and sys.argv[1] == "withimport":
    sys.path.insert(0, r"d:\new_automation\All codes")
    from core_organs.professor import pointer as PT
    from core_organs.professor import config as CFG

u = ctypes.WinDLL("user32", use_last_error=True)
u.DefWindowProcW.restype = ctypes.c_ssize_t
u.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
u.RegisterClassW.argtypes = [ctypes.c_void_p]
u.CreateWindowExW.restype = wt.HWND
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p)

class _WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]

class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wt.HWND), ("message", ctypes.c_uint), ("wParam", wt.WPARAM),
                ("lParam", wt.LPARAM), ("pt", wt.POINT), ("time", ctypes.c_uint)]

def wp(h, msg, w, lp):
    return u.DefWindowProcW(h, msg, w, 0 if lp is None else int(lp))

PROC = WNDPROC(wp)
stop = False

def main():
    global stop
    hinst = ctypes.WinDLL("kernel32", use_last_error=True).GetModuleHandleW(None)
    cls = _WNDCLASSW()
    cls.lpfnWndProc = PROC
    cls.hInstance = hinst
    cls.lpszClassName = "MiniProbeClass"
    u.RegisterClassW(ctypes.byref(cls))
    hwnd = u.CreateWindowExW(0, "MiniProbeClass", "mini", 0x10000000, 100, 100, 400, 200, 0, 0, hinst, 0)
    print("hwnd", hwnd, flush=True)
    m = MSG()
    while not stop:
        r = u.GetMessageW(ctypes.byref(m), 0, 0, 0)
        if r in (0, -1):
            break
        u.TranslateMessage(ctypes.byref(m))
        u.DispatchMessageW(ctypes.byref(m))

th = threading.Thread(target=main, daemon=True)
th.start()
time.sleep(0.3)
for i in range(10):
    _ = json.dumps({"k%d" % j: "v" * 80 for j in range(2000)})
    gc.collect()
    time.sleep(0.03)
stop = True
print("MINI survived", flush=True)
