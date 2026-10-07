"""Deterministic smoke of quality_loop (item [7]): scoring, bounded retry, plan carry, early stop, NOT_DONE."""
import sys, os
sys.path.insert(0, r"d:\new_automation\All codes")
sys.path.insert(0, r"d:\new_automation\All codes\core_organs")
os.environ.setdefault("HOJAIGA_WEBAPP_WATCH", "0")

from core_organs import quality_loop as ql

# --- loop that improves: fail, fail-with-progress, then meet the postcondition
state = {"written": ""}
calls = []

def executor(attempt, prev):
    calls.append((attempt, str(prev.get("last_plan") or "")[:40]))
    if attempt == 1:
        state["written"] = "half"
    elif attempt == 2:
        state["written"] = "half+more"
    else:
        state["written"] = "exact"
    return {"success": True}

loop = ql.QualityLoop(
    "produce exact output",
    [ql.Check("nonempty", lambda c: bool(state["written"])),
     ql.Check("exact", lambda c: state["written"] == "exact")],
    max_attempts=4,
    planner=lambda goal, rnd, a: f"unmet postconditions: {', '.join(rnd.failed)}")
rep = loop.run(executor)
print("report1:", rep["status"], rep["scores"], [a["delta"] for a in rep["attempts"]])
assert rep["status"] == "DONE" and rep["scores"] == [0.5, 0.5, 1.0], rep
assert rep["attempts"][1]["plan"].startswith("unmet"), rep["attempts"][1]
assert calls[1][1].startswith("unmet"), calls  # attempt 2 actually RECEIVED the plan
print("P-A carry+improve OK")

# --- loop that cannot improve: early stop + honest NOT_DONE
loop2 = ql.QualityLoop("never met",
                       [ql.Check("always", lambda c: True), ql.Check("never", lambda c: False)],
                       max_attempts=5,
                       planner=lambda goal, rnd, a: "static: " + ",".join(rnd.failed))
rep2 = loop2.run(lambda a, p: {"success": True})
print("report2:", rep2["status"], rep2["scores"], rep2["final_gaps"], str(rep2["self_relied_on"])[:90])
assert rep2["status"] == "NOT_DONE" and len(rep2["attempts"]) == 3 and "never" in rep2["final_gaps"]
assert "stopped_early" in rep2["self_relied_on"]
print("P-B honesty OK")

# --- bound exhaustion without improvement-stop: only 2 checks but delta rises each time -> runs to bound
prog = {"i": 0}
def exec3(a, p):
    prog["i"] = a
    return {"success": True}
loop3 = ql.QualityLoop("graded goal",
                       [ql.Check(f"c{i}", (lambda i: (lambda c: prog["i"] > i))(i)) for i in range(4)],
                       max_attempts=3, planner=lambda g, r, a: "unmet: x")
rep3 = loop3.run(exec3)
print("report3:", rep3["status"], rep3["scores"])
assert rep3["status"] == "NOT_DONE" and len(rep3["attempts"]) == 3 and rep3["scores"] == [0.25, 0.5, 0.75]
print("P-C bounded NOT_DONE OK")

# --- ledger (organ_01 hook)
led = ql.AttemptLedger("open calc and compute", 1)
led.record(1, 0, "FAILURE: lazy")
led.record(2, 0, "FAILURE: still lazy")
led.record(3, 1, "ok")
r = led.report()
print("ledger:", r["scores"], r["each_better_than_last"], r["final"])
assert r["scores"] == [0.0, 0.0, 1.0] and r["each_better_than_last"] and r["final"].startswith("MET")

# --- popup integration present but degraded honestly with no owner
loop4 = ql.QualityLoop("g", [ql.Check("x", lambda c: True)], max_attempts=1)
rep4 = loop4.run(lambda a, p: {})
print("report4:", rep4["status"], rep4["tiers_used"], str(rep4["self_relied_on"])[:80])
assert rep4["status"] == "DONE" and "popup_round" not in str(rep4["self_relied_on"])
print("SMOKE_DONE")
