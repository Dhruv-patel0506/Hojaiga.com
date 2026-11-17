import sys
for p in (r"D:\new_automation", r"D:\new_automation\All codes", r"D:\new_automation\All codes\core_organs"):
    if p not in sys.path:
        sys.path.append(p)
from core_organs import si_tests_consolidate as C
for n, f in C.TESTS:
    if n in ("AR60", "AR62"):
        r = f()
        print(n, "PASS" if r.passed else "FAIL", r.metrics.get("checks"), [x for x in r.evidence.split("; ") if x.endswith("=FAIL")][:3], flush=True)
print("DONE3")
