"""scan_only.py <app> -- start an owned instance, run ONLY the perception phase (tree + vision + menus + clicked options), print what the options exploration found, write report + pictures."""
import sys, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR

key = sys.argv[1]
vision = "--vision" in sys.argv
run = AR.AppRun(AR.SPECS[key], vision=vision, log=lambda s: None, phases=())
try:
    if not run.start():
        print("launch failed")
    else:
        try:
            run.perceive()
        except AR.RevealTainted as exc:
            print("TAINTED:", exc)
        ph = run.report["phases"]
        opt = ph.get("options", {})
        print("\n==== OPTIONS ====")
        for k in ("candidates", "tried", "opened", "dialogs", "pages", "inline", "nothing", "controls", "left_ok", "stopped", "seconds"):
            print(f"  {k}: {opt.get(k)}")
        for s in opt.get("surfaces", []):
            print(f"  - {s['path']}: {s['kind']} ({s.get('effect')}) controls={len(s['controls'])} left_by={s.get('left_by')} restored={s.get('restored')} {s.get('still_differs','')}")
            print("      ", s["controls"][:14])
        print("  NOT CLICKED:")
        for s in opt.get("skipped", []):
            print("   ", s["path"], "-", s["why"])
        print("\n==== MAP ====")
        for r in ph.get("ui_map", []):
            print(f"  [{r['kind']:<13}] {r['path']} ({r['count']}): {r['items'][:8]}")
finally:
    path = run.finish()
    print("report:", path)
