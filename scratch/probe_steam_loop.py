import sys, os, json, time, psutil
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import desktop_grounding as dg
t0 = time.time()
r = dg.operate_app("steam", ["open the Library tab"], max_steps_per_goal=6)
print("elapsed", round(time.time() - t0, 1))
print(json.dumps({k: v for k, v in r.items() if k not in ("trace_full",)}, default=str)[:3500])
# reap what THIS run launched (by creation time, never by image name)
now = time.time()
for p in psutil.process_iter(["name", "create_time"]):
    try:
        if p.info["name"] and p.info["name"].lower().startswith(("steam.exe", "steamwebhelper")) and p.info["create_time"] > t0 - 2:
            p.kill()
    except Exception:
        pass
