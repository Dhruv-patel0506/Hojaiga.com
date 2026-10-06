"""Live view of a running suite log: id, verdict and the failing part of the evidence."""
import io, re, sys

path = sys.argv[1] if len(sys.argv) > 1 else r"d:\new_automation\_suite_rev3.out"
raw = io.open(path, "r", encoding="utf-8", errors="replace").read()
blocks = re.findall(r"TEST (\S+) [^\n]*\n=+\n\[?(PASS|FAIL|ENV-BLOCKED)\]?[^\n]*", raw)
done = {b[0]: b[1] for b in blocks}
print("finished:", len(done), "  " + " ".join(f"{k}={v}" for k, v in list(done.items())[-6:]))
for m in re.finditer(r"TEST (\S+) \[(.*?)\]: (.*?)\n=+\n\[(FAIL|ENV-BLOCKED)\] ([^\n]*)", raw):
    tid, grp, title, verdict, rest = m.groups()
    bad = [c for c in rest.split("; ") if ("=FAIL" in c or verdict == "ENV-BLOCKED" and c.startswith("ABORTED"))]
    print(f"\n{verdict} {tid} [{grp}]  {title[:70]}")
    for c in (bad or [rest[:220]])[:4]:
        print("   ", c[:420])
