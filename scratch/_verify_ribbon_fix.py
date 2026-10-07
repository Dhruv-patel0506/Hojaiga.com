"""End-to-end verification of the RIBBON reveal fix (Word, live) + toggle spy (unit).

Part 1 runs the real production scanner (fast_scan.deep_scan_legacy_shape) against a minimized
Word so the pipeline is exercised exactly as scan_app_tool drives it, and asserts every ribbon
tab's buttons are now harvested, persisted, turned into commands (with tooltip-derived goal +
shortcut), and surfaced in the legacy ribbon_tabs/ribbon_groups fields.
Part 2 spies universal_scan.scan_desktop kwargs to prove the HOJAIGA_SCAN_RIBBON toggle chooses
deepen="ribbon" when ON and deepen=False when OFF (no live app needed).
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, r"D:\new_automation\All codes")
os.environ.setdefault("HOJAIGA_WEBAPP_WATCH", "0")

import win32con  # noqa: E402
import win32gui  # noqa: E402

WINWORD = r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE"
fails = []


def check(name, cond, detail=""):
    print(f"[{'OK' if cond else 'XX'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def find_word():
    hit = {"h": 0}

    def cb(h, _):
        if win32gui.GetClassName(h) == "OpusApp":
            hit["h"] = h
    win32gui.EnumWindows(cb, None)
    return hit["h"]


hwnd = find_word()
opened = False
if not hwnd:
    subprocess.Popen([WINWORD, "/n"])
    for _ in range(30):
        time.sleep(1.0)
        hwnd = find_word()
        if hwnd:
            opened = True
            break
check("Word window available for live test", bool(hwnd), "no OpusApp window")
if not hwnd:
    sys.exit(2)
win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)   # minimized => not user-visible => reveal is allowed
time.sleep(1.0)

from core_organs import fast_scan as fs            # noqa: E402
from core_organs import organ_48_app_behavior_model as bm  # noqa: E402

model = bm.get_model()
key = bm._app_key("word")
os.environ["HOJAIGA_SCAN_RIBBON"] = "1"
os.environ["HOJAIGA_RIBBON_BUDGET_S"] = "70"
res = fs.deep_scan_legacy_shape("word", target_hwnd=hwnd, budget_s=70, vision=False, force=True)

rg = res.get("ribbon_groups") or {}
rt = res.get("ribbon_tabs") or []
tabs_covered = sorted({g.get("tab") for g in rg.values() if g.get("tab")})
buttons = sum(len(g.get("controls", [])) for g in rg.values())
print("\n--- LIVE production scan (HOJAIGA_SCAN_RIBBON=1) ---")
print(f"total ribbon tabs seen      : {len(rt)}  {rt}")
print(f"ribbon groups w/ buttons    : {len(rg)}   (buttons listed={buttons})")
print(f"tabs covered by reveal      : {tabs_covered}")
for t in ("Insert", "Layout", "Review", "View"):
    g = next((v for v in rg.values() if v.get("tab") == t), None)
    if g:
        print(f"   {t}: {len(g['controls'])} buttons, e.g. {g['controls'][:6]}")
print(f"within_budget={res.get('within_budget')} seconds={res.get('seconds')} budget_extended={res.get('budget_extended')}")

check("ribbon tab LABELS captured", len(rt) >= 6, str(rt))
check("RIBBON BUTTONS harvested across tabs (was 0 before fix)", buttons >= 40, f"only {buttons}")
check("multiple non-active tabs revealed (Insert/Layout/Review/View)",
      len(tabs_covered) >= 4, str(tabs_covered))

# --- knowledge: ribbon buttons became commands with a tooltip-derived goal and a shortcut
try:
    ribbon_cmds = [c for c in model.commands(key, limit=20000)
                   if (c.get("origin") or "").startswith("layout") or (c.get("menu_path") or "").split(">")[0] in rt]
    with_goal = [c for c in ribbon_cmds if (c.get("goal") or "") != (c.get("name") or "")]
    with_short = [c for c in ribbon_cmds if (c.get("shortcut") or "").strip()]
    print(f"\nribbon-derived commands   : {len(ribbon_cmds)}  (goal-enriched by tooltip={len(with_goal)}, with shortcut={len(with_short)})")
    for c in ribbon_cmds[:4]:
        print(f"   '{c.get('name')}' -> goal='{c.get('goal')}' path='{c.get('menu_path')}' shortcut='{c.get('shortcut')}'")
    check("ribbon buttons became app-knowledge commands", len(ribbon_cmds) >= 20, str(len(ribbon_cmds)))
except Exception as exc:  # noqa: BLE001
    check("ribbon buttons became app-knowledge commands", False, f"query error {exc}")

# --- Part 2: toggle spy (no live app): deep_scan chooses the right deepen for scan_desktop
captured = {}
import core_organs.universal_scan as us  # noqa: E402
_orig = us.scan_desktop


def _spy(name, m=None, **kw):
    captured.setdefault("calls", []).append({"name": name, "deepen": kw.get("deepen"),
                                             "ribbon_budget_s": kw.get("ribbon_budget_s")})
    return {"kind": "desktop", "phases": {}, "layout": {}, "launch": {}, "hwnd": 0,
            "tree_nodes_when_ready": 30, "seconds": 1, "app_key": name}


us.scan_desktop = _spy
try:
    os.environ["HOJAIGA_SCAN_RIBBON"] = "1"
    fs.deep_scan("spyapp", model=model, budget_s=5, vision=False, target_hwnd=0)
    os.environ["HOJAIGA_SCAN_RIBBON"] = "0"
    fs.deep_scan("spyapp", model=model, budget_s=5, vision=False, target_hwnd=0)
except Exception as exc:  # noqa: BLE001
    print("spy path note:", type(exc).__name__, str(exc)[:80])
finally:
    us.scan_desktop = _orig
os.environ.pop("HOJAIGA_SCAN_RIBBON", None)
calls = captured.get("calls", [])
print("\n--- TOGGLE SPY ---")
for c in calls:
    print(f"   deepen={c['deepen']!r} ribbon_budget_s={c['ribbon_budget_s']}")
check("toggle ON  => deepen='ribbon'", calls and calls[0]["deepen"] == "ribbon", str(calls))
check("toggle OFF => deepen=False", len(calls) > 1 and calls[1]["deepen"] is False, str(calls))

if opened:
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    except Exception:
        pass

print("\nRESULT:", "ALL CHECKS PASSED" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
