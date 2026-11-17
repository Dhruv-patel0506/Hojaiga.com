import sys, json, time
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.atlas.scanner import Atlas
app, tier, budget = sys.argv[1], sys.argv[2], float(sys.argv[3])
t = time.time()
out = Atlas(log=print).learn(app, tier=tier, budget_s=budget)
json.dump(out, open(rf"D:\new_automation\scratch\learn_{app}.json", "w"), default=str, indent=1)
print("DONE", round(time.time() - t, 1))
for n, p in out["phases"].items():
    print("==", n, json.dumps(p, default=str)[:1500])
print({k: out.get(k) for k in ("exe", "claims_total", "commands", "dialogs", "transitions", "regions", "gestures", "errors")})
print(out.get("claims_by_kind"))
