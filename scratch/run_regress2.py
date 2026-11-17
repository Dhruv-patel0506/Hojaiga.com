import sys
for p in (r"D:\new_automation", r"D:\new_automation\All codes", r"D:\new_automation\All codes\core_organs"):
    if p not in sys.path: sys.path.append(p)
import cv2
print("cv2", cv2.__file__, hasattr(cv2, "CascadeClassifier"))
from core_organs import si_tests_consolidate as C
for n, f in C.TESTS:
    if n in ("AR50", "AR51", "AR52", "AR53", "AR57", "AR58"):
        try:
            r = f(); print(n, "PASS" if r.passed else "FAIL", r.metrics.get("checks"), flush=True)
        except Exception as e:
            print(n, "ERROR", type(e).__name__, str(e)[:100], flush=True)
print("DONE2")
