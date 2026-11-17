"""debug_proc.py <app> "<goal substring>" -- run ONE guide procedure of the app once, with step-level raw results and a picture after every step."""
import sys, time, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, capture as CAP
from core_organs import headless_input as hin

key, sub = sys.argv[1], sys.argv[2].lower()
shots = "D:/new_automation/scratch/shots_%s_proc_" % key
run = AR.AppRun(AR.SPECS[key], vision=False, log=lambda s: print(s) if any(w in s for w in ("reveal", "catalog", "menus", "guide")) else None)
try:
    assert run.start()
    run.perceive()
    tasks = run.build_tasks()
    t = next((x for x in tasks if sub in x["goal"].lower()), None)
    if t is None:
        print("no such task; tasks:", [x["goal"][:40] for x in tasks])
        raise SystemExit
    rep = run.ex.plan_from_procedure(t["goal"], t["cite"], t["steps"])
    for st in rep.steps:
        print("  plan:", st.index, st.kind, st.verb, st.path, "safety", st.safety, "human" if st.need_human else "", st.routes, st.note[:100])
    # run step by step so a picture can be taken after each
    import copy
    orig_run_step = None
    steps = list(rep.steps)
    all_results = []
    for i, st in enumerate(steps):
        one = copy.copy(rep)
        one.steps = [st]
        run.ex._run(one, False, None, 2.5) if False else None
    run.ex._sticky = None
    with run.fx.focus_watch():
        run.ex._run(rep, False, None, 2.5)
    for r in rep.results:
        print("  result:", r.index, r.verb, r.status, r.route, r.effect, "|", r.summary[:300], "|", r.tried[:4])
    im = CAP.grab_composite(run.hwnd, hin.popup_windows(run.hwnd)[:6])
    if im is not None:
        im.image.save(shots + "end.png")
    print("stopped:", rep.stopped)
    run.reset_ui()
finally:
    run.finish()
