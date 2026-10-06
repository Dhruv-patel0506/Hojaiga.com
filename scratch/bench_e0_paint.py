"""A/B Paint's E0 harvest against my own time/node budget rails.

Paint's MIN1 E0 count went 41 -> 18 between the run before and the run after the UIA walk budget landed, and
the E1 candidate ('Page setup') disappeared with it. Two of my rails could do that: the walk time budget
(desktop_grounding.UIA_WALK_BUDGET_S) or the observation deadline (organ_48.OBSERVE_BUDGET_S). Switching them
by env/module patch, with everything else fixed, says which one - instead of me picking the likelier story.
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
                    filename=os.path.join(r"D:\new_automation\scratch", "_bench_e0.log"),
                    filemode="w", format="%(asctime)s %(levelname)s %(name)s %(message)s")

from core_organs import desktop_grounding as dg                    # noqa: E402
from core_organs import organ_48_app_behavior_model as bm          # noqa: E402
from core_organs import si_tests_behavior as sib                    # noqa: E402

PASSES = [
    ("as-shipped (default rails)", {}),
    ("generous rails (no time/node cut)", {"walk_s": 600.0, "node": 10 ** 7, "observe_s": 120.0}),
]


def run(label: str, patch: dict[str, float]) -> None:
    saved = {k: getattr(dg, a) for k, a in
             (("walk_s", "UIA_WALK_BUDGET_S"), ("node", "UIA_WALK_NODE_BUDGET"))}
    saved_ob = bm.OBSERVE_BUDGET_S
    for k, v in patch.items():
        if k == "observe_s":
            bm.OBSERVE_BUDGET_S = v
        else:
            setattr(dg, {"walk_s": "UIA_WALK_BUDGET_S", "node": "UIA_WALK_NODE_BUDGET"}[k], v)
    db = tempfile.mktemp(suffix=".db")
    m = bm.BehaviorModel(db)
    try:
        with sib.LiveApp("paint") as la:
            if not la.ok:
                print(f"  {label}: env - could not open paint ({la.why})")
                return
            t0 = time.time()
            out = bm.crawl_e0(m, "paint", la.hwnd)
            print(f"\n===== {label}  ({time.time() - t0:.1f}s) =====")
            keep = {k: v for k, v in out.items() if k not in ("commands",)}
            print(json.dumps(keep, indent=2, default=str)[:2500])
    finally:
        m.close()
        bm.OBSERVE_BUDGET_S = saved_ob
        for k, a in (("walk_s", "UIA_WALK_BUDGET_S"), ("node", "UIA_WALK_NODE_BUDGET")):
            setattr(dg, a, saved[k])
        try:
            os.remove(db)
        except Exception:
            pass


def main() -> int:
    print(f"default rails: walk_s={dg.UIA_WALK_BUDGET_S} node={dg.UIA_WALK_NODE_BUDGET} "
          f"observe_s={bm.OBSERVE_BUDGET_S}")
    for label, patch in PASSES:
        run(label, patch)
    print("\nfull INFO log: scratch/_bench_e0.log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
