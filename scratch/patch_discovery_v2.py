import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
s = io.open(P, "r", encoding="utf-8").read()


def between(start_marker, end_marker):
    a = s.index(start_marker)
    b = s.index(end_marker, a)
    return a, b


# ------------------------------------------------------------------------------------------------ 1. search section
a, b = between("# ----------------------------------------------------------------------------------------------------------------- search", "# ================================================================================================================= registry")
SEARCH = r'''# ----------------------------------------------------------------------------------------------------------------- search
_BAD_HOSTS = ("youtube.", "youtu.be", "facebook.", "twitter.", "x.com", "instagram.", "pinterest.", "reddit.", "amazon.", "ebay.", "aliexpress.", "tiktok.", "linkedin.", "quora.", "wikipedia.org", "softonic.", "cnet.", "uptodown.", "filehippo.")
# third-party "manual libraries" re-host other people's PDFs (copyright, ads, wrong versions): never a source here
_AGGREGATORS = ("manualslib.", "manualzz.", "scribd.", "studylib.", "pdfcoffee.", "dokumen.", "usermanual.wiki", "manuals.plus", "manuals.ca", "manualsdir.", "device.report", "manualsbase.", "pdfslide.",
                "vdocuments.", "yumpu.", "issuu.", "slideshare.", "academia.edu", "coursehero.", "chegg.", "manualsonline.", "manualowl.", "all-guides.", "ifixit.")
_QA_HOSTS = ("stackoverflow.", "stackexchange.", "superuser.", "askubuntu.", "medium.com")
_ADULT_RX = re.compile(r"\b(porn\w*|xxx|xhamster\w*|xnxx\w*|xvideos\w*|redtube\w*|sex|sexy|sexo|nsfw|erotic\w*|escort\w*|casino\w*|betting|gambl\w*|lottery|onlyfans)\b", re.I)
_DOCISH_PATH = re.compile(r"(docs?|help|manual|guide|support|userguide|learn|handbook|documentation|knowledge)", re.I)
_DOCISH_TITLE = re.compile(r"(user guide|users guide|user manual|manual|documentation|help|handbook|getting started|reference guide|online help)", re.I)
BLOCKED_PROVIDERS: set = set()                         # search providers that answered with a bot-detection challenge in this process: never retried, NEVER bypassed
LAST_PROVIDER = ""


def unsafe_result(url: str, title: str) -> bool:
    """Adult / gambling results (a bot reading the web must never fetch them) and manual-aggregator sites."""
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return bool(_ADULT_RX.search(re.sub(r"[^a-z0-9]+", " ", host) + " " + (title or ""))) or any(a in host for a in _AGGREGATORS)


class _DDG(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: List[Tuple[str, str]] = []
        self._href = ""
        self._title = ""
        self._on = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "a":
            d = dict(attrs)
            if "result__a" in (d.get("class") or ""):
                self._on, self._href, self._title = True, d.get("href") or "", ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._on:
            self._on = False
            href = self._href
            if "uddg=" in href:
                href = urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get("uddg", [""])[0])
            elif href.startswith("//"):
                href = "https:" + href
            if href.startswith("http"):
                self.results.append((href, re.sub(r"\s+", " ", self._title).strip()))

    def handle_data(self, data: str) -> None:
        if self._on:
            self._title += data


def parse_ddg(html_text: str) -> List[Dict[str, str]]:
    p = _DDG()
    try:
        p.feed(html_text)
    except Exception:
        pass
    return [{"url": u, "title": t} for u, t in p.results]


def _decode_bing(href: str) -> str:
    """Bing wraps result links in bing.com/ck/a?...&u=a1<base64url of the real URL>."""
    href = html.unescape(href)
    if "bing.com/ck/a" not in href:
        return href
    u = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get("u", [""])[0]
    if u.startswith("a1"):
        b = u[2:] + "=" * (-len(u[2:]) % 4)
        try:
            return base64.urlsafe_b64decode(b).decode("utf-8", "replace")
        except Exception:
            return ""
    return ""


def parse_bing(html_text: str) -> List[Dict[str, str]]:
    out = []
    for m in re.finditer(r'<li class="b_algo".*?<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html_text, flags=re.S):
        url = _decode_bing(m.group(1))
        if url.startswith("http"):
            out.append({"url": url, "title": html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()})
    return out


def is_challenge(status: int, body: bytes) -> bool:
    """A bot-detection page (HTTP 202 / 403 / 429, a captcha, 'unusual traffic'). The Professor stops using that provider - it never tries to solve or get around it."""
    if status in (202, 403, 429):
        return True
    head = body[:6000].lower()
    return any(k in head for k in (b"captcha", b"unusual traffic", b"are you a robot", b"anomaly-modal", b"verify you are human"))


def _results_from_json_or_html(ct: str, body: bytes, limit: int) -> List[Dict[str, str]]:
    if "json" in ct or body.lstrip()[:1] in (b"{", b"["):
        try:
            data = json.loads(body.decode("utf-8", "replace"))
            items = (data.get("results") or data.get("items") or []) if isinstance(data, dict) else data
            return [{"url": str(i.get("url") or i.get("link") or ""), "title": str(i.get("title", ""))} for i in items if isinstance(i, dict) and (i.get("url") or i.get("link"))][:limit]
        except Exception:
            return []
    return parse_ddg(body.decode("utf-8", "replace"))[:limit]


def search_web(query: str, fetch: Fetcher, limit: int = 8) -> List[Dict[str, str]]:
    """Results [{url, title}]. Provider chain: HOJAIGA_GUIDE_SEARCH_URL (your own SearXNG / Google CSE endpoint: a template with {q}) -> Bing's HTML page -> DuckDuckGo's HTML page. A provider that answers with a bot-detection
    challenge is dropped for the rest of the process (never solved, never worked around); safe-search is requested strictly; adult / gambling results and manual-aggregator sites are removed."""
    global LAST_PROVIDER
    tmpl = os.environ.get("HOJAIGA_GUIDE_SEARCH_URL", "")
    chain = (["custom"] if tmpl else []) + ["bing", "ddg"]
    for prov in chain:
        if prov in BLOCKED_PROVIDERS:
            continue
        if prov == "custom":
            url = tmpl.replace("{q}", urllib.parse.quote_plus(query))
        elif prov == "bing":
            url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "setlang": "en", "adlt": "strict", "mkt": "en-US", "cc": "US"})
        else:
            url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query, "kp": "1"})
        status, ct, body, _f = fetch(url)
        if is_challenge(status, body) and prov != "custom":
            BLOCKED_PROVIDERS.add(prov)
            continue
        if status != 200 or not body:
            continue
        res = _results_from_json_or_html(ct, body, limit * 2) if prov in ("custom", "ddg") else parse_bing(body.decode("utf-8", "replace"))
        res = [r for r in res if r.get("url", "").startswith("http") and not unsafe_result(r["url"], r.get("title", ""))][:limit]
        if res:
            LAST_PROVIDER = prov
            return res
    return []


def _clean_names(ident: AppIdentity, k: int = 2) -> List[str]:
    names: List[str] = []
    for n in ident.names()[: k + 2]:
        n = re.sub(r"[\"'\\]", "", n).strip()
        if n and n.lower() not in [x.lower() for x in names]:
            names.append(n)
    return names[:k]


def dork_queries(ident: AppIdentity, max_queries: int = 5) -> List[Dict[str, str]]:
    """The search-OPERATOR queries (the 'Google dork' idea), filled with the application's own name:
         pdf    filetype:pdf (intitle:"user manual" OR intitle:"user guide") "<name>"            PDF manuals / guides
         docs   (inurl:docs OR inurl:manual OR inurl:help) "<name>" (guide OR documentation)       live documentation sites and sub-domains
         wiki   site:github.com inurl:wiki "<name>" documentation                                   open-source / developer tools' wikis
         plain  "<name>" user guide manual documentation                                            the fallback
    MEASURED: Bing's HTML page (the one that serves an honest bot) ignores `filetype:` / `site:` / `inurl:` (three different operator queries returned the same list, `site:` was read as plain words),
    DuckDuckGo's answers bots with a challenge, and Google needs a key. So these are used only through an endpoint that honours operators - your own SearXNG or a Google CSE you own
    (HOJAIGA_GUIDE_SEARCH_URL); everywhere else natural_queries() is used."""
    names = _clean_names(ident)
    out: List[Dict[str, str]] = []
    for i, n in enumerate(names):
        out.append({"kind": "pdf", "query": f'filetype:pdf (intitle:"user manual" OR intitle:"user guide") "{n}"'})
        if i == 0:
            out.append({"kind": "docs", "query": f'(inurl:docs OR inurl:manual OR inurl:help) "{n}" (guide OR documentation OR manual)'})
            out.append({"kind": "wiki", "query": f'site:github.com inurl:wiki "{n}" documentation'})
            out.append({"kind": "plain", "query": f'"{n}" user guide manual documentation'})
    return out[:max_queries]


def natural_queries(ident: AppIdentity, max_queries: int = 3) -> List[Dict[str, str]]:
    """Plain-language queries that an operator-ignoring engine answers well ('blender manual' -> docs.blender.org). An ambiguous one-word name gets its vendor as context ('Paint' -> 'Paint Microsoft')."""
    names = _clean_names(ident)
    if not names:
        return []
    n = names[0]
    ctx = ""
    vend = [w for w in re.findall(r"[A-Za-z0-9]+", ident.company or "") if len(w) > 2 and w.lower() not in ("inc", "ltd", "llc", "corp", "corporation", "software", "company", "gmbh", "the")]
    if len(n.split()) == 1 and vend:
        ctx = " " + vend[0]
    out = [{"kind": "manual", "query": f'"{n}"{ctx} user manual'}, {"kind": "docs", "query": f'"{n}"{ctx} documentation'}, {"kind": "pdf", "query": f'"{n}"{ctx} user guide pdf'}]
    if len(names) > 1:
        out.append({"kind": "docs", "query": f'"{names[1]}" help documentation'})
    return out[:max_queries]


def search_dorks(ident: AppIdentity, fetch: Fetcher, search: Optional[Callable[[str], List[Dict[str, str]]]] = None, delay_s: float = 0.6, per_query: int = 8,
                 sleep: Callable[[float], None] = time.sleep, max_queries: int = 5, operators: Optional[bool] = None) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    """Run the queries one after another (polite delay), merge and de-duplicate. Operator ('dork') queries when the endpoint honours them (a search function given, or HOJAIGA_GUIDE_SEARCH_URL set);
    natural-language queries otherwise. Returns (results tagged with the query kind, [{kind, query, results}])."""
    use_ops = bool(search) or bool(os.environ.get("HOJAIGA_GUIDE_SEARCH_URL")) if operators is None else operators
    queries = dork_queries(ident, max_queries) if use_ops else natural_queries(ident, max_queries)
    seen: Dict[str, Dict[str, str]] = {}
    ran: List[Dict[str, Any]] = []
    for i, dq in enumerate(queries):
        if i:
            sleep(delay_s)
        res = (search(dq["query"]) if search else search_web(dq["query"], fetch, per_query)) or []
        ran.append({"kind": dq["kind"], "query": dq["query"], "results": len(res), "provider": LAST_PROVIDER if not search else "custom-function"})
        for r in res:
            u = r.get("url", "")
            if u and u not in seen and not unsafe_result(u, r.get("title", "")):
                seen[u] = {**r, "kind": dq["kind"]}
    return list(seen.values()), ran


def rank_results(ident: AppIdentity, results: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Official-looking documentation first: vendor / product in the host, doc-looking path, manual-looking title; social, video, shop, Q&A, aggregator and adult results rejected."""
    vend = [w for w in re.findall(r"[a-z0-9]+", (ident.company or "").lower()) if len(w) > 2 and w not in ("inc", "ltd", "llc", "corp", "corporation", "software", "company", "gmbh", "the")]
    prod = [w for w in re.findall(r"[a-z0-9]+", " ".join(ident.names()).lower()) if len(w) > 2]
    out: List[Dict[str, Any]] = []
    for r in results:
        u = urllib.parse.urlsplit(r.get("url", ""))
        host, path, title = (u.hostname or "").lower(), u.path.lower(), r.get("title", "")
        if not host or any(b in host for b in _BAD_HOSTS) or unsafe_result(r.get("url", ""), title):
            continue
        score, why = 0.0, []
        if any(v in host for v in vend):
            score += 3
            why.append("vendor domain")
        if any(p in host for p in prod):
            score += 2
            why.append("product in domain")
        if _DOCISH_PATH.search(path) or host.startswith(("docs.", "help.", "support.", "manual.")):
            score += 2
            why.append("documentation path")
        if _DOCISH_TITLE.search(title):
            score += 2
            why.append("manual-looking title")
        if any(p in title.lower() for p in prod):
            score += 1
        if any(q in host for q in _QA_HOSTS):
            score -= 2
            why.append("Q&A site")
        if path.endswith(".pdf"):
            score += 0.5
            if r.get("kind") == "pdf":
                score += 0.5
                why.append("pdf manual")
        if r.get("kind") == "wiki" and host.endswith("github.com") and "/wiki" in path:
            score += 3
            why.append("project wiki")
        out.append({"url": r["url"], "title": title, "score": round(score, 2), "why": why, "kind": r.get("kind", "")})
    out.sort(key=lambda c: -c["score"])
    return out


# ------------------------------------------------------------------------------------ official sources (the 'other manners')
_TWO_LEVEL = {"co.uk", "com.au", "co.in", "co.jp", "com.br", "co.nz", "org.uk", "com.cn", "co.za"}


def registrable(host: str) -> str:
    parts = (host or "").lower().split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in _TWO_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


_DOC_LINK_POS = re.compile(r"(documentation|docs?\b|user[ -]?guide|user[ -]?manual|manual|help[ -]?cent|help\b|support|learn|knowledge|kb\b|getting[ -]?started|tutorials?|faq|reference)", re.I)
_DOC_LINK_NEG = re.compile(r"(download|pricing|price|login|log-in|sign[ -]?in|sign[ -]?up|blog|store|shop|cart|checkout|community|forum|careers?|jobs|press|about|contact|donate|privacy|terms|cookie|news|events|partners)", re.I)


class _Anchors(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: List[Tuple[str, str]] = []
        self._href = ""
        self._text = ""
        self._on = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "a":
            self._on, self._href, self._text = True, dict(attrs).get("href") or "", ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._on:
            self._on = False
            self.items.append((self._href, re.sub(r"\s+", " ", self._text).strip()))

    def handle_data(self, data: str) -> None:
        if self._on:
            self._text += data


def doc_links(home_url: str, fetch: Fetcher, robots: Optional[Robots] = None, limit: int = 3, allow_local: bool = False) -> List[Dict[str, Any]]:
    """Where does the vendor's own site keep its documentation? Read the page, score its links by what they SAY (docs / manual / user guide / help / support / learn ...) and keep the best ones that stay on
    the vendor's own registrable domain (docs.x.com, support.x.com, x.com/docs ...)."""
    ok, why = public_url(home_url, allow_local)
    if not ok or (robots is not None and not robots.allowed(home_url)):
        return []
    status, ct, body, final = fetch(home_url)
    if status != 200 or not body or ("html" not in ct and ct):
        return []
    a = _Anchors()
    try:
        a.feed(body.decode("utf-8", "replace"))
    except Exception:
        pass
    base = urllib.parse.urlsplit(final or home_url)
    dom = registrable(base.hostname or "")
    cands: Dict[str, Dict[str, Any]] = {}
    for href, text in a.items:
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        url = urllib.parse.urldefrag(urllib.parse.urljoin(final or home_url, href))[0]
        u = urllib.parse.urlsplit(url)
        if u.scheme not in ("http", "https") or registrable(u.hostname or "") != dom:
            continue
        if os.path.splitext(u.path.lower())[1] in BINARY_EXT:
            continue
        blob = f"{text} {u.path} {u.hostname}"
        score = (3 if _DOC_LINK_POS.search(text) else 0) + (2 if _DOC_LINK_POS.search((u.hostname or "").split(".")[0] + " " + u.path) else 0) - (3 if _DOC_LINK_NEG.search(text) else 0) - (2 if _DOC_LINK_NEG.search(u.path) else 0)
        if re.search(r"(user[ -]?guide|user[ -]?manual|documentation|manual)", blob, re.I):
            score += 1
        if score >= 3 and not unsafe_result(url, text):
            if url not in cands or cands[url]["score"] < score:
                cands[url] = {"url": url, "title": text[:60], "score": float(score), "why": ["link on the vendor's own site"], "kind": "official"}
    return sorted(cands.values(), key=lambda c: -c["score"])[:limit]


def _winget_run(args: List[str], timeout: float = 25.0) -> str:
    import subprocess
    try:
        r = subprocess.run(["winget"] + args + ["--accept-source-agreements"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=0x08000000)
        return r.stdout or ""
    except Exception:
        return ""


def winget_info(name: str, runner: Callable[[List[str]], str] = _winget_run) -> Dict[str, Any]:
    """The package's OFFICIAL links from the winget catalogue (structured, free): Documentation entries, Publisher Support Url, Homepage. {} when it is not a winget package."""
    out = runner(["search", name, "--source", "winget"])
    rows = [ln for ln in out.splitlines() if ln.strip() and not set(ln.strip()) <= set("-")]
    pid = ""
    low = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    for ln in rows[1:]:
        parts = re.split(r"\s{2,}", ln.strip())
        if len(parts) >= 2 and re.sub(r"[^a-z0-9]+", " ", parts[0].lower()).strip() == low:
            pid = parts[1]
            break
    if not pid:
        return {}
    txt = runner(["show", "--id", pid, "--exact", "--source", "winget"])
    info: Dict[str, Any] = {"id": pid, "docs": [], "support": "", "homepage": "", "publisher": ""}
    lines = txt.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"^(Publisher Support Url|Homepage|Publisher Url|Package Url):\s*(https?://\S+)", ln.strip())
        if m:
            key = {"Publisher Support Url": "support", "Homepage": "homepage", "Publisher Url": "publisher", "Package Url": "homepage"}[m.group(1)]
            info[key] = info[key] or m.group(2)
        if ln.strip() == "Documentation:":
            for sub in lines[i + 1:i + 8]:
                mm = re.match(r"^\s+([^:]+):\s*(https?://\S+)", sub)
                if not mm:
                    break
                info["docs"].append((mm.group(1).strip(), mm.group(2)))
    return info


def official_sources(ident: AppIdentity, fetch: Fetcher, robots: Robots, winget: bool = True, seeds: Sequence[str] = (), runner: Callable[[List[str]], str] = _winget_run,
                     allow_local: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Official starting points for crawling, strongest first: winget 'Documentation' links, the pages the vendor's support / home page links to as its docs, then seeds that answer HTTP 200."""
    out: List[Dict[str, Any]] = []
    note: Dict[str, Any] = {}
    if winget:
        for n in _clean_names(ident, 2):
            info = winget_info(n, runner)
            if info:
                note["winget"] = info.get("id")
                for label, url in info.get("docs", []):
                    out.append({"url": url, "title": label, "score": 9.0, "why": ["winget Documentation entry"], "kind": "winget-docs"})
                for key in ("support", "homepage"):
                    if info.get(key):
                        for c in doc_links(info[key], fetch, robots, limit=2, allow_local=allow_local):
                            out.append({**c, "kind": f"winget-{key}-link", "why": c["why"] + [f"linked from the winget {key} page"]})
                break
    for url in seeds:
        status, _ct, body, _f = fetch(url)
        if status == 200 and body:
            out.append({"url": url, "title": "seed", "score": 7.0, "why": ["official documentation root (seed list, verified to answer)"], "kind": "seed"})
    seen, uniq = set(), []
    for c in sorted(out, key=lambda c: -c["score"]):
        if c["url"] not in seen:
            seen.add(c["url"])
            uniq.append(c)
    return uniq, note


'''
s = s[:a] + SEARCH + s[b:]

# ------------------------------------------------------------------------------------------------ 2. imports
s = s.replace("import ctypes\nimport ctypes.wintypes as wt\nimport io\n", "import base64\nimport ctypes\nimport ctypes.wintypes as wt\nimport html\nimport io\n", 1)

# ------------------------------------------------------------------------------------------------ 3. discover(): official sources first, then search
old_sig = '''             max_pages: int = 40, max_depth: int = 2, embed_small: bool = True) -> Dict[str, Any]:'''
new_sig = '''             max_pages: int = 40, max_depth: int = 2, embed_small: bool = True, official: Optional[bool] = None, seeds: Sequence[str] = (), max_queries: int = 5, sources_wanted: int = 2,
             winget_runner: Callable[[List[str]], str] = _winget_run) -> Dict[str, Any]:'''
assert old_sig in s
s = s.replace(old_sig, new_sig, 1)
a2 = s.index("        # ---- tier 3: the web (opt-in)")
b2 = s.index("        n_docs = indexed_docs(ix, key)")
TIER3 = r'''        # ---- tier 3: the web (opt-in): official sources first (winget, the vendor's own links, verified seeds), then search
        if web_enabled(web) and not indexed_docs(ix, key):
            rep["web"] = "on"
            names = ident.names()
            if not names:
                rep["skipped"].append(("web", "no product name to search for"))
            else:
                use_official = (search is None) if official is None else official                     # a stubbed search function means a test: no winget, no homepage reading
                pool: List[Dict[str, Any]] = []
                if use_official or seeds:
                    off, note = official_sources(ident, fetch, robots, winget=use_official, seeds=seeds, runner=winget_runner, allow_local=allow_local_net)
                    pool += off
                    rep["tiers"].append({"tier": 3, "did": "official sources", "winget": note.get("winget"), "found": [{k: c[k] for k in ("url", "score", "kind")} for c in off][:8]})
                results, ran = search_dorks(ident, fetch, search, delay_s=delay_s, max_queries=max_queries)
                ranked = [c for c in rank_results(ident, results) if c["score"] >= 3][:4]
                rep["tiers"].append({"tier": 3, "did": "web search", "queries": ran, "results": len(results), "candidates": [{k: c[k] for k in ("url", "score", "why")} for c in ranked]})
                pool += ranked
                # a vendor home page found by the search leads to its docs
                if use_official:
                    for c in ranked[:2]:
                        if "vendor domain" in c["why"] or "product in domain" in c["why"]:
                            if not _DOCISH_PATH.search(urllib.parse.urlsplit(c["url"]).path) and not c["url"].lower().endswith(".pdf"):
                                for dl in doc_links(c["url"], fetch, robots, limit=2, allow_local=allow_local_net):
                                    pool.append(dl)
                got, tried = 0, set()
                for c in pool:
                    if time.time() > deadline or got >= sources_wanted:
                        break
                    if c["url"] in tried:
                        continue
                    tried.add(c["url"])
                    pages, sk = crawl(c["url"], fetch, robots, max_pages=max_pages, max_depth=max_depth, delay_s=delay_s, allow_local=allow_local_net, deadline=deadline)
                    rep["skipped"] += [(u, w) for u, w in sk]
                    if _ingest_pages(ix, key, pages, rep, reg, "web", ident.version, embed_small):
                        got += 1
'''
s = s[:a2] + TIER3 + s[b2:]
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("discovery v2 written")
