import sqlite3, json
con = sqlite3.connect(r"d:\new_automation\data\app_behavior.db")
con.row_factory = sqlite3.Row
KEY = "obs studio"
r = con.execute("SELECT COUNT(*) tot, SUM(enabled) en, SUM(CASE WHEN patterns LIKE '%invoke%' THEN 1 ELSE 0 END) inv,"
                " SUM(CASE WHEN patterns LIKE '%expand%' THEN 1 ELSE 0 END) exp,"
                " SUM(CASE WHEN patterns LIKE '%toggle%' THEN 1 ELSE 0 END) tog,"
                " SUM(CASE WHEN patterns LIKE '%select%' THEN 1 ELSE 0 END) sel"
                " FROM bm_layout WHERE app_key=?", (KEY,)).fetchone()
print("bm_layout patterns:", dict(r))
rows = con.execute("SELECT name, role, patterns, via FROM bm_layout WHERE app_key=? AND name<>'' AND enabled=1"
                   " AND (patterns LIKE '%invoke%' OR patterns LIKE '%expand%' OR patterns LIKE '%toggle%'"
                   " OR patterns LIKE '%select%') LIMIT 25", (KEY,)).fetchall()
for x in rows:
    print("  |", x["role"], "|", x["name"][:36], "|", x["patterns"], "|", x["via"][:28])
fr = con.execute("SELECT kind, label, status, path, substr(result_json,1,160) rj FROM bm_frontier WHERE app_key=?", (KEY,)).fetchall()
print("frontier rows:")
for x in fr:
    print("  F", dict(x))
cmd_r = con.execute("SELECT COUNT(*) n, SUM(CASE WHEN menu_path LIKE '%toolbar%' OR menu_path LIKE '%Toolbar%' THEN 1 ELSE 0 END) tb FROM bm_commands WHERE app_key=?", (KEY,)).fetchone()
print("commands:", dict(cmd_r))
