"""Read-only suite-log watcher: the TEST / verdict lines of a running --e2e run, truncated."""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else r"D:\new_automation\_full2.out"
rows = []
cur = ""
for line in open(path, encoding="utf-8", errors="replace"):
    m = re.match(r"^TEST (\S+) \[", line)
    if m:
        cur = m.group(1)
        continue
    m = re.match(r"^\[(PASS|FAIL|ENV-BLOCKED)\] ([\d.]+)s", line)
    if m:
        rows.append((cur, m.group(1), float(m.group(2)), line.strip()))
n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
print(f"{len(rows)} verdicts so far")
for rid, st, dur, raw in rows[-n:]:
    print(f"  {rid:<8} {st:<12} {dur:8.1f}s  {raw[:150]}")
by = {}
for _r, st, _d, _x in rows:
    by[st] = by.get(st, 0) + 1
print("totals:", by)
