import sys, time
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import universal_scan as us, background_window as bw, fast_uia
lh=us.launch_hidden("powerpoint", timeout_s=40.0, fast=True)
print({k:v for k,v in lh.items() if k in("hwnd","launched","status","why")})
h=int(lh.get("hwnd") or 0)
with bw.BackgroundSession(h) as bg:
    time.sleep(2.5)
    nodes=fast_uia.snapshot(h,timeout_ms=8000)
    print(len(nodes))
    for n in nodes:
        if n.name or n.aid: print("  "*min(n.depth,10),n.idx,n.ctype.replace("Control",""),repr(n.name)[:50],n.aid[:30],sorted(n.pats))
us.close_window(h, discard_unsaved=True)
