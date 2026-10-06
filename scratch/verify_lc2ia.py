import sys, time
from dataclasses import dataclass, field
from typing import Any, Dict

sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation\All codes\core_organs")


@dataclass
class TestOutcome:
    passed: bool
    evidence: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    env_blocked: bool = False


def main():
    from core_organs import si_tests_knowledge as k
    t0 = time.time()
    r = k.run_lc2ia(TestOutcome)
    print(f"passed={r.passed} env_blocked={r.env_blocked} ({time.time()-t0:.1f}s)")
    print("EVIDENCE:", r.evidence)
    print("METRICS:", r.metrics)


main()
