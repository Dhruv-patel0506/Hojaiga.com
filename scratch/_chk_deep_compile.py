import py_compile, sqlite3, sys
BASE = r"d:\new_automation\All codes\core_organs"
for f in ("organ_48_app_behavior_model.py", "scan_learner.py", "organ_50_layout_map.py", "organ_01_crewai_engine.py"):
    py_compile.compile(BASE + "\\" + f, doraise=True)
    print("compile OK:", f)
con = sqlite3.connect(r"d:\new_automation\data\app_behavior.db")
con.row_factory = sqlite3.Row
print("bm_dialogs exists:", bool(con.execute("SELECT 1 FROM sqlite_master WHERE name='bm_dialogs'").fetchone()))
try:
    rows = con.execute("SELECT app_key, source, COUNT(*) n FROM bm_dialogs GROUP BY app_key, source").fetchall()
    print("dialogs by app/source:", [dict(r) for r in rows])
except Exception as e:
    print("dialogs query failed:", e)
try:
    rows = con.execute("SELECT app_key, COUNT(*) n FROM bm_transitions GROUP BY app_key").fetchall()
    print("transitions by app:", [dict(r) for r in rows])
except Exception as e:
    print("transitions query failed:", e)
try:
    rows = con.execute("SELECT app_key, status, COUNT(*) n FROM bm_frontier GROUP BY app_key, status").fetchall()
    print("frontier by app/status:", [dict(r) for r in rows][:20])
except Exception as e:
    print("frontier query failed:", e)
