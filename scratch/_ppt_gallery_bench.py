"""D-workstream proof: re-scan PowerPoint (live) through the production deep path and show that
ribbon-internal dropdown galleries ('More Options', 'Change Case'...) now get revealed and persisted
as bm_layout rows with via='dropdown:<name>' (before the fix, ALL MenuItemControls were skipped)."""
import os, sys, time, json
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs import organ_48_app_behavior_model as bm
from core_organs import scan_learner, fast_scan

KEY = "powerpoint"
model = bm.get_model()

def gallery_counts():
    return [dict(r) for r in model._conn.execute(
        "SELECT region_name, COUNT(*) n FROM bm_layout WHERE app_key=? AND via LIKE 'dropdown:%'"
        " GROUP BY region_name ORDER BY n DESC", (KEY,)).fetchall()]

before = gallery_counts()
print("dropdown galleries BEFORE:", before)

# launch PPT if not running WITH A BLANK PRESENTATION (/b): the bare start screen has no real ribbon
# (measured: a start-screen launch gave only Data/Options/Shapes tabs and 0 gallery candidates)
import subprocess, win32gui, win32con
def _ppt_hwnd():
    found = []
    def _cb(h, _):
        if win32gui.GetClassName(h) == "PPTFrameClass" and win32gui.IsWindowVisible(h):
            found.append(h)
    win32gui.EnumWindows(_cb, None)
    # prefer a document window (title carries 'PowerPoint' with a presentation name), else any
    for h in found:
        if "powerpoint" in win32gui.GetWindowText(h).lower():
            return h
    return found[0] if found else 0

hwnd = _ppt_hwnd()
if not hwnd or not win32gui.GetWindowText(hwnd):
    subprocess.Popen([r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE", "/b"])
    end = time.time() + 60
    while time.time() < end and not hwnd:
        time.sleep(1)
        hwnd = _ppt_hwnd()
    for _ in range(15):            # wait for the blank presentation to actually be there
        t = win32gui.GetWindowText(hwnd) if hwnd else ""
        if t and "powerpoint" in t.lower():
            break
        time.sleep(1)
        hwnd = _ppt_hwnd()
    if hwnd:
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    print("PPT hwnd:", hwnd, "title:", win32gui.GetWindowText(hwnd) if hwnd else "")
time.sleep(2)

t0 = time.time()
# 240 s: measured at 90 s the dropdown phase only reached 5 of 69 candidates before the budget rail
# stopped it (honest, bounded) - a longer single proof run shows the named ribbon galleries too.
rep = fast_scan.deep_scan("powerpoint", budget_s=240.0, vision=False, close_if_launched=False,
                          fresh=True, force=True)
print(f"scan done in {time.time()-t0:.1f}s; seconds={rep.get('seconds')}")
lay = rep.get("layout") or {}
print("LAYOUT KEYS:", {k: lay.get(k) for k in ("nodes", "regions", "deepen", "error")})
print("DEEPEN STATS:", json.dumps(lay.get("deepen") or {}, default=str)[:600])
print("REPORT keys with 'ribbon'/'deepen':",
      {k: v for k, v in rep.items() if "ribbon" in str(k).lower() or "deepen" in str(k).lower()})
scan_learner.join_all(30)   # let anything queued drain briefly (not required for D)

after = gallery_counts()
print("dropdown galleries AFTER:", json.dumps(after[:15]))
names = [r["region_name"] for r in after]
hit = [n for n in names if n.lower() in ("more options", "change case", "layout", "editor vdiagnostics",
                                         "sections", "line spacing", "shading", "highlight", "grow/shrink font",
                                         "order", "arrange", "align", "rotate", "visibility")]
print("ribbon menuitem galleries revealed:", hit or "(none of the known gallery names)")
tot = sum(r["n"] for r in after)
print("total dropdown:-derived layout rows:", tot)

# cleanup: close the PPT we launched
def _cb(h, acc):
    if win32gui.GetClassName(h) == "PPTFrameClass":
        acc.append(h)
hs = []
win32gui.EnumWindows(_cb, hs)
for h in hs:
    win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
    print("closed PPT hwnd", h)
