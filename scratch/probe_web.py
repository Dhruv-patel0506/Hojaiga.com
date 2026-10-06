import sys, os, json, tempfile, uuid, time
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import organ_48_app_behavior_model as bm, universal_scan as us, command_registry as cr, knowledge_store as ks
for url in sys.argv[1:]:
    mdl = bm.BehaviorModel(os.path.join(tempfile.gettempdir(), f"hj_web_{uuid.uuid4().hex[:6]}.db"))
    ks.ensure(mdl)
    t0 = time.time()
    rep = us.scan(url, mdl, force=True)
    key = rep.get("app_key") or ("web:" + url.split("//")[-1].split("/")[0])
    reg = cr.build(mdl, key)
    d = cr.dossier(mdl, key)
    st = rep.get("stats") or rep.get("scan") or {}
    out = {"url": url, "s": round(time.time() - t0, 1), "error": rep.get("error"), "keys": [k for k in rep if k not in ("phases",)][:14],
           "phases": rep.get("phases"), "commands": len(reg), "by_kind": d["commands"]["by_kind"], "quick": {k: v["command"] for k, v in d.get("quick_answers", {}).items()},
           "skipped": (rep.get("stats") or {}).get("skipped") if isinstance(rep.get("stats"), dict) else rep.get("skipped"), "nav": rep.get("navigation")}
    print(json.dumps(out, default=str)[:1800], flush=True)
