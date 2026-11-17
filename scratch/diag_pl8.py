import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.atlas.fixture import harness
from core_organs import background_window as bw
from core_organs.atlas import scanner as SC
from core_organs.professor import harvest as HV, probe as P
from core_organs.professor.capture import foreground_hwnd
from core_organs.professor.effectors import Effector

fg0 = foreground_hwnd()
h = harness.launch(minimized=True)
hwnd = h["hwnd"]
try:
    with bw.BackgroundSession(hwnd) as bg:
        nodes, waited, frame_only = SC.ensure_tree(hwnd, bg)
        print("fg after launch+park same:", foreground_hwnd() == fg0)
        cat = HV.harvest_tree(hwnd, "atlas_fixture", "Atlas Fixture")
        print("verbs", len(cat.verbs), "sources", cat.sources)
        for v in cat.verbs:
            print("  ", v.text_path, "| aid=", v.aid, "| role=", v.role, "| safety=", v.safety)
        fx = Effector(hwnd, allow_input=True, owned=True)
        eng = P.ProbeEngine(hwnd, fx, cat, "atlas_fixture", budget_s=150, max_probes=15, owned=True)
        hyps, skipped = eng.plan()
        print("plan:", [(x.verb, x.role, x.kind) for x in hyps])
        for x in hyps:
            rep = eng.run([x])
            r = rep.rules[0] if rep.rules else None
            fg = foreground_hwnd()
            print(f"{x.verb:16s} effect={r.effect if r else None} restored={r.restored if r else None} fg_same={fg == fg0} fg={fg} how={r.how if r else ''} unwind={r.unwind if r else ''}")
finally:
    harness.close(h)
