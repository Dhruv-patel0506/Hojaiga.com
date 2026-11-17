"""Probe 4: lock down the three primitives an Excel runner needs, with evidence.

  P1  navigate by address through the Name Box (UIA value pattern) and PROVE selection moved
  P2  enter a value and commit with an explicit VK_TAB / VK_RETURN (not embedded \\t/\\n)
  P3  read the selected cell back out of the UIA tree (formula bar) -> per-step postcondition

Run against our own Excel instance; closed at the end without saving.
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

UIA_VALUE, UIA_INVOKE = 10002, 10000
EXE = r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE"


def snap(hwnd, cap=30000):
    return fast_uia.snapshot(hwnd, max_nodes=cap) or []


def edits(hwnd):
    return [n for n in snap(hwnd) if "edit" in n.ctype.lower() or "combo" in n.ctype.lower()]


def describe(hwnd, tag):
    print(f"   [{tag}] editable nodes:")
    for n in edits(hwnd):
        val = ""
        try:
            if "value" in (n.pats or []):
                val = str(n.ctrl.GetPattern(UIA_VALUE).Value)[:26]
        except Exception as exc:
            val = f"<{type(exc).__name__}>"
        print("      {:14s} aid={:10s} name={:28s} value={!r}".format(
            n.ctype[:14], str(n.aid)[:10], str(n.name)[:28], val))


def open_workbook():
    proc = subprocess.Popen([EXE, "/n"], creationflags=0x00000200)
    time.sleep(7)
    for _ in range(15):
        for h, t in headless_input.top_level_titles(visible_only=False):
            if "book" in (t or "").lower():
                return proc, h, t
        for h, t in headless_input.top_level_titles(visible_only=False):
            if (t or "").strip().lower() == "excel":
                for n in snap(h):
                    if "blank workbook" in str(n.name or "").lower():
                        try:
                            n.ctrl.GetPattern(UIA_INVOKE).Invoke()
                        except Exception as exc:
                            print("   invoke failed:", type(exc).__name__)
                        break
                break
        time.sleep(1.5)
    for h, t in headless_input.top_level_titles(visible_only=False):
        if "book" in (t or "").lower():
            return proc, h, t
    return proc, None, None


proc, book, title = open_workbook()
print(f"workbook hwnd={book} title={title!r}")
if not book:
    proc.terminate()
    sys.exit(1)

print("\nP1 Name Box navigation ...")
nb = None
for n in edits(book):
    if "name box" in str(n.name or "").lower():
        nb = n
        break
print("   name box node:", None if nb is None else (nb.ctype, nb.aid, nb.pats))
if nb is not None:
    for how in ("value", "type+enter"):
        try:
            if how == "value":
                nb.ctrl.GetPattern(UIA_VALUE).SetValue("D7")
                time.sleep(0.6)
                headless_input.post_key_combo(book, "enter")
            else:
                headless_input.post_key_combo(book, "escape")
                time.sleep(0.4)
                nb.ctrl.SetFocus()
                time.sleep(0.4)
                headless_input.post_text(book, "F9")
                time.sleep(0.4)
                headless_input.post_key_combo(book, "enter")
            time.sleep(1.2)
            describe(book, f"after {how}")
        except Exception as exc:
            print(f"   {how} failed: {type(exc).__name__} {str(exc)[:70]}")

print("\nP2 commit keys: value + TAB, value + ENTER ...")
headless_input.post_key_combo(book, "escape")
time.sleep(0.4)
try:
    nb.ctrl.GetPattern(UIA_VALUE).SetValue("A1")
    headless_input.post_key_combo(book, "enter")
except Exception as exc:
    print("   nav failed:", exc)
time.sleep(1.0)
for cell, payload in (("A1", "Alpha"), ("B1", "Beta"), ("C1", "=LEN(\"hello\")")):
    headless_input.post_text(book, payload)
    time.sleep(0.35)
    headless_input.post_key_combo(book, "tab")
    time.sleep(0.7)
describe(book, "after tab-chained entry")

print("\nP3 read each cell back through the formula bar ...")
for addr in ("A1", "B1", "C1"):
    try:
        nb.ctrl.GetPattern(UIA_VALUE).SetValue(addr)
        headless_input.post_key_combo(book, "enter")
    except Exception as exc:
        print("   nav err", exc)
    time.sleep(1.0)
    vals = []
    for n in edits(book):
        try:
            if "value" in (n.pats or []):
                v = str(n.ctrl.GetPattern(UIA_VALUE).Value or "")
                if v:
                    vals.append((str(n.name)[:16], v[:30]))
        except Exception:
            pass
    print(f"   {addr}: {vals}")

img, note, rung = headless_input.capture_window_robust(book)
if img is not None:
    out = Path(r"D:\new_automation\scratch\_excel_probe4.png")
    img.save(str(out))
    print(f"   proof -> {out} (rung={rung})")

print("\nclosing our instance without saving ...")
headless_input.post_key_combo(book, "alt+f4")
time.sleep(2.5)
for h, t in headless_input.top_level_titles(visible_only=False):
    if "microsoft excel" in (t or "").lower() or (t or "").lower().startswith("save"):
        for n in snap(h):
            if "don" in str(n.name or "").lower():
                try:
                    n.ctrl.GetPattern(UIA_INVOKE).Invoke()
                    print("   dismissed dialog via", n.name)
                except Exception as exc:
                    print("   dismiss failed:", type(exc).__name__)
                break
time.sleep(2.0)
if proc.poll() is None:
    proc.terminate()
    try:
        proc.wait(8)
    except Exception:
        proc.kill()
print("   alive:", proc.poll() is None)
