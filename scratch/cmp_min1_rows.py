"""Compare MIN1's per-leg measured rails across runs, so a regression is read and not guessed.

MIN1's ok-rule is a conjunction; the evidence line carries most of its terms. Pulling them side by
side shows WHICH rail moved between a passing and a failing run.
"""
import io
import re
import sys

LEG = re.compile(
    r"(?P<app>\w+): mode=(?P<mode>\S+) E0=(?P<e0>\d+) cmds, layout=(?P<layout>\d+) controls "
    r"\(File@(?P<file>[^)]*)\), E1 probe effect=(?P<effect>\S*) unwound=(?P<unwound>\S*)"
    r"(?:, template completed=(?P<tpl>\S*) truth=(?P<truth>\S*))?")
FOCUS = re.compile(r"longest=(?P<fg>\d+)ms.*longest-continuous-exposure=(?P<exp>\d+)ms")
ENDED = re.compile(r"ended minimized=(?P<min>\S+) placement-restored=(?P<rest>\S+)")


def rows(path: str):
    try:
        txt = io.open(path, encoding="utf-8", errors="replace").read()
    except Exception as exc:
        print(f"{path}: {exc}")
        return
    line = next((l for l in txt.splitlines() if "mode=" in l and " || " in l), "")
    verdict = re.search(r"^\[(PASS|FAIL|ENV-BLOCKED)\] [\d.]+s", txt, re.M)
    print(f"\n===== {path}  [{verdict.group(0) if verdict else 'no verdict'}]")
    for leg in line.split(" || "):
        g = LEG.search(leg)
        if not g:
            continue
        d = g.groupdict()
        f = FOCUS.search(leg)
        e = ENDED.search(leg)
        print(f"  {d['app']:<8} E0={d['e0']:<4} layout={d['layout']:<5} File@{d['file']:<20} "
              f"effect={d['effect'] or '-':<6} unwound={d['unwound'] or '-':<6} "
              f"tpl={d['tpl'] or '-':<6} truth={d['truth'] or '-':<6} "
              f"fg={f.group('fg') if f else '?'}ms exp={f.group('exp') if f else '?'}ms "
              f"min={e.group('min') if e else '?'} restored={e.group('rest') if e else '?'}")


for arg in sys.argv[1:] or ["full2", "full3", "m1s1", "m2"]:
    rows(arg if arg.endswith(".out") else rf"D:\new_automation\_{arg}.out")
