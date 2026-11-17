"""
harvest.web_curriculum -- scan EVERY web app on a ladder, easy to complex, and let each one make the system smarter.

    D:\\new_automation\\hojaiga_env\\Scripts\\python.exe -X utf8 -m core_organs.harvest.web_curriculum run --hours 10
    ... web_curriculum list                      the ladder, in the order it will be walked
    ... web_curriculum run --only jobs,social    only these categories
    ... web_curriculum run --tier 1              only the easiest rung
    ... web_curriculum report                    the growth numbers so far
    ... web_curriculum rollback <run-stamp>      forget what one run wrote into the pool (lexicon commands, hotkey rows)
    create the file  data/web_curriculum/STOP  to end a run after the current site.

For each site (rung 1 of every category first, then rung 2 ...):  deep, headless exploration (try_app --headless: clicks through menus, dialogs, pages, child windows; reverse-engineers the stack,
traffic, sign-in, sitemap, shortcut sheet) in its OWN process with a time limit  ->  learn_site files the result in the pool  ->  numbers are logged.

THE LEARNING CURVE is measured, not claimed. Before a site is learned from, the system PREDICTS two things about it from what it already knows:
   * its category        (web_kind: word profiles of the sites scanned before; compared with the label the ladder gives)
   * its sections        (the section names other sites of that category shared; compared with what the scan then found)
Both predictions are scored when the scan finishes, and the running accuracy is written to growth.jsonl / SUMMARY.md. If the system is getting smarter these numbers rise as the pool fills.
Sites that refuse an automated browser (HTTP 4xx) are recorded as refused and NOT worked around. Nothing is typed, submitted or logged into anywhere.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core_organs.harvest import web_kind as WK
from core_organs.harvest import web_learn as WL

REPORTS = os.environ.get("HOJAIGA_REPORTS", os.path.join("D:" + os.sep, "new_automation", "reports"))
OUT = os.path.join(REPORTS, "web_curriculum")
STATE = os.path.join(WK.FOLDER, "state.json")
STOP = os.path.join(WK.FOLDER, "STOP")
PROGRESS = os.path.join(OUT, "progress.jsonl")
LEDGER = os.path.join(OUT, "rag_writes.jsonl")
GROWTH = os.path.join(OUT, "growth.jsonl")

# category -> [(name, url, tier)]   tier 1 = a simple page or app ... 4 = a large product site, 5 = a SPECIALIST app (walked last: easy and common first, hard and niche at the end). The category is the curriculum author's decision (it is what the system learns to recognise).
LADDERS: Dict[str, List[Tuple[str, str, int]]] = {
    "search_reference": [("DuckDuckGo", "duckduckgo.com", 1), ("Wikipedia", "en.wikipedia.org", 1), ("Internet Archive", "archive.org", 2), ("Wolfram Alpha", "wolframalpha.com", 3)],
    "dev_docs": [("MDN Web Docs", "developer.mozilla.org", 1), ("W3Schools", "w3schools.com", 1), ("Python Docs", "docs.python.org", 1), ("regex101", "regex101.com", 2), ("DevDocs", "devdocs.io", 2)],
    "dev_platform": [("PyPI", "pypi.org", 1), ("GitHub", "github.com", 2), ("GitLab", "gitlab.com", 2), ("npm", "npmjs.com", 2), ("CodePen", "codepen.io", 2), ("Hugging Face", "huggingface.co", 3),
                     ("Kaggle", "kaggle.com", 3), ("Replit", "replit.com", 3), ("Vercel", "vercel.com", 3), ("Netlify", "netlify.com", 3)],
    "productivity_pm": [("Todoist", "todoist.com", 1), ("Trello", "trello.com", 2), ("Asana", "asana.com", 2), ("Notion", "notion.so", 3), ("Airtable", "airtable.com", 3), ("monday.com", "monday.com", 3),
                        ("ClickUp", "clickup.com", 3)],
    "design_tools": [("Excalidraw", "excalidraw.com", 1), ("Photopea", "photopea.com", 2), ("diagrams.net", "app.diagrams.net", 2), ("Canva", "canva.com", 3), ("Figma", "figma.com", 3), ("Miro", "miro.com", 3)],
    "video_audio": [("TED", "ted.com", 1), ("Vimeo", "vimeo.com", 2), ("Dailymotion", "dailymotion.com", 2), ("SoundCloud", "soundcloud.com", 2), ("Bandcamp", "bandcamp.com", 2),
                    ("YouTube", "youtube.com", 3), ("Twitch", "twitch.tv", 3)],
    "social": [("Hacker News", "news.ycombinator.com", 1), ("Lobsters", "lobste.rs", 1), ("Mastodon", "mastodon.social", 2), ("Reddit", "reddit.com", 2), ("Medium", "medium.com", 2),
               ("Pinterest", "pinterest.com", 3), ("Quora", "quora.com", 3)],
    "jobs": [("Naukri", "naukri.com", 2), ("Handshake", "joinhandshake.com", 2), ("Indeed", "indeed.com", 3), ("Wellfound", "wellfound.com", 3), ("Glassdoor", "glassdoor.com", 3)],
    "ecommerce": [("eBay", "ebay.com", 2), ("Flipkart", "flipkart.com", 3), ("Etsy", "etsy.com", 3), ("Amazon India", "amazon.in", 3), ("Shopify", "shopify.com", 3)],
    "news_media": [("NPR", "npr.org", 1), ("BBC", "bbc.com", 1), ("The Guardian", "theguardian.com", 2), ("The Hindu", "thehindu.com", 2), ("Al Jazeera", "aljazeera.com", 2)],
    "learning": [("Khan Academy", "khanacademy.org", 1), ("Coursera", "coursera.org", 2), ("edX", "edx.org", 2), ("Udemy", "udemy.com", 3), ("Duolingo", "duolingo.com", 3)],
    "maps_travel": [("OpenStreetMap", "openstreetmap.org", 1), ("Booking.com", "booking.com", 3), ("Airbnb", "airbnb.com", 3), ("Tripadvisor", "tripadvisor.com", 3)],
    "utilities": [("time.is", "time.is", 1), ("calculator.net", "calculator.net", 1), ("Speedtest", "speedtest.net", 1), ("Desmos", "desmos.com/scientific", 1), ("jwt.io", "jwt.io", 1),
                  ("TinyPNG", "tinypng.com", 1), ("iLovePDF", "ilovepdf.com", 2), ("Smallpdf", "smallpdf.com", 2), ("weather.com", "weather.com", 2), ("GeoGebra", "geogebra.org", 3)],
    "communication": [("Telegram", "telegram.org", 1), ("Proton", "proton.me", 2), ("Slack", "slack.com", 3), ("Discord", "discord.com", 3), ("Zoom", "zoom.us", 3)],
    "games": [("Lichess", "lichess.org", 2), ("Chess.com", "chess.com", 3)],
    "ai_tools": [("Perplexity", "perplexity.ai", 3), ("Hugging Face Spaces", "huggingface.co/spaces", 3)],
    # rung 5: SPECIALIST apps (a narrow audience, a narrow job): walked last, after everything common and general
    "science_research": [("arXiv", "arxiv.org", 5), ("PubMed", "pubmed.ncbi.nlm.nih.gov", 5), ("PhET Simulations", "phet.colorado.edu", 5), ("iNaturalist", "inaturalist.org", 5),
                         ("Protein Data Bank", "rcsb.org", 5), ("UniProt", "uniprot.org", 5), ("UCSC Genome Browser", "genome.ucsc.edu", 5), ("Ensembl", "ensembl.org", 5)],
    "geo_data": [("Windy", "windy.com", 5), ("Flightradar24", "flightradar24.com", 5), ("geojson.io", "geojson.io", 5), ("Stellarium Web", "stellarium-web.org", 5)],
    "creative_niche": [("Flat (music notation)", "flat.io", 5), ("BandLab", "bandlab.com", 5), ("Sketchfab", "sketchfab.com", 5), ("Falstad Circuit Simulator", "falstad.com/circuit", 5),
                       ("Teachable Machine", "teachablemachine.withgoogle.com", 5), ("Mermaid Live", "mermaid.live", 5), ("dbdiagram.io", "dbdiagram.io", 5)],
    "dev_niche": [("Compiler Explorer", "godbolt.org", 5), ("JSFiddle", "jsfiddle.net", 5), ("Observable", "observablehq.com", 5), ("OnlineGDB", "onlinegdb.com", 5), ("Postman", "postman.com", 5),
                  ("Try Jupyter", "jupyter.org/try-jupyter", 5)],
    "utility_niche": [("Monkeytype", "monkeytype.com", 5), ("DeepL Translator", "deepl.com/translator", 5), ("Color Hunt", "colorhunt.co", 5), ("Zotero", "zotero.org", 5)],
    "enterprise_cloud": [("Atlassian", "atlassian.com", 4), ("HubSpot", "hubspot.com", 4), ("Zendesk", "zendesk.com", 4), ("Salesforce", "salesforce.com", 4), ("Google Cloud", "cloud.google.com", 4),
                         ("AWS", "aws.amazon.com", 4), ("Azure", "azure.microsoft.com", 4)],
}
NO_TRANSCRIBE = False
MINIMIZED = False                    # a real browser window kept minimized, no overlay: the same exploration, nothing on screen, not the headless build
VISIBLE = True                       # the run happens ON SCREEN (a real browser window, the Hojaiga virtual cursor pointing); --headless makes it silent for unattended runs
LIMITS = {1: (200, 5, 10, 600), 2: (300, 6, 15, 900), 3: (400, 6, 20, 1200), 4: (500, 6, 25, 1500), 5: (400, 6, 20, 1200)}      # BUTTON clicks, depth, pages, seconds (links get a quarter of the clicks)      # clicks, depth, pages, seconds per site


# ---- Oct-27: more categories, easy to complex (rung 1 = a page of links, 2 = an app with menus, 3 = a heavy single-page app, 4 = enterprise, 5 = niche tools). Public pages only; the explorer never
# submits forms, never buys, never signs in, and skips risky buttons (DANGER); a wall (login / bot check) is recorded as such.
MORE: Dict[str, List[Tuple[str, str, int]]] = {
    "finance_public": [("Investopedia", "investopedia.com", 1), ("XE Currency", "xe.com", 1), ("Yahoo Finance", "finance.yahoo.com", 2), ("TradingView", "tradingview.com", 3), ("CoinMarketCap", "coinmarketcap.com", 2),
                       ("NerdWallet", "nerdwallet.com", 2), ("Moneycontrol", "moneycontrol.com", 2)],
    "health_info": [("Mayo Clinic", "mayoclinic.org", 1), ("WebMD", "webmd.com", 2), ("MedlinePlus", "medlineplus.gov", 1), ("NHS", "nhs.uk", 1), ("Healthline", "healthline.com", 2)],
    "food_home": [("AllRecipes", "allrecipes.com", 1), ("Serious Eats", "seriouseats.com", 1), ("BBC Good Food", "bbcgoodfood.com", 2), ("Epicurious", "epicurious.com", 2), ("Houzz", "houzz.com", 3)],
    "sports": [("ESPN", "espn.com", 2), ("Cricbuzz", "cricbuzz.com", 2), ("BBC Sport", "bbc.com/sport", 1), ("NBA", "nba.com", 3), ("FIFA", "fifa.com", 3)],
    "weather_time": [("timeanddate", "timeanddate.com", 1), ("Weather.gov", "weather.gov", 1), ("AccuWeather", "accuweather.com", 2), ("Time.is", "time.is", 1)],
    "government_public": [("USA.gov", "usa.gov", 1), ("data.gov", "data.gov", 1), ("GOV.UK", "gov.uk", 1), ("India.gov.in", "india.gov.in", 1), ("Library of Congress", "loc.gov", 2), ("NASA", "nasa.gov", 2)],
    "real_estate_travel": [("Zillow", "zillow.com", 3), ("Rightmove", "rightmove.co.uk", 2), ("TripAdvisor", "tripadvisor.com", 3), ("Kayak", "kayak.com", 3), ("Skyscanner", "skyscanner.net", 3)],
    "code_playgrounds": [("StackBlitz", "stackblitz.com", 3), ("Glitch", "glitch.com", 3), ("JupyterLite", "jupyter.org/try-jupyter", 3), ("Python Tutor", "pythontutor.com", 2), ("Programiz Online", "programiz.com/python-programming/online-compiler", 2),
                         ("OneCompiler", "onecompiler.com", 2), ("Mermaid Live", "mermaid.live", 2), ("TypeScript Playground", "typescriptlang.org/play", 3), ("Rust Playground", "play.rust-lang.org", 3)],
    "package_registries": [("crates.io", "crates.io", 1), ("Docker Hub", "hub.docker.com", 2), ("RubyGems", "rubygems.org", 1), ("Maven Central", "central.sonatype.com", 2), ("Packagist", "packagist.org", 1),
                           ("SourceForge", "sourceforge.net", 2), ("Homebrew", "brew.sh", 1)],
    "docs_enterprise": [("Kubernetes Docs", "kubernetes.io/docs", 2), ("Docker Docs", "docs.docker.com", 2), ("Microsoft Learn", "learn.microsoft.com", 2), ("Google Cloud Docs", "cloud.google.com/docs", 3), ("Stripe Docs", "docs.stripe.com", 3),
                        ("React Docs", "react.dev", 2), ("Django Docs", "docs.djangoproject.com", 2), ("Rust Book", "doc.rust-lang.org/book", 1), ("PostgreSQL Docs", "postgresql.org/docs", 1)],
    "saas_business": [("HubSpot", "hubspot.com", 3), ("Salesforce", "salesforce.com", 4), ("Zendesk", "zendesk.com", 3), ("Slack", "slack.com", 3), ("Zoom", "zoom.us", 3), ("Typeform", "typeform.com", 3),
                      ("Calendly", "calendly.com", 3), ("Mailchimp", "mailchimp.com", 3), ("DocuSign", "docusign.com", 3), ("QuickBooks", "quickbooks.intuit.com", 4)],
    "no_code_automation": [("Zapier", "zapier.com", 3), ("n8n", "n8n.io", 3), ("IFTTT", "ifttt.com", 2), ("Bubble", "bubble.io", 3), ("Webflow", "webflow.com", 3), ("Wix", "wix.com", 3), ("Squarespace", "squarespace.com", 3)],
    "creative_tools": [("Pixlr", "pixlr.com", 3), ("Photopea Learn", "photopea.com/learn", 2), ("Remove.bg", "remove.bg", 2), ("Clipchamp", "clipchamp.com", 3), ("Audiotool", "audiotool.com", 5), ("Soundtrap", "soundtrap.com", 4),
                       ("Chrome Music Lab", "musiclab.chromeexperiments.com", 2), ("Tinkercad", "tinkercad.com", 4), ("Sketchfab", "sketchfab.com", 3), ("Three.js Editor", "threejs.org/editor", 5), ("Scratch", "scratch.mit.edu", 3)],
    "converters_pdf": [("Smallpdf", "smallpdf.com", 2), ("CloudConvert", "cloudconvert.com", 2), ("PDF24", "tools.pdf24.org", 2), ("Convertio", "convertio.co", 2), ("Online-Convert", "online-convert.com", 2), ("Squoosh", "squoosh.app", 3),
                       ("Ezgif", "ezgif.com", 2)],
    "math_science_tools": [("GeoGebra", "geogebra.org/graphing", 4), ("Symbolab", "symbolab.com", 3), ("Desmos Graphing", "desmos.com/calculator", 3), ("WolframAlpha Examples", "wolframalpha.com/examples", 2), ("Wokwi", "wokwi.com", 5),
                           ("EasyEDA", "easyeda.com", 5), ("CircuitLab", "circuitlab.com", 5), ("Jupyter nbviewer", "nbviewer.org", 2), ("Our World in Data", "ourworldindata.org", 2), ("Datawrapper", "datawrapper.de", 3)],
    "learning_more": [("Duolingo", "duolingo.com", 3), ("Code.org", "code.org", 2), ("freeCodeCamp", "freecodecamp.org", 2), ("Codecademy", "codecademy.com", 3), ("Udemy", "udemy.com", 3), ("MIT OpenCourseWare", "ocw.mit.edu", 1),
                      ("LeetCode", "leetcode.com", 3), ("HackerRank", "hackerrank.com", 3), ("Brilliant", "brilliant.org", 3)],
    "social_more": [("Stack Overflow", "stackoverflow.com", 2), ("Goodreads", "goodreads.com", 2), ("Letterboxd", "letterboxd.com", 2), ("IMDb", "imdb.com", 2), ("Product Hunt", "producthunt.com", 2), ("Dev.to", "dev.to", 1),
                    ("Substack", "substack.com", 2), ("Wikipedia Edit Help", "en.wikipedia.org/wiki/Help:Contents", 1)],
    "web_office": [("Google Docs", "docs.google.com/document/about", 2), ("Google Sheets", "docs.google.com/spreadsheets/about", 2), ("Google Slides", "docs.google.com/presentation/about", 2),
                   ("Google Forms", "docs.google.com/forms/about", 2), ("Google Drive", "workspace.google.com/products/drive", 2), ("Google Calendar", "workspace.google.com/products/calendar", 2),
                   ("Gmail", "workspace.google.com/products/gmail", 2), ("Google Meet", "workspace.google.com/products/meet", 2), ("Google Keep", "workspace.google.com/products/keep", 2),
                   ("Google Docs shortcuts (help)", "support.google.com/docs/answer/179738", 1), ("Microsoft 365", "microsoft.com/microsoft-365", 2), ("Office on the web", "office.com", 2),
                   ("Canva", "canva.com", 3), ("Zoho Writer", "zoho.com/writer", 2), ("Airtable", "airtable.com", 3), ("Smartsheet", "smartsheet.com", 3), ("Evernote", "evernote.com", 2), ("Miro", "miro.com", 3),
                   ("Lucidchart", "lucid.co/product/lucidchart", 3), ("ClickUp", "clickup.com", 3)],
    "marketplaces_more": [("Craigslist", "craigslist.org", 1), ("OLX India", "olx.in", 2), ("Walmart", "walmart.com", 3), ("Target", "target.com", 3), ("IKEA", "ikea.com", 2), ("Best Buy", "bestbuy.com", 3)],
}
for _cat, _sites in MORE.items():
    _have = {u.lower().rstrip("/") for _s in LADDERS.values() for _, u, _ in _s}                         # a site belongs to ONE category: the first that lists it keeps it
    _new = []
    for _x in _sites:
        if _x[1].lower().rstrip("/") not in _have:
            _have.add(_x[1].lower().rstrip("/"))
            _new.append(_x)
    LADDERS.setdefault(_cat, []).extend(_new)


def rows(only: Optional[Sequence[str]] = None, tier: Optional[int] = None) -> List[Dict[str, Any]]:
    out = []
    for cat, sites in LADDERS.items():
        if only and cat not in only:
            continue
        for i, (name, url, t) in enumerate(sites):
            if tier and t != tier:
                continue
            out.append({"name": name, "url": url, "category": cat, "tier": t, "rank": i})
    return out


def ordered(items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rung first (every category's easiest site before any category's second), categories taking turns inside a rung."""
    by_tier: Dict[int, Dict[str, List[Dict[str, Any]]]] = {}
    for r in items:
        by_tier.setdefault(r["tier"], {}).setdefault(r["category"], []).append(r)
    out: List[Dict[str, Any]] = []
    for t in sorted(by_tier):
        cats = by_tier[t]
        while any(cats.values()):
            for c in sorted(cats):
                if cats[c]:
                    out.append(cats[c].pop(0))
    return out


def load_state() -> Dict[str, Any]:
    with contextlib.suppress(Exception):
        return json.load(open(STATE, encoding="utf-8"))
    return {"sites": {}}


@contextlib.contextmanager
def _state_lock():
    """Two crawlers (one on screen, one silent) share state.json: a short cross-process lock around read-modify-write."""
    import msvcrt
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    f = open(STATE + ".lock", "a+b")
    try:
        for _ in range(200):
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(0.1)
        yield
    finally:
        with contextlib.suppress(Exception):
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        f.close()


def save_site(url: str, ent: Dict[str, Any]) -> Dict[str, Any]:
    """Add ONE site to the shared state without overwriting what the other crawler wrote meanwhile; returns the merged state."""
    with _state_lock():
        st = load_state()
        st.setdefault("sites", {})[url] = ent
        save_state(st)
    return st


def in_shard(url: str, shard: str) -> bool:
    """'i/n': this crawler takes the sites whose address hashes to i of n (stable, so a restart keeps the same split)."""
    if not shard:
        return True
    import zlib
    i, n = (int(x) for x in shard.split("/"))
    return zlib.crc32(url.encode()) % n == i


def save_state(st: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, STATE)


def subprocess_runner(site: Dict[str, Any], log: Callable[[str], None]) -> Dict[str, Any]:
    """Scan one site in its own process (a hang or crash costs one site, not the run). Returns {'status', 'report', 'seconds', 'log'}."""
    clicks, depth, pages, secs = LIMITS.get(site["tier"], LIMITS[3])
    os.makedirs(OUT, exist_ok=True)
    logf = os.path.join(OUT, "site_logs", re.sub(r"[^a-z0-9.]+", "_", site["url"].lower()) + ".log")
    os.makedirs(os.path.dirname(logf), exist_ok=True)
    cmd = [sys.executable, "-X", "utf8", "-m", "core_organs.try_app", site["url"], "--show", "--clicks", str(clicks), "--depth", str(depth), "--pages", str(pages),
           "--explore-seconds", str(secs)]
    cmd += (["--minimized", "--pace", "0.1"] if MINIMIZED else ["--pace", "0.3", "--hold", "1"]) if VISIBLE else ["--headless", "--pace", "0.1"]
    if NO_TRANSCRIBE:
        cmd.append("--no-transcribe")
    env = dict(os.environ, PYTHONPATH=r"D:\new_automation;D:\new_automation\All codes", PYTHONUNBUFFERED="1")
    t0 = time.time()
    status = "ok"
    try:
        with open(logf, "w", encoding="utf-8") as f:
            p = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env, cwd=r"D:\new_automation\All codes", timeout=secs + 420)
            if p.returncode != 0:
                status = f"exit {p.returncode}"
    except subprocess.TimeoutExpired:
        status = "timed out"
    text = open(logf, encoding="utf-8", errors="replace").read()
    m = re.search(r"proof folder: (\S.*)", text)
    rep: Dict[str, Any] = {}
    if m:
        with contextlib.suppress(Exception):
            rep = json.load(open(os.path.join(m.group(1).strip(), "report.json"), encoding="utf-8"))
            rep["_folder"] = m.group(1).strip()
            md = os.path.join(m.group(1).strip(), "UNDERSTANDING.md")
            if os.path.isfile(md):
                rep["_understanding_md"] = open(md, encoding="utf-8").read()
    return {"status": status, "report": rep, "seconds": round(time.time() - t0), "log": logf}


def growth_snapshot(rag: Any, run: str, tag: str) -> Dict[str, Any]:
    snap: Dict[str, Any] = {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "run": run, "tag": tag}
    with contextlib.suppress(Exception):
        from core_organs.rag import lt
        snap["fast_paths_total"] = int(rag.fast.st.count("fast_paths"))
        snap["web_hotkey_rows"] = len([r for r in lt.fetch(rag.fast.st, "fast_paths", "app_key LIKE 'webapp:%'", 100000) if r.get("kind") == "hotkey"])
    with contextlib.suppress(Exception):
        import sqlite3
        db = sqlite3.connect(f"file:{os.path.join(WK.DATA, 'ai_root', 'rag', 'lexicon.db')}?mode=ro", uri=True)
        snap["web_commands"] = db.execute("SELECT COUNT(*) FROM commands WHERE app_key LIKE 'webapp:%'").fetchone()[0]
        snap["web_apps"] = db.execute("SELECT COUNT(DISTINCT app_key) FROM commands WHERE app_key LIKE 'webapp:%'").fetchone()[0]
        db.close()
    wk = WK.WebKind()
    snap["kind_examples"] = len(wk.examples)
    snap["kind_classes"] = len(wk.classes())
    with contextlib.suppress(Exception):
        snap["kind_leave_one_out"] = {k: v for k, v in wk.leave_one_out().items() if k != "wrong"}
    with contextlib.suppress(Exception):
        snap["patterns"] = json.load(open(WL.PATTERNS, encoding="utf-8")).get("summary")
    os.makedirs(OUT, exist_ok=True)
    with open(GROWTH, "a", encoding="utf-8") as f:
        f.write(json.dumps(snap, ensure_ascii=False) + "\n")
    return snap


def predict_before(site: Dict[str, Any]) -> Dict[str, Any]:
    """What the system expects of this site BEFORE scanning it: its category (from the labelled sites it already knows) and the sections that category's sites usually have."""
    out: Dict[str, Any] = {"category": None, "sections": []}
    out["sections"] = [x["section"] for x in WL.common_sections(site["category"], WL.host_of(site["url"]), top=15)]
    return out


def score_prediction(site: Dict[str, Any], report: Dict[str, Any], pre: Dict[str, Any]) -> Dict[str, Any]:
    words = WL.signature_words(report)
    wk = WK.WebKind()
    r = wk.classify(words, exclude_host=WL.host_of(site["url"]))
    sc: Dict[str, Any] = {"kind_status": r["status"], "kind_ranked": r["ranked"][:3], "kind_hit": None, "kind_n_examples": r.get("n_examples", 0)}
    if r["ranked"]:
        sc["kind_hit"] = r["ranked"][0][0] == site["category"]
        sc["kind_top2_hit"] = site["category"] in [c for c, _ in r["ranked"][:2]]
    actual = set(WL.sections_of(report))
    pred = set(pre.get("sections", []))
    if pred:
        sc["sections_predicted"] = len(pred)
        sc["sections_predicted_found"] = len(pred & actual)
        sc["sections_found"] = len(actual)
        sc["sections_precision"] = round(len(pred & actual) / len(pred), 3)
    return sc


def write_summary(state: Dict[str, Any]) -> None:
    items = list(state["sites"].items())
    done = [(u, s) for u, s in items if s.get("status") in ("ok", "refused", "no_page", "failed")]
    ok = [(u, s) for u, s in done if s["status"] == "ok"]
    hits = [s["score"]["kind_hit"] for _, s in ok if (s.get("score") or {}).get("kind_hit") is not None]
    prec = [s["score"]["sections_precision"] for _, s in ok if (s.get("score") or {}).get("sections_precision") is not None]
    md = ["# Web curriculum", "", f"{len(ok)} sites learned, {sum(1 for _, s in done if s['status'] == 'refused')} refused by the site, {sum(1 for _, s in done if s['status'] in ('failed', 'no_page'))} failed / empty.", ""]
    if hits:
        last = hits[-10:]
        md += [f"**Category recognised before learning (online accuracy): {sum(hits)}/{len(hits)} overall, {sum(last)}/{len(last)} on the latest {len(last)} sites.**"]
    if prec:
        md += [f"**Sections predicted from the category's other sites (precision): mean {sum(prec) / len(prec):.2f} overall, {sum(prec[-10:]) / len(prec[-10:]):.2f} on the latest {len(prec[-10:])}.**"]
    md += ["", "| site | category | tier | status | controls | clicks | depth | clicked % | commands | hotkeys | kind prediction | secs |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for u, s in done:
        sc = s.get("score") or {}
        kr = (sc.get("kind_ranked") or [["-", 0]])[0]
        md.append(f"| {u} | {s.get('category')} | {s.get('tier')} | {s['status']} | {s.get('controls', '-')} | {s.get('clicks', '-')} | {s.get('depth', '-')} | {s.get('pct_clicked', '-')} | {s.get('commands', '-')} | {s.get('hotkeys', '-')} | "
                  f"{kr[0]} ({sc.get('kind_status', '-')}){' OK' if sc.get('kind_hit') else ''} | {s.get('seconds', '-')} |")
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "SUMMARY.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))


def task_eval(rag: Any, n: int, stamp: str, log: Callable[[str], None]) -> Dict[str, Any]:
    """Every few sites: a small task test (cold agent vs the pool) on what is stored so far. The result is the learning curve that matters: do the stored paths WORK. Corrections found on the way are filed back."""
    out: Dict[str, Any] = {}
    with contextlib.suppress(Exception):
        from core_organs.harvest import web_tasks_eval as TE
        r = TE.run(n=n, seed=int(time.time()) % 100000, show=False, learn=True, log=lambda s: None)
        sm = r["summary"]
        out = {"tasks": sm["tasks"], "cold": sm["cold"]["success"], "pool": sm["pool"]["success"], "retrieval_top1": sm["retrieval_top1_correct"], "healed": sm.get("pool_healed_after_a_stale_path"), "folder": r["folder"]}
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "task_eval.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M:%S"), "run": stamp, **out}) + "\n")
        log(f"TASKEVAL {out['tasks']} tasks: cold {out['cold']}, pool {out['pool']}, retrieval top-1 {out['retrieval_top1']}, healed {out['healed']}")
    return out


def run(hours: float = 10.0, only: Optional[Sequence[str]] = None, tier: Optional[int] = None, rag: Any = None, runner: Callable[..., Dict[str, Any]] = subprocess_runner,
        write: bool = True, gap_s: float = 12.0, log: Callable[[str], None] = print, retry_refused: bool = False, eval_every: int = 0, eval_n: int = 8,
        evaluator: Optional[Callable[..., Dict[str, Any]]] = None, shard: str = "") -> Dict[str, Any]:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    st = load_state()
    todo = [r for r in ordered(rows(only, tier)) if in_shard(r["url"], shard) and st["sites"].get(r["url"], {}).get("status") not in (("ok",) if retry_refused else ("ok", "refused"))]
    deadline = time.time() + hours * 3600
    log(f"RUN {stamp}: {len(todo)} sites to do, budget {hours} h" + (f", shard {shard}" if shard else ""))
    if rag is not None and write:
        with contextlib.suppress(Exception):
            growth_snapshot(rag, stamp, "start")
    fails = 0
    learned_since_eval = 0
    for site in todo:
        if os.path.isfile(STOP):
            log("STOPPING: STOP file")
            break
        if time.time() > deadline:
            log("STOPPING: time budget spent")
            break
        if shutil.disk_usage(OUT if os.path.isdir(OUT) else os.path.dirname(OUT)).free < 3e9:
            log("STOPPING: low disk")
            break
        if st.get("sites", {}).get(site["url"], {}).get("status") in ("ok",) or load_state().get("sites", {}).get(site["url"], {}).get("status") in (("ok",) if retry_refused else ("ok", "refused")):
            continue                                                                                   # the other crawler did it meanwhile
        log(f"SITESTART {site['name']} ({site['url']}; {site['category']}, rung {site['tier']})")
        pre = predict_before(site)
        r = runner(site, log)
        rep = r.get("report") or {}
        ent: Dict[str, Any] = {"name": site["name"], "category": site["category"], "tier": site["tier"], "seconds": r.get("seconds"), "when": time.strftime("%Y-%m-%d %H:%M:%S"), "run": stamp}
        if not rep:
            ent["status"] = "no_page"
            ent["why"] = r.get("status")
            fails += 1
        else:
            fails = 0
            ex = (rep.get("scan") or {}).get("explore") or {}
            cov = ex.get("coverage") or {}
            ent.update(controls=(rep.get("digest") or {}).get("controls"), clicks=ex.get("clicks"), depth=ex.get("max_depth"), pct_clicked=cov.get("pct_clicked"))
            ent["score"] = score_prediction(site, rep, pre)
            lr = WL.learn_site(rag, rep, site["url"], site["category"], stamp, ledger=LEDGER, write=write, doc_text=rep.get("_understanding_md", ""))
            ent.update(status="refused" if lr["status"] == "refused_by_site" else "ok", commands=lr.get("commands"), hotkeys=lr.get("hotkeys"), doc_chunks=lr.get("doc_chunks"),
                       example_added=lr.get("example_added"))
        st = save_site(site["url"], ent)
        os.makedirs(OUT, exist_ok=True)
        with open(PROGRESS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"url": site["url"], **ent}, ensure_ascii=False) + "\n")
        write_summary(st)
        snap = growth_snapshot(rag, stamp, site["name"]) if (rag is not None and write) else {}
        loo = (snap.get("kind_leave_one_out") or {})
        log(f"SITEDONE {site['name']}: {ent['status']}; controls {ent.get('controls')}; clicks {ent.get('clicks')}; depth {ent.get('depth')}; commands {ent.get('commands')}; hotkeys {ent.get('hotkeys')}; "
            f"kind {((ent.get('score') or {}).get('kind_ranked') or [['-']])[0][0]}={'hit' if (ent.get('score') or {}).get('kind_hit') else 'miss'}; LOO top1 {loo.get('top1')}; {ent.get('seconds')} s")
        if fails >= 4:
            log("STOPPING: 4 sites in a row produced nothing")
            break
        if ent["status"] == "ok":
            learned_since_eval += 1
        if eval_every and learned_since_eval >= eval_every and write and (rag is not None or evaluator is not None):
            learned_since_eval = 0
            (evaluator or task_eval)(rag, eval_n, stamp, log)
        time.sleep(gap_s)
    log(f"RUNDONE {stamp}")
    return st


def rollback(stamp: str, rag: Any, ledger: str = "") -> Dict[str, Any]:
    """Forget what a run wrote: its hotkey rows (only unverified ones) and its lexicon commands (only those that no other run also wrote)."""
    n_rows = n_cmds = 0
    cmds: Dict[str, List[str]] = {}
    others: set = set()
    ledger = ledger or LEDGER
    for line in open(ledger, encoding="utf-8") if os.path.isfile(ledger) else []:
        j = json.loads(line)
        if j["run"] == stamp:
            ids = []
            for action, payload in j.get("hotkeys", []):
                row = rag.fast.find(j["key"], action, payload)
                if row and not row.get("verified"):
                    ids.append(row["fast_id"])
            with WL.rag_lock():
                n_rows += rag.fast.forget_rows(ids)
            cmds.setdefault(j["key"], []).extend(j.get("commands", []))
            if j.get("procedures"):
                with WL.rag_lock():
                    n_procs = locals().get("n_procs", 0) + int(rag.proc.forget_procedure_ids(j["procedures"]) or 0)
        else:
            others.update((j["key"], c) for c in j.get("commands", []))
    db = rag.lex.db                                                                          # the lexicon's own connection: the same store the run wrote to
    with WL.rag_lock():
        for key, labels in cmds.items():
            for lab in labels:
                if (key, lab) in others:
                    continue
                row = db.one("SELECT command_id FROM commands WHERE app_key=? AND label=?", (key, lab))
                if row:
                    db.execute("DELETE FROM aliases WHERE command_id=?", (row["command_id"],))
                    db.execute("DELETE FROM commands WHERE command_id=?", (row["command_id"],))
                    n_cmds += 1
    return {"hotkey_rows_forgotten": n_rows, "commands_forgotten": n_cmds, "procedures_forgotten": locals().get("n_procs", 0)}


def rebuild_kind() -> Dict[str, Any]:
    """Re-derive every site's word profile from its saved report with the CURRENT signature recipe (the newest report per site wins) and report the held-out accuracy before and after."""
    import glob
    cat_of = {WL.host_of(u): c for c, sites in LADDERS.items() for _, u, _ in sites}
    before = WK.WebKind().leave_one_out()
    newest: Dict[str, str] = {}
    for p in sorted(glob.glob(os.path.join(REPORTS, "try_app", "2026*", "report.json")), key=os.path.getmtime):
        with contextlib.suppress(Exception):
            tgt = WL.host_of(json.load(open(p, encoding="utf-8")).get("target", ""))
            if tgt in cat_of:
                newest[tgt] = p
    n = 0
    for host, p in newest.items():
        rep = json.load(open(p, encoding="utf-8"))
        if ((rep.get("understanding") or {}).get("auth") or {}).get("blocked"):
            continue
        n += WK.add_example(host, cat_of[host], WL.signature_words(rep))
    after = WK.WebKind().leave_one_out()
    return {"sites_rebuilt": n, "before": {k: v for k, v in before.items() if k != "wrong"}, "after": {k: v for k, v in after.items() if k != "wrong"}, "still_wrong": after.get("wrong", [])}


def start_vlm(log: Callable[[str], None] = print, wait_s: float = 240.0) -> Optional[subprocess.Popen]:
    """Start the local vision model if it is not already up; returns the process this call started (None if it was already running or could not start)."""
    import urllib.request
    def up() -> bool:
        with contextlib.suppress(Exception):
            return b"ok" in urllib.request.urlopen("http://127.0.0.1:8081/health", timeout=2).read()
        return False
    if up():
        log("vision model already running")
        return None
    bat = os.path.join("D:" + os.sep, "new_automation", "scratch", "_start_vision_8b.bat")
    if not os.path.isfile(bat):
        log("vision model script not found: video pictures will be read by OCR only")
        return None
    proc = subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000)
    t0 = time.time()
    while time.time() - t0 < wait_s:
        if up():
            log(f"vision model up after {time.time() - t0:.0f} s")
            return proc
        time.sleep(4)
    log("vision model did not come up in time: video pictures will be read by OCR only")
    return proc


def backup_rag() -> str:
    src = os.path.join(WK.DATA, "ai_root", "rag")
    dst = os.path.join(WK.DATA, "backups", "rag_before_web_curriculum_" + time.strftime("%Y%m%d_%H%M%S"))
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.lock"))
    return dst


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "list", "report", "rollback", "rebuild-kind"])
    ap.add_argument("arg", nargs="?", default="")
    ap.add_argument("--hours", type=float, default=10.0)
    ap.add_argument("--only", default="")
    ap.add_argument("--tier", type=int, default=0)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--retry-refused", action="store_true")
    ap.add_argument("--vlm", action="store_true", help="start the local vision model (Qwen3-VL on :8081) for the run so each video gets one-sentence descriptions of what its picture shows; stopped again at the end")
    ap.add_argument("--no-transcribe", action="store_true", help="read what videos SHOW but do not transcribe their audio")
    ap.add_argument("--eval-every", type=int, default=8, help="after every N learned sites run a small task test (cold agent vs the pool) and log the result; 0 = never")
    ap.add_argument("--shard", default="", help="i/n: this crawler takes every n-th site (by a stable hash); run two crawlers, one on screen and one --minimized, with --shard 0/2 and 1/2")
    ap.add_argument("--minimized", action="store_true", help="a real browser window that stays MINIMIZED with no cursor overlay (works with the screen locked to other work)")
    ap.add_argument("--headless", action="store_true", help="no browser window: the same exploration, silently (default is ON SCREEN with the virtual cursor)")
    a = ap.parse_args(argv)
    global VISIBLE, NO_TRANSCRIBE, MINIMIZED
    VISIBLE = not a.headless
    MINIMIZED = a.minimized
    NO_TRANSCRIBE = a.no_transcribe
    only = [x for x in a.only.split(",") if x] or None
    if a.cmd == "list":
        for i, r in enumerate(ordered(rows(only, a.tier or None)), 1):
            print(f"{i:3d}  rung {r['tier']}  {r['category']:<18} {r['name']:<22} {r['url']}")
        return 0
    if a.cmd == "report":
        write_summary(load_state())
        print(open(os.path.join(OUT, "SUMMARY.md"), encoding="utf-8").read())
        return 0
    if a.cmd == "rebuild-kind":
        print(json.dumps(rebuild_kind(), indent=1, default=str))
        return 0
    from core_organs import rag as R
    rag = R.get_rag()
    if a.cmd == "rollback":
        print(json.dumps(rollback(a.arg, rag), indent=1))
        return 0
    if not a.no_write and not a.no_backup:
        print("backing up the RAG folder to", backup_rag(), flush=True)
    with contextlib.suppress(Exception):
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)               # keep the machine awake while this process runs
        os.nice(10) if hasattr(os, "nice") else None
    vlm_proc = start_vlm(log=lambda s: print(s, flush=True)) if a.vlm else None
    try:
        run(a.hours, only, a.tier or None, rag, write=not a.no_write, log=lambda s: print(s, flush=True), retry_refused=a.retry_refused, eval_every=a.eval_every, shard=a.shard)
    finally:
        if vlm_proc is not None:
            with contextlib.suppress(Exception):
                subprocess.run(["taskkill", "/PID", str(vlm_proc.pid), "/T", "/F"], capture_output=True)              # only the process THIS run started
    return 0


if __name__ == "__main__":
    sys.exit(main())
