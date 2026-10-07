"""Empirical check: does the production scan harvest RIBBON buttons across ALL tabs?

Reproduces the exact production path (fast_scan.deep_scan_legacy_shape, which runs
universal_scan.scan_desktop(deepen=False)) and contrasts it with an organ_50 map that
DOES run the reversible tab deepening (_deepen_tabs). Prints ribbon-tab button counts so
the gap is measurable, not asserted. Headless: tab selection is via the UIA SelectionItem
pattern (no cursor), and every tab is restored to the original.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, r"D:\new_automation\All codes")
os.environ.setdefault("HOJAIGA_WEBAPP_WATCH", "0")

import win32gui  # noqa: E402

WINWORD = r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE"


def find_word():
    hit = {"h": 0}

    def cb(h, _):
        if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == "OpusApp":
            hit["h"] = h
    win32gui.EnumWindows(cb, None)
    return hit["h"]


def count_ribbon(mapper):
    """TabItem labels + how many controls were revealed per ribbon tab via 'tab:<name>'."""
    tabs, per_tab = [], {}
    for c in mapper.controls:
        if c["role"] == "tabitem":
            tabs.append(c["name"])
        via = c.get("via") or ""
        if via.startswith("tab:"):
            per_tab.setdefault(via[4:], 0)
            per_tab[via[4:]] += 1
    return tabs, per_tab, len(mapper.controls)


hwnd = find_word()
opened_here = False
if not hwnd:
    if not os.path.exists(WINWORD):
        print("WINWORD not found; cannot run live check.")
        sys.exit(2)
    subprocess.Popen([WINWORD, "/n"])
    for _ in range(30):
        time.sleep(1.0)
        hwnd = find_word()
        if hwnd:
            opened_here = True
            break
if not hwnd:
    print("Word window never appeared (activation/first-run dialog?) - aborting live check.")
    sys.exit(3)
time.sleep(2.0)
print(f"Word hwnd={hwnd}")

from core_organs import organ_50_layout_map as lm  # noqa: E402
from core_organs.organ_48_app_behavior_model import DiscoveryBudget  # noqa: E402

# ---- A) PRODUCTION SHAPE: map with deepen=False (exactly what fast_scan drives)
mA = lm.LayoutMapper(hwnd, "word", budget=DiscoveryBudget(base_s=8.0, extend_s=3.0, max_s=25.0, patience=5))
mA.map(deepen=False)
tabsA, perA, nA = count_ribbon(mA)
print(f"\n[A] deepen=False (PRODUCTION): total_controls={nA}  ribbon_tabs_seen={len(tabsA)}  revealed-per-tab={perA}")

# ---- B) with reversible tab deepening
hwnd2 = find_word() or hwnd
mB = lm.LayoutMapper(hwnd2, "word", budget=DiscoveryBudget(base_s=12.0, extend_s=4.0, max_s=90.0, patience=8))
mB.map(deepen=True)
tabsB, perB, nB = count_ribbon(mB)
print(f"[B] deepen=True  (tab crawl):  total_controls={nB}  ribbon_tabs_seen={len(tabsB)}  revealed-per-tab={perB}")
print(f"\nDELTA total_controls B-A = {nB - nA};  ribbon-tab reveals B={sum(perB.values())} vs A={sum(perA.values())}")
print("VERDICT:", "RIBBON UNDER-SCANNED by production path (deepen off) - fix needed"
      if sum(perB.values()) > sum(perA.values()) + 5 else "no material ribbon difference observed")

if opened_here:
    import win32con  # noqa: E402
    try:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    except Exception:
        pass
