"""
harvest.web_recorder -- training pairs and RAG knowledge from WEBSITES and WEB APPS, recorded by a bot in a throw-away browser, with the answer known by construction.

The browser (Edge / Chrome, a throw-away profile, a DevTools port; the person's own browser is never touched) tells us exactly what is on the page: every interactive control's name and role from the accessibility
tree and its box from the DOM. The bot loads a page, declines the cookie banner (the PRIVACY-PRESERVING answer: reject / decline / necessary only, never accept), then clicks the safe controls one by one --
through DevTools mouse events, never the person's mouse -- and keeps a BEFORE / AFTER picture pair whenever the picture changed. The target is the numbered element (the same scan the model reads) whose box contains the
DOM box of the control, so the pair has the exact format of every other source; prompt format v2 (control names + zoomed strips) is written next to it. Nothing is typed into a form, nothing is submitted, nothing leaves
the site: controls named like sign-in / purchase / subscribe / delete / post / upload / download are never operated, and a link that leaves the site is not followed.

`record_site(driver, url, ...)` takes any driver with the small interface below (CdpDriver for a real browser, a fake in tests).
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional

from .paths import harvest_dir

DENY = re.compile(r"\b(sign|log ?in|log ?out|register|create account|account|password|buy|purchase|checkout|cart|basket|order|pay|donate|subscribe|newsletter|delete|remove|post|publish|send|submit|upload|download|install|"
                  r"share|follow|like|dislike|report|accept|agree|consent|allow all|buy now|add to|book|reserve|apply|join|contact|call|install app|get the app|open|import|export|save|file|print|camera|microphone|location|notifications?)\b", re.I)
REJECT = re.compile(r"^(reject( all)?|decline( all)?|only (necessary|essential)( cookies)?|necessary( cookies)? only|refuse( all)?|no,? thanks|deny( all)?|continue without accepting|manage preferences)$", re.I)
CLOSE = re.compile(r"^(close|dismiss|not now|no thanks|maybe later|skip|got it)$", re.I)
VIEWPORT = (1280, 800)

# A curated starting set (DATA): public pages that need no sign-in. Websites are mostly prose + navigation; web apps are interactive pages. The domain of each is still DECIDED from the page by rag.domains.
SITES_WEBSITE = ["https://en.wikipedia.org/wiki/Main_Page", "https://developer.mozilla.org/en-US/", "https://docs.python.org/3/", "https://www.w3schools.com/", "https://docs.github.com/en", "https://learn.microsoft.com/en-us/",
                 "https://www.bbc.com/news", "https://www.nasa.gov/", "https://archive.org/", "https://www.gutenberg.org/", "https://www.geeksforgeeks.org/", "https://www.howtogeek.com/", "https://support.mozilla.org/en-US/",
                 "https://www.python.org/"]
SITES_WEBAPP = ["https://excalidraw.com/", "https://www.desmos.com/calculator", "https://www.geogebra.org/graphing", "https://regexr.com/", "https://squoosh.app/", "https://app.diagrams.net/", "https://www.openstreetmap.org/",
                "https://www.youtube.com/", "https://stackblitz.com/", "https://codepen.io/pen/", "https://jsfiddle.net/", "https://tldraw.com/", "https://www.photopea.com/", "https://playground.tensorflow.org/"]


class CdpDriver:
    """A real browser through DevTools. controls() -> [{name, role, box:(x,y,w,h), href}]; click_at / key go to the PAGE (DevTools input events), not to the operating system."""

    def __init__(self, page: Any):
        self.p = page
        for m, prm in (("Page.enable", {}), ("DOM.enable", {}), ("Accessibility.enable", {}), ("Emulation.setFocusEmulationEnabled", {"enabled": True}),
                       ("Emulation.setDeviceMetricsOverride", {"width": VIEWPORT[0], "height": VIEWPORT[1], "deviceScaleFactor": 1, "mobile": False})):
            with contextlib.suppress(Exception):
                self.p.call(m, prm)

    def navigate(self, url: str) -> bool:
        ok, _ = self.p.navigate(url)
        t_end = time.time() + 15
        while time.time() < t_end:
            with contextlib.suppress(Exception):
                if self.p.call("Runtime.evaluate", {"expression": "document.readyState", "returnByValue": True}).get("result", {}).get("value") in ("complete", "interactive"):
                    break
            time.sleep(0.3)
        time.sleep(1.2)
        return ok

    def url(self) -> str:
        return self.p.title_url()[1]

    def title(self) -> str:
        return self.p.title_url()[0]

    def screenshot(self):
        from PIL import Image
        try:
            r = self.p.call("Page.captureScreenshot", {"format": "png", "fromSurface": True}, timeout=25.0)
        except Exception:                                                    # a page in a parked window may not be producing frames: wake its lifecycle and ask once more (MEASURED: the 2nd site timed out)
            with contextlib.suppress(Exception):
                self.p.call("Page.setWebLifecycleState", {"state": "active"})
                self.p.call("Page.bringToFront")
            time.sleep(1.0)
            r = self.p.call("Page.captureScreenshot", {"format": "png", "fromSurface": True}, timeout=25.0)
        return Image.open(io.BytesIO(base64.b64decode(r["data"]))).convert("RGB")

    DOM_JS = r"""(function(){var sel='a[href],button,[role=button],[role=tab],[role=menuitem],[role=link],summary,input[type=checkbox],input[type=radio],select,[aria-haspopup],[tabindex]';
      var out=[];var seen=new Set();document.querySelectorAll(sel).forEach(function(e){var r=e.getBoundingClientRect();if(r.width<8||r.height<8||r.left<0||r.top<0||r.right>innerWidth||r.bottom>innerHeight)return;
      var st=getComputedStyle(e);if(st.visibility==='hidden'||st.display==='none'||+st.opacity===0)return;
      var name=(e.getAttribute('aria-label')||e.innerText||e.title||e.alt||e.value||'').trim().replace(/\s+/g,' ').slice(0,60);if(!name)return;
      var role=(e.getAttribute('role')||(e.tagName==='A'?'link':e.tagName.toLowerCase())).toLowerCase();var k=role+'|'+name.toLowerCase();if(seen.has(k))return;seen.add(k);
      var a=e.closest&&e.closest('a');out.push({name:name,role:role,x:r.left,y:r.top,w:r.width,h:r.height,href:(e.href||(a&&a.href)||'')});});return out.slice(0,200);})()"""

    FEATURES_JS = r"""(function(){var t=(document.body&&document.body.innerText||'');return {text_chars:t.length,scripts:document.scripts.length,
      interactive:document.querySelectorAll('button,input,select,textarea,[role=button],[role=tab],[role=menuitem],[role=dialog],[role=textbox],[aria-haspopup]').length,
      canvas:document.querySelectorAll('canvas').length,articles:document.querySelectorAll('article,p').length,forms:document.forms.length,
      manifest:!!document.querySelector('link[rel~=manifest]'),
      framework_shell:!!document.querySelector('#root,#app,#__next,#__nuxt,[ng-app],[data-reactroot],app-root')&&t.length<1500};})()"""

    def page_features(self) -> Dict[str, Any]:
        """The features rg.domains.classify_page expects, read from the RENDERED page."""
        return self.p.call("Runtime.evaluate", {"expression": self.FEATURES_JS, "returnByValue": True}, timeout=15.0).get("result", {}).get("value") or {}

    def controls_dom(self, limit: int = 120) -> List[Dict[str, Any]]:
        """The same list from the DOM itself (what a page that busies its accessibility tree still shows): name, role, box and link target of every visible interactive element."""
        r = self.p.call("Runtime.evaluate", {"expression": self.DOM_JS, "returnByValue": True}, timeout=20.0).get("result", {}).get("value") or []
        return [{"name": e["name"], "role": e["role"], "box": (e["x"], e["y"], e["w"], e["h"]), "href": e.get("href", "")} for e in r][:limit]

    def controls(self, limit: int = 120) -> List[Dict[str, Any]]:
        try:
            return self._controls_ax(limit)
        except Exception:                                                    # MEASURED: heavy single-page apps time out on Accessibility.getFullAXTree
            return self.controls_dom(limit)

    def _controls_ax(self, limit: int = 120) -> List[Dict[str, Any]]:
        out = []
        for v in self.p.verbs(limit=limit * 2):
            try:
                q = self.p.call("DOM.getBoxModel", {"backendNodeId": v["node"]})["model"]["content"]
            except Exception:
                continue
            xs, ys = q[0::2], q[1::2]
            x, y, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
            if w < 8 or h < 8 or x < 0 or y < 0 or x + w > VIEWPORT[0] or y + h > VIEWPORT[1]:
                continue
            href = ""
            with contextlib.suppress(Exception):
                oid = self.p.call("DOM.resolveNode", {"backendNodeId": v["node"]})["object"]["objectId"]
                href = self.p.call("Runtime.callFunctionOn", {"objectId": oid, "functionDeclaration": "function(){return this.href||(this.closest&&this.closest('a')?this.closest('a').href:'')||''}", "returnByValue": True}).get("result", {}).get("value", "") or ""
            out.append({"name": v["label"], "role": v["role"], "box": (x, y, w, h), "href": href})
            if len(out) >= limit:
                break
        return out

    def click_at(self, x: float, y: float) -> None:
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.p.call("Input.dispatchMouseEvent", {"type": t, "x": x, "y": y, "button": "left", "clickCount": 1, "buttons": 1 if t == "mousePressed" else 0})
            time.sleep(0.05)

    def key(self, name: str) -> None:
        self.p.key(name)

    def back(self) -> None:
        self.p.history(-1)
        time.sleep(1.0)


# ---------------------------------------------------------------------------------------------------------------------------------- pure decisions (tested offline)
def host_of(url: str) -> str:
    return re.sub(r"^www\.", "", urllib.parse.urlparse(url).netloc.lower())


def operable(c: Dict[str, Any], page_host: str) -> bool:
    """A control the bot may click: named, not a sign-in / purchase / post / download ..., and not a link that leaves the site."""
    n = str(c.get("name", "")).strip()
    if not n or len(n) > 60 or DENY.search(n):
        return False
    h = c.get("href") or ""
    if h:
        if h.startswith(("mailto:", "tel:", "javascript:")):
            return False
        hh = host_of(h)
        if hh and hh != page_host and not hh.endswith("." + page_host) and not page_host.endswith("." + hh):
            return False
    return True


def cookie_choice(controls: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The privacy-preserving answer to a consent banner: reject / decline / necessary-only; never accept."""
    for c in controls:
        if REJECT.match(str(c.get("name", "")).strip()):
            return c
    return None


def pick_controls(controls: List[Dict[str, Any]], page_host: str, limit: int) -> List[Dict[str, Any]]:
    """Operable controls, one per name, spread through the page (not just the first ones)."""
    seen, ok = set(), []
    for c in controls:
        k = (c["name"].lower(), c["role"])
        if k in seen or not operable(c, page_host):
            continue
        seen.add(k)
        ok.append(c)
    if len(ok) <= limit:
        return ok
    step = len(ok) / float(limit)
    return [ok[int(i * step)] for i in range(limit)]


def _same(a, b, thr: int = 24, min_px: int = 80) -> bool:
    import numpy as np
    if a.size != b.size:
        return False
    d = np.abs(np.asarray(a.convert("L"), dtype=np.int16) - np.asarray(b.convert("L"), dtype=np.int16)) > thr
    return int(d.sum()) < min_px


# ---------------------------------------------------------------------------------------------------------------------------------- recording
def record_site(driver: Any, url: str, domain: str = "website", max_actions: int = 20, root: str = "", out_jsonl: str = "", rag: Any = None, som_fn: Any = None, settle_s: float = 1.0) -> Dict[str, Any]:
    from . import local_recorder as LR, video_explain as VE, video_pipeline as VP
    from core_organs.rag import domains as DM
    root = root or harvest_dir()[0]
    out_jsonl = out_jsonl or os.path.join(root, "training", "ui_training_dataset.jsonl")
    os.makedirs(os.path.dirname(out_jsonl), exist_ok=True)
    som_fn = som_fn or VP.som_of_frame
    host = host_of(url)
    key = DM.key_for(domain if domain in DM.DOMAINS else "website", url)          # 'auto' (decided from the rendered page below) starts as a website
    rep: Dict[str, Any] = {"url": url, "key": key, "domain": domain, "actions": 0, "pairs": 0, "no_change": 0, "navigated": 0, "skipped_unsafe": 0, "cookie_banner": "", "controls": 0, "seconds": 0.0}
    t0 = time.time()
    plog = None
    if rag is not None:
        with contextlib.suppress(Exception):
            from core_organs import artist_memory as AM
            plog = AM.PaintLogger(rag, app_key=key, write_pairs=False, run_id=f"web-{host}-{int(time.time())}")
            DM.register(rag, key, domain, {"url": url, "recorded": time.strftime("%Y-%m-%d")})
    seen_ids = LR._existing_pair_ids(out_jsonl)
    fdir = os.path.join(root, "frames", "web_" + re.sub(r"[^a-z0-9]+", "_", host))
    os.makedirs(fdir, exist_ok=True)

    def save(img, tag: str) -> str:
        p = os.path.join(fdir, f"{hashlib.sha1((tag + str(time.time())).encode()).hexdigest()[:10]}_{tag}.jpg")
        img.save(p, "JPEG", quality=90)
        return p

    def emit(pre, post, c: Dict[str, Any], ctrls: List[Dict[str, Any]], kind_extra: Dict[str, Any]) -> bool:
        goal = LR.goal_for(c["name"], "ButtonControl" if c["role"] == "button" else "HyperlinkControl")
        ppre, ppost = save(pre, "pre"), save(post, "post")
        som = som_fn(ppre)
        el = LR.element_at(som, tuple(c["box"]))
        if el is None:
            for pth in (ppre, ppost):
                with contextlib.suppress(Exception):
                    os.remove(pth)
            return False
        pid = hashlib.sha1(f"{key}|{goal}|{hashlib.sha1(pre.tobytes()).hexdigest()}".encode()).hexdigest()[:16]
        if pid in seen_ids:
            return False
        seen_ids.add(pid)
        action = [{"step": 1, "action": "click", "target_id": el["id"], "hotkey": None, "text": None, "verify_expectation": "the screen changes"}]
        meta = dict({"source": "web_dom", "source_ref": url, "uia_name": c["name"], "uia_type": c["role"], "domain": domain, "ui_check": "browser DOM"}, **kind_extra)
        row = VE.build_row(root, key, "web_" + hashlib.sha1(url.encode()).hexdigest()[:8], {"t": float(rep["actions"]), "pre": ppre, "post": ppost, "bbox": None}, som, goal, action, pid, True, True, meta)
        with open(out_jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        with contextlib.suppress(Exception):
            v2 = LR._v2_row(row, pre, som, [{"name": x["name"], "box": list(x["box"])} for x in ctrls], root, ppre)
            with open(out_jsonl.replace(".jsonl", "_v2.jsonl"), "a", encoding="utf-8") as f2:
                f2.write(json.dumps(v2, ensure_ascii=False) + "\n")
        if plog is not None:
            with contextlib.suppress(Exception):
                plog.hook({"kind": "click", "name": c["name"], "type": "ButtonControl", "box": tuple(c["box"]), "pre": pre, "post": post, "controls": [{"name": x["name"], "type": "ButtonControl"} for x in ctrls], "origin": (0, 0)})
        rep["pairs"] += 1
        return True

    driver.navigate(url)
    if domain in ("", "auto", None) and hasattr(driver, "page_features"):
        with contextlib.suppress(Exception):                                   # the rendered page decides (MEASURED: judged from raw HTML, six single-page apps looked like websites)
            c_live = DM.classify_page(driver.page_features())
            domain = c_live["domain"]
            rep["classified_live"] = c_live["score"]
        key = DM.key_for(domain or "website", url)
        rep["domain"], rep["key"] = domain or "website", key
        domain = domain or "website"
        if rag is not None:
            with contextlib.suppress(Exception):
                DM.register(rag, key, domain, {"url": url, "live_score": rep.get("classified_live")})
    ctrls = driver.controls()
    rep["controls"] = len(ctrls)
    banner = cookie_choice(ctrls)
    if banner is not None:                                                  # the privacy-preserving answer, recorded as a pair like any other action
        pre = driver.screenshot()
        driver.click_at(banner["box"][0] + banner["box"][2] / 2, banner["box"][1] + banner["box"][3] / 2)
        time.sleep(settle_s)
        post = driver.screenshot()
        rep["cookie_banner"] = banner["name"]
        if not _same(pre, post):
            emit(pre, post, banner, ctrls, {"web_role": "cookie_banner"})
        ctrls = driver.controls()
    base_url = driver.url()
    todo = pick_controls(ctrls, host, max_actions)
    rep["skipped_unsafe"] = sum(1 for c in ctrls if not operable(c, host))
    for c in todo:
        if time.time() - t0 > 600:
            break
        if driver.url() != base_url:
            driver.navigate(base_url)
            ctrls = driver.controls()
            c = next((x for x in ctrls if x["name"] == c["name"] and x["role"] == c["role"]), None)
            if c is None:
                continue
        pre = driver.screenshot()
        rep["actions"] += 1
        driver.click_at(c["box"][0] + c["box"][2] / 2, c["box"][1] + c["box"][3] / 2)
        time.sleep(settle_s)
        moved = driver.url() != base_url
        post = driver.screenshot()
        if _same(pre, post) and not moved:
            rep["no_change"] += 1
            continue
        rep["navigated"] += 1 if moved else 0
        emit(pre, post, c, ctrls, {"navigated": moved})
        if moved:
            driver.back()
        else:
            driver.key("Escape")
            time.sleep(0.3)
    rep["seconds"] = round(time.time() - t0, 1)
    return rep


def record_sites(urls: List[str], domain_hint: Optional[Dict[str, str]] = None, max_actions: int = 20, log: Any = print) -> Dict[str, Any]:
    """Each URL in a fresh throw-away browser tab of one owned Edge. The domain of each (website | web_app) is decided from the page itself unless given."""
    from . import local_recorder as LR
    from core_organs.professor.adapters.cdp import CdpBrowser
    from core_organs.rag import domains as DM
    from core_organs import rag as _R
    rag = _R.get_rag()
    out: Dict[str, Any] = {"sites": [], "pairs": 0}
    with LR.OwnedApp("Microsoft Edge") as app:
        port = (getattr(app, "info", {}) or {}).get("cdp_port")
        b = CdpBrowser(port)
        b.wait(15.0)
        for u in urls:
            dom = (domain_hint or {}).get(u) or "auto"                          # decided from the rendered page inside record_site
            old_ids = {t["id"] for t in b.targets()}
            ok, _msg = b.new_tab("about:blank")                              # a FRESH tab per site: one heavy page must not poison the next (MEASURED: 12 sites in a row timed out after one)
            new = [t for t in b.targets() if t["id"] not in old_ids]
            try:
                from core_organs.professor.adapters.cdp import CdpPage
                pg = CdpPage(new[-1]) if new else b.page()
                drv = CdpDriver(pg)
                r = record_site(drv, u, dom, max_actions=max_actions, rag=rag)
            except Exception as exc:
                r = {"url": u, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
            with contextlib.suppress(Exception):
                if new:
                    b.close_tab(new[-1]["id"])
            out["sites"].append(r)
            out["pairs"] += r.get("pairs", 0)
            log(json.dumps({k: r.get(k) for k in ("url", "domain", "actions", "pairs", "no_change", "navigated", "cookie_banner", "seconds", "error")}))
    return out
