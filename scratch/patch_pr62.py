import ast
import io

t = io.open("D:/new_automation/scratch/pr62.txt", "r", encoding="utf-8").read()
T = "D:/new_automation/All codes/core_organs/si_tests_apprun.py"
f = io.open(T, "r", encoding="utf-8").read()
assert "run_pr62" not in f
f = f.replace('\nTESTS = [("PR49"', "\n" + t + '\nTESTS = [("PR49"', 1)
f = f.replace('("PR61", run_pr61)]', '("PR61", run_pr61), ("PR62", run_pr62)]', 1)
ast.parse(f)
io.open(T, "w", encoding="utf-8", newline="\n").write(f)
print("ok")
