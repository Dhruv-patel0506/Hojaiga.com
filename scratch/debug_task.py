import sys, time, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, capture as CAP
from core_organs import headless_input as hin

key = sys.argv[1]
idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
shots = "D:/new_automation/scratch/shots_%s_" % key
run = AR.AppRun(AR.SPECS[key], vision=False, log=print)


def shot(tag):
    img = CAP._printwindow(run.hwnd)
    if img is not None:
        img.save(shots + tag + ".png")
    wins = hin.process_windows(run.hwnd, include_hidden=True)
    print("   windows of the process:", [(w, hin._class_name(w)) for w in wins][:8], "popups", hin.popup_windows(run.hwnd))


try:
    assert run.start()
    run.perceive()
    tasks = run.build_tasks()
    print("tasks:", [(t["goal"][:50], len(t["steps"]), t["grounded"]) for t in tasks])
    t = tasks[idx]
    shot("0_before")
    rep = run.ex.plan_from_procedure(t["goal"], t["cite"], t["steps"])
    for st in rep.steps:
        print("  plan step:", st.index, st.kind, st.verb, st.path, st.safety, st.need_human, st.routes, st.note[:80])
    with run.fx.focus_watch():
        run.ex._run(rep, False, None, 2.5)
    for r in rep.results:
        print("  result:", r.index, r.verb, r.status, r.route, r.effect, r.summary[:120], r.tried[:3])
    shot("1_after")
finally:
    run.finish()
