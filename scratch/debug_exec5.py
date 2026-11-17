import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR
from core_organs.professor.schema import fold
from core_organs import headless_input as hin
key, label = sys.argv[1], sys.argv[2]
run = AR.AppRun(AR.SPECS[key], vision=False, log=lambda s: None)
try:
    assert run.start()
    run.perceive()
    ex = run.ex
    v = [v for v in run.cat.verbs if fold(v.label) == fold(label)][0]
    for attempt, hold in enumerate((False, True, False, True)):
        t0 = time.time()
        if hold:
            with run.fx.holding():
                ok = ex._open_path(v)
                n = ex._live_node(v)
        else:
            ok = ex._open_path(v)
            n = ex._live_node(v)
        print(f"attempt {attempt} hold={hold}: open_path={ok} live={'yes' if n else 'NO'} popups={hin.popup_windows(run.hwnd)} {time.time()-t0:.1f}s")
        run.fx.key("escape")
        time.sleep(0.8)
        print("   after escape: popups", hin.popup_windows(run.hwnd))
finally:
    run.finish()
