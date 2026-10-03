"""
organ_51_web_layout.py — the same "know the app" pipeline, for WEBSITES and WEB APPS.

A web page is just another app: sections (header, nav, main, sidebar, dialog, footer), controls with
a position, widgets that reveal more when operated (tabs, disclosure menus, lazy-loaded content).
This organ maps all of it with one generic method and stores it in the SAME knowledge tables the
desktop pipeline uses (bm_layout / bm_commands / bm_transitions), keyed `web:<host>`.

Invisible by construction: a dedicated HEADLESS Chrome (own temp profile, own debugging port) is
launched per scan. There is no window, no taskbar entry, no focus, and the user's own browser,
tabs, cookies and sessions are never touched.

Phase 1  STATIC MAP (read-only, E0): one in-page script walks the document, open shadow roots and
         same-origin iframes. Every named/interactive element gets role, accessible name, state,
         href, selector path, bounding box (viewport-relative fractions so it survives resizing)
         and the landmark region it belongs to. Cross-origin iframes are reported opaque.
Phase 2  REVERSIBLE DEEPENING (E1, every action verified and undone):
         * tabs        select each tab, harvest what it reveals, restore the original tab
         * disclosure  open aria-expanded=false widgets, harvest, close them again
         * lazy scroll page through the document so lazy content materialises, scroll back
         Never navigates away: links are catalogued, not followed. Anything destructive-looking
         (delete/buy/send/submit/sign-out ...) or inside a <form> submit is E2 = never touched.
Phase 3  PERSIST + KNOWLEDGE: layout rows, nav/button/link commands (catalog trust, risk graded),
         probe transitions, and a site-version hash (hash of the script bundle URLs) so a site
         deploy demotes what was learned.

Time is adaptive (DiscoveryBudget) like the desktop crawler — nothing is labelled easy or hard.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("hojaiga.organ_51_web_layout")

NAV_TIMEOUT_S = float(os.environ.get("HOJAIGA_WEB_NAV_TIMEOUT_S", "25"))
SETTLE_CAP_S = float(os.environ.get("HOJAIGA_WEB_SETTLE_CAP_S", "12"))
VIEWPORT = (1366, 900)

# ---------------------------------------------------------------------------
# headless Chrome + a tiny synchronous CDP client
# ---------------------------------------------------------------------------

def _chrome_path() -> Optional[str]:
    for p in (os.environ.get("HOJAIGA_CHROME", ""),
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
        if p and os.path.exists(p):
            return p
    return shutil.which("chrome") or shutil.which("msedge")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class HeadlessChrome:
    """One private headless browser. `with HeadlessChrome() as b:` -> b.cdp(...) / b.js(...)."""

    def __init__(self, viewport: Tuple[int, int] = VIEWPORT):
        self.viewport = viewport
        self.proc: Optional[subprocess.Popen] = None
        self.port = 0
        self.profile = ""
        self.ws = None
        self._id = 0
        self.exe = _chrome_path()

    def __enter__(self) -> "HeadlessChrome":
        if not self.exe:
            raise RuntimeError("no Chrome/Edge executable found")
        import websocket                                    # websocket-client (already in the env)
        self.port = _free_port()
        self.profile = tempfile.mkdtemp(prefix="hj_web_")
        args = [self.exe, "--headless=new", f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.profile}", "--no-first-run", "--no-default-browser-check",
                "--disable-extensions", "--disable-sync", "--mute-audio", "--disable-notifications",
                "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
                f"--window-size={self.viewport[0]},{self.viewport[1]}", "about:blank"]
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=0x08000000)         # CREATE_NO_WINDOW
        ws_url, end = "", time.time() + 20
        while time.time() < end and not ws_url:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json", timeout=1) as r:
                    tabs = json.loads(r.read().decode())
                page = next((t for t in tabs if t.get("type") == "page"), None)
                ws_url = (page or {}).get("webSocketDebuggerUrl", "")
            except Exception:
                time.sleep(0.2)
        if not ws_url:
            self.__exit__()
            raise RuntimeError("headless Chrome did not expose a debugging endpoint")
        self.ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
        self.cdp("Page.enable")
        self.cdp("Runtime.enable")
        self.cdp("Emulation.setDeviceMetricsOverride", {"width": self.viewport[0], "height": self.viewport[1],
                                                         "deviceScaleFactor": 1, "mobile": False})
        return self

    def __exit__(self, *exc):
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        try:
            if self.proc:
                self.proc.terminate()
                self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        shutil.rmtree(self.profile, ignore_errors=True)
        return False

    def cdp(self, method: str, params: Optional[dict] = None, timeout: float = 30.0) -> dict:
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        self.ws.settimeout(timeout)
        end = time.time() + timeout
        while time.time() < end:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error'].get('message')}")
                return msg.get("result", {})
        raise TimeoutError(method)

    def js(self, expr: str, timeout: float = 30.0) -> Any:
        r = self.cdp("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True,
                                          "timeout": int(timeout * 1000)}, timeout=timeout + 5)
        if r.get("exceptionDetails"):
            raise RuntimeError("js: " + str(r["exceptionDetails"].get("text", ""))[:120]
                               + " " + str(r["exceptionDetails"].get("exception", {}).get("description", ""))[:200])
        return r.get("result", {}).get("value")

    def set_cookies(self, cookies: List[Dict[str, Any]]) -> int:
        """Seed the PRIVATE headless browser with a saved session (Network.setCookies). The values are
        credentials: they are passed straight to the browser and never logged or persisted here."""
        self.cdp("Network.enable")
        out = []
        for c in cookies:
            try:
                item = {"name": c["name"], "value": c["value"], "domain": c.get("domain", ""), "path": c.get("path", "/"),
                        "secure": bool(c.get("secure", False)), "httpOnly": bool(c.get("httpOnly", False))}
                exp = c.get("expiry") or c.get("expires")
                if exp:
                    item["expires"] = float(exp)
                ss = c.get("sameSite")
                if ss in ("Strict", "Lax", "None"):
                    item["sameSite"] = ss
                out.append(item)
            except Exception:
                continue
        if out:
            try:
                self.cdp("Network.setCookies", {"cookies": out}, timeout=20)
            except Exception:
                n = 0
                for item in out:                                  # tolerate a few malformed entries
                    try:
                        self.cdp("Network.setCookie", item, timeout=5)
                        n += 1
                    except Exception:
                        continue
                return n
        return len(out)

    def navigate(self, url: str) -> Dict[str, Any]:
        t0 = time.time()
        r = self.cdp("Page.navigate", {"url": url})
        err = r.get("errorText", "")
        state, end = "", time.time() + NAV_TIMEOUT_S
        while time.time() < end:
            try:
                state = self.js("document.readyState", timeout=5)
            except Exception:
                state = ""
            if state == "complete":
                break
            time.sleep(0.2)
        quiet(self, cap_ms=int(SETTLE_CAP_S * 1000), quiet_ms=500)       # SPAs hydrate after 'complete'
        # a few SPAs render in bursts: also require the element count to stop growing
        last, stable, end2 = -1, 0, time.time() + SETTLE_CAP_S
        while time.time() < end2 and stable < 2:
            try:
                n = self.js("document.querySelectorAll('*').length", timeout=5)
            except Exception:
                n = -1
            stable = stable + 1 if n == last else 0
            last = n
            time.sleep(0.25)
        return {"error": err, "ready": state, "load_s": round(time.time() - t0, 2)}


# Wait for the DOM to go QUIET (no mutations for `quiet` ms, capped at `cap` ms) instead of sleeping a
# fixed time: a static page is ready at once, a heavy single-page app gets exactly as long as it needs.
QUIET_JS = ("((cap,quiet)=>new Promise(res=>{let t=setTimeout(done,quiet);"
            "const mo=new MutationObserver(()=>{clearTimeout(t);t=setTimeout(done,quiet)});"
            "mo.observe(document.documentElement,{subtree:true,childList:true,attributes:true,characterData:true});"
            "const c=setTimeout(done,cap);function done(){mo.disconnect();clearTimeout(c);clearTimeout(t);res(true)}}))")


def quiet(b, cap_ms: int = 700, quiet_ms: int = 90) -> None:
    try:
        b.js(f"{QUIET_JS}({cap_ms},{quiet_ms})", timeout=cap_ms / 1000 + 5)
    except Exception:
        time.sleep(min(cap_ms, 300) / 1000)


# ---------------------------------------------------------------------------
# the in-page mapper (one evaluation; walks shadow roots + same-origin iframes)
# ---------------------------------------------------------------------------

MAP_JS = r"""
(() => {
  const t0 = performance.now(), CAP = 6000, TIME_CAP = 4000;
  const out = [], regions = [], seenEl = new Set();
  const VW = window.innerWidth, VH = window.innerHeight;
  const IMPLICIT = {A:'link', BUTTON:'button', INPUT:'textbox', SELECT:'combobox', TEXTAREA:'textbox', SUMMARY:'button',
    NAV:'navigation', HEADER:'banner', FOOTER:'contentinfo', MAIN:'main', ASIDE:'complementary', FORM:'form',
    DIALOG:'dialog', UL:'list', OL:'list', TABLE:'grid', H1:'heading',H2:'heading',H3:'heading',H4:'heading',
    H5:'heading',H6:'heading', IMG:'img', LABEL:'label', SECTION:'region', ARTICLE:'article', SEARCH:'search'};
  const INPUT_ROLE = {checkbox:'checkbox', radio:'radio', button:'button', submit:'button', reset:'button',
    range:'slider', search:'searchbox', image:'button', file:'button'};
  const LANDMARK = new Set(['banner','navigation','main','complementary','contentinfo','search','form','region',
    'dialog','alertdialog','toolbar','menu','menubar','tablist','tree','grid','list','listbox','table','article']);
  const INTERACTIVE_ROLES = new Set(['button','link','textbox','searchbox','combobox','checkbox','radio','switch',
    'tab','menuitem','menuitemcheckbox','menuitemradio','option','slider','spinbutton','treeitem','gridcell','listitem_btn']);
  function roleOf(e) {
    const r = e.getAttribute && e.getAttribute('role');
    if (r) return r.split(' ')[0];
    const tag = e.tagName;
    if (tag === 'INPUT') return INPUT_ROLE[(e.type||'text').toLowerCase()] || 'textbox';
    if (tag === 'A' && !e.hasAttribute('href')) return 'generic';
    return IMPLICIT[tag] || 'generic';
  }
  function nameOf(e) {
    let n = e.getAttribute && (e.getAttribute('aria-label') || '');
    if (!n && e.getAttribute) {
      const lb = e.getAttribute('aria-labelledby');
      if (lb) n = lb.split(' ').map(id => { const x = e.getRootNode().getElementById && e.getRootNode().getElementById(id); return x ? x.textContent : ''; }).join(' ');
    }
    if (!n && e.tagName === 'IMG') n = e.alt || '';
    if (!n && e.labels && e.labels.length) n = e.labels[0].textContent;
    if (!n && e.placeholder) n = e.placeholder;
    if (!n && e.tagName === 'INPUT' && /button|submit|reset/.test(e.type)) n = e.value;
    if (!n && e.getAttribute) n = e.getAttribute('title') || '';
    if (!n && !LANDMARK.has(roleOf(e))) n = (e.innerText || e.textContent || '');
    return n.replace(/\s+/g, ' ').trim().slice(0, 90);
  }
  function visible(e, r) {
    if (r.width <= 0 || r.height <= 0) return false;
    const s = getComputedStyle(e);
    return s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity || '1') > 0.01;
  }
  function selectorOf(e) {
    const parts = []; let n = e, d = 0;
    while (n && n.nodeType === 1 && d < 5) {
      let p = n.tagName.toLowerCase();
      if (n.id && /^[A-Za-z][\w-]{0,40}$/.test(n.id)) { parts.unshift(p + '#' + n.id); break; }
      const par = n.parentElement;
      if (par) { const same = [...par.children].filter(c => c.tagName === n.tagName); if (same.length > 1) p += ':nth-of-type(' + (same.indexOf(n) + 1) + ')'; }
      parts.unshift(p); n = n.parentElement; d++;
    }
    return parts.join('>');
  }
  const regionIds = new Map();
  function regionFor(e) {
    let n = e;
    while (n && n.nodeType === 1) {
      const role = roleOf(n);
      if (LANDMARK.has(role) && (role !== 'region' || n.getAttribute('aria-label') || n.getAttribute('aria-labelledby')) && (role !== 'list' || n.children.length > 4) && n !== e) {
        if (!regionIds.has(n)) {
          const r = n.getBoundingClientRect();
          regionIds.set(n, regions.length);
          regions.push({kind: role, name: nameOf(n).slice(0, 60) || role, sel: selectorOf(n), n: 0,
                        box: [r.left + scrollX, r.top + scrollY, r.right + scrollX, r.bottom + scrollY]});
        }
        return regionIds.get(n);
      }
      n = n.parentElement || (n.getRootNode && n.getRootNode().host);
    }
    return -1;
  }
  let shadowRoots = 0, iframesSame = 0, iframesCross = [];
  function walk(root, frameOff, frameTag) {
    const els = root.querySelectorAll('*');
    for (const e of els) {
      if (out.length >= CAP || performance.now() - t0 > TIME_CAP) return;
      if (e.shadowRoot) { shadowRoots++; walk(e.shadowRoot, frameOff, frameTag); }
      if (e.tagName === 'IFRAME') {
        try { const d = e.contentDocument; if (d && d.documentElement) { iframesSame++; const fr = e.getBoundingClientRect(); walk(d, [frameOff[0] + fr.left, frameOff[1] + fr.top], 'iframe'); }
              else iframesCross.push({src: (e.src || '').slice(0, 120), box: (() => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })()}); }
        catch (x) { iframesCross.push({src: (e.src || '').slice(0, 120), box: []}); }
        continue;
      }
      const tag = e.tagName;
      if (/^(SCRIPT|STYLE|NOSCRIPT|META|LINK|HEAD|BR|HR|PATH|SVG|DEFS|TEMPLATE)$/.test(tag)) continue;
      const role = roleOf(e);
      const tabbable = e.hasAttribute('tabindex') && e.tabIndex >= 0;
      const clickable = e.onclick || e.getAttribute('onclick') || (tabbable && role === 'generic') || e.isContentEditable;
      const interactive = INTERACTIVE_ROLES.has(role) || clickable || (tag === 'A' && e.hasAttribute('href'));
      const labelish = /^(heading|img|label)$/.test(role) || LANDMARK.has(role);
      if (!interactive && !labelish) continue;
      const r = e.getBoundingClientRect();
      const vis = visible(e, r);
      if (!vis && !e.hasAttribute('aria-expanded')) continue;
      const nm = nameOf(e);
      if (!nm && !interactive && !LANDMARK.has(role)) continue;
      const rid = regionFor(e);
      if (rid >= 0) regions[rid].n++;
      out.push({role: role, name: nm, tag: tag.toLowerCase(), sel: selectorOf(e),
        href: tag === 'A' ? (e.getAttribute('href') || '').slice(0, 160) : '',
        target: e.getAttribute('target') || '', type: e.type || '',
        expanded: e.getAttribute('aria-expanded'), selected: e.getAttribute('aria-selected'),
        checked: e.getAttribute('aria-checked'), popup: e.getAttribute('aria-haspopup') || '',
        disabled: !!(e.disabled || e.getAttribute('aria-disabled') === 'true'),
        inForm: !!e.closest('form'), interactive: interactive, vis: vis,
        box: [r.left + frameOff[0] + scrollX, r.top + frameOff[1] + scrollY, r.right + frameOff[0] + scrollX, r.bottom + frameOff[1] + scrollY],
        region: rid, frame: frameTag});
    }
  }
  walk(document, [0, 0], 'top');
  const scripts = [...document.querySelectorAll('script[src]')].map(s => s.src).sort();
  const forms = [...document.forms].slice(0, 20).map(f => ({action: (f.getAttribute('action') || '').slice(0, 100), method: f.method,
      fields: [...f.elements].slice(0, 30).map(x => ({name: x.name || x.id || '', type: x.type || x.tagName.toLowerCase()}))}));
  const meta = {}; document.querySelectorAll('meta[name],meta[property]').forEach(m => { const k = m.getAttribute('name') || m.getAttribute('property'); if (meta[k] === undefined && k) meta[k] = (m.content || '').slice(0, 120); });
  const links = {}; document.querySelectorAll('link[rel]').forEach(l => { const k = l.rel; if (/manifest|sitemap|search|canonical|alternate/.test(k) && !links[k]) links[k] = (l.href || '').slice(0, 160); });
  return {title: document.title, url: location.href, vw: VW, vh: VH, docW: Math.max(document.documentElement.scrollWidth, VW),
    docH: Math.max(document.documentElement.scrollHeight, VH), scrollY: scrollY, elements: out, regions: regions,
    shadowRoots: shadowRoots, iframesSame: iframesSame, iframesCross: iframesCross.slice(0, 20),
    scripts: scripts.slice(0, 60), forms: forms, meta: meta, links: links, hasCanvas: document.querySelectorAll('canvas').length,
    capped: out.length >= CAP, ms: Math.round(performance.now() - t0)};
})()
"""

_E2_WEB = re.compile(r"\b(delete|remove|erase|buy|purchase|pay|checkout|order|send|publish|post|submit|subscribe|"
                     r"sign ?out|log ?out|unsubscribe|confirm|apply|donate|reset|clear all|accept all)\b", re.I)


# Authenticated pages are full of someone's data (mail subjects, senders, message text). In privacy mode
# only STRUCTURE is kept: operable controls and navigation keep their labels; names of data items are
# replaced by a placeholder, and link targets lose their query/ids.
_KEEP_NAME_ROLES = {"button", "tab", "menuitem", "menuitemcheckbox", "menuitemradio", "checkbox", "switch", "radio",
                    "combobox", "searchbox", "slider", "spinbutton", "navigation", "banner", "search", "toolbar",
                    "tablist", "menu", "menubar", "heading", "contentinfo", "dialog", "form"}
_DATA_REGION_KINDS = {"grid", "list", "tree", "content", "article"}


def _safe_href(h: str) -> str:
    if not h:
        return ""
    if h.startswith("#"):
        return "#"
    try:
        u = urlparse(h)
        seg = [x for x in u.path.split("/") if x][:1]
        return (u.scheme + "://" if u.scheme else "") + (u.netloc or "") + ("/" + seg[0] if seg else "/")
    except Exception:
        return ""


_E2_AUTH = re.compile(r"\b(compose|new message|new chat|reply|forward|archive|spam|report|mute|snooze|move|label|mark|trash|"
                      r"discard|save|like|dislike|comment|share|follow|subscribe|add|upload|create|edit|rename|"
                      r"invite|block|join|call|record|start|stop|pay|upgrade|buy|download|more actions)\b", re.I)


class WebMapper:
    """Quacks like organ_50's LayoutMapper so `save_layout` persists it unchanged."""

    def __init__(self, url: str, privacy: bool = False):
        self.privacy = privacy
        self.redacted = 0
        self.url = url
        self.app_name = "web:" + (urlparse(url).hostname or url)
        self.controls: List[Dict[str, Any]] = []
        self.regions: Dict[str, Dict[str, Any]] = {}
        self.win = (0, 0, VIEWPORT[0], VIEWPORT[1])
        self.stats: Dict[str, Any] = {"deepen": {}, "skipped": []}
        self._seen: set = set()
        self.raw: Dict[str, Any] = {}
        self.transitions: List[Dict[str, Any]] = []

    def structure_signature(self) -> str:
        return hashlib.md5("|".join(sorted(f"{r['kind']}:{r['name']}" for r in self.regions.values())).encode()).hexdigest()[:12]

    # -- ingest one map result (static or after a probe), dedupe by identity
    def ingest(self, data: Dict[str, Any], via: str = "static") -> int:
        vw, vh = max(data["vw"], 1), max(data["vh"], 1)
        new = 0
        regmap: Dict[int, str] = {}
        for i, r in enumerate(data["regions"]):
            rid = "rg_" + hashlib.md5(f"{r['kind']}|{r['name']}|{r['sel']}".encode()).hexdigest()[:10]
            regmap[i] = rid
            if rid not in self.regions:
                self.regions[rid] = {"region_id": rid, "parent": "", "kind": self._kind(r["kind"]), "name": r["name"],
                                     "automation_id": r["sel"], "bbox": [int(v) for v in r["box"]], "n": 0,
                                     "via": via, "opaque": False}
        if "rg_page" not in self.regions:
            self.regions["rg_page"] = {"region_id": "rg_page", "parent": "", "kind": "window", "name": data["title"][:60],
                                       "automation_id": "", "bbox": [0, 0, vw, int(data["docH"])], "n": 0, "via": via,
                                       "opaque": False}
        for e in data["elements"]:
            rid = regmap.get(e["region"], "")
            b = e["box"]
            if not rid:                                   # no landmark ancestor: section by POSITION in the viewport
                rid = self._geom_region(b, vw, vh)
            cid = "ctl_" + hashlib.md5(f"{rid}|{e['role']}|{e['name']}|{e['sel']}".encode()).hexdigest()[:12]
            if cid in self._seen:
                continue
            self._seen.add(cid)
            new += 1
            self.regions[rid]["n"] += 1
            if self.privacy:
                in_data = self.regions[rid]["kind"] in _DATA_REGION_KINDS or e["role"] in ("row", "gridcell", "cell", "option", "listitem", "article")
                short_ui = e["role"] in _KEEP_NAME_ROLES and len(e["name"]) <= 40 and not (in_data and e["role"] in ("heading",))
                if e["name"] and not short_ui:
                    e["name"] = f"<{e['role']}:redacted>"
                    self.redacted += 1
                elif e["name"] and in_data and e["role"] not in ("button", "tab", "menuitem", "checkbox", "switch"):
                    e["name"] = f"<{e['role']}:redacted>"
                    self.redacted += 1
                e["href"] = _safe_href(e["href"])
            pats = []
            if e["interactive"] and not e["disabled"]:
                pats.append("invoke")
            if e["expanded"] is not None:
                pats.append("expand")
            if e["selected"] is not None:
                pats.append("select")
            if e["role"] in ("textbox", "searchbox", "combobox"):
                pats.append("value")
            rel = (round(b[0] / vw, 4), round(b[1] / vh, 4), round(b[2] / vw, 4), round(b[3] / vh, 4))
            self.controls.append({
                "ctrl_id": cid, "region_id": rid, "role": e["role"], "name": e["name"], "automation_id": ("" if self.privacy else e["sel"][:120]),
                "cls": e["tag"], "bbox": [int(v) for v in b], "rel": list(rel),
                "center_rel": [round((rel[0] + rel[2]) / 2, 4), round((rel[1] + rel[3]) / 2, 4)],
                "enabled": not e["disabled"], "offscreen": not e["vis"], "patterns": pats,
                "path": f"{self.regions[rid]['kind']} > {e['role']} '{e['name'][:40]}'", "depth": 1, "via": via,
                "_href": e["href"], "_in_form": e["inForm"], "_type": e["type"], "_expanded": e["expanded"],
                "_selected": e["selected"], "_popup": e["popup"], "_sel": e["sel"], "_target": e["target"]})
        return new

    def _geom_region(self, b, vw: int, vh: int) -> str:
        cx, cy = (b[0] + b[2]) / 2 / vw, (b[1] + b[3]) / 2 / vh
        kind = ("header" if cy < 0.12 else "footer" if cy > 1.0 and False else
                "sidebar_left" if cx < 0.18 else "sidebar_right" if cx > 0.82 else "content")
        rid = "rg_geo_" + kind
        if rid not in self.regions:
            box = {"header": [0, 0, vw, int(vh * 0.12)], "sidebar_left": [0, int(vh * 0.12), int(vw * 0.18), vh],
                   "sidebar_right": [int(vw * 0.82), int(vh * 0.12), vw, vh],
                   "content": [int(vw * 0.18), int(vh * 0.12), int(vw * 0.82), vh]}[kind]
            self.regions[rid] = {"region_id": rid, "parent": "", "kind": kind, "name": f"{kind} (by position)",
                                 "automation_id": "", "bbox": box, "n": 0, "via": "geometry", "opaque": False}
        return rid

    @staticmethod
    def _kind(role: str) -> str:
        return {"banner": "header", "navigation": "menubar", "main": "content", "complementary": "sidebar_right",
                "contentinfo": "footer", "search": "search", "dialog": "dialog", "alertdialog": "dialog",
                "tablist": "tabstrip", "toolbar": "toolbar", "menu": "menu", "menubar": "menubar", "tree": "tree",
                "list": "list", "listbox": "list", "grid": "grid", "table": "grid", "form": "form",
                "region": "content", "article": "content"}.get(role, role)

    def summary(self) -> Dict[str, Any]:
        kinds: Dict[str, int] = {}
        for r in self.regions.values():
            kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        return {**self.stats, "region_kinds": kinds, "controls": len(self.controls), "regions": len(self.regions),
                "sections": [{"kind": r["kind"], "name": r["name"][:40], "controls": r["n"],
                              "rel": [round(r["bbox"][0] / max(self.win[2], 1), 3), round(r["bbox"][1] / max(self.win[3], 1), 3),
                                      round(r["bbox"][2] / max(self.win[2], 1), 3), round(r["bbox"][3] / max(self.win[3], 1), 3)],
                              "opaque": r["opaque"]} for r in sorted(self.regions.values(), key=lambda x: (x["bbox"][1], x["bbox"][0]))
                             if r["kind"] != "window"][:60]}


# ---------------------------------------------------------------------------
# E1 deepening
# ---------------------------------------------------------------------------

def _click_js(sel: str) -> str:
    """Click through the page's own event system by selector. (CDP, not OS input.)"""
    return ("(()=>{const q=" + json.dumps(sel) + ";let e=null;try{e=document.querySelector(q)}catch(x){}"
            "if(!e)return 'missing';e.scrollIntoView({block:'center'});"
            "const r=e.getBoundingClientRect();"
            "['pointerdown','mousedown','pointerup','mouseup','click'].forEach(t=>e.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:r.left+r.width/2,clientY:r.top+r.height/2})));"
            "return 'ok'})()")


def _state(b: HeadlessChrome) -> Dict[str, Any]:
    return b.js("({url:location.href,dialogs:document.querySelectorAll('dialog[open],[role=dialog],[aria-modal=true]').length,"
                "expanded:document.querySelectorAll('[aria-expanded=true]').length,"
                "tabsSel:[...document.querySelectorAll('[role=tab][aria-selected=true]')].map(t=>t.textContent.trim().slice(0,30)),"
                "scrollY:scrollY,n:document.querySelectorAll('*').length})")


def bad_tab(name: str, strict: bool) -> bool:
    return bool(_E2_WEB.search(name or "") or (strict and _E2_AUTH.search(name or "")))


def _deepen(b: HeadlessChrome, mp: WebMapper, budget, deepen_cap: int = 14, strict: bool = False) -> None:
    from core_organs import organ_48_app_behavior_model as bm
    base_url = b.js("location.href")
    probes = 0
    tabs = [c for c in mp.controls if c["role"] == "tab" and c["_selected"] == "false" and not bad_tab(c["name"], strict)]
    bad = (lambda n: bool(_E2_WEB.search(n or "") or (strict and _E2_AUTH.search(n or "")))) 
    discl = [c for c in mp.controls if c["_expanded"] == "false" and c["role"] in ("button", "menuitem", "tab", "link", "generic")
             and not c["_in_form"] and not bad(c["name"]) and not (c["role"] == "link" and c["_href"] and not c["_href"].startswith("#"))
             and not c["name"].startswith("<")]
    stats = {"tabs_visited": 0, "tabs_restored": 0, "disclosures_opened": 0, "disclosures_closed": 0,
             "scroll_pages": 0, "navigations_prevented": 0}

    def probe(c: Dict[str, Any], kind: str) -> int:
        nonlocal probes
        if budget.reason_to_stop() in ("hard-cap", "budget") or probes >= deepen_cap:
            mp.stats["skipped"].append(f"{kind}:budget")
            return -1
        s0 = _state(b)
        if b.js(_click_js(c["_sel"])) != "ok":
            return 0
        quiet(b, 700, 90)
        s1 = _state(b)
        if s1["url"] != base_url:                                   # a click navigated: undo, never follow
            stats["navigations_prevented"] += 1
            b.navigate(base_url)
            return 0
        data = b.js(MAP_JS, timeout=15)
        new = mp.ingest(data, via=f"{kind}:{c['name'][:30]}")
        mp.transitions.append({"action": f"click:{c['name'][:40]}", "from": s0, "to": s1, "new_controls": new})
        probes += 1
        budget.credit(new)
        return new

    for c in tabs[:8]:
        if probe(c, "tab") >= 0:
            stats["tabs_visited"] += 1
    if tabs:                                                       # restore: select the originally selected tab again
        sel = next((x for x in mp.controls if x["role"] == "tab" and x["_selected"] == "true"), None)
        if sel:
            b.js(_click_js(sel["_sel"]))
            quiet(b, 400, 80)
            stats["tabs_restored"] = 1
    for c in discl[:10]:
        r = probe(c, "disclosure")
        if r >= 0:
            stats["disclosures_opened"] += 1
            if _state(b)["expanded"] > 0:                          # close what we opened (same control again)
                b.js(_click_js(c["_sel"]))
                quiet(b, 500, 80)
                stats["disclosures_closed"] += 1
        if r < 0:
            break
    # lazy content: page through, then restore the scroll position
    try:
        dh = b.js("Math.max(document.documentElement.scrollHeight, innerHeight)")
        vh = b.js("innerHeight")
        y = 0
        while y + vh < dh and stats["scroll_pages"] < 6 and budget.reason_to_stop() not in ("hard-cap",):
            y += int(vh * 0.9)
            b.js(f"window.scrollTo(0,{y})")
            quiet(b, 600, 100)
            data = b.js(MAP_JS, timeout=15)
            new = mp.ingest(data, via="scroll")
            budget.credit(new)
            stats["scroll_pages"] += 1
            nd = b.js("Math.max(document.documentElement.scrollHeight, innerHeight)")
            dh = max(dh, nd)
        b.js("window.scrollTo(0,0)")
    except Exception as exc:
        mp.stats["skipped"].append(f"scroll:{type(exc).__name__}")
    mp.stats["deepen"] = stats


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

VAULT_DIR = r"D:\new_automation\var\hojaiga\cookie_vault"


def _vault_cookies(site: str) -> List[Dict[str, Any]]:
    """Saved session from the project's cookie vault (written after a manual login). Returns [] if none."""
    try:
        with open(os.path.join(VAULT_DIR, f"{site.lower()}.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def scan_url(url: str, model=None, *, deepen: bool = True, budget=None, cookies_site: str = "",
             privacy: Optional[bool] = None) -> Dict[str, Any]:
    """Map + persist one website / web app. Same shape of result as the desktop pipeline.
    cookies_site='gmail' seeds the private browser with that saved session; authenticated scans run in
    PRIVACY mode by default (structure kept, data names redacted) with the strict probe policy."""
    from core_organs import organ_48_app_behavior_model as bm
    from core_organs import organ_50_layout_map as lm
    if not re.match(r"^[a-z]+://", url):
        url = "https://" + url
    host = urlparse(url).hostname or url
    key = "web:" + host.lower()
    model = model or bm.get_model()
    budget = budget or bm.DiscoveryBudget(base_s=15.0, extend_s=6.0, max_s=90.0, patience=5)
    rep: Dict[str, Any] = {"kind": "web", "target": url, "app_key": key, "window_mode": "headless", "phases": {}}
    t_all = time.time()
    try:
        with HeadlessChrome() as b:
            authed = False
            if cookies_site:
                n = b.set_cookies(_vault_cookies(cookies_site))
                rep["session"] = {"site": cookies_site, "cookies_loaded": n}
                authed = n > 0
            privacy_on = authed if privacy is None else privacy
            rep["privacy_mode"] = privacy_on
            t = time.time()
            nav = b.navigate(url)
            rep["phases"]["navigate_s"] = round(time.time() - t, 2)
            rep["navigation"] = nav
            if nav.get("error"):
                rep["error"] = f"navigation: {nav}"                 # nothing real to map: stop now, say so
                rep["elapsed_s"] = round(time.time() - t_all, 2)
                return rep
            if nav.get("ready") != "complete":
                rep["navigation_note"] = f"page not fully loaded ({nav.get('ready')}); mapped what exists"
            t = time.time()
            data = b.js(MAP_JS, timeout=20)
            final_url = b.js("location.href")
            if authed:
                logged_out = bool(re.search(r"accounts\.google\.com|/signin|/login|/ServiceLogin|/v3/signin", final_url, re.I)) or                     bool(re.search(r"^(sign in|log in|login)\b", data.get("title", ""), re.I))
                signin_visible = any(e["role"] in ("button", "link") and re.match(r"^(sign in|log in|login)$", (e["name"] or "").strip(), re.I)
                                     for e in data["elements"])
                rep["session"]["state"] = ("login_required (saved session expired or rejected)" if logged_out else
                                           ("not_logged_in (page still offers 'Sign in': the saved session is not active here)" if signin_visible
                                            else "authenticated"))
                rep["final_url_host"] = urlparse(final_url).hostname
            mp = WebMapper(final_url, privacy=privacy_on)
            mp.app_name = key
            mp.raw = {k: v for k, v in data.items() if k != "elements"} if privacy_on else data
            budget.credit(mp.ingest(data))
            rep["phases"]["static_map_s"] = round(time.time() - t, 2)
            mp.stats.update(static_controls=len(mp.controls), page_title=data["title"][:80], doc_px=[data["docW"], data["docH"]],
                            shadow_roots=data["shadowRoots"], iframes_same_origin=data["iframesSame"],
                            iframes_cross_origin=len(data["iframesCross"]), canvas_elements=data["hasCanvas"],
                            capped=data["capped"], map_script_ms=data["ms"])
            if data["iframesCross"]:
                mp.stats["skipped"].append(f"cross-origin-iframes:{len(data['iframesCross'])}:opaque-to-DOM")
            if data["hasCanvas"] and len(mp.controls) < 40:
                mp.stats["skipped"].append("canvas-interior:needs-ocr-or-vision")
            t = time.time()
            if deepen and not (authed and rep.get("session", {}).get("state", "").startswith("login_required")):
                _deepen(b, mp, budget, strict=privacy_on)
            rep["phases"]["deepen_s"] = round(time.time() - t, 2)
            vh = bm.app_version_hash("", hashlib.md5("|".join(data["scripts"]).encode()).hexdigest())
            model.check_version(key, vh)
            n_saved = lm.save_layout(model, key, mp, vh)
            link_after = True
            # commands: nav links, buttons, tabs — catalog trust, risk graded, never executed here
            cmds = 0
            for c in mp.controls:
                if not c["name"] or c["role"] not in ("link", "button", "tab", "menuitem", "checkbox", "switch", "searchbox", "textbox", "combobox"):
                    continue
                risk = "E2" if (_E2_WEB.search(c["name"]) or (c["_in_form"] and c["_type"] in ("submit", "image"))) else \
                    ("E1" if (c["_expanded"] is not None or c["role"] == "tab") else "EU")
                model.upsert_command(key, {"name": c["name"], "goal": c["name"], "verb": "click",
                                           "menu_path": c["path"], "risk": risk, "automation_id": c["_sel"][:100],
                                           "post": [{"kind": "ui_changed"}] if c["role"] != "link" else
                                           [{"kind": "title_contains", "value": ""}]}, source="catalog",
                                     origin="web-e0", evidence=c["_href"][:80])
                cmds += 1
            for tr in mp.transitions:
                model._conn.execute("INSERT OR IGNORE INTO bm_transitions(tid, app_key, state_from, action, effector, state_to, evidence, count, ts)"
                                    " VALUES (?,?,?,?,?,?,?,1,?)",
                                    (hashlib.md5(json.dumps(tr, sort_keys=True, default=str).encode()).hexdigest()[:14], key,
                                     json.dumps(tr["from"], default=str)[:120], tr["action"], "cdp_click",
                                     json.dumps(tr["to"], default=str)[:120], f"+{tr['new_controls']} controls", time.time()))
            model._conn.commit()
            summ = mp.summary()
            rep.update(summ)
            try:
                rep["linked"] = lm.link_knowledge(model, key)   # position <-> meaning, both directions
            except Exception as exc:
                rep["linked"] = {"error": type(exc).__name__}
            rep.update(redacted_names=mp.redacted, commands_recorded=cmds, saved=n_saved, transitions=len(mp.transitions),
                       forms=len(data["forms"]), signature=mp.structure_signature(),
                       stopped=budget.reason_to_stop() or "complete")
    except Exception as exc:
        rep["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    rep["elapsed_s"] = round(time.time() - t_all, 2)
    return rep
