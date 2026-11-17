"""debug_find.py <app> <menu> <item> -- open menu, invoke item, dump every node that is new (main + popups), save a composite picture."""
import sys, time, os
os.environ["HOJAIGA_REVEAL"] = "0"
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, menus as MN, capture as CAP
from core_organs.professor.harvest import Verb, verb_id
from core_organs import headless_input as hin, fast_uia

key, menu, item = sys.argv[1], sys.argv[2], sys.argv[3]
run = AR.AppRun(AR.SPECS[key], vision=False, log=lambda s: None, phases=())
try:
    assert run.start()
    run.perceive()
    ex, fx = run.ex, run.fx
    base = {MN._ident(n) for n in ex._all_nodes()}
    v = Verb(verb_id([menu], item), item, [menu], role="menu_item", sources=["menu-expand"])
    with fx.holding():
        ex._open_path(v)
        node = ex._live_node(v)
        print("node:", None if node is None else (node.role, node.name, node.pats, node.rect))
        pre = {MN._ident(n) for n in ex._all_nodes()}
        ok, how = fx.node(node)
        print("invoke:", ok, how)
    for wait in (0.5, 1.5, 3.0):
        time.sleep(wait)
        nodes = ex._all_nodes()
        new = [(i, n) for i, n in enumerate(nodes) if MN._ident(n) not in pre and MN._ident(n) not in base]
        print(f"after +{wait}s: nodes={len(nodes)} main_n={ex._main_n} new={len(new)} popups={hin.popup_windows(run.hwnd)}")
        for i, n in new[:25]:
            print("   ", "POPUP" if i >= ex._main_n else "main ", n.role, "|", n.name[:40], "|", n.pats, "| off", n.offscreen, n.rect)
    fr = CAP.grab_composite(run.hwnd, hin.popup_windows(run.hwnd)[:6])
    if fr is not None:
        fr.image.save("D:/new_automation/scratch/shots_find.png")
    print("edits:", [(n.name, n.rect, n.offscreen) for n in ex._all_nodes() if n.role in ("edit", "document")])
    fx.key("escape")
finally:
    run.finish()
