"""READ-ONLY knowledge of an account app (Discord / WhatsApp / Teams): the program's own files + a UIA READ of the window that already exists.
Nothing is pressed, typed or focused; no window is launched, moved or restored."""
import sys, os, json, tempfile, uuid, time
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import organ_48_app_behavior_model as bm, organ_63_app_mastery as am, command_registry as cr, desktop_grounding as dg, fast_uia
for app in sys.argv[1:]:
    mdl = bm.BehaviorModel(os.path.join(tempfile.gettempdir(), f"hj_acc_{uuid.uuid4().hex[:6]}.db"))
    key = bm._app_key(app)
    from core_organs import knowledge_store as ks
    ks.ensure(mdl)
    t0 = time.time()
    g0 = dg.DesktopGrounding(); h0 = g0.find_window(app) or 0; st = am._static_phase(mdl, app, 0)
    if not st.get("ok") and h0: st = am._static_phase(mdl, app, h0)
    row = {"app": app, "static_s": st.get("elapsed_s"), "exe": os.path.basename(st.get("exe", "")), "frameworks": st.get("frameworks"), "archetype": st.get("archetype"),
           "static_commands": cr.build(mdl, key) and len(cr.build(mdl, key))}
    g = dg.DesktopGrounding()
    h = g.find_window(app) or 0
    row["window"] = bool(h)
    if h:
        t1 = time.time()
        nodes = list(fast_uia.snapshot(h, timeout_ms=8000) or [])
        row["uia_nodes"] = len(nodes)
        try:
            rep = g.ground(h, "", {}) if False else None
        except Exception:
            rep = None
        main = nodes
        added = am.record_resting_controls(mdl, key, main)
        row["resting_controls_added"] = added
        row["uia_s"] = round(time.time() - t1, 1)
    reg = cr.build(mdl, key)
    d = cr.dossier(mdl, key)
    row["commands_total"] = len(reg)
    row["by_kind"] = d["commands"]["by_kind"]
    row["quick_answers"] = {k: v["command"] for k, v in d.get("quick_answers", {}).items()}
    row["kind"] = (d.get("kind") or {}).get("archetype")
    row["total_s"] = round(time.time() - t0, 1)
    print(json.dumps(row, default=str), flush=True)
