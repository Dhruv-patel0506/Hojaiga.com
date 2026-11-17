# =========================================================================================================== PART 1: harvest / archetype / probing / effectors / executor / pedagogy
class _FN:
    """A fast_uia.Node look-alike for offline tests."""

    def __init__(self, idx, parent, ctype, name="", rect=(0, 0, 0, 0), aid="", help="", accel="", pats=(), enabled=True, selected=None, toggle=-1, expand=-1):
        self.idx, self.parent, self.ctype, self.name, self.rect, self.aid, self.cls = idx, parent, ctype, name, rect, aid, ""
        self.help, self.accel, self.pats = help, accel, list(pats)
        self.enabled, self.offscreen, self.expand_state, self.selected, self.toggle_state = enabled, False, expand, selected, toggle
        self.children, self.depth, self.el = [], 0, None

    @property
    def role(self):
        return self.ctype.replace("Control", "").lower()


def _fixture_like_nodes():
    """The Atlas fixture's accessibility tree, as fake nodes (menu bar, toolbar, tabs, a state label)."""
    nodes = [_FN(0, -1, "WindowControl", "Atlas Fixture", (0, 0, 1000, 640))]

    def add(parent, ctype, name, rect, **kw):
        n = _FN(len(nodes), parent, ctype, name, rect, **kw)
        nodes.append(n)
        nodes[parent].children.append(n.idx)
        return n.idx

    mb = add(0, "MenuBarControl", "menuBar", (0, 0, 1000, 24))
    for k, nm in enumerate(("File", "Edit", "View")):
        add(mb, "MenuItemControl", nm, (10 + 50 * k, 2, 50 + 50 * k, 22), pats=("invoke", "expand"))
    tb = add(0, "ToolBarControl", "toolBar", (0, 24, 1000, 56))
    add(tb, "ButtonControl", "Add Marker", (6, 28, 90, 52), aid="tbAddMarker", help="Add a marker at the view centre", pats=("invoke",))
    add(tb, "ButtonControl", "Clear Markers", (96, 28, 190, 52), aid="tbClearMarkers", help="Remove every marker", pats=("invoke",))
    add(tb, "ButtonControl", "Run Wizard", (196, 28, 280, 52), aid="tbRunWizard", help="Open the import wizard", pats=("invoke",))
    tabs = add(0, "TabControl", "tabs", (8, 60, 338, 560))
    add(tabs, "TabItemControl", "Shapes", (10, 62, 80, 84), pats=("select",), selected=True)
    add(tabs, "TabItemControl", "Options", (82, 62, 152, 84), pats=("select",), selected=False)
    add(tabs, "TabItemControl", "Data", (154, 62, 224, 84), pats=("select",), selected=False)
    add(tabs, "ButtonControl", "Delete All", (20, 270, 140, 300), aid="btnDeleteAll", pats=("invoke",))
    add(tabs, "CheckBoxControl", "Visible", (20, 230, 140, 254), aid="chkVisible", pats=("toggle",), toggle=1)
    add(tabs, "ButtonControl", "Export...", (20, 310, 140, 340), aid="btnExport", pats=("invoke",))
    add(0, "TextControl", "markers=0 zoom=1.00", (8, 570, 600, 592), aid="stateLabel")
    return nodes


def _p1_snap(names=None, texts=None, states=None, containers=None, windows=(1,), img=None, sig=""):
    from core_organs.professor import probe as P
    return P.Snapshot(0.0, dict(names or {}), dict(texts or {}), dict(states or {}), {k: tuple(v) for k, v in (containers or {}).items()}, tuple(windows), img, sig)


def _p1_verb(label, path=(), shortcut="", command_id=0, aid="", role="button", enabled=True):
    from core_organs.professor import safety
    from core_organs.professor.harvest import Verb, verb_id
    return Verb(verb_id(list(path), label), label, list(path), shortcut, "", enabled, False, "", command_id, aid, role, ["uia"], "measured", safety.classify(label, " ".join(path)))


def run_pr28() -> TestOutcome:
    """PR28: zero-rulebook discovery -- the application's own menus, accelerators, control states and tooltip strings become a structured Verb Registry + Shortcut Map (no model, no network, milliseconds); safety class per verb; conflicts flagged; JSON round trip"""
    import ctypes
    from core_organs.professor import harvest as HV, safety
    from core_organs.professor.schema import Box, Region, ScreenModel, UIElement
    u = ctypes.WinDLL("user32", use_last_error=True)
    H = ctypes.c_void_p
    u.CreateMenu.restype = H
    u.CreatePopupMenu.restype = H
    u.AppendMenuW.argtypes = [H, ctypes.c_uint, ctypes.c_size_t, ctypes.c_wchar_p]
    u.CreateWindowExW.restype = H
    u.CreateWindowExW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, H, H, H, H]
    u.DestroyWindow.argtypes = [H]
    fm, em, bar = u.CreatePopupMenu(), u.CreatePopupMenu(), u.CreateMenu()
    u.AppendMenuW(fm, 0, 101, "&New	Ctrl+N")
    u.AppendMenuW(fm, 0, 102, "Save &As...	Ctrl+Shift+S")
    u.AppendMenuW(fm, 0, 103, "E&xit")
    u.AppendMenuW(em, 0, 201, "&Copy	Ctrl+C")
    u.AppendMenuW(em, 0, 202, "Dup&licate	Ctrl+C")                       # the same chord on two verbs -> a conflict
    u.AppendMenuW(bar, 0x10, fm, "&File")
    u.AppendMenuW(bar, 0x10, em, "&Edit")
    hwnd = u.CreateWindowExW(0, "STATIC", "harvest-test", 0x00CF0000, 0, 0, 200, 100, None, bar, None, None)
    old_dir = HV.CATALOG_DIR
    HV.CATALOG_DIR = _tmp("catalogs")
    try:
        bevel = UIElement(1, "Bevel", "button", Box(10, 40, 60, 70), "r1", ["uia"], hint="Bevel Edges: Rounds selected mesh edges. (Ctrl+B)")
        move = UIElement(2, "Move", "button", Box(70, 40, 120, 70), "r1", ["uia"], hint="Move the selection")
        move.shortcut = "G"
        sm = ScreenModel(regions=[Region("r1", "toolbar", "Tools", Box(0, 30, 400, 80))], elements=[bevel, move], size=(800, 600))
        sm.app_key, sm.window_title = "harvest_test_app", "Harvest Test"
        t0 = time.time()
        cat = HV.harvest_model(sm, int(hwnd))
        dt = time.time() - t0
        by = {v.text_path: v for v in cat.verbs}
        lab = {v.label: v for v in cat.verbs if "win32-menu" not in v.sources}
        sc = cat.shortcut_map()
        p = cat.save()
        back = HV.Catalog.load("harvest_test_app")
        name, desc, chord = HV.split_tooltip("Bevel Edges: Rounds selected mesh edges. (Ctrl+B)")
        checks = {"menu_tree_with_command_ids": by["File > Save As..."].command_id == 102 and by["File > Save As..."].shortcut == "Ctrl+Shift+S" and "Edit > Copy" in by,
                  "tooltip_parsed_into_description_and_chord": (name, desc, chord) == ("Bevel Edges", "Rounds selected mesh edges.", "Ctrl+B") and lab["Bevel"].shortcut == "Ctrl+B" and "Rounds" in lab["Bevel"].desc,
                  "control_accelerator_kept": lab["Move"].shortcut == "G", "chord_grammar": HV.normalize_chord("ctrl + shift+s") == "Ctrl+Shift+S" and HV.normalize_chord("Control-Alt-x".replace("-", "+")) == "Ctrl+Alt+X",
                  "chords_found_in_text": HV.chords_in("Group (Ctrl+G) or Alt + E") == ["Ctrl+G", "Alt+E"], "shortcut_map_built": "Ctrl+B" in sc and "Ctrl+Shift+S" in sc,
                  "conflict_flagged": "Ctrl+C" in cat.conflicts(), "safety_classes": by["File > Exit"].safety == "unsafe" and by["File > Save As..."].safety == "commit" and lab["Bevel"].safety == "safe" and safety.classify("Present from Beginning") == "runtime",
                  "tooltip_dictionary": "bevel" in cat.tooltips, "sources_recorded": cat.sources.get("win32-menu", 0) >= 5 and cat.sources.get("uia", 0) >= 2,
                  "json_round_trip": back is not None and len(back.verbs) == len(cat.verbs) and back.shortcut_for("Save As...") == "Ctrl+Shift+S" and os.path.isfile(p),
                  "prompt_lines_quote_only_known_chords": all(":" in l and any(c in l for c in sc) for l in cat.prompt_lines(["bevel"]).splitlines()) and "Bevel" in cat.prompt_lines(["bevel"]), "milliseconds": dt < 0.5}
        return _verdict(checks, f"{len(cat.verbs)} verbs, {len(sc)} chords, conflicts {cat.conflicts()} in {dt * 1000:.1f} ms; sources {cat.sources}", {"ms": round(dt * 1000, 1)})
    finally:
        HV.CATALOG_DIR = old_dir
        u.DestroyWindow(hwnd)


def run_pr29() -> TestOutcome:
    """PR29: archetype -- what KIND of software this is is decided from the verbs + area captions + layout with every point of evidence listed; a model only adjudicates close calls among the candidates and can never invent a kind; the blueprint says where properties and structure live"""
    from core_organs.professor import archetype as AR, synth
    from core_organs.professor.harvest import Catalog
    img, truth, regs = synth.render_editor()
    sm, _ = _scan_offline(img, 1.0)
    cat3d = Catalog("t", verbs=[_p1_verb(x) for x in ("Extrude", "Bevel", "Modifier", "Subdivide", "Material", "Render", "Add Mesh", "Camera")])
    catnle = Catalog("t", verbs=[_p1_verb(x) for x in ("Trim", "Split Clip", "Ripple Delete Track", "Keyframe", "Transition", "Export Sequence", "Mute Track", "Marker")])
    a3d = AR.classify(sm, cat3d)
    anle = AR.classify(sm, catnle)
    img2, truth2, _ = synth.render_app("light", 1.0)
    sm2, _ = _scan_offline(img2, 1.0)
    catdoc = Catalog("t", verbs=[_p1_verb(x) for x in ("Bold", "Italic", "Paragraph", "Styles", "Spelling", "Heading", "Font", "Track Changes")])
    adoc = AR.classify(sm2, catdoc)
    none = AR.classify(sm2, Catalog("t"))
    fake = FakeLlama()
    try:
        second = a3d["ranked"][1][0]
        fake.text_reply = lambda req: json.dumps({"id": second})
        br = _scripted_brain(fake)
        forced = AR.classify(sm, cat3d, br, margin=9.0)                 # margin so large every result counts as a close call
        fake.text_reply = lambda req: json.dumps({"id": "not_a_kind"})
        bogus = AR.classify(sm, cat3d, br, margin=9.0)
    finally:
        fake.close()
    line = AR.teaching_line(a3d)
    checks = {"3d_verbs_make_spatial_3d": a3d["id"] == "spatial_3d", "evidence_listed": any(e.startswith("verb:") for e in a3d["evidence"]) and any(e.startswith("area:") for e in a3d["evidence"]),
              "timeline_verbs_make_temporal_media": anle["id"] == "temporal_media", "document_verbs_make_document": adoc["id"] == "document_text",
              "no_evidence_is_unknown_not_a_guess": none["id"] in ("unknown",) or none["blueprint"] == {} or none["confidence"] < 0.5, "blueprint_says_where_things_live": "outliner" in a3d["blueprint"]["structure_lives"].lower() and "propert" in a3d["blueprint"]["properties_live"].lower(),
              "teaching_line_for_the_prompt": line.startswith("KIND OF SOFTWARE") and "Properties of a selection live in" in line,
              "model_adjudicates_among_the_candidates": forced["id"] == second and forced["by"] == "rules+model",
              "invented_kind_ignored": bogus["id"] == "spatial_3d" and bogus["by"] == "rules", "layout_facts_measured": a3d["layout"]["center_canvas"] and a3d["layout"]["right_panel"]}
    return _verdict(checks, f"3d={a3d['id']} {a3d['ranked'][:2]} nle={anle['id']} doc={adoc['id']} none={none['id']} forced={forced['id']}/{forced['by']} evidence={a3d['evidence'][:6]} layout={ {k: v for k, v in a3d['layout'].items() if v} }")


def run_pr30() -> TestOutcome:
    """PR30: hypothesis-driven probing -- the plan tries only safe verbs (delete/run/commit refused with the reason), a before/after DELTA classifies the effect (state / context / dialog / visual / none), the transitions become a state graph, a dry run sends nothing"""
    import core_organs.fast_uia as FU
    from core_organs.professor import probe as P, pedagogy as PE
    from core_organs.professor.effectors import Effector
    nodes = _fixture_like_nodes()
    orig = FU.snapshot
    FU.snapshot = lambda hwnd, **kw: nodes                           # type: ignore[assignment]
    old_graphs = P.GRAPH_DIR
    P.GRAPH_DIR = _tmp("graphs")
    try:
        eng = P.ProbeEngine(4242, Effector(4242, allow_input=False), None, "fixture_like", owned=False)
        hyps, skipped = eng.plan()
        labels = [h.verb for h in hyps]
        why = dict(skipped)
        eng_owned = P.ProbeEngine(4242, Effector(4242, allow_input=False), None, "fixture_like", owned=True)
        hyps_o, skipped_o = eng_owned.plan()
        rep = eng.run()
        # deltas
        base = _p1_snap(names={"b|1": "Add Marker"}, texts={"text|@0,1": "markers=0"}, states={"tab|1": "sel=True"}, containers={"Properties": ["a", "b", "c"]}, sig="a")
        txt = _p1_snap(names={"b|1": "Add Marker"}, texts={"text|@0,1": "markers=1"}, states={"tab|1": "sel=True"}, containers={"Properties": ["a", "b", "c"]}, sig="b")
        ctx = _p1_snap(names={"b|1": "Add Marker", "x1": "Location", "x2": "Rotation", "x3": "Scale"}, texts={"text|@0,1": "markers=0"}, states={"tab|1": "sel=True"}, containers={"Properties": ["location", "rotation", "scale"]}, sig="c")
        dlg = _p1_snap(names=base.names, texts=base.texts, states=base.states, containers={"Properties": ["a", "b", "c"]}, windows=(1, 2), sig="d")
        g0 = Image.new("RGB", (200, 200), (120, 120, 120))
        g1 = g0.copy()
        g1.paste((255, 255, 255), (40, 40, 100, 100))
        pic0, pic1 = _p1_snap(names=base.names, texts=base.texts, states=base.states, containers=base.containers, img=g0, sig="e"), _p1_snap(names=base.names, texts=base.texts, states=base.states, containers=base.containers, img=g1, sig="e")
        d_txt, d_ctx, d_dlg, d_vis, d_none = P.delta(base, txt), P.delta(base, ctx), P.delta(base, dlg), P.delta(pic0, pic1), P.delta(base, base)
        graph = P.StateGraph("p30")
        for verb, d in (("Add Marker", d_txt), ("Options", d_ctx), ("Run", d_dlg), ("Tint", d_vis), ("Nothing", d_none)):
            graph.record(P.Rule(verb, [], "button", "UIA Invoke", d.effect(), d.to_dict(), "x", d.effect() != "no_effect", "toggled back", True, 5, "s0", "s1"))
        mm = graph.mental_model()
        gp = graph.save()
        with open(gp, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
        beh = PE.behaviour_lines("p30")
        checks = {"plan_only_safe_verbs": "Add Marker" in labels and "Visible" in labels and labels[0] == "Add Marker", "delete_refused_with_reason": why.get("Delete All") == "unsafe", "runtime_refused": why.get("Run Wizard") == "runtime",
                  "commit_refused_unowned": why.get("Export...") == "commit" and why.get("Clear Markers") == "commit", "commit_allowed_in_owned_window": "Clear Markers" in [h.verb for h in hyps_o] and "Export..." in [h.verb for h in hyps_o],
                  "top_level_menus_not_probed": not {"File", "Edit", "View"} & set(labels), "tabs_are_context_hypotheses": next(h for h in hyps if h.verb == "Options").kind == "context",
                  "dry_run_sends_nothing": rep.dry_run and rep.stopped.startswith("dry run") and all(r.effect == "untested" for r in rep.rules) and eng.fx.log == [],
                  "text_change_is_state_change": d_txt.effect() == "state_change" and d_txt.changed_text and "markers=1" in d_txt.summary(), "container_swap_is_context_change": d_ctx.effect() == "context_change" and "Properties" in d_ctx.containers_changed,
                  "new_window_is_dialog": d_dlg.effect() == "opens_dialog" and d_dlg.new_windows == [2], "pixels_only_is_visual": d_vis.effect() == "visual_only" and d_vis.pixel_boxes, "identical_is_no_effect": d_none.effect() == "no_effect",
                  "same_state_detects_restore": P.same_state(base, base) and not P.same_state(base, txt) and not P.same_state(pic0, pic1), "graph_mental_model": mm["state_mutators"] == ["Add Marker"] and mm["opens_dialog"] == ["Run"] and mm["no_effect"] == ["Nothing"],
                  "graph_saved": saved["model"]["probes"] == 5 and os.path.isfile(gp), "behaviour_facts_for_the_prompt": "Add Marker" in beh and "state" in beh and "Nothing" not in beh}
        return _verdict(checks, f"plan={labels} skipped={dict(list(why.items())[:6])} effects={[d.effect() for d in (d_txt, d_ctx, d_dlg, d_vis, d_none)]}")
    finally:
        FU.snapshot = orig
        P.GRAPH_DIR = old_graphs


def run_pr31() -> TestOutcome:
    """PR31: the input gate -- nothing reaches an application unless allow_input AND (owned OR authorised); every route is headless (messages and UIA patterns, never the physical mouse/keyboard); a UIA call that blocks is abandoned at its deadline; safety classes and unwinding inverses"""
    import types
    from core_organs.professor import effectors as E, safety
    posted: List[Any] = []

    def fake_post(h, m, w, l):
        posted.append((int(h), int(m), int(w), int(l)))
        return True

    real_u = E._u
    E._u = types.SimpleNamespace(PostMessageW=fake_post, GetClassNameW=lambda h, c, n: None)
    try:
        closed = E.Effector(77)
        not_owned = E.Effector(77, allow_input=True)
        owned = E.Effector(77, allow_input=True, owned=True)
        authorised = E.Effector(77, allow_input=True, authorized=True)

        class Pat:
            def __init__(self, delay=0.0):
                self.hits, self.delay = 0, delay

            def Invoke(self):
                time.sleep(self.delay)
                self.hits += 1

        class Ctl:
            def __init__(self, pat):
                self.pat = pat

            def GetInvokePattern(self):
                return self.pat

        class Nd:
            def __init__(self, name, pat, pats=("invoke",), rect=(10, 10, 50, 30)):
                self.name, self.ctrl, self.pats, self.rect = name, Ctl(pat), list(pats), rect

        refused = [closed.command(5), closed.key("Ctrl+B"), closed.text("hi"), closed.click_xy(5, 5), closed.node(Nd("OK", Pat())), closed.deselect(Nd("OK", Pat())), not_owned.command(5), not_owned.node(Nd("OK", Pat()))]
        n_refused_posts = len(posted)
        ok_cmd = owned.command(102)
        p_ok = Pat()
        ok_node = authorised.node(Nd("Apply", p_ok))
        slow = Pat(delay=3.0)
        t0 = time.time()
        res_slow = owned.node(Nd("Modal", slow), deadline_s=0.4)
        dt_slow = time.time() - t0
        clicked: List[Any] = []
        owned.click_xy = lambda x, y, button="left": clicked.append((x, y)) or (True, "posted")          # type: ignore[method-assign]
        res_fallback = owned.node(Nd("Plain", None, pats=(), rect=(100, 100, 140, 120)))
        table = {"Exit": "unsafe", "Delete All": "unsafe", "Sign out": "unsafe", "Share": "sensitive", "Record Screen": "sensitive", "Present from Beginning": "runtime", "Run Wizard": "runtime",
                 "Save As...": "commit", "Export...": "commit", "New": "commit", "Clear Markers": "commit", "Zoom In": "safe", "Add Marker": "safe", "Reset View": "safe", "Bold": "safe", "Undo": "safe"}
        wrong = {k: safety.classify(k) for k, v in table.items() if safety.classify(k) != v}
        checks = {"closed_gate_refuses_every_route": all((not ok) and why.startswith("refused") for ok, why in refused), "nothing_posted_when_refused": n_refused_posts == 0,
                  "owned_window_gets_wm_command": ok_cmd[0] and posted[-1] == (77, 0x0111, 102, 0), "authorised_window_allowed": ok_node[0] and p_ok.hits == 1 and "Invoke" in ok_node[1],
                  "blocked_uia_call_abandoned_at_deadline": dt_slow < 1.2 and res_slow[0] and "still running" in res_slow[1], "posted_click_is_the_last_resort": clicked == [(120, 110)] and "posted" in res_fallback[1],
                  "classes_match": not wrong, "owned_may_probe_commit_unowned_may_not": safety.may_probe("Clear Markers", "", True)[0] and not safety.may_probe("Clear Markers", "", False)[0] and not safety.may_probe("Delete All", "", True)[0],
                  "inverse_pairs": safety.inverse_candidates("Add Marker")[0] == "clear markers" and safety.inverse_candidates("Show Grid") == ["hide grid"] and safety.inverse_candidates("Zoom In") == ["zoom out"],
                  "needs_human_for_anything_not_safe": safety.needs_human("Export...") and safety.needs_human("Delete All") and not safety.needs_human("Zoom In")}
        return _verdict(checks, f"misclassified={wrong}; slow call returned in {dt_slow:.2f}s; log entries={len(owned.log)}")
    finally:
        E._u = real_u


def run_pr32() -> TestOutcome:
    """PR32: hotkeys over pixels -- a goal becomes steps that exist in the application's own catalog (an unknown step is reported, never invented), each verb is performed by the best route (command > shortcut > control > posted click) and falls through only on NO effect; risky verbs wait for a human; dry run by default"""
    import core_organs.professor.probe as P
    from core_organs.professor import executor as X
    from core_organs.professor.effectors import Effector
    from core_organs.professor.harvest import Catalog
    cat = Catalog("exec_test", "Exec Test", verbs=[_p1_verb("Add Marker", aid="tbAddMarker"), _p1_verb("Zoom In", shortcut="Ctrl+Plus"), _p1_verb("Save As...", ["File"], "Ctrl+Shift+S", 102, role="menu_item"),
                                                   _p1_verb("Delete All", aid="btnDeleteAll"), _p1_verb("Undo", shortcut="Ctrl+Z"), _p1_verb("Export...", aid="btnExport")])
    fake = FakeLlama()
    ST = {"n": 0}
    sent: List[str] = []
    old_snap, old_deliver = P.snapshot, X.Executor._deliver

    def snap(hwnd, with_image=True, nodes=None):
        return _p1_snap(texts={"text|@0,0": f"state={ST['n']}"}, sig=f"s{ST['n']}")

    P.snapshot = snap                                                  # type: ignore[assignment]
    try:
        closed = Effector(7)
        ex = X.Executor(7, closed, cat, owned=False)
        rep = ex.plan("add a marker then zoom in")
        unk = ex.plan("teleport the sun")
        risky = ex.plan("delete all")
        saveas = ex.plan("save as")
        routes_save = [r.label() for r in ex.routes_for(next(v for v in cat.verbs if v.label == "Save As..."))]
        routes_zoom = [r.label() for r in ex.routes_for(next(v for v in cat.verbs if v.label == "Zoom In"))]
        dry = ex.run(ex.plan("add a marker then zoom in"))
        # brain planning is constrained to catalog verbs
        fake.text_reply = lambda req: json.dumps({"steps": [{"verb": "Zoom In", "why": "get closer"}, {"verb": "Launch Rocket", "why": "invented"}]})
        exb = X.Executor(7, closed, cat, owned=False, brain=_scripted_brain(fake))
        planned = exb.plan("get closer then do something else")
        # real execution against a fake application: only the shortcut route changes the state
        live_fx = Effector(7, allow_input=True, owned=True)
        exl = X.Executor(7, live_fx, cat, owned=True)

        def deliver(self, v, r):
            sent.append(r.kind)
            if r.kind == "shortcut":
                ST["n"] += 1
            return True, "fake " + r.kind

        X.Executor._deliver = deliver                                  # type: ignore[method-assign]
        r_fall = exl.run(exl.plan("save as"), dry_run=False, settle_s=1.0)
        kinds_fall = list(sent)
        sent.clear()
        r_none = exl.run(exl.plan("add a marker"), dry_run=False, settle_s=1.0)     # nothing ever changes the state for the control route
        sent.clear()
        r_risky = exl.run(exl.plan("delete all"), dry_run=False, settle_s=1.0)
        r_ok = exl.run(exl.plan("delete all"), dry_run=False, approve=lambda st: True, settle_s=1.0)
        checks = {"steps_grounded_in_catalog": [s.verb for s in rep.steps] == ["Add Marker", "Zoom In"] and all(s.kind == "verb" for s in rep.steps), "unknown_step_not_invented": unk.steps and unk.steps[0].kind == "unknown",
                  "risky_step_marked_for_a_human": risky.steps[0].need_human and risky.steps[0].safety == "unsafe", "route_ranking_command_first": routes_save[:2] == ["command:WM_COMMAND 102", "shortcut:Ctrl+Shift+S"] and routes_zoom[0] == "shortcut:Ctrl+Plus",
                  "dry_run_default_sends_nothing": dry.dry_run and len(dry.results) == 2 and all(r.status == "dry_run" for r in dry.results) and sent == [] and closed.log == [],
                  "model_plan_limited_to_catalog": planned.by == "rules+model" and [s.kind for s in planned.steps] == ["verb", "unknown"], "falls_through_only_on_no_effect": kinds_fall == ["command", "shortcut"] and r_fall.results[0].status == "done" and r_fall.results[0].route.startswith("shortcut"),
                  "no_effect_reported_honestly": r_none.results[0].status == "no_effect" and not r_none.ok and r_none.stopped != "", "human_gate_blocks_and_sends_nothing": r_risky.results[0].status == "needs_human" and sent == [],
                  "approval_lets_it_through": r_ok.results[0].status in ("done", "no_effect") and "control" in "".join(sent)}
        return _verdict(checks, f"routes save={routes_save} zoom={routes_zoom}; fall-through {kinds_fall} -> {r_fall.results[0].status}/{r_fall.results[0].route}; none -> {r_none.results[0].status} tried={len(r_none.results[0].tried)}; {r_fall.line()}")
    finally:
        P.snapshot = old_snap
        X.Executor._deliver = old_deliver
        fake.close()


def run_pr33() -> TestOutcome:
    """PR33: the Professor teaches with the application's own facts -- macro idea first, kind of software + HOTKEYS in the prompt, step hotkeys resolved from the catalog (an invented shortcut is dropped), a key-cap badge in the bubble, an optional spotlight, and the lesson advances when the interface STRUCTURALLY changes"""
    import core_organs.professor.probe as P
    from core_organs.professor import archetype as AR, overlay_render as R, pedagogy as PE, synth
    from core_organs.professor.harvest import Catalog
    from core_organs.professor.lesson_runner import LessonRunner
    from core_organs.professor.overlay import RecordingOverlay
    from core_organs.professor.schema import Box, Lesson, LessonStep, ScreenModel
    from core_organs.professor.teacher import Conversation, Teacher
    from core_organs.professor.voice_out import SilentSpeaker
    img, truth, _ = synth.render_app("light", 1.0)
    sm, _ = _scan_offline(img, 1.0)
    bold = _el(sm, truth, "Bold")
    bold.label = "Bold"
    cat = Catalog("doc", "DocWriter", verbs=[_p1_verb(x) for x in ("Italic", "Paragraph", "Styles", "Spelling", "Heading", "Font", "Track Changes")] + [_p1_verb("Bold", shortcut="Ctrl+B")])
    arch = AR.classify(sm, cat)
    fake = FakeLlama()
    try:
        fake.text_reply = lambda req: json.dumps({"mode": "lesson", "title": "Make text bold", "speech": "Bold makes words stand out. Select the words and apply bold.", "steps": [
            {"say": "Click Bold.", "action": "click", "element": bold.id, "target": "Bold", "keys": "Ctrl+Q"}, {"say": "Or press the shortcut.", "action": "key", "element": None, "target": "", "keys": "ctrl+b"}]})
        t = Teacher(_scripted_brain(fake))
        les = t.plan("how do I make this bold", sm, Conversation(), catalog=cat, arch=arch)
        req = next(r for r in fake.requests if r["messages"][0]["role"] == "system" and "the Professor" in r["messages"][0]["content"])
        prompt, system = req["messages"][-1]["content"], req["messages"][0]["content"]
    finally:
        fake.close()
    s1, s2 = les.steps[0], les.steps[1]
    # the bubble
    plain, _tip = R.render_bubble("Click Bold.", 1, 340, "up")
    capped, _tip2 = R.render_bubble("Click Bold.", 1, 340, "up", hotkey="Ctrl+Shift+S")
    def keycap_pixels(im):                                                       # the key caps' 1-px outline colour, exactly (nothing else in a bubble has it)
        a = np.asarray(im.convert("RGBA"))
        return int(((a[..., 0] == 235) & (a[..., 1] == 235) & (a[..., 2] == 245) & (a[..., 3] == 255)).sum())
    ro = RecordingOverlay()
    ro.point(Box(100, 100, 180, 130), "Bold", 1, "click", True, "Click Bold.", True, True, "Ctrl+B")
    prev = ro.preview(Image.new("RGB", (600, 400), (240, 240, 240)))
    # the watcher
    state = {"sig": "a", "text": "markers=0"}
    old = P.snapshot
    P.snapshot = lambda hwnd, with_image=True, nodes=None: _p1_snap(texts={"text|@0,0": state["text"]}, sig=state["sig"])      # type: ignore[assignment]
    try:
        w = PE.StateWatcher(1, with_image=False)
        w.rebase()
        quiet = w.poll()
        state.update(sig="b", text="markers=1")
        changed = w.poll()
    finally:
        P.snapshot = old
    # the runner advances on the structural change, shows the badge, speaks the shortcut
    class W:
        def __init__(self):
            self.rebased, self.n = 0, 0

        def rebase(self):
            self.rebased += 1

        def poll(self):
            self.n += 1
            return P.Delta(changed_text=[("k", "markers=0", "markers=1")])

    fake2 = FakeLlama()
    try:
        ov, sp, wt = RecordingOverlay(), SilentSpeaker(), W()
        runner = LessonRunner(ov, sp, None, Teacher(_scripted_brain(fake2)), None, step_wait_s=6.0, spotlight=True, watcher=wt)
        lsn = Lesson("t", "", [LessonStep(1, "Click Add Marker.", "click", None, "", "", "", "", "", Box(100, 100, 180, 130), "Add Marker", "scan", hotkey="Ctrl+M")], "lesson", "test", "q")
        res = runner.run(lsn, ScreenModel(size=(1000, 600)), None, interactive=True)
    finally:
        fake2.close()
    pts = [e for e in ov.log if e[0] == "point"]
    checks = {"prompt_has_kind_of_software": "KIND OF SOFTWARE" in prompt and arch["id"] == "document_text", "prompt_has_catalog_hotkeys": "HOTKEYS" in prompt and "Bold: Ctrl+B" in prompt,
              "persona_teaches_idea_first_and_forbids_invented_keys": "idea before the clicks" in system and "ONLY if it is listed under HOTKEYS" in system, "macro_idea_recorded": les.principle == "Bold makes words stand out." and les.archetype == "document_text",
              "step_hotkey_from_catalog": s1.hotkey == "Ctrl+B", "invented_shortcut_dropped": s1.keys == "" and any("Ctrl+Q" in n for n in les.notes), "real_shortcut_kept": s2.keys.lower() == "ctrl+b" and s2.hotkey == "Ctrl+B",
              "keycap_badge_adds_a_row": capped.height > plain.height + 14 and keycap_pixels(capped) > 50 and keycap_pixels(plain) == 0, "overlay_logs_hotkey_and_spotlight": ro.log[-1][1]["hotkey"] == "Ctrl+B" and any(s["type"] == "spotlight" for s in ro.scene) and any(s.get("hotkey") == "Ctrl+B" for s in ro.scene),
              "preview_renders": prev.size == (600, 400), "watcher_quiet_when_nothing_changed": quiet is None, "watcher_reports_structural_change": changed is not None and changed.effect() == "state_change" and "markers=1" in changed.summary(),
              "runner_advances_on_structural_change": res["steps"][0]["outcome"] == "changed" and "markers=1" in res["steps"][0]["note"] and wt.rebased >= 1, "runner_shows_badge_and_dims": bool(pts) and pts[0][1]["hotkey"] == "Ctrl+M" and pts[0][1]["spotlight"],
              "runner_speaks_the_shortcut": any("control m" in s.lower() for s in sp.said)}
    return _verdict(checks, f"principle={les.principle!r} notes={les.notes[:2]} hotkeys={[s.hotkey for s in les.steps]} bubble {plain.size}->{capped.size}; runner {res['steps'][0]['outcome']} {res['steps'][0]['note'][:60]!r}; spoken={sp.said[:2]}")


def run_pl8() -> TestOutcome:
    """PL8: probe and execute on the REAL Atlas fixture (our own window, parked, headless) -- ground truth from its state label: Add Marker markers 0->1 then unwound to the exact starting state; Delete All / Run Wizard / Export never touched; an unauthorised effector changes nothing; the user's foreground window never changes"""
    try:
        from core_organs.atlas.fixture import harness
    except Exception as exc:
        return TestOutcome(True, f"fixture harness unavailable: {exc}", env_blocked=True)
    from core_organs import background_window as bw
    from core_organs.atlas import scanner as SC
    from core_organs.professor import executor as X, harvest as HV, probe as P
    from core_organs.professor.capture import foreground_hwnd
    from core_organs.professor.effectors import Effector
    h = None
    old_graphs = P.GRAPH_DIR
    P.GRAPH_DIR = _tmp("graphs_live")
    try:
        fg0 = foreground_hwnd()
        h = harness.launch(minimized=True)
        hwnd = h.get("hwnd") if isinstance(h, dict) else None
        if not hwnd:
            return TestOutcome(True, f"fixture did not start: {h}", env_blocked=True)
        with bw.BackgroundSession(hwnd) as bg:
            nodes, waited, frame_only = SC.ensure_tree(hwnd, bg)
            if frame_only:
                return TestOutcome(True, "fixture tree never populated while parked", env_blocked=True)
            s0 = harness.read_state_text(hwnd)
            btn = next(n for n in nodes if n.name == "Add Marker")
            ok_closed, why_closed = Effector(hwnd, allow_input=True, owned=False).node(btn)
            s_closed = harness.read_state_text(hwnd)
            fx = Effector(hwnd, allow_input=True, owned=True)
            cat = HV.harvest_tree(hwnd, "atlas_fixture", "Atlas Fixture")
            eng = P.ProbeEngine(hwnd, fx, cat, "atlas_fixture", budget_s=150, max_probes=12, owned=True)
            t0 = time.time()
            rep = eng.run()
            dt = time.time() - t0
            s_after = harness.read_state_text(hwnd)
            by = {r.verb: r for r in rep.rules}
            ex = X.Executor(hwnd, fx, cat, owned=True)
            r1 = ex.run(ex.plan("add a marker"), dry_run=False)
            s_marker = harness.read_state(hwnd)
            r2 = ex.run(ex.plan("clear markers"), dry_run=False)
            s_cleared = harness.read_state(hwnd)
            r3 = ex.run(ex.plan("delete all"), dry_run=False)
            s_final = harness.read_state(hwnd)
        st0 = harness.parse_state(s0)
        checks = {"unauthorised_effector_changed_nothing": (not ok_closed) and why_closed.startswith("refused") and s_closed == s0, "catalog_from_tree": len(cat.verbs) >= 8 and any(v.label == "Add Marker" and v.aid == "tbAddMarker" for v in cat.verbs),
                  "add_marker_probed_as_state_change": "Add Marker" in by and by["Add Marker"].effect == "state_change" and by["Add Marker"].confirmed, "add_marker_unwound": "Add Marker" in by and by["Add Marker"].restored is True,
                  "state_restored_exactly_after_all_probes": s_after == s0 and not eng.tainted, "dangerous_verbs_never_probed": not {"Delete All", "Run Wizard"} & set(by) and st0.get("dele", 0) == 0 and harness.parse_state(s_after).get("dele", 0) == 0 and harness.parse_state(s_after).get("wiz", 0) == 0,
                  "context_switch_seen_on_a_tab": any(r.effect in ("context_change", "state_change") for r in rep.rules if r.verb in ("Options", "Data")), "probe_count_in_budget": 1 <= len(rep.rules) <= 12 and dt < 150,
                  "executor_added_a_marker": r1.results and r1.results[0].status == "done" and s_marker.get("markers") == 1, "executor_cleared_it": r2.results and r2.results[0].status == "done" and s_cleared.get("markers") == 0,
                  "delete_all_waits_for_a_human": r3.results and r3.results[0].status == "needs_human" and s_final.get("dele", 0) == 0 and s_final.get("shapes") == 5, "foreground_window_never_changed": foreground_hwnd() == fg0, "graph_saved": os.path.isfile(eng.graph.save())}
        return _verdict(checks, f"probes {len(rep.rules)} in {dt:.1f}s tainted={eng.tainted}; effects { {r.verb: (r.effect, r.restored) for r in rep.rules} }; skipped {rep.skipped[:4]}; exec {r1.line()} | {r2.line()} | {r3.line()}; "
                                f"unauth: {why_closed}", {"probes": len(rep.rules), "seconds": round(dt, 1)})
    finally:
        P.GRAPH_DIR = old_graphs
        try:
            if h:
                harness.close(h)
        except Exception:
            pass


def run_pl9() -> TestOutcome:
    """PL9: hover tooltip dictionary on the fixture (posted pointer moves only) -- the safety properties are gated (real cursor and foreground untouched, only an owned window is ever hovered); how many tooltips the framework actually shows is MEASURED and reported, not assumed"""
    try:
        from core_organs.atlas.fixture import harness
    except Exception as exc:
        return TestOutcome(True, f"fixture harness unavailable: {exc}", env_blocked=True)
    from core_organs import background_window as bw
    from core_organs.atlas import scanner as SC
    from core_organs.professor import harvest as HV, sweeper
    from core_organs.professor.capture import cursor_pos, foreground_hwnd
    h = None
    try:
        fg0, cur0 = foreground_hwnd(), cursor_pos()
        h = harness.launch(minimized=True)
        hwnd = h.get("hwnd") if isinstance(h, dict) else None
        if not hwnd:
            return TestOutcome(True, f"fixture did not start: {h}", env_blocked=True)
        with bw.BackgroundSession(hwnd) as bg:
            nodes, waited, frame_only = SC.ensure_tree(hwnd, bg)
            if frame_only:
                return TestOutcome(True, "fixture tree never populated while parked", env_blocked=True)
            opt = sweeper.ScanOptions.for_mode("quick")
            opt.knowledge = opt.learn = False
            sm, fr = sweeper.scan(hwnd=hwnd, options=opt, isolated=True)
            for e in sm.elements:
                e.hint = ""                                           # pretend the tree gave no help text, so the hover has something to discover
            denied = HV.harvest_model(sm, hwnd, hover=True, allow_input=False, owned=True)
            got = HV.hover_tooltips(hwnd, sm, budget_s=25.0, settle_s=1.2)
        truth = {"Add Marker": "Add a marker at the view centre", "Clear Markers": "Remove every marker", "Run Wizard": "Open the import wizard"}
        found = {k: v for k, v in got.items() if k in truth}
        right = {k: v for k, v in found.items() if truth[k].lower() in v.lower()}
        checks = {"hover_not_attempted_without_authorisation": not any("hover-tooltip" in v.sources for v in denied.verbs), "real_cursor_untouched": cursor_pos() == cur0, "foreground_untouched": foreground_hwnd() == fg0,
                  "returns_a_mapping": isinstance(got, dict)}
        return _verdict(checks, f"MEASURED: tooltips read for {len(right)}/{len(truth)} toolbar buttons ({sorted(right)}); all hover results: {dict(list(got.items())[:5])}", {"tooltips_read": len(right), "of": len(truth)})
    finally:
        try:
            if h:
                harness.close(h)
        except Exception:
            pass


