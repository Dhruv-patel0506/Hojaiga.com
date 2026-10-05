"""
si_day_stub.py -- scripted executor + verifier for the day-runner crash/resume test (DAY2). Importable from a subprocess so the test
can kill a REAL process mid-ticket. Every execution is appended to HJ_DAY_COUNTER (the independent ground truth of what ran).
Behaviour is chosen by the ticket id: 'b' dies hard (os._exit) the first time, 'c' raises, 'e' hangs, 'g' claims DONE falsely.
"""

import os
import time


def _log(task_id: str) -> int:
    path = os.environ["HJ_DAY_COUNTER"]
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(task_id + "\n")
    with open(path, encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip() == task_id)


def executor(task):
    tid = task["id"]
    n = _log(tid)
    if tid == os.environ.get("HJ_DAY_KILL_AT") and n == 1:
        os._exit(9)                                    # a hard kill: no cleanup, no finally, the ticket stays RUNNING
    if tid == "c":
        raise RuntimeError("scripted failure")
    if tid == "e":
        time.sleep(30)
    return {"status": "DONE", "evidence": f"scripted DONE for {tid} (execution #{n})"}


def verify(task, result):
    if task["id"] == "g":
        return False, "the output file is not on disk"
    return True, "independent check passed"
