import sqlite3, sys
db = sqlite3.connect("D:/new_automation/data/professor/manuals.db")
for app, n, ch in db.execute("SELECT app, COUNT(*), SUM(chunks) FROM docs GROUP BY app ORDER BY app"):
    print(f"{app:22s} {n:4d} docs {ch or 0:6d} chunks")
if len(sys.argv) > 1:
    for r in db.execute("SELECT title, source FROM docs WHERE app=? LIMIT 8", (sys.argv[1],)):
        print("   ", r[0][:50], r[1][:100])
