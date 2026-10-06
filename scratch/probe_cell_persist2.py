"""Probe 18: which cell-write road puts the value INSIDE the saved file.

Probe 17 wrote '42' by UIA SetValue (the cell read back '42', then a posted Enter made it read '') and '55' by
opening the cell and typing; its save chain died on a transient COM error inside the dialog driver, so the file -
the only witness that cannot lie - was never produced. Here the save is driven directly (no judge, no LLM, the
dialog rung retried) and three roads are written into three different cells of ONE workbook:

  A  UIA SetValue on the cell                       (what the loop does today)
  D invoke the cell, post the characters, post Enter (the human road, no UIA write)
  E  UIA SetValue, then move the selection to a neighbour (a pending edit ended by focus change)

The file is then searched for each road's value.
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

TARGET = r"D:\new_automation\_e2e_tmp\hj_c18.xlsx"
if os.path.exists(TARGET):
    os.remove(TARGET)

from core_organs import background_window as bw                        # noqa: E402
from core_organs import headless_input as hin                          # noqa: E402
from core_organs.desktop_grounding import (DesktopGrounding, file_holds_text,  # noqa: E402
                                           get_loop, _act_on_element)

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
loop._hold_hidden("excel")


def els_now():
    h, e, _r = g.ground("excel", max_tier=2)
    return int(h or 0), e


def by_name(els, name, roles=None):
    return next((e for e in els if (e.name or "").strip().lower() == name
                 and (not roles or e.role in roles)), None)


def cell(els, ref):
    return next((e for e in els if e.role == "dataitem" and (e.name or "").strip().upper() == ref), None)


h, els = els_now()
maker = next((e for e in els if e.role in loop._NEW_DOC_ROLES
              and any(w in (e.name or "").lower() for w in loop._NEW_DOC_WORDS)), None)
print("creator:", _act_on_element(maker, "click", "") if maker else "none", flush=True)
time.sleep(3.0)
h, els = els_now()
print("document cells:", sum(1 for e in els if e.role == "dataitem"), "n:", len(els), flush=True)

# --- road A: UIA SetValue on A1, nothing else
print("A:", _act_on_element(cell(els, "A1"), "type", "42"), flush=True)
time.sleep(1.0)

# --- road D: open B1, type into it, Enter
h, els = els_now()
b1 = cell(els, "B1")
print("D invoke:", _act_on_element(b1, "click", ""), flush=True)
time.sleep(0.8)
print("D post_text:", hin.post_text(h, "55"), flush=True)
time.sleep(0.6)
print("D enter:", hin.post_key_combo(h, "enter"), flush=True)
time.sleep(1.2)

# --- road E: SetValue on C1 then move the selection to D1
h, els = els_now()
print("E:", _act_on_element(cell(els, "C1"), "type", "77"), flush=True)
time.sleep(0.8)
h, els = els_now()
d1 = cell(els, "D1")
print("E move selection:", _act_on_element(d1, "click", "") if d1 else "no D1", flush=True)
time.sleep(1.2)

h, els = els_now()
print("read-back:", {r: (cell(els, r).value if cell(els, r) else None) for r in ("A1", "B1", "C1", "D1")}, flush=True)

# --- deterministic save: File Tab -> Save As -> Browse -> dialog rung (retried), no model involved
for label, name, roles in (("File Tab", "file tab", ("button", "tabitem")),
                           ("Save As", "save as", ("listitem", "menuitem", "button", "tabitem")),
                           ("Browse", None, None)):
    h, els = els_now()
    if name == "browse" or name is None:
        target = next((e for e in els if (e.name or "").lower().startswith("browse")
                       and e.role in ("button", "hyperlink", "listitem")), None)
    else:
        target = by_name(els, name, roles)
    print(f"press {label or 'Browse'}:", _act_on_element(target, "click", "") if target else "NOT FOUND", flush=True)
    time.sleep(3.0)

ok = False
note = ""
for attempt in range(4):
    ok, note = loop.handle_native_file_dialog(TARGET, owner_hwnd=hwnd)
    print(f"dialog rung #{attempt + 1}: ok={ok} {note[:110]}", flush=True)
    if ok:
        break
    time.sleep(3.0)

for _ in range(20):
    if os.path.exists(TARGET):
        break
    time.sleep(1.0)
time.sleep(2.0)
print("file exists:", os.path.exists(TARGET), flush=True)
for probe in ("42", "55", "77"):
    print(f"file holds {probe!r}:", file_holds_text(TARGET, probe), flush=True)
from core_organs import universal_scan as us                           # noqa: E402
print("close:", us.close_window(h or hwnd, timeout_s=20.0, discard_unsaved=True), flush=True)
