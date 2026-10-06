"""Blocker #2 acceptance: modern fast_scan deep-scan route, two real apps under budget.
  dense   = File Explorer (a live window, like organ_01's hot call sites scan it: target_hwnd)
  sparse  = Character Map (charmap) - fresh, never scanned, sparse custom GDI tree
Legacy tree_stats keys must map, within_budget must be honest, vision status must be truthful."""
import sys, json, time, ctypes
sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation\All codes\core_organs")

from core_organs import fast_scan, universal_scan as us

def new_explorer_window():
    import subprocess
    subprocess.Popen(["explorer.exe", r"C:\Windows"])
    u = ctypes.windll.user32
    t0 = time.time()
    while time.time() - t0 < 15:
        found = []
        def cb(h, _):
            b = ctypes.create_unicode_buffer(64)
            u.GetClassNameW(h, b, 64)
            if b.value == "CabinetWClass" and u.IsWindowVisible(h):
                found.append(int(h))
            return True
        WNDENUM = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        u.EnumWindows(WNDENUM(cb), 0)
        if found:
            return found[0]
        time.sleep(0.5)
    return 0

results = []
hwnd = new_explorer_window()
print(f"[demo] opened Explorer window hwnd={hwnd}; settling...")
time.sleep(3.0)

for label, kwargs in (("explorer (dense, live window)", dict(target="explorer", target_hwnd=hwnd)),
                      ("calculator (sparse/custom WinUI, FRESH app never scanned)", dict(target="calculator")),
                      ("notepad (warm)", dict(target="notepad"))):
    r = fast_scan.deep_scan_legacy_shape(budget_s=10.0, close_if_launched=True, **kwargs)
    ts = r.get("tree_stats", {})
    row = {
        "app": label,
        "seconds": r.get("seconds"), "within_budget": r.get("within_budget"), "status": r.get("status"),
        "nodes_walked": ts.get("nodes_walked"), "max_depth_seen": ts.get("max_depth_seen"),
        "walk_max_depth": ts.get("walk_max_depth"), "truncated": ts.get("truncated"),
        "stopped_by": ts.get("stopped_by"), "walk_ms": ts.get("walk_ms"),
        "total_elements": r.get("total_elements"), "total_controls": r.get("total_controls"),
        "total_menu_items": r.get("total_menu_items"),
        "phases": r.get("phases"), "vision": r.get("vision"),
        "static_ok": (r.get("static") or {}).get("ok"), "polite_mode": r.get("polite_mode"),
        "warm": r.get("warm"), "closed": r.get("closed"),
    }
    results.append(row)
    if (r.get("vision") or {}).get("job"):
        row["vision_waited"] = fast_scan.wait_for_vision(r, timeout_s=120)
    if hwnd and "explorer" in label:
        us.close_window(hwnd, timeout_s=5.0, discard_unsaved=False)

print("\n==== BLOCKER #2 ACCEPTANCE (modern fast_scan route) ====")
print(json.dumps(results, indent=2, default=str))
