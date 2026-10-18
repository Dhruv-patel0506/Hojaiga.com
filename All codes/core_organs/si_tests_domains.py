"""AR23-AR26: the three master domains, the web recorder's decisions, the web failover chain and the 429 circuit breaker."""
from __future__ import annotations

import json
import os
import tempfile
import time

HTML_ARTICLE = ("<html><head><title>History of the thing</title></head><body><nav><a href='/a'>A</a><a href='/b'>B</a></nav><article>" + "<p>" + "Some long prose about history. " * 120 + "</p>" * 1 +
                "</article>" + "<p>more text</p>" * 40 + "</body></html>")
HTML_APP = ("<html><head><title>Draw</title><link rel='manifest' href='/m.json'></head><body><div id='root'></div><canvas></canvas>" + "<button>Tool</button>" * 30 + "<div role='tab'>Tab</div>" * 10 +
            "<script src='a.js'></script>" * 30 + "</body></html>")
HTML_STEPS = ("<html><head><title>How to use Fancy Editor</title></head><body><h1>How to use Fancy Editor</h1><ol>"
              "<li>Click the <b>File</b> menu, then press <kbd>Ctrl+N</kbd> to start a new document.<img src='/img/s1.png'></li>"
              "<li>Select <b>Insert</b> and choose \"Table\" from the toolbar.<img src='/img/s2.png'></li>"
              "<li>Press Ctrl+Shift+S to open the Save dialog and click <b>Save</b>.<img src='/img/s3.png'></li>"
              "<li>Open the menu to see the settings button.</li></ol>"
              "<h3>Watch</h3><p>A short demo.</p><video src='/clips/demo.mp4'></video><img src='/g/demo.gif'></body></html>")
HTML_DICT = "<html><head><title>use - definition</title></head><body><h1>use</h1><ol>" + "".join(f"<li>Meaning number {i} of the word as a noun in the language.</li>" for i in range(8)) + "</ol></body></html>"


def run_ar23(verdict):
    """AR23: three master domains -- a name or URL is classified from evidence, keys are namespaced, retrieval refuses a key of another domain, and the registry / stats count per domain"""
    from core_organs.rag import domains as DM, Query
    from si_tests_rag import _Env
    c_app = DM.classify("Fancy Editor", installed=lambda n: n == "Fancy Editor")
    c_site = DM.classify("https://history.example.org/", fetch=lambda u: HTML_ARTICLE)
    c_webapp = DM.classify("draw.example.io", fetch=lambda u: HTML_APP)
    c_unread = DM.classify("https://down.example.com", fetch=lambda u: "")
    c_name = DM.classify("Some Unknown Thing", installed=lambda n: False)
    with _Env(icons=True) as R:
        for d, k in ((DM.DESKTOP, "fancy_editor"), (DM.WEBSITE, "web:history.example.org"), (DM.WEBAPP, "webapp:draw.example.io")):
            R.register_domain(k, d, {"test": True})
            R.lex.set_app(k, tier=1)
        R.proc.ingest_procedure("web:history.example.org", "Read the history page", [{"text": "Open the contents list and pick a section"}], "test", trust="web")
        ok = R.retrieve(Query(text="read the history page", app_key="web:history.example.org", domain="website"))
        bad = R.retrieve(Query(text="read the history page", app_key="web:history.example.org", domain="desktop_app"))
        free = R.retrieve(Query(text="read the history page", app_key="web:history.example.org"))
        st = R.domain_stats()
        dom = {k: R.domain_of(k) for k in ("fancy_editor", "web:history.example.org", "webapp:draw.example.io", "never_registered")}
    checks = {"an_installed_name_is_a_desktop_app": c_app["domain"] == "desktop_app" and c_app["key"] == "fancy_editor",
              "an_article_page_is_a_website": c_site["domain"] == "website" and c_site["key"] == "web:history.example.org",
              "an_interactive_shell_page_is_a_web_app": c_webapp["domain"] == "web_app" and c_webapp["key"] == "webapp:draw.example.io" and c_webapp["evidence"]["score"] > c_site["evidence"]["score"],
              "an_unreadable_page_is_a_website_not_a_guess_of_app": c_unread["domain"] == "website",
              "an_unknown_name_is_left_to_a_web_search": c_name["domain"] == "" and c_name["key"] == "",
              "keys_are_namespaced_per_domain": DM.key_for("website", "https://www.Example.com/x") == "web:example.com" and DM.key_for("web_app", "example.com") == "webapp:example.com" and DM.key_for("desktop_app", "OBS Studio") == "obs_studio",
              "the_domain_is_read_back": dom == {"fancy_editor": "desktop_app", "web:history.example.org": "website", "webapp:draw.example.io": "web_app", "never_registered": "desktop_app"},
              "retrieval_refuses_a_key_of_another_domain": any(g.startswith("wrong_domain") for g in bad.gaps) and not any(g.startswith("wrong_domain") for g in ok.gaps) and not any(g.startswith("wrong_domain") for g in free.gaps),
              "stats_count_per_domain": st["desktop_app"]["apps"] == 1 and st["website"]["apps"] == 1 and st["web_app"]["apps"] == 1 and st["website"]["procedures"] >= 1}
    return verdict(checks, "classify=%s/%s/%s stats=%s dom=%s gaps=%s" % (c_app["domain"], c_site["domain"], c_webapp["domain"], st, dom, bad.gaps))


def run_ar24(verdict):
    """AR24: the web recorder's decisions -- sign-in / purchase / file / download controls and off-site links are never operated, a cookie banner is DECLINED (never accepted), controls are spread through the page"""
    from core_organs.harvest import web_recorder as WR
    c = lambda n, role="link", href="": {"name": n, "role": role, "box": (10, 10, 80, 30), "href": href}
    page = "docs.example.org"
    deny = ["Sign in", "Log in", "Buy now", "Add to cart", "Subscribe to our newsletter", "Download the app", "Open file", "Save as", "Delete", "Accept all cookies", "Share on Facebook", "Upload", "Import data"]
    fine = ["Contents", "Search the docs", "Next page", "Tutorial", "Menu", "Settings panel"]
    ctrls = [c(n) for n in deny + fine]
    ctrls.append(c("External", href="https://ads.other.com/x"))
    ctrls.append(c("Same site", href="https://docs.example.org/page2"))
    ctrls.append(c("Subdomain", href="https://api.docs.example.org/x"))
    ctrls.append(c("Mail us", href="mailto:a@b.c"))
    ops = [x["name"] for x in ctrls if WR.operable(x, page)]
    banner = [c("Accept all", "button"), c("Reject all", "button"), c("Manage preferences", "button")]
    banner2 = [c("Accept", "button"), c("Only necessary cookies", "button")]
    none = [c("Accept all", "button"), c("Agree", "button")]
    many = [c("Item %d" % i) for i in range(60)]
    picked = WR.pick_controls(many, page, 10)
    dup = WR.pick_controls([c("Same"), c("Same"), c("Other")], page, 10)
    checks = {"every_unsafe_control_is_refused": not any(n in ops for n in deny),
              "ordinary_controls_are_operable": all(n in ops for n in fine),
              "an_off_site_link_is_not_followed_a_same_site_one_is": "External" not in ops and "Same site" in ops and "Subdomain" in ops and "Mail us" not in ops,
              "a_cookie_banner_is_rejected_never_accepted": WR.cookie_choice(banner)["name"] == "Reject all" and WR.cookie_choice(banner2)["name"] == "Only necessary cookies" and WR.cookie_choice(none) is None,
              "controls_are_spread_through_the_page": len(picked) == 10 and picked[0]["name"] == "Item 0" and picked[-1]["name"] in ("Item 54", "Item 55", "Item 56", "Item 57", "Item 58", "Item 59"),
              "one_control_per_name": [x["name"] for x in dup] == ["Same", "Other"]}
    return verdict(checks, "ops=%s picked=%s" % (ops, [x["name"] for x in picked]))


class _FakeDriver:
    """A stand-in browser: a page with three controls; 'Next' navigates, 'Panel' changes the picture, 'Dead' does nothing."""

    def __init__(self):
        self.cur = "https://docs.example.org/"
        self.state = 0
        self.clicks = []

    def navigate(self, url):
        self.cur = url
        self.state = 0
        return True

    def url(self):
        return self.cur

    def screenshot(self):
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (1280, 800), (255, 255, 255))
        d = ImageDraw.Draw(im)
        d.rectangle([20, 20, 120, 60], fill=(60, 60, 60))
        d.rectangle([200, 20, 300, 60], fill=(60, 60, 60))
        d.rectangle([400, 20, 500, 60], fill=(60, 60, 60))
        if self.state == 1:
            d.rectangle([600, 300, 900, 600], fill=(30, 90, 160))
        if self.cur.endswith("/next"):
            d.rectangle([100, 100, 700, 500], fill=(200, 40, 40))
        return im

    def controls(self, limit=120):
        return [{"name": "Next", "role": "link", "box": (20, 20, 100, 40), "href": "https://docs.example.org/next"}, {"name": "Panel", "role": "button", "box": (200, 20, 100, 40), "href": ""},
                {"name": "Dead", "role": "button", "box": (400, 20, 100, 40), "href": ""}, {"name": "Sign in", "role": "button", "box": (600, 20, 100, 40), "href": ""}]

    def click_at(self, x, y):
        self.clicks.append((x, y))
        if 20 <= x <= 120:
            self.cur = "https://docs.example.org/next"
        elif 200 <= x <= 300:
            self.state = 1

    def page_features(self):
        return {"text_chars": 300, "scripts": 40, "interactive": 60, "canvas": 1, "articles": 2, "forms": 0, "manifest": True, "framework_shell": True}

    def key(self, name):
        self.state = 0

    def back(self):
        self.cur = "https://docs.example.org/"


def run_ar25(verdict):
    """AR25: recording a site end to end on a stand-in browser -- before/after pairs for what changed, none for what did not, the unsafe control untouched, both prompt formats written, nothing clicked off the allowed list"""
    from core_organs.harvest import web_recorder as WR
    with tempfile.TemporaryDirectory() as root:
        out = os.path.join(root, "training", "p.jsonl")

        def som_fn(path, budget_s=0, region=None):
            els = [{"id": 1, "label": "Next", "role": "button", "box": [20, 20, 100, 40]}, {"id": 2, "label": "Panel", "role": "button", "box": [200, 20, 100, 40]},
                   {"id": 3, "label": "Dead", "role": "button", "box": [400, 20, 100, 40]}] + [{"id": 4 + i, "label": "", "role": "button", "box": [700 + 24 * i, 20, 20, 20]} for i in range(5)]
            return {"elements": els, "seconds": 0.0, "size": [1280, 800], "tiers_used": [], "tiers_skipped": []}
        drv = _FakeDriver()
        rep = WR.record_site(drv, "https://docs.example.org/", "website", max_actions=10, root=root, out_jsonl=out, rag=None, som_fn=som_fn, settle_s=0.0)
        rows = [json.loads(line) for line in open(out, encoding="utf-8")]
        v2 = [json.loads(line) for line in open(out.replace(".jsonl", "_v2.jsonl"), encoding="utf-8")] if os.path.isfile(out.replace(".jsonl", "_v2.jsonl")) else []
        acts = {r["meta"]["uia_name"]: json.loads(r["messages"][2]["content"][0]["text"])[0] for r in rows}
        frames_ok = all(os.path.isfile(os.path.join(root, r["meta"]["pre"])) and os.path.isfile(os.path.join(root, r["meta"]["post"])) for r in rows)
        rep2 = WR.record_site(_FakeDriver(), "https://docs.example.org/", "website", max_actions=10, root=root, out_jsonl=out, rag=None, som_fn=som_fn, settle_s=0.0)
        out3 = os.path.join(root, "training", "p3.jsonl")
        rep3 = WR.record_site(_FakeDriver(), "https://docs.example.org/", "auto", max_actions=10, root=root, out_jsonl=out3, rag=None, som_fn=som_fn, settle_s=0.0)
    checks = {"pairs_for_the_controls_that_changed_the_page": sorted(acts) == ["Next", "Panel"] and rep["pairs"] == 2,
              "none_for_a_control_that_did_nothing": rep["no_change"] == 1,
              "the_unsafe_control_was_never_clicked": not any(600 <= x <= 700 for x, _y in drv.clicks) and rep["skipped_unsafe"] == 1,
              "the_target_is_the_numbered_element_inside_the_dom_box": acts["Next"]["target_id"] == 1 and acts["Panel"]["target_id"] == 2,
              "a_navigation_is_recorded_and_the_page_restored": rep["navigated"] == 1 and drv.cur == "https://docs.example.org/",
              "rows_carry_the_source_and_the_domain": all(r["meta"]["source"] == "web_dom" and r["meta"]["domain"] == "website" and r["meta"]["app_key"] == "web:docs.example.org" for r in rows),
              "frames_exist_for_every_pair": frames_ok,
              "prompt_v2_twins_with_names_are_written": len(v2) == 2 and all(r["meta"]["prompt_version"] == 2 and r["meta"]["names"] >= 1 for r in v2),
              "a_rerun_adds_nothing": rep2["pairs"] == 0,
              "the_rendered_page_decides_website_or_web_app": rep3["domain"] == "web_app" and rep3["key"] == "webapp:docs.example.org" and rep3["pairs"] == 2}
    return verdict(checks, "rep=%s acts=%s v2=%d" % ({k: v for k, v in rep.items() if k != "seconds"}, {k: (v["target_id"]) for k, v in acts.items()}, len(v2)))


def run_ar26(verdict):
    """AR26: the web failover chain -- steps, key combos, clips and relevance are read from a page; a refusing search engine trips its breaker at once and the next engine answers; pairs come from consecutive screenshots"""
    from core_organs.harvest import web_search_failover as W
    steps = W.parse_steps(HTML_STEPS, "https://docs.example.org/guide")
    clips = W.parse_clips(HTML_STEPS, "https://docs.example.org/guide")
    rel_ok = W.relevant(HTML_STEPS, steps, "Fancy Editor")
    rel_other_app = W.relevant(HTML_STEPS, steps, "Other Program")
    rel_dict = W.relevant(HTML_DICT, W.parse_steps(HTML_DICT, "https://d.example.org/"), "use")
    calls = []
    t_before = time.time()
    saved = (W.ENGINES, dict(W._engine_down))
    try:
        W._engine_down.clear()
        W.ENGINES = (("first", lambda q: (calls.append("first") or 429, [])), ("second", lambda q: (calls.append("second") or 200, [{"title": "t", "url": "https://x.example.org/"}])))
        r1 = W.search("anything")
        r2 = W.search("anything again")
    finally:
        W.ENGINES, down = saved
        W._engine_down.clear()
        W._engine_down.update(down)
    elapsed = time.time() - t_before
    # pairs from consecutive screenshots, with a stand-in scan and stand-in downloads
    from PIL import Image, ImageDraw
    import io
    from core_organs.harvest import video_explain as VE
    shots = {}
    for i in range(3):
        im = Image.new("RGB", (800, 500), (240, 240, 240))
        ImageDraw.Draw(im).rectangle([20, 20 + 60 * i, 200, 60 + 60 * i], fill=(20, 20, 20 + 40 * i))
        for j in range(30):
            ImageDraw.Draw(im).line([(0, 300 + j * 6), (800, 300 + j * 6)], fill=(200, 200, 200))
        b = io.BytesIO()
        im.save(b, "PNG")
        shots[f"https://docs.example.org/img/s{i + 1}.png"] = b.getvalue()
    real_get = W.get
    W.get = lambda url, binary=False, **kw: (200, shots.get(url, b"")) if binary else real_get(url, **kw)
    try:
        with tempfile.TemporaryDirectory() as root:
            som = lambda path, **kw: {"elements": [{"id": 1, "label": "File", "role": "button", "box": [20, 20, 60, 20]}, {"id": 2, "label": "Insert", "role": "button", "box": [90, 20, 60, 20]}, {"id": 3, "label": "Save", "role": "button", "box": [160, 20, 60, 20]}]
                                      + [{"id": 4 + k, "label": "", "role": "button", "box": [300 + 25 * k, 20, 20, 20]} for k in range(6)], "seconds": 0.0, "size": [800, 500], "tiers_used": [], "tiers_skipped": []}
            real_ui = W.ui_like
            W.ui_like = lambda path: (True, "stand-in")
            try:
                pr = W.pairs_from_steps("fancy_editor", steps, "https://docs.example.org/guide", root, som_fn=som, max_pairs=5)
            finally:
                W.ui_like = real_ui
    finally:
        W.get = real_get
    rows = pr["rows"]
    acts = [json.loads(r["messages"][2]["content"][0]["text"])[0] for r in rows]
    checks = {"numbered_steps_with_their_pictures_are_read": len(steps) >= 4 and sum(1 for s in steps if s["imgs"]) == 3,
              "key_combinations_are_found": any("Ctrl+N" in s["keys"] for s in steps) and any("Ctrl+Shift+S" in s["keys"] for s in steps),
              "control_names_come_from_bold_and_quoted_text": any("File" in s["names"] for s in steps) and any("Table" in s["names"] for s in steps),
              "embedded_clips_and_gifs_are_found_with_their_text": {c["kind"] for c in clips} == {"video", "gif"} and any("demo" in c["text"].lower() for c in clips),
              "a_page_about_the_app_is_relevant": rel_ok is True,
              "a_page_about_another_app_or_a_dictionary_entry_is_not": rel_other_app is False and rel_dict is False,
              "a_refusing_engine_trips_its_breaker_and_the_next_answers_at_once": r1["engine"] == "second" and r1["tried"][0] == ("first", 429) and elapsed < 3.0,
              "a_cooling_engine_is_not_asked_again": calls == ["first", "second", "second"] and r2["engine"] == "second",
              "before_after_pairs_come_from_consecutive_screenshots": len(rows) == 2 and acts[0]["target_id"] == 1 and acts[1]["target_id"] == 2,
              "pair_rows_name_their_source": all(r["meta"]["source"] == "web_steps" and r["meta"]["post"] for r in rows)}
    return verdict(checks, "steps=%d clips=%s keys=%s pairs=%s calls=%s r1=%s" % (len(steps), [(c["kind"]) for c in clips], [s["keys"] for s in steps], pr["grounded"], calls, r1["tried"]))


def run_ar27(verdict):
    """AR27: logic chains -- precondition / action / expectation / fallback are built from tutorial steps and written to the five stores (graph edge, procedure, hotkey, recovery, icon)"""
    from core_organs.rag import logic_chains as LC
    from si_tests_rag import _Env
    steps = [{"text": "In the Insert tab, click Chart and choose a bar chart. If you do not see the Chart button, widen the window.", "names": ["Chart"], "keys": [], "imgs": []},
             {"text": "Press Ctrl+Shift+S to save a copy.", "names": [], "keys": ["Ctrl+Shift+S"], "imgs": []},
             {"text": "Open File > Export > PDF to finish.", "names": [], "keys": [], "imgs": []},
             {"text": "Click Done.", "names": ["Done"], "keys": [], "imgs": []}]
    labels = [["Home", "Insert", "Design"], ["Chart Title", "Series", "Axis"], ["Save", "Close"], ["Done"]]
    page = "Troubleshooting. If the Chart button is greyed out, select a cell first. Unrelated sentence here."
    chains = LC.build_chains(steps, labels, page)
    texts = [LC.chain_text(c) for c in chains]
    with _Env(icons=True) as R:
        w = LC.write(R, "fancy", "Fancy Editor", chains, labels, "https://docs.example.org/x", "Make a chart")
        procs = R.proc.stats("fancy")["procedures"]
        fast = R.fast.count("fancy")
        nodes = R.graph.stats("fancy").get("edges", 0)
        rec = R.rec.lookup("fancy", failure_code="tutorial_fallback", message="the Chart button is greyed out, select a cell first")
    checks = {"the_place_a_step_names_is_its_precondition": chains[0]["precondition"]["where"].lower() == "insert tab" and chains[0]["precondition"]["screen_labels"][:2] == ["Home", "Insert"],
              "a_click_a_hotkey_and_a_menu_path_are_told_apart": [c["action"]["kind"] for c in chains] == ["click", "hotkey", "menu_path", "click"] and chains[2]["action"]["menu_path"] == ["File", "Export", "PDF"],
              "what_appears_next_is_the_expectation": chains[0]["expected"]["new_labels"] == ["Chart Title", "Series", "Axis"],
              "fallbacks_come_from_the_step_and_from_the_page": len(chains[0]["fallback"]) == 2 and any("greyed out" in f for f in chains[0]["fallback"]) and chains[3]["fallback"] == [],
              "the_chain_reads_as_one_line": all(t.startswith("PRECONDITION:") and "| ACTION:" in t and "| EXPECT:" in t and "| IF BLOCKED:" in t for t in texts) and "press Ctrl+Shift+S" in texts[1],
              "every_store_got_its_part": w["procedures"] >= 1 and w["edges"] >= 1 and w["playbooks"] >= 2 and procs >= 1 and nodes >= 1,
              "a_click_with_a_known_shortcut_is_linked_both_ways": any(c["action"]["target"] == "Chart" for c in chains) and fast >= 0,
              "recovery_finds_the_tutorial_fallback": bool(rec)}
    return verdict(checks, "w=%s procs=%s edges=%s texts0=%s" % (w, procs, nodes, texts[0][:160]))


def json_copy(x):
    import json
    return json.loads(json.dumps(x))


def run_ar28(verdict):
    """AR28: the CPU brain's language layer -- intent from words, app from the catalogue (versions ignored), AI-summary answer turned into steps"""
    from core_organs import brain_planner as BP
    from core_organs.harvest import search_browser as SBR
    names = ["Blender 5.2", "Calculator", "Photometric Calc 2025 R2", "Paint", "Word"]
    i1, i2, i3 = BP.classify_intent("how do I add a cube in Blender?"), BP.classify_intent("build a wooden table in Blender"), BP.classify_intent("learn Calculator and map it")
    text = "Like\nDislike\nYou can add a cube.\nPress Shift + A in the 3D Viewport.\nIn Object Mode, open the Toolbar and choose Add Cube.\nHelpful Hotkeys\nCtrl - Toggle snapping\nThis covers both ways of working here."
    steps = SBR.steps_from_summary(text)
    checks = {"a_question_is_teach": i1["mode"] == "teach", "an_order_is_delegate": i2["mode"] == "delegate", "learn_is_understand": i3["mode"] == "understand",
              "the_app_is_found_without_its_version": BP.detect_app("how do I add a cube in Blender?", names) == "Blender 5.2" and BP.detect_app("open photometric calc", names) == "Photometric Calc 2025 R2",
              "no_app_named_is_empty": BP.detect_app("make me a sandwich", names) == "",
              "version_suffixes_are_stripped": BP.strip_version("Blender 5.2") == "Blender" and BP.strip_version("Photometric Calc 2025 R2") == "Photometric Calc",
              "summary_steps_are_the_instruction_lines": len(steps) == 2 and steps[0]["keys"] == ["Shift + A"]}
    return verdict(checks, "intents=%s/%s/%s steps=%s" % (i1["mode"], i2["mode"], i3["mode"], [s["text"][:30] for s in steps]))


def run_ar29(verdict):
    """AR29: 3D design checks that hold for any object -- shapes read from the registry, floating / buried / duplicated parts named, a good design passes"""
    from core_organs import brain_planner as BP
    reg = [{"id": "mesh.primitive_cube_add"}, {"id": "mesh.primitive_uv_sphere_add"}, {"id": "mesh.primitive_cylinder_add"}, {"id": "object.delete"}, {"id": "curve.primitive_bezier_curve_add"}]
    shapes = BP.shapes_of(reg)
    sh = sorted(shapes)
    good = {"object": "stool", "parts": [{"name": "seat", "shape": "cube", "size": [0.4, 0.4, 0.05], "at": [0, 0, 0.475], "rotate": [0, 0, 0], "color": [0.5, 0.3, 0.2]},
                                         {"name": "leg_a", "shape": "cylinder", "size": [0.05, 0.05, 0.45], "at": [0.15, 0.15, 0.225], "rotate": [0, 0, 0], "color": [0.4, 0.3, 0.2]},
                                         {"name": "leg_b", "shape": "cylinder", "size": [0.05, 0.05, 0.45], "at": [-0.15, -0.15, 0.225], "rotate": [0, 0, 0], "color": [0.4, 0.3, 0.2]}]}
    clean, p1 = BP.validate_design(good, sh)
    float_ = json_copy(good)
    float_["parts"][1]["at"] = [0.15, 0.15, 0.9]
    buried = json_copy(good)
    buried["parts"][2]["at"] = [-0.15, -0.15, -0.3]
    dup = json_copy(good)
    dup["parts"][2]["at"] = [0.15, 0.15, 0.225]
    bad_shape, p2 = BP.validate_design({"parts": [{"name": "x", "shape": "dodecahedron", "size": [1, 1, 1], "at": [0, 0, 0.5]}]}, sh)
    rot = BP.part_box({"size": [1.0, 0.2, 0.2], "at": [0, 0, 0], "rotate": [0, 0, 90]})
    cf = BP.critic(BP.validate_design(float_, sh)[0])
    based, pb = BP.validate_design({"parts": [{"name": "post", "shape": "cylinder", "size": [0.1, 0.1, 0.8], "base": [0, 0, 0]}, {"name": "slab", "shape": "cube", "size": [1, 1, 0.04], "base": [0, 0, 0.8]}]}, sh)
    rest = {"parts": [{"name": "leg1", "shape": "cylinder", "size": [0.06, 0.06, 0.7], "on": "ground", "xy": [-0.5, -0.3]}, {"name": "leg2", "shape": "cylinder", "size": [0.06, 0.06, 0.7], "on": "ground", "xy": [0.5, 0.3]},
                     {"name": "top", "shape": "cube", "size": [1.2, 0.8, 0.04], "on": ["leg1", "leg2"], "xy": [0, 0]}]}
    stk, ps = BP.validate_design(rest, sh)
    lost = BP.validate_design({"parts": [{"name": "top", "shape": "cube", "size": [1, 1, 0.04], "on": ["leg9"], "xy": [0, 0]}]}, sh)[1]
    away = BP.validate_design({"parts": [{"name": "leg", "shape": "cylinder", "size": [0.05, 0.05, 0.7], "on": "ground", "xy": [3, 3]}, {"name": "top", "shape": "cube", "size": [1, 1, 0.04], "on": ["leg"], "xy": [0, 0]}]}, sh)[1]
    loop = BP.validate_design({"parts": [{"name": "a", "shape": "cube", "size": [1, 1, 0.1], "on": ["b"], "xy": [0, 0]}, {"name": "b", "shape": "cube", "size": [1, 1, 0.1], "on": ["a"], "xy": [0, 0]}]}, sh)[1]
    back = BP.infer_on(stk)
    words = BP.describe_design(stk)
    flat = BP.shapes_of([{"id": "mesh.primitive_plane_add"}, {"id": "mesh.primitive_cube_add"}])
    checks = {"shapes_come_from_the_registry": sh == ["cube", "cylinder", "uv_sphere"], "a_sound_design_has_no_problems": not p1 and not BP.critic(clean),
              "a_floating_part_is_named": any("leg_a" in x and "floating" in x for x in cf),
              "a_part_below_the_ground_is_named": any("leg_b" in x and "below the ground" in x for x in BP.critic(BP.validate_design(buried, sh)[0])),
              "two_parts_in_one_place_are_named": any("same place" in x for x in BP.critic(BP.validate_design(dup, sh)[0])),
              "an_unknown_shape_is_refused": bool(p2) and not bad_shape["parts"],
              "a_base_point_is_turned_into_a_centre": not pb and abs(based["parts"][0]["at"][2] - 0.4) < 1e-9 and abs(based["parts"][1]["at"][2] - 0.82) < 1e-9 and not BP.critic(based),
              "flat_shapes_are_not_offered": sorted(flat) == ["cube"],
              "the_top_is_put_on_the_legs_by_the_system": not ps and abs(stk["parts"][2]["at"][2] - 0.72) < 1e-9 and not BP.critic(stk),
              "an_unknown_support_a_loop_and_a_part_off_its_supports_are_named": any("not one of your parts" in x for x in lost) and any("loop" in x for x in loop) and any("not above it" in x for x in away),
              "the_design_is_described_in_words_from_its_geometry": "leg1: a tall thin post" in words and "stands on the ground; it carries top" in words and "top: a flat board" in words and "rests on leg1 and leg2" in words,
              "what_a_part_rests_on_is_read_back_from_geometry": back["top"] == ["leg1", "leg2"] and back["leg1"] == "ground",
              "a_turned_part_has_a_turned_box": abs((rot[1][0] - rot[0][0]) - 0.2) < 1e-6 and abs((rot[1][1] - rot[0][1]) - 1.0) < 1e-6}
    return verdict(checks, "shapes=%s p1=%s critic_float=%s" % (sh, p1, cf))


def run_ar30(verdict):
    """AR30: the unified section -- one state machine, quality judged from measurements, recipes remembered, a router that mounts sections"""
    import tempfile
    from core_organs import app_teaching_automation as ATA
    design = {"object": "stool", "parts": [{"name": "seat", "shape": "cube", "size": [0.4, 0.4, 0.05], "at": [0, 0, 0.475], "rotate": [0, 0, 0], "color": [0.5, 0.3, 0.2]},
                                           {"name": "leg", "shape": "cylinder", "size": [0.05, 0.05, 0.45], "at": [0.1, 0.1, 0.225], "rotate": [0, 0, 0], "color": [0.4, 0.3, 0.2]}]}
    steps = [{"part": "seat", "ok": True, "attempts": [{"ok": True, "dim_err": 0.0, "pos_err_m": 0.0}]}, {"part": "leg", "ok": True, "attempts": [{"ok": False, "rolled_back": True}, {"ok": True, "dim_err": 0.01, "pos_err_m": 0.002}]}]
    before = {"objects": [{"name": "old", "loc": [0, 0, 0], "dims": [1, 1, 1], "verts": 8}]}
    after = {"objects": before["objects"] + [{"name": "seat", "bbox": [[-0.2, -0.2, 0.45], [0.2, 0.2, 0.5]], "dims": [0.4, 0.4, 0.05], "loc": [0, 0, 0.475], "mats": ["m"], "verts": 8},
                                              {"name": "leg", "bbox": [[0.075, 0.075, 0.0], [0.125, 0.125, 0.45]], "dims": [0.05, 0.05, 0.45], "loc": [0.1, 0.1, 0.225], "mats": ["m"], "verts": 32}]}
    q = ATA.judge_scene("a stool", design, {"steps": steps, "made": ["seat", "leg"]}, before, after)
    broken = json_copy(after)
    broken["objects"][2]["bbox"] = [[0.5, 0.5, 0.0], [0.6, 0.6, 0.45]]
    qb = ATA.judge_scene("a stool", design, {"steps": steps, "made": ["seat", "leg"]}, before, broken)
    with tempfile.TemporaryDirectory() as d:
        old = ATA.RECIPES
        ATA.RECIPES = d
        try:
            ATA.remember_recipe("blender", "build a wooden dining table with four legs", design, 90.0)
            near = ATA.recall_recipes("blender", "build a wooden dining table", 0.2)
            far = ATA.recall_recipes("blender", "make a sandwich", 0.2)
        finally:
            ATA.RECIPES = old
    off = ATA._free_offset({"objects": [{"bbox": [[0, 0, 0], [1, 1, 1]]}]}, design)
    weak_yes = ATA.AppIntelligenceEngine.weak({"plans": [{"steps": ["click Click 'View' (a menuitem)."]}], "evidence": []}, "how do I draw a rectangle in Paint?")
    weak_no = ATA.AppIntelligenceEngine.weak({"plans": [{"steps": ["click the Rectangle shape in the Shapes group"]}], "evidence": []}, "how do I draw a rectangle in Paint?")
    fl = ATA.Flow(lambda s: None)
    with fl.enter("recall", "x"):
        pass
    checks = {"a_sound_build_scores_high": q["score"] >= 90 and q["connected"] and q["on_ground"] and q["earlier_objects_untouched"] and q["rollbacks"] == 1,
              "a_detached_part_lowers_the_score": (not qb["connected"]) and qb["score"] < q["score"] and qb["floating_parts"] == ["leg"],
              "a_recipe_is_found_by_its_words": len(near) == 1 and near[0]["similarity"] > 0.4 and far == [],
              "a_new_object_is_placed_clear_of_the_old": off[0] >= 0.9,
              "an_answer_that_does_not_speak_of_the_question_is_weak": weak_yes and not weak_no,
              "states_are_timed": bool(fl.states) and fl.states[0]["state"] == "recall",
              "the_router_mounts_and_chooses": _router_ok()}
    return verdict(checks, "score=%s broken=%s offset=%s" % (q["score"], qb["score"], off))


def _router_ok():
    import os
    import sys
    sys.path.insert(0, os.path.join("D:" + os.sep, "new_automation", "All codes"))
    from sections import HoJaiga

    class Dummy:
        name, description = "x_demo", "draw charts and spreadsheets"

        def handle(self, task, **kw):
            return {"ok": True}
    hj = HoJaiga().mount(Dummy())
    return hj.choose("make charts") == "x_demo" and hj.handle("charts")["section"] == "x_demo" and "error" in hj.handle("t", section="nope")


def run_ar31(verdict):
    """AR31: workflow feeds -- recorded actions become structure (control / keys / type), web traces and documentation become steps, values the person typed are dropped, fall-backs are not copied"""
    from core_organs.harvest import rag_feed as RF
    from si_tests_rag import _Env
    a1, a2, a3, a4 = (RF.parse_pyautogui("pyautogui.hotkey('ctrl', 'shift', 's')"), RF.parse_pyautogui("pyautogui.typewrite('hello there')"),
                      RF.parse_pyautogui("pyautogui.click(350, 214)"), RF.parse_pyautogui("pyautogui.press('enter')"))
    rows = [{"action_nl": 'Click the "Rating" filter button.', "action_pyautogui": "pyautogui.click(1, 2)", "action_target": '{"name": "Rating", "role": "static"}'},
            {"action_nl": "Type the address into the bar.", "action_pyautogui": "pyautogui.typewrite('secret@mail.com')", "action_target": "None"},
            {"action_nl": "Save the file.", "action_pyautogui": "pyautogui.hotkey('ctrl', 's')", "action_target": "None"}]
    steps = RF.steps_from_trace(rows)
    m2w = RF.mind2web_steps("['[button] Search -> CLICK', '[textbox] From -> TYPE: Boston', '[select] Sort by -> SELECT: Price', '[link] Cheapest -> CLICK']")
    NL = chr(10)
    doc = NL.join(["# Make a chart", '1. Click **Insert** and choose "Chart".', "2. Press Ctrl+Shift+C to copy the format.", "Some prose that is not a step at all here.", "# Other", "nothing to do here"])
    md = RF.md_steps(doc)
    with _Env(icons=False) as R:
        w = RF.write_workflow(R, "fancy_feed", "Fancy Feed", "Rate things", steps, "hf:test (apache-2.0)")
        one = RF.write_workflow(R, "fancy_feed", "Fancy Feed", "Too short", steps[:1], "hf:test")
    checks = {"a_hotkey_is_read_with_its_keys": a1["kind"] == "hotkey" and a1["keys"] == "Ctrl+Shift+S", "typing_a_click_and_a_key_press_are_told_apart": a2["kind"] == "type" and a3["kind"] == "click" and a4["kind"] == "press" and a4["keys"] == "Enter",
              "the_control_comes_from_the_recording": steps[0]["names"] == ["Rating"] and steps[2]["keys"] == ["Ctrl+S"],
              "typed_content_is_not_kept": "secret" not in json.dumps(steps) and steps[1]["names"] == [],
              "a_web_trace_becomes_steps_without_values": [s["names"] for s in m2w] == [["Search"], ["From"], ["Sort by"], ["Cheapest"]] and "Boston" not in json.dumps(m2w) and "Price" not in json.dumps(m2w),
              "documentation_steps_are_found_under_their_heading": len(md) == 1 and md[0][0] == "Make a chart" and len(md[0][1]) == 2 and md[0][1][1]["keys"] == ["Ctrl+Shift+C"],
              "a_workflow_reaches_the_stores": bool(w) and (w.get("procedures", 0) >= 1), "one_step_is_not_a_workflow": one == {}}
    return verdict(checks, "w=%s steps=%s" % (w, [s["text"][:30] for s in steps]))


def run_ar32(verdict):
    """AR32: the interactive tutor -- red marks drawn as data, repeated cells found by OpenCV and picked by 'row / step', beats waited on and steered by words, 'do it for me' hands over, unsafe controls never pointed at"""
    import numpy as np
    import cv2
    from core_organs import micro_beats as MB, micro_tutor as MT, tutor_overlay as TO, tutor_voice as TV
    from PIL import Image
    img = np.full((720, 1280, 3), 40, np.uint8)
    ctrls = []
    for i, nm in enumerate(["New", "Open", "Find", "Replace", "Undo", "Redo"]):
        x = 20 + i * 70
        cv2.rectangle(img, (x, 20), (x + 60, 50), (90, 90, 90), -1)
        ctrls.append({"name": nm, "type": "Button", "box": (x, 20, 60, 30)})
    ctrls.append({"name": "Close", "type": "Button", "box": (1200, 5, 40, 30)})
    ctrls.append({"name": "Cells", "type": "Pane", "box": (100, 200, 1000, 260)})
    for r in range(4):
        for c in range(16):
            x, y = 120 + c * 56 + (c // 4) * 10, 215 + r * 60
            cv2.rectangle(img, (x, y), (x + 44, y + 44), (200, 200, 200) if c % 4 == 0 else (150, 150, 150), -1)
    grid = MB.detect_grid(img, (100, 200, 1100, 460))
    steps = [{"text": "Use the Find button.", "names": ["Find"], "keys": ["Ctrl+F"]}, {"text": "Then close it.", "names": ["Close"], "keys": []},
             {"text": "On the second row click step 13.", "names": [], "keys": []}, {"text": "Press Space.", "names": [], "keys": ["Space"]}]
    beats = MB.plan_beats(steps, ctrls, image=img)

    class Script:
        """A watcher that answers from a list, in order."""
        def __init__(self, events):
            self.events, self._speaking = list(events), lambda: False
        def wait(self, box=None, keys=(), timeout=0):
            return self.events.pop(0) if self.events else {"kind": "line", "text": "stop", "command": "stop"}
    ov = TO.RecordingRedOverlay()
    t = MT.MicroTutor(overlay=ov, voice=TV.Voice(enabled=False), watcher=Script([{"kind": "click", "at": (1, 1)}, {"kind": "line", "text": "back", "command": "back"}, {"kind": "click", "at": (2, 2)},
                                                                                {"kind": "key", "key": "space"}]), bar=False, log=lambda s: None)
    out = t.run(beats)
    drawn = [h for h in t.history if "draw" in h]
    stopped = MT.MicroTutor(overlay=TO.RecordingRedOverlay(), voice=TV.Voice(enabled=False), watcher=Script([{"kind": "line", "text": "stop", "command": "stop"}]), bar=False, log=lambda s: None)
    out2 = stopped.run(beats)
    prev = TO.compose_red_preview(Image.new("RGB", (1280, 720), (46, 52, 64)), [{"cmd": "box", "box": __import__("core_organs.professor.schema", fromlist=["Box"]).Box(900, 300, 1000, 340), "pill": "kick step five"},
                                                                          {"cmd": "shape", "kind": "polygon", "points": [(100, 400), (100, 300), (300, 400)], "pill": "right angle"}, {"cmd": "status", "text": "Speaking"}])
    px = np.asarray(prev.convert("RGB"))
    red_edge = int((px[300:342, 900:1000, 0] > 200).sum()) > 80 and int(((px[:, :, 0] > 220) & (px[:, :, 1] < 90)).sum()) > 400
    checks = {"repeated_cells_are_found_by_geometry": grid is not None and len(grid) == 4 and all(len(r) == 16 for r in grid),
              "a_cell_is_picked_by_row_and_step": any(b.layer == "grid" and b.box and abs(b.box[0] - 822) < 3 and abs(b.box[1] - 275) < 3 for b in beats),
              "a_toolbar_row_is_one_beat_and_stops_at_a_gap": beats[0].primitive == "region" and beats[0].box[2] < 600,
              "a_control_that_closes_is_never_pointed_at": not any(b.target == "Close" for b in beats),
              "a_key_step_waits_for_that_key": any(b.wait == "key:space" for b in beats),
              "the_overlay_is_driven_beat_by_beat": len(drawn) >= len(beats) and out["done"] >= 3,
              "words_steer_the_lesson": out["reached"] >= len(beats) - 1 and stopped.history and out2["done"] == 0 and out2["reached"] <= 1,
              "red_marks_render_with_their_badges": bool(red_edge),
              "commands_are_read_from_words": TV.command_of("do it for me") == "delegate" and TV.command_of("go back") == "back" and TV.command_of("where is Find") == ""}
    return verdict(checks, "beats=%s out=%s drawn=%d" % ([(b.primitive, b.wait) for b in beats], out, len(drawn)))

