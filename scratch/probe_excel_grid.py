"""Probe 3: reach a real Excel WORKBOOK and answer the four decisive questions.

  Q1  reach Book1 from the start screen through UIA (Invoke 'Blank workbook')
  Q2  can a TAB/NEWLINE block be POSTED into the grid (no physical cursor) and land in cells?
  Q3  does UIA expose cell contents so a step can be verified from the tree?
  Q4  does a typed FORMULA come back with its computed value?

Posted-message input only. Our own instance is closed at the end (dialog dismissed with
'Don't Save'), nothing user-owned is touched.
"""
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

UIA_INVOKE, UIA_VALUE, UIA_SELECT_ITEM = 10000, 10002, 10007
EXE = r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE"


def snap(hwnd, cap=30000):
    return fast_uia.snapshot(hwnd, max_nodes=cap) or []


def find(hwnd_want, titles=None):
    for h, t in headless_input.top_level_titles(visible_only=False):
        if hwnd_want in (t or "").lower():
            return h, t
    return None, None


def node_by(hwnd, want, ctype="listitem"):
    want = want.lower()
    for n in snap(hwnd):
        if want in str(n.name or "").lower() and ctype.lower() in n.ctype.lower():
            return n
    return None


print("Q1 launch + reach a workbook ...")
proc = subprocess.Popen([EXE, "/n"], creationflags=0x00000200)
time.sleep(7)
book, btitle = find("book")
if not book:
    sh, st = find("excel")
    sh = sh or (proc.pid and None)
    for h, t in headless_input.top_level_titles(visible_only=False):
        if (t or "").strip().lower() == "excel":
            sh = h
            break
    n = node_by(sh, "Blank workbook") if sh else None
    print("   start screen hwnd:", sh, "-> 'Blank workbook' node:", None if n is None else n.ctype)
    if n is not None:
        try:
            n.ctrl.GetPattern(UIA_INVOKE).Invoke()
            print("   Invoked 'Blank workbook'")
        except Exception as exc:
            print("   Invoke failed:", type(exc).__name__, str(exc)[:80])
    for _ in range(20):
        time.sleep(1.0)
        book, btitle = find("book")
        if book:
            break
if not book:
    print("   RESULT: workbook window never appeared")
    proc.terminate()
    sys.exit(1)
print(f"   workbook hwnd={book} title={btitle!r}")

nodes = snap(book)
print(f"   workbook UIA nodes: {len(nodes)}")
types = {}
for x in nodes:
    types[x.ctype] = types.get(x.ctype, 0) + 1
print("   types:", dict(sorted(types.items(), key=lambda kv: -kv[1])[:12]))
cells = [x for x in nodes if x.ctype in ("DataItemControl", "CustomControl")]
print(f"   grid-ish nodes (DataItem/Custom): {len(cells)}")
for x in cells[:12]:
    print("      ", x.ctype[:12], "|", str(x.name)[:48], "|", x.pats)

print("\nQ2 post a TAB/NEWLINE block into the grid ...")
headless_input.post_key_combo(book, "ctrl+home")
time.sleep(1.0)
block = "SENT_A1\tSENT_B1\nSENT_A2\t=21+21\n"
ok, note = headless_input.post_text(book, block)
print("   post_text(block) ->", ok, note[:80])
time.sleep(2.0)
after = snap(book)
print(f"   nodes now: {len(after)}")
for want in ("SENT_A1", "SENT_B1", "SENT_A2", "42"):
    got = [str(n.name)[:60] for n in after if want in str(n.name or "")]
    print(f"   read back {want!r}: {got[:2] if got else 'NOT VISIBLE IN UIA'}")

print("\nQ4 explicit formula cell ...")
headless_input.post_key_combo(book, "ctrl+home")
time.sleep(0.8)
headless_input.post_key_combo(book, "down")
headless_input.post_key_combo(book, "down")
time.sleep(0.6)
headless_input.post_text(book, "=SUM(C1:D1)")
time.sleep(0.4)
headless_input.post_key_combo(book, "enter")
time.sleep(1.6)
after = snap(book)
hits = [str(n.name)[:70] for n in after if "SUM" in str(n.name or "") or "42" in str(n.name or "")]
print("   cells mentioning SUM / 42:", hits[:4])

img, capnote, rung = headless_input.capture_window_robust(book)
if img is not None:
    out = Path(r"D:\new_automation\scratch\_excel_probe_grid.png")
    img.save(str(out))
    print(f"   proof screenshot -> {out} (rung={rung}, {img.size})")
else:
    print("   screenshot failed:", str(capnote)[:60])

print("\nclose our instance, dismissing the unsaved-changes dialog with 'Don't Save' ...")
headless_input.post_key_combo(book, "alt+f4")
time.sleep(2.5)
for h, t in headless_input.top_level_titles(visible_only=False):
    tl = (t or "").lower()
    if "save" in tl or "microsoft excel" == tl.strip():
        print("   dialog:", t)
        for n in snap(h):
            if "don" in str(n.name or "").lower() and "save" in str(n.name or "").lower():
                try:
                    n.ctrl.GetPattern(UIA_INVOKE).Invoke()
                    print("     pressed 'Don't Save'")
                except Exception as exc:
                    print("     failed:", type(exc).__name__)
                break
time.sleep(2.0)
if proc.poll() is None:
    proc.terminate()
    try:
        proc.wait(8)
    except Exception:
        proc.kill()
print("   excel alive:", proc.poll() is None)
