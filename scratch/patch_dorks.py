import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


# 1. PDFs get a larger cap than pages
rep('''def default_fetch(url: str, timeout: float = 15.0, max_bytes: int = 2_000_000) -> Tuple[int, str, bytes, str]:
    if requests is None:
        return 0, "", b"", url''', '''PDF_MAX_BYTES = 12 * 1024 * 1024


def default_fetch(url: str, timeout: float = 15.0, max_bytes: int = 2_000_000) -> Tuple[int, str, bytes, str]:
    if requests is None:
        return 0, "", b"", url
    if urllib.parse.urlsplit(url).path.lower().endswith(".pdf"):
        max_bytes = max(max_bytes, PDF_MAX_BYTES)                  # a manual is a PDF of a few MB; a truncated PDF is unreadable, so it gets the larger cap''')

# 2. result formats: Google Custom Search JSON ('items' with 'link'), SearXNG ('results' with 'url')
rep('''            data = json.loads(body.decode("utf-8", "replace"))
            items = data.get("results", data) if isinstance(data, dict) else data
            return [{"url": str(i.get("url", "")), "title": str(i.get("title", ""))} for i in items if isinstance(i, dict) and i.get("url")][:limit]''',
    '''            data = json.loads(body.decode("utf-8", "replace"))
            items = (data.get("results") or data.get("items") or []) if isinstance(data, dict) else data
            return [{"url": str(i.get("url") or i.get("link") or ""), "title": str(i.get("title", ""))} for i in items if isinstance(i, dict) and (i.get("url") or i.get("link"))][:limit]''')

# 3. the dork query set + a multi-query search
rep('''def rank_results(ident: AppIdentity''', '''def dork_queries(ident: AppIdentity, max_queries: int = 5) -> List[Dict[str, str]]:
    """The search-operator queries that go straight to manuals instead of marketing pages (the 'Google dork' idea), filled with the application's own name:
         pdf    filetype:pdf (intitle:"user manual" OR intitle:"user guide") "<name>"            PDF manuals / guides
         docs   (inurl:docs OR inurl:manual OR inurl:help) "<name>" (guide OR documentation)       live documentation sites and sub-domains
         wiki   site:github.com inurl:wiki "<name>" documentation                                   open-source / developer tools' wikis
         plain  "<name>" user guide manual documentation                                            the fallback
    The operators are understood by DuckDuckGo, SearXNG (it forwards them to its engines) and Google; the default endpoint is DuckDuckGo's HTML page - scraping Google itself is against its terms
    and its official JSON API needs a key, so Google is only used if YOU point HOJAIGA_GUIDE_SEARCH_URL at your own endpoint."""
    names = []
    for n in ident.names()[:2]:
        n = re.sub(r"[\\"'\\\\]", "", n).strip()
        if n and n.lower() not in [x.lower() for x in names]:
            names.append(n)
    out: List[Dict[str, str]] = []
    for i, n in enumerate(names):
        out.append({"kind": "pdf", "query": f'filetype:pdf (intitle:"user manual" OR intitle:"user guide") "{n}"'})
        if i == 0:
            out.append({"kind": "docs", "query": f'(inurl:docs OR inurl:manual OR inurl:help) "{n}" (guide OR documentation OR manual)'})
            out.append({"kind": "wiki", "query": f'site:github.com inurl:wiki "{n}" documentation'})
            out.append({"kind": "plain", "query": f'"{n}" user guide manual documentation'})
    return out[:max_queries]


def search_dorks(ident: AppIdentity, fetch: Fetcher, search: Optional[Callable[[str], List[Dict[str, str]]]] = None, delay_s: float = 0.6, per_query: int = 8,
                 sleep: Callable[[float], None] = time.sleep) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    """Run the dork queries one after another (polite delay), merge and de-duplicate. Returns (results tagged with the query kind, [{kind, query, results}])."""
    seen: Dict[str, Dict[str, str]] = {}
    ran: List[Dict[str, Any]] = []
    for i, dq in enumerate(dork_queries(ident)):
        if i:
            sleep(delay_s)
        res = (search(dq["query"]) if search else search_web(dq["query"], fetch, per_query)) or []
        ran.append({"kind": dq["kind"], "query": dq["query"], "results": len(res)})
        for r in res:
            u = r.get("url", "")
            if u and u not in seen:
                seen[u] = {**r, "kind": dq["kind"]}
    return list(seen.values()), ran


def rank_results(ident: AppIdentity''')

# 4. ranking knows which dork found the result
rep('''        if path.endswith(".pdf"):
            score += 0.5
        out.append({"url": r["url"], "title": title, "score": round(score, 2), "why": why})''', '''        if path.endswith(".pdf"):
            score += 0.5
            if r.get("kind") == "pdf":
                score += 0.5
                why.append("pdf manual")
        if r.get("kind") == "wiki" and host.endswith("github.com") and "/wiki" in path:
            score += 3
            why.append("project wiki")
        out.append({"url": r["url"], "title": title, "score": round(score, 2), "why": why, "kind": r.get("kind", "")})''')

# 5. discover(): tier 3 uses the dork set and keeps up to two good sources (e.g. the PDF and the live docs)
rep('''            names = ident.names()
            if not names:
                rep["skipped"].append(("web", "no product name to search for"))
            else:
                q = f'"{names[0]}" user guide manual documentation'
                results = search(q) if search else search_web(q, fetch)
                ranked = [c for c in rank_results(ident, results) if c["score"] >= 3][:3]
                rep["tiers"].append({"tier": 3, "did": "web search", "query": q, "results": len(results), "candidates": [{k: c[k] for k in ("url", "score", "why")} for c in ranked]})
                for c in ranked:
                    if time.time() > deadline:
                        break
                    pages, sk = crawl(c["url"], fetch, robots, max_pages=max_pages, max_depth=max_depth, delay_s=delay_s, allow_local=allow_local_net, deadline=deadline)
                    rep["skipped"] += [(u, w) for u, w in sk]
                    n = _ingest_pages(ix, key, pages, rep, reg, "web", ident.version, embed_small)
                    if n:
                        break''', '''            names = ident.names()
            if not names:
                rep["skipped"].append(("web", "no product name to search for"))
            else:
                results, ran = search_dorks(ident, fetch, search, delay_s=delay_s)
                ranked = [c for c in rank_results(ident, results) if c["score"] >= 3][:4]
                rep["tiers"].append({"tier": 3, "did": "web search (dork queries)", "queries": ran, "results": len(results), "candidates": [{k: c[k] for k in ("url", "score", "why")} for c in ranked]})
                got = 0
                for c in ranked:
                    if time.time() > deadline or got >= 2:
                        break
                    pages, sk = crawl(c["url"], fetch, robots, max_pages=max_pages, max_depth=max_depth, delay_s=delay_s, allow_local=allow_local_net, deadline=deadline)
                    rep["skipped"] += [(u, w) for u, w in sk]
                    if _ingest_pages(ix, key, pages, rep, reg, "web", ident.version, embed_small):
                        got += 1''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("dork discovery patched")
