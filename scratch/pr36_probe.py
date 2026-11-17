import sys
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs import si_tests_professor as S
from core_organs.professor.knowledge import guide_steps as GS

cat = S._p2_catalog()
steps = GS.parse_steps("1. Click **Add Marker** on the toolbar.\n2. Choose **View** > **Zoom In**.\n3. Press **Ctrl**+**M**.\n4. Type \"Chapter one\" in the **Title** field.\n5. Tick the \"Visible\" checkbox.\n6. Select File > Export > PDF.", "demo")
g = GS.ground(steps, cat)
by = {s.step.n: s for s in g}
for n, s in sorted(by.items()):
    print(n, s.how, s.verb.label if s.verb else None, repr(s.note)[:80])
cu = GS.ground_step(GS.parse_line("Press **Ctrl**+**K**.", 1), cat)
print("chord_unknown:", cu.how, repr(cu.note), cu.verb.label if cu.verb else None)
print("catalog verbs:", [(v.label, v.shortcut) for v in cat.verbs])
