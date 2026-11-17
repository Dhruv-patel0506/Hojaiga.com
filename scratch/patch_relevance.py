import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


# 1. winget: names compare with '+' and '#' kept ('Notepad++' is not 'Notepad')
rep('''    low = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    for ln in rows[1:]:
        parts = re.split(r"\\s{2,}", ln.strip())
        if len(parts) >= 2 and re.sub(r"[^a-z0-9]+", " ", parts[0].lower()).strip() == low:''', '''    norm = lambda t: re.sub(r"[^a-z0-9+#]+", " ", t.lower()).strip()
    low = norm(name)
    for ln in rows[1:]:
        parts = re.split(r"\\s{2,}", ln.strip())
        if len(parts) >= 2 and norm(parts[0]) == low:''')

# 2. repository pages that are never documentation
rep('SKIP_PATH_RX = re.compile(r"(login|logout|signin|sign-in|signup|account|cart|checkout|download|forum|community|blog|store|shop|pricing|careers|press|search)", re.I)',
    'SKIP_PATH_RX = re.compile(r"(login|logout|signin|sign-in|signup|account|cart|checkout|download|forum|community|blog|store|shop|pricing|careers|press|search|/issues|/pull/|/pulls|/commit|/blob/|/tree/|/releases|/tags|/actions|/discussions|/compare|/graphs|/security|/stargazers|/forks|/network|/labels|/milestones)", re.I)')

# 3. relevance gate
rep('''def _ingest_pages(ix: Any, key: str, pages: Sequence[Page], rep: Dict[str, Any], reg: Dict[str, Any], kind: str, version: str, embed_small: bool) -> int:
    n = 0
    for p in pages:''', '''_GENERIC = {"microsoft", "windows", "google", "desktop", "app", "application", "the", "for", "and", "software", "inc", "pro", "new", "free", "official", "classic"}


def distinctive_words(ident: AppIdentity) -> List[str]:
    out: List[str] = []
    for n in _clean_names(ident, 2):
        for w in re.findall(r"[a-z0-9+#]+", n.lower()):
            if len(w) > 2 and w not in _GENERIC and w not in out:
                out.append(w)
    return out


def relevant(page: Page, words: Sequence[str]) -> bool:
    """A page belongs to this application only if it NAMES it (title, URL or the first screenful of text). Keeps a crawl that wandered off - or a search hit for a namesake - out of the corpus."""
    if not words:
        return True
    head = (page.title + " " + page.url + " " + page.text[:2500]).lower()
    return any(re.search(r"(?<![a-z0-9+#])" + re.escape(w) + r"(?![a-z0-9+#])", head) for w in words)


def _ingest_pages(ix: Any, key: str, pages: Sequence[Page], rep: Dict[str, Any], reg: Dict[str, Any], kind: str, version: str, embed_small: bool, words: Sequence[str] = ()) -> int:
    n = 0
    for p in pages:
        if words and not relevant(p, words):
            rep["skipped"].append((p.url, "off-topic: the page never names the application"))
            continue''')
# callers pass the words
s = s.replace("if _ingest_pages(ix, key, pages, rep, reg, \"web\", ident.version, embed_small):", "if _ingest_pages(ix, key, pages, rep, reg, \"web\", ident.version, embed_small, distinctive_words(ident)):")
s = s.replace("n = _ingest_pages(ix, key, pages, rep, reg, \"user\", ident.version, embed_small)", "n = _ingest_pages(ix, key, pages, rep, reg, \"user\", ident.version, embed_small)")
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("relevance gate + winget exact names + repo page skips")
