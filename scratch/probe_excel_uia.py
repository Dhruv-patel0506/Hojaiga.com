"""Probe: what does the live UIA tree + window class chain of Microsoft Excel actually expose?
Launches our own Excel instance, snapshots, prints the truth, and closes it again."""
import subprocess
import sys
import time
from ctypes import windll
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


def classes(hwnd, depth=0, out=None):
    """The raw Win32 class chain: where the document surface lives decides where keys go."""
    from ctypes import create_unicode_buffer
    out = [] if out is None else out
    b = create_unicode_buffer(256)
    windll.user32.GetClassNameW(int(hwnd), b, 256)
    t = create_unicode_buffer(512)
    windll.user32.GetWindowTextW(int(hwnd), t, 512)
    out.append(("  " * depth, int(hwnd), b.value, t.value[:60]))
    child = windll.user32.GetWindow(int(hwnd), 5)  # GW_CHILD
    while child:
        classes(child, depth + 1, out)
        child = windll.user32.GetWindow(child, 2)  # GW_HWNDNEXT
    return out


exe = r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE"
print("launching Excel /n ...")
proc = subprocess.Popen([exe, "/n"], creationflags=0x00000200)
hwnd, title = None, None
for i in range(60):
    time.sleep(1.0)
    for h, t in headless_input.top_level_titles(visible_only=False):
        tl = (t or "").lower()
        if "excel" in tl and ("book" in tl or "sheet" in tl or "excel" == tl.strip()):
            hwnd, title = h, t
            break
    if hwnd:
        break
    if i % 10 == 9:
        print(f"  still waiting... seen={[t for _, t in headless_input.top_level_titles(False)][:8]}")
if not hwnd:
    print("NO EXCEL WINDOW FOUND")
    sys.exit(1)
print(f"target hwnd={hwnd} title={title!r} pid={proc.pid}")

t0 = time.time()
nodes = fast_uia.snapshot(hwnd, max_nodes=20000) or []
print(f"UIA nodes: {len(nodes)} in {time.time() - t0:.1f}s")

INTERESTING = ("name box", "formula", "grid", "sheet", "home", "insert", "page layout",
               "file tab", "cell", "a1", "b2", "save", "ribbon", "command", "sum")
hits, types, pats = [], {}, {}
for n in nodes:
    nm = str(getattr(n, "name", "") or "")
    ct = str(getattr(n, "ctype", "") or "")
    aid = str(getattr(n, "aid", "") or getattr(n, "automation_id", "") or "")
    types[ct] = types.get(ct, 0) + 1
    for p in (getattr(n, "pats", []) or []):
        pats[p] = pats.get(p, 0) + 1
    low = (nm + " " + aid).lower()
    if any(k in low for k in INTERESTING):
        hits.append((ct, nm[:44], aid[:26], ",".join(getattr(n, "pats", []) or [])[:34]))
print("\ncontrol types:", dict(sorted(types.items(), key=lambda x: -x[1])[:14]))
print("patterns available:", pats)
print(f"\n{len(hits)} interesting nodes (first 40):")
for h in hits[:40]:
    print("   ", h)

print("\nwindow class chain:")
for row in classes(hwnd)[:40]:
    print("   ", row)

print("\nclosing our Excel instance ...")
headless_input.post_key_combo(hwnd, "alt+f4") if hasattr(headless_input, "post_key_combo") else None
time.sleep(2.0)
try:
    if proc.poll() is None:
        proc.terminate()
        proc.wait(8)
except Exception as exc:
    print("  terminate note:", exc)
print("done. alive:", proc.poll() is None)
