import sys
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs import si_tests_gaps as G
for name in ("run_pr63", "run_pr64"):
    o = getattr(G, name)()
    print(name, "->", o)
