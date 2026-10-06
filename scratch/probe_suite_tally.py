"""Final tally of a completed suite log: FAIL list, ENV list with the reason, and the pointer story."""
import io, re, sys

path = sys.argv[1] if len(sys.argv) > 1 else r"d:\new_automation\_suite_rev3.out"
raw = io.open(path, "r", encoding="utf-8", errors="replace").read()
sec = raw[raw.rindex("Hojaiga System Intelligence & Reliability Suite"):]

rows, cur = [], None
for ln in sec.splitlines():
    m = re.match(r"^TEST (\S+) \[(.*?)\]", ln)
    if m:
        cur = (m.group(1), m.group(2))
        continue
    v = re.match(r"^\[(FAIL|ENV-BLOCKED|PASS)\]\s+[\d.]+s\s*(?:\u2014|--)\s*(.*)", ln)
    if v and cur:
        rows.append((v.group(1), cur[0], cur[1], v.group(2)))

print("== FAIL")
for verdict, tid, grp, rest in rows:
    if verdict == "FAIL":
        bad = [c for c in re.split(r";\s+", rest) if "=FAIL" in c] or [rest[:170]]
        print(f"  {tid} [{grp}]: " + " | ".join(b[:230] for b in bad[:3]))
print("== ENV-BLOCKED")
for verdict, tid, grp, rest in rows:
    if verdict == "ENV-BLOCKED":
        head = rest[:190]
        print(f"  {tid} [{grp}]: {head}")
hum = re.findall(r"pointer = human-hand drift=(\d+)px", sec)
print("\ntests whose own metrics saw a human hand on the mouse:", len(hum),
      "| largest drift:", max((int(x) for x in hum), default=0), "px")
print("totals:", {k: sum(1 for r in rows if r[0] == k) for k in ("PASS", "FAIL", "ENV-BLOCKED")})
