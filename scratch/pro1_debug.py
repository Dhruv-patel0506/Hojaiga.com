import sys, traceback
sys.path.insert(0, r"d:\new_automation\All codes")
sys.path.insert(0, r"d:\new_automation\All codes\core_organs")

from core_organs import si_tests_behavior as s


class TestOutcome:
    def __init__(self, passed, evidence="", metrics=None, env_blocked=False):
        self.passed, self.evidence = passed, evidence
        self.metrics, self.env_blocked = metrics or {}, env_blocked


# instrument: patch run_pro1 internals to dump the odd type
orig = s.run_pro1
try:
    out = orig(TestOutcome)
    print("passed=", out.passed)
    print("evidence=", out.evidence)
    print("metrics=", out.metrics)
except Exception:
    tb = traceback.format_exc()
    print(tb)
    et, ev, tr = sys.exc_info()
    import inspect
    fr = tr.tb_frame
    while tr.tb_next:
        tr = tr.tb_next
        fr = tr.tb_frame
    loc = fr.f_locals
    print("checks type:", type(loc.get("checks")))
    print("checks value:", repr(loc.get("checks"))[:400])
    print("order:", repr(loc.get("rationale"))[:200])
