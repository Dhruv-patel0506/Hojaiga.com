import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, menus as MN
from core_organs.professor.schema import fold
from core_organs import headless_input as hin
key, label = sys.argv[1], sys.argv[2]
run = AR.AppRun(AR.SPECS[key], vision=False, log=lambda s: None)
try:
    assert run.start()
    run.perceive()
    ex = run.ex
    v = [v for v in run.cat.verbs if fold(v.label) == fold(label)][0]
    orig = ex._live_node
    def traced(vv):
        n = orig(vv)
        nodes = ex._all_nodes()
        print("   _live_node ->", None if n is None else (n.ctype, n.rect), "| nodes", len(nodes), "| popups", hin.popup_windows(run.hwnd), "| name-matches", [(x.ctype, x.rect, x.offscreen) for x in nodes if fold(x.name) == fold(vv.label)])
        return n
    ex._live_node = traced
    r = ex.routes_for(v)[0]
    print("deliver:")
    res = ex._deliver(v, r)
    print("->", res)
    time.sleep(1.0)
    print("after 1s popups", hin.popup_windows(run.hwnd))
    run.fx.key("escape")
finally:
    run.finish()
