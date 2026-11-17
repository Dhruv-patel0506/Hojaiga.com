"""
professor.knowledge.guide_finder -- JUST-IN-TIME GUIDE RETRIEVAL: find the user guide of the application on screen, read it, index it, remember where it came from.

Nobody can pre-load "every guide in the world", and one giant file would be useless anyway. The guide is fetched ON DEMAND for the application actually in front of the learner, stored as
chunks (heading path + text + citation) in the per-application manual index (`manual_rag`), and never re-fetched while it is fresh.

TIERS (cheapest and safest first; each reports what it did and what it skipped):
  0 already indexed    the manual index already holds documents for this application -> nothing to do
  1 on this computer   the application's own install folder: Help / docs / manual folders and files named manual, user guide, handbook, getting started, readme ...
                       (pdf needs `pypdf`; chm is reported, not read)
  2 pages you name     explicit URLs from the user (`guide fetch --url ...`): that page and the pages linked under the same documentation path
  3 the web (OPT-IN)   only with HOJAIGA_GUIDE_WEB=1 (or an explicit flag): search for "<product> user guide", rank candidates (vendor domain, doc-looking path, manual-looking title;
                       social / video / shop sites rejected), crawl the best few politely
WEB POLICY (every rule is enforced in code and covered by tests): off by default; robots.txt honoured (unreachable robots = do not fetch); same host + documentation path prefix only;
page / depth / byte / time caps; a delay between requests; no private or loopback addresses; text / html / markdown / pdf only; every request appended to the fetch log
(data/professor/logs/guide_fetch.log); a user-controlled search endpoint (HOJAIGA_GUIDE_SEARCH_URL, e.g. a local SearXNG) replaces the default search page. Nothing is redistributed: only
chunks and their citations are kept on this computer.

HONESTY: a guide describes ONE version, in prose. It is a hypothesis source: what the Professor takes from it is checked against the live interface (professor.executor / skills) before it is
trusted. An application with no findable guide is reported as such and falls back to the archetype memory + probing.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import html
import io
import ipaddress
import json
import os
import re
import socket
import struct
import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, field, asdict
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .. import config as CFG
from . import manual_rag as MR

try:
    import requests
except Exception:                                                                       # pragma: no cover
    requests = None

GUIDE_DIR = os.path.join(CFG.DATA_DIR, "guides")
FETCH_LOG = os.path.join(CFG.LOG_DIR, "guide_fetch.log")
UA = "hojaiga-professor/1.0 (+local user-guide reader; honours robots.txt)"
UA_READER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
ROBOTS_TOKEN = "hojaiga-professor"
Fetcher = Callable[[str], Tuple[int, str, bytes, str]]                                    # url -> (status, content-type, body, final url)


# ================================================================================================================= identity
@dataclass
class AppIdentity:
    app_key: str = ""
    process: str = ""
    exe: str = ""
    product: str = ""
    company: str = ""
    version: str = ""
    description: str = ""
    title: str = ""

    def names(self) -> List[str]:
        """Distinct display names worth searching by, best first."""
        out: List[str] = []
        for n in (self.product, self.description, os.path.splitext(self.process)[0], self.app_key):
            n = re.sub(r"\s+", " ", (n or "").strip())
            if n and n.lower() not in [o.lower() for o in out] and len(n) > 2:
                out.append(n)
        return out


def version_info(path: str) -> Dict[str, str]:
    """ProductName / CompanyName / FileVersion / FileDescription / Comments from the executable's version resource (read-only, no execution)."""
    out: Dict[str, str] = {}
    try:
        ver = ctypes.WinDLL("version", use_last_error=True)
        ver.GetFileVersionInfoSizeW.argtypes = [wt.LPCWSTR, ctypes.c_void_p]
        ver.GetFileVersionInfoSizeW.restype = wt.DWORD
        ver.GetFileVersionInfoW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p]
        ver.VerQueryValueW.argtypes = [ctypes.c_void_p, wt.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.UINT)]
        size = ver.GetFileVersionInfoSizeW(path, None)
        if not size:
            return out
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(path, 0, size, buf):
            return out
        lp, n = ctypes.c_void_p(), wt.UINT()
        if not ver.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(lp), ctypes.byref(n)) or n.value < 4:
            return out
        lang, cp = struct.unpack("<HH", ctypes.string_at(lp.value, 4))
        for key in ("ProductName", "CompanyName", "FileVersion", "FileDescription", "Comments"):
            if ver.VerQueryValueW(buf, f"\\StringFileInfo\\{lang:04x}{cp:04x}\\{key}", ctypes.byref(lp), ctypes.byref(n)) and n.value:
                out[key] = ctypes.wstring_at(lp.value, n.value).rstrip("\0").strip()
    except Exception:
        pass
    return out


def identity_of(hwnd: int = 0, exe: str = "", app_key: str = "", title: str = "", process: str = "") -> AppIdentity:
    """Who is this application? From the window (process, executable, title) and the executable's version resource."""
    ident = AppIdentity(app_key=app_key, process=process, exe=exe, title=title)
    if hwnd:
        try:
            from ..capture import window_info
            wi = window_info(hwnd)
            ident.title = ident.title or wi.title
            ident.process = ident.process or wi.process
            if not ident.exe:
                import psutil
                ident.exe = psutil.Process(wi.pid).exe()
        except Exception:
            pass
    if ident.exe and os.path.isfile(ident.exe):
        vi = version_info(ident.exe)
        ident.product = vi.get("ProductName", "")
        ident.company = vi.get("CompanyName", "")
        ident.version = vi.get("FileVersion", "")
        ident.description = vi.get("FileDescription", "")
    if not ident.app_key:
        stem = os.path.splitext(ident.process)[0] or ident.title or ident.product or "app"
        try:                                                              # the SAME key a scan gives the application (one key per application everywhere)
            from core_organs.atlas import common as AC
            ident.app_key = AC.app_key_of(stem)
        except Exception:
            ident.app_key = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
        ident.app_key = ident.app_key or "app"
    return ident


# =============================================================================================================== tier 1: local
DOC_DIRS = {"help", "docs", "doc", "documentation", "manual", "manuals", "userguide", "user guide", "guide", "guides", "handbook", "readme", "tutorials", "user_guide", "user-guide"}
DOC_FILE_RX = re.compile(r"(manual|user[ _-]?guide|userguide|handbook|documentation|getting[ _-]?started|quick[ _-]?start|readme|help|tutorial|reference[ _-]?guide|how[ _-]?to)", re.I)
NOT_DOC_RX = re.compile(r"(licen[sc]e|eula|notice|third[ _-]?party|copying|changelog|change[ _-]?log|release[ _-]?notes|credits|authors|privacy|terms|uninstall|setup|install)", re.I)
DOC_EXT = {".pdf", ".html", ".htm", ".md", ".markdown", ".txt", ".docx", ".rst"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", "locales", "locale", "_internal", "site-packages", "lib", "plugins", "cache", "temp", "tmp"}
MAX_FILE_BYTES = 15 * 1024 * 1024


def shared_folder_reason(folder: str) -> str:
    """'' for an application's own folder; otherwise why it is NOT (Windows system folders, Program Files roots, a user's home, any folder holding dozens of programs)."""
    f = os.path.normcase(os.path.abspath(folder)).rstrip("\\/")
    shared = set()
    for var, subs in (("WINDIR", ("", "system32", "syswow64", "winsxs", "system")), ("SystemRoot", ("", "system32", "syswow64")), ("ProgramFiles", ("",)), ("ProgramFiles(x86)", ("",)),
                      ("ProgramW6432", ("",)), ("ProgramData", ("",)), ("USERPROFILE", ("", "downloads", "desktop", "documents")), ("LOCALAPPDATA", ("", "programs")), ("APPDATA", ("",))):
        base = os.environ.get(var)
        if base:
            for sub in subs:
                shared.add(os.path.normcase(os.path.abspath(os.path.join(base, sub))).rstrip("\\/"))
    if f in shared:
        return "a shared system / profile folder"
    try:
        n_exe = sum(1 for e in os.scandir(folder) if e.name.lower().endswith(".exe"))
    except OSError:
        n_exe = 0
    return f"a folder with {n_exe} executables" if n_exe > 60 else ""


def local_candidates(exe: str, max_depth: int = 3, max_files: int = 40, scan_s: float = 6.0) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Guide-looking files in the application's own install folder. Returns (candidates best-first, notes about what was skipped and why). Read-only."""
    notes: List[str] = []
    if not exe:
        return [], ["no executable path known"]
    root = os.path.dirname(os.path.abspath(exe))
    if not os.path.isdir(root):
        return [], [f"install folder not found: {root}"]
    shared = shared_folder_reason(root)
    if shared:
        return [], [f"{root} is {shared}: it holds many applications, so none of its files is THIS application's guide (a guide must come from a page you name, or the web if you enabled it)"]
    roots = [root]
    if os.path.basename(root).lower() in ("bin", "x64", "x86", "win64", "win32", "release", "app", "application", "program"):
        roots.append(os.path.dirname(root))                       # typical layouts keep Help beside bin\, never the shared parent of several apps
    t_end = time.time() + scan_s
    seen_dirs = 0
    cands: List[Dict[str, Any]] = []
    chm = 0
    for r in roots:
        stack: List[Tuple[str, int, bool]] = [(r, 0, False)]
        while stack and time.time() < t_end and seen_dirs < 3000:
            d, depth, in_doc = stack.pop()
            seen_dirs += 1
            try:
                it = list(os.scandir(d))
            except OSError:
                continue
            for e in it:
                name = e.name
                low = name.lower()
                try:
                    if e.is_dir(follow_symlinks=False):
                        if depth < max_depth and low not in SKIP_DIRS:
                            stack.append((e.path, depth + 1, in_doc or low in DOC_DIRS))
                        continue
                    ext = os.path.splitext(low)[1]
                    if ext == ".chm":
                        chm += 1
                        continue
                    if ext not in DOC_EXT or NOT_DOC_RX.search(low):
                        continue
                    manualish = bool(DOC_FILE_RX.search(low))
                    if not (in_doc or manualish):
                        continue
                    size = e.stat().st_size
                    if size < 200 or size > MAX_FILE_BYTES:
                        if size > MAX_FILE_BYTES:
                            notes.append(f"too large, skipped: {name} ({size // 1048576} MB)")
                        continue
                    score = (3 if re.search(r"manual|user[ _-]?guide|handbook", low) else 0) + (2 if in_doc else 0) + (1 if manualish else 0) + (1 if ext == ".pdf" else 0) - depth * 0.2
                    cands.append({"path": e.path, "name": name, "ext": ext, "size": size, "score": round(score, 2), "in_doc_dir": in_doc})
                except OSError:
                    continue
    if chm:
        notes.append(f"{chm} .chm help file(s) found but not read (compiled help needs an extractor; not enabled)")
    cands.sort(key=lambda c: (-c["score"], c["size"]))
    return cands[:max_files], notes


# ==================================================================================================================== web
SETTINGS_PATH = os.path.join(CFG.DATA_DIR, "settings.json")


def settings() -> Dict[str, Any]:
    """The person's standing decisions (data/professor/settings.json), e.g. {"guide_web": true, "guide_web_approved": "<when, by whom>"}. Missing file = every default off."""
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def web_enabled(explicit: Optional[bool] = None) -> bool:
    """Web retrieval is OFF unless asked for: an explicit flag, HOJAIGA_GUIDE_WEB=1/0, or the person's standing approval in settings.json. HOJAIGA_PROF_OFFLINE=1 always wins."""
    if CFG.OFFLINE:
        return False
    if explicit is not None:
        return bool(explicit)
    env = os.environ.get("HOJAIGA_GUIDE_WEB")
    if env in ("0", "1"):
        return env == "1"
    return bool(settings().get("guide_web"))


# ---- the official-sources allow list (the person's guard-rail: documentation hubs, the vendor's own domain, project wikis, PDF manuals on those hosts - never SEO pages)
OFFICIAL_HOST_RX = re.compile(r"(?i)^(?:support|learn|docs?|help|manual|manuals|kb|knowledge|developer|developers|wiki|guide|guides|documentation|userguide|community-docs)\.")
OFFICIAL_HOSTS = {"support.microsoft.com", "learn.microsoft.com", "docs.microsoft.com", "support.google.com", "developer.apple.com", "support.apple.com", "helpx.adobe.com", "docs.blender.org",
                  "manual.audacityteam.org", "docs.gimp.org", "wiki.documentfoundation.org", "help.libreoffice.org", "code.visualstudio.com", "obsproject.com", "support.discord.com",
                  "faq.whatsapp.com", "readthedocs.io", "readthedocs.org", "gitbook.io"}
CODE_HOSTS = {"github.com", "raw.githubusercontent.com", "gitlab.com"}


def allowed_host(url: str, vendor_domains: Sequence[str] = ()) -> Tuple[bool, str]:
    """May a guide be taken from this URL? Official documentation hubs, the vendor's own registrable domain(s), a project's wiki / docs folder on a code host, or a vendor organisation's
    raw files. (ok, why). Everything else (blogs, aggregators, SEO 'how-to' sites) is refused."""
    u = urllib.parse.urlsplit(url or "")
    host = (u.hostname or "").lower()
    if not host:
        return False, "no host"
    reg = registrable(host)
    if host in OFFICIAL_HOSTS or reg in OFFICIAL_HOSTS:
        return True, "official documentation hub"
    vend = {registrable(d.lower().lstrip(".")) for d in vendor_domains if d}
    if reg in vend:
        if OFFICIAL_HOST_RX.match(host) or _DOCISH_PATH.search(u.path.lower()) or u.path.lower().endswith(".pdf"):
            return True, "the vendor's own documentation (docs host / docs path / PDF)"
        return False, "the vendor's domain, but not a documentation page (account, store, home page)"
    if host in CODE_HOSTS or reg in CODE_HOSTS:
        p = u.path.lower()
        if "/wiki" in p or "/docs/" in p or "/doc/" in p or p.endswith((".md", ".pdf", ".xlsx")) or host == "raw.githubusercontent.com":
            return True, "a project's own wiki / docs on its code host"
        return False, "a code-host page that is not the project's wiki or docs"
    if OFFICIAL_HOST_RX.match(host) and any(registrable(host) == v for v in vend | {reg}):
        return True, "a documentation sub-domain"
    return False, "not an official documentation source (allow list)"


def _log_fetch(url: str, status: int, nbytes: int, note: str = "") -> None:
    try:
        os.makedirs(os.path.dirname(FETCH_LOG), exist_ok=True)
        with open(FETCH_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{status}\t{nbytes}\t{url}\t{note}\n")
    except OSError:
        pass


def public_url(url: str, allow_local: bool = False) -> Tuple[bool, str]:
    """http(s) only, and (unless a test says otherwise) never a loopback / private / link-local address."""
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return False, "malformed url"
    if u.scheme not in ("http", "https") or not u.hostname:
        return False, "not an http(s) url"
    if allow_local:
        return True, ""
    try:
        infos = socket.getaddrinfo(u.hostname, None)
    except OSError:
        return False, "host does not resolve"
    for inf in infos:
        ip = ipaddress.ip_address(inf[4][0])
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return False, "private / loopback address"
    return True, ""


PDF_MAX_BYTES = 12 * 1024 * 1024


def _fetch_once(url: str, ua: str, timeout: float, max_bytes: int, note: str = "") -> Tuple[int, str, bytes, str]:
    try:
        r = requests.get(url, headers={"User-Agent": ua, "Accept": "text/html,application/xhtml+xml,text/plain,text/markdown;q=0.9,application/pdf;q=0.8,application/json;q=0.5"},
                         timeout=timeout, stream=True, allow_redirects=True)
        body = b""
        for chunk in r.iter_content(65536):
            body += chunk
            if len(body) > max_bytes:
                break
        ct = r.headers.get("content-type", "").split(";")[0].strip().lower()
        _log_fetch(url, r.status_code, len(body), (note + " " if note else "") + ("truncated" if len(body) > max_bytes else "").strip())
        return r.status_code, ct, body[:max_bytes], r.url
    except Exception as exc:
        _log_fetch(url, 0, 0, type(exc).__name__)
        return 0, "", b"", url


def default_fetch(url: str, timeout: float = 15.0, max_bytes: int = 2_000_000) -> Tuple[int, str, bytes, str]:
    if requests is None:
        return 0, "", b"", url
    if urllib.parse.urlsplit(url).path.lower().endswith(".pdf"):
        max_bytes = max(max_bytes, PDF_MAX_BYTES)                  # a manual is a PDF of a few MB; a truncated PDF is unreadable, so it gets the larger cap
    status, ct, body, final = _fetch_once(url, UA, timeout, max_bytes)
    # HYBRID READER (measured): www.mathworks.com/help answers 403 to the declared agent and 200 in a browser on the same machine - the block is on HOW the request
    # introduces itself, not on whether the page is public. And www.videolan.org/robots.txt answers the declared agent 418 - a host TEAPOTTING the bot while it serves
    # its documentation to a reader: 418 is listed because it was measured, not guessed. So a refused page is asked ONCE more as an ordinary reader of this computer.
    # Nothing else changes: the same robots.txt rules decide what may be read (and with the reader identity VideoLAN's real rules become READABLE instead of unknown),
    # the allow list still decides which host may be read at all, and the fetch log records that the second identity was the one that got through.
    # Turn it off with HOJAIGA_FETCH_READER_UA=0.
    if status in (401, 403, 406, 418) and os.environ.get("HOJAIGA_FETCH_READER_UA", "1") != "0":
        s2, c2, b2, f2 = _fetch_once(url, UA_READER, timeout, max_bytes, note="reader-ua")
        if s2 == 200 and b2:
            return s2, c2, b2, f2
    return status, ct, body, final


class Robots:
    """robots.txt per host. A missing file (404/410) allows everything; a file that cannot be read (network error, 5xx) forbids everything - when in doubt, do not fetch."""

    def __init__(self, fetch: Fetcher):
        self.fetch = fetch
        self.cache: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}

    def allowed(self, url: str) -> bool:
        u = urllib.parse.urlsplit(url)
        key = f"{u.scheme}://{u.netloc}"
        if key not in self.cache:
            status, _ct, body, _fin = self.fetch(key + "/robots.txt")
            if status == 200:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(body.decode("utf-8", "replace").splitlines())
                self.cache[key] = rp
            elif status in (404, 410) or (400 <= status < 500 and status not in (429,)):
                self.cache[key] = None                     # no robots file -> no restrictions
            else:
                self.cache[key] = urllib.robotparser.RobotFileParser()
                self.cache[key].disallow_all = True        # type: ignore[attr-defined]
        rp = self.cache[key]
        return True if rp is None else rp.can_fetch(ROBOTS_TOKEN, url)


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: List[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self.hrefs.append(v)
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


BINARY_EXT = {".zip", ".exe", ".msi", ".dmg", ".pkg", ".iso", ".7z", ".rar", ".gz", ".tar", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".mp4", ".mov", ".avi", ".mp3", ".wav", ".css", ".js", ".ico", ".woff", ".woff2", ".ttf", ".xml", ".rss"}
SKIP_PATH_RX = re.compile(r"(login|logout|signin|sign-in|signup|account|cart|checkout|download|forum|community|blog|store|shop|pricing|careers|press|search|/issues|/pull/|/pulls|/commit|/blob/|/tree/|/releases|/tags|/actions|/discussions|/compare|/graphs|/security|/stargazers|/forks|/network|/labels|/milestones)", re.I)


@dataclass
class Page:
    url: str
    title: str
    text: str
    depth: int = 0
    content_type: str = "text/html"


def _pdf_text(body: bytes) -> str:
    try:
        import pypdf
    except Exception:
        return ""
    try:
        r = pypdf.PdfReader(io.BytesIO(body))
        return "\n".join((pg.extract_text() or "") for pg in r.pages[:400])
    except Exception:
        return ""


def page_text(body: bytes, content_type: str) -> Tuple[str, str]:
    """(title, text with markdown-style headings / numbered steps / **ui terms**) for a fetched page."""
    if "html" in content_type or content_type in ("", "application/xhtml+xml"):
        raw = body.decode("utf-8", "replace")
        lk = _Links()
        try:
            lk.feed(raw)
        except Exception:
            pass
        return re.sub(r"\s+", " ", lk.title).strip(), MR._html_to_text(raw)
    if content_type == "application/pdf":
        return "", _pdf_text(body)
    return "", body.decode("utf-8", "replace")


def crawl(start_url: str, fetch: Fetcher, robots: Optional[Robots] = None, max_pages: int = 40, max_depth: int = 2, delay_s: float = 0.5, allow_local: bool = False,
          deadline: Optional[float] = None, sleep: Callable[[float], None] = time.sleep, keep: Optional[Callable[[Page], bool]] = None, give_up_after: int = 10,
          scope: str = "") -> Tuple[List[Page], List[Tuple[str, str]]]:
    """Breadth-first over the documentation under `start_url`: same host, same path prefix (the start page's folder), allowed by robots.txt, text-like content only, capped in
    pages / depth / time. Returns (pages, skipped [(url, reason)])."""
    robots = robots or Robots(fetch)
    u0 = urllib.parse.urlsplit(start_url)
    prefix = u0.path if u0.path.endswith("/") else (u0.path.rsplit("/", 1)[0] + "/" if "/" in u0.path else "/")
    if scope and u0.path.startswith(scope):                                   # a portal keeps its articles beside, not under, the product's landing page (support.microsoft.com/office/...)
        prefix = scope
    queue: List[Tuple[str, int]] = [(start_url, 0)]
    seen = {start_url}
    pages: List[Page] = []
    skipped: List[Tuple[str, str]] = []
    misses = 0
    first = True
    while queue and len(pages) < max_pages:
        if deadline is not None and time.time() > deadline:
            skipped.append((queue[0][0], "time budget reached"))
            break
        url, depth = queue.pop(0)
        ok, why = public_url(url, allow_local)
        if not ok:
            skipped.append((url, why))
            continue
        if not robots.allowed(url):
            skipped.append((url, "disallowed by robots.txt"))
            continue
        if not first:
            sleep(delay_s)
        first = False
        status, ct, body, final = fetch(url)
        if status != 200 or not body:
            skipped.append((url, f"http {status}" if status else "no response"))
            continue
        fu = urllib.parse.urlsplit(final or url)
        if fu.netloc != u0.netloc:
            skipped.append((url, f"redirected to another host ({fu.netloc})"))
            continue
        textlike = ct in ("", "text/html", "application/xhtml+xml", "text/plain", "text/markdown", "text/x-markdown", "application/pdf")
        if not textlike:
            skipped.append((url, f"content type {ct}"))
            continue
        title, text = page_text(body, ct)
        pg = Page(final or url, title or url.rsplit("/", 1)[-1], text, depth, ct or "text/html")
        on_topic = True
        if len(text.split()) >= 15:
            if keep is not None and not keep(pg):                                  # a portal root links to every product it hosts: only pages that name THIS application are kept and followed
                on_topic = False
                misses += 1
                skipped.append((url, "off-topic page: not kept" + (", links not followed" if depth else "")))   # at depth 0 the links of a portal ARE still followed
                if misses >= give_up_after + 2 * len(pages):
                    skipped.append((start_url, f"abandoned: {misses} pages never named the application (a portal for many products?)"))
                    break
            else:
                pages.append(pg)
        else:
            skipped.append((url, "almost no text"))
        if depth < max_depth and (on_topic or depth == 0) and ("html" in ct or ct == ""):                 # a portal's own start page is always read for its links
            lk = _Links()
            try:
                lk.feed(body.decode("utf-8", "replace"))
            except Exception:
                pass
            for h in lk.hrefs:
                nxt = urllib.parse.urldefrag(urllib.parse.urljoin(final or url, h))[0]
                nu = urllib.parse.urlsplit(nxt)
                if nxt in seen or nu.netloc != u0.netloc or nu.scheme not in ("http", "https"):
                    continue
                if not nu.path.startswith(prefix) or os.path.splitext(nu.path.lower())[1] in BINARY_EXT or SKIP_PATH_RX.search(nu.path):
                    continue
                seen.add(nxt)
                queue.append((nxt, depth + 1))
    return pages, skipped


# ----------------------------------------------------------------------------------------------------------------- search
# app-store / extension-marketplace / download-aggregator listings describe a product to buyers; they are not its user guide (site CLASSES, matched by pattern)
_STORE_RX = re.compile(r"(^|\.)(store|stores|shop|play|appstore|apps|marketplace|addons|itunes|market|chromewebstore|sourceforge|chocolatey|softpedia)\.|/(webstore|marketplace|store)(/|$)|github\.com/marketplace", re.I)
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


# developer / API reference portals are not the GUI user's guide (a package manager's 'Documentation' link for a browser can point at one): hosts named developer(s) / dev / api, feature-status trackers
_DEV_RX = re.compile(r"^(developers?|dev|api|apis)\.|(^|\.)[a-z]*status\.", re.I)
# ... but the PAGES on such a host that INTRODUCE and TEACH the tool are its user guide: an IDE / editor / build tool lives nowhere else
# (measured: Android Studio kept an empty guide because its whole documentation, developer.<vendor>/studio/intro, was refused by HOST alone).
# So the class is decided by the PATH: a product's own documentation reads /intro /guides /tutorials /docs /help; a library reference reads /reference /api /javadoc.
_USERDOC_PATH_RX = re.compile(r"(^|/)(intro|start|getting[-_]?started|quick ?start|tutorials?|guides?|concepts|tasks|use[-_]?cases|user[-_]?guide|handbook|documentation|docs|help|overview|training)(/|$|\.)", re.I)
_APIREF_PATH_RX = re.compile(r"(^|/)(references?|api|apis|sdk|javadoc|jar|cmdline|cli|rest|plugins/reference|rls[-_])", re.I)


def not_a_user_guide(url: str) -> bool:
    """A store listing, a marketplace page or a developer-API portal: never an application's user guide."""
    sp = urllib.parse.urlsplit(url)
    host, path = (sp.hostname or "").lower(), (sp.path or "").lower()
    if _DEV_RX.search(host):
        return not (bool(_USERDOC_PATH_RX.search(path)) and not _APIREF_PATH_RX.search(path))
    return bool(_STORE_RX.search(host + path))


def unsafe_result(url: str, title: str) -> bool:
    """Adult / gambling results (a bot reading the web must never fetch them) and manual-aggregator sites."""
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return bool(_ADULT_RX.search(re.sub(r"[^a-z0-9]+", " ", host) + " " + (title or ""))) or any(a in host for a in _AGGREGATORS) or not_a_user_guide(url)


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
    if len(n.split()) == 1 and vend and vend[0].lower() not in n.lower():
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
        named = any(p in (title + " " + host + " " + path).lower() for p in prod) if prod else True
        if not named:
            score = min(score, 1.5)                                  # a 'user guide' of something else (YouTube TV help for a Notepad query) must not qualify
            why.append("never names the application")
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


def _ip_literal(host: str) -> bool:
    """True when the host name is a bare IP address (v4 or v6) rather than a DNS name."""
    h = (host or "").strip("[]").lower()
    if not h:
        return False
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def registrable(host: str) -> str:
    parts = (host or "").lower().split(".")
    if _ip_literal(host):                                                     # an IP address has no registrable domain: 'registrable("127.0.0.1")' must not answer '0.1' (measured: it invented https://help.0.1/)
        return (host or "").lower()
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
    norm = lambda t: re.sub(r"\s+", " ", t.strip().lower())
    low = norm(name)
    for ln in rows[1:]:
        parts = re.split(r"\s{2,}", ln.strip())
        if len(parts) >= 2 and norm(parts[0]) == low:
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


DOCS_HOST_PREFIXES = ("help", "docs", "developer", "support")


def host_sitemap_sources(urls: Sequence[str], fetch: Fetcher, robots: Robots, words: Sequence[str] = (), per_host: int = 12, cap: int = 60) -> List[Dict[str, Any]]:
    """THE HOST'S OWN TABLE OF CONTENTS - the door that needs no search engine.
    Measured twice over on the applications left with an empty guide: a documentation host can answer 200 at its root while the root is a portal shell with nothing followable in it
    (help.tableau.com: 3 KB of navigation, 0 usable links), and a general search engine can be ANSWERING WITHOUT ANSWERING (measured: Bing returned the same list for three different products
    and off-topic pages for a fourth - a soft block that no operator, no retry and no disguise may be worked around). The host itself still says where its pages are: robots.txt names a
    Sitemap and the sitemap lists the documents. So the index of the host THIS run already identified is read, with robots.txt honoured and nothing invented."""
    out: List[Dict[str, Any]] = []
    hosts: List[str] = []
    for u in urls:
        sp = urllib.parse.urlsplit(u or "")
        h = (sp.hostname or "").lower()
        if not h or _ip_literal(h) or registrable(h) in CODE_HOSTS or h in hosts:
            continue                                    # an address has no sitemap and a code-hosting platform is not the vendor: both were measured inventing requests a sandboxed run must not make
        hosts.append(h)
        # A DOCUMENTATION SUB-DOMAIN THAT NO LONGER EXISTS IS STILL THE ADDRESS A PERSON VOUCHED FOR. Measured: the VLC seed docs.videolan.org/vlc-user/ does not resolve at all
        # (status 0 - the host was retired), while its parent videolan.org answers a reader and names, in its own robots.txt, the index of 904 pages of which 14 are documentation.
        # So the registrable parent of a docs-prefixed host is asked too: a SUFFIX of the address the person wrote, never a name built from the vendor's spelling.
        if h.split(".")[0] in DOCS_HOST_PREFIXES and h.count(".") >= 2:
            par = registrable(h)
            if par != h and par not in hosts:
                hosts.append(par)
    low = {t for w in words for t in re.findall(r"[a-z0-9]+", str(w).lower())}

    def locs(body: bytes) -> List[str]:
        return [m.strip() for m in re.findall(r"<loc>\s*([^<\s]{10,400})\s*</loc>", body.decode("utf-8", "replace"))]

    for h in hosts[:6]:
        if len(out) >= cap:
            break
        base = "https://" + h
        maps: List[str] = []
        st, _ct, body, _f = fetch(base + "/robots.txt")
        if st == 200:
            maps += [m for m in re.findall(r"(?im)^\s*sitemap:\s*(\S+)", (body or b"").decode("utf-8", "replace")) if m.lower().startswith(("http://", "https://"))]
        for extra in (base + "/sitemap.xml", base + "/sitemap_index.xml"):
            if extra not in maps:
                maps.append(extra)
        got = 0
        for mp in maps[:4]:
            if not robots.allowed(mp):
                continue
            st2, _ct2, b2, _f2 = fetch(mp)
            if st2 != 200 or not b2:
                continue
            entries = locs(b2)
            kids = [e for e in entries if e.lower().endswith((".xml", ".xml.gz"))][:6]          # a sitemap INDEX: its children hold the pages
            pages = [e for e in entries if not e.lower().endswith((".xml", ".xml.gz"))]
            for kid in kids:
                if not robots.allowed(kid):
                    continue
                st3, _ct3, b3, _f3 = fetch(kid)
                if st3 == 200:
                    pages += [p for p in locs(b3 or b"") if not p.lower().endswith((".xml", ".xml.gz"))]
            for p in pages:
                ph = (urllib.parse.urlsplit(p).hostname or "").lower()
                if registrable(ph) != registrable(h) or not robots.allowed(p) or not_a_user_guide(p) or p in {c["url"] for c in out}:
                    continue                            # the same vendor domain (measured: videolan.org's own index points at its www sibling), robots, and still a user guide
                path = urllib.parse.urlsplit(p).path
                docish = bool(_DOCISH_PATH.search(path)) or bool(low & set(re.findall(r"[a-z0-9]+", path.lower())))
                if not docish:
                    continue
                out.append({"url": p, "title": "from the host's own index", "score": 6.5, "why": [f"listed in the sitemap {mp} of {h}"], "kind": "vendor-docs-sitemap", "scope": path.rsplit("/", 1)[0]})
                got += 1
                if got >= per_host:
                    break
            if got >= per_host:
                break
    return out


def docs_host_sources(urls: Sequence[str], fetch: Fetcher, robots: Robots) -> List[Dict[str, Any]]:
    """THE DOCUMENTATION HOST OF A VENDOR WHOSE WEB SITE REFUSES A READER.
    Measured on the applications left with an empty guide: the vendor's marketing domain answers 403 to any client that is not a browser (its front-door bot rules), while the host where its
    manual actually lives answers 200 to that same polite reader. Asking the marketing site again under a DISGUISED identity is not the fix and is not done here; asking the `help.` / `docs.`
    host of the vendor's OWN domain is, with robots.txt read first. The domains come from what the run already learned (winget's homepage/support, the seeds, a page the search ranked, the
    vendor's stated company name) - never from a table of application names."""
    out: List[Dict[str, Any]] = []
    doms, known = set(), set()
    for u in urls:
        if not u:
            continue
        host = urllib.parse.urlsplit(u).hostname or ""
        if _ip_literal(host):                          # an address is not a vendor domain: inventing 'help.0.1' from '127.0.0.1' was measured reaching outside a sandboxed test run
            continue
        r = registrable(host)
        if r and r not in CODE_HOSTS:                  # a code-hosting platform is not the vendor: its documentation is already looked for by the wiki tier
            doms.add(r)
        known.add(u.rstrip("/"))
    for d in sorted(doms):
        for cand in [f"https://{p}.{d}/" for p in DOCS_HOST_PREFIXES] + [f"https://{d}/docs", f"https://{d}/help", f"https://www.{d}/docs"]:
            if cand.rstrip("/") in known or not_a_user_guide(cand) or not robots.allowed(cand):
                continue
            status, _ct, body, _f = fetch(cand)
            if status == 200 and len(body) > 400:
                out.append({"url": cand, "title": "documentation host", "score": 7.0, "why": [f"the vendor's documentation host answers a plain reader although its web site does not ({d})"], "kind": "vendor-docs-host"})
                break
    return out


def official_sources(ident: AppIdentity, fetch: Fetcher, robots: Robots, winget: bool = True, seeds: Sequence[str] = (), runner: Callable[[List[str]], str] = _winget_run,
                     allow_local: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Official starting points for crawling, strongest first: winget 'Documentation' links, the pages the vendor's support / home page links to as its docs, then seeds that answer HTTP 200."""
    out: List[Dict[str, Any]] = []
    note: Dict[str, Any] = {}
    info: Dict[str, Any] = {}
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
    for sd in seeds:
        url = sd["url"] if isinstance(sd, dict) else sd
        status, _ct, body, _f = fetch(url)
        if status == 200 and body:
            ent = {"url": url, "title": "seed", "score": 8.0, "why": ["official documentation root (seed list, verified to answer)"], "kind": "seed"}
            if isinstance(sd, dict):
                ent.update({k: sd[k] for k in ("depth", "pages", "scope") if k in sd})
            out.append(ent)
    # ---- THE DOCUMENTATION HOST OF A VENDOR WHOSE WEB SITE REFUSES A READER (see docs_host_sources)
    out += docs_host_sources([c["url"] for c in out] + [info.get(k, "") for k in ("homepage", "support")] +
                             [sd["url"] if isinstance(sd, dict) else sd for sd in seeds] +
                             ([f"https://{re.sub(r'[^a-z0-9]', '', (ident.company or '').lower())}.com/"] if ident.company else []),
                             fetch, robots)
    seen, uniq = set(), []
    for c in sorted(out, key=lambda c: -c["score"]):
        if not_a_user_guide(c["url"]):
            continue
        if c["url"] not in seen:
            seen.add(c["url"])
            uniq.append(c)
    return uniq, note


# ================================================================================================================= registry
def registry_path(app_key: str) -> str:
    return os.path.join(GUIDE_DIR, re.sub(r"[^A-Za-z0-9_.-]+", "_", app_key or "app") + ".json")


def load_registry(app_key: str) -> Dict[str, Any]:
    try:
        with open(registry_path(app_key), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"app": app_key, "sources": [], "runs": []}


def save_registry(reg: Dict[str, Any]) -> str:
    os.makedirs(GUIDE_DIR, exist_ok=True)
    p = registry_path(reg.get("app", "app"))
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, indent=1, ensure_ascii=False, default=str)
    return p


def indexed_docs(ix: Any, app_key: str) -> int:
    try:
        return int(ix.db.execute("SELECT COUNT(*) FROM docs WHERE app=?", (app_key,)).fetchone()[0])
    except Exception:
        return 0


# ================================================================================================================== discover
def discover(ident: AppIdentity, ix: Any = None, web: Optional[bool] = None, user_urls: Sequence[str] = (), fetch: Optional[Fetcher] = None, budget_s: float = 120.0,
             force: bool = False, allow_local_net: bool = False, search: Optional[Callable[[str], List[Dict[str, str]]]] = None, delay_s: float = 0.6,
             max_pages: int = 40, max_depth: int = 2, embed_small: bool = True, official: Optional[bool] = None, seeds: Sequence[str] = (), max_queries: int = 5, sources_wanted: int = 2,
             winget_runner: Callable[[List[str]], str] = _winget_run, want_docs: int = 0) -> Dict[str, Any]:
    """Find, read and index the guide of `ident`. Returns a report {app, tiers:[{tier, did, ...}], ingested:[...], skipped:[...], web, coverage}. Never raises."""
    t0 = time.time()
    deadline = t0 + budget_s
    own_ix = ix is None
    ix = ix or MR.ManualIndex()
    key = ident.app_key
    reg = load_registry(key)
    rep: Dict[str, Any] = {"app": key, "identity": asdict(ident), "tiers": [], "ingested": [], "skipped": [], "web": "off", "coverage": "", "seconds": 0.0}
    fetch = fetch or default_fetch
    try:
        have = indexed_docs(ix, key)
        if have and not force:
            rep["tiers"].append({"tier": 0, "did": f"already indexed: {have} document(s)"})
            rep["coverage"] = f"{have} guide document(s) already indexed"
            return rep
        # ---- tier 1: this computer
        cands, notes = local_candidates(ident.exe)
        rep["skipped"] += [("local", n) for n in notes]
        t1 = {"tier": 1, "did": "install folder", "found": len(cands), "ingested": 0}
        for c in cands:
            if time.time() > deadline:
                rep["skipped"].append(("local", "time budget reached"))
                break
            if c["ext"] == ".pdf":
                try:
                    import pypdf  # noqa: F401
                except Exception:
                    rep["skipped"].append((c["name"], "pdf needs the optional `pypdf` package"))
                    continue
            r = ix.ingest_path(key, c["path"], embed=embed_small and c["size"] < 400_000)
            if r.get("ok") and r.get("chunks", 0) > 0:
                t1["ingested"] += 1
                rep["ingested"].append({"kind": "local", "source": c["path"], "chunks": r["chunks"]})
                reg["sources"].append({"kind": "local", "source": c["path"], "chunks": r["chunks"], "ts": time.time(), "app_version": ident.version, "match": "install folder"})
            else:
                rep["skipped"].append((c["name"], r.get("error", "no readable text")))
        rep["tiers"].append(t1)
        # ---- tier 2: pages the user named (explicit: allowed even when web search is off)
        robots = Robots(fetch)
        for url in user_urls:
            pages, sk = crawl(url, fetch, robots, max_pages=max_pages, max_depth=max_depth, delay_s=delay_s, allow_local=allow_local_net, deadline=deadline)
            rep["skipped"] += [(u, w) for u, w in sk]
            n = _ingest_pages(ix, key, pages, rep, reg, "user", ident.version, embed_small)
            rep["tiers"].append({"tier": 2, "did": "user-named page", "url": url, "pages": len(pages), "ingested": n})
        # ---- tier 3: the web (opt-in): official sources first (winget, the vendor's own links, verified seeds), then search
        if web_enabled(web) and (not indexed_docs(ix, key) or (want_docs and indexed_docs(ix, key) < want_docs)):          # top-up: an application with only a handful of documents gets more
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
                # the search found the vendor's shop window; its manual is on the documentation host of the SAME domain (403 vs 200, measured)
                pool += docs_host_sources([c["url"] for c in pool], fetch, robots)
                # the host's own index, read before any search engine is asked (a portal root has no followable links, and a search provider may answer without answering: both measured)
                # HYBRID: the hosts asked include the seeds A PERSON VOUCHED FOR even when the page they named did not answer - measured on the empty-guide applications,
                # getsharex.com/docs is a dead 404 and www.mathworks.com/help refused the reader, yet a host whose page died still publishes the index of the pages it has.
                seed_urls = [(s["url"] if isinstance(s, dict) else str(s)) for s in seeds]
                smap = host_sitemap_sources([c["url"] for c in pool] + seed_urls, fetch, robots, words=distinctive_words(ident))
                pool += smap
                rep["tiers"].append({"tier": 3, "did": "host index (sitemap)", "found": len(smap),
                                     "candidates": [{k: c[k] for k in ("url", "kind")} for c in smap][:8]})
                # A DOCUMENTATION HOST WHOSE DOOR CANNOT BE CRAWLED IS STILL SEARCHABLE INSIDE. Measured on the applications left with an empty guide: help.autodesk.com and help.tableau.com
                # answer a plain reader 200, but their root is a portal shell (7 KB / 3 KB of navigation, no followable links), while the manual lives DEEPER on that same host
                # (help.tableau.com/current/pro/desktop/en-us/default.htm answers 30 KB of real text). So the search engine is asked for pages ON the host this run just identified - a host
                # learned from winget / the vendor's own links / a ranked page, never from a table of application names. HYBRID by provider (measured): an endpoint that honours operators (a
                # search function of the caller's, or HOJAIGA_GUIDE_SEARCH_URL) gets `site:<host>`; Bing / DuckDuckGo read `site:` as words, so there the host goes into the query as a keyword.
                in_pool = {c.get("url") for c in pool}
                ops_ok = bool(search) or bool(os.environ.get("HOJAIGA_GUIDE_SEARCH_URL"))
                hosts = sorted({(urllib.parse.urlsplit(str(c.get("url", ""))).netloc or "").lower().split(":")[0] for c in pool
                                if c.get("kind") in ("vendor-docs-host", "winget-docs", "vendor-docs")} - {""})
                hits: List[Dict[str, Any]] = []
                for h in hosts[:3]:
                    if time.time() > deadline:
                        break
                    q = f'site:{h} "{names[0]}" manual' if ops_ok else f'"{names[0]}" manual {h}'
                    try:
                        res = (search(q) if search else search_web(q, fetch, 6)) or []
                    except Exception:                                                # noqa: BLE001
                        res = []
                    on_host = [r for r in res if str(r.get("url", "")).lower().startswith(("http://", "https://"))
                               and (urllib.parse.urlsplit(r["url"]).netloc or "").lower().split(":")[0].endswith(h) and r["url"] not in in_pool]
                    on_host = [dict(r, kind="docs-host-search") for r in on_host if not unsafe_result(r.get("url", ""), r.get("title", ""))]
                    hits += on_host
                    in_pool |= {r["url"] for r in on_host}
                    rep["tiers"].append({"tier": 3, "did": f"host search ({h})", "query": q, "operators": ops_ok, "results": len(res), "kept": len(on_host),
                                         "provider": "custom-function" if search else LAST_PROVIDER})
                    time.sleep(delay_s)
                pool += hits
                vendor_domains = _vendor_domains(pool)
                strict = settings().get("guide_web_strict", True) and not allow_local_net
                for c in pool:
                    if time.time() > deadline or (got >= sources_wanted and c.get("kind") != "seed"):
                        break
                    if c["url"] in tried:
                        continue
                    tried.add(c["url"])
                    vetted = c.get("kind") in ("winget-docs", "seed")
                    if strict and not vetted:
                        okh, whyh = allowed_host(c["url"], vendor_domains)
                        if not okh:
                            rep["skipped"].append((c["url"], "allow list: " + whyh))
                            continue
                    words = () if vetted else distinctive_words(ident)
                    portal = is_portal_root(c["url"])                                                # a site ROOT cannot be scoped by path: there, only pages that name the application are kept
                    topic = (lambda pg, w=words: relevant(pg, w)) if (words and portal) else None
                    pages, sk = crawl(c["url"], fetch, robots, max_pages=int(c.get("pages", max_pages)), max_depth=int(c.get("depth", max_depth)), delay_s=delay_s, allow_local=allow_local_net,
                                      deadline=deadline, keep=topic, scope=c.get("scope", ""))
                    rep["skipped"] += [(u, w) for u, w in sk]                              # vetted by where it came from (the package catalogue / an official root that answered)
                    if _ingest_pages(ix, key, pages, rep, reg, "web", ident.version, embed_small, () if vetted else distinctive_words(ident)):
                        got += 1
        n_docs = indexed_docs(ix, key)
        rep["coverage"] = (f"guide indexed: {n_docs} document(s) from {sorted({i['kind'] for i in rep['ingested']}) or ['earlier runs']}" if n_docs else
                           "NO guide found (install folder empty" + (", web search found nothing usable" if rep["web"] == "on" else ", web search is off") + ") -> the Professor falls back to the archetype memory + probing")
        reg["runs"].append({"ts": time.time(), "tiers": rep["tiers"], "coverage": rep["coverage"]})
        reg["identity"] = asdict(ident)
        save_registry(reg)
        return rep
    except Exception as exc:                                                                 # never break a lesson because a guide could not be found
        rep["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return rep
    finally:
        rep["seconds"] = round(time.time() - t0, 2)
        if own_ix:
            ix.close()


_GENERIC = {"microsoft", "windows", "google", "desktop", "app", "application", "the", "for", "and", "software", "inc", "pro", "new", "free", "official", "classic"}


_LOCALE_SEG = re.compile(r"^(hc|en|latest|stable|current|home|index\.html?|[a-z]{2}([-_][a-z]{2,4})?)$", re.I)


def is_portal_root(url: str) -> bool:
    """A site root (or a bare locale root such as /en-us, /hc/en-us): its path names no product, so a crawl from it can wander into every product the site hosts."""
    segs = [x for x in urllib.parse.urlsplit(url).path.split("/") if x]
    return all(_LOCALE_SEG.match(x) for x in segs)


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


def _vendor_domains(pool: Sequence[Dict[str, Any]]) -> List[str]:
    """The vendor's own domains, as the package catalogue / verified seeds name them (their hosts are trusted; search results are not)."""
    out: List[str] = []
    for c in pool:
        if c.get("kind") in ("winget-docs", "seed") or str(c.get("kind", "")).startswith("winget-"):
            h = urllib.parse.urlsplit(c.get("url", "")).hostname or ""
            if h and registrable(h) not in out:
                out.append(registrable(h))
    return out


def _ingest_pages(ix: Any, key: str, pages: Sequence[Page], rep: Dict[str, Any], reg: Dict[str, Any], kind: str, version: str, embed_small: bool, words: Sequence[str] = ()) -> int:
    from . import version_fit as VF
    n = 0
    if words and pages and not relevant(pages[0], words):                       # the SOURCE must name the application (its start page); its sub-pages need not repeat the name
        rep["skipped"].append((pages[0].url, f"off-topic source: its start page never names the application ({', '.join(words[:3])}); {len(pages)} page(s) dropped"))
        return 0
    installed = VF.Installed.from_identity(rep.get("identity") or {})
    for p in pages:
        fit = VF.document_fit(p.title + "\n" + p.text[:6000], installed)
        if fit["fit"] == "other_platform":                                       # a page only about the Mac / phone / web edition: not this application
            rep["skipped"].append((p.url, "version check: " + fit["why"]))
            continue
        q = VF.procedural_quality(p.text)
        if q["score"] < 0.08 and len(p.text) > 400:
            rep["skipped"].append((p.url, f"quality gate: {q['why']}"))
            continue
        r = ix.ingest_text(key, p.title, p.text, p.url, "html" if "html" in p.content_type else "md", embed=embed_small and len(p.text) < 20000)
        if r.get("ok") and r.get("chunks", 0) > 0:
            n += 1
            rep["ingested"].append({"kind": kind, "source": p.url, "chunks": r["chunks"], "fit": fit["fit"]})
            reg["sources"].append({"kind": kind, "source": p.url, "title": p.title, "chunks": r["chunks"], "ts": time.time(), "app_version": version, "match": fit["fit"] + (": " + fit["why"] if fit["why"] else "")})
    return n


def status(app_key: str, ix: Any = None) -> Dict[str, Any]:
    reg = load_registry(app_key)
    close = False
    if ix is None:
        ix = MR.index()
    n = indexed_docs(ix, app_key) if ix is not None else 0
    return {"app": app_key, "documents": n, "sources": reg.get("sources", [])[-12:], "last_run": (reg.get("runs") or [{}])[-1], "web_enabled": web_enabled(None), "fetch_log": FETCH_LOG}
