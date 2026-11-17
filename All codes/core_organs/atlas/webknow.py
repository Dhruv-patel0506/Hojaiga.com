"""
atlas.webknow -- PUBLIC knowledge about an application, from free sources that need no key and no account.

    Wikidata    structured facts: what kind of software, written in (languages), operating systems, licence, developer,
                official website, SOURCE REPOSITORY (P1324), latest version
    Wikipedia   plain-text article (what it is, what it does, history, architecture notes)
    GitHub      repository metadata, the language breakdown, README, the file tree (module layout), and a handful of key files
                fetched raw: documentation pages, keymap / shortcut tables, plugin lists, build files

Properties:
  * KEYLESS. Only anonymous public endpoints; the GitHub rate limit (60/h) is respected (a 403/429 stops GitHub for the session).
  * CACHED. Every document is stored under data/atlas/webcache with its URL, hash and time (table atlas_docs), so a second
    run is offline and byte-identical. HOJAIGA_ATLAS_OFFLINE=1 serves the cache only.
  * HONEST. Anything fetched is 'published' trust (below anything a probe measured or a program file states). Every claim carries the
    URL and, for text, the exact quote. Failures are reported in the result, never hidden.
  * NAME-ONLY WORKS. An application that is not installed (or only known by name) still gets its public knowledge.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from . import common as C

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

TTL_DEFAULT = 7 * 86400
_STATE = {"github_blocked": False, "requests": 0, "cache_hits": 0, "errors": []}
CACHE_ONLY = False                      # set by the instant tier: serve the cache, never touch the network
SOFTWARE_WORDS = re.compile(r"software|application|program|editor|player|suite|tool|engine|browser|ide\b|dj|daw|workstation|recorder|streaming|modeller|modeler|renderer|package|app\b|game|processor|spreadsheet|presentation|client|framework|library|compiler|emulator|manager|viewer|tracker|simulator|mixer|sequencer|synth|platform|operating system|ide|environment|utility", re.I)


# --------------------------------------------------------------------------------------------------
# cached HTTP
# --------------------------------------------------------------------------------------------------

def _cache_file(url: str) -> str:
    return os.path.join(C.ensure_dir(C.WEB_CACHE_DIR), C.sha(url, 20) + ".txt")


def get(url: str, *, kind: str = "doc", app_key: str = "", ttl: float = TTL_DEFAULT, headers: Optional[Dict[str, str]] = None,
        max_bytes: int = 1_500_000, timeout: float = 12.0, store: Optional[C.AtlasStore] = None) -> Dict[str, Any]:
    """{'ok', 'status', 'text', 'from_cache', 'url', 'error'}; cached with provenance; bounded."""
    store = store or C.get_store()
    cf = _cache_file(url)
    cached = None
    if os.path.isfile(cf):
        try:
            with open(cf, "r", encoding="utf-8") as fh:
                cached = fh.read()
        except OSError:
            cached = None
    fresh = cached is not None and (time.time() - os.path.getmtime(cf) < ttl)
    if cached is not None and (fresh or C.OFFLINE or CACHE_ONLY):
        _STATE["cache_hits"] += 1
        return {"ok": True, "status": 200, "text": cached, "from_cache": True, "url": url}
    if C.OFFLINE or CACHE_ONLY or requests is None:
        return {"ok": False, "status": 0, "text": "", "from_cache": False, "url": url, "error": "offline/cache-only and not cached"}
    host = urllib.parse.urlparse(url).netloc
    if host == "api.github.com" and _STATE["github_blocked"]:
        if cached is not None:
            return {"ok": True, "status": 200, "text": cached, "from_cache": True, "url": url, "stale": True}
        return {"ok": False, "status": 403, "text": "", "from_cache": False, "url": url, "error": "GitHub rate limit reached earlier in this session"}
    h = {"User-Agent": C.USER_AGENT, "Accept": "application/json, text/plain, */*"}
    if host == "api.github.com":
        h["Accept"] = "application/vnd.github+json"
    h.update(headers or {})
    try:
        _STATE["requests"] += 1
        r = requests.get(url, headers=h, timeout=timeout, stream=True)
        if host == "api.github.com" and r.status_code in (403, 429):
            _STATE["github_blocked"] = True
        chunks, n = [], 0
        for part in r.iter_content(65536):
            chunks.append(part)
            n += len(part)
            if n > max_bytes:
                break
        text = b"".join(chunks).decode(r.encoding or "utf-8", "replace")
        if r.status_code == 200:
            with open(cf, "w", encoding="utf-8") as fh:
                fh.write(text)
            store.put_doc(url, app_key, kind, C.sha(text, 16), len(text), cf, 200)
            return {"ok": True, "status": 200, "text": text, "from_cache": False, "url": url}
        if cached is not None:
            return {"ok": True, "status": 200, "text": cached, "from_cache": True, "url": url, "stale": True}
        return {"ok": False, "status": r.status_code, "text": "", "from_cache": False, "url": url, "error": f"HTTP {r.status_code}"}
    except Exception as exc:
        msg = f"{type(exc).__name__}: {str(exc)[:100]}"
        _STATE["errors"].append(f"{url[:80]} -> {msg}")
        if cached is not None:
            return {"ok": True, "status": 200, "text": cached, "from_cache": True, "url": url, "stale": True}
        return {"ok": False, "status": 0, "text": "", "from_cache": False, "url": url, "error": msg}


def get_json(url: str, **kw) -> Tuple[Optional[Any], Dict[str, Any]]:
    r = get(url, **kw)
    if not r["ok"]:
        return None, r
    try:
        return json.loads(r["text"]), r
    except Exception:
        return None, dict(r, ok=False, error="not JSON")


def stats() -> Dict[str, Any]:
    return dict(_STATE, offline=C.OFFLINE)


# --------------------------------------------------------------------------------------------------
# Wikidata
# --------------------------------------------------------------------------------------------------

WD = "https://www.wikidata.org/w/api.php"
PROPS = {"P31": "instance of", "P277": "written in", "P306": "operating system", "P178": "developer", "P275": "license", "P856": "official website",
         "P1324": "source code repository", "P348": "software version", "P400": "platform", "P366": "has use", "P144": "based on", "P2078": "user manual URL",
         "P1482": "Stack Exchange tag", "P4033": "Mastodon address", "P973": "described at URL", "P1343": "described by source", "P2572": "hashtag",
         "P1535": "used by", "P1056": "product or material produced", "P279": "subclass of"}


def _wd_claim_values(entity: Dict[str, Any], pid: str) -> List[Any]:
    out = []
    for c in (entity.get("claims") or {}).get(pid, []):
        dv = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if dv is not None:
            out.append(dv)
    return out


def identify(name: str, *, vendor: str = "", app_key: str = "", limit: int = 6) -> Dict[str, Any]:
    """Best Wikidata entity for an application name, with its software facts. {} when nothing credible is found."""
    q = name.strip()
    if not q:
        return {}
    search, r1 = get_json(f"{WD}?action=wbsearchentities&search={urllib.parse.quote(q)}&language=en&format=json&limit={limit}&type=item", kind="wikidata", app_key=app_key)
    cands = (search or {}).get("search", [])
    if not cands:
        return {"ok": False, "why": r1.get("error") or "no Wikidata match"}
    ids = "|".join(c["id"] for c in cands)
    ents, r2 = get_json(f"{WD}?action=wbgetentities&ids={ids}&props=labels|descriptions|claims&languages=en&format=json", kind="wikidata", app_key=app_key)
    ents = (ents or {}).get("entities", {})
    p31_ids = sorted({v["id"] for e in ents.values() for v in _wd_claim_values(e, "P31") if isinstance(v, dict) and "id" in v})[:50]
    p31_labels: Dict[str, str] = {}
    if p31_ids:
        lab0, _ = get_json(f"{WD}?action=wbgetentities&ids={'|'.join(p31_ids)}&props=labels&languages=en&format=json", kind="wikidata", app_key=app_key)
        for qid0, ent0 in (lab0 or {}).get("entities", {}).items():
            p31_labels[qid0] = ((ent0.get("labels") or {}).get("en") or {}).get("value", "")
    qfold = C.fold(q)
    best, best_score = None, -1.0
    for c in cands:
        e = ents.get(c["id"], {})
        label = ((e.get("labels") or {}).get("en") or {}).get("value", c.get("label", ""))
        desc = ((e.get("descriptions") or {}).get("en") or {}).get("value", c.get("description", ""))
        score = 0.0
        lf = C.fold(label)
        if lf == qfold:
            score += 3.0
        elif qfold in lf or lf in qfold:
            score += 1.0
        if SOFTWARE_WORDS.search(desc or ""):
            score += 2.0
        if any(SOFTWARE_WORDS.search(p31_labels.get(v.get("id", ""), "")) for v in _wd_claim_values(e, "P31") if isinstance(v, dict)):
            score += 2.0
        for pid, w in (("P277", 1.5), ("P1324", 2.0), ("P306", 1.0), ("P856", 0.5), ("P348", 0.5), ("P178", 0.5)):
            if e.get("claims", {}).get(pid):
                score += w
        if vendor and vendor.lower() in desc.lower():
            score += 1.0
        if score > best_score:
            best, best_score = (c, e, label, desc), score
    if not best or best_score < 2.0:
        return {"ok": False, "why": "no candidate looked like software", "candidates": [{"id": c["id"], "label": c.get("label"), "description": c.get("description")} for c in cands]}
    c, e, label, desc = best
    facts: Dict[str, Any] = {"id": c["id"], "label": label, "description": desc, "score": best_score, "url": f"https://www.wikidata.org/wiki/{c['id']}"}
    qids: List[str] = []
    raw: Dict[str, List[Any]] = {}
    for pid in PROPS:
        vals = _wd_claim_values(e, pid)
        raw[pid] = vals
        for v in vals:
            if isinstance(v, dict) and str(v.get("id", "")).startswith("Q"):
                qids.append(v["id"])
    labels: Dict[str, str] = {}
    uq_all = sorted(set(qids))
    for i in range(0, min(len(uq_all), 150), 50):
        lab, _ = get_json(f"{WD}?action=wbgetentities&ids={'|'.join(uq_all[i:i + 50])}&props=labels&languages=en&format=json", kind="wikidata", app_key=app_key)
        for qid, ent in (lab or {}).get("entities", {}).items():
            labels[qid] = ((ent.get("labels") or {}).get("en") or {}).get("value", qid)
    for pid, vals in raw.items():
        out_vals = []
        for v in vals:
            if isinstance(v, dict) and "id" in v:
                out_vals.append(labels.get(v["id"], v["id"]))
            elif isinstance(v, dict) and "text" in v:
                out_vals.append(v["text"])
            elif isinstance(v, dict) and "amount" in v:
                out_vals.append(v["amount"])
            else:
                out_vals.append(str(v))
        if out_vals:
            facts[PROPS[pid]] = sorted(set(out_vals))[:12]
    facts["ok"] = True
    return facts


# --------------------------------------------------------------------------------------------------
# Wikipedia
# --------------------------------------------------------------------------------------------------

def wikipedia(title_or_name: str, *, app_key: str = "", chars: int = 9000) -> Dict[str, Any]:
    t = urllib.parse.quote(title_or_name.strip().replace(" ", "_"))
    summ, r = get_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{t}?redirect=true", kind="wikipedia", app_key=app_key)
    if not summ or summ.get("type") == "disambiguation" or "title" not in summ:
        s2, _ = get_json(f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(title_or_name)}&limit=3&format=json", kind="wikipedia", app_key=app_key)
        hits = (s2 or [None, [], [], []])[1] if isinstance(s2, list) and len(s2) > 1 else []
        if not hits:
            return {"ok": False, "why": r.get("error") or "no article"}
        summ, r = get_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(hits[0].replace(' ', '_'))}?redirect=true", kind="wikipedia", app_key=app_key)
        if not summ:
            return {"ok": False, "why": "no article"}
    title = summ.get("title", title_or_name)
    full, r3 = get_json(f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles={urllib.parse.quote(title)}&format=json&redirects=1",
                        kind="wikipedia", app_key=app_key, max_bytes=900_000)
    text = ""
    if full:
        for page in (full.get("query", {}).get("pages") or {}).values():
            text = page.get("extract", "") or text
    text = text[:chars]
    return {"ok": True, "title": title, "description": summ.get("description", ""), "summary": summ.get("extract", ""), "text": text or summ.get("extract", ""),
            "url": (summ.get("content_urls", {}).get("desktop", {}) or {}).get("page", f"https://en.wikipedia.org/wiki/{t}"), "wikibase_item": summ.get("wikibase_item")}


# --------------------------------------------------------------------------------------------------
# GitHub
# --------------------------------------------------------------------------------------------------

GH = "https://api.github.com"
INTERESTING = [
    (r"(^|/)(keymap|keybinding|keyboard|shortcut|hotkey|key_?bind)s?[^/]*\.(py|json|cfg|xml|toml|ya?ml|md|rst|txt|ini|kbd|keymap)$", "keymap", 6),
    (r"(^|/)(docs?|manual|documentation|wiki)/[^/]*(shortcut|keyboard|hotkey|keymap|navigation|gesture|mouse|interface|ui|architecture|overview|plugin|scripting|api)[^/]*\.(md|rst|txt)$", "doc", 6),
    (r"(^|/)(ARCHITECTURE|DESIGN|OVERVIEW|CONTRIBUTING|HACKING|DEVELOPERS?|INTERNALS)[^/]*\.(md|rst|txt)$", "dev-doc", 4),
    (r"(^|/)(package\.json|CMakeLists\.txt|pyproject\.toml|setup\.py|Cargo\.toml|\.csproj|meson\.build|SConstruct|build\.gradle)$", "build", 3),
    (r"(^|/)(README)[^/]*$", "readme", 1),
]


def parse_repo(url_or_slug: str) -> str:
    m = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git|/|$)", url_or_slug or "")
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    if re.fullmatch(r"[\w.-]+/[\w.-]+", url_or_slug or ""):
        return url_or_slug
    return ""


def find_repo(name: str, description: str = "", *, app_key: str = "") -> str:
    q = urllib.parse.quote(f"{name} in:name")
    d, r = get_json(f"{GH}/search/repositories?q={q}&sort=stars&order=desc&per_page=6", kind="github", app_key=app_key)
    items = (d or {}).get("items", [])
    nf = C.fold(name)
    best, best_s = "", 0.0
    for it in items:
        s = 0.0
        rn = C.fold(it.get("name", ""))
        if rn == nf or rn.replace(" ", "") == nf.replace(" ", ""):
            s += 3.0
        elif nf in rn:
            s += 1.0
        s += min(3.0, (it.get("stargazers_count", 0) or 0) / 20000.0)
        if description and any(w in (it.get("description") or "").lower() for w in re.findall(r"[a-z]{5,}", description.lower())[:6]):
            s += 1.0
        if it.get("fork") or it.get("archived"):
            s -= 2.0
        if s > best_s:
            best, best_s = it["full_name"], s
    return best if best_s >= 2.5 else ""


def repo_bundle(slug: str, *, app_key: str = "", max_files: int = 6) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": False, "repo": slug, "files": []}
    meta, r = get_json(f"{GH}/repos/{slug}", kind="github", app_key=app_key)
    if not meta:
        out["why"] = r.get("error", "repo metadata unavailable")
        return out
    out.update(ok=True, url=meta.get("html_url"), description=meta.get("description"), language=meta.get("language"), topics=meta.get("topics", []),
               license=(meta.get("license") or {}).get("spdx_id"), stars=meta.get("stargazers_count"), default_branch=meta.get("default_branch", "master"),
               homepage=meta.get("homepage"), pushed_at=meta.get("pushed_at"), size_kb=meta.get("size"))
    langs, _ = get_json(f"{GH}/repos/{slug}/languages", kind="github", app_key=app_key)
    if langs:
        tot = float(sum(langs.values())) or 1.0
        out["languages"] = {k: round(100.0 * v / tot, 1) for k, v in sorted(langs.items(), key=lambda kv: -kv[1])[:10]}
    br = out["default_branch"]
    tree, _ = get_json(f"{GH}/repos/{slug}/git/trees/{urllib.parse.quote(br)}?recursive=1", kind="github", app_key=app_key, max_bytes=6_000_000)
    paths: List[str] = []
    sizes: Dict[str, int] = {}
    if tree:
        paths = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]
        sizes = {t["path"]: int(t.get("size") or 0) for t in tree.get("tree", []) if t.get("type") == "blob"}
        out["tree_truncated"] = bool(tree.get("truncated"))
        top: Dict[str, int] = {}
        for p in paths:
            top[p.split("/")[0]] = top.get(p.split("/")[0], 0) + 1
        out["top_level"] = dict(sorted(top.items(), key=lambda kv: -kv[1])[:40])
        out["n_files"] = len(paths)
        dirs2: Dict[str, int] = {}
        for p in paths:
            parts = p.split("/")
            if len(parts) > 2 and parts[0] in ("plugins", "modules", "addons", "extensions", "src", "libs", "lib", "source", "scripts", "packages", "apps", "components"):
                dirs2[f"{parts[0]}/{parts[1]}"] = dirs2.get(f"{parts[0]}/{parts[1]}", 0) + 1
        out["modules"] = dict(sorted(dirs2.items(), key=lambda kv: -kv[1])[:60])
    import math as _m
    picks: List[Tuple[float, str, str]] = []
    for p in paths:
        sz = sizes.get(p, 0)
        if re.search(r"(keymap|keyconfig|keybind|key_?bind|shortcut|hotkey)", p, re.I) and re.search(r"\.(py|json|jsonc|cfg|xml|toml|ya?ml|ini|kbd|keymap|md|rst|txt)$", p, re.I):
            if 1500 <= sz <= 520_000 and not re.search(r"(test|example|sample|locale|i18n|translations?)", p, re.I):
                score = 6.0 + min(4.0, _m.log10(max(sz, 10))) + (2.0 if re.search(r"(default|main|global|common)", p, re.I) else 0) + (1.5 if p.endswith((".py", ".json", ".xml", ".cfg")) else 0)
                picks.append((score, "keymap", p))
            continue
        for rx, tag, pri in INTERESTING[1:]:
            if re.search(rx, p, re.I):
                picks.append((float(pri) + (0.5 if sz > 2000 else 0) + (3.0 if "/" not in p else 0.0) - 0.1 * p.count("/"), tag, p))
                break
    picks.sort(key=lambda t: -t[0])
    seen_tags: Dict[str, int] = {}
    chosen: List[Tuple[str, str]] = []
    for score, tag, p in picks:
        if seen_tags.get(tag, 0) >= (3 if tag in ("keymap", "doc") else 1):
            continue
        seen_tags[tag] = seen_tags.get(tag, 0) + 1
        chosen.append((p, tag))
        if len(chosen) >= max_files:
            break
    if not any(t == "readme" for _, t in chosen):
        chosen.append(("README.md", "readme"))
    def _fetch(item: Tuple[str, str]) -> Optional[Dict[str, Any]]:
        p, tag = item
        raw = get(f"https://raw.githubusercontent.com/{slug}/{br}/{urllib.parse.quote(p)}", kind="github-raw", app_key=app_key, max_bytes=500_000)
        if not raw["ok"] and tag == "readme":
            for alt in ("README.rst", "README", "readme.md", "README.txt"):
                raw = get(f"https://raw.githubusercontent.com/{slug}/{br}/{alt}", kind="github-raw", app_key=app_key, max_bytes=500_000)
                if raw["ok"]:
                    p = alt
                    break
        return {"path": p, "tag": tag, "url": raw["url"], "text": raw["text"]} if raw["ok"] else None
    import concurrent.futures as _cf
    with _cf.ThreadPoolExecutor(max_workers=5) as ex:
        for rec in ex.map(_fetch, chosen):
            if rec:
                out["files"].append(rec)
    return out


# --------------------------------------------------------------------------------------------------
# the one call
# --------------------------------------------------------------------------------------------------

def knowledge_for(name: str, *, vendor: str = "", product: str = "", app_key: str = "", repo_hint: str = "") -> Dict[str, Any]:
    """Everything public and free about `name`: Wikidata facts, Wikipedia text, the source repository bundle. Never raises."""
    t0 = time.time()
    out: Dict[str, Any] = {"name": name, "ok": False, "sources": [], "stats": {}}
    q = (product or name).strip()
    wd = identify(q, vendor=vendor, app_key=app_key)
    if not wd.get("ok") and q != name:
        wd = identify(name, vendor=vendor, app_key=app_key)
    if wd.get("ok"):
        out["wikidata"] = wd
        out["sources"].append(wd["url"])
    wp = wikipedia(wd.get("label") or q, app_key=app_key)
    if wp.get("ok"):
        out["wikipedia"] = wp
        out["sources"].append(wp["url"])
    slug = parse_repo(repo_hint) or (parse_repo((wd.get("source code repository") or [""])[0]) if wd.get("ok") else "")
    if not slug and (wd.get("ok") or wp.get("ok")):
        slug = find_repo(wd.get("label") or q, (wd.get("description") or "") + " " + (wp.get("description") or ""), app_key=app_key)
    if slug:
        gb = repo_bundle(slug, app_key=app_key)
        if gb.get("ok"):
            out["github"] = gb
            out["sources"].append(gb.get("url") or f"https://github.com/{slug}")
        else:
            out["github_error"] = gb.get("why")
    out["ok"] = bool(wd.get("ok") or wp.get("ok") or out.get("github"))
    out["seconds"] = round(time.time() - t0, 2)
    out["stats"] = stats()
    return out


# --------------------------------------------------------------------------------------------------
# deterministic claims from the structured parts (text goes through atlas.distill)
# --------------------------------------------------------------------------------------------------

def structured_claims(app_key: str, web: Dict[str, Any]) -> List[C.Claim]:
    out: List[C.Claim] = []
    wd = web.get("wikidata") or {}
    if wd.get("ok"):
        ev = [C.Evidence("url", wd["url"], f"{wd.get('label')}: {wd.get('description')}")]
        if wd.get("description"):
            out.append(C.Claim(app_key, "web.identity", f"{wd['label']} is described as: {wd['description']}", "published", 0.8, ev, {"wikidata": wd["id"]}, "atlas.webknow"))
        for fact, kind, pat in (("written in", "web.language", "Written in {v}"), ("operating system", "web.platform", "Runs on {v}"), ("license", "web.license", "Licence: {v}"),
                                ("developer", "web.developer", "Developed by {v}"), ("instance of", "web.kind", "Is a(n) {v}"), ("platform", "web.platform", "Platform: {v}"),
                                ("software version", "web.version", "Latest known version: {v}"), ("based on", "web.lineage", "Based on {v}")):
            vals = wd.get(fact)
            if vals:
                out.append(C.Claim(app_key, kind, pat.format(v=", ".join(str(x) for x in vals[:8])), "published", 0.8, ev, vals, "atlas.webknow"))
    gh = web.get("github") or {}
    if gh.get("ok"):
        base = gh.get("url") or f"https://github.com/{gh['repo']}"
        ev = [C.Evidence("url", base, gh.get("description") or "")]
        out.append(C.Claim(app_key, "web.source", f"Open-source repository {gh['repo']} ({gh.get('stars')} stars, licence {gh.get('license')}); {gh.get('description') or ''}".strip(), "published", 0.85, ev, gh["repo"], "atlas.webknow"))
        if gh.get("languages"):
            comp = ", ".join(f"{k} {v}%" for k, v in gh["languages"].items())
            out.append(C.Claim(app_key, "web.language", f"Source code composition: {comp}", "published", 0.9, [C.Evidence("url", f"{GH}/repos/{gh['repo']}/languages", comp)], gh["languages"], "atlas.webknow"))
        if gh.get("top_level"):
            out.append(C.Claim(app_key, "web.layout", "Repository top-level modules: " + ", ".join(f"{k} ({v} files)" for k, v in list(gh["top_level"].items())[:20]), "published", 0.85,
                               [C.Evidence("url", f"{GH}/repos/{gh['repo']}/git/trees/{gh.get('default_branch')}", "git tree")], gh["top_level"], "atlas.webknow"))
        if gh.get("modules"):
            mods = ", ".join(list(gh["modules"].keys())[:30])
            out.append(C.Claim(app_key, "web.modules", f"Source modules/plugins: {mods}", "published", 0.8, [C.Evidence("url", f"{GH}/repos/{gh['repo']}/git/trees/{gh.get('default_branch')}", "git tree")], gh["modules"], "atlas.webknow"))
        if gh.get("topics"):
            out.append(C.Claim(app_key, "web.topics", "Repository topics: " + ", ".join(gh["topics"]), "published", 0.7, ev, gh["topics"], "atlas.webknow"))
    return out
