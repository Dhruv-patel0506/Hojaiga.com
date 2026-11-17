"""What did the stalled Word run actually do? The history rows are the ground truth."""
import sqlite3
import sys

n = int(sys.argv[1]) if len(sys.argv) > 1 else 14
key = sys.argv[2] if len(sys.argv) > 2 else "winword"
c = sqlite3.connect(r"D:\new_automation\data\professor\history.db")
c.row_factory = sqlite3.Row
tbl = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
print("tables:", tbl)
cols = [r[1] for r in c.execute(f"PRAGMA table_info({tbl[0]})")]
print("cols:", cols)
for r in c.execute(f"select * from {tbl[0]} where app_key=? order by rowid desc limit {n}", (key,)):
    d = dict(r)
    print("---", d.get("ts"), "|", d.get("source"), "|", d.get("primitive"), "|", str(d.get("target"))[:44])
    print("     route=", str(d.get("route"))[:60], " effect=", d.get("effect"), " ok=", d.get("ok"), " unwound=", d.get("unwound"))
    print("     s0=", str(d.get("s0_note"))[:110])
    print("     s1=", str(d.get("s1_note"))[:110])
    print("     detail=", str(d.get("detail"))[:220])
