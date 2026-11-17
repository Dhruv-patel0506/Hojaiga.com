import sys, time
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs.professor import pointer_course as PC

c = PC.DotsCanvas(a_pos=(70, 60), b_pos=(1810, 60))
c.start()
print("hwnd:", c.hwnd, "fail:", c.fail_why)
time.sleep(0.3)
c.stop()
print("done")
