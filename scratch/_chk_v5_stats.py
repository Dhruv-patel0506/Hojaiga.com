import sqlite3, json
con = sqlite3.connect(r"d:\new_automation\data\app_behavior.db")
con.row_factory = sqlite3.Row
r = con.execute("SELECT status, stats_json FROM bm_learn_state WHERE app_key='obs studio'").fetchone()
s = json.loads((r["stats_json"] if r else "") or "{}")
print("status:", r["status"])
print(json.dumps(s, indent=1, default=str)[:2000])
f = con.execute("SELECT kind,label,path,status,substr(result_json,1,120) rj FROM bm_frontier WHERE app_key='obs studio'").fetchall()
for x in f:
    print("FRONTIER:", dict(x))
