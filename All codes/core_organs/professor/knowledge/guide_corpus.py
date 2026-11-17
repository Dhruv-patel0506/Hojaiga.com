"""
professor.knowledge.guide_corpus -- build the guide CORPUS: find the user guide of as many applications as possible, once, politely, from real sources only.

Nothing here is written by the Professor: every chunk in the corpus is text fetched from a vendor / project page or PDF, with its URL kept as the citation. Sources, in the order the finder tries them
(professor.knowledge.guide_finder): the install folder; winget's structured links (Documentation / Support / Homepage); the pages the vendor's own site links to as its docs; plain-language web
search (Bing's HTML page, DuckDuckGo's if it does not challenge; operator "dork" queries only through an endpoint that honours them); and the official documentation roots listed in the catalog
(each is fetched first and used only if it answers). What it will NOT do: solve or work around a bot challenge, fetch adult / gambling results, use manual-aggregator sites, ignore robots.txt.

  load_catalog()       the applications (data/app_catalog.json): name, scan key, tier, processes, company, official seeds
  build(...)           run the finder for each application, record the outcome in the app registry (history.apps) and in data/professor/guides/corpus_report.json
  report()             what was found for whom
  canonical_key(proc)  the catalog key for a process name (so a scan of chrome.exe finds the 'chrome' corpus)
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from .. import config as CFG
from . import guide_finder as GF, manual_rag as MR

CATALOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "app_catalog.json")
REPORT_PATH = os.path.join(GF.GUIDE_DIR, "corpus_report.json")


def load_catalog(path: Optional[str] = None) -> List[Dict[str, Any]]:
    try:
        with open(path or CATALOG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)["apps"]
    except Exception:
        return []


def canonical_key(process: str, catalog: Optional[List[Dict[str, Any]]] = None) -> str:
    p = (process or "").lower()
    for a in (catalog if catalog is not None else load_catalog()):
        if any(p == x.lower() for x in a.get("processes", [])):
            return a["key"]
    return ""


def find_app(name_or_key: str, catalog: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    q = (name_or_key or "").lower()
    for a in (catalog if catalog is not None else load_catalog()):
        if q in (a["key"].lower(), a["name"].lower()):
            return a
    for a in (catalog if catalog is not None else load_catalog()):
        if q and (q in a["name"].lower() or q in a["key"].lower()):
            return a
    return None


def _save_report(rep: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1, ensure_ascii=False, default=str)


def report() -> Dict[str, Any]:
    try:
        with open(REPORT_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"apps": [], "totals": {}}


def _chunks_of(ix: Any, key: str) -> int:
    try:
        return int(ix.db.execute("SELECT COALESCE(SUM(chunks),0) FROM docs WHERE app=?", (key,)).fetchone()[0])
    except Exception:
        return 0


def build(apps: Optional[Sequence[str]] = None, tiers: Optional[Sequence[int]] = None, force: bool = False, budget_per_app: float = 240.0, pages_tier: int = 120, pages_other: int = 25,
          delay_s: float = 0.4, history: Any = None, log: Callable[[str], None] = print, fetch: Optional[GF.Fetcher] = None, winget_runner: Optional[Callable[[List[str]], str]] = None,
          catalog: Optional[List[Dict[str, Any]]] = None, ix: Any = None, max_queries: int = 3, top_up: int = 0) -> Dict[str, Any]:
    """Find the guide of every selected application (all of them by default). Resumable: an application that already has documents is skipped unless force. Returns the report."""
    cat = catalog if catalog is not None else load_catalog()
    sel = [a for a in cat if (not apps or a["key"] in apps or a["name"] in apps) and (not tiers or a.get("tier", 0) in tiers)]
    own_ix = ix is None
    ix = ix or MR.ManualIndex()
    rep = report()
    done = {r["key"]: r for r in rep.get("apps", [])}
    t0 = time.time()
    for n, a in enumerate(sel, 1):
        key = a["key"]
        have = GF.indexed_docs(ix, key)
        if have and not force and not (top_up and have < top_up):
            log(f"[{n}/{len(sel)}] {a['name']}: already {have} document(s)")
            done[key] = {**done.get(key, {}), "key": key, "name": a["name"], "tier": a.get("tier", 0), "documents": have, "chunks": _chunks_of(ix, key), "skipped_because": "already indexed"}
            continue
        ident = GF.AppIdentity(app_key=key, product=a["name"], company=a.get("company", ""), process=(a.get("processes") or [""])[0])
        pages = pages_tier if a.get("tier", 0) else pages_other
        kw: Dict[str, Any] = {}
        if winget_runner is not None:
            kw["winget_runner"] = winget_runner
        r = GF.discover(ident, ix, web=True, fetch=fetch, budget_s=budget_per_app, force=force or bool(top_up and have < top_up), delay_s=delay_s, max_pages=pages, max_depth=2, embed_small=False, official=None, seeds=a.get("seeds", []),
                        max_queries=max_queries, want_docs=top_up, sources_wanted=(4 if top_up else 2), **kw)
        docs, chunks = GF.indexed_docs(ix, key), _chunks_of(ix, key)
        kinds = sorted({i["kind"] for i in r.get("ingested", [])})
        official = next((t for t in r.get("tiers", []) if t.get("did") == "official sources"), {})
        prov = next((q.get("provider") for t in r.get("tiers", []) if t.get("queries") for q in t["queries"] if q.get("provider")), "")
        done[key] = {"key": key, "name": a["name"], "tier": a.get("tier", 0), "documents": docs, "chunks": chunks, "kinds": kinds, "seconds": r.get("seconds"), "winget": official.get("winget"),
                     "official_found": len(official.get("found", [])), "search_provider": prov, "coverage": r.get("coverage"), "first_sources": [i["source"] for i in r.get("ingested", [])[:3]],
                     "skipped": len(r.get("skipped", [])), "error": r.get("error", "")}
        log(f"[{n}/{len(sel)}] {a['name']}: {docs} document(s), {chunks} chunk(s) via {kinds or 'nothing'} in {r.get('seconds')}s" + (f"  ERROR {r['error']}" if r.get("error") else ""))
        if history is not None:
            try:
                history.register_app(key, a["name"], "", "", a.get("tier", 0) or 0, guide_docs=docs, notes=f"guide corpus: {docs} docs, {chunks} chunks")
            except Exception:
                pass
        out = {"apps": list(done.values()), "blocked_providers": sorted(GF.BLOCKED_PROVIDERS), "seconds": round(time.time() - t0, 1)}
        out["totals"] = {"apps": len(out["apps"]), "with_guide": sum(1 for x in out["apps"] if x.get("documents")), "documents": sum(x.get("documents", 0) for x in out["apps"]),
                         "chunks": sum(x.get("chunks", 0) for x in out["apps"])}
        _save_report(out)
    out = {"apps": list(done.values()), "blocked_providers": sorted(GF.BLOCKED_PROVIDERS), "seconds": round(time.time() - t0, 1)}
    out["totals"] = {"apps": len(out["apps"]), "with_guide": sum(1 for x in out["apps"] if x.get("documents")), "documents": sum(x.get("documents", 0) for x in out["apps"]), "chunks": sum(x.get("chunks", 0) for x in out["apps"])}
    _save_report(out)
    if own_ix:
        ix.close()
    return out
