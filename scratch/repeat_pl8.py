import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes", "D:/new_automation/All codes/core_organs"]
from core_organs import si_tests_professor as T

n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
for i in range(n):
    r = T.run_pl8()
    bad = [c for c in r.evidence.split("|")[0].split(";") if "FAIL" in c]
    print(f"run {i + 1}: passed={r.passed} failed_checks={[b.strip() for b in bad]}", flush=True)
    if not r.passed:
        print("   ", r.evidence[:1800], flush=True)
    time.sleep(2)
