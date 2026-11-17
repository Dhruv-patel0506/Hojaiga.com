import ast
import io

SUITE = "D:/new_automation/All codes/core_organs/si_tests_professor.py"
BLOCK = "D:/new_automation/scratch/p1_tests_block.py"

src = io.open(SUITE, "r", encoding="utf-8").read()
block = io.open(BLOCK, "r", encoding="utf-8").read()
ast.parse(block)
if "def run_pr28" in src:
    raise SystemExit("already spliced")
marker = "OFFLINE = [(\"PR1\", run_pr1)"
assert marker in src
src = src.replace(marker, block + marker, 1)
old_off = "(\"PR26\", run_pr26), (\"PR27\", run_pr27)]"
assert old_off in src
src = src.replace(old_off, "(\"PR26\", run_pr26), (\"PR27\", run_pr27),\n           (\"PR28\", run_pr28), (\"PR29\", run_pr29), (\"PR30\", run_pr30), (\"PR31\", run_pr31), (\"PR32\", run_pr32), (\"PR33\", run_pr33)]", 1)
old_live = "(\"PV2\", run_pv2), (\"PL7\", run_pl7)]"
assert old_live in src
src = src.replace(old_live, "(\"PV2\", run_pv2), (\"PL7\", run_pl7), (\"PL8\", run_pl8), (\"PL9\", run_pl9)]", 1)
ast.parse(src)
io.open(SUITE, "w", encoding="utf-8", newline="\n").write(src)
print("spliced ok", len(src.splitlines()), "lines")
