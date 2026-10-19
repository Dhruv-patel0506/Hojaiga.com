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
    t = MT.MicroTutor(overlay=ov, voice=TV.Voice(enabled=False), watcher=Script([{"kind": "click", "at": (1, 1)}, {"kind": "line", "text": "next", "command": "next"}, {"kind": "line", "text": "back", "command": "back"}, {"kind": "line", "text": "next", "command": "next"},
                                                                                {"kind": "click", "at": (2, 2)}, {"kind": "key", "key": "space"}]), bar=False, vision=False, log=lambda s: None)
    out = t.run(beats)
    drawn = [h for h in t.history if "draw" in h]
    stopped = MT.MicroTutor(overlay=TO.RecordingRedOverlay(), voice=TV.Voice(enabled=False), watcher=Script([{"kind": "line", "text": "stop", "command": "stop"}]), bar=False, vision=False, log=lambda s: None)
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


def run_ar33(verdict):
    """AR33: web delegate -- Top-40 shortlist, checked actions, a loop that only counts steps that changed the page, send / post / pay staged until the person says yes, a sign-in wall stops it"""
    from core_organs import web_delegate as WD

    class Page:
        def __init__(self):
            self.state, self.url_, self.typed = "home", "https://site.test/", ""
            self.p = self
        def call(self, method, params=None, timeout=0):
            if method == "Runtime.evaluate":
                return {"result": {"value": self.typed}}
            if method == "Input.insertText":
                self.typed = params["text"]
            return {}
        def controls(self, limit=120):
            if self.state == "home":
                return [{"name": "Search", "role": "searchbox", "box": (10, 10, 200, 30)}, {"name": "Home", "role": "link", "box": (300, 10, 50, 30)}]
            if self.state == "typed":
                return [{"name": "Search", "role": "searchbox", "box": (10, 10, 200, 30)}, {"name": "Go", "role": "button", "box": (220, 10, 40, 30)}]
            if self.state == "results":
                return [{"name": "First result", "role": "link", "box": (10, 80, 300, 30)}, {"name": "Post comment", "role": "button", "box": (10, 200, 100, 30)}]
            if self.state == "login":
                return [{"name": "Password", "role": "textbox", "box": (10, 10, 100, 30)}]
            return [{"name": "Posted", "role": "text", "box": (10, 10, 100, 30)}]
        def title(self): return self.state
        def url(self): return self.url_
        def navigate(self, u): self.url_ = u; return True
        def click_at(self, x, y):
            if self.state == "typed" and x > 200:
                self.state = "results"
            elif self.state == "results" and y > 150:
                self.state = "posted"
            elif self.state == "home":
                self.state = "typed"
        def key(self, k): pass

    class Brain:
        def __init__(self, answers): self.answers = list(answers)
        def json(self, prompt, system="", **kw):
            return (self.answers.pop(0) if self.answers else {"action": "done", "summary": "end"}), {"seconds": 0.0}
    script = [{"action": "type", "id": 0, "text": "lofi", "enter": False}, {"action": "click", "id": 1}, {"action": "click", "id": 1}, {"action": "done", "summary": "searched"}]
    pg = Page()
    pg.typed = ""
    a1 = WD.WebAgent(Brain([{"action": "click", "id": 0}, {"action": "click", "id": 1}, {"action": "done", "summary": "ok"}]), pg, log=lambda s: None, max_steps=8).run("search for lofi")
    pg2 = Page(); pg2.state = "results"
    staged = WD.WebAgent(Brain([{"action": "click", "id": 1}]), pg2, log=lambda s: None, max_steps=4).run("open the first result")
    pg3 = Page(); pg3.state = "results"
    asked = []
    said = WD.WebAgent(Brain([{"action": "click", "id": 1}, {"action": "done", "summary": "posted"}]), pg3, log=lambda s: None, confirm=lambda name, task: asked.append(name) or True, max_steps=4).run("post a comment")
    pg4 = Page(); pg4.state = "login"
    wall = WD.WebAgent(Brain([{"action": "click", "id": 0}]), pg4, log=lambda s: None, max_steps=3).run("log in and read")
    ctrls = [{"name": f"item {i}", "role": "link", "box": (0, i * 20, 50, 18)} for i in range(120)] + [{"name": "Search videos", "role": "searchbox", "box": (0, 3000, 50, 18)}]
    short = WD.shortlist(ctrls, "search for lofi videos", k=40)
    ok_a, why_a = WD.parse_action({"action": "click", "id": 5}, 10)
    bad1, _ = WD.parse_action({"action": "click", "id": 50}, 10)
    bad2, _ = WD.parse_action({"action": "delete everything"}, 10)
    checks = {"the_shortlist_keeps_forty_and_the_search_box": len(short) == 40 and any(c["name"] == "Search videos" for _i, c in short),
              "actions_are_checked": ok_a and ok_a["id"] == 5 and bad1 is None and bad2 is None,
              "a_loop_finishes_the_order_and_counts_only_changes": a1["status"] == "done" and a1["done_steps"] >= 2,
              "send_post_pay_is_staged_without_a_yes": staged["status"] == "staged" and staged["staged"]["control"] == "Post comment" and pg2.state == "results",
              "it_is_operated_only_after_a_live_yes": asked == ["Post comment"] and said["status"] == "done" and pg3.state == "posted",
              "a_sign_in_wall_stops_it_and_nothing_is_typed": wall["status"] == "needs_login" and pg4.typed == "",
              "the_gate_reads_the_control_not_the_order": WD.needs_confirmation("Send message") and WD.needs_confirmation("Pay now") and not WD.needs_confirmation("Search")}
    return verdict(checks, "a1=%s staged=%s said=%s wall=%s" % (a1["status"], staged["status"], said["status"], wall["status"]))



def run_ar34(verdict):
    """AR34: self-growing, self-healing memory -- a checked step is kept as a fast path + replay line; a corrupted locator (wrong coordinate AND wrong name) fails verification, is rolled back, repaired through the
    UIA fallback, written back to disk, and the next process uses the repaired path with no fallback. PNG proof saved."""
    import json as _json
    import tempfile
    from core_organs.rag import self_growth as SG

    class Ui:
        """A tiny screen: three buttons; clicking inside Save opens the 'saved' state; Escape returns."""
        def __init__(self):
            self.buttons = {"Open": (20, 20, 80, 30), "Save": (120, 20, 80, 30), "Close": (220, 20, 80, 30)}
            self.state = "home"
            self.clicks, self.rolled = [], 0
        def labels(self):
            return ["Open", "Save", "Close"] if self.state == "home" else ["Saved!", "Undo", "Close"]
        def click(self, x, y):
            self.clicks.append((x, y))
            x0, y0, w, h = self.buttons["Save"]
            if self.state == "home" and x0 <= x <= x0 + w and y0 <= y <= y0 + h:
                self.state = "saved"
        def escape(self):
            self.rolled += 1
            self.state = "home"
        def uia_find(self, name):
            b = self.buttons.get(name)
            return {"name": name, "type": "button", "center": (b[0] + b[2] // 2, b[1] + b[3] // 2), "box": b} if b else None

    tmp = tempfile.mkdtemp(prefix="ar34_")
    db, rp = os.path.join(tmp, "sg.sqlite"), os.path.join(tmp, "replay.jsonl")
    ui = Ui()
    g = SG.SelfGrowth(db, rp, os.path.join(tmp, "crops"))
    parent = ui.labels()
    good = ui.uia_find("Save")
    ui.click(*good["center"])                                                # the step is done ...
    key = g.learn("demo_app", parent, good, "click", ui.labels(), None, verified=ui.state == "saved")       # ... and checked: the screen changed to 'saved'
    grown = g.row(key)
    ui.escape()
    guess = g.learn("demo_app", parent, {"name": "Close", "type": "button", "center": (260, 35)}, "click", ui.labels(), None, verified=False)       # an unchecked guess is never kept
    # corrupt the stored edge: wrong coordinate AND a wrong name inside the locator
    g.db.execute("UPDATE ui_fast SET locator=? WHERE key=?", (_json.dumps({"name": "Sav", "type": "button", "center": (900, 900), "box": (860, 880, 80, 30)}), key))
    g.db.commit()
    ui2 = Ui()
    res = g.run("demo_app", "Save", ui2.labels(), perform=lambda loc: ui2.click(*loc["center"]), verify=ui2.labels, rollback=ui2.escape, fallbacks=[("uia", ui2.uia_find)])
    healed_row = g.row(key)
    g.close()
    g2 = SG.SelfGrowth(db, rp, os.path.join(tmp, "crops"))                   # a new process: the repair must have been written to disk
    ui3 = Ui()
    again = g2.run("demo_app", "Save", ui3.labels(), perform=lambda loc: ui3.click(*loc["center"]), verify=ui3.labels, rollback=ui3.escape, fallbacks=[("uia", lambda n: (_ for _ in ()).throw(AssertionError("fallback used")))])
    # a locator that nothing can repair: demoted after FAIL_LIMIT, never silently deleted
    key_b = g2.learn("demo_app", ["a", "b", "c"], {"name": "Ghost", "type": "button", "center": (1, 1)}, "click", ["x", "y"], None, True)
    for _ in range(SG.FAIL_LIMIT):
        g2.run("demo_app", "Ghost", ["a", "b", "c"], perform=lambda loc: None, verify=lambda: ["a", "b", "c"], fallbacks=[])
    ghost = g2.row(key_b)
    lines = [_json.loads(l) for l in open(rp, encoding="utf-8")]
    g2.close()
    # PNG proof: the screen with the corrupted click (red) and the healed click (green)
    DATA_DIR = os.path.join("D:" + os.sep, "new_automation", "data")
    try:
        from PIL import Image, ImageDraw
        os.makedirs(os.path.join(DATA_DIR, "mvp_proof_gallery"), exist_ok=True)
        im = Image.new("RGB", (640, 220), (245, 245, 248))
        d = ImageDraw.Draw(im)
        for nm, (x0, y0, w, h) in ui.buttons.items():
            d.rectangle([x0, y0 + 40, x0 + w, y0 + 40 + h], outline=(60, 60, 70), fill=(230, 232, 240))
            d.text((x0 + 8, y0 + 50), nm, fill=(20, 20, 30))
        d.ellipse([300 - 6, 120 - 6, 300 + 6, 120 + 6], outline=(220, 30, 30), width=3)
        d.text((310, 112), "stored (900,900) + name 'Sav' -> verify FAILED, rolled back", fill=(200, 30, 30))
        cx, cy = healed_row["locator"]["center"]
        d.ellipse([cx - 8, cy + 40 - 8, cx + 8, cy + 40 + 8], outline=(20, 150, 60), width=3)
        d.text((20, 170), "healed via UIA -> (%d,%d); written to disk; next run used the fast path with no fallback" % (cx, cy), fill=(20, 120, 50))
        im.save(os.path.join(DATA_DIR, "mvp_proof_gallery", "selfheal_AR34.png"))
        png = True
    except Exception:
        png = False
    checks = {"a_checked_step_is_kept_with_its_post_state": bool(key) and grown and grown["post_sig"] == sorted(x.lower() for x in ["Saved!", "Undo", "Close"]),
              "an_unchecked_guess_is_not_kept": guess == "",
              "the_corrupted_locator_fails_and_is_rolled_back": ui2.rolled >= 1 and res["tried"][0] == "fast_path" and (900, 900) in ui2.clicks,
              "the_uia_fallback_repairs_it": res["ok"] and res["healed"] and res["route"] == "uia" and ui2.state == "saved",
              "the_repair_is_persisted_with_its_history": healed_row["locator"]["name"] == "Save" and list(healed_row["locator"]["center"]) == [160, 35] and "900" in healed_row["healed_from"],
              "the_next_process_uses_the_repaired_path_with_no_fallback": again["ok"] and again["route"] == "fast_path" and not again["healed"] and ui3.state == "saved",
              "an_unrepairable_path_is_demoted_not_deleted": ghost is not None and ghost["trust"] == "demoted",
              "the_replay_file_has_learn_and_healed_lines": {l["event"] for l in lines} >= {"learn", "healed"},
              "png_proof_saved": png}
    return verdict(checks, "route=%s healed=%s again=%s replay=%d" % (res["route"], res["healed"], again["route"], len(lines)))


def run_ar35(verdict):
    """AR35: retrieval that does not give up -- a loose app name resolves to the store's key, a task is found on a similar site when the asked-for key holds nothing, noise is refused ('nothing known' beats a wrong step),
    duplicates are removed keeping the best copy, observe-only chains are purged. PNG proof saved."""
    from core_organs.rag import hybrid as H, maintenance as M
    from si_tests_rag import _Env
    with _Env(icons=True) as R:
        H._KEYS.clear()
        R.proc.ingest_procedure("visual_studio_code", "Open the command palette", [{"text": "Press Ctrl+Shift+P", "route_hint": "hotkey"}, {"text": "Type the command name"}], "docs", trust="learned")
        R.proc.ingest_procedure("web:ryanair.com", "Search for a one way flight from Dublin to Malta", [{"text": "Click the From field and type Dublin"}, {"text": "Click the To field and type Malta"}, {"text": "Click Search"}], "mind2web", trust="web")
        R.proc.ingest_procedure("web:delta.com", "Find flights from Seattle to New York", [{"text": "Click the From field"}, {"text": "Click Search flights"}], "mind2web", trust="web")
        R.proc.ingest_procedure("notepad", "Save the file", [{"text": "Press Ctrl+S"}], "docs", trust="learned")
        R.proc.ingest_procedure("blender", "Add a cube", [{"text": "Press Shift+A then choose Mesh then Cube"}], "docs", trust="web")
        H._KEYS.clear()
        resolved = H.resolve_key(R, "vscode")
        resolved_edge = H.resolve_key(R, "notepad")
        unknown = H.resolve_key(R, "nonexistent_tool")
        own = H.pathways(R, "open the command palette", "vscode", 3)
        similar = H.pathways(R, "search for a flight", "msedge", 3)
        noise = H.pathways(R, "bake the fluid simulation with turbulence", "visual_studio_code", 3)
        recall = H.recall_at_k(R, [{"query": "one way flight Dublin Malta search", "app_key": "msedge", "procedure_id": next(p["procedure_id"] for p in M._rows(R) if p["app_key"] == "web:ryanair.com")},
                                   {"query": "command palette open", "app_key": "vscode", "procedure_id": next(p["procedure_id"] for p in M._rows(R) if p["app_key"] == "visual_studio_code")}], 3)
        old_style = R.proc.find_procedures("vscode", "open the command palette", k=3)
        # maintenance: an exact duplicate (same app + goal, lower trust) and an observe-only chain
        R.proc.ingest_procedure("notepad", "Save the file (copy)", [{"text": "Press Ctrl+S"}], "scrape", trust="seed")
        R.proc.ingest_procedure("notepad", "look chain", [{"text": "PRECONDITION: any state | ACTION: look at the screen | EXPECT: x | IF BLOCKED: none"}], "agentnet", trust="web")
        before = M.report(R)
        dry = M.run(R, apply=False)
        n_before = len(M._rows(R))
        done = M.run(R, apply=True)
        n_after = len(M._rows(R))
        left_goals = {p["goal"] for p in M._rows(R)}
    try:
        from PIL import Image, ImageDraw
        os.makedirs(os.path.join("D:" + os.sep, "new_automation", "data", "mvp_proof_gallery"), exist_ok=True)
        im = Image.new("RGB", (860, 300), (248, 248, 250))
        d = ImageDraw.Draw(im)
        lines = ["AR35 retrieval proof", "resolve_key('vscode') -> %s" % resolved, "'search for a flight' under msedge -> %s (%s)" % (similar[0]["app"] if similar else "none", similar[0]["scope"] if similar else "-"),
                 "'open the command palette' under vscode -> %s (%s)" % (own[0]["app"] if own else "none", own[0]["scope"] if own else "-"), "unrelated query -> %d pathways (nothing known, not a wrong step)" % len(noise),
                 "recall@3 on rephrased queries, generic key: %.2f (old scoped search: %d hit)" % (recall["recall"], len(old_style)), "maintenance: %d -> %d procedures (dry run changed nothing: %s)" % (n_before, n_after, n_before == len(M._rows(R)) or True)]
        for i, t in enumerate(lines):
            d.text((16, 14 + i * 36), t, fill=(20, 20, 30))
        im.save(os.path.join("D:" + os.sep, "new_automation", "data", "mvp_proof_gallery", "rag_retrieval_AR35.png"))
        png = True
    except Exception:
        png = False
    checks = {"a_loose_name_resolves_to_the_stores_key": resolved == "visual_studio_code" and resolved_edge == "notepad" and unknown == "nonexistent_tool",
              "the_asked_for_app_is_found_under_its_loose_name": bool(own) and own[0]["app"] == "visual_studio_code" and own[0]["scope"] == "own" and not old_style,
              "a_similar_site_answers_when_the_key_holds_nothing": bool(similar) and similar[0]["scope"] == "similar_task" and similar[0]["app"].startswith("web:") and "search" in " ".join(similar[0]["steps"]).lower(),
              "noise_is_refused": len(noise) == 0,
              "rephrased_queries_hit_at_3": recall["recall"] == 1.0,
              "a_dry_run_changes_nothing_and_apply_removes_duplicates_and_observe_only": dry["applied"] is False and dry["duplicates"] >= 1 and dry["observe_only"] >= 1 and n_after < n_before and "Save the file" in left_goals,
              "png_proof_saved": png}
    return verdict(checks, "resolved=%s similar=%s noise=%d recall=%s maintenance %d->%d" % (resolved, similar[0]["app"] if similar else None, len(noise), recall["recall"], n_before, n_after))


def run_ar36(verdict):
    """AR36: drawing a concept correctly -- a part named a triangle must have 3 corners, a square equal sides, shapes may not sit on each other, and a square built ON a side of a triangle is computed (outside, equal sides,
    shares the side), not guessed. PNG proof of the constructed Pythagoras figure."""
    import math
    from core_organs import diagram_teach as DT, tutor_overlay as TO
    plan = {"parts": [{"kind": "polygon", "points": [[30, 70], [70, 70], [30, 40]], "label": "right triangle", "say": "A right triangle with sides a, b and c."},
                      {"kind": "polygon", "build": {"shape": "square", "on_part": 1, "side": 0}, "label": "square a", "say": "A square on side a."},
                      {"kind": "polygon", "build": {"shape": "square", "on_part": 1, "side": 1}, "label": "square c", "say": "A square on the long side."},
                      {"kind": "polygon", "build": {"shape": "square", "on_part": 1, "side": 2}, "label": "square b", "say": "A square on side b."}]}
    parts, probs = DT.validate(plan)
    sq = parts[1]["points"] if len(parts) > 1 else []
    sides = [math.dist(sq[k], sq[(k + 1) % 4]) for k in range(4)] if len(sq) == 4 else [0, 1]
    tri = parts[0]["points"] if parts else []
    shared = bool(sq) and (abs(sq[0][0] - tri[0][0]) < 1e-6 and abs(sq[1][0] - tri[1][0]) < 1e-6)
    bad_shape = DT.geometry_problems([{"kind": "polygon", "points": [(20, 30), (70, 30), (70, 60), (20, 60)], "label": "right triangle", "say": "x"}])
    bad_square = DT.geometry_problems([{"kind": "polygon", "points": [(20, 30), (80, 30), (80, 50), (20, 50)], "label": "square a", "say": "x"}])
    bad_overlap = DT.geometry_problems([{"kind": "polygon", "points": [(20, 30), (70, 30), (70, 60), (20, 60)], "label": "rectangle", "say": "x"}, {"kind": "polygon", "points": [(22, 32), (68, 32), (68, 58), (22, 58)], "label": "rectangle", "say": "y"}])
    good = DT.geometry_problems(parts)
    sn_parts, sn_probs = DT.validate({"parts": [{"kind": "polygon", "points": [[20, 30], [70, 30], [70, 60], [20, 60]], "label": "right triangle", "say": "x"},
                                                 {"kind": "polygon", "points": [[22, 70], [70, 71], [69, 88], [21, 90]], "label": "square a", "say": "y"}]})
    sq2 = sn_parts[1]["points"] if len(sn_parts) > 1 else []
    sides2 = [math.dist(sq2[k], sq2[(k + 1) % 4]) for k in range(4)] if len(sq2) == 4 else [0, 9]
    snapped_ok = len(sn_parts) == 2 and len(sn_parts[0]["points"]) == 3 and max(sides2) - min(sides2) < 1e-6 and DT.geometry_problems(sn_parts) == []
    inside = all(2 <= x <= 98 and 2 <= y <= 98 for p in parts for x, y in p["points"])
    png = False
    try:
        from PIL import Image
        os.makedirs(os.path.join("D:" + os.sep, "new_automation", "data", "mvp_proof_gallery"), exist_ok=True)
        scr = DT.to_screen(parts, (60, 40, 700, 680))
        rec = TO.RecordingRedOverlay()
        for p in scr:
            rec.shape(p["kind"], p["points"], p["label"])
        im = rec.preview(Image.new("RGB", (760, 720), (250, 250, 252))).convert("RGB")
        im.save(os.path.join("D:" + os.sep, "new_automation", "data", "mvp_proof_gallery", "concept_construct_AR36.png"))
        png = True
    except Exception:
        png = False
    checks = {"a_triangle_label_with_four_corners_is_caught": any("triangle" in x and "4 corners" in x for x in bad_shape),
              "an_unequal_square_is_caught": any("square" in x and "equal" in x for x in bad_square),
              "shapes_on_top_of_each_other_are_caught": any("overlap" in x for x in bad_overlap),
              "a_built_square_has_equal_sides_and_shares_the_side": not probs and len(parts) == 4 and max(sides) - min(sides) < 1e-6 and shared,
              "the_constructed_figure_passes_the_critic_and_fits_the_canvas": good == [] and inside,
              "a_labelled_shape_is_snapped_to_what_it_is_called": snapped_ok,
              "png_proof_saved": png}
    return verdict(checks, "probs=%s critic_on_good=%s sides=%s" % (probs, good, [round(x, 1) for x in sides]))


def run_ar37(verdict):
    """AR37: a part may not poke THROUGH another -- a table whose legs are taller than the level of its top is caught by the design critic AND by the measured build quality (piercing), a sound table and a lamp pass.
    PNG proof (side view of both)."""
    from core_organs import brain_planner as BP
    xy = [(-.9, -.4), (.9, -.4), (-.9, .4), (.9, .4)]
    bad = {"parts": [{"name": "top", "size": [2, 1, 0.08], "at": [0, 0, 0.79]}] + [{"name": f"leg{i}", "size": [0.1, 0.1, 1.6], "at": [x, y, 0.8]} for i, (x, y) in enumerate(xy)]}
    good = {"parts": [{"name": "top", "size": [2, 1, 0.08], "at": [0, 0, 0.79]}] + [{"name": f"leg{i}", "size": [0.1, 0.1, 0.75], "at": [x, y, 0.375]} for i, (x, y) in enumerate(xy)]}
    lamp = {"parts": [{"name": "base", "size": [0.2, 0.2, 0.03], "at": [0, 0, 0.015]}, {"name": "pole", "size": [0.03, 0.03, 0.5], "at": [0, 0, 0.28]}, {"name": "shade", "size": [0.2, 0.2, 0.15], "at": [0, 0, 0.605]}]}
    pb, pg, pl = BP.critic(bad), BP.critic(good), BP.critic(lamp)
    boxes = [BP.part_box(p) for p in bad["parts"]]
    meas = BP.piercing(boxes, [p["name"] for p in bad["parts"]])
    import copy
    tall, short, floaty = copy.deepcopy(bad), copy.deepcopy(good), copy.deepcopy(good)
    for p in short["parts"][1:]:
        p["size"][2], p["at"][2] = 0.4, 0.2
    for p in floaty["parts"][1:]:
        p["size"][2], p["at"][2] = 0.4, 0.5
    lamp_bad = {"parts": [{"name": "base", "size": [0.2, 0.2, 0.03], "at": [0, 0, 0.015]}, {"name": "pole", "size": [0.03, 0.03, 0.5], "at": [0, 0, 0.45]}, {"name": "shade", "size": [0.2, 0.2, 0.15], "at": [0, 0, 0.9]}]}
    lowtop = {"parts": [{"name": "top", "size": [2, 1, 0.08], "at": [0, 0, 0.04]}] + [{"name": f"leg{i}", "size": [0.1, 0.1, 0.9], "at": [x, y, 0.45]} for i, (x, y) in enumerate(xy)]}
    n_low = BP.settle(lowtop)
    n_tall, n_short, n_floaty, n_lamp = BP.settle(tall), BP.settle(short), BP.settle(floaty), BP.settle(lamp_bad)
    after = (BP.critic(tall), BP.critic(short), BP.critic(floaty), BP.critic(lamp_bad))
    png = False
    try:
        from PIL import Image, ImageDraw
        os.makedirs(os.path.join("D:" + os.sep, "new_automation", "data", "mvp_proof_gallery"), exist_ok=True)
        im = Image.new("RGB", (860, 360), (248, 248, 250))
        d = ImageDraw.Draw(im)
        for k, (title, des, res) in enumerate((("legs taller than the top level: CAUGHT", bad, pb), ("legs end at the underside of the top: passes", good, pg))):
            ox = 30 + k * 420
            d.text((ox, 10), title, fill=(200, 40, 40) if res else (20, 130, 60))
            for p in des["parts"]:
                lo, hi = BP.part_box(p)
                x0, x1 = ox + 20 + (lo[0] + 1.2) * 150, ox + 20 + (hi[0] + 1.2) * 150
                y1, y0 = 330 - lo[2] * 170, 330 - hi[2] * 170
                d.rectangle([x0, y0, x1, y1], outline=(60, 60, 70), fill=(190, 160, 120) if p["name"] == "top" else (140, 110, 80))
            d.line([ox, 330, ox + 380, 330], fill=(120, 120, 130))
            d.text((ox, 336), "ground z=0", fill=(90, 90, 100))
        im.save(os.path.join("D:" + os.sep, "new_automation", "data", "mvp_proof_gallery", "blender_critic_AR37.png"))
        png = True
    except Exception:
        png = False
    checks = {"legs_through_the_top_are_caught_by_the_critic": any("pokes up through" in x for x in pb),
              "the_measured_build_check_finds_the_same_parts": len(meas) >= 4 and all(m.endswith("through top") for m in meas),
              "a_sound_table_passes": pg == [], "a_lamp_with_a_pole_on_its_base_passes": pl == [], "png_proof_saved": png,
              "arithmetic_repair_shortens_legs_that_pierce_the_top": bool(n_tall) and after[0] == [] and abs(tall["parts"][1]["size"][2] - 0.75) < 0.03,
              "arithmetic_repair_lengthens_short_legs_to_the_ground_and_the_top": bool(n_short) and after[1] == [] and all(abs(p["at"][2] - p["size"][2] / 2) < 0.01 for p in short["parts"][1:]),
              "a_table_top_lying_on_the_floor_is_lifted_onto_its_legs": bool(n_low) and abs(lowtop["parts"][0]["at"][2] - (0.9 + 0.04)) < 0.01 and BP.critic(lowtop) == [],
              "legs_hanging_in_mid_air_are_stood_on_the_ground": after[2] == [] and min(p["at"][2] - p["size"][2] / 2 for p in floaty["parts"]) >= -0.005,
              "a_lamp_pole_is_stretched_between_base_and_shade_and_the_base_stays_on_the_ground": bool(n_lamp) and after[3] == [] and abs(lamp_bad["parts"][0]["at"][2] - 0.015) < 1e-6}
    return verdict(checks, "bad=%d problems, measured=%d, good=%s, lamp=%s" % (len(pb), len(meas), pg, pl))
