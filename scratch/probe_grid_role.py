"""What IS a spreadsheet worksheet, as grounded data? (role/name/aid/cls/rect of every big surface)

Launched background-parked, exactly like a suite test would, and only READS. This is the fact the judge
scoring needs: 'type 42 in cell A1' currently offers only 'edit' controls (a search strip, a name box) and
never the grid, because nothing here knows what role the grid carries."""
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

from core_organs import desktop_grounding as dg                    # noqa: E402
from core_organs.desktop_grounding import DesktopGrounding         # noqa: E402

g = DesktopGrounding()
if g.find_window("excel") is not None:
    print("REFUSE: an excel window is already open and is not ours")
    sys.exit(2)

before = set()
import ctypes                                                        # noqa: E402
u = ctypes.windll.user32


def now_handles():
    out = set()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(h, _):
        b = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(h, b, 256)
        if "XLMAIN" in b.value:
            out.add(int(h))
        return True
    u.EnumWindows(cb, 0)
    return out


new: "set[int]" = set()
p = subprocess.Popen([EXE])
for _ in range(40):
    time.sleep(0.5)
    new = now_handles() - before
    if new:
        break
hwnd = int(sorted(new)[0]) if new else 0
print("hwnd", hwnd, "pid", p.pid)
time.sleep(6.0)

h, els, rep = g.ground("excel", target_text="zz_absent_zz", max_tier=2)
print("ground hwnd", h, "elements", len(els), "tiers_ran", rep.get("tiers_ran"))
from core_organs import fast_uia as fu                              # noqa: E402
nodes = fu.snapshot(int(h or hwnd), timeout_ms=6000) or []
byht = {}
for n in nodes:
    ct = str(n.ctype or "")
    byht.setdefault(ct, 0)
    byht[ct] += 1
print("UIA ctypes:", sorted(byht.items(), key=lambda t: -t[1]))
print("\n-- every grounded element over 40,000 px area --")
for e in els:
    a = abs(e.bbox[2] - e.bbox[0]) * abs(e.bbox[3] - e.bbox[1])
    if a >= 40000:
        print(f"  area={a:>9} role={e.role:<10} tier={e.tier:<5} name={str(e.name)[:40]!r:<44} aid={str(e.automation_id)[:30]!r}")
print("\n-- every UIA node over 40,000 px area --")
for n in nodes:
    try:
        r = n.rect
    except Exception:
        continue
    a = abs(int(r.right) - int(r.left)) * abs(int(r.bottom) - int(r.top))
    if a >= 40000:
        print(f"  area={a:>9} ctype={str(n.ctype):<22} name={str(n.name)[:38]!r:<42} aid={str(n.aid)[:28]!r} cls={str(n.cls)[:20]!r}")
print("\n-- all 'edit'-like / grid-like nodes regardless of area --")
for n in nodes:
    ct = str(n.ctype or "").lower()
    if any(k in ct for k in ("edit", "document", "table", "data", "list", "group")):
        try:
            r = n.rect
            a = abs(int(r.right) - int(r.left)) * abs(int(r.bottom) - int(r.top))
        except Exception:
            a = -1
        print(f"  area={a:>9} ctype={ct:<20} name={str(n.name)[:34]!r:<38} aid={str(n.aid)[:30]!r}")

from core_organs import universal_scan as us                        # noqa: E402
print("close:", us.close_window(int(h or hwnd), timeout_s=8.0, discard_unsaved=True))
