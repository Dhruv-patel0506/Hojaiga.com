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
    for t in tasks[:6]:
        run.tasks.append(run.run_task(t))
    def find(name, ctype):
        return next((n for n in run.ex._all_nodes() if fold(n.name) == fold(name) and n.ctype == ctype), None)
    def trial(tag):
        n = find("Rotate", "ButtonControl")
        ok, how = MN._expand(run.fx, n)
        t0 = time.time(); got = []
        while time.time() - t0 < 2.5 and not got:
            time.sleep(0.25); got = hin.popup_windows(run.hwnd)
        print(f"{tag}: {ok}; popups {got}")
        for x in run.ex._all_nodes():
            if x.expand_state == 1 and x.name: MN.collapse(x)
        run.fx.key("escape"); time.sleep(0.8)
    trial("plain")
    with run.fx.focus_watch():
        trial("focus_watch")
    with run.fx.focus_watch():
        with run.fx.holding():
            trial("focus_watch+holding")
    with run.learner.training():
        trial("learner.training")
    with run.learner.training(), run.fx.focus_watch():
        trial("training+watch")
finally:
    run.finish()
