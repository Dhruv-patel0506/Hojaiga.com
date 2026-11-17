import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs import background_window as bw
from core_organs.atlas import scanner as SC
from core_organs.professor import apprun as AR
from core_organs import fast_uia
key = sys.argv[1]
types = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else {"EditControl", "DocumentControl"}
spec = AR.SPECS[key]
prep = AR._Prep(spec.prep)
prep.before()
info = AR.launch(spec, prep)
h = int(info.get("hwnd") or 0)
try:
    bg = bw.BackgroundSession(h)
    bg.__enter__()
    SC.ensure_tree(h, bg, max_s=6.0)
    nodes = fast_uia.snapshot(h, timeout_ms=5000) or []
    for n in nodes:
        if n.ctype in types:
            print(n.ctype, repr(n.name), "aid=", repr(n.aid), "cls=", n.cls, "pats=", n.pats, n.rect, "enabled", n.enabled, "off", n.offscreen)
            try:
                c = n.ctrl
                vp = c.GetValuePattern()
                print("   value pattern:", None if vp is None else repr(vp.Value)[:60], "| text pattern:", c.GetTextPattern() is not None)
            except Exception as exc:
                print("   pattern error", exc)
finally:
    print("close", SC.close_owned(h))
    print("prep after", prep.after())
