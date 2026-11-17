"""Why does PPT open exactly 6 dropdowns no matter the budget? Live mapper run with organ_50 DEBUG on:
prints every 'dropdown deepen failed' reason and the candidate ctype/name list it tried."""
import os, sys, time, logging, subprocess
sys.path.insert(0, r"d:\new_automation\All codes")
logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
for noisier in ("uiautomation", "core_organs.fast_uia", "brain", "hojaiga"):
    logging.getLogger(noisier).setLevel(logging.INFO)
logging.getLogger("hojaiga.organ_50_layout_map").setLevel(logging.DEBUG)

import win32gui, win32con
from core_organs import organ_48_app_behavior_model as bm
from core_organs import organ_50_layout_map as lm

model = bm.get_model()

def _ppt_hwnd():
    found = []
    def _cb(h, _):
        if win32gui.GetClassName(h) == "PPTFrameClass" and win32gui.IsWindowVisible(h):
            found.append(h)
    win32gui.EnumWindows(_cb, None)
    for h in found:
        if "powerpoint" in win32gui.GetWindowText(h).lower():
            return h
    return found[0] if found else 0

hwnd = _ppt_hwnd()
if not hwnd:
    subprocess.Popen([r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE", "/b"])
    end = time.time() + 60
    while time.time() < end and not hwnd:
        time.sleep(1)
        hwnd = _ppt_hwnd()
    time.sleep(8)
print("PPT hwnd:", hwnd, win32gui.GetWindowText(hwnd) if hwnd else "")

t0 = time.time()
summ = lm.map_layout(model, "powerpoint", hwnd, deepen="ribbon", ribbon_budget_s=150.0,
                     version_hash=bm.app_version_hash(bm._exe_of_hwnd(hwnd)))
print(f"[probe] map_layout took {time.time()-t0:.1f}s")
print("[probe] deepen:", summ.get("deepen"), "mode:", summ.get("deepen_mode"), "skipped:", summ.get("skipped"))
try:
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
except Exception:
    pass
