"""Pre-warm Calculator the same way operate_app does (launch hidden/minimized), so the Jarvis run
starts on an enumerable window instead of hanging inside the launch path."""
import sys, time
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs import universal_scan as us
from core_organs.desktop_grounding import _launch_if_missing, get_loop

loop = get_loop()
h = loop.grounding.find_window("Calculator")
print("already running:", h)
if not h:
    ok = us.launch_hidden("Calculator")
    print("launch_hidden ->", ok)
    for i in range(15):
        time.sleep(2)
        h = loop.grounding.find_window("Calculator")
        if h:
            print("window appeared after %.1fs: hwnd=%s" % (2 * (i + 1), h))
            break
print("FINAL hwnd:", loop.grounding.find_window("Calculator"))
