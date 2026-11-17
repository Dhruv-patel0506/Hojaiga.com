import sys, time, ctypes
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR
from core_organs.professor.effectors import Effector
from core_organs.professor.schema import fold
from core_organs import fast_uia, headless_input as hin
name, how = sys.argv[1], sys.argv[2]
run = AR.AppRun(AR.SPECS["chrome"], vision=False, log=lambda s: None)
try:
    assert run.start()
    h = run.hwnd
    nodes = fast_uia.snapshot(h, timeout_ms=6000) or []
    base = {(n.aid, n.name, n.ctype) for n in nodes}
    n = next(x for x in nodes if fold(x.name) == fold(name) and x.ctype == "ButtonControl")
    c = n.ctrl
    try:
        if how == "legacy":
            p = c.GetLegacyIAccessiblePattern()
            print("legacy pattern", p is not None, getattr(p, "DefaultAction", None) if p else None)
            p.DoDefaultAction()
        elif how == "invoke":
            c.GetInvokePattern().Invoke()
        elif how == "focus_enter":
            c.SetFocus()
            time.sleep(0.2)
            hin.post_key_combo(h, "enter")
    except Exception as exc:
        print("error", type(exc).__name__, exc)
    for i in range(4):
        time.sleep(0.6)
        now = fast_uia.snapshot(h, timeout_ms=6000) or []
        new = [x for x in now if (x.aid, x.name, x.ctype) not in base and x.name]
        ws = hin.process_windows(h, include_hidden=True)
        print(f"{how} t={0.6*(i+1):.1f}s main-tree new {len(new)}: {[(x.ctype[:-7], x.name[:24]) for x in new][:8]} | windows {[(w, hin._class_name(w)) for w in ws if hin._class_name(w) == 'Chrome_WidgetWin_1']}")
finally:
    run.finish()
