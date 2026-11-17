import sys, time
sys.path.insert(0, r"d:\new_automation\All codes")
import ctypes
from core_organs.professor import pointer_course as PC
stage = int(sys.argv[1]) if len(sys.argv) > 1 else 1

if stage >= 1:
    from core_organs.professor import pointer_course as PC
    for i in range(2):
        c = PC.DotsCanvas(a_pos=(70, 60), b_pos=(1700, 70))
        c.start()
        assert c.hwnd, c.fail_why
        time.sleep(0.2)
        c.stop()
    print("stage1 canvas up/down ok", flush=True)

if stage >= 2:
    from core_organs.professor import pointer as PT
    c = PC.DotsCanvas(a_pos=(70, 60), b_pos=(1700, 70))
    c.start()
    b = PT.pixels(c.hwnd, (c.x, c.y, c.x + c.width, c.y + c.height))
    print("stage2 pixels:", type(b), None if b is None else b.shape, flush=True)
    c.stop()

if stage >= 3:
    c = PC.DotsCanvas(a_pos=(70, 60), b_pos=(1700, 70))
    c.start()
    vp = PC.PT.VirtualPointer(c.hwnd, "pointer_course", PC._Fx(), only=["posted"], allow_touch=False)
    res = vp.drag_drop(c.dot_screen("A"), (c.dot_screen("B")[0] + 36, c.dot_screen("B")[1]), verify=lambda: True)
    print("stage3 drag:", res.ok, res.route, flush=True)
    c.stop()
print("END stages run:", stage, flush=True)
