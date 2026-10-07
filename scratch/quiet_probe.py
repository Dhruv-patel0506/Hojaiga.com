"""Read-only: is a human on this machine right now? (Sentinel preflight, no windows touched.)"""
import sys, os
sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import pointer_sentinel as ps

rep = ps.preflight(seconds=float(sys.argv[1]) if len(sys.argv) > 1 else 3.0)
print("hardware_events", rep.get("hardware_events"),
      "hardware_keys", rep.get("hardware_keys"),
      "injected", rep.get("injected_events"),
      "cause", rep.get("cause"), "hook_ok", rep.get("hook_ok"))
