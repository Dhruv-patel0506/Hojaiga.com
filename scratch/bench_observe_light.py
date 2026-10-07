"""What does one per-probe observation cost, deep vs light, on a real minimized app?

The scanner observes before AND after every probe, so this number is multiplied by hundreds of probes.
The question worth measuring is not only speed: if a light read loses control NAMES, a real UI change
could go unseen and the scan would record "no effect". So print the name-set difference too.
"""
import logging
import os
import sys
import time

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

logging.basicConfig(level=logging.INFO,
                    filename=os.path.join(r"D:\new_automation\scratch", "_bench_observe.log"),
                    filemode="w", format="%(asctime)s %(levelname)s %(name)s %(message)s")

from core_organs import organ_48_app_behavior_model as bm            # noqa: E402
from core_organs import si_tests_behavior as sib                     # noqa: E402
from core_organs import desktop_grounding as dg                      # noqa: E402

ROUNDS = 4


def timed(grounding, hwnd, deep):
    t0 = time.perf_counter()
    st = bm.observe(hwnd, grounding=grounding, max_nodes=350, deep=deep)
    return (time.perf_counter() - t0) * 1000.0, st


def main() -> int:
    g = dg.DesktopGrounding()
    for app in ("paint", "notepad"):
        with sib.LiveApp(app, park=False) as la:
            if not la.ok:
                print(f"{app}: env - {la.why}")
                continue
            print(f"=== {app} hwnd={la.hwnd} ===")
            deep_ms, light_ms = [], []
            deep_names, light_names = set(), set()
            deep_vals = light_vals = 0
            for r in range(ROUNDS):
                ms, st = timed(g, la.hwnd, True)
                deep_ms.append(ms)
                deep_names |= {n for n in st.names if n}
                deep_vals = max(deep_vals, len(st.values))
                ms2, st2 = timed(g, la.hwnd, False)
                light_ms.append(ms2)
                light_names |= {n for n in st2.names if n}
                light_vals = max(light_vals, len(st2.values))
                print(f"  round {r + 1}: deep {ms:7.1f}ms names={len(st.names):4} values={len(st.values):3} "
                      f"windows={len(st.windows)} light {ms2:7.1f}ms names={len(st2.names):4} "
                      f"values={len(st2.values):3} light_flag={st2.light}")
            avg = lambda xs: sum(xs) / len(xs)
            print(f"  {app}: deep avg {avg(deep_ms):.0f}ms (max {max(deep_ms):.0f}) | "
                  f"light avg {avg(light_ms):.0f}ms (max {max(light_ms):.0f}) | "
                  f"{avg(deep_ms) / max(avg(light_ms), 0.001):.1f}x")
            print(f"  {app}: names deep={len(deep_names)} light={len(light_names)} "
                  f"deep-only={len(deep_names - light_names)} light-only={len(light_names - deep_names)}")
            print(f"  {app}: deep-only names sample {sorted(deep_names - light_names)[:12]}")
            print(f"  {app}: values deep={deep_vals} light={light_vals} (light never reads values by design)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
