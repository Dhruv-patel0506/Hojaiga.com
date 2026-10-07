import sqlite3

db = r"D:\new_automation\storage\hojaiga_knowledge.sqlite"
con = sqlite3.connect(db)
try:
    n = con.execute("SELECT COUNT(*) FROM app_catalog").fetchone()[0]
    print("app_catalog rows:", n)
    for row in con.execute("SELECT name, source, launcher_path<>'' FROM app_catalog ORDER BY RANDOM() LIMIT 25"):
        print("  ", row)
    for want in ("powerpoint", "blender", "audacity", "gimp", "vlc", "spotify"):
        hit = con.execute("SELECT name FROM app_catalog WHERE lower(name) LIKE ?", (f"%{want}%",)).fetchone()
        print(f"  contains {want!r}: {hit}")
except Exception as e:
    print("ERR:", e)
con.close()
