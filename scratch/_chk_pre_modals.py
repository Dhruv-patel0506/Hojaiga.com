import sqlite3, json
con = sqlite3.connect(r"d:\new_automation\data\app_behavior.db")
con.row_factory = sqlite3.Row
r = con.execute("SELECT status, stats_json FROM bm_learn_state WHERE app_key='obs studio'").fetchone()
s = json.loads((r["stats_json"] if r else "") or "{}")
print("status:", r["status"] if r else None)
print("pre_modals:", s.get("pre_modals"))
print("pre_modals_closed:", s.get("pre_modals_closed"))
d = con.execute("SELECT title, via, source, substr(controls_json,1,80) c FROM bm_dialogs"
                " WHERE app_key='obs studio' AND via LIKE '%already open%'").fetchall()
print("dialogs captured by hygiene:", len(d))
for x in d:
    print("  ", dict(x))
