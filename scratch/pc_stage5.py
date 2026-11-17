import sys, time, json, gc
sys.path.insert(0, r"d:\new_automation\All codes")
mode = sys.argv[1]  # idle | paint | click
from core_organs.professor import pointer_course as PC
from core_organs.professor import pointer as PT

c = PC.DotsCanvas(a_pos=(70, 60), b_pos=(1700, 70))
c.start()
assert c.hwnd, c.fail_why
if mode == "paint":
    for i in range(400):
        PT._u.PostMessageW(c.hwnd, PT.WM_MOUSEMOVE, 0, PT._lp(70 + i, 60))
elif mode == "click":
    PT._u.PostMessageW(c.hwnd, PT.WM_LBUTTONDOWN, 1, PT._lp(70, 60))
    for i in range(400):
        PT._u.PostMessageW(c.hwnd, PT.WM_MOUSEMOVE, 1, PT._lp(70 + i * 4, 60))
    PT._u.PostMessageW(c.hwnd, PT.WM_LBUTTONUP, 0, PT._lp(70 + 400 * 4, 60))
time.sleep(0.4)
for i in range(8):
    _ = json.dumps({"k%d" % j: "v" * 80 for j in range(2000)})
    gc.collect()
    time.sleep(0.03)
c.stop()
gc.collect()
print("MODE", mode, "survived", flush=True)
