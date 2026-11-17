import sys, time, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, menus as MN
from core_organs.professor.schema import fold
from core_organs import headless_input as hin
run = AR.AppRun(AR.SPECS["mspaint"], vision=False, max_attempts=1, log=lambda s: None)
try:
    assert run.start()
    run.perceive()
    tasks = run.build_tasks()
    t = next(x for x in tasks if "create a new image" in x["goal"].lower())
    print("task:", run.run_task(t).final)
    def rot():
        return next(n for n in run.ex._all_nodes() if fold(n.name) == "rotate" and n.ctype == "ButtonControl")
    def wait(tag, s=3.0):
        end = time.time() + s
        while time.time() < end:
            if hin.popup_windows(run.hwnd):
                print(tag, "-> popup after", round(s - (end - time.time()), 1), "s"); return True
            time.sleep(0.25)
        print(tag, "-> NO popup in", s, "s"); return False
    def clean():
        for n in run.ex._all_nodes():
            if getattr(n, "expand_state", -1) == 1 and n.name:
                MN.collapse(n)
        run.fx.key("escape"); time.sleep(0.6)
    ok, how = MN._expand(run.fx, rot()); print("1 expand only", ok, how); wait("1"); clean()
    ok, how = MN._expand(run.fx, rot()); print("2 expand again", ok, how); wait("2"); clean()
    rot().ctrl.SetFocus(); time.sleep(0.3)
    ok, how = MN._expand(run.fx, rot()); print("3 setfocus + expand", ok, how); wait("3"); clean()
    run.fx.key("escape"); time.sleep(0.5)
    ok, how = MN._expand(run.fx, rot()); print("4 escape then expand", ok, how); wait("4"); clean()
finally:
    run.finish()
