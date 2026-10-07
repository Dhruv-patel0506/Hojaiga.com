"""Which tests failed in this run, and what did the SAME test do in the previous full runs?

A verdict line alone does not attribute anything: the id has to come from the nearest PRECEDING banner
(the first attempt printed the file's first TEST line for every hit), and "regression" only means
something against the run that passed before it.
"""
import io
import re
import sys

RUNS = ("f4", "full3", "full2", "full1")
TAG = sys.argv[1] if len(sys.argv) > 1 else "f4"


def rows(tag):
    """{test_id: (verdict, seconds)} for one run, from banner + verdict lines in order."""
    path = rf"D:\new_automation\_{tag}.out"
    try:
        ls = io.open(path, encoding="utf-8", errors="replace").read().splitlines()
    except Exception as exc:
        return {}
    out, cur = {}, ""
    for l in ls:
        m = re.match(r"^TEST (\S+) ", l)
        if m:
            cur = m.group(1)
            out.setdefault(cur, ("NOT-RUN", 0))
            continue
        m = re.match(r"^\[(PASS|FAIL|ENV-BLOCKED|ABORTED-ENV)\] ([\d.]+)s", l)
        if m and cur:
            out[cur] = (m.group(1), float(m.group(2)))
    return out


def main() -> int:
    here = rows(TAG)
    failed = [t for t, (v, _s) in here.items() if v == "FAIL"]
    print(f"{TAG}: {len(here)} tests started, "
          f"{sum(1 for v, _ in here.values() if v == 'PASS')} PASS, {len(failed)} FAIL, "
          f"{sum(1 for v, _ in here.values() if v.startswith('ENV'))} ENV-BLOCKED, "
          f"{sum(1 for v, _ in here.values() if v == 'NOT-RUN')} not reached")
    history = {r: rows(r) for r in RUNS if r != TAG}
    for t in failed:
        v, s = here[t]
        prev = "; ".join(f"{r}:{history[r].get(t, ('absent', 0))[0]}" for r in history)
        print(f"  {t:6} {s:8.2f}s   was -> {prev}")
    missing = [t for t, (v, _s) in here.items() if v == "NOT-RUN"]
    if missing:
        print(f"  started but no verdict: {missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
