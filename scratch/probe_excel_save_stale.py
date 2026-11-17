"""Probe 6: two things the payroll run exposed.

  A  does F12 open the CLASSIC Save As dialog (which accepts a full path, unlike Office's
     native pane)?  Dump the dialog window title, class and its File-name edit + Save button.
  B  does a cached UIA control go stale mid-session? Read the Name Box, do something that
     rebuilds the tree (add/delete a sheet), then try the cached handle again and compare
     with a freshly resolved one. This decides whether the runner must self-heal.
"""
import subprocess
import sys
import time
from ctypes import windll, create_unicode_buffer
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


def cls(hwnd):
    b = create_unicode_buffer(256)
    windll.user32.GetClassNameW(int(hwnd), b, 256)
    return b.value


def snap(hwnd, cap=30000):
    return fast_uia.snapshot(hwnd, max_nodes=cap) or []


def find(ns, want, ctype=""):
    for n in ns:
        if want.lower() in str(n.name or "").lower() or want.lower() == str(n.aid or "").lower():
            if not ctype or ctype.lower() in n.ctype.lower():
                return n
    return None


proc = None
book = None
for h, t in headless_input.top_level_titles(visible_only=False):
    if "book" in (t or "").lower():
        book = int(h)
if book is None:
    proc = subprocess.Popen([EXE, "/n"], creationflags=0x00000200)
    for _ in range(30):
        time.sleep(1.5)
        for h, t in headless_input.top_level_titles(visible_only=False):
            if "book" in (t or "").lower():
                book = int(h)
                break
        if book:
            break
print("workbook hwnd:", book)
if book is None:
    sys.exit(1)

print("\nB  stale-control test ...")
ns = snap(book)
nb_cached = find(ns, "13", "combobox") or find(ns, "name box", "combobox")
print("   cached name box:", None if nb_cached is None else (nb_cached.ctype, nb_cached.aid))
try:
    nb_cached.ctrl.GetPattern(UIA_VALUE).SetValue("B4")
    headless_input.post_key_combo(book, "enter")
    print("   cached SetValue BEFORE tree change: OK")
except Exception as exc:
    print("   cached SetValue BEFORE:", type(exc).__name__, str(exc)[:70])
time.sleep(1.0)

# force a tree rebuild: add a sheet through the '+' tab, then remove it
plus = find(snap(book), "add new sheet") or find(snap(book), "insert worksheet")
print("   '+' sheet node:", None if plus is None else (plus.ctype, str(plus.name)[:24]))
if plus is not None:
    try:
        plus.ctrl.GetPattern(UIA_INVOKE).Invoke()
        print("   added a sheet; tree rebuilt")
    except Exception as exc:
        print("   add sheet failed:", type(exc).__name__, str(exc)[:60])
time.sleep(2.0)
try:
    nb_cached.ctrl.GetPattern(UIA_VALUE).SetValue("C5")
    headless_input.post_key_combo(book, "enter")
    print("   cached SetValue AFTER tree change: OK (handle still valid)")
except Exception as exc:
    print(f"   cached SetValue AFTER tree change: FAILED {type(exc).__name__}: {str(exc)[:70]}")
    fresh = find(snap(book), "13", "combobox")
    try:
        fresh.ctrl.GetPattern(UIA_VALUE).SetValue("C5")
        headless_input.post_key_combo(book, "enter")
        print("   freshly-resolved Name Box works -> self-heal by re-finding is viable")
    except Exception as exc2:
        print("   fresh also failed:", type(exc2).__name__, str(exc2)[:60])

print("\nA  F12 classic Save As dialog ...")
headless_input.post_key_combo(book, "f12")
time.sleep(3.0)
dlg = None
for h, t in headless_input.top_level_titles(visible_only=False):
    if "save as" in (t or "").lower():
        dlg = (int(h), t)
        break
if dlg is None:
    print("   no window titled 'Save As' appeared")
    for h, t in headless_input.top_level_titles(visible_only=False):
        print("     ", h, cls(h), repr(t)[:52])
else:
    print(f"   dialog hwnd={dlg[0]} class={cls(dlg[0])!r} title={dlg[1]!r}")
    dn = snap(dlg[0], 8000)
    print(f"   dialog UIA nodes: {len(dn)}")
    for n in dn:
        nm = str(n.name or "").strip()
        if any(k in nm.lower() for k in ("file name", "save as type", "save", "cancel", "directory", "file")):
            print("      ", n.ctype[:14], "|", nm[:34], "|", n.aid, "|", n.pats)
    fe = None
    for n in dn:
        if str(n.name or "").strip().lower().startswith("file name"):
            fe = n
            break
    if fe is not None:
        full = str(Path(r"D:\new_automation\scratch\_f12_probe.xlsx"))
        try:
            fe.ctrl.GetPattern(UIA_VALUE).SetValue(full)
            time.sleep(0.8)
            save_btn = None
            for n in (snap(dlg[0], 8000) or []):
                if str(n.name or "").strip().lower() in ("save", "save as") and "button" in n.ctype.lower():
                    save_btn = n
                    break
            print("   typed FULL path into the classic dialog; Save button found:", save_btn is not None)
            if save_btn is not None:
                try:
                    print("     Save enabled:", save_btn.enabled)
                    save_btn.ctrl.GetPattern(UIA_INVOKE).Invoke()
                    time.sleep(3.0)
                    print("     after Save, files on disk:",
                          [p.name for p in Path(r'D:\new_automation\scratch').glob('_f12_probe*')])
                    for h, t in headless_input.top_level_titles(visible_only=False):
                        if "f12_probe" in (t or "").lower():
                            print("     title now:", t)
                except Exception as exc:
                    print("     Invoke failed:", type(exc).__name__, str(exc)[:70])
        except Exception as exc:
            print("   SetValue failed:", type(exc).__name__, str(exc)[:70])

print("\ncleanup: close dialog/instance we own ...")
headless_input.post_key_combo(book, "alt+f4")
time.sleep(2.0)
for h, t in headless_input.top_level_titles(visible_only=False):
    if "microsoft excel" in (t or "").lower():
        for n in (snap(int(h), 4000) or []):
            if "don" in str(n.name or "").lower():
                try:
                    n.ctrl.GetPattern(UIA_INVOKE).Invoke()
                except Exception:
                    pass
                break
if proc is not None and proc.poll() is None:
    proc.terminate()
