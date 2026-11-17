"""
Global App-Guide Extractor  (implements PART-2 "Autonomous Software Knowledge
Ingestion Agent" methodology)

Pipeline
--------
1. TARGET DISCOVERY  : Pull the complete Windows Package Manager (WinGet) community
   manifest registry from the microsoft/winget-pkgs GitHub repo via the Git Trees
   API. This yields the canonical [AppName] + [Publisher] + version + homepage /
   documentation URLs for tens of thousands of global software packages.

2. DOC-HUB RESOLUTION: For each app, resolve likely end-user documentation from
   the manifest (Documentation field, Homepage-derived docs/help/support subdomains).

3. DATA EXTRACTION   : Fetch each candidate URL, strip boilerplate (nav, cookie
   banners, ads, sidebars) and convert the main article to clean Markdown, keeping
   the original heading / ordered-list / button-step hierarchy.

4. PERSISTENCE       : Write one row per extracted guide into a single Excel
   workbook (one row per app + guide) AND archive the markdown to
   ./raw_app_guides/{Category}/{Vendor}_{AppName}/{TaskSlug}.md with YAML
   frontmatter, exactly as the spec requires.

5. VOLUME & RATE     : A resumable index tracker at ./raw_app_guides/index.json
   de-duplicates re-crawls and lets you scale the run across as many letters /
   apps as you want in successive passes.

Usage
-----
  python guide_extractor.py                      # full registry, bounded scrape
  python guide_extractor.py --letters a,b,c      # restrict discovery to letters
  python guide_extractor.py --max-apps 500       # cap processed apps
  python guide_extractor.py --no-scrape          # just build the registry sheet
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import hashlib
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup, NavigableString, Comment

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
except ImportError:  # pragma: no cover
    print("openpyxl is required: pip install openpyxl")
    raise

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GITHUB_API = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com/microsoft/winget-pkgs/master"
REPO = "microsoft/winget-pkgs"

OUTPUT_DIR = Path("./raw_app_guides")
INDEX_FILE = OUTPUT_DIR / "index.json"
EXCEL_FILE = Path("app_guides_master.xlsx")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

# Be polite + survive bot detectors.
SCRAPER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 GuideIngestionBot/1.0"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Content filters — target end-user guides, reject raw API/SDK/source docs.
SKIP_URL_PATTERNS = [
    r"/api/", r"/sdk/", r"/reference/", r"/source/", r"/raw/", r"\.git/",
    r"/issues(?:/|$|\?)", r"/pulls?(?:/|$|\?)", r"/releases", r"/blob/",
    r"/actions", r"/security", r"/compare", r"/discussions/new",
    r"developer\.mozilla", r"nodejs\.org/api",
]
# GitHub / site chrome that betrays a non-guide page (login walls, repo boilerplate).
GARBAGE_MARKERS = [
    "change the issues type filter", "new issue", "sign in", "sign up",
    "this account", "pull requests", "forks", "stars", "watching",
    "you must be signed in", "404", "page not found", "are you a robot",
    "enable javascript and cookies", "just a moment", "access denied",
]
GUIDE_HINT_TOKENS = [
    "how to", "guide", "getting started", "tutorial", "user manual",
    "documentation", "help", "walkthrough", "step",
]

# Destructive / boilerplate DOM to strip during cleaning.
STRIP_TAGS = [
    "script", "style", "noscript", "nav", "header", "footer", "aside",
    "form", "iframe", "svg", "button", "figcaption",
]
STRIP_CLASS_RE = re.compile(
    r"cookie|banner|advert|sidebar|nav-|navigation|menu-|footer|header|"
    r"related|comments|share|social|breadcrumb|newsletter|popup|modal",
    re.I,
)

HTTP_TIMEOUT = 15
MAX_MARKDOWN_CHARS = 20000
MIN_MARKDOWN_CHARS = 120  # too short -> probably a stub / JS shell page


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def xlsx_safe(value) -> str:
    """Strip control characters openpyxl rejects, and clamp to cell limit."""
    if value is None:
        return ""
    s = str(value)
    try:
        s = ILLEGAL_CHARACTERS_RE.sub("", s)
    except Exception:
        s = "".join(ch for ch in s if ord(ch) >= 0x20 or ch in "\n\t")
    if len(s) > 32000:
        s = s[:32000] + "\n...[truncated]"
    return s


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class AppRecord:
    app_name: str
    publisher: str = ""
    category: str = "Uncategorized"
    homepage: str = ""
    documentation: str = ""
    version: str = ""
    letter: str = ""
    # scratch fields populated during discovery / enrichment
    _files: list[str] = field(default_factory=list)
    _app_full: str = ""
    _pkg_name: str = ""

    def key(self) -> str:
        return f"{self.letter}::{self.app_name}".lower()


@dataclass
class GuideRow:
    app_name: str
    publisher: str
    category: str
    homepage: str
    docs_url: str
    guide_title: str
    guide_markdown: str
    source_url: str
    extraction_timestamp: str
    word_count: int
    status: str
    md_path: str = ""

    def to_sheet_row(self):
        return [
            self.app_name, self.publisher, self.category, self.homepage,
            self.docs_url, self.guide_title, self.guide_markdown,
            self.source_url, self.extraction_timestamp, self.word_count,
            self.status, self.md_path,
        ]


# ---------------------------------------------------------------------------
# 1. TARGET DISCOVERY — WinGet registry via GitHub Trees API
# ---------------------------------------------------------------------------

def gh_get(url: str, session: requests.Session) -> requests.Response:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    resp = session.get(url, headers=headers, timeout=60)
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        log("GitHub rate limit hit — sleeping 60s")
        time.sleep(60)
        return gh_get(url, session)
    return resp


def discover_winget_apps(letters: list[str], session: requests.Session) -> list[AppRecord]:
    """Walk the WinGet manifests tree and collect one AppRecord per package."""
    log("Resolving manifests tree SHA ...")
    ref = gh_get(f"{GITHUB_API}/repos/{REPO}/git/ref/heads/master", session)
    ref.raise_for_status()
    root_sha = ref.json()["object"]["sha"]

    root_tree = gh_get(f"{GITHUB_API}/repos/{REPO}/git/trees/{root_sha}", session)
    root_tree.raise_for_status()
    manifests_sha = None
    for item in root_tree.json()["tree"]:
        if item["path"] == "manifests":
            manifests_sha = item["sha"]
            break
    if not manifests_sha:
        raise RuntimeError("Could not find 'manifests' tree in winget-pkgs")

    apps: list[AppRecord] = []
    for letter in letters:
        letter = letter.strip().lower()
        if not letter:
            continue
        log(f"Listing manifests/{letter} tree ...")
        # resolve letter subtree sha
        q = gh_get(
            f"{GITHUB_API}/repos/{REPO}/git/trees/{manifests_sha}", session
        )
        q.raise_for_status()
        letter_sha = None
        for item in q.json()["tree"]:
            if item["path"].lower() == letter:
                letter_sha = item["sha"]
                break
        if not letter_sha:
            log(f"  no subtree for '{letter}'")
            continue

        # recursive tree for the letter -> paths like a/Adobe.../1.0/..._installer.yaml
        rec = gh_get(
            f"{GITHUB_API}/repos/{REPO}/git/trees/{letter_sha}?recursive=1",
            session,
        )
        rec.raise_for_status()
        payload = rec.json()
        truncated = payload.get("truncated", False)
        # Paths are relative to the letter subtree, format:
        #   {Publisher}/{AppName}/{Version}/{PackageId}.{type}.yaml
        # Map letter-qualified app dir -> {version -> [files]}
        app_versions: dict[str, dict[str, list[str]]] = {}
        for entry in payload["tree"]:
            if entry["type"] != "blob":
                continue
            parts = entry["path"].split("/")
            if len(parts) < 4:
                continue
            publisher_dir, app_name, version = parts[0], parts[1], parts[2]
            app_full = f"{letter}/{publisher_dir}/{app_name}"
            app_versions.setdefault(app_full, {}).setdefault(version, []).append(parts[-1])

        for app_full, ver_map in app_versions.items():
            # pick latest version by natural sort
            latest = sorted(ver_map.keys())[-1]
            files = ver_map[latest]
            # app_full = {letter}/{Publisher}/{AppName}
            segs = app_full.split("/")
            app_name = segs[2]
            rec_app = AppRecord(app_name=app_name, version=latest, letter=letter,
                                publisher=segs[1])
            rec_app._files = files  # type: ignore
            rec_app._app_full = app_full  # type: ignore
            apps.append(rec_app)

        log(f"  '{letter}': {len(app_versions)} packages" + (" (TRUNCATED)" if truncated else ""))

    log(f"Discovery complete: {len(apps)} packages across {len(letters)} letters.")
    return apps


# ---------------------------------------------------------------------------
# 2. Manifest enrichment — fetch installer+default-locale YAML from raw (free)
# ---------------------------------------------------------------------------

def fetch_manifest_fields(app: AppRecord, session: requests.Session) -> AppRecord:
    """Download the default+locale manifest YAMLs and populate publisher etc."""
    files = getattr(app, "_files", [])
    app_full = getattr(app, "_app_full", f"{app.letter}/{app.app_name}")
    for fname in files:
        low = fname.lower()
        url = f"{RAW_BASE}/manifests/{app_full}/{app.version}/{fname}"
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code != 200:
                continue
            doc = yaml.safe_load(resp.text) or {}
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        # winget has NO 'Homepage'/'Documentation'/'Category' fields; the real
        # URL fields live in the defaultLocale manifest.
        def pick(*keys):
            for k in keys:
                v = doc.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            return ""
        if not app.homepage:
            app.homepage = pick("PackageUrl", "Homepage", "PublisherUrl")
        if not app.documentation:
            app.documentation = pick(
                "Documentation", "PublisherSupportUrl", "ReleaseNotes", "PrivacyUrl"
            )
        if (not app.publisher) or app.publisher == app.app_name:
            app.publisher = pick("Publisher") or app.publisher
        # human-readable package name
        pname = pick("PackageName")
        if pname and ("installer" in low or "locale" in low):
            app._pkg_name = pname
    if getattr(app, "_pkg_name", ""):
        app.app_name = app._pkg_name  # type: ignore
    return app


# ---------------------------------------------------------------------------
# 3. DOC-HUB RESOLUTION — candidate guide URLs
# ---------------------------------------------------------------------------

def _github_repo_readme_urls(app: AppRecord) -> list[str]:
    """For a github.com/{owner}/{repo} reference, return the RAW README markdown
    URLs. GitHub's repo-root HTML lazy-loads the README via JS, so the static
    HTML only yields chrome; the raw markdown endpoint is the reliable guide."""
    urls: list[str] = []
    for cand in (app.documentation, app.homepage):
        if not cand:
            continue
        p = urlparse(cand)
        if p.netloc.lower() not in ("github.com", "www.github.com"):
            continue
        segs = [s for s in p.path.split("/") if s]
        if len(segs) < 2:
            continue
        owner, repo = segs[0], segs[1]
        for name in ("README.md", "readme.md", "README"):
            u = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{name}"
            if u not in urls:
                urls.append(u)
    return urls


def candidate_doc_urls(app: AppRecord) -> list[str]:
    # GitHub-hosted projects: the user guide is the README, not issues/releases.
    gh = _github_repo_readme_urls(app)
    if gh:
        return gh[:2]

    urls: list[str] = []
    if app.documentation:
        urls.append(app.documentation)
    if app.homepage:
        p = urlparse(app.homepage)
        host = p.netloc
        if host:
            scheme = p.scheme or "https"
            base = host.replace("www.", "")
            # docs / help / support subdomains + homepage itself
            for sub in ("docs", "help", "support"):
                urls.append(f"{scheme}://{sub}.{base}")
            urls.append(app.homepage)
    # de-dupe, keep order, drop non-guide paths
    seen, out = set(), []
    for u in urls:
        if u and u not in seen and not any(re.search(pat, u, re.I) for pat in SKIP_URL_PATTERNS):
            seen.add(u)
            out.append(u)
    return out[:3]  # cap crawl per app


# ---------------------------------------------------------------------------
# 4. SCRAPE + CLEAN to Markdown
# ---------------------------------------------------------------------------

def _is_probably_binary(ct: str) -> bool:
    return any(t in ct for t in ("image/", "octet-stream", "video/", "audio/"))


def scrape_page_to_markdown(url: str, session: requests.Session) -> tuple[str, str]:
    """Return (title, markdown). Raises on non-HTML / HTTP error."""
    resp = session.get(url, headers=SCRAPER_HEADERS, timeout=HTTP_TIMEOUT, allow_redirects=True)
    resp.raise_for_status()
    ct = resp.headers.get("Content-Type", "")

    # Raw markdown (e.g. GitHub README.md served as text/plain): use as-is.
    body = resp.text
    if url.endswith((".md", "/README", "/readme")) or (
        "markdown" in ct or ("html" not in ct and not body.lstrip().startswith("<"))
    ):
        first_heading = next((ln for ln in body.splitlines() if ln.strip().startswith("#")), "")
        title = first_heading.lstrip("# ").strip() or urlparse(url).path.strip("/")
        return title[:200] or "README", body.strip()

    if "html" not in ct and "text" not in ct:
        raise ValueError(f"not an HTML document ({ct})")

    soup = BeautifulSoup(resp.text, "lxml" if _has_lxml() else "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else urlparse(url).netloc

    # strip boilerplate
    for tag in soup(STRIP_TAGS):
        tag.decompose()
    for el in soup.find_all(class_=STRIP_CLASS_RE):
        el.decompose()
    for el in soup.find_all(id=STRIP_CLASS_RE):
        el.decompose()

    # choose the richest content container
    main = (
        soup.find("article")
        or soup.find("main")
        or soup.find(id=re.compile("content|main|article", re.I))
        or soup.find(class_=re.compile("content|main|article|post-body", re.I))
        or soup.body
        or soup
    )

    md = html_to_markdown(main)
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return title, md


_lxml_ok_cache: bool | None = None
def _has_lxml() -> bool:
    global _lxml_ok_cache
    if _lxml_ok_cache is None:
        try:
            import lxml  # noqa
            _lxml_ok_cache = True
        except Exception:
            _lxml_ok_cache = False
    return _lxml_ok_cache


def html_to_markdown(root) -> str:
    """Minimal recursive HTML->Markdown that preserves heading + list structure."""
    out: list[str] = []

    def walk(node, depth=0):
        if isinstance(node, Comment):
            return
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                out.append(text)
            return
        name = getattr(node, "name", None)
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(name[1])
            txt = node.get_text(" ", strip=True)
            if txt:
                out.append("\n" + "#" * level + " " + txt + "\n")
            return
        if name in ("p", "div", "section"):
            for child in node.children:
                walk(child, depth)
            out.append("\n")
            return
        if name == "li":
            txt = node.get_text(" ", strip=True)
            if txt:
                out.append(f"- {txt}")
            return
        if name in ("ul", "ol"):
            for child in node.find_all("li", recursive=False):
                walk(child, depth)
            out.append("\n")
            return
        if name == "a":
            txt = node.get_text(" ", strip=True)
            href = node.get("href", "")
            if txt and href:
                out.append(f"[{txt}]({urljoin('https://x', href)})")
            elif txt:
                out.append(txt)
            return
        if name == "br":
            out.append("\n")
            return
        # default: recurse
        for child in node.children:
            walk(child, depth)

    walk(root)
    text = " ".join(out)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return text.strip()


def is_guide_like(markdown: str) -> bool:
    hay = markdown.lower()
    return any(tok in hay for tok in GUIDE_HINT_TOKENS)


# Markers that strongly indicate a login wall / error / repo-chrome page
# rather than a genuine user guide.
_STRONG_GARBAGE = [
    "change the issues type filter", "you must be signed in",
    "are you a robot", "enable javascript and cookies", "just a moment",
    "page not found", "404", "sign in to your account",
    "new issue", "pull requests", "release notes are empty",
]


def _looks_like_garbage(markdown: str) -> bool:
    hay = (markdown or "").lower()
    hits = sum(1 for m in _STRONG_GARBAGE if m in hay)
    # A real guide may mention "issues" once; a chrome page trips many markers
    # while offering almost no substantive prose.
    return hits >= 2 and len(hay) < 4000


# ---------------------------------------------------------------------------
# Persistence — markdown files + index
# ---------------------------------------------------------------------------

def slugify(text: str, maxlen: int = 60) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text or "").strip("-").lower()
    return text[:maxlen] or hashlib.md5((text or "guide").encode()).hexdigest()[:12]


def safe_dir(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", text or "unknown")[:80] or "unknown"


def write_markdown_file(row: GuideRow) -> str:
    d = OUTPUT_DIR / safe_dir(row.category) / f"{safe_dir(row.publisher or 'unknown')}_{safe_dir(row.app_name)}"
    d.mkdir(parents=True, exist_ok=True)
    fname = slugify(row.guide_title or row.source_url) + ".md"
    path = d / fname
    fm = (
        "---\n"
        f'app_name: "{row.app_name}"\n'
        f'vendor: "{row.publisher}"\n'
        f'source_url: "{row.source_url}"\n'
        f'extraction_timestamp: "{row.extraction_timestamp}"\n'
        f'inferred_category: "{row.category}"\n'
        "---\n\n"
    )
    path.write_text(fm + row.guide_markdown, encoding="utf-8")
    return str(path)


def load_index() -> dict:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"apps_seen": {}, "guides": [], "last_run": ""}


def save_index(index: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    index["last_run"] = now_iso()
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=3), encoding="utf-8")


# ---------------------------------------------------------------------------
# 5. Excel export
# ---------------------------------------------------------------------------

SHEET_HEADERS = [
    "App Name", "Publisher", "Category", "Homepage", "Docs URL",
    "Guide Title", "Guide Markdown", "Source URL",
    "Extraction Timestamp", "Word Count", "Status", "MD Path",
]


def export_excel(rows: list[GuideRow], registry: list[AppRecord]) -> None:
    wb = Workbook()

    # --- Guides sheet
    ws = wb.active
    ws.title = "App_Guides"
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2F5597")
    ws.append(SHEET_HEADERS)
    for c in ws[1]:
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(vertical="center")

    for r in rows:
        ws.append([xlsx_safe(v) if not isinstance(v, int) else v for v in [
            r.app_name, r.publisher, r.category, r.homepage, r.docs_url,
            r.guide_title, r.guide_markdown, r.source_url, r.extraction_timestamp,
            r.word_count, r.status, r.md_path,
        ]])

    widths = [24, 20, 16, 32, 32, 32, 60, 40, 20, 10, 12, 40]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    # truncate huge markdown display but keep full file content; wrap title col
    for row_cells in ws.iter_rows(min_row=2):
        row_cells[6].alignment = Alignment(wrap_text=False, vertical="top")

    # --- Registry sheet (every discovered app, even ones with no scrapeable guide)
    ws2 = wb.create_sheet("Winget_Registry")
    ws2.append(["App Name", "Publisher", "Category", "Homepage", "Documentation", "Version", "Letter"])
    for c in ws2[1]:
        c.font = header_font
        c.fill = header_fill
    for a in registry:
        ws2.append([xlsx_safe(v) for v in [a.app_name, a.publisher, a.category, a.homepage, a.documentation, a.version, a.letter]])
    for i, w in enumerate([30, 22, 18, 36, 36, 14, 8], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    ws2.freeze_panes = "A2"

    wb.save(EXCEL_FILE)
    log(f"Excel written: {EXCEL_FILE.resolve()}")


# ---------------------------------------------------------------------------
# Rebuild the workbook from already-saved Markdown guides (no re-scraping).
# ---------------------------------------------------------------------------

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)


def _parse_md(path: Path) -> GuideRow | None:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    m = _FM_RE.match(raw)
    if m:
        fm_text, body = m.group(1), m.group(2)
        try:
            fm = yaml.safe_load(fm_text) or {}
        except Exception:
            fm = {}
    else:
        fm, body = {}, raw
    body = body.strip()
    wc = len(body.split())
    title = next((ln.lstrip("# ").strip() for ln in body.splitlines()
                  if ln.strip().startswith("#")), path.stem)
    return GuideRow(
        app_name=str(fm.get("app_name") or path.parent.name.split("_", 1)[-1]),
        publisher=str(fm.get("vendor") or path.parent.name.split("_", 1)[0]),
        category=str(fm.get("inferred_category") or path.parent.parent.name),
        homepage=str(fm.get("homepage") or fm.get("source_url") or ""),
        docs_url=str(fm.get("source_url") or ""),
        guide_title=title[:200],
        guide_markdown=body,
        source_url=str(fm.get("source_url") or ""),
        extraction_timestamp=str(fm.get("extraction_timestamp") or ""),
        word_count=wc,
        status="extracted",
        md_path=str(path),
    )


def rebuild_excel_from_md() -> int:
    md_files = sorted(OUTPUT_DIR.rglob("*.md"))
    log(f"Rebuilding workbook from {len(md_files)} saved guides ...")
    guide_rows: list[GuideRow] = []
    for p in md_files:
        row = _parse_md(p)
        if row and row.word_count >= MIN_MARKDOWN_CHARS:
            guide_rows.append(row)
    # registry derived from the same corpus (app/publisher/category/source)
    seen, registry = set(), []
    for r in guide_rows:
        k = (r.app_name.lower(), r.publisher.lower())
        if k not in seen:
            seen.add(k)
            registry.append(AppRecord(
                app_name=r.app_name, publisher=r.publisher, category=r.category,
                homepage=r.homepage, documentation=r.docs_url,
            ))
    log(f"Valid guide rows: {len(guide_rows)} | unique apps: {len(registry)}")
    export_excel(guide_rows, registry)
    # persist an index too so future runs de-dupe
    index = load_index()
    for r in registry:
        index["apps_seen"][r.key()] = {
            "name": r.app_name, "pub": r.publisher, "cat": r.category,
            "home": r.homepage, "docs": r.documentation, "ver": r.version,
        }
    save_index(index)
    return 0


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def process_app(app: AppRecord, session: requests.Session, index: dict) -> list[GuideRow]:
    results: list[GuideRow] = []
    cands = candidate_doc_urls(app)
    if not cands:
        results.append(GuideRow(
            app_name=app.app_name, publisher=app.publisher, category=app.category,
            homepage=app.homepage, docs_url="", guide_title="", guide_markdown="",
            source_url="", extraction_timestamp=now_iso(), word_count=0,
            status="no_doc_url",
        ))
        return results

    got_good = False
    for url in cands:
        try:
            title, md = scrape_page_to_markdown(url, session)
        except Exception as e:
            results.append(GuideRow(
                app_name=app.app_name, publisher=app.publisher, category=app.category,
                homepage=app.homepage, docs_url=app.documentation, guide_title="",
                guide_markdown="", source_url=url, extraction_timestamp=now_iso(),
                word_count=0, status=f"fetch_error: {type(e).__name__}",
            ))
            continue
        wc = len(md.split())
        if wc < MIN_MARKDOWN_CHARS:
            results.append(GuideRow(
                app_name=app.app_name, publisher=app.publisher, category=app.category,
                homepage=app.homepage, docs_url=app.documentation,
                guide_title=title[:200], guide_markdown=md[:2000], source_url=url,
                extraction_timestamp=now_iso(), word_count=wc, status="too_short",
            ))
            continue
        md = md[:MAX_MARKDOWN_CHARS]
        if _looks_like_garbage(md):
            results.append(GuideRow(
                app_name=app.app_name, publisher=app.publisher, category=app.category,
                homepage=app.homepage, docs_url=app.documentation or url,
                guide_title=title[:200], guide_markdown=md[:1500], source_url=url,
                extraction_timestamp=now_iso(), word_count=wc, status="filtered_boilerplate",
            ))
            continue
        row = GuideRow(
            app_name=app.app_name, publisher=app.publisher, category=app.category,
            homepage=app.homepage, docs_url=app.documentation or url,
            guide_title=title[:200], guide_markdown=md, source_url=url,
            extraction_timestamp=now_iso(), word_count=wc,
            status="extracted" if is_guide_like(md) else "extracted_weak",
        )
        row.md_path = write_markdown_file(row)
        results.append(row)
        got_good = True
        break  # one good guide per app is enough for the training corpus

    if not got_good and not any(r.status.startswith("extract") for r in results):
        # keep best-effort row already appended above
        pass
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="WinGet global app-guide extractor")
    default_letters = "abcdefghijklmnopqrstuvwxyz"
    ap.add_argument("--letters", default=default_letters,
                    help="comma list of manifest letters to discover (default all)")
    ap.add_argument("--max-apps", type=int, default=1000,
                    help="cap on apps to run doc-resolution + scraping for")
    ap.add_argument("--no-scrape", action="store_true",
                    help="only build the registry sheet (no web scraping)")
    ap.add_argument("--workers", type=int, default=8, help="thread pool size")
    ap.add_argument("--rebuild", action="store_true",
                    help="rebuild the Excel from saved raw_app_guides/*.md (no scraping)")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if args.rebuild:
        return rebuild_excel_from_md()

    letters = [l for l in args.letters.split(",") if l]
    session = requests.Session()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    index = load_index()

    log("=== STAGE 1: WinGet registry discovery ===")
    apps = discover_winget_apps(letters, session)

    log("=== STAGE 2: manifest enrichment (publisher/homepage/docs) ===")
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(fetch_manifest_fields, a, session): a for a in apps}
        done = 0
        for fut in as_completed(futures):
            a = futures[fut]
            try:
                fut.result()
            except Exception:
                pass
            done += 1
            if done % 200 == 0:
                log(f"  enriched {done}/{len(apps)}")

    # attach discovered apps to index (de-dupe by key)
    new_apps = [a for a in apps if a.key() not in index["apps_seen"]]
    for a in apps:
        index["apps_seen"][a.key()] = {
            "name": a.app_name, "pub": a.publisher, "cat": a.category,
            "home": a.homepage, "docs": a.documentation, "ver": a.version,
        }

    registry_rows = apps

    guide_rows: list[GuideRow] = []
    if not args.no_scrape:
        # prioritize apps that have a documentation/homepage url
        with_docs = [a for a in apps if a.documentation or a.homepage]
        todo = with_docs[: args.max_apps]
        log(f"=== STAGE 3/4: scraping guides for {len(todo)} apps (of {len(with_docs)} with doc urls) ===")
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(process_app, a, session, index): a for a in todo}
            done = 0
            for fut in as_completed(futures):
                a = futures[fut]
                try:
                    res = fut.result()
                    guide_rows.extend(res)
                except Exception as e:
                    log(f"  scrape failed {a.app_name}: {e}")
                done += 1
                if done % 25 == 0:
                    log(f"  scraped {done}/{len(todo)} apps | {len(guide_rows)} guide rows so far")

    log(f"=== STAGE 5: export ===")
    log(f"Total registry entries : {len(registry_rows)}")
    log(f"Extracted guide rows   : {sum(1 for g in guide_rows if g.status.startswith('extract'))}")
    export_excel(guide_rows, registry_rows)
    save_index(index)
    log("DONE.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted — index saved for resume.")
        sys.exit(130)
