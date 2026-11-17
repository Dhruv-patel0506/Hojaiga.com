import sys, collections
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs.professor import workflows as WF
for app in sys.argv[1:]:
    d = WF.build(app, write=False)
    c = collections.Counter(s["note"] for w in d["workflows"] for s in w["steps"] if s["how"] == "outside")
    print(app, c.most_common())
    n = 0
    for w in d["workflows"]:
        for s in w["steps"]:
            if s["how"] == "outside" and n < int(sys.argv[-1] if sys.argv[-1].isdigit() else 40):
                n += 1; print("   ", s["note"][:30], "|", w["cite"][:50], "|", s["text"][:100])
