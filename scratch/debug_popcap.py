import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, capture as CAP, menus as MN
from core_organs.professor.schema import fold
from core_organs import headless_input as hin
run = AR.AppRun(AR.SPECS["notepad"], vision=False, echo=False)
try:
    assert run.start()
    run.perceive_min = True
    from core_organs.professor.effectors import Effector
    run.fx = Effector(run.hwnd, allow_input=True, owned=True)
    from core_organs import fast_uia
    n = next(x for x in fast_uia.snapshot(run.hwnd, timeout_ms=5000) if fold(x.name) == "file" and x.ctype == "MenuItemControl")
    print("expand", MN._expand(run.fx, n)); time.sleep(1.2)
    pops = hin.popup_windows(run.hwnd)
    print("popups", pops, [(p, hin._class_name(p), CAP.window_info(p).box) for p in pops])
    for p in pops:
        a = CAP._printwindow(p); b = CAP.wgc_grab(p)
        print(p, "printwindow", None if a is None else ("blank" if CAP._is_blank(a) else a.size), "| wgc", None if b is None else ("blank" if CAP._is_blank(b) else b.size))
        if b is not None: b.save(f"D:/new_automation/scratch/pop_wgc_{p}.png")
        if a is not None: a.save(f"D:/new_automation/scratch/pop_pw_{p}.png")
    # the main window with and without popup via WGC of the main window
    m = CAP.wgc_grab(run.hwnd); print("main wgc", None if m is None else m.size)
finally:
    run.finish()
