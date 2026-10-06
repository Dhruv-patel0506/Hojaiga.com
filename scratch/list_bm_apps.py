import sys
sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation\All codes\core_organs")
from core_organs import organ_48_app_behavior_model as bm
m = bm.get_model()
tables = [r[0] for r in m._conn.execute("SELECT name FROM sqlite_master WHERE type = ?", ("table",)).fetchall()]
print("tables:", tables)
for t in tables:
    if "command" in t or "cmd" in t:
        rows = m._conn.execute(f"SELECT app_key, COUNT(*) c FROM {t} GROUP BY app_key ORDER BY c DESC").fetchall()
        print(t, "->", [(r[0], r[1]) for r in rows][:40])
