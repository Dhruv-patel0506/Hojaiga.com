"""
harvest.web_learn -- turn ONE scanned web app into lasting knowledge.

try_app's deep exploration of a site ends in a report (what was clicked and what happened, the reverse-engineered stack / traffic / sign-in / site map, the shortcut sheet if the page has one).
`learn_site` files that report where the system can USE it later:

    lexicon      one command per path that DID something ('Features > Inbox', 'Pricing > FAQ > How are seats counted') under the app key `webapp:<host>`, filed with its category,
                 trust 'web' (read off a live page, never verified by use)
    hotkeys      every single-step shortcut from the page's own shortcut sheet, as a hotkey row in the fast-path store (trust 'web', verified False)
    document     the plain-language understanding (what it is, how to use it, stack, sign-in, page types, the map) as a retrievable document, so a question about the app finds it
    web kind     the site's word profile + the category the curriculum gave it, added to the examples the kind-recogniser learns from (web_kind.add_example)
    patterns     cross-site counters (stacks, sign-in providers, shortcut sheets, API style, the section names each category has) in data/web_curriculum/patterns.json

Nothing is deleted or overwritten; everything written is listed in reports/web_curriculum/rag_writes.jsonl so a run can be rolled back (`web_curriculum rollback <run>`).
Writers take a cross-process lock first: the video curriculum may be writing to the same store.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import time
from collections import Counter
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from core_organs.harvest import web_kind as WK

DATA = WK.DATA
FOLDER = WK.FOLDER
PATTERNS = os.path.join(FOLDER, "patterns.json")
LOCK = os.path.join(DATA, "ai_root", "rag", "write.lock")
NOTHING = ("nothing visible happened", "unreachable", "could not click")


@contextlib.contextmanager
def rag_lock(timeout_s: float = 120.0) -> Iterator[None]:
    """Cross-process write lock (Windows byte-range lock on a small file): two curricula never write to the LanceDB store at the same moment."""
    import msvcrt
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    f = open(LOCK, "a+b")
    t0 = time.time()
    got = False
    try:
        while time.time() - t0 < timeout_s:
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                got = True
                break
            except OSError:
                time.sleep(0.5)
        yield
    finally:
        if got:
            with contextlib.suppress(Exception):
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        f.close()


def host_of(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url.strip().lower()).split("/")[0]


def structure_tokens(report: Dict[str, Any]) -> List[str]:
    """What the site is BUILT like, as pseudo-words (letters only, so they ride in the same word profile): button-heavy vs link-heavy, canvas, frames, framework, GraphQL, sockets, sign-in kind, API volume ..."""
    u = report.get("understanding") or {}
    st, net, au, sh = u.get("stack", {}), u.get("network", {}), u.get("auth", {}), u.get("shortcut_sheet", {})
    roles = (report.get("digest") or {}).get("roles") or {}
    tot = max(1, sum(roles.values()))
    btn = sum(n for r, n in roles.items() if r in ("button", "tab", "menuitem", "summary", "combobox", "clickable")) / tot
    link = roles.get("link", 0) / tot
    sc = report.get("scan") or {}
    toks = []
    toks.append("zzbtnhigh" if btn >= 0.25 else "zzbtnlow" if btn < 0.08 else "zzbtnmid")
    toks.append("zzlinkheavy" if link >= 0.7 else "zzlinklight" if link < 0.4 else "zzlinkmid")
    if sum(n for r, n in roles.items() if r.endswith("input") or r in ("select", "combobox")) >= 3:
        toks.append("zzinputs")
    if (sc.get("canvases") or 0) > 0:
        toks.append("zzcanvas")
    if (sc.get("iframes") or 0) >= 3:
        toks.append("zziframes")
    for f in st.get("frameworks", []):
        toks.append("zzfw" + re.sub(r"[^a-z]", "", f.lower())[:12])
    if net.get("graphql_operations"):
        toks.append("zzgraphql")
    if net.get("websockets"):
        toks.append("zzwebsocket")
    if st.get("manifest"):
        toks.append("zzpwa")
    if au.get("sso_providers"):
        toks.append("zzsso")
    if au.get("login_wall"):
        toks.append("zzloginwall")
    if sh.get("opened"):
        toks.append("zzshortcutsheet")
    if len(net.get("api_endpoints", [])) >= 15:
        toks.append("zzapiheavy")
    ex = sc.get("explore") or {}
    if ex.get("outcomes", {}).get("opens on hover"):
        toks.append("zzhovermenus")
    if ex.get("outcomes", {}).get("opened a dialog"):
        toks.append("zzdialogs")
    return toks


def signature_words(report: Dict[str, Any]) -> Counter:
    """The words a site says about ITSELF, not its content: the page description and headings, the main navigation, every path the exploration walked and what opening each revealed, page titles,
    plus how it is built (structure_tokens, counted three times). The thousands of body links of a news or docs site (article titles) are deliberately left out: they describe what is published, not what the app is."""
    u = report.get("understanding") or {}
    me = u.get("meaning") or {}
    texts: List[str] = [me.get("description", ""), me.get("name", "")] + list(me.get("headings") or []) + list(me.get("navigation") or [])
    ex = (report.get("scan") or {}).get("explore") or {}
    lang = re.compile(r"(language|langue|sprache|lingua|idioma|taal|locale|country|region|cookie)", re.I)
    for n in ex.get("nodes", []):
        if lang.search(n.get("path", "")):
            continue                                                      # a list of 44 language names says nothing about what the app is
        texts.append(n.get("path", ""))
        texts += [str(x).split(": ", 1)[-1] for x in (n.get("revealed") or [])[:15]]
    texts += [t for t in (ex.get("pages") or {}).values()]
    c = WK.words_of(texts)
    for t in structure_tokens(report):
        c[t] += 3
    return c


def sections_of(report: Dict[str, Any]) -> List[str]:
    """Top-level section names (the first label of each explored path + the main navigation), lower-cased."""
    u = (report.get("understanding") or {}).get("meaning") or {}
    ex = (report.get("scan") or {}).get("explore") or {}
    out = [n["path"].split(" > ")[0] for n in ex.get("nodes", []) if n.get("outcome") not in NOTHING and n.get("path")]
    out += list(u.get("navigation") or [])
    cleaned = []
    for s in out:
        s = re.sub(r"\s+", " ", s).strip().lower()
        if 2 < len(s) <= 28 and not re.search(r"(skip|close|toggle|menu|navigation|cookie|accept|privacy|terms|sign|log ?in)", s):
            cleaned.append(s)
    return list(dict.fromkeys(cleaned))


def hotkey_rows(key: str, pairs: Sequence[Dict[str, str]], BR: Any) -> List[Dict[str, Any]]:
    rows = []
    for p in pairs:
        k = re.sub(r"\s*\+\s*", "+", (p.get("keys") or "").strip().lower())
        act = re.sub(r"\s+", " ", p.get("action", "")).strip()
        if not k or not act or re.search(r"\b(then|or)\b|,", k) or len(k) > 18 or len(act) < 3:
            continue
        kind, payload = BR.norm_keys(k)
        rows.append({"app_key": key, "kind": kind, "task_pattern": act[:80], "payload": payload, "source": "web_table", "trust": "web", "verified": False,
                     "context": "web-sheet: read from the page's own keyboard-shortcut sheet", "params_schema_json": BR.infer_schema(payload)})
    return rows


def probe_rows(key: str, probes: Sequence[Dict[str, str]], BR: Any) -> List[Dict[str, Any]]:
    """Keys that were PRESSED on the live page and whose effect was SEEN (focus moved into a text field, a dialog appeared): the only web hotkeys that are written as verified."""
    rows = []
    for p in probes:
        kind, payload = BR.norm_keys(re.sub(r"\s*\+\s*", "+", p["keys"].lower()))
        rows.append({"app_key": key, "kind": kind, "task_pattern": p["action"][:80], "payload": payload, "source": "web_probe", "trust": "learned", "verified": True,
                     "context": f"pressed live on the page: {p['effect']}", "params_schema_json": BR.infer_schema(payload)})
    return rows


def spoken_rows(key: str, shortcuts: Sequence[Dict[str, str]], BR: Any, title: str) -> List[Dict[str, Any]]:
    """Shortcuts a speaker named in a video about / on the app: leads (trust 'transcript', unverified)."""
    rows = []
    for p in shortcuts:
        kind, payload = BR.norm_keys(p["keys"])
        rows.append({"app_key": key, "kind": kind, "task_pattern": p["action"][:80], "payload": payload, "source": "transcript", "trust": "transcript", "verified": False,
                     "context": f"said in a video on the site: {title[:60]}", "params_schema_json": BR.infer_schema(payload)})
    return rows


def update_patterns(host: str, category: str, report: Dict[str, Any], path: str = "") -> Dict[str, Any]:
    path = path or PATTERNS
    pat: Dict[str, Any] = {}
    if os.path.isfile(path):
        with contextlib.suppress(Exception):
            pat = json.load(open(path, encoding="utf-8"))
    pat.setdefault("sites", {})
    u = report.get("understanding") or {}
    st, net, au, sh = u.get("stack", {}), u.get("network", {}), u.get("auth", {}), u.get("shortcut_sheet", {})
    pat["sites"][host] = {"category": category, "frameworks": st.get("frameworks", []), "platform": (st.get("headers") or {}).get("platform_hints", []), "sso": au.get("sso_providers", []),
                          "login_wall": bool(au.get("login_wall")), "blocked": au.get("blocked"), "shortcut_sheet": bool(sh.get("opened")), "graphql": bool(net.get("graphql_operations")),
                          "websocket": bool(net.get("websockets")), "pwa": bool(st.get("manifest")), "requests": net.get("requests"), "api_endpoints": len(net.get("api_endpoints", [])),
                          "third_party_share": round((net.get("by_kind", {}).get("analytics", 0) + net.get("by_kind", {}).get("ads", 0) + net.get("by_kind", {}).get("third-party", 0)) / max(1, net.get("requests", 1)), 3),
                          "sections": sections_of(report)[:40]}
    sites = pat["sites"]
    by_cat: Dict[str, Counter] = {}
    for h, s in sites.items():
        by_cat.setdefault(s["category"], Counter()).update(set(s["sections"]))
    n_cat = Counter(s["category"] for s in sites.values())
    pat["sections_by_category"] = {c: [{"section": w, "sites": n} for w, n in cnt.most_common(25) if n >= 2] for c, cnt in by_cat.items()}
    pat["summary"] = {"sites": len(sites), "per_category": dict(n_cat),
                      "frameworks": Counter(f for s in sites.values() for f in s["frameworks"]).most_common(12), "sso": Counter(p for s in sites.values() for p in s["sso"]).most_common(8),
                      "share_with_shortcut_sheet": round(sum(s["shortcut_sheet"] for s in sites.values()) / len(sites), 3), "share_graphql": round(sum(s["graphql"] for s in sites.values()) / len(sites), 3),
                      "share_login_wall": round(sum(s["login_wall"] for s in sites.values()) / len(sites), 3), "share_pwa": round(sum(s["pwa"] for s in sites.values()) / len(sites), 3)}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pat, f, indent=1, ensure_ascii=False)
    return pat["summary"]


def common_sections(category: str, host: str = "", top: int = 12, path: str = "") -> List[Dict[str, Any]]:
    """Sections that other sites of this category share (>= 2 of them) and this one has not shown: what to look for next."""
    path = path or PATTERNS
    if not os.path.isfile(path):
        return []
    with contextlib.suppress(Exception):
        pat = json.load(open(path, encoding="utf-8"))
        have = set((pat["sites"].get(host) or {}).get("sections", []))
        return [x for x in pat["sections_by_category"].get(category, []) if x["section"] not in have][:top]
    return []


def learn_site(rag: Any, report: Dict[str, Any], url: str, category: str, run: str, ledger: str = "", write: bool = True, doc_text: str = "") -> Dict[str, Any]:
    host = host_of(url)
    key = "webapp:" + host
    res: Dict[str, Any] = {"key": key, "category": category, "commands": 0, "hotkeys": 0, "doc_chunks": 0, "example_added": False}
    ex = (report.get("scan") or {}).get("explore") or {}
    u = report.get("understanding") or {}
    blocked = (u.get("auth") or {}).get("blocked") or ((report.get("scan") or {}).get("http_status") or 0) >= 400
    words = signature_words(report)
    if blocked:
        res["status"] = "refused_by_site"
        update_patterns(host, category, report)
        return res
    labels: List[str] = []
    for n in ex.get("nodes", []):
        if n.get("outcome") not in NOTHING and n.get("path"):
            labels.append(n["path"][:120])
    labels += [x for x in sections_of(report)]
    labels = list(dict.fromkeys(labels))[:220]
    from core_organs.harvest import bridge as BR
    pairs = (u.get("shortcut_sheet") or {}).get("pairs", [])
    rows = hotkey_rows(key, pairs, BR)
    rows += probe_rows(key, (u.get("keyboard") or {}).get("hotkeys", []), BR)
    media = list(((report.get("scan") or {}).get("explore") or {}).get("media") or [])
    for m in media:
        rows += spoken_rows(key, m.get("spoken_shortcuts") or [], BR, m.get("title", ""))
    written_rows: List[Tuple[str, str]] = []
    if write and rag is not None:
        with rag_lock():
            for lab in labels:
                with contextlib.suppress(Exception):
                    rag.lex.add_command(key, lab, archetype="web:" + category, source="web_explore", trust="web")
                    res["commands"] += 1
            fresh = [r for r in rows if not rag.fast.find(key, r["task_pattern"], r["payload"])]
            if fresh:
                for r in fresh:
                    r["command_id"] = rag.lex.add_command(key, r["task_pattern"], archetype="web:" + category, source="web_table", trust="web")
                rag.fast.upsert(fresh)
                res["hotkeys"] = len(fresh)
                written_rows = [(r["task_pattern"], r["payload"]) for r in fresh]
            from core_organs.harvest import web_media as WM
            for m in media:                                                                   # what a video on the site SHOWS and SAYS becomes something a question can find
                try:
                    vid = re.sub(r"[^A-Za-z0-9]+", "_", (m.get("url", "") + m.get("title", ""))[-60:])
                    rep1 = rag.proc.ingest_document(key, WM.media_document(m), f"web_media:{m.get('url', '')}", kind="web_doc", title=m.get("title", "")[:80] or "video", trust="web")
                    res["media_docs"] = res.get("media_docs", 0) + int(getattr(rep1, "inserted", 0) or 0) + int(getattr(rep1, "updated", 0) or 0)
                    segs = m.get("_segments") or []
                    if segs:
                        rep2 = rag.proc.ingest_transcript(key, segs, vid, title=m.get("title", "")[:80], caption="auto_caption")
                        res["transcript_chunks"] = res.get("transcript_chunks", 0) + int(getattr(rep2, "inserted", 0) or 0) + int(getattr(rep2, "updated", 0) or 0)
                except Exception as e:
                    res["media_error"] = f"{type(e).__name__}: {str(e)[:100]}"
            if doc_text:
                try:
                    rep = rag.proc.ingest_document(key, doc_text, f"web_explore:{run}", kind="web_doc", title=f"{host} (explored {time.strftime('%Y-%m-%d')})", trust="web")
                    res["doc_chunks"] = int(getattr(rep, "inserted", 0) or 0) + int(getattr(rep, "updated", 0) or 0)
                except Exception as e:                                                          # a document that could not be stored is reported, never silently lost
                    res["doc_error"] = f"{type(e).__name__}: {str(e)[:120]}"
    try:                                                                                       # what the page is made of, read by REA (scripts, routes, API tools)
        sc = report.get("scan") or {}
        rr = sc.get("rea") or {}
        if rr and write and rag is not None:
            from core_organs import rea_bridge as RB
            fr = RB.file_into_rag(rag, key, host, rr.get("web"), rr.get("api"), run, write=True)
            res.update(rea_document_chunks=fr["document_chunks"], rea_api_procedures=fr["api_procedures"], rea_routes=fr["route_commands"])
    except Exception as e:
        res["rea_error"] = f"{type(e).__name__}: {str(e)[:100]}"
    try:                                                                                       # what every click DID: retrievable procedures + real multi-choice training rows
        from core_organs.harvest import web_actions as WA
        ar = WA.file_actions(rag, report, url, run, write=write)
        res.update(procedures=ar["procedures"], train_rows=ar["train_rows"])
        action_pids = ar["pids"]
    except Exception as e:
        res["actions_error"] = f"{type(e).__name__}: {str(e)[:100]}"
        action_pids = []
    res["example_added"] = WK.add_example(host, category, words) if write else False
    res["words"] = len(words)
    res["patterns"] = update_patterns(host, category, report) if write else {}
    res["status"] = "ok"
    if ledger and write:
        os.makedirs(os.path.dirname(ledger), exist_ok=True)
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps({"run": run, "key": key, "commands": list(dict.fromkeys(labels + [a for a, _ in written_rows])), "hotkeys": written_rows, "procedures": action_pids}, ensure_ascii=False) + "\n")
    return res
