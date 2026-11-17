import sys
for p in (r"D:\new_automation", r"D:\new_automation\All codes", r"D:\new_automation\All codes\core_organs"):
    if p not in sys.path:
        sys.path.append(p)
from core_organs import si_tests_consolidate as C
bad = []
for n, f in C.TESTS:
    try:
        r = f()
        print(n, "PASS" if r.passed else "FAIL", r.metrics.get("checks"), flush=True)
        if not r.passed:
            bad.append((n, [x for x in r.evidence.split("; ") if x.endswith("=FAIL")][:4]))
    except Exception as e:
        print(n, "ERROR", type(e).__name__, str(e)[:120], flush=True)
        bad.append((n, str(e)[:100]))
print("FAILED:", bad)
print("REGRESS_DONE")
