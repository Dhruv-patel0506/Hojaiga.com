import sys, time, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, capture as CAP, menus as MN
from core_organs.professor.effectors import pattern_of
from core_organs.professor.schema import fold
from core_organs import headless_input as hin
run = AR.AppRun(AR.SPECS["mspaint"], vision=False, max_attempts=1, log=lambda s: None)
try:
    assert run.start()
    run.perceive()
    tasks = run.build_tasks()
    t = next(x for x in tasks if "create a new image" in x["goal"].lower())
    tr = run.run_task(t)
    print("task:", tr.final)
    def rot():
        return next(n for n in run.ex._all_nodes() if fold(n.name) == "rotate" and n.ctype == "ButtonControl")
    def popups(tag):
        time.sleep(0.8)
        print(tag, "popups", hin.popup_windows(run.hwnd))
        run.fx.key("escape"); time.sleep(0.3)
    n = rot(); n.ctrl.SetFocus(); time.sleep(0.3)
    ok, how = run.fx.node(rot()); print("setfocus+invoke", ok, how); popups("A")
    ok, how = MN._expand(run.fx, rot()); print("expand", ok, how); popups("B")
    with run.fx.holding():
        ok, how = run.fx.node(rot()); print("hold+invoke", ok, how); print("   (in hold) popups", hin.popup_windows(run.hwnd)) if time.sleep(0.8) is None else None
    # a different opener: the Zoom combo
    z = next(n for n in run.ex._all_nodes() if fold(n.name) == "zoom" and n.ctype == "ComboBoxControl")
    ok, how = MN._expand(run.fx, z); print("zoom expand", ok, how); popups("Z")
    ok, how = MN._expand(run.fx, next(n for n in run.ex._all_nodes() if fold(n.name) == "file" and n.ctype == "MenuItemControl")); print("file expand", ok); popups("F")
finally:
    run.finish()
