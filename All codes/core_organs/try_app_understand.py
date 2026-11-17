"""
try_app_understand -- reverse-engineer a web app from the outside, with nothing but what a browser can legitimately see.

While the deep explorer clicks through the app, this watches and afterwards reads:

  NETWORK     every request the page made: which servers (first party vs third party: analytics, ads, CDN, fonts), which API endpoints (paths with ids folded: /api/jobs/{n}), which methods,
              GraphQL operation names, WebSocket hosts, how many requests of each kind. Query strings, bodies and cookie VALUES are never stored.
  STACK       framework fingerprints in the page (React, Next.js, Vue, Angular, jQuery, webpack ...), response headers that name the platform (server, CDN ids), PWA / service worker,
              the names (never values) of cookies and local-storage keys
  SIGN-IN     what the logged-out page offers: password form, which single-sign-on buttons, captcha, whether the app is behind a login wall
  SITE MAP    robots.txt and the sitemap (one or two plain GETs): how many pages, and the page TYPES (first path segment: /jobs, /company, /watch ...)
  SHORTCUTS   many apps open a keyboard-shortcut sheet on '?': it is opened, read, closed
  MEANING     the page's own description, headings, main navigation, what the deep explorer found, and a plain-language 'how to use it' lesson built from those facts (no model)

Everything is read-only and logged-out; nothing is typed, submitted or logged into.
"""
from __future__ import annotations

import contextlib
import re
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

ANALYTICS = re.compile(r"(google-analytics|googletagmanager|analytics|segment\.|mixpanel|amplitude|hotjar|clarity\.ms|heap|newrelic|nr-data|datadog|sentry|bugsnag|fullstory|logrocket|optimizely|quantserve|scorecardresearch|"
                       r"snowplow|adobedtm|omtrdc|demdex|bat\.bing|px\.ads|tiktok|pinterest|hubspot|intercom|drift|segment|rudderstack|posthog|statsig|launchdarkly|mpulse|akstat|beacon|telemetry|metrics|tracking|collect)", re.I)
ADS = re.compile(r"(doubleclick|googlesyndication|adservice|adsystem|adnxs|criteo|taboola|outbrain|rubicon|pubmatic|openx|amazon-adsystem|adsrvr|casalemedia|facebook\.net|connect\.facebook|ads\.|/ads/|advert)", re.I)
CDN = re.compile(r"(cloudfront|akamai|fastly|cloudflare|gstatic|jsdelivr|unpkg|cdnjs|cdn\.|static\.|edgekey|azureedge|imgix|ytimg|licdn|fbcdn|twimg|ggpht|googleusercontent|githubassets|assets\.)", re.I)
FONTS = re.compile(r"(fonts\.googleapis|fonts\.gstatic|typekit|fontawesome|use\.fonts)", re.I)
SSO = [("Google", r"google"), ("Apple", r"apple"), ("Facebook", r"facebook"), ("Microsoft", r"microsoft"), ("GitHub", r"github"), ("LinkedIn", r"linkedin"), ("Twitter/X", r"twitter|\bx\b"), ("Amazon", r"amazon"),
       ("Email", r"email|e-mail"), ("Phone", r"phone|mobile number")]
CAPTCHA = re.compile(r"(recaptcha|hcaptcha|turnstile|arkoselabs|funcaptcha|geetest|px-captcha|datadome|perimeterx)", re.I)

FRAMEWORK_JS = r"""
() => {
  const w = window, f = [];
  const some = (sel) => !!document.querySelector(sel);
  let react = !!w.React || some('[data-reactroot]');
  if (!react) { const els = [...document.querySelectorAll('body *')].slice(0, 600); react = els.some(e => Object.keys(e).some(k => k.startsWith('__reactFiber') || k.startsWith('__reactContainer') || k.startsWith('__reactProps'))); }
  if (react) f.push('React');
  if (w.__NEXT_DATA__ || some('#__next')) f.push('Next.js');
  if (w.__NUXT__ || some('#__nuxt')) f.push('Nuxt');
  if (w.Vue || some('[data-v-app]') || some('[data-server-rendered]')) f.push('Vue');
  const ng = document.querySelector('[ng-version]'); if (ng) f.push('Angular ' + ng.getAttribute('ng-version')); else if (w.angular) f.push('AngularJS');
  if (w.jQuery && w.jQuery.fn) f.push('jQuery ' + w.jQuery.fn.jquery);
  if (some('[class*="svelte-"]')) f.push('Svelte');
  if (w.Ember) f.push('Ember'); if (w.Backbone) f.push('Backbone'); if (w.Polymer) f.push('Polymer'); if (w.Alpine) f.push('Alpine.js'); if (w.htmx) f.push('htmx');
  if (some('ytd-app, yt-formatted-string')) f.push('Polymer (YouTube)');
  if (Object.keys(w).some(k => k.startsWith('webpackChunk') || k === 'webpackJsonp')) f.push('webpack');
  if (w.dataLayer) f.push('Google Tag Manager dataLayer'); if (w.ga || w.gtag) f.push('Google Analytics');
  const meta = {};
  for (const m of document.querySelectorAll('meta[name],meta[property]')) { const n = m.getAttribute('name') || m.getAttribute('property');
    if (['description','og:title','og:description','og:type','og:site_name','generator','application-name','twitter:card','theme-color'].includes(n)) meta[n] = (m.content || '').slice(0, 220); }
  const text = (e) => (e.innerText || e.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
  const heads = [...document.querySelectorAll('h1,h2')].map(text).filter(t => t && t.length < 90).slice(0, 14);
  const nav = [...document.querySelectorAll('nav a, header a, [role=navigation] a, nav button, header button')].map(text).filter(t => t && t.length < 40);
  const forms = [...document.forms].slice(0, 6).map(fm => ({fields: [...fm.elements].filter(x => x.name || x.type).slice(0, 12).map(x => (x.type || x.tagName.toLowerCase()) + (x.autocomplete ? ':' + x.autocomplete : '')), method: (fm.method || 'get').toLowerCase(),
                                                         action: (() => { try { return new URL(fm.action, location.href).pathname; } catch (e) { return ''; } })()}));
  const sso = [...document.querySelectorAll('a,button,[role=button]')].map(text).filter(t => /(continue|sign in|log in|login|sign up|connect) (with|using|via)|\bwith (google|apple|facebook|microsoft|github|linkedin)\b/i.test(t)).slice(0, 12);
  return {frameworks: [...new Set(f)], meta, manifest: some('link[rel=manifest]'), sw: !!(navigator.serviceWorker && navigator.serviceWorker.controller), lang: document.documentElement.lang || '',
          title: document.title, headings: heads, nav: [...new Set(nav)].slice(0, 40), forms, sso_buttons: [...new Set(sso)], password: some('input[type=password]'),
          local_keys: Object.keys(localStorage).slice(0, 40), session_keys: Object.keys(sessionStorage).slice(0, 20), iframes: [...document.querySelectorAll('iframe')].map(i => { try { return new URL(i.src, location.href).host; } catch (e) { return ''; } }).filter(Boolean).slice(0, 12),
          canvases: document.querySelectorAll('canvas').length, videos: document.querySelectorAll('video').length, search: some('input[type=search], [role=search], input[name=q], input[placeholder*=earch i]')};
}
"""

DIALOG_TEXT_JS = r"""
() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 80 && r.height > 80 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const cands = [...document.querySelectorAll('[role=dialog], [aria-modal=true], dialog[open], [class*=modal i], [class*=shortcut i], [id*=shortcut i], ytd-hotkey-dialog-renderer, [class*=hotkey i]')].filter(vis);
  const hit = cands.find(e => /shortcut|hotkey|keyboard/i.test(e.innerText || '')) || null;
  return hit ? (hit.innerText || '').slice(0, 6000) : '';
}
"""


def registrable(host: str) -> str:
    parts = host.lower().split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "gov", "ac") and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def fold_path(path: str) -> str:
    out = []
    for seg in path.split("/"):
        if re.fullmatch(r"\d+", seg):
            out.append("{n}")
        elif re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}", seg):
            out.append("{uuid}")
        elif re.fullmatch(r"[0-9a-fA-F]{16,}", seg):
            out.append("{hash}")
        elif len(seg) >= 20 and re.search(r"\d", seg) and re.search(r"[A-Za-z]", seg):
            out.append("{token}")
        else:
            out.append(seg)
    return "/".join(out) or "/"


def classify_host(host: str, first: str) -> str:
    if registrable(host) == first:
        return "first-party"
    if FONTS.search(host):
        return "fonts"
    if ADS.search(host):
        return "ads"
    if ANALYTICS.search(host):
        return "analytics"
    if CDN.search(host):
        return "cdn"
    return "third-party"


class Understander:
    def __init__(self, page: Any, ctx: Any, url: str) -> None:
        self.page, self.ctx, self.url = page, ctx, url
        self.first = registrable(urlparse(url).netloc)
        self.reqs: List[Dict[str, Any]] = []
        self.ws: List[str] = []
        self.statuses: Counter = Counter()
        self.headers: Dict[str, Any] = {}
        self.gql: Counter = Counter()
        self.t0 = time.monotonic()
        page.on("request", self._req)
        page.on("response", self._resp)
        page.on("websocket", lambda w: self.ws.append(urlparse(w.url).netloc))

    def _req(self, r: Any) -> None:
        with contextlib.suppress(Exception):
            u = urlparse(r.url)
            if u.scheme not in ("http", "https"):
                return
            rec = {"host": u.netloc, "path": fold_path(u.path), "method": r.method, "type": r.resource_type, "params": sorted({q.split("=")[0] for q in u.query.split("&") if q})[:8]}
            if r.method == "POST":
                body = ""
                with contextlib.suppress(Exception):
                    body = r.post_data or ""
                m = re.search(r'"operationName"\s*:\s*"([A-Za-z0-9_]{2,60})"', body or "")
                if m:
                    self.gql[m.group(1)] += 1
                    rec["gql"] = m.group(1)
            self.reqs.append(rec)

    def _resp(self, r: Any) -> None:
        with contextlib.suppress(Exception):
            self.statuses[r.status // 100 * 100] += 1
            req = r.request
            if req.is_navigation_request() and not self.headers and r.frame == self.page.main_frame:
                h = {k.lower(): v for k, v in r.headers.items()}
                keep = {k: h[k][:80] for k in ("server", "via", "x-powered-by", "content-type", "cache-control", "x-frame-options", "referrer-policy") if k in h}
                for k, label in (("cf-ray", "Cloudflare"), ("x-amz-cf-id", "Amazon CloudFront"), ("x-vercel-id", "Vercel"), ("x-github-request-id", "GitHub"), ("x-served-by", "Fastly"),
                                 ("x-azure-ref", "Azure Front Door"), ("x-akamai-transformed", "Akamai"), ("x-goog-meta", "Google"), ("alt-svc", "HTTP/3 offered"), ("x-envoy-upstream-service-time", "Envoy")):
                    if k in h:
                        keep.setdefault("platform_hints", []).append(label)
                keep["security_headers"] = [k for k in ("content-security-policy", "strict-transport-security", "x-content-type-options", "permissions-policy") if k in h]
                keep["status"] = r.status
                self.headers = keep

    # ---------------------------------------------------------------- reading
    def network(self) -> Dict[str, Any]:
        hosts: Dict[str, Dict[str, Any]] = {}
        kinds: Counter = Counter()
        api: Dict[Tuple[str, str, str], int] = defaultdict(int)
        for r in self.reqs:
            kind = classify_host(r["host"], self.first)
            kinds[kind] += 1
            h = hosts.setdefault(r["host"], {"kind": kind, "n": 0, "types": Counter()})
            h["n"] += 1
            h["types"][r["type"]] += 1
            if kind == "first-party" and r["type"] in ("xhr", "fetch") or (r["type"] in ("xhr", "fetch") and kind == "third-party" and r["method"] != "GET"):
                api[(r["method"], r["host"], r["path"])] += 1
        top_hosts = sorted(hosts.items(), key=lambda kv: -kv[1]["n"])[:14]
        return {"requests": len(self.reqs), "by_kind": dict(kinds), "status": dict(self.statuses),
                "hosts": [{"host": h, "kind": d["kind"], "n": d["n"], "types": dict(d["types"].most_common(3))} for h, d in top_hosts],
                "api_endpoints": [{"method": m, "host": h, "path": p, "n": n} for (m, h, p), n in sorted(api.items(), key=lambda kv: -kv[1])[:25]],
                "graphql_operations": dict(self.gql.most_common(15)), "websockets": sorted(set(self.ws))[:6]}

    def stack(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        with contextlib.suppress(Exception):
            out = self.page.evaluate(FRAMEWORK_JS)
        with contextlib.suppress(Exception):
            names = sorted({c["name"] for c in self.ctx.cookies()})
            out["cookie_names"] = names[:40]
            out["cookie_flags"] = {"n": len(names), "analytics_like": [n for n in names if re.match(r"^(_ga|_gid|_fbp|_gcl|_hj|ajs_|amplitude|mp_|optimizely|_uet|_clck|_cl|ttcsid|_pin)", n)][:10]}
        out["headers"] = self.headers
        return out

    def site_files(self) -> Dict[str, Any]:
        origin = "{0.scheme}://{0.netloc}".format(urlparse(self.url))
        out: Dict[str, Any] = {}

        def get(path: str, n: int = 400000) -> str:
            with contextlib.suppress(Exception):
                r = self.ctx.request.get(path if path.startswith("http") else origin + path, timeout=9000)
                if r.ok:
                    return r.text()[:n]
            return ""
        robots = get("/robots.txt", 60000)
        sitemaps: List[str] = []
        if robots:
            dis = [l.split(":", 1)[1].strip() for l in robots.splitlines() if l.lower().startswith("disallow:") and l.split(":", 1)[1].strip()]
            sitemaps = [l.split(":", 1)[1].strip() for l in robots.splitlines() if l.lower().startswith("sitemap:")]
            out["robots"] = {"disallow_rules": len(dis), "sample_disallowed": dis[:8], "sitemaps": sitemaps[:4], "user_agent_groups": sum(1 for l in robots.splitlines() if l.lower().startswith("user-agent:"))}
        locs: List[str] = []
        index_children = 0
        for sm in (sitemaps[:1] or [origin + "/sitemap.xml"]):
            xml = get(sm)
            if not xml:
                continue
            found = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
            if "<sitemapindex" in xml:
                index_children = len(found)
                for child in found[:2]:
                    cx = get(child)
                    locs += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", cx)[:3000]
            else:
                locs += found[:5000]
        if locs:
            seg = Counter()
            for u in locs:
                p = urlparse(u).path.strip("/").split("/")
                seg["/" + (p[0] if p and p[0] else "")] += 1
            out["sitemap"] = {"urls_sampled": len(locs), "child_sitemaps": index_children, "page_types": [{"prefix": k, "n": v} for k, v in seg.most_common(12)]}
        return out

    def shortcut_sheet(self) -> Dict[str, Any]:
        """Press '?' with nothing focused: apps that have a shortcut sheet show it. Read it, close it."""
        res: Dict[str, Any] = {"opened": False}
        with contextlib.suppress(Exception):
            self.page.evaluate("() => { if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur(); }")
            self.page.keyboard.press("Shift+/")
            time.sleep(1.0)
            txt = self.page.evaluate(DIALOG_TEXT_JS) or ""
            if txt:
                res.update(opened=True, text=txt[:2500], pairs=parse_shortcut_text(txt))
            self.page.keyboard.press("Escape")
            time.sleep(0.3)
        return res

    FOCUS_JS = """() => { const a = document.activeElement; if (!a || a === document.body) return null; const r = a.getBoundingClientRect();
        return {tag: a.tagName.toLowerCase(), role: a.getAttribute('role') || '', label: ((a.getAttribute('aria-label') || a.innerText || a.placeholder || a.value || a.title || '') + '').replace(/\\s+/g, ' ').trim().slice(0, 60),
                typing: /^(input|textarea)$/i.test(a.tagName) || a.isContentEditable || /searchbox|combobox|textbox/.test(a.getAttribute('role') || ''), x: Math.round(r.left), y: Math.round(r.top)}; }"""

    def keyboard(self, tabs: int = 30) -> Dict[str, Any]:
        """The keyboard side of the app, found by trying it. TAB ORDER: Tab is pressed up to `tabs` times and every element that takes focus is written down in order (a free, safe, systematic
        way to meet every control a keyboard user can reach). HOTKEYS: the few keys that many sites share ('/' to search, Ctrl+K for a palette) are pressed once each with nothing focused; a key counts
        only if its EFFECT is seen (focus moved into a text field, or a dialog appeared). Nothing is typed into any field."""
        res: Dict[str, Any] = {"tab_order": [], "hotkeys": []}
        with contextlib.suppress(Exception):
            self.page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); window.scrollTo(0, 0); }")
            seen = set()
            for _ in range(tabs):
                self.page.keyboard.press("Tab")
                f = self.page.evaluate(self.FOCUS_JS)
                if not f:
                    continue
                k = (f["tag"], f["label"], f["x"], f["y"])
                if k in seen:
                    break
                seen.add(k)
                res["tab_order"].append({"tag": f["tag"], "role": f["role"], "label": f["label"]})
            self.page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); window.scrollTo(0, 0); }")
        dlg = "() => [...document.querySelectorAll('[role=dialog], [aria-modal=true], dialog[open]')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 40 && r.height > 40; }).length"
        for key, meaning in (("/", "focus the search box"), ("Control+k", "open the search / command palette")):
            with contextlib.suppress(Exception):
                self.page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
                d0 = self.page.evaluate(dlg)
                self.page.keyboard.press(key)
                time.sleep(0.7)
                f = self.page.evaluate(self.FOCUS_JS)
                d1 = self.page.evaluate(dlg)
                if f and f["typing"]:
                    res["hotkeys"].append({"keys": key.lower().replace("control", "ctrl"), "action": meaning, "effect": f"focus moved into a text field ('{f['label'] or f['tag']}')"})
                elif d1 > d0:
                    res["hotkeys"].append({"keys": key.lower().replace("control", "ctrl"), "action": meaning, "effect": "a dialog opened"})
                self.page.keyboard.press("Escape")
                time.sleep(0.2)
                self.page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
        return res

    def finish(self, rep: Dict[str, Any], explore: Optional[Dict[str, Any]], labels: List[str]) -> Dict[str, Any]:
        out: Dict[str, Any] = {"seconds_watching": round(time.monotonic() - self.t0, 1)}
        out["shortcut_sheet"] = self.shortcut_sheet()
        out["keyboard"] = self.keyboard()
        out["network"] = self.network()
        out["stack"] = self.stack()
        out["site_files"] = self.site_files()
        out["auth"] = auth_summary(out["stack"], rep)
        out["meaning"] = meaning(out, explore, labels, self.url)
        return out


# --------------------------------------------------------------------------------------------- analysis
KEY_TOKEN = re.compile(r"^(?:(?:ctrl|control|cmd|command|alt|option|shift)\s*\+?\s*)*(?:[A-Za-z0-9/?.,;'\[\]\\=-]|enter|esc|escape|tab|space|home|end|f\d{1,2}|up|down|left|right|delete|backspace|pageup|pagedown)$", re.I)


def parse_shortcut_text(text: str) -> List[Dict[str, str]]:
    """Pairs (keys, action) from a shortcut sheet's text. Sheets list 'S   Focus search bar' (two columns -> two lines or a tab), or 'Focus search bar   S'."""
    pairs: List[Dict[str, str]] = []
    lines = [l.strip() for l in re.split(r"[\r\n]+", text) if l.strip()]

    def keylike(s: str) -> bool:
        toks = [t for t in re.split(r"\s*(?:\+|\bthen\b|,|\s)\s*", s) if t]
        return 0 < len(toks) <= 4 and len(s) <= 18 and all(KEY_TOKEN.match(t) or t.lower() in ("then", "or") for t in toks)

    i = 0
    while i < len(lines):
        l = lines[i]
        if "\t" in l:
            a, b = [x.strip() for x in l.split("\t", 1)]
            if keylike(a) and len(b) > 2:
                pairs.append({"keys": a, "action": b})
            elif keylike(b) and len(a) > 2:
                pairs.append({"keys": b, "action": a})
        elif keylike(l) and i + 1 < len(lines) and not keylike(lines[i + 1]) and re.search(r"[A-Za-z]{3}", lines[i + 1]) and len(lines[i + 1]) < 70:
            pairs.append({"keys": l, "action": lines[i + 1]})
            i += 1
        elif not keylike(l) and re.search(r"[A-Za-z]{3}", l) and len(l) < 70 and i + 1 < len(lines) and keylike(lines[i + 1]):
            pairs.append({"keys": lines[i + 1], "action": l})
            i += 1
        i += 1
    seen, out = set(), []
    for p in pairs:
        k = (p["keys"].lower(), p["action"].lower())
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out[:80]


def auth_summary(stack: Dict[str, Any], rep: Dict[str, Any]) -> Dict[str, Any]:
    texts = " | ".join(stack.get("sso_buttons", []))
    providers = [name for name, rx in SSO if re.search(rx, texts, re.I)]
    frames = " ".join(stack.get("iframes", []))
    wall = bool(stack.get("password")) or (len([c for c in rep.get("controls", []) if c.get("inview")]) < 18 and bool(re.search(r"(sign in|log in|login)", rep.get("text", "")[:2500], re.I)))
    status = rep.get("http_status") or 0
    if status >= 400:
        return {"password_form": False, "sso_providers": [], "sso_buttons": [], "captcha": [], "login_wall": False, "forms": [], "blocked": status,
                "reads_as": f"the site answered this automated browser with HTTP {status}: nothing of it could be read (not worked around)"}
    return {"password_form": bool(stack.get("password")), "sso_providers": providers, "sso_buttons": stack.get("sso_buttons", [])[:6], "captcha": sorted(set(m.group(1).lower() for m in CAPTCHA.finditer(frames + " " + str(stack.get("local_keys", []))))),
            "login_wall": wall, "forms": stack.get("forms", [])[:4], "reads_as": "behind a login: only the public / logged-out side was scanned" if wall else "public pages are open to a logged-out visitor"}


def meaning(u: Dict[str, Any], explore: Optional[Dict[str, Any]], labels: List[str], url: str) -> Dict[str, Any]:
    st, net, files = u.get("stack", {}), u.get("network", {}), u.get("site_files", {})
    meta = st.get("meta", {})
    desc = meta.get("description") or meta.get("og:description") or ""
    name = meta.get("og:site_name") or meta.get("application-name") or (st.get("title") or "").split("|")[0].split("-")[0].strip() or urlparse(url).netloc
    sections = []
    if explore:
        for n in explore.get("nodes", []):
            if n.get("depth", 1) == 1 and n["outcome"] not in ("nothing visible happened", "unreachable", "could not click"):
                sections.append(n["path"].split(" > ")[0])
    nav = [x for x in st.get("nav", []) if 2 < len(x) < 30][:14]
    pairs = (u.get("shortcut_sheet") or {}).get("pairs", [])
    lesson: List[str] = []
    lesson.append(f"{name}: {desc[:200]}" if desc else f"{name} ({urlparse(url).netloc})")
    if nav:
        lesson.append("Main navigation: " + ", ".join(nav[:10]) + ".")
    if st.get("search"):
        lesson.append("There is a search box on the page: that is the fastest way in.")
    if sections:
        lesson.append("Menus / buttons that open something: " + ", ".join(list(dict.fromkeys(sections))[:8]) + ".")
    auth = u.get("auth", {})
    if auth.get("sso_providers"):
        lesson.append("Sign in with: " + ", ".join(auth["sso_providers"]) + ".")
    elif auth.get("password_form"):
        lesson.append("Sign-in is a username + password form.")
    if pairs:
        lesson.append("Keyboard shortcuts it shows on '?': " + "; ".join(f"{p['keys']} = {p['action'][:28]}" for p in pairs[:6]) + ".")
    pt = (files.get("sitemap") or {}).get("page_types", [])
    if pt:
        lesson.append("Kinds of pages (from its sitemap): " + ", ".join(f"{p['prefix']} ({p['n']})" for p in pt[:6]) + ".")
    return {"name": name, "description": desc, "headings": st.get("headings", [])[:10], "navigation": nav, "opens_something": list(dict.fromkeys(sections))[:20], "lesson": lesson}
