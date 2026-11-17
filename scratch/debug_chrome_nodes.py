import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR
from core_organs import fast_uia
run = AR.AppRun(AR.SPECS["chrome"], vision=False, log=lambda s: None)
try:
    assert run.start()
    nodes = fast_uia.snapshot(run.hwnd, timeout_ms=6000) or []
    for n in nodes:
        if n.name and n.rect[2] > n.rect[0] and n.ctype in ("ButtonControl","MenuItemControl","EditControl","TabItemControl","SplitButtonControl","ComboBoxControl","MenuBarControl","ToolBarControl") and n.depth < 9:
            print(n.depth, n.ctype, repr(n.name)[:60], "pats", n.pats, "exp", n.expand_state, "off" if n.offscreen else "")
finally:
    run.finish()
