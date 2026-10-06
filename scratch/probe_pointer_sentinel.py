"""P0-C offline + live check of the pointer sentinel.

1. live: start it for 2 s - both hooks must install and it must stop cleanly (no hung thread, no crash), and the
   report must carry the keyboard counters.
2. offline: the classification and the ABORTED-ENV rule on the three shapes the suite produces, including the one
   that used to be graded as a code defect: a GOAL failure while a person was clicking in the same window.
"""
import sys
import time

sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import pointer_sentinel as ps

s = ps.Sentinel().start()
time.sleep(2.0)
s.stop()
rep = s.report()
print("live   :", {k: rep[k] for k in ("hook_ok", "hardware_events", "hardware_keys", "injected_events", "cause", "moved")})
print("threads:", [t.name for t in __import__("threading").enumerate() if "hook" in t.name or "sampler" in t.name])

CASES = [
    ("goal failed, person clicking (the measured case)",
     "run1 completed=False content[42]=FAIL('42' is NOT inside) pointer=OK",
     {"cause": "human-hand", "hardware_events": 831, "hardware_keys": 12, "injected_events": 0,
      "p0": (0, 0), "p1": (50, 50), "drift_px": 100, "moved": True, "guard_violations": 0,
      "max_step_px": 40, "max_speed_px_ms": 3.1, "hook_ok": True}),
    ("only the pointer assertion failed",
     "cursor=FAIL(1154px); app=OK; file=OK",     {"cause": "human-hand", "hardware_events": 2, "hardware_keys": 0, "injected_events": 0,
      "p0": (0, 0), "p1": (50, 50), "drift_px": 100, "moved": True, "guard_violations": 0,
      "max_step_px": 40, "max_speed_px_ms": 3.1, "hook_ok": True}),
    ("XLS1 evidence style, no =FAIL tokens",
     "run1 completed=False file=yes content[42]=False/'42' is NOT inside; physical pointer untouched=False",
     {"cause": "human-hand", "hardware_events": 831, "hardware_keys": 0, "injected_events": 0,
      "p0": (576, 760), "p1": (1100, 400), "drift_px": 1154, "moved": True, "guard_violations": 0,
      "max_step_px": 40, "max_speed_px_ms": 3.1, "hook_ok": True}),
    ("real code failure, machine quiet",
     "run1 completed=False; menu=FAIL(no menu item)",
     {"cause": "still", "hardware_events": 0, "hardware_keys": 0, "injected_events": 0,
      "p0": (0, 0), "p1": (0, 0), "drift_px": 0, "moved": False, "guard_violations": 0,
      "max_step_px": 0, "max_speed_px_ms": 0.0, "hook_ok": True}),
    ("WE moved the pointer (guard saw it)",
     "cursor=FAIL(1154px)",
     {"cause": "ours-guard", "hardware_events": 0, "hardware_keys": 0, "injected_events": 4, "guard_violations": 2,
      "p0": (0, 0), "p1": (50, 50), "drift_px": 100, "moved": True, "max_step_px": 40, "max_speed_px_ms": 3.1,
      "hook_ok": True}),
    ("one stray key press is not an excuse",
     "menu=FAIL(no menu item)",
     {"cause": "human-hand", "hardware_events": 0, "hardware_keys": 1, "injected_events": 0,
      "p0": (0, 0), "p1": (0, 0), "drift_px": 0, "moved": False, "guard_violations": 0,
      "max_step_px": 0, "max_speed_px_ms": 0.0, "hook_ok": True}),
]
for label, ev, r in CASES:
    note = ps.abort_if_env_only(ev, r)
    print(f"\n{label}\n  -> {'STAYS A FAILURE' if not note else note[:170]}")
