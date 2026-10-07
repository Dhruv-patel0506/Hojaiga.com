"""Summarise a suite run: one row per TEST banner with its verdict, and (for a baseline file) the per-id diff.
python scratch/sum_suite.py <run.out> [<baseline.out>]
"""
import re
import sys

VERDICT = re.compile(r"^\[(PASS|FAIL|ENV-BLOCKED|ABORTED-ENV|SKIP)\]\s+([\d.]+)s")
BANNER = re.compile(r"^TEST\s+(\S+)\s+\[([^\]]+)\]")


def parse(path):
    rows, cur = [], None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            b = BANNER.match(line)
            if b:
                cur = (b.group(1), b.group(2))
                continue
            v = VERDICT.match(line)
            if v and cur:
                rows.append({"id": cur[0], "tag": cur[1], "verdict": v.group(1), "s": float(v.group(2)),
                             "evidence": line.strip()})
                cur = None
    return rows


def tally(rows):
    t = {}
    for r in rows:
        t[r["verdict"]] = t.get(r["verdict"], 0) + 1
    t["total"] = len(rows)
    return t


a = parse(sys.argv[1])
print(f"{sys.argv[1]}: {tally(a)}")
for r in a:
    if r["verdict"] != "PASS":
        print(f"  {r['verdict']:<12} {r['id']:<8} [{r['tag']}] {r['s']:.1f}s  {r['evidence'][:150]}")
if len(sys.argv) > 2:
    b = {r["id"]: r for r in parse(sys.argv[2])}
    now = {r["id"]: r for r in a}
    print("\n--- change vs baseline ---")
    for i in sorted(set(b) | set(now)):
        x, y = b.get(i, {}).get("verdict", "-"), now.get(i, {}).get("verdict", "-")
        if x != y:
            print(f"  {i:<8} {x} -> {y}")
