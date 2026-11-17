import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


# crawl(): a topic filter that decides which pages are KEPT and EXPANDED
rep('''def crawl(start_url: str, fetch: Fetcher, robots: Optional[Robots] = None, max_pages: int = 40, max_depth: int = 2, delay_s: float = 0.5, allow_local: bool = False,
          deadline: Optional[float] = None, sleep: Callable[[float], None] = time.sleep) -> Tuple[List[Page], List[Tuple[str, str]]]:''', '''def crawl(start_url: str, fetch: Fetcher, robots: Optional[Robots] = None, max_pages: int = 40, max_depth: int = 2, delay_s: float = 0.5, allow_local: bool = False,
          deadline: Optional[float] = None, sleep: Callable[[float], None] = time.sleep, keep: Optional[Callable[[Page], bool]] = None, give_up_after: int = 10) -> Tuple[List[Page], List[Tuple[str, str]]]:''')
rep('''        title, text = page_text(body, ct)
        if len(text.split()) >= 15:
            pages.append(Page(final or url, title or url.rsplit("/", 1)[-1], text, depth, ct or "text/html"))
        else:
            skipped.append((url, "almost no text"))
        if depth < max_depth and ("html" in ct or ct == ""):''', '''        title, text = page_text(body, ct)
        pg = Page(final or url, title or url.rsplit("/", 1)[-1], text, depth, ct or "text/html")
        on_topic = True
        if len(text.split()) >= 15:
            if keep is not None and not keep(pg):                                  # a portal root links to every product it hosts: only pages that name THIS application are kept and followed
                on_topic = False
                misses += 1
                skipped.append((url, "off-topic page: not kept, links not followed"))
                if misses >= give_up_after and not pages:
                    skipped.append((start_url, f"abandoned: the first {misses} pages never named the application"))
                    break
            else:
                pages.append(pg)
        else:
            skipped.append((url, "almost no text"))
        if depth < max_depth and on_topic and ("html" in ct or ct == ""):''')
rep('''    pages: List[Page] = []
    skipped: List[Tuple[str, str]] = []
    first = True''', '''    pages: List[Page] = []
    skipped: List[Tuple[str, str]] = []
    misses = 0
    first = True''')
# seeds before generic portal links
rep('''out.append({"url": url, "title": "seed", "score": 7.0,''', '''out.append({"url": url, "title": "seed", "score": 8.0,''')
# discover(): pass the topic filter for sources that are not vetted by where they came from
rep('''                    pages, sk = crawl(c["url"], fetch, robots, max_pages=max_pages, max_depth=max_depth, delay_s=delay_s, allow_local=allow_local_net, deadline=deadline)
                    rep["skipped"] += [(u, w) for u, w in sk]
                    vetted = c.get("kind") in ("winget-docs", "seed")''', '''                    vetted = c.get("kind") in ("winget-docs", "seed")
                    words = () if vetted else distinctive_words(ident)
                    topic = (lambda pg, w=words: relevant(pg, w)) if words else None
                    pages, sk = crawl(c["url"], fetch, robots, max_pages=max_pages, max_depth=max_depth, delay_s=delay_s, allow_local=allow_local_net, deadline=deadline, keep=topic)
                    rep["skipped"] += [(u, w) for u, w in sk]''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("topic-aware crawl")
