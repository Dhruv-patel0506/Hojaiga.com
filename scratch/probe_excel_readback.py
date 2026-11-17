"""Probe 5: which UIA pattern actually READS a cell's content out of Excel?

Types a known value into A1, then tries every candidate read on the Formula Bar and the
Name Box: ValuePattern, TextPattern, LegacyIAccessible, the node's Name, and an OCR crop of
the formula-bar strip. Prints which one returns the truth.
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

UIA_VALUE, UIA_TEXT, UIA_LEGACY, UIA_INVOKE = 10002, 10014, 10018, 10000
EXE = r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE"
SENTINEL = "Alpha"


def snap(hwnd, cap=30000):
    return fast_uia.snapshot(hwnd, max_nodes=cap) or []


def by_aid(hwnd, aid):
    for n in snap(hwnd):
        if str(n.aid or "").lower() == aid.lower():
            return n
    return None


proc = subprocess.Popen([EXE, "/n"], creationflags=0x00000200)
time.sleep(7)
book = None
for _ in range(18):
    for h, t in headless_input.top_level_titles(visible_only=False):
        if "book" in (t or "").lower():
            book = h
            break
    if book:
        break
    for h, t in headless_input.top_level_titles(visible_only=False):
        if (t or "").strip().lower() == "excel":
            for n in snap(h):
                if "blank workbook" in str(n.name or "").lower():
                    try:
                        n.ctrl.GetPattern(UIA_INVOKE).Invoke()
                    except Exception:
                        pass
                    break
            break
    time.sleep(1.5)
print("workbook hwnd:", book)
if not book:
    proc.terminate()
    sys.exit(1)

# put a known value in A1 using the primitives that probe 4 proved work
headless_input.post_key_combo(book, "ctrl+home")
time.sleep(1.0)
headless_input.post_text(book, SENTINEL)
time.sleep(0.5)
headless_input.post_key_combo(book, "enter")
time.sleep(1.2)
headless_input.post_key_combo(book, "up")
time.sleep(1.0)

fb = by_aid(book, "FormulaBar")
nb = by_aid(book, "1001")
print(f"formula bar node: {None if fb is None else (fb.ctype, fb.pats)}")
print(f"name box node   : {None if nb is None else (nb.ctype, nb.pats)}")


def reads(node, tag):
    if node is None:
        print(f"   {tag}: node missing")
        return
    out = {"name": str(node.name or "")[:40]}
    for label, pid in (("value", UIA_VALUE), ("legacy", UIA_LEGACY)):
        try:
            p = node.ctrl.GetPattern(pid)
            v = getattr(p, "Value", None)
            out[label] = str(v)[:40] if v is not None else ""
        except Exception as exc:
            out[label] = f"<{type(exc).__name__}>"
    try:
        tp = node.ctrl.GetPattern(UIA_TEXT)
        out["text"] = str(tp.DocumentRange.GetText(-1))[:40]
    except Exception as exc:
        out["text"] = f"<{type(exc).__name__}>"
    try:
        tp = node.ctrl.GetPattern(UIA_TEXT)
        out["text_visible"] = str(tp.GetVisibleText())[:40]
    except Exception as exc:
        out["text_visible"] = f"<{type(exc).__name__}>"
    print(f"   {tag}: {out}")
    hit = [k for k, v in out.items() if SENTINEL in str(v)]
    print(f"      -> reads containing {SENTINEL!r}: {hit or 'NONE'}")


print("\nreads while A1 is selected:")
reads(fb, "FormulaBar")
reads(nb, "NameBox(1001)")

img, note, rung = headless_input.capture_window_robust(book)
if img is not None:
    out = Path(r"D:\new_automation\scratch\_excel_probe5.png")
    img.save(str(out))
    try:
        import pytesseract
        w, h = img.size
        crop = img.crop((int(w * 0.20), int(h * 0.22), w, int(h * 0.27)))
        txt = pytesseract.image_to_string(crop, config="--psm 7").strip()
        print(f"   OCR of the formula-bar strip -> {txt[:60]!r}")
    except Exception as exc:
        print("   OCR failed:", type(exc).__name__, str(exc)[:60])

print("\nclosing our instance ...")
headless_input.post_key_combo(book, "alt+f4")
time.sleep(2.0)
for h, t in headless_input.top_level_titles(visible_only=False):
    if "microsoft excel" in (t or "").lower():
        for n in snap(h):
            if "don" in str(n.name or "").lower():
                try:
                    n.ctrl.GetPattern(UIA_INVOKE).Invoke()
                except Exception:
                    pass
                break
time.sleep(1.5)
if proc.poll() is None:
    proc.terminate()
    try:
        proc.wait(6)
    except Exception:
        proc.kill()
print("alive:", proc.poll() is None)
