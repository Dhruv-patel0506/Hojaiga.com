import sqlite3
con = sqlite3.connect(r"d:\new_automation\data\app_behavior.db")
con.row_factory = sqlite3.Row
rows = con.execute("SELECT app_key, COUNT(*) n, SUM(via LIKE 'dropdown:%') dd, SUM(via LIKE 'ribbon%') rb,"
                   " MAX(ts) latest FROM bm_layout GROUP BY app_key ORDER BY latest DESC").fetchall()
for r in rows:
    print(dict(r))
print("--- distinct via prefixes for powerpoint-ish keys ---")
for r in con.execute("SELECT DISTINCT substr(via,1,24) v, COUNT(*) n FROM bm_layout"
                     " WHERE app_key LIKE '%power%' OR app_key LIKE '%ppt%' GROUP BY v ORDER BY n DESC LIMIT 20").fetchall():
    print(dict(r))
