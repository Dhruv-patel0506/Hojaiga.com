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
    v = [v for v in run.cat.verbs if fold(v.label) == fold(label)][0]
    print("popups before", hin.popup_windows(run.hwnd))
    nodes = run.ex._all_nodes()
    cand = [n for n in nodes if fold(n.name) == fold(v.path[0]) and not n.offscreen and n.enabled and n.rect[2] > n.rect[0]]
    print("cands", [(n.ctype, n.rect) for n in cand])
    ok, how = MN._expand(run.fx, cand[0])
    print("expand", ok, how)
    for i in range(8):
        time.sleep(0.4)
        ns = run.ex._all_nodes()
        print(i, "popups", hin.popup_windows(run.hwnd), "nodes", len(ns), "match", [(n.ctype, n.rect, n.offscreen) for n in ns if fold(n.name) == fold(v.label)])
    run.fx.key("escape")
finally:
    run.finish()
