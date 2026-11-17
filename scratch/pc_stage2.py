import sys, time, gc
sys.path.insert(0, r"d:\new_automation\All codes")
mode = sys.argv[1] if len(sys.argv) > 1 else "drag_only"
from core_organs.professor import pointer_course as PC
from core_organs.professor import pointer as PT

c = PC.DotsCanvas(a_pos=(70, 60), b_pos=(1700, 70))
c.start()
assert c.hwnd, c.fail_why
if mode in ("pixels", "both"):
    b = PT.pixels(c.hwnd, (c.x, c.y, c.x + c.width, c.y + c.height))
    print("pixels ok", None if b is None else b.shape, flush=True)
    gc.collect()
if mode in ("drag", "both"):
    vp = PC.PT.VirtualPointer(c.hwnd, "pointer_course", PC._Fx(), only=["posted"], allow_touch=False)
    res = vp.drag_drop(c.dot_screen("A"), (c.dot_screen("B")[0] + 36, c.dot_screen("B")[1]), verify=lambda: True)
    print("drag ok", res.ok, res.route, flush=True)
time.sleep(0.3)
c.stop()
gc.collect()
print("MODE", mode, "finished", flush=True)
