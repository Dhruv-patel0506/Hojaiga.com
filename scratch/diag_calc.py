"""Diagnose WHY 'add 21 and 21' fails on WinUI Calculator: run it through the real engine with
verbose tracing, dump the step-by-step decisions, what was clicked, and read the live display
value so we can see whether it misclicked, skipped a press, ran out of steps, or verified wrong."""
import io, sys, time, logging
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation")
logging.basicConfig(level=logging.INFO, format="%(message)s")
from core_organs import desktop_grounding as dg
from core_organs import universal_scan as us

GOAL = ["add 21 and 21"]
r = dg.operate_app("Calculator", GOAL, allow_destructive=False,
                   max_steps_per_goal=12, isolated=True)
print("\n========== TRACE ==========")
print("completed=", r.get("completed"), "steps=", r.get("steps"),
      "elapsed=", r.get("elapsed_s"), "window=", r.get("window_title"))
for i, t in enumerate(r.get("trace") or []):
    print(f"  step {i}: {t if isinstance(t, str) else str(t)[:240]}")

# Read what the calculator display actually says now, via UIA names/values.
hwnd = int(r.get("hwnd") or 0)
if hwnd:
    try:
        els = dg.DesktopGrounding()._walk_uia(hwnd)
        named = [(e.role, (e.name or "")[:40], getattr(e, "value", "") or "") for e in els]
        interesting = [x for x in named if x[2] or any(k in x[1].lower() for k in
                       ("result", "display", "42", "output", "calculator"))]
        print("--- display-ish elements ---")
        for row in interesting[:12]:
            print("   ", row)
        nums = [x[1] for x in named if x[1] and any(ch.isdigit() for ch in x[1])][:20]
        print("--- digit-bearing names seen ---", nums)
    except Exception as exc:
        print("readback failed:", type(exc).__name__, exc)
    if r.get("launched"):
        us.close_window(hwnd, timeout_s=4.0, discard_unsaved=True)
        print("cleanup: closed our Calculator")
