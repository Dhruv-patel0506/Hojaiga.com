import sys
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import harvest as HV
from core_organs.professor.knowledge import guide_card as GCARD, guide_steps as GS
key = sys.argv[1]
cat = HV.Catalog.load(key)
print(key, "catalog verbs:", len(cat.verbs))
for v in cat.verbs:
    print("   V", (" > ".join(v.path) + " > " if v.path else "") + v.label, "|", v.role, "|", v.shortcut, "|", v.safety, "|", ",".join(v.sources))
for p in GCARD.procedures(key):
    g = GS.ground(p["steps"], cat)
    print("PROC", p["goal"][:60], "|", [(x.step.action, x.step.target[:25], x.how, round(x.conf, 2)) for x in g][:8])
