import sys, time, ctypes
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, menus as MN
from core_organs.professor.schema import fold
from core_organs import headless_input as hin, fast_uia

u = ctypes.WinDLL("user32")
run = AR.AppRun(AR.SPECS["chrome"], vision=False, log=lambda s: None)
try:
    assert run.start()
    from core_organs.professor.effectors import Effector
    run.fx = Effector(run.hwnd, allow_input=True, owned=True)
    # no perceive(): just the tree
    nodes = fast_uia.snapshot(run.hwnd, timeout_ms=6000) or []
    print("tree", len(nodes))
    ops = [n for n in nodes if fold(n.name) == fold(sys.argv[1] if len(sys.argv) > 1 else "You") and n.ctype == "ButtonControl"]
    print("openers:", [(n.ctype, n.name, n.pats, n.expand_state, n.rect) for n in ops][:4])
    base_w = set(hin.process_windows(run.hwnd, include_hidden=True))
    base_pop = set(hin.popup_windows(run.hwnd))
    n = ops[0]
    ok, how = MN._expand(run.fx, n)
    print("expand", ok, how)
    for i in range(6):
        time.sleep(0.5)
        ws = hin.process_windows(run.hwnd, include_hidden=True)
        new = [w for w in ws if w not in base_w]
        print(f"t={0.5*(i+1)}: new process windows={[(w, hin._class_name(w), bool(u.IsWindowVisible(w)), hex(u.GetWindowLongW(w, -16) & 0xffffffff), hex(u.GetWindowLongW(w, -20) & 0xffffffff), u.GetWindow(w, 4)) for w in new]} popup_windows={hin.popup_windows(run.hwnd)} main={run.hwnd}")
        for w in new:
            ns = fast_uia.snapshot(w, timeout_ms=2000) or []
            print("    nodes in", w, len(ns), [x.name for x in ns if x.name][:12])
        if new:
            break
    run.fx.key("escape")
finally:
    run.finish()
