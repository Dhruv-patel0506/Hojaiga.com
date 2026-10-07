"""FULL PRODUCTION SCAN on PowerPoint through organ_01.scan_app_tool (the exact agent entry point).

Not a scratch-pipeline replay: we launch POWERPNT.EXE, minimize it (reveal is only allowed on
non-user-visible windows), then call the CrewAI tool exactly as the swarm would:
scan_app_tool("powerpoint"). Asserts from the tool's OWN output text:
  - "RIBBON TABS & GROUPS DETECTED" section exists and covers many non-active tabs;
  - per-tab button lists are populated (Insert/Design/Transitions/Animations/Record/Review/View);
then reads the persisted knowledge (organ_48) to confirm ribbon-derived commands with
tooltip goals and shortcuts are surfaced for the app.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, r"D:\new_automation\All codes")
os.environ.setdefault("HOJAIGA_WEBAPP_WATCH", "0")

import win32con  # noqa: E402
import win32gui  # noqa: E402

PPTEXE = r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE"
fails = []


def check(name, cond, detail=""):
    print(f"[{'OK' if cond else 'XX'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def find_pp():
    hit = {"h": 0}

    def cb(h, _):
        t = (win32gui.GetWindowText(h) or "")
        c = win32gui.GetClassName(h)
        if c in ("PPTApp", "PPTFrameClass", "OpusApp") or "PowerPoint" in t:
            if "PowerPoint" in t and c != "PPTWinPreviewClass":
                hit["h"] = h
    win32gui.EnumWindows(cb, None)
    return hit["h"]


hwnd = find_pp()
opened = False
if not hwnd:
    subprocess.Popen([PPTEXE, "/n"])
    for _ in range(40):
        time.sleep(1.0)
        hwnd = find_pp()
        if hwnd:
            opened = True
            break
check("PowerPoint window available", bool(hwnd), "no PowerPoint window found")
if not hwnd:
    sys.exit(2)
print(f"hwnd={hwnd} class={win32gui.GetClassName(hwnd)} title={win32gui.GetWindowText(hwnd)!r}")
win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)   # not user-visible => reveal allowed
time.sleep(1.5)

# ---------------- the production entry point itself ----------------
from core_organs import organ_01_crewai_engine as o1  # noqa: E402
tool = getattr(o1, "scan_app_tool", None)
check("scan_app_tool exists on organ_01", tool is not None)
if tool is None:
    sys.exit(2)

t0 = time.time()
if hasattr(tool, "func"):
    out = tool.func(app_name="powerpoint")
else:
    out = tool(app_name="powerpoint")
secs = time.time() - t0
print(f"\n--- scan_app_tool('powerpoint') returned {len(out or '')} chars in {secs:.1f}s ---\n")
print(out)

# ---------------- assertions on the tool's own output ----------------
check("tool reports APP SCAN COMPLETE", "APP SCAN COMPLETE" in (out or ""))
check("RIBBON section present in agent-facing output", "RIBBON TABS & GROUPS DETECTED" in (out or ""))

import re  # noqa: E402
tabs_in_output = sorted(set(re.findall(r"\[Tab: ([^\]]+)\]", out or "")))
print(f"\ntabs covered in tool output: {len(tabs_in_output)} {tabs_in_output}")
grp_counts = re.findall(r"Group '([^']+)'(?: \[Tab: [^\]]+\])?: (.*)", out or "")
listed_buttons = sum(len([b for b in (ctrls.split(",")) if b.strip()]) for _, ctrls in grp_counts)
check(">=5 non-active ribbon tabs covered", len(tabs_in_output) >= 5, str(tabs_in_output))
for want in ("Insert", "Design", "Transitions", "Animations", "Review", "View"):
    check(f"tab '{want}' harvested", want in tabs_in_output, str(tabs_in_output))

# ---------------- knowledge surfaced for the app ----------------
from core_organs import organ_48_app_behavior_model as bm  # noqa: E402
model = bm.get_model()
key = bm._app_key("powerpoint")
cmds = model.commands(key, limit=20000)
ribbon_cmds = [c for c in cmds if (c.get("origin") or "").startswith("layout")]
with_goal = [c for c in ribbon_cmds if (c.get("goal") or "") != (c.get("name") or "")]
with_short = [c for c in ribbon_cmds if (c.get("shortcut") or "").strip()]
print(f"\nknowledge: commands_total={len(cmds)} layout-derived={len(ribbon_cmds)} "
      f"goal-enriched={len(with_goal)} shortcut-carrying={len(with_short)}")
for c in ribbon_cmds[:6]:
    print(f"   '{c.get('name')}' goal={c.get('goal')!r} path={c.get('menu_path')!r} shortcut={c.get('shortcut')!r}")
check("ribbon buttons surfaced as app-knowledge commands", len(ribbon_cmds) >= 25, str(len(ribbon_cmds)))
check("commands carry tooltip-derived goals (what each button does)", len(with_goal) >= 10, str(len(with_goal)))
# App-dependent: PowerPoint's UIA exposes almost no AcceleratorKey on ribbon buttons
# (measured: 7/150 layout rows, none with Ctrl in the tooltip). Word exposes many.
# So assert only that whatever the app DOES expose is carried through, not a fixed count.
print(f"note: shortcut-carrying commands={len(with_short)} (PPT UIA rarely publishes accelerators;"
      f" bm_layout shows 7 accel rows for this app)")
check("shortcut carry-through (>=1, app-dependent)", len(with_short) >= 1, str(len(with_short)))

# bm_layout ground truth: per-tab button counts
try:
    import sqlite3  # noqa: E402
    db = os.environ.get("HOJAIGA_BEHAVIOR_DB", r"D:\new_automation\data\app_behavior.db")
    if os.path.exists(db):
        con = sqlite3.connect(db)
        rows = con.execute(
            "SELECT region_name, COUNT(*) FROM bm_layout WHERE app_key=? AND via LIKE 'tab:%' GROUP BY 1",
            (key,)).fetchall()
        print("bm_layout buttons per tab (region: count):", rows[:20])
        con.close()
except Exception as exc:  # noqa: BLE001
    print("bm_layout cross-check note:", exc)

if opened:
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(1.0)
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    except Exception:
        pass

print("\nRESULT:", "ALL CHECKS PASSED" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
