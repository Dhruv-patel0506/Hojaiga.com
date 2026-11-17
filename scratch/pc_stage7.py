import sys, time, json, gc
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs.professor import pointer_course as PC
import threading
c = PC.DotsCanvas(a_pos=(70, 60), b_pos=(1700, 70))
c.start()
assert c.hwnd, c.fail_why
for i in range(10):
    _ = json.dumps({"k%d" % j: "v" * 80 for j in range(2000)})
    gc.collect()
    time.sleep(0.03)
print("SURVIVED", flush=True)
c.stop()
print("STOPPED", flush=True)
print("THREADS", [t.name for t in threading.enumerate()], flush=True)
