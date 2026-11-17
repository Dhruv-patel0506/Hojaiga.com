"""debug_seq.py <app> "<goal substring>|<goal substring>" -- run several guide procedures in a row on ONE instance with the real run_task (retries off), print raw results."""
import sys, time, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR
key, subs = sys.argv[1], [x.strip().lower() for x in sys.argv[2].split("|")]
run = AR.AppRun(AR.SPECS[key], vision=False, max_attempts=1, log=lambda s: print(s) if any(w in s for w in ("reveal", "attempt", "remedy", "task")) else None)
try:
    assert run.start()
    run.perceive()
    tasks = run.build_tasks()
    for sub in subs:
        t = next((x for x in tasks if sub in x["goal"].lower()), None)
        if t is None:
            print("no task", sub)
            continue
        tr = run.run_task(t)
        run.tasks.append(tr)
        for a in tr.attempts:
            for r in a.results:
                print("   ", json.dumps(r)[:600])
        print("   fx._hold =", run.fx._hold, "sticky =", run.ex._sticky is not None)
finally:
    run.finish()
