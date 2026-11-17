import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, menus as MN
from core_organs.professor.schema import fold
from core_organs import headless_input as hin, fast_uia
key, label = sys.argv[1], sys.argv[2]
from core_organs.professor import effectors as E
if len(sys.argv) > 3 and sys.argv[3] == "noclose":
    E.Effector.close_popups = lambda self, before: 0
run = AR.AppRun(AR.SPECS[key], vision=False, log=lambda s: None)
try:
    assert run.start()
    run.perceive()
    ex = run.ex
    for rnd in range(3):
        nodes = ex._all_nodes()
        cands = [n for n in nodes if fold(n.name) == "file" and n.ctype == "MenuItemControl"]
        n = cands[0]
        print(f"round {rnd}: File node expand_state={n.expand_state} rect={n.rect} enabled={n.enabled} pats={n.pats}")
        ok, how = MN._expand(run.fx, n)
        print("   expand ->", ok, how)
        for i in range(8):
            time.sleep(0.4)
            ws = hin.process_windows(run.hwnd, include_hidden=True)
            vis = hin.popup_windows(run.hwnd)
            hit = []
            for w in ws:
                if w == run.hwnd:
                    continue
                ns = fast_uia.snapshot(w, timeout_ms=1500) or []
                if any("page setup" in fold(x.name) for x in ns):
                    hit.append(w)
            print(f"   t={0.4*(i+1):.1f}s visible popups={vis} windows-with-'Page setup'={hit}")
            if hit:
                break
        run.fx.key("escape")
        time.sleep(1.0)
finally:
    run.finish()
