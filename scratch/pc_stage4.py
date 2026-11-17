import sys, time, json, gc
sys.path.insert(0, r"d:\new_automation\All codes")
mode = sys.argv[1]  # route | perform | full
from core_organs.professor import pointer_course as PC
from core_organs.professor import pointer as PT

c = PC.DotsCanvas(a_pos=(70, 60), b_pos=(1700, 70))
c.start()
assert c.hwnd, c.fail_why
script = PT.s_drop((70, 60), (1700, 70))
if mode == "route":
    r = PT.PostedRoute(c.hwnd, None).deliver(script)
    print("route delivered", r.ok, r.note, flush=True)
else:
    vp = PT.VirtualPointer(c.hwnd, "pointer_course_raw", PC._Fx(), only=["posted"], allow_touch=False)
    if mode == "perform":
        res = vp.perform(script, "drag-drop", verify=lambda: True)
        print("perform ok", res.ok, res.route, flush=True)
    else:
        res = vp.drag_drop((70, 60), (1700, 70), verify=lambda: True)
        print("drag_drop ok", res.ok, res.route, flush=True)
for i in range(5):
    gc.collect()
    _ = json.dumps({"k%d" % j: "v" * 80 for j in range(2000)})
    time.sleep(0.05)
c.stop()
gc.collect()
print("MODE", mode, "survived", flush=True)
