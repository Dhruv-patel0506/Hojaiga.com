"""poll_suite.py -- compact status of a running suite from its raw stdout log.

Reads the [TEST id] headers and the [PASS/FAIL/ENV-BLOCKED] lines, plus every capture-blank
diagnostic (pw/err/dib/obj/px/where/xaml) that headless_input now puts in its notes.
"""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else r"D:\new_automation\_job1_suite_run.out"
txt = open(path, encoding="utf-8", errors="replace").read()

rows = []
cur = ("?", "?")
for line in txt.splitlines():
    m = re.match(r"TEST (\S+) \[([A-Z]+)\]", line.strip())
    if m:
        cur = (m.group(1), m.group(2))
    m = re.match(r"^\[(PASS|FAIL|ENV-BLOCKED)\] ([\d.]+)s . (\S.*)$", line.strip())
    if m:
        rows.append((m.group(1), cur[0], cur[1], float(m.group(2)), m.group(3)))

done = {r[1] for r in rows}
print(f"finished {len(rows)}  PASS={sum(1 for r in rows if r[0] == 'PASS')}  "
      f"FAIL={sum(1 for r in rows if r[0] == 'FAIL')}  ENV={sum(1 for r in rows if r[0] == 'ENV-BLOCKED')}")
for st, tid, grp, dur, ev in rows:
    if st != "PASS":
        print(f"  [{st}] {tid} ({grp}) {dur:.0f}s :: {ev[:230]}")
blanks = re.findall(r"capture-blank\[[^\]]*\]", txt)
print(f"capture-blank notes: {len(blanks)}")
for b in blanks[:8]:
    print("   ", b)
last = [r[1] for r in rows[-1:]]
mtest = re.findall(r"TEST (\S+) \[", txt)
print("last completed:", last, "| currently running:", mtest[-1] if mtest and mtest[-1] not in done else "-")
if "SUMMARY" in txt:
    hit = re.search(r"SUMMARY.*", txt)
    print("RUN FINISHED:", (hit.group(0) if hit else "?")[:200])
