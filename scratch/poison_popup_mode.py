"""Reproduce the popup_mode leak: a 'probe' flag written by a process that is now GONE.

f5's PL1/PL2/UP1/PP1 all died with the same signature ("resolved via gate in 1 ms",
"cancel_only_no_handle") and all pass standalone. The only code path that produces
cancel_only_no_handle is the gate's probe branch, so the TEMP flag said 'probe'.

This script creates that exact state on purpose - a fresh ts (inside the 120 s TTL) with
the pid of a child that has already exited - so a following test run either reproduces the
f5 failure (proving the leak) or, after the fix, ignores the dead writer.
"""
import json
import os
import subprocess
import sys
import time

FLAG = os.path.join(os.environ.get("TEMP", "."), "hojaiga_popup_mode.json")

# a pid that is definitively dead: spawn a child, let it print its own pid, then exit
child = subprocess.Popen([sys.executable, "-c", "import os;print(os.getpid())"],
                         stdout=subprocess.PIPE, text=True)
dead_pid = int(child.communicate()[0].strip())
child.wait()
time.sleep(0.2)   # let the pid truly disappear before we claim it is dead

with open(FLAG, "w", encoding="utf-8") as fh:
    json.dump({"policy": "probe", "ts": time.time(), "pid": dead_pid, "expect": []}, fh)

print(f"poisoned {FLAG}")
print(f"  policy=probe ts=now (age 0 s, TTL 120) writer pid={dead_pid} (that process has exited)")

os.environ["PYTHONPATH"] = r"D:\new_automation;D:\new_automation\All codes"
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import popup_mode as pm  # noqa: E402
print(f"  popup_mode.current_policy() in THIS live process -> {pm.current_policy()!r}")
print("  (a live reader seeing 'probe' from a dead writer is the bug; 'task' is the fix)")
