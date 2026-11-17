import sys, time, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR
from core_organs.professor.schema import fold

key = sys.argv[1]
label = sys.argv[2]
run = AR.AppRun(AR.SPECS[key], vision=False, log=print)
try:
    assert run.start()
    run.perceive()
    vs = [v for v in run.cat.verbs if fold(v.label) == fold(label)]
    print("verbs", [(v.path, v.label, v.role, v.aid, v.shortcut, v.safety) for v in vs])
    v = vs[0]
    print("live node before:", run._dbg if hasattr(run, "_dbg") else run.ex._live_node(v))
    print("open_path ->", run.ex._open_path(v))
    n = run.ex._live_node(v)
    print("live node after:", None if n is None else (n.ctype, n.name, n.rect, n.offscreen))
    rs = run.ex.routes_for(v)
    print("routes", [r.label() for r in rs])
    run.fx.key("escape")
finally:
    run.finish()
