import sys, os, glob, json
sys.path.extend([r"D:\new_automation", r"D:\new_automation\All codes"])
from core_organs.professor import scorecard as SC

apps = ["winword", "powerpnt", "mspaint", "notepad", "calculator", "systemsettings", "blender", "obs64", "code"]
for app in apps:
    p = SC.latest_report(app)
    if not p:
        print(f"=== {app}: NO REPORT ===")
        continue
    sc = SC.score(p)
    rep_name = os.path.basename(os.path.dirname(p))
    print(f"\n=======================================================")
    print(f"=== {app.upper()} ({rep_name}) ===")
    print(f"=== {sc['passed']}/{sc['total']} passed, {sc['measured']} measured ===")
    for r in sc["rows"]:
        v = "  n/a " if r["percent"] is None else f"{r['percent']:5.1f}%"
        st = "PASS" if r["passed"] else ("----" if r["percent"] is None else "FAIL")
        print(f"  {st:4s}  {r['id']:4s} {v}  {r['checkpoint']:35s} {r['detail'][:80]}")
