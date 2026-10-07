"""verify_uwp.py -- prove the UWP actuation fix: 'open the About page' should now reach the
real 'About' nav item (content realizes) and complete via a UIA pattern, not a fake XAML click."""
import os, sys, time, logging
sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")
os.chdir(r"D:\new_automation\All codes\core_organs")
logging.basicConfig(level=logging.INFO, format="%(message)s")
from core_organs.desktop_grounding import operate_app
from core_organs import universal_scan as us

GOALS = ["open the About page"]
r = operate_app("Settings", GOALS, allow_destructive=False, max_steps_per_goal=5, isolated=True)
print("\n================ RESULT ================")
print("completed=", r.get("completed"), "steps=", r.get("steps"),
      "window=", r.get("window_title"), "elapsed=", r.get("elapsed_s"))
for i, t in enumerate(r.get("trace") or []):
    print(f"  step {i}: {t if isinstance(t, str) else str(t)[:200]}")
hwnd = r.get("hwnd") or 0
if r.get("launched") and hwnd:
    us.close_window(hwnd, timeout_s=4.0, discard_unsaved=True)
    print("cleanup: closed our Settings instance")
