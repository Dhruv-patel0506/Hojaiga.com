"""Diagnose the stalled Excel session: is a modal in the way, is the tree empty, and what
does the window actually contain right now? Read-only, plus one screenshot for proof."""
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


def cls(hwnd):
    b = create_unicode_buffer(256)
    windll.user32.GetClassNameW(int(hwnd), b, 256)
    return b.value


def txt(hwnd):
    b = create_unicode_buffer(512)
    windll.user32.GetWindowTextW(int(hwnd), b, 512)
    return b.value


print("=== all top-level windows that look like Excel or a dialog ===")
book = None
for h, t in headless_input.top_level_titles(visible_only=False):
    tl = (t or "").lower()
    if "excel" in tl or "save as" in tl or "microsoft" in tl or "error" in tl or "alert" in tl:
        vis = windll.user32.IsWindowVisible(int(h))
        print(f"  hwnd={h:9d} vis={vis} class={cls(h)!r:26s} title={t!r}")
        if tl.endswith("- excel") and "book" in tl:
            book = int(h)

print("\n=== foreground window ===")
fg = windll.user32.GetForegroundWindow()
print(f"  hwnd={fg} class={cls(fg)!r} title={txt(fg)!r}")

if book:
    print(f"\n=== workbook hwnd={book} ===")
    for attempt in (1, 2):
        t0 = time.time()
        ns = fast_uia.snapshot(book, max_nodes=30000) or []
        print(f"  snapshot attempt {attempt}: {len(ns)} nodes in {time.time() - t0:.2f}s")
        time.sleep(1.0)
    tabs = [str(n.name) for n in (fast_uia.snapshot(book, max_nodes=30000) or [])
            if "tabitem" in n.ctype.lower()]
    print(f"  tab items ({len(tabs)}): {tabs[:22]}")
    sel = [f"{n.name}(sel={n.selected})" for n in (fast_uia.snapshot(book, max_nodes=30000) or [])
           if "tabitem" in n.ctype.lower() and n.selected]
    print(f"  selected tabs: {sel}")
    fb = [n for n in (fast_uia.snapshot(book, max_nodes=30000) or [])
          if str(n.aid or "").lower() == "formulabar"]
    print(f"  formula bar nodes: {len(fb)}")
    if fb:
        try:
            print("     live text:", repr(str(fb[0].ctrl.GetPattern(10014).DocumentRange.GetText(-1)))[:60])
        except Exception as exc:
            print("     read failed:", type(exc).__name__, str(exc)[:60])
    pops = headless_input.popup_windows(book)
    print(f"  popup_windows(): {len(pops)}")
    for p in pops[:6]:
        print(f"     popup hwnd={p} class={cls(int(p))!r} title={txt(int(p))!r}")
    cells = [n for n in (fast_uia.snapshot(book, max_nodes=30000) or [])
             if n.ctype == "DataItemControl" and str(n.name or "")]
    print(f"  data items with a name: {len(cells)}")
    img, note, rung = headless_input.capture_window_robust(book)
    if img is not None:
        out = Path(r"D:\new_automation\scratch\_excel_diagnose.png")
        img.save(str(out))
        print(f"  screenshot -> {out} (rung={rung})")
    else:
        print("  screenshot failed:", str(note)[:80])
else:
    print("no workbook window found at all")
