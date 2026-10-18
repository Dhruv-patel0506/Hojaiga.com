"""
harvest.web_search_failover -- when YouTube says 429, the harvest does not wait: it searches the web.

An illustrated step-by-step page (official docs, Microsoft Learn, WikiHow, How-To Geek ...) already has what a transcript + keyframes would give after minutes of video download and speech recognition: numbered
steps with a screenshot under each. One page is ~1 second of work and gives several RAG procedure steps, the keyboard shortcuts the text names, and BEFORE / AFTER picture pairs (screenshot i -> screenshot i+1) whose
target control is found on the picture by the numbered-element scan, exactly like the video route.

Search chain with its own circuit breaker: DuckDuckGo (HTML) first, Bing (HTML) as the fallback; Google is deliberately NOT scraped (it answers an automated client with a CAPTCHA, and a CAPTCHA is not bypassed).
An engine that refuses (HTTP 429 / 202 / a challenge page) is left alone for `COOLDOWN_S`; the next engine is tried at once, no sleeping. Pages are fetched politely (robots.txt honoured, a pause between requests,
size caps). Nothing here sends anything about the person; no cookie is read.

Path A -- embedded clips: <video> / <source> (.mp4 .webm) and animated .gif walk-throughs, paired with the heading + paragraph above them as the transcript (no speech recognition needed).
Path B -- illustrated steps: <ol><li> or 'Step N' headings with <img>/<figure> -> RAG procedure + hotkeys + before/after pairs.

    python -m core_organs.harvest web --apps notepad,paint --minutes 20      # YouTube-independent batch with speed log
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import time
import urllib.parse
import urllib.robotparser
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .paths import harvest_dir

# Illustrated how-to / documentation sites that put a screenshot under each numbered step. DATA, not logic: the search is restricted to one host at a time (`site:`), and a page is kept only if its CONTENT
# is about the app and made of instructions (relevant()), so a host that has nothing on the app costs one search and yields nothing.
DOC_HOSTS = ("wikihow.com", "support.microsoft.com", "learn.microsoft.com", "howtogeek.com", "geeksforgeeks.org", "helpx.adobe.com", "support.apple.com", "docs.github.com")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 HojaigaResearch/1.0"
COOLDOWN_S = 1800.0
MIN_GAP_S = 1.2
MAX_PAGE_BYTES = 2_500_000
MAX_IMG_BYTES = 1_800_000
MAX_CLIP_BYTES = 8_000_000
_engine_down: Dict[str, float] = {}
_last_request = [0.0]
_robots: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
VIDEO_HOSTS_OK = ("archive.org", "wikimedia.org", "wikipedia.org", "learn.microsoft.com", "docs.microsoft.com", "github.com", "githubusercontent.com", "vimeo.com", "dailymotion.com")


# ------------------------------------------------------------------------------------------------------------------------------------ polite fetching
def _pause() -> None:
    gap = MIN_GAP_S - (time.time() - _last_request[0])
    if gap > 0:
        time.sleep(gap)
    _last_request[0] = time.time()


def allowed(url: str) -> bool:
    """robots.txt of the site, cached per host (a site that cannot be read is treated as allowing: robots.txt is advice about crawling pages, not a login)."""
    host = urllib.parse.urlparse(url).netloc
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            import requests
            r = requests.get(f"{urllib.parse.urlparse(url).scheme}://{host}/robots.txt", headers={"User-Agent": UA}, timeout=6)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            _robots[host] = rp
        except Exception:
            _robots[host] = None
    rp = _robots[host]
    return True if rp is None else rp.can_fetch(UA, url)


def get(url: str, binary: bool = False, max_bytes: int = MAX_PAGE_BYTES, timeout: float = 12.0, respect_robots: bool = True) -> Tuple[int, Any]:
    """(status, text | bytes). Status 0 = not fetched (robots, error). A response larger than max_bytes is cut."""
    import requests
    if respect_robots and not allowed(url):
        return 0, b"" if binary else ""
    _pause()
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en"}, timeout=timeout, stream=True)
        data = b""
        for chunk in r.iter_content(65536):
            data += chunk
            if len(data) > max_bytes:
                break
        return r.status_code, (data if binary else data.decode(r.encoding or "utf-8", errors="replace"))
    except Exception:
        return 0, b"" if binary else ""


# ------------------------------------------------------------------------------------------------------------------------------------ search with a circuit breaker per engine
def _clean_link(href: str) -> str:
    if "uddg=" in href:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        return urllib.parse.unquote(q.get("uddg", [""])[0])
    if href.startswith("//"):
        return "https:" + href
    return href


def _search_ddg(query: str) -> Tuple[int, List[Dict[str, str]]]:
    from bs4 import BeautifulSoup
    st, html = get("https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query}), respect_robots=False)
    if st != 200 or "anomaly" in html[:4000].lower() or "captcha" in html[:4000].lower():
        return st or 599, []
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select("a.result__a")[:12]:
        u = _clean_link(a.get("href", ""))
        if u.startswith("http"):
            out.append({"title": a.get_text(" ", strip=True)[:140], "url": u})
    return 200, out


def _search_bing(query: str) -> Tuple[int, List[Dict[str, str]]]:
    from bs4 import BeautifulSoup
    st, html = get("https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "setlang": "en"}), respect_robots=False)
    if st != 200 or "captcha" in html[:5000].lower():
        return st or 599, []
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select("li.b_algo h2 a")[:12]:
        u = _unwrap_bing(a.get("href", ""))
        if u.startswith("http") and "bing.com" not in urllib.parse.urlparse(u).netloc:
            out.append({"title": a.get_text(" ", strip=True)[:140], "url": u})
    return 200, out


def _unwrap_bing(href: str) -> str:
    """Bing result links are redirects (bing.com/ck/a?...&u=a1<base64url of the real address>): the real address is in `u`."""
    import base64
    href = href.replace("&amp;", "&")
    if "bing.com/ck/a" in href:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        u = (q.get("u") or [""])[0]
        if u.startswith("a1"):
            b = u[2:]
            with contextlib.suppress(Exception):
                return base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode("utf-8", errors="replace")
    return href


ENGINES = (("duckduckgo", _search_ddg), ("bing", _search_bing))


def search(query: str) -> Dict[str, Any]:
    """Results from the first engine that answers; an engine that refuses is marked down for COOLDOWN_S and the next one is tried AT ONCE (nothing sleeps)."""
    tried = []
    for name, fn in ENGINES:
        if _engine_down.get(name, 0) > time.time():
            tried.append((name, "cooling down"))
            continue
        st, res = fn(query)
        if st == 200 and res:
            return {"engine": name, "results": res, "tried": tried}
        tried.append((name, st))
        if st in (0, 202, 403, 429, 503, 599):
            _engine_down[name] = time.time() + COOLDOWN_S
    return {"engine": "", "results": [], "tried": tried}


# ------------------------------------------------------------------------------------------------------------------------------------ pages -> steps / clips
KEY_RX = re.compile(r"\b((?:Ctrl|Control|Alt|Shift|Win|Cmd|Command|Option)(?:\s*\+\s*[A-Za-z0-9]{1,6}|\s*\+\s*(?:Shift|Alt|Tab|Enter|Esc|Space|Del|F\d{1,2}))+|F\d{1,2})\b")
NAME_RX = [re.compile(r"[\"“]([^\"”]{2,40})[\"”]"), re.compile(r"\*\*([^*]{2,40})\*\*"), re.compile(r"‘([^’]{2,40})’")]
VERB_RX = re.compile(r"^(?:then\s+)?(?:click|select|choose|press|tap|open|go to|on the|in the|under|check|enable|turn on|double-click|right-click)\b", re.I)


def _text_of(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def _names_in(el) -> List[str]:
    """Control names a step mentions: bold / strong / kbd / ui-ish tags, quoted words."""
    names: List[str] = []
    for t in el.find_all(["b", "strong", "kbd", "em", "code", "span"], limit=24):
        cls = " ".join(t.get("class", [])).lower()
        if t.name in ("b", "strong", "kbd", "code") or "ui" in cls or "menu" in cls or "button" in cls:
            s = _text_of(t)
            if 2 <= len(s) <= 40 and not KEY_RX.fullmatch(s):
                names.append(s)
    txt = _text_of(el)
    for rx in NAME_RX:
        names += [m for m in rx.findall(txt) if 2 <= len(m) <= 40]
    seen, out = set(), []
    for n in names:
        k = n.lower()
        if k not in seen:
            seen.add(k)
            out.append(n)
    return out[:6]


def parse_steps(html: str, base_url: str) -> List[Dict[str, Any]]:
    """Ordered instruction steps with their pictures: every <ol><li>, and 'Step N' headings with the content until the next heading."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "nav", "footer", "aside", "form"]):
        t.decompose()
    steps: List[Dict[str, Any]] = []

    def add(text: str, scope) -> None:
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 12 or len(text) > 600:
            return
        imgs = []
        for im in scope.find_all("img", limit=4):
            src = im.get("data-src") or im.get("data-lazy-src") or im.get("src") or ""
            if not src or src.startswith("data:") or re.search(r"(logo|icon|avatar|sprite|badge|banner|ad[s_-])", src, re.I):
                continue
            imgs.append(urllib.parse.urljoin(base_url, src))
        steps.append({"text": text, "imgs": imgs, "keys": sorted({m if isinstance(m, str) else m[0] for m in KEY_RX.findall(text)})[:4], "names": _names_in(scope)})
    for ol in soup.find_all("ol"):
        lis = ol.find_all("li", recursive=False)
        if 2 <= len(lis) <= 40:
            for li in lis:
                add(_text_of(li), li)
    if len(steps) < 3:
        for h in soup.find_all(re.compile(r"^h[2-4]$")):
            if re.match(r"^\s*(step\s*\d+|\d+[.)])\b", _text_of(h), re.I):
                body, scope_parts = [], []
                for sib in h.find_next_siblings(limit=6):
                    if sib.name and re.match(r"^h[1-4]$", sib.name):
                        break
                    scope_parts.append(sib)
                    body.append(_text_of(sib))
                from bs4 import BeautifulSoup as BS
                box = BS("<div></div>", "lxml").div
                for sp in scope_parts:
                    box.append(sp.__copy__())
                add(_text_of(h) + " " + " ".join(body), box)
    return steps


def parse_clips(html: str, base_url: str) -> List[Dict[str, Any]]:
    """Embedded screen-recording clips (<video>, <source>, .mp4/.webm links, animated .gif) with the heading and paragraph above each as its transcript."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    out: List[Dict[str, Any]] = []
    cand = []
    for v in soup.find_all(["video", "source"]):
        src = v.get("src") or ""
        if src:
            cand.append((v, src))
    for a in soup.find_all("a", href=True):
        if re.search(r"\.(mp4|webm)(\?|$)", a["href"], re.I):
            cand.append((a, a["href"]))
    for im in soup.find_all("img", src=True):
        if re.search(r"\.gif(\?|$)", im["src"], re.I):
            cand.append((im, im["src"]))
    seen = set()
    for el, src in cand:
        url = urllib.parse.urljoin(base_url, src)
        if url in seen:
            continue
        seen.add(url)
        head = el.find_previous(re.compile(r"^h[1-4]$"))
        para = el.find_previous("p")
        text = " ".join(x for x in (_text_of(head) if head else "", _text_of(para) if para else "") if x)[:400]
        out.append({"url": url, "kind": "gif" if url.lower().split("?")[0].endswith(".gif") else "video", "text": text})
    return out


# ------------------------------------------------------------------------------------------------------------------------------------ pictures
def save_image(data: bytes, out_dir: str, min_w: int = 420, min_h: int = 240) -> Optional[str]:
    """Save an image as JPEG when it is big enough to be a screenshot; the path, or None."""
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        if im.size[0] < min_w or im.size[1] < min_h:
            return None
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, hashlib.sha1(data).hexdigest()[:14] + ".jpg")
        if not os.path.isfile(p):
            im.convert("RGB").save(p, "JPEG", quality=90)
        return p
    except Exception:
        return None


def ui_like(path: str) -> Tuple[bool, str]:
    """A cheap check that a picture is a software screenshot, not a photograph or a diagram: no face, enough edges (frame_prefilter) and enough numbered elements from the scanner."""
    from PIL import Image
    from . import frame_prefilter as FP
    try:
        im = Image.open(path).convert("RGB")
        ok, why = FP.looks_like_screencast(im)
        return bool(ok), why
    except Exception as exc:
        return False, f"unreadable: {type(exc).__name__}"


# ------------------------------------------------------------------------------------------------------------------------------------ harvesting one app
ACTION_RX = re.compile(r"\b(click|select|choose|press|tap|open|go to|type|enter|drag|check|enable|turn on|right-click|double-click|menu|button|tab|dialog|toolbar|ribbon)\b", re.I)


def relevant(html: str, steps: Sequence[Dict[str, Any]], app_name: str) -> bool:
    """A page is about THIS app and is made of instructions: the app's name (every word, any order) is in the title or the first part of the page, and most steps contain an instruction verb or a UI word.
    (MEASURED: a dictionary page for the word 'use' has an <ol> of 46 'steps'.)"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1 = " ".join(h.get_text(" ", strip=True) for h in soup.find_all("h1", limit=2))
    head = (title + " " + h1 + " " + soup.get_text(" ", strip=True)[:2500]).lower()
    words = [w for w in re.findall(r"[a-z0-9]+", app_name.lower()) if len(w) > 2]
    if not words or not all(w in head for w in words):
        return False
    hits = sum(1 for s in steps if ACTION_RX.search(s["text"]))
    return hits >= max(3, int(0.4 * len(steps)))


def _goal_of(step: Dict[str, Any]) -> str:
    t = step["text"]
    t = re.sub(r"^\s*(step\s*\d+[:.)-]?|\d+[.)])\s*", "", t, flags=re.I)
    first = re.split(r"(?<=[.!?])\s", t)[0]
    return first[:160].strip()


def pairs_from_steps(app_key: str, steps: Sequence[Dict[str, Any]], source_url: str, root: str, som_fn: Optional[Any] = None, max_pairs: int = 12) -> Dict[str, Any]:
    """Consecutive steps with pictures -> (before, after) pairs; the target control is the numbered element whose label matches a name the step mentions. Returns rows + counts (and why others were dropped)."""
    from . import video_explain as VE, video_pipeline as VP
    som_fn = som_fn or VP.som_of_frame
    rep = {"images": 0, "ui_like": 0, "grounded": 0, "no_target": 0, "not_ui": 0, "rows": []}
    out_dir = os.path.join(root, "frames", "web", app_key)
    shots: List[Tuple[Dict[str, Any], str]] = []
    for st in steps:
        if st.get("local_imgs"):                                             # a picture the browser rendered and the recorder captured from the page: no download, no image-server challenge
            rep["images"] += 1
            shots.append((st, st["local_imgs"][0]))
            continue
        for u in st["imgs"][:1]:
            code, data = get(u, binary=True, max_bytes=MAX_IMG_BYTES)
            p = save_image(data, out_dir) if code == 200 and data else None
            if p:
                rep["images"] += 1
                shots.append((st, p))
                break
    for i in range(len(shots) - 1):
        if len(rep["rows"]) >= max_pairs:
            break
        st, pre = shots[i]
        _nxt, post = shots[i + 1]
        ok, _why = ui_like(pre)
        if not ok:
            rep["not_ui"] += 1
            continue
        rep["ui_like"] += 1
        som = som_fn(pre)
        if len(som["elements"]) < 8:
            rep["not_ui"] += 1
            continue
        el = None
        for nm in st["names"]:
            el = VE.match_element(som, nm)
            if el:
                break
        if el is None:
            rep["no_target"] += 1
            continue
        goal = _goal_of(st)
        pair_id = hashlib.sha1(f"{app_key}|{goal}|{os.path.basename(pre)}".encode()).hexdigest()[:16]
        action = [{"step": 1, "action": "click", "target_id": el["id"], "hotkey": None, "text": None, "verify_expectation": "the screen changes as in the next step's picture"}]
        row = VE.build_row(root, app_key, "web_" + hashlib.sha1(source_url.encode()).hexdigest()[:8], {"t": float(i), "pre": pre, "post": post, "bbox": None}, som, goal, action, pair_id, True, True,
                           {"source": "web_steps", "source_ref": source_url, "ui_check": "frame_prefilter + numbered elements", "uia_name": el.get("label", "")})
        rep["rows"].append(row)
        rep["grounded"] += 1
    return rep


def feed_rag(rag: Any, app_key: str, app_name: str, steps: Sequence[Dict[str, Any]], url: str, title: str) -> Dict[str, int]:
    """Steps -> Sub-RAG 3 (procedure + chunks); key combos the text names -> Sub-RAG 4 (hotkeys, trust 'web')."""
    n = {"procedures": 0, "hotkeys": 0}
    if rag is None or not steps:
        return n
    with contextlib.suppress(Exception):
        r = rag.proc.ingest_procedure(app_key, (title or f"How to use {app_name}")[:160], [{"text": s["text"], "route_hint": "observe"} for s in steps[:25]], url, trust="web")
        n["procedures"] += r.inserted + r.updated
    with contextlib.suppress(Exception):
        from . import bridge as BR
        rows = []
        for s in steps:
            for k in s["keys"]:
                rows.append({"app_name": app_name, "app_key": app_key, "action": _goal_of(s)[:100], "shortcut": k, "source": "web_table", "url": url})
        if rows:
            r2 = BR.ingest_hotkeys(rag, rows)
            n["hotkeys"] += int(sum(v for v in r2.values() if isinstance(v, int))) if isinstance(r2, dict) else 0
    return n


def harvest_app(app_name: str, root: str = "", rag: Any = None, max_pages: int = 4, max_pairs: int = 12, write_pairs: bool = True, log: Any = None, with_clips: bool = True, with_open_video: bool = False, app_key: str = "") -> Dict[str, Any]:
    """One app through the web chain: search -> illustrated pages -> RAG + pairs; clips on pages that have them. Speed and counts are returned."""
    from . import free_master_harvester as M
    root = root or harvest_dir()[0]
    app_key = app_key or M.app_key_of(app_name)                          # a caller may file the knowledge under a domain key ('web:<host>' / 'webapp:<host>')
    t0 = time.time()
    rep: Dict[str, Any] = {"app": app_key, "pages": 0, "steps": 0, "procedures": 0, "hotkeys": 0, "images": 0, "pairs": 0, "clips_found": 0, "engine": "", "urls": []}
    queries = [f"{app_name} tutorial site:{h}" for h in DOC_HOSTS] + [f"{app_name} keyboard shortcuts"]
    seen_urls = set()
    if rag is None:
        with contextlib.suppress(Exception):
            from core_organs import rag as _R
            rag = _R.get_rag()
    out_rows: List[Dict[str, Any]] = []
    for q in queries:
        if rep["pages"] >= max_pages:
            break
        sr = search(q)
        rep["engine"] = rep["engine"] or sr["engine"]
        if not sr["results"]:
            rep.setdefault("search_failed", sr["tried"])
            continue
        for res in sr["results"]:
            u = res["url"]
            host = urllib.parse.urlparse(u).netloc
            if u in seen_urls or rep["pages"] >= max_pages or re.search(r"(youtube\.com|youtu\.be|pinterest|facebook|twitter|x\.com|reddit\.com|quora)", host):
                continue
            seen_urls.add(u)
            st, html = get(u)
            if st != 200 or not html:
                continue
            steps = parse_steps(html, u)
            clips = parse_clips(html, u)
            if len(steps) < 3 or not relevant(html, steps, app_name):
                continue
            rep["clips_found"] += len(clips)
            if clips and with_clips:                                         # Source A: the page's own screen recordings, with the text above each as its transcript
                with contextlib.suppress(Exception):
                    from . import multi_source_video as MS
                    cr = MS.harvest_page_clips(app_name, u, html, root, rag, max_clips=2)
                    rep["clip_pairs"] = rep.get("clip_pairs", 0) + cr["pairs"]
            rep["pages"] += 1
            rep["urls"].append(u)
            rep["steps"] += len(steps)
            fr = feed_rag(rag, app_key, app_name, steps, u, res["title"])
            rep["procedures"] += fr["procedures"]
            rep["hotkeys"] += fr["hotkeys"]
            if write_pairs and any(s["imgs"] for s in steps):
                pr = pairs_from_steps(app_key, steps, u, root, max_pairs=max_pairs)
                rep["images"] += pr["images"]
                out_rows += pr["rows"]
            if log:
                log(f"[web] {app_key}: {u[:80]} steps={len(steps)} imgs={rep['images']} pairs={len(out_rows)}")
    if with_open_video:                                                      # Source B: Internet Archive / Wikimedia Commons (official APIs)
        with contextlib.suppress(Exception):
            from . import multi_source_video as MS
            ov = MS.harvest_open_video(app_name, root, rag)
            rep["open_video"] = ov
            rep["clip_pairs"] = rep.get("clip_pairs", 0) + ov["pairs"]
    if out_rows:
        p = os.path.join(root, "training", "ui_training_dataset.jsonl")
        seen = set()
        if os.path.isfile(p):
            for line in open(p, encoding="utf-8"):
                with contextlib.suppress(Exception):
                    seen.add(json.loads(line)["meta"]["pair_id"])
        new = [r for r in out_rows if r["meta"]["pair_id"] not in seen]
        with open(p, "a", encoding="utf-8") as f:
            for r in new:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        rep["pairs"] = len(new)
    rep["seconds"] = round(time.time() - t0, 1)
    return rep


def web_failover_source(app_name: str, root: str) -> Dict[str, Any]:
    """The `static_source` the YouTube harvester calls on a 429: the older static tables first, then the web chain. {'ok': bool, ...}"""
    from . import free_master_harvester as M
    out: Dict[str, Any] = {"ok": False}
    with contextlib.suppress(Exception):
        out = dict(M._static_docs(app_name, root))
    r = harvest_app(app_name, root)
    out["web"] = {k: r[k] for k in ("pages", "steps", "procedures", "hotkeys", "pairs", "seconds")}
    out["ok"] = bool(out.get("ok")) or r["pages"] > 0
    return out


def run_batch(apps: Sequence[str], minutes: float = 20.0, log: Any = print) -> Dict[str, Any]:
    """A YouTube-independent batch over `apps` with an items-per-minute log."""
    root = harvest_dir()[0]
    t0 = time.time()
    tot = {"apps": 0, "pages": 0, "steps": 0, "procedures": 0, "hotkeys": 0, "pairs": 0}
    rows = []
    for a in apps:
        if time.time() - t0 > minutes * 60:
            break
        r = harvest_app(a, root, log=log, with_open_video=True)
        rows.append(r)
        tot["apps"] += 1
        for k in ("pages", "steps", "procedures", "hotkeys", "pairs"):
            tot[k] += r[k]
        mins = max((time.time() - t0) / 60.0, 1e-6)
        log(json.dumps({"app": r["app"], "pages": r["pages"], "steps": r["steps"], "procedures": r["procedures"], "pairs": r["pairs"], "seconds": r["seconds"], "steps_per_min": round(tot["steps"] / mins, 1), "pairs_per_min": round(tot["pairs"] / mins, 2)}))
    tot["seconds"] = round(time.time() - t0, 1)
    return {"totals": tot, "rows": rows}
