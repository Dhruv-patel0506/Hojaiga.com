"""
overnight_hojaiga.py -- run EVERY organ over a breadth of REAL apps (not excel/notepad).

Phase 1 (perception -> brain -> vision, read-only, safe): the app ladder over
  Visual Studio Code, WhatsApp (packaged/tray-resident), Settings, Microsoft Teams (PWA),
  plus the web tier (LinkedIn + YouTube) driven through an ISOLATED Chrome "temporary agent"
  profile on CDP :9222.  Each step is self-graded against the app's own UIA ground-truth.

Phase 2 (actuation -> real headless clicks + postcondition, bounded & reversible): operate_app
  on two safe desktop targets with a tiny goal each; only instances we started are closed after.

Nothing is hardcoded per-app; nothing external is edited.  A timestamped report is written to
scratch/overnight_report.txt so the morning read is just that file.
"""
import os
import sys
import time
import traceback

os.environ.setdefault("PYTHONUNBUFFERED", "1")
sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")
os.chdir(r"D:\new_automation\All codes\core_organs")

REPORT = r"D:\new_automation\scratch\overnight_report.txt"
_fh = open(REPORT, "a", encoding="utf-8")


def log(msg: str = "") -> None:
    line = f"{time.strftime('%H:%M:%S')}  {msg}" if msg else ""
    print(msg, flush=True)
    _fh.write(line + "\n")
    _fh.flush()


DESKTOP = ["Visual Studio Code", "WhatsApp", "Settings", "Microsoft Teams (PWA)"]
# the web tier the user asked for (LinkedIn + YouTube) -- monkeypatched, source untouched
PHASE2 = [
    ("Settings", ["open the About page"], 4),
    ("Visual Studio Code", ["open the File menu"], 4),
]


def phase1():
    from core_organs import run_app_ladder as ral
    from core_organs.desktop_grounding import DesktopGrounding, get_loop
    ral.WEB = ["https://www.linkedin.com/login", "https://www.youtube.com/"]
    g = DesktopGrounding()
    get_loop()
    log(f"PHASE 1  app-ladder (perception/brain/vision)  qwen-vl="
        f"{'up' if ral.qv.available() else 'DOWN'}")
    for app in DESKTOP:
        log(f"-- {app}")
        try:
            row = ral.run_desktop(app, True, g)
            log(ral.fmt(row))
        except Exception as exc:  # noqa: BLE001
            log(f"   !! {app} errored: {type(exc).__name__}: {exc}")
            log("   " + traceback.format_exc().replace("\n", "\n   ")[-800:])
    log("-- web tier (Chrome temporary agent, CDP :9222)")
    try:
        for row in ral.run_web():
            log(ral.fmt(row))
    except Exception as exc:  # noqa: BLE001
        log(f"   !! web tier errored: {type(exc).__name__}: {exc}")


def phase2():
    from core_organs.desktop_grounding import operate_app
    from core_organs import universal_scan as us
    log("PHASE 2  actuation (real headless clicks + postcondition, bounded, reversible)")
    for app, goals, steps in PHASE2:
        log(f"-- operate_app({app!r}, {goals}, max_steps={steps})")
        try:
            r = operate_app(app, goals, allow_destructive=False,
                            max_steps_per_goal=steps, isolated=True)
            log(f"   completed={r.get('completed')} steps={r.get('steps')} "
                f"launched={r.get('launched')} recipe={r.get('recipe')!r} "
                f"window={r.get('window_title')!r} elapsed={r.get('elapsed_s')}s")
            tr = r.get("trace") or []
            for i, t in enumerate(tr[:8]):
                log(f"     step {i}: {t if isinstance(t, str) else str(t)[:160]}")
            # revert: close only the instance we started for this test
            hwnd = r.get("hwnd") or 0
            if r.get("launched") and hwnd:
                us.close_window(hwnd, timeout_s=4.0, discard_unsaved=True)
                log("   cleanup: closed the instance we started")
        except Exception as exc:  # noqa: BLE001
            log(f"   !! {app} actuation errored: {type(exc).__name__}: {exc}")
            log("   " + traceback.format_exc().replace("\n", "\n   ")[-800:])


def main():
    log("\n" + "=" * 78)
    log(f"OVERNIGHT HOJAIGA TEST START  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 78)
    t0 = time.time()
    try:
        phase1()
    except Exception:  # noqa: BLE001
        log("PHASE 1 fatal:\n" + traceback.format_exc())
    try:
        phase2()
    except Exception:  # noqa: BLE001
        log("PHASE 2 fatal:\n" + traceback.format_exc())
    log(f"OVERNIGHT HOJAIGA TEST DONE  total {time.time() - t0:.0f}s")
    log("=" * 78)


if __name__ == "__main__":
    main()
