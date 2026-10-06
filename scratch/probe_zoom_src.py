import sys, os, tempfile, uuid, collections, json
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import static_knowledge as sk, organ_48_app_behavior_model as bm, knowledge_store as ks
exe = sys.argv[1]
d = sk.harvest(exe)
print({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in d.items() if k in ("ok","commands","menus","preload","strings","file_types")})
mdl = bm.BehaviorModel(os.path.join(tempfile.gettempdir(), f"hj_z_{uuid.uuid4().hex[:6]}.db"))
ks.ensure(mdl)
print(sk.ingest(mdl, "z", d))
rows = mdl._conn.execute("SELECT origin, source, COUNT(*) c FROM bm_commands WHERE app_key=? GROUP BY origin, source ORDER BY c DESC LIMIT 8", (bm._app_key("z"),)).fetchall()
print([tuple(r) for r in rows])
ex = mdl._conn.execute("SELECT name, origin FROM bm_commands WHERE app_key=? ORDER BY RANDOM() LIMIT 8", (bm._app_key("z"),)).fetchall()
print([tuple(r) for r in ex])
pre = d.get("preload") or {}
print("preload keys", list(pre)[:6] if isinstance(pre, dict) else type(pre), {k: (v if not isinstance(v,(list,dict)) else len(v)) for k,v in (pre.items() if isinstance(pre, dict) else [])})
