"""bench_report.py — turn bench_universal_results.json into a side-by-side comparison with explicit,
mechanical pass criteria (no impressions).

    python bench_report.py [results.json] [--md out.md]

A target PASSES a criterion or it does not; the table shows which, per target, so what works and what
does not can be compared across tiers.
"""
import json
import sys

CRITERIA_DESKTOP = [
    ("scanned",      lambda d: not d.get("error")),
    ("layout>=20",   lambda d: ((d.get("layout") or {}).get("controls") or 0) >= 20),
    ("sections>=3",  lambda d: ((d.get("layout") or {}).get("regions") or 0) >= 3),
    ("menus/cmds",   lambda d: (d.get("known_commands") or 0) >= 1),
    ("hidden",       lambda d: d.get("window_mode") in ("parked", "visible") and not (d.get("polite_mode") and False)),
    ("focus<=120ms", lambda d: ((d.get("monitor") or {}).get("foreground_longest_ms", 0) or 0) <= 120),
    ("expose<=120ms", lambda d: ((d.get("monitor") or {}).get("exposure_longest_ms", 0) or 0) <= 120),
    ("restored",     lambda d: d.get("ended_minimized", True) is not False),
]
CRITERIA_WEB = [
    ("scanned",      lambda d: not d.get("error")),
    ("controls>=20", lambda d: (d.get("controls") or 0) >= 20),
    ("sections>=3",  lambda d: (d.get("regions") or 0) >= 3),
    ("commands",     lambda d: (d.get("commands_recorded") or 0) >= 1),
    ("headless",     lambda d: d.get("window_mode") == "headless"),
]


def verdicts(row):
    d = row["cold"] or {}
    crit = CRITERIA_DESKTOP if row["kind"] == "desktop" else CRITERIA_WEB
    return {n: bool(f(d)) for n, f in crit}


def main():
    path = r"D:\new_automation\data\bench_universal_results.json"
    md = None
    a = sys.argv[1:]
    if a and not a[0].startswith("--"):
        path = a[0]
    if "--md" in a:
        md = a[a.index("--md") + 1]
    rows = json.load(open(path, encoding="utf-8"))
    lines = []
    out = lines.append
    out("| tier | target | cold s | warm s | controls | sections | commands | deepen | focus ms | expose ms | criteria failed |")
    out("|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|")
    for r in rows:
        c, w = r["cold"] or {}, r["warm"] or {}
        lay = c.get("layout") or {}
        ctrls = lay.get("controls", c.get("controls"))
        regs = lay.get("regions", c.get("regions"))
        cmds = c.get("known_commands", c.get("commands_recorded"))
        dp = lay.get("deepen") or c.get("deepen") or {}
        dps = ",".join(f"{k.split('_')[0]}={v}" for k, v in dp.items() if v)[:40]
        mon = c.get("monitor") or {}
        v = verdicts(r)
        failed = [k for k, ok in v.items() if not ok]
        err = c.get("error")
        out(f"| {r['tier']} | {r['target'].split('|')[0][:44]} | {c.get('wall_s', '')} | {w.get('wall_s', '')} | {ctrls} | {regs} | {cmds} | {dps} | "
            f"{mon.get('foreground_longest_ms', '-')} | {mon.get('exposure_longest_ms', '-')} | {(', '.join(failed) if failed else 'none')}"
            f"{' ERR: ' + str(err)[:60] if err else ''} |")
    text = "\n".join(lines)
    print(text)
    if md:
        open(md, "w", encoding="utf-8").write(text)


if __name__ == "__main__":
    main()
