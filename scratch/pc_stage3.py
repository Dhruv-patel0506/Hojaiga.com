import sys, time, json, gc
sys.path.insert(0, r"d:\new_automation\All codes")
mode = sys.argv[1] if len(sys.argv) > 1 else "raw"
import ctypes
import ctypes.wintypes as wt
from core_organs.professor import pointer_course as PC
from core_organs.professor import pointer as PT

c = PC.DotsCanvas(a_pos=(70, 60), b_pos=(1700, 70))
c.start()
assert c.hwnd, c.fail_why
if mode == "raw":
    h = c.hwnd
    for i in range(200):
        x = 70 + i * 8
        PT._u.PostMessageW(h, PT.WM_MOUSEMOVE, 0, PT._lp(x, 60))
    PT._u.PostMessageW(h, PT.WM_LBUTTONDOWN, 1, PT._lp(70, 60))
    time.sleep(0.3)
    PT._u.PostMessageW(h, PT.WM_LBUTTONUP, 0, PT._lp(300, 60))
    time.sleep(0.3)
    print("raw posted fine", flush=True)
elif mode == "vp":
    vp = PT.VirtualPointer(c.hwnd, "pointer_course_raw", PC._Fx(), only=["posted"], allow_touch=False)
    res = vp.perform(PT.s_drop((70, 60), (1700, 70)), "drag-drop", verify=lambda: True)
    print("vp perform fine", res.ok, res.route, flush=True)
big = json.dumps({"k%d" % i: "v" * 40 for i in range(3000)})
gc.collect()
time.sleep(0.2)
c.stop()
gc.collect()
print("MODE", mode, "survived, big json len", len(big), flush=True)
