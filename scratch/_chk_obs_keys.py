import sqlite3
con = sqlite3.connect(r"d:\new_automation\data\app_behavior.db")
con.row_factory = sqlite3.Row
for t, col in [("bm_commands", "app_key"), ("bm_learn_state", "app_key"), ("bm_dialogs", "app_key"),
               ("bm_frontier", "app_key")]:
    try:
        rows = con.execute(f"SELECT {col} k, COUNT(*) n FROM {t} WHERE {col} LIKE '%obs%' GROUP BY {col}").fetchall()
        print(t, [dict(r) for r in rows])
    except Exception as e:
        print(t, "ERR", e)
try:
    rows = con.execute("SELECT app_key, status, substr(stats_json,1,160) s FROM bm_learn_state WHERE app_key LIKE '%obs%'").fetchall()
    for r in rows:
        print("learn_state:", dict(r))
except Exception as e:
    print("ls ERR", e)
import subprocess
print(subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe"], capture_output=True, text=True).stdout)
