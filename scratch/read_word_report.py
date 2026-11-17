import io, json, os, re, sys
p = r'D:\new_automation\data\professor\apprun\winword_20261012_204337'
d = json.load(io.open(os.path.join(p, "report.json"), encoding="utf-8"))
tasks = d.get("tasks") or []
print("TASKS", len(tasks))
for r in tasks:
    print("\n=== TASK:", str(r.get("goal") or r.get("title") or r.get("procedure"))[:90], "|", r.get("result") or r.get("outcome"))
    print("  keys:", list(r.keys()))
    steps = r.get("steps") or r.get("plan") or []
    for st in steps:
        if isinstance(st, dict):
            print("  step:", str(st.get("verb") or st.get("label") or st.get("text"))[:38], "|", st.get("status"), "|", str(st.get("route"))[:26], "|", str(st.get("summary"))[:130])
    for st in (r.get("step_results") or []):
        print("  res:", str(st)[:180])
print("\nLEDGER COUNTS:", d.get("ledger_counts"))
print("POINTER:", json.dumps(d.get("pointer"))[:300])
print("DIALOGS:", json.dumps(d.get("dialogs"))[:300])
