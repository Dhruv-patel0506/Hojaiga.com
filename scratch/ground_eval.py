import sys, json, collections
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs.professor import workflows as WF
from core_organs.professor.knowledge.guide_steps import GROUNDED_HOW
apps = sys.argv[1:] or ["notepad", "mspaint", "winword", "powerpnt"]
show = "--show" in apps
apps = [a for a in apps if not a.startswith("--")]
for app in apps:
    d = WF.build(app, write=False)
    hows = collections.Counter(s["how"] for w in d["workflows"] for s in w["steps"])
    tot = sum(hows.values())
    out = sum(v for k, v in hows.items() if k == "outside")
    g = sum(v for k, v in hows.items() if k in GROUNDED_HOW)
    app_ = tot - out
    print(f"{app:10s} steps {tot:4d}  grounded {g:4d} raw {g/max(1,tot):.1%}  applicable {app_:4d} -> {g/max(1,app_):.1%}  {dict(hows)}")
    if show:
        for w in d["workflows"]:
            for s in w["steps"]:
                if s["how"] not in GROUNDED_HOW and s["how"] != "outside":
                    print("    ", s["how"], "|", s["action"], "|", s["target"][:30], "|", s["path"], "|", s["text"][:120])
