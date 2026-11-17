import sys, time, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, capture as CAP
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
    def info(tag):
        ns = [n for n in run.ex._all_nodes() if fold(n.name) == "rotate"]
        print(tag, [(n.ctype, n.enabled, n.offscreen, n.pats, n.expand_state, n.rect) for n in ns], "popups", hin.popup_windows(run.hwnd), "windows", hin.process_windows(run.hwnd, include_hidden=False))
    info("after task")
    n = next(n for n in run.ex._all_nodes() if fold(n.name) == "rotate" and n.ctype == "ButtonControl")
    ok, how = run.fx.node(n)
    print("invoke ->", ok, how)
    for i in range(4):
        time.sleep(0.5)
        info(f"t={0.5*(i+1)}")
    fr = CAP.grab_composite(run.hwnd, hin.popup_windows(run.hwnd)[:6]); fr.image.save("D:/new_automation/scratch/shots_seq2.png")
finally:
    run.finish()
