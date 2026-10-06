import sys, os, json, tempfile, uuid, time
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import organ_48_app_behavior_model as bm, organ_63_app_mastery as am
app = sys.argv[1]; budget = float(sys.argv[2]) if len(sys.argv) > 2 else 40
mdl = bm.BehaviorModel(os.path.join(tempfile.gettempdir(), f"hj_pm_{uuid.uuid4().hex[:6]}.db"))
t0 = time.time()
out = am.master(app, model=mdl, budget_s=budget, runs=1)
print("elapsed", round(time.time()-t0,1))
for r in out["runs"]:
    print(json.dumps({k: v for k, v in r.items() if k in ("error","launch","scan","note","app_hung","phases","aborted","reason")}, default=str)[:1800])
print("known", json.dumps(out.get("known"), default=str)[:500])
