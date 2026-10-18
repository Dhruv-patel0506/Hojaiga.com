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
