"""
try_app -- point it at ANYTHING (an app name, a web app, a website) and see how well it scans, recognises and teaches it, with timings and proof.

    python -m core_organs.try_app excalidraw.com                 a web app / website  -> headless browser, nothing appears on your screen
    python -m core_organs.try_app "https://trello.com"           same, with a full URL
    python -m core_organs.try_app notepad                        a desktop app        -> the fast first-contact scan (it launches the app itself and closes it afterwards)
    python -m core_organs.try_app "Paint" --desktop --budget 25  force the kind; give the scan more time
    python -m core_organs.try_app figma.com --web --login-wait   (not built: pages behind a login show only what a logged-out visitor sees - the report says so)

What it prints, each stage with its milliseconds:
  1 RECALL      does the knowledge pool already know this app?  (rows, how many proven, the kind of app it was filed under)
  2 SCAN        web: every button / link / field / menu / canvas on the page, shortcuts the page itself announces, a picture with the controls boxed (proof)
                desktop: control tree, menu commands, ribbon tabs, regions, vision state, the capability card's honest verdict
  3 RECOGNISE   from the labels it found: which kind of app this looks like (the archetype router), and which shortcuts apps of that kind usually have that this one has not shown yet
  4 TEACH       what it would teach you first (pool lesson when it has one, otherwise the scanned controls grouped by role)
  5 SCORECARD   pass / fail lines, no marks for effort. A report + the picture go to reports/try_app/<stamp>/.

No API keys, no model call, no network except loading the page you asked for. Read-only: it does not click, type, log in or submit anything.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = os.environ.get("HOJAIGA_REPORTS", os.path.join("D:" + os.sep, "new_automation", "reports"))
SHORTCUT_RX = re.compile(r"\b((?:ctrl|control|cmd|command|alt|option|shift)(?:\s*\+\s*(?:ctrl|control|cmd|command|alt|option|shift))*\s*\+\s*(?:[A-Za-z0-9/\\\[\]\.,;'=-]|enter|esc|tab|space|del|delete|home|end|f\d{1,2}))\b", re.I)

COLLECT_JS = r"""
() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 3 && r.height > 3 && s.visibility !== 'hidden' && s.display !== 'none' && r.bottom > 0 && r.right > 0 && r.top < innerHeight * 3; };
  const sel = 'button, a[href], input, select, textarea, summary, [role=button], [role=menuitem], [role=menuitemcheckbox], [role=menuitemradio], [role=tab], [role=link], [role=checkbox], [role=switch], [role=option], [role=combobox], [role=slider], [role=treeitem], [contenteditable=true], [tabindex]:not([tabindex="-1"])';
  const out = []; const seen = new Set();
  for (const e of document.querySelectorAll(sel)) {
    if (!vis(e) || seen.has(e)) continue; seen.add(e);
    const r = e.getBoundingClientRect();
    const label = (e.getAttribute('aria-label') || e.innerText || e.getAttribute('title') || e.getAttribute('placeholder') || e.getAttribute('alt') || e.value || '').replace(/\s+/g, ' ').trim().slice(0, 80);
    out.push({tag: e.tagName.toLowerCase(), role: e.getAttribute('role') || (e.tagName === 'A' ? 'link' : e.tagName === 'INPUT' ? (e.type || 'text') + ' input' : e.tagName.toLowerCase()),
              label, title: (e.getAttribute('title') || '').slice(0, 80), keys: e.getAttribute('aria-keyshortcuts') || '', x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height),
              inview: r.top >= 0 && r.top < innerHeight});
  }
  const txt = (document.body && document.body.innerText || '').slice(0, 20000);
  return {controls: out, canvases: document.querySelectorAll('canvas').length, iframes: document.querySelectorAll('iframe').length, svgs: document.querySelectorAll('svg').length,
          password: !!document.querySelector('input[type=password]'), title: document.title, url: location.href, text: txt, height: document.documentElement.scrollHeight, width: innerWidth, vh: innerHeight};
}
"""


def looks_like_web(target: str) -> bool:
    t = target.strip()
    if re.match(r"^https?://", t, re.I):
        return True
    return " " not in t and bool(re.match(r"^[\w-]+(\.[\w-]+)+(/.*)?$", t)) and not t.lower().endswith((".exe", ".lnk", ".msc", ".bat", ".cmd"))


def ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def recall(target: str, web: bool) -> Dict[str, Any]:
    """What the pool already holds for this target (read-only)."""
    t0 = time.perf_counter()
    out: Dict[str, Any] = {"known": False}
    with contextlib.suppress(Exception):
        from core_organs import rag as R
        from core_organs.harvest import teach_back as TB
        rag = R.get_rag()
        keys = TB.app_keys(rag)
        name = re.sub(r"^https?://(www\.)?", "", target.strip().lower()).split("/")[0] if web else target.strip().lower()
        key, alts = TB.resolve_key(rag, name, keys)
        if key:
            rows = TB.rows_of(rag, key)
            out = {"known": True, "key": key, "rows": len(rows), "proven": sum(1 for r in rows if r["verified"]), "leads": sum(1 for r in rows if not r["verified"]),
                   "also": alts, "top": [(TB.pretty(r["chord"]), TB.shown(r["action"]), TB.mark(r).strip()) for r in rows[:12]]}
            with contextlib.suppress(Exception):
                from core_organs.harvest import transfer_priors as TP
                out["filed_as"] = TP.archetype_map().get(key, "")
        out["_rag"] = rag
    out["ms"] = ms(t0)
    return out


# --------------------------------------------------------------------------------------------- browser
def launch_browser(pw: Any, headless: bool = True, args: Optional[List[str]] = None) -> Any:
    """Open Chromium whichever way works on this machine. Playwright asks for the exact browser build it was released with; when only an older build is installed (the project's pinned
    environment and the system Python carry different Playwright versions) the newest installed Chromium is used by path, then the person's own Chrome / Edge."""
    import glob
    try:
        return pw.chromium.launch(headless=headless, args=args or [])
    except Exception as first:
        if "Executable doesn't exist" not in str(first):
            raise
        base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
        for exe in sorted(glob.glob(os.path.join(base, "chromium-*", "chrome-win*", "chrome.exe")), reverse=True):
            with contextlib.suppress(Exception):
                return pw.chromium.launch(headless=headless, args=args or [], executable_path=exe)
        for channel in ("chrome", "msedge"):
            with contextlib.suppress(Exception):
                return pw.chromium.launch(headless=headless, args=args or [], channel=channel)
        raise first


# --------------------------------------------------------------------------------------------- web
def scan_web(target: str, out_dir: str, timeout_s: float = 30.0, width: int = 1440, height: int = 900) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright
    url = target if re.match(r"^https?://", target, re.I) else "https://" + target
    rep: Dict[str, Any] = {"kind": "web", "url": url}
    t0 = time.perf_counter()
    with sync_playwright() as pw:
        br = launch_browser(pw, headless=True)
        try:
            ctx = br.new_context(viewport={"width": width, "height": height}, locale="en-US")
            page = ctx.new_page()
            t1 = time.perf_counter()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
            except Exception as e:
                rep["load_error"] = f"{type(e).__name__}: {str(e)[:140]}"
            rep["load_ms"] = ms(t1)
            with contextlib.suppress(Exception):
                page.wait_for_load_state("networkidle", timeout=6000)             # SPAs paint after the first load; bounded wait
            rep["settled_ms"] = ms(t1)
            t2 = time.perf_counter()
            data = page.evaluate(COLLECT_JS)
            rep["read_ms"] = ms(t2)
            os.makedirs(out_dir, exist_ok=True)
            shot = os.path.join(out_dir, "page.png")
            with contextlib.suppress(Exception):
                page.screenshot(path=shot)
                rep["screenshot"] = shot
            # menus that open on a click are NOT opened (read-only): the report says how many openers were seen
            rep.update(data)
        finally:
            br.close()
    rep["total_ms"] = ms(t0)
    return rep


def draw_boxes(rep: Dict[str, Any], top: int = 60) -> str:
    """The picture with each found control boxed and numbered - proof of what the scan saw."""
    shot = rep.get("screenshot")
    if not shot or not os.path.isfile(shot):
        return ""
    with contextlib.suppress(Exception):
        from PIL import Image, ImageDraw
        im = Image.open(shot).convert("RGB")
        d = ImageDraw.Draw(im)
        n = 0
        for c in rep["controls"]:
            if not c["inview"]:
                continue
            n += 1
            d.rectangle([c["x"], c["y"], c["x"] + c["w"], c["y"] + c["h"]], outline=(220, 30, 30), width=2)
            d.text((c["x"] + 2, max(0, c["y"] - 11)), str(n), fill=(220, 30, 30))
            if n >= top:
                break
        out = shot.replace("page.png", "page_controls.png")
        im.save(out)
        return out
    return ""


def digest_web(rep: Dict[str, Any]) -> Dict[str, Any]:
    cs = rep.get("controls", [])
    by_role: Dict[str, int] = {}
    for c in cs:
        by_role[c["role"]] = by_role.get(c["role"], 0) + 1
    labelled = [c for c in cs if c["label"]]
    found_keys: List[Tuple[str, str]] = []
    for c in cs:
        for src in (c["keys"], c["title"], c["label"]):
            m = SHORTCUT_RX.search(src or "")
            if m:
                found_keys.append((re.sub(r"\s+", "", m.group(1)).lower().replace("control", "ctrl").replace("command", "cmd"), c["label"] or c["title"]))
                break
    text = rep.get("text", "").lower()
    walls = []
    if (rep.get("http_status") or 0) >= 400:
        walls.append(f"the site refused this automated browser: HTTP {rep['http_status']} (reported, not worked around)")
    if rep.get("password") or (re.search(r"\b(sign in|log in|login)\b", text[:3000]) and len(cs) < 15):
        walls.append("login wall (only the logged-out page is visible)")
    if re.search(r"(accept all|accept cookies|we use cookies|cookie settings)", text[:6000]):
        walls.append("cookie banner on the page (not clicked)")
    if re.search(r"(verify you are human|captcha|are you a robot)", text[:6000]):
        walls.append("bot check (not attempted)")
    return {"controls": len(cs), "labelled": len(labelled), "roles": dict(sorted(by_role.items(), key=lambda kv: -kv[1])), "page_shortcuts": found_keys[:20], "walls": walls,
            "canvas_app": rep.get("canvases", 0) > 0 and len(cs) < 60}


# --------------------------------------------------------------------------------------------- desktop
def scan_desktop(target: str, budget: float, vision: bool) -> Dict[str, Any]:
    from core_organs import fast_scan
    t0 = time.perf_counter()
    rep = fast_scan.deep_scan(target, budget_s=budget, vision=vision)
    rep["_wall_ms"] = ms(t0)
    return rep


def digest_desktop(rep: Dict[str, Any]) -> Dict[str, Any]:
    tree, menus = rep.get("tree") or {}, rep.get("menus") or {}
    cap = rep.get("capability") or {}
    return {"seconds": rep.get("seconds"), "within_budget": rep.get("within_budget"), "budget_s": rep.get("budget_s_effective"), "nodes": tree.get("nodes"), "controls_mapped": tree.get("controls_mapped"),
            "regions": tree.get("regions"), "menu_commands": menus.get("commands"), "menu_with_path": menus.get("with_path"), "ribbon_tabs": (rep.get("ribbon") or {}).get("tabs"),
            "vision": (rep.get("vision") or {}).get("state"), "verdict": cap.get("verdict") if isinstance(cap, dict) else None, "closed_again": rep.get("closed")}


def desktop_labels(rep: Dict[str, Any], target: str, limit: int = 400) -> List[str]:
    labels: List[str] = []
    with contextlib.suppress(Exception):
        from core_organs import organ_48_app_behavior_model as bm
        model = bm.get_model()
        for c in model.commands(bm._app_key(target), limit=limit):
            lab = c.get("label") or c.get("name") or ""
            if lab:
                labels.append(lab)
    return labels


# --------------------------------------------------------------------------------------------- shared
def recognise(labels: Sequence[str], name: str, key: str, rag: Any, seen_chords: Sequence[Tuple[str, str]] = ()) -> Dict[str, Any]:
    t0 = time.perf_counter()
    out: Dict[str, Any] = {}
    with contextlib.suppress(Exception):
        from core_organs.rag import archetypes as A
        a = A.ArchetypeRouter().assess({"app": name, "title": name, "controls": list(labels)[:400]}, top=3)
        out = {"status": a["status"], "ranked": [(k, round(float(v), 3)) for k, v in a["ranked"][:3]], "margin": round(float(a.get("margin") or 0), 3)}
        if a["ranked"] and a["status"] in ("candidate", "weak_candidate"):
            top = a["ranked"][0][0]
            with contextlib.suppress(Exception):
                from core_organs.harvest import transfer_priors as TP
                P = TP.Priors.from_rag(rag)
                out["usually_has"] = P.expectations(top, key or name, [(act, ch) for ch, act in seen_chords], top=8)
    out["ms"] = ms(t0)
    return out


def teach_lines(rec: Dict[str, Any], digest: Dict[str, Any], rep: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    if rec.get("known") and rec.get("top"):
        out.append(f"From the pool ({rec['rows']} shortcuts, {rec['proven']} proven):")
        out += [f"  {c:<16} {a}   [{m}]" for c, a, m in rec["top"][:10]]
    if rep.get("kind") == "web":
        cs = [c for c in rep.get("controls", []) if c["label"] and c["inview"]]
        out.append("On this page, in the order they appear:")
        for c in cs[:15]:
            out.append(f"  {c['role']:<16} {c['label']}")
        if digest.get("page_shortcuts"):
            out.append("Shortcuts the page itself announces:")
            out += [f"  {k:<16} {lab}" for k, lab in digest["page_shortcuts"][:10]]
    return out


def scorecard(kind: str, digest: Dict[str, Any], rec: Dict[str, Any], rep: Dict[str, Any], recog: Dict[str, Any]) -> List[Tuple[bool, str]]:
    s: List[Tuple[Optional[bool], str]] = []
    if kind == "web":
        s.append((not rep.get("load_error") and (rep.get("http_status") or 200) < 400, f"page loaded ({rep.get('load_ms')} ms to first paint, {rep.get('settled_ms')} ms settled)" if not rep.get("load_error") else f"page did NOT load: {rep['load_error']}"))
        s.append((digest["controls"] >= 10, f"{digest['controls']} controls found ({digest['labelled']} with a readable label)"))
        s.append((digest["labelled"] >= 0.6 * max(1, digest["controls"]), f"label coverage {digest['labelled']}/{digest['controls']}"))
        s.append((not digest["walls"], "no login / bot wall in the way" if not digest["walls"] else "in the way: " + "; ".join(digest["walls"])))
        s.append((rep.get("read_ms", 99999) < 2000, f"controls read in {rep.get('read_ms')} ms"))
        if "openers_tried" in rep:
            n_rev = sum(r["n"] for r in rep.get("revealed", []))
            ex = rep.get("explore")
            if ex and (ex.get("coverage") or {}).get("buttons_seen"):
                cv = ex["coverage"]
                s.append((cv["buttons_pct"] >= 80.0, f"buttons / menus / tabs clicked: {cv['buttons_clicked']} of {cv['buttons_seen']} ({cv['buttons_pct']}%)"))
            if rep.get("media"):
                s.append((any(m.get("on_screen_text") or (m.get("transcript") or {}).get("segments") for m in rep["media"]), f"{len(rep['media'])} video(s) read: " + "; ".join(f"{len(m.get('on_screen_text', []))} on-screen lines, "
                          f"{(m.get('transcript') or {}).get('segments', 0)} spoken segments" for m in rep["media"])))
            if ex:
                s.append((ex["clicks"] > 0 and (ex["max_depth"] >= 2 or not ex["outcomes"]), f"deep exploration: {ex['clicks']} clicks, {ex['max_depth']} levels down, {len(ex['pages'])} extra pages, "
                          f"{sum(1 for k in ex['outcomes'] if 'dialog' in k)} kinds of dialog/menu outcomes, stopped by {ex['stopped_by']}"))
            else:
                s.append((rep["openers_opened"] > 0 or rep["openers_tried"] == 0, f"depth pass: opened {rep['openers_opened']} of {rep['openers_tried']} menus / tabs / dropdowns, revealed {n_rev} hidden controls"))
        if digest["canvas_app"]:
            s.append((False, f"drawing area is a canvas ({rep.get('canvases')}): its inside is pixels, a DOM scan cannot list what is drawn there"))
    else:
        s.append((bool(digest.get("within_budget")), f"scan took {digest.get('seconds')} s (budget {digest.get('budget_s')} s)"))
        s.append(((digest.get("controls_mapped") or 0) >= 10, f"{digest.get('controls_mapped')} controls mapped from {digest.get('nodes')} tree nodes, {digest.get('regions')} regions"))
        s.append(((digest.get("menu_commands") or 0) > 0, f"{digest.get('menu_commands')} menu commands ({digest.get('menu_with_path')} with their full menu path)"))
        s.append((None, f"app closed again: {digest.get('closed_again')} (only a window this run launched is closed; an app that was already open is left alone)"))
    s.append((True if rec.get("known") else None, f"pool already knew it: {rec.get('rows')} rows ({rec.get('proven')} proven)" if rec.get("known") else "new to the pool: this is a first contact, so there is nothing to recall (not a failure)"))
    if recog.get("ranked"):
        s.append((recog.get("status") in ("candidate", "weak_candidate"), f"recognised as '{recog['ranked'][0][0]}' ({recog['status']}, score {recog['ranked'][0][1]}, margin {recog['margin']})"))
    return s


def learn_into_pool(rag: Any, target: str, ex: Dict[str, Any]) -> Dict[str, Any]:
    """Put the explored map into the lexicon: one command per path that DID something ('Features > Inbox' -> opens a page). Trust 'web' = a lead read off a live page, nothing was verified by use."""
    host = re.sub(r"^https?://(www\.)?", "", target.strip().lower()).split("/")[0]
    key = "webapp:" + host
    n = 0
    for nd in ex.get("nodes", []):
        if nd["outcome"] in ("nothing visible happened", "unreachable", "could not click"):
            continue
        label = nd["path"][:120]
        with contextlib.suppress(Exception):
            rag.lex.add_command(key, label, source="web_explore", trust="web")
            n += 1
    return {"key": key, "commands": n}


def print_understanding(u: Dict[str, Any]) -> None:
    net, st, au, fl, sh, me = u["network"], u["stack"], u["auth"], u["site_files"], u["shortcut_sheet"], u["meaning"]
    print(f"[UNDERSTAND] reverse-engineered from the outside ({u['seconds_watching']} s of traffic watched)")
    print(f"   what it is   : {me['name']} - {me['description'][:150] or '(no description in the page)'}")
    print(f"   built with   : {', '.join(st.get('frameworks', [])) or 'no common framework fingerprint'}"
          + (f"  | platform hints: {', '.join(st.get('headers', {}).get('platform_hints', []))}" if st.get("headers", {}).get("platform_hints") else "")
          + ("  | PWA manifest" if st.get("manifest") else "") + ("  | service worker" if st.get("sw") else ""))
    print(f"   network      : {net['requests']} requests; " + ", ".join(f"{n} {k}" for k, n in sorted(net["by_kind"].items(), key=lambda kv: -kv[1])))
    for h in net["hosts"][:6]:
        print(f"                    {h['host']:<38} {h['kind']:<12} {h['n']:>4}  {h['types']}")
    for e in net["api_endpoints"][:8]:
        print(f"                    API {e['method']:<5} {e['host']}{e['path']}  x{e['n']}")
    if net["graphql_operations"]:
        print(f"                    GraphQL operations: {', '.join(list(net['graphql_operations'])[:8])}")
    if net["websockets"]:
        print(f"                    WebSockets: {', '.join(net['websockets'])}")
    print(f"   sign-in      : {au['reads_as']}" + (f"; single sign-on: {', '.join(au['sso_providers'])}" if au["sso_providers"] else "") + ("; password form" if au["password_form"] else "")
          + (f"; bot check: {', '.join(au['captcha'])}" if au["captcha"] else ""))
    if st.get("cookie_flags"):
        print(f"   cookies      : {st['cookie_flags']['n']} set before any login (names only); tracking-like: {', '.join(st['cookie_flags']['analytics_like']) or 'none recognised'}")
    if fl.get("robots"):
        print(f"   robots.txt   : {fl['robots']['disallow_rules']} disallow rules, {len(fl['robots']['sitemaps'])} sitemap(s)")
    if fl.get("sitemap"):
        print("   page types   : " + ", ".join(f"{p['prefix']} ({p['n']})" for p in fl["sitemap"]["page_types"][:8]) + f"   [{fl['sitemap']['urls_sampled']} urls sampled]")
    if sh.get("opened"):
        print(f"   shortcut '?' : the app opened a shortcut sheet: {len(sh['pairs'])} shortcuts read")
        for p in sh["pairs"][:10]:
            print(f"                    {p['keys']:<14} {p['action']}")
    else:
        print("   shortcut '?' : no shortcut sheet opened")
    kb = u.get("keyboard") or {}
    rr = u.get("_rea") or {}
    if rr:
        w, a = rr.get("web") or {}, rr.get("api") or {}
        if w.get("page"):
            p = w["page"]
            print(f"   REA page     : {p['scripts']} scripts ({p['script_bytes']:,} bytes, {p['source_maps']} with source maps), {p['dom_nodes']} DOM nodes, {len(p['same_site_paths'])} same-site URLs in the page, storage keys: {', '.join(p['local_storage_keys'][:5]) or 'none'}")
        if w.get("bundle"):
            print(f"   REA routes   : {len(w['bundle']['routes'])} route candidates in the code (application routes: {w['bundle']['coverage']}): {', '.join(w['bundle']['routes'][:6])}")
        if w.get("webmcp"):
            print(f"   REA WebMCP   : {w['webmcp']['status']}; tools the page declares: {', '.join(w['webmcp']['tools']) or 'none'}")
        if a.get("ok"):
            print(f"   REA API tools: {len(a['tools'])} on {a.get('origin')} ({sum(1 for t in a['tools'] if t['write'])} write, never executed), from {a['records']} recorded calls; {a.get('other_origin_groups', 0)} other-origin groups left out")
            for t in a["tools"][:6]:
                print(f"                    {t['method']:<6} {t['path']}  {t['name']}")
        elif a:
            print(f"   REA API tools: none ({a.get('error', '')[:100]})")
    if kb.get("tab_order"):
        print(f"   keyboard     : Tab reaches {len(kb['tab_order'])} controls in this order: " + " > ".join((t["label"] or t["tag"])[:18] for t in kb["tab_order"][:9]) + (" ..." if len(kb["tab_order"]) > 9 else ""))
    for h in kb.get("hotkeys", []):
        print(f"                    pressed {h['keys']}: {h['effect']}  -> {h['action']}")
    print("   HOW TO USE IT (built from the above, no model):")
    for l in me["lesson"]:
        print("     - " + l)
    print()


def understanding_markdown(target: str, u: Dict[str, Any], ex: Optional[Dict[str, Any]]) -> str:
    me, st, net, au, fl, sh = u["meaning"], u["stack"], u["network"], u["auth"], u["site_files"], u["shortcut_sheet"]
    fence = "`" * 3
    md = [f"# {me['name']}  ({target})", "", me["description"], "", "## How to use it", ""] + [f"- {l}" for l in me["lesson"]]
    md += ["", "## Built with", "", ", ".join(st.get("frameworks", [])) or "no common framework fingerprint", "", f"Headers: {st.get('headers', {})}", "",
           "## Network", "", f"{net['requests']} requests: {net['by_kind']}", ""]
    md += [f"- {h['host']}  {h['kind']}  x{h['n']}" for h in net["hosts"]]
    md += ["", "### API endpoints seen", ""] + [f"- {e['method']} {e['host']}{e['path']}  x{e['n']}" for e in net["api_endpoints"]]
    if net["graphql_operations"]:
        md += ["", "### GraphQL operations", "", ", ".join(net["graphql_operations"])]
    md += ["", "## Sign-in", "", au["reads_as"], f"SSO: {au['sso_providers']}  password form: {au['password_form']}  captcha: {au['captcha']}"]
    if fl:
        md += ["", "## Site files", "", fence, str(fl), fence]
    if sh.get("opened"):
        md += ["", "## Keyboard shortcuts (from its own '?' sheet)", ""] + [f"- {p['keys']}   {p['action']}" for p in sh["pairs"]]
    if ex:
        md += ["", "## Map found by clicking through it", "", fence] + ex.get("tree", [])[:200] + [fence]
    return "\n".join(md)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Scan, recognise and teach ANY app or web app, with timings and proof.")
    ap.add_argument("target", nargs="?", default="")
    ap.add_argument("--web", action="store_true")
    ap.add_argument("--desktop", action="store_true")
    ap.add_argument("--budget", type=float, default=20.0, help="desktop scan time budget in seconds")
    ap.add_argument("--vision", action="store_true", help="desktop: also run the slow vision pass in the background")
    ap.add_argument("--no-scan", action="store_true", help="only recall what the pool knows")
    ap.add_argument("--json", action="store_true", help="print the report as JSON as well")
    ap.add_argument("--show", action="store_true", help="do the scan ON SCREEN: visible window, live overlay, the depth pass opens menus / tabs / dropdowns where you can watch")
    ap.add_argument("--headless", action="store_true", help="--show without a window: the same deep exploration and reverse engineering, nothing on screen (for unattended runs)")
    ap.add_argument("--minimized", action="store_true", help="--show without being seen: a real browser window that starts MINIMIZED, no cursor overlay, nothing on screen (the same exploration)")
    ap.add_argument("--pace", type=float, default=0.35, help="--show: seconds per step (bigger = slower to watch)")
    ap.add_argument("--shallow", action="store_true", help="--show: only open each menu / tab one level (old behaviour) instead of digging all the way down")
    ap.add_argument("--learn", action="store_true", help="write what the deep exploration found into the knowledge pool (lexicon commands 'Menu > Item' as unverified leads)")
    ap.add_argument("--clicks", type=int, default=400, help="deep exploration: most clicks on BUTTONS / menus / tabs (anything that is not a plain link)")
    ap.add_argument("--link-clicks", type=int, default=-1, help="deep exploration: most clicks on plain links (default: a quarter of --clicks, at least 30)")
    ap.add_argument("--no-media", action="store_true", help="do not read videos (what they show and say)")
    ap.add_argument("--no-transcribe", action="store_true", help="read what a video SHOWS but do not fetch and transcribe its audio")
    ap.add_argument("--depth", type=int, default=6, help="deep exploration: how many levels down (menu > submenu > item ...)")
    ap.add_argument("--pages", type=int, default=25, help="deep exploration: most extra pages to explore")
    ap.add_argument("--explore-seconds", type=float, default=900.0, help="deep exploration: time limit")
    ap.add_argument("--hold", type=float, default=8.0, help="--show: seconds to keep the finished window up")
    a = ap.parse_args(argv)
    if not a.target:
        print(__doc__)
        return 2
    web = a.web or (not a.desktop and looks_like_web(a.target))
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(ROOT, "try_app", stamp)
    T0 = time.perf_counter()
    kind_txt = ("web app / website, " + ("a VISIBLE browser window, a pointer shows what it finds" if a.show else "headless browser, nothing shown on screen")) if web else \
               ("desktop app, " + ("scanned VISIBLY on your screen, the virtual cursor shows what it found" if a.show else "scanned in the background (minimized); add --show to watch it"))
    print(f"target: {a.target}   kind: {kind_txt}\n")
    rec = recall(a.target, web)
    rag = rec.pop("_rag", None)
    print(f"[1 RECALL  {rec['ms']:>6} ms] " + (f"pool knows '{rec['key']}': {rec['rows']} shortcuts, {rec['proven']} proven, {rec['leads']} leads" + (f", filed as {rec['filed_as']}" if rec.get("filed_as") else "") if rec.get("known") else "pool has nothing on this one yet"))
    rep: Dict[str, Any] = {"kind": "web" if web else "desktop"}
    digest: Dict[str, Any] = {}
    labels: List[str] = []
    boxed = ""
    if not a.no_scan:
        if web:
            try:
                if a.show:
                    from core_organs import try_app_show as TS
                    rep = TS.scan_web_show(a.target, out_dir, pace=a.pace, hold_s=0.0 if (a.headless or a.minimized) else a.hold, headless=a.headless, minimized=a.minimized, deep=not a.shallow, max_link_clicks=a.link_clicks, media=not a.no_media, transcribe_media=not a.no_transcribe, max_clicks=a.clicks, max_depth=a.depth, max_pages=a.pages, budget_s=a.explore_seconds)
                else:
                    rep = scan_web(a.target, out_dir)
            except Exception as e:
                print(f"[2 SCAN] failed: {type(e).__name__}: {str(e)[:200]}")
                return 1
            digest = digest_web(rep)
            boxed = draw_boxes(rep)
            labels = [c["label"] for c in rep.get("controls", []) if c["label"]]
            print(f"[2 SCAN    {rep['total_ms']:>6} ms] {digest['controls']} controls ({digest['labelled']} labelled): " + ", ".join(f"{n} {r}" for r, n in list(digest["roles"].items())[:6])
                  + f"  | canvases {rep.get('canvases')}, frames {rep.get('iframes')}   [load {rep.get('load_ms')} ms, settled {rep.get('settled_ms')} ms, read {rep.get('read_ms')} ms]")
            for w in digest["walls"]:
                print(f"             note: {w}")
            ex = rep.get("explore")
            if ex:
                print(f"             DEEP: {ex['clicks']} clicks, {ex['max_depth']} levels down, {len(ex['pages'])} extra pages, stopped by: {ex['stopped_by']};  outcomes: " + ", ".join(f"{n} {k}" for k, n in sorted(ex["outcomes"].items(), key=lambda kv: -kv[1])))
                cov = ex.get("coverage") or {}
                if cov:
                    print(f"             BUTTONS / MENUS / TABS: {cov.get('buttons_clicked')} of {cov.get('buttons_seen')} clicked ({cov.get('buttons_pct')}%)   |   plain LINKS: {cov.get('links_clicked')} of {cov.get('links_seen')} "
                          f"({cov.get('links_pct')}%)   |   not clicked, by reason: {cov['not_clicked']}")
                    if cov.get("buttons_left"):
                        print("               buttons still unclicked: " + "; ".join(cov["buttons_left"][:8]))
                    if cov["left_over_sample"]:
                        print("               still waiting when it stopped: " + "; ".join(cov["left_over_sample"][:8]))
                for ln in ex["tree"][:60]:
                    print("               " + ln)
                if len(ex["tree"]) > 60:
                    print(f"               ... {len(ex['tree']) - 60} more in report.json")
                if ex.get("external"):
                    print(f"             links to other sites (not followed): {', '.join(ex['external'][:5])}")
            for m in rep.get("media", []):
                print(f"             VIDEO: {m.get('summary', '')[:230]}")
                if m.get("spoken_shortcuts"):
                    print("                    shortcuts the speaker named: " + "; ".join(f"{x['keys']} = {x['action']}" for x in m["spoken_shortcuts"][:5]))
            for r in ([] if ex else rep.get("revealed", [])[:12]):
                print(f"             opened '{r['opener'][:30]}' -> {r['n']} hidden controls: " + ", ".join(x.split(': ', 1)[-1][:16] for x in r["found"][:5]))
            if rep.get("skipped_risky"):
                print(f"             left alone as risky: {', '.join(x[:22] for x in rep['skipped_risky'][:8])}")
        else:
            try:
                if a.show:
                    from core_organs import try_app_show_desktop as TD
                    t_d = time.perf_counter()
                    rep = TD.scan_desktop_show(a.target, a.budget, a.vision, pace=a.pace * 2.5, hold_s=a.hold)
                    rep.setdefault("_wall_ms", ms(t_d))
                else:
                    rep = scan_desktop(a.target, a.budget, a.vision)
            except Exception as e:
                print(f"[2 SCAN] failed: {type(e).__name__}: {str(e)[:300]}")
                return 1
            rep["kind"] = "desktop"
            digest = digest_desktop(rep)
            labels = desktop_labels(rep, a.target)
            print(f"[2 SCAN    {rep.get('_wall_ms', 0):>6} ms] " + ", ".join(f"{k}={v}" for k, v in digest.items() if v is not None))
    key = rec.get("key", "") or re.sub(r"[^a-z0-9.]+", "", a.target.lower())
    seen = digest.get("page_shortcuts", []) if web else []
    recog = recognise(labels, a.target, key, rag, [(lab, k) for k, lab in seen]) if labels and rag is not None else {}
    if recog.get("ranked"):
        print(f"[3 RECOGNISE {recog['ms']:>4} ms] looks like: " + ", ".join(f"{k} ({v})" for k, v in recog["ranked"]) + f"   status={recog['status']}")
        if recog.get("usually_has"):
            print("             apps of this kind usually also have (not shown by this one yet):")
            for e in recog["usually_has"][:6]:
                print(f"               {e['chord']:<16} {e['action_words']}   ({e['apps']} apps)")
    elif labels:
        print("[3 RECOGNISE] not enough label evidence to place it")
    und = rep.get("understanding")
    if und:
        if rep.get("rea"):
            und["_rea"] = rep["rea"]
        print_understanding(und)
    t4 = time.perf_counter()
    tl = teach_lines(rec, digest, rep)
    print(f"[4 TEACH   {ms(t4):>6} ms]")
    for ln in tl:
        print("   " + ln)
    if not a.no_scan:
        print("\nSCORECARD")
        sc = scorecard(rep["kind"], digest, rec, rep, recog)
        for ok, line in sc:
            print(f"  [{'INFO' if ok is None else 'PASS' if ok else 'FAIL'}] {line}")
        graded = [ok for ok, _ in sc if ok is not None]
        print(f"  {sum(1 for ok in graded if ok)}/{len(graded)} graded checks passed. Total {ms(T0)} ms.")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
            json.dump({"target": a.target, "labels": labels[:500], "recall": rec, "digest": digest, "recognise": recog, "scorecard": sc, "understanding": rep.get("understanding"),
                       "scan": {k: v for k, v in rep.items() if k not in ("controls", "text", "_measure_rows", "understanding")}}, f, indent=1, default=str)
            if und:
                with open(os.path.join(out_dir, "UNDERSTANDING.md"), "w", encoding="utf-8") as f2:
                    f2.write(understanding_markdown(a.target, und, rep.get("explore")))
        print(f"\nproof folder: {out_dir}" + (f"\n  picture with every found control boxed: {boxed}" if boxed else ""))
    if a.learn and rep.get("explore") and rag is not None:
        wrote = learn_into_pool(rag, a.target, rep["explore"])
        print(f"\nLEARN: wrote {wrote['commands']} paths of '{wrote['key']}' into the pool as unverified leads (lexicon)")
    if a.json:
        print(json.dumps({"recall": rec, "digest": digest, "recognise": recog}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
