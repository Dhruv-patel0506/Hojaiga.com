import sys, time, ctypes
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.atlas.fixture import harness
from core_organs import background_window as bw
from core_organs.atlas import scanner as SC
from core_organs import fast_uia
from core_organs.professor.effectors import Effector

u = ctypes.WinDLL("user32")
u.GetForegroundWindow.restype = ctypes.c_void_p


def who():
    h = u.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(120)
    cl = ctypes.create_unicode_buffer(80)
    if h:
        u.GetWindowTextW(ctypes.c_void_p(h), buf, 120)
        u.GetClassNameW(ctypes.c_void_p(h), cl, 80)
    return f"{h} '{buf.value}' [{cl.value}]"


print("start fg:", who())
h = harness.launch(minimized=True)
hwnd = h["hwnd"]
print("fixture hwnd", hwnd)
try:
    time.sleep(1.0)
    print("after launch (1s):", who())
    with bw.BackgroundSession(hwnd) as bg:
        print("after park:", who())
        nodes, waited, frame_only = SC.ensure_tree(hwnd, bg)
        print("after ensure_tree:", who())
        fx = Effector(hwnd, allow_input=True, owned=True)
        btn = next(n for n in nodes if n.name == "Add Marker")
        for i in range(3):
            time.sleep(0.5)
            print(f"idle {i}:", who())
        ok, how = fx.node(btn)
        print("after Add Marker invoke:", ok, how, "->", who())
        time.sleep(1.0)
        print("1s later:", who())
        nodes2 = fast_uia.snapshot(hwnd, timeout_ms=4000)
        clr = next(n for n in nodes2 if n.name == "Clear Markers")
        ok, how = fx.node(clr)
        print("after Clear invoke:", ok, how, "->", who())
        time.sleep(1.0)
        print("1s later:", who())
finally:
    harness.close(h)
    time.sleep(0.5)
    print("after close:", who())
