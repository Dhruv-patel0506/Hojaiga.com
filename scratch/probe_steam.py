import sys, os, json, time, ctypes, ctypes.wintypes as wt, tempfile, uuid
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import universal_scan as us, fast_uia, desktop_grounding as dg
u32 = ctypes.windll.user32
t0 = time.time()
info = us.launch_hidden("steam", timeout_s=90.0, fast=False)
print("launch:", {k: info.get(k) for k in ("launched", "hwnd", "title", "resolved", "notes", "launch_s", "already_running_dialog", "startup_dialog_needs_human")}, flush=True)
h = info.get("hwnd")
if h:
    p = wt.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(p)); print("pid", p.value, flush=True)
    print("wake:", us.wake_accessibility(h), flush=True)
    time.sleep(6)
    n = us.wait_tree_ready(h, timeout_s=25.0, min_nodes=5)
    print("tree nodes when ready:", n, flush=True)
    snap = list(fast_uia.snapshot(h, timeout_ms=15000) or [])
    print("raw snapshot nodes:", len(snap), flush=True)
    named = [(x.role, x.name) for x in snap if x.name][:40]
    print("named controls (first 40):", named, flush=True)
    g = dg.DesktopGrounding()
    hh, els, rep = g.ground("steam", target_text="Library", max_tier=4)
    print("ground('Library'):", len(els), {k: rep.get(k) for k in ("tiers_ran", "tiers_skipped", "vision_engine")}, flush=True)
    print([(e.name, e.role, e.tier) for e in els][:10], flush=True)
