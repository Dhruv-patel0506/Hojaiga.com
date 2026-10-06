import sys, time, ctypes
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import universal_scan as us, popup_policy as pp
info = us.launch_hidden("obs studio", timeout_s=40.0, fast=True)
print("launch", info.get("hwnd"), info.get("title"), flush=True)
h = info["hwnd"]
di = pp.inspect_dialog(h)
print("title:", di.title, "| message:", di.message[:200], "| buttons:", [(n, a) for n, a, c in di.buttons], flush=True)
cat = pp.classify(di)
print("category:", cat, "| roles:", pp.POLICY.get(cat), flush=True)
print("choose:", pp.choose_button(di, pp.POLICY.get(cat, ()))[0], flush=True)
from core_organs import fast_uia
snap = fast_uia.snapshot(h, timeout_ms=4000) or []
print("nodes:", len(snap), [(n.role, n.name) for n in snap][:20], flush=True)
# leave OBS exactly as it is; report its pid for a PID-only close
pid = wt = None
import ctypes.wintypes as w
p = w.DWORD(); ctypes.windll.user32.GetWindowThreadProcessId(h, ctypes.byref(p)); print("pid", p.value, flush=True)
