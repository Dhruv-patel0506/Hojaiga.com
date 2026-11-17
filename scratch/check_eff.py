from core_organs.professor import history as HS
h = HS.History("data/professor/history.db")
for app in ["calculator", "notepad", "mspaint", "winword"]:
    cur = h.db.execute("SELECT target, effect FROM transitions WHERE app_key=? AND ok=1 AND effect!='' LIMIT 5", (app,))
    print(app, cur.fetchall())
