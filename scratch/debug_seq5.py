import sys, time, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, probe as PB
from core_organs import headless_input as hin
run = AR.AppRun(AR.SPECS["mspaint"], vision=False, max_attempts=1, log=lambda s: None)
try:
    assert run.start()
    run.perceive()
    tasks = run.build_tasks()
    print("task1:", run.run_task(next(x for x in tasks if (sys.argv[1] if len(sys.argv) > 1 else "create a new image") in x["goal"].lower())).final)
    orig = run.ex._settle
    def traced(before, max_s, expect_change=False):
        out = orig(before, max_s, expect_change)
        d = PB.delta(before, out)
        print(f"   settle(expect_change={expect_change}, max_s={max_s}): before windows={before.windows} names={len(before.names)} texts={len(before.texts)} sig={before.sig} | after windows={out.windows} names={len(out.names)} sig={out.sig} -> {d.effect()}")
        print("      popups now:", hin.popup_windows(run.hwnd))
        return out
    run.ex._settle = traced
    orig_deliver = run.ex._deliver
    def tdeliver(v, r):
        res = orig_deliver(v, r)
        print(f"   deliver {r.label()} -> {res}; popups right after: {hin.popup_windows(run.hwnd)}")
        return res
    run.ex._deliver = tdeliver
    t = next(x for x in tasks if "rotate and flip" in x["goal"].lower())
    tr = run.run_task(t)
    print("task2:", tr.final)
finally:
    run.finish()
