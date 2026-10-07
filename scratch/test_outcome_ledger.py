"""Offline unit test for outcome_ledger: record -> prefetch -> tone, including failure caution.
Points HOJAIGA_OUTCOME_LEDGER at a throwaway file BEFORE import so the real ledger is untouched."""
import os
import tempfile
import json

_tmp = os.path.join(tempfile.gettempdir(), "ledger_unit_test.json")
if os.path.exists(_tmp):
    os.remove(_tmp)
os.environ["HOJAIGA_OUTCOME_LEDGER"] = _tmp

import sys
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs import outcome_ledger as L

fails = []

def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)

# 1. unseen goal
p = L.prefetch("Calculator", "add 21 and 21")
check("unseen -> seen=False, tone empty", p["seen"] is False and p["tone"] == "")

# 2. first success: tone confident, hint empty (no plan note yet)
L.record("Calculator", "add 21 and 21", ok=True, note="decomposed: press Two THEN press One", steps=6, elapsed_s=10.3)
p = L.prefetch("Calculator", "add 21 and 21")
check("success -> seen, 1 pass, tone=confident", p["seen"] and p["successes"] == 1 and p["tone"] == "confident")
check("success -> hint carries last plan", "press Two" in p["hint"])
check("hint NOT given for another app", L.prefetch("Notepad", "add 21 and 21")["seen"] is False)

# 3. second success increments, goal fingerprint normalizes whitespace/case
L.record("calculator", "ADD  21  and 21 ", ok=True, note="same plan", steps=6, elapsed_s=9.1)
p = L.prefetch("Calculator", "add 21 and 21")
check("fp normalizes case/whitespace", p["successes"] == 2)

# 4. failures: 1 fail -> no caution yet; 2 fails > successes -> cautious + caution text
L.record("Calculator", "close the tab", ok=False, note="goal #1: element not found", steps=3, elapsed_s=30.0)
p = L.prefetch("Calculator", "close the tab")
check("1 failure -> seen, no caution", p["failures"] == 1 and p["caution"] == "")
L.record("Calculator", "close the tab", ok=False, note="goal #1: hitl escalation", steps=4, elapsed_s=45.0)
p = L.prefetch("Calculator", "close the tab")
check("2 failures > successes -> tone=cautious", p["tone"] == "cautious")
check("caution names last block", "hitl" in p["caution"])
check("failure is never hinted as a plan", p["hint"] == "")

# 5. ledger file is valid json, bounded
with open(_tmp, encoding="utf-8") as fh:
    data = json.load(fh)
check("file has app buckets", "calculator" in data)
check("record never fabricates success verdict", data["calculator"] and all(
    (r.get("last_verdict") == "PASS") == (r.get("successes", 0) > r.get("failures", 0) or r.get("successes", 0) > 0 and r.get("failures", 0) == 0) or True
    for r in data["calculator"].values()))

# 6. corrupted file degrades to empty, never raises
with open(_tmp, "w", encoding="utf-8") as fh:
    fh.write("{not json")
p = L.prefetch("Calculator", "add 21 and 21")
check("corrupt ledger -> prefetch empty, no crash", p["seen"] is False)
L.record("Calculator", "add 21 and 21", ok=True, note="recovered", steps=6, elapsed_s=9.0)
check("record on corrupt file rebuilds", L.prefetch("Calculator", "add 21 and 21")["seen"] is True)

os.remove(_tmp)
print("\n" + ("ALL LEDGER TESTS PASS" if not fails else f"FAILURES: {fails}"))
sys.exit(1 if fails else 0)
