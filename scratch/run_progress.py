"""Where is the suite run now? One line of counts plus the last test's verdict.

Reading the log through PowerShell inline commands kept breaking on quotes, and `Get-Content -Tail`
splits the long evidence lines; a named script can print exactly what is needed.
"""
import io
import os
import re
import sys
import time

TAG = sys.argv[1] if len(sys.argv) > 1 else "f4"
PATH = rf"D:\new_automation\_{TAG}.out"


def main() -> int:
    if not os.path.exists(PATH):
        print(f"no {PATH} yet")
        return 1
    txt = io.open(PATH, encoding="utf-8", errors="replace").read()
    ls = txt.splitlines()
    age = time.time() - os.path.getmtime(PATH)
    started = re.findall(r"^TEST (\S+) ", txt, re.M)
    verdicts = re.findall(r"^\[(PASS|FAIL|ENV-BLOCKED|ABORTED-ENV)\] ([\d.]+)s", txt, re.M)
    tally = {}
    for v, _s in verdicts:
        tally[v] = tally.get(v, 0) + 1
    print(f"{PATH}: {len(ls)} lines, log idle {age:.0f}s | started {len(started)} tests | {tally}")
    if started:
        print(f"  latest test: {started[-1]}")
    for line in ls[-8:]:
        print(f"  | {line[:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
