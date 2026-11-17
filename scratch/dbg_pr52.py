import sys
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes", "D:/new_automation/All codes/core_organs"]
import si_tests_apprun as T
r = T.run_pr52()
print(r.evidence)
