import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, menus as MN
from core_organs.professor.effectors import Effector
from core_organs.professor.schema import fold
from core_organs import fast_uia
name = sys.argv[1]
run = AR.AppRun(AR.SPECS["chrome"], vision=False, log=lambda s: None)
try:
    assert run.start()
    run.fx = Effector(run.hwnd, allow_input=True, owned=True)
    print("lay_out ->", run.bg.lay_out(settle_s=1.0), "mode", run.bg.mode)
    nodes = fast_uia.snapshot(run.hwnd, timeout_ms=6000) or []
    base = {(n.aid, n.name, n.ctype) for n in nodes}
    n = next(x for x in nodes if fold(x.name) == fold(name) and x.ctype == "ButtonControl" and "expand" in x.pats)
    ok, how = MN._expand(run.fx, n)
    print("expand", ok, how)
    for i in range(5):
        time.sleep(0.6)
        now = fast_uia.snapshot(run.hwnd, timeout_ms=6000) or []
        new = [x for x in now if (x.aid, x.name, x.ctype) not in base and x.name]
        print(f"t={0.6*(i+1):.1f}s main-tree nodes {len(now)} new named {len(new)}:", [(x.ctype[:-7], x.name[:28], x.rect) for x in new][:10])
    run.fx.key("escape")
finally:
    run.finish()
