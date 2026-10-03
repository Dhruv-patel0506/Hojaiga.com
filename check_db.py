import pyodbc
import json

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=DHRUV_PATEL\\SQLEXPRESS;"
    "DATABASE=hojaiga_knowledge;"
    "UID=Hojaiga.com;PWD=DhPa@3396$"
)
cursor = conn.cursor()

cursor.execute("SELECT TOP 5 sig, info, last_scanned FROM ui_scanned WHERE app_id=? ORDER BY last_scanned DESC", ("Gatekeeper",))
rows = cursor.fetchall()
for r in rows:
    info = r[1][:80] if r[1] else ""
    print(f"  {r[0]} | {info} | {r[2]}")

cursor.execute("SELECT COUNT(*) FROM ui_scanned WHERE app_id=?", ("Gatekeeper",))
print(f"\nGatekeeper rows: {cursor.fetchone()[0]}")
conn.close()
conn.close()
