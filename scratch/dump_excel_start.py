"""Dump every UIA node of the Excel start screen so the blank-workbook item can be named
correctly instead of guessed. Reads only; closes our own Excel at the end."""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(r"D:\new_automation\All codes")))
for s in (sys.stdout, sys.stderr):
    try:
        rc = getattr(s, "reconfigure", None)
        if callable(rc):
            rc(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core_organs import fast_uia, headless_input  # noqa: E402

EXE = r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE"

alive = [h for h, t in headless_input.top_level_titles(False) if (t or "").lower().endswith("excel")]
print("existing excel windows:", alive)
proc = None
if not alive:
    proc = subprocess.Popen([EXE, "/n"], creationflags=0x00000200)
    time.sleep(8)

for h, t in headless_input.top_level_titles(False):
    if (t or "").strip().lower() != "excel":
        continue
    ns = fast_uia.snapshot(h, max_nodes=20000) or []
    print(f"\n=== start screen hwnd={h} title={t!r} nodes={len(ns)} ===")
    for n in ns:
        if n.name or n.aid:
            print("  {:14s} | {:38s} | {:26s} | {}".format(
                n.ctype[:14], str(n.name)[:38], str(n.aid)[:26], ",".join(n.pats or [])))
    break

if proc is not None:
    proc.terminate()
    try:
        proc.wait(6)
    except Exception:
        proc.kill()
    print("\n(our excel instance closed)")
