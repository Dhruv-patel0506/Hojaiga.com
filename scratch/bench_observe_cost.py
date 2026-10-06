"""Measure what one per-probe observation actually costs: the deep UIA walk vs the cheap bulk snapshot.

The scan observes the app BEFORE and AFTER every single probe (organ_49.light_state -> organ_48.observe), so
this number multiplies by the probe count and decides whether a deep scan takes seconds or minutes.
Numbers, not opinions, decide whether the walk belongs on that path.
"""
import statistics
import sys
import time

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs import desktop_grounding as dg          # noqa: E402
from core_organs import fast_uia                          # noqa: E402
from core_organs import organ_48_app_behavior_model as bm  # noqa: E402
from core_organs import si_tests_behavior as sib          # noqa: E402

REPEATS = 3


def _one(hwnd, g):
    """Return the costs of each observation shape, measured on the same window."""
    out = {}

    t = time.perf_counter()
    st = bm.observe(hwnd, grounding=g, max_nodes=350)
    out["observe(full)"] = time.perf_counter() - t
    out["observe.names"] = len(st.names)
    out["observe.cut"] = st.cut

    t = time.perf_counter()
    els = g._walk_uia(hwnd, max_depth=14, max_nodes=350)
    out["_walk_uia only"] = time.perf_counter() - t
    out["walk.surfaced"] = len(els)
    out["walk.stopped_by"] = getattr(g, "last_walk", {}).get("stopped_by", "")

    t = time.perf_counter()
    others = bm._open_popups(hwnd)
    out["popup list"] = time.perf_counter() - t
    out["popups"] = len(others)

    t = time.perf_counter()
    snap = fast_uia.snapshot(hwnd, timeout_ms=2500) or []
    out["fast_uia snapshot"] = time.perf_counter() - t
    out["snap.nodes"] = len(snap)
    out["snap.named"] = len({(n.name or "").strip().lower() for n in snap if (n.name or "").strip()})

    walk_names = {(e.name or "").strip().lower() for e in els if (e.name or "").strip()}
    snap_names = {(n.name or "").strip().lower() for n in snap if (n.name or "").strip()}
    out["names: walk-only"] = len(walk_names)
    out["names: snap-only"] = len(snap_names)
    out["names lost by dropping the walk"] = len(walk_names - snap_names)
    out["names gained by dropping the walk"] = len(snap_names - walk_names)
    return out


def main() -> int:
    for app in ("notepad", "paint"):
        print(f"\n===== {app} =====")
        g = dg.DesktopGrounding()
        with sib.LiveApp(app) as la:
            if not la.ok:
                print(f"  env: could not open ({la.why})")
                continue
            runs = [_one(la.hwnd, g) for _ in range(REPEATS)]
            for k in runs[0]:
                vals = [r[k] for r in runs]
                if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
                    if "names" in k or "surfaced" in k or "nodes" in k or "named" in k or "popups" in k:
                        print(f"  {k:<38} {vals[0]}")
                    else:
                        print(f"  {k:<38} median {statistics.median(vals) * 1000:8.1f} ms   runs={[round(v, 3) for v in vals]}")
                else:
                    print(f"  {k:<38} {vals[0]}")
    print("\nPer probe the scan pays the 'observe(full)' line TWICE (before + after).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
