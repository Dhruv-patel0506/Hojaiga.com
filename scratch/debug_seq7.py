import sys, time, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, probe as PB, capture as CAP
from core_organs import headless_input as hin
run = AR.AppRun(AR.SPECS["mspaint"], vision=False, max_attempts=1, log=lambda s: None)
try:
    assert run.start()
    run.perceive()
    tasks = run.build_tasks()
    for t in tasks[:6]:
        tr = run.run_task(t); run.tasks.append(tr)
        print("  ", t["goal"][:40], tr.final)
    orig = run.ex._settle
    def traced(before, max_s, expect_change=False):
        out = orig(before, max_s, expect_change)
        d = PB.delta(before, out)
        print(f"   settle(expect={expect_change}): windows {before.windows} -> {out.windows}; sig {before.sig} -> {out.sig}; effect {d.effect()}; popups now {hin.popup_windows(run.hwnd)}")
        return out
    run.ex._settle = traced
    od = run.ex._deliver
    def td(v, r):
        res = od(v, r)
        print(f"   deliver {r.label()} -> {res}; popups right after {hin.popup_windows(run.hwnd)}")
        return res
    run.ex._deliver = td
    live = [n for n in run.ex._all_nodes() if n.name and n.name.lower() == "rotate"]
    print("rotate nodes before:", [(n.ctype, n.enabled, n.expand_state, n.rect) for n in live], "popups:", hin.popup_windows(run.hwnd), "fg:", hin.window_pid(CAP.foreground_hwnd()), "target pid:", hin.window_pid(run.hwnd))
    tr = run.run_task(tasks[6])
    print("task7:", tr.final)
finally:
    run.finish()
