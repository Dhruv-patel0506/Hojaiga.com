"""
harvest.search_browser -- the search engine's own tabs, browsed in the throw-away Edge, as a harvester.

Plain HTTP fetches are refused (image servers answer scripts with a bot challenge; YouTube answers the caption endpoint with a 429). A real browser, driven at human pace through DevTools, is not asked to prove
anything: it loads the tutorial page, the pictures render, and the picture can be read from the PAGE, element by element (a screenshot clip of the <img>), instead of being downloaded as a file.

  All tab      result links; the illustrated tutorials among them are opened in a fresh tab each
  Images tab   what the engine shows for '<app> toolbar annotated diagram / step by step screenshot': titles, the pages the pictures come from (more tutorials), the grid itself as a frame
  Videos tab   titles, durations, hosts and the timestamped chapter lines the results panel shows -- NO video is downloaded and the caption endpoint is never touched
  Tutorial     numbered steps + the screenshot rendered next to each -> before/after pairs (target found on the picture by the numbered-element scan) AND logic chains for the RAG (rag.logic_chains)

Safety: nothing is typed except the search query; no form is submitted; no account; links are only followed to read; cookie banners are declined (the privacy-preserving answer). One query per tab, a pause
between page loads.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Sequence

from .paths import harvest_dir

GOOGLE = {"all": "https://www.google.com/search?q={q}&hl=en", "images": "https://www.google.com/search?q={q}&hl=en&udm=2", "videos": "https://www.google.com/search?q={q}&hl=en&udm=7",
          "ai_mode": "https://www.google.com/search?q={q}&hl=en&udm=50"}
ENGINE = {"name": "bing"}                                                   # which engine this process reads; set by run(engine=...)
BLOCKED = {"google": False}                                                 # a refusal (a CAPTCHA / 'unusual traffic' page) ends the use of that engine for this run: it is never solved or worked around


class EngineRefused(Exception):
    pass


def refused(drv) -> bool:
    """The engine answered with a challenge instead of results: detected from the address and the page text; never answered."""
    with contextlib.suppress(Exception):
        u = (drv.url() or "").lower()
        if "/sorry/" in u or "consent.google" in u and False:
            return True
        t = (_page_text(drv) or "")[:1500].lower()
        return "unusual traffic" in t or "not a robot" in t or "captcha" in t
    return False


def table():
    return GOOGLE if ENGINE["name"] == "google" and not BLOCKED["google"] else BING


BING = {"all": "https://www.bing.com/search?q={q}&setlang=en", "images": "https://www.bing.com/images/search?q={q}&setlang=en", "videos": "https://www.bing.com/videos/search?q={q}&setlang=en"}
SKIP_HOST = re.compile(r"(youtube\.com|youtu\.be|pinterest|facebook|twitter|x\.com|reddit\.com|quora|instagram|tiktok|linkedin|amazon\.|bing\.com|microsoft\.com/en-us/p/)")
CHAPTER_RX = re.compile(r"^\s*((?:\d{1,2}:)?\d{1,2}:\d{2})\s+(.{3,90})$", re.M)

LINKS_JS = r"""(function(){var out=[];document.querySelectorAll('li.b_algo h2 a, #b_results .b_algo a[href]').forEach(function(a){var h=a.href||'';if(h.indexOf('http')===0)out.push({title:(a.innerText||'').trim().slice(0,120),url:h});});return out.slice(0,20);})()"""
IMAGES_JS = r"""(function(){var out=[];document.querySelectorAll('a.iusc').forEach(function(a){try{var m=JSON.parse(a.getAttribute('m'));out.push({title:(m.t||'').replace(/<[^>]+>/g,''),page:m.purl||'',img:m.murl||''});}catch(e){}});return out.slice(0,24);})()"""
VIDEOS_JS = r"""(function(){var out=[];document.querySelectorAll('.mc_vtvc, .dg_u, [data-vk], .vrhdata').forEach(function(c){var t=(c.innerText||'').trim().replace(/\s+/g,' ');var a=c.querySelector('a[href]');
      if(t.length>8)out.push({text:t.slice(0,200),url:a?a.href:''});});return out.slice(0,20);})()"""
LINKS_JS_GOOGLE = r"""(function(){var out=[];document.querySelectorAll('#search a:has(h3), #rso a:has(h3)').forEach(function(a){var h=a.href||'';var c=a.querySelector('cite');var cite=c?(c.innerText||''):'';
  if(h.indexOf('http')===0)out.push({title:(a.innerText||'').trim().split('\\n')[0].slice(0,120),url:h,cite:cite});});return out.slice(0,20);})()"""
STEPS_HTML_JS = "document.documentElement.outerHTML"


def _page_text(drv) -> str:
    return drv.p.call("Runtime.evaluate", {"expression": "document.body?document.body.innerText:''", "returnByValue": True}, timeout=15.0).get("result", {}).get("value") or ""


def _eval(drv, js: str, timeout: float = 20.0) -> Any:
    return drv.p.call("Runtime.evaluate", {"expression": js, "returnByValue": True}, timeout=timeout).get("result", {}).get("value")


def decline_banner(drv) -> str:
    """The privacy-preserving answer to a consent banner, whatever the site calls it (reject / decline / necessary only)."""
    from . import web_recorder as WR
    c = WR.cookie_choice(drv.controls(limit=80))
    if c is not None:
        drv.click_at(c["box"][0] + c["box"][2] / 2, c["box"][1] + c["box"][3] / 2)
        time.sleep(0.8)
        return c["name"]
    return ""


def _host_of(it: Dict[str, Any]) -> str:
    """A result's site: from its address, or - for a search engine's redirect link (google.com/goto?url=...) - from the address the result itself shows (its 'cite' line)."""
    u = it.get("url", "")
    if "/goto?" in u or "/url?" in u:
        m = re.match(r"\s*(?:https?://)?([A-Za-z0-9.-]+\.[a-z]{2,})", it.get("cite", ""))
        return m.group(1).lower() if m else ""
    return urllib.parse.urlparse(u).netloc


def search_tab(drv, tab: str, query: str) -> Dict[str, Any]:
    """One tab of the search engine: its items, read from the rendered page, and the viewport as a frame."""
    tbl = table()
    drv.navigate(tbl[tab].format(q=urllib.parse.quote_plus(query)))
    decline_banner(drv)
    if tbl is GOOGLE and refused(drv):
        BLOCKED["google"] = True
        raise EngineRefused("google answered with a challenge")
    if tbl is GOOGLE:                                                       # the result list is drawn after the page loads: wait for it (up to 8 s)
        for _ in range(16):
            if _eval(drv, "document.querySelectorAll('#search a h3, #rso a h3').length"):
                break
            time.sleep(0.5)
    time.sleep(1.0)
    out: Dict[str, Any] = {"tab": tab, "query": query, "items": []}
    if tab == "all":
        seen = set()
        for it in _eval(drv, LINKS_JS_GOOGLE if tbl is GOOGLE else LINKS_JS) or []:
            u = it["url"]
            h = _host_of(it)
            if h and h not in seen and not SKIP_HOST.search(h + " " + u if "/goto?" in u else u):
                seen.add(h)
                it["host"] = h
                out["items"].append(it)
    elif tab == "images":
        out["items"] = _eval(drv, IMAGES_JS) or []
    else:
        out["items"] = _eval(drv, VIDEOS_JS) or []
        txt = _page_text(drv)
        out["chapters"] = [{"t": m.group(1), "text": m.group(2).strip()} for m in CHAPTER_RX.finditer(txt)][:30]
    with contextlib.suppress(Exception):
        out["shot"] = drv.screenshot()
    return out


AI_JS = r"""(function(){
  function txt(e){return (e.innerText||'').replace(/[ \t]+/g,' ').replace(/\n{3,}/g,'\n\n').trim();}
  var sels=['#b_copilot','[id*=copilot i]','[class*=copilot i]','[data-tag*=Answer i]','[class*=genai i]','[class*=aisum i]','.b_ans','#b_context .b_entityTP','.b_algospacing'];
  var best=null,why='';
  for(var i=0;i<sels.length&&!best;i++){var els=[].slice.call(document.querySelectorAll(sels[i]));
    for(var j=0;j<els.length;j++){var t=txt(els[j]);if(t.length>=180&&t.split(/[.!?]\s/).length>=2&&!els[j].closest('li.b_algo')){best=els[j];why=sels[i];break;}}}
  if(!best){var res=document.querySelector('#b_results');if(res){var kids=[].slice.call(res.children);
    for(var k=0;k<kids.length&&k<6;k++){if(kids[k].classList.contains('b_algo'))break;var t2=txt(kids[k]);if(t2.length>=220&&t2.split(/[.!?]\s/).length>=3){best=kids[k];why='first block above the organic results';break;}}}}
  if(!best)return {found:false};
  var items=[].slice.call(best.querySelectorAll('li,p')).map(txt).filter(function(s){return s.length>15&&s.length<400;});
  return {found:true,selector:why,text:txt(best).slice(0,6000),items:items.slice(0,40),cites:[].slice.call(best.querySelectorAll('a[href^=http]')).map(function(a){return a.href}).slice(0,8)};})()"""
NAME_RX = re.compile(r"[\"“‘'`]([^\"”’'`]{2,32})[\"”’'`]|\*\*([^*]{2,32})\*\*")


def steps_from_summary(text: str, items: Sequence[str] = ()) -> List[Dict[str, Any]]:
    """The instruction-like sentences of a synthesized answer as steps (text, quoted control names, key combinations): the same shape a tutorial page gives the logic-chain builder."""
    from core_organs.rag import logic_chains as LC
    cand = [re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", s).strip() for s in (list(items) or re.split(r"(?<=[.!?])\s+|\n+", text))]
    imperative = re.compile(r"(?:^|[,:;]\s*|\bthen\s+|\band\s+)(?:click|select|choose|open|press|go to|navigate|tap|use|type|enter|drag|right-click|double-click|hold|check|uncheck|turn|toggle|set|add|insert|save|export|then|next)\b", re.I)
    steps = []
    seen_txt: set = set()
    for s in cand:
        s = re.split(r"\s+\|\s+", s)[0].strip()                                   # a source attribution after a bar ('... | Ten Forums | +1') is not part of the step
        k = re.sub(r"\W+", " ", s.lower()).strip()
        if k in seen_txt:                                                         # the same instruction under several cited sources is one step
            continue
        seen_txt.add(k)
        if 12 <= len(s) <= 300 and (imperative.search(s) or LC.KEY_RX.search(s) or re.match(r"^\d+[.)]", s)):
            names = [a or b for a, b in NAME_RX.findall(s)]
            steps.append({"text": s, "names": names[:4], "keys": [k if isinstance(k, str) else k[0] for k in LC.KEY_RX.findall(s)][:3], "imgs": []})
    return steps[:30]


AI_JS_GOOGLE = r"""(function(){
  function txt(e){return (e.innerText||'').replace(/[ \t]+/g,' ').replace(/\n{3,}/g,'\n\n').trim();}
  var heads=[].slice.call(document.querySelectorAll('h1,h2,h3,div,span')).filter(function(e){var t=(e.innerText||'').trim();return /^(AI Overview|AI Mode)$/i.test(t)&&e.children.length<=2;});
  for(var i=0;i<heads.length;i++){var n=heads[i];for(var k=0;k<8&&n;k++){n=n.parentElement;if(n&&txt(n).length>260){var items=[].slice.call(n.querySelectorAll('li,p')).map(txt).filter(function(s){return s.length>15&&s.length<400;});
      return {found:true,selector:'ai-heading',text:txt(n).slice(0,6000),items:items.slice(0,40),cites:[].slice.call(n.querySelectorAll('a[href^=http]')).map(function(a){return a.href}).filter(function(h){return h.indexOf('google.')<0}).slice(0,8)};}}}
  return {found:false};})()"""


def ai_summary(drv, query: str) -> Dict[str, Any]:
    if ENGINE["name"] == "google" and not BLOCKED["google"]:
        drv.navigate(GOOGLE["all"].format(q=urllib.parse.quote_plus(query)))
        decline_banner(drv)
        if refused(drv):
            BLOCKED["google"] = True
            raise EngineRefused("google answered with a challenge")
        time.sleep(3.0)
        out = _eval(drv, AI_JS_GOOGLE, timeout=20.0) or {"found": False}
        out["query"], out["engine"] = query, "google"
        if out.get("found"):
            out["steps"] = steps_from_summary(out.get("text", ""), out.get("items", []))
        return out
    return _ai_summary_bing(drv, query)


def _ai_summary_bing(drv, query: str) -> Dict[str, Any]:
    """The engine's synthesized answer (AI overview / Copilot answer block) for one query, read from the PUBLIC rendered results page of this one browser session: no account, no sign-in, no second session.
    {found: False} when the engine shows none for the query - that is a normal outcome, not an error."""
    drv.navigate(BING["all"].format(q=urllib.parse.quote_plus(query)))
    decline_banner(drv)
    time.sleep(2.5)
    out = _eval(drv, AI_JS, timeout=20.0) or {"found": False}
    out["query"] = query
    if out.get("found"):
        out["steps"] = steps_from_summary(out.get("text", ""), out.get("items", []))
    return out


SHOT_JS = r"""(function(src){var im=[].slice.call(document.images).filter(function(i){return i.currentSrc===src||i.src===src||i.getAttribute('data-src')===src||(i.getAttribute('data-lazy-src')===src)})[0];
  if(!im)return null;im.scrollIntoView({block:'center'});var r=im.getBoundingClientRect();return {x:r.left+scrollX,y:r.top+scrollY,w:r.width,h:r.height,nw:im.naturalWidth,nh:im.naturalHeight};})(%s)"""


def _load_lazy(drv, seconds: float = 6.0) -> None:
    """Scroll the page top to bottom once so lazily loaded pictures render, then back to the top."""
    t0 = time.time()
    h = _eval(drv, "document.documentElement.scrollHeight") or 0
    y = 0
    while y < min(h, 40000) and time.time() - t0 < seconds:
        y += 700
        _eval(drv, f"window.scrollTo(0,{y})")
        time.sleep(0.12)
    _eval(drv, "window.scrollTo(0,0)")
    time.sleep(0.3)


def element_shot(drv, src: str):
    """The picture of an <img> as the page RENDERS it (a screenshot clip of the element)."""
    import base64
    import io
    from PIL import Image
    box = _eval(drv, SHOT_JS % json.dumps(src))
    if not box or box["w"] < 300 or box["h"] < 160:
        return None
    r = drv.p.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True, "clip": {"x": box["x"], "y": box["y"], "width": box["w"], "height": box["h"], "scale": 1}}, timeout=25.0)
    return Image.open(io.BytesIO(base64.b64decode(r["data"]))).convert("RGB")


def read_tutorial(drv, url: str, app_name: str, root: str, app_key: str) -> Dict[str, Any]:
    """Open a tutorial in the (fresh) tab: steps from the rendered page, each step's first picture captured from the page; None-steps when it is not about the app."""
    from . import web_search_failover as W
    drv.navigate(url)
    decline_banner(drv)
    _load_lazy(drv)
    html = _eval(drv, STEPS_HTML_JS, timeout=30.0) or ""
    steps = W.parse_steps(html, drv.url() or url)
    out: Dict[str, Any] = {"url": drv.url() or url, "title": drv.title(), "steps": [], "text": "", "shots": 0}
    if len(steps) < 3 or not W.relevant(html, steps, app_name):
        return out
    out["text"] = _page_text(drv)[:20000]
    fdir = os.path.join(root, "frames", "web", app_key)
    os.makedirs(fdir, exist_ok=True)
    for st in steps[:40]:
        st = dict(st)
        st["local_imgs"] = []
        for u in st["imgs"][:2]:
            im = element_shot(drv, u)
            if im is not None:
                p = os.path.join(fdir, hashlib.sha1(im.tobytes()[:5000] + u.encode()).hexdigest()[:14] + ".jpg")
                im.save(p, "JPEG", quality=90)
                st["local_imgs"].append(p)
                out["shots"] += 1
                break
        out["steps"].append(st)
    return out


def labels_of(path: str, som_fn: Any = None, limit: int = 12) -> List[str]:
    from . import video_pipeline as VP
    som = (som_fn or VP.som_of_frame)(path)
    return [e["label"] for e in som["elements"] if e.get("label") and len(e["label"]) > 1][:limit]


def harvest_app_in_browser(b: Any, app_name: str, rag: Any = None, root: str = "", max_tutorials: int = 3, log: Any = print, som_fn: Any = None, app_key: str = "") -> Dict[str, Any]:
    """All / Images / Videos tabs, then the best tutorials, for one app. Returns the counts and what was written."""
    from core_organs.professor.adapters.cdp import CdpPage
    from core_organs.rag import logic_chains as LC
    from . import free_master_harvester as M, web_recorder as WR, web_search_failover as W, video_pipeline as VP
    root = root or harvest_dir()[0]
    som_fn = som_fn or VP.som_of_frame
    key = app_key or M.app_key_of(app_name)
    rep: Dict[str, Any] = {"app": key, "tutorials": 0, "steps": 0, "shots": 0, "pairs": 0, "chains": 0, "procedures": 0, "edges": 0, "hotkeys": 0, "playbooks": 0, "icons": 0, "image_items": 0, "video_items": 0, "chapters": 0}
    t0 = time.time()
    if rag is None:
        with contextlib.suppress(Exception):
            from core_organs import rag as _R
            rag = _R.get_rag()

    def fresh():
        old = {t["id"] for t in b.targets()}
        b.new_tab("about:blank")
        new = [t for t in b.targets() if t["id"] not in old]
        return WR.CdpDriver(CdpPage(new[-1])), (new[-1]["id"] if new else "")

    candidates: List[Dict[str, str]] = []
    for tab, q in (("all", f"{app_name} tutorial step by step with screenshots"), ("images", f"{app_name} step by step screenshot toolbar annotated"), ("videos", f"{app_name} tutorial for beginners")):
        drv, tid = fresh()
        try:
            r = search_tab(drv, tab, q)
        except Exception as exc:
            log(f"[browser] {key} {tab}: {type(exc).__name__}: {str(exc)[:70]}")
            r = {"items": []}
        if tab == "all":
            candidates += [{"url": i["url"], "title": i["title"], "host": i.get("host", "")} for i in r["items"]]
        elif tab == "images":
            rep["image_items"] = len(r["items"])
            candidates += [{"url": i["page"], "title": i["title"]} for i in r["items"] if i.get("page") and not SKIP_HOST.search(i["page"])]
            with contextlib.suppress(Exception):
                if r.get("shot") is not None:
                    r["shot"].save(os.path.join(root, "frames", f"search_images_{key}.jpg"), "JPEG", quality=85)
        else:
            rep["video_items"] = len(r["items"])
            rep["chapters"] = len(r.get("chapters", []))
            steps = [{"text": (it["text"] + (f"  <{it['url']}>" if it.get("url") else ""))[:240], "route_hint": "observe"} for it in r["items"][:12]] + [{"text": f"{c['t']} {c['text']}", "route_hint": "observe"} for c in r.get("chapters", [])[:12]]
            if rag is not None and steps:
                with contextlib.suppress(Exception):
                    rr = rag.proc.ingest_procedure(key, f"Video tutorials and chapters for {app_name}", steps, "search:videos", trust="web")
                    rep["procedures"] += rr.inserted + rr.updated
        with contextlib.suppress(Exception):
            b.close_tab(tid)
    for q in (f"how to use {app_name} step by step", f"{app_name} toolbar menu keyboard shortcuts for beginners"):      # the engine's synthesized answer (public page, this one session)
        drv, tid = fresh()
        try:
            ai = ai_summary(drv, q)
            if ai.get("found") and ai.get("steps"):
                rep["ai_summaries"] = rep.get("ai_summaries", 0) + 1
                chains = LC.build_chains(ai["steps"], [[] for _ in ai["steps"]], ai.get("text", ""))
                w = LC.write(rag, key, app_name, chains, [[] for _ in ai["steps"]], "bing:ai-summary?q=" + urllib.parse.quote_plus(q), f"AI summary: {q}")
                rep["ai_chains"] = rep.get("ai_chains", 0) + len(chains)
                rep["chains"] += len(chains)
                for k in ("procedures", "edges", "hotkeys", "playbooks"):
                    rep[k] += w.get(k, 0)
                candidates += [{"url": u, "title": ""} for u in ai.get("cites", [])]       # the pages the summary cites are tutorials to read
            else:
                rep["ai_none"] = rep.get("ai_none", 0) + 1
        except Exception as exc:
            log(f"[browser] {key} ai-summary: {type(exc).__name__}: {str(exc)[:70]}")
        with contextlib.suppress(Exception):
            b.close_tab(tid)
    seen, ranked = set(), []
    for c in candidates:                                                         # illustrated how-to / documentation hosts first, one page per host
        h = c.get("host") or urllib.parse.urlparse(c["url"]).netloc
        if not h or h in seen or SKIP_HOST.search(h + " " + c["url"] if "/goto?" in c["url"] else c["url"]):
            continue
        seen.add(h)
        ranked.append((0 if any(d in h for d in W.DOC_HOSTS) else 1, c))
    ranked.sort(key=lambda x: x[0])
    out_rows: List[Dict[str, Any]] = []
    for _rank, c in ranked[:max_tutorials * 3]:
        if rep["tutorials"] >= max_tutorials:
            break
        drv, tid = fresh()
        try:
            tut = read_tutorial(drv, c["url"], app_name, root, key)
        except Exception as exc:
            log(f"[browser] {key} tutorial {c['url'][:50]}: {type(exc).__name__}")
            tut = {"steps": []}
        with contextlib.suppress(Exception):
            b.close_tab(tid)
        if not tut["steps"]:
            continue
        rep["tutorials"] += 1
        rep["steps"] += len(tut["steps"])
        rep["shots"] += tut["shots"]
        steps = tut["steps"]
        labels = []
        crops = []
        for st in steps:
            p = (st.get("local_imgs") or [""])[0]
            labels.append(labels_of(p, som_fn) if p else [])
            crops.append(None)
        chains = LC.build_chains(steps, labels, tut["text"])
        w = LC.write(rag, key, app_name, chains, labels, tut["url"], tut["title"], crops)
        rep["chains"] += len(chains)
        for k in ("procedures", "edges", "hotkeys", "playbooks", "icons"):
            rep[k] += w.get(k, 0)
        if any(st.get("local_imgs") for st in steps):
            pr = W.pairs_from_steps(key, steps, tut["url"], root, som_fn=som_fn, max_pairs=10)
            out_rows += pr["rows"]
        log(f"[browser] {key}: {tut['url'][:70]} steps={len(steps)} shots={tut['shots']} chains={len(chains)} pairs={len(out_rows)}")
    if out_rows:
        p = os.path.join(root, "training", "ui_training_dataset.jsonl")
        seen_ids = set()
        if os.path.isfile(p):
            for line in open(p, encoding="utf-8"):
                with contextlib.suppress(Exception):
                    seen_ids.add(json.loads(line)["meta"]["pair_id"])
        new = [r for r in out_rows if r["meta"]["pair_id"] not in seen_ids]
        with open(p, "a", encoding="utf-8") as f:
            for r in new:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        rep["pairs"] = len(new)
    rep["seconds"] = round(time.time() - t0, 1)
    return rep


def run(apps: Sequence[str], max_tutorials: int = 3, log: Any = print, app_keys: Optional[Dict[str, str]] = None, engine: str = "bing", browser: str = "") -> Dict[str, Any]:
    from . import local_recorder as LR
    from core_organs.professor.adapters.cdp import CdpBrowser
    ENGINE["name"] = engine
    out = {"apps": [], "engine": engine}
    with LR.OwnedApp(browser or ("Google Chrome" if engine == "google" else "Microsoft Edge")) as app:
        b = CdpBrowser((getattr(app, "info", {}) or {}).get("cdp_port"))
        b.wait(15.0)
        for a in apps:
            try:
                r = harvest_app_in_browser(b, a, max_tutorials=max_tutorials, log=log, app_key=(app_keys or {}).get(a, ""))
            except Exception as exc:
                r = {"app": a, "error": f"{type(exc).__name__}: {str(exc)[:100]}"}
            out["apps"].append(r)
            log(json.dumps({k: r.get(k) for k in ("app", "tutorials", "steps", "shots", "pairs", "chains", "procedures", "edges", "hotkeys", "playbooks", "image_items", "video_items", "chapters", "seconds", "error")}))
    return out
