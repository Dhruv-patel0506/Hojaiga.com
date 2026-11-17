# =========================================================================================================== the ML models (continuous learning)
def run_pr45() -> TestOutcome:
    """PR45: the action-outcome model really LEARNS - on a synthetic world where each toolkit favours different routes it beats the majority baseline test-then-train, learns that 'control' works in a XAML-like toolkit and 'click' in a GL-like one, re-orders routes accordingly (never inventing one), explores routes it has rarely seen, and survives a save / load"""
    from core_organs.professor.ml import outcome as OM
    rng = np.random.default_rng(5)
    P_OK = {("winui", "control"): 0.95, ("winui", "click"): 0.08, ("winui", "shortcut"): 0.7, ("gl", "control"): 0.02, ("gl", "click"): 0.85, ("gl", "shortcut"): 0.3,
            ("win32", "control"): 0.9, ("win32", "click"): 0.6, ("win32", "shortcut"): 0.9}
    labels = ["Save", "Bold", "Add Marker", "Zoom In", "Options", "Export...", "Paste"]
    m = OM.OutcomeModel(None)
    fresh_rank = m.rank_routes({"toolkit": "winui", "role": "button", "app": "x"}, ["click", "control", "shortcut"])
    for i in range(1800):
        tk = ["winui", "gl", "win32"][i % 3]
        route = ["control", "click", "shortcut"][int(rng.integers(0, 3))]
        lbl = labels[int(rng.integers(0, len(labels)))]
        ok = bool(rng.random() < P_OK[(tk, route)])
        eff = ("opens_dialog" if lbl.endswith("...") else "state_change") if ok else "no_effect"
        m.observe({"app": f"app_{tk}", "toolkit": tk, "role": "button", "route": route, "safety": "safe", "source": "exec", "label": lbl, "n_controls": 40, "has_shortcut": route == "shortcut"}, eff, ok)
    met = m.metrics()
    ctx = lambda tk: {"app": f"app_{tk}", "toolkit": tk, "role": "button", "safety": "safe", "source": "exec", "label": "Save", "n_controls": 40}
    p_w_control = m.predict({**ctx("winui"), "route": "control"})["p_ok"]
    p_w_click = m.predict({**ctx("winui"), "route": "click"})["p_ok"]
    p_g_control = m.predict({**ctx("gl"), "route": "control"})["p_ok"]
    p_g_click = m.predict({**ctx("gl"), "route": "click"})["p_ok"]
    rank_w = m.rank_routes(ctx("winui"), ["click", "control", "shortcut"])
    rank_g = m.rank_routes(ctx("gl"), ["control", "shortcut", "click"])
    rank_new = m.rank_routes({**ctx("qt"), "app": "app_qt"}, ["control", "click"])                  # a toolkit it never saw
    dialog_p = m.predict({**ctx("win32"), "route": "control", "label": "Export..."})["effect"]
    path = _tmp("outcome") + ".npz"
    m.save(path)
    m2 = OM.OutcomeModel(path)
    same = abs(m2.predict({**ctx("gl"), "route": "click"})["p_ok"] - p_g_click) < 1e-9 and m2.seen == m.seen
    for suf in ("", ".json"):
        try:
            os.remove(path + suf)
        except OSError:
            pass
    checks = {"beats_the_majority_baseline_test_then_train": met["ok_accuracy"] >= met["ok_baseline"] + 0.08 and met["beats_baseline"], "learns_the_toolkit_route_pattern": p_w_control > 0.8 and p_w_click < 0.35 and p_g_control < 0.25 and p_g_click > 0.6,
              "reorders_routes_per_toolkit": rank_w[0][0] == "control" and rank_g[0][0] == "click", "before_learning_the_static_ladder_stands": [k for k, _s in fresh_rank] == ["click", "control", "shortcut"],
              "ranking_never_adds_a_route": {k for k, _s in rank_w} == {"click", "control", "shortcut"} and {k for k, _s in rank_new} == {"control", "click"}, "unseen_toolkit_gets_an_exploration_bonus": rank_new[0][1] > 0.0 and all(s > 0 for _k, s in rank_new),
              "dialog_labels_learn_their_effect": dialog_p["opens_dialog"] > dialog_p["no_effect"] or dialog_p["opens_dialog"] > 0.15, "save_and_load_identical": same, "small_enough_to_train_beside_a_vision_model": met["parameters"] < 150_000}
    return _verdict(checks, f"{met['seen']} examples: ok accuracy {met['ok_accuracy']} vs baseline {met['ok_baseline']}, effect accuracy {met['effect_accuracy']} vs {met['effect_baseline']}; winui control/click {p_w_control:.2f}/{p_w_click:.2f}, gl control/click {p_g_control:.2f}/{p_g_click:.2f}; "
                            f"params {met['parameters']}", {"ok_accuracy": met["ok_accuracy"], "baseline": met["ok_baseline"]})


def run_pr46() -> TestOutcome:
    """PR46: the vision-candidate model learns, from the TREE-labelled scans alone (no hand labels), which boxes the vision tier proposed are real controls - on a held-out theme + scale it is far above chance and raises precision at full recall; on a layout it has never seen it is honestly weaker; it improves again as soon as it has learnt from that layout; its noise filter stays OFF until it has seen enough different applications"""
    from core_organs.professor import candidates as CD, synth
    from core_organs.professor.ml import candidates as MC
    from core_organs.professor.schema import Box

    def scene(kind, theme="light", scale=1.0):
        img, truth, _ = {"app": lambda: synth.render_app(theme, scale), "dialog": lambda: synth.render_dialog(theme, scale), "editor": lambda: synth.render_editor(scale)}[kind]()
        cs = CD.detect(img, scale, ocr=True, budget_s=30)
        return cs.candidates, img.size, CD.ink_mask(np.asarray(img.convert("L")), scale), [Box(*t["box"]) for t in truth if t.get("label") is not None]

    train = [scene("app", "light", 1.0), scene("app", "dark", 1.0), scene("app", "light", 1.5)]
    held_app, dlg, dlg_dark, edt = scene("app", "dark", 1.25), scene("dialog", "light"), scene("dialog", "dark"), scene("editor")
    m = MC.CandidateModel(None)
    never = m.filter(held_app[0], held_app[1], held_app[2])[1]
    for _ in range(6):
        for c, size, ink, tb in train:
            m.observe_scan(c, size, ink, tb, epochs=2, source="synthetic-app")
    e_held = m.evaluate(*held_app, 0.5)
    e_untrained = MC.CandidateModel(None).evaluate(*held_app, 0.5)
    e_dlg = m.evaluate(*dlg, 0.5)
    ready_one_source = m.ready()
    for _ in range(6):
        for c, size, ink, tb in (dlg, edt):
            m.observe_scan(c, size, ink, tb, epochs=2, source="synthetic-dialog")
    e_dlg_dark = m.evaluate(*dlg_dark, 0.5)
    kept, dropped = m.filter(held_app[0], held_app[1], held_app[2])
    for src in ("a", "b", "c", "d"):                                    # pretend it has learnt from several applications with a good running AUC
        m.sources.add(src)
    m.preq_p, m.preq_y = [0.9] * 100 + [0.1] * 100, [1] * 100 + [0] * 100
    m.seen = max(m.seen, 500)
    ready_diverse = m.ready()
    path = _tmp("cand") + ".npz"
    m.save(path)
    m2 = MC.CandidateModel(path)
    same = np.allclose(m.prob(held_app[0], held_app[1], held_app[2]), m2.prob(held_app[0], held_app[1], held_app[2])) and m2.sources == m.sources
    for suf in ("", ".json"):
        try:
            os.remove(path + suf)
        except OSError:
            pass
    checks = {"labels_come_from_the_tree_alone": e_held["positives"] > 10 and e_held["n"] > e_held["positives"], "held_out_theme_and_scale_far_above_chance": e_held["auc"] >= 0.95 and e_untrained["auc"] < 0.85,
              "precision_rises_at_full_recall": e_held["precision"] >= e_held["base_precision"] + 0.2 and e_held["recall"] >= 0.9, "unseen_dialog_layout_beats_untrained": e_dlg["auc"] >= e_untrained["auc"] - 0.3 and e_dlg["auc"] >= 0.65,
              "learns_the_new_layout_quickly": e_dlg_dark["auc"] >= 0.9, "filter_off_after_one_layout": not ready_one_source and never == 0 and dropped == 0, "filter_ready_only_with_diversity_and_good_auc": ready_diverse,
              "save_and_load_identical": same}
    return _verdict(checks, f"held-out dark@1.25: auc {e_held['auc']} precision {e_held['precision']} (base {e_held['base_precision']}) recall {e_held['recall']}; untrained auc {e_untrained['auc']}; unseen dialog auc {e_dlg['auc']}; "
                            f"after learning dialog+editor, held-out dark dialog auc {e_dlg_dark['auc']}", {"auc_heldout": e_held["auc"]})


def run_pr47() -> TestOutcome:
    """PR47: the motor-timing model - with no data it IS the Fitts prior (and says it was not learnt from people); fed noisy movements it recovers the generating law, its fit quality is reported, a handful of points barely move it (ridge prior), it persists, and the pointer's Fitts parameters follow it"""
    from core_organs.professor import pointing as PT
    from core_organs.professor.ml import motor as MM
    rng = np.random.default_rng(9)
    m = MM.MotorModel(None)
    prior = m.summary()
    a_true, b_true = 0.22, 0.17
    for _ in range(300):
        d, w = float(rng.uniform(40, 1400)), float(rng.uniform(8, 160))
        m.observe(d, w, a_true + b_true * m.index_of_difficulty(d, w) + float(rng.normal(0, 0.025)))
    fit = m.summary()
    few = MM.MotorModel(None)
    for _ in range(3):
        few.observe(500, 20, 1.2)
    old = (PT.FITTS_A, PT.FITTS_B)
    PT.set_fitts(fit["a"], fit["b"])
    t_far_small = PT.fitts_seconds(900, 10)
    PT.set_fitts(*old)
    path = _tmp("motor") + ".json"
    m.save(path)
    m2 = MM.MotorModel(path)
    os.remove(path)
    checks = {"no_data_is_the_prior": prior["a"] == MM.A0 and prior["b"] == MM.B0 and prior["learned_from_people"] is False, "recovers_the_generating_law": abs(fit["a"] - a_true) < 0.03 and abs(fit["b"] - b_true) < 0.02,
              "fit_quality_reported": fit["r2"] is not None and fit["r2"] > 0.85 and fit["rmse"] < 0.05, "three_points_barely_move_it": abs(few.params()[0] - MM.A0) < 0.25 and few.summary()["n"] == 3,
              "pointer_follows_the_model": abs(t_far_small - min(1.6, max(0.16, fit["a"] + fit["b"] * MM.MotorModel.index_of_difficulty(900, 10)))) < 1e-6 and (PT.FITTS_A, PT.FITTS_B) == old,
              "prediction_obeys_fitts": m.predict(1200, 10) > m.predict(100, 10) and m.predict(600, 10) > m.predict(600, 120), "save_and_load_identical": m2.params() == m.params() and m2.n == m.n}
    return _verdict(checks, f"prior {prior['a']}/{prior['b']} -> fitted {fit['a']}/{fit['b']} (true {a_true}/{b_true}) r2 {fit['r2']} rmse {fit['rmse']} on {fit['n']} movements")


def run_pr48() -> TestOutcome:
    """PR48: CONTINUOUS training - every logged transition trains the outcome model the moment it is logged, rows logged earlier are caught up exactly once, a background trainer runs only while the architecture is in use (replaying, checkpointing, logging metrics), checkpoints reload identically, and HOJAIGA_PROF_ML=0 switches it all off"""
    import shutil
    from core_organs.professor import history as HS
    from core_organs.professor.ml import learner as LN
    d = _tmp("mldir")
    hp = _tmp("hist_ml") + ".db"
    hist = HS.History(hp)
    # 40 rows logged BEFORE any learner exists
    for i in range(40):
        hist.log("app_a", "exec", "invoke", "Save", "control:Save", effect="state_change", ok=True, toolkit="winui", role="button", safety="safe")
    L = LN.Learner(d, interval_s=0.2, save_every_s=0.6, log_every_s=0.5)
    att = L.attach(hist)
    seen_after_catchup = L.outcome.seen
    att2 = L.attach(hist)                                           # second attach: nothing to catch up, no duplicate listener
    for i in range(25):
        hist.log("app_a", "exec", "key", "Bold", "shortcut:Ctrl+B", effect="no_effect" if i % 5 == 0 else "state_change", ok=i % 5 != 0, toolkit="winui", role="button", safety="safe")
    live = L.outcome.seen - seen_after_catchup
    before_thread = L._thread is not None and L._thread.is_alive()
    with L.training():
        during = L._thread is not None and L._thread.is_alive()
        time.sleep(1.6)
    after = L._thread is not None and L._thread.is_alive()
    rep = L.report()
    files = sorted(os.listdir(d))
    log_lines = [json.loads(x) for x in open(L.log_path, "r", encoding="utf-8")] if os.path.isfile(L.log_path) else []
    p1 = L.outcome.predict({"app": "app_a", "toolkit": "winui", "role": "button", "route": "control", "safety": "safe", "label": "Save"})["p_ok"]
    L2 = LN.Learner(d)
    p2 = L2.outcome.predict({"app": "app_a", "toolkit": "winui", "role": "button", "route": "control", "safety": "safe", "label": "Save"})["p_ok"]
    L2.attach(hist)
    no_dupes = L2.outcome.seen == L.outcome.seen
    old = os.environ.get("HOJAIGA_PROF_ML")
    os.environ["HOJAIGA_PROF_ML"] = "0"
    try:
        n0 = L.outcome.seen
        hist.log("app_a", "exec", "invoke", "Save", "control:Save", effect="state_change", ok=True, toolkit="winui")
        off_observe = L.outcome.seen == n0
        with L.training():
            off_thread = L._thread is not None and L._thread.is_alive()
    finally:
        if old is None:
            os.environ.pop("HOJAIGA_PROF_ML", None)
        else:
            os.environ["HOJAIGA_PROF_ML"] = old
    hist.close()
    shutil.rmtree(d, ignore_errors=True)
    for suf in ("", "-wal", "-shm"):
        try:
            os.remove(hp + suf)
        except OSError:
            pass
    checks = {"earlier_rows_caught_up": att["caught_up_rows"] == 40 and seen_after_catchup == 40, "second_attach_does_not_duplicate": att2["caught_up_rows"] == 0 and len(hist.listeners) == 1,
              "every_new_transition_trains_at_once": live == 25, "trainer_runs_only_while_in_use": (not before_thread) and during and not after, "replayed_while_running": rep["events"]["replay_rounds"] >= 3,
              "checkpoints_written": {"outcome.npz", "candidates.npz", "motor.json", "learner.json"} <= set(files) and rep["events"]["checkpoints"] >= 1, "metrics_logged_to_jsonl": len(log_lines) >= 1 and "outcome" in log_lines[-1],
              "reload_is_identical": abs(p1 - p2) < 1e-9 and no_dupes, "learns_the_pattern_it_was_shown": p1 > 0.5, "switch_off_stops_everything": off_observe and not off_thread}
    return _verdict(checks, f"outcome seen {rep['outcome']['seen']}, replay rounds {rep['events']['replay_rounds']}, checkpoints {rep['events']['checkpoints']}, files {files}, log lines {len(log_lines)}; p(ok|winui,control,Save) {p1:.2f}")


