"""
try_app_show -- the SAME scan as try_app, but done where you can WATCH it: a visible browser window with a live overlay.

You see, in order:
  1 LOAD     the page opens in a real window
  2 SWEEP    a blue pointer glides from control to control (nothing is outlined or highlighted); a small status panel (bottom right) counts them
  3 SCROLL   the page scrolls down in steps; the pointer visits what was below the fold
  4 OPEN     the depth pass: every control that opens something (menu, dropdown, tab, disclosure) is clicked, the pointer goes to each NEW control it reveals and they are listed in the panel,
             then it is closed again (Escape / click again; a page change goes Back)
  5 SUMMARY  what was learned, the shortcuts the page itself announces, how the app was recognised

Safety (the whole pass is read-only in effect): only OPENERS are clicked (aria-haspopup / aria-expanded / tabs / <summary>); never a link, a field, a submit; anything whose name suggests an
irreversible or account action (delete, sign out, pay, buy, submit, send, publish, post, confirm, reset, subscribe, install, download, share, invite, export, save, sign up, accept ...) is skipped
and listed as SKIPPED. Nothing is typed. No login. The window is a throw-away browser profile, so none of your own cookies or sessions are involved.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

DANGER = re.compile(r"\b(delete|remove|sign\s*out|log\s*out|logout|pay|buy|purchase|checkout|order|submit|send|publish|post|confirm|erase|clear|reset|unsubscribe|subscribe|cancel|upgrade|donate|install|"
                    r"download|share|invite|export|save|sign\s*up|register|create\s+account|accept|agree|allow|deny|reject|discard|undo|redo|trash|archive|block|report|follow|like|buy now)\b", re.I)

SETUP_JS = r"""
() => {
  if (window.__hj) return true;
  const hud = document.createElement('div');
  hud.id = '__hj_hud';
  hud.style.cssText = 'position:fixed;bottom:10px;right:10px;width:380px;max-height:78vh;overflow:hidden;z-index:2147483647;background:rgba(15,18,28,.93);color:#e8ecf5;font:12px/1.45 Consolas,monospace;padding:10px 12px;border-radius:8px;border:1px solid #4a90ff;pointer-events:none;box-shadow:0 4px 18px rgba(0,0,0,.5)';
  const cur = document.createElement('div');
  cur.id = '__hj_cur';
  cur.style.cssText = 'position:fixed;left:-60px;top:-60px;width:26px;height:30px;z-index:2147483646;pointer-events:none;display:none;transition:left .32s cubic-bezier(.4,0,.2,1),top .32s cubic-bezier(.4,0,.2,1);filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))';
  { const NS = 'http://www.w3.org/2000/svg'; const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('width', '26'); svg.setAttribute('height', '30'); svg.setAttribute('viewBox', '0 0 26 30');
    const path = document.createElementNS(NS, 'path'); path.setAttribute('d', 'M2 2 L2 24 L8 18.5 L12.5 28 L16.5 26.2 L12 17 L20 17 Z'); path.setAttribute('fill', '#2f7bff'); path.setAttribute('stroke', '#ffffff');
    path.setAttribute('stroke-width', '2'); path.setAttribute('stroke-linejoin', 'round'); svg.appendChild(path); cur.appendChild(svg); }
  document.documentElement.appendChild(cur); document.documentElement.appendChild(hud);
  window.__hj = {
    hud(title, lines) { while (hud.firstChild) hud.removeChild(hud.firstChild);                       // no innerHTML: pages with Trusted Types (YouTube, Google) refuse it
      const t = document.createElement('div'); t.style.cssText = 'font:bold 13px Consolas,monospace;color:#7db2ff;margin-bottom:4px'; t.textContent = title; hud.appendChild(t);
      for (const l of lines) { const d = document.createElement('div'); d.textContent = String(l); hud.appendChild(d); } },
    // the ONLY pointing aid is the cursor: it glides to the middle of the control (document coords in, viewport coords out); nothing is outlined or highlighted
    box(x, y, w, h) { cur.style.display = 'block'; cur.style.left = (x + w / 2 - scrollX) + 'px'; cur.style.top = (y + h / 2 - scrollY) + 'px'; },
    keep() {},
    hide() { cur.style.display = 'none'; }
  };
  return true;
}
"""

COLLECT_JS = r"""
() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 3 && r.height > 3 && s.visibility !== 'hidden' && s.display !== 'none' && r.bottom > -4000 && r.top < 12000; };
  const sel = 'button, a[href], input, select, textarea, summary, [role=button], [role=menuitem], [role=menuitemcheckbox], [role=menuitemradio], [role=tab], [role=link], [role=checkbox], [role=switch], [role=option], [role=combobox], [role=slider], [role=treeitem], [contenteditable=true], [aria-haspopup], [aria-expanded]';
  window.__hjn = window.__hjn || 0;
  const out = [];
  // web components keep their buttons inside open shadow roots (YouTube, Salesforce, many design systems): walk into every one of them
  const deepAll = (selector) => { const found = []; const walk = (root) => { for (const e of root.querySelectorAll(selector)) found.push(e);
      for (const h of root.querySelectorAll('*')) if (h.shadowRoot) walk(h.shadowRoot); }; walk(document); return found; };
  for (const e of deepAll(sel)) {
    if (e.closest('#__hj_hud')) continue;
    if (!vis(e)) continue;
    if (!e.dataset.hjId) e.dataset.hjId = String(++window.__hjn);
    const r = e.getBoundingClientRect();
    const label = (e.getAttribute('aria-label') || e.innerText || e.getAttribute('title') || e.getAttribute('placeholder') || e.getAttribute('alt') || e.value || '').replace(/\s+/g, ' ').trim().slice(0, 80);
    const role = e.getAttribute('role') || (e.tagName === 'A' ? 'link' : e.tagName === 'INPUT' ? (e.type || 'text') + ' input' : e.tagName.toLowerCase());
    const hp = e.getAttribute('aria-haspopup'); const ex = e.getAttribute('aria-expanded');
    const opener = (hp && hp !== 'false') || ex === 'false' || role === 'tab' || e.tagName === 'SUMMARY' || role === 'combobox';
    const zone = e.closest('footer, [role=contentinfo]') ? 'footer' : e.closest('nav, [role=navigation], header, [role=banner], aside, [role=complementary], [role=menu], [role=menubar], [role=tablist], [role=toolbar]') ? 'nav' : 'body';
    out.push({id: e.dataset.hjId, tag: e.tagName.toLowerCase(), role, label, title: (e.getAttribute('title') || '').slice(0, 80), keys: e.getAttribute('aria-keyshortcuts') || '',
              x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height), inview: r.top >= 0 && r.bottom <= innerHeight, opener: !!opener,
              expanded: ex, haspopup: hp || '', zone, href: e.tagName === 'A' ? (e.href || '') : ''});
  }
  if (out.length < 60) {
    // the page offers few semantic controls (buttons / links / menu items): it is probably drawn from plain <div>s. Those are still clickable: they are the outermost elements the page gives a pointing-hand cursor
    const have = new Set(out.map(o => o.id));
    for (const e of deepAll('div, span, li, a, td, img, svg, i, label, p')) {
      if (e.closest('#__hj_hud') || (e.dataset.hjId && have.has(e.dataset.hjId)) || !vis(e)) continue;
      if (getComputedStyle(e).cursor !== 'pointer') continue;
      const par = e.parentElement;
      if (par && par.tagName !== 'BODY' && getComputedStyle(par).cursor === 'pointer') continue;
      const r = e.getBoundingClientRect();
      if (r.width < 8 || r.height < 8 || r.width > innerWidth * 0.9 || r.height > innerHeight * 0.9) continue;
      const label = (e.getAttribute('aria-label') || e.innerText || e.getAttribute('title') || e.getAttribute('alt') || '').replace(/\s+/g, ' ').trim().slice(0, 80);
      if (!label) continue;
      if (!e.dataset.hjId) e.dataset.hjId = String(++window.__hjn);
      out.push({id: e.dataset.hjId, tag: e.tagName.toLowerCase(), role: 'clickable', label, title: '', keys: '', x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height),
                inview: r.top >= 0 && r.bottom <= innerHeight, opener: false, expanded: null, haspopup: '', zone: e.closest('footer') ? 'footer' : e.closest('nav, header, aside, [role=toolbar], [role=menubar]') ? 'nav' : 'body', href: ''});
      if (out.length > 400) break;
    }
  }
  return {controls: out, canvases: document.querySelectorAll('canvas').length, iframes: document.querySelectorAll('iframe').length,
          password: !!document.querySelector('input[type=password]'), title: document.title, url: location.href, text: (document.body && document.body.innerText || '').slice(0, 20000),
          scrollY: scrollY, height: document.documentElement.scrollHeight, vh: innerHeight};
}
"""


FIND_JS = r"""
([role, label, x, y]) => {
  const sel = 'button, a[href], input, select, textarea, summary, [role=button], [role=menuitem], [role=menuitemcheckbox], [role=menuitemradio], [role=tab], [role=link], [role=checkbox], [role=switch], [role=option], [role=combobox], [role=slider], [role=treeitem], [contenteditable=true], [aria-haspopup], [aria-expanded]';
  const deepAll = (selector) => { const found = []; const walk = (root) => { for (const e of root.querySelectorAll(selector)) found.push(e); for (const h of root.querySelectorAll('*')) if (h.shadowRoot) walk(h.shadowRoot); }; walk(document); return found; };
  window.__hjn = window.__hjn || 0;
  let best = null, bd = 1e9;
  for (const e of deepAll(sel)) {
    const lab = (e.getAttribute('aria-label') || e.innerText || e.getAttribute('title') || e.getAttribute('placeholder') || e.getAttribute('alt') || e.value || '').replace(/\s+/g, ' ').trim().slice(0, 80);
    if (lab !== label) continue;
    const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    if (!(r.width > 3 && r.height > 3 && s.visibility !== 'hidden' && s.display !== 'none')) continue;
    const tag = e.tagName.toLowerCase();
    const rl = e.getAttribute('role') || (tag === 'a' ? 'link' : tag === 'input' ? (e.type || 'text') + ' input' : tag);
    if (rl !== role) continue;
    const d = Math.abs(r.left + scrollX - x) + Math.abs(r.top + scrollY - y);
    if (d < bd) { bd = d; best = e; }
  }
  if (!best && role === 'clickable') {
    for (const e of deepAll('div, span, li, a, td, img, svg, i, label, p')) {
      const lab = (e.getAttribute('aria-label') || e.innerText || e.getAttribute('title') || e.getAttribute('alt') || '').replace(/\s+/g, ' ').trim().slice(0, 80);
      if (lab !== label) continue;
      const r = e.getBoundingClientRect(); const st = getComputedStyle(e);
      if (!(r.width > 3 && r.height > 3 && st.visibility !== 'hidden' && st.display !== 'none') || st.cursor !== 'pointer') continue;
      const d = Math.abs(r.left + scrollX - x) + Math.abs(r.top + scrollY - y);
      if (d < bd) { bd = d; best = e; }
    }
  }
  if (!best || bd > 600) return null;
  if (!best.dataset.hjId) best.dataset.hjId = String(++window.__hjn);
  const r = best.getBoundingClientRect();
  return {id: best.dataset.hjId, role, label, x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height), tag: best.tagName.toLowerCase(), title: (best.getAttribute('title') || '').slice(0, 80),
          href: best.tagName === 'A' ? (best.href || '') : '', opener: false, keys: '', expanded: best.getAttribute('aria-expanded'), haspopup: best.getAttribute('aria-haspopup') || '', inview: r.top >= 0 && r.bottom <= innerHeight};
}
"""


def _key(c: Dict[str, Any]) -> Tuple[Any, ...]:
    return (c["role"], c["label"], c["x"] // 8, c["y"] // 8)


def scan_web_show(target: str, out_dir: str, pace: float = 0.35, max_open: int = 14, max_sweep: int = 80, hold_s: float = 6.0,
                  say: Callable[[str], None] = print, headless: bool = False, deep: bool = True, max_clicks: int = 400, max_depth: int = 6, max_pages: int = 25,
                  budget_s: float = 900.0, understand: bool = True, media: bool = True, transcribe_media: bool = True, max_link_clicks: int = -1,
                  max_media: int = 3, rea: bool = True, minimized: bool = False) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright
    if minimized:                  # a minimized Chromium window drops trusted mouse input (measured: link clicks do nothing, "element is stable" never completes) and a restored off-screen one steals focus;
        headless = True            # headless is the silent equivalent: same browser engine, real input, nothing on screen, no overlay
    url = target if re.match(r"^https?://", target, re.I) else "https://" + target
    rep: Dict[str, Any] = {"kind": "web", "url": url, "show": not headless, "minimized": bool(minimized)}
    known: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    revealed: List[Dict[str, Any]] = []
    skipped: List[str] = []
    log: List[str] = []
    t0 = time.perf_counter()

    def ms() -> int:
        return int((time.perf_counter() - t0) * 1000)

    with sync_playwright() as pw:
        from core_organs.try_app import launch_browser
        rea_on = False
        har_dir = har_path = ""
        port = 0
        if rea:
            with contextlib.suppress(Exception):
                from core_organs import rea_bridge as RB
                if RB.available():
                    import socket
                    sk = socket.socket()
                    sk.bind(("127.0.0.1", 0))
                    port = sk.getsockname()[1]
                    sk.close()
                    import tempfile
                    har_dir = tempfile.mkdtemp(prefix="hj_har_")
                    har_path = os.path.join(har_dir, "session.har")
                    rea_on = True
        extra_args = [] if headless else ["--window-position=30,20", "--window-size=1500,940"]
        extra_args += [f"--remote-debugging-port={port}"] if rea_on else []
        br = launch_browser(pw, headless=headless, args=extra_args)
        try:
            har_kw: Dict[str, Any] = {}
            if rea_on:                                                                                # record the session so REA can turn the site's API calls into tools (static assets and trackers are left out)
                har_kw = dict(record_har_path=har_path, record_har_mode="minimal", record_har_content="embed", record_har_url_filter=re.compile(
                    r"^https?://(?!.*(?:google-analytics|googletagmanager|doubleclick|googlesyndication|facebook\.net|hotjar|segment\.|sentry|datadog|newrelic|fonts\.g|gstatic|cloudfront|akamai|cdn\.|fastly|jsdelivr|unpkg|cdnjs|telemetry))"
                    r".*(?<!\.js)(?<!\.css)(?<!\.png)(?<!\.jpg)(?<!\.jpeg)(?<!\.gif)(?<!\.svg)(?<!\.woff2)(?<!\.woff)(?<!\.ico)(?<!\.webp)(?<!\.map)(?<!\.mp4)(?<!\.webm)$"))
            ctx = (br.new_context(viewport={"width": 1440, "height": 820}, locale="en-US", **har_kw) if headless else br.new_context(no_viewport=True, locale="en-US", **har_kw))
            page = ctx.new_page()
            sp = None
            if not headless:                                                                       # the Hojaiga virtual cursor (system overlay) points; the in-page arrow is the fallback
                from core_organs.try_app_pointer import ScreenPointer
                sp = ScreenPointer()
                if not sp.start():
                    say(f"  [show] virtual cursor overlay unavailable ({sp.err}); using the in-page pointer")
                    sp = None
            U = None
            if understand:
                from core_organs.try_app_understand import Understander
                U = Understander(page, ctx, url)
            origin = re.match(r"^(https?://[^/]+)", url).group(1)

            def hud(title: str, lines: List[str]) -> None:
                with contextlib.suppress(Exception):
                    page.evaluate(SETUP_JS)
                    page.evaluate("([t,l]) => window.__hj.hud(t,l)", [title, lines[-14:]])

            def point(c: Dict[str, Any], color: str = "#ff2d2d", label: str = "") -> None:
                if sp is not None and sp.move(page, c):
                    return
                with contextlib.suppress(Exception):
                    page.evaluate(SETUP_JS)
                    page.evaluate("([x,y,w,h,l,c]) => window.__hj.box(x,y,w,h,l,c)", [c["x"], c["y"], c["w"], c["h"], label or f"{c['role']}: {c['label']}"[:70], color])

            def keep(c: Dict[str, Any], color: str = "#ff2d2d") -> None:
                with contextlib.suppress(Exception):
                    page.evaluate("([x,y,w,h,c]) => window.__hj.keep(x,y,w,h,c)", [c["x"], c["y"], c["w"], c["h"], color])

            def collect() -> Dict[str, Any]:
                """Read the page's controls; a click that starts a navigation destroys the page context mid-read, so wait for it to settle and read again."""
                last: Optional[Exception] = None
                for _ in range(5):
                    try:
                        page.evaluate(SETUP_JS)
                        return page.evaluate(COLLECT_JS)
                    except Exception as e:
                        last = e
                        if "context was destroyed" not in str(e) and "navigat" not in str(e).lower() and "Target closed" not in str(e):
                            raise
                        with contextlib.suppress(Exception):
                            page.wait_for_load_state("domcontentloaded", timeout=5000)
                        time.sleep(0.4)
                raise last if last else RuntimeError("collect failed")

            # ---- 1 LOAD
            say(f"  [show] 1 LOAD   {url}")
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                rep["http_status"] = resp.status if resp else None
                host = urlparse(url).netloc
                if resp is not None and resp.status >= 400 and host.count(".") == 1:                  # some sites only answer on www.: try that ONE variant, nothing cleverer
                    alt = url.replace("//" + host, "//www." + host, 1)
                    resp2 = page.goto(alt, wait_until="domcontentloaded", timeout=30000)
                    rep["http_status_first_try"] = resp.status
                    rep["http_status"] = resp2.status if resp2 else None
                    if resp2 is not None and resp2.status < 400:
                        rep["retried_as"] = alt
            except Exception as e:
                rep["load_error"] = f"{type(e).__name__}: {str(e)[:140]}"
            with contextlib.suppress(Exception):
                page.wait_for_load_state("networkidle", timeout=6000)
            rep["settled_ms"] = ms()
            hud("HOJAIGA SCAN  1/5 LOAD", [f"{url}", f"loaded in {rep['settled_ms']} ms"])
            time.sleep(pace * 2)
            data = collect()
            first = data["controls"]
            # ---- 2 SWEEP
            say(f"  [show] 2 SWEEP  {len(first)} controls on the first screen")
            seen_n = 0
            for c in sorted(first, key=lambda c: (c["y"] // 40, c["x"])):
                if seen_n >= max_sweep:
                    break
                k = _key(c)
                if k in known:
                    continue
                known[k] = c
                seen_n += 1
                point(c, "#ff2d2d", f"#{seen_n} {c['role']}: {c['label']}"[:70])
                log.append(f"#{seen_n} {c['role']}: {c['label'][:34]}")
                hud(f"HOJAIGA SCAN  2/5 SWEEP  ({seen_n}/{len(first)})", log)
                keep(c)
                time.sleep(pace * 0.45)
            with contextlib.suppress(Exception):
                page.evaluate("() => window.__hj.hide()")
            # ---- 3 SCROLL
            say("  [show] 3 SCROLL  reading below the fold")
            vh = data.get("vh", 800)
            added = 0
            for step in range(1, 7):
                if step * vh * 0.85 > data.get("height", 0):
                    break
                page.evaluate("(y) => window.scrollTo({top: y, behavior: 'smooth'})", int(step * vh * 0.85))
                time.sleep(pace * 1.6)
                d2 = collect()
                new = [c for c in d2["controls"] if _key(c) not in known]
                for c in new:
                    known[_key(c)] = c
                    keep(c)
                added += len(new)
                hud(f"HOJAIGA SCAN  3/5 SCROLL  (+{added} below the fold)", log + [f"scroll {step}: +{len(new)} controls"])
            page.evaluate("() => window.scrollTo({top: 0, behavior: 'smooth'})")
            time.sleep(pace * 2)
            # ---- 4 DEEP EXPLORE (default): click what opens, click what is inside it, down to max_depth, come back
            cands, opened = [], 0
            if deep:
                from core_organs.try_app_explore import Explorer
                data = collect()
                say(f"  [show] 4 DEEP   clicking through menus, dialogs, pages and child windows (<= {max_clicks} clicks, depth {max_depth}, {max_pages} pages, {budget_s:.0f} s)")
                def find_one(role: str, label: str, x: int, y: int) -> Optional[Dict[str, Any]]:
                    for _ in range(3):
                        try:
                            page.evaluate(SETUP_JS)
                            return page.evaluate(FIND_JS, [role, label, x, y])
                        except Exception as e:
                            if "context was destroyed" not in str(e) and "navigat" not in str(e).lower():
                                raise
                            with contextlib.suppress(Exception):
                                page.wait_for_load_state("domcontentloaded", timeout=5000)
                    return None
                transcribed = {"n": 0}

                def media_cb() -> Optional[Dict[str, Any]]:
                    """A player is on the page: read what it shows (muted, sampled, OCR) and says (first 2.5 minutes, local speech recognition) - for the first two players only the speech."""
                    from core_organs.harvest import web_media as WM
                    if not WM.find_media(page):
                        return None
                    hud("HOJAIGA  WATCHING A VIDEO", ["muted; sampling the picture", "reading the text on screen", "transcribing the first minutes locally"])
                    want = transcribe_media and transcribed["n"] < 2
                    r = WM.understand_media(page, frames=4, gap_s=2.5, transcript_seconds=150 if want else 0, want_transcript=want, out_dir=os.path.join(out_dir, "media"))
                    if r and (r.get("transcript") or {}).get("segments"):
                        transcribed["n"] += 1
                    return r
                ex = Explorer(page, ctx, page.url, collect, point, hud, DANGER, finder=find_one, max_links=max_link_clicks, media_cb=media_cb if media else None, max_media=max_media, pace=pace, max_clicks=max_clicks, max_depth=max_depth, max_pages=max_pages, budget_s=budget_s, say=say)
                res = ex.run(data["controls"])
                for c in res["controls"]:
                    known.setdefault(_key(c), c)
                for nd in res["nodes"]:
                    if nd.get("revealed"):
                        revealed.append({"opener": nd["path"], "found": nd["revealed"], "n": nd["n_new"]})
                skipped = res["skipped_risky"]
                opened = sum(1 for nd in res["nodes"] if nd["outcome"] not in ("nothing visible happened", "unreachable", "could not click"))
                rep["explore"] = {k: v for k, v in res.items() if k != "controls"}
                rep["media"] = res.get("media", [])
                rep["openers_tried"] = res["clicks"]
                cands = [None] * res["clicks"]
            else:
                # ---- 4 OPEN
                data = collect()
                cands = []
                for c in data["controls"]:
                    if not c["opener"] or c["tag"] in ("input", "textarea"):
                        continue
                    name = c["label"] or c["title"]
                    if DANGER.search(name or ""):
                        skipped.append(name)
                        continue
                    if c["tag"] == "a":
                        continue
                    cands.append(c)
                cands = cands[:max_open]
                say(f"  [show] 4 OPEN   {len(cands)} openers to try ({len(skipped)} skipped as risky: {', '.join(s[:20] for s in skipped[:4])})")
                opened = 0
                for c in cands:
                    name = c["label"] or c["title"] or c["role"]
                    before_url = page.url
                    before = {_key(x) for x in collect()["controls"]}
                    point(c, "#ff9d00", f"OPENING: {name}"[:70])
                    hud("HOJAIGA SCAN  4/5 OPEN  (depth)", log[-6:] + [f"opening '{name[:40]}'"])
                    time.sleep(pace)
                    try:
                        page.locator(f"[data-hj-id='{c['id']}']").first.click(timeout=2500)
                    except Exception as e:
                        log.append(f"could not open '{name[:30]}'")
                        continue
                    time.sleep(pace * 1.4)
                    after = collect()
                    if page.url.split("#")[0] != before_url.split("#")[0]:
                        with contextlib.suppress(Exception):
                            page.go_back(wait_until="domcontentloaded", timeout=8000)
                        log.append(f"'{name[:28]}' left the page - went Back")
                        continue
                    new = [x for x in after["controls"] if _key(x) not in before and _key(x) not in known]
                    opened += 1
                    for x in new:
                        known[_key(x)] = x
                        keep(x, "#ff9d00")
                    if new:
                        revealed.append({"opener": name, "found": [f"{x['role']}: {x['label']}" for x in new[:40]], "n": len(new)})
                        log.append(f"'{name[:26]}' revealed {len(new)}: " + ", ".join(x["label"][:14] for x in new[:4] if x["label"]))
                        for x in new[:12]:
                            point(x, "#ff9d00", f"{x['role']}: {x['label']}"[:70])
                            hud("HOJAIGA SCAN  4/5 OPEN  (revealed)", log[-9:])
                            time.sleep(pace * 0.35)
                    else:
                        log.append(f"'{name[:28]}' opened nothing new")
                    with contextlib.suppress(Exception):
                        page.keyboard.press("Escape")
                        time.sleep(0.15)
                        st = page.locator(f"[data-hj-id='{c['id']}']").first.get_attribute("aria-expanded")
                        if st == "true":
                            page.locator(f"[data-hj-id='{c['id']}']").first.click(timeout=1500)
                    time.sleep(pace * 0.5)
            with contextlib.suppress(Exception):
                page.evaluate("() => window.__hj.hide()")
            final = collect()
            rep.update({k: final[k] for k in ("canvases", "iframes", "password", "title", "text", "height")})
            allc = list(known.values())
            rep["controls"] = [dict(c, inview=True) for c in allc]
            rep["revealed"] = revealed
            rep["skipped_risky"] = skipped
            rep["openers_tried"] = len(cands)
            rep["openers_opened"] = opened
            # ---- 4b UNDERSTAND: network, stack, sign-in, site map, shortcut sheet, plain-language meaning
            if U is not None:
                say("  [show] 4b UNDERSTAND  reading the network traffic, the stack, the sign-in, robots / sitemap and the shortcut sheet")
                hud("HOJAIGA  4b UNDERSTAND", ["network + stack + sign-in", "robots.txt / sitemap", "keyboard shortcut sheet ('?')"])
                rep["understanding"] = U.finish(rep, rep.get("explore"), [c["label"] for c in allc if c["label"]])
            # ---- 4c REA: what the page is made of (scripts, routes in the code, same-site URLs, WebMCP), read with evidence through the browser's debug port
            if rea_on:
                say("  [show] 4c REA   reading the page's scripts, routes and structure with REA")
                hud("HOJAIGA  4c REA", ["scripts + routes in the code", "same-site URLs in the page", "tools the page declares"])
                with contextlib.suppress(Exception):
                    page.goto(page.url if urlparse(page.url).netloc == urlparse(url).netloc else url, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(1.0)
                    rep["rea"] = {"web": RB.web_static(f"http://127.0.0.1:{port}", origin="{0.scheme}://{0.netloc}".format(urlparse(page.url)))}
            # ---- 5 SUMMARY
            roles: Dict[str, int] = {}
            for c in allc:
                roles[c["role"]] = roles.get(c["role"], 0) + 1
            sumlines = [f"{len(allc)} controls mapped", ", ".join(f"{n} {r}" for r, n in sorted(roles.items(), key=lambda kv: -kv[1])[:5]),
                        f"{opened} of {len(cands)} openers opened, {sum(r['n'] for r in revealed)} hidden controls revealed", f"{len(skipped)} risky ones left alone",
                        f"scan took {ms() / 1000:.1f} s"]
            hud("HOJAIGA SCAN  5/5 DONE", sumlines)
            say("  [show] 5 DONE   " + " | ".join(sumlines[:3]))
            os.makedirs(out_dir, exist_ok=True)
            shot = os.path.join(out_dir, "page_show.png")
            with contextlib.suppress(Exception):
                page.screenshot(path=shot)
                rep["screenshot_show"] = shot
            time.sleep(max(0.0, hold_s))
        finally:
            with contextlib.suppress(Exception):
                if sp is not None:
                    sp.stop()
            with contextlib.suppress(Exception):
                ctx.close()                                                                         # closing the context is what writes the recorded session (HAR) to disk
            br.close()
    if rea_on:                                                                                      # the recording is complete once the browser is closed: REA derives the API tools from it, then it is deleted
        with contextlib.suppress(Exception):
            rep.setdefault("rea", {})["api"] = RB.api_tools(har_path, name=urlparse(url).netloc)
        shutil.rmtree(har_dir, ignore_errors=True)
    rep["total_ms"] = ms()
    rep["load_ms"] = rep.get("settled_ms")
    rep["read_ms"] = 0
    return rep
