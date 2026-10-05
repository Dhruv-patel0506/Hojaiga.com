import pyodbc

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=DHRUV_PATEL\\SQLEXPRESS;"
    "DATABASE=hojaiga_knowledge;"
    "UID=Hojaiga.com;PWD=DhPa@3396$"
)
cursor = conn.cursor()

# Check unique index columns
cursor.execute("""
    SELECT i.name, ic.key_ordinal, c.name
    FROM sys.indexes i
    JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
    JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
    WHERE i.name = 'uq_scanned'
""")
print("uq_scanned columns:", [(r[1], r[2]) for r in cursor.fetchall()])

conn.close()

