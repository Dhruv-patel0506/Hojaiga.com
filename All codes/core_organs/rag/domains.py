"""
rag.domains -- the three MASTER DOMAINS above the five Sub-RAGs.

    desktop_app   a native Win32 / UWP / Electron application   (UIA trees, ribbons, child windows)
    website       a content / informational site                 (URL routes, landmarks, forms, scroll, banners)
    web_app       an interactive browser application             (stateful DOM + accessibility tree, modals, shortcuts)

The five stores (icons, UI graph, procedures / chunks, hotkeys / macros, recovery) are REUSED unchanged; a domain is a NAMESPACE on the app key, so every row of every store is partitioned with no schema change:

    desktop_app   key = slug of the name                    'obs_studio'
    website       key = 'web:<host>'                        'web:en.wikipedia.org'
    web_app       key = 'webapp:<host>'                     'webapp:excalidraw.com'

`domain_of(key)` reads the namespace (or the registry for anything older), `register` records a key's domain and how it was classified, `stats(rag)` counts rows per domain per store, and `classify` decides
the domain of ONE input -- an application name or a URL -- from evidence: an installed program wins; a page is a web_app when it behaves like one (framework shell, canvas, many interactive controls, a web
manifest / service worker) and a website when it is mostly article text with navigation. `Query.domain` (optional) makes retrieval refuse a key from another domain.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional

DESKTOP, WEBSITE, WEBAPP = "desktop_app", "website", "web_app"
DOMAINS = (DESKTOP, WEBSITE, WEBAPP)
PREFIX = {WEBSITE: "web:", WEBAPP: "webapp:"}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40]


def host_of(url: str) -> str:
    u = url if "://" in url else "https://" + url
    h = urllib.parse.urlparse(u).netloc.lower()
    return re.sub(r"^www\.", "", h.split("@")[-1].split(":")[0])


def key_for(domain: str, name_or_url: str) -> str:
    if domain == DESKTOP:
        return slug(name_or_url)
    return PREFIX[domain] + host_of(name_or_url)


def domain_of(app_key: str, registry: Optional[Dict[str, Any]] = None) -> str:
    if app_key.startswith(PREFIX[WEBAPP]):
        return WEBAPP
    if app_key.startswith(PREFIX[WEBSITE]):
        return WEBSITE
    if registry and app_key in registry:
        return registry[app_key].get("domain", DESKTOP)
    return DESKTOP


# ---------------------------------------------------------------------------------------------------------------------------------- registry (a small JSON next to the stores)
def _path(rag: Any) -> str:
    return os.path.join(rag.st.base, "domains.json")


def load(rag: Any) -> Dict[str, Any]:
    with contextlib.suppress(Exception):
        return json.load(open(_path(rag), encoding="utf-8"))
    return {}


def register(rag: Any, app_key: str, domain: str, evidence: Optional[Dict[str, Any]] = None) -> None:
    assert domain in DOMAINS, domain
    reg = load(rag)
    reg[app_key] = {"domain": domain, "evidence": evidence or {}}
    os.makedirs(os.path.dirname(_path(rag)), exist_ok=True)
    json.dump(reg, open(_path(rag), "w", encoding="utf-8"), indent=1, default=str)


def keys_of(rag: Any, domain: str) -> List[str]:
    reg = load(rag)
    return sorted(k for k in reg if domain_of(k, reg) == domain)


def stats(rag: Any) -> Dict[str, Dict[str, int]]:
    """Rows per domain per store: {domain: {apps, graph_nodes, graph_edges, procedures, chunks, hotkeys}} (counted through each store's own per-app query)."""
    reg = load(rag)
    out: Dict[str, Dict[str, int]] = {d: {"apps": 0, "graph_nodes": 0, "graph_edges": 0, "procedures": 0, "chunks": 0, "hotkeys": 0} for d in DOMAINS}
    for k in reg:
        d = domain_of(k, reg)
        out[d]["apps"] += 1
        with contextlib.suppress(Exception):
            gs = rag.graph.stats(k)
            out[d]["graph_nodes"] += int(gs.get("nodes", 0))
            out[d]["graph_edges"] += int(gs.get("edges", 0))
        with contextlib.suppress(Exception):
            ps = rag.proc.stats(k)
            out[d]["procedures"] += int(ps.get("procedures", 0))
            out[d]["chunks"] += int(ps.get("chunks", 0))
        with contextlib.suppress(Exception):
            out[d]["hotkeys"] += int(rag.fast.count(k))
    return out


# ---------------------------------------------------------------------------------------------------------------------------------- classification
URL_RX = re.compile(r"^(https?://)?([a-z0-9-]+\.)+[a-z]{2,}(/\S*)?$", re.I)


def looks_like_url(text: str) -> bool:
    return bool(URL_RX.match(text.strip())) and " " not in text.strip()


def page_features(html: str) -> Dict[str, Any]:
    """Evidence from a page's HTML: how interactive it is, whether it is a framework shell, how much of it is prose."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    body_text = soup.get_text(" ", strip=True)
    scripts = soup.find_all("script")
    interactive = len(soup.find_all(["button", "input", "select", "textarea"])) + len(soup.select("[role=button],[role=tab],[role=menuitem],[role=dialog],[role=textbox],[aria-haspopup]"))
    shell = bool(soup.select_one("#root,#app,#__next,#__nuxt,[ng-app],[data-reactroot],app-root")) and len(body_text) < 1500
    return {"text_chars": len(body_text), "scripts": len(scripts), "interactive": interactive, "canvas": len(soup.find_all("canvas")), "articles": len(soup.find_all(["article", "p"])), "framework_shell": shell,
            "manifest": bool(soup.find("link", rel=lambda r: r and "manifest" in r)), "forms": len(soup.find_all("form"))}


def classify_page(f: Dict[str, Any]) -> Dict[str, Any]:
    """web_app vs website from page features: a score of app-likeness (interactivity, shell, canvas, manifest, scripts vs prose)."""
    score = 0.0
    score += 2.0 if f["framework_shell"] else 0.0
    score += 1.5 if f["canvas"] else 0.0
    score += 1.0 if f["manifest"] else 0.0
    score += min(f["interactive"] / 25.0, 2.0)
    score += min(f["scripts"] / 40.0, 1.0)
    score -= min(f["text_chars"] / 6000.0, 2.0) + min(f["articles"] / 60.0, 1.0)
    return {"domain": WEBAPP if score >= 1.5 else WEBSITE, "score": round(score, 2), "features": f}


def classify(text: str, installed: Optional[Any] = None, fetch: Optional[Any] = None) -> Dict[str, Any]:
    """The domain of one input. `installed(name) -> bool` (default: the Start menu) and `fetch(url) -> html` (default: a polite HTTP GET) are injectable for tests."""
    t = text.strip()
    if looks_like_url(t):
        url = t if "://" in t else "https://" + t
        html = ""
        with contextlib.suppress(Exception):
            html = (fetch or _fetch)(url)
        if not html:
            return {"domain": WEBSITE, "url": url, "key": key_for(WEBSITE, url), "evidence": {"why": "page not readable: treated as a website"}}
        c = classify_page(page_features(html))
        return {"domain": c["domain"], "url": url, "key": key_for(c["domain"], url), "evidence": c}
    if (installed or _installed)(t):
        return {"domain": DESKTOP, "name": t, "key": key_for(DESKTOP, t), "evidence": {"why": "an installed program of that name"}}
    return {"domain": "", "name": t, "key": "", "evidence": {"why": "not installed and not a URL: a web search decides the address"}}


def _fetch(url: str) -> str:
    from core_organs.harvest import web_search_failover as W
    st, html = W.get(url)
    return html if st == 200 else ""


def _installed(name: str) -> bool:
    """A Start-menu entry of that name whose target program still exists."""
    from core_organs.harvest import catalogue as C
    low = name.lower()
    stale = C.stale_shortcuts()
    return any(a["name"].lower() == low and low not in stale for a in C.installed())
