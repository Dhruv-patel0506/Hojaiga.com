"""Jarvis failure path proof: run a goal Calculator CANNOT do (basic mode has no binary button) twice,
so the ledger records 2 real failures; then prefetch must report tone=cautious with the last block.
Keeps honesty contract: prefetch only warns - it never changes a verdict."""
import time, json, sys, logging

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")

from core_organs.desktop_grounding import operate_app
from core_organs import outcome_ledger as L

GOAL = "press the binary mode button"

for i in (1, 2):
    res = operate_app("Calculator", [GOAL], isolated=True, max_steps_per_goal=2)
    print("RESULT run%d:" % i, json.dumps({
        "completed": res.get("completed"), "steps": res.get("steps"),
        "elapsed_s": res.get("elapsed_s"),
        "launch_note": (res.get("launch_note") or "")[:200],
    }, default=str))

p = L.prefetch("Calculator", " / ".join([GOAL]))   # operate_app records under " / ".join(goals)
print("PREFETCH(task key):", json.dumps(p, default=str))
print("LEDGER_OK" if (p.get("failures", 0) >= 1 and p.get("tone") == "cautious" and p.get("caution")) else "LEDGER_PARTIAL: " + json.dumps(p))
