import ast
import io

SUITE = "D:/new_automation/All codes/core_organs/si_tests_professor.py"
BLOCK = "D:/new_automation/scratch/p5_tests_block.py"

src = io.open(SUITE, "r", encoding="utf-8").read()
block = io.open(BLOCK, "r", encoding="utf-8").read()
ast.parse(block)
if "def run_pr45" in src:
    raise SystemExit("already spliced")
marker = "OFFLINE = [(\"PR1\", run_pr1)"
src = src.replace(marker, block + marker, 1)
old_off = "(\"PR43\", run_pr43), (\"PR44\", run_pr44)]"
assert old_off in src
src = src.replace(old_off, "(\"PR43\", run_pr43), (\"PR44\", run_pr44),\n           (\"PR45\", run_pr45), (\"PR46\", run_pr46), (\"PR47\", run_pr47), (\"PR48\", run_pr48)]", 1)
ast.parse(src)
io.open(SUITE, "w", encoding="utf-8", newline="\n").write(src)
print("spliced ok", len(src.splitlines()))
