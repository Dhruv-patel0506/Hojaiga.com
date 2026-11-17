"""debug_step.py <app> "<goal text or verb>" [--path "File>Open"] -- perceive the app, plan the goal through the guide-free rules, run it, print every route's raw delta + save before/after pictures."""
import sys, time, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, capture as CAP, probe as PB
from core_organs.professor.schema import fold
from core_organs import headless_input as hin

key = sys.argv[1]
label = sys.argv[2]
shots = "D:/new_automation/scratch/shots_%s_step_" % key
run = AR.AppRun(AR.SPECS[key], vision=False, log=lambda s: print(s) if "reveal" in s or "catalog" in s else None)
try:
    assert run.start()
    run.perceive()
    ex = run.ex
    vs = [v for v in run.cat.verbs if fold(v.label) == fold(label)]
    print("verbs:", [(v.path, v.label, v.role, v.leads_to, v.aid) for v in vs])
    v = vs[0]
    live = ex._live_node(v)
    print("live:", None if live is None else (live.ctype, live.name, live.pats, live.expand_state, live.toggle_state, live.rect))
    s0 = PB.snapshot(run.hwnd)
    im = CAP.grab_composite(run.hwnd, hin.popup_windows(run.hwnd)[:6])
    if im is not None:
        im.image.save(shots + "0.png")
    with run.fx.focus_watch():
        for r in ex.routes_for(v):
            s0 = PB.snapshot(run.hwnd)
            ok, how = ex._deliver(v, r)
            time.sleep(1.2)
            s1 = PB.snapshot(run.hwnd)
            d = PB.delta(s0, s1)
            print(f"route {r.label()}: ok={ok} how={how} -> effect={d.effect()} | {d.summary()[:300]}")
            print("    windows before/after", s0.windows, s1.windows, "popups", hin.popup_windows(run.hwnd))
            im = CAP.grab_composite(run.hwnd, hin.popup_windows(run.hwnd)[:6])
            if im is not None:
                im.image.save(shots + f"1_{r.kind}.png")
            if d.effect() != "no_effect":
                break
        run.reset_ui()
finally:
    run.finish()
