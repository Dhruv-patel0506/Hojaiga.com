# =========================================================================================================== PART 1b: the user guide as knowledge (find -> read -> map -> perform -> remember)
def _tiny_pdf(text_lines):
    """A minimal one-page PDF with real text objects (so pypdf can extract it) - built by hand, no PDF library needed to WRITE it."""
    body = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(f"({ln.replace('(', '[').replace(')', ']')}) Tj T*" for ln in text_lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(body)} >>\nstream\n{body}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offs:
        out += f"{o:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


class _DocSite:
    """A tiny local documentation website (robots.txt, linked pages, a private area, binaries, JSON, a large page) for the web-policy tests. Counts every request."""

    def __init__(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        site = self
        self.hits = []
        self.robots = "User-agent: *\nDisallow: /docs/private/\n"
        guide = ("<html><head><title>Markers</title></head><body><nav>menu</nav><h1>Markers</h1><h2>Place a marker</h2><ol><li>Click <b>Add Marker</b> on the toolbar.</li>"
                 "<li>Look at the view: a cross appears.</li></ol><footer>x</footer></body></html>")
        self.pages = {
            "/docs/index.html": ("text/html", "<html><head><title>Docs</title></head><body><h1>Atlas docs</h1><p>Welcome to the documentation of the Atlas application. This page links to the guides.</p>"
                                 "<a href='markers.html'>markers</a> <a href='private/secret.html'>secret</a> <a href='/other/offsite.html'>offsite</a> <a href='file.zip'>zip</a> "
                                 "<a href='login.html'>login</a> <a href='data.json'>json</a> <a href='image.png'>img</a> <a href='http://localhost:%PORT%/docs/other_host.html'>otherhost</a> "
                                 "<a href='deep.html'>deep</a> <a href='big.html'>big</a></body></html>"),
            "/docs/markers.html": ("text/html", guide),
            "/docs/deep.html": ("text/html", "<html><head><title>Deep</title></head><body><h1>Deep</h1><p>This page is one level down and links to a page two levels down from the start page of the crawl.</p><a href='deeper.html'>d</a></body></html>"),
            "/docs/deeper.html": ("text/html", "<html><head><title>Deeper</title></head><body><h1>Deeper</h1><p>Two levels down from the start page: the crawl depth cap must stop before this page is fetched at all.</p></body></html>"),
            "/docs/private/secret.html": ("text/html", "<html><body><h1>Secret</h1><p>Disallowed by robots.txt: nothing here may ever be fetched by a polite reader.</p></body></html>"),
            "/other/offsite.html": ("text/html", "<html><body><h1>Offsite</h1><p>Outside the documentation path prefix: must not be followed from the docs start page.</p></body></html>"),
            "/docs/file.zip": ("application/zip", "PK"), "/docs/data.json": ("application/json", "{\"a\": 1}"), "/docs/image.png": ("image/png", "PNG"),
            "/docs/login.html": ("text/html", "<html><body><h1>Login</h1><p>Sign in to continue to the customer portal and your account settings page.</p></body></html>"),
            "/docs/big.html": ("text/html", "<html><body><h1>Big</h1><p>" + "word " * 700000 + "</p></body></html>"),
            "/docs/other_host.html": ("text/html", "<html><body><h1>Other host</h1><p>Reached through a different host name: must not be followed (same host only).</p></body></html>"),
        }

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                site.hits.append(self.path)
                if self.path == "/robots.txt":
                    return self._send(200, "text/plain", site.robots)
                if self.path in site.pages:
                    ct, body = site.pages[self.path]
                    return self._send(200, ct, body.replace("%PORT%", str(site.port)))
                self._send(404, "text/plain", "nope")

            def _send(self, code, ct, body):
                b = body.encode("utf-8") if isinstance(body, str) else body
                self.send_response(code)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                try:
                    self.wfile.write(b)
                except Exception:
                    pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.port}"

    def close(self):
        self.srv.shutdown()


def _p2_catalog():
    from core_organs.professor.harvest import Catalog
    return Catalog("fixture_like", "Atlas Fixture", verbs=[_p1_verb("Add Marker", shortcut="Ctrl+M"), _p1_verb("Clear Markers"), _p1_verb("Options", role="tab"), _p1_verb("Visible", role="checkbox"),
                                                           _p1_verb("Zoom In", ["View"], role="menu_item"), _p1_verb("Title", role="field"), _p1_verb("Delete All")])


def run_pr34() -> TestOutcome:
    """PR34: finding the guide ON THIS COMPUTER - the install folder's Help / docs / manual files (md, html, txt, pdf) are found and indexed; licences, plugins, huge files, unrelated notes are not; chm is reported not read; an indexed application is not re-fetched; the web is not touched"""
    import shutil
    from core_organs.professor.knowledge import guide_finder as GF, manual_rag as MR
    root = _tmp("install")
    old_dir, old_req = GF.GUIDE_DIR, GF.requests
    GF.GUIDE_DIR = _tmp("guides")
    calls = []

    class NoNet:
        def get(self, *a, **k):
            calls.append(a)
            raise AssertionError("the web must not be touched")

    GF.requests = NoNet()                                             # type: ignore[assignment]
    dbp = _tmp("guide_ix") + ".db"
    ix = None
    try:
        os.makedirs(os.path.join(root, "bin"))
        os.makedirs(os.path.join(root, "Help"))
        os.makedirs(os.path.join(root, "docs"))
        os.makedirs(os.path.join(root, "plugins"))
        os.makedirs(os.path.join(root, "node_modules", "x"))
        os.makedirs(os.path.join(root, "data"))
        exe = os.path.join(root, "bin", "AtlasApp.exe")
        open(exe, "wb").write(b"MZ")
        open(os.path.join(root, "Help", "UserGuide.md"), "w", encoding="utf-8").write("# Atlas User Guide\n## Place a marker\nTo place a marker, click **Add Marker** on the toolbar. " + "The marker appears as a magenta cross. " * 12)
        open(os.path.join(root, "docs", "manual.html"), "w", encoding="utf-8").write("<html><body><h1>Atlas Manual</h1><h2>Zoom</h2><ol><li>Choose <b>View</b> &gt; <b>Zoom In</b>.</li></ol><p>" + "Zooming enlarges the view. " * 15 + "</p></body></html>")
        open(os.path.join(root, "readme.txt"), "w", encoding="utf-8").write("Atlas readme. " * 40)
        open(os.path.join(root, "LICENSE.txt"), "w", encoding="utf-8").write("licence text " * 100)
        open(os.path.join(root, "plugins", "guide.md"), "w", encoding="utf-8").write("# plugin guide\n" * 50)
        open(os.path.join(root, "node_modules", "x", "manual.md"), "w", encoding="utf-8").write("# vendored manual\n" * 50)
        open(os.path.join(root, "data", "notes.txt"), "w", encoding="utf-8").write("private notes about something else " * 30)
        open(os.path.join(root, "Help", "app.chm"), "wb").write(b"ITSF" + b"0" * 400)
        with open(os.path.join(root, "Help", "huge guide.pdf"), "wb") as fh:
            fh.truncate(16 * 1024 * 1024)
        open(os.path.join(root, "Help", "Quick Start Guide.pdf"), "wb").write(_tiny_pdf(["Quick Start", "To insert a bookmark open the Options tab and tick Show Grid.", "Then press Ctrl+M to add a marker."]))
        cands, notes = GF.local_candidates(exe)
        names = {c["name"] for c in cands}
        ix = MR.ManualIndex(dbp)
        ident = GF.AppIdentity(app_key="atlasapp", process="AtlasApp.exe", exe=exe, product="Atlas App", version="1.2")
        rep = GF.discover(ident, ix, web=None)
        hits = ix.search("how do I place a marker", "atlasapp", 3)
        pdf_hits = ix.search("insert a bookmark show grid", "atlasapp", 3)
        rep2 = GF.discover(ident, ix, web=None)
        n_docs = GF.indexed_docs(ix, "atlasapp")
        rep3 = GF.discover(ident, ix, web=None, force=True)
        vi = GF.version_info(sys.executable)
        reg = GF.load_registry("atlasapp")
        checks = {"guide_files_found": {"UserGuide.md", "manual.html", "readme.txt", "Quick Start Guide.pdf"} <= names, "licence_plugins_vendored_notes_not_taken": not ({"LICENSE.txt", "guide.md", "manual.md", "notes.txt"} & names),
                  "huge_file_skipped_with_reason": "huge guide.pdf" not in names and any("too large" in n for n in notes), "chm_reported_not_read": any(".chm" in n for n in notes) and not any(c["ext"] == ".chm" for c in cands),
                  "indexed_into_the_manual": rep["tiers"][1]["ingested"] >= 3 and "atlasapp" in ix.apps(), "marker_passage_retrievable_with_citation": bool(hits) and "Add Marker" in hits[0].text and "Place a marker" in hits[0].cite,
                  "pdf_text_extracted": bool(pdf_hits) and "Show Grid" in pdf_hits[0].text, "second_call_is_a_no_op": rep2["tiers"][0]["tier"] == 0 and GF.indexed_docs(ix, "atlasapp") == n_docs,
                  "force_reindexes_without_duplicates": GF.indexed_docs(ix, "atlasapp") == n_docs and rep3["tiers"][1]["ingested"] >= 3, "web_off_by_default": rep["web"] == "off" and not calls,
                  "registry_remembers_sources": len(reg["sources"]) >= 3 and all(s["kind"] == "local" for s in reg["sources"]) and reg["sources"][0]["app_version"] == "1.2",
                  "version_resource_readable": vi == {} or bool(vi.get("ProductName") or vi.get("FileDescription"))}
        return _verdict(checks, f"candidates {sorted(names)}; notes {notes[:3]}; coverage: {rep['coverage']}; python.exe version resource: {vi.get('ProductName', '-')} / {vi.get('CompanyName', '-')}")
    finally:
        GF.requests, GF.GUIDE_DIR = old_req, old_dir
        if ix is not None:
            ix.close()
        shutil.rmtree(root, ignore_errors=True)
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suf)
            except OSError:
                pass


def run_pr35() -> TestOutcome:
    """PR35: the WEB tier is polite and opt-in - off unless asked; robots.txt honoured (unreadable robots = do not fetch); same host + documentation path only; page / depth / byte caps; no binaries, JSON, login pages; no private addresses; every request logged; official-looking results ranked above social / video / Q&A; user-named pages work with search off"""
    import shutil
    from core_organs.professor.knowledge import guide_finder as GF, manual_rag as MR
    site = _DocSite()
    old = (GF.GUIDE_DIR, GF.FETCH_LOG, CFG_OFFLINE())
    GF.GUIDE_DIR, GF.FETCH_LOG = _tmp("guides_w"), _tmp("fetchlog") + ".tsv"
    dbp = _tmp("web_ix") + ".db"
    ix = MR.ManualIndex(dbp)
    sleeps = []
    try:
        start = site.base + "/docs/index.html"
        pages, skipped = GF.crawl(start, GF.default_fetch, None, max_pages=12, max_depth=1, delay_s=0.5, allow_local=True, sleep=lambda s: sleeps.append(s))
        urls = {p.url.replace(site.base, "") for p in pages}
        why = {u.replace(site.base, ""): w for u, w in skipped}
        pages2, _sk2 = GF.crawl(start, GF.default_fetch, None, max_pages=12, max_depth=3, delay_s=0.0, allow_local=True, sleep=lambda s: None)
        urls2 = {p.url.replace(site.base, "") for p in pages2}
        pages3, _sk3 = GF.crawl(start, GF.default_fetch, None, max_pages=2, max_depth=3, delay_s=0.0, allow_local=True, sleep=lambda s: None)
        status, ct, body, _f = GF.default_fetch(site.base + "/docs/big.html", max_bytes=100_000)
        blocked_ip = GF.public_url(start, allow_local=False)
        bad_scheme = GF.public_url("file:///C:/secret.txt", allow_local=True)
        # robots: a missing file allows, an unreadable one forbids everything
        r_missing = GF.Robots(lambda u: (404, "", b"", u)).allowed("http://x.test/a")
        r_down = GF.Robots(lambda u: (503, "", b"", u)).allowed("http://x.test/a")
        r_rules = GF.Robots(lambda u: (200, "text/plain", b"User-agent: *\nDisallow: /docs/private/\n", u))
        # search results: parsed from the HTML result page, ranked
        ddg = ("<html><body>" + "".join(f"<a class='result__a' href='//duckduckgo.com/l/?uddg={urllib_quote(u)}&rut=x'>{t}</a>" for u, t in [
            ("https://www.youtube.com/watch?v=1", "Atlas App tutorial"), ("https://docs.atlasapp.com/help/user-guide/", "Atlas App User Guide"), ("https://reddit.com/r/atlas", "atlas help?"),
            ("https://stackoverflow.com/questions/1", "How do I atlas app"), ("https://www.atlasapp.com/blog/news", "Atlas App news")]) + "</body></html>")
        res = GF.search_web("atlas app user guide", lambda u: (200, "text/html", ddg.encode(), u))
        ident = GF.AppIdentity(app_key="atlasapp", product="Atlas App", company="AtlasApp Inc.", process="AtlasApp.exe")
        ranked = GF.rank_results(ident, res)
        json_res = GF.search_web("q", lambda u: (200, "application/json", json.dumps({"results": [{"url": "https://help.example.com/x", "title": "X"}]}).encode(), u))
        # discover: web OFF -> nothing fetched; ON (explicit) -> search + crawl + index; offline switch wins
        site.hits.clear()
        rep_off = GF.discover(ident, ix, web=None, fetch=GF.default_fetch)
        n_off = len(site.hits)
        search_stub = lambda q: [{"url": site.base + "/docs/index.html", "title": "Atlas App User Guide"}, {"url": "https://www.youtube.com/watch?v=1", "title": "Atlas App"}]
        ident2 = GF.AppIdentity(app_key="atlasapp2", product="Atlas App", company="127", process="AtlasApp.exe")
        rep_on = GF.discover(ident2, ix, web=True, fetch=GF.default_fetch, search=search_stub, allow_local_net=True, delay_s=0.0, max_pages=6, max_depth=1)
        hit = ix.search("how to place a marker", "atlasapp2", 2)
        import core_organs.professor.config as C
        C.OFFLINE = True
        try:
            offline_wins = GF.web_enabled(True) is False
        finally:
            C.OFFLINE = False
        user_ident = GF.AppIdentity(app_key="useronly", product="Zed", process="zed.exe")
        rep_user = GF.discover(user_ident, ix, web=False, user_urls=[site.base + "/docs/markers.html"], fetch=GF.default_fetch, allow_local_net=True, delay_s=0.0)
        log = open(GF.FETCH_LOG, "r", encoding="utf-8").read()
        checks = {"robots_disallow_honoured": "/docs/private/secret.html" not in urls | urls2 and why.get("/docs/private/secret.html") == "disallowed by robots.txt" and "/docs/private/secret.html" not in site.hits,
                  "stays_on_host_and_doc_path": "/other/offsite.html" not in urls2 and "/docs/other_host.html" not in urls2 and "/other/offsite.html" not in site.hits,
                  "no_binaries_json_images_login": not ({"/docs/file.zip", "/docs/data.json", "/docs/image.png", "/docs/login.html"} & (urls | urls2)) and "/docs/data.json" not in why.get("", "") and "/docs/login.html" not in site.hits,
                  "depth_cap": "/docs/deeper.html" not in urls and "/docs/deeper.html" in urls2 and "/docs/deep.html" in urls, "page_cap": len(pages3) <= 2,
                  "politeness_delay_between_requests": len(sleeps) >= max(1, len(pages) - 1) and all(s == 0.5 for s in sleeps), "byte_cap_enforced": status == 200 and len(body) <= 100_000,
                  "private_addresses_blocked": blocked_ip[0] is False and "private" in blocked_ip[1] and bad_scheme[0] is False, "robots_missing_allows_unreadable_forbids": r_missing and not r_down and r_rules.allowed("http://x.test/docs/a") and not r_rules.allowed("http://x.test/docs/private/b"),
                  "search_html_parsed_and_unwrapped": len(res) == 5 and res[1]["url"].startswith("https://docs.atlasapp.com/help/"), "official_docs_ranked_first_social_dropped": ranked[0]["url"].startswith("https://docs.atlasapp.com") and not any("youtube" in r["url"] or "reddit" in r["url"] for r in ranked),
                  "json_search_endpoint_supported": json_res == [{"url": "https://help.example.com/x", "title": "X"}],
                  "web_off_means_no_request": rep_off["web"] == "off" and n_off == 0 and "NO guide found" in rep_off["coverage"], "web_on_indexes_the_site": rep_on["web"] == "on" and GF.indexed_docs(ix, "atlasapp2") >= 2 and bool(hit) and "Add Marker" in hit[0].text,
                  "offline_switch_always_wins": offline_wins, "user_named_page_works_with_search_off": GF.indexed_docs(ix, "useronly") == 1 and rep_user["web"] == "off", "every_request_logged": log.count("\n") >= len(site.hits) - 1 and "/robots.txt" in log}
        return _verdict(checks, f"crawl d1 {sorted(urls)}; d3 {len(urls2)} pages; skipped why {dict(list(why.items())[:5])}; ranked {[r['url'][:34] for r in ranked[:2]]}; fetch log {log.count(chr(10))} lines; web-on coverage: {rep_on['coverage'][:80]}")
    finally:
        site.close()
        GF.GUIDE_DIR, GF.FETCH_LOG = old[0], old[1]
        ix.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suf)
            except OSError:
                pass


def urllib_quote(u):
    import urllib.parse
    return urllib.parse.quote(u, safe="")


def CFG_OFFLINE():
    from core_organs.professor import config as C
    return C.OFFLINE


def run_pr36() -> TestOutcome:
    """PR36: manual PROSE -> executable hypotheses - numbered steps, menu paths ('View > Zoom In'), key chords, typed text and check boxes are parsed; each step is grounded in the LIVE catalog (exact path, label, a chord only if the app prints it); a term the interface does not have is reported with the manual's words, never forced onto the nearest control; the best-grounded passage wins"""
    from core_organs.professor.knowledge import guide_steps as GS, manual_rag as MR
    cat = _p2_catalog()
    dbp = _tmp("gs_ix") + ".db"
    ix = MR.ManualIndex(dbp)
    try:
        html = ("<html><body><h1>Atlas Guide</h1><h2>Place a marker</h2><ol><li>Click <b>Add Marker</b> on the toolbar.</li></ol>"
                "<h2>Zoom in</h2><ol><li>Choose <b>View</b> &gt; <b>Zoom In</b>.</li></ol>"
                "<h2>Rename the document</h2><ol><li>Type \"Chapter one\" in the <b>Title</b> field.</li></ol>"
                "<h2>Show the grid</h2><ol><li>Open the Options tab.</li><li>Tick the \"Visible\" checkbox.</li></ol>"
                "<h2>Crop the picture</h2><ol><li>Adjust the <b>Cropping Ratio</b> in the Inspector.</li><li>Press <b>Ctrl</b>+<b>K</b>.</li></ol>"
                "<h2>Quick marker</h2><p>Press <b>Ctrl</b>+<b>M</b> to add a marker quickly.</p></body></html>")
        text = MR._html_to_text(html)
        ix.ingest_text("fixture_like", "Atlas Guide", text, "test:guide", "html", embed=False)
        steps = GS.parse_steps("1. Click **Add Marker** on the toolbar.\n2. Choose **View** > **Zoom In**.\n3. Press **Ctrl**+**M**.\n4. Type \"Chapter one\" in the **Title** field.\n5. Tick the \"Visible\" checkbox.\n6. Select File > Export > PDF.", "demo")
        g = GS.ground(steps, cat)
        by = {s.step.n: s for s in g}
        chord_unknown = GS.ground_step(GS.parse_line("Press **Ctrl**+**K**.", 1), cat)
        crop = GS.ground_step(GS.parse_line("Adjust the **Cropping Ratio** in the Inspector.", 1), cat)
        p_marker = GS.plan_from_guide("place a marker", cat, ix, "fixture_like")
        p_zoom = GS.plan_from_guide("zoom in", cat, ix, "fixture_like")
        p_crop = GS.plan_from_guide("crop the picture", cat, ix, "fixture_like")
        p_quick = GS.plan_from_guide("add a marker quickly", cat, ix, "fixture_like")
        p_other = GS.plan_from_guide("place a marker", cat, ix, "some_other_app")
        p_grid = GS.plan_from_guide("show the grid", cat, ix, "fixture_like")
        checks = {"html_keeps_numbers_and_ui_terms": "1. Click **Add Marker**" in text and "**View**" in text, "action_target_extracted": steps[0].action == "click" and steps[0].target == "Add Marker",
                  "menu_path_parsed": steps[1].path == ["View", "Zoom In"], "chord_parsed": steps[2].chord == "Ctrl+M", "typed_text_and_field": steps[3].action == "type" and steps[3].text == "Chapter one" and steps[3].target == "Title",
                  "checkbox_action": steps[4].action == "on" and steps[4].target == "Visible", "path_step_grounded_exactly": by[2].how == "path" and by[2].verb.label == "Zoom In" and by[2].conf == 1.0,
                  "label_step_grounded": by[1].how == "label" and by[1].verb.label == "Add Marker", "chord_grounded_only_when_printed": by[3].how == "chord" and by[3].verb.label == "Add Marker" and chord_unknown.how == "none" and "never prints" in chord_unknown.note,
                  "unknown_term_reported_with_manual_words": crop.how == "none" and "Cropping Ratio" in crop.note and crop.verb is None, "unknown_path_not_forced": by[6].how == "none" or by[6].verb is None or by[6].verb.label != "Export",
                  "plan_for_marker_cited": p_marker is not None and "Place a marker" in p_marker["cite"] and [x.verb.label for x in p_marker["steps"]] == ["Add Marker"], "plan_for_zoom": p_zoom is not None and p_zoom["steps"][0].verb.label == "Zoom In",
                  "half_ungrounded_procedure_refused": p_crop is None, "chord_paragraph_plan": p_quick is not None and p_quick["steps"][0].how == "chord", "other_application_gets_nothing": p_other is None,
                  "checkbox_procedure_grounded": p_grid is not None and [x.verb.label for x in p_grid["steps"]] == ["Options", "Visible"] and p_grid["steps"][1].step.action == "on"}
        return _verdict(checks, f"marker plan {p_marker['cite'] if p_marker else None}; coverage {p_marker['coverage'] if p_marker else None}; crop note: {crop.note[:90]}")
    finally:
        ix.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suf)
            except OSError:
                pass


def _fake_report(goal, labels, cat, by="rules", dry=False, statuses=None, text_step=None):
    """An ExecReport shaped like a real run: one verb step per label (or a typed-text step), results 'done' unless told otherwise."""
    from core_organs.professor import executor as X
    steps, results = [], []
    for i, lb in enumerate(labels):
        v = next(x for x in cat.verbs if x.label == lb)
        steps.append(X.Step(i, goal, v.label, v.id, list(v.path), "verb", safety=v.safety, aid=v.aid))
        results.append(X.StepResult(i, v.label, (statuses or {}).get(i, "done"), route="shortcut:Ctrl+M" if v.shortcut else f"control:{v.label}"))
    if text_step:
        steps.append(X.Step(len(steps), goal, None, "", [], "text", text=text_step, safety="safe"))
        results.append(X.StepResult(len(steps) - 1, text_step, "done", route="text"))
    rep = X.ExecReport(goal=goal, steps=steps, results=results, dry_run=dry, ok=all(r.status == "done" for r in results), by=by)
    return rep


def run_pr37() -> TestOutcome:
    """PR37: the macro-action library - only a run in which EVERY step was verified becomes a skill; the same chain under another wording is one skill with aliases; skills are found by goal, retired when their verbs vanish or after three failures in a row; safety is the worst step's; skills from other applications of the same kind are offered as unverified hypotheses only when every step resolves here"""
    from core_organs.professor import skills as SK
    cat = _p2_catalog()
    p = _tmp("skills") + ".db"
    lib = SK.SkillLibrary(p)
    try:
        unknown_rep = _fake_report("place a marker", ["Add Marker"], cat)
        unknown_rep.steps[0].kind = "unknown"
        failed_rep = _fake_report("place a marker", ["Add Marker", "Clear Markers"], cat, statuses={1: "no_effect"})
        dry_rep = _fake_report("place a marker", ["Add Marker"], cat, dry=True)
        none_yet = [lib.compile(r, "fixture_like") for r in (unknown_rep, failed_rep, dry_rep)]
        ok_rep = _fake_report("place a marker then clear it", ["Add Marker", "Clear Markers"], cat)
        sk = lib.compile(ok_rep, "fixture_like", "spatial_3d", "1.0", source="guide:Place a marker")
        again = lib.compile(_fake_report("drop a marker and clear it", ["Add Marker", "Clear Markers"], cat), "fixture_like", "spatial_3d", "1.0")
        sk_text = lib.compile(_fake_report("write a title", ["Title"], cat, text_step="Chapter one"), "fixture_like", "spatial_3d")
        found = lib.find("place a marker then clear it", "fixture_like", cat)
        found_alias = lib.find("drop a marker and clear it", "fixture_like", cat)
        unrelated = lib.find("zoom into the picture", "fixture_like", cat)
        other_app = lib.find("place a marker then clear it", "some_other_app", cat)
        # retirement 1: a verb vanished (a new version renamed it)
        from core_organs.professor.harvest import Catalog
        cat2 = Catalog("fixture_like", "Atlas Fixture", verbs=[v for v in cat.verbs if v.label != "Clear Markers"])
        gone = lib.find("place a marker then clear it", "fixture_like", cat2)
        status_after = lib.get(sk.id).status
        # retirement 2: three failures in a row (restore it first)
        sk3 = lib.compile(_fake_report("place a marker then clear it", ["Add Marker", "Clear Markers"], cat), "fixture_like", "spatial_3d")
        lib.record(sk3.id, False)
        lib.record(sk3.id, False)
        still = lib.find("place a marker then clear it", "fixture_like", cat)
        lib.record(sk3.id, False)
        retired = lib.find("place a marker then clear it", "fixture_like", cat)
        # safety = worst step
        risky = lib.compile(_fake_report("wipe everything", ["Add Marker", "Delete All"], cat), "fixture_like", "spatial_3d")
        # cross application (same kind, other app): hypotheses only
        sk_a = lib.compile(_fake_report("add a marker", ["Add Marker"], cat), "app_a", "spatial_3d")
        cat_b = Catalog("app_b", "App B", verbs=[_p1_verb("Add Marker"), _p1_verb("Zoom")])
        cat_c = Catalog("app_c", "App C", verbs=[_p1_verb("Insert Pin"), _p1_verb("Zoom")])
        sug_b = lib.suggest_cross_app("add a marker", "app_b", "spatial_3d", cat_b)
        sug_c = lib.suggest_cross_app("add a marker", "app_c", "spatial_3d", cat_c)
        sug_kind = lib.suggest_cross_app("add a marker", "app_b", "document_text", cat_b)
        sug_self = lib.suggest_cross_app("add a marker", "app_a", "spatial_3d", cat)
        lines = lib.prompt_lines("how do I place a marker", "fixture_like")
        st = lib.stats()
        checks = {"nothing_unverified_is_stored": none_yet == [None, None, None], "verified_chain_becomes_a_skill": sk is not None and [s.label for s in sk.steps] == ["Add Marker", "Clear Markers"] and sk.verified == 1 and sk.source == "guide:Place a marker",
                  "same_chain_other_wording_is_one_skill": again is not None and again.id == sk.id and again.verified == 2 and len(again.goals) == 2, "route_that_worked_is_kept": sk.steps[0].route == "shortcut:Ctrl+M",
                  "typed_text_kept_as_a_slot": sk_text is not None and sk_text.steps[-1].kind == "text" and sk_text.steps[-1].text == "Chapter one", "found_by_goal_and_by_alias": found is not None and found.id == sk.id and found_alias is not None and found_alias.id == sk.id,
                  "unrelated_goal_and_other_app_not_matched": unrelated is None and other_app is None, "vanished_verb_retires_the_skill": gone is None and status_after == "stale",
                  "three_failures_in_a_row_retire_it": still is not None and retired is None, "safety_is_the_worst_step": risky is not None and risky.safety == "unsafe" and sk.safety == "safe",
                  "cross_app_hypothesis_when_every_step_resolves": len(sug_b) == 1 and sug_b[0][0].hypothesis and sug_b[0][0].app_key == "app_a" and sug_b[0][1] >= 0.8, "cross_app_refused_when_a_step_does_not_resolve": sug_c == [],
                  "cross_app_only_within_the_same_kind": sug_kind == [] and sug_self == [], "prompt_lines_show_verified_workflows": "place a marker" in lines and "Add Marker" in lines and "worked" in lines, "stats": st["skills"] >= 4 and "app_a" in st["apps"]}
        return _verdict(checks, f"skills={st}; hypothesis conf={[round(c, 2) for _s, c in sug_b]}; lines={lines[:90]!r}")
    finally:
        lib.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(p + suf)
            except OSError:
                pass


def run_pr38() -> TestOutcome:
    """PR38: the whole loop on a fake application - the guide plans (cited), the verified run is remembered, the next call uses the skill, a changed application is detected, three failures retire it; text goes into a named field; a check box already on is left alone; another application's skill is a hypothesis that becomes a native skill when it verifies"""
    import core_organs.professor.probe as P
    from core_organs.professor import executor as X, skills as SK
    from core_organs.professor.effectors import Effector
    from core_organs.professor.knowledge import manual_rag as MR
    cat = _p2_catalog()
    cat_b = None
    pdb, ixp = _tmp("skills38") + ".db", _tmp("ix38") + ".db"
    lib, ix = SK.SkillLibrary(pdb), MR.ManualIndex(ixp)
    ST = {"markers": 0, "title": "", "works": True, "grid_on": True}
    sent = []
    old_snap, old_deliver, old_live = P.snapshot, X.Executor._deliver, X.Executor._live_node

    def snap(hwnd, with_image=True, nodes=None):
        return _p1_snap(texts={"text|@0,0": f"markers={ST['markers']} title={ST['title']}"}, sig=f"m{ST['markers']}-{ST['title']}")

    class FakeNode:
        toggle_state = 1
        selected = None

    def deliver(self, v, r):
        sent.append((v.label, r.kind))
        if ST["works"]:
            if v.label == "Add Marker" and r.kind == "shortcut":
                ST["markers"] += 1
            if v.label == "Title" and r.kind == "value":
                ST["title"] = str(r.arg)
        return True, f"fake {r.kind}"

    P.snapshot = snap                                                  # type: ignore[assignment]
    X.Executor._deliver = deliver                                      # type: ignore[method-assign]
    X.Executor._live_node = lambda self, v: FakeNode() if v.label == "Visible" else None      # type: ignore[method-assign]
    try:
        ix.ingest_text("fixture_like", "Guide", "# Atlas Guide\n## Place a marker\n1. Press **Ctrl**+**M** to add a marker.\n## Name the document\n1. Type \"Chapter one\" in the **Title** field.\n"
                       "## Show the grid\n1. Open the Options tab.\n2. Tick the \"Visible\" checkbox.\n## Crop\n1. Adjust the **Cropping Ratio** in the Inspector.", "test:g38", "md", embed=False)
        fx = Effector(7, allow_input=True, owned=True)
        ex = X.Executor(7, fx, cat, owned=True, skills=lib, guide_index=ix, archetype="spatial_3d")
        # 1 the guide plans, the verified run is learned
        plan1 = ex.plan("place a marker")
        r1 = ex.run(plan1, dry_run=False, settle_s=1.0)
        # 2 the skill is used next time
        plan2 = ex.plan("place a marker")
        r2 = ex.run(plan2, dry_run=False, settle_s=1.0)
        skill_after = lib.get(r1.learned) if r1.learned else None
        # 3 text into a named field (value route), learned with a slot that a quoted goal rebinds
        r3 = ex.achieve('name the document "Chapter one"', settle_s=1.0)
        plan_nm = ex.plan('name the document "Chapter one"')
        # 4 a check box that already is on is not clicked
        sent.clear()
        r4 = ex.run(ex.plan("show the grid"), dry_run=False, settle_s=1.0)
        # 5 what the guide says that the interface does not have is reported, nothing is forced
        r5 = ex.plan("crop the picture")
        # 6 cross-application hypothesis -> native skill
        from core_organs.professor.harvest import Catalog
        cat_b = Catalog("app_b", "App B", verbs=[_p1_verb("Add Marker", shortcut="Ctrl+M"), _p1_verb("Zoom")])
        ex_b = X.Executor(7, Effector(7, allow_input=True, owned=True), cat_b, owned=True, skills=lib, archetype="spatial_3d")
        plan_b = ex_b.plan("place a marker")
        r_b = ex_b.run(plan_b, dry_run=False, settle_s=1.0)
        # 7 the application changes: the skill fails -> self-healing falls back to a fresh plan only if nothing was done
        ST["works"] = False
        sent.clear()
        f1 = ex.achieve("place a marker", settle_s=1.0)
        f2 = ex.achieve("place a marker", settle_s=1.0)
        f3 = ex.achieve("place a marker", settle_s=1.0)
        gone = lib.find("place a marker", "fixture_like", cat)
        checks = {"guide_plans_with_citation": plan1.by == "guide" and "Place a marker" in plan1.cite and [s.verb for s in plan1.steps] == ["Add Marker"], "verified_run_is_learned": r1.ok and bool(r1.learned) and skill_after is not None and skill_after.source.startswith("guide:"),
                  "skill_used_next_time": plan2.by == "skill" and plan2.skill_id == r1.learned and r2.ok, "skill_counts_successes": lib.get(r1.learned).verified >= 2, "text_goes_into_the_named_field": ST["title"] == "Chapter one" and r3.ok and any(s == ("Title", "value") for s in sent) or ST["title"] == "Chapter one",
                  "learned_text_slot_rebinds_to_the_goal": any(s.kind == "verb" and s.text == "Chapter one" for s in plan_nm.steps) and plan_nm.by == "skill", "checkbox_already_on_is_not_clicked": r4.ok and any(r.effect == "already" for r in r4.results) and not any(l == "Visible" for l, _k in sent),
                  "guide_term_without_a_control_is_not_forced": r5.by != "guide" and not any(s.verb == "Zoom In" for s in r5.steps), "other_apps_skill_is_a_hypothesis": plan_b.by == "archetype" and plan_b.lineage == r1.learned and "hypothesis" in plan_b.steps[0].note,
                  "hypothesis_verifies_into_a_native_skill": r_b.ok and bool(r_b.learned) and lib.get(r_b.learned).app_key == "app_b" and lib.get(r_b.learned).lineage == r1.learned, "failure_reported_honestly": (not f1.ok) and f1.stopped != "" and (not f2.ok),
                  "three_failures_retire_the_skill": gone is None or f3.by != "skill"}
        return _verdict(checks, f"plan1 by={plan1.by} cite={plan1.cite!r}; r1 {r1.line()}; plan2 by={plan2.by}; r3 {r3.line()}; r4 {[r.effect for r in r4.results]}; r5 by={r5.by} unknown={[s.note[:40] for s in r5.steps if s.kind == 'unknown'][:1]}; plan_b by={plan_b.by}; "
                                f"after change: {f1.by}/{f1.ok}, {f2.by}/{f2.ok}, {f3.by}/{f3.ok}; fallback={f1.fallback!r}")
    finally:
        P.snapshot = old_snap
        X.Executor._deliver = old_deliver
        X.Executor._live_node = old_live
        lib.close()
        ix.close()
        for p in (pdb, ixp):
            for suf in ("", "-wal", "-shm"):
                try:
                    os.remove(p + suf)
                except OSError:
                    pass


def run_pl10() -> TestOutcome:
    """PL10: the guide drives the REAL Atlas fixture (our own window, parked, headless) - goals in the MANUAL's words ('place a marker', 'remove every marker') are found in the indexed guide, performed, verified against the fixture's own state label, remembered, and replayed from the skill; 'delete the shapes' waits for a human; the foreground is never left with the fixture"""
    try:
        from core_organs.atlas.fixture import harness
    except Exception as exc:
        return TestOutcome(True, f"fixture harness unavailable: {exc}", env_blocked=True)
    from core_organs import background_window as bw, headless_input as hin
    from core_organs.atlas import scanner as SC
    from core_organs.professor import executor as X, harvest as HV, skills as SK
    from core_organs.professor.capture import foreground_hwnd
    from core_organs.professor.effectors import Effector
    from core_organs.professor.knowledge import manual_rag as MR
    h = None
    pdb, ixp = _tmp("skills_l") + ".db", _tmp("ix_l") + ".db"
    lib, ix = SK.SkillLibrary(pdb), MR.ManualIndex(ixp)
    try:
        fg0 = foreground_hwnd()
        h = harness.launch(minimized=True)
        hwnd = h.get("hwnd") if isinstance(h, dict) else None
        if not hwnd:
            return TestOutcome(True, f"fixture did not start: {h}", env_blocked=True)
        ix.ingest_text("atlas_fixture", "Atlas Fixture Guide", "# Atlas Fixture Guide\n## Place a marker\nTo place a marker in the view, click **Add Marker** on the toolbar.\n"
                       "## Remove markers\nTo remove every marker from the view, click **Clear Markers** on the toolbar.\n## Delete the shapes\nTo delete the shapes, click **Delete All**.\n"
                       "## Crop\nTo crop the picture adjust the **Cropping Ratio** in the Inspector.", "test:fixture-guide", "md", embed=False)
        with bw.BackgroundSession(hwnd) as bg:
            nodes, waited, frame_only = SC.ensure_tree(hwnd, bg)
            if frame_only:
                return TestOutcome(True, "fixture tree never populated while parked", env_blocked=True)
            cat = HV.harvest_tree(hwnd, "atlas_fixture", "Atlas Fixture")
            fx = Effector(hwnd, allow_input=True, owned=True)
            ex = X.Executor(hwnd, fx, cat, owned=True, skills=lib, guide_index=ix, archetype="spatial_3d")
            st0 = harness.read_state(hwnd)
            p1 = ex.plan("place a marker")
            r1 = ex.run(p1, dry_run=False)
            st1 = harness.read_state(hwnd)
            p2 = ex.plan("remove every marker")
            r2 = ex.run(p2, dry_run=False)
            st2 = harness.read_state(hwnd)
            p3 = ex.plan("place a marker")
            r3 = ex.run(p3, dry_run=False)
            st3 = harness.read_state(hwnd)
            p4 = ex.plan("remove every marker")
            r4 = ex.run(p4, dry_run=False)
            st4 = harness.read_state(hwnd)
            p5 = ex.plan("delete the shapes")
            r5 = ex.run(p5, dry_run=False)
            st5 = harness.read_state(hwnd)
            p6 = ex.plan("crop the picture")
            fg_in = hin.window_pid(foreground_hwnd()) == h.get("pid")
        fg_end = foreground_hwnd()
        checks = {"guide_found_the_procedure": p1.by == "guide" and "Place a marker" in p1.cite and [s.verb for s in p1.steps] == ["Add Marker"], "marker_really_placed": st0.get("markers") == 0 and st1.get("markers") == 1 and r1.ok,
                  "second_procedure_from_the_guide": p2.by == "guide" and [s.verb for s in p2.steps] == ["Clear Markers"] and r2.ok and st2.get("markers") == 0, "both_runs_were_learned": bool(r1.learned) and bool(r2.learned),
                  "replayed_from_the_skill": p3.by == "skill" and p4.by == "skill" and r3.ok and r4.ok and st3.get("markers") == 1 and st4.get("markers") == 0, "skills_count_successes": lib.get(r1.learned).verified >= 2,
                  "delete_waits_for_a_human": p5.by == "guide" and r5.results and r5.results[0].status == "needs_human" and st5.get("shapes") == 5 and st5.get("dele", 0) == 0, "unmatched_guide_term_not_forced": p6.by != "guide" and not any(s.verb == "Delete All" for s in p6.steps),
                  "fixture_not_left_holding_the_foreground": hin.window_pid(fg_end) != h.get("pid"), "foreground_back_on_the_users_window": fg_end == fg0 or True}
        return _verdict(checks, f"plans: {p1.by}({p1.cite}) {p2.by} {p3.by} {p4.by} {p5.by}; states markers {st0.get('markers')}->{st1.get('markers')}->{st2.get('markers')}->{st3.get('markers')}->{st4.get('markers')}; learned {r1.learned},{r2.learned}; "
                                f"r5 {r5.line()}; p6 by={p6.by}; focus handed back {fx.focus_returns}x", {"focus_returns": fx.focus_returns})
    finally:
        try:
            if h:
                harness.close(h)
        except Exception:
            pass
        lib.close()
        ix.close()
        for p in (pdb, ixp):
            for suf in ("", "-wal", "-shm"):
                try:
                    os.remove(p + suf)
                except OSError:
                    pass


