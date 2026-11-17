import ast
import io

SUITE = "D:/new_automation/All codes/core_organs/si_tests_professor.py"
BLOCK = "D:/new_automation/scratch/p2_tests_block.py"

src = io.open(SUITE, "r", encoding="utf-8").read()
block = io.open(BLOCK, "r", encoding="utf-8").read()
ast.parse(block)
if "def run_pr34" in src:
    raise SystemExit("already spliced")
marker = "OFFLINE = [(\"PR1\", run_pr1)"
assert marker in src
src = src.replace(marker, block + marker, 1)
old_off = "(\"PR32\", run_pr32), (\"PR33\", run_pr33)]"
assert old_off in src
src = src.replace(old_off, "(\"PR32\", run_pr32), (\"PR33\", run_pr33),\n           (\"PR34\", run_pr34), (\"PR35\", run_pr35), (\"PR36\", run_pr36), (\"PR37\", run_pr37), (\"PR38\", run_pr38)]", 1)
old_live = "(\"PL8\", run_pl8), (\"PL9\", run_pl9)]"
assert old_live in src
src = src.replace(old_live, "(\"PL8\", run_pl8), (\"PL9\", run_pl9), (\"PL10\", run_pl10)]", 1)
ast.parse(src)
io.open(SUITE, "w", encoding="utf-8", newline="\n").write(src)
print("spliced ok", len(src.splitlines()), "lines")
