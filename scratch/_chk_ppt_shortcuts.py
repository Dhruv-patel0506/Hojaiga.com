import sqlite3
import sys
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import organ_48_app_behavior_model as bm
KEY = bm._app_key("powerpoint")

db = r"D:\new_automation\data\app_behavior.db"
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT name, help, accel FROM bm_layout WHERE app_key=? AND help LIKE '%Ctrl%'",
    (KEY,)).fetchall()
print(f"controls whose tooltip mentions Ctrl: {len(rows)}")
for r in rows[:15]:
    print(f"  name={r['name']!r} accel={r['accel']!r} help={r['help'][:90]!r}")
n_accel = con.execute(
    "SELECT COUNT(*) c FROM bm_layout WHERE app_key=? AND accel IS NOT NULL AND accel<>''",
    (KEY,)).fetchone()["c"]
print("rows with non-empty accel column:", n_accel)
con.close()
