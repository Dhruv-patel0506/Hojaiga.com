import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs import background_window as bw, headless_input as hin
from core_organs.atlas import scanner as SC
from core_organs.professor import apprun as AR, menus as MN, harvest as HV
from core_organs.professor.effectors import Effector
from core_organs import fast_uia
from core_organs.professor.schema import fold

key = sys.argv[1] if len(sys.argv) > 1 else "notepad"
opener = sys.argv[2] if len(sys.argv) > 2 else "File"
spec = AR.SPECS[key]
prep = AR._Prep(spec.prep)
prep.before()
info = AR.launch(spec, prep)
h = int(info.get("hwnd") or 0)
try:
    bg = bw.BackgroundSession(h)
    bg.__enter__()
    SC.ensure_tree(h, bg, max_s=6.0)
    fx = Effector(h, allow_input=True, owned=True)

    def allnodes():
        nodes = list(fast_uia.snapshot(h, timeout_ms=4000) or [])
        for w in hin.popup_windows(h)[:6]:
            nodes += fast_uia.snapshot(w, timeout_ms=3000) or []
        return nodes

    base = allnodes()
    print("base nodes", len(base), "popups", hin.popup_windows(h))
    ops = [n for n in base if fold(n.name) == fold(opener)]
    print("openers named", opener, [(n.ctype, n.rect, n.offscreen, n.enabled, n.pats, n.expand_state) for n in ops])
    ok, how = MN._expand(fx, ops[0])
    print("expand ->", ok, how)
    for t in (0.3, 0.6, 1.0):
        time.sleep(t)
        now = allnodes()
        print(f"after {t}s: nodes {len(now)}, popups {hin.popup_windows(h)}")
    ids = {(n.aid, n.name, n.ctype) for n in base}
    new = [n for n in now if (n.aid, n.name, n.ctype) not in ids]
    for n in new[:40]:
        print("  NEW", n.ctype, repr(n.name), "off" if n.offscreen else "on", n.rect, n.pats, "accel=", n.accel)
    # find "Page setup"
    ps = [n for n in now if "page setup" in fold(n.name)]
    print("page setup nodes", [(n.ctype, n.name, n.rect, n.offscreen, n.enabled, n.pats) for n in ps])
    fx.key("escape")
finally:
    print("close", SC.close_owned(h))
    print("prep after", prep.after())
