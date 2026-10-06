import sys, time
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import popup_policy as pp, headless_input as hin
h = int(sys.argv[1])
print("alive", hin.is_alive(h), pp._title_of(h))
r = pp.resolve_dialog(h, mode="preflight")
print(r)
time.sleep(3)
print("alive after", hin.is_alive(h))
