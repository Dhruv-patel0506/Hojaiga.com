"""Reproduce MIN1's Paint E0 shortfall (41 measured here, 18 in the suite) in isolation.

Shapes to compare, one process each is enough because the crawl is the thing under test:
  A  park=True,  paint alone                     -> what bench_e0_paint measured: 41
  B  park=False (truly minimized), paint alone    -> MIN1's entry condition
  C  park=False, notepad leg first, then paint    -> MIN1's SEQUENCE: does the first app's
     leftovers (a popup, focus juggling, the parked-window journal) cost the second leg its menus?
The crawl report carries `stopped` and per-method `skipped`, so the answer is read, not inferred.
"""
import json
import logging
import os
import sys
import tempfile
import time

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

logging.basicConfig(level=logging.INFO,
                    filename=os.path.join(r"D:\new_automation\scratch", "_bench_min1_legs.log"),
                    filemode="w", format="%(asctime)s %(levelname)s %(name)s %(message)s")

from core_organs import organ_48_app_behavior_model as bm           # noqa: E402
from core_organs import si_tests_behavior as sib                     # noqa: E402
from core_organs import organ_50_layout_map as lm                    # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else "B"
APPS = {"B": ["paint"], "C": ["notepad", "paint"], "D": ["notepad", "paint"]}[MODE]
# Mode D re-crawls the SECOND app's SAME window in the same process: if the re-crawl comes back full, the
# shortfall is UIA first-touch laziness (the tree had not been built when it was read); if it comes back
# short again, something about the process state persists and the crawl is genuinely reading a smaller tree.
REPEAT_SECOND = MODE == "D"


def yields_by_menu(m, key):
    """Which top-level menu gave how many catalogued commands - the missing detail in the count."""
    by = {}
    for c in m.commands(key, limit=2000):
        top = ((c.get("menu_path") or "?").split(" > ") + ["?"])[0]
        by[top] = by.get(top, 0) + 1
    return dict(sorted(by.items(), key=lambda kv: -kv[1]))


def brief(out):                                  # the crawl report is a plain dict; no value in over-typing a probe
    keep = {k: v for k, v in out.items() if k in ("ingested", "elapsed_s", "units", "stopped", "window_mode")}
    keep["methods"] = [{k: r.get(k) for k in ("method", "found", "nodes", "stopped", "expand_collapse", "skipped")}
                       for r in out.get("methods", [])]
    return json.dumps(keep, default=str)


def main() -> int:
    db = tempfile.mktemp(suffix=".db")
    m = bm.BehaviorModel(db)
    print(f"mode {MODE}: apps={APPS}")
    try:
        for app in APPS:
            repeat = 1
            for pass_no in range(repeat):
                print(f"  --- {app} pass {pass_no + 1} ---")
                with sib.LiveApp(app, park=False) as la:
                    if not la.ok:
                        print(f"  {app}: env - {la.why}")
                        continue
                    t0 = time.time()
                    e0 = bm.crawl_e0(m, app, la.hwnd)
                    print(f"  {app} E0 ({time.time() - t0:.1f}s): {brief(e0)}")
                    print(f"  {app} by-menu {yields_by_menu(m, bm._app_key(app))}")
                    if REPEAT_SECOND:
                        # same window, crawled a second time: a UIA tree that was still being built on
                        # first touch comes back full here, and that is a different fix than a
                        # permanently smaller tree.
                        t1 = time.time()
                        e0b = bm.crawl_e0(m, app, la.hwnd)
                        print(f"  {app} E0 again on the SAME window ({time.time() - t1:.1f}s): {brief(e0b)}")
                        print(f"  {app} by-menu now {yields_by_menu(m, bm._app_key(app))}")
                    lay = lm.map_layout(m, app, la.hwnd)
                    key = bm._app_key(app)
                    cand = next((c for c in m.commands(key, limit=500) if c["risk"] == "E1"
                                 and "page setup" in c["name"].lower()), None)
                    print(f"  {app} layout={lay.get('controls')} e1_page_setup_candidate={'yes' if cand else 'NO'}")
                    if cand:
                        pr = bm.probe_e1(m, app, la.hwnd, cand)
                        print(f"  {app} probe effect={pr.get('effect_observed')} unwound={pr.get('unwound')} "
                              f"effector={pr.get('effector')} evidence={str(pr.get('evidence'))[:160]}")
    finally:
        m.close()
        try:
            os.remove(db)
        except Exception:
            pass
    print("log: scratch/_bench_min1_legs.log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
