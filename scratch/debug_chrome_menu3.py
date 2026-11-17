import sys, time, ctypes
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, menus as MN
from core_organs.professor.effectors import Effector
from core_organs.professor.schema import fold
from core_organs import fast_uia, headless_input as hin
u = ctypes.WinDLL("user32")
name, mode = sys.argv[1], sys.argv[2]
run = AR.AppRun(AR.SPECS["chrome"], vision=False, log=lambda s: None)
try:
    assert run.start()
    run.fx = Effector(run.hwnd, allow_input=True, owned=True)
    h = run.hwnd
    if mode == "wm_activate":
        u.SendMessageW(h, 0x0086, 1, 0)       # WM_NCACTIVATE TRUE
        u.SendMessageW(h, 0x0006, 1, 0)       # WM_ACTIVATE WA_ACTIVE
        u.SendMessageW(h, 0x0007, 0, 0)       # WM_SETFOCUS
    elif mode == "foreground":
        u.ShowWindow(h, 4)
        u.SetForegroundWindow(h)
    time.sleep(0.5)
    nodes = fast_uia.snapshot(h, timeout_ms=6000) or []
    base = {(n.aid, n.name, n.ctype) for n in nodes}
    n = next(x for x in nodes if fold(x.name) == fold(name) and x.ctype == "ButtonControl" and "expand" in x.pats)
    ok, how = MN._expand(run.fx, n)
    print(mode, "expand", ok, how)
    for i in range(4):
        time.sleep(0.6)
        now = fast_uia.snapshot(h, timeout_ms=6000) or []
        new = [x for x in now if (x.aid, x.name, x.ctype) not in base and x.name]
        ws = hin.process_windows(h, include_hidden=True)
        print(f"t={0.6*(i+1):.1f}s main-tree new {len(new)}: {[(x.ctype[:-7], x.name[:24]) for x in new][:8]} | process windows {[(w, hin._class_name(w)) for w in ws][:8]}")
    run.fx.key("escape")
finally:
    run.finish()
