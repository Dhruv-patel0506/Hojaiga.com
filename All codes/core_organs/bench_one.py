"""bench_one.py — scan ONE target (cold or warm) and print a single JSON line. Run by bench_universal.py
in its own process so a hung app can never poison the next measurement.

    python bench_one.py <target> <db_path> [--no-e1] [--keep]
"""
import json
import os
import sys
import time

os.environ.setdefault("HOJAIGA_WEBAPP_WATCH", "0")
sys.path.insert(0, r"D:\new_automation\All codes\core_organs")
sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation")


def main() -> int:
    target, db = sys.argv[1], sys.argv[2]
    cookies_site = ""
    existing = False
    if "|" in target:                                  # "url|vault-site" (web) or "app|existing" (desktop)
        target, cookies_site = target.split("|", 1)
        if cookies_site == "existing":
            existing, cookies_site = True, ""
    from core_organs import organ_48_app_behavior_model as bm
    from core_organs import universal_scan as us
    model = bm.BehaviorModel(db)
    mon_holder = {}
    kw = {}
    if us.classify_target(target) == "desktop":
        from core_organs import si_tests_behavior as T

        def on_window(hwnd):
            mon_holder["m"] = T._ScreenMonitor(hwnd).start()
        kw["on_window"] = on_window
        kw["e1_actions"] = 0 if "--no-e1" in sys.argv else 3
        kw["close_if_launched"] = "--keep" not in sys.argv
        kw["fresh"] = not existing               # benchmark windows are our own unless told otherwise; user windows are never touched
    if cookies_site:
        kw["cookies_site"] = cookies_site
    t0 = time.time()
    rep = us.scan(target, model, **kw)
    mon = mon_holder.get("m")
    if mon:
        mon.stop()
        rep["monitor"] = {"foreground_longest_ms": round(mon.max_fg_run_ms), "foreground_samples": f"{mon.fg_hits}/{mon.samples}",
                          "exposure_longest_ms": round(mon.max_run_ms), "exposure_max_px": mon.max_px}
    rep["wall_s"] = round(time.time() - t0, 2)
    model.close()
    print("BENCH_JSON " + json.dumps(rep, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
