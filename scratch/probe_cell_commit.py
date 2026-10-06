"""Probe 16: what COMMITS a cell write in a spreadsheet, measured on one screen.

The E2E run saved a real file whose sheet held nothing: the cell's UIA value read back '42', the app's own
document label said 'Saved' (never 'Edited'), and the workbook on disk had no text at all. So the write sits in
the in-cell editor and is thrown away when the file is written. This asks each candidate commit in turn and reads
the same two witnesses every time - the cell's value and the app's own dirty-state label.

Roads: (1) UIA SetValue alone  (2) SetValue then posted Enter  (3) UIA select the next cell (selection moves =
Excel ends the pending edit)  (4) select the cell, post the characters, post Enter (the human road, no UIA write).
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

from core_organs import background_window as bw                        # noqa: E402
from core_organs import headless_input as hin                          # noqa: E402
from core_organs.desktop_grounding import DesktopGrounding, get_loop, _act_on_element  # noqa: E402

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
print("hwnd", hwnd, "pid", p.pid, flush=True)
bw.mark_ours(hwnd)
time.sleep(6.0)

loop = get_loop()
print("[prepare]", loop._ensure_blank_document("excel"), flush=True)


def snap(tag):
    h, els, _rep = g.ground("excel", max_tier=2)
    h = int(h or 0)
    cells = {str(e.name).strip().upper(): (e.value or "") for e in els
             if e.role == "dataitem" and str(e.name).strip().upper() in ("A1", "B1", "C1")}
    dirty = [str(e.name) for e in els if any(w in (e.name or "").lower() for w in ("saved", "edited", "modified"))]
    editors = [str(e.name) for e in els if (e.name or "").lower() in ("edit cell", "formula bar")]
    print(f"[{tag}] title={hin.safe_window_text(h)!r} cells={cells} "
          f"dirty={dirty[:3]} editors={editors} n={len(els)}", flush=True)
    return h, els


def cell(els, ref):
    return next((e for e in els if e.role == "dataitem" and (e.name or "").strip().upper() == ref), None)


h, els = snap("base")

a1 = cell(els, "A1")
print("1 write only   :", _act_on_element(a1, "type", "42") if a1 else "no A1", flush=True)
time.sleep(1.0)
h, els = snap("after SetValue")

ok, how = hin.post_key_combo(h, "enter")
print("2 posted Enter :", ok, how, flush=True)
time.sleep(1.2)
h, els = snap("after Enter")

b1 = cell(els, "B1")
print("3 select B1    :", _act_on_element(b1, "click", "") if b1 else "no B1", flush=True)
time.sleep(1.2)
h, els = snap("after select B1")

a1 = cell(els, "A1")
print("4 select A1    :", _act_on_element(a1, "click", "") if a1 else "no A1", flush=True)
ok_pt, how_pt = hin.post_text(h, "777")
print("  post_text    :", ok_pt, how_pt, flush=True)
ok_en, how_en = hin.post_key_combo(h, "enter")
print("  post Enter   :", ok_en, how_en, flush=True)
time.sleep(1.5)
h, els = snap("after keys+Enter")

# does the app itself now think there is unsaved work? the document window's own label is the witness
print("names with the doc title:", [str(e.name)[:48] for e in els if "book" in (e.name or "").lower()][:6], flush=True)
from core_organs import universal_scan as us                           # noqa: E402
print("close:", us.close_window(h or hwnd, timeout_s=15.0, discard_unsaved=True), flush=True)
