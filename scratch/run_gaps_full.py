import sys
import traceback

sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs import si_tests_gaps as G

ok = bad = 0
for name, fn in G.TESTS:
    try:
        res = fn()
    except Exception as exc:
        print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=2)
        bad += 1
        continue
    s = getattr(res, "ok", None)
    if s is None:
        s = str(res)
    passed = bool(res) if isinstance(res, (bool, int)) else ("FAIL" not in str(res))
    print(("[PASS] " if passed else "[FAIL] ") + name + " " + str(res)[:100].replace("\n", " "))
    ok += 1 if passed else 0
    bad += 0 if passed else 1
print(f"gaps: {ok} passed, {bad} failed of {len(G.TESTS)}")
sys.exit(1 if bad else 0)
