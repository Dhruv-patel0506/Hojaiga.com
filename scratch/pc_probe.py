import ctypes, ctypes.wintypes as wt, threading, time, sys
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs.professor import pointer_course as PC

msgs = []

def probe(width, height, tag):
    c = PC.DotsCanvas(a_pos=(70, 60), b_pos=(width - 70, 60))
    c.width, c.height = width, height
    proc = None
    def wp(h, msg, w, lp):
        msgs.append(msg)
        return PC._u.DefWindowProcW(h, msg, w, lp if lp else 0)
    def main():
        nonlocal proc
        hinst = PC._k.GetModuleHandleW(None)
        proc = PC.WNDPROC(wp)
        cls = PC._WNDCLASSW()
        cls.style = PC.CS_HREDRAW | PC.CS_VREDRAW
        cls.lpfnWndProc = proc
        cls.hInstance = hinst
        cls.hCursor = PC._u.LoadCursorW(0, ctypes.cast(32512, wt.LPCWSTR))
        cls.hbrBackground = 0
        cls.lpszClassName = "ProbeClass_" + tag
        atom = PC._u.RegisterClassW(ctypes.byref(cls))
        e1 = ctypes.get_last_error(); ctypes.set_last_error(0)
        hw = PC._u.CreateWindowExW(PC.WS_EX_TOOLWINDOW | PC.WS_EX_NOACTIVATE,
                                   "ProbeClass_" + tag, "probe", PC.WS_POPUP | PC.WS_VISIBLE,
                                   20, 60, width, height, 0, 0, hinst, 0)
        e2 = ctypes.get_last_error()
        print(f"[{tag} w={width}] atom={atom} err={e1} hwnd={hw} err={e2} msgs={[hex(m) for m in msgs]}")
    th = threading.Thread(target=main); th.start(); th.join(3)
    time.sleep(0.2)

msgs = []; probe(800, 140, "a")
msgs = []; probe(1880, 140, "b")
