"""Plan test 2 (Word leg): production deep scan of Microsoft Word and the ribbon gallery reveals
('Change Case', 'Character Spacing', 'Line Spacing', 'Sections', 'More Options'...) persisted as
bm_layout rows with via='dropdown:<name>'. Word launched with a blank document (/w): the start
screen has no ribbon (measured with PowerPoint)."""
import os, sys, time, json
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs import organ_48_app_behavior_model as bm
from core_organs import scan_learner, fast_scan

KEY = "word"
model = bm.get_model()

def gallery_counts():
    return [dict(r) for r in model._conn.execute(
        "SELECT region_name, COUNT(*) n FROM bm_layout WHERE app_key=? AND via LIKE 'dropdown:%'"
        " GROUP BY region_name ORDER BY n DESC", (KEY,)).fetchall()]

before = gallery_counts()
print("word dropdown galleries BEFORE:", before)

import subprocess, win32gui, win32con
def _word_hwnd():
    found = []
    def _cb(h, _):
        if win32gui.GetClassName(h) == "OpusApp" and win32gui.IsWindowVisible(h):
            found.append(h)
    win32gui.EnumWindows(_cb, None)
    for h in found:
        if "word" in win32gui.GetWindowText(h).lower():
            return h
    return found[0] if found else 0

hwnd = _word_hwnd()
if not hwnd:
    subprocess.Popen([r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE", "/w"])
    end = time.time() + 60
    while time.time() < end and not hwnd:
        time.sleep(1)
        hwnd = _word_hwnd()
    for _ in range(15):
        t = win32gui.GetWindowText(hwnd) if hwnd else ""
        if t and "word" in t.lower():
            break
        time.sleep(1)
        hwnd = _word_hwnd()
    if hwnd:
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    print("WORD hwnd:", hwnd, "title:", win32gui.GetWindowText(hwnd) if hwnd else "")
time.sleep(2)

t0 = time.time()
rep = fast_scan.deep_scan("word", budget_s=240.0, vision=False, close_if_launched=False,
                          fresh=True, force=True)
print(f"scan done in {time.time()-t0:.1f}s; seconds={rep.get('seconds')}")
lay = rep.get("layout") or {}
print("DEEPEN STATS:", json.dumps(lay.get("deepen") or {}, default=str)[:400])
scan_learner.join_all(30)

after = gallery_counts()
print("word dropdown galleries AFTER:", json.dumps(after[:20]))
names = [r["region_name"] for r in after]
hit = [n for n in names if n.lower() in ("more options", "change case", "sections", "line spacing",
                                         "shading", "highlight", "grow/shrink font", "character spacing",
                                         "layout", "align", "arrange", "rotate", "order", "visibility",
                                         "styles", "edit", "paste", "draw") or "case" in n.lower()]
print("ribbon menuitem galleries revealed:", hit or "(none of the known gallery names)")
print("total dropdown:-derived layout rows:", sum(r["n"] for r in after))
print("QUALITY:", bm.knowledge_quality(model, KEY)["one_line"])

def _cb2(h, acc):
    if win32gui.GetClassName(h) == "OpusApp":
        acc.append(h)
hs = []
win32gui.EnumWindows(_cb2, hs)
for h in hs:
    win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
    print("closed WORD hwnd", h)
