"""Summarise the LAST full run recorded in system_intelligence_results.txt (read-only)."""
import re
import sys

p = r"D:\new_automation\All codes\core_organs\system_intelligence_results.txt"
t = open(p, encoding="utf-8", errors="replace").read()
head = "Hojaiga System Intelligence Suite"
i = t.rfind(head)
seg = t[i:]
rows = re.findall(r"^\[(PASS|FAIL|ENV-BLOCKED)\]\s+(\S+)", seg, re.M)
print("run timestamp:", seg[:60].splitlines()[0] if seg else "-")
if not rows:
    rows = re.findall(r"^\s*\[(PASS|FAIL|ENV-BLOCKED)\]\s+(\S+)", seg, re.M)
print("last run header at offset", i, "of", len(t))
print("rows:", len(rows))
counts = {}
for st, tid in rows:
    counts[st] = counts.get(st, 0) + 1
print(counts)
for st, tid in rows:
    if st != "PASS":
        m = re.search(r"^\[" + st + r"\]\s+" + re.escape(tid) + r"\b(.{0,140})", seg, re.M)
        print(f"  {st:<12} {tid:<8} {(m.group(1) if m else '').strip()[:130]}")
tot = re.findall(r"(?i)(total|passed|failed|env)[- ]?(?:tests)?.*(?:\d+)", seg[-4000:])
print("\n".join(tot[:12]))
