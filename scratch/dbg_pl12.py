import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes", "D:/new_automation/All codes/core_organs"]
from core_organs.atlas.fixture import harness
from core_organs import background_window as bw
from core_organs.atlas import scanner as SC
from core_organs.professor import explore as EX, harvest as HV
from core_organs.professor.effectors import Effector
from core_organs.professor import probe as P

h = harness.launch(minimized=True)
hwnd = h["hwnd"]
try:
    with bw.BackgroundSession(hwnd) as bg:
        nodes, waited, fo = SC.ensure_tree(hwnd, bg)
        s0 = harness.read_state_text(hwnd)
        cat = HV.harvest_tree(hwnd, "atlas_fixture", "Atlas Fixture")
        fx = Effector(hwnd, allow_input=True, owned=True)
        ex = EX.Explorer(hwnd, fx, cat, "atlas_fixture", None, owned=True, max_actions=3, budget_s=150.0)
        hyps, sk = ex.engine.plan(k=12)
        pool = [x for x in hyps if x.kind == "state" and x.role in ("button", "menuitem", "checkbox", "splitbutton")][:3]
        print("pool", [(x.verb, x.role) for x in pool])
        a = next(x for x in pool if x.verb == "Add Marker")
        v = next(x for x in pool if x.verb == "Visible")
        base = P.snapshot(hwnd)
        print("base sig", base.sig, "windows", base.windows)
        for first, second in ((a, v), (v, a)):
            print("==", first.verb, "then", second.verb)
            r1 = ex._apply(first)
            print("  after first:", r1[1].sig if r1 else None, "| state:", harness.read_state_text(hwnd)[:60])
            r2 = ex._apply(second)
            print("  after second:", r2[1].sig if r2 else None, "| state:", harness.read_state_text(hwnd)[:60])
            for hh, rr in ((second, r2), (first, r1)):
                if rr is None:
                    continue
                ok = ex._undo(hh, rr)
                cur = P.snapshot(hwnd)
                print("  undo", hh.verb, "ok" if ok else "NOT OK", "->", cur.sig, "| state:", harness.read_state_text(hwnd)[:60])
                if not ok:
                    print("     diff vs its own before:", P.diff_state(rr[0], cur, 1.0))
            cur = P.snapshot(hwnd)
            print("  vs base:", P.diff_state(base, cur, 1.0))
finally:
    harness.close(h)
