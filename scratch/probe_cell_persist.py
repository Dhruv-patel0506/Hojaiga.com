"""Probe 17: (1) what the start screen offers as a 'surface', (2) which write road actually PERSISTS.

Why: the E2E run saved a real 8 KB workbook whose sheet held nothing, while the cell's UIA value read back '42'.
So a UIA cell write is pending text in the in-cell editor, and the file is written before it is committed. Also:
this probe's predecessor found a writable surface on a start screen that had none, so every text-role control on
that screen is dumped with its rectangle - the geometry decides, not an app name.

The answer is read from the file itself, which is the only witness that cannot lie: write by road A, write by road
D, save once, then look for each value inside the workbook.
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

TARGET = r"D:\new_automation\_e2e_tmp\hj_c17.xlsx"
try:
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
except Exception:
    pass
if os.path.exists(TARGET):
    os.remove(TARGET)

from core_organs import background_window as bw                        # noqa: E402
from core_organs import headless_input as hin                          # noqa: E402
from core_organs.desktop_grounding import (DesktopGrounding, ConstrainedJudge, file_holds_text,  # noqa: E402
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


def snap(tag):
    h, els, _rep = g.ground("excel", max_tier=2)
    h = int(h or 0)
    want = {"A1": "", "B1": "", "C1": ""}
    for e in els:
        key = (e.name or "").strip().upper()
        if e.role == "dataitem" and key in want:
            want[key] = e.value or ""
    state = [str(e.name)[:40] for e in els
             if any(w in (e.name or "").lower() for w in ("saved", "edited", "modified", "book1"))]
    strip = [(str(e.name)[:20], e.role, e.bbox) for e in els if e.role in ConstrainedJudge._TEXT_ROLES]
    print(f"[{tag}] cells={want} state={state[:3]} texts={strip[:6]} n={len(els)}", flush=True)
    return h, els


def cell(els, ref):
    return next((e for e in els if e.role == "dataitem" and (e.name or "").strip().upper() == ref), None)


# ---- (1) the start screen's own text-role geometry: does anything on it look like a canvas? ----
_h0, els0 = snap("start screen")
maker = next((e for e in els0 if e.role in loop._NEW_DOC_ROLES
              and any(w in (e.name or "").lower() for w in loop._NEW_DOC_WORDS)), None)
print("surface count as the rung sees it:", loop._writable_surface(els0),
      "maker:", (maker.name, maker.role) if maker else None, flush=True)
print("press creator:", _act_on_element(maker, "click", "") if maker else "no creator", flush=True)
time.sleep(2.5)

# ---- (2) two write roads, then ONE save, then the file is the witness ----
h, els = snap("document")
a1 = cell(els, "A1")
print("road A (UIA SetValue '42'):", _act_on_element(a1, "type", "42") if a1 else "no A1", flush=True)
time.sleep(1.2)
h, els = snap("after road A")
ok_en, how_en = hin.post_key_combo(h, "enter")
print("  posted Enter:", ok_en, how_en, flush=True)
time.sleep(1.2)
h, els = snap("after Enter")

a1 = cell(els, "A1")
print("road D (select A1 + typed keys '55'):", _act_on_element(a1, "click", "") if a1 else "no A1", flush=True)
ok_pt, how_pt = hin.post_text(h, "55")
ok_en2, how_en2 = hin.post_key_combo(h, "enter")
print("  post_text:", ok_pt, how_pt, "| post Enter:", ok_en2, how_en2, flush=True)
time.sleep(1.5)
h, els = snap("after road D")

print("---- save through the loop's own flow ----", flush=True)
res = loop.run([f"save the workbook as {TARGET}"], "excel", max_steps_per_goal=4,
               expect_map={0: {"file_created": TARGET}}, allow_destructive=False)
print("run:", {k: res.get(k) for k in ("completed", "blocked_at_goal", "steps")}, flush=True)
print("file exists:", os.path.exists(TARGET), flush=True)
for probe in ("42", "55"):
    print(f"file holds {probe!r}:", file_holds_text(TARGET, probe), flush=True)
from core_organs import universal_scan as us                           # noqa: E402
print("close:", us.close_window(h or hwnd, timeout_s=15.0, discard_unsaved=True), flush=True)
