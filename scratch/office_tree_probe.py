"""Probe: start an OWNED parked instance, dump its UIA tree shape (tabs, groups, start-screen items), optionally create a blank document, dump again, close."""
import sys, time, json, collections, ctypes
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs.professor import apprun as AR
from core_organs import fast_uia

name = sys.argv[1] if len(sys.argv) > 1 else "word"
u = ctypes.windll.user32
fg0 = u.GetForegroundWindow()
run = AR.AppRun(AR.spec_for(name), echo=True, vision=False)
ok = run.start()
print("started", ok, run.hwnd, run.report["phases"].get("park"), run.report["phases"].get("tree"))


def dump(tag):
    nodes = fast_uia.snapshot(run.hwnd, timeout_ms=8000) or []
    roles = collections.Counter(n.role for n in nodes)
    print(f"--- {tag}: {len(nodes)} nodes", dict(roles.most_common(12)))
    tabs = [n for n in nodes if n.role == "tabitem"]
    print("tabitems:", [(n.name, n.cls, n.selected, nodes[n.parent].name if n.parent >= 0 else "", nodes[n.parent].ctype if n.parent >= 0 else "") for n in tabs][:30])
    groups = [n for n in nodes if n.ctype == "GroupControl" and n.name]
    print("groups:", [(g.name, g.cls, g.rect) for g in groups][:30])
    for n in nodes:
        if n.name and n.role in ("listitem", "button", "hyperlink") and n.depth <= 12 and not n.offscreen:
            pass
    print("first named:", [(n.role, n.name[:30], n.cls) for n in nodes if n.name and not n.offscreen][:60])
    return nodes


try:
    if ok:
        nodes = dump("start")
        blank = [n for n in nodes if n.name and n.name.lower().startswith("blank") and not n.offscreen]
        print("blank candidates:", [(n.role, n.name, n.pats) for n in blank][:6])
        if blank and "--blank" in sys.argv:
            run.fx = __import__("core_organs.professor.effectors", fromlist=["Effector"]).Effector(run.hwnd, allow_input=True, owned=True)
            with run.fx.focus_watch():
                print("invoke:", run.fx.node(blank[0]))
            time.sleep(4)
            dump("after blank")
finally:
    print("fg changed?", u.GetForegroundWindow() != fg0)
    run._teardown()
    print("closed")
