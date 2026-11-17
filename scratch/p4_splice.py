import ast
import io

SUITE = "D:/new_automation/All codes/core_organs/si_tests_professor.py"
BLOCK = "D:/new_automation/scratch/p4_tests_block.py"

src = io.open(SUITE, "r", encoding="utf-8").read()
block = io.open(BLOCK, "r", encoding="utf-8").read()
ast.parse(block)
if "def run_pr40" in src:
    raise SystemExit("already spliced")
marker = "OFFLINE = [(\"PR1\", run_pr1)"
src = src.replace(marker, block + marker, 1)
old_off = "(\"PR38\", run_pr38), (\"PR39\", run_pr39)]"
assert old_off in src
src = src.replace(old_off, "(\"PR38\", run_pr38), (\"PR39\", run_pr39),\n           (\"PR40\", run_pr40), (\"PR41\", run_pr41), (\"PR42\", run_pr42), (\"PR43\", run_pr43), (\"PR44\", run_pr44)]", 1)
old_live = "(\"PL10\", run_pl10), (\"PL11\", run_pl11)]"
assert old_live in src
src = src.replace(old_live, "(\"PL10\", run_pl10), (\"PL11\", run_pl11), (\"PL12\", run_pl12), (\"PL13\", run_pl13)]", 1)
ast.parse(src)
io.open(SUITE, "w", encoding="utf-8", newline="\n").write(src)
print("spliced ok", len(src.splitlines()))
