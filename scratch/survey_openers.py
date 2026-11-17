"""survey_openers.py <app> -- what is still hidden behind clickable controls after the single-level menu expansion?
Prints: every control of the main window with its patterns, then for each opener the items it shows, and which of those are openers themselves (submenus) or dialog / page openers."""
import sys, time, json
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, menus as MN
from core_organs.professor.schema import fold

key = sys.argv[1]
run = AR.AppRun(AR.SPECS[key], vision=False, log=lambda s: None)
try:
    assert run.start()
    run.perceive()
    nodes = [n for n in run.ex._all_nodes() if n.rect[2] > n.rect[0] and not n.offscreen]
    print("MAIN WINDOW CONTROLS (role | name | patterns | expand_state | aid)")
    for n in nodes:
        if n.name and n.role not in ("text", "pane", "group", "window", "document"):
            print("  ", n.role, "|", n.name[:40], "|", n.pats, "|", n.expand_state, "|", n.aid)
    print()
    ops = MN.find_openers(nodes)
    print("OPENERS:", [o.name for o in ops])
    for op in ops[:8]:
        base = {MN._ident(n) for n in run.ex._all_nodes()}
        ok, how = MN._expand(run.fx, op)
        _all, new = MN._await_items(run.ex._all_nodes, base)
        print(f"\n== {op.name}: {ok} {how} -> {len(new)} items")
        for n in new:
            lab, ch = MN._item_label(n)
            print("    ", n.role, "|", lab, "|", ch, "| pats", n.pats, "| exp", n.expand_state, "| aid", n.aid)
        MN.collapse(op)
        time.sleep(0.4)
        run.fx.key("escape")
        time.sleep(0.3)
finally:
    run.finish()
