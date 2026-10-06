import sys, os, json, time, psutil
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import task_lifecycle as tl, universal_scan as us
t0 = time.time()
info = us.launch_hidden("steam", timeout_s=90.0, fast=False)
print("launched", info.get("launched"), info.get("title"), flush=True)
time.sleep(5)
if info.get("hwnd"):
    r = tl.capture_evidence("steam", "Steam needs a sign-in (credentials): a human must sign in; the agent never types credentials", hwnd=info["hwnd"])
    print(json.dumps(r, default=str))
    if r.get("path"):
        print("bytes", os.path.getsize(r["path"]))
for p in psutil.process_iter(["name", "create_time"]):
    try:
        if p.info["name"] and p.info["name"].lower().startswith(("steam.exe", "steamwebhelper")) and p.info["create_time"] > t0 - 2:
            p.kill()
    except Exception:
        pass
