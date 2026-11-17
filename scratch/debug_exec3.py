import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR
from core_organs.professor.schema import fold
from core_organs.professor.effectors import _fg
from core_organs import headless_input as hin
key, label = sys.argv[1], sys.argv[2]
run = AR.AppRun(AR.SPECS[key], vision=False, log=lambda s: None)
try:
    assert run.start()
    run.perceive()
    v = [v for v in run.cat.verbs if fold(v.label) == fold(label)][0]
    print("fg before", _fg(), "target pid", hin.window_pid(run.hwnd), "fg pid", hin.window_pid(_fg()))
    with run.fx.focus_watch():
        ok = run.ex._open_path(v)
        print("open_path", ok, "fg pid", hin.window_pid(_fg()), "returns", run.fx.focus_returns)
        n = run.ex._live_node(v)
        print("live after (with watch):", None if n is None else (n.name, n.rect))
        print("popups", hin.popup_windows(run.hwnd))
    run.fx.key("escape")
finally:
    run.finish()
