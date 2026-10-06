"""Probe 14: does the judge actually SEE the grid, and does the cell branch fire?

The suite run typed into 'Formula Bar' instead of a cell, which means decisive()'s spreadsheet branch returned
None. Two possible reasons and this separates them: (a) no element carries role 'datagrid', (b) no element
carries a cell-reference name as 'dataitem' (the 120-cell sample may never include A1). Also asks the judge
the real goal and prints what it would do, without acting.
"""
import os
import subprocess
import sys
import time

os.environ.setdefault("PYTHONPATH", r"D:\new_automation;D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation\All codes")

EXE = next((p for p in (r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
                        r"C:\Program Files (x86)\Microsoft Office\root\Office16\EXCEL.EXE")
            if os.path.isfile(p)), None)
assert EXE, "no excel"

from core_organs import background_window as bw                       # noqa: E402
from core_organs.desktop_grounding import DesktopGrounding, ConstrainedJudge  # noqa: E402

g = DesktopGrounding()
if g.find_window("excel") is not None:
    print("REFUSE: an excel window is already open and is not ours")
    sys.exit(2)

p = subprocess.Popen([EXE])
hwnd = 0
for _ in range(60):
    time.sleep(0.5)
    h = g.find_window("excel")
    if h:
        hwnd = int(h)
        break
print("hwnd", hwnd, "pid", p.pid)
bw.mark_ours(hwnd)
time.sleep(6.0)

# leave the start screen exactly the way the loop now does, through the loop's own code
from core_organs.desktop_grounding import get_loop                    # noqa: E402
loop = get_loop()
note = loop._ensure_blank_document("excel")
print("[prepare]", note)

h, els, rep = g.ground("excel", max_tier=2)
roles = {}
for e in els:
    roles[e.role] = roles.get(e.role, 0) + 1
print("grounded", len(els), "roles:", sorted(roles.items(), key=lambda x: -x[1]))
print("walk stats:", getattr(g, "last_walk", None))
cells = [e for e in els if e.role == "dataitem"]
print("dataitem names:", [str(e.name)[:10] for e in cells][:20])
print("'A1' present:", any(str(e.name).strip().upper() == "A1" for e in cells))
print("datagrid present:", any(e.role == "datagrid" for e in els),
      [(str(e.name), e.bbox) for e in els if e.role in ("datagrid", "table")][:3])

goal = "type 42 in cell A1"
judge = ConstrainedJudge()
d = judge.decisive(goal, els)
print("\ndecisive ->", d if d is None else {k: d[k] for k in ("verb", "why", "element") if k in d})
top = judge.rank_scored(goal, els, None)[:6]
print("ranked:", [(round(s, 1), str(e.name)[:22], e.role) for s, _i, e in top])
print("_cell_target ->", judge._cell_target(goal, els))
print("_writable_surface ->", loop._writable_surface(els))

from core_organs import universal_scan as us                          # noqa: E402
print("close:", us.close_window(h or hwnd, timeout_s=10.0, discard_unsaved=True))
