import sys, time, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, probe as PB, menus as MN
from core_organs.professor.schema import fold
from core_organs import headless_input as hin
run = AR.AppRun(AR.SPECS["mspaint"], vision=False, max_attempts=1, log=lambda s: None)
try:
    assert run.start()
    run.perceive()
    tasks = run.build_tasks()
    tr = run.run_task(next(x for x in tasks if "use brushes" in x["goal"].lower()))
    print("task1:", tr.final, [ (r.get('verb'), r.get('status'), r.get('route'), r.get('summary','')[:150]) for a in tr.attempts for r in a.results if 'verb' in r])
    nodes = run.ex._all_nodes()
    print("expanded nodes:", [(n.ctype[:-7], n.name, n.expand_state) for n in nodes if n.expand_state == 1])
    print("popups:", hin.popup_windows(run.hwnd), "windows:", hin.process_windows(run.hwnd, include_hidden=False))
    rot = next(n for n in nodes if fold(n.name) == "rotate" and n.ctype == "ButtonControl")
    print("rotate:", rot.enabled, rot.expand_state, rot.pats, rot.rect)
    for i in range(3):
        ok, how = MN._expand(run.fx, rot); time.sleep(1.0)
        print(f"expand try {i}: {ok} {how} popups={hin.popup_windows(run.hwnd)}")
        for n in run.ex._all_nodes():
            if n.expand_state == 1 and n.name: MN.collapse(n)
        run.fx.key("escape"); time.sleep(0.5)
        nodes = run.ex._all_nodes(); rot = next(n for n in nodes if fold(n.name) == "rotate" and n.ctype == "ButtonControl")
finally:
    run.finish()
