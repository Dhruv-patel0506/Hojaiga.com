"""settings_diag.py -- read-only: does 'open the About page' actually OFFER the About nav item?
Grounds a fresh minimized Settings window, prints every actionable element, and the judge shortlist."""
import os, sys, time
sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")
os.chdir(r"D:\new_automation\All codes\core_organs")
import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

from core_organs import universal_scan as us, app_scan
from core_organs.desktop_grounding import DesktopGrounding, ConstrainedJudge, GroundedElement

GOAL = "open the About page"
g = DesktopGrounding()
info = us.launch_hidden("Settings", timeout_s=45.0)
hwnd = info.get("hwnd") or 0
print("hwnd=", hwnd, "notes=", info.get("notes"))
time.sleep(1.0)
try:
    from core_organs.desktop_grounding import get_loop
    loop = get_loop()
    loop._run_depth += 1
    try:
        h, els, rep = loop._wait_for_ready("Settings")
    finally:
        loop._run_depth -= 1
    hwnd = h or hwnd
    print(f"READY grounded {len(els)} elements; rep ready={rep.get('ready_wait_s')}")
    actionable = [e for e in els if (e.role or '').lower() not in ('pane','window','group','titlebar','custom','')]
    named = [e for e in els if (e.name or '').strip()]
    print(f"named={len(named)} actionable-role={len(actionable)}")
    print("=== all listitem/treeitem/tabitem/button/hyperlink names (the nav) ===")
    for e in els:
        if (e.role or '').lower() in ('listitem','treeitem','tabitem','button','hyperlink','group'):
            print(f"   role={e.role:<10} name={(e.name or '')[:40]!r}")
    about = [e for e in els if 'about' in (e.name or '').lower()]
    print("=== elements whose name contains 'about' ===")
    for e in about:
        print(f"   name={e.name!r} role={e.role!r} tier={e.tier} bbox={tuple(int(x) for x in e.bbox)}")
    print("=== top 12 by ConstrainedJudge.rank_scored for GOAL ===")
    ranked = ConstrainedJudge.rank_scored(GOAL, els)
    for sc, i, e in ranked[:12]:
        print(f"   {sc:6.1f}  role={e.role:<12} name={(e.name or '')[:34]!r}")
    print("=== scan_desktop (deep UIA) 'about' items ===")
    scan = app_scan.scan_desktop(hwnd)
    print("scan nodes=", len(scan.elements))
    for e in scan.elements:
        if 'about' in (e.get('name') or '').lower():
            print(f"   name={e.get('name')!r} role={e.get('role')!r}")
finally:
    try:
        us.close_window(hwnd, timeout_s=4.0, discard_unsaved=True)
    except Exception:
        pass
    print("closed our Settings instance")
