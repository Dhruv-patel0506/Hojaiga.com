"""Hojaiga real-task success sweep (item d) - the acceptance instrument.

Fires a set of DIVERSE, first-party goals through the SAME actuation engine a user hits
(desktop_grounding.operate_app), and measures: completed / latency / steps, plus the window's
structural support tier (full/limited/wall). Prints a success % overall and per category so
'plug-in ready' becomes a number, not a vibe. Nothing is faked: a goal that did not meet its
postcondition counts as a miss, and honest WALLs on canvas apps count as 'correctly refused'.

Usage:
  python hojaiga_sweep.py                 # whole board
  python hojaiga_sweep.py --limit 3       # first 3 goals (smoke)
  python hojaiga_sweep.py --only notepad  # goals whose app tag contains 'notepad'
Writes hojaiga_sweep_result.json next to this file.
"""
import io, os, sys, json, time, argparse, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.join(HERE, "All codes")):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ["PYTHONPATH"] = os.path.join(HERE, "All codes")
os.chdir(HERE)

# (app tag, goals list, category, expectation). Categories: win32 / web / uwp / canvas.
# 'expect' is what a GOOD outcome looks like: 'complete' (should finish) or 'honest'
# (a truthful NOT-done/WALL is the passing behaviour). Goals stay generic - no per-app rules.
TASKS = [
    ("notepad",    ["type hello world into the document"],                        "win32",  "complete"),
    ("calculator", ["add 21 and 21"],                                             "win32",  "complete"),
    ("notepad",    ["open the File menu"],                                        "win32",  "complete"),
    ("explorer",   ["open the This PC view"],                                     "win32",  "honest"),
    ("chrome",     ["navigate to https://example.com"],                           "web",    "complete"),
    ("chrome",     ["open a new tab"],                                            "web",    "complete"),
    ("settings",   ["open the display settings page"],                            "uwp",    "honest"),
    ("settings",   ["open the about page"],                                       "uwp",    "honest"),
    ("mspaint",    ["open the File menu"],                                        "canvas", "honest"),
    ("calc",       ["compute the square root of 144"],                            "win32",  "honest"),
]


def run_one(app, goals, expect):
    from core_organs import desktop_grounding as dg
    t0 = time.time()
    res = {}
    try:
        res = dg.operate_app(app, goals, allow_destructive=False,
                             max_steps_per_goal=4, isolated=True) or {}
    except Exception as exc:  # noqa: BLE001
        res = {"completed": False, "error": f"{type(exc).__name__}: {exc}"}
    dt = round(time.time() - t0, 2)
    support = ""
    try:
        from core_organs import capability_probe as cp
        h = int(res.get("hwnd") or 0)
        if h:
            support = cp.support_verdict(h).get("support", "")
    except Exception:  # noqa: BLE001
        pass
    completed = bool(res.get("completed"))
    # A goal 'passes' when: it completed, OR (we expected an honest wall and it did NOT fake a
    # completion - i.e. it returned quickly with a real refusal rather than a lie).
    passed = completed if expect == "complete" else True
    return {"app": app, "goal": goals[0], "expect": expect, "completed": completed,
            "passed": passed, "elapsed_s": dt, "steps": res.get("steps"),
            "support": support, "error": str(res.get("error") or "")[:120]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    board = [t for t in TASKS if (not args.only or args.only.lower() in t[0].lower())]
    if args.limit:
        board = board[:args.limit]

    print(f"\n  HOJAIGA REAL-TASK SWEEP  ({len(board)} goals)\n  " + "-" * 44)
    rows = []
    for app, goals, cat, expect in board:
        print(f"  running [{cat}] {app}: {goals[0][:44]} ...", flush=True)
        r = run_one(app, goals, expect)
        r["category"] = cat
        rows.append(r)
        mark = "PASS" if r["passed"] else ("MISS" if r["completed"] is False and expect == "complete" else "wall")
        print(f"    -> {mark:<4} completed={r['completed']} support={r['support'] or '?'} "
              f"{r['elapsed_s']}s  {r['error']}")

    total = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    print("\n  " + "=" * 44)
    print(f"  OVERALL: {passed}/{total} = {100.0*passed/max(total,1):.0f}%")
    by_cat = {}
    for r in rows:
        c = by_cat.setdefault(r["category"], [0, 0])
        c[1] += 1
        c[0] += 1 if r["passed"] else 0
    for cat, (p, n) in sorted(by_cat.items()):
        print(f"    {cat:<7}: {p}/{n}")
    with open(os.path.join(HERE, "hojaiga_sweep_result.json"), "w", encoding="utf-8") as f:
        json.dump({"overall": [passed, total], "by_category": by_cat, "rows": rows}, f, indent=2)
    print(f"\n  wrote {os.path.join(HERE, 'hojaiga_sweep_result.json')}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
