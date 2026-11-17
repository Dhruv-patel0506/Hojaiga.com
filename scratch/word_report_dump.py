import json, sys
d = json.load(open(r'd:\new_automation\data\professor\apprun\winword_20261012_160734\report.json', encoding='utf-8'))
g = d['phases']['guide']
print("guide keys:", list(g.keys()))
print(json.dumps({k: v for k, v in g.items() if k not in ("attempts", "tasks")}, indent=1)[:1500])
for key in ("attempts", "tasks", "runs", "procedures"):
    rows = g.get(key)
    if rows:
        print(f"--- {key} ({len(rows)}) ---")
        for a in rows[:2]:
            print(json.dumps(a, indent=1)[:3000])
print("pointer_course:", json.dumps(d['phases'].get('pointer_course'), indent=1)[:800])
