import sqlite3
con = sqlite3.connect(r"d:\new_automation\data\app_behavior.db")
con.row_factory = sqlite3.Row
K = "obs studio"
r = con.execute("SELECT status, substr(stats_json,1,500) s FROM bm_learn_state WHERE app_key=?", (K,)).fetchone()
print("learn_state:", dict(r) if r else "NO ROW")
f = con.execute("SELECT COUNT(*) n, SUM(status='explored') e FROM bm_frontier WHERE app_key=?", (K,)).fetchone()
print("frontier:", dict(f))
d = con.execute("SELECT COUNT(*) n FROM bm_dialogs WHERE app_key=? AND source LIKE 'live%'", (K,)).fetchone()
print("live dialogs:", dict(d))
t = con.execute("SELECT COUNT(*) n FROM bm_transitions WHERE app_key=?", (K,)).fetchone()
print("transitions:", dict(t))
c = con.execute("SELECT COUNT(*) n, SUM(source='learned') l FROM bm_commands WHERE app_key=?", (K,)).fetchone()
print("commands:", dict(c))
p = con.execute("SELECT COUNT(*) n FROM bm_templates WHERE app_key=? AND seed_note LIKE 'composed%'", (K,)).fetchone()
print("composed recipes:", dict(p))
