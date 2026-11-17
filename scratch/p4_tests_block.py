# =========================================================================================================== PART 2 (safe subset): dorks, guide card, history, trajectories, idle exploration
def run_pr40() -> TestOutcome:
    """PR40: finding manuals with SEARCH OPERATORS - the query set (filetype:pdf intitle:"user manual" / inurl:docs / site:github.com inurl:wiki / plain) is built from the app's own name, run politely, merged and ranked (PDF manuals, project wikis and vendor docs first, social / video dropped); PDFs get a big enough fetch cap; the PDF and the live docs are both indexed; Google / SearXNG result formats are read"""
    from core_organs.professor.knowledge import guide_finder as GF, manual_rag as MR
    site = _DocSite()
    old = (GF.GUIDE_DIR, GF.FETCH_LOG)
    GF.GUIDE_DIR, GF.FETCH_LOG = _tmp("guides_d"), _tmp("fetchlog_d") + ".tsv"
    dbp = _tmp("dork_ix") + ".db"
    ix = MR.ManualIndex(dbp)
    try:
        ident = GF.AppIdentity(app_key="atlasapp3", product='Atlas "App"', company="127", process="AtlasApp.exe", description="Atlas App Desktop")
        qs = GF.dork_queries(ident)
        kinds = [q["kind"] for q in qs]
        # results by query kind: the pdf dork finds the manual, the docs dork the live documentation, the wiki dork a repository wiki, junk everywhere
        seen_q, sleeps = [], []

        def stub(q):
            seen_q.append(q)
            if "filetype:pdf" in q:
                return [{"url": site.base + "/docs/guide.pdf", "title": "Atlas App User Manual"}, {"url": "https://www.youtube.com/watch?v=1", "title": "Atlas App tutorial"}]
            if "inurl:docs" in q:
                return [{"url": site.base + "/docs/index.html", "title": "Atlas App documentation"}, {"url": site.base + "/docs/guide.pdf", "title": "Atlas App User Manual"}]
            if "site:github.com" in q:
                return [{"url": "https://github.com/acme/atlas/wiki/Home", "title": "Home - acme/atlas wiki"}, {"url": "https://reddit.com/r/x", "title": "atlas help?"}]
            return []

        res, ran = GF.search_dorks(ident, GF.default_fetch, stub, delay_s=0.7, sleep=lambda s: sleeps.append(s))
        ranked = GF.rank_results(ident, res)
        by_url = {r["url"]: r for r in ranked}
        gh = by_url.get("https://github.com/acme/atlas/wiki/Home")
        # PDF cap vs page cap
        site.pages["/docs/big.pdf"] = ("application/pdf", b"%PDF-1.4 " + b"x" * 3_000_000)
        st_pdf, ct_pdf, body_pdf, _f = GF.default_fetch(site.base + "/docs/big.pdf")
        st_htm, ct_htm, body_htm, _f2 = GF.default_fetch(site.base + "/docs/big.html")
        # Google Custom Search style + SearXNG style results
        g = GF.search_web("q", lambda u: (200, "application/json", json.dumps({"items": [{"link": "https://docs.example.com/a", "title": "A"}]}).encode(), u))
        sx = GF.search_web("q", lambda u: (200, "application/json", json.dumps({"results": [{"url": "https://help.example.com/b", "title": "B"}]}).encode(), u))
        # the whole discovery, web on (explicit), local server standing in for the internet
        external = []

        def local_only(url):                                   # the test must never reach the real internet: anything that is not the local doc site is refused and recorded
            if "127.0.0.1" not in url:
                external.append(url)
                return 0, "", b"", url
            return GF.default_fetch(url)

        rep = GF.discover(ident, ix, web=True, fetch=local_only, search=stub, allow_local_net=True, delay_s=0.0, max_pages=6, max_depth=1)
        pdf_hit = ix.search("press ctrl m add a marker quickly", "atlasapp3", 3)
        docs_hit = ix.search("place a marker toolbar", "atlasapp3", 3)
        t3 = next(t for t in rep["tiers"] if t.get("tier") == 3)
        srcs = {i["source"].replace(site.base, "") for i in rep["ingested"]}
        checks = {"query_set_has_the_operators": kinds[:4] == ["pdf", "docs", "wiki", "plain"] and 'filetype:pdf' in qs[0]["query"] and 'intitle:"user manual"' in qs[0]["query"] and "inurl:docs" in qs[1]["query"] and "site:github.com inurl:wiki" in qs[2]["query"],
                  "name_is_quoted_and_sanitised": all('"Atlas App"' in q["query"] for q in qs[:4]) and not any("\\" in q["query"] for q in qs), "second_name_gets_its_own_pdf_query": len(qs) == 5 and "Atlas App Desktop" in qs[4]["query"],
                  "queries_run_politely_and_merged": len(seen_q) == 5 and len(sleeps) == 4 and all(s == 0.7 for s in sleeps) and len(res) == 5 and len({r["url"] for r in res}) == 5,
                  "pdf_manual_and_vendor_docs_ranked_first": ranked[0]["url"].endswith(("guide.pdf", "index.html")) and not any("youtube" in r["url"] or "reddit" in r["url"] for r in ranked), "project_wiki_recognised": gh is not None and gh["score"] >= 3 and "project wiki" in gh["why"],
                  "pdf_gets_the_large_cap_pages_do_not": st_pdf == 200 and len(body_pdf) > 2_500_000 and st_htm == 200 and len(body_htm) <= 2_000_000, "google_and_searxng_formats_read": g == [{"url": "https://docs.example.com/a", "title": "A"}] and sx == [{"url": "https://help.example.com/b", "title": "B"}],
                  "discovery_indexed_pdf_and_live_docs": rep["web"] == "on" and any(s.endswith("guide.pdf") for s in srcs) and any(s.endswith("index.html") for s in srcs), "pdf_text_searchable": bool(pdf_hit) and "Ctrl+M" in pdf_hit[0].text,
                  "live_docs_searchable": bool(docs_hit) and "Add Marker" in docs_hit[0].text, "report_lists_the_queries": len(t3["queries"]) == 5 and t3["queries"][0]["kind"] == "pdf",
                  "test_never_reached_the_internet": external == []}
        return _verdict(checks, f"queries: {[q['query'][:48] for q in qs[:3]]}; ranked {[(r['url'].replace(site.base, '')[-18:], r['score']) for r in ranked[:3]]}; indexed {sorted(srcs)}; pdf body {len(body_pdf)} B vs page {len(body_htm)} B")
    finally:
        site.close()
        GF.GUIDE_DIR, GF.FETCH_LOG = old
        ix.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suf)
            except OSError:
                pass


def run_pr41() -> TestOutcome:
    """PR41: the guide as ONE structured JSON card - UI taxonomy (nested menu paths, interface terms), shortcuts (with what they do), action sequences (parsed steps) and the seven-division map; with the live catalog every procedure says how much of it applies to the installed version"""
    from core_organs.professor.knowledge import guide_card as GC, guide_finder as GF, manual_rag as MR
    cat = _p2_catalog()
    dbp = _tmp("card_ix") + ".db"
    ix = MR.ManualIndex(dbp)
    old = GF.GUIDE_DIR
    GF.GUIDE_DIR = _tmp("guides_c")
    try:
        html = ("<html><body><h1>Atlas Guide</h1><h2>Place a marker</h2><ol><li>Click <b>Add Marker</b> on the toolbar.</li></ol>"
                "<h2>Zoom in</h2><ol><li>Choose <b>View</b> &gt; <b>Zoom In</b>.</li></ol><h2>Crop the picture</h2><ol><li>Adjust the <b>Cropping Ratio</b> in the Inspector.</li><li>Click <b>Apply Crop</b>.</li></ol>"
                "<h2>Quick marker</h2><p>Press <b>Ctrl</b>+<b>M</b> to add a marker quickly.</p><h2>Export</h2><ol><li>Choose <b>File</b> &gt; <b>Export</b> &gt; <b>PDF</b>.</li></ol></body></html>")
        ix.ingest_text("fixture_like", "Atlas Guide", MR._html_to_text(html), "test:card", "html", embed=False)
        card = GC.build_card("fixture_like", ix, cat)
        card_nocat = GC.build_card("fixture_like", ix, None, save=False)
        with open(GC.card_path("fixture_like"), "r", encoding="utf-8") as fh:
            disk = json.load(fh)
        seq = {s["goal"]: s for s in card["action_sequences"]}
        terms = {t["term"] for t in card["ui_taxonomy"]["terms"]}
        checks = {"menus_are_nested": card["ui_taxonomy"]["menus"].get("View", {}).get("Zoom In") == {} and card["ui_taxonomy"]["menus"]["File"]["Export"]["PDF"] == {},
                  "interface_terms_collected": {"Add Marker", "Zoom In", "Cropping Ratio"} <= terms and "Ctrl" not in terms and "M" not in terms, "shortcut_with_what_it_does": "Ctrl+M" in card["shortcuts"] and "marker" in card["shortcuts"]["Ctrl+M"][0]["label"].lower(),
                  "procedures_parsed": {"Place a marker", "Zoom in", "Crop the picture", "Export"} <= set(seq) and seq["Place a marker"]["steps"][0]["target"] == "Add Marker", "grounding_measured_with_the_catalog": seq["Place a marker"]["grounded"] == 1.0 and seq["Zoom in"]["grounded"] == 1.0,
                  "what_does_not_apply_is_named": seq["Crop the picture"]["grounded"] < 1.0 and "Cropping Ratio" in seq["Crop the picture"]["unmatched"] and seq["Export"]["grounded"] < 1.0,
                  "version_fit_is_a_fraction": 0.0 < card["applies_to_installed_version"] < 1.0 and "applies_to_installed_version" not in card_nocat and "grounded" not in card_nocat["action_sequences"][0],
                  "mapped_onto_the_seven_divisions": bool(card["by_division"]) and all(isinstance(v, list) and v for v in card["by_division"].values()), "saved_as_json": disk["app"] == "fixture_like" and disk["chunks"] == card["chunks"] and len(disk["action_sequences"]) == len(card["action_sequences"])}
        return _verdict(checks, f"{card['chunks']} chunks, {len(card['action_sequences'])} procedures, shortcuts {list(card['shortcuts'])}, fit {card['applies_to_installed_version']}, divisions {list(card['by_division'])}")
    finally:
        GF.GUIDE_DIR = old
        ix.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suf)
            except OSError:
                pass


def run_pr42() -> TestOutcome:
    """PR42: the state-transition history - every probe and every route tried by the executor leaves a row (before-state, motor primitive, after-state, effect, ok); effects, best route, recoveries and order effects are queryable; one table with an app_key column; forget() removes an application"""
    import core_organs.professor.probe as P
    from core_organs.professor import executor as X, history as HS
    from core_organs.professor.effectors import Effector
    p = _tmp("hist") + ".db"
    h = HS.History(p)
    ST = {"n": 0}
    old_snap, old_deliver = P.snapshot, X.Executor._deliver

    def snap(hwnd, with_image=True, nodes=None):
        return _p1_snap(texts={"text|@0,0": f"n={ST['n']}"}, sig=f"s{ST['n']}")

    def deliver(self, v, r):
        if r.kind == "shortcut":
            ST["n"] += 1
        return True, "fake " + r.kind

    try:
        cat = _p2_catalog()
        P.snapshot = snap                                                  # type: ignore[assignment]
        X.Executor._deliver = deliver                                      # type: ignore[method-assign]
        ex = X.Executor(7, Effector(7, allow_input=True, owned=True), cat, owned=True, history=h)
        rep = ex.run(ex.plan("add a marker"), dry_run=False, settle_s=1.0)
        rows = h.recent("fixture_like", 10)
        # a probe row and a recovery row, through the engine's own logging methods
        eng = P.ProbeEngine(7, Effector(7), cat, "fixture_like", history=h)
        hyp = P.Hypothesis("Options", [], "tabitem", "", "context", "x")
        rule = P.Rule("Options", [], "tabitem", "UIA Select", "context_change", {}, "x", True, "re-selected 'Shapes' (UIA Select)", True, 12, "a", "b", note="context changed in tabs")
        eng._log_probe(hyp, rule, _p1_snap(sig="a", names={"k": "v"}), _p1_snap(sig="b"))
        eng._log_recovery("Export", "close", "Escape then WM_CLOSE", True)
        eng._log_recovery("Export", "close", "Escape then WM_CLOSE", True)
        h.log("fixture_like", "sleep", "pair", "Add Marker / Clear Markers", "both orders", effect="order_matters", ok=True, unwound=True, detail={"ab": "markers=0", "ba": "markers=1", "diff": ["text"]})
        h.log("other_app", "probe", "invoke", "Save", effect="state_change", ok=True)
        eff = h.effects_of("fixture_like", "Add Marker")
        st = h.stats("fixture_like")
        tables = [r[0] for r in h.db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        n_forgot = h.forget("other_app")
        checks = {"executor_run_logged_each_route": rep.ok and len(rows) == 1 and rows[0]["source"] == "exec" and rows[0]["target"] == "Add Marker" and rows[0]["primitive"] == "key" and rows[0]["effect"] == "state_change" and rows[0]["ok"] == 1,
                  "before_and_after_signatures_kept": rows[0]["s0_sig"] == "s0" and rows[0]["s1_sig"] == "s1", "probe_row_has_unwound_flag": any(r["source"] == "probe" and r["primitive"] == "select" and r["unwound"] == 1 for r in h.recent("fixture_like", 10)),
                  "effects_counted": eff == {"state_change": 1}, "best_route_is_the_one_that_worked": h.best_route("fixture_like", "Add Marker") == "shortcut:Ctrl+M",
                  "recoveries_aggregated": h.recoveries("fixture_like") == [{"trigger": "Export", "primitive": "close", "route": "Escape then WM_CLOSE", "times": 2, "worked": 2}],
                  "order_effects_readable": h.order_effects("fixture_like")[0]["verdict"] == "order_matters" and h.order_effects("fixture_like")[0]["ba"] == "markers=1", "stats": st["transitions"] == 5 and st["by_source"].get("recovery") == 2,
                  "one_table_with_an_app_key": tables.count("transitions") == 1 and not any(t.startswith("app_history_") for t in tables), "forget_removes_one_application": n_forgot == 1 and h.stats("other_app")["transitions"] == 0 and h.stats("fixture_like")["transitions"] == 5,
                  "primitive_vocabulary": [HS.primitive_of(x) for x in ("UIA Invoke", "BM_CLICK -> btn", "WM_COMMAND 102", "posted click x", "UIA SetValue", "UIA Select")] == ["invoke", "click", "command", "click", "set_value", "select"]}
        return _verdict(checks, f"rows {st}; recent[0]={ {k: rows[0][k] for k in ('source', 'primitive', 'target', 'effect', 'ok')} }")
    finally:
        P.snapshot = old_snap
        X.Executor._deliver = old_deliver
        h.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(p + suf)
            except OSError:
                pass


def run_pr43() -> TestOutcome:
    """PR43: Fitts's-law trajectories - movement time grows with distance and shrinks with target width; several targets are ONE continuous route (passes through each waypoint at its arrival time, starts and ends at rest, no stop-and-go between waypoints, velocity continuous at the joins); the overlay's glide and the session's 'watch me' demonstration use it and never touch the real mouse"""
    import math
    from core_organs.professor import pointing as PT, skills as SK, synth
    from core_organs.professor.overlay import RecordingOverlay
    from core_organs.professor.schema import Box
    from core_organs.professor.session import ProfessorSession
    from core_organs.professor.voice_out import SilentSpeaker
    from core_organs.professor.capture import cursor_pos
    near, far = PT.fitts_seconds(100, 40), PT.fitts_seconds(1200, 40)
    small, big = PT.fitts_seconds(600, 8), PT.fitts_seconds(600, 150)
    pts = [(100.0, 100.0), (600.0, 200.0), (900.0, 700.0), (300.0, 650.0)]
    tr = PT.stitch(pts, [0, 20, 120, 14])
    at_arrivals = [tr.at(a) for a in tr.arrival]
    speeds = [math.hypot(*tr.velocity(a)) for a in tr.arrival]
    joins = []
    for a in tr.arrival[1:-1]:
        v1, v2 = tr.velocity(a - 0.004), tr.velocity(a + 0.004)
        joins.append(math.hypot(v1[0] - v2[0], v1[1] - v2[1]) / max(1.0, math.hypot(*tr.velocity(a))))
    chord = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(3))
    flat = PT.stitch([(0.0, 0.0), (500.0, 0.0)], [0, 30])
    boxes = [Box(100, 100, 160, 130), Box(400, 300, 440, 330), Box(800, 120, 1000, 180)]
    rp, rw = PT.route_for(boxes, (10.0, 10.0))
    ov = RecordingOverlay()
    dur = ov.glide(rp[1:], rw[1:])
    # the session demonstration on a real scan of the synthetic application (nothing on screen)
    img, truth, _ = synth.render_app("light", 1.0)
    sm, _ = _scan_offline(img, 1.0)
    bold, ital = _el(sm, truth, "Bold"), _el(sm, truth, "Italic")
    bold.label, ital.label = "Bold", "Italic"
    sk = SK.Skill("t1", "synth", "bold_italic", ["make it bold and italic"], [SK.SkillStep("verb", "Bold", "", [], "", ""), SK.SkillStep("verb", "Italic", "", [], "", ""), SK.SkillStep("verb", "No Such Control", "", [], "", "")])
    sp, ov2 = SilentSpeaker(), RecordingOverlay()
    ps = ProfessorSession(mute=True, speaker=sp, overlay_obj=ov2, upgrade=False, interactive=False, find_guide=False, use_catalog=False)
    mouse0 = cursor_pos()
    out = ps.demonstrate(sk, image=img)
    mouse1 = cursor_pos()
    glides = [e for e in ov2.log if e[0] == "glide"]
    points = [e for e in ov2.log if e[0] == "point"]
    checks = {"fitts_distance_and_width": far > near and small > big and 0.16 <= near <= far <= 1.6, "passes_through_every_waypoint": all(math.hypot(a[0] - p[0], a[1] - p[1]) < 1.5 for a, p in zip(at_arrivals, pts)),
              "starts_and_ends_at_rest": speeds[0] < 20 and speeds[-1] < 20, "moves_between": speeds[1] > 200 and speeds[2] > 100, "no_stop_and_go_velocity_continuous_at_joins": all(j < 0.15 for j in joins),
              "route_is_not_wasteful": chord <= tr.length() <= 1.35 * chord, "duration_is_the_sum_of_the_segments": abs(tr.duration - sum(tr.times)) < 1e-9 and tr.arrival == sorted(tr.arrival), "straight_hop_is_straight": abs(flat.at(flat.duration / 2)[1]) < 1e-6,
              "overlay_glide_records_the_route": dur > 0.5 and ov.log[-1][0] == "glide" and ov.log[-1][1]["arrivals"][-1] == round(dur, 3) and len(ov.log[-1][1]["arrivals"]) == 3,
              "demonstration_found_the_visible_controls": out["ok"] and out["steps"] == ["Bold", "Italic"] and out["missing"] == ["No Such Control"], "glide_then_point_at_each_target_in_order": len(glides) == 1 and [p[1]["label"] for p in points] == ["Bold", "Italic"] and [p[1]["step"] for p in points] == [1, 2],
              "narrated": any("Bold" in s for s in sp.said) and any("Italic" in s for s in sp.said), "real_mouse_untouched": mouse0 == mouse1}
    return _verdict(checks, f"fitts near {near:.2f}s far {far:.2f}s small {small:.2f}s big {big:.2f}s; route {tr.duration:.2f}s len {tr.length():.0f}px (chord {chord:.0f}); join discontinuity {max(joins):.3f}; demo {out.get('route_seconds')}s")


def run_pr44() -> TestOutcome:
    """PR44: idle permutation learning on a fake application - for every pair of safe actions both orders are run and the application is put back each time; 'Add Marker / Clear Markers' is order-sensitive, the others commute; verdicts land in the history; it refuses when input is closed, when the user is active, and stops when the user comes back"""
    import core_organs.fast_uia as FU
    import core_organs.professor.probe as P
    from core_organs.professor import explore as EX, history as HS
    from core_organs.professor.effectors import Effector
    S = {"markers": 0, "vis": 1}
    nodes: list = []

    class Pat:
        def __init__(self, fn):
            self.fn = fn

        def Invoke(self):
            self.fn()

        def Toggle(self):
            self.fn()

    class Ctl:
        def __init__(self, fn, kind):
            self.fn, self.kind = fn, kind

        def GetInvokePattern(self):
            return Pat(self.fn) if self.kind == "invoke" else None

        def GetTogglePattern(self):
            return Pat(self.fn) if self.kind == "toggle" else None

    def add():
        S["markers"] += 1

    def clear():
        S["markers"] = 0

    def tog():
        S["vis"] = 1 - S["vis"]

    def build():
        nodes.clear()
        nodes.append(_FN(0, -1, "WindowControl", "Fake", (0, 0, 800, 600)))
        for i, (nm, fn, kind, pats) in enumerate((("Add Marker", add, "invoke", ("invoke",)), ("Clear Markers", clear, "invoke", ("invoke",)), ("Visible", tog, "toggle", ("toggle",))), 1):
            n = _FN(i, 0, "CheckBoxControl" if kind == "toggle" else "ButtonControl", nm, (10, 40 * i, 120, 40 * i + 28), pats=pats, toggle=(S["vis"] if kind == "toggle" else -1))
            n.ctrl = Ctl(fn, kind)
            nodes.append(n)
            nodes[0].children.append(i)
        return nodes

    def snap(hwnd, with_image=True, nodes=None):
        return _p1_snap(names={"b1": "Add Marker", "b2": "Clear Markers", "c1": "Visible"}, texts={"text|@0,0": f"markers={S['markers']}"}, states={"chk": f"tog={S['vis']}"}, sig=f"m{S['markers']}v{S['vis']}")

    old = (FU.snapshot, P.snapshot, EX.snapshot)
    FU.snapshot = lambda hwnd, **kw: build()                          # type: ignore[assignment]
    P.snapshot = EX.snapshot = snap                                    # type: ignore[assignment]
    p = _tmp("hist_x") + ".db"
    h = HS.History(p)
    try:
        cat = _p2_catalog()
        fx = Effector(7, allow_input=True, owned=True)
        idle = {"s": 1000.0}
        ex = EX.Explorer(7, fx, cat, "fake_app", h, owned=True, idle_required_s=60.0, max_actions=4, budget_s=60.0, idle_fn=lambda: idle["s"])
        rep = ex.run(require_idle=True)
        by = {(p_.a, p_.b): p_ for p_ in rep.pairs}
        pair = by.get(("Add Marker", "Clear Markers")) or by.get(("Clear Markers", "Add Marker"))
        rows = h.order_effects("fake_app")
        # refusals
        closed = EX.Explorer(7, Effector(7), cat, "fake_app", h, owned=True, idle_fn=lambda: 1000.0).run()
        S.update(markers=0, vis=1)
        busy = EX.Explorer(7, fx, cat, "fake_app", h, owned=True, idle_required_s=60.0, idle_fn=lambda: 3.0).run(require_idle=True)
        foreign_busy = EX.Explorer(7, Effector(7, allow_input=True, authorized=True), cat, "fake_app", h, owned=False, idle_required_s=60.0, idle_fn=lambda: 3.0).run(require_idle=False)
        # the user returns after the first pair
        calls = {"n": 0}

        def returning():
            calls["n"] += 1
            return 1000.0 if calls["n"] <= 3 else 0.2

        S.update(markers=0, vis=1)
        ret = EX.Explorer(7, fx, cat, "fake_app", h, owned=True, idle_required_s=60.0, idle_fn=returning).run(require_idle=True)
        checks = {"every_pair_tried_both_ways": len(rep.pairs) == 3 and all(p_.verdict in ("order_matters", "commutes") for p_ in rep.pairs), "add_clear_is_order_sensitive": pair is not None and pair.verdict == "order_matters" and {"markers=0", "markers=1"} <= {pair.ab, pair.ba},
                  "independent_actions_commute": all(p_.verdict == "commutes" for p_ in rep.pairs if "Visible" in (p_.a, p_.b)), "application_put_back_after_every_pair": all(p_.restored for p_ in rep.pairs) and S["markers"] == 0 and rep.stopped == "",
                  "verdicts_in_the_history": len(rows) == 3 and sorted(r["verdict"] for r in rows) == ["commutes", "commutes", "order_matters"], "refuses_when_input_closed": closed.stopped.startswith("input closed") and not closed.pairs,
                  "refuses_while_the_user_is_active": busy.stopped.startswith("the user is active") and not busy.pairs, "someone_elses_window_always_needs_idle": foreign_busy.stopped.startswith("the user is active") and not foreign_busy.pairs,
                  "stops_when_the_user_returns": ret.stopped.startswith("the user came back") and len(ret.pairs) < 3, "state_untouched_after_refusals": S["markers"] == 0 and S["vis"] == 1}
        return _verdict(checks, f"pairs { {f'{p_.a}/{p_.b}': p_.verdict for p_ in rep.pairs} }; ab={pair.ab if pair else None!r} ba={pair.ba if pair else None!r}; returned-user run did {len(ret.pairs)} pair(s): {ret.stopped}")
    finally:
        FU.snapshot, P.snapshot, EX.snapshot = old
        h.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(p + suf)
            except OSError:
                pass


def run_pl12() -> TestOutcome:
    """PL12: idle permutation learning on the REAL Atlas fixture (our own window, parked, headless) - 'Add Marker' then 'Clear Markers' leaves 0 markers, the reverse leaves 1 (ground truth: its own state label), the fixture is put back to its starting state exactly, the verdicts are in the history"""
    try:
        from core_organs.atlas.fixture import harness
    except Exception as exc:
        return TestOutcome(True, f"fixture harness unavailable: {exc}", env_blocked=True)
    from core_organs import background_window as bw, headless_input as hin
    from core_organs.atlas import scanner as SC
    from core_organs.professor import explore as EX, harvest as HV, history as HS
    from core_organs.professor.capture import foreground_hwnd
    from core_organs.professor.effectors import Effector
    h = None
    p = _tmp("hist_l") + ".db"
    hist = HS.History(p)
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
            cat = HV.harvest_tree(hwnd, "atlas_fixture", "Atlas Fixture")
            fx = Effector(hwnd, allow_input=True, owned=True)
            rep = EX.Explorer(hwnd, fx, cat, "atlas_fixture", hist, owned=True, max_actions=3, budget_s=150.0).run(require_idle=False)
            s1 = harness.read_state_text(hwnd)
        by = {frozenset((p_.a, p_.b)): p_ for p_ in rep.pairs}
        pair = by.get(frozenset(("Add Marker", "Clear Markers")))
        fg_end = foreground_hwnd()
        checks = {"fixture_pairs_explored": len(rep.pairs) >= 1 and pair is not None, "add_clear_order_matters": pair is not None and pair.verdict == "order_matters", "ground_truth_of_both_orders": pair is not None and any("markers=0" in x for x in (pair.ab, pair.ba)) and any("markers=1" in x for x in (pair.ab, pair.ba)),
                  "fixture_back_to_its_start_exactly": s1 == s0 and rep.stopped == "", "every_pair_restored": all(p_.restored for p_ in rep.pairs), "verdicts_logged": len(hist.order_effects("atlas_fixture")) == len(rep.pairs),
                  "fixture_not_left_holding_the_foreground": hin.window_pid(fg_end) != h.get("pid")}
        return _verdict(checks, f"pairs { {f'{p_.a}/{p_.b}': p_.verdict for p_ in rep.pairs} }; ab={pair.ab if pair else None!r} ba={pair.ba if pair else None!r}; {rep.seconds}s; stopped={rep.stopped!r}; skipped {rep.skipped[:3]}; focus handed back {fx.focus_returns}x",
                        {"pairs": len(rep.pairs), "seconds": rep.seconds})
    finally:
        try:
            if h:
                harness.close(h)
        except Exception:
            pass
        hist.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(p + suf)
            except OSError:
                pass


def run_pl13() -> TestOutcome:
    """PL13: the REAL overlay pointer glides through three targets as one Fitts's-law route - it arrives at the last one, the overlay reports no error, the user's real mouse does not move, the foreground window never changes"""
    from core_organs.professor import capture as CAP, pointing as PT
    from core_organs.professor.overlay import Overlay
    from core_organs.professor.schema import Box
    ov = Overlay()
    if not ov.start():
        return TestOutcome(True, f"overlay could not start here: {ov.error}", env_blocked=True)
    try:
        mon = CAP.monitors()[0].box
        base_x, base_y = mon.x2 - 700, mon.y2 - 260
        boxes = [Box(base_x, base_y, base_x + 40, base_y + 30), Box(base_x + 300, base_y + 120, base_x + 360, base_y + 160), Box(base_x + 120, base_y + 60, base_x + 150, base_y + 90)]
        pts, ws = PT.route_for(boxes)
        fg0, mouse0 = CAP.foreground_hwnd(), CAP.cursor_pos()
        time.sleep(0.3)
        user_moving = CAP.cursor_pos() != mouse0                 # if a person is moving the real mouse during the test, that check says nothing
        mouse0 = CAP.cursor_pos()
        ov.point(boxes[0], "start", 1, "look", False, "", False, False)         # the pointer appears at the first target
        time.sleep(0.5)
        t0 = time.time()
        planned = ov.glide(pts[1:], ws[1:])
        while ov.cursor is not None and ov.cursor.flying() and time.time() - t0 < planned + 3.0:
            time.sleep(0.05)
        took = time.time() - t0
        pos = ov.cursor.pos if ov.cursor is not None else (-1, -1)
        mouse1, fg1 = CAP.cursor_pos(), CAP.foreground_hwnd()
        checks = {"glide_planned_with_fitts": 0.5 < planned < 3.0, "pointer_arrived_at_the_last_target": abs(pos[0] - pts[-1][0]) < 4 and abs(pos[1] - pts[-1][1]) < 4, "took_about_the_planned_time": abs(took - planned) < 1.0,
                  "no_overlay_error": not ov.error, "real_mouse_never_moved": user_moving or mouse1 == mouse0, "foreground_unchanged": fg1 == fg0}
        return _verdict(checks, f"(user was moving the mouse: {user_moving}) planned {planned:.2f}s took {took:.2f}s; pointer at {tuple(round(c) for c in pos)} target {tuple(round(c) for c in pts[-1])}; overlay error {ov.error!r}")
    finally:
        ov.clear()
        time.sleep(0.8)
        ov.stop()


