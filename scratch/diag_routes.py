import sys, time, ctypes
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.atlas.fixture import harness
from core_organs import background_window as bw
from core_organs.atlas import scanner as SC
from core_organs import fast_uia
from core_organs.professor.effectors import Effector

u = ctypes.WinDLL("user32")
u.GetForegroundWindow.restype = ctypes.c_void_p


def fgid():
    return int(u.GetForegroundWindow() or 0)


def trial(name, fn):
    fg0 = fgid()
    h = harness.launch(minimized=True)
    hwnd = h["hwnd"]
    try:
        time.sleep(0.8)
        with bw.BackgroundSession(hwnd) as bg:
            nodes, waited, fo = SC.ensure_tree(hwnd, bg)
            fx = Effector(hwnd, allow_input=True, owned=True)
            s0 = harness.read_state_text(hwnd)
            fg_before = fgid()
            res = fn(fx, nodes, hwnd)
            time.sleep(0.8)
            fg_after = fgid()
            s1 = harness.read_state_text(hwnd)
            def title(h):
                b = ctypes.create_unicode_buffer(80)
                if h:
                    u.GetWindowTextW(ctypes.c_void_p(h), b, 80)
                return b.value[:40]
            print(f"{name:34s} fg_before={title(fg_before)!r} fg_after={title(fg_after)!r} stolen={fg_after == hwnd}  state_changed={s0 != s1}  delivered={res[1][:60]}")
    finally:
        harness.close(h)
        time.sleep(0.6)


def by(nodes, name):
    return next(n for n in nodes if n.name == name)


def centre(n):
    l, t, r, b = n.rect
    return (l + r) // 2, (t + b) // 2


trial("posted click on tab", lambda fx, nodes, hwnd: fx.click_xy(*centre(by(nodes, "Options"))))
trial("posted click on toolbar button", lambda fx, nodes, hwnd: fx.click_xy(*centre(by(nodes, "Add Marker"))))
trial("posted click on tab (again)", lambda fx, nodes, hwnd: fx.click_xy(*centre(by(nodes, "Data"))))
trial("UIA Select on tab", lambda fx, nodes, hwnd: fx.node(by(nodes, "Options")))
trial("no action at all (control)", lambda fx, nodes, hwnd: (True, "nothing sent"))
